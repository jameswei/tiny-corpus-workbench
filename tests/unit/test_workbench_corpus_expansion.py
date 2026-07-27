from __future__ import annotations

import copy
import hashlib
import shutil
import unittest
from pathlib import Path
from unittest.mock import patch

from tiny_corpus_workbench.workbench_projection import (
    _record_edges,
    build_projection,
)
from tiny_corpus_workbench.workbench_records import (
    AdmittedRecords,
    Backing,
    _nested_backings,
    admit_record,
    admit_records,
)
from tests.unit.workbench_test_support import (
    PublishedCorpus,
    PublishedFailedObservation,
)


class WorkbenchCorpusExpansionTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.published = PublishedCorpus()
        cls.failed = PublishedFailedObservation()

    @classmethod
    def tearDownClass(cls) -> None:
        cls.published.close()
        cls.failed.close()

    def test_null_stage_contract_is_covered_by_canonical_example(self) -> None:
        # The committed missing-edge example is the bounded no-inference branch.
        fixture = (
            Path(__file__).resolve().parents[1]
            / "fixtures/workbench-api/projection-missing-edge.json"
        )
        self.assertIn(b'"state":"MISSING"', fixture.read_bytes())

    def test_contained_dedup_example_has_exact_count_equation(self) -> None:
        import json

        fixture = (
            Path(__file__).resolve().parents[1]
            / "fixtures/workbench-api/projection-contained-dedup.json"
        )
        value = json.loads(fixture.read_text("utf-8"))
        counts = value["counts"]
        self.assertEqual(
            counts["record_count"],
            counts["top_level_record_count"] + counts["contained_record_count"],
        )
        self.assertTrue(
            any(
                edge["relation"].startswith("CORPUS_CONTAINS_")
                and edge["state"] == "MATCH"
                for edge in value["edges"]
            )
        )

    def test_verified_descriptors_expand_bounded_member_records(self) -> None:
        admitted = admit_records([self.published.root])
        built = build_projection(admitted)
        self.assertEqual(
            built.projection["counts"],
            {
                "record_count": 11,
                "top_level_record_count": 1,
                "contained_record_count": 10,
            },
        )
        containment = [
            edge
            for edge in built.projection["edges"]
            if edge["relation"].startswith("CORPUS_CONTAINS_")
        ]
        self.assertEqual(len(containment), 10)
        self.assertTrue(all(edge["state"] == "MATCH" for edge in containment))

    def test_explicit_member_copy_deduplicates_and_has_top_level_precedence(self) -> None:
        corpus = admit_records([self.published.root])
        child = next(
            record
            for record in corpus.records.values()
            if record.kind == "OBSERVATION"
        )
        combined = admit_records([self.published.root, child.backing.root])
        built = build_projection(combined)
        self.assertEqual(built.projection["counts"]["record_count"], 11)
        self.assertEqual(built.projection["counts"]["top_level_record_count"], 2)
        self.assertEqual(built.projection["counts"]["contained_record_count"], 9)

    def test_published_failed_observation_is_an_admitted_logical_node(self) -> None:
        admitted = admit_records([self.failed.root])
        built = build_projection(admitted)
        self.assertEqual(built.projection["counts"]["record_count"], 1)
        self.assertEqual(built.projection["records"][0]["status"], "FAILED")
        self.assertEqual(built.projection["records"][0]["artifact_count"], 2)

    def test_published_failed_descriptor_expands_but_null_stages_do_not_probe(
        self,
    ) -> None:
        corpus = next(
            record
            for record in admit_records([self.published.root]).records.values()
            if record.kind == "CORPUS"
        )
        fake_root = Path(self.published.temporary.name) / "synthetic-corpus"
        fake_root.mkdir()
        nested = fake_root / "failed" / self.failed.root.name
        nested.parent.mkdir()
        shutil.copytree(self.failed.root, nested)
        manifest_path = nested / "manifest.json"
        descriptor = {
            "path": manifest_path.relative_to(fake_root).as_posix(),
            "size": manifest_path.stat().st_size,
            "sha256": hashlib.sha256(manifest_path.read_bytes()).hexdigest(),
        }
        fake = copy.copy(corpus)
        fake.backing = Backing(root=fake_root, top_level=True)
        fake.manifest = {
            **corpus.manifest,
            "members": [
                {
                    "member_id": "failed-published",
                    "observation": {"manifest": descriptor},
                    "diagnosis": {"manifest": None},
                },
                {
                    "member_id": "failed-null",
                    "observation": {"manifest": None},
                    "diagnosis": {"manifest": None},
                },
                {
                    "member_id": "not-run-null",
                    "observation": {"manifest": None},
                    "diagnosis": {"manifest": None},
                },
            ],
        }
        backings = list(_nested_backings(fake))
        self.assertEqual(len(backings), 1)
        expanded = admit_record(backings[0][0].root, backing=backings[0][0])
        self.assertEqual((expanded.kind, expanded.status), ("OBSERVATION", "FAILED"))

        fake.manifest["members"] = fake.manifest["members"][1:]
        with patch(
            "tiny_corpus_workbench.workbench_records._safe_path",
            side_effect=AssertionError("null stage inferred a path"),
        ):
            self.assertEqual(list(_nested_backings(fake)), [])

    def test_external_revision_path_is_never_opened(self) -> None:
        corpus = next(
            record
            for record in admit_records([self.published.root]).records.values()
            if record.kind == "CORPUS"
        )
        fake = copy.copy(corpus)
        fake.manifest = {
            **corpus.manifest,
            "members": [],
            "revisions": [
                {
                    "member_id": "external",
                    "revision_id": "1" * 64,
                    "refinement_run_id": "external-run",
                    "refinement_manifest_sha256": "2" * 64,
                    "prepared_document_sha256": "3" * 64,
                    "bundle_paths": {
                        "refinement": "/private/tmp/must-not-open",
                    },
                }
            ],
        }
        records = AdmittedRecords(
            records={fake.record_key: fake},
            explicit_keys={fake.record_key},
            containment=[],
        )
        with patch(
            "pathlib.Path.read_bytes",
            side_effect=AssertionError("external revision path was opened"),
        ):
            edges = _record_edges(records, fake)
        self.assertEqual(len(edges), 1)
        self.assertEqual(
            (edges[0]["relation"], edges[0]["state"]),
            ("CORPUS_EXTERNAL_REFINEMENT", "MISSING"),
        )


if __name__ == "__main__":
    unittest.main()
