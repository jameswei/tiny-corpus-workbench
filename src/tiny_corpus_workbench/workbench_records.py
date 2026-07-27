"""Intrinsic record admission for the read-only v0.5 workbench.

This module deliberately has no server or discovery behavior.  Callers give it
record roots; corpus children are followed only through verified descriptors.
"""

from __future__ import annotations

import hashlib
import json
import os
import stat
import tempfile
from contextlib import contextmanager
from dataclasses import dataclass, field
from pathlib import Path, PurePosixPath
from typing import Any, Iterable, Iterator

from tiny_corpus_workbench.artifacts import canonical_json as artifact_json
from tiny_corpus_workbench.application.records import require_record_header
from tiny_corpus_workbench.canonical_json import (
    artifact_key,
    logical_copy_key,
    record_key,
)
from tiny_corpus_workbench.corpus_verification import verify_corpus
from tiny_corpus_workbench.domain import InputError, IntegrityError
from tiny_corpus_workbench.supported_provenance import active_build_provenance
from tiny_corpus_workbench.v03 import verify_diagnosis, verify_refinement
from tiny_corpus_workbench.verification import verify_observation


MAX_STRUCTURED_RESPONSE = 4 * 1024 * 1024
MAX_ARTIFACT_CONTENT = 16 * 1024 * 1024

ROOTS = {
    "manifest.json": (
        "OBSERVATION",
        "tcw.preparation-manifest/v0.5",
        "preparation-manifest",
    ),
    "diagnosis-manifest.json": (
        "DIAGNOSIS",
        "tcw.diagnosis-manifest/v0.5",
        "diagnosis-manifest",
    ),
    "refinement-manifest.json": (
        "REFINEMENT",
        "tcw.refinement-manifest/v0.5",
        "refinement-manifest",
    ),
    "corpus-manifest.json": (
        "CORPUS",
        "tcw.corpus-manifest/v0.5",
        "corpus-manifest",
    ),
}

ALLOWED_ROLES = {
    "comparison-summary",
    "docling-document-json",
    "docling-markdown",
    "markitdown-markdown",
    "diagnostic-findings",
    "diagnostic-report",
    "refinement-decision",
    "refinement-report",
    "transformation",
    "transformation-history",
    "prepared-document-json",
    "prepared-document-markdown",
    "normalized-corpus-specification",
    "corpus-summary",
}
ALLOWED_MEDIA = {"application/json", "text/markdown"}


@dataclass(frozen=True)
class Backing:
    root: Path
    containing_corpus_key: str | None = None
    member_id: str | None = None
    descriptor_path: str | None = None
    top_level: bool = False

    def order_key(self) -> tuple[str, str, str]:
        return (
            self.containing_corpus_key or "",
            self.member_id or "",
            self.descriptor_path or "",
        )


