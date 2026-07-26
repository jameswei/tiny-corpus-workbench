"""Lightweight catalog for the closed v0.5 JSON Schema baseline."""

from __future__ import annotations

import json
from pathlib import Path
from types import MappingProxyType
from typing import Any, Final, Mapping

from jsonschema import Draft202012Validator, FormatChecker
from referencing import Registry, Resource


SCHEMA_ROOT: Final = Path(__file__).with_name("schemas")
FORMAT_CHECKER: Final = FormatChecker()
COMMON_SCHEMA_PATH: Final = SCHEMA_ROOT / "common-v0.5.schema.json"
_COMMON_SCHEMA: Final = json.loads(COMMON_SCHEMA_PATH.read_text("utf-8"))
COMMON_DEFINITIONS: Final[Mapping[str, Any]] = MappingProxyType(
    _COMMON_SCHEMA["$defs"]
)

SCHEMA_FILES: Final[Mapping[str, str]] = MappingProxyType(
    {
        "tcw.authored-fixture/v0.5": "authored-fixture-v0.5.schema.json",
        "tcw.fixture-registry/v0.5": "fixture-registry-v0.5.schema.json",
        "tcw.preparation-manifest/v0.5": "preparation-manifest-v0.5.schema.json",
        "tcw.comparison-summary/v0.5": "comparison-summary-v0.5.schema.json",
        "tcw.verification-result/v0.5": "verification-result-v0.5.schema.json",
        "tcw.diagnosis-fixture-registry/v0.5": "diagnosis-fixture-registry-v0.5.schema.json",
        "tcw.diagnosis-manifest/v0.5": "diagnosis-manifest-v0.5.schema.json",
        "tcw.finding-set/v0.5": "finding-set-v0.5.schema.json",
        "tcw.diagnosis-verification-result/v0.5": "diagnosis-verification-result-v0.5.schema.json",
        "tcw.refinement-fixture-registry/v0.5": "refinement-fixture-registry-v0.5.schema.json",
        "tcw.refinement-draft/v0.5": "refinement-draft-v0.5.schema.json",
        "tcw.refinement-manifest/v0.5": "refinement-manifest-v0.5.schema.json",
        "tcw.transformation/v0.5": "transformation-v0.5.schema.json",
        "tcw.transformation-history/v0.5": "transformation-history-v0.5.schema.json",
        "tcw.refinement-verification-result/v0.5": "refinement-verification-result-v0.5.schema.json",
        "tcw.corpus-spec/v0.5": "corpus-spec-v0.5.schema.json",
        "tcw.corpus-manifest/v0.5": "corpus-manifest-v0.5.schema.json",
        "tcw.corpus-summary/v0.5": "corpus-summary-v0.5.schema.json",
        "tcw.corpus-verification-result/v0.5": "corpus-verification-result-v0.5.schema.json",
        "tcw.supported-provenance-registry/v0.5": "supported-provenance-registry-v0.5.schema.json",
        "tcw.workbench-startup/v0.5": "workbench-startup-v0.5.schema.json",
        "tcw.workbench-projection/v0.5": "workbench-projection-v0.5.schema.json",
        "tcw.workbench-record-detail/v0.5": "workbench-record-detail-v0.5.schema.json",
        "tcw.workbench-error/v0.5": "workbench-error-v0.5.schema.json",
    }
)

PRIVATE_MIGRATION_SCHEMAS: Final = frozenset(
    path.name
    for path in SCHEMA_ROOT.glob("*.schema.json")
    if path.name not in SCHEMA_FILES.values() and path != COMMON_SCHEMA_PATH
)


def load_schema(schema_version: str) -> dict[str, Any]:
    try:
        path = SCHEMA_ROOT / SCHEMA_FILES[schema_version]
    except KeyError as error:
        raise ValueError("unsupported schema version") from error
    schema = json.loads(path.read_text("utf-8"))
    Draft202012Validator.check_schema(schema)
    return schema


def validator(schema_version: str) -> Draft202012Validator:
    resources = []
    for path in (COMMON_SCHEMA_PATH, *(SCHEMA_ROOT / name for name in SCHEMA_FILES.values())):
        candidate = json.loads(path.read_text("utf-8"))
        resources.append((candidate["$id"], Resource.from_contents(candidate)))
    registry = Registry().with_resources(resources)
    return Draft202012Validator(
        load_schema(schema_version),
        format_checker=FORMAT_CHECKER,
        registry=registry,
    )


def common_validator(definition: str) -> Draft202012Validator:
    if definition not in COMMON_DEFINITIONS:
        raise ValueError("unknown common schema definition")
    resources = []
    for path in (
        COMMON_SCHEMA_PATH,
        *(SCHEMA_ROOT / name for name in SCHEMA_FILES.values()),
    ):
        candidate = json.loads(path.read_text("utf-8"))
        resources.append((candidate["$id"], Resource.from_contents(candidate)))
    return Draft202012Validator(
        {
            "$schema": "https://json-schema.org/draft/2020-12/schema",
            "$defs": dict(COMMON_DEFINITIONS),
            "$ref": f"#/$defs/{definition}",
        },
        format_checker=FORMAT_CHECKER,
        registry=Registry().with_resources(resources),
    )


def validate_document(
    schema_version: str, document: dict[str, Any]
) -> None:
    """Validate one public v0.5 document structurally and semantically."""

    validator(schema_version).validate(document)
    from tiny_corpus_workbench.semantic_validation import validate_semantics

    validate_semantics(schema_version, document)
