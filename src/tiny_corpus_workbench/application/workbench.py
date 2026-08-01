"""Workspace discovery and transactional state for the local Workbench."""

from __future__ import annotations

import copy
import os
import stat
import threading
from dataclasses import dataclass
from pathlib import Path
from types import MappingProxyType
from typing import Iterable, Mapping, Sequence

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
    AdmittedRecords,
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
    """Create and validate one workspace that can accept future records."""

    workspace = Path(value)
    try:
        workspace.mkdir(parents=True, exist_ok=True)
    except FileExistsError:
        pass
    except OSError as error:
        raise InputError("workspace is unavailable") from error
    try:
        metadata = workspace.lstat()
    except OSError as error:
        raise InputError("workspace is unavailable") from error
    if stat.S_ISLNK(metadata.st_mode):
        raise InputError("workspace must be a real directory")
    if not stat.S_ISDIR(metadata.st_mode):
        raise InputError("workspace must be a directory")
    if not os.access(workspace, os.R_OK | os.W_OK | os.X_OK):
        raise InputError("workspace must be readable, writable, and searchable")
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
            metadata = family_root.lstat()
        except FileNotFoundError:
            continue
        except OSError as error:
            raise InputError(f"{family}: family directory is unreadable") from error
        if stat.S_ISLNK(metadata.st_mode) or not stat.S_ISDIR(metadata.st_mode):
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


class WorkspaceStaleError(WorkbenchError):
    """An accepted actionable root no longer names the admitted record."""


@dataclass(frozen=True)
class ActionableRootToken:
    """Private identity for one verified top-level actionable record root."""

    relative_path: str
    canonical_root: Path
    device: int
    inode: int


@dataclass(frozen=True)
class AcceptedWorkspaceSnapshot:
    """One atomically accepted projection and its private root index."""

    projection: WorkbenchProjection
    actionable_roots: Mapping[str, ActionableRootToken]


def _real_contained_directory(
    workspace: Path, relative: str
) -> tuple[Path, os.stat_result]:
    """Resolve one contained directory path without accepting symlink components."""

    try:
        relative_path = Path(relative)
        if (
            not relative
            or "\\" in relative
            or "\x00" in relative
            or relative_path.is_absolute()
            or relative_path.as_posix() != relative
            or any(part in {"", ".", ".."} for part in relative_path.parts)
        ):
            raise WorkspaceStaleError("workspace record root is stale")
        workspace_metadata = workspace.lstat()
        if stat.S_ISLNK(workspace_metadata.st_mode) or not stat.S_ISDIR(
            workspace_metadata.st_mode
        ):
            raise WorkspaceStaleError("workspace record root is stale")
        current = workspace
        metadata = workspace_metadata
        for component in relative_path.parts:
            current = current / component
            metadata = current.lstat()
            if stat.S_ISLNK(metadata.st_mode) or not stat.S_ISDIR(metadata.st_mode):
                raise WorkspaceStaleError("workspace record root is stale")
        current.relative_to(workspace)
        return current, metadata
    except WorkspaceStaleError:
        raise
    except (OSError, ValueError) as error:
        raise WorkspaceStaleError("workspace record root is stale") from error


def _actionable_roots(
    workspace: Path, records: AdmittedRecords
) -> Mapping[str, ActionableRootToken]:
    result: dict[str, ActionableRootToken] = {}
    for record_key in sorted(records.explicit_keys):
        record = records.records[record_key]
        if record.kind not in {"OBSERVATION", "DIAGNOSIS", "REFINEMENT"}:
            continue
        try:
            relative = record.backing.root.relative_to(workspace).as_posix()
        except ValueError as error:
            raise IntegrityError(
                "workspace record root escapes the workspace"
            ) from error
        try:
            canonical, metadata = _real_contained_directory(workspace, relative)
        except WorkspaceStaleError as error:
            raise IntegrityError(
                "workspace record root is not a real directory"
            ) from error
        if (
            canonical != record.backing.root
            or metadata.st_dev != record.backing.device
            or metadata.st_ino != record.backing.inode
        ):
            raise IntegrityError("workspace record root changed during admission")
        result[record_key] = ActionableRootToken(
            relative_path=relative,
            canonical_root=canonical,
            device=metadata.st_dev,
            inode=metadata.st_ino,
        )
    return MappingProxyType(result)


def _revalidate_root_token(
    workspace: Path, token: ActionableRootToken
) -> Path:
    canonical, metadata = _real_contained_directory(
        workspace, token.relative_path
    )
    if (
        canonical != token.canonical_root
        or metadata.st_dev != token.device
        or metadata.st_ino != token.inode
    ):
        raise WorkspaceStaleError("workspace record root is stale")
    return canonical