@dataclass
class AdmittedRecord:
    kind: str
    schema_version: str
    identity: dict[str, Any]
    run_id: str
    status: str
    manifest_name: str
    manifest: dict[str, Any]
    manifest_bytes: bytes
    manifest_identity: tuple[int, ...]
    manifest_sha256: str
    logical_copy_key: str
    record_key: str | None
    listed: list[dict[str, Any]]
    artifact_bytes: dict[tuple[str, str, str], bytes]
    artifact_identities: dict[tuple[str, str, str], tuple[int, ...]]
    backing: Backing
    copies: list[Backing] = field(default_factory=list)
    contained_by: set[str] = field(default_factory=set)
    top_level: bool = False
    authorized_artifacts: dict[str, dict[str, Any]] = field(default_factory=dict)

    @property
    def content_sha256(self) -> str | None:
        if self.kind == "OBSERVATION":
            for extractor in self.manifest["extractors"]:
                for item in extractor["artifacts"]:
                    if item["role"] == "docling-document-json":
                        return item["sha256"]
            return None
        if self.kind == "DIAGNOSIS":
            return next(
                item["sha256"]
                for item in self.manifest["artifacts"]
                if item["role"] == "diagnostic-findings"
            )
        if self.kind == "REFINEMENT":
            return next(
                (
                    item["sha256"]
                    for item in self.manifest["artifacts"]
                    if item["role"] == "prepared-document-json"
                ),
                None,
            )
        return None

    def descriptors(self) -> tuple[dict[str, Any], list[dict[str, Any]]]:
        if self.record_key is None:
            raise IntegrityError(
                "record identity is unavailable before copy equivalence"
            )
        root = _api_descriptor(
            self,
            {
                "path": self.manifest_name,
                "role": ROOTS[self.manifest_name][2],
                "media_type": "application/json",
                "size": len(self.manifest_bytes),
                "sha256": self.manifest_sha256,
            },
            "ROOT_MANIFEST",
        )
        listed = sorted(
            (_api_descriptor(self, item, "MANIFEST_LISTED") for item in self.listed),
            key=lambda item: item["artifact_key"],
        )
        keys = [root["artifact_key"], *(item["artifact_key"] for item in listed)]
        if len(keys) != len(set(keys)):
            raise IntegrityError("authorized artifact keys are not unique")
        union = [root, *listed]
        if self.authorized_artifacts:
            if self.authorized_artifacts != {
                item["artifact_key"]: item for item in union
            }:
                raise IntegrityError("frozen artifact authorization differs")
        else:
            self.authorized_artifacts = {
                item["artifact_key"]: item for item in union
            }
        return root, listed

    def read_artifact(self, role: str) -> bytes:
        matches = [item for item in self.listed if item["role"] == role]
        if len(matches) != 1:
            raise IntegrityError("authorized artifact role is not singular")
        item = matches[0]
        try:
            return self.artifact_bytes[(item["role"], item["path"], item["sha256"])]
        except KeyError as error:
            raise IntegrityError("frozen authorized artifact is unavailable") from error


@dataclass
class AdmittedRecords:
    records: dict[str, AdmittedRecord]
    explicit_keys: set[str]
    containment: list[tuple[str, str, str, str]]

    @property
    def contained_only_keys(self) -> set[str]:
        return set(self.records) - self.explicit_keys

    def recheck_artifact(self, artifact: dict[str, Any] | str) -> bytes:
        """Capture one authorized canonical artifact as immutable verified bytes."""

        key = artifact if isinstance(artifact, str) else artifact.get("artifact_key")
        if not isinstance(key, str):
            raise IntegrityError("artifact authorization key is invalid")
        matches = [
            (record, descriptor)
            for record in self.records.values()
            for artifact_key_value, descriptor in record.authorized_artifacts.items()
            if artifact_key_value == key
        ]
        if len(matches) != 1:
            raise IntegrityError("artifact is not authorized")
        record, authorized = matches[0]
        if isinstance(artifact, dict) and artifact != authorized:
            raise IntegrityError("artifact descriptor differs from authorization")
        if authorized["origin"] == "ROOT_MANIFEST":
            expected_identity = record.manifest_identity
        else:
            expected_identity = record.artifact_identities[
                (
                    authorized["role"],
                    authorized["relative_path"],
                    authorized["sha256"],
                )
            ]
        captured = _capture_authorized_artifact(
            record.backing.root,
            authorized["relative_path"],
            expected_identity,
        )
        if (
            len(captured) != authorized["size"]
            or _sha(captured) != authorized["sha256"]
        ):
            raise IntegrityError("canonical artifact backing changed")
        return captured


def _sha(value: bytes) -> str:
    return hashlib.sha256(value).hexdigest()


def _safe_relative(value: object) -> PurePosixPath:
    if not isinstance(value, str) or not value or "\\" in value or "\x00" in value:
        raise IntegrityError("artifact reference is unsafe")
    result = PurePosixPath(value)
    if result.is_absolute() or any(part in {"", ".", ".."} for part in result.parts):
        raise IntegrityError("artifact reference is unsafe")
    return result


def _safe_path(root: Path, relative: object) -> Path:
    rel = _safe_relative(relative)
    current = root
    for part in rel.parts:
        current /= part
        mode = current.lstat().st_mode
        if stat.S_ISLNK(mode):
            raise IntegrityError("accessed record node is a symbolic link")
    current.resolve(strict=True).relative_to(root.resolve(strict=True))
    return current


