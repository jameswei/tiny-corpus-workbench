"""v0.3 diagnosis subjects, explicit decisions, and reversible revisions."""

from __future__ import annotations

import base64
import copy
import hashlib
import json
import os
import re
import stat
import sys
import tempfile
import unicodedata
import uuid
from collections import Counter
from datetime import UTC, datetime
from pathlib import Path, PurePosixPath
from typing import Any, Iterable

from docling_core.types.doc import DoclingDocument
from jsonschema import Draft202012Validator
from referencing import Registry, Resource

from tiny_corpus_workbench.artifacts import _rename_exclusive, canonical_json
from tiny_corpus_workbench.diagnosis import (
    RULESET as V02_RULES,
    _canonicalize_findings,
    _hash,
    _index,
    _reading_order,
    _table_cells,
    analyze_document as analyze_v02,
    snapshot_tree,
    validate_finding_contract as validate_v02_finding,
)
from tiny_corpus_workbench.domain import (
    CanonicalUnavailableError,
    InputError,
    IntegrityError,
    RuntimeContractError,
    sanitize_message,
)
from tiny_corpus_workbench.runtime import active_locked_runtime
from tiny_corpus_workbench.source import sha256_file
from tiny_corpus_workbench.verification import FORMAT_CHECKER, verify_observation


