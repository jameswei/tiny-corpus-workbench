from __future__ import annotations

import hashlib
import json
import os
import stat
import tempfile
import unicodedata
import uuid
from collections import Counter, defaultdict
from datetime import UTC, datetime
from decimal import Decimal, InvalidOperation
from pathlib import Path, PureWindowsPath
from typing import Any, Iterable

from docling_core.types.doc import DoclingDocument
from jsonschema import Draft202012Validator
from referencing import Registry, Resource

from tiny_corpus_workbench.artifacts import (
    _rename_exclusive,
    canonical_json,
    write_json,
)
from tiny_corpus_workbench.domain import (
    CanonicalUnavailableError,
    InputError,
    IntegrityError,
    RuntimeContractError,
)
from tiny_corpus_workbench.runtime import active_locked_runtime
from tiny_corpus_workbench.source import sha256_file
from tiny_corpus_workbench.verification import FORMAT_CHECKER, verify_observation


SCHEMA_ROOT = Path(__file__).with_name("schemas")
RULESET = [
    {
        "rule_id": "TCW-D001",
        "name": "EMPTY_DOCUMENT",
        "version": "1",
        "severity": "ERROR",
        "parameters": {},
    },
    {
        "rule_id": "TCW-D002",
        "name": "SUSPICIOUSLY_SHORT_DOCUMENT",
        "version": "1",
        "severity": "INFO",
        "parameters": {"minimum": 1, "maximum": 199},
    },
    {
        "rule_id": "TCW-D003",
        "name": "REPLACEMENT_CHARACTER",
        "version": "1",
        "severity": "ERROR",
        "parameters": {"character": "U+FFFD"},
    },
    {
        "rule_id": "TCW-D004",
        "name": "DUPLICATE_TEXT_BLOCK",
        "version": "1",
        "severity": "WARNING",
        "parameters": {"minimum_characters": 80},
    },
    {
        "rule_id": "TCW-D005",
        "name": "HEADING_LEVEL_JUMP",
        "version": "1",
        "severity": "WARNING",
        "parameters": {"first_level": 1, "maximum_increase": 1},
    },
    {
        "rule_id": "TCW-D006",
        "name": "ORPHAN_CAPTION",
        "version": "1",
        "severity": "WARNING",
        "parameters": {},
    },
    {
        "rule_id": "TCW-D007",
        "name": "REPEATED_PAGE_MARGIN_TEXT",
        "version": "1",
        "severity": "WARNING",
        "parameters": {
            "minimum_characters": 3,
            "maximum_characters": 200,
            "minimum_pages": 3,
            "top_maximum": 0.1,
            "bottom_minimum": 0.9,
        },
    },
    {
        "rule_id": "TCW-D008",
        "name": "MISSING_PDF_PROVENANCE",
        "version": "1",
        "severity": "WARNING",
        "parameters": {},
    },
]
RULESET_DESCRIPTOR = {
    "name": "tcw-evidence-based-diagnosis",
    "version": "v0.2",
    "rules": RULESET,
}
RULESET_PARAMETER_HASH = hashlib.sha256(
    canonical_json(
        [
            {
                "rule_id": rule["rule_id"],
                "rule_version": rule["version"],
                "parameters": rule["parameters"],
            }
            for rule in RULESET
        ]
    ).rstrip(b"\n")
).hexdigest()
TEXT_COLLECTIONS = (
    "texts",
    "pictures",
    "tables",
    "key_value_items",
    "form_items",
    "field_regions",
    "field_items",
)
SUMMARY_BY_RULE = {rule["rule_id"]: rule["name"] for rule in RULESET}
SEVERITY_BY_RULE = {rule["rule_id"]: rule["severity"] for rule in RULESET}


