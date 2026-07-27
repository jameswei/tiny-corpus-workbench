"""Internal v0.5 corpus-specification admission.

This module is intentionally not imported by the package root or the existing
single-document command paths.
"""

from __future__ import annotations

import hashlib
import json
import os
import stat
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from jsonschema import Draft202012Validator
from referencing import Registry, Resource

from tiny_corpus_workbench.application.records import require_record_header
from tiny_corpus_workbench.artifacts import canonical_json
from tiny_corpus_workbench.domain import InputError, IntegrityError, RuntimeContractError
from tiny_corpus_workbench.source import MEDIA_TYPES, sha256_file, validate_source
from tiny_corpus_workbench.verification import FORMAT_CHECKER


SCHEMA_ROOT = Path(__file__).with_name("schemas")
FORMAT_SUFFIXES = {
    "pdf": ".pdf",
    "docx": ".docx",
    "md": ".md",
    "txt": ".txt",
}
FORMAT_MEDIA_TYPES = {
    name: MEDIA_TYPES[suffix] for name, suffix in FORMAT_SUFFIXES.items()
}
_UNSAFE_PATH_CHARACTERS = frozenset("*?[]{}")


@dataclass(frozen=True)
class AdmittedCorpusSpec:
    """Validated specification plus stable input identities for execution."""

    path: Path
    normalized: dict[str, Any]
    specification_identity: dict[str, Any]
    members: tuple[dict[str, Any], ...]

    @property
    def canonical_bytes(self) -> bytes:
        return canonical_json(self.normalized)


def _schema_validator() -> Draft202012Validator:
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
            schemas["corpus-spec-v0.5.schema.json"],
            registry=registry,
            format_checker=FORMAT_CHECKER,
        )
    except Exception as error:
        raise InputError("bundled corpus specification schema is unavailable") from error


def _object_without_duplicate_keys(
    pairs: list[tuple[str, Any]],
) -> dict[str, Any]:
    value: dict[str, Any] = {}
    for key, item in pairs:
        if key in value:
            raise ValueError(f"duplicate JSON property: {key}")
        value[key] = item
    return value


def _file_signature(path: Path) -> tuple[int, int, int, int, int]:
    metadata = path.stat()
    return (
        metadata.st_dev,
        metadata.st_ino,
        metadata.st_size,
        metadata.st_mtime_ns,
        metadata.st_ctime_ns,
    )


def _absolute_lexical(path: Path) -> Path:
    return Path(os.path.abspath(os.fspath(path)))


def _reject_symlink_components(path: Path, label: str) -> Path:
    current = Path(path.anchor) if path.is_absolute() else Path.cwd()
    try:
        components = path.parts[1:] if path.is_absolute() else path.parts
        for component in components:
            if component in {"", "."}:
                continue
            if component == "..":
                current = current.parent
                continue
            current /= component
            if stat.S_ISLNK(current.lstat().st_mode):
                raise IntegrityError(f"{label} must not use symlinks")
    except IntegrityError:
        raise
    except OSError as error:
        raise InputError(f"{label} is unavailable") from error
    return _absolute_lexical(path)


def _regular_file(path: Path, label: str) -> Path:
    absolute = _reject_symlink_components(path, label)
    try:
        mode = absolute.lstat().st_mode
    except OSError as error:
        raise InputError(f"{label} is unavailable") from error
    if stat.S_ISLNK(mode):
        raise IntegrityError(f"{label} must not be a symbolic link")
    if not stat.S_ISREG(mode):
        raise InputError(f"{label} must be one regular local file")
    return absolute


def _directory(path: Path, label: str) -> Path:
    absolute = _reject_symlink_components(path, label)
    try:
        mode = absolute.lstat().st_mode
    except OSError as error:
        raise InputError(f"{label} is unavailable") from error
    if stat.S_ISLNK(mode):
        raise IntegrityError(f"{label} must not be a symbolic link")
    if not stat.S_ISDIR(mode):
        raise InputError(f"{label} must be one local directory")
    return absolute


