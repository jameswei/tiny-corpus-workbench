from __future__ import annotations

import argparse
import importlib
import json
import os
import stat
import sys
from pathlib import Path
from typing import Any

from tiny_corpus_workbench.application.observation import observe
from tiny_corpus_workbench.application.diagnosis import (
    diagnose,
    published_diagnosis_line,
    verify_diagnosis_command,
)
from tiny_corpus_workbench.application.records import require_record_header
from tiny_corpus_workbench.domain import (
    ExitCode,
    InputError,
    IntegrityError,
    RuntimeContractError,
    WorkbenchError,
    sanitize_message,
)


ACTIVE_RUNTIME_ERROR = (
    "active runtime does not match this package provenance registry"
)
WORKBENCH_ROOT_MANIFESTS = (
    "manifest.json",
    "diagnosis-manifest.json",
    "refinement-manifest.json",
    "corpus-manifest.json",
)


def _runtime_import_message(error: Exception, fallback: str) -> str:
    return ACTIVE_RUNTIME_ERROR if isinstance(error, ImportError) else fallback


def _active_build_provenance(**arguments: Any) -> dict[str, Any]:
    try:
        from tiny_corpus_workbench.supported_provenance import (
            active_build_provenance,
        )

        return active_build_provenance(**arguments)
    except RuntimeContractError:
        raise
    except Exception as error:
        raise RuntimeContractError(ACTIVE_RUNTIME_ERROR) from error


def _preflight_workbench_roots(roots: list[Path]) -> None:
    for root in roots:
        try:
            metadata = root.lstat()
        except FileNotFoundError as error:
            raise InputError("RECORD root is unavailable") from error
        except OSError:
            continue
        if stat.S_ISLNK(metadata.st_mode):
            continue
        if not stat.S_ISDIR(metadata.st_mode):
            raise InputError("RECORD must be a root directory")
        try:
            known = any(
                os.path.lexists(root / name) for name in WORKBENCH_ROOT_MANIFESTS
            )
        except OSError:
            continue
        if not known:
            raise InputError("RECORD root is not a supported record")


def _verification_callable(name: str) -> Any:
    try:
        from tiny_corpus_workbench.application import verification as module

        function = getattr(module, name)
    except Exception as error:
        raise RuntimeContractError(
            _runtime_import_message(
                error,
                "bundled verification/schema runtime is unavailable or incompatible",
            )
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
            _runtime_import_message(
                error,
                "bundled diagnosis/schema runtime is unavailable or incompatible",
            )
        ) from error
    if not callable(function):
        raise RuntimeContractError(
            "bundled diagnosis/schema runtime is unavailable or incompatible"
        )
    return function


