"""Compose the bundled Workbench's small internal read model."""

from __future__ import annotations

import copy
import hashlib
import importlib.metadata
import json
import tempfile
from contextlib import contextmanager
from dataclasses import dataclass
from pathlib import Path, PurePosixPath
from typing import Any, Iterator, Sequence

from tiny_corpus_workbench.canonical_json import (
    canonical_json,
    canonical_sha256,
    edge_key,
    session_id,
)
from tiny_corpus_workbench.diagnosis_rules import (
    CURRENT_RULES,
    CURRENT_RULESET,
    CURRENT_RULESET_PARAMETER_HASH,
    RULESET,
    RULESET_PARAMETER_HASH,
)
from tiny_corpus_workbench.domain import IntegrityError
from tiny_corpus_workbench.application.diagnosis import verify_diagnosis
from tiny_corpus_workbench.application.refinement import (
    supported_refiner,
    verify_refinement,
)
from tiny_corpus_workbench.workbench_records import (
    MAX_STRUCTURED_RESPONSE,
    AdmittedRecord,
    AdmittedRecords,
)
from tiny_corpus_workbench.verification_results import (
    DiagnosisVerificationResult,
    RefinementVerificationResult,
)


SCHEMAS = {
    "OBSERVATION": "observation-manifest",
    "DIAGNOSIS": "diagnosis-manifest",
    "REFINEMENT": "refinement-manifest",
    "CORPUS": "corpus-manifest",
}
PACKAGE_VERSION = importlib.metadata.version("tiny-corpus-workbench")


@dataclass(frozen=True)
class WorkbenchProjection:
    projection: dict[str, Any]
    details: dict[str, dict[str, Any]]
    artifact_contents: dict[str, bytes]

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
) -> DiagnosisVerificationResult:
    with _frozen_verifier_roots((diagnosis, subject)) as roots:
        return verify_diagnosis(roots[0], roots[1])