def _path_from_spec(directory: Path, raw: str, label: str) -> Path:
    if (
        raw == "-"
        or "://" in raw
        or "\0" in raw
        or any(character in raw for character in _UNSAFE_PATH_CHARACTERS)
    ):
        raise InputError(
            f"{label} must be one explicit local path; URLs, stdin, and globs are unsupported"
        )
    value = Path(raw)
    return value if value.is_absolute() else directory / value


def _normalized_path(path: Path, directory: Path) -> str:
    return Path(os.path.relpath(path, directory)).as_posix()


def _tree_inventory(root: Path, label: str) -> dict[str, Any]:
    entries: list[dict[str, Any]] = []
    file_count = 0
    try:
        for path in sorted(root.rglob("*")):
            mode = path.lstat().st_mode
            relative = path.relative_to(root).as_posix()
            if stat.S_ISLNK(mode):
                raise IntegrityError(f"{label} must not contain symlinks")
            if stat.S_ISDIR(mode):
                entries.append({"path": relative, "kind": "directory"})
                continue
            if not stat.S_ISREG(mode):
                raise IntegrityError(f"{label} contains an unsafe filesystem node")
            raw = path.read_bytes()
            entries.append(
                {
                    "path": relative,
                    "kind": "file",
                    "size": len(raw),
                    "sha256": hashlib.sha256(raw).hexdigest(),
                }
            )
            file_count += 1
    except (InputError, IntegrityError):
        raise
    except OSError as error:
        raise InputError(f"{label} is unreadable") from error
    if not file_count:
        raise InputError(f"{label} is empty")
    return {
        "entries": entries,
        "inventory_hash": hashlib.sha256(
            canonical_json(entries).rstrip(b"\n")
        ).hexdigest(),
    }


def _load_json_file(path: Path, label: str) -> tuple[bytes, dict[str, Any]]:
    path = _regular_file(path, label)
    try:
        raw = path.read_bytes()
        value = json.loads(
            raw.decode("utf-8"),
            object_pairs_hook=_object_without_duplicate_keys,
        )
    except (OSError, UnicodeDecodeError, ValueError) as error:
        raise InputError(f"{label} is not valid JSON") from error
    if not isinstance(value, dict):
        raise InputError(f"{label} must contain one JSON object")
    return raw, value


def _recheck_revision_inventory(
    roots: dict[str, Path], before: dict[str, dict[str, Any]]
) -> dict[str, dict[str, Any]]:
    try:
        current = {
            name: _tree_inventory(
                _directory(root, f"revision {name}"),
                f"revision {name}",
            )
            for name, root in roots.items()
        }
    except (InputError, IntegrityError) as error:
        raise IntegrityError("revision bundle changed during admission") from error
    if current != before:
        raise IntegrityError("revision bundle changed during admission")
    return current


