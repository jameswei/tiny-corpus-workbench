from __future__ import annotations

from typing import Any

from tiny_corpus_workbench.domain import InputError


CURRENT_FORMAT_VERSION = 1


def record_header(record_type: str) -> dict[str, Any]:
    """Return the current root header for one generated record family."""

    return {
        "record_type": record_type,
        "format_version": CURRENT_FORMAT_VERSION,
    }


def require_record_header(document: object, record_type: str) -> None:
    """Reject records that are not in the one current internal format."""

    if not isinstance(document, dict) or (
        document.get("record_type"),
        document.get("format_version"),
    ) != (record_type, CURRENT_FORMAT_VERSION):
        raise InputError(
            f"{record_type} record format is unsupported; "
            "regenerate the record with the current project"
        )
