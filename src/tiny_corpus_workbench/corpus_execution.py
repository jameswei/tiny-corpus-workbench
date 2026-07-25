"""Internal sequential corpus evidence execution for milestone v0.4.

This module does not publish a corpus run and is not a public Python API.
The caller owns the private staging directory and the later publication step.
"""

from __future__ import annotations

import hashlib
import json
import os
import re
import stat
from collections import Counter, defaultdict
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Callable

from jsonschema import Draft202012Validator
from referencing import Registry, Resource

from tiny_corpus_workbench.artifacts import canonical_json, inventory_models
from tiny_corpus_workbench.comparison import NUMERIC_METRICS
from tiny_corpus_workbench.corpus import (
    AdmittedCorpusSpec,
    _directory,
    _tree_inventory,
)
from tiny_corpus_workbench.domain import (
    ExitCode,
    IntegrityError,
    RuntimeContractError,
    StableError,
)
from tiny_corpus_workbench.source import sha256_file


Observe = Callable[[str, Path, Path], tuple[ExitCode, Path]]
Diagnose = Callable[[Path, Path], Path]
RuntimeLoader = Callable[[], dict[str, Any]]
ModelInventoryLoader = Callable[..., dict[str, Any]]


@dataclass(frozen=True)
class CorpusExecutionResult:
    """Evidence prepared for the later corpus publication step."""

    snapshot_id: str
    status: str
    exit_code: ExitCode
    runtime: dict[str, Any]
    members: tuple[dict[str, Any], ...]
    revisions: tuple[dict[str, Any], ...]
    summary: dict[str, Any]
    input_capture: dict[str, Any]


def recheck_corpus_inputs(
    result: CorpusExecutionResult,
    *,
    model_inventory_loader: ModelInventoryLoader = inventory_models,
) -> None:
    """Require every captured external input to match immediately before publish."""

    capture = result.input_capture
    specification = capture["specification"]
    try:
        path = specification["path"]
        metadata = path.stat()
        signature = (
            metadata.st_dev,
            metadata.st_ino,
            metadata.st_size,
            metadata.st_mtime_ns,
            metadata.st_ctime_ns,
        )
        if (
            path.is_symlink()
            or not path.is_file()
            or signature != specification["signature"]
            or sha256_file(path) != specification["sha256"]
        ):
            raise OSError
    except OSError as error:
        raise IntegrityError(
            "corpus specification changed during corpus execution"
        ) from error

    for source in capture["sources"]:
        try:
            path = source["path"]
            metadata = path.stat()
            signature = (
                metadata.st_dev,
                metadata.st_ino,
                metadata.st_size,
                metadata.st_mtime_ns,
                metadata.st_ctime_ns,
            )
            if (
                path.is_symlink()
                or not path.is_file()
                or signature != source["signature"]
                or metadata.st_size != source["size"]
                or sha256_file(path) != source["sha256"]
            ):
                raise OSError
        except OSError as error:
            raise IntegrityError(
                "member source changed during corpus execution"
            ) from error

    for revision in capture["revision_inventories"]:
        try:
            current = {
                name: _tree_inventory(root, f"revision {name}")
                for name, root in revision["roots"].items()
            }
        except Exception as error:
            raise IntegrityError(
                "revision bundle changed during corpus execution"
            ) from error
        if current != revision["inventories"]:
            raise IntegrityError(
                "revision bundle changed during corpus execution"
            )

    model_identity = capture["model_identity"]
    model_root = capture["model_root"]
    _, current_model_identity = _model_capture(
        model_root,
        required=model_identity["required"],
        loader=model_inventory_loader,
    )
    if current_model_identity != model_identity:
        raise IntegrityError(
            "Docling model inventory changed during corpus execution"
        )


