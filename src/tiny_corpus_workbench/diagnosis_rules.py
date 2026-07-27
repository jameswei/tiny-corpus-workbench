from __future__ import annotations

import hashlib
import json
import os
import stat
import unicodedata
from collections import Counter, defaultdict
from decimal import Decimal, InvalidOperation
from pathlib import Path, PureWindowsPath
from typing import Any, Iterable

from docling_core.types.doc import DoclingDocument
from jsonschema import Draft202012Validator
from referencing import Registry, Resource

from tiny_corpus_workbench.artifacts import (
    canonical_json,
)
from tiny_corpus_workbench.domain import (
    CanonicalUnavailableError,
    InputError,
    IntegrityError,
)
from tiny_corpus_workbench.source import sha256_file
from tiny_corpus_workbench.verification import FORMAT_CHECKER


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
CURRENT_RULES = [
    *RULESET,
    {
        "rule_id": "TCW-D009",
        "name": "NORMALIZABLE_WHITESPACE",
        "version": "1",
        "severity": "INFO",
        "parameters": {
            "line_endings": "LF",
            "horizontal_whitespace": "ASCII_SPACE",
            "preserve_internal_line_breaks": True,
        },
    },
    {
        "rule_id": "TCW-D010",
        "name": "POSSIBLE_LINE_END_HYPHENATION",
        "version": "1",
        "severity": "WARNING",
        "parameters": {
            "minimum_fragment_code_points": 2,
            "logical_line_breaks": 1,
            "right_initial": "lowercase",
        },
    },
]
CURRENT_RULESET = {
    "name": "tcw-evidence-based-diagnosis",
    "version": "v0.3",
    "rules": CURRENT_RULES,
}
CURRENT_RULESET_PARAMETER_HASH = hashlib.sha256(
    canonical_json(
        [
            {
                "rule_id": rule["rule_id"],
                "rule_version": rule["version"],
                "parameters": rule["parameters"],
            }
            for rule in CURRENT_RULES
        ]
    ).rstrip(b"\n")
).hexdigest()
CURRENT_FINDING_METADATA = {
    rule["rule_id"]: {
        "rule_version": rule["version"],
        "severity": rule["severity"],
        "summary": rule["name"],
    }
    for rule in CURRENT_RULES
}
TEXT_COLLECTIONS = (
    "texts",
    "pictures",
    "tables",
    "key_value_items",
    "form_items",
    "field_regions",
    "field_items",
)
REFINABLE_TEXT_REFERENCE_PREFIXES = (
    "#/texts/",
    "#/field_items/",
)
SUMMARY_BY_RULE = {rule["rule_id"]: rule["name"] for rule in RULESET}
SEVERITY_BY_RULE = {rule["rule_id"]: rule["severity"] for rule in RULESET}


def validate_finding_contract(finding: dict[str, Any]) -> None:
    rule_id = finding.get("rule_id")
    expected_metadata = CURRENT_FINDING_METADATA.get(rule_id)
    actual_metadata = {
        key: finding.get(key)
        for key in ("rule_version", "severity", "summary")
    }
    if expected_metadata is None or actual_metadata != expected_metadata:
        raise IntegrityError("finding metadata is inconsistent with its rule")
    references = finding.get("document_refs")
    evidence = finding.get("evidence")
    if not isinstance(references, list) or not isinstance(evidence, dict):
        raise IntegrityError("finding violates its rule-specific evidence contract")
    keys = set(evidence)

    def is_hash(value: Any) -> bool:
        return (
            isinstance(value, str)
            and len(value) == 64
            and all(character in "0123456789abcdef" for character in value)
        )

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
            and is_hash(evidence["normalized_text_sha256"])
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
            declared_is_owner = isinstance(declared, str) and declared.startswith(
                ("#/tables/", "#/pictures/")
            )
            owner_shape = (
                declared_is_owner
                and declared in owners
                and len(owners) in {1, 2}
            ) or (not declared_is_owner and len(owners) == 1)
            expected = sorted(
                set(owners + ([declared] if isinstance(declared, str) and declared else []))
            )
            valid = (
                keys == {"declared_ref", "relationship_kind"}
                and isinstance(declared, str)
                and bool(declared)
                and owner_shape
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
            and is_hash(evidence["normalized_text_sha256"])
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
    elif rule_id in {"TCW-D009", "TCW-D010"}:
        offsets_name = (
            "code_point_offsets"
            if rule_id == "TCW-D009"
            else "hyphen_code_point_offsets"
        )
        result_hash_name = (
            "normalized_text_sha256"
            if rule_id == "TCW-D009"
            else "repaired_text_sha256"
        )
        required = {
            offsets_name,
            "occurrence_count",
            "original_text_sha256",
            result_hash_name,
        }
        has_row = "row" in evidence
        has_column = "column" in evidence
        if has_row or has_column:
            required.update({"row", "column"})
        offsets = evidence.get(offsets_name)
        target_prefixes = (
            ("#/tables/",)
            if has_row and has_column
            else REFINABLE_TEXT_REFERENCE_PREFIXES
        )
        valid = (
            keys == required
            and references_match(
                minimum=1,
                maximum=1,
                prefixes=target_prefixes,
            )
            and isinstance(offsets, list)
            and bool(offsets)
            and all(type(offset) is int and offset >= 0 for offset in offsets)
            and offsets == sorted(set(offsets))
            and type(evidence.get("occurrence_count")) is int
            and evidence["occurrence_count"] == len(offsets)
            and is_hash(evidence.get("original_text_sha256"))
            and is_hash(evidence.get(result_hash_name))
            and has_row == has_column
            and (
                not has_row
                or (
                    references[0].startswith("#/tables/")
                    and type(evidence["row"]) is int
                    and evidence["row"] >= 0
                    and type(evidence["column"]) is int
                    and evidence["column"] >= 0
                )
            )
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
        "summary": SUMMARY_BY_RULE[rule_id],
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
    return sorted(unique.values(), key=lambda item: item["finding_id"])


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
