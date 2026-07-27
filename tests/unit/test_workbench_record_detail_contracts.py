from __future__ import annotations

import copy
import json
import unittest
from pathlib import Path

from jsonschema import ValidationError

from tiny_corpus_workbench.schema_catalog import validate_document
from tiny_corpus_workbench.semantic_validation import SemanticValidationError
from tiny_corpus_workbench.workbench_projection import build_projection
from tiny_corpus_workbench.workbench_records import admit_records
from tests.unit.workbench_test_support import PublishedChain, PublishedRefinements


FIXTURES = Path(__file__).resolve().parents[1] / "fixtures" / "workbench-api"


class WorkbenchRecordDetailContractTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.published = PublishedRefinements()
        cls.chain = PublishedChain()

    @classmethod
    def tearDownClass(cls) -> None:
        cls.published.close()
        cls.chain.close()

    def test_all_kind_and_branch_examples_validate(self) -> None:
        names = (
            "detail-observation.json",
            "detail-diagnosis.json",
            "detail-diagnosis-refinement-subject.json",
            "detail-refinement-applied.json",
            "detail-refinement-rejected.json",
            "detail-corpus.json",
        )
        for name in names:
            with self.subTest(name=name):
                validate_document(
                    "tcw.workbench-record-detail/v0.5",
                    json.loads((FIXTURES / name).read_text("utf-8")),
                )

    def test_closed_detail_rejects_extra_fields(self) -> None:
        value = json.loads((FIXTURES / "detail-observation.json").read_text("utf-8"))
        changed = copy.deepcopy(value)
        changed["detail"]["extra"] = True
        with self.assertRaises(ValidationError):
            validate_document("tcw.workbench-record-detail/v0.5", changed)

    def test_each_common_required_field_and_mistyped_branch_is_rejected(self) -> None:
        value = json.loads((FIXTURES / "detail-observation.json").read_text("utf-8"))
        for field in (
            "schema_version",
            "record_key",
            "kind",
            "artifact_integrity",
            "manifest",
            "artifacts",
            "relationships",
            "detail",
        ):
            with self.subTest(field=field), self.assertRaises(ValidationError):
                changed = copy.deepcopy(value)
                del changed[field]
                validate_document("tcw.workbench-record-detail/v0.5", changed)
        changed = copy.deepcopy(value)
        changed["detail"]["extractors"][0]["artifact_keys"] = "not-an-array"
        with self.assertRaises(ValidationError):
            validate_document("tcw.workbench-record-detail/v0.5", changed)

    def test_mispaired_refinement_history_is_rejected_semantically(self) -> None:
        value = json.loads(
            (FIXTURES / "detail-refinement-applied.json").read_text("utf-8")
        )
        changed = copy.deepcopy(value)
        changed["detail"]["revision_chain"][0]["after_sha256"] = "0" * 64
        with self.assertRaises(SemanticValidationError):
            validate_document("tcw.workbench-record-detail/v0.5", changed)

    def test_real_applied_and_rejected_details_preserve_branch_semantics(self) -> None:
        built = build_projection(
            admit_records(
                [
                    self.published.observation,
                    self.published.diagnosis,
                    self.published.applied,
                    self.published.rejected,
                ]
            )
        )
        refinements = [
            detail
            for detail in built.details.values()
            if detail["kind"] == "REFINEMENT"
        ]
        by_state = {
            detail["detail"]["decision"]["state"]: detail["detail"]
            for detail in refinements
        }
        self.assertEqual(by_state["APPROVED"]["derivation_state"], "MATCH")
        self.assertEqual(by_state["APPROVED"]["reversibility_state"], "MATCH")
        self.assertTrue(by_state["APPROVED"]["transformations"])
        self.assertEqual(
            by_state["REJECTED"]["derivation_state"], "NOT_APPLICABLE"
        )
        self.assertEqual(
            by_state["REJECTED"]["reversibility_state"], "NOT_APPLICABLE"
        )
        self.assertEqual(by_state["REJECTED"]["transformations"], [])

    def test_real_two_step_chain_projects_every_contiguous_ordinal(self) -> None:
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
        detail = next(
            value["detail"]
            for value in built.details.values()
            if value["kind"] == "REFINEMENT"
            and value["record_key"]
            == next(
                record.record_key
                for record in admit_records([self.chain.second]).records.values()
            )
        )
        self.assertEqual(
            [item["ordinal"] for item in detail["transformations"]], [0, 1]
        )
        self.assertEqual(len(detail["transformations"]), len(detail["revision_chain"]))


if __name__ == "__main__":
    unittest.main()
