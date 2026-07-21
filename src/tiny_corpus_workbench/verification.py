from __future__ import annotations

import hashlib
import json
import re
import stat
import sys
from datetime import date
from pathlib import Path, PurePosixPath
from typing import Any

from jsonschema import Draft202012Validator, FormatChecker

from tiny_corpus_workbench.artifacts import (
    REQUIRED_MODEL_FILES,
    canonical_json,
    compute_observation_id,
    inventory_models,
)
from tiny_corpus_workbench.comparison import make_comparison
from tiny_corpus_workbench.domain import (
    DOCLING_DOCUMENT_COMPATIBILITY,
    RuntimeContractError,
    sanitize_message,
)
from tiny_corpus_workbench.runtime import RUNTIME_DEPENDENCIES
from tiny_corpus_workbench.source import sha256_file


SCHEMA_ROOT = Path(__file__).with_name("schemas")
RFC3339_DATE_TIME = re.compile(
    r"^(\d{4})-(\d{2})-(\d{2})[Tt](\d{2}):(\d{2}):(\d{2})"
    r"(?:\.\d+)?(?:[Zz]|[+-](\d{2}):(\d{2}))$"
)
FORMAT_CHECKER = FormatChecker()
BROKEN_CODES = {
    "MANIFEST_MISSING",
    "MANIFEST_INVALID",
    "SCHEMA_UNSUPPORTED",
    "SCHEMA_INVALID",
    "RUN_ID_MISMATCH",
    "OBSERVATION_ID_MISMATCH",
    "UNSAFE_REFERENCE",
    "REFERENCE_MISMATCH",
    "STATUS_MISMATCH",
    "COMPARISON_INVALID",
}


@FORMAT_CHECKER.checks("date-time")
def _is_rfc3339_date_time(value: object) -> bool:
    if not isinstance(value, str):
        return True
    match = RFC3339_DATE_TIME.fullmatch(value)
    if match is None:
        return False
    year, month, day, hour, minute, second, offset_hour, offset_minute = (
        int(part) if part is not None else 0 for part in match.groups()
    )
    try:
        date(year, month, day)
    except ValueError:
        return False
    return (
        hour <= 23
        and minute <= 59
        and second <= 60
        and offset_hour <= 23
        and offset_minute <= 59
    )


def _schema(name: str) -> dict[str, Any]:
    try:
        value = json.loads((SCHEMA_ROOT / name).read_text("utf-8"))
        Draft202012Validator.check_schema(value)
        return value
    except Exception as error:
        raise RuntimeContractError("bundled verification schema is unavailable") from error


def _validator(schema: dict[str, Any]) -> Draft202012Validator:
    return Draft202012Validator(schema, format_checker=FORMAT_CHECKER)


def _issue(code: str, path: str | None, message: str) -> dict[str, Any]:
    return {"code": code, "path": path, "message": sanitize_message(message)}


def _safe_relative(value: Any) -> str | None:
    if not isinstance(value, str):
        return None
    path = PurePosixPath(value)
    if path.is_absolute() or not path.parts or ".." in path.parts:
        return None
    return path.as_posix()


def _advisory_source(source: Path | None, recorded: dict[str, Any] | None) -> dict[str, str]:
    if source is None:
        return {"status": "NOT_CHECKED"}
    try:
        if source.is_symlink():
            return {"status": "ERROR"}
        metadata = source.stat()
        if not stat.S_ISREG(metadata.st_mode):
            return {"status": "ERROR"}
        if recorded is None:
            return {"status": "ERROR"}
        current = (metadata.st_size, sha256_file(source))
        expected = (recorded["size"], recorded["sha256"])
        return {"status": "MATCH" if current == expected else "CHANGED"}
    except FileNotFoundError:
        return {"status": "MISSING"}
    except (OSError, KeyError, TypeError):
        return {"status": "ERROR"}


