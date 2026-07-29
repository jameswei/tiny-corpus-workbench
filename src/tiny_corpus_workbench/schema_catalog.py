"""Load the project's current internal record schemas."""

from __future__ import annotations

import json
from pathlib import Path
from types import MappingProxyType
from typing import Any, Final, Mapping

from jsonschema import Draft202012Validator, FormatChecker


SCHEMA_ROOT: Final = Path(__file__).with_name("schemas")
FORMAT_CHECKER: Final = FormatChecker()

SCHEMA_FILES: Final[Mapping[str, str]] = MappingProxyType(
    {
        "observation-manifest": "observation-manifest.schema.json",
        "comparison": "comparison.schema.json",
        "diagnosis-manifest": "diagnosis-manifest.schema.json",
        "finding-set": "finding-set.schema.json",
        "refinement-draft": "refinement-draft.schema.json",
        "refinement-manifest": "refinement-manifest.schema.json",
        "transformation": "transformation.schema.json",
        "transformation-history": "transformation-history.schema.json",
        "corpus-spec": "corpus-spec.schema.json",
        "corpus-manifest": "corpus-manifest.schema.json",
        "corpus-summary": "corpus-summary.schema.json",
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
    return Draft202012Validator(
        load_schema(schema_version),
        format_checker=FORMAT_CHECKER,
    )


def validate_document(
    schema_version: str, document: dict[str, Any]
) -> None:
    """Validate one internal document structurally and semantically."""

    validator(schema_version).validate(document)
    if schema_version == "comparison":
        from tiny_corpus_workbench.comparison import validate_comparison_semantics

        validate_comparison_semantics(document)
    elif schema_version == "finding-set":
        from tiny_corpus_workbench.diagnosis_rules import (
            validate_finding_set_semantics,
        )

        validate_finding_set_semantics(document)
