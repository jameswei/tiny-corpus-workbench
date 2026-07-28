"""Application entry point for the read-only local Workbench."""

from __future__ import annotations

from pathlib import Path
from typing import Iterable

from tiny_corpus_workbench.workbench_projection import WorkbenchProjection, build_projection
from tiny_corpus_workbench.workbench_records import admit_records


def prepare_workbench(roots: Iterable[Path]) -> WorkbenchProjection:
    """Admit explicit records and compose one frozen internal read model."""

    return build_projection(admit_records(roots))


__all__ = ["prepare_workbench"]
