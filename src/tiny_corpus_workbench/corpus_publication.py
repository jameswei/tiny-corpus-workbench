"""Atomic v0.4 corpus inspection publication."""

from __future__ import annotations

import json
import os
import stat
import uuid
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from jsonschema import Draft202012Validator
from referencing import Registry, Resource

from tiny_corpus_workbench.artifacts import AtomicObservation, canonical_json
from tiny_corpus_workbench.corpus import AdmittedCorpusSpec, load_corpus_spec
from tiny_corpus_workbench.corpus_execution import (
    CorpusExecutionResult,
    execute_corpus,
    recheck_corpus_inputs,
)
from tiny_corpus_workbench.corpus_report import render_report, render_stylesheet
from tiny_corpus_workbench.domain import InputError, IntegrityError
from tiny_corpus_workbench.source import sha256_file
from tiny_corpus_workbench.verification import FORMAT_CHECKER


@dataclass(frozen=True)
class PublishedCorpus:
    corpus_id: str
    snapshot_id: str
    run_id: str
    member_count: int
    status: str
    exit_code: int
    directory: Path

    @property
    def manifest_path(self) -> Path:
        return self.directory / "corpus-manifest.json"


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
        return Draft202012Validator(
            schemas[name],
            registry=registry,
            format_checker=FORMAT_CHECKER,
        )
    except Exception as error:
        raise InputError("bundled corpus publication schema is unavailable") from error


def _absolute(path: Path) -> Path:
    return Path(os.path.abspath(os.fspath(path)))


def _prepare_output_root(path: Path) -> Path:
    absolute = _absolute(path)
    try:
        current = Path(absolute.anchor)
        for component in absolute.parts[1:]:
            current /= component
            if current.exists() or current.is_symlink():
                mode = current.lstat().st_mode
                if stat.S_ISLNK(mode) or not stat.S_ISDIR(mode):
                    raise InputError(
                        "corpus output root contains an unsafe path component"
                    )
        absolute.mkdir(parents=True, exist_ok=True)
        current = Path(absolute.anchor)
        for component in absolute.parts[1:]:
            current /= component
            mode = current.lstat().st_mode
            if stat.S_ISLNK(mode) or not stat.S_ISDIR(mode):
                raise InputError(
                    "corpus output root contains an unsafe path component"
                )
    except InputError:
        raise
    except OSError as error:
        raise InputError("corpus output root is unavailable") from error
    return absolute


def _is_within(path: Path, root: Path) -> bool:
    try:
        path.resolve(strict=False).relative_to(root.resolve(strict=True))
        return True
    except (OSError, ValueError):
        return False


def _reject_output_overlap(
    output_root: Path,
    admitted: AdmittedCorpusSpec,
    model_root: Path,
) -> None:
    input_directories = {admitted.path.parent}
    input_directories.update(member["source_path"].parent for member in admitted.members)
    for member in admitted.members:
        for revision in member["revisions"]:
            for raw in revision["bundle_paths"].values():
                candidate = admitted.path.parent / raw
                if candidate.is_dir():
                    input_directories.add(candidate)
    if any(_is_within(output_root, directory) for directory in input_directories):
        raise InputError("corpus publication must not be inside an input directory")
    if model_root.exists() and model_root.is_dir() and _is_within(
        output_root, model_root
    ):
        raise InputError(
            "corpus publication must not be inside the model artifact directory"
        )


def _artifact(
    path: Path,
    root: Path,
    *,
    role: str,
    media_type: str,
) -> dict[str, Any]:
    return {
        "path": path.relative_to(root).as_posix(),
        "role": role,
        "media_type": media_type,
        "size": path.stat().st_size,
        "sha256": sha256_file(path),
        "application_immutable": True,
    }


def _safe_tree(root: Path) -> None:
    try:
        for path in root.rglob("*"):
            mode = path.lstat().st_mode
            if stat.S_ISLNK(mode):
                raise IntegrityError(
                    "corpus staging contains a symbolic link"
                )
            if not (stat.S_ISREG(mode) or stat.S_ISDIR(mode)):
                raise IntegrityError(
                    "corpus staging contains an unsafe filesystem node"
                )
    except IntegrityError:
        raise
    except OSError as error:
        raise IntegrityError("corpus staging inventory is unavailable") from error