def _stat_identity(metadata: os.stat_result) -> tuple[int, ...]:
    return (
        metadata.st_dev,
        metadata.st_ino,
        metadata.st_mode,
        metadata.st_nlink,
        metadata.st_size,
        metadata.st_mtime_ns,
        metadata.st_ctime_ns,
    )


def _directory_identity(
    metadata: os.stat_result, *, root: bool
) -> tuple[int, ...]:
    return (
        metadata.st_dev,
        metadata.st_ino,
        stat.S_IFMT(metadata.st_mode),
    )


@dataclass(frozen=True)
class _CapturedFile:
    identity: tuple[int, ...]
    content: bytes


@dataclass(frozen=True)
class _InventoryEntry:
    relative_path: str
    kind: str
    mode: int
    identity: tuple[int, ...]
    content: bytes | None


@dataclass(frozen=True)
class _AdmissionCapture:
    canonical_root: str
    root_name: str
    directory_identities: tuple[tuple[int, ...], ...]
    inventory: tuple[_InventoryEntry, ...]
    manifest_name: str
    manifest: dict[str, Any]
    manifest_file: _CapturedFile
    listed: tuple[tuple[tuple[str, str, str], _CapturedFile], ...]


def _open_no_follow(
    path: str, flags: int, *, dir_fd: int | None = None
) -> int:
    options = flags | os.O_CLOEXEC | os.O_NOFOLLOW
    if dir_fd is None:
        return os.open(path, options)
    return os.open(path, options, dir_fd=dir_fd)


def _close_descriptors(descriptors: list[int]) -> None:
    for descriptor in reversed(descriptors):
        try:
            os.close(descriptor)
        except OSError:
            pass


def _open_root_components(root: Path) -> list[int]:
    descriptors: list[int] = []
    try:
        descriptors.append(
            _open_no_follow("/", os.O_RDONLY | os.O_DIRECTORY)
        )
        components = root.parts[1:]
        for index, component in enumerate(components):
            metadata = os.stat(
                component,
                dir_fd=descriptors[-1],
                follow_symlinks=False,
            )
            if stat.S_ISLNK(metadata.st_mode):
                raise IntegrityError(
                    "record root or ancestor is a symbolic link"
                )
            if not stat.S_ISDIR(metadata.st_mode):
                if index == len(components) - 1:
                    raise InputError(
                        "RECORD must be one local non-symlink directory"
                    )
                raise IntegrityError("record root or ancestor is unsafe")
            descriptors.append(
                _open_no_follow(
                    component,
                    os.O_RDONLY | os.O_DIRECTORY,
                    dir_fd=descriptors[-1],
                )
            )
        return descriptors
    except Exception:
        _close_descriptors(descriptors)
        raise


@contextmanager
def _opened_root(
    root: Path,
) -> Iterator[tuple[int, str, tuple[tuple[int, ...], ...], tuple[int, ...]]]:
    try:
        descriptors = _open_root_components(root)
        canonical = root.resolve(strict=True)
        identities = tuple(
            _directory_identity(
                os.fstat(descriptor),
                root=index == len(descriptors) - 1,
            )
            for index, descriptor in enumerate(descriptors)
        )
        yield (
            descriptors[-1],
            os.fspath(canonical),
            identities,
            identities[-1],
        )
        current_descriptors = _open_root_components(root)
        try:
            current_identities = tuple(
                _directory_identity(
                    os.fstat(descriptor),
                    root=index == len(current_descriptors) - 1,
                )
                for index, descriptor in enumerate(current_descriptors)
            )
            current_canonical = root.resolve(strict=True)
            if (
                current_canonical != canonical
                or current_identities != identities
            ):
                raise IntegrityError("record root or ancestor changed")
        finally:
            _close_descriptors(current_descriptors)
    except InputError:
        raise
    except IntegrityError:
        raise
    except OSError as error:
        raise IntegrityError("record root or ancestor is unsafe") from error
    finally:
        _close_descriptors(locals().get("descriptors", []))


