"""Deterministic v0.5 workbench projection and record-detail serialization."""

from __future__ import annotations

import copy
import hashlib
import json
import tempfile
from contextlib import contextmanager
from dataclasses import dataclass
from pathlib import Path, PurePosixPath
from typing import Any, Iterator, Sequence

from tiny_corpus_workbench.canonical_json import canonical_json, edge_key, session_id
from tiny_corpus_workbench.diagnosis_rules import RULESET, RULESET_PARAMETER_HASH
from tiny_corpus_workbench.domain import IntegrityError
from tiny_corpus_workbench.schema_catalog import validate_document
from tiny_corpus_workbench.supported_provenance import active_build_provenance
from tiny_corpus_workbench.v03 import verify_diagnosis, verify_refinement
from tiny_corpus_workbench.workbench_records import (
    MAX_STRUCTURED_RESPONSE,
    AdmittedRecord,
    AdmittedRecords,
)


SCHEMAS = {
    "OBSERVATION": "tcw.preparation-manifest/v0.5",
    "DIAGNOSIS": "tcw.diagnosis-manifest/v0.5",
    "REFINEMENT": "tcw.refinement-manifest/v0.5",
    "CORPUS": "tcw.corpus-manifest/v0.5",
}


@dataclass(frozen=True)
class WorkbenchProjection:
    projection: dict[str, Any]
    details: dict[str, dict[str, Any]]

    def projection_bytes(self) -> bytes:
        return canonical_json(self.projection)

    def detail_bytes(self, record_key: str) -> bytes:
        return canonical_json(self.details[record_key])


def _snapshot_relative_path(value: object) -> PurePosixPath:
    if (
        not isinstance(value, str)
        or not value
        or "\\" in value
        or "\x00" in value
    ):
        raise IntegrityError("frozen artifact reference is unsafe")
    relative = PurePosixPath(value)
    if (
        relative.is_absolute()
        or relative.as_posix() != value
        or any(part in {"", ".", ".."} for part in relative.parts)
    ):
        raise IntegrityError("frozen artifact reference is unsafe")
    return relative


def _frozen_file_bytes(
    record: AdmittedRecord, descriptor: dict[str, Any]
) -> bytes:
    if descriptor["origin"] == "ROOT_MANIFEST":
        if descriptor["relative_path"] != record.manifest_name:
            raise IntegrityError("frozen root manifest descriptor differs")
        raw = record.manifest_bytes
    elif descriptor["origin"] == "MANIFEST_LISTED":
        key = (
            descriptor["role"],
            descriptor["relative_path"],
            descriptor["sha256"],
        )
        try:
            raw = record.artifact_bytes[key]
        except KeyError as error:
            raise IntegrityError(
                "frozen authorized artifact is unavailable"
            ) from error
    else:
        raise IntegrityError("frozen artifact origin is invalid")
    if (
        len(raw) != descriptor["size"]
        or hashlib.sha256(raw).hexdigest() != descriptor["sha256"]
    ):
        raise IntegrityError("frozen authorized artifact differs")
    return raw


@contextmanager
def _frozen_verifier_roots(
    records: Sequence[AdmittedRecord],
) -> Iterator[tuple[Path, ...]]:
    """Materialize private verifier inputs from admitted bytes only."""

    with tempfile.TemporaryDirectory(prefix="tcw-workbench-replay-") as temporary:
        snapshot = Path(temporary)
        roots: list[Path] = []
        for index, record in enumerate(records):
            run_component = _snapshot_relative_path(record.run_id)
            if len(run_component.parts) != 1:
                raise IntegrityError("frozen record run_id is unsafe")
            root = snapshot / str(index) / run_component.name
            root.mkdir(parents=True)
            manifest, listed = record.descriptors()
            descriptors = [manifest, *listed]
            if len({item["relative_path"] for item in descriptors}) != len(
                descriptors
            ):
                raise IntegrityError("frozen artifact paths are not unique")
            for descriptor in descriptors:
                relative = _snapshot_relative_path(descriptor["relative_path"])
                destination = root.joinpath(*relative.parts)
                try:
                    destination.parent.mkdir(parents=True, exist_ok=True)
                    if destination.exists() or destination.is_symlink():
                        raise IntegrityError(
                            "frozen artifact snapshot path conflicts"
                        )
                    destination.write_bytes(
                        _frozen_file_bytes(record, descriptor)
                    )
                except OSError as error:
                    raise IntegrityError(
                        "frozen artifact snapshot could not be materialized"
                    ) from error
            roots.append(root)
        yield tuple(roots)


