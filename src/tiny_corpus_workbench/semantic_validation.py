"""Cross-field validation for the public v0.5 JSON contracts."""

from __future__ import annotations

from collections import Counter
from typing import Any, Callable, Iterable

from tiny_corpus_workbench.canonical_json import (
    artifact_key,
    canonical_sha256,
    edge_key,
    record_key,
    session_id,
)


class SemanticValidationError(ValueError):
    """Raised when schema-valid JSON violates a v0.5 semantic invariant."""


EXPLICIT_ARTIFACT_LIMIT = 16 * 1024 * 1024
ROOT_MANIFEST_BINDINGS = {
    "OBSERVATION": ("preparation-manifest", "manifest.json"),
    "DIAGNOSIS": ("diagnosis-manifest", "diagnosis-manifest.json"),
    "REFINEMENT": ("refinement-manifest", "refinement-manifest.json"),
    "CORPUS": ("corpus-manifest", "corpus-manifest.json"),
}
EDGE_SOURCE_KINDS = {
    "DIAGNOSIS_SUBJECT": "DIAGNOSIS",
    "REFINEMENT_DIAGNOSIS": "REFINEMENT",
    "REFINEMENT_BASE": "REFINEMENT",
    "REFINEMENT_PARENT": "REFINEMENT",
    "CORPUS_CONTAINS_OBSERVATION": "CORPUS",
    "CORPUS_CONTAINS_DIAGNOSIS": "CORPUS",
    "CORPUS_EXTERNAL_REFINEMENT": "CORPUS",
}


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


def _validate_expected_target(target: dict[str, Any]) -> None:
    discriminator = (
        target["kind"],
        target["record_schema_version"],
        target["identity_type"],
    )
    _require(
        discriminator
        in {
            (
                "OBSERVATION",
                "tcw.preparation-manifest/v0.5",
                "observation_id",
            ),
            (
                "DIAGNOSIS",
                "tcw.diagnosis-manifest/v0.5",
                "diagnosis_id",
            ),
            (
                "REFINEMENT",
                "tcw.refinement-manifest/v0.5",
                "revision_id",
            ),
        },
        "expected-target discriminator tuple is inconsistent",
    )


def _validate_descriptor(
    descriptor: dict[str, Any], expected_record_key: str
) -> None:
    _require(
        descriptor["record_key"] == expected_record_key,
        "descriptor record_key does not match its record",
    )
    _require(
        descriptor["artifact_key"]
        == artifact_key(
            record_key=descriptor["record_key"],
            role=descriptor["role"],
            relative_path=descriptor["relative_path"],
            sha256=descriptor["sha256"],
        ),
        "descriptor artifact_key does not match its identity preimage",
    )
    _require(
        (descriptor["availability"] == "TOO_LARGE")
        == (descriptor["size"] > EXPLICIT_ARTIFACT_LIMIT),
        "descriptor availability is inconsistent with its size",
    )


def _validate_root_manifest(kind: str, descriptor: dict[str, Any]) -> None:
    expected_role, expected_path = ROOT_MANIFEST_BINDINGS[kind]
    _require(
        descriptor["origin"] == "ROOT_MANIFEST"
        and descriptor["role"] == expected_role
        and descriptor["relative_path"] == expected_path,
        "root manifest descriptor does not match its record kind",
    )


def _validate_edge_source(edge: dict[str, Any], source_kind: str) -> None:
    _require(
        source_kind == EDGE_SOURCE_KINDS[edge["relation"]],
        "relationship source kind is inconsistent with its relation",
    )


