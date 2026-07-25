"""Self-contained and advisory verification for v0.4 corpus runs."""

from __future__ import annotations

import hashlib
import json
import os
import stat
from html.parser import HTMLParser
from pathlib import Path, PurePosixPath
from typing import Any
from urllib.parse import unquote, urlsplit

from jsonschema import Draft202012Validator
from referencing import Registry, Resource

from tiny_corpus_workbench.artifacts import canonical_json, inventory_models
from tiny_corpus_workbench.corpus import AdmittedCorpusSpec, _tree_inventory
from tiny_corpus_workbench.corpus_execution import (
    _build_summary,
    _comparison_record,
    _extractor_state,
)
from tiny_corpus_workbench.corpus_report import render_report, render_stylesheet
from tiny_corpus_workbench.domain import InputError, RuntimeContractError
from tiny_corpus_workbench.runtime import active_locked_runtime
from tiny_corpus_workbench.source import sha256_file


def _validator(name: str) -> Draft202012Validator:
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
            "bundled corpus verification schema is unavailable"
        ) from error


def _issue(code: str, path: str | None, message: str) -> dict[str, Any]:
    return {"code": code, "path": path, "message": message}


def _read_json(
    path: Path,
    *,
    canonical: bool,
) -> tuple[bytes, dict[str, Any]]:
    if path.is_symlink() or not path.is_file():
        raise OSError
    raw = path.read_bytes()
    value = json.loads(raw.decode("utf-8"))
    if not isinstance(value, dict):
        raise ValueError
    if canonical and raw != canonical_json(value):
        raise ValueError
    return raw, value


def _safe_relative(value: Any) -> PurePosixPath | None:
    if not isinstance(value, str) or not value:
        return None
    path = PurePosixPath(value)
    if path.is_absolute() or "\x00" in value:
        return None
    if any(part in {"", ".", ".."} for part in path.parts):
        return None
    return path


def _descriptor_root(
    corpus_root: Path,
    descriptor: dict[str, Any] | None,
    expected_name: str,
) -> Path | None:
    if not isinstance(descriptor, dict):
        return None
    relative = _safe_relative(descriptor.get("path"))
    if relative is None or relative.name != expected_name:
        return None
    path = corpus_root.joinpath(*relative.parts).parent
    try:
        path.resolve(strict=True).relative_to(corpus_root.resolve(strict=True))
    except (OSError, ValueError):
        return None
    return path


def _top_artifacts(
    root: Path,
    manifest: dict[str, Any],
    issues: list[dict[str, Any]],
) -> None:
    expected = {
        "corpus-spec.json": (
            "normalized-corpus-specification",
            "application/json",
        ),
        "summary.json": ("corpus-summary", "application/json"),
        "report/index.html": ("corpus-report", "text/html"),
        "report/styles.css": ("corpus-stylesheet", "text/css"),
    }
    descriptors = {
        item.get("path"): item
        for item in manifest.get("artifacts", [])
        if isinstance(item, dict)
    }
    if set(descriptors) != set(expected) or len(manifest.get("artifacts", [])) != 4:
        issues.append(
            _issue(
                "MANIFEST_INVALID",
                "corpus-manifest.json",
                "top-level artifact inventory differs",
            )
        )
        return
    for relative, contract in expected.items():
        descriptor = descriptors[relative]
        if (
            descriptor.get("role"),
            descriptor.get("media_type"),
            descriptor.get("application_immutable"),
        ) != (*contract, True):
            issues.append(
                _issue(
                    "MANIFEST_INVALID",
                    relative,
                    "top-level artifact descriptor differs",
                )
            )
            continue
        path = root / relative
        try:
            if path.is_symlink() or not path.is_file():
                raise OSError
            if (
                path.stat().st_size != descriptor["size"]
                or sha256_file(path) != descriptor["sha256"]
            ):
                issues.append(
                    _issue(
                        "HASH_MISMATCH",
                        relative,
                        "top-level artifact descriptor differs",
                    )
                )
        except OSError:
            issues.append(
                _issue("FILE_MISSING", relative, "top-level artifact is missing")
            )


