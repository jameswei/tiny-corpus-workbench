from __future__ import annotations

import hashlib
import json
import os
import re
import stat
import tempfile
import zipfile
from pathlib import Path

from tiny_corpus_workbench.domain import IntegrityError, InputError, SourceIdentity


MEDIA_TYPES = {
    ".pdf": "application/pdf",
    ".docx": "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
    ".md": "text/markdown",
    ".txt": "text/plain",
}
DOCX_REQUIRED = {"[Content_Types].xml", "word/document.xml", "_rels/.rels"}


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _fixture_id(path: Path, registry_path: Path = Path("fixtures/golden/fixtures.json")) -> str | None:
    if not registry_path.is_file():
        return None
    try:
        registry = json.loads(registry_path.read_text("utf-8"))
        resolved = path.resolve()
        for fixture in registry.get("fixtures", []):
            if Path(fixture["path"]).resolve() == resolved:
                return fixture["id"]
    except (OSError, ValueError, KeyError, TypeError):
        return None
    return None


def _validate_content(path: Path, suffix: str) -> None:
    if suffix == ".pdf":
        if not path.read_bytes()[:5] == b"%PDF-":
            raise InputError("PDF extension does not match file content")
        return
    if suffix == ".docx":
        if not zipfile.is_zipfile(path):
            raise InputError("DOCX extension does not match file content")
        try:
            with zipfile.ZipFile(path) as archive:
                if not DOCX_REQUIRED.issubset(archive.namelist()):
                    raise InputError("DOCX is missing required OOXML members")
        except (OSError, zipfile.BadZipFile) as error:
            raise InputError("DOCX content is invalid") from error
        return
    try:
        text = path.read_text("utf-8", errors="strict")
    except UnicodeDecodeError as error:
        raise InputError("text input must be strict UTF-8") from error
    if "\x00" in text:
        raise InputError("text input must not contain NUL characters")


def validate_source(value: str | Path) -> SourceIdentity:
    raw = str(value)
    if raw == "-" or "://" in raw:
        raise InputError("SOURCE must be one local file; stdin and URLs are unsupported")
    path = Path(value)
    try:
        mode = path.stat().st_mode
    except OSError as error:
        raise InputError("SOURCE is unavailable") from error
    if not stat.S_ISREG(mode):
        raise InputError("SOURCE must be one regular local file")
    suffix = path.suffix.lower()
    if suffix not in MEDIA_TYPES:
        raise InputError("unsupported media type; expected .pdf, .docx, .md, or .txt")
    _validate_content(path, suffix)
    digest = sha256_file(path)
    fixture_id = _fixture_id(path)
    stem = re.sub(r"[^a-z0-9]+", "-", path.stem.lower()).strip("-") or "source"
    key = fixture_id or f"{stem}-{digest[:12]}"
    return SourceIdentity(
        path=str(path.resolve()),
        name=path.name,
        key=key,
        media_type=MEDIA_TYPES[suffix],
        size=path.stat().st_size,
        sha256=digest,
        fixture_id=fixture_id,
        capture_method="direct-file-validation-v1",
    )


def _copy_descriptor(source_fd: int, destination_fd: int) -> tuple[int, str]:
    digest = hashlib.sha256()
    size = 0
    while True:
        chunk = os.read(source_fd, 1024 * 1024)
        if not chunk:
            break
        digest.update(chunk)
        size += len(chunk)
        view = memoryview(chunk)
        while view:
            written = os.write(destination_fd, view)
            view = view[written:]
    return size, digest.hexdigest()


class SourceSnapshot:
    """One owner-only byte snapshot shared by both extraction adapters."""

    def __init__(self, value: str | Path):
        self.original = Path(value)
        self.directory: Path | None = None
        self.path: Path | None = None
        self.identity: SourceIdentity | None = None

    def capture(self) -> tuple[Path, SourceIdentity]:
        raw = str(self.original)
        if raw == "-" or "://" in raw:
            raise InputError(
                "SOURCE must be one local file; stdin and URLs are unsupported"
            )
        suffix = self.original.suffix.lower()
        if suffix not in MEDIA_TYPES:
            raise InputError(
                "unsupported media type; expected .pdf, .docx, .md, or .txt"
            )
        try:
            initial = self.original.lstat()
        except OSError as error:
            raise InputError("SOURCE is unavailable") from error
        if stat.S_ISLNK(initial.st_mode) or not stat.S_ISREG(initial.st_mode):
            raise InputError("SOURCE must be one regular, non-symlink local file")

        self.directory = Path(tempfile.mkdtemp(prefix="tcw-source-"))
        os.chmod(self.directory, 0o700)
        self.path = self.directory / self.original.name
        source_fd: int | None = None
        destination_fd: int | None = None
        try:
            flags = os.O_RDONLY | getattr(os, "O_NOFOLLOW", 0)
            source_fd = os.open(self.original, flags)
            before = os.fstat(source_fd)
            if not stat.S_ISREG(before.st_mode):
                raise InputError("SOURCE must be one regular local file")
            destination_fd = os.open(
                self.path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600
            )
            size, digest = _copy_descriptor(source_fd, destination_fd)
            os.fsync(destination_fd)
            after = os.fstat(source_fd)
            identity_before = (
                before.st_dev,
                before.st_ino,
                before.st_size,
                before.st_mtime_ns,
                before.st_ctime_ns,
            )
            identity_after = (
                after.st_dev,
                after.st_ino,
                after.st_size,
                after.st_mtime_ns,
                after.st_ctime_ns,
            )
            if identity_before != identity_after or size != after.st_size:
                raise IntegrityError(
                    "SOURCE changed while its private snapshot was captured"
                )
        except InputError:
            raise
        except IntegrityError:
            raise
        except OSError as error:
            raise IntegrityError("SOURCE snapshot capture failed") from error
        finally:
            if destination_fd is not None:
                os.close(destination_fd)
            if source_fd is not None:
                os.close(source_fd)

        try:
            _validate_content(self.path, suffix)
        except Exception:
            self.cleanup()
            raise
        fixture_id = _fixture_id(self.original)
        stem = re.sub(r"[^a-z0-9]+", "-", self.original.stem.lower()).strip("-") or "source"
        key = fixture_id or f"{stem}-{digest[:12]}"
        self.identity = SourceIdentity(
            path=str(self.original.resolve()),
            name=self.original.name,
            key=key,
            media_type=MEDIA_TYPES[suffix],
            size=size,
            sha256=digest,
            fixture_id=fixture_id,
            capture_method="private-byte-snapshot-v1",
        )
        return self.path, self.identity

    def cleanup(self) -> None:
        if self.directory is None:
            return
        directory = self.directory
        try:
            if self.path is not None and self.path.exists():
                self.path.unlink()
            directory.rmdir()
        except OSError as error:
            raise IntegrityError("private SOURCE snapshot cleanup failed") from error
        finally:
            if not directory.exists():
                self.directory = None
                self.path = None