class WorkbenchState:
    """Own one accepted workspace snapshot and its last refresh result."""

    def __init__(self, workspace: str | os.PathLike[str]) -> None:
        self.workspace = validate_workspace(workspace)
        try:
            self.workspace = self.workspace.resolve(strict=True)
        except OSError as error:
            raise InputError("workspace is unavailable") from error
        self._lock = threading.RLock()
        self._accepted = AcceptedWorkspaceSnapshot(
            empty_projection(), MappingProxyType({})
        )
        self.refresh_status = "READY"
        self.refresh_message: str | None = None
        self.refresh()

    @property
    def projection(self) -> WorkbenchProjection:
        with self._lock:
            return self._accepted.projection

    def capture_snapshot(self) -> AcceptedWorkspaceSnapshot:
        """Return one accepted projection/root pair for an application action."""

        with self._lock:
            return self._accepted

    def _candidate_projection(self, roots: list[Path]) -> AcceptedWorkspaceSnapshot:
        if not roots:
            return AcceptedWorkspaceSnapshot(
                empty_projection(), MappingProxyType({})
            )
        for root in roots:
            try:
                prepare_workbench([root])
            except (WorkbenchError, OSError, ValueError) as error:
                relative = root.relative_to(self.workspace).as_posix()
                raise InputError(f"{relative}: {sanitize_message(error)}") from error
        try:
            admitted = admit_records(roots)
            projection = build_projection(admitted)
            actionable_roots = _actionable_roots(self.workspace, admitted)
            return AcceptedWorkspaceSnapshot(projection, actionable_roots)
        except Exception as error:
            raise IntegrityError(
                "workspace records conflict or cannot form one projection"
            ) from error

    def refresh(self) -> RefreshResult:
        """Build a full candidate, then atomically replace the accepted snapshot."""

        with self._lock:
            try:
                validate_workspace(self.workspace)
                roots = discover_workspace(self.workspace)
                candidate = self._candidate_projection(roots)
                payload = copy.deepcopy(candidate.projection.projection)
                payload["refresh"] = {"status": "READY", "message": None}
                if len(canonical_json(payload)) > MAX_STRUCTURED_RESPONSE:
                    raise IntegrityError(
                        "workbench projection exceeds the structured response limit"
                    )
            except Exception as error:
                self.refresh_status = "FAILED"
                self.refresh_message = sanitize_message(error)
                return RefreshResult(False, self.refresh_message)
            self._accepted = candidate
            self.refresh_status = "READY"
            self.refresh_message = None
            return RefreshResult(True, None)

    def projection_object(self) -> dict[str, object]:
        with self._lock:
            value = copy.deepcopy(self._accepted.projection.projection)
            value["refresh"] = {
                "status": self.refresh_status,
                "message": self.refresh_message,
            }
            return value

    def projection_bytes(self) -> bytes:
        return canonical_json(self.projection_object())

    @staticmethod
    def diagnosis_subject(
        snapshot: AcceptedWorkspaceSnapshot, record_key: str
    ) -> ActionableRootToken | None:
        """Return an eligible observation or approved-refinement subject token."""

        token = snapshot.actionable_roots.get(record_key)
        detail = snapshot.projection.details.get(record_key)
        if token is None or detail is None:
            return None
        if detail["kind"] == "OBSERVATION":
            roles = {artifact["role"] for artifact in detail["artifacts"]}
            return token if "docling-document-json" in roles else None
        if detail["kind"] == "REFINEMENT":
            node = next(
                (
                    item
                    for item in snapshot.projection.projection["records"]
                    if item["record_key"] == record_key
                ),
                None,
            )
            return token if node is not None and node["status"] == "APPROVED" else None
        return None

    @classmethod
    def diagnosis_base(
        cls, snapshot: AcceptedWorkspaceSnapshot, diagnosis_record_key: str
    ) -> ActionableRootToken | None:
        """Resolve a diagnosis base only through its admitted matching subject."""

        if diagnosis_record_key not in snapshot.actionable_roots:
            return None
        detail = snapshot.projection.details.get(diagnosis_record_key)
        if detail is None or detail["kind"] != "DIAGNOSIS":
            return None
        matches = [
            relationship
            for relationship in detail["relationships"]
            if relationship["relation"] == "DIAGNOSIS_SUBJECT"
            and relationship["state"] == "MATCH"
        ]
        if len(matches) != 1:
            return None
        target_key = matches[0].get("target_record_key")
        if not isinstance(target_key, str):
            return None
        return cls.diagnosis_subject(snapshot, target_key)

    def resolve_actionable_roots(
        self,
        snapshot: AcceptedWorkspaceSnapshot,
        record_keys: Sequence[str],
    ) -> dict[str, Path]:
        """Revalidate required accepted roots and return current canonical paths."""

        resolved: dict[str, Path] = {}
        for record_key in dict.fromkeys(record_keys):
            token = snapshot.actionable_roots.get(record_key)
            if token is None:
                raise WorkspaceStaleError("workspace record root is stale")
            canonical = _revalidate_root_token(self.workspace, token)
            try:
                admitted = admit_records([canonical])
                if set(admitted.records) != {record_key}:
                    raise WorkspaceStaleError("workspace record root is stale")
                fresh = admitted.records[record_key]
                canonical = _revalidate_root_token(self.workspace, token)
                if (
                    fresh.backing.root != token.canonical_root
                    or fresh.backing.device != token.device
                    or fresh.backing.inode != token.inode
                ):
                    raise WorkspaceStaleError("workspace record root is stale")
            except WorkspaceStaleError:
                raise
            except (WorkbenchError, OSError, ValueError) as error:
                raise WorkspaceStaleError("workspace record root is stale") from error
            resolved[record_key] = canonical
        return resolved


__all__ = [
    "AcceptedWorkspaceSnapshot",
    "ActionableRootToken",
    "FAMILIES",
    "RefreshResult",
    "WorkbenchState",
    "WorkspaceStaleError",
    "discover_workspace",
    "prepare_workbench",
    "validate_workspace",
]
