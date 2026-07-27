from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

from tests.unit.workbench_server_test_support import ServerHarness
from tests.unit.workbench_test_support import (
    PublishedCorpus,
    PublishedDiagnosis,
    PublishedFailedObservation,
    PublishedObservation,
    run_tcw,
)


class WorkbenchIntegrationTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.complete = PublishedObservation()
        cls.incomplete = PublishedFailedObservation()
        cls.corpus = PublishedCorpus()
        cls.diagnosis = PublishedDiagnosis()
        cls.complete_server = ServerHarness(cls.complete.root)
        cls.incomplete_server = ServerHarness(cls.incomplete.root)
        cls.corpus_server = ServerHarness(cls.corpus.root)
        cls.missing_server = ServerHarness(cls.diagnosis.diagnosis)

    @classmethod
    def tearDownClass(cls) -> None:
        cls.complete_server.close()
        cls.incomplete_server.close()
        cls.corpus_server.close()
        cls.missing_server.close()
        cls.diagnosis.close()
        cls.corpus.close()
        cls.incomplete.close()
        cls.complete.close()

    def test_bundled_shell_uses_only_same_origin_assets_with_effective_csp(
        self,
    ) -> None:
        page = self.complete_server.request("/")
        self.assertEqual(page.status, 200)
        html = page.body.decode("utf-8")
        self.assertIn('href="/assets/workbench.css"', html)
        self.assertIn('src="/assets/workbench.js"', html)
        self.assertNotIn("http://", html)
        self.assertNotIn("https://", html)
        csp = page.headers["content-security-policy"]
        self.assertIn("default-src 'self'", csp)
        self.assertIn("script-src 'self'", csp)
        self.assertIn("connect-src 'self'", csp)
        self.assertIn("object-src 'none'", csp)

    def test_complete_and_failed_observations_are_both_usable(self) -> None:
        complete = json.loads(
            self.complete_server.request("/api/v0.5/workbench").body
        )
        failed = json.loads(
            self.incomplete_server.request("/api/v0.5/workbench").body
        )
        self.assertEqual(complete["records"][0]["status"], "SUCCESS")
        self.assertEqual(failed["records"][0]["status"], "FAILED")
        for harness, projection in (
            (self.complete_server, complete),
            (self.incomplete_server, failed),
        ):
            key = projection["records"][0]["record_key"]
            detail = harness.request(f"/api/v0.5/records/{key}")
            self.assertEqual(detail.status, 200)
            self.assertEqual(json.loads(detail.body)["kind"], "OBSERVATION")

    def test_complete_corpus_exposes_matrix_and_all_aggregate_families(
        self,
    ) -> None:
        projection = json.loads(
            self.corpus_server.request("/api/v0.5/workbench").body
        )
        corpus_record = next(
            record for record in projection["records"] if record["kind"] == "CORPUS"
        )
        detail = json.loads(
            self.corpus_server.request(
                f"/api/v0.5/records/{corpus_record['record_key']}"
            ).body
        )
        self.assertEqual(detail["detail"]["summary"]["status"], "COMPLETE")
        self.assertEqual(
            {row["status"] for row in detail["detail"]["matrix"]}, {"COMPLETE"}
        )
        self.assertTrue(detail["detail"]["aggregates"]["extractors"])
        self.assertTrue(detail["detail"]["aggregates"]["findings"])
        comparisons = detail["detail"]["aggregates"]["comparisons"]
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
        self.assertIn("revision_groups", detail["detail"]["aggregates"])
        self.assertIn("revisions", detail["detail"]["aggregates"])

    def test_missing_diagnosis_subject_maps_to_not_checked_evaluations(self) -> None:
        projection = json.loads(
            self.missing_server.request("/api/v0.5/workbench").body
        )
        record = projection["records"][0]
        detail = json.loads(
            self.missing_server.request(
                f"/api/v0.5/records/{record['record_key']}"
            ).body
        )
        self.assertEqual(detail["relationships"][0]["state"], "MISSING")
        self.assertEqual(detail["detail"]["subject_state"], "NOT_CHECKED")
        self.assertEqual(detail["detail"]["derivation_state"], "NOT_CHECKED")

    def test_artifact_retrieval_is_plain_text_and_preserves_unsafe_markup(
        self,
    ) -> None:
        with tempfile.TemporaryDirectory(dir="/private/tmp") as temporary:
            source = Path(temporary) / "unsafe.md"
            unsafe = '<img src=x onerror="alert(1)"> **not rendered**\n'
            source.write_text(unsafe, "utf-8")
            result = run_tcw(
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
                    f"/api/v0.5/artifacts/{descriptor['artifact_key']}"
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

    def test_traversal_mutation_and_unauthorized_artifacts_fail_safely(self) -> None:
        traversal = self.complete_server.request("/api/v0.5/records/../secret")
        mutation = self.complete_server.request("/", method="POST")
        unauthorized = self.complete_server.request(
            "/api/v0.5/artifacts/" + "a" * 64
        )
        self.assertEqual(traversal.status, 400)
        self.assertEqual(mutation.status, 405)
        self.assertEqual(unauthorized.status, 404)
        for response in (traversal, mutation, unauthorized):
            payload = json.loads(response.body)
            self.assertEqual(payload["schema_version"], "tcw.workbench-error/v0.5")

    def test_invalid_authority_precedes_method_and_discloses_no_backing_path(
        self,
    ) -> None:
        response = self.complete_server.request(
            "/unknown",
            method="POST",
            headers=[("Host", "example.invalid")],
        )
        self.assertEqual(response.status, 403)
        payload = json.loads(response.body)
        self.assertEqual(payload["error"]["code"], "HOST_REJECTED")
        body = response.body.decode("utf-8")
        self.assertNotIn(str(self.complete.root), body)
        self.assertNotIn("/private/", body)

    def test_canonical_artifact_mutation_returns_sanitized_conflict(self) -> None:
        detail = next(iter(self.incomplete_server.projection.details.values()))
        descriptor = detail["manifest"]
        record = next(iter(self.incomplete_server.records.records.values()))
        target = record.backing.root / descriptor["relative_path"]
        target.write_bytes(target.read_bytes() + b" ")
        response = self.incomplete_server.request(
            f"/api/v0.5/artifacts/{descriptor['artifact_key']}"
        )
        self.assertEqual(response.status, 409)
        payload = json.loads(response.body)
        self.assertEqual(payload["error"]["code"], "ARTIFACT_CHANGED")
        self.assertNotIn(str(target), response.body.decode("utf-8"))


if __name__ == "__main__":
    unittest.main()
