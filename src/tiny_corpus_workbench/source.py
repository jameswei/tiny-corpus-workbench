from __future__ import annotations

import hashlib
import json
import re
import stat
import zipfile
from pathlib import Path

from tiny_corpus_workbench.domain import InputError, SourceIdentity


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
    )
