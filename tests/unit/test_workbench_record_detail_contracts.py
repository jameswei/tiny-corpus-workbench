from __future__ import annotations

import unittest
from typing import Any

from tiny_corpus_workbench.workbench_projection import (
    COMPARISON_METRICS,
    build_projection,
)
from tiny_corpus_workbench.workbench_records import admit_records
from tests.unit.workbench_test_support import (
    PublishedCorpus,
    PublishedDiagnosis,
    PublishedFailedObservation,
    PublishedObservation,
    PublishedRefinements,
)


SOURCE_FIELDS = {"key", "name", "media_type", "size", "sha256"}
FINDING_FIELDS = {
    "finding_id",
    "rule_id",
    "rule_version",
    "summary",
    "severity",
    "document_refs",
    "evidence",
    "refiner",
    "proposal_action",
}
FORBIDDEN = {
    "schema_version",
    "runtime",
    "projection_role",
    "relative_path",
    "path",
    "$ref",
}


def walk(value: Any):
    if isinstance(value, dict):
        yield value
        for child in value.values():
            yield from walk(child)
    elif isinstance(value, list):
        for child in value:
            yield from walk(child)


class WorkbenchRecordDetailContractTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.observation = PublishedObservation()
        cls.failed = PublishedFailedObservation()
        cls.diagnosis = PublishedDiagnosis()
        cls.refinements = PublishedRefinements()
        cls.corpus = PublishedCorpus()

    @classmethod
    def tearDownClass(cls) -> None:
        cls.corpus.close()
        cls.refinements.close()
        cls.diagnosis.close()
        cls.failed.close()
        cls.observation.close()

    def _details(self, roots):
        return build_projection(admit_records(roots)).details.values()

    def test_all_four_kinds_and_incomplete_states_use_current_data(self) -> None:
        applied_details = list(
            self._details(
                [
                    self.refinements.observation,
                    self.refinements.diagnosis,
                    self.refinements.applied,
                    self.corpus.root,
                ]
            )
        )
        rejected_details = list(
            self._details(
                [
                    self.refinements.observation,
                    self.refinements.diagnosis,
                    self.refinements.rejected,
                ]
            )
        )
        incomplete_details = list(self._details([self.failed.root]))
        details = [*applied_details, *rejected_details, *incomplete_details]
        self.assertEqual(
            {detail["kind"] for detail in details},
            {"OBSERVATION", "DIAGNOSIS", "REFINEMENT", "CORPUS"},
        )
        self.assertTrue(
            any(
                detail["kind"] == "REFINEMENT"
                and detail["view"]["decision"] == "REJECTED"
                for detail in details
            )
        )
        for detail in details:
            for mapping in walk(detail):
                self.assertTrue(FORBIDDEN.isdisjoint(mapping))

    def test_observation_contract_is_exact(self) -> None:
        detail = next(iter(self._details([self.observation.root])))
        view = detail["view"]
        self.assertEqual(
            set(view),
            {"source", "docling_document", "extractors", "comparison"},
        )
        self.assertEqual(set(view["source"]), SOURCE_FIELDS)
        self.assertEqual(
            set(view["docling_document"]), {"name", "version"}
        )
        self.assertEqual(view["docling_document"]["name"], "DoclingDocument")
        for extractor in view["extractors"]:
            self.assertEqual(
                set(extractor),
                {"name", "version", "status", "upstream_status", "error"},
            )
        comparison = view["comparison"]
        self.assertEqual(
            set(comparison),
            {
                "status",
                "docling",
                "markitdown",
                "docling_minus_markitdown",
            },
        )
        self.assertEqual(set(comparison["docling"]), set(COMPARISON_METRICS))
        self.assertEqual(set(comparison["markitdown"]), set(COMPARISON_METRICS))
        self.assertEqual(
            set(comparison["docling_minus_markitdown"]),
            set(COMPARISON_METRICS) | {"normalized_equal"},
        )

    def test_diagnosis_and_refinement_contracts_are_exact(self) -> None:
        approved_details = list(
            self._details(
                [
                    self.refinements.observation,
                    self.refinements.diagnosis,
                    self.refinements.applied,
                ]
            )
        )
        rejected_details = list(
            self._details(
                [
                    self.refinements.observation,
                    self.refinements.diagnosis,
                    self.refinements.rejected,
                ]
            )
        )
        diagnosis = next(
            value["view"]
            for value in approved_details
            if value["kind"] == "DIAGNOSIS"
        )
        self.assertEqual(set(diagnosis["source"]), SOURCE_FIELDS)
        self.assertTrue(
            all(set(finding) == FINDING_FIELDS for finding in diagnosis["findings"])
        )
        refinements = [
            next(
                value["view"]
                for value in details
                if value["kind"] == "REFINEMENT"
            )
            for details in (approved_details, rejected_details)
        ]
        by_state = {value["decision"]: value for value in refinements}
        for value in refinements:
            self.assertEqual(
                set(value["proposal"]),
                {"draft_id", "finding_id", "refiner"},
            )
        self.assertEqual(by_state["APPROVED"]["derivation_state"], "MATCH")
        self.assertTrue(by_state["APPROVED"]["transformations"])
        self.assertEqual(
            by_state["REJECTED"]["derivation_state"], "NOT_APPLICABLE"
        )
        self.assertEqual(by_state["REJECTED"]["transformations"], [])

    def test_corpus_sources_and_relationships_are_compact(self) -> None:
        details = list(self._details([self.corpus.root]))
        corpus = next(value for value in details if value["kind"] == "CORPUS")
        for member in corpus["view"]["matrix"]:
            self.assertEqual(set(member["source"]), SOURCE_FIELDS)
            self.assertEqual(member["source"]["key"], member["member_id"])
        for detail in details:
            for relationship in detail["relationships"]:
                self.assertIn(
                    set(relationship),
                    (
                        {
                            "relation",
                            "state",
                            "target_kind",
                            "target_identity",
                        },
                        {
                            "relation",
                            "state",
                            "target_kind",
                            "target_identity",
                            "target_record_key",
                        },
                    ),
                )
                self.assertEqual(
                    set(relationship["target_identity"]), {"name", "value"}
                )

    def test_corpus_detail_exposes_verified_report_and_stylesheet(self) -> None:
        details = list(self._details([self.corpus.root]))
        corpus = next(value for value in details if value["kind"] == "CORPUS")
        by_role = {item["role"]: item for item in corpus["artifacts"]}
        self.assertEqual(by_role["corpus-report"]["media_type"], "text/html")
        self.assertEqual(by_role["corpus-stylesheet"]["media_type"], "text/css")
        self.assertEqual(by_role["corpus-report"]["availability"], "AVAILABLE")
        self.assertEqual(by_role["corpus-stylesheet"]["availability"], "AVAILABLE")


if __name__ == "__main__":
    unittest.main()