def validate_finding_contract(finding: dict[str, Any]) -> None:
    rule_id = finding["rule_id"]
    references = finding["document_refs"]
    evidence = finding["evidence"]
    keys = set(evidence)

    def references_match(
        *,
        minimum: int,
        maximum: int | None,
        prefixes: tuple[str, ...],
    ) -> bool:
        return (
            len(references) >= minimum
            and (maximum is None or len(references) <= maximum)
            and all(reference.startswith(prefixes) for reference in references)
        )

    valid = False
    if rule_id == "TCW-D001":
        valid = (
            references == ["#/body"]
            and keys == {"non_whitespace_characters"}
            and type(evidence["non_whitespace_characters"]) is int
            and evidence["non_whitespace_characters"] == 0
        )
    elif rule_id == "TCW-D002":
        valid = (
            references == ["#/body"]
            and keys == {"non_whitespace_characters"}
            and type(evidence["non_whitespace_characters"]) is int
            and 1 <= evidence["non_whitespace_characters"] <= 199
        )
    elif rule_id == "TCW-D003":
        offsets = evidence.get("code_point_offsets")
        shared = (
            isinstance(offsets, list)
            and offsets
            and all(type(offset) is int and offset >= 0 for offset in offsets)
            and offsets == sorted(set(offsets))
            and type(evidence.get("occurrence_count")) is int
            and evidence.get("occurrence_count") == len(offsets)
        )
        text_shape = keys == {"code_point_offsets", "occurrence_count"}
        table_shape = keys == {
            "code_point_offsets",
            "column",
            "occurrence_count",
            "row",
        }
        valid = shared and (
            (
                text_shape
                and references_match(
                    minimum=1, maximum=1, prefixes=("#/texts/",)
                )
            )
            or (
                table_shape
                and references_match(
                    minimum=1, maximum=1, prefixes=("#/tables/",)
                )
                and type(evidence["row"]) is int
                and evidence["row"] >= 0
                and type(evidence["column"]) is int
                and evidence["column"] >= 0
            )
        )
    elif rule_id == "TCW-D004":
        valid = (
            keys
            == {"count", "normalized_character_count", "normalized_text_sha256"}
            and references_match(minimum=2, maximum=None, prefixes=("#/texts/",))
            and type(evidence["count"]) is int
            and evidence["count"] == len(references)
            and type(evidence["normalized_character_count"]) is int
            and evidence["normalized_character_count"] >= 80
        )
    elif rule_id == "TCW-D005":
        first_shape = keys == {"current_level", "previous_level"}
        later_shape = keys == {
            "current_level",
            "previous_level",
            "previous_ref",
        }
        current = evidence.get("current_level")
        previous = evidence.get("previous_level")
        valid = (
            references_match(minimum=1, maximum=1, prefixes=("#/texts/",))
            and type(current) is int
            and type(previous) is int
            and current > previous + 1
            and (
                (first_shape and previous == 0)
                or (
                    later_shape
                    and previous >= 1
                    and isinstance(evidence["previous_ref"], str)
                    and evidence["previous_ref"].startswith("#/texts/")
                )
            )
        )
    elif rule_id == "TCW-D006":
        relationship = evidence.get("relationship_kind")
        if relationship == "orphan_caption":
            valid = (
                keys == {"relationship_kind"}
                and references_match(
                    minimum=1, maximum=1, prefixes=("#/texts/",)
                )
            )
        elif relationship == "invalid_declared_caption":
            declared = evidence.get("declared_ref")
            owners = [
                reference
                for reference in references
                if reference.startswith(("#/tables/", "#/pictures/"))
            ]
            expected = sorted(
                set(owners + ([declared] if isinstance(declared, str) and declared else []))
            )
            valid = (
                keys == {"declared_ref", "relationship_kind"}
                and isinstance(declared, str)
                and len(owners) == 1
                and references == expected
            )
    elif rule_id == "TCW-D007":
        pages = evidence.get("page_numbers")
        valid = (
            keys
            == {
                "band",
                "normalized_character_count",
                "normalized_text_sha256",
                "page_count",
                "page_numbers",
            }
            and references_match(minimum=1, maximum=None, prefixes=("#/texts/",))
            and evidence["band"] in {"top", "bottom"}
            and type(evidence["normalized_character_count"]) is int
            and 3 <= evidence["normalized_character_count"] <= 200
            and isinstance(pages, list)
            and all(type(page) is int and page >= 1 for page in pages)
            and pages == sorted(set(pages))
            and len(pages) >= 3
            and type(evidence["page_count"]) is int
            and evidence["page_count"] == len(pages)
        )
    elif rule_id == "TCW-D008":
        valid = (
            keys == {"content_layer"}
            and references_match(
                minimum=1,
                maximum=1,
                prefixes=("#/texts/", "#/tables/", "#/pictures/"),
            )
            and isinstance(evidence["content_layer"], str)
            and bool(evidence["content_layer"])
        )
    if not valid:
        raise IntegrityError("finding violates its rule-specific evidence contract")


def _normalize(value: str) -> str:
    value = unicodedata.normalize("NFC", value.replace("\r\n", "\n").replace("\r", "\n"))
    return " ".join(value.split()).strip()


def _non_whitespace_characters(value: str) -> int:
    return sum(not character.isspace() for character in value)


def _hash(value: bytes | str) -> str:
    if isinstance(value, str):
        value = value.encode("utf-8")
    return hashlib.sha256(value).hexdigest()


def _cref(value: Any) -> str | None:
    if isinstance(value, dict):
        for name in ("cref", "$ref"):
            if isinstance(value.get(name), str):
                return value[name]
    if isinstance(value, str):
        return value
    return None