def _check_tree(
    root: Path,
    nested_roots: list[Path],
    issues: list[dict[str, Any]],
) -> None:
    expected_top_files = {
        "corpus-manifest.json",
        "corpus-spec.json",
        "summary.json",
        "report/index.html",
        "report/styles.css",
    }
    nested = []
    for value in nested_roots:
        try:
            nested.append(value.resolve(strict=True))
        except OSError:
            continue
    try:
        for path in sorted(root.rglob("*")):
            relative = path.relative_to(root).as_posix()
            mode = path.lstat().st_mode
            if stat.S_ISLNK(mode) or not (
                stat.S_ISREG(mode) or stat.S_ISDIR(mode)
            ):
                issues.append(
                    _issue(
                        "FILE_KIND_INVALID",
                        relative,
                        "corpus path is not a regular file or directory",
                    )
                )
                continue
            resolved = path.resolve(strict=True)
            inside_nested = any(
                resolved == nested_root
                or resolved.is_relative_to(nested_root)
                for nested_root in nested
            )
            if stat.S_ISREG(mode) and not inside_nested and relative not in expected_top_files:
                issues.append(
                    _issue(
                        "FILE_UNEXPECTED",
                        relative,
                        "file is not part of the corpus inventory",
                    )
                )
    except OSError:
        issues.append(
            _issue(
                "FILE_KIND_INVALID",
                None,
                "corpus inventory cannot be read safely",
            )
        )


class _ReportParser(HTMLParser):
    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.ids: set[str] = set()
        self.duplicate_ids: set[str] = set()
        self.links: list[str] = []
        self.forbidden = False

    def handle_starttag(
        self,
        tag: str,
        attrs: list[tuple[str, str | None]],
    ) -> None:
        values = dict(attrs)
        if tag in {"script", "iframe", "object", "embed"}:
            self.forbidden = True
        identifier = values.get("id")
        if identifier is not None:
            if identifier in self.ids:
                self.duplicate_ids.add(identifier)
            self.ids.add(identifier)
        for name in ("href", "src"):
            value = values.get(name)
            if value is not None:
                self.links.append(value)


def _check_report_links(
    root: Path,
    manifest: dict[str, Any],
    report_bytes: bytes,
    issues: list[dict[str, Any]],
) -> None:
    try:
        text = report_bytes.decode("utf-8")
    except UnicodeError:
        issues.append(
            _issue("REPORT_INVALID", "report/index.html", "report is not UTF-8")
        )
        return
    parser = _ReportParser()
    parser.feed(text)
    if parser.forbidden or parser.duplicate_ids:
        issues.append(
            _issue(
                "REPORT_INVALID",
                "report/index.html",
                "report contains forbidden markup or duplicate anchors",
            )
        )
    report_directory = root / "report"
    external_roots = []
    for revision in manifest.get("revisions", []):
        if not isinstance(revision, dict):
            continue
        for value in revision.get("bundle_paths", {}).values():
            if isinstance(value, str):
                external_roots.append(
                    (report_directory / unquote(value)).resolve(strict=False)
                )
    for link in parser.links:
        if any(ord(character) < 0x20 for character in link):
            issues.append(
                _issue(
                    "UNSAFE_REFERENCE",
                    "report/index.html",
                    "report link contains a control character",
                )
            )
            continue
        split = urlsplit(link)
        if split.scheme or split.netloc or split.query or split.path.startswith("/"):
            issues.append(
                _issue(
                    "UNSAFE_REFERENCE",
                    "report/index.html",
                    "report link is not one local relative reference",
                )
            )
            continue
        if not split.path:
            if split.fragment and split.fragment not in parser.ids:
                issues.append(
                    _issue(
                        "REFERENCE_MISMATCH",
                        "report/index.html",
                        "report fragment target is missing",
                    )
                )
            continue
        target = (report_directory / unquote(split.path)).resolve(strict=False)
        inside_corpus = target == root or target.is_relative_to(root)
        inside_external = any(
            target == external or target.is_relative_to(external)
            for external in external_roots
        )
        if not inside_corpus and not inside_external:
            issues.append(
                _issue(
                    "UNSAFE_REFERENCE",
                    "report/index.html",
                    "report link escapes known local evidence",
                )
            )
        elif inside_corpus and not target.is_file():
            issues.append(
                _issue(
                    "REFERENCE_MISMATCH",
                    "report/index.html",
                    "report link target is missing",
                )
            )
        if split.fragment and split.path in {"", "index.html"} and split.fragment not in parser.ids:
            issues.append(
                _issue(
                    "REFERENCE_MISMATCH",
                    "report/index.html",
                    "report fragment target is missing",
                )
            )


