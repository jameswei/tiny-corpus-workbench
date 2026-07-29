"""Small internal value types for transient verification results."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any


@dataclass(frozen=True)
class VerificationIssue:
    code: str
    path: str | None
    message: str

    def to_json_object(self) -> dict[str, Any]:
        return {
            "code": self.code,
            "path": self.path,
            "message": self.message,
        }


@dataclass(frozen=True)
class VerificationState:
    status: str

    def to_json_object(self) -> dict[str, str]:
        return {"status": self.status}


@dataclass(frozen=True)
class ArtifactIntegrity:
    status: str
    issues: tuple[VerificationIssue, ...]

    def to_json_object(self) -> dict[str, Any]:
        return {
            "status": self.status,
            "issues": [issue.to_json_object() for issue in self.issues],
        }


@dataclass(frozen=True)
class ObservationVerificationResult:
    observation_directory: str
    artifact_integrity: ArtifactIntegrity
    source_state: VerificationState
    model_state: VerificationState

    def to_json_object(self) -> dict[str, Any]:
        return {
            "observation_directory": self.observation_directory,
            "artifact_integrity": self.artifact_integrity.to_json_object(),
            "source_state": self.source_state.to_json_object(),
            "model_state": self.model_state.to_json_object(),
        }


@dataclass(frozen=True)
class DiagnosisVerificationResult:
    diagnosis_directory: str
    artifact_integrity: ArtifactIntegrity
    subject_state: VerificationState
    derivation_state: VerificationState

    def to_json_object(self) -> dict[str, Any]:
        return {
            "diagnosis_directory": self.diagnosis_directory,
            "artifact_integrity": self.artifact_integrity.to_json_object(),
            "subject_state": self.subject_state.to_json_object(),
            "derivation_state": self.derivation_state.to_json_object(),
        }


@dataclass(frozen=True)
class RefinementVerificationResult:
    refinement_directory: str
    artifact_integrity: ArtifactIntegrity
    diagnosis_state: VerificationState
    base_state: VerificationState
    derivation_state: VerificationState
    reversibility_state: VerificationState

    def to_json_object(self) -> dict[str, Any]:
        return {
            "refinement_directory": self.refinement_directory,
            "artifact_integrity": self.artifact_integrity.to_json_object(),
            "diagnosis_state": self.diagnosis_state.to_json_object(),
            "base_state": self.base_state.to_json_object(),
            "derivation_state": self.derivation_state.to_json_object(),
            "reversibility_state": self.reversibility_state.to_json_object(),
        }


@dataclass(frozen=True)
class CorpusSourceState:
    member_id: str
    state: VerificationState

    def to_json_object(self) -> dict[str, Any]:
        return {
            "member_id": self.member_id,
            "state": self.state.to_json_object(),
        }


@dataclass(frozen=True)
class CorpusRevisionState:
    member_id: str
    revision_id: str
    refinement_state: VerificationState
    diagnosis_state: VerificationState
    base_state: VerificationState

    def to_json_object(self) -> dict[str, Any]:
        return {
            "member_id": self.member_id,
            "revision_id": self.revision_id,
            "refinement_state": self.refinement_state.to_json_object(),
            "diagnosis_state": self.diagnosis_state.to_json_object(),
            "base_state": self.base_state.to_json_object(),
        }


@dataclass(frozen=True)
class CorpusVerificationResult:
    corpus_directory: str
    artifact_integrity: ArtifactIntegrity
    specification_state: VerificationState
    source_states: tuple[CorpusSourceState, ...]
    model_state: VerificationState
    revision_states: tuple[CorpusRevisionState, ...]

    def to_json_object(self) -> dict[str, Any]:
        return {
            "corpus_directory": self.corpus_directory,
            "artifact_integrity": self.artifact_integrity.to_json_object(),
            "specification_state": self.specification_state.to_json_object(),
            "source_states": [
                state.to_json_object() for state in self.source_states
            ],
            "model_state": self.model_state.to_json_object(),
            "revision_states": [
                state.to_json_object() for state in self.revision_states
            ],
        }