def _index(payload: dict[str, Any]) -> dict[str, dict[str, Any]]:
    values: dict[str, dict[str, Any]] = {}
    for root_name in ("body", "furniture"):
        item = payload.get(root_name)
        canonical = f"#/{root_name}"
        if not isinstance(item, dict) or item.get("self_ref") != canonical:
            raise IntegrityError(
                "canonical document item self_ref does not match its stored path"
            )
        values[canonical] = item
    for collection in (*TEXT_COLLECTIONS, "groups"):
        items = payload.get(collection, [])
        if not isinstance(items, list):
            raise IntegrityError("canonical document collection is invalid")
        for position, item in enumerate(items):
            canonical = f"#/{collection}/{position}"
            if not isinstance(item, dict) or item.get("self_ref") != canonical:
                raise IntegrityError(
                    "canonical document item self_ref does not match its stored path"
                )
            values[canonical] = item
    for item in values.values():
        children = item.get("children", [])
        if not isinstance(children, list):
            raise IntegrityError("canonical document child references are invalid")
        for child in children:
            reference = _cref(child)
            if reference is None or reference not in values:
                raise IntegrityError("canonical document child reference is unresolved")
    return values


def _reading_order(
    payload: dict[str, Any], index: dict[str, dict[str, Any]]
) -> list[dict[str, Any]]:
    ordered: list[dict[str, Any]] = []
    visited: set[str] = set()

    def visit(reference: str) -> None:
        if reference in visited:
            return
        visited.add(reference)
        item = index[reference]
        if reference != "#/body":
            ordered.append(item)
        for child in item.get("children", []):
            child_reference = _cref(child)
            if child_reference is not None:
                visit(child_reference)

    visit("#/body")
    return ordered


def _table_cells(item: dict[str, Any]) -> list[dict[str, Any]]:
    data = item.get("data")
    cells = data.get("table_cells") if isinstance(data, dict) else None
    return [cell for cell in cells or [] if isinstance(cell, dict)]


def _finding(
    diagnosis_id: str,
    rule_id: str,
    references: Iterable[str],
    evidence: dict[str, Any],
) -> dict[str, Any]:
    document_refs = sorted(set(references))
    stable_evidence = {name: evidence[name] for name in sorted(evidence)}
    identity = {
        "diagnosis_id": diagnosis_id,
        "rule_id": rule_id,
        "rule_version": "1",
        "document_refs": document_refs,
        "evidence": stable_evidence,
    }
    return {
        "finding_id": _hash(canonical_json(identity).rstrip(b"\n")),
        "rule_id": rule_id,
        "rule_version": "1",
        "severity": SEVERITY_BY_RULE[rule_id],
        "summary": SUMMARY_BY_RULE[rule_id].replace("_", " ").title(),
        "document_refs": document_refs,
        "evidence": stable_evidence,
    }


def _finding_identity(diagnosis_id: str, finding: dict[str, Any]) -> dict[str, Any]:
    return {
        "diagnosis_id": diagnosis_id,
        "rule_id": finding["rule_id"],
        "rule_version": finding["rule_version"],
        "document_refs": finding["document_refs"],
        "evidence": finding["evidence"],
    }


def _canonicalize_findings(
    findings: Iterable[dict[str, Any]],
) -> list[dict[str, Any]]:
    unique: dict[str, dict[str, Any]] = {}
    for finding in findings:
        existing = unique.get(finding["finding_id"])
        if existing is not None and existing != finding:
            raise IntegrityError("finding identity collision")
        unique[finding["finding_id"]] = finding
    return sorted(
        unique.values(),
        key=lambda item: (
            item["rule_id"],
            item["document_refs"],
            canonical_json(item["evidence"]),
            item["finding_id"],
        ),
    )


def _bbox_midpoint_top_ratio(
    provenance: dict[str, Any], pages: dict[str, Any]
) -> tuple[int, Decimal] | None:
    page_no = provenance.get("page_no")
    bbox = provenance.get("bbox")
    page = pages.get(str(page_no), pages.get(page_no))
    if (
        type(page_no) is not int
        or not isinstance(bbox, dict)
        or not isinstance(page, dict)
        or not isinstance(page.get("size"), dict)
    ):
        return None
    height = page["size"].get("height")
    top, bottom = bbox.get("t"), bbox.get("b")
    if not all(isinstance(value, (int, float)) for value in (height, top, bottom)):
        return None
    try:
        height_decimal = Decimal(str(height))
        top_decimal = Decimal(str(top))
        bottom_decimal = Decimal(str(bottom))
    except (InvalidOperation, ValueError):
        return None
    if (
        not all(
            value.is_finite()
            for value in (height_decimal, top_decimal, bottom_decimal)
        )
        or height_decimal <= 0
    ):
        return None
    midpoint = (top_decimal + bottom_decimal) / 2
    if bbox.get("coord_origin") == "BOTTOMLEFT":
        midpoint = height_decimal - midpoint
    return page_no, midpoint / height_decimal


