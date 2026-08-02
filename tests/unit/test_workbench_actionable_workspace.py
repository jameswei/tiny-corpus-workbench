from __future__ import annotations

import io
import json
import shutil
import tempfile
import unittest
from contextlib import redirect_stderr, redirect_stdout
from pathlib import Path
from unittest.mock import patch

from tiny_corpus_workbench import cli
from tiny_corpus_workbench.application import workbench as workbench_module
from tiny_corpus_workbench.application.workbench import (
    WorkbenchState,
    WorkspaceStaleError,
)
from tiny_corpus_workbench.domain import InputError
from tiny_corpus_workbench.workbench_records import admit_records
from tests.unit.workbench_test_support import (
    PublishedCorpus,
    PublishedDiagnosis,
    PublishedFailedObservation,
    PublishedObservation,
    PublishedRefinements,
    REPOSITORY,
)


class WorkbenchActionableWorkspaceTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.observation = PublishedObservation()
        cls.failed_observation = PublishedFailedObservation()
        cls.diagnosis = PublishedDiagnosis()
        cls.refinements = PublishedRefinements()
        cls.corpus = PublishedCorpus()
        cls.markitdown_only = cls._publish_partial("docling")
        cls.docling_only = cls._publish_partial("markitdown")

    @classmethod
    def tearDownClass(cls) -> None:
        cls.observation.close()
        cls.failed_observation.close()
        cls.diagnosis.close()
        cls.refinements.close()
        cls.corpus.close()
        for temporary, _ in (cls.markitdown_only, cls.docling_only):
            temporary.cleanup()

    @classmethod
    def _publish_partial(
        cls, failed_extractor: str
    ) -> tuple[tempfile.TemporaryDirectory[str], Path]:
        temporary = tempfile.TemporaryDirectory(
            dir=Path(tempfile.gettempdir()).resolve()
        )
        stdout, stderr = io.StringIO(), io.StringIO()
        target = f"tiny_corpus_workbench.extractors.{failed_extractor}.convert"
        with (
            patch(target, side_effect=RuntimeError("stable extractor failure")),
            redirect_stdout(stdout),
            redirect_stderr(stderr),
        ):
            code = cli.main(
                [
                    "observe",
                    str(REPOSITORY / "fixtures/golden/policy-memo.md"),
                    "--output-root",
                    temporary.name,
                ]
            )
        if code != 3:
            temporary.cleanup()
            raise RuntimeError(stderr.getvalue())
        root = Path(json.loads(stdout.getvalue())["manifest"]).parent
        return temporary, root

    def setUp(self) -> None:
        self.temporary = tempfile.TemporaryDirectory(
            dir=Path(tempfile.gettempdir()).resolve()
        )
        self.workspace = Path(self.temporary.name)

    def tearDown(self) -> None:
        self.temporary.cleanup()

    @staticmethod
    def _record_key(state: WorkbenchState, kind: str) -> str:
        return next(
            item["record_key"]
            for item in state.projection.projection["records"]
            if item["kind"] == kind and item["origin"] == "TOP_LEVEL"
        )

    def _copy(self, source: Path, family: str, name: str) -> Path:
        target = self.workspace / family / name / source.name
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copytree(source, target)
        return target

    def test_workspace_and_actionable_root_components_must_be_real_directories(
        self,
    ) -> None:
        target = self.workspace / "real-workspace"
        target.mkdir()
        alias = self.workspace / "workspace-alias"
        alias.symlink_to(target, target_is_directory=True)
        with self.assertRaisesRegex(
            InputError, "workspace must be a real directory"
        ):
            WorkbenchState(alias)

        outside = self.workspace / "outside-family"
        record = outside / "record" / self.observation.root.name
        record.parent.mkdir(parents=True)
        shutil.copytree(self.observation.root, record)
        family = self.workspace / "extraction-observatory"
        family.symlink_to(outside, target_is_directory=True)
        state = WorkbenchState(self.workspace)
        self.assertEqual(state.refresh_status, "READY")
        self.assertEqual(state.capture_snapshot().actionable_roots, {})

    def test_only_top_level_non_corpus_records_receive_root_tokens(self) -> None:
        self._copy(self.corpus.root, "corpus-inspection", "corpus")
        state = WorkbenchState(self.workspace)
        self.assertGreater(
            state.projection.projection["counts"]["contained_record_count"], 0
        )
        self.assertEqual(state.capture_snapshot().actionable_roots, {})

        self._copy(
            self.observation.root,
            "extraction-observatory",
            "explicit-observation",
        )
        self.assertTrue(state.refresh().succeeded)
        key = self._record_key(state, "OBSERVATION")
        self.assertIn(key, state.capture_snapshot().actionable_roots)

    def test_observation_eligibility_uses_canonical_artifact_availability(self) -> None:
        cases = (
            (self.failed_observation.root, "FAILED", False),
            (self.markitdown_only[1], "PARTIAL_SUCCESS", False),
            (self.docling_only[1], "PARTIAL_SUCCESS", True),
        )
        for index, (source, status, eligible) in enumerate(cases):
            with self.subTest(status=status, eligible=eligible):
                workspace = self.workspace / str(index)
                target = (
                    workspace
                    / "extraction-observatory"
                    / "record"
                    / source.name
                )
                target.parent.mkdir(parents=True)
                shutil.copytree(source, target)
                state = WorkbenchState(workspace)
                key = self._record_key(state, "OBSERVATION")
                snapshot = state.capture_snapshot()
                self.assertIn(key, snapshot.actionable_roots)
                self.assertEqual(
                    state.projection.projection["records"][0]["status"],
                    status,
                )
                self.assertEqual(
                    state.diagnosis_subject(snapshot, key) is not None,
                    eligible,
                )

    def test_approved_refinement_is_a_subject_but_rejected_is_not(self) -> None:
        for status, refinement, eligible in (
            ("APPROVED", self.refinements.applied, True),
            ("REJECTED", self.refinements.rejected, False),
        ):
            with self.subTest(status=status):
                workspace = self.workspace / status.lower()
                for family, source in (
                    ("extraction-observatory", self.refinements.observation),
                    ("evidence-based-diagnosis", self.refinements.diagnosis),
                    ("controlled-revisions", refinement),
                ):
                    target = workspace / family / source.name
                    target.parent.mkdir(parents=True, exist_ok=True)
                    shutil.copytree(source, target)
                state = WorkbenchState(workspace)
                snapshot = state.capture_snapshot()
                key = self._record_key(state, "REFINEMENT")
                self.assertEqual(
                    state.diagnosis_subject(snapshot, key) is not None,
                    eligible,
                )

    def test_diagnosis_base_requires_a_matching_top_level_actionable_subject(
        self,
    ) -> None:
        self._copy(
            self.diagnosis.root,
            "extraction-observatory",
            "observation",
        )
        diagnosis_root = self._copy(
            self.diagnosis.diagnosis,
            "evidence-based-diagnosis",
            "diagnosis",
        )
        state = WorkbenchState(self.workspace)
        snapshot = state.capture_snapshot()
        diagnosis_key = self._record_key(state, "DIAGNOSIS")
        subject_key = self._record_key(state, "OBSERVATION")
        self.assertIs(
            state.diagnosis_base(snapshot, diagnosis_key),
            snapshot.actionable_roots[subject_key],
        )

        diagnosis_root.parent.rename(self.workspace / "not-discovered")
        self.assertTrue(state.refresh().succeeded)
        self.assertIsNone(
            state.diagnosis_base(state.capture_snapshot(), diagnosis_key)
        )

    def test_refresh_atomically_replaces_projection_and_root_index(self) -> None:
        self._copy(
            self.diagnosis.root,
            "extraction-observatory",
            "observation",
        )
        state = WorkbenchState(self.workspace)
        first = state.capture_snapshot()
        self.assertEqual(len(first.actionable_roots), 1)

        diagnosis = self._copy(
            self.diagnosis.diagnosis,
            "evidence-based-diagnosis",
            "diagnosis",
        )
        self.assertTrue(state.refresh().succeeded)
        second = state.capture_snapshot()
        self.assertIsNot(second, first)
        self.assertEqual(len(second.actionable_roots), 2)
        self.assertEqual(second.projection.projection["counts"]["record_count"], 2)

        (diagnosis / "diagnosis-manifest.json").write_bytes(b"not json")
        self.assertFalse(state.refresh().succeeded)
        self.assertIs(state.capture_snapshot(), second)
        self.assertIs(state.projection, second.projection)

    def test_refresh_rejects_replacement_after_admission_before_token_creation(
        self,
    ) -> None:
        root = self._copy(
            self.observation.root,
            "extraction-observatory",
            "record",
        )
        state = WorkbenchState(self.workspace)
        accepted = state.capture_snapshot()
        backup = root.with_name("admitted-record")
        build_tokens = workbench_module._actionable_roots

        def replace_before_tokens(workspace, records):
            root.rename(backup)
            shutil.copytree(backup, root)
            return build_tokens(workspace, records)

        with patch.object(
            workbench_module,
            "_actionable_roots",
            side_effect=replace_before_tokens,
        ):
            result = state.refresh()

        self.assertFalse(result.succeeded)
        self.assertIs(state.capture_snapshot(), accepted)
        self.assertIs(state.projection, accepted.projection)

    def test_root_resolution_rejects_changed_missing_moved_symlink_and_replacement(
        self,
    ) -> None:
        scenarios = ("changed", "missing", "moved", "symlink", "replacement")
        for scenario in scenarios:
            with self.subTest(scenario=scenario):
                workspace = self.workspace / scenario
                root = (
                    workspace
                    / "extraction-observatory"
                    / "record"
                    / self.observation.root.name
                )
                root.parent.mkdir(parents=True)
                shutil.copytree(self.observation.root, root)
                state = WorkbenchState(workspace)
                snapshot = state.capture_snapshot()
                key = self._record_key(state, "OBSERVATION")

                if scenario == "changed":
                    (root / "manifest.json").write_bytes(b"changed")
                elif scenario == "missing":
                    shutil.rmtree(root)
                elif scenario == "moved":
                    root.rename(root.with_name("moved-record"))
                elif scenario == "symlink":
                    backup = root.with_name("real-record")
                    root.rename(backup)
                    root.symlink_to(backup, target_is_directory=True)
                else:
                    backup = root.with_name("original-record")
                    root.rename(backup)
                    shutil.copytree(backup, root)

                with self.assertRaises(WorkspaceStaleError):
                    state.resolve_actionable_roots(snapshot, [key])

    def test_root_resolution_rejects_valid_record_key_mismatch(self) -> None:
        root = self._copy(
            self.observation.root,
            "extraction-observatory",
            "record",
        )
        state = WorkbenchState(self.workspace)
        snapshot = state.capture_snapshot()
        key = self._record_key(state, "OBSERVATION")
        original_identity = root.stat().st_ino

        for child in root.iterdir():
            if child.is_dir():
                shutil.rmtree(child)
            else:
                child.unlink()
        shutil.copytree(
            self.refinements.observation,
            root,
            dirs_exist_ok=True,
        )
        self.assertEqual(root.stat().st_ino, original_identity)
        with self.assertRaises(WorkspaceStaleError):
            state.resolve_actionable_roots(snapshot, [key])

    def test_root_resolution_rechecks_identity_after_readmission(self) -> None:
        root = self._copy(
            self.observation.root,
            "extraction-observatory",
            "record",
        )
        state = WorkbenchState(self.workspace)
        snapshot = state.capture_snapshot()
        key = self._record_key(state, "OBSERVATION")
        backup = root.with_name("accepted-record")

        def replace_before_admission(roots):
            root.rename(backup)
            shutil.copytree(backup, root)
            try:
                admitted = admit_records(roots)
            finally:
                shutil.rmtree(root)
                backup.rename(root)
            return admitted

        with (
            patch(
                "tiny_corpus_workbench.application.workbench.admit_records",
                side_effect=replace_before_admission,
            ),
            self.assertRaises(WorkspaceStaleError),
        ):
            state.resolve_actionable_roots(snapshot, [key])

    def test_root_resolution_checks_admitted_backing_after_symlink_swap(self) -> None:
        root = self._copy(
            self.observation.root,
            "extraction-observatory",
            "record",
        )
        state = WorkbenchState(self.workspace)
        snapshot = state.capture_snapshot()
        key = self._record_key(state, "OBSERVATION")
        backup = root.with_name("symlink-target")

        def swap_during_admission(roots):
            root.rename(backup)
            root.symlink_to(backup, target_is_directory=True)
            try:
                admitted = admit_records(roots)
            finally:
                root.unlink()
                backup.rename(root)
            return admitted

        with (
            patch(
                "tiny_corpus_workbench.application.workbench.admit_records",
                side_effect=swap_during_admission,
            ),
            self.assertRaises(WorkspaceStaleError),
        ):
            state.resolve_actionable_roots(snapshot, [key])

    def test_unchanged_required_roots_resolve_from_one_snapshot(self) -> None:
        observation = self._copy(
            self.diagnosis.root,
            "extraction-observatory",
            "observation",
        )
        diagnosis = self._copy(
            self.diagnosis.diagnosis,
            "evidence-based-diagnosis",
            "diagnosis",
        )
        state = WorkbenchState(self.workspace)
        snapshot = state.capture_snapshot()
        observation_key = self._record_key(state, "OBSERVATION")
        diagnosis_key = self._record_key(state, "DIAGNOSIS")
        for token in snapshot.actionable_roots.values():
            self.assertFalse(Path(token.relative_path).is_absolute())
            self.assertNotIn("..", Path(token.relative_path).parts)
            metadata = token.canonical_root.stat()
            self.assertEqual(
                (token.device, token.inode),
                (metadata.st_dev, metadata.st_ino),
            )
        self.assertEqual(
            state.resolve_actionable_roots(
                snapshot, [diagnosis_key, observation_key, diagnosis_key]
            ),
            {
                diagnosis_key: diagnosis.resolve(),
                observation_key: observation.resolve(),
            },
        )


if __name__ == "__main__":
    unittest.main()
