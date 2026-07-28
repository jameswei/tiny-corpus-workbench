from __future__ import annotations

import unittest
from unittest.mock import patch

from tiny_corpus_workbench.canonical_json import session_id
from tiny_corpus_workbench.domain import IntegrityError
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

    def test_projection_is_compact_and_deterministic(self) -> None:
        first = build_projection(admit_records([self.published.root]))
        second = build_projection(admit_records([self.published.root]))
        self.assertEqual(first.projection_bytes(), second.projection_bytes())
        self.assertEqual(
            set(first.projection), {"session_id", "counts", "records"}
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


if __name__ == "__main__":
    unittest.main()