def analyze_document(
    payload: dict[str, Any],
    *,
    media_type: str,
    diagnosis_id: str,
) -> list[dict[str, Any]]:
    index = _index(payload)
    body = _reading_order(payload, index)
    body_refs = {
        item["self_ref"]
        for item in body
        if isinstance(item.get("self_ref"), str)
        and item.get("content_layer", "body") == "body"
    }
    body_items = [index[reference] for reference in body_refs]
    findings: list[dict[str, Any]] = []

    body_content: list[str] = []
    for item in body_items:
        text = item.get("text")
        if isinstance(text, str):
            body_content.append(_normalize(text))
        if item.get("label") == "table":
            body_content.extend(
                _normalize(cell["text"])
                for cell in _table_cells(item)
                if isinstance(cell.get("text"), str)
            )
    character_count = sum(_non_whitespace_characters(text) for text in body_content)
    if character_count == 0:
        findings.append(
            _finding(
                diagnosis_id,
                "TCW-D001",
                ["#/body"],
                {"non_whitespace_characters": 0},
            )
        )
    elif character_count <= 199:
        findings.append(
            _finding(
                diagnosis_id,
                "TCW-D002",
                ["#/body"],
                {"non_whitespace_characters": character_count},
            )
        )

    for collection in ("texts",):
        for item in payload.get(collection, []):
            if not isinstance(item, dict) or not isinstance(item.get("text"), str):
                continue
            offsets = [
                offset
                for offset, character in enumerate(item["text"])
                if character == "\ufffd"
            ]
            if offsets:
                findings.append(
                    _finding(
                        diagnosis_id,
                        "TCW-D003",
                        [item["self_ref"]],
                        {"code_point_offsets": offsets, "occurrence_count": len(offsets)},
                    )
                )
    for table in payload.get("tables", []):
        if not isinstance(table, dict):
            continue
        for cell in _table_cells(table):
            text = cell.get("text")
            if not isinstance(text, str) or "\ufffd" not in text:
                continue
            offsets = [
                offset for offset, character in enumerate(text) if character == "\ufffd"
            ]
            findings.append(
                _finding(
                    diagnosis_id,
                    "TCW-D003",
                    [table["self_ref"]],
                    {
                        "code_point_offsets": offsets,
                        "column": cell.get("start_col_offset_idx", 0),
                        "occurrence_count": len(offsets),
                        "row": cell.get("start_row_offset_idx", 0),
                    },
                )
            )

    duplicate_groups: dict[str, list[str]] = defaultdict(list)
    for item in body_items:
        if item.get("label") not in ("text", "paragraph"):
            continue
        text = _normalize(item.get("text", ""))
        if len(text) >= 80:
            duplicate_groups[text].append(item["self_ref"])
    for text, references in duplicate_groups.items():
        if len(references) >= 2:
            findings.append(
                _finding(
                    diagnosis_id,
                    "TCW-D004",
                    references,
                    {
                        "count": len(references),
                        "normalized_character_count": len(text),
                        "normalized_text_sha256": _hash(text),
                    },
                )
            )

    previous: tuple[str, int] | None = None
    for item in body:
        if item.get("content_layer", "body") != "body" or item.get("label") != "section_header":
            continue
        level = item.get("level")
        if type(level) is not int:
            continue
        if previous is None and level > 1:
            findings.append(
                _finding(
                    diagnosis_id,
                    "TCW-D005",
                    [item["self_ref"]],
                    {"current_level": level, "previous_level": 0},
                )
            )
        elif previous is not None and level > previous[1] + 1:
            findings.append(
                _finding(
                    diagnosis_id,
                    "TCW-D005",
                    [item["self_ref"]],
                    {
                        "current_level": level,
                        "previous_level": previous[1],
                        "previous_ref": previous[0],
                    },
                )
            )
        previous = (item["self_ref"], level)

    captions = {
        item["self_ref"]: item
        for item in payload.get("texts", [])
        if isinstance(item, dict) and item.get("label") == "caption"
    }
    valid_incoming: set[str] = set()
    for collection in ("tables", "pictures"):
        for owner in payload.get(collection, []):
            if not isinstance(owner, dict):
                continue
            for declared in owner.get("captions", []):
                reference = _cref(declared)
                target = index.get(reference or "")
                if target is not None and target.get("label") == "caption":
                    valid_incoming.add(reference or "")
                else:
                    references = [owner["self_ref"]]
                    if reference:
                        references.append(reference)
                    findings.append(
                        _finding(
                            diagnosis_id,
                            "TCW-D006",
                            references,
                            {
                                "declared_ref": reference or "",
                                "relationship_kind": "invalid_declared_caption",
                            },
                        )
                    )
    for reference in sorted(set(captions) - valid_incoming):
        findings.append(
            _finding(
                diagnosis_id,
                "TCW-D006",
                [reference],
                {"relationship_kind": "orphan_caption"},
            )
        )

    if media_type == "application/pdf":
        pages = payload.get("pages", {})
        margin_groups: dict[tuple[str, str], dict[str, Any]] = {}
        for item in body_items:
            text = _normalize(item.get("text", ""))
            if not 3 <= len(text) <= 200:
                continue
            for provenance in item.get("prov", []):
                if not isinstance(provenance, dict):
                    continue
                point = _bbox_midpoint_top_ratio(provenance, pages)
                if point is None:
                    continue
                page_no, ratio = point
                band = (
                    "top"
                    if ratio <= Decimal("0.10")
                    else "bottom"
                    if ratio >= Decimal("0.90")
                    else None
                )
                if band is None:
                    continue
                key = (_hash(text), band)
                group = margin_groups.setdefault(
                    key,
                    {"pages": set(), "refs": set(), "length": len(text)},
                )
                group["pages"].add(page_no)
                group["refs"].add(item["self_ref"])
        for (text_hash, band), group in margin_groups.items():
            if len(group["pages"]) >= 3:
                findings.append(
                    _finding(
                        diagnosis_id,
                        "TCW-D007",
                        group["refs"],
                        {
                            "band": band,
                            "normalized_character_count": group["length"],
                            "normalized_text_sha256": text_hash,
                            "page_count": len(group["pages"]),
                            "page_numbers": sorted(group["pages"]),
                        },
                    )
                )

        for collection in ("texts", "tables", "pictures"):
            for item in payload.get(collection, []):
                if isinstance(item, dict) and not item.get("prov"):
                    findings.append(
                        _finding(
                            diagnosis_id,
                            "TCW-D008",
                            [item["self_ref"]],
                            {"content_layer": item.get("content_layer", "body")},
                        )
                    )

    return _canonicalize_findings(findings)


