from __future__ import annotations

import json
import shutil
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

from tests.unit.workbench_server_test_support import ServerHarness
from tests.unit.workbench_test_support import (
    REPOSITORY,
    PublishedCorpus,
    PublishedDiagnosis,
    PublishedFailedObservation,
    PublishedObservation,
    PublishedRefinements,
    run_corpus,
)


class WorkbenchIntegrationTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.complete = PublishedObservation()
        cls.incomplete = PublishedFailedObservation()
        cls.corpus = PublishedCorpus()
        cls.diagnosis = PublishedDiagnosis()
        cls.refinements = PublishedRefinements()
        cls.complete_server = ServerHarness(cls.complete.root)
        cls.incomplete_server = ServerHarness(cls.incomplete.root)
        cls.corpus_server = ServerHarness(cls.corpus.root)

    @classmethod
    def tearDownClass(cls) -> None:
        cls.complete_server.close()
        cls.incomplete_server.close()
        cls.corpus_server.close()
        cls.diagnosis.close()
        cls.refinements.close()
        cls.corpus.close()
        cls.incomplete.close()
        cls.complete.close()

    def test_bundled_shell_uses_only_same_origin_assets(self) -> None:
        page = self.complete_server.request("/")
        self.assertEqual(page.status, 200)
        html = page.body.decode("utf-8")
        self.assertIn('href="/assets/workbench.css"', html)
        self.assertIn('src="/assets/workbench.js"', html)
        self.assertNotIn("http://", html)
        self.assertNotIn("https://", html)

    def test_complete_and_failed_observations_are_both_usable(self) -> None:
        complete = json.loads(
            self.complete_server.request("/api/workbench").body
        )
        failed = json.loads(
            self.incomplete_server.request("/api/workbench").body
        )
        self.assertEqual(complete["records"][0]["status"], "SUCCESS")
        self.assertEqual(failed["records"][0]["status"], "FAILED")
        for harness, projection in (
            (self.complete_server, complete),
            (self.incomplete_server, failed),
        ):
            key = projection["records"][0]["record_key"]
            detail = harness.request(f"/api/records/{key}")
            self.assertEqual(detail.status, 200)
            self.assertEqual(json.loads(detail.body)["kind"], "OBSERVATION")

    def test_complete_corpus_exposes_matrix_and_all_aggregate_families(
        self,
    ) -> None:
        projection = json.loads(
            self.corpus_server.request("/api/workbench").body
        )
        corpus_record = next(
            record for record in projection["records"] if record["kind"] == "CORPUS"
        )
        self.assertEqual(
            projection["corpora"],
            [
                {
                    "record_key": corpus_record["record_key"],
                    "corpus_id": "model-free-workbench-corpus",
                    "title": "Model-free workbench corpus",
                    "status": "COMPLETE",
                    "member_count": 5,
                }
            ],
        )
        detail = json.loads(
            self.corpus_server.request(
                f"/api/records/{corpus_record['record_key']}"
            ).body
        )
        self.assertEqual(detail["view"]["status"], "COMPLETE")
        self.assertEqual(
            {row["status"] for row in detail["view"]["matrix"]}, {"COMPLETE"}
        )
        self.assertTrue(detail["view"]["aggregates"]["extractors"])
        self.assertTrue(detail["view"]["aggregates"]["findings"])
        comparisons = detail["view"]["aggregates"]["comparisons"]
        self.assertTrue(comparisons)
        exact_metrics = {
            "bytes",
            "characters",
            "non_whitespace_characters",
            "lines",
            "non_empty_lines",
            "atx_headings",
            "unordered_list_items",
            "ordered_list_items",
            "pipe_table_rows",
            "visible_urls",
        }
        for comparison in comparisons:
            with self.subTest(member_id=comparison["member_id"]):
                self.assertEqual(set(comparison["docling"]), exact_metrics)
                self.assertEqual(set(comparison["markitdown"]), exact_metrics)
                self.assertEqual(
                    set(comparison["docling_minus_markitdown"]),
                    exact_metrics | {"normalized_equal"},
                )
        self.assertIn("revision_groups", detail["view"]["aggregates"])
        self.assertIn("revisions", detail["view"]["aggregates"])

    def test_missing_lifecycle_subject_refresh_keeps_accepted_snapshot(self) -> None:
        with tempfile.TemporaryDirectory(
            dir=Path(tempfile.gettempdir()).resolve()
        ) as temporary:
            workspace = Path(temporary)
            observation = (
                workspace
                / "extraction-observatory"
                / self.complete.root.name
            )
            observation.parent.mkdir(parents=True)
            shutil.copytree(self.complete.root, observation)
            harness = ServerHarness(workspace=workspace)
            try:
                accepted = harness.state.projection
                diagnosis = (
                    workspace
                    / "evidence-based-diagnosis"
                    / self.diagnosis.diagnosis.name
                )
                diagnosis.parent.mkdir(parents=True)
                shutil.copytree(self.diagnosis.diagnosis, diagnosis)
                before = {
                    path: path.read_bytes()
                    for path in (observation / "manifest.json", diagnosis / "diagnosis-manifest.json")
                }
                response = harness.request(
                    "/api/workbench/refresh",
                    method="POST",
                    headers=[
                        ("Host", harness.authority),
                        ("Content-Length", "0"),
                    ],
                )
                after = {path: path.read_bytes() for path in before}
            finally:
                harness.close()
        self.assertEqual(response.status, 409)
        self.assertIs(harness.state.projection, accepted)
        self.assertEqual(after, before)

    def test_artifact_retrieval_is_plain_text_and_preserves_unsafe_markup(
        self,
    ) -> None:
        with tempfile.TemporaryDirectory(
            dir=Path(tempfile.gettempdir()).resolve()
        ) as temporary:
            source = Path(temporary) / "unsafe.md"
            unsafe = '<img src=x onerror="alert(1)"> **not rendered**\n'
            source.write_text(unsafe, "utf-8")
            result = run_corpus(
                "observe",
                str(source),
                "--output-root",
                str(Path(temporary) / "output"),
            )
            harness = ServerHarness(Path(result["manifest"]).parent)
            try:
                detail = next(iter(harness.projection.details.values()))
                descriptor = next(
                    artifact
                    for artifact in detail["artifacts"]
                    if artifact["role"] == "markitdown-markdown"
                )
                response = harness.request(
                    f"/api/artifacts/{descriptor['artifact_key']}"
                )
            finally:
                harness.close()
        self.assertEqual(response.status, 200)
        self.assertEqual(
            response.headers["content-type"], "text/plain; charset=utf-8"
        )
        content = response.body.decode("utf-8")
        self.assertIn("<img", content)
        self.assertIn("onerror", content)
        self.assertIn("**not rendered**", content)

    def test_unknown_mutation_and_unauthorized_artifacts_fail_safely(self) -> None:
        unknown = self.complete_server.request("/api/records/not-a-key")
        mutation = self.complete_server.request("/", method="POST")
        unauthorized = self.complete_server.request(
            "/api/artifacts/" + "a" * 64
        )
        self.assertEqual(unknown.status, 404)
        self.assertEqual(mutation.status, 405)
        self.assertEqual(unauthorized.status, 404)
        for response in (unknown, mutation, unauthorized):
            payload = json.loads(response.body)
            self.assertEqual(set(payload), {"code", "message"})

    def test_canonical_artifact_is_served_from_startup_capture(self) -> None:
        detail = next(iter(self.incomplete_server.projection.details.values()))
        descriptor = detail["artifacts"][0]
        captured = self.incomplete_server.projection.artifact_contents[
            descriptor["artifact_key"]
        ]
        record = next(iter(self.incomplete_server.records.records.values()))
        target = record.backing.root / record.manifest_name
        original = target.read_bytes()
        try:
            target.write_bytes(b"changed after startup")
            response = self.incomplete_server.request(
                f"/api/artifacts/{descriptor['artifact_key']}"
            )
        finally:
            target.write_bytes(original)
        self.assertEqual(response.status, 200)
        self.assertEqual(response.body, captured)

    def test_empty_workspace_accepts_cli_publication_after_refresh(self) -> None:
        with tempfile.TemporaryDirectory(
            dir=Path(tempfile.gettempdir()).resolve()
        ) as temporary:
            workspace = Path(temporary)
            harness = ServerHarness(workspace=workspace)
            try:
                empty = json.loads(harness.request("/api/workbench").body)
                self.assertEqual(empty["refresh"]["status"], "READY")
                self.assertEqual(empty["counts"]["record_count"], 0)
                published = run_corpus(
                    "observe",
                    str(REPOSITORY / "fixtures/golden/policy-memo.md"),
                    "--output-root",
                    str(workspace / "extraction-observatory"),
                )
                refreshed = harness.request(
                    "/api/workbench/refresh",
                    method="POST",
                    headers=[("Host", harness.authority), ("Content-Length", "0")],
                )
                accepted = json.loads(harness.request("/api/workbench").body)
                record_key = accepted["records"][0]["record_key"]
                detail = harness.request(f"/api/records/{record_key}")
            finally:
                harness.close()
        self.assertEqual(Path(published["manifest"]).name, "manifest.json")
        self.assertEqual(refreshed.status, 204)
        self.assertEqual(accepted["refresh"]["status"], "READY")
        self.assertEqual(accepted["counts"]["record_count"], 1)
        self.assertEqual(json.loads(detail.body)["kind"], "OBSERVATION")

    def test_default_build_workspace_needs_no_output_configuration(self) -> None:
        with tempfile.TemporaryDirectory(
            dir=Path(tempfile.gettempdir()).resolve()
        ) as temporary:
            root = Path(temporary)
            harness = ServerHarness(workspace=root / "build")
            try:
                completed = subprocess.run(
                    [
                        sys.executable,
                        "-m",
                        "tiny_corpus_workbench",
                        "observe",
                        str(REPOSITORY / "fixtures/golden/policy-memo.md"),
                    ],
                    cwd=root,
                    check=True,
                    capture_output=True,
                    text=True,
                )
                response = harness.request(
                    "/api/workbench/refresh",
                    method="POST",
                    headers=[("Host", harness.authority), ("Content-Length", "0")],
                )
                accepted = json.loads(harness.request("/api/workbench").body)
            finally:
                harness.close()
        self.assertEqual(response.status, 204)
        self.assertEqual(accepted["counts"]["record_count"], 1)
        manifest = json.loads(completed.stdout)["manifest"]
        self.assertTrue(manifest.endswith("manifest.json"))

    def test_shared_workspace_accepts_all_four_record_families(self) -> None:
        with tempfile.TemporaryDirectory(
            dir=Path(tempfile.gettempdir()).resolve()
        ) as temporary:
            workspace = Path(temporary)
            supplied = (
                ("extraction-observatory", self.refinements.observation),
                ("evidence-based-diagnosis", self.refinements.diagnosis),
                ("controlled-revisions", self.refinements.applied),
                ("corpus-inspection", self.corpus.root),
            )
            for family, source in supplied:
                destination = workspace / family / source.name
                destination.parent.mkdir(parents=True, exist_ok=True)
                shutil.copytree(source, destination)
            harness = ServerHarness(workspace=workspace)
            try:
                accepted = json.loads(harness.request("/api/workbench").body)
            finally:
                harness.close()
        self.assertEqual(
            {record["kind"] for record in accepted["records"]},
            {"OBSERVATION", "DIAGNOSIS", "REFINEMENT", "CORPUS"},
        )
        self.assertEqual(accepted["counts"]["top_level_record_count"], 4)
        self.assertGreater(accepted["counts"]["contained_record_count"], 0)

    def test_sibling_decision_refresh_rejects_candidate_and_keeps_snapshot(self) -> None:
        with tempfile.TemporaryDirectory(
            dir=Path(tempfile.gettempdir()).resolve()
        ) as temporary:
            workspace = Path(temporary)
            supplied = (
                ("extraction-observatory", self.refinements.observation),
                ("evidence-based-diagnosis", self.refinements.diagnosis),
                ("controlled-revisions", self.refinements.applied),
            )
            for family, source in supplied:
                destination = workspace / family / source.name
                destination.parent.mkdir(parents=True, exist_ok=True)
                shutil.copytree(source, destination)
            harness = ServerHarness(workspace=workspace)
            try:
                accepted = harness.state.projection
                rejected = (
                    workspace
                    / "controlled-revisions"
                    / self.refinements.rejected.name
                )
                shutil.copytree(self.refinements.rejected, rejected)
                response = harness.request(
                    "/api/workbench/refresh",
                    method="POST",
                    headers=[
                        ("Host", harness.authority),
                        ("Content-Length", "0"),
                    ],
                )
                payload = json.loads(
                    harness.request("/api/workbench").body
                )
            finally:
                harness.close()
        self.assertEqual(response.status, 409)
        self.assertIs(harness.state.projection, accepted)
        self.assertEqual(payload["refresh"]["status"], "FAILED")
        self.assertEqual(payload["counts"]["top_level_record_count"], 3)

    def test_second_observation_root_refresh_keeps_first_snapshot_and_files(self) -> None:
        with tempfile.TemporaryDirectory(
            dir=Path(tempfile.gettempdir()).resolve()
        ) as temporary:
            workspace = Path(temporary)
            output = workspace / "extraction-observatory"
            first = run_corpus(
                "observe",
                str(REPOSITORY / "fixtures/golden/policy-memo.md"),
                "--output-root",
                str(output),
            )
            harness = ServerHarness(workspace=workspace)
            try:
                accepted = harness.state.projection
                second = run_corpus(
                    "observe",
                    str(REPOSITORY / "fixtures/golden/policy-memo.md"),
                    "--output-root",
                    str(output),
                )
                manifests = {
                    Path(first["manifest"]): Path(first["manifest"]).read_bytes(),
                    Path(second["manifest"]): Path(second["manifest"]).read_bytes(),
                }
                response = harness.request(
                    "/api/workbench/refresh",
                    method="POST",
                    headers=[
                        ("Host", harness.authority),
                        ("Content-Length", "0"),
                    ],
                )
                after = {path: path.read_bytes() for path in manifests}
            finally:
                harness.close()
        self.assertEqual(response.status, 409)
        self.assertIs(harness.state.projection, accepted)
        self.assertEqual(after, manifests)


if __name__ == "__main__":
    unittest.main()
