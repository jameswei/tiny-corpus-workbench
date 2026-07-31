from __future__ import annotations

import json
import tempfile
import time
import unittest
from pathlib import Path

from tests.unit.workbench_server_test_support import ServerHarness


class GuidedWebObservationSmokeTests(unittest.TestCase):
    def test_guided_observation_publishes_refreshes_and_is_selectable(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            harness = ServerHarness(workspace=Path(directory) / "workspace")
            try:
                accepted = harness.request(
                    "/api/observation-jobs/guided",
                    method="POST",
                    headers=[
                        ("Host", harness.authority),
                        ("Content-Length", "0"),
                    ],
                )
                self.assertEqual(accepted.status, 202)

                deadline = time.monotonic() + 15
                job = None
                while time.monotonic() < deadline:
                    response = harness.request("/api/observation-jobs")
                    job = json.loads(response.body)["job"]
                    if job is not None and job["state"] in {"COMPLETED", "FAILED"}:
                        break
                    time.sleep(0.02)
                else:
                    self.fail("guided Web observation did not become terminal")

                self.assertEqual(job["state"], "COMPLETED")
                self.assertEqual(job["refresh"], {"status": "READY", "message": None})
                record_key = job["observation"]["record_key"]
                projection = json.loads(harness.request("/api/workbench").body)
                self.assertIn(
                    record_key,
                    {record["record_key"] for record in projection["records"]},
                )
            finally:
                harness.close()


if __name__ == "__main__":
    unittest.main()