def _revision_summary(revision: dict[str, Any]) -> dict[str, Any]:
    return {
        "member_id": revision["member_id"],
        "family": "",
        "format": "",
        "revision_id": revision["revision_id"],
        "parent": revision["parent"],
        "chain_length": revision["chain_length"],
        "finding_id": revision["finding_id"],
        "finding_rule": revision["finding_rule"],
        "refiner_id": revision["refiner"]["refiner_id"],
        "affected_reference_count": revision["affected_reference_count"],
        "before_document_sha256": revision["parent"][
            "canonical_document_sha256"
        ],
        "after_document_sha256": revision["prepared_document_sha256"],
    }


def _regenerate_summary(
    root: Path,
    manifest: dict[str, Any],
    specification: dict[str, Any],
    issues: list[dict[str, Any]],
) -> tuple[dict[str, Any] | None, list[Path]]:
    from tiny_corpus_workbench.v03 import verify_diagnosis
    from tiny_corpus_workbench.verification import verify_observation

    spec_members = {
        member["member_id"]: member for member in specification["members"]
    }
    comparisons = []
    availability = []
    findings = []
    nested_roots: list[Path] = []
    regenerated_members = []
    family_format = {
        member["member_id"]: (member["family"], member["format"])
        for member in manifest["members"]
    }
    for member in manifest["members"]:
        observation_root = _descriptor_root(
            root, member["observation"]["manifest"], "manifest.json"
        )
        diagnosis_root = _descriptor_root(
            root,
            member["diagnosis"]["manifest"],
            "diagnosis-manifest.json",
        )
        if observation_root is not None:
            nested_roots.append(observation_root)
        if diagnosis_root is not None:
            nested_roots.append(diagnosis_root)
        docling_available = False
        markitdown_available = False
        diagnosis_complete = False
        comparison = {
            "member_id": member["member_id"],
            "status": "NOT_AVAILABLE",
            "docling": None,
            "markitdown": None,
            "docling_minus_markitdown": None,
        }
        if observation_root is not None:
            observation_result = verify_observation(observation_root)
            if observation_result["artifact_integrity"]["status"] != "VERIFIED":
                issues.append(
                    _issue(
                        "NESTED_OBSERVATION_INVALID",
                        str(observation_root.relative_to(root)),
                        "nested observation integrity differs",
                    )
                )
            try:
                _, observation = _read_json(
                    observation_root / "manifest.json", canonical=True
                )
                docling_claimed, _ = _extractor_state(observation, "docling")
                markitdown_available, _ = _extractor_state(
                    observation, "markitdown"
                )
                docling_available = (
                    docling_claimed
                    and (observation_root / "docling/document.json").is_file()
                    and not (observation_root / "docling/document.json").is_symlink()
                )
                _, comparison_value = _read_json(
                    observation_root / "comparison.json", canonical=True
                )
                comparison = _comparison_record(
                    member["member_id"], comparison_value
                )
            except Exception:
                issues.append(
                    _issue(
                        "NESTED_OBSERVATION_INVALID",
                        str(observation_root.relative_to(root)),
                        "nested observation cannot be aggregated",
                    )
                )
        if diagnosis_root is not None and observation_root is not None:
            diagnosis_result = verify_diagnosis(
                diagnosis_root, observation_root
            )
            diagnosis_complete = (
                diagnosis_result["artifact_integrity"]["status"] == "VERIFIED"
                and diagnosis_result["subject_state"]["status"] == "MATCH"
                and diagnosis_result["derivation_state"]["status"] == "MATCH"
            )
            if not diagnosis_complete:
                issues.append(
                    _issue(
                        "NESTED_DIAGNOSIS_INVALID",
                        str(diagnosis_root.relative_to(root)),
                        "nested diagnosis integrity or derivation differs",
                    )
                )
            try:
                _, finding_set = _read_json(
                    diagnosis_root / "findings.json", canonical=True
                )
                for finding in finding_set["findings"]:
                    findings.append(
                        {
                            "member_id": member["member_id"],
                            "family": member["family"],
                            "format": member["format"],
                            "rule_id": finding["rule_id"],
                            "severity": finding["severity"],
                        }
                    )
            except Exception:
                issues.append(
                    _issue(
                        "NESTED_DIAGNOSIS_INVALID",
                        str(diagnosis_root.relative_to(root)),
                        "nested findings cannot be aggregated",
                    )
                )
        expected_status = (
            "COMPLETE"
            if docling_available and markitdown_available and diagnosis_complete
            else "PARTIAL"
            if docling_available or markitdown_available
            else "FAILED"
        )
        if member["status"] != expected_status:
            issues.append(
                _issue(
                    "STATUS_MISMATCH",
                    f"members/{member['member_id']}",
                    "member status differs from nested evidence",
                )
            )
        if expected_status == "COMPLETE" and member["error"] is not None:
            issues.append(
                _issue(
                    "STATUS_MISMATCH",
                    f"members/{member['member_id']}",
                    "complete member contains an error",
                )
            )
        if member["member_id"] not in spec_members or (
            member["family"],
            member["format"],
        ) != (
            spec_members.get(member["member_id"], {}).get("family"),
            spec_members.get(member["member_id"], {}).get("format"),
        ):
            issues.append(
                _issue(
                    "REFERENCE_MISMATCH",
                    f"members/{member['member_id']}",
                    "member differs from the normalized specification",
                )
            )
        regenerated_members.append(member)
        comparisons.append(comparison)
        availability.append(
            {
                "docling": docling_available,
                "markitdown": markitdown_available,
            }
        )

    revisions = []
    for revision in manifest["revisions"]:
        value = _revision_summary(revision)
        value["family"], value["format"] = family_format[revision["member_id"]]
        revisions.append(value)
    usable = sum(member["status"] != "FAILED" for member in regenerated_members)
    status = (
        "FAILED"
        if usable == 0
        else "COMPLETE"
        if all(member["status"] == "COMPLETE" for member in regenerated_members)
        else "PARTIAL"
    )
    admitted = AdmittedCorpusSpec(
        path=root / "corpus-spec.json",
        normalized=specification,
        specification_identity={},
        members=(),
    )
    try:
        summary = _build_summary(
            admitted=admitted,
            snapshot_id=manifest["snapshot_id"],
            run_id=manifest["run_id"],
            status=status,
            members=regenerated_members,
            comparisons=comparisons,
            extractor_availability=availability,
            findings=findings,
            revisions=sorted(
                revisions,
                key=lambda item: (item["member_id"], item["revision_id"]),
            ),
            validator=_validator("corpus-summary-v0.4.schema.json"),
        )
    except Exception:
        issues.append(
            _issue(
                "SUMMARY_INVALID",
                "summary.json",
                "summary cannot be regenerated from nested evidence",
            )
        )
        return None, nested_roots
    return summary, nested_roots


