from __future__ import annotations

import json
import tempfile
import time
import unittest
from pathlib import Path

from tests.unit.workbench_server_test_support import ServerHarness


class WorkbenchLifecycleJourneyTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temporary = tempfile.TemporaryDirectory()
        self.workspace = Path(self.temporary.name) / "workspace"
        self.harness = ServerHarness(workspace=self.workspace)
        token_response = self.harness.request("/api/lifecycle/action-token")
        self.token = json.loads(token_response.body)["action_token"]

    def tearDown(self) -> None:
        self.harness.close()
        self.temporary.cleanup()

    def post(self, target: str, *, token: bool = False):
        headers = [
            ("Host", self.harness.authority),
            ("Content-Length", "0"),
        ]
        if token:
            headers.append(("X-TCW-Action-Token", self.token))
        return self.harness.request(target, method="POST", headers=headers)

    def wait_for_observation(self) -> dict[str, object]:
        deadline = time.monotonic() + 15
        while time.monotonic() < deadline:
            job = json.loads(
                self.harness.request("/api/observation-jobs").body
            )["job"]
            if job is not None and job["state"] in {"COMPLETED", "FAILED"}:
                return job
            time.sleep(0.02)
        raise AssertionError("guided lifecycle observation did not finish")

    def _run_whitespace_lifecycle(self, decision: str) -> None:
        accepted = self.post(
            "/api/observation-jobs/guided/whitespace-cleanup-md"
        )
        self.assertEqual(accepted.status, 202)
        observation_job = self.wait_for_observation()
        self.assertEqual(observation_job["state"], "COMPLETED")
        observation_key = observation_job["observation"]["record_key"]

        diagnosed = self.post(
            f"/api/lifecycle/diagnoses/{observation_key}", token=True
        )
        self.assertEqual(diagnosed.status, 200)
        diagnosis_key = json.loads(diagnosed.body)["publication"]["record_key"]
        diagnosis = json.loads(
            self.harness.request(f"/api/records/{diagnosis_key}").body
        )
        finding = next(
            item
            for item in diagnosis["view"]["findings"]
            if item["rule_id"] == "D009"
        )
        self.assertEqual(finding["refiner"]["name"], "WHITESPACE_NORMALIZATION")
        self.assertEqual(
            finding["proposal_action"], {"status": "AVAILABLE", "reason": None}
        )

        proposal_target = (
            f"/api/lifecycle/proposals/{diagnosis_key}/{finding['finding_id']}"
        )
        proposal = json.loads(self.post(proposal_target, token=True).body)["draft"]
        self.assertIsInstance(proposal["edits"][0]["before"], str)
        self.assertIsInstance(proposal["edits"][0]["after"], str)

        resolved = json.loads(
            self.post(
                f"/api/lifecycle/proposals/{proposal['draft_key']}/{decision}",
                token=True,
            ).body
        )
        expected = "APPROVED" if decision == "approve" else "REJECTED"
        self.assertEqual(resolved["publication"]["decision"], expected)
        if decision == "reject":
            self.assertIsNone(resolved["publication"]["revision_id"])
            return

        self.assertIsInstance(resolved["publication"]["revision_id"], str)
        refinement_key = resolved["publication"]["record_key"]
        refinement = json.loads(
            self.harness.request(f"/api/records/{refinement_key}").body
        )
        self.assertEqual(refinement["view"]["reversibility_state"], "MATCH")
        continued = self.post(
            f"/api/lifecycle/diagnoses/{refinement_key}", token=True
        )
        self.assertEqual(continued.status, 200)

    def test_whitespace_lifecycle_supports_approval(self) -> None:
        self._run_whitespace_lifecycle("approve")

    def test_whitespace_lifecycle_supports_rejection(self) -> None:
        self._run_whitespace_lifecycle("reject")


if __name__ == "__main__":
    unittest.main()
