from __future__ import annotations

import hashlib
import json
import stat
import sys
from pathlib import Path
from typing import Any

from docling_core.types.doc import DoclingDocument
from jsonschema import Draft202012Validator
from referencing import Registry, Resource

from tiny_corpus_workbench.artifacts import canonical_json
from tiny_corpus_workbench.diagnosis import (
    RULESET_DESCRIPTOR,
    RULESET_PARAMETER_HASH,
    SCHEMA_ROOT,
    SUMMARY_BY_RULE,
    SEVERITY_BY_RULE,
    _summary,
    compute_diagnosis_id,
    make_finding_set,
    render_report,
    validate_finding_contract,
)
from tiny_corpus_workbench.domain import (
    IntegrityError,
    RuntimeContractError,
    sanitize_message,
)
from tiny_corpus_workbench.runtime import active_locked_runtime
from tiny_corpus_workbench.verification import FORMAT_CHECKER, verify_observation


def _issue(code: str, path: str | None, message: str) -> dict[str, Any]:
    return {"code": code, "path": path, "message": sanitize_message(message)}


def _validate_schema(name: str, value: object) -> bool:
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
        schema = schemas[name]
        Draft202012Validator.check_schema(schema)
        return not list(
            Draft202012Validator(
                schema, registry=registry, format_checker=FORMAT_CHECKER
            ).iter_errors(value)
        )
    except RuntimeContractError:
        raise
    except Exception as error:
        raise RuntimeContractError("bundled diagnosis schema is unavailable") from error


def _load_regular_json(
    root: Path,
    name: str,
    issues: list[dict[str, Any]],
) -> object | None:
    path = root / name
    try:
        mode = path.lstat().st_mode
        if stat.S_ISLNK(mode) or not stat.S_ISREG(mode):
            issues.append(_issue("FILE_KIND_INVALID", name, "file is not regular"))
            return None
        return json.loads(path.read_text("utf-8"))
    except FileNotFoundError:
        issues.append(_issue("FILE_MISSING", name, "file is missing"))
    except (OSError, UnicodeError, json.JSONDecodeError):
        issues.append(_issue("FILE_INVALID", name, "file cannot be read as JSON"))
    return None


def _observation_states(
    root: Path | None,
    manifest: dict[str, Any] | None,
    findings_bytes: bytes | None,
    report_bytes: bytes | None,
) -> tuple[dict[str, str], dict[str, str]]:
    if root is None:
        return {"status": "NOT_CHECKED"}, {"status": "NOT_CHECKED"}
    if not root.exists() and not root.is_symlink():
        return {"status": "MISSING"}, {"status": "NOT_CHECKED"}
    if root.is_symlink() or not root.is_dir() or manifest is None:
        return {"status": "ERROR"}, {"status": "NOT_CHECKED"}
    try:
        observation_report = verify_observation(root)
        if observation_report["artifact_integrity"]["status"] != "VERIFIED":
            return {"status": "ERROR"}, {"status": "NOT_CHECKED"}
        observation_bytes = (root / "manifest.json").read_bytes()
        observation = json.loads(observation_bytes)
        document_path = root / manifest["observation"]["canonical_document_path"]
        document_bytes = document_path.read_bytes()
        same = (
            manifest["source"]
            == {
                key: observation["source"][key]
                for key in ("key", "media_type", "size", "sha256")
            }
            and observation["run_id"] == manifest["observation"]["run_id"]
            and observation["observation_id"]
            == manifest["observation"]["observation_id"]
            and len(observation_bytes) == manifest["observation"]["manifest_size"]
            and hashlib.sha256(observation_bytes).hexdigest()
            == manifest["observation"]["manifest_sha256"]
            and len(document_bytes)
            == manifest["observation"]["canonical_document_size"]
            and hashlib.sha256(document_bytes).hexdigest()
            == manifest["observation"]["canonical_document_sha256"]
        )
        if not same:
            return {"status": "CHANGED"}, {"status": "NOT_CHECKED"}
    except RuntimeContractError:
        raise
    except Exception:
        return {"status": "ERROR"}, {"status": "NOT_CHECKED"}
    try:
        payload = json.loads(document_bytes)
        try:
            document = DoclingDocument.model_validate(payload)
            list(document.iterate_items(with_groups=True))
        except Exception as error:
            raise RuntimeContractError(
                "locked Docling runtime cannot traverse the canonical artifact"
            ) from error
        expected = make_finding_set(
            payload,
            observation,
            manifest_hash=manifest["observation"]["manifest_sha256"],
            document_hash=manifest["observation"]["canonical_document_sha256"],
        )
        expected_findings = canonical_json(expected)
        expected_report = render_report(expected)
        derivation = (
            "MATCH"
            if findings_bytes == expected_findings and report_bytes == expected_report
            else "MISMATCH"
        )
        return {"status": "MATCH"}, {"status": derivation}
    except RuntimeContractError:
        raise
    except Exception:
        return {"status": "MATCH"}, {"status": "ERROR"}