def _load_defaults() -> tuple[
    Observe,
    Diagnose,
    RuntimeLoader,
    dict[str, Any],
    dict[str, Any],
    dict[str, Any],
]:
    # Keep corpus behavior out of existing command import paths.
    try:
        from tiny_corpus_workbench.cli import (
            DOCLING_CONFIG,
            MARKITDOWN_CONFIG,
            _preflight_extractors,
            observe,
        )
        from tiny_corpus_workbench.runtime import active_locked_runtime
        from tiny_corpus_workbench.v03 import (
            RULESET,
            RULESET_PARAMETER_HASH,
            diagnose,
        )
    except Exception as error:
        raise RuntimeContractError(
            "bundled corpus execution runtime is unavailable"
        ) from error

    ruleset = {**RULESET, "parameter_sha256": RULESET_PARAMETER_HASH}

    def locked_corpus_runtime() -> dict[str, Any]:
        runtime = active_locked_runtime()
        lock, _, _ = _preflight_extractors()
        if (
            lock["sha256"] != runtime["lockfile_sha256"]
            or lock["dependencies"] != runtime["dependencies"]
        ):
            raise RuntimeContractError(
                "observation and diagnosis runtime identities do not match"
            )
        return runtime

    return (
        observe,
        diagnose,
        locked_corpus_runtime,
        dict(DOCLING_CONFIG),
        dict(MARKITDOWN_CONFIG),
        ruleset,
    )


def _schema_validator(name: str) -> Draft202012Validator:
    try:
        root = Path(__file__).with_name("schemas")
        schemas = {
            path.name: json.loads(path.read_text("utf-8"))
            for path in root.glob("*.schema.json")
        }
        registry = Registry()
        for schema in schemas.values():
            registry = registry.with_resource(
                schema["$id"], Resource.from_contents(schema)
            )
        Draft202012Validator.check_schema(schemas[name])
        return Draft202012Validator(schemas[name], registry=registry)
    except Exception as error:
        raise RuntimeContractError(
            "bundled corpus schema runtime is unavailable"
        ) from error


def _safe_staging_root(path: Path) -> Path:
    absolute = Path(os.path.abspath(os.fspath(path)))
    try:
        mode = absolute.lstat().st_mode
    except OSError as error:
        raise IntegrityError("corpus staging root is unavailable") from error
    if stat.S_ISLNK(mode) or not stat.S_ISDIR(mode):
        raise IntegrityError("corpus staging root must be one private directory")
    return absolute


def _inside(path: Path, root: Path, label: str) -> Path:
    absolute = Path(os.path.abspath(os.fspath(path)))
    try:
        relative = absolute.relative_to(root)
        current = root
        for component in relative.parts:
            current /= component
            mode = current.lstat().st_mode
            if stat.S_ISLNK(mode):
                raise IntegrityError(f"{label} contains a symbolic link")
        absolute.resolve(strict=True).relative_to(root.resolve(strict=True))
    except IntegrityError:
        raise
    except (OSError, ValueError) as error:
        raise IntegrityError(f"{label} escaped the corpus staging root") from error
    if not absolute.is_dir():
        raise IntegrityError(f"{label} is not one staged directory")
    return absolute


def _staged_directory(root: Path, *parts: str) -> Path:
    current = root
    for part in parts:
        current /= part
        try:
            current.mkdir()
        except FileExistsError:
            pass
        except OSError as error:
            raise IntegrityError("corpus member staging is unavailable") from error
        try:
            mode = current.lstat().st_mode
        except OSError as error:
            raise IntegrityError("corpus member staging is unavailable") from error
        if stat.S_ISLNK(mode) or not stat.S_ISDIR(mode):
            raise IntegrityError("corpus member staging contains an unsafe node")
    return current


def _read_json(path: Path, label: str) -> dict[str, Any]:
    try:
        if path.is_symlink() or not path.is_file():
            raise OSError
        value = json.loads(path.read_text("utf-8"))
    except (OSError, UnicodeError, ValueError) as error:
        raise IntegrityError(f"{label} is unavailable") from error
    if not isinstance(value, dict):
        raise IntegrityError(f"{label} is malformed")
    return value


