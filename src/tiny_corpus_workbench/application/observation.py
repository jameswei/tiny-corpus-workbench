from __future__ import annotations

import importlib
import importlib.metadata
import os
import shutil
import time
import uuid
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, Callable

from tiny_corpus_workbench.application.records import record_header
from tiny_corpus_workbench.artifacts import (
    AtomicObservation,
    compute_observation_id,
    inventory_models,
    model_filesystem_identity,
    verify_staged_observation,
    write_json,
)
from tiny_corpus_workbench.comparison import make_comparison
from tiny_corpus_workbench.domain import (
    ExitCode,
    IntegrityError,
    RuntimeContractError,
    StableError,
    sanitize_message,
)
from tiny_corpus_workbench.golden_fixtures import fixture_anchors
from tiny_corpus_workbench.source import SourceSnapshot, sha256_file


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
OBSERVATION_STAGES = (
    "PREPARING_SOURCE",
    "EXTRACTING_DOCLING",
    "EXTRACTING_MARKITDOWN",
    "BUILDING_EVIDENCE",
    "VERIFYING_AND_PUBLISHING",
)


def validate_staged_schemas(root: Path) -> None:
    """Load schema validation only when staged observation evidence exists."""

    try:
        from tiny_corpus_workbench.verification import (
            validate_staged_schemas as validate,
        )
    except Exception as error:
        raise RuntimeContractError(
            "bundled observation schema validation is unavailable"
        ) from error

    validate(root)


def _preflight_extractors() -> tuple[Any, Any]:
    try:
        docling_adapter = importlib.import_module(
            "tiny_corpus_workbench.extractors.docling"
        )
        markitdown_adapter = importlib.import_module(
            "tiny_corpus_workbench.extractors.markitdown"
        )
        for adapter in (docling_adapter, markitdown_adapter):
            if not callable(getattr(adapter, "convert", None)) or not callable(
                getattr(adapter, "preflight", None)
            ):
                raise RuntimeError("adapter symbols are unavailable")
            adapter.preflight()
    except Exception as error:
        raise RuntimeContractError("extractor runtime preflight failed") from error
    return docling_adapter, markitdown_adapter