def _verify_diagnosis_frozen(
    diagnosis: AdmittedRecord, subject: AdmittedRecord
) -> dict[str, Any]:
    with _frozen_verifier_roots((diagnosis, subject)) as roots:
        return verify_diagnosis(roots[0], roots[1])


def _verify_refinement_frozen(
    refinement: AdmittedRecord,
    diagnosis: AdmittedRecord | None,
    base: AdmittedRecord | None,
) -> dict[str, Any]:
    inputs = [
        record for record in (refinement, diagnosis, base) if record is not None
    ]
    with _frozen_verifier_roots(inputs) as roots:
        by_record = {
            id(record): root for record, root in zip(inputs, roots, strict=True)
        }
        return verify_refinement(
            by_record[id(refinement)],
            by_record[id(diagnosis)] if diagnosis is not None else None,
            by_record[id(base)] if base is not None else None,
        )


def _target(
    *,
    kind: str,
    identity_type: str,
    identity_value: str,
    run_id: str,
    manifest_sha256: str | None,
    content_sha256: str | None,
) -> dict[str, Any]:
    return {
        "kind": kind,
        "record_schema_version": SCHEMAS[kind],
        "identity_type": identity_type,
        "identity_value": identity_value,
        "run_id": run_id,
        "manifest_sha256": manifest_sha256,
        "content_sha256": content_sha256,
    }


def _candidate(records: AdmittedRecords, target: dict[str, Any]) -> AdmittedRecord | None:
    matches = [
        record
        for record in records.records.values()
        if record.kind == target["kind"]
        and record.schema_version == target["record_schema_version"]
        and record.run_id == target["run_id"]
        and record.identity.get(target["identity_type"]) == target["identity_value"]
    ]
    if len(matches) > 1:
        raise IntegrityError("relationship target is ambiguous")
    if not matches:
        return None
    match = matches[0]
    if target["manifest_sha256"] not in (None, match.manifest_sha256):
        raise IntegrityError("relationship target manifest differs")
    if target["content_sha256"] not in (None, match.content_sha256):
        raise IntegrityError("relationship target content differs")
    return match


def _edge(
    records: AdmittedRecords,
    source: AdmittedRecord,
    relation: str,
    target: dict[str, Any],
    *,
    required: AdmittedRecord | None = None,
) -> dict[str, Any]:
    candidate = required or _candidate(records, target)
    state = "MATCH" if candidate is not None else "MISSING"
    return {
        "edge_key": edge_key(
            relation=relation,
            from_record_key=source.record_key,
            expected_target=target,
        ),
        "relation": relation,
        "from_record_key": source.record_key,
        "expected_target": target,
        "target_record_key": candidate.record_key if candidate else None,
        "state": state,
    }


