"""Synchronous application service for the interactive document lifecycle."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Callable

from tiny_corpus_workbench.application.diagnosis import diagnose
from tiny_corpus_workbench.application.mutation_coordinator import (
    MutationBusyError,
    MutationCoordinator,
)
from tiny_corpus_workbench.application.refinement import (
    draft_refinement,
    resolve_refinement,
    supported_refiner,
)
from tiny_corpus_workbench.application.refinement_drafts import (
    DraftContext,
    RefinementDraftStore,
    draft_key as make_draft_key,
)
from tiny_corpus_workbench.application.workbench import (
    AcceptedWorkspaceSnapshot,
    WorkbenchState,
    WorkspaceStaleError,
)
from tiny_corpus_workbench.canonical_json import canonical_json
from tiny_corpus_workbench.domain import (
    IntegrityError,
    WorkbenchError,
    sanitize_message,
)
from tiny_corpus_workbench.workbench_records import MAX_STRUCTURED_RESPONSE


class LifecycleBusyError(WorkbenchError):
    """Background observation currently owns Workbench mutation."""


class ActionNotAvailableError(WorkbenchError):
    """The selected record, relationship, finding, or refiner is ineligible."""


class LifecycleNotFoundError(WorkbenchError):
    """One well-formed opaque application key has no live object."""


class ResponseTooLargeError(WorkbenchError):
    """A lifecycle response would exceed the Workbench response bound."""


DiagnoseCallable = Callable[[Path, Path], Path]
DraftCallable = Callable[[Path, str, Path, Path], dict[str, object]]
ResolveCallable = Callable[[Path, Path, Path, Path, str], Path]


def _subject_key(
    snapshot: AcceptedWorkspaceSnapshot, diagnosis_record_key: str
) -> str | None:
    detail = snapshot.projection.details.get(diagnosis_record_key)
    if detail is None or detail["kind"] != "DIAGNOSIS":
        return None
    matches = [
        item
        for item in detail["relationships"]
        if item["relation"] == "DIAGNOSIS_SUBJECT" and item["state"] == "MATCH"
    ]
    if len(matches) != 1:
        return None
    value = matches[0].get("target_record_key")
    return value if isinstance(value, str) else None


class WorkbenchLifecycleService:
    """Publish lifecycle records and keep proposal decision context process-local."""

    def __init__(
        self,
        state: WorkbenchState,
        coordinator: MutationCoordinator,
        *,
        draft_store: RefinementDraftStore | None = None,
        diagnose_service: DiagnoseCallable = diagnose,
        draft_service: DraftCallable = draft_refinement,
        resolve_service: ResolveCallable = resolve_refinement,
        response_limit: int = MAX_STRUCTURED_RESPONSE,
    ) -> None:
        self.state = state
        self.coordinator = coordinator
        self.drafts = draft_store or RefinementDraftStore(state.workspace)
        self._diagnose = diagnose_service
        self._draft = draft_service
        self._resolve = resolve_service
        self.response_limit = response_limit

    def _lease(self):
        try:
            return self.coordinator.acquire("LIFECYCLE")
        except MutationBusyError as error:
            raise LifecycleBusyError("background observation is active") from error

    def diagnose(self, subject_record_key: str) -> dict[str, object]:
        with self._lease():
            snapshot = self.state.capture_snapshot()
            if subject_record_key not in snapshot.projection.details:
                raise LifecycleNotFoundError("record is not in the accepted workspace")
            if self.state.diagnosis_subject(snapshot, subject_record_key) is None:
                raise ActionNotAvailableError("record cannot be diagnosed")
            subject = self.state.resolve_actionable_roots(
                snapshot, [subject_record_key]
            )[subject_record_key]
            published = self._diagnose(
                subject, self.state.workspace / "evidence-based-diagnosis"
            )
            manifest = self._published_manifest(
                published, "diagnosis-manifest.json", "diagnosis"
            )
            publication = {
                "kind": "DIAGNOSIS",
                "run_id": manifest["run_id"],
                "record_key": None,
            }
            return self._refresh_publication(
                publication,
                kind="DIAGNOSIS",
                run_id=manifest["run_id"],
                identity_name="diagnosis_id",
                identity_value=manifest["diagnosis_id"],
            )

    def create_proposal(
        self, diagnosis_record_key: str, finding_id: str
    ) -> dict[str, object]:
        with self._lease():
            snapshot = self.state.capture_snapshot()
            detail = snapshot.projection.details.get(diagnosis_record_key)
            if detail is None:
                raise LifecycleNotFoundError(
                    "diagnosis is not in the accepted workspace"
                )
            if detail["kind"] != "DIAGNOSIS":
                raise ActionNotAvailableError("selected record is not a diagnosis")
            finding = next(
                (
                    item
                    for item in detail["view"]["findings"]
                    if item["finding_id"] == finding_id
                ),
                None,
            )
            if finding is None:
                raise ActionNotAvailableError("finding is absent from the diagnosis")
            refiner = supported_refiner(finding["rule_id"])
            base_record_key = _subject_key(snapshot, diagnosis_record_key)
            if (
                refiner is None
                or base_record_key is None
                or self.state.diagnosis_base(snapshot, diagnosis_record_key) is None
            ):
                raise ActionNotAvailableError("finding is not actionable")
            roots = self.state.resolve_actionable_roots(
                snapshot, [diagnosis_record_key, base_record_key]
            )
            with self.drafts.staging_path() as staged:
                self._draft(
                    roots[diagnosis_record_key],
                    finding_id,
                    roots[base_record_key],
                    staged,
                )
                proposal, raw = self.drafts.inspect_staged(staged)
                draft_id = proposal["draft_id"]
                if not isinstance(draft_id, str):
                    raise IntegrityError("refinement draft identity is invalid")
                context = DraftContext(
                    draft_key=make_draft_key(
                        draft_id, diagnosis_record_key, base_record_key
                    ),
                    draft_id=draft_id,
                    diagnosis_record_key=diagnosis_record_key,
                    base_record_key=base_record_key,
                )
                response = self._proposal_response(context, proposal)
                if len(canonical_json(response)) > self.response_limit:
                    raise ResponseTooLargeError("lifecycle response is too large")
                destination = self.drafts.publish(staged, draft_id, raw)
                registered = self.drafts.register(
                    draft_id, diagnosis_record_key, base_record_key
                )
                response = self._proposal_response(registered, proposal)
                response["draft"]["cli_continuation"]["proposal_path"] = str(
                    destination.resolve()
                )
                return response

    def approve(self, draft_key: str) -> dict[str, object]:
        return self.resolve(draft_key, "APPROVED")

    def reject(self, draft_key: str) -> dict[str, object]:
        return self.resolve(draft_key, "REJECTED")

    def resolve(self, draft_key: str, decision: str) -> dict[str, object]:
        if decision not in {"APPROVED", "REJECTED"}:
            raise ActionNotAvailableError("decision is unavailable")
        with self._lease():
            context = self.drafts.context(draft_key)
            if context is None:
                raise LifecycleNotFoundError("refinement draft context is not live")
            snapshot = self.state.capture_snapshot()
            if (
                context.diagnosis_record_key not in snapshot.actionable_roots
                or context.base_record_key not in snapshot.actionable_roots
                or _subject_key(snapshot, context.diagnosis_record_key)
                != context.base_record_key
                or self.state.diagnosis_base(
                    snapshot, context.diagnosis_record_key
                )
                is None
            ):
                raise WorkspaceStaleError("refinement draft context is stale")
            roots = self.state.resolve_actionable_roots(
                snapshot,
                [context.diagnosis_record_key, context.base_record_key],
            )
            try:
                self.drafts.read(context.draft_id)
            except IntegrityError as error:
                raise WorkspaceStaleError("refinement draft is stale") from error
            proposal_path = self.drafts.root / f"{context.draft_id}.json"
            published = self._resolve(
                proposal_path,
                roots[context.diagnosis_record_key],
                roots[context.base_record_key],
                self.state.workspace / "controlled-revisions",
                decision,
            )
            manifest = self._published_manifest(
                published, "refinement-manifest.json", "refinement"
            )
            publication = {
                "kind": "REFINEMENT",
                "decision": manifest["decision"],
                "run_id": manifest["run_id"],
                "revision_id": manifest["revision_id"],
                "record_key": None,
            }
            return self._refresh_publication(
                publication,
                kind="REFINEMENT",
                run_id=manifest["run_id"],
                identity_name="draft_id",
                identity_value=context.draft_id,
            )

    def _proposal_response(
        self, context: DraftContext, proposal: dict[str, object]
    ) -> dict[str, object]:
        proposal_path = self.drafts.root / f"{context.draft_id}.json"
        snapshot = self.state.capture_snapshot()
        roots = self.state.resolve_actionable_roots(
            snapshot, [context.diagnosis_record_key, context.base_record_key]
        )
        finding = proposal["finding"]
        if not isinstance(finding, dict):
            raise IntegrityError("refinement draft finding is invalid")
        return {
            "draft": {
                "draft_key": context.draft_key,
                "draft_id": context.draft_id,
                "diagnosis_record_key": context.diagnosis_record_key,
                "base_record_key": context.base_record_key,
                "finding": {
                    key: finding[key]
                    for key in ("finding_id", "rule_id", "summary")
                },
                "refiner": proposal["refiner"],
                "affected_refs": proposal["affected_refs"],
                "edits": proposal["forward_edits"],
                "cli_continuation": {
                    "proposal_path": str(proposal_path.resolve()),
                    "diagnosis_path": str(
                        roots[context.diagnosis_record_key].resolve()
                    ),
                    "base_path": str(roots[context.base_record_key].resolve()),
                    "output_root_path": str(
                        (self.state.workspace / "controlled-revisions").resolve()
                    ),
                },
            }
        }

    @staticmethod
    def _published_manifest(
        published: Path, name: str, label: str
    ) -> dict[str, object]:
        try:
            value = json.loads((published / name).read_text("utf-8"))
            if not isinstance(value, dict) or value.get("run_id") != published.name:
                raise ValueError
            return value
        except Exception as error:
            raise IntegrityError(
                f"published {label} manifest is unavailable or invalid"
            ) from error

    def _refresh_publication(
        self,
        publication: dict[str, object],
        *,
        kind: str,
        run_id: object,
        identity_name: str,
        identity_value: object,
    ) -> dict[str, object]:
        try:
            refreshed = self.state.refresh()
            if not refreshed.succeeded:
                return {
                    "publication": publication,
                    "refresh": {"status": "FAILED", "message": refreshed.message},
                }
            matches = [
                item
                for item in self.state.projection.projection["records"]
                if item["kind"] == kind
                and item["run_id"] == run_id
                and item["primary_identity"]
                == {"name": identity_name, "value": identity_value}
            ]
            if len(matches) != 1:
                raise IntegrityError(
                    "published record is absent from the refreshed workspace"
                )
            publication["record_key"] = matches[0]["record_key"]
            return {
                "publication": publication,
                "refresh": {"status": "READY", "message": None},
            }
        except Exception as error:
            publication["record_key"] = None
            return {
                "publication": publication,
                "refresh": {"status": "FAILED", "message": sanitize_message(error)},
            }


__all__ = [
    "ActionNotAvailableError",
    "LifecycleBusyError",
    "LifecycleNotFoundError",
    "ResponseTooLargeError",
    "WorkbenchLifecycleService",
]
