from __future__ import annotations

import json
import tempfile
import time
import unittest
from pathlib import Path
from unittest.mock import patch

from tiny_corpus_workbench.application.workbench import RefreshResult
from tests.unit.workbench_server_test_support import ServerHarness


class WorkbenchObservationJourneyTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temporary = tempfile.TemporaryDirectory()
        self.workspace = Path(self.temporary.name) / "workspace"
        self.harness = ServerHarness(workspace=self.workspace)

    def tearDown(self) -> None:
        self.harness.close()
        self.temporary.cleanup()

    def submit(self, target: str, body: bytes = b""):
        return self.harness.request(
            target,
            method="POST",
            headers=[
                ("Host", self.harness.authority),
                ("Content-Length", str(len(body))),
            ],
            body=body,
        )

    def wait_for_terminal(self) -> dict[str, object]:
        deadline = time.monotonic() + 15
        while time.monotonic() < deadline:
            response = self.harness.request("/api/observation-jobs")
            job = json.loads(response.body)["job"]
            if job is not None and job["state"] in {"COMPLETED", "FAILED"}:
                return job
            time.sleep(0.02)
        raise AssertionError("browser observation did not become terminal")

    def assert_selectable_extraction_views(self, job: dict[str, object]) -> None:
        observation = job["observation"]
        self.assertIsInstance(observation, dict)
        record_key = observation["record_key"]
        self.assertIsInstance(record_key, str)
        projection = json.loads(self.harness.request("/api/workbench").body)
        self.assertIn(
            record_key,
            {record["record_key"] for record in projection["records"]},
        )
        detail_response = self.harness.request(f"/api/records/{record_key}")
        self.assertEqual(detail_response.status, 200)
        detail = json.loads(detail_response.body)
        self.assertEqual(detail["kind"], "OBSERVATION")
        self.assertEqual(
            {extractor["name"] for extractor in detail["view"]["extractors"]},
            {"docling", "markitdown"},
        )
        artifact_roles = {artifact["role"] for artifact in detail["artifacts"]}
        self.assertIn("docling-markdown", artifact_roles)
        self.assertIn("markitdown-markdown", artifact_roles)

    def test_guided_and_uploaded_markdown_publish_refresh_and_select(self) -> None:
        guided = self.submit("/api/observation-jobs/guided/policy-memo-md")
        self.assertEqual(guided.status, 202)
        guided_job = self.wait_for_terminal()
        self.assertEqual(guided_job["state"], "COMPLETED")
        self.assertEqual(guided_job["refresh"], {"status": "READY", "message": None})
        self.assert_selectable_extraction_views(guided_job)

        content = b"# Learner upload\n\nThis document stays local.\n"
        uploaded = self.submit(
            "/api/observation-jobs/upload?filename=learner%20memo.md",
            content,
        )
        self.assertEqual(uploaded.status, 202)
        uploaded_job = self.wait_for_terminal()
        self.assertEqual(uploaded_job["state"], "COMPLETED")
        self.assertEqual(
            uploaded_job["refresh"],
            {"status": "READY", "message": None},
        )
        self.assert_selectable_extraction_views(uploaded_job)
        digest = uploaded_job["input"]["sha256"]
        stored = self.workspace / "inputs" / digest / "learner memo.md"
        self.assertEqual(stored.read_bytes(), content)
        self.assertEqual(
            json.loads(self.harness.request("/api/workbench").body)["counts"][
                "record_count"
            ],
            2,
        )

    def test_refresh_failure_retains_view_then_manual_refresh_recovers(self) -> None:
        old_projection = self.harness.state.projection
        with patch.object(
            self.harness.state,
            "refresh",
            return_value=RefreshResult(False, "candidate records are invalid"),
        ):
            accepted = self.submit("/api/observation-jobs/guided/policy-memo-md")
            self.assertEqual(accepted.status, 202)
            terminal = self.wait_for_terminal()

        self.assertEqual(terminal["state"], "COMPLETED")
        self.assertEqual(
            terminal["refresh"],
            {"status": "FAILED", "message": "candidate records are invalid"},
        )
        self.assertIsNone(terminal["observation"]["record_key"])
        self.assertIs(self.harness.state.projection, old_projection)
        self.assertEqual(
            json.loads(self.harness.request("/api/workbench").body)["counts"][
                "record_count"
            ],
            0,
        )
        published = list(
            (self.workspace / "extraction-observatory").rglob("manifest.json")
        )
        self.assertEqual(len(published), 1)

        manual = self.submit("/api/workbench/refresh")
        self.assertEqual(manual.status, 204)
        projection = json.loads(self.harness.request("/api/workbench").body)
        self.assertEqual(projection["counts"]["record_count"], 1)


if __name__ == "__main__":
    unittest.main()
