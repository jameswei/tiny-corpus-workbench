"""Immutable storage for document inputs accepted by the local Workbench."""

from __future__ import annotations

import os
import stat
import tempfile
from dataclasses import dataclass
from pathlib import Path

from tiny_corpus_workbench.application.workbench import validate_workspace
from tiny_corpus_workbench.domain import IntegrityError, InputError
from tiny_corpus_workbench.source import MEDIA_TYPES, validate_source


MAX_UPLOAD_BYTES = 33_554_432
MAX_FILENAME_BYTES = 255
SUPPORTED_EXTENSIONS = (".docx", ".md", ".pdf", ".txt")


@dataclass(frozen=True)
class StoredInput:
    """Metadata for one immutable content-addressed uploaded input."""

    path: Path
    name: str
    media_type: str
    size: int
    sha256: str


def validate_upload_filename(filename: str) -> str:
    """Return a safe, supported single-component upload filename."""

    if (
        not filename
        or filename in {".", ".."}
        or "\x00" in filename
        or "/" in filename
        or "\\" in filename
    ):
        raise InputError("upload filename must be one safe filesystem component")
    try:
        encoded = filename.encode("utf-8", errors="strict")
    except UnicodeEncodeError as error:
        raise InputError("upload filename must be valid UTF-8") from error
    if len(encoded) > MAX_FILENAME_BYTES:
        raise InputError("upload filename exceeds the 255-byte UTF-8 limit")
    if Path(filename).suffix.lower() not in SUPPORTED_EXTENSIONS:
        raise InputError(
            "unsupported media type; expected .pdf, .docx, .md, or .txt"
        )
    return filename


def _prepare_inputs_root(workspace: Path) -> Path:
    inputs = workspace / "inputs"
    try:
        inputs.mkdir(exist_ok=True)
        metadata = inputs.lstat()
    except OSError as error:
        raise InputError("workspace inputs are unavailable") from error
    if stat.S_ISLNK(metadata.st_mode) or not stat.S_ISDIR(metadata.st_mode):
        raise InputError("workspace inputs must be one local directory")
    if not os.access(inputs, os.R_OK | os.W_OK | os.X_OK):
        raise InputError(
            "workspace inputs must be readable, writable, and searchable"
        )
    return inputs


def _prepare_digest_root(inputs: Path, digest: str) -> tuple[Path, bool]:
    root = inputs / digest
    created = False
    try:
        root.mkdir()
        created = True
    except FileExistsError:
        pass
    except OSError as error:
        raise IntegrityError("input publication directory is unavailable") from error
    try:
        metadata = root.lstat()
    except OSError as error:
        raise IntegrityError("input publication directory is unavailable") from error
    if stat.S_ISLNK(metadata.st_mode) or not stat.S_ISDIR(metadata.st_mode):
        raise IntegrityError("input publication directory is invalid")
    if not os.access(root, os.R_OK | os.W_OK | os.X_OK):
        raise IntegrityError("input publication directory is unusable")
    return root, created


def _matches_existing_target(target: Path, staging: Path, size: int) -> bool:
    descriptor: int | None = None
    try:
        metadata = target.lstat()
        if (
            not stat.S_ISREG(metadata.st_mode)
            or stat.S_ISLNK(metadata.st_mode)
            or metadata.st_size != size
        ):
            return False
        descriptor = os.open(
            target, os.O_RDONLY | getattr(os, "O_NOFOLLOW", 0)
        )
        before = os.fstat(descriptor)
        if not stat.S_ISREG(before.st_mode) or before.st_size != size:
            return False
        with os.fdopen(descriptor, "rb", closefd=False) as existing:
            with staging.open("rb") as candidate:
                while True:
                    existing_chunk = existing.read(1024 * 1024)
                    candidate_chunk = candidate.read(1024 * 1024)
                    if existing_chunk != candidate_chunk:
                        return False
                    if not existing_chunk:
                        break
        after = os.fstat(descriptor)
        return (
            before.st_dev,
            before.st_ino,
            before.st_size,
            before.st_mtime_ns,
            before.st_ctime_ns,
        ) == (
            after.st_dev,
            after.st_ino,
            after.st_size,
            after.st_mtime_ns,
            after.st_ctime_ns,
        )
    except OSError as error:
        raise IntegrityError("existing input target is unreadable") from error
    finally:
        if descriptor is not None:
            os.close(descriptor)


def store_uploaded_input(
    workspace_value: str | os.PathLike[str],
    filename: str,
    content: bytes,
) -> StoredInput:
    """Validate, hash, and atomically publish one immutable uploaded input."""

    workspace = validate_workspace(workspace_value)
    name = validate_upload_filename(filename)
    if len(content) > MAX_UPLOAD_BYTES:
        raise InputError("upload exceeds the 33,554,432-byte limit")
    inputs = _prepare_inputs_root(workspace)
    suffix = Path(name).suffix.lower()
    descriptor, staging_name = tempfile.mkstemp(
        prefix=".staging-",
        suffix=suffix,
        dir=inputs,
    )
    staging = Path(staging_name)
    digest_root: Path | None = None
    digest_root_created = False
    try:
        with os.fdopen(descriptor, "wb") as stream:
            stream.write(content)
            stream.flush()
            os.fsync(stream.fileno())
        identity = validate_source(staging)
        digest_root, digest_root_created = _prepare_digest_root(
            inputs, identity.sha256
        )
        target = digest_root / name
        try:
            os.link(staging, target, follow_symlinks=False)
        except FileExistsError:
            if not _matches_existing_target(target, staging, identity.size):
                raise IntegrityError(
                    "input publication conflicts with existing target"
                )
        except OSError as error:
            raise IntegrityError("input publication failed") from error
        return StoredInput(
            path=target,
            name=name,
            media_type=MEDIA_TYPES[suffix],
            size=identity.size,
            sha256=identity.sha256,
        )
    finally:
        try:
            staging.unlink(missing_ok=True)
        except OSError as error:
            raise IntegrityError("input staging cleanup failed") from error
        if digest_root_created and digest_root is not None:
            try:
                digest_root.rmdir()
            except OSError:
                pass


__all__ = [
    "MAX_FILENAME_BYTES",
    "MAX_UPLOAD_BYTES",
    "SUPPORTED_EXTENSIONS",
    "StoredInput",
    "store_uploaded_input",
    "validate_upload_filename",
]