SCHEMA_ROOT = Path(__file__).with_name("schemas")
V03_RULES = [
    *V02_RULES,
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
RULESET = {
    "name": "tcw-evidence-based-diagnosis",
    "version": "v0.3",
    "rules": V03_RULES,
}
RULESET_PARAMETER_HASH = _hash(
    canonical_json(
        [
            {
                "rule_id": item["rule_id"],
                "rule_version": item["version"],
                "parameters": item["parameters"],
            }
            for item in V03_RULES
        ]
    ).rstrip(b"\n")
)
REFINERS = {
    "TCW-D009": {
        "refiner_id": "TCW-R001",
        "name": "WHITESPACE_NORMALIZATION",
        "version": "1",
    },
    "TCW-D007": {
        "refiner_id": "TCW-R002",
        "name": "REPEATED_BOILERPLATE_REMOVAL",
        "version": "1",
    },
    "TCW-D010": {
        "refiner_id": "TCW-R003",
        "name": "DETERMINISTIC_DEHYPHENATION",
        "version": "1",
    },
}
_ALPHA = r"[^\W\d_]"
_HYPHENATION = re.compile(
    rf"(?<!{_ALPHA})({_ALPHA}{{2,}})-([^\S\r\n]*)(\r\n|\r|\n)([^\S\r\n]*)({_ALPHA}{{2,}})(?!{_ALPHA})",
    re.UNICODE,
)


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
        raise RuntimeContractError("bundled v0.3 schema is unavailable") from error


def _validate(name: str, value: object) -> None:
    try:
        _validator(name).validate(value)
    except RuntimeContractError:
        raise
    except Exception as error:
        raise IntegrityError(f"{name} validation failed") from error


def _artifact(path: Path, root: Path, role: str, media_type: str) -> dict[str, Any]:
    return {
        "path": path.relative_to(root).as_posix(),
        "role": role,
        "media_type": media_type,
        "size": path.stat().st_size,
        "sha256": sha256_file(path),
        "application_immutable": True,
    }


def _safe_component(value: str, label: str) -> str:
    if (
        not value
        or value in {".", ".."}
        or "/" in value
        or "\\" in value
        or "\0" in value
        or Path(value).is_absolute()
    ):
        raise InputError(f"{label} is not a safe path component")
    return value


def _ensure_outside(inputs: Iterable[Path], target: Path) -> None:
    try:
        resolved_target = target.resolve(strict=False)
        for value in inputs:
            resolved_input = value.resolve(strict=True)
            if resolved_target == resolved_input or resolved_target.is_relative_to(
                resolved_input
            ):
                raise InputError("output must not be inside an input directory")
    except InputError:
        raise
    except (OSError, RuntimeError) as error:
        raise InputError("input or output path cannot be resolved safely") from error


def _publish_directory(staging: Path, destination: Path) -> Path:
    destination.parent.mkdir(parents=True, exist_ok=True)
    try:
        _rename_exclusive(staging, destination)
    except OSError as error:
        raise IntegrityError("publication conflict or failure") from error
    return destination


def _write_exclusive(path: Path, data: bytes) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    try:
        descriptor = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
        with os.fdopen(descriptor, "wb") as stream:
            stream.write(data)
    except FileExistsError as error:
        raise IntegrityError("decision file already exists") from error
    except OSError as error:
        raise IntegrityError("decision file cannot be published") from error


def _load_json_regular(path: Path, label: str) -> tuple[bytes, dict[str, Any]]:
    try:
        mode = path.lstat().st_mode
        if stat.S_ISLNK(mode) or not stat.S_ISREG(mode):
            raise OSError
        raw = path.read_bytes()
        value = json.loads(raw)
        if not isinstance(value, dict):
            raise ValueError
        return raw, value
    except (OSError, UnicodeError, json.JSONDecodeError, ValueError) as error:
        raise InputError(f"{label} is unavailable or invalid") from error


def _file_identity(path: Path) -> tuple[Any, ...]:
    try:
        metadata = path.lstat()
        if stat.S_ISLNK(metadata.st_mode) or not stat.S_ISREG(metadata.st_mode):
            raise OSError
        return (
            metadata.st_dev,
            metadata.st_ino,
            metadata.st_mode,
            metadata.st_size,
            metadata.st_mtime_ns,
            metadata.st_ctime_ns,
            sha256_file(path),
        )
    except OSError as error:
        raise IntegrityError("decision file changed or became unavailable") from error


def _observation_subject(root: Path) -> dict[str, Any]:
    before = snapshot_tree(root)
    manifest_bytes, manifest = _load_json_regular(root / "manifest.json", "observation")
    try:
        docling = manifest["extractors"][0]
        descriptor = next(
            (
                item
                for item in docling["artifacts"]
                if item["role"] == "docling-document-json"
            ),
            None,
        )
    except (KeyError, TypeError, IndexError):
        docling = {}
        descriptor = None
    if docling.get("status") not in {"SUCCESS", "PARTIAL_SUCCESS"} or descriptor is None:
        raise CanonicalUnavailableError("canonical Docling artifact is unavailable")
    if not (root / descriptor["path"]).is_file():
        raise CanonicalUnavailableError("canonical Docling artifact is unavailable")
    if (
        manifest.get("schema_version") != "tcw.preparation-manifest/v0.1"
        or verify_observation(root)["artifact_integrity"]["status"] != "VERIFIED"
    ):
        raise InputError("observation integrity is not verified")
    try:
        document_bytes, payload = _load_json_regular(
            root / descriptor["path"], "canonical Docling artifact"
        )
        _index(payload)
        DoclingDocument.model_validate(payload)
    except (InputError, IntegrityError, ValueError) as error:
        raise CanonicalUnavailableError(
            "canonical Docling artifact is unavailable"
        ) from error
    return {
        "before": before,
        "root": root,
        "kind": "OBSERVATION",
        "subject_id": manifest["observation_id"],
        "parent_id": None,
        "origin_observation_id": manifest["observation_id"],
        "origin_observation_run_id": manifest["run_id"],
        "source": {
            key: manifest["source"][key]
            for key in ("key", "media_type", "size", "sha256")
        },
        "manifest_bytes": manifest_bytes,
        "manifest": manifest,
        "document_path": descriptor["path"],
        "document_bytes": document_bytes,
        "payload": payload,
        "history": [],
    }


def _refinement_subject(root: Path) -> dict[str, Any]:
    report = verify_refinement(root)
    if report["artifact_integrity"]["status"] != "VERIFIED":
        raise InputError("refinement integrity is not verified")
    manifest_bytes, manifest = _load_json_regular(
        root / "refinement-manifest.json", "refinement manifest"
    )
    if manifest["status"] != "APPLIED":
        raise InputError("a rejected refinement cannot be a diagnosis subject")
    document_bytes, payload = _load_json_regular(
        root / "prepared/document.json", "prepared document"
    )
    _, history = _load_json_regular(root / "history.json", "transformation history")
    _index(payload)
    DoclingDocument.model_validate(payload)
    return {
        "before": snapshot_tree(root),
        "root": root,
        "kind": "REVISION",
        "subject_id": manifest["revision_id"],
        "parent_id": manifest["base"]["subject_id"],
        "origin_observation_id": manifest["origin_observation_id"],
        "origin_observation_run_id": manifest["origin_observation_run_id"],
        "source": manifest["source"],
        "manifest_bytes": manifest_bytes,
        "manifest": manifest,
        "document_path": "prepared/document.json",
        "document_bytes": document_bytes,
        "payload": payload,
        "history": history["transformations"],
    }


def load_subject(root: Path) -> dict[str, Any]:
    if root.is_symlink() or not root.is_dir():
        raise InputError("DOCUMENT_DIRECTORY must be one local non-symlink directory")
    if (root / "manifest.json").is_file():
        return _observation_subject(root)
    if (root / "refinement-manifest.json").is_file():
        return _refinement_subject(root)
    raise InputError("document directory is not a supported observation or revision")


def _normalize_whitespace(value: str) -> str:
    value = value.replace("\r\n", "\n").replace("\r", "\n")
    lines = []
    for line in value.split("\n"):
        mapped = "".join(" " if character.isspace() else character for character in line)
        lines.append(re.sub(" +", " ", mapped).strip(" "))
    return "\n".join(lines)


def _whitespace_span_offsets(value: str) -> list[int]:
    normalized = _normalize_whitespace(value)
    if normalized == value:
        return []
    offsets: list[int] = []
    position = 0
    while position < len(value):
        character = value[position]
        if character == "\r":
            offsets.append(position)
            position += 2 if value[position : position + 2] == "\r\n" else 1
        elif character.isspace() and character != "\n":
            offsets.append(position)
            position += 1
            while (
                position < len(value)
                and value[position].isspace()
                and value[position] not in "\r\n"
            ):
                position += 1
        else:
            position += 1
    if not offsets:
        offsets.append(0)
    return offsets


def _hyphen_matches(value: str) -> list[re.Match[str]]:
    return [
        match
        for match in _HYPHENATION.finditer(value)
        if match.group(5)[0].islower()
    ]


def _repair_hyphenation(value: str) -> str:
    matches = _hyphen_matches(value)
    for match in reversed(matches):
        replacement = match.group(1) + match.group(5)
        value = value[: match.start()] + replacement + value[match.end() :]
    return value


def _eligible_targets(payload: dict[str, Any]) -> Iterable[tuple[dict[str, Any], dict[str, Any]]]:
    index = _index(payload)
    for item in _reading_order(payload, index):
        if item.get("content_layer", "body") != "body":
            continue
        if item.get("label") in {"code", "formula"}:
            continue
        if isinstance(item.get("text"), str):
            yield item, {"ref": item["self_ref"]}
        if item.get("label") == "table":
            for cell in _table_cells(item):
                if isinstance(cell.get("text"), str):
                    yield cell, {
                        "ref": item["self_ref"],
                        "row": cell.get("start_row_offset_idx", 0),
                        "column": cell.get("start_col_offset_idx", 0),
                    }


def _v3_finding(
    diagnosis_id: str,
    rule_id: str,
    target: dict[str, Any],
    evidence: dict[str, Any],
) -> dict[str, Any]:
    stable = {name: evidence[name] for name in sorted(evidence)}
    identity = {
        "diagnosis_id": diagnosis_id,
        "rule_id": rule_id,
        "rule_version": "1",
        "document_refs": [target["ref"]],
        "evidence": stable,
    }
    names = {"TCW-D009": "Normalizable Whitespace", "TCW-D010": "Possible Line End Hyphenation"}
    return {
        "finding_id": _hash(canonical_json(identity).rstrip(b"\n")),
        "rule_id": rule_id,
        "rule_version": "1",
        "severity": "INFO" if rule_id == "TCW-D009" else "WARNING",
        "summary": names[rule_id],
        "document_refs": [target["ref"]],
        "evidence": stable,
    }


def compute_diagnosis_id(subject: dict[str, Any]) -> str:
    descriptor = {
        "kind": subject["kind"],
        "subject_id": subject["subject_id"],
        "canonical_document_path": subject["document_path"],
        "canonical_document_size": len(subject["document_bytes"]),
        "canonical_document_sha256": _hash(subject["document_bytes"]),
        "origin_observation_id": subject["origin_observation_id"],
    }
    return _hash(
        canonical_json(
            {
                "subject": descriptor,
                "canonical_document_sha256": descriptor[
                    "canonical_document_sha256"
                ],
                "ruleset": RULESET,
            }
        ).rstrip(b"\n")
    )


def make_finding_set(subject: dict[str, Any]) -> dict[str, Any]:
    diagnosis_id = compute_diagnosis_id(subject)
    findings = analyze_v02(
        subject["payload"],
        media_type=subject["source"]["media_type"],
        diagnosis_id=diagnosis_id,
    )
    for target_value, target in _eligible_targets(subject["payload"]):
        value = target_value["text"]
        offsets = _whitespace_span_offsets(value)
        if offsets:
            normalized = _normalize_whitespace(value)
            evidence = {
                "code_point_offsets": offsets,
                "occurrence_count": len(offsets),
                "original_text_sha256": _hash(value),
                "normalized_text_sha256": _hash(normalized),
            }
            evidence.update({key: target[key] for key in ("row", "column") if key in target})
            findings.append(_v3_finding(diagnosis_id, "TCW-D009", target, evidence))
        matches = _hyphen_matches(value)
        if matches:
            repaired = _repair_hyphenation(value)
            evidence = {
                "hyphen_code_point_offsets": [
                    match.start(1) + len(match.group(1)) for match in matches
                ],
                "occurrence_count": len(matches),
                "original_text_sha256": _hash(value),
                "repaired_text_sha256": _hash(repaired),
            }
            evidence.update({key: target[key] for key in ("row", "column") if key in target})
            findings.append(_v3_finding(diagnosis_id, "TCW-D010", target, evidence))
    findings = _canonicalize_findings(findings)
    severity = Counter(item["severity"] for item in findings)
    rules = Counter(item["rule_id"] for item in findings)
    summary = {
        "total": len(findings),
        "by_severity": {
            name: severity.get(name, 0) for name in ("ERROR", "WARNING", "INFO")
        },
        "by_rule": {
            item["rule_id"]: rules.get(item["rule_id"], 0) for item in V03_RULES
        },
    }
    return {
        "schema_version": "tcw.finding-set/v0.3",
        "diagnosis_id": diagnosis_id,
        "subject": {
            "kind": subject["kind"],
            "subject_id": subject["subject_id"],
            "canonical_document_path": subject["document_path"],
            "canonical_document_size": len(subject["document_bytes"]),
            "canonical_document_sha256": _hash(subject["document_bytes"]),
            "origin_observation_id": subject["origin_observation_id"],
        },
        "ruleset": RULESET,
        "summary": summary,
        "findings": findings,
    }


def validate_finding_set(value: dict[str, Any]) -> None:
    findings = value["findings"]
    if findings != _canonicalize_findings(findings):
        raise IntegrityError("findings are not unique and canonically ordered")
    severity = Counter(item["severity"] for item in findings)
    rules = Counter(item["rule_id"] for item in findings)
    expected_summary = {
        "total": len(findings),
        "by_severity": {
            name: severity.get(name, 0) for name in ("ERROR", "WARNING", "INFO")
        },
        "by_rule": {
            item["rule_id"]: rules.get(item["rule_id"], 0) for item in V03_RULES
        },
    }
    if value["summary"] != expected_summary or value["ruleset"] != RULESET:
        raise IntegrityError("finding summary or ruleset is inconsistent")
    for finding in findings:
        expected_id = _hash(
            canonical_json(
                {
                    "diagnosis_id": value["diagnosis_id"],
                    "rule_id": finding["rule_id"],
                    "rule_version": finding["rule_version"],
                    "document_refs": finding["document_refs"],
                    "evidence": finding["evidence"],
                }
            ).rstrip(b"\n")
        )
        if finding["finding_id"] != expected_id:
            raise IntegrityError("finding identity is inconsistent")
        if finding["rule_id"] in {item["rule_id"] for item in V02_RULES}:
            validate_v02_finding(finding)
            continue
        evidence = finding["evidence"]
        offsets_name = (
            "code_point_offsets"
            if finding["rule_id"] == "TCW-D009"
            else "hyphen_code_point_offsets"
        )
        required = {
            offsets_name,
            "occurrence_count",
            "original_text_sha256",
            (
                "normalized_text_sha256"
                if finding["rule_id"] == "TCW-D009"
                else "repaired_text_sha256"
            ),
        }
        if "row" in evidence or "column" in evidence:
            required.update({"row", "column"})
        offsets = evidence.get(offsets_name)
        if (
            set(evidence) != required
            or not isinstance(offsets, list)
            or not offsets
            or offsets != sorted(set(offsets))
            or any(type(offset) is not int or offset < 0 for offset in offsets)
            or evidence.get("occurrence_count") != len(offsets)
            or len(finding["document_refs"]) != 1
        ):
            raise IntegrityError("v0.3 finding evidence is inconsistent")


def _diagnosis_report(findings: dict[str, Any]) -> bytes:
    lines = [
        "# Evidence-Based Diagnosis",
        "",
        f"- Diagnosis ID: `{findings['diagnosis_id']}`",
        f"- Subject: `{findings['subject']['kind']}:{findings['subject']['subject_id']}`",
        f"- Finding count: {findings['summary']['total']}",
        "",
        "A finding does not authorize mutation or certify overall quality.",
        "",
        "## Findings",
        "",
    ]
    if not findings["findings"]:
        lines.extend(["No fixed v0.3 rule produced a finding.", ""])
    for finding in findings["findings"]:
        lines.extend(
            [
                f"### {finding['rule_id']} — {finding['summary']}",
                "",
                f"- Finding ID: `{finding['finding_id']}`",
                f"- Severity: `{finding['severity']}`",
                "- Document refs: "
                + ", ".join(f"`{item}`" for item in finding["document_refs"]),
                "- Evidence:",
            ]
        )
        for name, value in finding["evidence"].items():
            lines.append(
                f"  - `{name}`: `{json.dumps(value, ensure_ascii=False, separators=(',', ':'))}`"
            )
        lines.append("")
    return ("\n".join(lines).rstrip() + "\n").encode()


def diagnose(root: Path, output_root: Path) -> Path:
    if output_root.is_symlink():
        raise InputError("diagnosis output root must not be a symlink")
    subject = load_subject(root)
    findings = make_finding_set(subject)
    validate_finding_set(findings)
    findings_bytes = canonical_json(findings)
    report_bytes = _diagnosis_report(findings)
    now = datetime.now(UTC)
    run_id = f"{now.strftime('%Y%m%dT%H%M%S.%fZ')}-{uuid.uuid4().hex[:12]}"
    destination = (
        output_root
        / _safe_component(subject["source"]["key"], "source key")
        / _safe_component(subject["subject_id"], "subject ID")
        / run_id
    )
    _ensure_outside([root], destination)
    destination.parent.mkdir(parents=True, exist_ok=True)
    staging = Path(tempfile.mkdtemp(prefix=".staging-", dir=destination.parent))
    try:
        (staging / "findings.json").write_bytes(findings_bytes)
        (staging / "report.md").write_bytes(report_bytes)
        artifacts = [
            _artifact(staging / "findings.json", staging, "diagnostic-findings", "application/json"),
            _artifact(staging / "report.md", staging, "diagnostic-report", "text/markdown"),
        ]
        runtime = active_locked_runtime()
        manifest = {
            "schema_version": "tcw.diagnosis-manifest/v0.3",
            "milestone": "v0.3",
            "run_id": run_id,
            "diagnosis_id": findings["diagnosis_id"],
            "created_at": now.isoformat().replace("+00:00", "Z"),
            "status": "FINDINGS" if findings["summary"]["total"] else "NO_FINDINGS",
            "source": subject["source"],
            "subject": findings["subject"],
            "subject_manifest_size": len(subject["manifest_bytes"]),
            "subject_manifest_sha256": _hash(subject["manifest_bytes"]),
            "runtime": runtime,
            "ruleset": {**RULESET, "parameter_sha256": RULESET_PARAMETER_HASH},
            "summary": findings["summary"],
            "artifacts": artifacts,
        }
        (staging / "diagnosis-manifest.json").write_bytes(canonical_json(manifest))
        _validate("finding-set-v0.3.schema.json", findings)
        _validate("diagnosis-manifest-v0.3.schema.json", manifest)
        if snapshot_tree(root) != subject["before"]:
            raise IntegrityError("diagnosis subject changed during diagnosis")
        return _publish_directory(staging, destination)
    finally:
        if staging.exists():
            import shutil

            shutil.rmtree(staging)


def _load_diagnosis(root: Path) -> tuple[tuple[Any, ...], dict[str, Any], dict[str, Any]]:
    before = snapshot_tree(root)
    _, manifest = _load_json_regular(
        root / "diagnosis-manifest.json", "diagnosis manifest"
    )
    _, findings = _load_json_regular(root / "findings.json", "finding set")
    if manifest.get("schema_version") != "tcw.diagnosis-manifest/v0.3":
        raise InputError("refinement requires a v0.3 diagnosis")
    _validate("diagnosis-manifest-v0.3.schema.json", manifest)
    _validate("finding-set-v0.3.schema.json", findings)
    if verify_diagnosis(root)["artifact_integrity"]["status"] != "VERIFIED":
        raise InputError("diagnosis integrity is not verified")
    return before, manifest, findings


def _target(payload: dict[str, Any], reference: str, evidence: dict[str, Any]) -> dict[str, Any]:
    item = _index(payload).get(reference)
    if item is None:
        raise IntegrityError("finding reference is stale")
    if "row" not in evidence:
        return item
    for cell in _table_cells(item):
        if (
            cell.get("start_row_offset_idx", 0) == evidence["row"]
            and cell.get("start_col_offset_idx", 0) == evidence["column"]
        ):
            return cell
    raise IntegrityError("finding table-cell reference is stale")


def _proposal(
    diagnosis_root: Path, finding_id: str, base_root: Path
) -> tuple[dict[str, Any], dict[str, Any]]:
    _, diagnosis, finding_set = _load_diagnosis(diagnosis_root)
    base = load_subject(base_root)
    if (
        finding_set["subject"]["subject_id"] != base["subject_id"]
        or finding_set["subject"]["canonical_document_sha256"]
        != _hash(base["document_bytes"])
    ):
        raise InputError("diagnosis does not describe the supplied base")
    finding = next(
        (item for item in finding_set["findings"] if item["finding_id"] == finding_id),
        None,
    )
    if finding is None:
        raise InputError("finding is absent from the diagnosis")
    refiner = REFINERS.get(finding["rule_id"])
    if refiner is None:
        raise InputError("finding has no v0.3 refiner")
    edits = []
    if finding["rule_id"] in {"TCW-D009", "TCW-D010"}:
        target = _target(
            base["payload"], finding["document_refs"][0], finding["evidence"]
        )
        before = target.get("text")
        if not isinstance(before, str):
            raise IntegrityError("finding target is stale")
        after = (
            _normalize_whitespace(before)
            if finding["rule_id"] == "TCW-D009"
            else _repair_hyphenation(before)
        )
        expected_hash = finding["evidence"][
            "normalized_text_sha256"
            if finding["rule_id"] == "TCW-D009"
            else "repaired_text_sha256"
        ]
        if before == after or _hash(before) != finding["evidence"]["original_text_sha256"] or _hash(after) != expected_hash:
            raise IntegrityError("finding target is stale")
        edits.append(
            {
                "target": {
                    "ref": finding["document_refs"][0],
                    **{
                        key: finding["evidence"][key]
                        for key in ("row", "column")
                        if key in finding["evidence"]
                    },
                    "field": "text",
                },
                "before": before,
                "after": after,
            }
        )
    else:
        index = _index(base["payload"])
        body = [
            value.get("$ref", value.get("cref"))
            for value in base["payload"]["body"].get("children", [])
        ]
        for reference in finding["document_refs"]:
            item = index.get(reference)
            if (
                item is None
                or item.get("content_layer", "body") != "body"
                or reference not in body
            ):
                raise IntegrityError("repeated-margin finding is stale")
            edits.append(
                {
                    "target": {"ref": reference, "field": "content_layer"},
                    "before": {
                        "content_layer": item.get("content_layer", "body"),
                        "body_index": body.index(reference),
                    },
                    "after": {"content_layer": "furniture"},
                }
            )
    proposal = {
        "state": "REQUESTED",
        "diagnosis_id": diagnosis["diagnosis_id"],
        "base": {
            "kind": base["kind"],
            "subject_id": base["subject_id"],
            "canonical_document_sha256": _hash(base["document_bytes"]),
            "origin_observation_id": base["origin_observation_id"],
        },
        "finding": finding,
        "refiner": refiner,
        "affected_refs": finding["document_refs"],
        "forward_edits": edits,
        "inverse_edits": [
            {"target": edit["target"], "before": edit["after"], "after": edit["before"]}
            for edit in reversed(edits)
        ],
    }
    proposal["draft_id"] = _hash(canonical_json(proposal).rstrip(b"\n"))
    return proposal, base


def draft_refinement(
    diagnosis_root: Path, finding_id: str, base_root: Path, output: Path
) -> dict[str, Any]:
    diagnosis_before = snapshot_tree(diagnosis_root)
    base_before = snapshot_tree(base_root)
    proposal, _ = _proposal(diagnosis_root, finding_id, base_root)
    draft = {
        "schema_version": "tcw.refinement-draft/v0.3",
        "proposal": proposal,
        "decision": {"state": "PENDING", "decided_by": None, "note": None},
    }
    _validate("refinement-draft-v0.3.schema.json", draft)
    _ensure_outside([diagnosis_root, base_root], output)
    if snapshot_tree(diagnosis_root) != diagnosis_before or snapshot_tree(base_root) != base_before:
        raise IntegrityError("refinement input changed during drafting")
    _write_exclusive(output, canonical_json(draft))
    return {"draft_id": proposal["draft_id"], "decision": str(output.resolve()), "state": "PENDING"}


def _apply_edits(payload: dict[str, Any], edits: list[dict[str, Any]]) -> dict[str, Any]:
    value = copy.deepcopy(payload)
    for edit in edits:
        target_spec = edit["target"]
        target = _target(value, target_spec["ref"], target_spec)
        if target_spec["field"] == "text":
            if target.get("text") != edit["before"]:
                raise IntegrityError("edit precondition does not match")
            target["text"] = edit["after"]
            continue
        if target.get("content_layer", "body") != edit["before"]["content_layer"]:
            raise IntegrityError("edit precondition does not match")
        reference = target_spec["ref"]
        body = value["body"]["children"]
        furniture = value["furniture"]["children"]
        body_refs = [item.get("$ref", item.get("cref")) for item in body]
        if reference not in body_refs:
            raise IntegrityError("body membership precondition does not match")
        body.pop(body_refs.index(reference))
        furniture.append({"$ref": reference})
        target["content_layer"] = "furniture"
    return value


def _prepared_bytes(payload: dict[str, Any]) -> tuple[bytes, bytes]:
    document = DoclingDocument.model_validate(payload)
    document_bytes = canonical_json(
        document.model_dump(mode="json", by_alias=True, exclude_none=True)
    )
    markdown = (document.export_to_markdown().rstrip() + "\n").encode()
    return document_bytes, markdown


def _render_refinement(manifest: dict[str, Any], decision: dict[str, Any]) -> bytes:
    lines = [
        "# Controlled Refinement",
        "",
        f"- Status: `{manifest['status']}`",
        f"- Draft ID: `{decision['proposal']['draft_id']}`",
        f"- Finding: `{decision['proposal']['finding']['finding_id']}`",
        f"- Refiner: `{decision['proposal']['refiner']['refiner_id']}`",
        f"- Decided by: `{decision['decision']['decided_by']}`",
    ]
    if manifest["revision_id"]:
        lines.append(f"- Revision ID: `{manifest['revision_id']}`")
    if decision["decision"]["note"]:
        lines.append(f"- Note: {decision['decision']['note']}")
    lines.extend(["", "The source, observation, diagnosis, base, and earlier revisions remain unchanged.", ""])
    return "\n".join(lines).encode()


def resolve_refinement(
    decision_file: Path,
    diagnosis_root: Path,
    base_root: Path,
    output_root: Path,
) -> Path:
    if output_root.is_symlink():
        raise InputError("refinement output root must not be a symlink")
    decision_before = _file_identity(decision_file)
    diagnosis_before = snapshot_tree(diagnosis_root)
    base_before = snapshot_tree(base_root)
    _, draft = _load_json_regular(decision_file, "decision file")
    _validate("refinement-draft-v0.3.schema.json", draft)
    state = draft["decision"]["state"]
    if state not in {"APPROVED", "REJECTED"}:
        raise InputError("decision must be APPROVED or REJECTED")
    if not draft["decision"]["decided_by"]:
        raise InputError("decided_by is required for a resolved decision")
    expected, base = _proposal(
        diagnosis_root, draft["proposal"]["finding"]["finding_id"], base_root
    )
    if draft["proposal"] != expected:
        raise IntegrityError("draft proposal was modified or is stale")
    now = datetime.now(UTC)
    run_id = f"{now.strftime('%Y%m%dT%H%M%S.%fZ')}-{uuid.uuid4().hex[:12]}"
    origin = _safe_component(base["origin_observation_id"], "observation ID")
    source_key = _safe_component(base["source"]["key"], "source key")
    destination = output_root / source_key / origin / run_id
    _ensure_outside([diagnosis_root, base_root], destination)
    destination.parent.mkdir(parents=True, exist_ok=True)
    staging = Path(tempfile.mkdtemp(prefix=".staging-", dir=destination.parent))
    try:
        finalized = copy.deepcopy(draft)
        (staging / "decision.json").write_bytes(canonical_json(finalized))
        artifacts = []
        revision_id = None
        transformation = None
        if state == "APPROVED":
            prepared_payload = _apply_edits(
                base["payload"], expected["forward_edits"]
            )
            document_bytes, markdown_bytes = _prepared_bytes(prepared_payload)
            revision_id = _hash(
                canonical_json(
                    {
                        "parent": base["subject_id"],
                        "base_sha256": _hash(base["document_bytes"]),
                        "draft_id": expected["draft_id"],
                        "prepared_sha256": _hash(document_bytes),
                    }
                ).rstrip(b"\n")
            )
            transformation = {
                "transformation_id": _hash(
                    canonical_json(
                        {
                            "revision_id": revision_id,
                            "draft_id": expected["draft_id"],
                            "refiner": expected["refiner"],
                        }
                    ).rstrip(b"\n")
                ),
                "state": "APPLIED",
                "parent": {
                    "kind": base["kind"],
                    "subject_id": base["subject_id"],
                    "canonical_document_sha256": _hash(base["document_bytes"]),
                },
                "revision_id": revision_id,
                "finding_id": expected["finding"]["finding_id"],
                "decision_id": expected["draft_id"],
                "decided_by": draft["decision"]["decided_by"],
                "refiner": expected["refiner"],
                "affected_refs": expected["affected_refs"],
                "forward_edits": expected["forward_edits"],
                "inverse_edits": expected["inverse_edits"],
                "base_document_base64": base64.b64encode(base["document_bytes"]).decode(),
                "prepared_document_sha256": _hash(document_bytes),
            }
            history = {
                "schema_version": "tcw.transformation-history/v0.3",
                "origin_observation_id": base["origin_observation_id"],
                "revision_id": revision_id,
                "transformations": [*base["history"], transformation],
            }
            (staging / "prepared").mkdir()
            (staging / "prepared/document.json").write_bytes(document_bytes)
            (staging / "prepared/document.md").write_bytes(markdown_bytes)
            (staging / "transformation.json").write_bytes(canonical_json(transformation))
            (staging / "history.json").write_bytes(canonical_json(history))
            _validate("transformation-history-v0.3.schema.json", history)
        runtime = active_locked_runtime()
        manifest = {
            "schema_version": "tcw.refinement-manifest/v0.3",
            "milestone": "v0.3",
            "run_id": run_id,
            "created_at": now.isoformat().replace("+00:00", "Z"),
            "status": "APPLIED" if state == "APPROVED" else "REJECTED",
            "revision_id": revision_id,
            "origin_observation_id": base["origin_observation_id"],
            "origin_observation_run_id": base["origin_observation_run_id"],
            "source": base["source"],
            "base": {
                "kind": base["kind"],
                "subject_id": base["subject_id"],
                "canonical_document_path": base["document_path"],
                "canonical_document_size": len(base["document_bytes"]),
                "canonical_document_sha256": _hash(base["document_bytes"]),
            },
            "diagnosis_id": expected["diagnosis_id"],
            "draft_id": expected["draft_id"],
            "runtime": runtime,
            "artifacts": [],
        }
        (staging / "report.md").write_bytes(_render_refinement(manifest, finalized))
        role_map = {
            "decision.json": ("refinement-decision", "application/json"),
            "report.md": ("refinement-report", "text/markdown"),
            "transformation.json": ("transformation", "application/json"),
            "history.json": ("transformation-history", "application/json"),
            "prepared/document.json": ("prepared-document-json", "application/json"),
            "prepared/document.md": ("prepared-document-markdown", "text/markdown"),
        }
        for relative, (role, media_type) in role_map.items():
            path = staging / relative
            if path.is_file():
                artifacts.append(_artifact(path, staging, role, media_type))
        manifest["artifacts"] = artifacts
        (staging / "refinement-manifest.json").write_bytes(canonical_json(manifest))
        _validate("refinement-manifest-v0.3.schema.json", manifest)
        if snapshot_tree(diagnosis_root) != diagnosis_before or snapshot_tree(base_root) != base_before or _file_identity(decision_file) != decision_before:
            raise IntegrityError("refinement input changed during resolution")
        return _publish_directory(staging, destination)
    finally:
        if staging.exists():
            import shutil

            shutil.rmtree(staging)


def _inventory(root: Path) -> tuple[set[str], set[str], list[dict[str, Any]]]:
    files: set[str] = set()
    directories: set[str] = set()
    issues = []
    try:
        for path in sorted(root.rglob("*")):
            relative = path.relative_to(root).as_posix()
            mode = path.lstat().st_mode
            if stat.S_ISLNK(mode) or not (stat.S_ISREG(mode) or stat.S_ISDIR(mode)):
                issues.append({"code": "FILE_KIND_INVALID", "path": relative, "message": "path kind is invalid"})
            elif stat.S_ISREG(mode):
                files.add(relative)
            else:
                directories.add(relative)
    except OSError:
        issues.append({"code": "INVENTORY_INVALID", "path": None, "message": "directory inventory is unreadable"})
    return files, directories, issues


def verify_diagnosis(root: Path, subject_root: Path | None = None) -> dict[str, Any]:
    active_locked_runtime()
    files, directories, issues = _inventory(root)
    expected = {"diagnosis-manifest.json", "findings.json", "report.md"}
    for path in sorted(expected - files):
        issues.append({"code": "FILE_MISSING", "path": path, "message": "expected file is missing"})
    for path in sorted(files - expected):
        issues.append({"code": "FILE_UNEXPECTED", "path": path, "message": "file is not expected"})
    for path in sorted(directories):
        issues.append({"code": "DIRECTORY_UNEXPECTED", "path": path, "message": "directory is not expected"})
    manifest = findings = None
    try:
        _, manifest = _load_json_regular(root / "diagnosis-manifest.json", "manifest")
        _, findings = _load_json_regular(root / "findings.json", "findings")
        _validate("diagnosis-manifest-v0.3.schema.json", manifest)
        _validate("finding-set-v0.3.schema.json", findings)
        validate_finding_set(findings)
        if root.name != manifest["run_id"] or findings["diagnosis_id"] != manifest["diagnosis_id"]:
            raise IntegrityError("diagnosis identity differs")
        if (
            manifest["subject"] != findings["subject"]
            or manifest["summary"] != findings["summary"]
            or manifest["ruleset"] != {**RULESET, "parameter_sha256": RULESET_PARAMETER_HASH}
            or manifest["status"]
            != ("FINDINGS" if findings["summary"]["total"] else "NO_FINDINGS")
        ):
            raise IntegrityError("diagnosis references differ")
        if (root / "findings.json").read_bytes() != canonical_json(findings):
            raise IntegrityError("findings are not canonical")
        if (root / "report.md").read_bytes() != _diagnosis_report(findings):
            issues.append({"code": "REPORT_INVALID", "path": "report.md", "message": "report differs"})
        for descriptor in manifest["artifacts"]:
            path = root / descriptor["path"]
            if path.stat().st_size != descriptor["size"] or sha256_file(path) != descriptor["sha256"]:
                issues.append({"code": "HASH_MISMATCH", "path": descriptor["path"], "message": "descriptor differs"})
    except (InputError, IntegrityError, OSError, KeyError, TypeError):
        issues.append({"code": "MANIFEST_INVALID", "path": "diagnosis-manifest.json", "message": "diagnosis contract is invalid"})
    subject_state = {"status": "NOT_CHECKED"}
    derivation_state = {"status": "NOT_CHECKED"}
    if subject_root is not None and manifest is not None and findings is not None:
        if not subject_root.exists():
            subject_state = {"status": "MISSING"}
        else:
            try:
                subject = load_subject(subject_root)
                matches = (
                    subject["subject_id"] == manifest["subject"]["subject_id"]
                    and _hash(subject["document_bytes"]) == manifest["subject"]["canonical_document_sha256"]
                )
                subject_state = {"status": "MATCH" if matches else "CHANGED"}
                if matches:
                    expected_findings = make_finding_set(subject)
                    derivation_state = {"status": "MATCH" if expected_findings == findings else "MISMATCH"}
            except RuntimeContractError:
                raise
            except Exception:
                subject_state = {"status": "ERROR"}
    status = "VERIFIED" if not issues else ("BROKEN" if any(item["code"] == "MANIFEST_INVALID" for item in issues) else "INTEGRITY_MISMATCH")
    result = {
        "schema_version": "tcw.diagnosis-verification-result/v0.3",
        "diagnosis_directory": str(root.resolve()),
        "artifact_integrity": {"status": status, "issues": issues},
        "subject_state": subject_state,
        "derivation_state": derivation_state,
    }
    _validate("diagnosis-verification-result-v0.3.schema.json", result)
    return result


def verify_diagnosis_command(root: Path, subject_root: Path | None) -> int:
    if root.is_symlink() or not root.is_dir():
        print("DIAGNOSIS_DIRECTORY must be one local non-symlink directory", file=sys.stderr)
        return 2
    try:
        report = verify_diagnosis(root, subject_root)
    except RuntimeContractError as error:
        print(sanitize_message(error), file=sys.stderr)
        return 6
    except Exception as error:
        print(f"internal diagnosis verifier failure: {sanitize_message(error)}", file=sys.stderr)
        return 1
    print(json.dumps(report, ensure_ascii=False, sort_keys=True, separators=(",", ":")))
    return 0 if report["artifact_integrity"]["status"] == "VERIFIED" else 5


def verify_refinement(
    root: Path,
    diagnosis_root: Path | None = None,
    base_root: Path | None = None,
) -> dict[str, Any]:
    active_locked_runtime()
    files, directories, issues = _inventory(root)
    manifest = decision = None
    try:
        _, manifest = _load_json_regular(root / "refinement-manifest.json", "manifest")
        _, decision = _load_json_regular(root / "decision.json", "decision")
        _validate("refinement-manifest-v0.3.schema.json", manifest)
        _validate("refinement-draft-v0.3.schema.json", decision)
        expected = {"refinement-manifest.json", *[item["path"] for item in manifest["artifacts"]]}
        for path in sorted(expected - files):
            issues.append({"code": "FILE_MISSING", "path": path, "message": "expected file is missing"})
        for path in sorted(files - expected):
            issues.append({"code": "FILE_UNEXPECTED", "path": path, "message": "file is not expected"})
        allowed_dirs = {"prepared"} if manifest["status"] == "APPLIED" else set()
        for path in sorted(directories - allowed_dirs):
            issues.append({"code": "DIRECTORY_UNEXPECTED", "path": path, "message": "directory is not expected"})
        for descriptor in manifest["artifacts"]:
            path = root / descriptor["path"]
            if path.is_file() and (
                path.stat().st_size != descriptor["size"]
                or sha256_file(path) != descriptor["sha256"]
            ):
                issues.append({"code": "HASH_MISMATCH", "path": descriptor["path"], "message": "descriptor differs"})
        if root.name != manifest["run_id"] or decision["proposal"]["draft_id"] != manifest["draft_id"]:
            raise IntegrityError("refinement identity differs")
    except (InputError, IntegrityError, OSError, KeyError, TypeError):
        issues.append({"code": "MANIFEST_INVALID", "path": "refinement-manifest.json", "message": "refinement contract is invalid"})
    diagnosis_state = {"status": "NOT_CHECKED"}
    base_state = {"status": "NOT_CHECKED"}
    derivation = {"status": "NOT_APPLICABLE" if manifest and manifest.get("status") == "REJECTED" else "NOT_CHECKED"}
    reversibility = dict(derivation)
    if diagnosis_root is not None and manifest is not None:
        try:
            _, diagnosis_manifest = _load_json_regular(diagnosis_root / "diagnosis-manifest.json", "diagnosis")
            diagnosis_state = {"status": "MATCH" if diagnosis_manifest["diagnosis_id"] == manifest["diagnosis_id"] else "CHANGED"}
        except Exception:
            diagnosis_state = {"status": "MISSING" if not diagnosis_root.exists() else "ERROR"}
    if base_root is not None and manifest is not None:
        try:
            base = load_subject(base_root)
            matches = base["subject_id"] == manifest["base"]["subject_id"] and _hash(base["document_bytes"]) == manifest["base"]["canonical_document_sha256"]
            base_state = {"status": "MATCH" if matches else "CHANGED"}
            if matches and manifest["status"] == "APPLIED":
                _, transformation = _load_json_regular(root / "transformation.json", "transformation")
                forward = _apply_edits(base["payload"], transformation["forward_edits"])
                forward_bytes, _ = _prepared_bytes(forward)
                prepared = (root / "prepared/document.json").read_bytes()
                derivation = {"status": "MATCH" if forward_bytes == prepared else "MISMATCH"}
                inverse_bytes = base64.b64decode(transformation["base_document_base64"], validate=True)
                reversibility = {"status": "MATCH" if inverse_bytes == base["document_bytes"] else "MISMATCH"}
        except RuntimeContractError:
            raise
        except Exception:
            base_state = {"status": "ERROR"}
            derivation = {"status": "ERROR"} if manifest.get("status") == "APPLIED" else derivation
            reversibility = {"status": "ERROR"} if manifest.get("status") == "APPLIED" else reversibility
    status = "VERIFIED" if not issues else ("BROKEN" if any(item["code"] == "MANIFEST_INVALID" for item in issues) else "INTEGRITY_MISMATCH")
    result = {
        "schema_version": "tcw.refinement-verification-result/v0.3",
        "refinement_directory": str(root.resolve()),
        "artifact_integrity": {"status": status, "issues": issues},
        "diagnosis_state": diagnosis_state,
        "base_state": base_state,
        "derivation_state": derivation,
        "reversibility_state": reversibility,
    }
    _validate("refinement-verification-result-v0.3.schema.json", result)
    return result


def verify_refinement_command(
    root: Path, diagnosis_root: Path | None, base_root: Path | None
) -> int:
    if root.is_symlink() or not root.is_dir():
        print("REFINEMENT_DIRECTORY must be one local non-symlink directory", file=sys.stderr)
        return 2
    try:
        report = verify_refinement(root, diagnosis_root, base_root)
    except RuntimeContractError as error:
        print(sanitize_message(error), file=sys.stderr)
        return 6
    except Exception as error:
        print(f"internal refinement verifier failure: {sanitize_message(error)}", file=sys.stderr)
        return 1
    print(json.dumps(report, ensure_ascii=False, sort_keys=True, separators=(",", ":")))
    return 0 if report["artifact_integrity"]["status"] == "VERIFIED" else 5
