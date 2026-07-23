"""Fixed runtime identity shared by observation, diagnosis, and verification."""

from __future__ import annotations

import hashlib
import importlib.metadata
import platform
import sys
import tomllib
from pathlib import Path
from types import MappingProxyType
from typing import Any, Final, Mapping

from tiny_corpus_workbench.domain import RuntimeContractError


RUNTIME_DEPENDENCIES: Final[Mapping[str, str]] = MappingProxyType(
    {
        "docling": "2.113.0",
        "docling-core": "2.87.1",
        "markitdown": "0.1.6",
    }
)


def active_locked_runtime(lock_path: Path = Path("uv.lock")) -> dict[str, Any]:
    if platform.python_implementation() != "CPython" or sys.version_info[:2] != (
        3,
        12,
    ):
        raise RuntimeContractError("diagnosis requires the locked CPython 3.12 runtime")
    try:
        if lock_path.is_symlink() or not lock_path.is_file():
            raise OSError
        dependencies = {
            name: importlib.metadata.version(name) for name in RUNTIME_DEPENDENCIES
        }
        lock_bytes = lock_path.read_bytes()
        lock = tomllib.loads(lock_bytes.decode("utf-8"))
        locked_packages = [
            package
            for package in lock["package"]
            if package.get("name") in RUNTIME_DEPENDENCIES
        ]
        locked_dependencies = {
            package["name"]: package["version"] for package in locked_packages
        }
        lock_sha256 = hashlib.sha256(lock_bytes).hexdigest()
    except Exception as error:
        raise RuntimeContractError(
            "locked diagnosis runtime metadata is unavailable"
        ) from error
    if dependencies != RUNTIME_DEPENDENCIES:
        raise RuntimeContractError(
            "installed extractor versions do not match the locked diagnosis contract"
        )
    if (
        locked_dependencies != RUNTIME_DEPENDENCIES
        or len(locked_packages) != len(RUNTIME_DEPENDENCIES)
    ):
        raise RuntimeContractError(
            "uv.lock extractor versions do not match the diagnosis contract"
        )
    return {
        "python": platform.python_version(),
        "implementation": platform.python_implementation(),
        "lockfile_sha256": lock_sha256,
        "dependencies": dependencies,
    }