def _descriptor(path: Path, staging_root: Path) -> dict[str, Any]:
    try:
        if path.is_symlink() or not path.is_file():
            raise OSError
        relative = path.relative_to(staging_root).as_posix()
        size = path.stat().st_size
        digest = sha256_file(path)
    except (OSError, ValueError) as error:
        raise IntegrityError("nested manifest is unavailable") from error
    return {"path": relative, "size": size, "sha256": digest}


def _safe_regular_file(root: Path, relative: str) -> bool:
    current = root
    try:
        for component in Path(relative).parts:
            current /= component
            mode = current.lstat().st_mode
            if stat.S_ISLNK(mode):
                return False
        return stat.S_ISREG(current.lstat().st_mode)
    except OSError:
        return False


def _extractor_artifacts_available(
    root: Path,
    manifest: dict[str, Any],
    name: str,
) -> bool:
    expected = {
        "docling": {"docling/document.json", "docling/document.md"},
        "markitdown": {"markitdown/document.md"},
    }[name]
    extractor = next(
        (
            item
            for item in manifest.get("extractors", [])
            if isinstance(item, dict) and item.get("name") == name
        ),
        None,
    )
    if extractor is None or not isinstance(extractor.get("artifacts"), list):
        return False
    descriptors = extractor["artifacts"]
    if (
        len(descriptors) != len(expected)
        or {
            item.get("path")
            for item in descriptors
            if isinstance(item, dict)
        }
        != expected
    ):
        return False
    for descriptor in descriptors:
        relative = descriptor["path"]
        path = root / relative
        try:
            if (
                not _safe_regular_file(root, relative)
                or type(descriptor.get("size")) is not int
                or not isinstance(descriptor.get("sha256"), str)
                or path.stat().st_size != descriptor["size"]
                or sha256_file(path) != descriptor["sha256"]
            ):
                return False
        except OSError:
            return False
    return True


def _source_capture(member: dict[str, Any]) -> dict[str, Any]:
    path = member["source_path"]
    try:
        mode = path.lstat().st_mode
        if stat.S_ISLNK(mode) or not stat.S_ISREG(mode):
            raise OSError
        before = path.stat()
        digest = sha256_file(path)
        after = path.stat()
    except OSError as error:
        raise IntegrityError(
            "member source became unavailable before execution"
        ) from error
    before_signature = (
        before.st_dev,
        before.st_ino,
        before.st_size,
        before.st_mtime_ns,
        before.st_ctime_ns,
    )
    after_signature = (
        after.st_dev,
        after.st_ino,
        after.st_size,
        after.st_mtime_ns,
        after.st_ctime_ns,
    )
    if (
        before_signature != after_signature
        or digest != member["source"]["sha256"]
        or after.st_size != member["source"]["size"]
    ):
        raise IntegrityError("member source changed before corpus execution")
    return {
        "path": path,
        "signature": after_signature,
        "size": after.st_size,
        "sha256": digest,
    }


def _specification_capture(admitted: AdmittedCorpusSpec) -> dict[str, Any]:
    path = admitted.path
    try:
        mode = path.lstat().st_mode
        if stat.S_ISLNK(mode) or not stat.S_ISREG(mode):
            raise OSError
        before = path.stat()
        digest = sha256_file(path)
        after = path.stat()
    except OSError as error:
        raise IntegrityError(
            "corpus specification became unavailable before execution"
        ) from error
    signature = (
        after.st_dev,
        after.st_ino,
        after.st_size,
        after.st_mtime_ns,
        after.st_ctime_ns,
    )
    if (
        before != after
        or after.st_size != admitted.specification_identity["size"]
        or digest != admitted.specification_identity["sha256"]
    ):
        raise IntegrityError("corpus specification changed before execution")
    return {
        "path": path,
        "signature": signature,
        "size": after.st_size,
        "sha256": digest,
    }