def _state_for_file(path: Path, descriptor: dict[str, Any]) -> str:
    try:
        if path.is_symlink():
            return "ERROR"
        if not path.exists():
            return "MISSING"
        if not path.is_file():
            return "ERROR"
        return (
            "MATCH"
            if path.stat().st_size == descriptor["size"]
            and sha256_file(path) == descriptor["sha256"]
            else "CHANGED"
        )
    except OSError:
        return "ERROR"


def _state_for_tree(path: Path, expected_hash: str) -> str:
    try:
        if path.is_symlink():
            return "ERROR"
        if not path.exists():
            return "MISSING"
        if not path.is_dir():
            return "ERROR"
        current = _tree_inventory(path, "revision advisory")
        return (
            "MATCH"
            if current["inventory_hash"] == expected_hash
            else "CHANGED"
        )
    except InputError:
        return "ERROR"


def _advisories(
    *,
    root: Path,
    manifest: dict[str, Any] | None,
    spec_path: Path | None,
) -> tuple[
    dict[str, str],
    list[dict[str, Any]],
    dict[str, str],
    list[dict[str, Any]],
]:
    if spec_path is None or manifest is None:
        return (
            {"status": "NOT_CHECKED"},
            [],
            {"status": "NOT_CHECKED"},
            [],
        )
    specification_state = {"status": "ERROR"}
    try:
        if spec_path.is_symlink():
            specification_state = {"status": "ERROR"}
        elif not spec_path.exists():
            specification_state = {"status": "MISSING"}
        elif not spec_path.is_file():
            specification_state = {"status": "ERROR"}
        else:
            specification_state = {
                "status": (
                    "MATCH"
                    if spec_path.stat().st_size
                    == manifest["input_specification"]["size"]
                    and sha256_file(spec_path)
                    == manifest["input_specification"]["sha256"]
                    else "CHANGED"
                )
            }
    except OSError:
        specification_state = {"status": "ERROR"}

    source_states = [
        {
            "member_id": member["member_id"],
            "state": {
                "status": _state_for_file(
                    Path(member["source"]["path"]), member["source"]
                )
            },
        }
        for member in manifest["members"]
    ]
    model = manifest["runtime"]["model_inventory"]
    if not model["required"]:
        model_state = {"status": "MATCH"}
    else:
        try:
            current = inventory_models(Path(model["path"]), required=True)
            model_state = {
                "status": (
                    "MATCH"
                    if current["inventory_hash"] == model["inventory_hash"]
                    else "CHANGED"
                )
            }
        except RuntimeContractError:
            model_state = {
                "status": (
                    "MISSING" if not Path(model["path"]).exists() else "ERROR"
                )
            }

    revision_states = []
    report_directory = root / "report"
    for revision in manifest["revisions"]:
        states = {
            name: _state_for_tree(
                (report_directory / unquote(revision["bundle_paths"][name])).resolve(
                    strict=False
                ),
                revision["inventory_fingerprints"][name],
            )
            for name in ("refinement", "diagnosis", "base")
        }
        revision_states.append(
            {
                "member_id": revision["member_id"],
                "revision_id": revision["revision_id"],
                "refinement_state": {"status": states["refinement"]},
                "diagnosis_state": {"status": states["diagnosis"]},
                "base_state": {"status": states["base"]},
            }
        )
    return specification_state, source_states, model_state, revision_states