def _validate_edge(edge: dict[str, Any]) -> None:
    _validate_expected_target(edge["expected_target"])
    _require(
        edge["expected_target"]["manifest_sha256"] is not None,
        "relationship target manifest hash is required",
    )
    _require(
        edge["expected_target"]["content_sha256"] is not None
        or edge["relation"] == "CORPUS_CONTAINS_OBSERVATION",
        "relationship target content hash is required",
    )
    target_kind = edge["expected_target"]["kind"]
    allowed_kinds = {
        "DIAGNOSIS_SUBJECT": {"OBSERVATION", "REFINEMENT"},
        "REFINEMENT_DIAGNOSIS": {"DIAGNOSIS"},
        "REFINEMENT_BASE": {"OBSERVATION", "REFINEMENT"},
        "REFINEMENT_PARENT": {"REFINEMENT"},
        "CORPUS_CONTAINS_OBSERVATION": {"OBSERVATION"},
        "CORPUS_CONTAINS_DIAGNOSIS": {"DIAGNOSIS"},
        "CORPUS_EXTERNAL_REFINEMENT": {"REFINEMENT"},
    }[edge["relation"]]
    _require(
        target_kind in allowed_kinds,
        "edge relation and expected-target kind are inconsistent",
    )
    _require(
        edge["edge_key"]
        == edge_key(
            relation=edge["relation"],
            from_record_key=edge["from_record_key"],
            expected_target=edge["expected_target"],
        ),
        "edge_key does not match its identity preimage",
    )
    _require(
        (edge["state"] == "MATCH") == (edge["target_record_key"] is not None),
        "edge state and target_record_key are inconsistent",
    )


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
    rules = ruleset["rules"]
    _require(
        [rule["rule_id"] for rule in rules]
        == [f"TCW-D{number:03d}" for number in range(1, 11)],
        "diagnosis rules are not in D001..D010 order",
    )
    _require(
        ruleset["parameter_sha256"]
        == canonical_sha256(
            [
                {
                    "rule_id": rule["rule_id"],
                    "rule_version": rule["version"],
                    "parameters": rule["parameters"],
                }
                for rule in rules
            ]
        ),
        "diagnosis ruleset parameter_sha256 is incorrect",
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


def _relationship_for(
    relationships: list[dict[str, Any]], relation: str
) -> dict[str, Any]:
    matches = [
        edge for edge in relationships if edge["relation"] == relation
    ]
    _require(
        len(matches) == 1,
        f"detail requires exactly one {relation} relationship",
    )
    return matches[0]


def _validate_diagnosis_detail(
    detail: dict[str, Any], relationships: list[dict[str, Any]]
) -> None:
    _validate_expected_target(detail["subject"])
    subject_edge = _relationship_for(relationships, "DIAGNOSIS_SUBJECT")
    _require(
        subject_edge["expected_target"] == detail["subject"],
        "diagnosis subject disagrees with its relationship",
    )
    expected_state = (
        "MATCH" if subject_edge["state"] == "MATCH" else "NOT_CHECKED"
    )
    _require(
        detail["subject_state"] == expected_state,
        "diagnosis subject state disagrees with its relationship",
    )
    _require(
        detail["derivation_state"] == detail["subject_state"],
        "diagnosis derivation state must equal subject presence",
    )
    _validate_finding_collection(
        detail["findings"], detail["ruleset"], detail["summary"]
    )


def _validate_observation_detail(detail: dict[str, Any]) -> None:
    for extractor in detail["extractors"]:
        _require_ordered(
            extractor["artifact_keys"],
            unique=True,
            message="extractor artifact_keys are not ordered and unique",
        )
        failed = extractor["status"] == "FAILED"
        _require(
            failed == (extractor["error"] is not None),
            "extractor status and error are inconsistent",
        )
        if failed:
            _require(
                not extractor["artifact_keys"],
                "failed extractor has artifact keys",
            )
    docling = detail["extractors"][0]
    schema_values = detail["docling_document_schema"].values()
    _require(
        (docling["status"] == "FAILED")
        == all(value is None for value in schema_values),
        "Docling status and schema capture are inconsistent",
    )
    if docling["status"] != "FAILED":
        _require(
            all(value is not None for value in schema_values),
            "successful Docling capture has null schema fields",
        )
    _validate_comparison(detail["comparison"])


def _validate_refinement_detail(
    detail: dict[str, Any], relationships: list[dict[str, Any]]
) -> None:
    _validate_expected_target(detail["diagnosis_target"])
    _validate_expected_target(detail["base_target"])
    if detail["parent_target"] is not None:
        _validate_expected_target(detail["parent_target"])
    diagnosis_edge = _relationship_for(
        relationships, "REFINEMENT_DIAGNOSIS"
    )
    base_edge = _relationship_for(relationships, "REFINEMENT_BASE")
    _require(
        diagnosis_edge["expected_target"] == detail["diagnosis_target"]
        and base_edge["expected_target"] == detail["base_target"],
        "refinement targets disagree with their relationships",
    )
    _require(
        detail["diagnosis_state"]
        == ("MATCH" if diagnosis_edge["state"] == "MATCH" else "NOT_CHECKED")
        and detail["base_state"]
        == ("MATCH" if base_edge["state"] == "MATCH" else "NOT_CHECKED"),
        "refinement relationship states are inconsistent",
    )
    approved = detail["decision"]["state"] == "APPROVED"
    _require(
        approved == bool(detail["transformations"])
        == bool(detail["revision_chain"]),
        "refinement decision and nonempty derivation arrays are inconsistent",
    )
    if not approved:
        _require(
            detail["parent_target"] is None
            and detail["derivation_state"] == "NOT_APPLICABLE"
            and detail["reversibility_state"] == "NOT_APPLICABLE",
            "rejected refinement has applied-only state",
        )
        _require(
            not any(
                edge["relation"] == "REFINEMENT_PARENT"
                for edge in relationships
            ),
            "rejected refinement has a parent relationship",
        )
        return
    transformations = detail["transformations"]
    chain = detail["revision_chain"]
    _require(
        [item["ordinal"] for item in transformations]
        == list(range(len(transformations))),
        "transformation ordinals are not contiguous from zero",
    )
    for previous, current in zip(transformations, transformations[1:]):
        _require(
            previous["after_sha256"] == current["before_sha256"],
            "transformation hashes do not chain",
        )
    for previous, current in zip(chain, chain[1:]):
        _require(
            current["parent_revision_id"] == previous["revision_id"]
            and current["before_sha256"] == previous["after_sha256"],
            "revision IDs or hashes do not chain",
        )
    _require(
        len(transformations) == len(chain)
        and all(
            transformation["before_sha256"] == revision["before_sha256"]
            and transformation["after_sha256"] == revision["after_sha256"]
            and transformation["refiner"] == revision["refiner"]
            for transformation, revision in zip(transformations, chain)
        ),
        "transformations and revision_chain disagree",
    )
    _require(
        transformations[0]["before_sha256"]
        == detail["base_target"]["content_sha256"],
        "first transformation does not start at the base content hash",
    )
    evaluation_state = (
        "MATCH"
        if detail["diagnosis_state"] == detail["base_state"] == "MATCH"
        else "NOT_CHECKED"
    )
    _require(
        detail["derivation_state"] == evaluation_state
        and detail["reversibility_state"] == evaluation_state,
        "applied refinement evaluation states disagree with target presence",
    )
    if detail["base_target"]["kind"] == "OBSERVATION":
        _require(
            detail["parent_target"] is None
            and chain[0]["parent_revision_id"] is None,
            "observation-based refinement has a parent revision",
        )
        _require(
            not any(
                edge["relation"] == "REFINEMENT_PARENT"
                for edge in relationships
            ),
            "observation-based refinement has a parent relationship",
        )
    else:
        parent = detail["parent_target"]
        _require(
            parent is not None
            and parent == detail["base_target"]
            and chain[0]["parent_revision_id"] == parent["identity_value"],
            "revision-based refinement does not identify its parent",
        )
        parent_edge = _relationship_for(
            relationships, "REFINEMENT_PARENT"
        )
        _require(
            parent_edge["expected_target"] == parent,
            "refinement parent disagrees with its relationship",
        )


def _validate_named_counts(
    groups: Iterable[dict[str, Any]], member_count: int
) -> None:
    for counts in groups:
        _require(
            counts["member_count"]
            == counts["complete"] + counts["partial"] + counts["failed"],
            "named corpus counts do not sum",
        )
        _require(
            counts["member_count"] <= member_count,
            "named corpus count exceeds corpus total",
        )


def _validate_corpus_detail(
    detail: dict[str, Any], relationships: list[dict[str, Any]]
) -> None:
    totals = detail["summary"]["totals"]
    matrix = detail["matrix"]
    _require(
        totals["member_count"] == len(matrix)
        == totals["complete"] + totals["partial"] + totals["failed"],
        "corpus totals do not match the matrix",
    )
    status_counts = Counter(item["status"].lower() for item in matrix)
    _require(
        all(totals[name] == status_counts[name] for name in status_counts),
        "corpus status totals do not match matrix rows",
    )
    _require_ordered(
        matrix,
        key=lambda item: item["member_id"],
        unique=True,
        message="corpus matrix is not ordered and unique by member_id",
    )
    aggregates = detail["aggregates"]
    _require_ordered(
        aggregates["by_family"],
        key=lambda item: item["name"],
        unique=True,
        message="family counts are not ordered and unique",
    )
    format_order = {"pdf": 0, "docx": 1, "md": 2, "txt": 3}
    _require(
        aggregates["by_format"]
        == sorted(
            aggregates["by_format"],
            key=lambda item: format_order[item["name"]],
        ),
        "format counts are not in pdf/docx/md/txt order",
    )
    _require(
        len({item["name"] for item in aggregates["by_format"]})
        == len(aggregates["by_format"]),
        "format counts are not unique",
    )
    _validate_named_counts(
        [*aggregates["by_family"], *aggregates["by_format"]],
        totals["member_count"],
    )
    _require(
        sum(item["member_count"] for item in aggregates["by_family"])
        == totals["member_count"]
        and sum(item["member_count"] for item in aggregates["by_format"])
        == totals["member_count"],
        "corpus named groups do not partition members",
    )
    _require(
        [item["name"] for item in aggregates["extractors"]]
        == ["docling", "markitdown"],
        "extractor counts are not in canonical order",
    )
    for counts in aggregates["extractors"]:
        _require(
            counts["available"] + counts["unavailable"]
            == totals["member_count"],
            "extractor availability does not sum to corpus members",
        )
    _require_ordered(
        aggregates["comparisons"],
        key=lambda item: item["member_id"],
        unique=True,
        message="corpus comparisons are not ordered and unique",
    )
    for comparison in aggregates["comparisons"]:
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
            aggregates[name],
            key=key,
            unique=True,
            message=f"corpus {name} are not in semantic order",
        )
    for finding_group in aggregates["findings"]:
        _require(
            finding_group["affected_member_count"]
            <= finding_group["finding_count"],
            "affected member count exceeds finding count",
        )
    _require(
        totals["finding_count"]
        == sum(item["finding_count"] for item in aggregates["findings"]),
        "corpus finding total does not match finding groups",
    )
    _require(
        totals["revision_count"]
        == len(aggregates["revisions"])
        == sum(
            item["revision_count"]
            for item in aggregates["revision_groups"]
        ),
        "corpus revision total does not match revision aggregates",
    )
    contained = sorted(
        {
            key
            for item in matrix
            for key in (
                item["observation_record_key"],
                item["diagnosis_record_key"],
            )
            if key is not None
        }
    )
    _require(
        detail["contained_record_keys"] == contained,
        "contained_record_keys do not match the matrix",
    )
    containment_edges = [
        edge
        for edge in relationships
        if edge["relation"]
        in {
            "CORPUS_CONTAINS_OBSERVATION",
            "CORPUS_CONTAINS_DIAGNOSIS",
        }
    ]
    _require(
        all(
            edge["state"] == "MATCH"
            and edge["target_record_key"] is not None
            for edge in containment_edges
        )
        and sorted(edge["target_record_key"] for edge in containment_edges)
        == contained,
        "corpus matrix keys do not match containment relationships",
    )
    rows_by_observation_key = {
        row["observation_record_key"]: row
        for row in matrix
        if row["observation_record_key"] is not None
    }
    for edge in containment_edges:
        if edge["expected_target"]["content_sha256"] is not None:
            continue
        row = rows_by_observation_key.get(edge["target_record_key"])
        _require(
            edge["relation"] == "CORPUS_CONTAINS_OBSERVATION"
            and row is not None
            and row["status"] in {"PARTIAL", "FAILED"},
            "null corpus-observation content hash is not a partial/failed case",
        )
    for row in matrix:
        complete = row["status"] == "COMPLETE"
        _require(
            complete == (row["error"] is None),
            "corpus row status and error are inconsistent",
        )
        if complete:
            _require(
                row["observation_record_key"] is not None
                and row["diagnosis_record_key"] is not None,
                "complete corpus row lacks record keys",
            )
        if row["status"] == "FAILED":
            _require(
                row["diagnosis_record_key"] is None,
                "failed corpus row has a diagnosis key",
            )
    for external in detail["external_revisions"]:
        _require(
            external["member_id"] == external["revision"]["member_id"]
            and external["prepared_document_sha256"]
            == external["revision"]["after_document_sha256"],
            "external revision fields disagree",
        )
        _require(
            (external["relationship_state"] == "MATCH")
            == (external["record_key"] is not None),
            "external revision state and record_key disagree",
        )
        matching_edges = [
            edge
            for edge in relationships
            if edge["relation"] == "CORPUS_EXTERNAL_REFINEMENT"
            and edge["expected_target"]["identity_value"]
            == external["revision"]["revision_id"]
            and edge["expected_target"]["run_id"]
            == external["refinement_run_id"]
        ]
        _require(
            len(matching_edges) == 1
            and matching_edges[0]["state"]
            == external["relationship_state"]
            and matching_edges[0]["target_record_key"]
            == external["record_key"],
            "external revision does not match its relationship edge",
        )
    _require_ordered(
        detail["external_revisions"],
        key=lambda item: (
            item["member_id"],
            item["revision"]["chain_length"],
            item["revision"]["revision_id"],
        ),
        message="external revisions are not in semantic order",
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


def _validate_projection(document: dict[str, Any]) -> None:
    records = document["records"]
    edges = document["edges"]
    counts = document["counts"]
    _require(
        counts["record_count"] == len(records)
        == counts["top_level_record_count"]
        + counts["contained_record_count"],
        "projection counts do not match records",
    )
    _require(
        counts["top_level_record_count"]
        == sum(
            record["admission_origin"] == "TOP_LEVEL" for record in records
        )
        and counts["contained_record_count"]
        == sum(
            record["admission_origin"] == "CORPUS_CONTAINED"
            for record in records
        ),
        "projection admission-origin counts do not match records",
    )
    _require_ordered(
        records,
        key=lambda item: item["record_key"],
        unique=True,
        message="projection records are not ordered and unique",
    )
    _require_ordered(
        edges,
        key=lambda item: item["edge_key"],
        unique=True,
        message="projection edges are not ordered and unique",
    )
    for record in records:
        expected = record_key(
            kind=record["kind"],
            record_schema_version=record["record_schema_version"],
            identity=record["identity"],
            run_id=record["run_id"],
            manifest_sha256=record["manifest"]["sha256"],
        )
        _require(
            record["record_key"] == expected,
            "record_key does not match its identity preimage",
        )
        _validate_descriptor(record["manifest"], record["record_key"])
        _validate_root_manifest(record["kind"], record["manifest"])
        _require_ordered(
            record["contained_by"],
            unique=True,
            message="contained_by is not ordered and unique",
        )
        _require(
            record["admission_origin"] != "CORPUS_CONTAINED"
            or bool(record["contained_by"]),
            "corpus-contained record has no containing corpus",
        )
        if record["kind"] == "REFINEMENT":
            _require(
                (record["status"] == "APPLIED")
                == (record["identity"]["revision_id"] is not None),
                "refinement status and revision_id are inconsistent",
            )
    records_by_key = {
        record["record_key"]: record for record in records
    }
    for edge in edges:
        _validate_edge(edge)
        source = records_by_key.get(edge["from_record_key"])
        _require(
            source is not None,
            "relationship source is absent from projection",
        )
        _validate_edge_source(edge, source["kind"])
        target_key = edge["target_record_key"]
        if edge["state"] == "MATCH":
            _require(
                target_key in records_by_key,
                "matching relationship target is absent from projection",
            )
            target = records_by_key[target_key]
            expected = edge["expected_target"]
            _require(
                target["kind"] == expected["kind"]
                and target["record_schema_version"]
                == expected["record_schema_version"]
                and target["run_id"] == expected["run_id"]
                and target["manifest"]["sha256"]
                == expected["manifest_sha256"]
                and target["identity"].get(expected["identity_type"])
                == expected["identity_value"],
                "matching relationship target does not match its expectation",
            )
            _require(
                expected["content_sha256"] is not None
                or (
                    edge["relation"] == "CORPUS_CONTAINS_OBSERVATION"
                    and target["kind"] == "OBSERVATION"
                    and target["status"] in {"PARTIAL_SUCCESS", "FAILED"}
                ),
                "null relationship content hash is not an allowed observation case",
            )
        else:
            expected = edge["expected_target"]
            _require(
                not any(
                    record["kind"] == expected["kind"]
                    and record["record_schema_version"]
                    == expected["record_schema_version"]
                    and record["run_id"] == expected["run_id"]
                    and record["identity"].get(expected["identity_type"])
                    == expected["identity_value"]
                    for record in records
                ),
                "missing relationship has a projection identity candidate",
            )
    containment_relations = {
        "CORPUS_CONTAINS_OBSERVATION",
        "CORPUS_CONTAINS_DIAGNOSIS",
    }
    containment_by_target: dict[str, list[str]] = {}
    for edge in edges:
        if edge["relation"] not in containment_relations:
            continue
        source = records_by_key.get(edge["from_record_key"])
        target_key = edge["target_record_key"]
        _require(
            edge["state"] == "MATCH"
            and source is not None
            and source["kind"] == "CORPUS"
            and target_key is not None,
            "containment edge does not resolve from a projected corpus",
        )
        containment_by_target.setdefault(target_key, []).append(
            edge["from_record_key"]
        )
    for record in records:
        _require(
            record["contained_by"]
            == sorted(containment_by_target.get(record["record_key"], [])),
            "contained_by does not match containment-edge provenance",
        )
    _require(
        document["session_id"]
        == session_id(
            top_level_record_keys=[
                record["record_key"]
                for record in records
                if record["admission_origin"] == "TOP_LEVEL"
            ],
            contained_record_keys=[
                record["record_key"]
                for record in records
                if record["admission_origin"] == "CORPUS_CONTAINED"
            ],
            edge_keys=[edge["edge_key"] for edge in edges],
        ),
        "session_id does not match its identity preimage",
    )


def _validate_record_detail(document: dict[str, Any]) -> None:
    _validate_descriptor(document["manifest"], document["record_key"])
    _validate_root_manifest(document["kind"], document["manifest"])
    _require_ordered(
        document["artifacts"],
        key=lambda item: item["artifact_key"],
        unique=True,
        message="detail artifacts are not ordered and unique",
    )
    for descriptor in document["artifacts"]:
        _validate_descriptor(descriptor, document["record_key"])
        _require(
            descriptor["origin"] == "MANIFEST_LISTED",
            "detail artifacts include a root descriptor",
        )
    union_descriptors = [document["manifest"], *document["artifacts"]]
    _require(
        len(
            {
                descriptor["artifact_key"]
                for descriptor in union_descriptors
            }
        )
        == len(union_descriptors)
        and len(
            {
                (descriptor["relative_path"], descriptor["role"])
                for descriptor in union_descriptors
            }
        )
        == len(union_descriptors)
        and len(
            {
                descriptor["relative_path"]
                for descriptor in union_descriptors
            }
        )
        == len(union_descriptors),
        "record artifact union violates key or path-role uniqueness",
    )
    _require_ordered(
        document["relationships"],
        key=lambda item: item["edge_key"],
        unique=True,
        message="detail relationships are not ordered and unique",
    )
    for edge in document["relationships"]:
        _validate_edge(edge)
        _require(
            edge["from_record_key"] == document["record_key"],
            "detail relationship belongs to another record",
        )
        _validate_edge_source(edge, document["kind"])
    detail = document["detail"]
    if document["kind"] == "OBSERVATION":
        _validate_observation_detail(detail)
    elif document["kind"] == "DIAGNOSIS":
        _validate_diagnosis_detail(detail, document["relationships"])
    elif document["kind"] == "REFINEMENT":
        _validate_refinement_detail(detail, document["relationships"])
    else:
        _validate_corpus_detail(detail, document["relationships"])


def validate_semantics(
    schema_version: str, document: dict[str, Any]
) -> None:
    """Validate equations and ordering that Draft 2020-12 cannot express."""

    if schema_version == "tcw.workbench-startup/v0.5":
        _require(
            document["record_count"]
            == document["top_level_record_count"]
            + document["contained_record_count"],
            "startup counts do not sum",
        )
    elif schema_version == "tcw.workbench-projection/v0.5":
        _validate_projection(document)
    elif schema_version == "tcw.workbench-record-detail/v0.5":
        _validate_record_detail(document)
    elif schema_version == "tcw.finding-set/v0.5":
        _validate_finding_collection(
            document["findings"],
            document["ruleset"],
            document["summary"],
        )
    elif schema_version == "tcw.comparison-summary/v0.5":
        _validate_comparison(document)
    elif schema_version == "tcw.corpus-summary/v0.5":
        _validate_corpus_summary(document)