def _advisory_models(
    model_root: Path | None, recorded: dict[str, Any] | None
) -> dict[str, str]:
    if model_root is None:
        return {"status": "NOT_CHECKED"}
    if recorded is not None and not recorded.get("required"):
        return {"status": "NOT_APPLICABLE"}
    if not model_root.exists() and not model_root.is_symlink():
        return {"status": "MISSING"}
    if recorded is None:
        return {"status": "ERROR"}
    try:
        current = inventory_models(model_root, required=True)
    except RuntimeContractError:
        return {"status": "ERROR"}
    same_inventory = (
        current["inventory_hash"] == recorded.get("inventory_hash")
        and current["files"] == recorded.get("files")
    )
    return {"status": "MATCH" if same_inventory else "CHANGED"}


def _expected_statuses(manifest: dict[str, Any]) -> tuple[str, str]:
    statuses = [result["status"] for result in manifest["extractors"]]
    if statuses == ["SUCCESS", "SUCCESS"]:
        overall = "SUCCESS"
    elif statuses == ["FAILED", "FAILED"]:
        overall = "FAILED"
    else:
        overall = "PARTIAL_SUCCESS"
    usable = sum(status in ("SUCCESS", "PARTIAL_SUCCESS") for status in statuses)
    comparison = "COMPLETE" if usable == 2 else "INCOMPLETE" if usable == 1 else "NOT_AVAILABLE"
    return overall, comparison


EXPECTED_ARTIFACTS = {
    "docling": (
        ("docling/document.json", "docling-document-json", "application/json"),
        ("docling/document.md", "docling-markdown", "text/markdown"),
    ),
    "markitdown": (
        ("markitdown/document.md", "markitdown-markdown", "text/markdown"),
    ),
}