def _record_edges(records: AdmittedRecords, record: AdmittedRecord) -> list[dict[str, Any]]:
    manifest = record.manifest
    result: list[dict[str, Any]] = []
    if record.kind == "DIAGNOSIS":
        value = manifest["subject"]
        result.append(
            _edge(
                records,
                record,
                "DIAGNOSIS_SUBJECT",
                _target(
                    kind=value["kind"],
                    identity_type=value["identity_type"],
                    identity_value=value["identity_value"],
                    run_id=value["run_id"],
                    manifest_sha256=value["manifest_sha256"],
                    content_sha256=value["canonical_document_sha256"],
                ),
            )
        )
        target_record = _candidate(records, result[-1]["expected_target"])
        if target_record is not None:
            checked = _verify_diagnosis_frozen(record, target_record)
            if (
                checked["artifact_integrity"]["status"] != "VERIFIED"
                or checked["subject_state"]["status"] != "MATCH"
                or checked["derivation_state"]["status"] != "MATCH"
            ):
                raise IntegrityError("diagnosis relationship evaluation failed")
    elif record.kind == "REFINEMENT":
        diagnosis = manifest["diagnosis"]
        result.append(
            _edge(
                records,
                record,
                "REFINEMENT_DIAGNOSIS",
                _target(
                    kind="DIAGNOSIS",
                    identity_type="diagnosis_id",
                    identity_value=diagnosis["diagnosis_id"],
                    run_id=diagnosis["run_id"],
                    manifest_sha256=diagnosis["diagnosis_manifest_sha256"],
                    content_sha256=diagnosis["findings_artifact_sha256"],
                ),
            )
        )
        base = manifest["base"]
        result.append(
            _edge(
                records,
                record,
                "REFINEMENT_BASE",
                _target(
                    kind=base["kind"],
                    identity_type=base["identity_type"],
                    identity_value=base["identity_value"],
                    run_id=base["run_id"],
                    manifest_sha256=base["base_manifest_sha256"],
                    content_sha256=base["canonical_document_sha256"],
                ),
            )
        )
        if manifest["parent"] is not None:
            parent = manifest["parent"]
            result.append(
                _edge(
                    records,
                    record,
                    "REFINEMENT_PARENT",
                    _target(
                        kind="REFINEMENT",
                        identity_type="revision_id",
                        identity_value=parent["revision_id"],
                        run_id=parent["run_id"],
                        manifest_sha256=parent["refinement_manifest_sha256"],
                        content_sha256=parent["prepared_document_sha256"],
                    ),
                )
            )
        by_relation = {item["relation"]: item for item in result}
        diagnosis_record = _candidate(
            records, by_relation["REFINEMENT_DIAGNOSIS"]["expected_target"]
        )
        base_record = _candidate(
            records, by_relation["REFINEMENT_BASE"]["expected_target"]
        )
        if diagnosis_record is not None:
            diagnosis_checked = _verify_refinement_frozen(
                record, diagnosis_record, None
            )
            if (
                diagnosis_checked["artifact_integrity"]["status"] != "VERIFIED"
                or diagnosis_checked["diagnosis_state"]["status"] != "MATCH"
            ):
                raise IntegrityError(
                    "refinement diagnosis relationship evaluation failed"
                )
        if base_record is not None:
            base_checked = _verify_refinement_frozen(
                record, None, base_record
            )
            if (
                base_checked["artifact_integrity"]["status"] != "VERIFIED"
                or base_checked["base_state"]["status"] != "MATCH"
            ):
                raise IntegrityError(
                    "refinement base relationship evaluation failed"
                )
        if diagnosis_record is not None and base_record is not None:
            checked = _verify_refinement_frozen(
                record, diagnosis_record, base_record
            )
            expected = "MATCH" if manifest["status"] == "APPLIED" else "NOT_APPLICABLE"
            if (
                checked["artifact_integrity"]["status"] != "VERIFIED"
                or checked["diagnosis_state"]["status"] != "MATCH"
                or checked["base_state"]["status"] != "MATCH"
                or checked["derivation_state"]["status"] != expected
                or checked["reversibility_state"]["status"] != expected
            ):
                raise IntegrityError("refinement relationship evaluation failed")
    elif record.kind == "CORPUS":
        by_member = {
            (member_id, relation): target_key
            for source_key, target_key, relation, member_id in records.containment
            if source_key == record.record_key
        }
        for member in sorted(manifest["members"], key=lambda value: value["member_id"]):
            for stage, relation, kind, identity_type, content_field in (
                ("observation", "CORPUS_CONTAINS_OBSERVATION", "OBSERVATION", "observation_id", "canonical_document_sha256"),
                ("diagnosis", "CORPUS_CONTAINS_DIAGNOSIS", "DIAGNOSIS", "diagnosis_id", "findings_sha256"),
            ):
                value = member[stage]
                if value["manifest"] is None:
                    continue
                target_record = next(
                    candidate
                    for candidate in records.records.values()
                    if candidate.record_key
                    == by_member[(member["member_id"], relation)]
                    and candidate.kind == kind
                    and candidate.run_id == value["run_id"]
                    and candidate.identity[identity_type] == value[identity_type]
                )
                if stage == "diagnosis":
                    observation_key = by_member.get(
                        (member["member_id"], "CORPUS_CONTAINS_OBSERVATION")
                    )
                    if observation_key is None:
                        raise IntegrityError(
                            "contained diagnosis lacks its member observation"
                        )
                    checked = _verify_diagnosis_frozen(
                        target_record, records.records[observation_key]
                    )
                    if (
                        checked["artifact_integrity"]["status"] != "VERIFIED"
                        or checked["subject_state"]["status"] != "MATCH"
                        or checked["derivation_state"]["status"] != "MATCH"
                    ):
                        raise IntegrityError(
                            "contained diagnosis relationship evaluation failed"
                        )
                result.append(
                    _edge(
                        records,
                        record,
                        relation,
                        _target(
                            kind=kind,
                            identity_type=identity_type,
                            identity_value=value[identity_type],
                            run_id=value["run_id"],
                            manifest_sha256=value["manifest"]["sha256"],
                            content_sha256=value[content_field],
                        ),
                        required=target_record,
                    )
                )
        for revision in manifest["revisions"]:
            target = _target(
                kind="REFINEMENT",
                identity_type="revision_id",
                identity_value=revision["revision_id"],
                run_id=revision["refinement_run_id"],
                manifest_sha256=revision["refinement_manifest_sha256"],
                content_sha256=revision["prepared_document_sha256"],
            )
            result.append(_edge(records, record, "CORPUS_EXTERNAL_REFINEMENT", target))
    return sorted(result, key=lambda value: value["edge_key"])


