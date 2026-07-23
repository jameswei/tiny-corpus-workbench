from __future__ import annotations

import argparse
import importlib
import importlib.metadata
import json
import os
import platform
import stat
import sys
import time
import uuid
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

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
    DOCLING_DOCUMENT_COMPATIBILITY,
    ExitCode,
    InputError,
    IntegrityError,
    RuntimeContractError,
    StableError,
    WorkbenchError,
    sanitize_message,
)
from tiny_corpus_workbench.runtime import RUNTIME_DEPENDENCIES
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


def _verification_callable(name: str) -> Any:
    try:
        from tiny_corpus_workbench import verification as module

        function = getattr(module, name)
    except Exception as error:
        raise RuntimeContractError(
            "bundled verification/schema runtime is unavailable or incompatible"
        ) from error
    if not callable(function):
        raise RuntimeContractError(
            "bundled verification/schema runtime is unavailable or incompatible"
        )
    return function


def _diagnosis_callable(module_name: str, name: str) -> Any:
    try:
        module = importlib.import_module(f"tiny_corpus_workbench.{module_name}")
        function = getattr(module, name)
    except Exception as error:
        raise RuntimeContractError(
            "bundled diagnosis/schema runtime is unavailable or incompatible"
        ) from error
    if not callable(function):
        raise RuntimeContractError(
            "bundled diagnosis/schema runtime is unavailable or incompatible"
        )
    return function


def _validate_staged_schemas(root: Path) -> None:
    _verification_callable("validate_staged_schemas")(root)


def _published_diagnosis_line(published: Path) -> dict[str, Any]:
    manifest_path = published / "diagnosis-manifest.json"
    try:
        snapshot = _diagnosis_callable("diagnosis", "snapshot_tree")
        before = snapshot(published)
        verify = _diagnosis_callable(
            "diagnosis_verification", "verify_diagnosis"
        )
        verification = verify(published)
        if verification["artifact_integrity"]["status"] != "VERIFIED":
            raise IntegrityError(
                "published diagnosis manifest is unavailable or invalid"
            )
    except (RuntimeContractError, IntegrityError):
        raise
    except Exception as error:
        raise IntegrityError(
            "published diagnosis manifest is unavailable or invalid"
        ) from error
    try:
        if not stat.S_ISREG(manifest_path.lstat().st_mode):
            raise OSError
        manifest = json.loads(manifest_path.read_text("utf-8"))
        diagnosis_id = manifest["diagnosis_id"]
        finding_count = manifest["summary"]["total"]
        run_id = manifest["run_id"]
        status = manifest["status"]
        if (
            not isinstance(diagnosis_id, str)
            or len(diagnosis_id) != 64
            or type(finding_count) is not int
            or finding_count < 0
            or not isinstance(run_id, str)
            or run_id != published.name
            or status not in {"FINDINGS", "NO_FINDINGS"}
        ):
            raise ValueError
        line = {
            "diagnosis_id": diagnosis_id,
            "finding_count": finding_count,
            "manifest": str(manifest_path.resolve()),
            "run_id": run_id,
            "status": status,
        }
    except (OSError, UnicodeError, json.JSONDecodeError, KeyError, TypeError, ValueError) as error:
        raise IntegrityError(
            "published diagnosis manifest is unavailable or invalid"
        ) from error
    try:
        if snapshot(published) != before:
            raise IntegrityError(
                "published diagnosis changed before summary output"
            )
    except IntegrityError:
        raise
    except Exception as error:
        raise IntegrityError(
            "published diagnosis changed before summary output"
        ) from error
    return line


def parser() -> argparse.ArgumentParser:
    root = argparse.ArgumentParser(prog="tcw")
    commands = root.add_subparsers(dest="command", required=True)
    observe = commands.add_parser(
        "observe", help="publish one application-immutable extraction observation"
    )
    observe.add_argument("source", metavar="SOURCE")
    observe.add_argument("--output-root", type=Path, default=Path("build/extraction-observatory"))
    observe.add_argument("--docling-artifacts", type=Path, default=Path(".cache/docling/models"))
    verify = commands.add_parser("verify", help="read and verify one observation")
    verify.add_argument("observation_directory", metavar="OBSERVATION_DIRECTORY", type=Path)
    verify.add_argument("--source", type=Path)
    verify.add_argument("--docling-artifacts", type=Path)
    diagnose_command = commands.add_parser(
        "diagnose", help="publish one application-immutable diagnosis"
    )
    diagnose_command.add_argument(
        "observation_directory", metavar="OBSERVATION_DIRECTORY", type=Path
    )
    diagnose_command.add_argument(
        "--output-root",
        type=Path,
        default=Path("build/evidence-based-diagnosis"),
    )
    verify_diagnosis = commands.add_parser(
        "verify-diagnosis", help="read and verify one diagnosis"
    )
    verify_diagnosis.add_argument(
        "diagnosis_directory", metavar="DIAGNOSIS_DIRECTORY", type=Path
    )
    verify_diagnosis.add_argument(
        "--observation", metavar="OBSERVATION_DIRECTORY", type=Path
    )
    return root