def _revision_captures(
    admitted: AdmittedCorpusSpec,
) -> tuple[dict[str, Any], ...]:
    captures = []
    for member in admitted.members:
        for revision in member["revisions"]:
            roots = {
                name: _directory(
                    admitted.path.parent / revision["bundle_paths"][name],
                    f"revision {name}",
                )
                for name in ("refinement", "diagnosis", "base")
            }
            current = {
                name: _tree_inventory(root, f"revision {name}")
                for name, root in roots.items()
            }
            if current != revision["inventories"]:
                raise IntegrityError("revision bundle changed before corpus execution")
            captures.append(
                {
                    "member_id": member["member_id"],
                    "revision_id": revision["revision_id"],
                    "roots": roots,
                    "inventories": current,
                }
            )
    return tuple(captures)


def _model_capture(
    model_root: Path,
    *,
    required: bool,
    loader: ModelInventoryLoader,
) -> tuple[dict[str, Any], dict[str, Any]]:
    try:
        inventory = loader(model_root, required=required)
        state = "AVAILABLE" if required else "NOT_REQUIRED"
    except RuntimeContractError:
        state = "INVALID" if model_root.exists() else "MISSING"
        inventory = {
            "required": required,
            "path": str(model_root.absolute()),
            "inventory_hash": None,
            "files": [],
        }
    manifest_value = {
        "required": required,
        "path": str(Path(os.path.abspath(os.fspath(model_root)))),
        "inventory_hash": inventory["inventory_hash"],
    }
    identity = {
        "state": state,
        "required": required,
        "inventory_hash": inventory["inventory_hash"],
        "files": inventory.get("files", []),
    }
    return manifest_value, identity


def _ruleset_id(ruleset: dict[str, Any]) -> str:
    return hashlib.sha256(canonical_json(ruleset).rstrip(b"\n")).hexdigest()


def _snapshot_identity(
    admitted: AdmittedCorpusSpec,
    runtime: dict[str, Any],
    configurations: dict[str, Any],
    ruleset: dict[str, Any],
    model_identity: dict[str, Any],
) -> tuple[str, dict[str, Any]]:
    members = []
    revisions = []
    for member in admitted.members:
        members.append(
            {
                "member_id": member["member_id"],
                "family": member["family"],
                "format": member["format"],
                "source": member["source"],
            }
        )
        for revision in member["revisions"]:
            revisions.append(
                {
                    key: revision[key]
                    for key in (
                        "revision_id",
                        "refinement_run_id",
                        "diagnosis_id",
                        "parent",
                        "source",
                        "chain_length",
                        "finding_id",
                        "finding_rule",
                        "refiner",
                        "affected_reference_count",
                        "prepared_document_sha256",
                        "inventory_fingerprints",
                    )
                }
            )
    identity = {
        "normalized_specification": admitted.normalized,
        "members": members,
        "runtime": runtime,
        "configurations": configurations,
        "ruleset": ruleset,
        "model_inventory": model_identity,
        "revisions": sorted(revisions, key=lambda item: item["revision_id"]),
    }
    snapshot_id = hashlib.sha256(
        canonical_json(identity).rstrip(b"\n")
    ).hexdigest()
    return snapshot_id, identity


def _error(code: str, message: str) -> dict[str, str]:
    return StableError(code, message).to_dict()


def _extractor_state(
    manifest: dict[str, Any], name: str
) -> tuple[bool, dict[str, Any] | None]:
    for extractor in manifest.get("extractors", []):
        if isinstance(extractor, dict) and extractor.get("name") == name:
            available = extractor.get("status") in {"SUCCESS", "PARTIAL_SUCCESS"}
            error = extractor.get("error")
            return available, error if isinstance(error, dict) else None
    return False, None


_EXTRACTOR_ERRORS = {
    "MODEL_ARTIFACTS_MISSING": "Required Docling model artifacts are missing",
    "MODEL_ARTIFACTS_INVALID": "Required Docling model artifacts are invalid",
    "DOCLING_SERIALIZATION_FAILED": (
        "Docling serialization failed for the corpus member"
    ),
    "DOCLING_CONVERSION_FAILED": "Docling conversion failed for the corpus member",
    "MARKITDOWN_CONVERSION_FAILED": (
        "MarkItDown conversion failed for the corpus member"
    ),
}


