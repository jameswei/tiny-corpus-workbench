"""In-process background observation jobs for the local Workbench."""

from __future__ import annotations

import json
import os
import queue
import threading
import uuid
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Callable

from tiny_corpus_workbench.application.observation import observe
from tiny_corpus_workbench.application.mutation_coordinator import (
    MutationBusyError,
    MutationCoordinator,
    MutationLease,
)
from tiny_corpus_workbench.application.workbench import WorkbenchState
from tiny_corpus_workbench.domain import (
    InputError,
    IntegrityError,
    RuntimeContractError,
    sanitize_message,
)


@dataclass(frozen=True)
class JobInput:
    kind: str
    name: str
    media_type: str
    size: int
    sha256: str


@dataclass(frozen=True)
class JobObservation:
    status: str
    observation_id: str
    record_key: str | None


@dataclass(frozen=True)
class JobRefresh:
    status: str
    message: str | None


@dataclass(frozen=True)
class JobError:
    code: str
    message: str


@dataclass(frozen=True)
class ObservationJob:
    job_id: str
    state: str
    stage: str | None
    input: JobInput
    observation: JobObservation | None
    refresh: JobRefresh | None
    error: JobError | None

    def to_dict(self) -> dict[str, object]:
        return asdict(self)


class ObservationBusyError(Exception):
    """One observation is already queued or running."""


ObserveCallable = Callable[
    [str, Path, Path, Callable[[str], None] | None], tuple[object, Path]
]


class ObservationJobManager:
    """Own one latest job and execute accepted work on one worker."""

    def __init__(
        self,
        state: WorkbenchState,
        model_root: str | os.PathLike[str],
        *,
        observe_service: ObserveCallable = observe,
        coordinator: MutationCoordinator | None = None,
    ) -> None:
        self.state = state
        self.model_root = Path(model_root)
        self._observe = observe_service
        self.coordinator = coordinator or MutationCoordinator()
        self._lock = threading.Lock()
        self._queue: queue.Queue[
            tuple[ObservationJob, Path, MutationLease] | None
        ] = queue.Queue(
            maxsize=1
        )
        self._latest: ObservationJob | None = None
        self._accepting = True
        self._worker = threading.Thread(
            target=self._run, name="workbench-observation", daemon=False
        )
        self._worker.start()

    def snapshot(self) -> ObservationJob | None:
        with self._lock:
            return self._latest

    def is_busy(self) -> bool:
        with self._lock:
            return (
                not self._accepting
                or (
                    self._latest is not None
                    and self._latest.state in {"QUEUED", "RUNNING"}
                )
            )

    def accept(self, source: Path, input_value: JobInput) -> ObservationJob:
        with self._lock:
            if not self._accepting:
                raise ObservationBusyError("observation manager is shutting down")
            if self._latest is not None and self._latest.state in {
                "QUEUED",
                "RUNNING",
            }:
                raise ObservationBusyError("one observation is already active")
            try:
                lease = self.coordinator.acquire("OBSERVATION")
            except MutationBusyError as error:
                raise ObservationBusyError(
                    "one lifecycle mutation is already active"
                ) from error
            try:
                job = ObservationJob(
                    job_id=uuid.uuid4().hex,
                    state="QUEUED",
                    stage=None,
                    input=input_value,
                    observation=None,
                    refresh=None,
                    error=None,
                )
                self._queue.put_nowait((job, source, lease))
                self._latest = job
                return job
            except Exception:
                lease.release()
                raise

    def shutdown(self) -> None:
        with self._lock:
            if not self._accepting:
                worker = self._worker
            else:
                self._accepting = False
                worker = self._worker
        if worker.is_alive():
            self._queue.put(None)
            worker.join()

    def _replace(self, job_id: str, **changes: object) -> ObservationJob | None:
        with self._lock:
            current = self._latest
            if current is None or current.job_id != job_id:
                return None
            values = current.to_dict()
            values.update(changes)
            for field, kind in (
                ("input", JobInput),
                ("observation", JobObservation),
                ("refresh", JobRefresh),
                ("error", JobError),
            ):
                value = values[field]
                if isinstance(value, dict):
                    values[field] = kind(**value)
            replacement = ObservationJob(**values)
            self._latest = replacement
            return replacement

    def _run(self) -> None:
        while True:
            work = self._queue.get()
            try:
                if work is None:
                    return
                job, source, lease = work
                try:
                    self._execute(job, source, lease)
                finally:
                    lease.release()
            finally:
                self._queue.task_done()

    def _execute(
        self, job: ObservationJob, source: Path, lease: MutationLease
    ) -> None:
        published: Path | None = None
        try:
            def progress(stage: str) -> None:
                self._replace(job.job_id, state="RUNNING", stage=stage)

            _, published = self._observe(
                str(source),
                self.state.workspace / "extraction-observatory",
                self.model_root,
                progress,
            )
            manifest = json.loads((published / "manifest.json").read_text("utf-8"))
            observation = JobObservation(
                status=manifest["status"],
                observation_id=manifest["observation_id"],
                record_key=None,
            )
            run_id = manifest["run_id"]
            self._replace(
                job.job_id,
                state="RUNNING",
                stage="REFRESHING_WORKSPACE",
                observation=observation,
            )
            refreshed = self.state.refresh()
            if not refreshed.succeeded:
                self._finish(
                    lease,
                    job.job_id,
                    state="COMPLETED",
                    stage=None,
                    observation=observation,
                    refresh=JobRefresh("FAILED", refreshed.message),
                )
                return
            record_key = self._record_key(observation.observation_id, run_id)
            if record_key is None:
                raise IntegrityError(
                    "published observation is absent from the refreshed workspace"
                )
            self._finish(
                lease,
                job.job_id,
                state="COMPLETED",
                stage=None,
                observation=JobObservation(
                    observation.status,
                    observation.observation_id,
                    record_key,
                ),
                refresh=JobRefresh("READY", None),
            )
        except Exception as error:
            if published is not None:
                self._finish(
                    lease,
                    job.job_id,
                    state="COMPLETED",
                    stage=None,
                    refresh=JobRefresh("FAILED", sanitize_message(error)),
                )
                return
            self._finish(
                lease,
                job.job_id,
                state="FAILED",
                stage=None,
                observation=None,
                refresh=None,
                error=self._job_error(error),
            )

    def _finish(
        self,
        lease: MutationLease,
        job_id: str,
        **changes: object,
    ) -> None:
        """Release mutation and publish terminal state as one synchronized step."""

        lease.release(lambda: self._replace(job_id, **changes))

    def _record_key(self, observation_id: str, run_id: str) -> str | None:
        projection = self.state.projection
        for record in projection.projection["records"]:
            if (
                record["kind"] == "OBSERVATION"
                and record["run_id"] == run_id
                and record["primary_identity"]
                == {"name": "observation_id", "value": observation_id}
            ):
                return record["record_key"]
        return None

    @staticmethod
    def _job_error(error: Exception) -> JobError:
        if isinstance(error, InputError):
            code = "OBSERVATION_INPUT_FAILED"
        elif isinstance(error, IntegrityError):
            code = "OBSERVATION_INTEGRITY_FAILED"
        elif isinstance(error, RuntimeContractError):
            code = "OBSERVATION_RUNTIME_FAILED"
        else:
            code = "OBSERVATION_INTERNAL_FAILED"
        return JobError(code, sanitize_message(error))


__all__ = [
    "JobError",
    "JobInput",
    "JobObservation",
    "JobRefresh",
    "ObservationBusyError",
    "ObservationJob",
    "ObservationJobManager",
]