def _read_open_regular(file_descriptor: int) -> _CapturedFile:
    before = os.fstat(file_descriptor)
    if not stat.S_ISREG(before.st_mode) or before.st_nlink != 1:
        raise IntegrityError(
            "accessed record artifact is not a single-link regular file"
        )
    chunks: list[bytes] = []
    while True:
        chunk = os.read(file_descriptor, 1024 * 1024)
        if not chunk:
            break
        chunks.append(chunk)
    after = os.fstat(file_descriptor)
    if _stat_identity(after) != _stat_identity(before):
        raise IntegrityError("record artifact changed during capture")
    content = b"".join(chunks)
    if len(content) != before.st_size:
        raise IntegrityError("record artifact size changed during capture")
    return _CapturedFile(_stat_identity(before), content)


def _open_artifact_components(
    root_fd: int, relative: PurePosixPath
) -> tuple[list[int], tuple[tuple[int, ...], ...]]:
    descriptors: list[int] = []
    identities: list[tuple[int, ...]] = []
    current = root_fd
    try:
        for component in relative.parts[:-1]:
            descriptor = _open_no_follow(
                component,
                os.O_RDONLY | os.O_DIRECTORY,
                dir_fd=current,
            )
            metadata = os.fstat(descriptor)
            if not stat.S_ISDIR(metadata.st_mode):
                raise IntegrityError(
                    "canonical artifact parent is not a directory"
                )
            descriptors.append(descriptor)
            identities.append(_directory_identity(metadata, root=False))
            current = descriptor
        descriptor = _open_no_follow(
            relative.parts[-1], os.O_RDONLY, dir_fd=current
        )
        descriptors.append(descriptor)
        identities.append(_stat_identity(os.fstat(descriptor)))
        return descriptors, tuple(identities)
    except Exception:
        _close_descriptors(descriptors)
        raise


def _capture_authorized_artifact(
    root: Path,
    relative_value: object,
    expected_identity: tuple[int, ...],
) -> bytes:
    relative = _safe_relative(relative_value)
    try:
        with _opened_root(root) as (root_fd, _, _, _):
            descriptors, identities = _open_artifact_components(root_fd, relative)
            try:
                if identities[-1] != expected_identity:
                    raise IntegrityError(
                        "canonical artifact node changed after admission"
                    )
                captured = _read_open_regular(descriptors[-1])
                if captured.identity != identities[-1]:
                    raise IntegrityError(
                        "canonical artifact changed before capture"
                    )
                current, current_identities = _open_artifact_components(
                    root_fd, relative
                )
                try:
                    if current_identities != identities:
                        raise IntegrityError(
                            "canonical artifact node changed during capture"
                        )
                finally:
                    _close_descriptors(current)
                return captured.content
            finally:
                _close_descriptors(descriptors)
    except IntegrityError:
        raise
    except OSError as error:
        raise IntegrityError("canonical artifact backing changed") from error


def _capture_inventory(
    directory_fd: int, prefix: PurePosixPath | None = None
) -> list[_InventoryEntry]:
    before = _directory_identity(os.fstat(directory_fd), root=False)
    try:
        names = sorted(os.listdir(directory_fd))
    except OSError as error:
        raise IntegrityError("record directory cannot be inventoried") from error
    entries: list[_InventoryEntry] = []
    for name in names:
        relative = PurePosixPath(name) if prefix is None else prefix / name
        _safe_relative(relative.as_posix())
        descriptor: int | None = None
        try:
            descriptor = _open_no_follow(
                name, os.O_RDONLY, dir_fd=directory_fd
            )
            metadata = os.fstat(descriptor)
            if stat.S_ISDIR(metadata.st_mode):
                entries.append(
                    _InventoryEntry(
                        relative.as_posix(),
                        "DIRECTORY",
                        stat.S_IMODE(metadata.st_mode),
                        _directory_identity(metadata, root=False),
                        None,
                    )
                )
                entries.extend(_capture_inventory(descriptor, relative))
            elif stat.S_ISREG(metadata.st_mode):
                captured = _read_open_regular(descriptor)
                entries.append(
                    _InventoryEntry(
                        relative.as_posix(),
                        "FILE",
                        stat.S_IMODE(metadata.st_mode),
                        captured.identity,
                        captured.content,
                    )
                )
            else:
                raise IntegrityError(
                    "record inventory contains an unsafe node"
                )
        except IntegrityError:
            raise
        except OSError as error:
            raise IntegrityError(
                "record inventory contains an unsafe node"
            ) from error
        finally:
            if descriptor is not None:
                try:
                    os.close(descriptor)
                except OSError:
                    pass
    if (
        _directory_identity(os.fstat(directory_fd), root=False) != before
        or sorted(os.listdir(directory_fd)) != names
    ):
        raise IntegrityError("record directory changed during capture")
    return entries


