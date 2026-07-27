from __future__ import annotations

import json
import shutil
import unittest
from pathlib import Path
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
        artifact_key = detail["manifest"]["artifact_key"]
        routes = (
            "/",
            "/assets/workbench.css",
            "/assets/workbench.js",
            "/api/v0.5/workbench",
            f"/api/v0.5/records/{record_key}",
            f"/api/v0.5/artifacts/{artifact_key}",
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

    def test_json_routes_serve_the_frozen_canonical_projection(self) -> None:
        response = self.harness.request("/api/v0.5/workbench")
        self.assertEqual(response.body, self.harness.projection.projection_bytes())
        self.assertEqual(
            json.loads(response.body)["projection_role"], "DERIVED_READ_ONLY"
        )

    def test_unknown_and_bad_keys_use_the_closed_error(self) -> None:
        for target in (
            "/unknown",
            "/api/v0.5/records/" + "a" * 64,
            "/api/v0.5/records/" + "A" * 64,
            "/api/v0.5/artifacts/not-a-key",
        ):
            with self.subTest(target=target):
                response = self.harness.request(target)
                self.assertEqual(response.status, 404)
                self.assertEqual(
                    json.loads(response.body)["error"]["code"], "NOT_FOUND"
                )
                self.assertEqual(
                    response.headers["content-type"],
                    "application/json; charset=utf-8",
                )

    def _local_harness(self):
        published = PublishedObservation()
        return published, ServerHarness(published.root)

    def test_canonical_artifact_mutation_returns_409_without_path(self) -> None:
        published, harness = self._local_harness()
        try:
            detail = next(iter(harness.projection.details.values()))
            descriptor = detail["manifest"]
            record = next(iter(harness.records.records.values()))
            path = record.backing.root / descriptor["relative_path"]
            path.write_bytes(path.read_bytes() + b" ")
            response = harness.request(
                f"/api/v0.5/artifacts/{descriptor['artifact_key']}"
            )
        finally:
            harness.close()
            published.close()
        self.assertEqual(response.status, 409)
        payload = json.loads(response.body)
        self.assertEqual(payload["error"]["code"], "ARTIFACT_CHANGED")
        self.assertNotIn(str(path), response.body.decode())

    def test_post_capture_replacement_never_changes_served_bytes(self) -> None:
        published, harness = self._local_harness()
        try:
            detail = next(iter(harness.projection.details.values()))
            descriptor = detail["manifest"]
            record = next(iter(harness.records.records.values()))
            target = record.backing.root / descriptor["relative_path"]
            original = target.read_bytes()
            capture = harness.records.recheck_artifact

            def capture_then_replace(value):
                content = capture(value)
                target.write_bytes(b"replacement bytes")
                return content

            with patch.object(
                harness.records,
                "recheck_artifact",
                side_effect=capture_then_replace,
            ):
                response = harness.request(
                    f"/api/v0.5/artifacts/{descriptor['artifact_key']}"
                )
        finally:
            harness.close()
            published.close()
        self.assertEqual(response.status, 200)
        self.assertEqual(response.body, original)
        self.assertNotEqual(response.body, b"replacement bytes")

    def test_node_mutations_return_409_with_head_parity_and_no_partial_body(
        self,
    ) -> None:
        mutations = ("in-place", "atomic", "symlink", "directory")
        for mutation in mutations:
            with self.subTest(mutation=mutation):
                published, harness = self._local_harness()
                try:
                    detail = next(iter(harness.projection.details.values()))
                    descriptor = detail["manifest"]
                    record = next(iter(harness.records.records.values()))
                    target = record.backing.root / descriptor["relative_path"]
                    original = target.read_bytes()
                    replacement = target.with_name("replacement-node")
                    if mutation == "in-place":
                        target.write_bytes(b"x" * len(original))
                    elif mutation == "atomic":
                        replacement.write_bytes(original)
                        replacement.replace(target)
                    elif mutation == "symlink":
                        replacement.write_bytes(original)
                        target.unlink()
                        target.symlink_to(replacement)
                    else:
                        target.unlink()
                        target.mkdir()
                    route = (
                        f"/api/v0.5/artifacts/{descriptor['artifact_key']}"
                    )
                    get = harness.request(route)
                    head = harness.request(route, method="HEAD")
                finally:
                    harness.close()
                    published.close()
                self.assertEqual(get.status, 409)
                self.assertEqual(head.status, 409)
                self.assertEqual(head.body, b"")
                self.assertEqual(
                    head.headers["content-length"],
                    get.headers["content-length"],
                )
                self.assertEqual(
                    json.loads(get.body)["error"]["code"],
                    "ARTIFACT_CHANGED",
                )
                self.assertEqual(len(get.body), int(get.headers["content-length"]))
                self.assertFalse(get.body.startswith(original[:32]))


if __name__ == "__main__":
    unittest.main()