def _manifest_contract_issues(manifest: dict[str, Any]) -> list[dict[str, Any]]:
    """Check cross-field contracts that JSON Schema cannot express safely."""

    issues: list[dict[str, Any]] = []
    dependencies = manifest["runtime"]["dependencies"]
    runtime = manifest["runtime"]
    if runtime["implementation"] != "CPython" or re.fullmatch(
        r"3\.12(?:\.\d+)?(?:[a-z]+\d*)?", runtime["python"]
    ) is None:
        issues.append(
            _issue(
                "REFERENCE_MISMATCH",
                "manifest.json",
                "recorded Python runtime differs from the fixed CPython 3.12 contract",
            )
        )
    if dependencies != RUNTIME_DEPENDENCIES:
        issues.append(
            _issue(
                "REFERENCE_MISMATCH",
                "manifest.json",
                "recorded dependencies differ from the fixed runtime contract",
            )
        )
    results = {result["name"]: result for result in manifest["extractors"]}
    for name, result in results.items():
        if result["version"] != dependencies[name]:
            issues.append(
                _issue(
                    "REFERENCE_MISMATCH",
                    "manifest.json",
                    f"{name} version differs from runtime dependency",
                )
            )

        expected_artifacts = (
            EXPECTED_ARTIFACTS[name]
            if result["status"] in ("SUCCESS", "PARTIAL_SUCCESS")
            else ()
        )
        actual_artifacts = tuple(
            (item["path"], item["role"], item["media_type"])
            for item in result["artifacts"]
        )
        if len(actual_artifacts) != len(expected_artifacts) or set(
            actual_artifacts
        ) != set(expected_artifacts):
            issues.append(
                _issue(
                    "REFERENCE_MISMATCH",
                    "manifest.json",
                    f"{name} artifact contract is inconsistent",
                )
            )

    docling = results["docling"]
    expected_upstream = {
        "SUCCESS": "success",
        "PARTIAL_SUCCESS": "partial_success",
        "FAILED": None,
    }[docling["status"]]
    if docling["upstream_status"] != expected_upstream:
        issues.append(
            _issue(
                "STATUS_MISMATCH",
                "manifest.json",
                "Docling upstream and extractor statuses disagree",
            )
        )
    document_schema = manifest["docling_document_schema"]
    if docling["status"] == "FAILED":
        if any(document_schema[key] is not None for key in ("name", "version", "compatibility")):
            issues.append(
                _issue(
                    "REFERENCE_MISMATCH",
                    "manifest.json",
                    "failed Docling result must not claim document schema identity",
                )
            )
    elif (
        document_schema["name"] is None
        or document_schema["version"] is None
        or document_schema["compatibility"] != DOCLING_DOCUMENT_COMPATIBILITY
    ):
        issues.append(
            _issue(
                "REFERENCE_MISMATCH",
                "manifest.json",
                "usable Docling result requires its exact schema compatibility identity",
            )
        )
    markitdown = results["markitdown"]
    if markitdown["status"] == "PARTIAL_SUCCESS" or markitdown["upstream_status"] is not None:
        issues.append(
            _issue(
                "STATUS_MISMATCH",
                "manifest.json",
                "MarkItDown status contract is inconsistent",
            )
        )

    is_pdf = manifest["source"]["media_type"] == "application/pdf"
    models = manifest["models"]
    if models["required"] != is_pdf:
        issues.append(
            _issue(
                "STATUS_MISMATCH",
                "manifest.json",
                "model applicability differs from source media type",
            )
        )
    model_error_codes = {"MODEL_ARTIFACTS_MISSING", "MODEL_ARTIFACTS_INVALID"}
    docling_error = docling["error"]
    has_model_error = (
        docling_error is not None and docling_error["code"] in model_error_codes
    )
    inventory_available = bool(models["files"]) and models["inventory_hash"] is not None
    expected_model_error = is_pdf and not inventory_available
    if has_model_error != expected_model_error:
        issues.append(
            _issue(
                "STATUS_MISMATCH",
                "manifest.json",
                "model inventory and Docling runtime state disagree",
            )
        )
    if not is_pdf and (models["files"] or models["inventory_hash"] is not None):
        issues.append(
            _issue(
                "REFERENCE_MISMATCH",
                "manifest.json",
                "non-PDF observation contains a model inventory",
            )
        )
    model_paths = {item["path"] for item in models["files"]}
    if any(_safe_relative(path) is None for path in model_paths):
        issues.append(
            _issue(
                "UNSAFE_REFERENCE",
                "manifest.json",
                "model inventory contains an unsafe path",
            )
        )
    if is_pdf and inventory_available and not set(REQUIRED_MODEL_FILES).issubset(
        model_paths
    ):
        issues.append(
            _issue(
                "REFERENCE_MISMATCH",
                "manifest.json",
                "PDF model inventory omits required artifacts",
            )
        )

    allowed_errors = {
        "docling": {
            "MODEL_ARTIFACTS_MISSING",
            "MODEL_ARTIFACTS_INVALID",
            "DOCLING_CONVERSION_FAILED",
            "DOCLING_SERIALIZATION_FAILED",
        },
        "markitdown": {"MARKITDOWN_CONVERSION_FAILED"},
    }
    for name, result in results.items():
        error = result["error"]
        if error is not None and error["code"] not in allowed_errors[name]:
            issues.append(
                _issue(
                    "STATUS_MISMATCH",
                    "manifest.json",
                    f"{name} error code is inconsistent",
                )
            )
    return issues


def _docling_document_schema_issues(
    root: Path,
    manifest: dict[str, Any],
    actual_files: set[str],
) -> list[dict[str, Any]]:
    result = manifest["extractors"][0]
    if result["status"] == "FAILED":
        return []
    descriptor = next(
        (
            item
            for item in result["artifacts"]
            if item["role"] == "docling-document-json"
        ),
        None,
    )
    if descriptor is None or descriptor["path"] not in actual_files:
        return []
    path = root / descriptor["path"]
    try:
        mode = path.lstat().st_mode
        if stat.S_ISLNK(mode) or not stat.S_ISREG(mode):
            return []
        raw = path.read_bytes()
    except OSError:
        return []
    if (
        len(raw) != descriptor["size"]
        or hashlib.sha256(raw).hexdigest() != descriptor["sha256"]
    ):
        return []
    try:
        document = json.loads(raw)
    except (UnicodeError, json.JSONDecodeError):
        return [
            _issue(
                "SCHEMA_INVALID",
                descriptor["path"],
                "Docling document schema identity cannot be read",
            )
        ]
    if not isinstance(document, dict) or not isinstance(
        document.get("schema_name"), str
    ) or not isinstance(document.get("version"), str):
        return [
            _issue(
                "SCHEMA_INVALID",
                descriptor["path"],
                "Docling document schema identity is invalid",
            )
        ]
    recorded = manifest["docling_document_schema"]
    if (
        recorded["name"] != document["schema_name"]
        or recorded["version"] != document["version"]
    ):
        return [
            _issue(
                "REFERENCE_MISMATCH",
                descriptor["path"],
                "Docling document schema identity differs from the manifest",
            )
        ]
    return []


