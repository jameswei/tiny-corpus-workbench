from __future__ import annotations

import importlib.metadata
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from tiny_corpus_workbench.canonical_json import session_id
from tiny_corpus_workbench.diagnosis_rules import (
    CURRENT_RULES,
    CURRENT_RULESET,
    CURRENT_RULESET_PARAMETER_HASH,
)
from tiny_corpus_workbench.domain import IntegrityError
from tiny_corpus_workbench.application.refinement import supported_refiner
from tiny_corpus_workbench.workbench_projection import build_projection
from tiny_corpus_workbench.workbench_records import admit_records
from tests.unit.workbench_test_support import (
    PublishedChain,
    PublishedDiagnosis,
    PublishedObservation,
    PublishedRefinements,
    REPOSITORY,
    run_corpus,
)


class WorkbenchProjectionTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.published = PublishedObservation()

    @classmethod
    def tearDownClass(cls) -> None:
        cls.published.close()

    def test_projection_is_compact_and_deterministic(self) -> None:
        first = build_projection(admit_records([self.published.root]))
        second = build_projection(admit_records([self.published.root]))
        self.assertEqual(first.projection_bytes(), second.projection_bytes())
        self.assertEqual(
            set(first.projection),
            {
                "package_version",
                "reference",
                "session_id",
                "counts",
                "records",
                "documents",
                "corpora",
            },
        )
        self.assertEqual(
            first.projection["counts"],
            {
                "record_count": 1,
                "top_level_record_count": 1,
                "contained_record_count": 0,
            },
        )
        self.assertEqual(
            set(first.projection["records"][0]),
            {
                "record_key",
                "kind",
                "status",
                "run_id",
                "primary_identity",
                "origin",
                "artifact_count",
            },
        )
        self.assertEqual(
            first.projection["records"][0]["primary_identity"]["name"],
            "observation_id",
        )
        document = first.projection["documents"][0]
        self.assertEqual(
            set(document),
            {
                "document_key",
                "source",
                "first_observation_at",
                "observation_record_key",
                "rounds",
            },
        )
        self.assertEqual(document["rounds"], [])
        self.assertEqual(first.projection["corpora"], [])
        self.assertEqual(
            first.projection["package_version"],
            importlib.metadata.version("tiny-corpus-workbench"),
        )

    def test_reference_uses_current_python_rules_and_refiner_registry(self) -> None:
        reference = build_projection(
            admit_records([self.published.root])
        ).projection["reference"]
        self.assertEqual(
            reference["ruleset"],
            {
                "name": CURRENT_RULESET["name"],
                "version": CURRENT_RULESET["version"],
                "parameter_hash": CURRENT_RULESET_PARAMETER_HASH,
            },
        )
        self.assertEqual(
            reference["rules"],
            [
                {**rule, "refiner": supported_refiner(rule["rule_id"])}
                for rule in CURRENT_RULES
            ],
        )

    def test_detail_artifacts_are_exactly_the_captured_artifacts(self) -> None:
        built = build_projection(admit_records([self.published.root]))
        node = built.projection["records"][0]
        detail = built.details[node["record_key"]]
        self.assertEqual(
            set(detail),
            {
                "record_key",
                "kind",
                "artifact_integrity",
                "relationships",
                "artifacts",
                "view",
            },
        )
        self.assertEqual(node["artifact_count"], len(detail["artifacts"]))
        keys = [item["artifact_key"] for item in detail["artifacts"]]
        self.assertEqual(keys, sorted(keys))
        self.assertEqual(set(keys), set(built.artifact_contents))
        self.assertEqual(len(keys), len(set(keys)))
        for descriptor in detail["artifacts"]:
            self.assertEqual(
                set(descriptor),
                {
                    "artifact_key",
                    "role",
                    "media_type",
                    "size",
                    "sha256",
                    "availability",
                },
            )

    def test_structured_response_limit_fails_before_serving(self) -> None:
        admitted = admit_records([self.published.root])
        with (
            patch(
                "tiny_corpus_workbench.workbench_projection.MAX_STRUCTURED_RESPONSE",
                1,
            ),
            self.assertRaises(IntegrityError),
        ):
            build_projection(admitted)

    def test_artifact_limit_changes_availability_not_capture(self) -> None:
        with patch(
            "tiny_corpus_workbench.workbench_records.MAX_ARTIFACT_CONTENT", 1
        ):
            built = build_projection(admit_records([self.published.root]))
        detail = next(iter(built.details.values()))
        self.assertTrue(
            all(
                item["availability"] == "TOO_LARGE"
                for item in detail["artifacts"]
            )
        )
        self.assertEqual(
            {item["artifact_key"] for item in detail["artifacts"]},
            set(built.artifact_contents),
        )

    def test_count_and_session_identity_equations_are_exact(self) -> None:
        built = build_projection(admit_records([self.published.root]))
        projection = built.projection
        counts = projection["counts"]
        self.assertEqual(
            counts["record_count"],
            counts["top_level_record_count"] + counts["contained_record_count"],
        )
        top = [
            item["record_key"]
            for item in projection["records"]
            if item["origin"] == "TOP_LEVEL"
        ]
        contained = [
            item["record_key"]
            for item in projection["records"]
            if item["origin"] == "CORPUS_CONTAINED"
        ]
        admitted = admit_records([self.published.root])
        edge_keys = [
            edge["edge_key"]
            for record in admitted.records.values()
            for edge in __import__(
                "tiny_corpus_workbench.workbench_projection",
                fromlist=["_record_edges"],
            )._record_edges(admitted, record)
        ]
        self.assertEqual(
            projection["session_id"],
            session_id(
                top_level_record_keys=top,
                contained_record_keys=contained,
                edge_keys=edge_keys,
            ),
        )

    def test_documents_sort_by_first_observation_then_source_identity(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            roots = []
            for index, fixture in enumerate(
                ("policy-memo.md", "meeting-minutes.md")
            ):
                result = run_corpus(
                    "observe",
                    str(REPOSITORY / "fixtures/golden" / fixture),
                    "--output-root",
                    str(Path(temporary) / str(index)),
                )
                roots.append(Path(result["manifest"]).parent)
            admitted = admit_records(roots)
            for record in admitted.records.values():
                record.manifest["created_at"] = "2026-08-03T00:00:00Z"
            documents = build_projection(admitted).projection["documents"]
        identities = [
            (item["source"]["sha256"], item["source"]["media_type"])
            for item in documents
        ]
        self.assertEqual(identities, sorted(identities))

    def test_multiple_observation_roots_for_source_identity_are_rejected(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            roots = []
            for index in range(2):
                result = run_corpus(
                    "observe",
                    str(REPOSITORY / "fixtures/golden/policy-memo.md"),
                    "--output-root",
                    str(Path(temporary) / str(index)),
                )
                roots.append(Path(result["manifest"]).parent)
            with self.assertRaisesRegex(
                IntegrityError,
                "multiple Observation roots",
            ):
                build_projection(admit_records(roots))

    def test_explicit_diagnosis_with_missing_subject_is_rejected(self) -> None:
        diagnosis = PublishedDiagnosis()
        try:
            with self.assertRaisesRegex(
                IntegrityError, "missing required relationship"
            ):
                build_projection(admit_records([diagnosis.diagnosis]))
        finally:
            diagnosis.close()

    def test_matched_lifecycle_record_without_explicit_root_is_rejected(self) -> None:
        diagnosis = PublishedDiagnosis()
        try:
            admitted = admit_records(
                [diagnosis.root, diagnosis.diagnosis]
            )
            diagnosis_key = next(
                key
                for key, record in admitted.records.items()
                if record.kind == "DIAGNOSIS"
            )
            admitted.explicit_keys = {diagnosis_key}
            with self.assertRaisesRegex(
                IntegrityError, "unreachable from an Observation root"
            ):
                build_projection(admitted)
        finally:
            diagnosis.close()


class WorkbenchLinearPreparationProjectionTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.chain = PublishedChain()
        cls.decisions = PublishedRefinements()

    @classmethod
    def tearDownClass(cls) -> None:
        cls.decisions.close()
        cls.chain.close()

    def test_verified_chain_becomes_two_ordered_preparation_rounds(self) -> None:
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
        rounds = built.projection["documents"][0]["rounds"]
        self.assertEqual([round_["number"] for round_ in rounds], [1, 2])
        self.assertEqual(
            rounds[0]["revision_record_key"], rounds[1]["base_record_key"]
        )
        self.assertEqual(
            rounds[1]["revision_record_key"],
            rounds[1]["refinement_record_key"],
        )

    def test_approved_and_rejected_siblings_are_rejected_atomically(self) -> None:
        with self.assertRaisesRegex(
            IntegrityError,
            "multiple refinement decisions",
        ):
            build_projection(
                admit_records(
                    [
                        self.decisions.observation,
                        self.decisions.diagnosis,
                        self.decisions.applied,
                        self.decisions.rejected,
                    ]
                )
            )

    def test_each_final_decision_is_valid_in_an_independent_workspace(self) -> None:
        for decision in (self.decisions.applied, self.decisions.rejected):
            with self.subTest(decision=decision):
                rounds = build_projection(
                    admit_records(
                        [
                            self.decisions.observation,
                            self.decisions.diagnosis,
                            decision,
                        ]
                    )
                ).projection["documents"][0]["rounds"]
                self.assertEqual(len(rounds), 1)
                self.assertEqual(
                    rounds[0]["revision_record_key"],
                    rounds[0]["refinement_record_key"]
                    if decision == self.decisions.applied
                    else None,
                )


if __name__ == "__main__":
    unittest.main()
