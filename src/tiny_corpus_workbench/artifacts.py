from __future__ import annotations

import hashlib
import json
import os
import tempfile
from pathlib import Path
from typing import Any

from tiny_corpus_workbench.domain import IntegrityError, RuntimeContractError
from tiny_corpus_workbench.source import sha256_file


def canonical_json(value: Any) -> bytes:
    return (json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":")) + "\n").encode("utf-8")


def write_json(path: Path, value: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(canonical_json(value))


def inventory_models(root: Path, *, required: bool) -> dict[str, Any]:
    if root.is_symlink():
        raise RuntimeContractError("Docling model artifact root must not be a symlink")
    root = root.resolve()
    if not required:
        return {"required": False, "path": str(root), "inventory_hash": None, "files": []}
    if not root.is_dir():
        raise RuntimeContractError(f"required Docling model artifacts are missing: {root}")
    files = []
    for path in sorted(root.rglob("*")):
        if path.is_symlink():
            raise RuntimeContractError("Docling model artifacts must not contain symlinks")
        if path.is_file():
            files.append(
                {
                    "path": path.relative_to(root).as_posix(),
                    "size": path.stat().st_size,
                    "sha256": sha256_file(path),
                }
            )
    if not files:
        raise RuntimeContractError(f"required Docling model artifacts are empty: {root}")
    inventory_hash = hashlib.sha256(canonical_json(files).rstrip(b"\n")).hexdigest()
    return {"required": True, "path": str(root), "inventory_hash": inventory_hash, "files": files}


class AtomicObservation:
    def __init__(self, output_root: Path, source_key: str, run_id: str):
        self.parent = output_root / source_key
        self.destination = self.parent / run_id
        self.staging: Path | None = None

    def __enter__(self) -> Path:
        self.parent.mkdir(parents=True, exist_ok=True)
        if self.destination.exists():
            raise IntegrityError("publication conflict: run already exists")
        self.staging = Path(tempfile.mkdtemp(prefix=".staging-", dir=self.parent))
        return self.staging

    def publish(self) -> Path:
        if self.staging is None:
            raise IntegrityError("observation staging is unavailable")
        try:
            os.rename(self.staging, self.destination)
        except FileExistsError as error:
            raise IntegrityError("publication conflict: run already exists") from error
        self.staging = None
        return self.destination

    def __exit__(self, exc_type, exc, traceback) -> None:
        if self.staging and self.staging.exists():
            import shutil

            shutil.rmtree(self.staging)