def _node(record: AdmittedRecord) -> dict[str, Any]:
    manifest_descriptor, artifacts = record.descriptors()
    return {
        "record_key": record.record_key,
        "kind": record.kind,
        "record_schema_version": record.schema_version,
        "run_id": record.run_id,
        "identity": copy.deepcopy(record.identity),
        "admission_origin": "TOP_LEVEL" if record.top_level else "CORPUS_CONTAINED",
        "contained_by": sorted(record.contained_by),
        "status": record.status,
        "artifact_integrity": "VERIFIED",
        "manifest": manifest_descriptor,
        "artifact_count": 1 + len(artifacts),
    }


def _artifact_json(record: AdmittedRecord, role: str) -> dict[str, Any]:
    raw = record.read_artifact(role)
    try:
        value = json.loads(raw.decode("utf-8"))
    except (UnicodeError, json.JSONDecodeError) as error:
        raise IntegrityError("frozen authorized artifact is not valid JSON") from error
    if not isinstance(value, dict):
        raise IntegrityError("frozen authorized artifact root is not an object")
    return value


def _observation_detail(record: AdmittedRecord) -> dict[str, Any]:
    manifest = record.manifest
    descriptors = {item["role"]: item for item in record.descriptors()[1]}
    comparison = _artifact_json(record, "comparison-summary")
    extractors = []
    for extractor in manifest["extractors"]:
        keys = sorted(
            descriptors[item["role"]]["artifact_key"]
            for item in extractor["artifacts"]
        )
        extractors.append(
            {
                "name": extractor["name"],
                "version": extractor["version"],
                "status": extractor["status"],
                "upstream_status": extractor["upstream_status"],
                "artifact_keys": keys,
                "error": copy.deepcopy(extractor["error"]),
            }
        )
    return {
        "source": copy.deepcopy(manifest["source"]),
        "docling_document_schema": copy.deepcopy(manifest["docling_document_schema"]),
        "extractors": extractors,
        "comparison": {
            "status": comparison["status"],
            "normalization_algorithm": comparison["normalization_algorithm"],
            "views": copy.deepcopy(comparison["views"]),
            "docling_minus_markitdown": copy.deepcopy(comparison["deltas"]),
        },
    }


def _diagnosis_detail(
    record: AdmittedRecord, edges: list[dict[str, Any]]
) -> dict[str, Any]:
    manifest = record.manifest
    findings = _artifact_json(record, "diagnostic-findings")
    state = edges[0]["state"]
    return {
        "source": copy.deepcopy(manifest["source"]),
        "subject": copy.deepcopy(edges[0]["expected_target"]),
        "subject_state": "MATCH" if state == "MATCH" else "NOT_CHECKED",
        "derivation_state": "MATCH" if state == "MATCH" else "NOT_CHECKED",
        "ruleset": copy.deepcopy(manifest["ruleset"]),
        "summary": copy.deepcopy(manifest["summary"]),
        "findings": sorted(copy.deepcopy(findings["findings"]), key=lambda value: value["finding_id"]),
    }