def _verify_refinement_frozen(
    refinement: AdmittedRecord,
    diagnosis: AdmittedRecord | None,
    base: AdmittedRecord | None,
) -> RefinementVerificationResult:
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
                checked.artifact_integrity.status != "VERIFIED"
                or checked.subject_state.status != "MATCH"
                or checked.derivation_state.status != "MATCH"
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
                diagnosis_checked.artifact_integrity.status != "VERIFIED"
                or diagnosis_checked.diagnosis_state.status != "MATCH"
            ):
                raise IntegrityError(
                    "refinement diagnosis relationship evaluation failed"
                )
        if base_record is not None:
            base_checked = _verify_refinement_frozen(
                record, None, base_record
            )
            if (
                base_checked.artifact_integrity.status != "VERIFIED"
                or base_checked.base_state.status != "MATCH"
            ):
                raise IntegrityError(
                    "refinement base relationship evaluation failed"
                )
        if diagnosis_record is not None and base_record is not None:
            checked = _verify_refinement_frozen(
                record, diagnosis_record, base_record
            )
            expected = (
                "MATCH"
                if manifest["decision"] == "APPROVED"
                else "NOT_APPLICABLE"
            )
            if (
                checked.artifact_integrity.status != "VERIFIED"
                or checked.diagnosis_state.status != "MATCH"
                or checked.base_state.status != "MATCH"
                or checked.derivation_state.status != expected
                or checked.reversibility_state.status != expected
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
                        checked.artifact_integrity.status != "VERIFIED"
                        or checked.subject_state.status != "MATCH"
                        or checked.derivation_state.status != "MATCH"
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


PRIMARY_IDENTITIES = {
    "OBSERVATION": "observation_id",
    "DIAGNOSIS": "diagnosis_id",
    "REFINEMENT": "draft_id",
    "CORPUS": "corpus_id",
}

COMPARISON_METRICS = (
    "bytes",
    "characters",
    "non_whitespace_characters",
    "lines",
    "non_empty_lines",
    "atx_headings",
    "unordered_list_items",
    "ordered_list_items",
    "pipe_table_rows",
    "visible_urls",
)


def _primary_identity(record: AdmittedRecord) -> dict[str, str]:
    name = PRIMARY_IDENTITIES[record.kind]
    return {"name": name, "value": record.identity[name]}


def _artifact_descriptor(descriptor: dict[str, Any]) -> dict[str, Any]:
    return {
        "artifact_key": descriptor["artifact_key"],
        "role": descriptor["role"],
        "media_type": descriptor["recorded_media_type"],
        "size": descriptor["size"],
        "sha256": descriptor["sha256"],
        "availability": descriptor["availability"],
    }


def _artifact_bundle(
    record: AdmittedRecord,
) -> tuple[list[dict[str, Any]], dict[str, bytes]]:
    root, listed = record.descriptors()
    original = [root, *listed]
    descriptors = sorted(
        (_artifact_descriptor(item) for item in original),
        key=lambda item: item["artifact_key"],
    )
    contents = {
        item["artifact_key"]: _frozen_file_bytes(record, item)
        for item in original
    }
    return descriptors, contents


def _node(record: AdmittedRecord, artifact_count: int) -> dict[str, Any]:
    return {
        "record_key": record.record_key,
        "kind": record.kind,
        "status": record.status,
        "run_id": record.run_id,
        "primary_identity": _primary_identity(record),
        "origin": "TOP_LEVEL" if record.top_level else "CORPUS_CONTAINED",
        "artifact_count": artifact_count,
    }


def _source_identity(source: dict[str, Any]) -> tuple[str, str]:
    return source["sha256"], source["media_type"]


def _document_key(identity: tuple[str, str]) -> str:
    return canonical_sha256(
        {"source_sha256": identity[0], "media_type": identity[1]}
    )


def _reference_data() -> dict[str, Any]:
    return {
        "ruleset": {
            "name": CURRENT_RULESET["name"],
            "version": CURRENT_RULESET["version"],
            "parameter_hash": CURRENT_RULESET_PARAMETER_HASH,
        },
        "rules": [
            {
                **copy.deepcopy(rule),
                "refiner": supported_refiner(rule["rule_id"]),
            }
            for rule in CURRENT_RULES
        ],
    }


def _matched_target_key(
    edges: list[dict[str, Any]], relation: str
) -> str | None:
    matches = [
        edge["target_record_key"]
        for edge in edges
        if edge["relation"] == relation and edge["state"] == "MATCH"
    ]
    if len(matches) > 1:
        raise IntegrityError("linear preparation relationship is ambiguous")
    return matches[0] if matches else None


def _document_rounds(
    records: AdmittedRecords,
    edge_map: dict[str, list[dict[str, Any]]],
    observation: AdmittedRecord,
    consumed: set[str],
) -> list[dict[str, Any]]:
    """Shape only the fixed Diagnose -> Refine journey over verified edges."""

    explicit = {
        key: records.records[key] for key in records.explicit_keys
    }
    diagnoses_by_subject: dict[str, list[AdmittedRecord]] = {}
    refinements_by_diagnosis_base: dict[
        tuple[str, str], list[AdmittedRecord]
    ] = {}
    for key, record in explicit.items():
        if record.kind == "DIAGNOSIS":
            subject_key = _matched_target_key(
                edge_map[key], "DIAGNOSIS_SUBJECT"
            )
            if subject_key is not None:
                diagnoses_by_subject.setdefault(subject_key, []).append(record)
        elif record.kind == "REFINEMENT":
            diagnosis_key = _matched_target_key(
                edge_map[key], "REFINEMENT_DIAGNOSIS"
            )
            base_key = _matched_target_key(edge_map[key], "REFINEMENT_BASE")
            if diagnosis_key is not None and base_key is not None:
                refinements_by_diagnosis_base.setdefault(
                    (diagnosis_key, base_key), []
                ).append(record)

    rounds: list[dict[str, Any]] = []
    seen_bases: set[str] = set()
    base = observation
    while True:
        if base.record_key in seen_bases:
            raise IntegrityError("preparation rounds are not linear")
        seen_bases.add(base.record_key)
        diagnoses = diagnoses_by_subject.get(base.record_key, [])
        if len(diagnoses) > 1:
            raise IntegrityError(
                "one preparation base has multiple diagnoses"
            )
        if not diagnoses:
            break
        diagnosis = diagnoses[0]
        if diagnosis.record_key in consumed:
            raise IntegrityError("preparation record is not uniquely reachable")
        consumed.add(diagnosis.record_key)
        refinements = refinements_by_diagnosis_base.get(
            (diagnosis.record_key, base.record_key), []
        )
        if len(refinements) > 1:
            raise IntegrityError(
                "one preparation diagnosis has multiple refinement decisions"
            )
        refinement = refinements[0] if refinements else None
        if refinement is not None:
            if refinement.record_key in consumed:
                raise IntegrityError(
                    "preparation record is not uniquely reachable"
                )
            consumed.add(refinement.record_key)
        rounds.append(
            {
                "number": len(rounds) + 1,
                "base_record_key": base.record_key,
                "diagnosis_record_key": diagnosis.record_key,
                "refinement_record_key": (
                    refinement.record_key if refinement is not None else None
                ),
                "revision_record_key": (
                    refinement.record_key
                    if refinement is not None
                    and refinement.status == "APPROVED"
                    else None
                ),
            }
        )
        if refinement is None or refinement.status != "APPROVED":
            break
        base = refinement
    return rounds


def _presentation(
    records: AdmittedRecords,
    edge_map: dict[str, list[dict[str, Any]]],
    nodes: list[dict[str, Any]],
) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    explicit_lifecycle = {
        key
        for key in records.explicit_keys
        if records.records[key].kind in {"DIAGNOSIS", "REFINEMENT"}
    }
    for key in explicit_lifecycle:
        if any(edge["state"] != "MATCH" for edge in edge_map[key]):
            raise IntegrityError(
                "explicit lifecycle record has a missing required relationship"
            )
    observations: dict[tuple[str, str], list[AdmittedRecord]] = {}
    for key in records.explicit_keys:
        record = records.records[key]
        if record.kind == "OBSERVATION":
            observations.setdefault(
                _source_identity(record.manifest["source"]), []
            ).append(record)
    duplicate = next(
        (values for values in observations.values() if len(values) > 1),
        None,
    )
    if duplicate is not None:
        raise IntegrityError(
            "workspace has multiple Observation roots for one source identity; "
            "use a new or clean workspace"
        )

    documents = []
    consumed: set[str] = set()
    for identity, values in observations.items():
        observation = values[0]
        documents.append(
            {
                "document_key": _document_key(identity),
                "source": _compact_source(observation.manifest["source"]),
                "first_observation_at": observation.manifest["created_at"],
                "observation_record_key": observation.record_key,
                "rounds": _document_rounds(
                    records, edge_map, observation, consumed
                ),
            }
        )
    if consumed != explicit_lifecycle:
        raise IntegrityError(
            "explicit lifecycle record is unreachable from an Observation root"
        )
    documents.sort(
        key=lambda item: (
            item["source"]["sha256"], item["source"]["media_type"]
        )
    )
    documents.sort(
        key=lambda item: item["first_observation_at"], reverse=True
    )
    by_key = {node["record_key"]: node for node in nodes}
    corpora = []
    for key in sorted(records.explicit_keys):
        record = records.records[key]
        if record.kind != "CORPUS":
            continue
        specification = _artifact_json(
            record, "normalized-corpus-specification"
        )
        corpora.append(
            {
                "record_key": key,
                "corpus_id": record.manifest["corpus_id"],
                "title": specification["title"],
                "status": by_key[key]["status"],
                "member_count": record.manifest["summary"]["member_count"],
            }
        )
    return documents, corpora


def _artifact_json(record: AdmittedRecord, role: str) -> dict[str, Any]:
    raw = record.read_artifact(role)
    try:
        value = json.loads(raw.decode("utf-8"))
    except (UnicodeError, json.JSONDecodeError) as error:
        raise IntegrityError("frozen authorized artifact is not valid JSON") from error
    if not isinstance(value, dict):
        raise IntegrityError("frozen authorized artifact root is not an object")
    return value


def _compact_source(
    source: dict[str, Any], *, logical_key: str | None = None
) -> dict[str, Any]:
    return {
        "key": source.get("key", logical_key),
        "name": source.get("name"),
        "media_type": source["media_type"],
        "size": source["size"],
        "sha256": source["sha256"],
    }


def _metric_view(value: dict[str, Any] | None) -> dict[str, int] | None:
    if value is None:
        return None
    metrics = value.get("metrics", value)
    return {name: metrics[name] for name in COMPARISON_METRICS}


def _metric_deltas(value: dict[str, Any] | None) -> dict[str, Any] | None:
    if value is None:
        return None
    return {
        **{name: value[name] for name in COMPARISON_METRICS},
        "normalized_equal": value["normalized_equal"],
    }


def _observation_detail(record: AdmittedRecord) -> dict[str, Any]:
    manifest = record.manifest
    comparison = _artifact_json(record, "comparison-summary")
    return {
        "source": _compact_source(manifest["source"]),
        "docling_document": {
            "name": manifest["docling_document_schema"]["name"],
            "version": manifest["docling_document_schema"]["version"],
        },
        "extractors": [
            {
                "name": extractor["name"],
                "version": extractor["version"],
                "status": extractor["status"],
                "upstream_status": extractor["upstream_status"],
                "error": copy.deepcopy(extractor["error"]),
            }
            for extractor in manifest["extractors"]
        ],
        "comparison": {
            "status": comparison["status"],
            "docling": _metric_view(comparison["views"]["docling"]),
            "markitdown": _metric_view(comparison["views"]["markitdown"]),
            "docling_minus_markitdown": _metric_deltas(comparison["deltas"]),
        },
    }


def _actionable_diagnosis_subject(
    records: AdmittedRecords, edge: dict[str, Any]
) -> bool:
    key = edge.get("target_record_key")
    if edge["state"] != "MATCH" or key not in records.explicit_keys:
        return False
    target = records.records[key]
    if target.kind == "OBSERVATION":
        _, artifacts = target.descriptors()
        return any(
            artifact["role"] == "docling-document-json"
            for artifact in artifacts
        )
    return target.kind == "REFINEMENT" and target.status == "APPROVED"


def _diagnosis_detail(
    records: AdmittedRecords,
    record: AdmittedRecord,
    edges: list[dict[str, Any]],
) -> dict[str, Any]:
    manifest = record.manifest
    findings = _artifact_json(record, "diagnostic-findings")
    state = edges[0]["state"]
    subject_actionable = (
        record.record_key in records.explicit_keys
        and len(edges) == 1
        and _actionable_diagnosis_subject(records, edges[0])
    )
    enriched = []
    for finding in findings["findings"]:
        refiner = supported_refiner(finding["rule_id"])
        if refiner is None:
            action = {"status": "UNAVAILABLE", "reason": "NO_SUPPORTED_REFINER"}
        elif subject_actionable:
            action = {"status": "AVAILABLE", "reason": None}
        else:
            action = {"status": "UNAVAILABLE", "reason": "SUBJECT_NOT_ACTIONABLE"}
        enriched.append(
            {
                **{
                    key: copy.deepcopy(finding[key])
                    for key in (
                        "finding_id",
                        "rule_id",
                        "rule_version",
                        "summary",
                        "severity",
                        "document_refs",
                        "evidence",
                    )
                },
                "refiner": refiner,
                "proposal_action": action,
            }
        )
    return {
        "source": _compact_source(manifest["source"]),
        "subject_state": "MATCH" if state == "MATCH" else "NOT_CHECKED",
        "derivation_state": "MATCH" if state == "MATCH" else "NOT_CHECKED",
        "finding_total": manifest["summary"]["total"],
        "findings": sorted(enriched, key=lambda value: value["finding_id"]),
    }


def _refinement_detail(
    record: AdmittedRecord, edges: list[dict[str, Any]]
) -> dict[str, Any]:
    manifest = record.manifest
    by_relation = {item["relation"]: item for item in edges}
    proposal = _artifact_json(record, "refinement-proposal")
    approved = manifest["decision"] == "APPROVED"
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
        "source": _compact_source(manifest["source"]),
        "decision": manifest["decision"],
        "proposal": {
            "draft_id": proposal["draft_id"],
            "finding_id": proposal["finding"]["finding_id"],
            "refiner": copy.deepcopy(proposal["refiner"]),
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
                "source": _compact_source(
                    member["source"], logical_key=member["member_id"]
                ),
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
    for revision in sorted(
        manifest["revisions"],
        key=lambda value: (value["member_id"], value["chain_length"], value["revision_id"]),
    ):
        edge = external_edges[revision["revision_id"]]
        external.append(
            {
                "member_id": revision["member_id"],
                "revision_id": revision["revision_id"],
                "relationship_state": edge["state"],
                "target_record_key": edge["target_record_key"],
            }
        )
    return {
        "corpus_id": manifest["corpus_id"],
        "snapshot_id": manifest["snapshot_id"],
        "status": summary["status"],
        "totals": copy.deepcopy(summary["totals"]),
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


def _compact_relationship(edge: dict[str, Any]) -> dict[str, Any]:
    target = edge["expected_target"]
    result = {
        "relation": edge["relation"],
        "state": edge["state"],
        "target_kind": target["kind"],
        "target_identity": {
            "name": target["identity_type"],
            "value": target["identity_value"],
        },
    }
    if edge["target_record_key"] is not None:
        result["target_record_key"] = edge["target_record_key"]
    return result


def _detail(
    records: AdmittedRecords,
    record: AdmittedRecord,
    edges: list[dict[str, Any]],
    artifacts: list[dict[str, Any]],
) -> dict[str, Any]:
    if record.kind == "OBSERVATION":
        kind_detail = _observation_detail(record)
    elif record.kind == "DIAGNOSIS":
        kind_detail = _diagnosis_detail(records, record, edges)
    elif record.kind == "REFINEMENT":
        kind_detail = _refinement_detail(record, edges)
    else:
        kind_detail = _corpus_detail(records, record, edges)
    return {
        "record_key": record.record_key,
        "kind": record.kind,
        "artifact_integrity": "VERIFIED",
        "artifacts": artifacts,
        "relationships": [_compact_relationship(edge) for edge in edges],
        "view": kind_detail,
    }


def build_projection(records: AdmittedRecords) -> WorkbenchProjection:
    """Build one frozen, internal Workbench representation."""

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
        "package_version": PACKAGE_VERSION,
        "reference": _reference_data(),
        "session_id": sid,
        "counts": {
            "record_count": len(records.records),
            "top_level_record_count": len(top),
            "contained_record_count": len(contained),
        },
    }
    artifact_descriptors: dict[str, list[dict[str, Any]]] = {}
    artifact_contents: dict[str, bytes] = {}
    for key, record in records.records.items():
        descriptors, contents = _artifact_bundle(record)
        artifact_descriptors[key] = descriptors
        for artifact_key, content in contents.items():
            if (
                artifact_key in artifact_contents
                and artifact_contents[artifact_key] != content
            ):
                raise IntegrityError("artifact key resolves to conflicting bytes")
            artifact_contents[artifact_key] = content
    projection["records"] = sorted(
        (
            _node(record, len(artifact_descriptors[key]))
            for key, record in records.records.items()
        ),
        key=lambda value: value["record_key"],
    )
    projection["documents"], projection["corpora"] = _presentation(
        records, edge_map, projection["records"]
    )
    details = {
        key: _detail(
            records,
            record,
            edge_map[key],
            artifact_descriptors[key],
        )
        for key, record in records.records.items()
    }
    if len(canonical_json(projection)) > MAX_STRUCTURED_RESPONSE:
        raise IntegrityError("workbench projection exceeds the structured response limit")
    if any(len(canonical_json(detail)) > MAX_STRUCTURED_RESPONSE for detail in details.values()):
        raise IntegrityError("workbench record detail exceeds the structured response limit")
    advertised = {
        artifact["artifact_key"]
        for detail in details.values()
        for artifact in detail["artifacts"]
    }
    if advertised != set(artifact_contents):
        raise IntegrityError("advertised artifact keys differ from captured bytes")
    return WorkbenchProjection(projection, details, artifact_contents)


def empty_projection() -> WorkbenchProjection:
    """Build the stable read model for a workspace with no records."""

    return build_projection(AdmittedRecords({}, set(), []))
