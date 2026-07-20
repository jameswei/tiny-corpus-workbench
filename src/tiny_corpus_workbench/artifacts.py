from __future__ import annotations

import hashlib
import json
import os
import stat
import sys
import tempfile
from pathlib import Path, PurePosixPath
from typing import Any

from tiny_corpus_workbench.domain import IntegrityError, RuntimeContractError
from tiny_corpus_workbench.source import sha256_file


REQUIRED_MODEL_FILES = (
    "docling-project--docling-layout-heron/config.json",
    "docling-project--docling-layout-heron/preprocessor_config.json",
    "docling-project--docling-layout-heron/model.safetensors",
    "docling-project--docling-models/model_artifacts/tableformer/accurate/tm_config.json",
    "docling-project--docling-models/model_artifacts/tableformer/accurate/tableformer_accurate.safetensors",
)


def canonical_json(value: Any) -> bytes:
    return (json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":")) + "\n").encode("utf-8")


def write_json(path: Path, value: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(canonical_json(value))


def inventory_models(root: Path, *, required: bool) -> dict[str, Any]:
    if not required:
        return {
            "required": False,
            "path": str(root.absolute()),
            "inventory_hash": None,
            "files": [],
        }
    if root.is_symlink():
        raise RuntimeContractError("Docling model artifact root must not be a symlink")
    root = root.resolve()
    if not root.is_dir():
        raise RuntimeContractError(f"required Docling model artifacts are missing: {root}")
    for relative in REQUIRED_MODEL_FILES:
        path = root / relative
        if path.is_symlink() or not path.is_file() or path.stat().st_size == 0:
            raise RuntimeContractError(
                f"required Docling model artifact is missing or invalid: {relative}"
            )
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


def verify_staged_observation(
    root: Path, artifacts: list[dict[str, Any]]
) -> None:
    """Verify every staged path and captured byte descriptor before publish."""

    expected_files: dict[str, dict[str, Any]] = {}
    expected_directories: set[str] = set()
    for artifact in artifacts:
        relative = PurePosixPath(artifact["path"])
        if relative.is_absolute() or not relative.parts or ".." in relative.parts:
            raise IntegrityError("staged artifact path is invalid")
        key = relative.as_posix()
        if key in expected_files:
            raise IntegrityError("staged artifact inventory contains a duplicate path")
        expected_files[key] = artifact
        parent = relative.parent
        while parent != PurePosixPath("."):
            expected_directories.add(parent.as_posix())
            parent = parent.parent

    actual_files: set[str] = set()
    actual_directories: set[str] = set()
    try:
        staged_paths = sorted(root.rglob("*"))
        for path in staged_paths:
            relative = path.relative_to(root).as_posix()
            mode = path.lstat().st_mode
            if stat.S_ISLNK(mode):
                raise IntegrityError(f"staged artifact must not be a symlink: {relative}")
            if stat.S_ISREG(mode):
                actual_files.add(relative)
            elif stat.S_ISDIR(mode):
                actual_directories.add(relative)
            else:
                raise IntegrityError(
                    f"staged artifact has an unsupported file kind: {relative}"
                )
    except IntegrityError:
        raise
    except OSError as error:
        raise IntegrityError("staged artifact inventory is unreadable") from error

    if actual_files != set(expected_files):
        raise IntegrityError("staged artifact file inventory does not match the manifest")
    if actual_directories != expected_directories:
        raise IntegrityError(
            "staged artifact directory inventory does not match the manifest"
        )

    for relative, artifact in expected_files.items():
        path = root / relative
        try:
            mode = path.lstat().st_mode
            if not stat.S_ISREG(mode) or stat.S_ISLNK(mode):
                raise IntegrityError(
                    f"staged artifact is not a regular file: {relative}"
                )
            if path.stat().st_size != artifact["size"]:
                raise IntegrityError(f"staged artifact size changed: {relative}")
            if sha256_file(path) != artifact["sha256"]:
                raise IntegrityError(f"staged artifact hash changed: {relative}")
        except IntegrityError:
            raise
        except OSError as error:
            raise IntegrityError(
                f"staged artifact became unavailable: {relative}"
            ) from error


def _rename_exclusive(source: Path, destination: Path) -> None:
    """Atomically rename a directory while refusing any existing destination."""

    if sys.platform == "darwin":
        import ctypes

        library = ctypes.CDLL(None, use_errno=True)
        rename = library.renamex_np
        rename.argtypes = [ctypes.c_char_p, ctypes.c_char_p, ctypes.c_uint]
        rename.restype = ctypes.c_int
        result = rename(os.fsencode(source), os.fsencode(destination), 0x00000004)
    elif sys.platform.startswith("linux"):
        import ctypes

        library = ctypes.CDLL(None, use_errno=True)
        try:
            rename = library.renameat2
        except AttributeError as error:
            raise OSError("exclusive directory rename is unavailable") from error
        rename.argtypes = [ctypes.c_int, ctypes.c_char_p, ctypes.c_int, ctypes.c_char_p, ctypes.c_uint]
        rename.restype = ctypes.c_int
        result = rename(-100, os.fsencode(source), -100, os.fsencode(destination), 1)
    elif os.name == "nt":
        os.rename(source, destination)
        return
    else:
        raise OSError("exclusive directory rename is unavailable")
    if result != 0:
        import ctypes

        error_number = ctypes.get_errno()
        raise OSError(error_number, os.strerror(error_number), destination)


class AtomicObservation:
    def __init__(self, output_root: Path, source_key: str, run_id: str):
        self.parent = output_root / source_key
        self.destination = self.parent / run_id
        self.staging: Path | None = None

    def __enter__(self) -> Path:
        self.parent.mkdir(parents=True, exist_ok=True)
        self.staging = Path(tempfile.mkdtemp(prefix=".staging-", dir=self.parent))
        return self.staging

    def publish(self) -> Path:
        if self.staging is None:
            raise IntegrityError("observation staging is unavailable")
        try:
            _rename_exclusive(self.staging, self.destination)
        except OSError as error:
            if self.destination.exists() or self.destination.is_symlink():
                raise IntegrityError("publication conflict: run already exists") from error
            raise IntegrityError("artifact publication failed") from error
        self.staging = None
        return self.destination

    def __exit__(self, exc_type, exc, traceback) -> None:
        if self.staging and self.staging.exists():
            import shutil

            shutil.rmtree(self.staging)
