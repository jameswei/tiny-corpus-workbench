"""Load the project's current internal record schemas."""

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
        "observation-manifest": "observation-manifest.schema.json",
        "comparison": "comparison.schema.json",
        "observation-verification-result": "observation-verification-result.schema.json",
        "diagnosis-fixture-registry": "diagnosis-fixture-registry-v0.5.schema.json",
        "diagnosis-manifest": "diagnosis-manifest-v0.5.schema.json",
        "finding-set": "finding-set-v0.5.schema.json",
        "diagnosis-verification-result": "diagnosis-verification-result-v0.5.schema.json",
        "refinement-draft": "refinement-draft.schema.json",
        "refinement-manifest": "refinement-manifest.schema.json",
        "transformation": "transformation.schema.json",
        "transformation-history": "transformation-history.schema.json",
        "refinement-verification-result": "refinement-verification-result.schema.json",
        "corpus-spec": "corpus-spec.schema.json",
        "corpus-manifest": "corpus-manifest.schema.json",
        "corpus-summary": "corpus-summary.schema.json",
        "corpus-verification-result": "corpus-verification-result.schema.json",
        "tcw.supported-provenance-registry/v0.5": "supported-provenance-registry-v0.5.schema.json",
    }
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
    """Validate one internal document structurally and semantically."""

    validator(schema_version).validate(document)
    if schema_version == "comparison":
        from tiny_corpus_workbench.semantic_validation import (
            _validate_comparison,
        )

        _validate_comparison(document)
        return
    from tiny_corpus_workbench.semantic_validation import validate_semantics

    validate_semantics(schema_version, document)
