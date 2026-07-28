"""Cross-field validation for the public v0.5 JSON contracts."""

from __future__ import annotations

from collections import Counter
from typing import Any, Callable, Iterable

from tiny_corpus_workbench.diagnosis_rules import (
    CURRENT_RULESET,
    CURRENT_RULESET_PARAMETER_HASH,
    validate_finding_contract,
)
from tiny_corpus_workbench.domain import IntegrityError


class SemanticValidationError(ValueError):
    """Raised when schema-valid JSON violates a v0.5 semantic invariant."""


def _require(condition: bool, message: str) -> None:
    if not condition:
        raise SemanticValidationError(message)


def _require_ordered(
    values: list[Any],
    *,
    key: Callable[[Any], Any] | None = None,
    unique: bool = False,
    message: str,
) -> None:
    projected = [key(value) for value in values] if key else values
    _require(projected == sorted(projected), message)
    if unique:
        _require(len(projected) == len(set(projected)), message)


def _validate_comparison(comparison: dict[str, Any]) -> None:
    views = comparison["views"]
    present = sum(views[name] is not None for name in ("docling", "markitdown"))
    delta_key = (
        "docling_minus_markitdown"
        if "docling_minus_markitdown" in comparison
        else "deltas"
    )
    delta_present = comparison[delta_key] is not None
    expected = {
        "COMPLETE": (2, True),
        "INCOMPLETE": (1, False),
        "NOT_AVAILABLE": (0, False),
    }[comparison["status"]]
    _require(
        (present, delta_present) == expected,
        "comparison status and nullable views/deltas are inconsistent",
    )
    for view in views.values():
        if view is not None and "anchors" in view:
            _require_ordered(
                view["anchors"],
                key=lambda item: item["name"],
                unique=True,
                message="comparison anchors are not ordered and unique",
            )
    if "anchors" in comparison:
        _require_ordered(
            comparison["anchors"],
            key=lambda item: item["name"],
            unique=True,
            message="comparison source anchors are not ordered and unique",
        )


def _validate_finding(finding: dict[str, Any]) -> None:
    try:
        validate_finding_contract(finding)
    except IntegrityError as error:
        raise SemanticValidationError(str(error)) from error
    refs = finding["document_refs"]
    _require_ordered(
        refs,
        unique=True,
        message="finding document_refs are not ordered and unique",
    )
    evidence = finding["evidence"]
    rule_id = finding["rule_id"]
    if rule_id in {"TCW-D003", "TCW-D009"}:
        _require(
            evidence["occurrence_count"] == len(evidence["code_point_offsets"]),
            f"{rule_id} occurrence_count does not match code_point_offsets",
        )
        _require_ordered(
            evidence["code_point_offsets"],
            unique=True,
            message=f"{rule_id} offsets are not ordered and unique",
        )
    elif rule_id == "TCW-D004":
        _require(
            evidence["count"] == len(refs),
            "TCW-D004 count does not match document_refs",
        )
    elif rule_id == "TCW-D005":
        _require(
            evidence["current_level"] > evidence["previous_level"] + 1,
            "TCW-D005 is not a heading-level jump",
        )
    elif rule_id == "TCW-D006":
        if evidence["relationship_kind"] == "invalid_declared_caption":
            declared = evidence["declared_ref"]
            owners = [
                ref
                for ref in refs
                if ref.startswith(("#/tables/", "#/pictures/"))
            ]
            declared_is_owner = declared.startswith(
                ("#/tables/", "#/pictures/")
            )
            expected_owner_count = {1, 2} if declared_is_owner else {1}
            _require(
                len(owners) in expected_owner_count,
                "TCW-D006 has an invalid owner count",
            )
            _require(
                refs == sorted(set([*owners, declared])),
                "TCW-D006 document_refs are not the exact owner/declared union",
            )
    elif rule_id == "TCW-D007":
        _require(
            evidence["page_count"] == len(evidence["page_numbers"]),
            "TCW-D007 page_count does not match page_numbers",
        )
        _require_ordered(
            evidence["page_numbers"],
            unique=True,
            message="TCW-D007 page_numbers are not ordered and unique",
        )
    elif rule_id == "TCW-D010":
        _require(
            evidence["occurrence_count"]
            == len(evidence["hyphen_code_point_offsets"]),
            "TCW-D010 occurrence_count does not match offsets",
        )
        _require_ordered(
            evidence["hyphen_code_point_offsets"],
            unique=True,
            message="TCW-D010 offsets are not ordered and unique",
        )


