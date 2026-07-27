from __future__ import annotations

import json
import unittest

from tests.unit.workbench_server_test_support import ServerHarness
from tests.unit.workbench_test_support import PublishedObservation


class WorkbenchAuthorityHeaderTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.published = PublishedObservation()
        cls.harness = ServerHarness(cls.published.root)

    @classmethod
    def tearDownClass(cls) -> None:
        cls.harness.close()
        cls.published.close()

    def code(self, response) -> str:
        return json.loads(response.body)["error"]["code"]

    def test_host_cardinality_and_exact_value_variants(self) -> None:
        port = self.harness.port
        invalid = (
            f"localhost:{port}",
            f"[::1]:{port}",
            f"127.0.0.1.:{port}",
            "127.0.0.1",
            f"127.0.0.1:{port + 1}",
            f"127.0.0.1 :{port}",
            f"127.0.0.1: {port}",
            f"127.0.0.1:{port},evil",
            f"127.0.0.1:{port}, 127.0.0.1:{port}",
        )
        missing = self.harness.request(headers=[])
        duplicate = self.harness.request(
            headers=[("Host", self.harness.authority), ("host", self.harness.authority)]
        )
        outer_ows = self.harness.request(
            headers=[("Host", f"\t{self.harness.authority}\t")]
        )
        self.assertEqual((missing.status, self.code(missing)), (400, "BAD_REQUEST"))
        self.assertEqual((duplicate.status, self.code(duplicate)), (400, "BAD_REQUEST"))
        self.assertEqual(outer_ows.status, 200)
        for value in invalid:
            with self.subTest(value=value):
                response = self.harness.request(headers=[("Host", value)])
                self.assertEqual(
                    (response.status, self.code(response)),
                    (403, "HOST_REJECTED"),
                )

    def test_origin_cardinality_and_exact_value_variants(self) -> None:
        valid = self.harness.request(
            headers=[("Host", self.harness.authority), ("Origin", self.harness.origin)]
        )
        self.assertEqual(valid.status, 200)
        invalid = (
            self.harness.origin.upper(),
            self.harness.origin.replace("127.0.0.1", "localhost"),
            self.harness.origin.replace("127.0.0.1", "[::1]"),
            self.harness.origin.replace("127.0.0.1", "127.0.0.1."),
            self.harness.origin.rsplit(":", 1)[0],
            self.harness.origin + ", http://evil.invalid",
            self.harness.origin.replace(":", ": ", 1),
        )
        duplicate = self.harness.request(
            headers=[
                ("Host", self.harness.authority),
                ("Origin", self.harness.origin),
                ("origin", self.harness.origin),
            ]
        )
        self.assertEqual((duplicate.status, self.code(duplicate)), (400, "BAD_REQUEST"))
        for value in invalid:
            with self.subTest(value=value):
                response = self.harness.request(
                    headers=[("Host", self.harness.authority), ("Origin", value)]
                )
                self.assertEqual(
                    (response.status, self.code(response)), (403, "ORIGIN_REJECTED")
                )

    def test_proxy_values_never_supply_or_change_authority(self) -> None:
        response = self.harness.request(
            headers=[("Forwarded", f"host={self.harness.authority}")]
        )
        self.assertEqual((response.status, self.code(response)), (400, "BAD_REQUEST"))
        response = self.harness.request(
            headers=[
                ("Host", "evil.invalid"),
                ("X-Forwarded-Host", self.harness.authority),
            ]
        )
        self.assertEqual((response.status, self.code(response)), (403, "HOST_REJECTED"))

    def test_authority_precedes_route_method_and_body_across_surfaces(self) -> None:
        record_key = self.harness.projection.projection["records"][0]["record_key"]
        contexts = (
            ("/", "GET", []),
            ("/assets/workbench.css", "HEAD", []),
            ("/api/v0.5/workbench", "GET", []),
            (f"/api/v0.5/records/{record_key}", "HEAD", []),
            ("/unknown", "GET", []),
            ("/unknown", "POST", []),
            ("/unknown", "OPTIONS", []),
            ("/unknown", "POST", [("Content-Length", "1")]),
        )
        for target, method, later_headers in contexts:
            with self.subTest(target=target, method=method):
                missing = self.harness.request(
                    target, method=method, headers=later_headers
                )
                wrong = self.harness.request(
                    target,
                    method=method,
                    headers=[("Host", "evil.invalid"), *later_headers],
                )
                self.assertEqual(missing.status, 400)
                self.assertEqual(wrong.status, 403)
                if method == "HEAD":
                    self.assertEqual(missing.body, b"")
                    self.assertEqual(wrong.body, b"")
                    self.assertEqual(
                        missing.headers["content-type"],
                        "application/json; charset=utf-8",
                    )
                else:
                    self.assertEqual(self.code(missing), "BAD_REQUEST")
                    self.assertEqual(self.code(wrong), "HOST_REJECTED")

    def test_combined_invalid_precedence_table(self) -> None:
        authority = self.harness.authority
        origin = self.harness.origin
        cases = (
            (
                [
                    ("Host", authority),
                    ("Host", "evil"),
                    ("Origin", "evil"),
                    ("Content-Length", "1"),
                ],
                "/%zz",
                "POST",
                "BAD_REQUEST",
            ),
            (
                [("Host", "evil"), ("Origin", origin), ("Origin", origin)],
                "/",
                "GET",
                "HOST_REJECTED",
            ),
            (
                [("Host", authority), ("Origin", origin), ("Origin", "evil")],
                "/" + "x" * 8192,
                "GET",
                "BAD_REQUEST",
            ),
            (
                [
                    ("Host", authority),
                    ("Origin", "evil"),
                    ("Transfer-Encoding", "chunked"),
                ],
                "/",
                "GET",
                "ORIGIN_REJECTED",
            ),
            (
                [("Host", authority), ("Transfer-Encoding", "chunked")],
                "/%zz",
                "POST",
                "BAD_REQUEST",
            ),
            (
                [
                    ("Host", authority),
                    ("Transfer-Encoding", "chunked"),
                    ("Content-Length", "1"),
                ],
                "/",
                "POST",
                "BAD_REQUEST",
            ),
            (
                [("Host", authority), ("Content-Length", "1")],
                "/unknown",
                "POST",
                "REQUEST_TOO_LARGE",
            ),
            (
                [("Host", authority)],
                "/unknown",
                "POST",
                "METHOD_NOT_ALLOWED",
            ),
        )
        for headers, target, method, expected in cases:
            with self.subTest(expected=expected):
                response = self.harness.request(
                    target, method=method, headers=headers
                )
                self.assertEqual(self.code(response), expected)


if __name__ == "__main__":
    unittest.main()