def _refinement_detail(
    record: AdmittedRecord, edges: list[dict[str, Any]]
) -> dict[str, Any]:
    manifest = record.manifest
    by_relation = {item["relation"]: item for item in edges}
    decision_file = _artifact_json(record, "refinement-decision")
    approved = manifest["status"] == "APPLIED"
    both = (
        by_relation["REFINEMENT_DIAGNOSIS"]["state"] == "MATCH"
        and by_relation["REFINEMENT_BASE"]["state"] == "MATCH"
    )
    transformations: list[dict[str, Any]] = []
    chain: list[dict[str, Any]] = []
    if approved:
        transformation = _artifact_json(record, "transformation")
        history = _artifact_json(record, "transformation-history")
        transformations = [
            {
                "ordinal": ordinal,
                "refiner": copy.deepcopy(item["refiner"]),
                "before_sha256": item["parent"][
                    "canonical_document_sha256"
                ],
                "after_sha256": item["prepared_document_sha256"],
                "affected_reference_count": len(item["affected_refs"]),
            }
            for ordinal, item in enumerate(history["transformations"])
        ]
        chain = [
            {
                "revision_id": item["revision_id"],
                "parent_revision_id": (
                    item["parent"]["subject_id"]
                    if item["parent"]["kind"] == "REVISION"
                    else None
                ),
                "refiner": copy.deepcopy(item["refiner"]),
                "before_sha256": item["parent"]["canonical_document_sha256"],
                "after_sha256": item["prepared_document_sha256"],
            }
            for item in history["transformations"]
        ]
    state = "MATCH" if both else "NOT_CHECKED"
    return {
        "source": copy.deepcopy(manifest["source"]),
        "diagnosis_target": copy.deepcopy(by_relation["REFINEMENT_DIAGNOSIS"]["expected_target"]),
        "base_target": copy.deepcopy(by_relation["REFINEMENT_BASE"]["expected_target"]),
        "parent_target": (
            copy.deepcopy(by_relation["REFINEMENT_PARENT"]["expected_target"])
            if "REFINEMENT_PARENT" in by_relation
            else None
        ),
        "decision": {
            "draft_id": manifest["draft_id"],
            **copy.deepcopy(decision_file["decision"]),
        },
        "diagnosis_state": (
            "MATCH" if by_relation["REFINEMENT_DIAGNOSIS"]["state"] == "MATCH" else "NOT_CHECKED"
        ),
        "base_state": (
            "MATCH" if by_relation["REFINEMENT_BASE"]["state"] == "MATCH" else "NOT_CHECKED"
        ),
        "derivation_state": state if approved else "NOT_APPLICABLE",
        "reversibility_state": state if approved else "NOT_APPLICABLE",
        "transformations": transformations,
        "revision_chain": chain,
    }


def _corpus_detail(
    records: AdmittedRecords, record: AdmittedRecord, edges: list[dict[str, Any]]
) -> dict[str, Any]:
    manifest = record.manifest
    summary = _artifact_json(record, "corpus-summary")
    containment = {
        (edge["relation"], edge["expected_target"]["run_id"]): edge["target_record_key"]
        for edge in edges
        if edge["relation"].startswith("CORPUS_CONTAINS_")
    }
    matrix = []
    for member in sorted(manifest["members"], key=lambda value: value["member_id"]):
        matrix.append(
            {
                "member_id": member["member_id"],
                "family": member["family"],
                "format": member["format"],
                "status": member["status"],
                "source": copy.deepcopy(member["source"]),
                "observation_record_key": (
                    containment.get(("CORPUS_CONTAINS_OBSERVATION", member["observation"]["run_id"]))
                    if member["observation"]["manifest"] is not None
                    else None
                ),
                "diagnosis_record_key": (
                    containment.get(("CORPUS_CONTAINS_DIAGNOSIS", member["diagnosis"]["run_id"]))
                    if member["diagnosis"]["manifest"] is not None
                    else None
                ),
                "error": copy.deepcopy(member["error"]),
            }
        )
    external_edges = {
        edge["expected_target"]["identity_value"]: edge
        for edge in edges
        if edge["relation"] == "CORPUS_EXTERNAL_REFINEMENT"
    }
    external = []
    summary_revisions = {
        item["revision_id"]: item for item in summary["revisions"]
    }
    for revision in sorted(
        manifest["revisions"],
        key=lambda value: (value["member_id"], value["chain_length"], value["revision_id"]),
    ):
        edge = external_edges[revision["revision_id"]]
        external.append(
            {
                "member_id": revision["member_id"],
                "revision": copy.deepcopy(summary_revisions[revision["revision_id"]]),
                "refinement_run_id": revision["refinement_run_id"],
                "refinement_manifest_sha256": revision["refinement_manifest_sha256"],
                "prepared_document_sha256": revision["prepared_document_sha256"],
                "relationship_state": edge["state"],
                "record_key": edge["target_record_key"],
            }
        )
    return {
        "corpus_id": manifest["corpus_id"],
        "snapshot_id": manifest["snapshot_id"],
        "summary": {"status": summary["status"], "totals": copy.deepcopy(summary["totals"])},
        "contained_record_keys": sorted(
            {
                value
                for row in matrix
                for value in (row["observation_record_key"], row["diagnosis_record_key"])
                if value is not None
            }
        ),
        "matrix": matrix,
        "aggregates": {
            "by_family": sorted(
                copy.deepcopy(summary["by_family"]), key=lambda value: value["name"]
            ),
            "by_format": sorted(
                copy.deepcopy(summary["by_format"]),
                key=lambda value: ("pdf", "docx", "md", "txt").index(value["name"]),
            ),
            "extractors": sorted(
                copy.deepcopy(summary["extractors"]),
                key=lambda value: ("docling", "markitdown").index(value["name"]),
            ),
            "comparisons": sorted(
                copy.deepcopy(summary["comparisons"]),
                key=lambda value: value["member_id"],
            ),
            "findings": sorted(
                copy.deepcopy(summary["findings"]),
                key=lambda value: (
                    value["rule_id"],
                    value["severity"],
                    value["family"],
                    value["format"],
                ),
            ),
            "revision_groups": sorted(
                copy.deepcopy(summary["revision_groups"]),
                key=lambda value: (
                    value["family"],
                    value["format"],
                    value["finding_rule"],
                    value["refiner_id"],
                ),
            ),
            "revisions": sorted(
                copy.deepcopy(summary["revisions"]),
                key=lambda value: (
                    value["member_id"],
                    value["chain_length"],
                    value["revision_id"],
                ),
            ),
        },
        "external_revisions": external,
    }


