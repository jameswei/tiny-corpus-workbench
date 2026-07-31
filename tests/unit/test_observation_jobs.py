from __future__ import annotations

import json
import tempfile
import threading
import time
import unittest
from dataclasses import FrozenInstanceError
from pathlib import Path

from tiny_corpus_workbench.application.observation import OBSERVATION_STAGES
from tiny_corpus_workbench.application.observation_jobs import (
    JobInput,
    ObservationBusyError,
    ObservationJobManager,
)
from tiny_corpus_workbench.application.workbench import RefreshResult
from tiny_corpus_workbench.domain import InputError
from tiny_corpus_workbench.workbench_projection import empty_projection


def wait_for_terminal(manager: ObservationJobManager):
    deadline = time.monotonic() + 5
    while time.monotonic() < deadline:
        job = manager.snapshot()
        if job is not None and job.state in {"COMPLETED", "FAILED"}:
            return job
        time.sleep(0.01)
    raise AssertionError("job did not reach a terminal state")


class FakeState:
    def __init__(self, workspace: Path, *, refresh_succeeds: bool = True) -> None:
        self.workspace = workspace
        self.refresh_succeeds = refresh_succeeds
        self.projection = empty_projection()
        self.projection_before_failure = self.projection
        self.observation_id: str | None = None
        self.run_id: str | None = None
        self.refresh_calls = 0

    def refresh(self) -> RefreshResult:
        self.refresh_calls += 1
        if not self.refresh_succeeds:
            return RefreshResult(False, "candidate records are invalid")
        if self.observation_id is not None:
            projection = empty_projection()
            projection.projection["records"] = [
                {
                    "record_key": "a" * 64,
                    "kind": "OBSERVATION",
                    "run_id": self.run_id,
                    "primary_identity": {
                        "name": "observation_id",
                        "value": self.observation_id,
                    },
                }
            ]
            self.projection = projection
        return RefreshResult(True, None)


class ObservationJobTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temporary = tempfile.TemporaryDirectory()
        self.workspace = Path(self.temporary.name)
        self.source = self.workspace / "source.md"
        self.source.write_text("# Source\n", "utf-8")
        self.input = JobInput(
            "GUIDED", "source.md", "text/markdown", self.source.stat().st_size, "b" * 64
        )
        self.managers: list[ObservationJobManager] = []

    def tearDown(self) -> None:
        for manager in self.managers:
            manager.shutdown()
        self.temporary.cleanup()

    def manager(self, state, observe) -> ObservationJobManager:
        manager = ObservationJobManager(
            state, self.workspace / "models", observe_service=observe
        )
        self.managers.append(manager)
        return manager

    def publisher(self, state: FakeState, status: str = "SUCCESS"):
        observation_id = f"{status.lower()}-observation"

        def observe(source, output, models, progress):
            for stage in OBSERVATION_STAGES:
                progress(stage)
            published = output / observation_id
            published.mkdir(parents=True)
            (published / "manifest.json").write_text(
                json.dumps(
                    {
                        "status": status,
                        "observation_id": observation_id,
                        "run_id": f"{observation_id}-run",
                    }
                ),
                "utf-8",
            )
            state.observation_id = observation_id
            state.run_id = f"{observation_id}-run"
            return object(), published

        return observe

    def test_completed_snapshot_is_immutable_and_resolves_record_key(self) -> None:
        state = FakeState(self.workspace)
        manager = self.manager(state, self.publisher(state, "PARTIAL_SUCCESS"))
        accepted = manager.accept(self.source, self.input)
        terminal = wait_for_terminal(manager)

        self.assertEqual(accepted.state, "QUEUED")
        self.assertEqual(terminal.state, "COMPLETED")
        self.assertIsNone(terminal.stage)
        self.assertEqual(terminal.observation.status, "PARTIAL_SUCCESS")
        self.assertEqual(terminal.observation.record_key, "a" * 64)
        self.assertEqual(terminal.refresh.status, "READY")
        self.assertIsNone(terminal.error)
        with self.assertRaises(FrozenInstanceError):
            terminal.state = "FAILED"

    def test_all_real_stages_are_visible_in_order(self) -> None:
        state = FakeState(self.workspace)
        manager_holder = {}
        seen = []

        def observe(source, output, models, progress):
            for stage in OBSERVATION_STAGES:
                progress(stage)
                seen.append(manager_holder["manager"].snapshot().stage)
            published = output / "staged"
            published.mkdir(parents=True)
            (published / "manifest.json").write_text(
                json.dumps(
                    {
                        "status": "SUCCESS",
                        "observation_id": "staged",
                        "run_id": "staged-run",
                    }
                ),
                "utf-8",
            )
            state.observation_id = "staged"
            state.run_id = "staged-run"
            return object(), published

        manager = self.manager(state, observe)
        manager_holder["manager"] = manager
        manager.accept(self.source, self.input)
        wait_for_terminal(manager)
        self.assertEqual(seen, list(OBSERVATION_STAGES))

    def test_job_stays_queued_until_first_real_progress_callback(self) -> None:
        state = FakeState(self.workspace)
        entered_service = threading.Event()
        allow_first_callback = threading.Event()
        first_callback_done = threading.Event()
        finish_service = threading.Event()

        def observe(source, output, models, progress):
            entered_service.set()
            allow_first_callback.wait(5)
            progress("PREPARING_SOURCE")
            first_callback_done.set()
            finish_service.wait(5)
            for stage in OBSERVATION_STAGES[1:]:
                progress(stage)
            published = output / "first-stage"
            published.mkdir(parents=True)
            (published / "manifest.json").write_text(
                json.dumps(
                    {
                        "status": "SUCCESS",
                        "observation_id": "first-stage",
                        "run_id": "first-stage-run",
                    }
                ),
                "utf-8",
            )
            state.observation_id = "first-stage"
            state.run_id = "first-stage-run"
            return object(), published

        manager = self.manager(state, observe)
        manager.accept(self.source, self.input)
        self.assertTrue(entered_service.wait(2))
        before = manager.snapshot()
        self.assertEqual((before.state, before.stage), ("QUEUED", None))

        allow_first_callback.set()
        self.assertTrue(first_callback_done.wait(2))
        first = manager.snapshot()
        self.assertEqual(
            (first.state, first.stage),
            ("RUNNING", "PREPARING_SOURCE"),
        )
        finish_service.set()
        self.assertEqual(wait_for_terminal(manager).state, "COMPLETED")

    def test_repeated_observation_resolves_the_new_published_run(self) -> None:
        class RepeatedState(FakeState):
            def refresh(inner_self):
                inner_self.refresh_calls += 1
                projection = empty_projection()
                projection.projection["records"] = [
                    {
                        "record_key": "a" * 64,
                        "kind": "OBSERVATION",
                        "run_id": "prior-run",
                        "primary_identity": {
                            "name": "observation_id",
                            "value": "shared-observation",
                        },
                    },
                    {
                        "record_key": "b" * 64,
                        "kind": "OBSERVATION",
                        "run_id": "new-run",
                        "primary_identity": {
                            "name": "observation_id",
                            "value": "shared-observation",
                        },
                    },
                ]
                inner_self.projection = projection
                return RefreshResult(True, None)

        state = RepeatedState(self.workspace)

        def observe(source, output, models, progress):
            for stage in OBSERVATION_STAGES:
                progress(stage)
            published = output / "new-run"
            published.mkdir(parents=True)
            (published / "manifest.json").write_text(
                json.dumps(
                    {
                        "status": "SUCCESS",
                        "observation_id": "shared-observation",
                        "run_id": "new-run",
                    }
                ),
                "utf-8",
            )
            return object(), published

        manager = self.manager(state, observe)
        manager.accept(self.source, self.input)
        terminal = wait_for_terminal(manager)
        self.assertEqual(terminal.state, "COMPLETED")
        self.assertEqual(terminal.observation.observation_id, "shared-observation")
        self.assertEqual(terminal.observation.record_key, "b" * 64)

    def test_busy_rejection_and_terminal_replacement(self) -> None:
        state = FakeState(self.workspace)
        started = threading.Event()
        release = threading.Event()

        def observe(source, output, models, progress):
            started.set()
            release.wait(5)
            return self.publisher(state)(source, output, models, progress)

        manager = self.manager(state, observe)
        first = manager.accept(self.source, self.input)
        self.assertTrue(started.wait(2))
        with self.assertRaises(ObservationBusyError):
            manager.accept(self.source, self.input)
        release.set()
        wait_for_terminal(manager)
        second = manager.accept(self.source, self.input)
        self.assertNotEqual(first.job_id, second.job_id)
        wait_for_terminal(manager)

    def test_prepublication_failure_has_sanitized_typed_error(self) -> None:
        state = FakeState(self.workspace)

        def observe(source, output, models, progress):
            raise InputError("invalid\nsource")

        manager = self.manager(state, observe)
        manager.accept(self.source, self.input)
        terminal = wait_for_terminal(manager)
        self.assertEqual(terminal.state, "FAILED")
        self.assertIsNone(terminal.observation)
        self.assertIsNone(terminal.refresh)
        self.assertEqual(terminal.error.code, "OBSERVATION_INPUT_FAILED")
        self.assertEqual(terminal.error.message, "invalid source")

    def test_failed_record_is_completed_and_refresh_failure_retains_projection(
        self,
    ) -> None:
        state = FakeState(self.workspace, refresh_succeeds=False)
        manager = self.manager(state, self.publisher(state, "FAILED"))
        manager.accept(self.source, self.input)
        terminal = wait_for_terminal(manager)
        self.assertEqual(terminal.state, "COMPLETED")
        self.assertEqual(terminal.observation.status, "FAILED")
        self.assertIsNone(terminal.observation.record_key)
        self.assertEqual(terminal.refresh.status, "FAILED")
        self.assertIs(state.projection, state.projection_before_failure)

    def test_shutdown_stops_accepting_and_waits_for_active_worker(self) -> None:
        state = FakeState(self.workspace)
        started = threading.Event()
        release = threading.Event()

        def observe(source, output, models, progress):
            started.set()
            release.wait(5)
            return self.publisher(state)(source, output, models, progress)

        manager = self.manager(state, observe)
        manager.accept(self.source, self.input)
        self.assertTrue(started.wait(2))
        closing = threading.Thread(target=manager.shutdown)
        closing.start()
        time.sleep(0.05)
        self.assertTrue(closing.is_alive())
        with self.assertRaises(ObservationBusyError):
            manager.accept(self.source, self.input)
        release.set()
        closing.join(5)
        self.assertFalse(closing.is_alive())
        self.assertEqual(manager.snapshot().state, "COMPLETED")


if __name__ == "__main__":
    unittest.main()
