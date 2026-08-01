"""Canonical, non-record proposal storage for the local Workbench."""

from __future__ import annotations

import hashlib
import json
import os
import shutil
import stat
import tempfile
from contextlib import contextmanager
from dataclasses import dataclass
from pathlib import Path
from typing import Iterator

from tiny_corpus_workbench.artifacts import canonical_json as record_json
from tiny_corpus_workbench.canonical_json import canonical_sha256
from tiny_corpus_workbench.domain import IntegrityError
from tiny_corpus_workbench.schema_catalog import validate_document


@dataclass(frozen=True)
class DraftContext:
    draft_key: str
    draft_id: str
    diagnosis_record_key: str
    base_record_key: str


def draft_key(
    draft_id: str, diagnosis_record_key: str, base_record_key: str
) -> str:
    return canonical_sha256(
        {
            "draft_id": draft_id,
            "diagnosis_record_key": diagnosis_record_key,
            "base_record_key": base_record_key,
        }
    )


def _validated_canonical(raw: bytes) -> tuple[dict[str, object], str]:
    try:
        value = json.loads(raw.decode("utf-8"))
        if not isinstance(value, dict):
            raise ValueError
        validate_document("refinement-draft", value)
        identity = {key: item for key, item in value.items() if key != "draft_id"}
        expected_id = hashlib.sha256(record_json(identity).rstrip(b"\n")).hexdigest()
        if value.get("draft_id") != expected_id or raw != record_json(value):
            raise ValueError
        return value, expected_id
    except Exception as error:
        raise IntegrityError("refinement draft is invalid or non-canonical") from error


class RefinementDraftStore:
    """Keep canonical drafts on disk and live action contexts in memory."""

    def __init__(self, workspace: Path) -> None:
        self.workspace = workspace
        self.root = workspace / "refinement-drafts"
        self._contexts: dict[str, DraftContext] = {}

    def prepare(self) -> Path:
        try:
            workspace = self.workspace.lstat()
            if stat.S_ISLNK(workspace.st_mode) or not stat.S_ISDIR(workspace.st_mode):
                raise OSError
            self.root.mkdir(mode=0o700, exist_ok=True)
            metadata = self.root.lstat()
            if stat.S_ISLNK(metadata.st_mode) or not stat.S_ISDIR(metadata.st_mode):
                raise OSError
            if not os.access(self.root, os.R_OK | os.W_OK | os.X_OK):
                raise OSError
            if self.root.parent != self.workspace:
                raise OSError
            return self.root
        except OSError as error:
            raise IntegrityError("refinement draft directory is unavailable") from error

    @contextmanager
    def staging_path(self) -> Iterator[Path]:
        root = self.prepare()
        staging = Path(tempfile.mkdtemp(prefix=".staging-", dir=root))
        try:
            staging.chmod(0o700)
            yield staging / "proposal.json"
        finally:
            shutil.rmtree(staging, ignore_errors=True)

    def inspect_staged(self, path: Path) -> tuple[dict[str, object], bytes]:
        try:
            metadata = path.lstat()
            if stat.S_ISLNK(metadata.st_mode) or not stat.S_ISREG(metadata.st_mode):
                raise OSError
            raw = path.read_bytes()
            after = path.lstat()
            if (metadata.st_dev, metadata.st_ino, metadata.st_size) != (
                after.st_dev,
                after.st_ino,
                after.st_size,
            ):
                raise OSError
        except OSError as error:
            raise IntegrityError("staged refinement draft is unavailable") from error
        value, _ = _validated_canonical(raw)
        return value, raw

    def publish(self, staged: Path, draft_id: str, expected: bytes) -> Path:
        root = self.prepare()
        destination = root / f"{draft_id}.json"
        try:
            os.link(staged, destination, follow_symlinks=False)
        except FileExistsError:
            if self.read(draft_id) != expected:
                raise IntegrityError("refinement draft identity conflicts")
        except OSError as error:
            raise IntegrityError("refinement draft could not be published") from error
        if self.read(draft_id) != expected:
            raise IntegrityError("published refinement draft changed")
        return destination

    def read(self, draft_id: str) -> bytes:
        self.prepare()
        path = self.root / f"{draft_id}.json"
        descriptor: int | None = None
        try:
            root_before = self.root.lstat()
            flags = os.O_RDONLY | getattr(os, "O_NOFOLLOW", 0)
            descriptor = os.open(path, flags)
            before = os.fstat(descriptor)
            if not stat.S_ISREG(before.st_mode):
                raise OSError
            chunks: list[bytes] = []
            while True:
                chunk = os.read(descriptor, 1024 * 1024)
                if not chunk:
                    break
                chunks.append(chunk)
            after = os.fstat(descriptor)
            current = path.lstat()
            root_after = self.root.lstat()
            if (
                stat.S_ISLNK(root_after.st_mode)
                or not stat.S_ISDIR(root_after.st_mode)
                or (root_before.st_dev, root_before.st_ino)
                != (root_after.st_dev, root_after.st_ino)
                or (before.st_dev, before.st_ino, before.st_size)
                != (after.st_dev, after.st_ino, after.st_size)
                or (after.st_dev, after.st_ino, after.st_size)
                != (current.st_dev, current.st_ino, current.st_size)
                or stat.S_ISLNK(current.st_mode)
            ):
                raise OSError
            raw = b"".join(chunks)
        except OSError as error:
            raise IntegrityError("refinement draft is missing or changed") from error
        finally:
            if descriptor is not None:
                os.close(descriptor)
        value, validated_id = _validated_canonical(raw)
        if validated_id != draft_id or value["draft_id"] != draft_id:
            raise IntegrityError("refinement draft identity differs")
        return raw

    def register(
        self, draft_id: str, diagnosis_record_key: str, base_record_key: str
    ) -> DraftContext:
        key = draft_key(draft_id, diagnosis_record_key, base_record_key)
        context = DraftContext(key, draft_id, diagnosis_record_key, base_record_key)
        existing = self._contexts.get(key)
        if existing is not None and existing != context:
            raise IntegrityError("refinement draft context conflicts")
        self._contexts[key] = context
        return context

    def context(self, key: str) -> DraftContext | None:
        return self._contexts.get(key)


__all__ = ["DraftContext", "RefinementDraftStore", "draft_key"]
