from __future__ import annotations

import json
import unittest

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

    def test_json_routes_serve_the_canonical_projection_and_detail(self) -> None:
        response = self.harness.request("/api/workbench")
        self.assertEqual(response.body, self.harness.projection.projection_bytes())
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
