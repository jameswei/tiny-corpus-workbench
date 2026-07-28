from __future__ import annotations

import copy
import unittest
from contextlib import contextmanager
from pathlib import Path
from typing import Callable, Iterator
from unittest.mock import patch

import tiny_corpus_workbench.workbench_projection as projection_module
import tiny_corpus_workbench.workbench_records as records_module
from tiny_corpus_workbench.domain import IntegrityError
from tiny_corpus_workbench.workbench_projection import build_projection
from tiny_corpus_workbench.workbench_records import admit_records
from tests.unit.workbench_test_support import (
    PublishedDiagnosis,
    PublishedChain,
    PublishedCorpus,
    PublishedRefinements,
)


class WorkbenchRelationshipResolutionTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.published = PublishedDiagnosis()
        cls.refinements = PublishedRefinements()
        cls.chain = PublishedChain()
        cls.corpus = PublishedCorpus()

    @classmethod
    def tearDownClass(cls) -> None:
        cls.published.close()
        cls.refinements.close()
        cls.chain.close()
        cls.corpus.close()

    @staticmethod
    def _serialized(admitted: object) -> tuple[bytes, tuple[tuple[str, bytes], ...]]:
        built = build_projection(admitted)
        return (
            built.projection_bytes(),
            tuple(
                (key, built.detail_bytes(key))
                for key in sorted(built.details)
            ),
        )

    @staticmethod
    def _listed_path(
        admitted: object, kind: str, role: str
    ) -> Path:
        record = next(
            value
            for value in admitted.records.values()
            if value.kind == kind
        )
        descriptor = next(
            value for value in record.listed if value["role"] == role
        )
        return record.backing.root / descriptor["path"]

    @staticmethod
    @contextmanager
    def _mutated_path(path: Path, mode: str) -> Iterator[None]:
        if mode != "CONTENT_REPLACEMENT":
            raise AssertionError(f"unknown mutation mode: {mode}")
        original = path.read_bytes()
        path.write_bytes(original + b"\n")
        try:
            yield
        finally:
            path.write_bytes(original)

    def _assert_frozen_replay(
        self,
        roots: list[Path],
        artifact_path: Callable[[object], Path],
    ) -> None:
        admitted = admit_records(roots)
        expected = self._serialized(admitted)
        path = artifact_path(admitted)
        with self._mutated_path(path, "CONTENT_REPLACEMENT"):
            self.assertEqual(self._serialized(admitted), expected)
        self.assertEqual(self._serialized(admitted), expected)

    def test_missing_subject_is_preserved_without_path_inference(self) -> None:
        built = build_projection(admit_records([self.published.diagnosis]))
        detail = next(iter(built.details.values()))
        edge = detail["relationships"][0]
        self.assertEqual(edge["state"], "MISSING")
        self.assertNotIn("target_record_key", edge)
        self.assertEqual(detail["view"]["subject_state"], "NOT_CHECKED")
        self.assertEqual(detail["view"]["derivation_state"], "NOT_CHECKED")

    def test_exact_subject_is_replayed_and_matches(self) -> None:
        built = build_projection(
            admit_records([self.published.root, self.published.diagnosis])
        )
        detail = next(
            value for value in built.details.values() if value["kind"] == "DIAGNOSIS"
        )
        edge = detail["relationships"][0]
        self.assertEqual(edge["state"], "MATCH")
        self.assertIsNotNone(edge["target_record_key"])

    def test_catalog_key_rename_does_not_change_workbench_identity(self) -> None:
        def snapshot() -> dict[str, object]:
            admitted = admit_records(
                [self.published.root, self.published.diagnosis]
            )
            built = build_projection(admitted)
            diagnosis = next(
                record
                for record in admitted.records.values()
                if record.kind == "DIAGNOSIS"
            )
            edge = projection_module._record_edges(
                admitted, diagnosis
            )[0]
            return {
                "logical_keys": sorted(
                    record.logical_copy_key
                    for record in admitted.records.values()
                ),
                "record_keys": sorted(admitted.records),
                "edge_key": edge["edge_key"],
                "edge_state": edge["state"],
                "target_record_key": edge["target_record_key"],
                "session_id": built.projection["session_id"],
            }

        baseline = snapshot()
        renamed_roots = {
            name: (kind, f"renamed-{schema}", role)
            for name, (kind, schema, role) in records_module.ROOTS.items()
        }
        renamed_schemas = {
            kind: f"renamed-{schema}"
            for kind, schema in projection_module.SCHEMAS.items()
        }
        with (
            patch.object(records_module, "ROOTS", renamed_roots),
            patch.object(projection_module, "SCHEMAS", renamed_schemas),
        ):
            self.assertEqual(snapshot(), baseline)

    def test_refinement_targets_are_evaluated_independently(self) -> None:
        diagnosis_only = build_projection(
            admit_records(
                [self.refinements.diagnosis, self.refinements.applied]
            )
        )
        detail = next(
            value["view"]
            for value in diagnosis_only.details.values()
            if value["kind"] == "REFINEMENT"
        )
        self.assertEqual(detail["diagnosis_state"], "MATCH")
        self.assertEqual(detail["base_state"], "NOT_CHECKED")
        self.assertEqual(detail["derivation_state"], "NOT_CHECKED")
        self.assertEqual(detail["reversibility_state"], "NOT_CHECKED")

        base_only = build_projection(
            admit_records(
                [self.refinements.observation, self.refinements.applied]
            )
        )
        detail = next(
            value["view"]
            for value in base_only.details.values()
            if value["kind"] == "REFINEMENT"
        )
        self.assertEqual(detail["diagnosis_state"], "NOT_CHECKED")
        self.assertEqual(detail["base_state"], "MATCH")
        self.assertEqual(detail["derivation_state"], "NOT_CHECKED")

    def test_direct_diagnosis_replay_uses_only_frozen_bytes(self) -> None:
        self._assert_frozen_replay(
            [self.published.root, self.published.diagnosis],
            lambda admitted: self._listed_path(
                admitted, "DIAGNOSIS", "diagnostic-findings"
            ),
        )

    def test_refinement_diagnosis_only_replay_uses_only_frozen_bytes(
        self,
    ) -> None:
        self._assert_frozen_replay(
            [self.refinements.diagnosis, self.refinements.applied],
            lambda admitted: self._listed_path(
                admitted, "DIAGNOSIS", "diagnostic-findings"
            ),
        )

    def test_refinement_base_only_replay_uses_only_frozen_bytes(self) -> None:
        self._assert_frozen_replay(
            [self.refinements.observation, self.refinements.applied],
            lambda admitted: self._listed_path(
                admitted, "OBSERVATION", "docling-document-json"
            ),
        )

    def test_refinement_combined_replay_uses_only_frozen_bytes(self) -> None:
        self._assert_frozen_replay(
            [
                self.refinements.observation,
                self.refinements.diagnosis,
                self.refinements.applied,
            ],
            lambda admitted: self._listed_path(
                admitted, "REFINEMENT", "transformation-history"
            ),
        )

    def test_contained_diagnosis_replay_uses_only_frozen_bytes(self) -> None:
        self._assert_frozen_replay(
            [self.corpus.root],
            lambda admitted: self._listed_path(
                admitted, "DIAGNOSIS", "diagnostic-findings"
            ),
        )

    def test_present_diagnosis_binding_failure_rejects_with_missing_base(self) -> None:
        admitted = admit_records(
            [self.refinements.diagnosis, self.refinements.applied]
        )
        with patch(
            "tiny_corpus_workbench.workbench_projection.verify_refinement",
            return_value={
                "artifact_integrity": {"status": "VERIFIED"},
                "diagnosis_state": {"status": "CHANGED"},
                "base_state": {"status": "NOT_CHECKED"},
                "derivation_state": {"status": "NOT_CHECKED"},
                "reversibility_state": {"status": "NOT_CHECKED"},
            },
        ), self.assertRaises(IntegrityError):
            build_projection(admitted)

    def test_rejected_refinement_without_targets_is_not_applicable(self) -> None:
        built = build_projection(admit_records([self.refinements.rejected]))
        detail = next(iter(built.details.values()))["view"]
        self.assertEqual(detail["diagnosis_state"], "NOT_CHECKED")
        self.assertEqual(detail["base_state"], "NOT_CHECKED")
        self.assertEqual(detail["derivation_state"], "NOT_APPLICABLE")
        self.assertEqual(detail["reversibility_state"], "NOT_APPLICABLE")

    def test_refinement_subject_and_parent_relations_match_real_chain(self) -> None:
        built = build_projection(
            admit_records(
                [
                    self.chain.observation,
                    self.chain.first_diagnosis,
                    self.chain.first,
                    self.chain.second_diagnosis,
                    self.chain.second,
                ]
            )
        )
        diagnosis = next(
            value
            for value in built.details.values()
            if value["kind"] == "DIAGNOSIS"
            and value["relationships"][0]["target_kind"] == "REFINEMENT"
        )
        self.assertEqual(
            diagnosis["relationships"][0]["state"], "MATCH"
        )
        second_revision_id = __import__("json").loads(
            (self.chain.second / "refinement-manifest.json").read_text("utf-8")
        )["revision_id"]
        refinement = next(
            value
            for value in built.details.values()
            if value["kind"] == "REFINEMENT"
            and value["view"]["revision_chain"][-1]["revision_id"]
            == second_revision_id
        )
        self.assertEqual(
            {item["relation"]: item["state"] for item in refinement["relationships"]},
            {
                "REFINEMENT_BASE": "MATCH",
                "REFINEMENT_DIAGNOSIS": "MATCH",
                "REFINEMENT_PARENT": "MATCH",
            },
        )

    def test_wrong_run_is_missing_and_multiple_candidates_reject(self) -> None:
        admitted = admit_records([self.published.diagnosis])
        diagnosis = next(iter(admitted.records.values()))
        wrong_run = copy.copy(diagnosis)
        wrong_run.manifest = copy.deepcopy(diagnosis.manifest)
        wrong_run.manifest["subject"]["run_id"] = "different-run"
        records = type(admitted)(
            records={wrong_run.record_key: wrong_run},
            explicit_keys={wrong_run.record_key},
            containment=[],
        )
        built = build_projection(records)
        detail = next(iter(built.details.values()))
        self.assertEqual(detail["relationships"][0]["state"], "MISSING")

        subject_admitted = admit_records([self.published.root])
        subject = next(iter(subject_admitted.records.values()))
        duplicate = copy.copy(subject)
        duplicate.record_key = "f" * 64
        records = type(subject_admitted)(
            records={
                subject.record_key: subject,
                duplicate.record_key: duplicate,
                diagnosis.record_key: diagnosis,
            },
            explicit_keys={
                subject.record_key,
                duplicate.record_key,
                diagnosis.record_key,
            },
            containment=[],
        )
        with self.assertRaises(IntegrityError):
            build_projection(records)


if __name__ == "__main__":
    unittest.main()