def compute_diagnosis_id(
    observation_id: str, manifest_hash: str, document_hash: str
) -> str:
    identity = {
        "observation_id": observation_id,
        "observation_manifest_sha256": manifest_hash,
        "canonical_document_sha256": document_hash,
        "ruleset": RULESET_DESCRIPTOR,
    }
    return _hash(canonical_json(identity).rstrip(b"\n"))


def make_finding_set(
    payload: dict[str, Any],
    observation_manifest: dict[str, Any],
    *,
    manifest_hash: str,
    document_hash: str,
) -> dict[str, Any]:
    diagnosis_id = compute_diagnosis_id(
        observation_manifest["observation_id"], manifest_hash, document_hash
    )
    findings = analyze_document(
        payload,
        media_type=observation_manifest["source"]["media_type"],
        diagnosis_id=diagnosis_id,
    )
    return {
        "schema_version": "tcw.finding-set/v0.2",
        "diagnosis_id": diagnosis_id,
        "observation_id": observation_manifest["observation_id"],
        "canonical_artifact": "docling/document.json",
        "canonical_document_sha256": document_hash,
        "ruleset": RULESET_DESCRIPTOR,
        "summary": _summary(findings),
        "findings": findings,
    }


def validate_finding_set_semantics(
    finding_set: dict[str, Any], payload: dict[str, Any]
) -> None:
    findings = finding_set["findings"]
    if findings != _canonicalize_findings(findings):
        raise IntegrityError("findings are not unique and canonically ordered")
    if finding_set["summary"] != _summary(findings):
        raise IntegrityError("finding summary is inconsistent")
    known_references = set(_index(payload))
    for finding in findings:
        validate_finding_contract(finding)
        if (
            finding["severity"] != SEVERITY_BY_RULE[finding["rule_id"]]
            or finding["summary"]
            != SUMMARY_BY_RULE[finding["rule_id"]].replace("_", " ").title()
            or finding["document_refs"] != sorted(set(finding["document_refs"]))
            or list(finding["evidence"]) != sorted(finding["evidence"])
            or finding["finding_id"]
            != _hash(
                canonical_json(
                    _finding_identity(finding_set["diagnosis_id"], finding)
                ).rstrip(b"\n")
            )
        ):
            raise IntegrityError("finding identity or canonical form is inconsistent")
        unresolved_allowed = (
            finding["rule_id"] == "TCW-D006"
            and finding["evidence"].get("relationship_kind")
            == "invalid_declared_caption"
            and finding["evidence"].get("declared_ref")
        )
        for reference in finding["document_refs"]:
            if reference not in known_references and reference != unresolved_allowed:
                raise IntegrityError("finding document reference is inconsistent")
        previous_ref = finding["evidence"].get("previous_ref")
        if previous_ref is not None and previous_ref not in known_references:
            raise IntegrityError("finding document reference is inconsistent")


def _summary(findings: list[dict[str, Any]]) -> dict[str, Any]:
    severity = Counter(item["severity"] for item in findings)
    rules = Counter(item["rule_id"] for item in findings)
    return {
        "total": len(findings),
        "by_severity": {
            name: severity.get(name, 0) for name in ("ERROR", "WARNING", "INFO")
        },
        "by_rule": {
            rule["rule_id"]: rules.get(rule["rule_id"], 0) for rule in RULESET
        },
    }


