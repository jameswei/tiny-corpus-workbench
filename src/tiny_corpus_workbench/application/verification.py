"""Application entry points for record verification."""

from tiny_corpus_workbench.verification import verify_command, verify_observation
from tiny_corpus_workbench.application.diagnosis import (
    verify_diagnosis,
    verify_diagnosis_command,
)

__all__ = [
    "verify_command",
    "verify_diagnosis",
    "verify_diagnosis_command",
    "verify_observation",
]