def _capture_record(root: Path) -> _AdmissionCapture:
    with _opened_root(root) as (
        root_fd,
        canonical_root,
        directory_identities,
        _,
    ):
        inventory = tuple(_capture_inventory(root_fd))
        by_path = {item.relative_path: item for item in inventory}
        names = {
            item.relative_path
            for item in inventory
            if "/" not in item.relative_path
        }
        present = [name for name in ROOTS if name in names]
        if len(present) != 1:
            raise IntegrityError(
                "record root must contain exactly one known manifest"
        )
        name = present[0]
        manifest_entry = by_path[name]
        if manifest_entry.kind != "FILE" or manifest_entry.content is None:
            raise IntegrityError("record manifest is not a regular file")
        manifest_file = _CapturedFile(
            manifest_entry.identity, manifest_entry.content
        )
        raw = manifest_file.content
        try:
            manifest = json.loads(raw.decode("utf-8"))
        except (UnicodeError, json.JSONDecodeError) as error:
            raise IntegrityError("record manifest is not canonical JSON") from error
        if not isinstance(manifest, dict) or raw != artifact_json(manifest):
            raise IntegrityError("record manifest is not canonical JSON")
        kind, schema, _ = ROOTS[name]
        if kind == "OBSERVATION":
            require_record_header(manifest, "observation")
        elif manifest.get("schema_version") != schema:
            raise InputError("workbench requires a v0.5 record")
        listed = _listed_descriptors(kind, manifest)
        captured: list[tuple[tuple[str, str, str], _CapturedFile]] = []
        for descriptor in listed:
            try:
                entry = by_path[descriptor["path"]]
            except KeyError as error:
                raise IntegrityError(
                    "authorized artifact is unavailable"
                ) from error
            if entry.kind != "FILE" or entry.content is None:
                raise IntegrityError(
                    "authorized artifact is not a regular file"
                )
            item = _CapturedFile(entry.identity, entry.content)
            if (
                len(item.content) != descriptor["size"]
                or _sha(item.content) != descriptor["sha256"]
            ):
                raise IntegrityError(
                    "authorized artifact descriptor differs"
                )
            captured.append(
                (
                    (
                        descriptor["role"],
                        descriptor["path"],
                        descriptor["sha256"],
                    ),
                    item,
                )
            )
        return _AdmissionCapture(
            canonical_root=canonical_root,
            root_name=Path(canonical_root).name,
            directory_identities=directory_identities,
            inventory=inventory,
            manifest_name=name,
            manifest=manifest,
            manifest_file=manifest_file,
            listed=tuple(captured),
        )


def _identity(kind: str, manifest: dict[str, Any]) -> dict[str, Any]:
    if kind == "OBSERVATION":
        return {"observation_id": manifest["observation_id"]}
    if kind == "DIAGNOSIS":
        return {
            "diagnosis_id": manifest["diagnosis_id"],
            "subject_id": manifest["subject"]["identity_value"],
        }
    if kind == "REFINEMENT":
        return {
            "draft_id": manifest["draft_id"],
            "revision_id": manifest["revision_id"],
        }
    return {
        "corpus_id": manifest["corpus_id"],
        "snapshot_id": manifest["snapshot_id"],
    }