def _artifact(
    path: Path, root: Path, role: str, media_type: str
) -> dict[str, Any]:
    return {
        "path": path.relative_to(root).as_posix(),
        "role": role,
        "media_type": media_type,
        "size": path.stat().st_size,
        "sha256": sha256_file(path),
        "application_immutable": True,
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


def _extractor_versions() -> dict[str, str]:
    try:
        return {
            "docling": importlib.metadata.version("docling"),
            "markitdown": importlib.metadata.version("markitdown"),
        }
    except Exception as error:
        raise RuntimeContractError("extractor runtime preflight failed") from error


def observe(
    source_value: str,
    output_root: Path,
    model_root: Path,
    progress: Callable[[str], None] | None = None,
) -> tuple[ExitCode, Path]:
    def report(stage: str) -> None:
        if progress is not None:
            progress(stage)

    report("PREPARING_SOURCE")
    docling_adapter, markitdown_adapter = _preflight_extractors()
    extractor_versions = _extractor_versions()
    snapshot = SourceSnapshot(source_value)
    try:
        source_path, source = snapshot.capture()
        is_pdf = source.media_type == "application/pdf"
        model_error: StableError | None = None
        try:
            models = inventory_models(model_root, required=is_pdf)
            model_identity_before = (
                model_filesystem_identity(model_root) if is_pdf else None
            )
        except RuntimeContractError as error:
            code = (
                "MODEL_ARTIFACTS_INVALID"
                if model_root.exists()
                else "MODEL_ARTIFACTS_MISSING"
            )
            model_error = StableError(code, sanitize_message(error))
            models = {
                "required": is_pdf,
                "inventory_hash": None,
                "files": [],
            }
            model_identity_before = None

        now = datetime.now(UTC)
        run_id = f"{now.strftime('%Y%m%dT%H%M%S.%fZ')}-{uuid.uuid4().hex[:12]}"
        publisher = AtomicObservation(output_root, source.key, run_id)
        with publisher as staging:
            docling_result = _result("docling", extractor_versions["docling"])
            markitdown_result = _result(
                "markitdown", extractor_versions["markitdown"]
            )
            document_schema = {"name": None, "version": None}

            report("EXTRACTING_DOCLING")
            if model_error is not None:
                docling_result["error"] = model_error.to_dict()
            else:
                started = time.monotonic_ns()
                try:
                    os.environ["HF_HUB_OFFLINE"] = "1"
                    os.environ["TRANSFORMERS_OFFLINE"] = "1"
                    upstream, document_schema = docling_adapter.convert(
                        source_path, staging / "docling", model_root
                    )
                    docling_result["upstream_status"] = upstream
                    docling_result["status"] = (
                        "PARTIAL_SUCCESS"
                        if "partial" in upstream.lower()
                        else "SUCCESS"
                    )
                    docling_result["artifacts"] = [
                        _artifact(
                            staging / "docling/document.json",
                            staging,
                            "docling-document-json",
                            "application/json",
                        ),
                        _artifact(
                            staging / "docling/document.md",
                            staging,
                            "docling-markdown",
                            "text/markdown",
                        ),
                    ]
                except Exception as error:
                    shutil.rmtree(staging / "docling", ignore_errors=True)
                    code = (
                        "DOCLING_SERIALIZATION_FAILED"
                        if isinstance(
                            error, docling_adapter.DoclingSerializationError
                        )
                        else "DOCLING_CONVERSION_FAILED"
                    )
                    message = (
                        "Docling serialization failed for the validated local source"
                        if code == "DOCLING_SERIALIZATION_FAILED"
                        else "Docling conversion failed for the validated local source"
                    )
                    docling_result["error"] = StableError(code, message).to_dict()
                finally:
                    docling_result["duration_ms"] = (
                        time.monotonic_ns() - started
                    ) // 1_000_000

            report("EXTRACTING_MARKITDOWN")
            started = time.monotonic_ns()
            try:
                markitdown_adapter.convert(source_path, staging / "markitdown")
                markitdown_result["status"] = "SUCCESS"
                markitdown_result["artifacts"] = [
                    _artifact(
                        staging / "markitdown/document.md",
                        staging,
                        "markitdown-markdown",
                        "text/markdown",
                    )
                ]
            except Exception:
                shutil.rmtree(staging / "markitdown", ignore_errors=True)
                markitdown_result["error"] = StableError(
                    "MARKITDOWN_CONVERSION_FAILED",
                    "MarkItDown conversion failed for the validated local source",
                ).to_dict()
            finally:
                markitdown_result["duration_ms"] = (
                    time.monotonic_ns() - started
                ) // 1_000_000

            report("BUILDING_EVIDENCE")
            docling_view = None
            if docling_result["status"] in ("SUCCESS", "PARTIAL_SUCCESS"):
                path = staging / "docling/document.md"
                docling_view = (path.read_bytes(), sha256_file(path))
            markitdown_view = None
            if markitdown_result["status"] == "SUCCESS":
                path = staging / "markitdown/document.md"
                markitdown_view = (path.read_bytes(), sha256_file(path))
            configurations = {
                "docling": DOCLING_CONFIG,
                "markitdown": MARKITDOWN_CONFIG,
            }
            extractors = [docling_result, markitdown_result]
            observation_id = compute_observation_id(
                source.to_dict(),
                configurations,
                models["inventory_hash"],
                extractors,
                document_schema,
            )
            comparison = make_comparison(
                observation_id,
                source.to_dict(),
                fixture_anchors(source.fixture_id),
                docling_view,
                markitdown_view,
            )
            write_json(staging / "comparison.json", comparison)
            comparison_artifact = _artifact(
                staging / "comparison.json",
                staging,
                "comparison-summary",
                "application/json",
            )

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
                **record_header("observation"),
                "run_id": run_id,
                "observation_id": observation_id,
                "created_at": now.isoformat().replace("+00:00", "Z"),
                "status": overall,
                "source": source.to_dict(),
                "configurations": configurations,
                "docling_document_schema": document_schema,
                "models": models,
                "extractors": extractors,
                "comparison": {
                    "status": comparison["status"],
                    "path": "comparison.json",
                    "size": comparison_artifact["size"],
                    "sha256": comparison_artifact["sha256"],
                    "application_immutable": True,
                },
            }
            write_json(staging / "manifest.json", manifest)
            staged_artifacts = [
                artifact
                for result in manifest["extractors"]
                for artifact in result["artifacts"]
            ]
            staged_artifacts.extend(
                [
                    comparison_artifact,
                    _artifact(
                        staging / "manifest.json",
                        staging,
                        "observation-manifest",
                        "application/json",
                    ),
                ]
            )
            report("VERIFYING_AND_PUBLISHING")
            snapshot.cleanup()
            if is_pdf and model_error is None:
                try:
                    models_after = inventory_models(model_root, required=True)
                    model_identity_after = model_filesystem_identity(model_root)
                except RuntimeContractError as error:
                    raise IntegrityError(
                        "Docling model inventory changed during extraction"
                    ) from error
                if (
                    models_after != models
                    or model_identity_after != model_identity_before
                ):
                    raise IntegrityError(
                        "Docling model inventory changed during extraction"
                    )
            validate_staged_schemas(staging)
            verify_staged_observation(staging, staged_artifacts)
            published = publisher.publish()
            return exit_code, published
    finally:
        snapshot.cleanup()
