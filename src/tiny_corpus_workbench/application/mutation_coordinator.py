"""Non-blocking ownership for Workbench record-producing operations."""

from __future__ import annotations

import threading
from dataclasses import dataclass
from typing import Callable


class MutationBusyError(Exception):
    """Another Workbench mutation already owns publication."""


@dataclass
class MutationLease:
    """One exactly-once release handle returned after successful acquisition."""

    _coordinator: "MutationCoordinator"
    owner: str
    _released: bool = False

    def release(self, finalize: Callable[[], None] | None = None) -> None:
        if self._released:
            return
        try:
            self._coordinator._release(self.owner, finalize)
        finally:
            self._released = True

    def __enter__(self) -> "MutationLease":
        return self

    def __exit__(self, *_: object) -> None:
        self.release()


class MutationCoordinator:
    """Give either observation or lifecycle one process-local mutation lease."""

    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._owner: str | None = None

    @property
    def owner(self) -> str | None:
        with self._lock:
            return self._owner

    def acquire(self, owner: str) -> MutationLease:
        if owner not in {"OBSERVATION", "LIFECYCLE"}:
            raise ValueError("mutation owner is invalid")
        with self._lock:
            if self._owner is not None:
                raise MutationBusyError("one Workbench mutation is already active")
            self._owner = owner
        return MutationLease(self, owner)

    def _release(
        self, owner: str, finalize: Callable[[], None] | None = None
    ) -> None:
        with self._lock:
            if self._owner != owner:
                raise RuntimeError("mutation lease ownership differs")
            self._owner = None
            if finalize is not None:
                finalize()


__all__ = ["MutationBusyError", "MutationCoordinator", "MutationLease"]
