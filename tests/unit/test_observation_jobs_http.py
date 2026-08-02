from __future__ import annotations

import json
import tempfile
import time
import unittest
from pathlib import Path
from unittest.mock import patch

from tiny_corpus_workbench.workbench_server import Response
from tests.unit.workbench_server_test_support import ServerHarness


class ObservationJobHttpTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temporary = tempfile.TemporaryDirectory()
        self.workspace = Path(self.temporary.name) / "workspace"
        self.harness = ServerHarness(workspace=self.workspace)

    def tearDown(self) -> None:
        self.harness.close()
        self.temporary.cleanup()

    def request_upload(self, query: str, content: bytes):
        return self.harness.request(
            f"/api/observation-jobs/upload?{query}",
            method="POST",
            headers=[
                ("Host", self.harness.authority),
                ("Content-Length", str(len(content))),
            ],
            body=content,
        )

    def wait_for_terminal(self):
        deadline = time.monotonic() + 15
        while time.monotonic() < deadline:
            response = self.harness.request("/api/observation-jobs")
            job = json.loads(response.body)["job"]
            if job is not None and job["state"] in {"COMPLETED", "FAILED"}:
                return job
            time.sleep(0.02)
        raise AssertionError("HTTP job did not become terminal")

    def test_capability_envelope_has_exact_get_head_parity(self) -> None:
        get = self.harness.request("/api/observation-jobs")
        head = self.harness.request("/api/observation-jobs", method="HEAD")
        payload = json.loads(get.body)
        self.assertEqual(get.status, 200)
        self.assertEqual(head.status, 200)
        self.assertEqual(head.body, b"")
        self.assertEqual(head.headers["content-length"], get.headers["content-length"])
        self.assertNotIn("access-control-allow-origin", get.headers)
        self.assertEqual(
            payload,
            {
                "capabilities": {
                    "guided": [
                        {
                            "id": "policy-memo-md",
                            "name": "policy-memo.md",
                            "media_type": "text/markdown",
                        },
                        {
                            "id": "whitespace-cleanup-md",
                            "name": "whitespace-cleanup.md",
                            "media_type": "text/markdown",
                        },
                    ],
                    "upload": {
                        "extensions": [".docx", ".md", ".pdf", ".txt"],
                        "max_bytes": 33554432,
                    },
                },
                "job": None,
            },
        )

    def test_methods_and_strict_upload_query_contract(self) -> None:
        recognized = (
            "/api/observation-jobs",
            "/api/observation-jobs/guided/policy-memo-md",
            "/api/observation-jobs/upload?filename=x.md",
        )
        for target in recognized:
            response = self.harness.request(target, method="DELETE")
            self.assertEqual(response.status, 405)
            self.assertEqual(json.loads(response.body)["code"], "METHOD_NOT_ALLOWED")

        invalid = (
            "",
            "filename=",
            "filename",
            "filename=x.md&extra=y",
            "extra=x.md",
            "filename=%",
            "filename=%GG",
            "filename=%FF.md",
            "filename=.",
            "filename=..",
        )
        for query in invalid:
            with self.subTest(query=query):
                response = self.request_upload(query, b"# valid\n")
                self.assertEqual(response.status, 400)
                self.assertEqual(json.loads(response.body)["code"], "INVALID_REQUEST")

    def test_upload_framing_and_size_reject_before_body_read(self) -> None:
        path = "/api/observation-jobs/upload?filename=x.md"
        invalid_headers = (
            [],
            [("Content-Length", "0")],
            [("Content-Length", "-1")],
            [("Content-Length", "nope")],
            [("Transfer-Encoding", "chunked")],
        )
        for extra in invalid_headers:
            response = self.harness.request(
                path,
                method="POST",
                headers=[("Host", self.harness.authority), *extra],
            )
            self.assertEqual(response.status, 400)
            self.assertEqual(json.loads(response.body)["code"], "INVALID_REQUEST")
        duplicate = self.harness.request(
            path,
            method="POST",
            headers=[
                ("Host", self.harness.authority),
                ("Content-Length", "1"),
            ],
            raw_header_lines=[b"Content-Length: 1"],
            body=b"x",
        )
        self.assertEqual(duplicate.status, 400)
        oversized = self.harness.request(
            path,
            method="POST",
            headers=[
                ("Host", self.harness.authority),
                ("Content-Length", "33554433"),
            ],
        )
        self.assertEqual(oversized.status, 413)
        self.assertEqual(json.loads(oversized.body)["code"], "UPLOAD_TOO_LARGE")
        self.assertFalse((self.workspace / "inputs").exists())

    def test_exact_transport_limit_is_read_and_accepted(self) -> None:
        content = b"x" * 33_554_432
        received = []

        def accept_at_boundary(filename, body):
            received.append((filename, len(body)))
            return Response(
                202,
                "application/json; charset=utf-8",
                b'{"job":null}',
            )

        with patch.object(
            self.harness.server.application,
            "_upload",
            side_effect=accept_at_boundary,
        ):
            response = self.request_upload("filename=limit.txt", content)
        self.assertEqual(response.status, 202)
        self.assertEqual(received, [("limit.txt", 33_554_432)])

    def test_extreme_decimal_upload_length_is_rejected_before_body_read(
        self,
    ) -> None:
        response = self.harness.request(
            "/api/observation-jobs/upload?filename=huge.txt",
            method="POST",
            headers=[
                ("Host", self.harness.authority),
                ("Content-Length", "9" * 5000),
            ],
        )
        self.assertEqual(response.status, 413)
        self.assertEqual(
            json.loads(response.body)["code"], "UPLOAD_TOO_LARGE"
        )
        self.assertFalse((self.workspace / "inputs").exists())
        self.assertIsNone(
            json.loads(
                self.harness.request("/api/observation-jobs").body
            )["job"]
        )

    def test_invalid_source_and_filename_publish_no_input_or_job(self) -> None:
        cases = (
            ("filename=bad.csv", b"value\n", "INVALID_SOURCE"),
            ("filename=nested%2Fbad.md", b"value\n", "INVALID_REQUEST"),
            ("filename=bad.md", b"\xff", "INVALID_SOURCE"),
        )
        for query, body, code in cases:
            with self.subTest(query=query):
                response = self.request_upload(query, body)
                self.assertEqual(response.status, 400)
                self.assertEqual(json.loads(response.body)["code"], code)
                self.assertIsNone(
                    json.loads(
                        self.harness.request("/api/observation-jobs").body
                    )["job"]
                )
        inputs = self.workspace / "inputs"
        self.assertEqual(list(inputs.rglob("*")) if inputs.exists() else [], [])

    def test_upload_storage_oserror_is_workspace_unavailable(self) -> None:
        with patch(
            "tiny_corpus_workbench.workbench_server.store_uploaded_input",
            side_effect=OSError("disk\nfull"),
        ):
            response = self.request_upload(
                "filename=storage-failure.md", b"# Valid\n"
            )
        self.assertEqual(response.status, 409)
        self.assertEqual(
            json.loads(response.body),
            {
                "code": "WORKSPACE_UNAVAILABLE",
                "message": "disk full",
            },
        )
        self.assertIsNone(
            json.loads(
                self.harness.request("/api/observation-jobs").body
            )["job"]
        )

    def test_uploaded_markdown_is_stored_observed_and_refreshed(self) -> None:
        content = b"# Browser upload\n\nModel-free observation.\n"
        accepted = self.request_upload("filename=browser%20memo.md", content)
        self.assertEqual(accepted.status, 202)
        queued = json.loads(accepted.body)["job"]
        self.assertEqual(queued["state"], "QUEUED")
        self.assertEqual(queued["input"]["kind"], "UPLOAD")
        terminal = self.wait_for_terminal()
        self.assertEqual(terminal["state"], "COMPLETED")
        self.assertEqual(terminal["refresh"], {"status": "READY", "message": None})
        self.assertIsNotNone(terminal["observation"]["record_key"])
        digest = terminal["input"]["sha256"]
        self.assertEqual(
            (self.workspace / "inputs" / digest / "browser memo.md").read_bytes(),
            content,
        )
        projection = json.loads(self.harness.request("/api/workbench").body)
        self.assertEqual(projection["counts"]["record_count"], 1)

    def test_guided_body_contract_and_model_free_service_path(self) -> None:
        invalid = self.harness.request(
            "/api/observation-jobs/guided/policy-memo-md",
            method="POST",
            headers=[
                ("Host", self.harness.authority),
                ("Content-Length", "1"),
            ],
            body=b"x",
        )
        self.assertEqual(invalid.status, 400)
        accepted = self.harness.request(
            "/api/observation-jobs/guided/policy-memo-md",
            method="POST",
            headers=[
                ("Host", self.harness.authority),
                ("Content-Length", "0"),
                ("Origin", "https://example.test"),
            ],
        )
        self.assertEqual(accepted.status, 202)
        self.assertNotIn("access-control-allow-origin", accepted.headers)
        terminal = self.wait_for_terminal()
        self.assertEqual(terminal["state"], "COMPLETED")
        self.assertEqual(terminal["observation"]["status"], "SUCCESS")
        self.assertFalse((self.workspace / "inputs").exists())

    def test_duplicate_guided_source_reactivates_without_starting_job(self) -> None:
        first = self.harness.request(
            "/api/observation-jobs/guided/policy-memo-md",
            method="POST",
            headers=[("Host", self.harness.authority), ("Content-Length", "0")],
        )
        self.assertEqual(first.status, 202)
        terminal = self.wait_for_terminal()
        before = self.harness.server.application.jobs.snapshot()
        with patch.object(
            self.harness.server.application.jobs,
            "accept",
            wraps=self.harness.server.application.jobs.accept,
        ) as accept:
            duplicate = self.harness.request(
                "/api/observation-jobs/guided/policy-memo-md",
                method="POST",
                headers=[
                    ("Host", self.harness.authority),
                    ("Content-Length", "0"),
                ],
            )
        payload = json.loads(duplicate.body)
        self.assertEqual(duplicate.status, 200)
        self.assertIsNone(payload["job"])
        self.assertEqual(
            payload["reactivation"]["observation_record_key"],
            terminal["observation"]["record_key"],
        )
        self.assertEqual(
            payload["reactivation"]["document_key"],
            json.loads(
                self.harness.request("/api/workbench").body
            )["documents"][0]["document_key"],
        )
        accept.assert_not_called()
        self.assertIs(self.harness.server.application.jobs.snapshot(), before)

    def test_duplicate_upload_reactivates_before_input_storage(self) -> None:
        content = b"# Same bytes\n\nOne source identity.\n"
        first = self.request_upload("filename=first.md", content)
        self.assertEqual(first.status, 202)
        terminal = self.wait_for_terminal()
        digest = terminal["input"]["sha256"]
        duplicate = self.request_upload("filename=renamed.md", content)
        payload = json.loads(duplicate.body)
        self.assertEqual(duplicate.status, 200)
        self.assertIsNone(payload["job"])
        self.assertEqual(
            payload["reactivation"]["observation_record_key"],
            terminal["observation"]["record_key"],
        )
        self.assertFalse(
            (self.workspace / "inputs" / digest / "renamed.md").exists()
        )

    def test_duplicate_reactivation_preserves_lifecycle_lease_ordering(self) -> None:
        first = self.harness.request(
            "/api/observation-jobs/guided/policy-memo-md",
            method="POST",
            headers=[("Host", self.harness.authority), ("Content-Length", "0")],
        )
        self.assertEqual(first.status, 202)
        self.wait_for_terminal()
        with self.harness.server.application.jobs.coordinator.acquire(
            "LIFECYCLE"
        ):
            duplicate = self.harness.request(
                "/api/observation-jobs/guided/policy-memo-md",
                method="POST",
                headers=[
                    ("Host", self.harness.authority),
                    ("Content-Length", "0"),
                ],
            )
        self.assertEqual(duplicate.status, 409)
        self.assertEqual(
            json.loads(duplicate.body)["code"], "OBSERVATION_BUSY"
        )

    def test_guided_ids_are_exact_and_singular_route_is_removed(self) -> None:
        application = self.harness.server.application
        with patch.object(application, "_submit", wraps=application._submit) as submit:
            unknown = self.harness.request(
                "/api/observation-jobs/guided/not-known",
                method="POST",
                headers=[("Host", self.harness.authority), ("Content-Length", "0")],
            )
            unknown_with_query = self.harness.request(
                "/api/observation-jobs/guided/not-known?extra=value",
                method="POST",
                headers=[("Host", self.harness.authority), ("Content-Length", "0")],
            )
            unknown_with_body = self.harness.request(
                "/api/observation-jobs/guided/not-known",
                method="POST",
                headers=[("Host", self.harness.authority), ("Content-Length", "1")],
                body=b"x",
            )
            removed = self.harness.request(
                "/api/observation-jobs/guided",
                method="POST",
                headers=[("Host", self.harness.authority), ("Content-Length", "0")],
            )
        self.assertEqual(unknown.status, 404)
        self.assertEqual(unknown_with_query.status, 400)
        self.assertEqual(
            json.loads(unknown_with_query.body)["code"], "INVALID_REQUEST"
        )
        self.assertEqual(unknown_with_body.status, 400)
        self.assertEqual(
            json.loads(unknown_with_body.body)["code"], "INVALID_REQUEST"
        )
        self.assertEqual(removed.status, 404)
        submit.assert_not_called()

        accepted = self.harness.request(
            "/api/observation-jobs/guided/whitespace-cleanup-md",
            method="POST",
            headers=[("Host", self.harness.authority), ("Content-Length", "0")],
        )
        self.assertEqual(accepted.status, 202)
        terminal = self.wait_for_terminal()
        self.assertEqual(terminal["input"]["name"], "whitespace-cleanup.md")
        self.assertEqual(terminal["state"], "COMPLETED")

    def test_unavailable_workspace_returns_stable_conflict(self) -> None:
        moved = self.workspace.with_name("moved-workspace")
        self.workspace.rename(moved)
        self.workspace.write_text("not a directory", "utf-8")
        try:
            response = self.harness.request(
                "/api/observation-jobs/guided/policy-memo-md",
                method="POST",
                headers=[
                    ("Host", self.harness.authority),
                    ("Content-Length", "0"),
                ],
            )
        finally:
            self.workspace.unlink()
            moved.rename(self.workspace)
        self.assertEqual(response.status, 409)
        self.assertEqual(
            json.loads(response.body)["code"], "WORKSPACE_UNAVAILABLE"
        )

    def test_busy_upload_is_rejected_without_reading_or_storing(self) -> None:
        release = __import__("threading").Event()
        original = self.harness.server.application.jobs._observe

        def blocked(*arguments):
            release.wait(5)
            return original(*arguments)

        with patch.object(
            self.harness.server.application.jobs, "_observe", side_effect=blocked
        ):
            accepted = self.harness.request(
                "/api/observation-jobs/guided/policy-memo-md",
                method="POST",
                headers=[
                    ("Host", self.harness.authority),
                    ("Content-Length", "0"),
                ],
            )
            self.assertEqual(accepted.status, 202)
            deadline = time.monotonic() + 2
            while time.monotonic() < deadline:
                job = self.harness.server.application.jobs.snapshot()
                if job is not None and job.state == "RUNNING":
                    break
                time.sleep(0.01)
            busy = self.request_upload("filename=busy.md", b"# Busy\n")
            self.assertEqual(busy.status, 409)
            self.assertEqual(json.loads(busy.body)["code"], "OBSERVATION_BUSY")
            self.assertFalse((self.workspace / "inputs").exists())
            duplicate = self.harness.request(
                "/api/observation-jobs/guided/policy-memo-md",
                method="POST",
                headers=[
                    ("Host", self.harness.authority),
                    ("Content-Length", "0"),
                ],
            )
            self.assertEqual(duplicate.status, 409)
            self.assertEqual(
                json.loads(duplicate.body)["code"], "OBSERVATION_BUSY"
            )
            release.set()
            self.wait_for_terminal()


if __name__ == "__main__":
    unittest.main()