def _listed_descriptors(kind: str, manifest: dict[str, Any]) -> list[dict[str, Any]]:
    if kind == "OBSERVATION":
        values = [
            item
            for extractor in manifest["extractors"]
            for item in extractor["artifacts"]
        ]
        values.append(
            {
                **manifest["comparison"],
                "role": "comparison-summary",
                "media_type": "application/json",
            }
        )
    else:
        values = list(manifest["artifacts"])
        if kind == "CORPUS":
            values = [
                item
                for item in values
                if item["role"] not in {"corpus-report", "corpus-stylesheet"}
            ]
    result: list[dict[str, Any]] = []
    seen_paths: set[str] = set()
    seen_pairs: set[tuple[str, str]] = set()
    root_name = next(name for name, item in ROOTS.items() if item[0] == kind)
    for original in values:
        item = {
            key: original[key]
            for key in ("path", "role", "media_type", "size", "sha256")
        }
        _safe_relative(item["path"])
        pair = (item["path"], item["role"])
        if (
            item["path"] == root_name
            or item["role"] not in ALLOWED_ROLES
            or item["media_type"] not in ALLOWED_MEDIA
            or item["path"] in seen_paths
            or pair in seen_pairs
        ):
            raise IntegrityError("authorized artifact descriptor union is invalid")
        seen_paths.add(item["path"])
        seen_pairs.add(pair)
        result.append(item)
    return result


def _verify_intrinsic(kind: str, root: Path) -> None:
    if kind == "OBSERVATION":
        result = verify_observation(root)
    elif kind == "DIAGNOSIS":
        result = verify_diagnosis(root)
    elif kind == "REFINEMENT":
        result = verify_refinement(root)
    else:
        result = verify_corpus(root)
    if result["artifact_integrity"]["status"] != "VERIFIED":
        raise IntegrityError("record does not have verified intrinsic integrity")


def _verify_intrinsic_capture(
    kind: str, capture: _AdmissionCapture
) -> None:
    root_name = _safe_relative(capture.root_name)
    if len(root_name.parts) != 1:
        raise IntegrityError("captured record root name is unsafe")
    with tempfile.TemporaryDirectory(
        prefix="tcw-workbench-admission-"
    ) as temporary:
        root = Path(temporary).resolve(strict=True) / root_name.name
        root.mkdir()
        directories: list[tuple[Path, int]] = []
        for entry in capture.inventory:
            relative = _safe_relative(entry.relative_path)
            destination = root.joinpath(*relative.parts)
            if entry.kind == "DIRECTORY":
                destination.mkdir()
                directories.append((destination, entry.mode))
                continue
            if entry.kind != "FILE" or entry.content is None:
                raise IntegrityError("captured inventory entry is invalid")
            destination.write_bytes(entry.content)
            os.chmod(destination, entry.mode)
        for directory, mode in reversed(directories):
            os.chmod(directory, mode)
        _verify_intrinsic(kind, root)


def _supplied_root(root: Path) -> Path:
    raw = os.fspath(root)
    if not isinstance(raw, str) or not raw:
        raise InputError("RECORD must be one local non-symlink directory")
    if any(component in {".", ".."} for component in raw.split(os.sep)):
        raise InputError("RECORD path must not contain traversal components")
    if os.path.isabs(raw):
        return Path(raw)
    return Path.cwd() / raw