def _validate_finding_collection(
    findings: list[dict[str, Any]],
    ruleset: dict[str, Any],
    summary: dict[str, Any],
) -> None:
    _require_ordered(
        findings,
        key=lambda item: item["finding_id"],
        unique=True,
        message="findings are not ordered and unique by finding_id",
    )
    for finding in findings:
        _validate_finding(finding)
    _require(
        ruleset
        == {
            **CURRENT_RULESET,
            "parameter_sha256": CURRENT_RULESET_PARAMETER_HASH,
        },
        "diagnosis ruleset metadata or parameter hash is inconsistent",
    )
    by_rule = Counter(finding["rule_id"] for finding in findings)
    by_severity = Counter(finding["severity"] for finding in findings)
    _require(
        summary["total"] == len(findings)
        == sum(summary["by_rule"].values())
        == sum(summary["by_severity"].values()),
        "diagnosis summary totals do not match findings",
    )
    _require(
        summary["by_rule"] == {key: by_rule[key] for key in summary["by_rule"]},
        "diagnosis by_rule counts do not match findings",
    )
    _require(
        summary["by_severity"]
        == {key: by_severity[key] for key in summary["by_severity"]},
        "diagnosis by_severity counts do not match findings",
    )


def _validate_corpus_summary(document: dict[str, Any]) -> None:
    totals = document["totals"]
    members = document["members"]
    _require(
        totals["member_count"] == len(members)
        == totals["complete"] + totals["partial"] + totals["failed"],
        "corpus summary totals do not match members",
    )
    status_counts = Counter(item["status"].lower() for item in members)
    _require(
        all(totals[name] == status_counts[name] for name in status_counts),
        "corpus summary status totals do not match members",
    )
    _require_ordered(
        members,
        key=lambda item: item["member_id"],
        unique=True,
        message="corpus summary members are not ordered and unique",
    )
    for member in members:
        _require(
            (member["status"] == "COMPLETE") == (member["error"] is None),
            "corpus summary member status and error are inconsistent",
        )
    _require_ordered(
        document["by_family"],
        key=lambda item: item["name"],
        unique=True,
        message="corpus summary families are not ordered and unique",
    )
    format_order = {"pdf": 0, "docx": 1, "md": 2, "txt": 3}
    _require(
        document["by_format"]
        == sorted(
            document["by_format"],
            key=lambda item: format_order[item["name"]],
        ),
        "corpus summary formats are not in canonical order",
    )
    _validate_named_counts(
        [*document["by_family"], *document["by_format"]],
        totals["member_count"],
    )
    _require(
        sum(item["member_count"] for item in document["by_family"])
        == totals["member_count"]
        and sum(item["member_count"] for item in document["by_format"])
        == totals["member_count"],
        "corpus summary named groups do not partition members",
    )
    _require(
        [item["name"] for item in document["extractors"]]
        == ["docling", "markitdown"],
        "corpus summary extractors are not in canonical order",
    )
    for counts in document["extractors"]:
        _require(
            counts["available"] + counts["unavailable"]
            == totals["member_count"],
            "corpus summary extractor counts do not sum",
        )
    _require_ordered(
        document["comparisons"],
        key=lambda item: item["member_id"],
        unique=True,
        message="corpus summary comparisons are not ordered and unique",
    )
    for comparison in document["comparisons"]:
        _validate_comparison(
            {
                "status": comparison["status"],
                "views": {
                    "docling": comparison["docling"],
                    "markitdown": comparison["markitdown"],
                },
                "docling_minus_markitdown": comparison[
                    "docling_minus_markitdown"
                ],
            }
        )
    for name, key in (
        (
            "findings",
            lambda item: (
                item["rule_id"],
                item["severity"],
                item["family"],
                item["format"],
            ),
        ),
        (
            "revision_groups",
            lambda item: (
                item["family"],
                item["format"],
                item["finding_rule"],
                item["refiner_id"],
            ),
        ),
        (
            "revisions",
            lambda item: (
                item["member_id"],
                item["chain_length"],
                item["revision_id"],
            ),
        ),
    ):
        _require_ordered(
            document[name],
            key=key,
            unique=True,
            message=f"corpus summary {name} are not in semantic order",
        )
    for finding_group in document["findings"]:
        _require(
            finding_group["affected_member_count"]
            <= finding_group["finding_count"],
            "corpus summary affected member count exceeds finding count",
        )
    _require(
        totals["finding_count"]
        == sum(item["finding_count"] for item in document["findings"]),
        "corpus summary finding total does not match groups",
    )
    _require(
        totals["revision_count"]
        == len(document["revisions"])
        == sum(
            item["revision_count"] for item in document["revision_groups"]
        ),
        "corpus summary revision total does not match aggregates",
    )


def validate_semantics(
    schema_version: str, document: dict[str, Any]
) -> None:
    """Validate equations and ordering that Draft 2020-12 cannot express."""

    if schema_version == "finding-set":
        _validate_finding_collection(
            document["findings"],
            document["ruleset"],
            document["summary"],
        )
    elif schema_version == "tcw.comparison-summary/v0.5":
        _validate_comparison(document)
    elif schema_version == "tcw.corpus-summary/v0.5":
        _validate_corpus_summary(document)
