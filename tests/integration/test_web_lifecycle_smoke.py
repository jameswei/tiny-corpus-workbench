from __future__ import annotations

import json
import tempfile
import time
import unittest
from pathlib import Path

from tests.unit.workbench_server_test_support import ServerHarness


class InstalledRuntimeLifecycleSmokeTests(unittest.TestCase):
    def test_whitespace_approval_is_published_and_inspectable(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            harness = ServerHarness(workspace=Path(directory) / "workspace")
            try:
                token = json.loads(
                    harness.request("/api/lifecycle/action-token").body
                )["action_token"]

                accepted = self._post(
                    harness,
                    "/api/observation-jobs/guided/whitespace-cleanup-md",
                )
                self.assertEqual(accepted.status, 202)
                observation = self._wait_for_observation(harness)
                self.assertEqual(observation["state"], "COMPLETED")
                self.assertEqual(
                    observation["refresh"], {"status": "READY", "message": None}
                )

                diagnosis = json.loads(
                    self._post(
                        harness,
                        "/api/lifecycle/diagnoses/"
                        + observation["observation"]["record_key"],
                        token=token,
                    ).body
                )
                diagnosis_key = diagnosis["publication"]["record_key"]
                detail = json.loads(
                    harness.request(f"/api/records/{diagnosis_key}").body
                )
                finding = next(
                    item
                    for item in detail["view"]["findings"]
                    if item["rule_id"] == "D009"
                )
                self.assertEqual(
                    finding["proposal_action"],
                    {"status": "AVAILABLE", "reason": None},
                )

                draft = json.loads(
                    self._post(
                        harness,
                        f"/api/lifecycle/proposals/{diagnosis_key}/"
                        f"{finding['finding_id']}",
                        token=token,
                    ).body
                )["draft"]
                approved = json.loads(
                    self._post(
                        harness,
                        f"/api/lifecycle/proposals/{draft['draft_key']}/approve",
                        token=token,
                    ).body
                )
                self.assertEqual(approved["publication"]["decision"], "APPROVED")
                refinement_key = approved["publication"]["record_key"]

                refinement = json.loads(
                    harness.request(f"/api/records/{refinement_key}").body
                )["view"]
                self.assertEqual(refinement["decision"], "APPROVED")
                self.assertEqual(refinement["derivation_state"], "MATCH")
                self.assertEqual(refinement["reversibility_state"], "MATCH")
                self.assertTrue(refinement["transformations"])
                self.assertTrue(refinement["revision_chain"])
            finally:
                harness.close()

    @staticmethod
    def _post(
        harness: ServerHarness, target: str, *, token: str | None = None
    ):
        headers = [("Host", harness.authority), ("Content-Length", "0")]
        if token is not None:
            headers.append(("X-TCW-Action-Token", token))
        return harness.request(target, method="POST", headers=headers)

    @staticmethod
    def _wait_for_observation(harness: ServerHarness) -> dict[str, object]:
        deadline = time.monotonic() + 15
        while time.monotonic() < deadline:
            job = json.loads(harness.request("/api/observation-jobs").body)["job"]
            if job is not None and job["state"] in {"COMPLETED", "FAILED"}:
                return job
            time.sleep(0.02)
        raise AssertionError("whitespace observation did not become terminal")


if __name__ == "__main__":
    unittest.main()
