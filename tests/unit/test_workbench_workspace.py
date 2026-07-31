from __future__ import annotations

import json
import os
import shutil
import tempfile
import threading
import time
import unittest
from pathlib import Path
from unittest.mock import patch

from tiny_corpus_workbench.application.workbench import (
    WorkbenchState,
    discover_workspace,
)
from tiny_corpus_workbench.domain import InputError
from tiny_corpus_workbench.workbench_projection import empty_projection
from tiny_corpus_workbench.workbench_records import admit_records
from tests.unit.workbench_test_support import PublishedObservation


class WorkbenchWorkspaceTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.published = PublishedObservation()

    @classmethod
    def tearDownClass(cls) -> None:
        cls.published.close()

    def setUp(self) -> None:
        self.temporary = tempfile.TemporaryDirectory(
            dir=Path(tempfile.gettempdir()).resolve()
        )
        self.workspace = Path(self.temporary.name)

    def tearDown(self) -> None:
        self.temporary.cleanup()

    def publish_copy(self, relative: str) -> Path:
        target = self.workspace / relative / self.published.root.name
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copytree(self.published.root, target)
        return target

    def test_missing_workspace_and_parents_are_created_with_empty_projection(
        self,
    ) -> None:
        missing = self.workspace / "missing" / "nested"
        state = WorkbenchState(missing)
        expected = empty_projection()
        self.assertTrue(missing.is_dir())
        self.assertEqual(state.refresh_status, "READY")
        self.assertEqual(state.projection.projection, expected.projection)
        self.assertEqual(
            state.projection_object()["counts"],
            {
                "record_count": 0,
                "top_level_record_count": 0,
                "contained_record_count": 0,
            },
        )
        with self.assertRaises(InputError):
            admit_records([])

    def test_existing_unreadable_workspace_is_rejected(self) -> None:
        with patch(
            "tiny_corpus_workbench.application.workbench.os.access",
            return_value=False,
        ), self.assertRaisesRegex(
            InputError, "workspace must be readable, writable, and searchable"
        ):
            WorkbenchState(self.workspace)

    def test_existing_non_directory_workspace_is_rejected(self) -> None:
        target = self.workspace / "workspace"
        target.write_text("not a directory", "utf-8")
        with self.assertRaisesRegex(InputError, "workspace must be a directory"):
            WorkbenchState(target)

    def test_discovery_is_fixed_nested_deterministic_and_excludes_staging(self) -> None:
        second = self.publish_copy("extraction-observatory/z")
        first = self.publish_copy("extraction-observatory/a/nested")
        self.publish_copy("inputs/ignored")
        self.publish_copy("unrelated/ignored")
        self.publish_copy("extraction-observatory/.staging-next/ignored")
        (self.workspace / "extraction-observatory" / "wrong.json").write_text(
            "{}", "utf-8"
        )
        self.assertEqual(discover_workspace(self.workspace), [first, second])

    def test_refresh_swaps_only_after_full_success_and_clears_error(self) -> None:
        target = self.publish_copy("extraction-observatory/one")
        state = WorkbenchState(self.workspace)
        original_projection = state.projection
        descriptor = next(iter(original_projection.details.values()))["artifacts"][0]
        captured = original_projection.artifact_contents[descriptor["artifact_key"]]
        manifest_path = target / "manifest.json"
        original_manifest = manifest_path.read_bytes()

        manifest_path.write_bytes(b"not json")
        failed = state.refresh()
        self.assertFalse(failed.succeeded)
        self.assertIn("extraction-observatory/one", failed.message)
        self.assertIs(state.projection, original_projection)
        self.assertEqual(
            state.projection.artifact_contents[descriptor["artifact_key"]], captured
        )
        self.assertEqual(state.projection_object()["refresh"]["status"], "FAILED")

        manifest_path.write_bytes(original_manifest)
        succeeded = state.refresh()
        self.assertTrue(succeeded.succeeded)
        self.assertEqual(state.refresh_status, "READY")
        self.assertIsNone(state.refresh_message)
        self.assertEqual(state.projection_object()["refresh"]["message"], None)

    def test_response_limit_failure_preserves_snapshot_and_can_recover(self) -> None:
        self.publish_copy("extraction-observatory/one")
        state = WorkbenchState(self.workspace)
        original_projection = state.projection
        original_details = state.projection.details
        original_artifacts = state.projection.artifact_contents

        with patch(
            "tiny_corpus_workbench.application.workbench.MAX_STRUCTURED_RESPONSE",
            1,
        ):
            failed = state.refresh()
        self.assertFalse(failed.succeeded)
        self.assertIn("structured response limit", failed.message)
        self.assertIs(state.projection, original_projection)
        self.assertIs(state.projection.details, original_details)
        self.assertIs(state.projection.artifact_contents, original_artifacts)

        recovered = state.refresh()
        self.assertTrue(recovered.succeeded)
        self.assertEqual(state.refresh_status, "READY")
        self.assertIsNone(state.refresh_message)

    def test_workspace_replaced_by_file_preserves_last_good_snapshot(self) -> None:
        self.publish_copy("extraction-observatory/one")
        state = WorkbenchState(self.workspace)
        original_projection = state.projection
        backup = Path(f"{self.workspace}-backup")
        self.workspace.rename(backup)
        try:
            self.workspace.write_text("not a workspace", "utf-8")
            result = state.refresh()
            self.assertFalse(result.succeeded)
            self.assertEqual(state.refresh_status, "FAILED")
            self.assertIs(state.projection, original_projection)
            self.assertTrue(state.projection.details)
            self.assertTrue(state.projection.artifact_contents)
        finally:
            self.workspace.unlink()
            backup.rename(self.workspace)

    def test_unreadable_subtree_preserves_last_good_snapshot(self) -> None:
        target = self.publish_copy("extraction-observatory/one")
        state = WorkbenchState(self.workspace)
        original_projection = state.projection
        blocked = target.parent
        real_scandir = os.scandir

        def fail_one_subtree(path):
            if Path(path) == blocked:
                raise PermissionError("blocked for test")
            return real_scandir(path)

        with patch(
            "tiny_corpus_workbench.application.workbench.os.scandir",
            side_effect=fail_one_subtree,
        ):
            result = state.refresh()
        self.assertFalse(result.succeeded)
        self.assertIn("directory is unreadable", result.message)
        self.assertIs(state.projection, original_projection)

    def test_initial_invalid_record_keeps_usable_empty_failed_snapshot(self) -> None:
        root = self.workspace / "extraction-observatory" / "bad"
        root.mkdir(parents=True)
        (root / "manifest.json").write_text(json.dumps({"bad": True}), "utf-8")
        state = WorkbenchState(self.workspace)
        self.assertEqual(state.refresh_status, "FAILED")
        self.assertEqual(state.projection.projection["records"], [])
        self.assertIn("extraction-observatory/bad", state.refresh_message)

    def test_concurrent_refreshes_are_serialized(self) -> None:
        state = WorkbenchState(self.workspace)
        original = state._candidate_projection
        entered = threading.Event()
        release = threading.Event()
        counter_lock = threading.Lock()
        active = 0
        maximum = 0

        def blocked_candidate(roots):
            nonlocal active, maximum
            with counter_lock:
                active += 1
                maximum = max(maximum, active)
            entered.set()
            release.wait(2)
            try:
                return original(roots)
            finally:
                with counter_lock:
                    active -= 1

        with patch.object(
            state, "_candidate_projection", side_effect=blocked_candidate
        ):
            first = threading.Thread(target=state.refresh)
            second = threading.Thread(target=state.refresh)
            first.start()
            self.assertTrue(entered.wait(1))
            second.start()
            time.sleep(0.05)
            self.assertEqual(maximum, 1)
            release.set()
            first.join(2)
            second.join(2)
        self.assertFalse(first.is_alive())
        self.assertFalse(second.is_alive())
        self.assertEqual(maximum, 1)


if __name__ == "__main__":
    unittest.main()