def _admit_revision(
    value: dict[str, str],
    *,
    spec_directory: Path,
    member_source: dict[str, Any],
) -> tuple[dict[str, Any], dict[str, Any], dict[str, Any]]:
    roots = {
        name: _directory(
            _path_from_spec(spec_directory, value[name], f"revision {name}"),
            f"revision {name}",
        )
        for name in ("refinement", "diagnosis", "base")
    }
    before = {
        name: _tree_inventory(root, f"revision {name}")
        for name, root in roots.items()
    }
    _, diagnosis_manifest = _load_json_file(
        roots["diagnosis"] / "diagnosis-manifest.json",
        "diagnosis manifest",
    )
    require_record_header(diagnosis_manifest, "diagnosis")

    # Keep the refinement implementation out of import paths that do not admit
    # revision bundles.
    from tiny_corpus_workbench.v03 import verify_refinement

    try:
        verification = verify_refinement(
            roots["refinement"], roots["diagnosis"], roots["base"]
        )
    except RuntimeContractError:
        _recheck_revision_inventory(roots, before)
        raise
    except Exception as error:
        _recheck_revision_inventory(roots, before)
        raise InputError("revision bundle verification failed") from error
    required_states = {
        "artifact_integrity": "VERIFIED",
        "diagnosis_state": "MATCH",
        "base_state": "MATCH",
        "derivation_state": "MATCH",
        "reversibility_state": "MATCH",
    }
    if any(
        verification.get(name, {}).get("status") != expected
        for name, expected in required_states.items()
    ):
        _recheck_revision_inventory(roots, before)
        raise InputError(
            "revision bundle does not satisfy the full v0.5 verification contract"
        )

    try:
        _, manifest = _load_json_file(
            roots["refinement"] / "refinement-manifest.json",
            "refinement manifest",
        )
        if manifest.get("status") != "APPLIED" or not manifest.get("revision_id"):
            raise InputError("revision bundle must identify one applied refinement")
        source = manifest.get("source")
        if not isinstance(source, dict) or (
            source.get("sha256") != member_source["sha256"]
            or source.get("media_type") != member_source["media_type"]
        ):
            raise InputError(
                "revision source identity does not match its corpus member"
            )
        _, history = _load_json_file(
            roots["refinement"] / "history.json", "transformation history"
        )
        transformations = history.get("transformations")
        if not isinstance(transformations, list) or not transformations:
            raise InputError("revision transformation history is malformed")
        latest = transformations[-1]
        if (
            not isinstance(latest, dict)
            or latest.get("revision_id") != manifest["revision_id"]
        ):
            raise InputError("revision transformation history is malformed")
        _, finding_set = _load_json_file(
            roots["diagnosis"] / "findings.json", "diagnostic findings"
        )
        matching_findings = [
            finding
            for finding in finding_set.get("findings", [])
            if isinstance(finding, dict)
            and finding.get("finding_id") == latest.get("finding_id")
        ]
        if len(matching_findings) != 1 or not isinstance(
            matching_findings[0].get("rule_id"), str
        ):
            raise InputError("revision finding identity is malformed")
    except InputError:
        _recheck_revision_inventory(roots, before)
        raise
    except Exception as error:
        _recheck_revision_inventory(roots, before)
        raise InputError("revision bundle identity is malformed") from error

    after = _recheck_revision_inventory(roots, before)

    normalized = {
        name: _normalized_path(root, spec_directory)
        for name, root in roots.items()
    }
    identity = {
        "revision_id": manifest["revision_id"],
        "refinement_run_id": manifest["run_id"],
        "refinement_manifest_sha256": sha256_file(
            roots["refinement"] / "refinement-manifest.json"
        ),
        "diagnosis_id": manifest["diagnosis"]["diagnosis_id"],
        "parent": {
            "kind": (
                "OBSERVATION"
                if manifest["base"]["kind"] == "OBSERVATION"
                else "REVISION"
            ),
            "subject_id": manifest["base"]["identity_value"],
            "canonical_document_sha256": manifest["base"][
                "canonical_document_sha256"
            ],
        },
        "source": {
            key: source[key] for key in ("key", "media_type", "size", "sha256")
        },
        "chain_length": len(transformations),
        "finding_id": latest["finding_id"],
        "finding_rule": matching_findings[0]["rule_id"],
        "refiner": latest["refiner"],
        "affected_refs": sorted(latest["affected_refs"]),
        "affected_reference_count": len(latest["affected_refs"]),
        "prepared_document_sha256": latest["prepared_document_sha256"],
        "bundle_paths": normalized,
        "inventory_fingerprints": {
            name: inventory["inventory_hash"]
            for name, inventory in sorted(after.items())
        },
        "inventories": {
            name: {
                "inventory_hash": inventory["inventory_hash"],
                "entries": inventory["entries"],
            }
            for name, inventory in sorted(after.items())
        },
    }
    capture = {"roots": roots, "inventories": after}
    return normalized, identity, capture


