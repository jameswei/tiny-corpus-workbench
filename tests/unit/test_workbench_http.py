from __future__ import annotations

import json
import socket
import unittest
from unittest.mock import patch

from tests.unit.workbench_server_test_support import ServerHarness
from tests.unit.workbench_test_support import PublishedObservation


class WorkbenchHttpTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.published = PublishedObservation()
        cls.harness = ServerHarness(cls.published.root)

    @classmethod
    def tearDownClass(cls) -> None:
        cls.harness.close()
        cls.published.close()

    def test_every_static_and_api_route_has_exact_head_parity(self) -> None:
        projection = self.harness.projection.projection
        record_key = projection["records"][0]["record_key"]
        detail = self.harness.projection.details[record_key]
        artifact_key = detail["artifacts"][0]["artifact_key"]
        routes = (
            "/",
            "/assets/workbench.css",
            "/assets/workbench.js",
            "/api/workbench",
            f"/api/records/{record_key}",
            f"/api/artifacts/{artifact_key}",
        )
        for route in routes:
            with self.subTest(route=route):
                get = self.harness.request(route)
                head = self.harness.request(route, method="HEAD")
                self.assertEqual(get.status, 200)
                self.assertEqual(head.status, get.status)
                self.assertEqual(
                    head.headers["content-type"], get.headers["content-type"]
                )
                self.assertEqual(
                    head.headers["content-length"], get.headers["content-length"]
                )
                self.assertEqual(head.body, b"")
                self.assertEqual(len(get.body), int(get.headers["content-length"]))

    def test_each_response_releases_sequential_server_for_next_connection(
        self,
    ) -> None:
        def response_from(client: socket.socket, target: str) -> tuple[bytes, bytes]:
            client.sendall(
                (
                    f"GET {target} HTTP/1.1\r\n"
                    f"Host: {self.harness.authority}\r\n"
                    "\r\n"
                ).encode("ascii")
            )
            received = b""
            while b"\r\n\r\n" not in received:
                received += client.recv(4096)
            header, _, initial_body = received.partition(b"\r\n\r\n")
            length_line = next(
                line
                for line in header.split(b"\r\n")
                if line.lower().startswith(b"content-length:")
            )
            length = int(length_line.split(b":", 1)[1])
            body = initial_body
            while len(body) < length:
                body += client.recv(length - len(body))
            return header, body

        with socket.create_connection(
            ("127.0.0.1", self.harness.port), timeout=1
        ) as first:
            first.settimeout(1)
            first_header, first_body = response_from(first, "/")
            self.assertIn(b"\r\nConnection: close\r\n", b"\r\n" + first_header + b"\r\n")
            self.assertTrue(first_body)
            with socket.create_connection(
                ("127.0.0.1", self.harness.port), timeout=1
            ) as second:
                second.settimeout(1)
                second_header, second_body = response_from(
                    second, "/assets/workbench.js"
                )
        self.assertIn(b" 200 ", second_header.split(b"\r\n", 1)[0])
        self.assertTrue(second_body)

    def test_json_routes_serve_the_canonical_projection_and_detail(self) -> None:
        response = self.harness.request("/api/workbench")
        self.assertEqual(response.body, self.harness.state.projection_bytes())
        record_key = self.harness.projection.projection["records"][0]["record_key"]
        detail = self.harness.request(f"/api/records/{record_key}")
        self.assertEqual(
            detail.body, self.harness.projection.detail_bytes(record_key)
        )

    def test_unknown_malformed_and_absent_keys_return_stable_404(self) -> None:
        for target in (
            "/unknown",
            "/api/records/" + "a" * 64,
            "/api/records/" + "A" * 64,
            "/api/artifacts/not-a-key",
        ):
            with self.subTest(target=target):
                response = self.harness.request(target)
                self.assertEqual(response.status, 404)
                self.assertEqual(
                    json.loads(response.body),
                    {
                        "code": "NOT_FOUND",
                        "message": "resource was not found",
                    },
                )

    def test_non_read_methods_return_405_and_allow_header(self) -> None:
        for method in ("POST", "PUT", "PATCH", "DELETE", "OPTIONS"):
            with self.subTest(method=method):
                response = self.harness.request("/", method=method)
                self.assertEqual(response.status, 405)
                self.assertEqual(response.headers["allow"], "GET, HEAD")
                self.assertEqual(
                    json.loads(response.body)["code"], "METHOD_NOT_ALLOWED"
                )

    def test_refresh_method_contract_and_success(self) -> None:
        for method in ("GET", "HEAD", "PUT", "PATCH", "DELETE", "OPTIONS"):
            with self.subTest(method=method):
                response = self.harness.request(
                    "/api/workbench/refresh", method=method
                )
                self.assertEqual(response.status, 405)
                self.assertEqual(response.headers["allow"], "POST")
                if method == "HEAD":
                    self.assertEqual(response.body, b"")
        response = self.harness.request(
            "/api/workbench/refresh",
            method="POST",
            headers=[("Host", self.harness.authority), ("Content-Length", "0")],
        )
        self.assertEqual(response.status, 204)
        self.assertEqual(response.body, b"")

    def test_refresh_rejects_nonempty_body(self) -> None:
        response = self.harness.request(
            "/api/workbench/refresh",
            method="POST",
            headers=[("Host", self.harness.authority), ("Content-Length", "1")],
            body=b"x",
        )
        self.assertEqual(response.status, 400)
        self.assertEqual(json.loads(response.body)["code"], "INVALID_REQUEST")

    def test_refresh_rejects_invalid_framing_without_invoking_refresh(self) -> None:
        cases = (
            (
                "negative",
                [("Host", self.harness.authority), ("Content-Length", "-1")],
                [],
                b"",
            ),
            (
                "malformed",
                [("Host", self.harness.authority), ("Content-Length", "nope")],
                [],
                b"",
            ),
            (
                "duplicate",
                [("Host", self.harness.authority), ("Content-Length", "0")],
                [b"Content-Length: 0"],
                b"",
            ),
            (
                "transfer-encoding",
                [("Host", self.harness.authority), ("Transfer-Encoding", "chunked")],
                [],
                b"0\r\n\r\n",
            ),
        )
        for name, headers, raw_headers, body in cases:
            with self.subTest(name=name), patch.object(
                self.harness.state, "refresh", wraps=self.harness.state.refresh
            ) as refresh:
                response = self.harness.request(
                    "/api/workbench/refresh",
                    method="POST",
                    headers=headers,
                    raw_header_lines=raw_headers,
                    body=body,
                )
                self.assertEqual(response.status, 400)
                self.assertEqual(
                    json.loads(response.body)["code"], "INVALID_REQUEST"
                )
                refresh.assert_not_called()

    def test_refresh_accepts_absent_content_length(self) -> None:
        with patch.object(
            self.harness.state, "refresh", wraps=self.harness.state.refresh
        ) as refresh:
            response = self.harness.request(
                "/api/workbench/refresh",
                method="POST",
                headers=[("Host", self.harness.authority)],
            )
        self.assertEqual(response.status, 204)
        refresh.assert_called_once_with()

    def test_failed_refresh_returns_409_and_preserves_snapshot(self) -> None:
        old_projection = self.harness.state.projection
        record = next(iter(self.harness.records.records.values()))
        target = record.backing.root / record.manifest_name
        original = target.read_bytes()
        try:
            target.write_bytes(b"tampered")
            response = self.harness.request(
                "/api/workbench/refresh",
                method="POST",
                headers=[("Host", self.harness.authority), ("Content-Length", "0")],
            )
            catalog = json.loads(
                self.harness.request("/api/workbench").body
            )
        finally:
            target.write_bytes(original)
        self.assertEqual(response.status, 409)
        self.assertEqual(
            json.loads(response.body)["code"], "WORKSPACE_REFRESH_FAILED"
        )
        self.assertIs(self.harness.state.projection, old_projection)
        self.assertEqual(catalog["refresh"]["status"], "FAILED")
        self.assertTrue(self.harness.state.refresh().succeeded)

    def test_post_startup_file_change_does_not_change_served_bytes(self) -> None:
        detail = next(iter(self.harness.projection.details.values()))
        descriptor = detail["artifacts"][0]
        captured = self.harness.projection.artifact_contents[
            descriptor["artifact_key"]
        ]
        record = next(iter(self.harness.records.records.values()))
        target = record.backing.root / record.manifest_name
        original = target.read_bytes()
        try:
            target.write_bytes(b"replacement bytes")
            response = self.harness.request(
                f"/api/artifacts/{descriptor['artifact_key']}"
            )
        finally:
            target.write_bytes(original)
        self.assertEqual(response.status, 200)
        self.assertEqual(response.body, captured)


if __name__ == "__main__":
    unittest.main()