def render_report(finding_set: dict[str, Any]) -> bytes:
    summary = finding_set["summary"]
    lines = [
        "# Evidence-Based Diagnosis",
        "",
        f"- Diagnosis ID: `{finding_set['diagnosis_id']}`",
        f"- Observation ID: `{finding_set['observation_id']}`",
        f"- Status: `{'FINDINGS' if summary['total'] else 'NO_FINDINGS'}`",
        f"- Finding count: {summary['total']}",
        "",
        "This diagnosis does not authorize mutation and does not certify overall quality.",
        "",
        "## Findings",
        "",
    ]
    if not finding_set["findings"]:
        lines.extend(
            [
                "No fixed v0.2 rule produced a finding. This result is not proof of correctness.",
                "",
            ]
        )
    else:
        for finding in finding_set["findings"]:
            lines.extend(
                [
                    f"### {finding['rule_id']} — {finding['summary']}",
                    "",
                    f"- Finding ID: `{finding['finding_id']}`",
                    f"- Severity: `{finding['severity']}`",
                    "- Document refs: "
                    + ", ".join(f"`{reference}`" for reference in finding["document_refs"]),
                    "- Evidence:",
                ]
            )
            for name, value in finding["evidence"].items():
                rendered = json.dumps(value, ensure_ascii=False, separators=(",", ":"))
                lines.append(f"  - `{name}`: `{rendered}`")
            lines.append("")
    return ("\n".join(lines).rstrip() + "\n").encode("utf-8")


def _validator(name: str) -> Draft202012Validator:
    try:
        schemas = {
            path.name: json.loads(path.read_text("utf-8"))
            for path in SCHEMA_ROOT.glob("*.schema.json")
        }
        registry = Registry()
        for schema in schemas.values():
            registry = registry.with_resource(
                schema["$id"], Resource.from_contents(schema)
            )
        return Draft202012Validator(
            schemas[name], registry=registry, format_checker=FORMAT_CHECKER
        )
    except Exception as error:
        raise RuntimeContractError("bundled diagnosis schema is unavailable") from error


def _validate(name: str, value: object) -> None:
    try:
        _validator(name).validate(value)
    except RuntimeContractError:
        raise
    except Exception as error:
        raise IntegrityError("staged diagnosis does not conform to its schema") from error


def snapshot_tree(root: Path) -> tuple[tuple[Any, ...], ...]:
    if root.is_symlink() or not root.is_dir():
        raise InputError("OBSERVATION_DIRECTORY must be one local non-symlink directory")
    identity: list[tuple[Any, ...]] = []
    try:
        root_metadata = root.stat()
        identity.append(
            (
                ".",
                "directory",
                root_metadata.st_dev,
                root_metadata.st_ino,
                stat.S_IMODE(root_metadata.st_mode),
                root_metadata.st_mtime_ns,
                root_metadata.st_ctime_ns,
            )
        )
        for path in sorted(root.rglob("*")):
            relative = path.relative_to(root).as_posix()
            metadata = path.lstat()
            if stat.S_ISLNK(metadata.st_mode):
                kind, digest = "symlink", os.readlink(path)
            elif stat.S_ISREG(metadata.st_mode):
                kind, digest = "file", sha256_file(path)
            elif stat.S_ISDIR(metadata.st_mode):
                kind, digest = "directory", None
            else:
                kind, digest = "other", None
            identity.append(
                (
                    relative,
                    kind,
                    metadata.st_dev,
                    metadata.st_ino,
                    stat.S_IMODE(metadata.st_mode),
                    metadata.st_size,
                    metadata.st_mtime_ns,
                    metadata.st_ctime_ns,
                    digest,
                )
            )
    except OSError as error:
        raise IntegrityError("observation inventory is unreadable") from error
    return tuple(identity)


class AtomicDiagnosis:
    def __init__(
        self,
        output_root: Path,
        source_key: str,
        observation_run_id: str,
        run_id: str,
    ):
        self.parent = output_root / source_key / observation_run_id
        self.destination = self.parent / run_id
        self.staging: Path | None = None

    def __enter__(self) -> Path:
        self.parent.mkdir(parents=True, exist_ok=True)
        self.staging = Path(tempfile.mkdtemp(prefix=".staging-", dir=self.parent))
        return self.staging

    def publish(self) -> Path:
        if self.staging is None:
            raise IntegrityError("diagnosis staging is unavailable")
        try:
            _rename_exclusive(self.staging, self.destination)
        except OSError as error:
            if self.destination.exists() or self.destination.is_symlink():
                raise IntegrityError(
                    "publication conflict: diagnosis run already exists"
                ) from error
            raise IntegrityError("diagnosis publication failed") from error
        self.staging = None
        return self.destination

    def __exit__(self, exc_type, exc, traceback) -> None:
        if self.staging and self.staging.exists():
            import shutil

            shutil.rmtree(self.staging)