def load_corpus_spec(path: str | Path) -> AdmittedCorpusSpec:
    """Parse, normalize, and safely admit one corpus specification."""

    spec_path = _regular_file(Path(path), "corpus specification")
    spec_before = _file_signature(spec_path)
    raw, value = _load_json_file(spec_path, "corpus specification")
    try:
        _schema_validator().validate(value)
    except Exception as error:
        raise InputError("corpus specification schema validation failed") from error

    directory = spec_path.parent
    member_ids: set[str] = set()
    source_files: set[tuple[int, int]] = set()
    source_captures: list[dict[str, Any]] = []
    revision_captures: list[dict[str, Any]] = []
    normalized_members: list[dict[str, Any]] = []
    admitted_members: list[dict[str, Any]] = []
    for member in sorted(value["members"], key=lambda item: item["member_id"]):
        member_id = member["member_id"]
        if member_id in member_ids:
            raise InputError("corpus member IDs must be unique")
        member_ids.add(member_id)

        source_path = _regular_file(
            _path_from_spec(directory, member["source"], "member source"),
            "member source",
        )
        source_before = _file_signature(source_path)
        filesystem_identity = source_before[:2]
        if filesystem_identity in source_files:
            raise InputError("corpus member sources must resolve to unique files")
        source_files.add(filesystem_identity)
        expected_suffix = FORMAT_SUFFIXES[member["format"]]
        if source_path.suffix.lower() != expected_suffix:
            raise InputError("declared member format does not match its source suffix")
        source = validate_source(source_path).to_dict()
        if (
            source["media_type"] != FORMAT_MEDIA_TYPES[member["format"]]
            or source_before != _file_signature(source_path)
        ):
            raise InputError("declared member format or media type does not match its source")
        source_captures.append(
            {
                "path": source_path,
                "signature": source_before,
                "sha256": source["sha256"],
            }
        )

        normalized_revisions: list[dict[str, Any]] = []
        revision_identities: list[dict[str, Any]] = []
        revision_values = sorted(
            member.get("revisions", []),
            key=lambda item: (item["refinement"], item["diagnosis"], item["base"]),
        )
        for revision in revision_values:
            normalized_revision, revision_identity, revision_capture = _admit_revision(
                revision,
                spec_directory=directory,
                member_source=source,
            )
            normalized_revisions.append(normalized_revision)
            revision_identities.append(revision_identity)
            revision_captures.append(revision_capture)
        if len({item["revision_id"] for item in revision_identities}) != len(
            revision_identities
        ):
            raise InputError("corpus member revision IDs must be unique")
        paired = sorted(
            zip(normalized_revisions, revision_identities, strict=True),
            key=lambda pair: pair[1]["revision_id"],
        )
        normalized_revisions = [pair[0] for pair in paired]
        revision_identities = [pair[1] for pair in paired]

        normalized_member = {
            "member_id": member_id,
            "family": member["family"],
            "format": member["format"],
            "source": _normalized_path(source_path, directory),
        }
        if normalized_revisions:
            normalized_member["revisions"] = normalized_revisions
        normalized_members.append(normalized_member)
        admitted_members.append(
            {
                "member_id": member_id,
                "family": member["family"],
                "format": member["format"],
                "source_path": source_path,
                "source": {
                    key: source[key]
                    for key in (
                        "name",
                        "media_type",
                        "size",
                        "sha256",
                    )
                },
                "revisions": revision_identities,
            }
        )

    normalized = {
        "schema_version": "tcw.corpus-spec/v0.5",
        "corpus_id": value["corpus_id"],
        "title": value["title"],
        "members": normalized_members,
    }
    for capture in revision_captures:
        _recheck_revision_inventory(capture["roots"], capture["inventories"])
    for capture in source_captures:
        try:
            current_path = _regular_file(capture["path"], "member source")
            before_hash = _file_signature(current_path)
            current_hash = sha256_file(current_path)
            after_hash = _file_signature(current_path)
        except (InputError, IntegrityError, OSError) as error:
            raise IntegrityError("member source changed during admission") from error
        if (
            before_hash != after_hash
            or after_hash != capture["signature"]
            or current_hash != capture["sha256"]
        ):
            raise IntegrityError("member source changed during admission")
    try:
        current_spec = _regular_file(spec_path, "corpus specification")
        spec_hash_before = _file_signature(current_spec)
        current_spec_hash = sha256_file(current_spec)
        spec_hash_after = _file_signature(current_spec)
    except (InputError, IntegrityError, OSError) as error:
        raise IntegrityError("corpus specification changed during admission") from error
    if (
        spec_hash_before != spec_hash_after
        or spec_hash_after != spec_before
        or current_spec_hash != hashlib.sha256(raw).hexdigest()
    ):
        raise IntegrityError("corpus specification changed during admission")
    return AdmittedCorpusSpec(
        path=spec_path,
        normalized=normalized,
        specification_identity={
            "size": len(raw),
            "sha256": hashlib.sha256(raw).hexdigest(),
        },
        members=tuple(admitted_members),
    )
