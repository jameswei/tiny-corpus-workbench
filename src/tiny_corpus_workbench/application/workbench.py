"""Workspace discovery and transactional state for the local Workbench."""

from __future__ import annotations

import copy
import os
import stat
from dataclasses import dataclass
from pathlib import Path
from typing import Iterable

from tiny_corpus_workbench.canonical_json import canonical_json
from tiny_corpus_workbench.domain import (
    InputError,
    IntegrityError,
    WorkbenchError,
    sanitize_message,
)
from tiny_corpus_workbench.workbench_projection import (
    WorkbenchProjection,
    build_projection,
    empty_projection,
)
from tiny_corpus_workbench.workbench_records import (
    MAX_STRUCTURED_RESPONSE,
    admit_records,
)


FAMILIES = (
    ("extraction-observatory", "manifest.json"),
    ("evidence-based-diagnosis", "diagnosis-manifest.json"),
    ("controlled-revisions", "refinement-manifest.json"),
    ("corpus-inspection", "corpus-manifest.json"),
)


def prepare_workbench(
    roots: Iterable[str | os.PathLike[str]],
) -> WorkbenchProjection:
    """Admit explicit records and compose one frozen internal read model."""

    return build_projection(admit_records(roots))


def validate_workspace(value: str | os.PathLike[str]) -> Path:
    """Validate an existing workspace without creating it."""

    workspace = Path(value)
    try:
        metadata = workspace.stat()
    except FileNotFoundError:
        return workspace
    except OSError as error:
        raise InputError("workspace is unavailable") from error
    if not stat.S_ISDIR(metadata.st_mode):
        raise InputError("workspace must be a directory")
    if not os.access(workspace, os.R_OK | os.X_OK):
        raise InputError("workspace must be readable")
    return workspace


def discover_workspace(workspace: Path) -> list[Path]:
    """Return fixed-family record roots in workspace-relative path order."""

    workspace = validate_workspace(workspace)
    try:
        before = workspace.stat()
    except FileNotFoundError:
        return []
    except OSError as error:
        raise InputError("workspace is unavailable") from error
    if not stat.S_ISDIR(before.st_mode):
        raise InputError("workspace must be a directory")
    if not os.access(workspace, os.R_OK | os.X_OK):
        raise InputError("workspace must be readable")
    candidates: list[tuple[str, Path]] = []
    for family, manifest_name in FAMILIES:
        family_root = workspace / family
        try:
            metadata = family_root.stat()
        except FileNotFoundError:
            continue
        except OSError as error:
            raise InputError(f"{family}: family directory is unreadable") from error
        if not stat.S_ISDIR(metadata.st_mode):
            continue
        if not os.access(family_root, os.R_OK | os.X_OK):
            raise InputError(f"{family}: family directory is unreadable")

        pending = [family_root]
        while pending:
            directory = pending.pop()
            relative_directory = directory.relative_to(workspace)
            if not os.access(directory, os.R_OK | os.X_OK):
                raise InputError(
                    f"{relative_directory.as_posix()}: directory is unreadable"
                )
            try:
                with os.scandir(directory) as iterator:
                    entries = sorted(iterator, key=lambda entry: entry.name)
            except OSError as error:
                raise InputError(
                    f"{relative_directory.as_posix()}: directory is unreadable"
                ) from error
            child_directories: list[Path] = []
            for entry in entries:
                try:
                    if entry.is_dir(follow_symlinks=False):
                        if entry.name.startswith(".staging-"):
                            continue
                        child_directories.append(Path(entry.path))
                    elif entry.name == manifest_name and entry.is_file():
                        manifest = Path(entry.path)
                        relative = manifest.relative_to(workspace)
                        candidates.append((relative.as_posix(), manifest.parent))
                except OSError as error:
                    relative = Path(entry.path).relative_to(workspace).as_posix()
                    raise InputError(f"{relative}: path is unreadable") from error
            pending.extend(reversed(child_directories))
    try:
        validate_workspace(workspace)
        after = workspace.stat()
    except OSError as error:
        raise InputError("workspace changed during refresh") from error
    if (before.st_dev, before.st_ino) != (after.st_dev, after.st_ino):
        raise InputError("workspace changed during refresh")
    return [root for _, root in sorted(candidates)]


@dataclass(frozen=True)
class RefreshResult:
    succeeded: bool
    message: str | None


class WorkbenchState:
    """Own one accepted workspace snapshot and its last refresh result."""

    def __init__(self, workspace: str | os.PathLike[str]) -> None:
        self.workspace = validate_workspace(workspace)
        self.projection = empty_projection()
        self.refresh_status = "READY"
        self.refresh_message: str | None = None
        self.refresh()

    def _candidate_projection(self, roots: list[Path]) -> WorkbenchProjection:
        if not roots:
            return empty_projection()
        for root in roots:
            try:
                prepare_workbench([root])
            except (WorkbenchError, OSError, ValueError) as error:
                relative = root.relative_to(self.workspace).as_posix()
                raise InputError(f"{relative}: {sanitize_message(error)}") from error
        try:
            return prepare_workbench(roots)
        except Exception as error:
            raise IntegrityError(
                "workspace records conflict or cannot form one projection"
            ) from error

    def refresh(self) -> RefreshResult:
        """Build a full candidate, then atomically replace the accepted snapshot."""

        try:
            validate_workspace(self.workspace)
            roots = discover_workspace(self.workspace)
            candidate = self._candidate_projection(roots)
            payload = copy.deepcopy(candidate.projection)
            payload["refresh"] = {"status": "READY", "message": None}
            if len(canonical_json(payload)) > MAX_STRUCTURED_RESPONSE:
                raise IntegrityError(
                    "workbench projection exceeds the structured response limit"
                )
        except Exception as error:
            self.refresh_status = "FAILED"
            self.refresh_message = sanitize_message(error)
            return RefreshResult(False, self.refresh_message)
        self.projection = candidate
        self.refresh_status = "READY"
        self.refresh_message = None
        return RefreshResult(True, None)

    def projection_object(self) -> dict[str, object]:
        value = copy.deepcopy(self.projection.projection)
        value["refresh"] = {
            "status": self.refresh_status,
            "message": self.refresh_message,
        }
        return value

    def projection_bytes(self) -> bytes:
        return canonical_json(self.projection_object())


__all__ = [
    "FAMILIES",
    "RefreshResult",
    "WorkbenchState",
    "discover_workspace",
    "prepare_workbench",
    "validate_workspace",
]