def verify_diagnosis(
    root: Path, observation_root: Path | None = None
) -> dict[str, Any]:
    active_runtime = active_locked_runtime()
    issues: list[dict[str, Any]] = []
    expected = {"diagnosis-manifest.json", "findings.json", "report.md"}
    actual: set[str] = set()
    directories: set[str] = set()
    try:
        for path in sorted(root.rglob("*")):
            relative = path.relative_to(root).as_posix()
            mode = path.lstat().st_mode
            if stat.S_ISLNK(mode) or not (stat.S_ISREG(mode) or stat.S_ISDIR(mode)):
                issues.append(_issue("FILE_KIND_INVALID", relative, "path kind is invalid"))
            elif stat.S_ISREG(mode):
                actual.add(relative)
            else:
                directories.add(relative)
    except OSError:
        issues.append(_issue("INVENTORY_INVALID", None, "directory inventory is unreadable"))
    for relative in sorted(expected - actual):
        if not any(item["path"] == relative for item in issues):
            issues.append(_issue("FILE_MISSING", relative, "expected file is missing"))
    for relative in sorted(actual - expected):
        issues.append(_issue("FILE_UNEXPECTED", relative, "file is not expected"))
    for relative in sorted(directories):
        issues.append(_issue("DIRECTORY_UNEXPECTED", relative, "directory is not expected"))

    manifest_value = _load_regular_json(root, "diagnosis-manifest.json", issues)
    findings_value = _load_regular_json(root, "findings.json", issues)
    manifest = manifest_value if isinstance(manifest_value, dict) else None
    findings = findings_value if isinstance(findings_value, dict) else None
    if manifest_value is not None and (
        manifest is None
        or not _validate_schema("diagnosis-manifest-v0.2.schema.json", manifest)
    ):
        issues.append(
            _issue("MANIFEST_INVALID", "diagnosis-manifest.json", "manifest schema is invalid")
        )
        manifest = None
    if findings_value is not None and (
        findings is None or not _validate_schema("finding-set-v0.2.schema.json", findings)
    ):
        issues.append(_issue("FINDINGS_INVALID", "findings.json", "finding schema is invalid"))
        findings = None

    findings_bytes: bytes | None = None
    report_bytes: bytes | None = None
    if "findings.json" in actual:
        try:
            findings_bytes = (root / "findings.json").read_bytes()
        except OSError:
            pass
    if "report.md" in actual:
        try:
            report_bytes = (root / "report.md").read_bytes()
        except OSError:
            issues.append(_issue("FILE_INVALID", "report.md", "report is unreadable"))

    if manifest is not None:
        try:
            manifest_bytes = (root / "diagnosis-manifest.json").read_bytes()
            if manifest_bytes != canonical_json(manifest):
                issues.append(
                    _issue(
                        "MANIFEST_INVALID",
                        "diagnosis-manifest.json",
                        "manifest JSON is not canonical",
                    )
                )
        except OSError:
            pass
        if root.name != manifest["run_id"]:
            issues.append(_issue("RUN_ID_MISMATCH", None, "directory basename differs"))
        if manifest["ruleset"] != {
            **RULESET_DESCRIPTOR,
            "parameter_sha256": RULESET_PARAMETER_HASH,
        }:
            issues.append(_issue("RULESET_MISMATCH", None, "ruleset provenance differs"))
        descriptor_map = {item["path"]: item for item in manifest["artifacts"]}
        if set(descriptor_map) != {"findings.json", "report.md"}:
            issues.append(_issue("REFERENCE_MISMATCH", None, "artifact references differ"))
        for relative, descriptor in descriptor_map.items():
            if relative not in actual:
                continue
            try:
                raw = (root / relative).read_bytes()
                if (
                    len(raw) != descriptor["size"]
                    or hashlib.sha256(raw).hexdigest() != descriptor["sha256"]
                ):
                    issues.append(_issue("HASH_MISMATCH", relative, "descriptor differs"))
            except OSError:
                issues.append(_issue("FILE_INVALID", relative, "file is unreadable"))
        expected_descriptors = {
            "findings.json": ("diagnostic-findings", "application/json"),
            "report.md": ("diagnostic-report", "text/markdown"),
        }
        if any(
            (descriptor["role"], descriptor["media_type"])
            != expected_descriptors.get(relative)
            for relative, descriptor in descriptor_map.items()
        ):
            issues.append(_issue("REFERENCE_MISMATCH", None, "artifact roles differ"))
        try:
            runtime_ok = (
                manifest["runtime"]["python"] == active_runtime["python"]
                and manifest["runtime"]["implementation"]
                == active_runtime["implementation"]
                and manifest["runtime"]["package_version"]
                == active_runtime["package_version"]
                and manifest["runtime"]["dependencies"]
                == active_runtime["dependencies"]
                and manifest["runtime"]["lockfile_sha256"]
                == active_runtime["lockfile_sha256"]
            )
        except (KeyError, TypeError):
            runtime_ok = False
        if not runtime_ok:
            issues.append(_issue("RUNTIME_MISMATCH", None, "runtime provenance differs"))
        expected_diagnosis_id = compute_diagnosis_id(
            manifest["observation"]["observation_id"],
            manifest["observation"]["manifest_sha256"],
            manifest["observation"]["canonical_document_sha256"],
        )
        if manifest["diagnosis_id"] != expected_diagnosis_id:
            issues.append(_issue("DIAGNOSIS_ID_MISMATCH", None, "diagnosis identity differs"))
    if manifest is not None and findings is not None:
        if findings_bytes != canonical_json(findings):
            issues.append(
                _issue(
                    "FINDINGS_INVALID",
                    "findings.json",
                    "finding JSON is not canonical",
                )
            )
        if (
            findings["diagnosis_id"] != manifest["diagnosis_id"]
            or findings["observation_id"] != manifest["observation"]["observation_id"]
            or findings["canonical_document_sha256"]
            != manifest["observation"]["canonical_document_sha256"]
            or findings["summary"] != manifest["summary"]
            or findings["ruleset"] != RULESET_DESCRIPTOR
        ):
            issues.append(_issue("REFERENCE_MISMATCH", "findings.json", "identities differ"))
        expected_status = "FINDINGS" if findings["summary"]["total"] else "NO_FINDINGS"
        if manifest["status"] != expected_status:
            issues.append(_issue("STATUS_MISMATCH", None, "status differs"))
        finding_ids = [item["finding_id"] for item in findings["findings"]]
        if len(finding_ids) != len(set(finding_ids)):
            issues.append(_issue("FINDINGS_INVALID", "findings.json", "finding IDs repeat"))
        if findings["summary"]["total"] != len(findings["findings"]):
            issues.append(_issue("STATUS_MISMATCH", "findings.json", "summary differs"))
        if findings["summary"] != _summary(findings["findings"]):
            issues.append(
                _issue("STATUS_MISMATCH", "findings.json", "summary counts differ")
            )
        expected_findings = []
        for finding in findings["findings"]:
            try:
                validate_finding_contract(finding)
            except IntegrityError:
                issues.append(
                    _issue(
                        "FINDINGS_INVALID",
                        "findings.json",
                        "rule-specific finding contract differs",
                    )
                )
            identity = {
                "diagnosis_id": findings["diagnosis_id"],
                "rule_id": finding["rule_id"],
                "rule_version": finding["rule_version"],
                "document_refs": finding["document_refs"],
                "evidence": finding["evidence"],
            }
            expected_id = hashlib.sha256(
                canonical_json(identity).rstrip(b"\n")
            ).hexdigest()
            if (
                finding["finding_id"] != expected_id
                or finding["severity"] != SEVERITY_BY_RULE[finding["rule_id"]]
                or finding["summary"]
                != SUMMARY_BY_RULE[finding["rule_id"]].replace("_", " ").title()
                or finding["document_refs"] != sorted(set(finding["document_refs"]))
                or list(finding["evidence"]) != sorted(finding["evidence"])
            ):
                issues.append(
                    _issue(
                        "FINDINGS_INVALID",
                        "findings.json",
                        "finding identity or canonical form differs",
                    )
                )
            expected_findings.append(finding)
        if expected_findings != sorted(
            expected_findings,
            key=lambda item: (
                item["rule_id"],
                item["document_refs"],
                canonical_json(item["evidence"]),
                item["finding_id"],
            ),
        ):
            issues.append(
                _issue("FINDINGS_INVALID", "findings.json", "finding order differs")
            )
        if report_bytes is not None and report_bytes != render_report(findings):
            issues.append(_issue("REPORT_INVALID", "report.md", "report does not match findings"))

    artifact_status = "VERIFIED" if not issues else "INTEGRITY_MISMATCH"
    if any(
        item["code"]
        in {
            "MANIFEST_INVALID",
            "FINDINGS_INVALID",
            "RUN_ID_MISMATCH",
            "DIAGNOSIS_ID_MISMATCH",
            "REFERENCE_MISMATCH",
            "RULESET_MISMATCH",
        }
        for item in issues
    ):
        artifact_status = "BROKEN"
    observation_state, derivation_state = _observation_states(
        observation_root, manifest, findings_bytes, report_bytes
    )
    result = {
        "schema_version": "tcw.diagnosis-verification-result/v0.2",
        "diagnosis_directory": str(root.resolve()),
        "artifact_integrity": {"status": artifact_status, "issues": issues},
        "observation_state": observation_state,
        "derivation_state": derivation_state,
    }
    if not _validate_schema("diagnosis-verification-result-v0.2.schema.json", result):
        raise RuntimeContractError("diagnosis verification result schema is incompatible")
    return result


def verify_diagnosis_command(root: Path, observation_root: Path | None) -> int:
    if root.is_symlink() or not root.is_dir():
        print("DIAGNOSIS_DIRECTORY must be one local non-symlink directory", file=sys.stderr)
        return 2
    try:
        report = verify_diagnosis(root, observation_root)
    except RuntimeContractError as error:
        print(sanitize_message(error), file=sys.stderr)
        return 6
    except Exception as error:
        print(f"internal diagnosis verifier failure: {sanitize_message(error)}", file=sys.stderr)
        return 1
    print(json.dumps(report, ensure_ascii=False, sort_keys=True, separators=(",", ":")))
    return 0 if report["artifact_integrity"]["status"] == "VERIFIED" else 5