def _detail(
    records: AdmittedRecords, record: AdmittedRecord, edges: list[dict[str, Any]]
) -> dict[str, Any]:
    manifest_descriptor, artifacts = record.descriptors()
    if record.kind == "OBSERVATION":
        kind_detail = _observation_detail(record)
    elif record.kind == "DIAGNOSIS":
        kind_detail = _diagnosis_detail(record, edges)
    elif record.kind == "REFINEMENT":
        kind_detail = _refinement_detail(record, edges)
    else:
        kind_detail = _corpus_detail(records, record, edges)
    return {
        "schema_version": "tcw.workbench-record-detail/v0.5",
        "record_key": record.record_key,
        "kind": record.kind,
        "artifact_integrity": "VERIFIED",
        "manifest": manifest_descriptor,
        "artifacts": artifacts,
        "relationships": edges,
        "detail": kind_detail,
    }


def build_projection(records: AdmittedRecords) -> WorkbenchProjection:
    """Build and validate one frozen, non-persisted workbench representation."""

    runtime = active_build_provenance(command_id="tcw.workbench")
    runtime_display = {
        "package_version": runtime["package_version"],
        "provenance_id": runtime["provenance_id"],
    }
    edge_map = {
        key: _record_edges(records, record)
        for key, record in records.records.items()
    }
    edges = sorted(
        [edge for values in edge_map.values() for edge in values],
        key=lambda value: value["edge_key"],
    )
    top = sorted(records.explicit_keys)
    contained = sorted(records.contained_only_keys)
    sid = session_id(
        top_level_record_keys=top,
        contained_record_keys=contained,
        edge_keys=[edge["edge_key"] for edge in edges],
    )
    projection = {
        "schema_version": "tcw.workbench-projection/v0.5",
        "projection_role": "DERIVED_READ_ONLY",
        "session_id": sid,
        "runtime": runtime_display,
        "counts": {
            "record_count": len(records.records),
            "top_level_record_count": len(top),
            "contained_record_count": len(contained),
        },
        "records": sorted(
            (_node(record) for record in records.records.values()),
            key=lambda value: value["record_key"],
        ),
        "edges": edges,
    }
    details = {
        key: _detail(records, record, edge_map[key])
        for key, record in records.records.items()
    }
    validate_document("tcw.workbench-projection/v0.5", projection)
    for detail in details.values():
        validate_document("tcw.workbench-record-detail/v0.5", detail)
    if len(canonical_json(projection)) > MAX_STRUCTURED_RESPONSE:
        raise IntegrityError("workbench projection exceeds the structured response limit")
    if any(len(canonical_json(detail)) > MAX_STRUCTURED_RESPONSE for detail in details.values()):
        raise IntegrityError("workbench record detail exceeds the structured response limit")
    return WorkbenchProjection(projection, details)
