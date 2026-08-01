from __future__ import annotations

import json
import shutil
import socket
import tempfile
import threading
import time
import unittest
from pathlib import Path
from unittest.mock import patch

from tiny_corpus_workbench.application.lifecycle import (
    ActionNotAvailableError,
    LifecycleBusyError,
    LifecycleNotFoundError,
    ResponseTooLargeError,
)
from tiny_corpus_workbench.application.workbench import (
    RefreshResult,
    WorkspaceStaleError,
)
from tiny_corpus_workbench.canonical_json import canonical_json
from tests.unit.workbench_server_test_support import ServerHarness
from tests.unit.workbench_test_support import PublishedRefinements


class WorkbenchLifecycleHttpTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.published = PublishedRefinements()

    @classmethod
    def tearDownClass(cls) -> None:
        cls.published.close()

    def setUp(self) -> None:
        self.temporary = tempfile.TemporaryDirectory()
        self.workspace = Path(self.temporary.name) / "workspace"
        for source, family, label in (
            (
                self.published.observation,
                "extraction-observatory",
                "observation",
            ),
            (
                self.published.diagnosis,
                "evidence-based-diagnosis",
                "diagnosis",
            ),
        ):
            target = self.workspace / family / label / source.name
            target.parent.mkdir(parents=True, exist_ok=True)
            shutil.copytree(source, target)
        self.harness = ServerHarness(workspace=self.workspace)
        records = self.harness.state.projection.projection["records"]
        self.observation_key = next(
            item["record_key"] for item in records if item["kind"] == "OBSERVATION"
        )
        self.diagnosis_key = next(
            item["record_key"] for item in records if item["kind"] == "DIAGNOSIS"
        )
        findings = self.harness.state.projection.details[self.diagnosis_key]["view"][
            "findings"
        ]
        self.finding_id = next(
            item["finding_id"] for item in findings if item["rule_id"] == "D009"
        )
        self.token = json.loads(
            self.harness.request("/api/lifecycle/action-token").body
        )["action_token"]

    def tearDown(self) -> None:
        self.harness.close()
        self.temporary.cleanup()

    def post(self, target: str, *, token: str | None = None, **kwargs):
        headers = [("Host", self.harness.authority), ("Content-Length", "0")]
        if token is not None:
            headers.append(("X-TCW-Action-Token", token))
        return self.harness.request(
            target, method="POST", headers=headers, **kwargs
        )

    def test_one_coordinator_is_shared_by_observation_and_lifecycle(self) -> None:
        application = self.harness.server.application
        self.assertIs(application.jobs.coordinator, application.lifecycle.coordinator)

    def test_token_get_head_headers_and_restart_invalidation(self) -> None:
        get = self.harness.request("/api/lifecycle/action-token")
        head = self.harness.request("/api/lifecycle/action-token", method="HEAD")
        self.assertEqual(get.status, 200)
        self.assertEqual(get.body, canonical_json({"action_token": self.token}))
        self.assertEqual(head.status, 200)
        self.assertEqual(head.body, b"")
        self.assertEqual(head.headers["content-length"], get.headers["content-length"])
        self.assertEqual(head.headers["cache-control"], "no-store")
        self.assertEqual(get.headers["cache-control"], "no-store")
        self.assertNotIn("access-control-allow-origin", get.headers)
        wrong_method = self.post("/api/lifecycle/action-token")
        self.assertEqual(wrong_method.status, 405)
        self.assertEqual(wrong_method.headers["allow"], "GET, HEAD")

        restarted = ServerHarness(workspace=self.workspace)
        try:
            with patch.object(
                restarted.server.application.lifecycle, "diagnose"
            ) as call:
                response = restarted.request(
                    f"/api/lifecycle/diagnoses/{self.observation_key}",
                    method="POST",
                    headers=[
                        ("Host", restarted.authority),
                        ("Content-Length", "0"),
                        ("X-TCW-Action-Token", self.token),
                    ],
                )
            self.assertEqual(response.status, 403)
            self.assertEqual(json.loads(response.body)["code"], "ACTION_TOKEN_INVALID")
            call.assert_not_called()
        finally:
            restarted.close()

    def test_route_method_framing_and_token_precedence(self) -> None:
        target = f"/api/lifecycle/diagnoses/{self.observation_key}"
        wrong_method = self.harness.request(target)
        self.assertEqual(wrong_method.status, 405)
        self.assertEqual(wrong_method.headers["allow"], "POST")

        malformed = (
            target + "?x=1",
            target + "/extra",
            "/api/lifecycle/diagnoses/" + self.observation_key.upper(),
        )
        for value in malformed:
            with self.subTest(value=value):
                response = self.post(value, token=self.token)
                self.assertEqual(response.status, 404)

        with patch.object(
            self.harness.server.application.lifecycle, "diagnose"
        ) as call:
            framing_cases = (
                (
                    [("Content-Length", "1"), ("X-TCW-Action-Token", "wrong")],
                    [],
                    b"x",
                ),
                (
                    [("Content-Length", "0"), ("X-TCW-Action-Token", "wrong")],
                    [b"Content-Length: 0"],
                    b"",
                ),
                (
                    [("Transfer-Encoding", "chunked"), ("X-TCW-Action-Token", "wrong")],
                    [],
                    b"0\r\n\r\n",
                ),
            )
            for fields, raw, body in framing_cases:
                invalid_framing = self.harness.request(
                    target,
                    method="POST",
                    headers=[("Host", self.harness.authority), *fields],
                    raw_header_lines=raw,
                    body=body,
                )
                self.assertEqual(invalid_framing.status, 400)
                self.assertEqual(
                    json.loads(invalid_framing.body)["code"], "INVALID_REQUEST"
                )

            token_cases = (
                ([], []),
                ([("X-TCW-Action-Token", "wrong")], []),
                (
                    [("X-TCW-Action-Token", self.token)],
                    [f"X-TCW-Action-Token: {self.token}".encode("ascii")],
                ),
            )
            for fields, raw in token_cases:
                response = self.harness.request(
                    target,
                    method="POST",
                    headers=[
                        ("Host", self.harness.authority),
                        ("Content-Length", "0"),
                        *fields,
                    ],
                    raw_header_lines=raw,
                )
                self.assertEqual(response.status, 403)
                self.assertEqual(
                    json.loads(response.body)["code"], "ACTION_TOKEN_INVALID"
                )
            call.assert_not_called()

    def test_non_ascii_token_is_forbidden_without_service_call(self) -> None:
        target = f"/api/lifecycle/diagnoses/{self.observation_key}"
        with patch.object(
            self.harness.server.application.lifecycle, "diagnose"
        ) as call:
            response = self.harness.request(
                target,
                method="POST",
                headers=[
                    ("Host", self.harness.authority),
                    ("Content-Length", "0"),
                    ("X-TCW-Action-Token", "é"),
                ],
            )
        self.assertEqual(response.status, 403)
        self.assertEqual(json.loads(response.body)["code"], "ACTION_TOKEN_INVALID")
        call.assert_not_called()

    def test_unsupported_methods_use_the_exact_route_classifier(self) -> None:
        known_action = self.harness.request(
            f"/api/lifecycle/diagnoses/{self.observation_key}", method="TRACE"
        )
        token_route = self.harness.request(
            "/api/lifecycle/action-token", method="TRACE"
        )
        malformed = self.harness.request(
            "/api/lifecycle/diagnoses/not-a-key", method="TRACE"
        )
        self.assertEqual(known_action.status, 405)
        self.assertEqual(known_action.headers["allow"], "POST")
        self.assertEqual(token_route.status, 405)
        self.assertEqual(token_route.headers["allow"], "GET, HEAD")
        self.assertEqual(malformed.status, 404)
        self.assertEqual(json.loads(malformed.body)["code"], "NOT_FOUND")

        with socket.create_connection(
            ("127.0.0.1", self.harness.port), timeout=2
        ) as client:
            client.sendall(
                b"GET /api/lifecycle/action-token HTTP/9.9\r\n"
                + f"Host: {self.harness.authority}\r\n\r\n".encode("ascii")
            )
            parser_error = client.recv(4096)
        self.assertIn(b" 505 ", parser_error.split(b"\r\n", 1)[0])

    def test_lifecycle_namespace_root_is_always_malformed(self) -> None:
        application = self.harness.server.application
        direct = application.route("/api/lifecycle", method="POST")
        with (
            patch.object(application.lifecycle, "diagnose") as diagnose,
            patch.object(application.lifecycle, "create_proposal") as proposal,
            patch.object(application.lifecycle, "approve") as approve,
            patch.object(application.lifecycle, "reject") as reject,
        ):
            post = self.harness.request(
                "/api/lifecycle",
                method="POST",
                headers=[
                    ("Host", self.harness.authority),
                    ("Content-Length", "0"),
                    ("X-TCW-Action-Token", self.token),
                ],
            )
            trace = self.harness.request("/api/lifecycle", method="TRACE")

        for response in (direct, post, trace):
            self.assertEqual(response.status, 404)
            self.assertEqual(json.loads(response.body)["code"], "NOT_FOUND")
            if isinstance(response.headers, dict):
                self.assertNotIn("allow", response.headers)
            else:
                self.assertFalse(
                    any(name.lower() == "allow" for name, _ in response.headers)
                )
        diagnose.assert_not_called()
        proposal.assert_not_called()
        approve.assert_not_called()
        reject.assert_not_called()

    def test_unknown_and_ineligible_live_keys_keep_distinct_errors(self) -> None:
        unknown = self.post(
            "/api/lifecycle/diagnoses/" + "a" * 64, token=self.token
        )
        ineligible = self.post(
            f"/api/lifecycle/diagnoses/{self.diagnosis_key}", token=self.token
        )
        absent_finding = self.post(
            f"/api/lifecycle/proposals/{self.diagnosis_key}/" + "a" * 64,
            token=self.token,
        )
        self.assertEqual(
            (unknown.status, json.loads(unknown.body)["code"]),
            (404, "NOT_FOUND"),
        )
        self.assertEqual(
            (ineligible.status, json.loads(ineligible.body)["code"]),
            (409, "ACTION_NOT_AVAILABLE"),
        )
        self.assertEqual(
            (absent_finding.status, json.loads(absent_finding.body)["code"]),
            (409, "ACTION_NOT_AVAILABLE"),
        )

    def test_real_proposal_and_resolution_have_canonical_http_parity(self) -> None:
        proposal_target = (
            f"/api/lifecycle/proposals/{self.diagnosis_key}/{self.finding_id}"
        )
        direct = self.harness.server.application.route(
            proposal_target,
            method="POST",
            action_tokens=(self.token,),
        )
        http = self.post(proposal_target, token=self.token)
        self.assertEqual(http.status, 200)
        self.assertEqual(http.body, direct.body)
        draft = json.loads(http.body)["draft"]
        self.assertEqual(draft["diagnosis_record_key"], self.diagnosis_key)
        resolved = self.post(
            f"/api/lifecycle/proposals/{draft['draft_key']}/reject",
            token=self.token,
        )
        self.assertEqual(resolved.status, 200)
        payload = json.loads(resolved.body)
        self.assertEqual(payload["publication"]["decision"], "REJECTED")
        self.assertIsNone(payload["publication"]["revision_id"])
        self.assertEqual(payload["refresh"], {"status": "READY", "message": None})
        approved = self.post(
            f"/api/lifecycle/proposals/{draft['draft_key']}/approve",
            token=self.token,
        )
        self.assertEqual(approved.status, 200)
        self.assertEqual(
            json.loads(approved.body)["publication"]["decision"], "APPROVED"
        )

    def test_lifecycle_errors_map_to_stable_statuses(self) -> None:
        target = f"/api/lifecycle/diagnoses/{self.observation_key}"
        cases = (
            (LifecycleBusyError("busy\nnow"), 409, "LIFECYCLE_BUSY"),
            (ActionNotAvailableError("not available"), 409, "ACTION_NOT_AVAILABLE"),
            (LifecycleNotFoundError("not found"), 404, "NOT_FOUND"),
            (WorkspaceStaleError("stale"), 409, "WORKSPACE_STALE"),
            (ResponseTooLargeError("large"), 413, "RESPONSE_TOO_LARGE"),
        )
        for error, status, code in cases:
            with self.subTest(code=code), patch.object(
                self.harness.server.application.lifecycle,
                "diagnose",
                side_effect=error,
            ):
                response = self.post(target, token=self.token)
                self.assertEqual(response.status, status)
                self.assertEqual(json.loads(response.body)["code"], code)
                self.assertNotIn("\n", json.loads(response.body)["message"])

        with patch.object(
            self.harness.server.application.lifecycle,
            "diagnose",
            return_value={"oversized": "x" * (4 * 1024 * 1024)},
        ):
            oversized = self.post(target, token=self.token)
        self.assertEqual(oversized.status, 413)
        self.assertEqual(json.loads(oversized.body)["code"], "RESPONSE_TOO_LARGE")

    def test_publication_with_failed_refresh_is_still_success(self) -> None:
        target = f"/api/lifecycle/diagnoses/{self.observation_key}"
        with patch.object(
            self.harness.state,
            "refresh",
            return_value=RefreshResult(False, "admission failed"),
        ):
            response = self.post(target, token=self.token)
        self.assertEqual(response.status, 200)
        payload = json.loads(response.body)
        self.assertEqual(payload["publication"]["kind"], "DIAGNOSIS")
        self.assertIsNone(payload["publication"]["record_key"])
        self.assertEqual(
            payload["refresh"], {"status": "FAILED", "message": "admission failed"}
        )

    def test_observation_ownership_rejects_lifecycle_as_busy(self) -> None:
        release = threading.Event()
        original = self.harness.server.application.jobs._observe

        def blocked(*arguments):
            release.wait(5)
            return original(*arguments)

        with patch.object(
            self.harness.server.application.jobs, "_observe", side_effect=blocked
        ):
            accepted = self.post(
                "/api/observation-jobs/guided/whitespace-cleanup-md"
            )
            self.assertEqual(accepted.status, 202)
            deadline = time.monotonic() + 2
            while time.monotonic() < deadline:
                job = self.harness.server.application.jobs.snapshot()
                if job is not None and job.state == "RUNNING":
                    break
                time.sleep(0.01)
            busy = self.post(
                f"/api/lifecycle/diagnoses/{self.observation_key}", token=self.token
            )
            self.assertEqual(busy.status, 409)
            self.assertEqual(json.loads(busy.body)["code"], "LIFECYCLE_BUSY")
            release.set()

    def test_slow_lifecycle_blocks_then_later_request_reads_current_state(
        self,
    ) -> None:
        entered = threading.Event()
        release = threading.Event()
        current = threading.Event()
        first_result = []
        second_result = []

        def slow_diagnose(_key):
            entered.set()
            release.wait(5)
            current.set()
            return {
                "publication": {
                    "kind": "DIAGNOSIS",
                    "run_id": "run",
                    "record_key": None,
                },
                "refresh": {"status": "FAILED", "message": "test"},
            }

        def projection_bytes():
            return canonical_json({"phase": "after" if current.is_set() else "before"})

        with (
            patch.object(
                self.harness.server.application.lifecycle,
                "diagnose",
                side_effect=slow_diagnose,
            ),
            patch.object(
                self.harness.state,
                "projection_bytes",
                side_effect=projection_bytes,
            ),
        ):
            first = threading.Thread(
                target=lambda: first_result.append(
                    self.post(
                        f"/api/lifecycle/diagnoses/{self.observation_key}",
                        token=self.token,
                    )
                )
            )
            first.start()
            self.assertTrue(entered.wait(2))
            second = threading.Thread(
                target=lambda: second_result.append(
                    self.harness.request("/api/workbench")
                )
            )
            second.start()
            time.sleep(0.1)
            self.assertEqual(second_result, [])
            release.set()
            first.join(2)
            second.join(2)

        self.assertEqual(first_result[0].status, 200)
        self.assertEqual(json.loads(second_result[0].body), {"phase": "after"})


if __name__ == "__main__":
    unittest.main()
