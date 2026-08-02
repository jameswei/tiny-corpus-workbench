from __future__ import annotations

import json
import os
import shutil
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from tiny_corpus_workbench import cli
from tiny_corpus_workbench.application.diagnosis import diagnose
from tiny_corpus_workbench.application.lifecycle import (
    ActionNotAvailableError,
    LifecycleBusyError,
    LifecycleNotFoundError,
    ResponseTooLargeError,
    WorkbenchLifecycleService,
)
from tiny_corpus_workbench.application.mutation_coordinator import (
    MutationBusyError,
    MutationCoordinator,
)
from tiny_corpus_workbench.application.refinement import draft_refinement
from tiny_corpus_workbench.application.refinement_drafts import draft_key
from tiny_corpus_workbench.application.workbench import (
    RefreshResult,
    WorkbenchState,
    WorkspaceStaleError,
)
from tiny_corpus_workbench.artifacts import (
    REQUIRED_MODEL_FILES,
    canonical_json as record_json,
)
from tiny_corpus_workbench.domain import IntegrityError
from tests.unit.test_v03_controlled_revisions import (
    PDF_SOURCE,
    docling_with_repeated_margins,
    markitdown,
)
from tests.unit.workbench_test_support import (
    REPOSITORY,
    PublishedChain,
    PublishedRefinements,
    run_corpus,
)


class WorkbenchLifecycleTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.published = PublishedRefinements()
        cls.chain = PublishedChain()
        cls.shared = tempfile.TemporaryDirectory(
            dir=Path(tempfile.gettempdir()).resolve()
        )
        shared = Path(cls.shared.name)

        model_root = shared / "models"
        for relative in REQUIRED_MODEL_FILES:
            path = model_root / relative
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text("test-model", "utf-8")
        with (
            patch(
                "tiny_corpus_workbench.extractors.docling.convert",
                side_effect=docling_with_repeated_margins,
            ),
            patch(
                "tiny_corpus_workbench.extractors.markitdown.convert",
                side_effect=markitdown,
            ),
        ):
            code, cls.d007_observation = cli.observe(
                str(PDF_SOURCE), shared / "d007-observations", model_root
            )
        if int(code) != 0:
            raise RuntimeError("D007 support fixture observation failed")
        cls.d007_diagnosis = diagnose(
            cls.d007_observation, shared / "d007-diagnoses"
        )

        corpus_input = shared / "corpus-input"
        corpus_input.mkdir()
        corpus_spec = corpus_input / "actionability-corpus.json"
        whitespace_source = corpus_input / "whitespace-cleanup.md"
        short_source = corpus_input / "short-note.md"
        shutil.copy2(
            REPOSITORY / "fixtures/refinement/whitespace-cleanup.md",
            whitespace_source,
        )
        shutil.copy2(
            REPOSITORY / "fixtures/diagnosis/short-note.md", short_source
        )
        corpus_spec.write_bytes(
            record_json(
                {
                    "corpus_id": "actionability-matrix",
                    "title": "Actionability matrix",
                    "members": [
                        {
                            "member_id": "whitespace",
                            "family": "refinement",
                            "format": "md",
                            "source": os.path.relpath(
                                whitespace_source, corpus_spec.parent
                            ),
                        },
                        {
                            "member_id": "short-note",
                            "family": "diagnosis",
                            "format": "md",
                            "source": os.path.relpath(
                                short_source, corpus_spec.parent
                            ),
                        },
                    ],
                }
            )
        )
        corpus = run_corpus(
            "inspect",
            str(corpus_spec),
            "--output-root",
            str(shared / "corpus-output"),
            "--docling-artifacts",
            str(shared / "missing-models"),
        )
        cls.actionability_corpus = Path(corpus["manifest"]).parent

    @classmethod
    def tearDownClass(cls) -> None:
        cls.shared.cleanup()
        cls.chain.close()
        cls.published.close()

    def setUp(self) -> None:
        self.temporary = tempfile.TemporaryDirectory()
        self.workspace = Path(self.temporary.name)
        self._copy(
            self.published.observation, "extraction-observatory", "observation"
        )
        self._copy(
            self.published.diagnosis, "evidence-based-diagnosis", "diagnosis"
        )
        self.state = WorkbenchState(self.workspace)
        self.coordinator = MutationCoordinator()
        self.service = WorkbenchLifecycleService(self.state, self.coordinator)
        self.observation_key = self._key("OBSERVATION")
        self.diagnosis_key = self._key("DIAGNOSIS")
        detail = self.state.projection.details[self.diagnosis_key]
        self.finding_id = next(
            item["finding_id"]
            for item in detail["view"]["findings"]
            if item["rule_id"] == "D009"
        )

    def tearDown(self) -> None:
        self.temporary.cleanup()

    def _copy(self, source: Path, family: str, label: str) -> Path:
        target = self.workspace / family / label / source.name
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copytree(source, target)
        return target

    def _key(self, kind: str) -> str:
        return next(
            item["record_key"]
            for item in self.state.projection.projection["records"]
            if item["kind"] == kind
        )

    def test_coordinator_is_non_blocking_and_release_is_exactly_once(self) -> None:
        lease = self.coordinator.acquire("OBSERVATION")
        with self.assertRaises(MutationBusyError):
            self.coordinator.acquire("LIFECYCLE")
        with self.assertRaises(LifecycleBusyError):
            self.service.create_proposal(self.diagnosis_key, self.finding_id)
        lease.release()
        lease.release()
        with self.coordinator.acquire("LIFECYCLE"):
            self.assertEqual(self.coordinator.owner, "LIFECYCLE")
        self.assertIsNone(self.coordinator.owner)

    def test_proposal_is_canonical_reused_and_context_is_process_local(self) -> None:
        first = self.service.create_proposal(self.diagnosis_key, self.finding_id)
        second = self.service.create_proposal(self.diagnosis_key, self.finding_id)
        self.assertEqual(first, second)
        draft = first["draft"]
        path = Path(draft["cli_continuation"]["proposal_path"])
        self.assertTrue(path.is_file())
        self.assertEqual(
            path.parent, (self.workspace / "refinement-drafts").resolve()
        )
        self.assertEqual(
            json.loads(path.read_text("utf-8"))["draft_id"], draft["draft_id"]
        )
        restarted = WorkbenchLifecycleService(
            self.state, MutationCoordinator()
        )
        with self.assertRaises(LifecycleNotFoundError):
            restarted.approve(draft["draft_key"])

    def test_resolution_publishes_and_retains_draft(self) -> None:
        proposal = self.service.create_proposal(
            self.diagnosis_key, self.finding_id
        )["draft"]
        result = self.service.approve(proposal["draft_key"])
        self.assertEqual(result["publication"]["decision"], "APPROVED")
        self.assertIsNotNone(result["publication"]["revision_id"])
        self.assertIsNotNone(result["publication"]["record_key"])
        self.assertEqual(result["refresh"], {"status": "READY", "message": None})
        self.assertTrue(Path(proposal["cli_continuation"]["proposal_path"]).is_file())
        self.assertIsNone(self.coordinator.owner)

    def test_tampered_draft_is_stale_without_publication(self) -> None:
        proposal = self.service.create_proposal(
            self.diagnosis_key, self.finding_id
        )["draft"]
        path = Path(proposal["cli_continuation"]["proposal_path"])
        path.write_bytes(b"{}")
        before = list((self.workspace / "controlled-revisions").rglob("*"))
        with self.assertRaises(WorkspaceStaleError):
            self.service.reject(proposal["draft_key"])
        after = list((self.workspace / "controlled-revisions").rglob("*"))
        self.assertEqual(after, before)
        self.assertIsNone(self.coordinator.owner)

    def test_conflicting_existing_draft_is_not_replaced_or_registered(self) -> None:
        snapshot = self.state.capture_snapshot()
        base_key = next(
            item["target_record_key"]
            for item in self.state.projection.details[self.diagnosis_key][
                "relationships"
            ]
            if item["relation"] == "DIAGNOSIS_SUBJECT"
        )
        roots = self.state.resolve_actionable_roots(
            snapshot, [self.diagnosis_key, base_key]
        )
        seed = self.workspace / "expected-proposal.json"
        draft_refinement(
            roots[self.diagnosis_key],
            self.finding_id,
            roots[base_key],
            seed,
        )
        draft_id = json.loads(seed.read_text("utf-8"))["draft_id"]
        expected_key = draft_key(draft_id, self.diagnosis_key, base_key)
        draft_root = self.workspace / "refinement-drafts"
        draft_root.mkdir()
        path = draft_root / f"{draft_id}.json"
        conflicting = b'{"conflicting":true}\n'
        path.write_bytes(conflicting)
        restarted = WorkbenchLifecycleService(
            self.state, MutationCoordinator()
        )

        with self.assertRaises(IntegrityError):
            restarted.create_proposal(self.diagnosis_key, self.finding_id)

        self.assertEqual(path.read_bytes(), conflicting)
        self.assertIsNone(restarted.drafts.context(expected_key))
        self.assertFalse(
            (self.workspace / "controlled-revisions").exists()
            and any(
                (self.workspace / "controlled-revisions").rglob(
                    "refinement-manifest.json"
                )
            )
        )

    def test_response_bound_fails_before_draft_or_context_publication(self) -> None:
        service = WorkbenchLifecycleService(
            self.state, self.coordinator, response_limit=1
        )
        with self.assertRaises(ResponseTooLargeError):
            service.create_proposal(self.diagnosis_key, self.finding_id)
        root = self.workspace / "refinement-drafts"
        self.assertFalse(root.exists() and any(root.glob("*.json")))
        self.assertIsNone(self.coordinator.owner)

    def test_diagnosis_publication_refreshes_and_selects_result(self) -> None:
        state = self._state_with_records(
            "undiagnosed",
            ((self.published.observation, "extraction-observatory", "observation"),),
        )
        observation_key = next(
            item["record_key"]
            for item in state.projection.projection["records"]
            if item["kind"] == "OBSERVATION"
        )
        result = WorkbenchLifecycleService(
            state, MutationCoordinator()
        ).diagnose(observation_key)
        self.assertEqual(result["publication"]["kind"], "DIAGNOSIS")
        self.assertIsNotNone(result["publication"]["record_key"])
        self.assertEqual(result["refresh"]["status"], "READY")

    def test_equivalent_diagnoses_resolve_interleaved_without_context_alias(
        self,
    ) -> None:
        alternate_diagnosis = diagnose(
            self.published.observation,
            self.workspace / "alternate-diagnosis",
        )
        states = [
            self._state_with_records(
                label,
                (
                    (
                        self.published.observation,
                        "extraction-observatory",
                        "observation",
                    ),
                    (diagnosis_root, "evidence-based-diagnosis", "diagnosis"),
                ),
            )
            for label, diagnosis_root in (
                ("equivalent-a", self.published.diagnosis),
                ("equivalent-b", alternate_diagnosis),
            )
        ]
        proposals = []
        services = []
        for state in states:
            key, finding = self._finding(state, "D009")
            service = WorkbenchLifecycleService(state, MutationCoordinator())
            services.append(service)
            detail = state.projection.details[key]
            finding = next(
                item
                for item in detail["view"]["findings"]
                if item["rule_id"] == "D009"
            )
            proposals.append(
                service.create_proposal(key, finding["finding_id"])["draft"]
            )
        self.assertEqual(proposals[0]["draft_id"], proposals[1]["draft_id"])
        self.assertNotEqual(proposals[0]["draft_key"], proposals[1]["draft_key"])
        self.assertNotEqual(
            proposals[0]["diagnosis_record_key"],
            proposals[1]["diagnosis_record_key"],
        )

        rejected = services[1].reject(proposals[1]["draft_key"])
        approved = services[0].approve(proposals[0]["draft_key"])
        self.assertEqual(rejected["publication"]["decision"], "REJECTED")
        self.assertEqual(approved["publication"]["decision"], "APPROVED")

        for state, proposal, result in (
            (states[1], proposals[1], rejected),
            (states[0], proposals[0], approved),
        ):
            record_key = result["publication"]["record_key"]
            snapshot = state.capture_snapshot()
            root = state.resolve_actionable_roots(snapshot, [record_key])[
                record_key
            ]
            manifest = json.loads(
                (root / "refinement-manifest.json").read_text("utf-8")
            )
            continuation = proposal["cli_continuation"]
            self.assertEqual(
                manifest["diagnosis"]["run_id"],
                Path(continuation["diagnosis_path"]).name,
            )
            self.assertEqual(
                manifest["base"]["run_id"],
                Path(continuation["base_path"]).name,
            )
            self.assertEqual(manifest["draft_id"], proposal["draft_id"])
            relationships = {
                item["relation"]: item
                for item in state.projection.details[record_key][
                    "relationships"
                ]
            }
            self.assertEqual(
                relationships["REFINEMENT_DIAGNOSIS"]["target_record_key"],
                proposal["diagnosis_record_key"],
            )
            self.assertEqual(
                relationships["REFINEMENT_BASE"]["target_record_key"],
                proposal["base_record_key"],
            )

    def test_publication_identity_survives_refresh_failure(self) -> None:
        proposal = self.service.create_proposal(
            self.diagnosis_key, self.finding_id
        )["draft"]
        with patch.object(
            self.state,
            "refresh",
            return_value=RefreshResult(False, "candidate records are invalid"),
        ):
            result = self.service.reject(proposal["draft_key"])
        self.assertEqual(result["publication"]["decision"], "REJECTED")
        self.assertIsNone(result["publication"]["revision_id"])
        self.assertIsNone(result["publication"]["record_key"])
        self.assertEqual(result["refresh"]["status"], "FAILED")
        self.assertTrue(
            any(
                (self.workspace / "controlled-revisions").rglob(
                    "refinement-manifest.json"
                )
            )
        )

    def test_failure_before_publication_releases_coordinator(self) -> None:
        def fail(*args):
            raise RuntimeError("draft failed")

        service = WorkbenchLifecycleService(
            self.state,
            self.coordinator,
            draft_service=fail,
        )
        with self.assertRaisesRegex(RuntimeError, "draft failed"):
            service.create_proposal(self.diagnosis_key, self.finding_id)
        self.assertIsNone(self.coordinator.owner)
        self.assertFalse(
            (self.workspace / "refinement-drafts").exists()
            and any((self.workspace / "refinement-drafts").glob("*.json"))
        )

    def test_supported_finding_actionability_is_enriched(self) -> None:
        finding = next(
            item
            for item in self.state.projection.details[self.diagnosis_key]["view"][
                "findings"
            ]
            if item["rule_id"] == "D009"
        )
        self.assertEqual(finding["refiner"]["refiner_id"], "R001")
        self.assertEqual(
            finding["proposal_action"], {"status": "AVAILABLE", "reason": None}
        )

        isolated = self.workspace / "isolated"
        self._copy_to(
            self.published.observation,
            isolated
            / "extraction-observatory"
            / "observation"
            / self.published.observation.name,
        )
        self._copy_to(
            self.published.diagnosis,
            isolated
            / "evidence-based-diagnosis"
            / "diagnosis"
            / self.published.diagnosis.name,
        )
        isolated_state = WorkbenchState(isolated)
        isolated_diagnosis = next(iter(isolated_state.projection.details.values()))
        supported = next(
            item
            for item in isolated_diagnosis["view"]["findings"]
            if item["rule_id"] == "D009"
        )
        self.assertEqual(supported["refiner"]["refiner_id"], "R001")
        self.assertEqual(
            supported["proposal_action"],
            {"status": "AVAILABLE", "reason": None},
        )
        isolated_key = isolated_diagnosis["record_key"]
        proposal = WorkbenchLifecycleService(
            isolated_state, MutationCoordinator()
        ).create_proposal(isolated_key, supported["finding_id"])["draft"]
        self.assertEqual(proposal["diagnosis_record_key"], isolated_key)
        self.assertTrue(
            (isolated / "refinement-drafts" / f"{proposal['draft_id']}.json").is_file()
        )

    def test_all_supported_refiners_create_their_application_previews(self) -> None:
        d007_state = self._state_with_records(
            "d007",
            (
                (self.d007_observation, "extraction-observatory", "observation"),
                (self.d007_diagnosis, "evidence-based-diagnosis", "diagnosis"),
            ),
        )
        d010_state = self._state_with_records(
            "d010",
            (
                (self.chain.observation, "extraction-observatory", "observation"),
                (
                    self.chain.first_diagnosis,
                    "evidence-based-diagnosis",
                    "first-diagnosis",
                ),
                (self.chain.first, "controlled-revisions", "first-refinement"),
                (
                    self.chain.second_diagnosis,
                    "evidence-based-diagnosis",
                    "second-diagnosis",
                ),
            ),
        )
        cases = (
            ("D007", "R002", d007_state),
            ("D009", "R001", self.state),
            ("D010", "R003", d010_state),
        )
        for rule_id, refiner_id, state in cases:
            with self.subTest(rule_id=rule_id):
                diagnosis_key, finding = self._finding(state, rule_id)
                self.assertEqual(finding["refiner"]["refiner_id"], refiner_id)
                self.assertEqual(
                    finding["proposal_action"],
                    {"status": "AVAILABLE", "reason": None},
                )
                proposal = WorkbenchLifecycleService(
                    state, MutationCoordinator()
                ).create_proposal(diagnosis_key, finding["finding_id"])["draft"]
                self.assertEqual(proposal["refiner"]["refiner_id"], refiner_id)
                if rule_id == "D007":
                    self.assertEqual(
                        proposal["edits"][0]["before"]["content_layer"], "body"
                    )
                    self.assertEqual(
                        proposal["edits"][0]["after"]["content_layer"],
                        "furniture",
                    )
                else:
                    self.assertIsInstance(proposal["edits"][0]["before"], str)
                    self.assertIsInstance(proposal["edits"][0]["after"], str)

    def test_unsupported_contained_and_missing_actionability_branches(self) -> None:
        contained_state = self._state_with_records(
            "contained",
            ((self.actionability_corpus, "corpus-inspection", "corpus"),),
        )
        findings = [
            (detail["record_key"], finding)
            for detail in contained_state.projection.details.values()
            if detail["kind"] == "DIAGNOSIS"
            for finding in detail["view"]["findings"]
        ]
        contained_key, contained = next(
            (key, finding)
            for key, finding in findings
            if finding["rule_id"] == "D009"
        )
        self.assertEqual(contained["refiner"]["refiner_id"], "R001")
        self.assertEqual(
            contained["proposal_action"],
            {"status": "UNAVAILABLE", "reason": "SUBJECT_NOT_ACTIONABLE"},
        )
        with self.assertRaises(ActionNotAvailableError):
            WorkbenchLifecycleService(
                contained_state, MutationCoordinator()
            ).create_proposal(contained_key, contained["finding_id"])

        unsupported = next(
            finding for _, finding in findings if finding["refiner"] is None
        )
        self.assertEqual(
            unsupported["proposal_action"],
            {"status": "UNAVAILABLE", "reason": "NO_SUPPORTED_REFINER"},
        )

        missing = self.workspace / "missing-subject"
        self._copy_to(
            self.published.diagnosis,
            missing
            / "evidence-based-diagnosis"
            / "diagnosis"
            / self.published.diagnosis.name,
        )
        missing_state = WorkbenchState(missing)
        self.assertEqual(missing_state.refresh_status, "FAILED")
        self.assertEqual(missing_state.projection.projection["records"], [])
        self.assertEqual(missing_state.projection.details, {})

    def _state_with_records(self, label, records) -> WorkbenchState:
        workspace = self.workspace / label
        for source, family, record_label in records:
            target = workspace / family / record_label / source.name
            self._copy_to(source, target)
        return WorkbenchState(workspace)

    @staticmethod
    def _finding(state: WorkbenchState, rule_id: str):
        for key, detail in state.projection.details.items():
            if detail["kind"] != "DIAGNOSIS":
                continue
            for finding in detail["view"]["findings"]:
                if finding["rule_id"] == rule_id:
                    return key, finding
        raise AssertionError(f"{rule_id} finding is absent")

    @staticmethod
    def _copy_to(source: Path, target: Path) -> None:
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copytree(source, target)


if __name__ == "__main__":
    unittest.main()