def admit_record(root: Path, *, backing: Backing | None = None) -> AdmittedRecord:
    root = _supplied_root(root)
    before_capture = _capture_record(root)
    canonical_root = Path(before_capture.canonical_root)
    name = before_capture.manifest_name
    before = before_capture.manifest_file.content
    manifest = before_capture.manifest
    kind, schema, _ = ROOTS[name]
    _verify_intrinsic_capture(kind, before_capture)
    after_capture = _capture_record(root)
    if after_capture != before_capture:
        raise IntegrityError("record changed during admission")
    identity = _identity(kind, manifest)
    manifest_hash = _sha(before)
    logical = logical_copy_key(
        kind=kind,
        record_schema_version=schema,
        identity=identity,
        run_id=manifest["run_id"],
    )
    listed = _listed_descriptors(kind, manifest)
    captured = {
        key: item.content for key, item in before_capture.listed
    }
    captured_identities = {
        key: item.identity for key, item in before_capture.listed
    }
    canonical_backing = (
        Backing(root=canonical_root, top_level=True)
        if backing is None
        else Backing(
            root=canonical_root,
            containing_corpus_key=backing.containing_corpus_key,
            member_id=backing.member_id,
            descriptor_path=backing.descriptor_path,
            top_level=backing.top_level,
        )
    )
    result = AdmittedRecord(
        kind=kind,
        schema_version=schema,
        identity=identity,
        run_id=manifest["run_id"],
        status=manifest["status"],
        manifest_name=name,
        manifest=manifest,
        manifest_bytes=before,
        manifest_identity=before_capture.manifest_file.identity,
        manifest_sha256=manifest_hash,
        logical_copy_key=logical,
        record_key=None,
        listed=listed,
        artifact_bytes=captured,
        artifact_identities=captured_identities,
        backing=canonical_backing,
        copies=[canonical_backing],
        top_level=(backing is None or backing.top_level),
    )
    return result


def _equivalence(record: AdmittedRecord) -> bytes:
    root_role = ROOTS[record.manifest_name][2]
    union = sorted(
        [
            (
                "ROOT_MANIFEST",
                root_role,
                record.manifest_name,
                "application/json",
                len(record.manifest_bytes),
                record.manifest_sha256,
                (
                    "AVAILABLE"
                    if len(record.manifest_bytes) <= MAX_ARTIFACT_CONTENT
                    else "TOO_LARGE"
                ),
            ),
            *[
            (
                "MANIFEST_LISTED",
                item["role"],
                item["path"],
                item["media_type"],
                item["size"],
                item["sha256"],
                "AVAILABLE" if item["size"] <= MAX_ARTIFACT_CONTENT else "TOO_LARGE",
            )
            for item in record.listed
            ],
        ]
    )
    return b"\0".join(
        [
            record.manifest_bytes,
            json.dumps(union, separators=(",", ":")).encode(),
            record.status.encode(),
            json.dumps(record.identity, sort_keys=True).encode(),
        ]
    )


def _api_descriptor(
    record: AdmittedRecord, item: dict[str, Any], origin: str
) -> dict[str, Any]:
    key = artifact_key(
        record_key=record.record_key,
        role=item["role"],
        relative_path=item["path"],
        sha256=item["sha256"],
    )
    return {
        "artifact_key": key,
        "record_key": record.record_key,
        "role": item["role"],
        "relative_path": item["path"],
        "recorded_media_type": item["media_type"],
        "served_media_type": "text/plain; charset=utf-8",
        "size": item["size"],
        "sha256": item["sha256"],
        "availability": (
            "AVAILABLE" if item["size"] <= MAX_ARTIFACT_CONTENT else "TOO_LARGE"
        ),
        "origin": origin,
    }


def _nested_backings(
    corpus: AdmittedRecord,
) -> Iterable[tuple[Backing, str, dict[str, Any]]]:
    if corpus.record_key is None:
        raise IntegrityError("corpus identity is unavailable before expansion")
    for member in sorted(corpus.manifest["members"], key=lambda value: value["member_id"]):
        for stage, expected in (
            ("observation", "manifest.json"),
            ("diagnosis", "diagnosis-manifest.json"),
        ):
            descriptor = member[stage]["manifest"]
            if descriptor is None:
                continue
            relative = _safe_relative(descriptor["path"])
            if relative.name != expected:
                raise IntegrityError("nested manifest descriptor has the wrong kind")
            path = _safe_path(corpus.backing.root, descriptor["path"])
            yield (
                Backing(
                    root=path.parent,
                    containing_corpus_key=corpus.record_key,
                    member_id=member["member_id"],
                    descriptor_path=descriptor["path"],
                ),
                stage,
                descriptor,
            )