def _validate_publication_parent(
    observation_root: Path,
    output_root: Path,
    source_key: str,
    observation_run_id: str,
) -> None:
    for label, value in (
        ("source key", source_key),
        ("observation run ID", observation_run_id),
    ):
        if (
            not isinstance(value, str)
            or not value
            or value in {".", ".."}
            or "/" in value
            or "\\" in value
            or "\x00" in value
            or Path(value).is_absolute()
            or bool(PureWindowsPath(value).drive)
        ):
            raise InputError(f"observation {label} is not a safe path component")
    ancestor = output_root
    while not (ancestor.exists() or ancestor.is_symlink()):
        if ancestor.parent == ancestor:
            break
        ancestor = ancestor.parent
    if not ancestor.is_dir():
        raise InputError("diagnosis output path conflicts with a non-directory")
    for component in (
        output_root,
        output_root / source_key,
        output_root / source_key / observation_run_id,
    ):
        if (component.exists() or component.is_symlink()) and not component.is_dir():
            raise InputError("diagnosis output path conflicts with a non-directory")
    try:
        observation = observation_root.resolve(strict=True)
        output = output_root.resolve(strict=False)
        parent = (output / source_key / observation_run_id).resolve(strict=False)
    except (OSError, RuntimeError) as error:
        raise InputError("diagnosis publication path cannot be resolved safely") from error
    if parent == output or not parent.is_relative_to(output):
        raise InputError("diagnosis publication path escapes the output root")
    if parent == observation or parent.is_relative_to(observation):
        raise InputError(
            "diagnosis output must not overlap the immutable observation"
        )


def _artifact(path: Path, root: Path, role: str, media_type: str) -> dict[str, Any]:
    return {
        "path": path.relative_to(root).as_posix(),
        "role": role,
        "media_type": media_type,
        "size": path.stat().st_size,
        "sha256": sha256_file(path),
        "application_immutable": True,
    }


def _load_input(
    root: Path,
) -> tuple[tuple[tuple[Any, ...], ...], dict[str, Any], bytes, bytes, dict[str, Any]]:
    before = snapshot_tree(root)
    try:
        manifest_bytes = (root / "manifest.json").read_bytes()
        manifest = json.loads(manifest_bytes)
    except (OSError, UnicodeError, json.JSONDecodeError) as error:
        raise InputError("observation manifest is unavailable") from error
    report = verify_observation(root)
    if report["artifact_integrity"]["status"] != "VERIFIED":
        if (
            isinstance(manifest, dict)
            and manifest.get("schema_version") == "tcw.preparation-manifest/v0.1"
            and isinstance(manifest.get("extractors"), list)
            and manifest["extractors"]
        ):
            docling = manifest["extractors"][0]
            descriptors = docling.get("artifacts", []) if isinstance(docling, dict) else []
            canonical = next(
                (
                    item
                    for item in descriptors
                    if isinstance(item, dict)
                    and item.get("role") == "docling-document-json"
                ),
                None,
            )
            if (
                isinstance(docling, dict)
                and docling.get("status") == "FAILED"
            ) or (
                isinstance(canonical, dict)
                and not (root / str(canonical.get("path", ""))).is_file()
            ):
                raise CanonicalUnavailableError(
                    "canonical Docling artifact is unavailable"
                )
        raise InputError("observation integrity is not verified")
    docling = manifest["extractors"][0]
    if docling["status"] not in ("SUCCESS", "PARTIAL_SUCCESS"):
        raise CanonicalUnavailableError("observation has no usable Docling result")
    descriptor = next(
        (
            item
            for item in docling["artifacts"]
            if item["role"] == "docling-document-json"
        ),
        None,
    )
    if descriptor is None:
        raise CanonicalUnavailableError("observation has no canonical Docling artifact")
    try:
        document_bytes = (root / descriptor["path"]).read_bytes()
        payload = json.loads(document_bytes)
    except (OSError, UnicodeError, json.JSONDecodeError) as error:
        raise CanonicalUnavailableError(
            "canonical Docling artifact is unavailable"
        ) from error
    try:
        _index(payload)
    except IntegrityError as error:
        raise CanonicalUnavailableError(
            "canonical Docling artifact paths are inconsistent"
        ) from error
    try:
        document = DoclingDocument.model_validate(payload)
        list(document.iterate_items(with_groups=True))
        for child in document.body.children:
            child.resolve(document)
        for table in document.tables:
            list(table.data.table_cells)
            for caption in table.captions:
                if not isinstance(caption.cref, str):
                    raise RuntimeError("caption reference API is incompatible")
        for picture in document.pictures:
            for caption in picture.captions:
                if not isinstance(caption.cref, str):
                    raise RuntimeError("caption reference API is incompatible")
        for item, _ in document.iterate_items(with_groups=True):
            for provenance in getattr(item, "prov", []):
                _ = (provenance.page_no, provenance.bbox)
        for page in document.pages.values():
            _ = (page.size.width, page.size.height)
    except Exception as error:
        raise RuntimeContractError(
            "locked Docling runtime cannot traverse the canonical artifact"
        ) from error
    return before, manifest, manifest_bytes, document_bytes, payload


