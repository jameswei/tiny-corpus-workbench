from __future__ import annotations

import argparse
import hashlib
import importlib.metadata
import json
import os
import platform
import sys
import time
import uuid
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from tiny_corpus_workbench.artifacts import AtomicObservation, canonical_json, inventory_models, write_json
from tiny_corpus_workbench.comparison import make_comparison
from tiny_corpus_workbench.domain import (
    ExitCode,
    InputError,
    IntegrityError,
    RuntimeContractError,
    StableError,
    WorkbenchError,
    sanitize_message,
)
from tiny_corpus_workbench.source import sha256_file, validate_source


DEPENDENCIES = {
    "docling": "2.113.0",
    "docling-core": "2.87.1",
    "markitdown": "0.1.6",
}
DOCLING_CONFIG = {
    "accelerator": "cpu",
    "ocr": False,
    "table_structure": True,
    "remote_services": False,
    "external_plugins": False,
    "artifacts_path": "explicit-local-path",
}
MARKITDOWN_CONFIG = {
    "convert_method": "convert_local",
    "plugins": False,
    "llm_client": False,
    "text_hints": "extension-media-type-utf8",
}


def parser() -> argparse.ArgumentParser:
    root = argparse.ArgumentParser(prog="tcw")
    commands = root.add_subparsers(dest="command", required=True)
    observe = commands.add_parser("observe", help="publish one immutable extraction observation")
    observe.add_argument("source", metavar="SOURCE")
    observe.add_argument("--output-root", type=Path, default=Path("build/extraction-observatory"))
    observe.add_argument("--docling-artifacts", type=Path, default=Path(".cache/docling/models"))
    return root


def _lock_identity() -> dict[str, Any]:
    lock = Path("uv.lock")
    if not lock.is_file():
        raise RuntimeContractError("uv.lock is required from the repository root")
    try:
        installed = {name: importlib.metadata.version(name) for name in DEPENDENCIES}
    except Exception as error:
        raise RuntimeContractError(
            "required extractor package metadata is unavailable"
        ) from error
    if installed != DEPENDENCIES:
        raise RuntimeContractError("installed extractor versions do not match the locked v0.1 contract")
    if sys.version_info[:2] != (3, 12):
        raise RuntimeContractError("the v0.1 acceptance runtime is CPython 3.12")
    return {"path": str(lock.resolve()), "sha256": sha256_file(lock), "dependencies": installed}


def _fixture_anchors(fixture_id: str | None) -> dict[str, str]:
    if fixture_id is None:
        return {}
    registry = json.loads(Path("fixtures/golden/fixtures.json").read_text("utf-8"))
    for fixture in registry["fixtures"]:
        if fixture["id"] == fixture_id:
            return fixture["anchors"]
    return {}


def _artifact(path: Path, root: Path, role: str, media_type: str) -> dict[str, Any]:
    return {
        "path": path.relative_to(root).as_posix(),
        "role": role,
        "media_type": media_type,
        "size": path.stat().st_size,
        "sha256": sha256_file(path),
        "immutable": True,
    }


def _result(name: str, version: str) -> dict[str, Any]:
    return {
        "name": name,
        "version": version,
        "status": "FAILED",
        "duration_ms": 0,
        "upstream_status": None,
        "artifacts": [],
        "error": None,
    }


def _observation_id(source: dict[str, Any], lock: dict[str, Any], models: dict[str, Any]) -> str:
    identity = {
        "source": {key: source[key] for key in ("sha256", "size", "media_type")},
        "extractors": DEPENDENCIES,
        "configurations": {"docling": DOCLING_CONFIG, "markitdown": MARKITDOWN_CONFIG},
        "lock_sha256": lock["sha256"],
        "model_inventory_hash": models["inventory_hash"],
    }
    return hashlib.sha256(canonical_json(identity).rstrip(b"\n")).hexdigest()


