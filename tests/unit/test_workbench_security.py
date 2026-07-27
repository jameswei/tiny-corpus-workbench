from __future__ import annotations

import json
import unittest

from tests.unit.workbench_server_test_support import ServerHarness
from tests.unit.workbench_test_support import PublishedObservation


class WorkbenchSecurityTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.published = PublishedObservation()
        cls.harness = ServerHarness(cls.published.root)

    @classmethod
    def tearDownClass(cls) -> None:
        cls.harness.close()
        cls.published.close()

    def assert_error(self, response, status: int, code: str) -> None:
        self.assertEqual(response.status, status)
        self.assertEqual(json.loads(response.body)["error"]["code"], code)
        self.assertNotIn("traceback", response.body.decode().lower())
        self.assertNotIn(str(self.published.root), response.body.decode())

    def test_targets_queries_decoding_and_traversal_fail_closed(self) -> None:
        cases = (
            ("/?x=1", 400, "BAD_REQUEST"),
            ("/#x", 400, "BAD_REQUEST"),
            ("/%2e%2e/manifest.json", 400, "BAD_REQUEST"),
            ("/%252e%252e/manifest.json", 400, "BAD_REQUEST"),
            ("/a%5cb", 400, "BAD_REQUEST"),
            ("/%61ssets/workbench.css", 400, "BAD_REQUEST"),
            ("/a%00b", 400, "BAD_REQUEST"),
            ("/" + "a" * 8192, 413, "REQUEST_TOO_LARGE"),
        )
        for target, status, code in cases:
            with self.subTest(target=target[:40]):
                self.assert_error(self.harness.request(target), status, code)

    def test_proxy_transfer_body_and_methods_follow_closed_errors(self) -> None:
        authority = self.harness.authority
        cases = (
            (
                [("Host", authority), ("Forwarded", "host=evil")],
                "GET",
                400,
                "BAD_REQUEST",
            ),
            (
                [("Host", authority), ("X-Forwarded-Host", authority)],
                "GET",
                400,
                "BAD_REQUEST",
            ),
            (
                [("Host", authority), ("Transfer-Encoding", "chunked")],
                "POST",
                400,
                "BAD_REQUEST",
            ),
            (
                [("Host", authority), ("Content-Length", "x")],
                "GET",
                400,
                "BAD_REQUEST",
            ),
            (
                [("Host", authority), ("Content-Length", "1")],
                "GET",
                413,
                "REQUEST_TOO_LARGE",
            ),
            (
                [("Host", authority), ("Content-Length", "0")],
                "OPTIONS",
                405,
                "METHOD_NOT_ALLOWED",
            ),
            ([("Host", authority)], "TRACE", 405, "METHOD_NOT_ALLOWED"),
        )
        for headers, method, status, code in cases:
            with self.subTest(method=method, code=code):
                response = self.harness.request(
                    "/unknown", method=method, headers=headers
                )
                self.assert_error(response, status, code)
                if status == 405:
                    self.assertEqual(response.headers["allow"], "GET, HEAD")

    def test_every_response_has_security_headers_and_no_cors(self) -> None:
        for target in ("/", "/unknown"):
            response = self.harness.request(target)
            self.assertEqual(response.headers["cache-control"], "no-store")
            self.assertEqual(response.headers["x-content-type-options"], "nosniff")
            self.assertEqual(response.headers["referrer-policy"], "no-referrer")
            self.assertEqual(
                response.headers["cross-origin-resource-policy"], "same-origin"
            )
            self.assertEqual(response.headers["x-frame-options"], "DENY")
            self.assertIn(
                "default-src 'self'", response.headers["content-security-policy"]
            )
            self.assertNotIn("access-control-allow-origin", response.headers)

    def test_header_count_limit_precedes_body_and_method(self) -> None:
        headers = [("Host", self.harness.authority)]
        headers.extend((f"X-Test-{index}", "x") for index in range(32))
        headers.append(("Content-Length", "1"))
        response = self.harness.request(
            "/unknown", method="POST", headers=headers
        )
        self.assert_error(response, 413, "REQUEST_TOO_LARGE")

    def test_malformed_field_and_obsolete_folding_are_rejected(self) -> None:
        malformed = self.harness.request(
            raw_header_lines=[b"not-a-header-field"]
        )
        folded = self.harness.request(
            raw_header_lines=[b"X-Test: first", b" second"]
        )
        self.assert_error(malformed, 400, "BAD_REQUEST")
        self.assert_error(folded, 400, "BAD_REQUEST")


if __name__ == "__main__":
    unittest.main()
