"""Fixed runtime identity shared by observation, diagnosis, and verification."""

from __future__ import annotations

import hashlib
import importlib.metadata
import platform
import re
import sys
import tomllib
from pathlib import Path
from types import MappingProxyType
from typing import Any, Final, Mapping

from tiny_corpus_workbench.domain import RuntimeContractError


LOCK_PATH = Path("uv.lock")
V03_PACKAGE_VERSION: Final = "0.3.0"
V03_LOCKFILE_SHA256: Final = (
    "013ff8962de07dc91077bb3029a1746ba20e7725fa89d293be7666a9d8d05e65"
)
V04_PACKAGE_VERSION: Final = "0.4.0"
EXPECTED_LOCKFILE_SHA256: Final = (
    "2db4442fd44959691f9a391fec9fd46f8f14cf38b03679d97f6224dd2f1b3f0b"
)
RUNTIME_DEPENDENCIES: Final[Mapping[str, str]] = MappingProxyType(
    {
        "docling": "2.113.0",
        "docling-core": "2.87.1",
        "markitdown": "0.1.6",
    }
)
V03_COMPATIBLE_PACKAGE_LOCK_PAIRS: Final = frozenset(
    {
        (V03_PACKAGE_VERSION, V03_LOCKFILE_SHA256),
        (V04_PACKAGE_VERSION, EXPECTED_LOCKFILE_SHA256),
    }
)


def is_v03_compatible_runtime(runtime: Mapping[str, Any]) -> bool:
    """Return whether runtime provenance is one exact supported v0.3 pair."""

    try:
        package_lock_pair = (
            runtime["package_version"],
            runtime["lockfile_sha256"],
        )
        return (
            set(runtime)
            == {
                "python",
                "implementation",
                "lockfile_sha256",
                "package_version",
                "dependencies",
            }
            and runtime["implementation"] == "CPython"
            and isinstance(runtime["python"], str)
            and re.fullmatch(
                r"3\.12(?:\.\d+)?(?:[a-z]+\d*)?", runtime["python"]
            )
            is not None
            and runtime["dependencies"] == RUNTIME_DEPENDENCIES
            and package_lock_pair in V03_COMPATIBLE_PACKAGE_LOCK_PAIRS
        )
    except (KeyError, TypeError):
        return False


def active_locked_runtime(lock_path: Path | None = None) -> dict[str, Any]:
    from tiny_corpus_workbench import __version__

    lock_path = LOCK_PATH if lock_path is None else lock_path
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
        package_version = importlib.metadata.version("tiny-corpus-workbench")
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
    if lock_sha256 != EXPECTED_LOCKFILE_SHA256:
        raise RuntimeContractError(
            "uv.lock bytes do not match the exact diagnosis lock contract"
        )
    if package_version != __version__:
        raise RuntimeContractError(
            "installed tiny-corpus-workbench metadata does not match the source version"
        )
    return {
        "python": platform.python_version(),
        "implementation": platform.python_implementation(),
        "lockfile_sha256": lock_sha256,
        "package_version": package_version,
        "dependencies": dependencies,
    }