def observe(source_value: str, output_root: Path, model_root: Path) -> tuple[ExitCode, Path]:
    source = validate_source(source_value)
    lock = _lock_identity()
    source_path = Path(source.path)
    is_pdf = source.media_type == "application/pdf"
    model_error: StableError | None = None
    try:
        models = inventory_models(model_root, required=is_pdf)
    except RuntimeContractError as error:
        code = "MODEL_ARTIFACTS_INVALID" if model_root.exists() else "MODEL_ARTIFACTS_MISSING"
        model_error = StableError(code, sanitize_message(error))
        models = {
            "required": is_pdf,
            "path": str(model_root.resolve()),
            "inventory_hash": None,
            "files": [],
        }

    now = datetime.now(UTC)
    run_id = f"{now.strftime('%Y%m%dT%H%M%S.%fZ')}-{uuid.uuid4().hex[:12]}"
    publisher = AtomicObservation(output_root, source.key, run_id)
    with publisher as staging:
        docling_result = _result("docling", DEPENDENCIES["docling"])
        markitdown_result = _result("markitdown", DEPENDENCIES["markitdown"])
        schema = {"name": "DoclingDocument", "version": "unknown"}

        if model_error is not None:
            docling_result["error"] = model_error.to_dict()
        else:
            started = time.monotonic_ns()
            try:
                os.environ["HF_HUB_OFFLINE"] = "1"
                os.environ["TRANSFORMERS_OFFLINE"] = "1"
                from tiny_corpus_workbench.extractors.docling import convert

                upstream, schema = convert(source_path, staging / "docling", model_root)
                docling_result["upstream_status"] = upstream
                docling_result["status"] = (
                    "PARTIAL_SUCCESS" if "partial" in upstream.lower() else "SUCCESS"
                )
                docling_result["artifacts"] = [
                    _artifact(staging / "docling/document.json", staging, "docling-document-json", "application/json"),
                    _artifact(staging / "docling/document.md", staging, "docling-markdown", "text/markdown"),
                ]
            except Exception as error:
                import shutil

                shutil.rmtree(staging / "docling", ignore_errors=True)
                from tiny_corpus_workbench.extractors.docling import DoclingSerializationError

                code = (
                    "DOCLING_SERIALIZATION_FAILED"
                    if isinstance(error, DoclingSerializationError)
                    else "DOCLING_CONVERSION_FAILED"
                )
                message = (
                    "Docling serialization failed for the validated local source"
                    if code == "DOCLING_SERIALIZATION_FAILED"
                    else "Docling conversion failed for the validated local source"
                )
                docling_result["error"] = StableError(
                    code, message
                ).to_dict()
            finally:
                docling_result["duration_ms"] = (time.monotonic_ns() - started) // 1_000_000

        started = time.monotonic_ns()
        try:
            from tiny_corpus_workbench.extractors.markitdown import convert

            convert(source_path, staging / "markitdown")
            markitdown_result["status"] = "SUCCESS"
            markitdown_result["artifacts"] = [
                _artifact(staging / "markitdown/document.md", staging, "markitdown-markdown", "text/markdown")
            ]
        except Exception as error:
            import shutil

            shutil.rmtree(staging / "markitdown", ignore_errors=True)
            markitdown_result["error"] = StableError(
                "MARKITDOWN_CONVERSION_FAILED",
                "MarkItDown conversion failed for the validated local source",
            ).to_dict()
        finally:
            markitdown_result["duration_ms"] = (time.monotonic_ns() - started) // 1_000_000

        if sha256_file(source_path) != source.sha256 or source_path.stat().st_size != source.size:
            raise IntegrityError("SOURCE changed during extraction; observation discarded")

        docling_view = None
        if docling_result["status"] in ("SUCCESS", "PARTIAL_SUCCESS"):
            path = staging / "docling/document.md"
            docling_view = (path.read_bytes(), sha256_file(path))
        markitdown_view = None
        if markitdown_result["status"] == "SUCCESS":
            path = staging / "markitdown/document.md"
            markitdown_view = (path.read_bytes(), sha256_file(path))
        comparison = make_comparison(
            source.to_dict(), _fixture_anchors(source.fixture_id), docling_view, markitdown_view
        )
        write_json(staging / "comparison.json", comparison)

        statuses = [docling_result["status"], markitdown_result["status"]]
        if statuses == ["SUCCESS", "SUCCESS"]:
            overall, exit_code = "SUCCESS", ExitCode.SUCCESS
        elif all(status == "FAILED" for status in statuses):
            overall, exit_code = "FAILED", ExitCode.FAILED
        else:
            overall, exit_code = "PARTIAL_SUCCESS", ExitCode.PARTIAL
        if model_error is not None:
            exit_code = ExitCode.RUNTIME

        manifest = {
            "schema_version": "tcw.preparation-manifest/v0.1",
            "milestone": "v0.1",
            "run_id": run_id,
            "observation_id": _observation_id(source.to_dict(), lock, models),
            "created_at": now.isoformat().replace("+00:00", "Z"),
            "status": overall,
            "source": source.to_dict(),
            "runtime": {
                "python": platform.python_version(),
                "implementation": platform.python_implementation(),
                "platform": platform.platform(),
                "lockfile": {"path": lock["path"], "sha256": lock["sha256"]},
                "dependencies": lock["dependencies"],
            },
            "configurations": {"docling": DOCLING_CONFIG, "markitdown": MARKITDOWN_CONFIG},
            "docling_document_schema": {
                **schema,
                "compatibility": "reloadable only with the exact uv.lock environment that created this artifact",
            },
            "models": models,
            "extractors": [docling_result, markitdown_result],
            "comparison": {
                "status": comparison["status"],
                "path": "comparison.json",
            },
        }
        write_json(staging / "manifest.json", manifest)
        published = publisher.publish()
    return exit_code, published


def main(argv: list[str] | None = None) -> int:
    args = parser().parse_args(argv)
    try:
        exit_code, published = observe(args.source, args.output_root, args.docling_artifacts)
    except WorkbenchError as error:
        print(sanitize_message(error), file=sys.stderr)
        return int(error.exit_code)
    except Exception as error:
        print(f"internal failure: {sanitize_message(error)}", file=sys.stderr)
        return int(ExitCode.INTERNAL)
    line = {
        "manifest": str((published / "manifest.json").resolve()),
        "run_id": published.name,
        "status": json.loads((published / "manifest.json").read_text("utf-8"))["status"],
    }
    print(json.dumps(line, sort_keys=True, separators=(",", ":")))
    return int(exit_code)