def _extractor_error(
    name: str, upstream: dict[str, Any] | None
) -> dict[str, str]:
    code = upstream.get("code") if upstream else None
    if (
        isinstance(code, str)
        and re.fullmatch(r"[A-Z][A-Z0-9_]*", code)
        and code in _EXTRACTOR_ERRORS
    ):
        return _error(code, _EXTRACTOR_ERRORS[code])
    return _error(
        "OBSERVATION_INCOMPLETE",
        f"The {name} extraction view is unavailable",
    )


def _metric_view(value: Any) -> dict[str, int] | None:
    if not isinstance(value, dict):
        return None
    try:
        return {name: int(value[name]) for name in NUMERIC_METRICS}
    except (KeyError, TypeError, ValueError):
        return None


def _comparison_record(member_id: str, value: dict[str, Any]) -> dict[str, Any]:
    views = value.get("views", {})
    docling = _metric_view(views.get("docling")) if isinstance(views, dict) else None
    markitdown = (
        _metric_view(views.get("markitdown")) if isinstance(views, dict) else None
    )
    deltas = None
    raw_deltas = value.get("deltas")
    if docling is not None and markitdown is not None and isinstance(raw_deltas, dict):
        try:
            deltas = {name: int(raw_deltas[name]) for name in NUMERIC_METRICS}
            deltas["normalized_equal"] = bool(raw_deltas["normalized_equal"])
        except (KeyError, TypeError, ValueError):
            deltas = None
    status = (
        "COMPLETE"
        if docling is not None and markitdown is not None and deltas is not None
        else "INCOMPLETE"
        if docling is not None or markitdown is not None
        else "NOT_AVAILABLE"
    )
    return {
        "member_id": member_id,
        "status": status,
        "docling": docling,
        "markitdown": markitdown,
        "docling_minus_markitdown": deltas,
    }


def _revision_records(
    admitted: AdmittedCorpusSpec,
) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    manifest_records: list[dict[str, Any]] = []
    summary_records: list[dict[str, Any]] = []
    for member in admitted.members:
        for revision in member["revisions"]:
            manifest_records.append(
                {
                    "member_id": member["member_id"],
                    **{
                        key: revision[key]
                        for key in (
                            "revision_id",
                            "refinement_run_id",
                            "diagnosis_id",
                            "parent",
                            "source",
                            "chain_length",
                            "finding_id",
                            "finding_rule",
                            "refiner",
                            "affected_reference_count",
                            "prepared_document_sha256",
                            "bundle_paths",
                            "inventory_fingerprints",
                        )
                    },
                }
            )
            summary_records.append(
                {
                    "member_id": member["member_id"],
                    "family": member["family"],
                    "format": member["format"],
                    "revision_id": revision["revision_id"],
                    "parent": revision["parent"],
                    "chain_length": revision["chain_length"],
                    "finding_id": revision["finding_id"],
                    "finding_rule": revision["finding_rule"],
                    "refiner_id": revision["refiner"]["refiner_id"],
                    "affected_reference_count": revision[
                        "affected_reference_count"
                    ],
                    "before_document_sha256": revision["parent"][
                        "canonical_document_sha256"
                    ],
                    "after_document_sha256": revision[
                        "prepared_document_sha256"
                    ],
                }
            )
    return (
        sorted(
            manifest_records,
            key=lambda item: (item["member_id"], item["revision_id"]),
        ),
        sorted(
            summary_records,
            key=lambda item: (item["member_id"], item["revision_id"]),
        ),
    )


def _counts(
    values: list[dict[str, Any]], group_name: str
) -> list[dict[str, Any]]:
    grouped: dict[str, Counter[str]] = defaultdict(Counter)
    for value in values:
        grouped[value[group_name]][value["status"].lower()] += 1
    return [
        {
            "name": name,
            "member_count": sum(counts.values()),
            "complete": counts["complete"],
            "partial": counts["partial"],
            "failed": counts["failed"],
        }
        for name, counts in sorted(grouped.items())
    ]


