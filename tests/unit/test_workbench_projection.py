from __future__ import annotations

import unittest
from unittest.mock import patch

from tiny_corpus_workbench.domain import IntegrityError
from tiny_corpus_workbench.schema_catalog import validate_document
from tiny_corpus_workbench.canonical_json import session_id
from tiny_corpus_workbench.workbench_projection import build_projection
from tiny_corpus_workbench.workbench_records import admit_records
from tests.unit.workbench_test_support import PublishedObservation


class WorkbenchProjectionTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.published = PublishedObservation()

    @classmethod
    def tearDownClass(cls) -> None:
        cls.published.close()

    def test_projection_is_schema_valid_and_deterministic(self) -> None:
        first = build_projection(admit_records([self.published.root]))
        second = build_projection(admit_records([self.published.root]))
        self.assertEqual(first.projection_bytes(), second.projection_bytes())
        validate_document("tcw.workbench-projection/v0.5", first.projection)
        self.assertEqual(
            first.projection["counts"],
            {
                "record_count": 1,
                "top_level_record_count": 1,
                "contained_record_count": 0,
            },
        )

    def test_projection_and_detail_use_the_same_manifest_descriptor(self) -> None:
        built = build_projection(admit_records([self.published.root]))
        node = built.projection["records"][0]
        detail = built.details[node["record_key"]]
        self.assertEqual(node["manifest"], detail["manifest"])
        self.assertEqual(node["artifact_count"], 1 + len(detail["artifacts"]))

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

    def test_descriptor_union_is_exact_unique_ordered_and_authorized(self) -> None:
        admitted = admit_records([self.published.root])
        built = build_projection(admitted)
        node = built.projection["records"][0]
        detail = built.details[node["record_key"]]
        union = [detail["manifest"], *detail["artifacts"]]
        self.assertEqual(node["artifact_count"], len(union))
        self.assertEqual(
            [item["artifact_key"] for item in detail["artifacts"]],
            sorted(item["artifact_key"] for item in detail["artifacts"]),
        )
        self.assertEqual(
            len({item["artifact_key"] for item in union}), len(union)
        )
        self.assertEqual(
            len({item["relative_path"] for item in union}), len(union)
        )
        record = next(iter(admitted.records.values()))
        self.assertEqual(set(record.authorized_artifacts), {
            item["artifact_key"] for item in union
        })
        self.assertEqual(detail["manifest"]["origin"], "ROOT_MANIFEST")
        self.assertTrue(
            all(item["origin"] == "MANIFEST_LISTED" for item in detail["artifacts"])
        )

    def test_root_and_listed_artifact_limits_are_independent(self) -> None:
        with (
            patch(
                "tiny_corpus_workbench.workbench_records.MAX_ARTIFACT_CONTENT",
                1,
            ),
            patch(
                "tiny_corpus_workbench.semantic_validation.EXPLICIT_ARTIFACT_LIMIT",
                1,
            ),
        ):
            built = build_projection(admit_records([self.published.root]))
        detail = next(iter(built.details.values()))
        self.assertEqual(detail["manifest"]["availability"], "TOO_LARGE")
        self.assertTrue(
            all(
                item["availability"] == "TOO_LARGE"
                for item in detail["artifacts"]
            )
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
            if item["admission_origin"] == "TOP_LEVEL"
        ]
        contained = [
            item["record_key"]
            for item in projection["records"]
            if item["admission_origin"] == "CORPUS_CONTAINED"
        ]
        self.assertEqual(
            projection["session_id"],
            session_id(
                top_level_record_keys=top,
                contained_record_keys=contained,
                edge_keys=[item["edge_key"] for item in projection["edges"]],
            ),
        )


if __name__ == "__main__":
    unittest.main()
