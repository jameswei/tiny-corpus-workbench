"""Application entry points for controlled refinement."""

from __future__ import annotations

import copy
import json
from pathlib import Path
from typing import Any

from tiny_corpus_workbench.application.records import require_record_header
from tiny_corpus_workbench.domain import IntegrityError, RuntimeContractError
from tiny_corpus_workbench.verification_results import RefinementVerificationResult


def _domain_callable(name: str) -> Any:
    try:
        from tiny_corpus_workbench import v03

        function = getattr(v03, name)
    except Exception as error:
        raise RuntimeContractError(
            "bundled refinement/schema runtime is unavailable or incompatible"
        ) from error
    if not callable(function):
        raise RuntimeContractError(
            "bundled refinement/schema runtime is unavailable or incompatible"
        )
    return function


def draft_refinement(
    diagnosis_root: Path,
    finding_id: str,
    base_root: Path,
    output: Path,
) -> dict[str, Any]:
    return _domain_callable("draft_refinement")(
        diagnosis_root, finding_id, base_root, output
    )


def supported_refiner(rule_id: str) -> dict[str, str] | None:
    """Return one current domain refiner capability without duplicating its catalog."""

    try:
        from tiny_corpus_workbench.v03 import REFINERS

        value = REFINERS.get(rule_id)
    except Exception as error:
        raise RuntimeContractError(
            "bundled refinement catalog is unavailable or incompatible"
        ) from error
    return copy.deepcopy(value) if value is not None else None


def resolve_refinement(
    proposal_file: Path,
    diagnosis_root: Path,
    base_root: Path,
    output_root: Path,
    decision: str,
) -> Path:
    return _domain_callable("resolve_refinement")(
        proposal_file, diagnosis_root, base_root, output_root, decision
    )


def verify_refinement(
    root: Path,
    diagnosis_root: Path | None = None,
    base_root: Path | None = None,
) -> RefinementVerificationResult:
    return _domain_callable("verify_refinement")(root, diagnosis_root, base_root)


def verify_refinement_command(
    root: Path,
    diagnosis_root: Path | None,
    base_root: Path | None,
) -> int:
    return _domain_callable("verify_refinement_command")(
        root, diagnosis_root, base_root
    )


def published_refinement_line(published: Path) -> dict[str, Any]:
    manifest_path = published / "refinement-manifest.json"
    try:
        manifest = json.loads(manifest_path.read_text("utf-8"))
        require_record_header(manifest, "refinement")
        result = {
            "manifest": str(manifest_path.resolve()),
            "run_id": manifest["run_id"],
            "decision": manifest["decision"],
            "revision_id": manifest["revision_id"],
        }
        if (
            not isinstance(result["run_id"], str)
            or result["run_id"] != published.name
            or result["decision"] not in {"APPROVED", "REJECTED"}
            or (
                result["revision_id"] is not None
                and (
                    not isinstance(result["revision_id"], str)
                    or len(result["revision_id"]) != 64
                )
            )
        ):
            raise ValueError
        return result
    except Exception as error:
        raise IntegrityError(
            "published refinement manifest is unavailable or invalid"
        ) from error


__all__ = [
    "draft_refinement",
    "published_refinement_line",
    "resolve_refinement",
    "supported_refiner",
    "verify_refinement",
    "verify_refinement_command",
]