def _collapse_physical(
    physical: Iterable[AdmittedRecord],
) -> dict[str, AdmittedRecord]:
    """Collapse independently verified copies after pre-key equivalence."""

    groups: dict[str, list[AdmittedRecord]] = {}
    for item in physical:
        groups.setdefault(item.logical_copy_key, []).append(item)
    records: dict[str, AdmittedRecord] = {}
    for group in groups.values():
        first = group[0]
        if any(_equivalence(item) != _equivalence(first) for item in group[1:]):
            raise IntegrityError("logical record copies conflict")
        explicit = [item for item in group if item.top_level]
        canonical = (
            explicit[0]
            if explicit
            else min(group, key=lambda item: item.backing.order_key())
        )
        common_key = canonical.record_key or record_key(
            kind=canonical.kind,
            record_schema_version=canonical.schema_version,
            identity=canonical.identity,
            run_id=canonical.run_id,
            manifest_sha256=canonical.manifest_sha256,
        )
        canonical.record_key = common_key
        canonical.copies = [item.backing for item in group]
        canonical.top_level = bool(explicit)
        canonical.contained_by = {
            item.backing.containing_corpus_key
            for item in group
            if item.backing.containing_corpus_key is not None
        }
        canonical.descriptors()
        records[common_key] = canonical
    return records


def admit_records(roots: Iterable[Path]) -> AdmittedRecords:
    """Admit explicit roots and their descriptor-bounded corpus children."""

    active_build_provenance(command_id="tcw.workbench")
    root_list = list(roots)
    if not root_list:
        raise InputError("at least one RECORD is required")
    physical = [admit_record(root) for root in root_list]
    canonical_roots = [item.backing.root for item in physical]
    if len(canonical_roots) != len(set(canonical_roots)):
        raise InputError("repeated explicit RECORD")
    if len({item.logical_copy_key for item in physical}) != len(physical):
        raise InputError("two explicit roots represent the same logical record")

    # Corpus children are admitted after all explicit records.  New corpus
    # children are not recursively expanded: nested stages can only be
    # observation or diagnosis records under the closed corpus schema.
    for corpus in [item for item in physical if item.kind == "CORPUS"]:
        # Repeated logical explicit roots were rejected above, so this
        # one-element corpus-copy group has completed equivalence before the
        # key is needed for deterministic child-backing tuples.
        corpus.record_key = record_key(
            kind=corpus.kind,
            record_schema_version=corpus.schema_version,
            identity=corpus.identity,
            run_id=corpus.run_id,
            manifest_sha256=corpus.manifest_sha256,
        )
        for backing, stage, descriptor in _nested_backings(corpus):
            child = admit_record(backing.root, backing=backing)
            expected_kind = "OBSERVATION" if stage == "observation" else "DIAGNOSIS"
            if child.kind != expected_kind:
                raise IntegrityError("nested descriptor targets the wrong record kind")
            if (
                child.manifest_name
                != PurePosixPath(descriptor["path"]).name
                or len(child.manifest_bytes) != descriptor["size"]
                or child.manifest_sha256 != descriptor["sha256"]
            ):
                raise IntegrityError("nested manifest descriptor differs")
            physical.append(child)

    records = _collapse_physical(physical)

    explicit_keys = {
        item.record_key for item in records.values() if item.top_level
    }
    containment: list[tuple[str, str, str, str]] = []
    for corpus in [item for item in records.values() if item.kind == "CORPUS"]:
        for member in sorted(corpus.manifest["members"], key=lambda value: value["member_id"]):
            for stage, relation, identity_name in (
                ("observation", "CORPUS_CONTAINS_OBSERVATION", "observation_id"),
                ("diagnosis", "CORPUS_CONTAINS_DIAGNOSIS", "diagnosis_id"),
            ):
                data = member[stage]
                if data["manifest"] is None:
                    continue
                matches = [
                    item
                    for item in records.values()
                    if item.kind == ("OBSERVATION" if stage == "observation" else "DIAGNOSIS")
                    and item.run_id == data["run_id"]
                    and item.identity[identity_name] == data[identity_name]
                    and item.manifest_sha256 == data["manifest"]["sha256"]
                ]
                if len(matches) != 1:
                    raise IntegrityError("corpus containment target is not singular")
                containment.append(
                    (corpus.record_key, matches[0].record_key, relation, member["member_id"])
                )
    return AdmittedRecords(records, explicit_keys, containment)