def verify_observation(
    root: Path,
    source: Path | None = None,
    model_root: Path | None = None,
) -> dict[str, Any]:
    manifest_schema = _schema("preparation-manifest-v0.1.schema.json")
    comparison_schema = _schema("comparison-summary-v0.1.schema.json")
    result_schema = _schema("verification-result-v0.1.schema.json")
    issues: list[dict[str, Any]] = []
    manifest: dict[str, Any] | None = None
    manifest_path = root / "manifest.json"

    try:
        mode = manifest_path.lstat().st_mode
        if not stat.S_ISREG(mode) or stat.S_ISLNK(mode):
            issues.append(_issue("MANIFEST_INVALID", "manifest.json", "manifest is not a regular file"))
        else:
            manifest = json.loads(manifest_path.read_text("utf-8"))
    except FileNotFoundError:
        issues.append(_issue("MANIFEST_MISSING", "manifest.json", "manifest is missing"))
    except (OSError, UnicodeError, json.JSONDecodeError):
        issues.append(_issue("MANIFEST_INVALID", "manifest.json", "manifest cannot be read as JSON"))

    if manifest is not None:
        if manifest.get("schema_version") != "tcw.preparation-manifest/v0.1":
            issues.append(_issue("SCHEMA_UNSUPPORTED", "manifest.json", "manifest schema is unsupported"))
        else:
            errors = list(_validator(manifest_schema).iter_errors(manifest))
            if errors:
                issues.append(_issue("MANIFEST_INVALID", "manifest.json", "manifest does not conform to its schema"))

    if manifest is not None and not any(issue["code"] in {"SCHEMA_UNSUPPORTED", "MANIFEST_INVALID"} for issue in issues):
        if root.name != manifest["run_id"]:
            issues.append(_issue("RUN_ID_MISMATCH", None, "directory basename does not match run_id"))
        computed_id = compute_observation_id(
            manifest["source"],
            manifest["runtime"]["dependencies"],
            manifest["configurations"],
            manifest["runtime"]["lockfile"]["sha256"],
            manifest["models"]["inventory_hash"],
        )
        if computed_id != manifest["observation_id"]:
            issues.append(_issue("OBSERVATION_ID_MISMATCH", None, "observation_id does not match recorded provenance"))
        issues.extend(_manifest_contract_issues(manifest))

        model_files = manifest["models"]["files"]
        if model_files != sorted(model_files, key=lambda item: item["path"]) or len({item["path"] for item in model_files}) != len(model_files):
            issues.append(_issue("REFERENCE_MISMATCH", None, "model inventory paths are not unique and sorted"))
        model_hash = hashlib.sha256(canonical_json(model_files).rstrip(b"\n")).hexdigest() if model_files else None
        if model_hash != manifest["models"]["inventory_hash"]:
            issues.append(_issue("REFERENCE_MISMATCH", None, "model inventory hash does not match descriptors"))

        expected: dict[str, dict[str, Any] | None] = {"manifest.json": None}
        descriptors = [
            artifact
            for result in manifest["extractors"]
            for artifact in result["artifacts"]
        ] + [manifest["comparison"]]
        for descriptor in descriptors:
            relative = _safe_relative(descriptor.get("path"))
            if relative is None:
                issues.append(_issue("UNSAFE_REFERENCE", None, "artifact reference is unsafe"))
            elif relative in expected:
                issues.append(_issue("UNSAFE_REFERENCE", relative, "artifact reference is duplicated"))
            else:
                expected[relative] = descriptor

        expected_directories: set[str] = set()
        for relative in expected:
            parent = PurePosixPath(relative).parent
            while parent != PurePosixPath("."):
                expected_directories.add(parent.as_posix())
                parent = parent.parent

        actual_files: set[str] = set()
        actual_directories: set[str] = set()
        try:
            for path in sorted(root.rglob("*")):
                relative = path.relative_to(root).as_posix()
                mode = path.lstat().st_mode
                if stat.S_ISLNK(mode) or not (stat.S_ISREG(mode) or stat.S_ISDIR(mode)):
                    issues.append(_issue("FILE_KIND_INVALID", relative, "path is not a regular file or directory"))
                elif stat.S_ISREG(mode):
                    actual_files.add(relative)
                else:
                    actual_directories.add(relative)
        except OSError:
            issues.append(_issue("FILE_KIND_INVALID", None, "observation tree cannot be read safely"))

        for relative in sorted(set(expected) - actual_files):
            if not any(issue["path"] == relative and issue["code"] == "FILE_KIND_INVALID" for issue in issues):
                issues.append(_issue("FILE_MISSING", relative, "expected file is missing"))
        for relative in sorted(actual_files - set(expected)):
            issues.append(_issue("FILE_UNEXPECTED", relative, "file is not referenced by the manifest"))
        for relative in sorted(actual_directories - expected_directories):
            issues.append(_issue("DIRECTORY_UNEXPECTED", relative, "directory is not implied by artifact references"))

        for relative, descriptor in expected.items():
            if descriptor is None or relative not in actual_files:
                continue
            path = root / relative
            try:
                size = path.stat().st_size
                digest = sha256_file(path)
                if size != descriptor["size"]:
                    issues.append(_issue("SIZE_MISMATCH", relative, "persisted size does not match"))
                if digest != descriptor["sha256"]:
                    issues.append(_issue("HASH_MISMATCH", relative, "persisted hash does not match"))
            except OSError:
                issues.append(_issue("FILE_KIND_INVALID", relative, "persisted file cannot be read"))

        issues.extend(_docling_document_schema_issues(root, manifest, actual_files))

        overall, comparison_status = _expected_statuses(manifest)
        if manifest["status"] != overall or manifest["comparison"]["status"] != comparison_status:
            issues.append(_issue("STATUS_MISMATCH", None, "manifest statuses are inconsistent"))
        for result in manifest["extractors"]:
            expected_count = 2 if result["name"] == "docling" else 1
            if result["status"] == "FAILED":
                if result["artifacts"] or result["error"] is None:
                    issues.append(_issue("STATUS_MISMATCH", None, f"{result['name']} failure evidence is inconsistent"))
            elif len(result["artifacts"]) != expected_count or result["error"] is not None:
                issues.append(_issue("STATUS_MISMATCH", None, f"{result['name']} success evidence is inconsistent"))

        comparison_path = root / manifest["comparison"]["path"]
        comparison: dict[str, Any] | None = None
        if manifest["comparison"]["path"] in actual_files:
            try:
                comparison_bytes = comparison_path.read_bytes()
                if (
                    len(comparison_bytes) != manifest["comparison"]["size"]
                    or hashlib.sha256(comparison_bytes).hexdigest()
                    != manifest["comparison"]["sha256"]
                ):
                    issues.append(
                        _issue(
                            "REFERENCE_MISMATCH",
                            "comparison.json",
                            "comparison descriptor differs from persisted bytes",
                        )
                    )
                comparison = json.loads(comparison_path.read_text("utf-8"))
                if list(_validator(comparison_schema).iter_errors(comparison)):
                    issues.append(_issue("COMPARISON_INVALID", "comparison.json", "comparison does not conform to its schema"))
                    comparison = None
            except (OSError, UnicodeError, json.JSONDecodeError):
                issues.append(_issue("COMPARISON_INVALID", "comparison.json", "comparison cannot be read as JSON"))
        if comparison is not None:
            if comparison["observation_id"] != manifest["observation_id"]:
                issues.append(_issue("REFERENCE_MISMATCH", "comparison.json", "comparison observation_id differs"))
            expected_source = {key: manifest["source"][key] for key in ("sha256", "media_type", "fixture_id")}
            if comparison["source"] != expected_source or comparison["status"] != manifest["comparison"]["status"]:
                issues.append(_issue("REFERENCE_MISMATCH", "comparison.json", "comparison source or status differs"))
            markdown_hashes = {
                result["name"]: next((item["sha256"] for item in result["artifacts"] if item["role"].endswith("markdown")), None)
                for result in manifest["extractors"]
            }
            for name in ("docling", "markitdown"):
                view = comparison["views"][name]
                if (view is None) != (markdown_hashes[name] is None) or (
                    view is not None and view["artifact_sha256"] != markdown_hashes[name]
                ):
                    issues.append(_issue("REFERENCE_MISMATCH", "comparison.json", f"{name} view reference differs"))
            markdown_views: dict[str, tuple[bytes, str] | None] = {}
            comparison_inputs_intact = True
            for result in manifest["extractors"]:
                descriptor = next(
                    (
                        item
                        for item in result["artifacts"]
                        if item["role"].endswith("markdown")
                    ),
                    None,
                )
                if descriptor is None:
                    markdown_views[result["name"]] = None
                    continue
                relative = _safe_relative(descriptor["path"])
                if relative is None or relative not in actual_files:
                    markdown_views[result["name"]] = None
                    comparison_inputs_intact = False
                    continue
                try:
                    raw = (root / relative).read_bytes()
                except OSError:
                    markdown_views[result["name"]] = None
                    comparison_inputs_intact = False
                    continue
                if (
                    len(raw) != descriptor["size"]
                    or hashlib.sha256(raw).hexdigest() != descriptor["sha256"]
                ):
                    markdown_views[result["name"]] = None
                    comparison_inputs_intact = False
                    continue
                markdown_views[result["name"]] = (raw, descriptor["sha256"])
            if comparison_inputs_intact and all(
                name in markdown_views for name in ("docling", "markitdown")
            ):
                try:
                    expected_comparison = make_comparison(
                        manifest["observation_id"],
                        manifest["source"],
                        comparison["anchors"],
                        markdown_views["docling"],
                        markdown_views["markitdown"],
                    )
                except UnicodeError:
                    expected_comparison = None
                if expected_comparison != comparison:
                    issues.append(
                        _issue(
                            "COMPARISON_INVALID",
                            "comparison.json",
                            "comparison views do not match persisted Markdown",
                        )
                    )

    artifact_status = "VERIFIED"
    if issues:
        artifact_status = "BROKEN" if any(issue["code"] in BROKEN_CODES for issue in issues) else "INTEGRITY_MISMATCH"
    report = {
        "schema_version": "tcw.verification-result/v0.1",
        "observation_directory": str(root.resolve()),
        "artifact_integrity": {"status": artifact_status, "issues": issues},
        "source_state": _advisory_source(source, manifest.get("source") if manifest else None),
        "model_state": _advisory_models(model_root, manifest.get("models") if manifest else None),
    }
    _validator(result_schema).validate(report)
    return report


def verify_command(
    root: Path, source: Path | None, model_root: Path | None
) -> int:
    if root.is_symlink() or not root.is_dir():
        print("OBSERVATION_DIRECTORY must be one local non-symlink directory", file=sys.stderr)
        return 2
    try:
        report = verify_observation(root, source, model_root)
    except RuntimeContractError as error:
        print(sanitize_message(error), file=sys.stderr)
        return 6
    except Exception as error:
        print(f"internal verifier failure: {sanitize_message(error)}", file=sys.stderr)
        return 1
    print(json.dumps(report, ensure_ascii=False, sort_keys=True, separators=(",", ":")))
    return 0 if report["artifact_integrity"]["status"] == "VERIFIED" else 5