def _report_relative_revision_paths(
    result: CorpusExecutionResult,
    report_directory: Path,
) -> list[dict[str, Any]]:
    captures = {
        (item["member_id"], item["revision_id"]): item
        for item in result.input_capture["revision_inventories"]
    }
    revisions = []
    for revision in result.revisions:
        copied = {
            key: value
            for key, value in revision.items()
            if key != "bundle_paths"
        }
        capture = captures[(revision["member_id"], revision["revision_id"])]
        paths = {}
        for name, root in capture["roots"].items():
            relative = Path(os.path.relpath(root, report_directory)).as_posix()
            try:
                (report_directory / relative).resolve(strict=True).relative_to(
                    root.resolve(strict=True)
                )
            except (OSError, ValueError) as error:
                raise IntegrityError(
                    "external revision report link is unsafe"
                ) from error
            paths[name] = relative
        copied["bundle_paths"] = paths
        revisions.append(copied)
    return revisions


def _write_publication(
    *,
    admitted: AdmittedCorpusSpec,
    staging: Path,
    model_root: Path,
    run_id: str,
    created_at: str,
) -> CorpusExecutionResult:
    result = execute_corpus(
        admitted,
        staging,
        model_root,
        run_id=run_id,
    )
    report_directory = staging / "report"
    report_directory.mkdir()
    revisions = _report_relative_revision_paths(result, report_directory)

    specification_path = staging / "corpus-spec.json"
    summary_path = staging / "summary.json"
    report_path = report_directory / "index.html"
    stylesheet_path = report_directory / "styles.css"
    specification_path.write_bytes(admitted.canonical_bytes)
    summary_path.write_bytes(canonical_json(result.summary))
    report_path.write_bytes(
        render_report(
            title=admitted.normalized["title"],
            summary=result.summary,
            members=list(result.members),
            revisions=revisions,
        )
    )
    stylesheet_path.write_bytes(render_stylesheet())

    counts = result.summary["totals"]
    manifest = {
        "schema_version": "tcw.corpus-manifest/v0.4",
        "milestone": "v0.4",
        "corpus_id": admitted.normalized["corpus_id"],
        "snapshot_id": result.snapshot_id,
        "run_id": run_id,
        "created_at": created_at,
        "status": result.status,
        "input_specification": {
            **admitted.specification_identity,
            "normalized_sha256": sha256_file(specification_path),
        },
        "runtime": result.runtime,
        "summary": {
            key: counts[key]
            for key in ("member_count", "complete", "partial", "failed")
        },
        "members": list(result.members),
        "revisions": revisions,
        "artifacts": [
            _artifact(
                specification_path,
                staging,
                role="normalized-corpus-specification",
                media_type="application/json",
            ),
            _artifact(
                summary_path,
                staging,
                role="corpus-summary",
                media_type="application/json",
            ),
            _artifact(
                report_path,
                staging,
                role="corpus-report",
                media_type="text/html",
            ),
            _artifact(
                stylesheet_path,
                staging,
                role="corpus-stylesheet",
                media_type="text/css",
            ),
        ],
    }
    _schema_validator("corpus-manifest-v0.4.schema.json").validate(manifest)
    (staging / "corpus-manifest.json").write_bytes(canonical_json(manifest))
    _safe_tree(staging)
    recheck_corpus_inputs(result)
    return result


def inspect_corpus(
    corpus_spec: str | Path,
    output_root: Path,
    model_root: Path,
) -> PublishedCorpus:
    """Admit, execute, and atomically publish one explicit local corpus."""

    admitted = load_corpus_spec(corpus_spec)
    output = _prepare_output_root(output_root)
    _reject_output_overlap(output, admitted, _absolute(model_root))
    now = datetime.now(UTC)
    run_id = f"{now.strftime('%Y%m%dT%H%M%S.%fZ')}-{uuid.uuid4().hex[:12]}"
    publisher = AtomicObservation(
        output,
        admitted.normalized["corpus_id"],
        run_id,
    )
    with publisher as staging:
        result = _write_publication(
            admitted=admitted,
            staging=staging,
            model_root=_absolute(model_root),
            run_id=run_id,
            created_at=now.isoformat().replace("+00:00", "Z"),
        )
        directory = publisher.publish()
    return PublishedCorpus(
        corpus_id=admitted.normalized["corpus_id"],
        snapshot_id=result.snapshot_id,
        run_id=run_id,
        member_count=len(admitted.members),
        status=result.status,
        exit_code=int(result.exit_code),
        directory=directory,
    )
