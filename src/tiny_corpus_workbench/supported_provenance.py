"""Validation and direct-ID lookup for supported v0.5 package provenance."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from tiny_corpus_workbench.canonical_json import canonical_json, canonical_sha256
from jsonschema import ValidationError

from tiny_corpus_workbench.schema_catalog import common_validator, validator


REGISTRY_PATH = Path(__file__).with_name("supported-provenance-v0.5.json")
ACTIVE_RUNTIME_ERROR = (
    "active runtime does not match this package provenance registry"
)
RECORDED_PROVENANCE_ERROR = (
    "recorded provenance is unsupported by this v0.5 package"
)
MALFORMED_RECORDED_PROVENANCE_ERROR = "recorded provenance is malformed"

COMMAND_IDS = (
    "tcw.diagnose",
    "tcw.draft-refinement",
    "tcw.inspect-corpus",
    "tcw.observe",
    "tcw.resolve-refinement",
    "tcw.verify",
    "tcw.verify-corpus",
    "tcw.verify-diagnosis",
    "tcw.verify-refinement",
    "tcw.workbench",
)
GENERATOR_IDS = (
    "tools.generate_diagnosis_fixtures",
    "tools.generate_fixtures",
    "tools.generate_refinement_fixtures",
)


def provenance_tuple(entry: dict[str, Any]) -> dict[str, Any]:
    return {
        key: value
        for key, value in entry.items()
        if key not in {"provenance_id", "commands", "generators"}
    }


def _validate_registry_intrinsic(registry: dict[str, Any]) -> None:
    validator("tcw.supported-provenance-registry/v0.5").validate(registry)
    entries = registry["entries"]
    ids = [entry["provenance_id"] for entry in entries]
    tuples = [canonical_json(provenance_tuple(entry)) for entry in entries]
    if ids != sorted(ids) or len(ids) != len(set(ids)):
        raise ValueError("supported provenance IDs are not strictly ordered and unique")
    if len(tuples) != len(set(tuples)):
        raise ValueError("supported provenance tuples are not unique")
    for entry in entries:
        if entry["provenance_id"] != canonical_sha256(provenance_tuple(entry)):
            raise ValueError("supported provenance ID does not match its tuple")
        for field in ("commands", "generators"):
            values = entry[field]
            if values != sorted(values) or len(values) != len(set(values)):
                raise ValueError(f"supported provenance {field} are not ordered")


def _read_checked_in_registry() -> dict[str, Any]:
    raw = REGISTRY_PATH.read_bytes()
    registry = json.loads(raw)
    if raw != canonical_json(registry) + b"\n":
        raise ValueError("supported provenance registry is not canonical JSON")
    _validate_registry_intrinsic(registry)
    return registry


def validate_registry(
    registry: dict[str, Any],
    *,
    checked_in_registry: dict[str, Any] | None = None,
) -> None:
    """Validate intrinsic integrity and append-only v0.5 compatibility."""

    _validate_registry_intrinsic(registry)
    baseline = (
        _read_checked_in_registry()
        if checked_in_registry is None
        else checked_in_registry
    )
    _validate_registry_intrinsic(baseline)
    baseline_entries = baseline["entries"]
    candidate_entries = registry["entries"]
    if (
        len(candidate_entries) < len(baseline_entries)
        or any(
            canonical_json(candidate) != canonical_json(checked_in)
            for candidate, checked_in in zip(
                candidate_entries, baseline_entries
            )
        )
    ):
        raise ValueError(
            "supported provenance registry does not preserve checked-in entries"
        )


def load_registry(path: Path = REGISTRY_PATH) -> dict[str, Any]:
    raw = path.read_bytes()
    registry = json.loads(raw)
    if raw != canonical_json(registry) + b"\n":
        raise ValueError("supported provenance registry is not canonical JSON")
    validate_registry(registry)
    return registry


def resolve_provenance(
    provenance_id: str, registry: dict[str, Any] | None = None
) -> dict[str, Any]:
    registry = load_registry() if registry is None else registry
    validate_registry(registry)
    matches = [
        entry for entry in registry["entries"] if entry["provenance_id"] == provenance_id
    ]
    if len(matches) != 1:
        raise ValueError(RECORDED_PROVENANCE_ERROR)
    return matches[0]


def _base_from_entry(entry: dict[str, Any]) -> dict[str, Any]:
    return {
        key: entry[key]
        for key in (
            "provenance_id",
            "package_version",
            "lockfile_sha256",
            "python",
            "dependencies",
        )
    }


def validate_recorded_provenance(
    recorded: dict[str, Any],
    *,
    command_id: str | None = None,
    generator_id: str | None = None,
    extracting: bool = False,
    registry: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Resolve by ID and compare every applicable recorded field."""

    if (command_id is None) == (generator_id is None):
        raise ValueError("exactly one provenance identifier is required")
    shape = (
        "BUILD_GENERATOR"
        if generator_id is not None
        else "BUILD_EXTRACTING_COMMAND"
        if extracting
        else "BUILD_COMMAND"
    )
    try:
        common_validator(shape).validate(recorded)
    except ValidationError as error:
        raise ValueError(MALFORMED_RECORDED_PROVENANCE_ERROR) from error
    try:
        entry = resolve_provenance(recorded["provenance_id"], registry)
        expected = _base_from_entry(entry)
        if command_id is not None:
            expected["command_id"] = command_id
            if extracting:
                expected["extractor_contract"] = entry["extractor_contract"]
            allowed = command_id in entry["commands"]
        else:
            expected["generator_id"] = generator_id
            allowed = generator_id in entry["generators"]
        if not allowed or recorded != expected:
            raise ValueError
    except (KeyError, TypeError, ValueError) as error:
        raise ValueError(RECORDED_PROVENANCE_ERROR) from error
    return entry


def resolve_active_provenance(
    active_tuple: dict[str, Any],
    *,
    command_id: str | None = None,
    generator_id: str | None = None,
    registry: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Resolve an installed tuple exactly; this is not artifact tuple lookup."""

    if (command_id is None) == (generator_id is None):
        raise ValueError("exactly one active identifier is required")
    try:
        registry = load_registry() if registry is None else registry
        validate_registry(registry)
        matches = [
            entry
            for entry in registry["entries"]
            if provenance_tuple(entry) == active_tuple
        ]
        if len(matches) != 1:
            raise ValueError
        entry = matches[0]
        allowed = (
            command_id in entry["commands"]
            if command_id is not None
            else generator_id in entry["generators"]
        )
        if not allowed:
            raise ValueError
    except (TypeError, ValueError) as error:
        raise ValueError(ACTIVE_RUNTIME_ERROR) from error
    return entry
