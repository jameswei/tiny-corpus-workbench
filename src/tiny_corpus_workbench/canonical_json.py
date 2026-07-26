"""Canonical JSON and v0.5 workbench identity preimages."""

from __future__ import annotations

import hashlib
import json
from collections.abc import Mapping, Sequence
from typing import Any


def canonical_json(value: Any) -> bytes:
    """Serialize one identity preimage as compact sorted UTF-8 JSON."""

    return json.dumps(
        value,
        ensure_ascii=False,
        allow_nan=False,
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")


def canonical_sha256(value: Any) -> str:
    return hashlib.sha256(canonical_json(value)).hexdigest()


def logical_copy_key(
    *,
    kind: str,
    record_schema_version: str,
    identity: Mapping[str, Any],
    run_id: str,
) -> str:
    return canonical_sha256(
        {
            "kind": kind,
            "record_schema_version": record_schema_version,
            "identity": dict(identity),
            "run_id": run_id,
        }
    )


def record_key(
    *,
    kind: str,
    record_schema_version: str,
    identity: Mapping[str, Any],
    run_id: str,
    manifest_sha256: str,
) -> str:
    return canonical_sha256(
        {
            "kind": kind,
            "record_schema_version": record_schema_version,
            "identity": dict(identity),
            "run_id": run_id,
            "manifest_sha256": manifest_sha256,
        }
    )


def edge_key(
    *,
    relation: str,
    from_record_key: str,
    expected_target: Mapping[str, Any],
) -> str:
    return canonical_sha256(
        {
            "relation": relation,
            "from_record_key": from_record_key,
            "expected_target": dict(expected_target),
        }
    )


def artifact_key(
    *,
    record_key: str,
    role: str,
    relative_path: str,
    sha256: str,
) -> str:
    return canonical_sha256(
        {
            "record_key": record_key,
            "role": role,
            "relative_path": relative_path,
            "sha256": sha256,
        }
    )


def _sorted_unique(values: Sequence[str], label: str) -> list[str]:
    ordered = sorted(values)
    if len(ordered) != len(set(ordered)):
        raise ValueError(f"{label} must contain unique keys")
    return ordered


def session_id(
    *,
    top_level_record_keys: Sequence[str],
    contained_record_keys: Sequence[str],
    edge_keys: Sequence[str],
) -> str:
    return canonical_sha256(
        {
            "schema_version": "tcw.workbench-projection/v0.5",
            "top_level_record_keys": _sorted_unique(
                top_level_record_keys, "top-level record keys"
            ),
            "contained_record_keys": _sorted_unique(
                contained_record_keys, "contained record keys"
            ),
            "edge_keys": _sorted_unique(edge_keys, "edge keys"),
        }
    )