def verify_corpus(
    corpus_root: Path,
    spec_path: Path | None = None,
) -> dict[str, Any]:
    """Verify one corpus run without repairing or regenerating its files."""

    active_locked_runtime()
    root = Path(os.path.abspath(os.fspath(corpus_root)))
    if root.is_symlink() or not root.is_dir():
        raise InputError(
            "CORPUS_DIRECTORY must be one local non-symlink directory"
        )
    issues: list[dict[str, Any]] = []
    manifest: dict[str, Any] | None = None
    specification: dict[str, Any] | None = None
    summary: dict[str, Any] | None = None
    try:
        _, manifest = _read_json(
            root / "corpus-manifest.json", canonical=True
        )
        _validator("corpus-manifest-v0.4.schema.json").validate(manifest)
        if manifest["run_id"] != root.name:
            raise ValueError
    except Exception:
        issues.append(
            _issue(
                "MANIFEST_INVALID",
                "corpus-manifest.json",
                "corpus manifest is invalid",
            )
        )
        manifest = None

    if manifest is not None:
        _top_artifacts(root, manifest, issues)
        try:
            specification_bytes, specification = _read_json(
                root / "corpus-spec.json", canonical=True
            )
            _validator("corpus-spec-v0.4.schema.json").validate(specification)
            if (
                hashlib.sha256(specification_bytes).hexdigest()
                != manifest["input_specification"]["normalized_sha256"]
                or specification["corpus_id"] != manifest["corpus_id"]
            ):
                raise ValueError
        except Exception:
            issues.append(
                _issue(
                    "SCHEMA_INVALID",
                    "corpus-spec.json",
                    "normalized corpus specification is invalid",
                )
            )
            specification = None
        try:
            _, summary = _read_json(root / "summary.json", canonical=True)
            _validator("corpus-summary-v0.4.schema.json").validate(summary)
        except Exception:
            issues.append(
                _issue(
                    "SUMMARY_INVALID",
                    "summary.json",
                    "corpus summary is invalid",
                )
            )
            summary = None

    nested_roots: list[Path] = []
    regenerated: dict[str, Any] | None = None
    if manifest is not None and specification is not None:
        regenerated, nested_roots = _regenerate_summary(
            root, manifest, specification, issues
        )
        if regenerated is not None and regenerated != summary:
            issues.append(
                _issue(
                    "SUMMARY_INVALID",
                    "summary.json",
                    "corpus summary differs from regenerated evidence",
                )
            )
        if regenerated is not None:
            expected_counts = {
                key: regenerated["totals"][key]
                for key in ("member_count", "complete", "partial", "failed")
            }
            if (
                manifest["summary"] != expected_counts
                or manifest["status"] != regenerated["status"]
            ):
                issues.append(
                    _issue(
                        "STATUS_MISMATCH",
                        "corpus-manifest.json",
                        "corpus status or counts differ",
                    )
                )
    if manifest is not None:
        _check_tree(root, nested_roots, issues)
    if (
        manifest is not None
        and specification is not None
        and regenerated is not None
    ):
        try:
            report_bytes = (root / "report/index.html").read_bytes()
            expected_report = render_report(
                title=specification["title"],
                summary=regenerated,
                members=manifest["members"],
                revisions=manifest["revisions"],
            )
            if report_bytes != expected_report:
                issues.append(
                    _issue(
                        "REPORT_INVALID",
                        "report/index.html",
                        "corpus report differs from deterministic rendering",
                    )
                )
            _check_report_links(root, manifest, report_bytes, issues)
            if (root / "report/styles.css").read_bytes() != render_stylesheet():
                issues.append(
                    _issue(
                        "REPORT_INVALID",
                        "report/styles.css",
                        "corpus stylesheet differs",
                    )
                )
        except OSError:
            issues.append(
                _issue(
                    "REPORT_INVALID",
                    "report/index.html",
                    "corpus report cannot be read",
                )
            )

    (
        specification_state,
        source_states,
        model_state,
        revision_states,
    ) = _advisories(root=root, manifest=manifest, spec_path=spec_path)
    broken_codes = {
        "MANIFEST_INVALID",
        "SCHEMA_INVALID",
        "SUMMARY_INVALID",
        "REFERENCE_MISMATCH",
        "STATUS_MISMATCH",
        "NESTED_OBSERVATION_INVALID",
        "NESTED_DIAGNOSIS_INVALID",
    }
    artifact_status = (
        "VERIFIED"
        if not issues
        else "BROKEN"
        if any(issue["code"] in broken_codes for issue in issues)
        else "INTEGRITY_MISMATCH"
    )
    result = {
        "schema_version": "tcw.corpus-verification-result/v0.4",
        "corpus_directory": str(root.resolve()),
        "artifact_integrity": {
            "status": artifact_status,
            "issues": issues,
        },
        "specification_state": specification_state,
        "source_states": source_states,
        "model_state": model_state,
        "revision_states": revision_states,
    }
    _validator("corpus-verification-result-v0.4.schema.json").validate(result)
    return result
