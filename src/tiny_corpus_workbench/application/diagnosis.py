"""Application entry points for diagnosis publication and verification."""

from __future__ import annotations

import json
import stat
from pathlib import Path
from typing import Any

from tiny_corpus_workbench.application.records import require_record_header
from tiny_corpus_workbench.domain import IntegrityError, RuntimeContractError
from tiny_corpus_workbench.verification_results import DiagnosisVerificationResult


def _domain_callable(name: str) -> Any:
    try:
        from tiny_corpus_workbench import v03

        function = getattr(v03, name)
    except Exception as error:
        raise RuntimeContractError(
            "bundled diagnosis/schema runtime is unavailable or incompatible"
        ) from error
    if not callable(function):
        raise RuntimeContractError(
            "bundled diagnosis/schema runtime is unavailable or incompatible"
        )
    return function


def diagnose(root: Path, output_root: Path) -> Path:
    """Publish one diagnosis through the domain implementation."""

    return _domain_callable("diagnose")(root, output_root)


def verify_diagnosis(
    root: Path, subject_root: Path | None = None
) -> DiagnosisVerificationResult:
    """Verify one diagnosis through the domain implementation."""

    return _domain_callable("verify_diagnosis")(root, subject_root)


def verify_diagnosis_command(
    root: Path, subject_root: Path | None
) -> int:
    """Run the diagnosis verifier command adapter."""

    return _domain_callable("verify_diagnosis_command")(root, subject_root)


def published_diagnosis_line(published: Path) -> dict[str, Any]:
    """Verify one publication and return its compact CLI result."""

    manifest_path = published / "diagnosis-manifest.json"
    try:
        from tiny_corpus_workbench.diagnosis_rules import snapshot_tree

        before = snapshot_tree(published)
        manifest = json.loads(manifest_path.read_text("utf-8"))
        require_record_header(manifest, "diagnosis")
        verification = verify_diagnosis(published)
        if verification.artifact_integrity.status != "VERIFIED":
            raise IntegrityError(
                "published diagnosis manifest is unavailable or invalid"
            )
        if not stat.S_ISREG(manifest_path.lstat().st_mode):
            raise OSError
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
        if snapshot_tree(published) != before:
            raise IntegrityError(
                "published diagnosis changed before summary output"
            )
        return line
    except (RuntimeContractError, IntegrityError):
        raise
    except Exception as error:
        raise IntegrityError(
            "published diagnosis manifest is unavailable or invalid"
        ) from error


__all__ = [
    "diagnose",
    "published_diagnosis_line",
    "verify_diagnosis",
    "verify_diagnosis_command",
]