def _lock_identity() -> dict[str, Any]:
    lock = Path("uv.lock")
    if not lock.is_file():
        raise RuntimeContractError("uv.lock is required from the repository root")
    try:
        installed = {
            name: importlib.metadata.version(name) for name in RUNTIME_DEPENDENCIES
        }
    except Exception as error:
        raise RuntimeContractError(
            "required extractor package metadata is unavailable"
        ) from error
    if installed != RUNTIME_DEPENDENCIES:
        raise RuntimeContractError("installed extractor versions do not match the locked v0.1 contract")
    if platform.python_implementation() != "CPython" or sys.version_info[:2] != (
        3,
        12,
    ):
        raise RuntimeContractError("the v0.1 acceptance runtime is CPython 3.12")
    try:
        lock_hash = sha256_file(lock)
    except OSError as error:
        raise RuntimeContractError("uv.lock is unavailable") from error
    return {"path": str(lock.resolve()), "sha256": lock_hash, "dependencies": installed}


def _preflight_extractors() -> tuple[dict[str, Any], Any, Any]:
    lock = _lock_identity()
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
        raise RuntimeContractError(
            "extractor runtime preflight failed"
        ) from error
    return lock, docling_adapter, markitdown_adapter


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


def _observation_id(source: dict[str, Any], lock: dict[str, Any], models: dict[str, Any]) -> str:
    return compute_observation_id(
        source,
        lock["dependencies"],
        {"docling": DOCLING_CONFIG, "markitdown": MARKITDOWN_CONFIG},
        lock["sha256"],
        models["inventory_hash"],
    )


def observe(source_value: str, output_root: Path, model_root: Path) -> tuple[ExitCode, Path]:
    lock, docling_adapter, markitdown_adapter = _preflight_extractors()
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
                "path": str(model_root.absolute()),
                "inventory_hash": None,
                "files": [],
            }
            model_identity_before = None

        now = datetime.now(UTC)
        run_id = f"{now.strftime('%Y%m%dT%H%M%S.%fZ')}-{uuid.uuid4().hex[:12]}"
        publisher = AtomicObservation(output_root, source.key, run_id)
        with publisher as staging:
            docling_result = _result(
                "docling", RUNTIME_DEPENDENCIES["docling"]
            )
            markitdown_result = _result(
                "markitdown", RUNTIME_DEPENDENCIES["markitdown"]
            )
            schema = {"name": None, "version": None}

            if model_error is not None:
                docling_result["error"] = model_error.to_dict()
            else:
                started = time.monotonic_ns()
                try:
                    os.environ["HF_HUB_OFFLINE"] = "1"
                    os.environ["TRANSFORMERS_OFFLINE"] = "1"
                    upstream, schema = docling_adapter.convert(
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
                    import shutil

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
                import shutil

                shutil.rmtree(staging / "markitdown", ignore_errors=True)
                markitdown_result["error"] = StableError(
                    "MARKITDOWN_CONVERSION_FAILED",
                    "MarkItDown conversion failed for the validated local source",
                ).to_dict()
            finally:
                markitdown_result["duration_ms"] = (
                    time.monotonic_ns() - started
                ) // 1_000_000

            docling_view = None
            if docling_result["status"] in ("SUCCESS", "PARTIAL_SUCCESS"):
                path = staging / "docling/document.md"
                docling_view = (path.read_bytes(), sha256_file(path))
            markitdown_view = None
            if markitdown_result["status"] == "SUCCESS":
                path = staging / "markitdown/document.md"
                markitdown_view = (path.read_bytes(), sha256_file(path))
            observation_id = _observation_id(source.to_dict(), lock, models)
            comparison = make_comparison(
                observation_id,
                source.to_dict(),
                _fixture_anchors(source.fixture_id),
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
                "schema_version": "tcw.preparation-manifest/v0.1",
                "milestone": "v0.1",
                "run_id": run_id,
                "observation_id": observation_id,
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
                "configurations": {
                    "docling": DOCLING_CONFIG,
                    "markitdown": MARKITDOWN_CONFIG,
                },
                "docling_document_schema": {
                    **schema,
                    "compatibility": (
                        DOCLING_DOCUMENT_COMPATIBILITY
                        if schema["name"] is not None
                        else None
                    ),
                },
                "models": models,
                "extractors": [docling_result, markitdown_result],
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
                        "preparation-manifest",
                        "application/json",
                    ),
                ]
            )
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
            _validate_staged_schemas(staging)
            verify_staged_observation(staging, staged_artifacts)
            published = publisher.publish()
            return exit_code, published
    finally:
        snapshot.cleanup()


def main(argv: list[str] | None = None) -> int:
    args = parser().parse_args(argv)
    if args.command == "verify":
        try:
            verify_command = _verification_callable("verify_command")
        except RuntimeContractError as error:
            print(sanitize_message(error), file=sys.stderr)
            return int(ExitCode.RUNTIME)

        return verify_command(
            args.observation_directory, args.source, args.docling_artifacts
        )
    if args.command == "verify-diagnosis":
        try:
            command = _diagnosis_callable(
                "diagnosis_verification", "verify_diagnosis_command"
            )
        except RuntimeContractError as error:
            print(sanitize_message(error), file=sys.stderr)
            return int(ExitCode.RUNTIME)
        return command(args.diagnosis_directory, args.observation)
    if args.command == "diagnose":
        try:
            command = _diagnosis_callable("diagnosis", "diagnose")
            published = command(
                args.observation_directory,
                args.output_root,
            )
            line = _published_diagnosis_line(published)
        except WorkbenchError as error:
            print(sanitize_message(error), file=sys.stderr)
            return int(error.exit_code)
        except Exception as error:
            print(
                f"internal diagnosis failure: {sanitize_message(error)}",
                file=sys.stderr,
            )
            return int(ExitCode.INTERNAL)
        print(json.dumps(line, sort_keys=True, separators=(",", ":")))
        return int(ExitCode.SUCCESS)
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