def _build_summary(
    *,
    admitted: AdmittedCorpusSpec,
    snapshot_id: str,
    run_id: str,
    status: str,
    members: list[dict[str, Any]],
    comparisons: list[dict[str, Any]],
    extractor_availability: list[dict[str, bool]],
    findings: list[dict[str, Any]],
    revisions: list[dict[str, Any]],
    validator: Draft202012Validator,
) -> dict[str, Any]:
    status_counts = Counter(member["status"].lower() for member in members)
    extractor_counts = {
        name: sum(item[name] for item in extractor_availability)
        for name in ("docling", "markitdown")
    }
    finding_groups: dict[
        tuple[str, str, str, str], dict[str, Any]
    ] = {}
    for finding in findings:
        key = (
            finding["rule_id"],
            finding["severity"],
            finding["family"],
            finding["format"],
        )
        group = finding_groups.setdefault(
            key, {"finding_count": 0, "members": set()}
        )
        group["finding_count"] += 1
        group["members"].add(finding["member_id"])
    grouped_findings = [
        {
            "rule_id": key[0],
            "severity": key[1],
            "family": key[2],
            "format": key[3],
            "finding_count": value["finding_count"],
            "affected_member_count": len(value["members"]),
        }
        for key, value in sorted(finding_groups.items())
    ]
    revision_counts = Counter(
        (
            item["family"],
            item["format"],
            item["finding_rule"],
            item["refiner_id"],
        )
        for item in revisions
    )
    revision_groups = [
        {
            "family": key[0],
            "format": key[1],
            "finding_rule": key[2],
            "refiner_id": key[3],
            "revision_count": count,
        }
        for key, count in sorted(revision_counts.items())
    ]
    summary_members = [
        {
            "member_id": member["member_id"],
            "family": member["family"],
            "format": member["format"],
            "status": member["status"],
            "error": member["error"],
        }
        for member in members
    ]
    summary = {
        "schema_version": "tcw.corpus-summary/v0.4",
        "corpus_id": admitted.normalized["corpus_id"],
        "snapshot_id": snapshot_id,
        "run_id": run_id,
        "status": status,
        "totals": {
            "member_count": len(members),
            "complete": status_counts["complete"],
            "partial": status_counts["partial"],
            "failed": status_counts["failed"],
            "finding_count": len(findings),
            "revision_count": len(revisions),
        },
        "by_family": _counts(summary_members, "family"),
        "by_format": _counts(summary_members, "format"),
        "extractors": [
            {
                "name": name,
                "available": extractor_counts[name],
                "unavailable": len(members) - extractor_counts[name],
            }
            for name in ("docling", "markitdown")
        ],
        "comparisons": sorted(comparisons, key=lambda item: item["member_id"]),
        "findings": grouped_findings,
        "revision_groups": revision_groups,
        "revisions": revisions,
        "members": summary_members,
    }
    validator.validate(summary)
    return summary