def _corpus_callable(module_name: str, name: str) -> Any:
    try:
        module = importlib.import_module(f"tiny_corpus_workbench.{module_name}")
        function = getattr(module, name)
    except Exception as error:
        raise RuntimeContractError(
            _runtime_import_message(
                error,
                "bundled corpus/schema runtime is unavailable or incompatible",
            )
        ) from error
    if not callable(function):
        raise RuntimeContractError(
            "bundled corpus/schema runtime is unavailable or incompatible"
        )
    return function


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
        "document_directory", metavar="DOCUMENT_DIRECTORY", type=Path
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
    verify_diagnosis.add_argument(
        "--subject", metavar="DOCUMENT_DIRECTORY", type=Path
    )
    draft = commands.add_parser(
        "draft-refinement", help="draft one explicit refinement decision"
    )
    draft.add_argument("diagnosis_directory", metavar="DIAGNOSIS_DIRECTORY", type=Path)
    draft.add_argument("--finding", required=True, metavar="FINDING_ID")
    draft.add_argument("--base", required=True, metavar="BASE_DIRECTORY", type=Path)
    draft.add_argument("--output", required=True, metavar="DECISION_FILE", type=Path)
    resolve = commands.add_parser(
        "resolve-refinement", help="publish one approved or rejected refinement"
    )
    resolve.add_argument("decision_file", metavar="DECISION_FILE", type=Path)
    resolve.add_argument("--diagnosis", required=True, metavar="DIAGNOSIS_DIRECTORY", type=Path)
    resolve.add_argument("--base", required=True, metavar="BASE_DIRECTORY", type=Path)
    resolve.add_argument(
        "--output-root", type=Path, default=Path("build/controlled-revisions")
    )
    verify_refinement = commands.add_parser(
        "verify-refinement", help="read and verify one refinement record"
    )
    verify_refinement.add_argument(
        "refinement_directory", metavar="REFINEMENT_DIRECTORY", type=Path
    )
    verify_refinement.add_argument("--diagnosis", type=Path)
    verify_refinement.add_argument("--base", type=Path)
    inspect_corpus = commands.add_parser(
        "inspect-corpus",
        help="publish one static inspection report for an explicit local corpus",
    )
    inspect_corpus.add_argument(
        "corpus_spec", metavar="CORPUS_SPEC", type=Path
    )
    inspect_corpus.add_argument(
        "--output-root",
        type=Path,
        default=Path("build/corpus-inspection"),
    )
    inspect_corpus.add_argument(
        "--docling-artifacts",
        type=Path,
        default=Path(".cache/docling/models"),
    )
    verify_corpus = commands.add_parser(
        "verify-corpus", help="read and verify one corpus inspection"
    )
    verify_corpus.add_argument(
        "corpus_directory", metavar="CORPUS_DIRECTORY", type=Path
    )
    verify_corpus.add_argument("--spec", metavar="CORPUS_SPEC", type=Path)
    workbench = commands.add_parser(
        "workbench", help="serve explicit records in a read-only local workbench"
    )
    workbench.add_argument("records", metavar="RECORD", type=Path, nargs="+")
    workbench.add_argument("--port", default="8765")
    workbench.add_argument("--no-open", action="store_true")
    return root