def diagnose(root: Path, output_root: Path) -> Path:
    before, observation, manifest_bytes, document_bytes, payload = _load_input(root)
    manifest_hash = _hash(manifest_bytes)
    document_hash = _hash(document_bytes)
    finding_set = make_finding_set(
        payload,
        observation,
        manifest_hash=manifest_hash,
        document_hash=document_hash,
    )
    validate_finding_set_semantics(finding_set, payload)
    findings_bytes = canonical_json(finding_set)
    report_bytes = render_report(finding_set)
    now = datetime.now(UTC)
    run_id = f"{now.strftime('%Y%m%dT%H%M%S.%fZ')}-{uuid.uuid4().hex[:12]}"
    runtime = active_locked_runtime()
    _validate_publication_parent(
        root,
        output_root,
        observation["source"]["key"],
        observation["run_id"],
    )
    publisher = AtomicDiagnosis(
        output_root,
        observation["source"]["key"],
        observation["run_id"],
        run_id,
    )
    with publisher as staging:
        (staging / "findings.json").write_bytes(findings_bytes)
        (staging / "report.md").write_bytes(report_bytes)
        findings_artifact = _artifact(
            staging / "findings.json",
            staging,
            "diagnostic-findings",
            "application/json",
        )
        report_artifact = _artifact(
            staging / "report.md",
            staging,
            "diagnostic-report",
            "text/markdown",
        )
        manifest = {
            "schema_version": "tcw.diagnosis-manifest/v0.2",
            "milestone": "v0.2",
            "run_id": run_id,
            "diagnosis_id": finding_set["diagnosis_id"],
            "created_at": now.isoformat().replace("+00:00", "Z"),
            "status": "FINDINGS" if finding_set["summary"]["total"] else "NO_FINDINGS",
            "source": {
                key: observation["source"][key]
                for key in ("key", "media_type", "size", "sha256")
            },
            "observation": {
                "run_id": observation["run_id"],
                "observation_id": observation["observation_id"],
                "manifest_size": len(manifest_bytes),
                "manifest_sha256": manifest_hash,
                "canonical_document_path": "docling/document.json",
                "canonical_document_size": len(document_bytes),
                "canonical_document_sha256": document_hash,
                "docling_document_schema": observation["docling_document_schema"],
            },
            "runtime": {
                "python": runtime["python"],
                "implementation": runtime["implementation"],
                "lockfile_sha256": runtime["lockfile_sha256"],
                "package_version": runtime["package_version"],
                "dependencies": runtime["dependencies"],
            },
            "ruleset": {
                **RULESET_DESCRIPTOR,
                "parameter_sha256": RULESET_PARAMETER_HASH,
            },
            "summary": finding_set["summary"],
            "artifacts": [findings_artifact, report_artifact],
        }
        write_json(staging / "diagnosis-manifest.json", manifest)
        _validate("finding-set-v0.2.schema.json", finding_set)
        _validate("diagnosis-manifest-v0.2.schema.json", manifest)
        try:
            if (
                (staging / "findings.json").read_bytes() != findings_bytes
                or (staging / "report.md").read_bytes() != report_bytes
                or (staging / "diagnosis-manifest.json").read_bytes()
                != canonical_json(manifest)
            ):
                raise IntegrityError("staged diagnosis content changed")
            for descriptor in manifest["artifacts"]:
                path = staging / descriptor["path"]
                if (
                    path.stat().st_size != descriptor["size"]
                    or sha256_file(path) != descriptor["sha256"]
                ):
                    raise IntegrityError(
                        "staged diagnosis descriptor is inconsistent"
                    )
        except IntegrityError:
            raise
        except OSError as error:
            raise IntegrityError("staged diagnosis content is unavailable") from error
        expected = {
            "diagnosis-manifest.json",
            findings_artifact["path"],
            report_artifact["path"],
        }
        actual = {
            path.relative_to(staging).as_posix()
            for path in staging.rglob("*")
            if path.is_file()
        }
        if actual != expected or any(path.is_symlink() for path in staging.rglob("*")):
            raise IntegrityError("staged diagnosis inventory is invalid")
        if snapshot_tree(root) != before:
            raise IntegrityError("observation changed during diagnosis")
        return publisher.publish()
