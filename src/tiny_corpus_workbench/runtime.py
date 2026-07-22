"""Fixed v0.1 runtime identity shared by observation and verification."""

from __future__ import annotations

from types import MappingProxyType
from typing import Final, Mapping


RUNTIME_DEPENDENCIES: Final[Mapping[str, str]] = MappingProxyType(
    {
        "docling": "2.113.0",
        "docling-core": "2.87.1",
        "markitdown": "0.1.6",
    }
)