def main(argv: list[str] | None = None) -> int:
    args = parser().parse_args(argv)
    if args.command == "workbench":
        server = None
        try:
            _active_build_provenance(command_id="tcw.workbench")
            from tiny_corpus_workbench.workbench_projection import build_projection
            from tiny_corpus_workbench.workbench_records import admit_records
            from tiny_corpus_workbench.workbench_server import (
                create_server,
                open_browser,
                startup_document,
                validate_port,
            )

            port = validate_port(args.port)
            _preflight_workbench_roots(args.records)
            records = admit_records(args.records)
            try:
                projection = build_projection(records)
            except IntegrityError as error:
                if "structured response limit" not in str(error):
                    raise
                raise InputError(
                    "workbench projection exceeds the structured response limit"
                ) from error
            server = create_server(records, projection, port)
            try:
                startup = startup_document(projection, port)
                print(
                    json.dumps(startup, sort_keys=True, separators=(",", ":")),
                    flush=True,
                )
                if not args.no_open:
                    warning = open_browser(startup["url"])
                    if warning is not None:
                        print(warning, file=sys.stderr, flush=True)
                server.serve_forever()
            except KeyboardInterrupt:
                pass
            return int(ExitCode.SUCCESS)
        except KeyboardInterrupt:
            return int(ExitCode.SUCCESS)
        except WorkbenchError as error:
            print(sanitize_message(error), file=sys.stderr)
            return int(error.exit_code)
        except Exception:
            print("internal workbench failure", file=sys.stderr)
            return int(ExitCode.INTERNAL)
        finally:
            if server is not None:
                server.server_close()
    if args.command == "inspect-corpus":
        try:
            command = _corpus_callable(
                "application.corpus", "inspect_corpus"
            )
            published = command(
                args.corpus_spec,
                args.output_root,
                args.docling_artifacts,
            )
            verify = _corpus_callable(
                "application.corpus", "verify_corpus"
            )
            verification = verify(published.directory)
            if verification["artifact_integrity"]["status"] != "VERIFIED":
                raise IntegrityError(
                    "published corpus inspection failed verification"
                )
            line = {
                "corpus_id": published.corpus_id,
                "manifest": str(published.manifest_path.resolve()),
                "member_count": published.member_count,
                "run_id": published.run_id,
                "snapshot_id": published.snapshot_id,
                "status": published.status,
            }
        except WorkbenchError as error:
            print(sanitize_message(error), file=sys.stderr)
            return int(error.exit_code)
        except Exception as error:
            print(
                f"internal corpus inspection failure: {sanitize_message(error)}",
                file=sys.stderr,
            )
            return int(ExitCode.INTERNAL)
        print(json.dumps(line, sort_keys=True, separators=(",", ":")))
        return published.exit_code
    if args.command == "verify-corpus":
        try:
            command = _corpus_callable(
                "application.corpus", "verify_corpus"
            )
            verification = command(args.corpus_directory, args.spec)
        except WorkbenchError as error:
            print(sanitize_message(error), file=sys.stderr)
            return int(error.exit_code)
        except Exception as error:
            print(
                f"internal corpus verifier failure: {sanitize_message(error)}",
                file=sys.stderr,
            )
            return int(ExitCode.INTERNAL)
        print(
            json.dumps(
                verification,
                ensure_ascii=False,
                sort_keys=True,
                separators=(",", ":"),
            )
        )
        return (
            int(ExitCode.SUCCESS)
            if verification["artifact_integrity"]["status"] == "VERIFIED"
            else int(ExitCode.INTEGRITY)
        )
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
        if args.observation is not None and args.subject is not None:
            print("--observation and --subject are mutually exclusive", file=sys.stderr)
            return int(ExitCode.INPUT)
        try:
            try:
                candidate = json.loads(
                    (args.diagnosis_directory / "diagnosis-manifest.json").read_text("utf-8")
                )
                require_record_header(candidate, "diagnosis")
            except Exception:
                print(
                    "diagnosis record format is unsupported; regenerate the "
                    "record with the current project",
                    file=sys.stderr,
                )
                return int(ExitCode.INPUT)
        except RuntimeContractError as error:
            print(sanitize_message(error), file=sys.stderr)
            return int(ExitCode.RUNTIME)
        return verify_diagnosis_command(
            args.diagnosis_directory, args.subject or args.observation
        )
    if args.command == "diagnose":
        try:
            published = diagnose(
                args.document_directory,
                args.output_root,
            )
            line = published_diagnosis_line(published)
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
    if args.command in {"draft-refinement", "resolve-refinement", "verify-refinement"}:
        try:
            from tiny_corpus_workbench.application.refinement import (
                draft_refinement,
                published_refinement_line,
                resolve_refinement,
                verify_refinement_command,
            )

            if args.command == "draft-refinement":
                result = draft_refinement(
                    args.diagnosis_directory, args.finding, args.base, args.output
                )
                print(json.dumps(result, sort_keys=True, separators=(",", ":")))
                return int(ExitCode.SUCCESS)
            if args.command == "resolve-refinement":
                published = resolve_refinement(
                    args.decision_file, args.diagnosis, args.base, args.output_root
                )
                print(
                    json.dumps(
                        published_refinement_line(published),
                        sort_keys=True,
                        separators=(",", ":"),
                    )
                )
                return int(ExitCode.SUCCESS)
            return verify_refinement_command(
                args.refinement_directory, args.diagnosis, args.base
            )
        except WorkbenchError as error:
            print(sanitize_message(error), file=sys.stderr)
            return int(error.exit_code)
        except Exception as error:
            print(
                f"internal refinement failure: {sanitize_message(error)}",
                file=sys.stderr,
            )
            return int(ExitCode.INTERNAL)
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