def execute_corpus(
    admitted: AdmittedCorpusSpec,
    staging_root: Path,
    model_root: Path,
    *,
    run_id: str,
    observe_member: Observe | None = None,
    diagnose_member: Diagnose | None = None,
    runtime_loader: RuntimeLoader | None = None,
    model_inventory_loader: ModelInventoryLoader = inventory_models,
) -> CorpusExecutionResult:
    """Process admitted members sequentially and aggregate source-free evidence."""

    (
        default_observe,
        default_diagnose,
        default_runtime,
        docling_config,
        markitdown_config,
        ruleset,
    ) = _load_defaults()
    observe_member = default_observe if observe_member is None else observe_member
    diagnose_member = (
        default_diagnose if diagnose_member is None else diagnose_member
    )
    runtime_loader = default_runtime if runtime_loader is None else runtime_loader

    root = _safe_staging_root(staging_root)
    runtime = runtime_loader()  # Global mismatch must stop before any member work.
    summary_validator = _schema_validator("corpus-summary-v0.4.schema.json")
    configurations = {
        "docling": docling_config,
        "markitdown": markitdown_config,
    }
    pdf_required = any(member["format"] == "pdf" for member in admitted.members)
    model_manifest, model_identity = _model_capture(
        model_root,
        required=pdf_required,
        loader=model_inventory_loader,
    )
    runtime_record = {
        **runtime,
        "ruleset_id": _ruleset_id(ruleset),
        "configurations": configurations,
        "model_inventory": model_manifest,
    }
    specification_capture = _specification_capture(admitted)
    source_captures = tuple(_source_capture(member) for member in admitted.members)
    revision_captures = _revision_captures(admitted)
    snapshot_id, snapshot_identity = _snapshot_identity(
        admitted, runtime, configurations, ruleset, model_identity
    )
    manifest_revisions, summary_revisions = _revision_records(admitted)

    manifest_members: list[dict[str, Any]] = []
    comparisons: list[dict[str, Any]] = []
    extractor_availability: list[dict[str, bool]] = []
    findings: list[dict[str, Any]] = []
    for member in admitted.members:
        member_root = _staged_directory(
            root, "members", member["member_id"]
        )
        observations_root = _staged_directory(member_root, "observations")
        diagnoses_root = _staged_directory(member_root, "diagnoses")
        observation_record = {
            "status": "NOT_RUN",
            "observation_id": None,
            "run_id": None,
            "manifest": None,
        }
        diagnosis_record = {
            "status": "NOT_RUN",
            "diagnosis_id": None,
            "run_id": None,
            "manifest": None,
        }
        comparison = {
            "member_id": member["member_id"],
            "status": "NOT_AVAILABLE",
            "docling": None,
            "markitdown": None,
            "docling_minus_markitdown": None,
        }
        member_error: dict[str, str] | None = None
        docling_available = False
        markitdown_available = False
        diagnosis_complete = False
        try:
            _, observation_root = observe_member(
                str(member["source_path"]), observations_root, model_root
            )
            observation_root = _inside(
                observation_root, observations_root, "nested observation"
            )
            observation_manifest_path = observation_root / "manifest.json"
            observation = _read_json(
                observation_manifest_path, "nested observation manifest"
            )
            docling_claimed, docling_error = _extractor_state(
                observation, "docling"
            )
            markitdown_claimed, markitdown_error = _extractor_state(
                observation, "markitdown"
            )
            docling_available = (
                docling_claimed
                and _extractor_artifacts_available(
                    observation_root, observation, "docling"
                )
            )
            markitdown_available = (
                markitdown_claimed
                and _extractor_artifacts_available(
                    observation_root, observation, "markitdown"
                )
            )
            observation_record = {
                "status": observation.get("status", "FAILED"),
                "observation_id": observation.get("observation_id"),
                "run_id": observation.get("run_id"),
                "manifest": _descriptor(observation_manifest_path, root),
            }
            comparison_value = _read_json(
                observation_root / "comparison.json",
                "nested comparison summary",
            )
            comparison = _comparison_record(member["member_id"], comparison_value)
            if docling_claimed and not docling_available:
                member_error = _error(
                    "CANONICAL_UNAVAILABLE",
                    "The Docling canonical document is unavailable",
                )
            elif not docling_available:
                member_error = _extractor_error("Docling", docling_error)
            elif not markitdown_available:
                member_error = _extractor_error("MarkItDown", markitdown_error)
            if docling_available:
                try:
                    diagnosis_root = diagnose_member(
                        observation_root, diagnoses_root
                    )
                    diagnosis_root = _inside(
                        diagnosis_root, diagnoses_root, "nested diagnosis"
                    )
                    diagnosis_manifest_path = (
                        diagnosis_root / "diagnosis-manifest.json"
                    )
                    diagnosis = _read_json(
                        diagnosis_manifest_path, "nested diagnosis manifest"
                    )
                    diagnosis_complete = diagnosis.get("status") in {
                        "FINDINGS",
                        "NO_FINDINGS",
                    }
                    diagnosis_record = {
                        "status": (
                            diagnosis["status"] if diagnosis_complete else "FAILED"
                        ),
                        "diagnosis_id": diagnosis.get("diagnosis_id"),
                        "run_id": diagnosis.get("run_id"),
                        "manifest": _descriptor(diagnosis_manifest_path, root),
                    }
                    finding_set = _read_json(
                        diagnosis_root / "findings.json",
                        "nested diagnostic findings",
                    )
                    if diagnosis_complete:
                        for finding in finding_set.get("findings", []):
                            if isinstance(finding, dict):
                                findings.append(
                                    {
                                        "member_id": member["member_id"],
                                        "family": member["family"],
                                        "format": member["format"],
                                        "rule_id": finding["rule_id"],
                                        "severity": finding["severity"],
                                    }
                                )
                    else:
                        member_error = _error(
                            "DIAGNOSIS_FAILED",
                            "Diagnosis did not complete for the canonical document",
                        )
                except (RuntimeContractError, IntegrityError):
                    raise
                except Exception:
                    diagnosis_record["status"] = "FAILED"
                    member_error = _error(
                        "DIAGNOSIS_FAILED",
                        "Diagnosis failed for the canonical document",
                    )
        except (RuntimeContractError, IntegrityError):
            raise
        except Exception:
            if observation_record["status"] == "NOT_RUN":
                observation_record["status"] = "FAILED"
            member_error = _error(
                "OBSERVATION_FAILED",
                "Observation failed for the corpus member",
            )

        usable = docling_available or markitdown_available
        revisions_complete = True  # Admission fully verified every listed revision.
        member_status = (
            "COMPLETE"
            if (
                docling_available
                and markitdown_available
                and diagnosis_complete
                and revisions_complete
            )
            else "PARTIAL"
            if usable
            else "FAILED"
        )
        if member_status == "COMPLETE":
            member_error = None
        elif member_error is None:
            member_error = _error(
                "MEMBER_INCOMPLETE",
                "The corpus member has incomplete reportable evidence",
            )
        comparisons.append(comparison)
        extractor_availability.append(
            {
                "docling": docling_available,
                "markitdown": markitdown_available,
            }
        )
        manifest_members.append(
            {
                "member_id": member["member_id"],
                "family": member["family"],
                "format": member["format"],
                "status": member_status,
                "source": {
                    "path": str(member["source_path"]),
                    **member["source"],
                },
                "observation": observation_record,
                "diagnosis": diagnosis_record,
                "error": member_error,
            }
        )

    usable_count = sum(member["status"] != "FAILED" for member in manifest_members)
    status = (
        "FAILED"
        if usable_count == 0
        else "COMPLETE"
        if all(member["status"] == "COMPLETE" for member in manifest_members)
        else "PARTIAL"
    )
    exit_code = {
        "COMPLETE": ExitCode.SUCCESS,
        "PARTIAL": ExitCode.PARTIAL,
        "FAILED": ExitCode.FAILED,
    }[status]
    summary = _build_summary(
        admitted=admitted,
        snapshot_id=snapshot_id,
        run_id=run_id,
        status=status,
        members=manifest_members,
        comparisons=comparisons,
        extractor_availability=extractor_availability,
        findings=findings,
        revisions=summary_revisions,
        validator=summary_validator,
    )
    return CorpusExecutionResult(
        snapshot_id=snapshot_id,
        status=status,
        exit_code=exit_code,
        runtime=runtime_record,
        members=tuple(manifest_members),
        revisions=tuple(manifest_revisions),
        summary=summary,
        input_capture={
            "snapshot_identity": snapshot_identity,
            "specification": specification_capture,
            "sources": source_captures,
            "model_root": model_root,
            "model_identity": model_identity,
            "revision_inventories": revision_captures,
        },
    )
