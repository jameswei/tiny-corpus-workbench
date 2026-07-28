"""Application entry points for corpus inspection and verification."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from tiny_corpus_workbench.domain import RuntimeContractError


def _implementation_callable(module_name: str, name: str) -> Any:
    try:
        module = __import__(
            f"tiny_corpus_workbench.{module_name}",
            fromlist=[name],
        )
        function = getattr(module, name)
    except Exception as error:
        raise RuntimeContractError(
            "bundled corpus/schema runtime is unavailable or incompatible"
        ) from error
    if not callable(function):
        raise RuntimeContractError(
            "bundled corpus/schema runtime is unavailable or incompatible"
        )
    return function


def inspect_corpus(
    corpus_spec: str | Path,
    output_root: Path,
    model_root: Path,
) -> Any:
    """Inspect one explicit local corpus and publish its evidence."""

    return _implementation_callable("corpus_publication", "inspect_corpus")(
        corpus_spec, output_root, model_root
    )


def verify_corpus(
    corpus_root: Path,
    spec_path: Path | None = None,
) -> dict[str, Any]:
    """Verify one published corpus without changing it."""

    return _implementation_callable("corpus_verification", "verify_corpus")(
        corpus_root, spec_path
    )


__all__ = ["inspect_corpus", "verify_corpus"]
