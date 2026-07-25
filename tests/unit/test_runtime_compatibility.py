from __future__ import annotations

import unittest

from tiny_corpus_workbench.runtime import (
    EXPECTED_LOCKFILE_SHA256,
    RUNTIME_DEPENDENCIES,
    V03_LOCKFILE_SHA256,
    is_v03_compatible_runtime,
)


class RuntimeCompatibilityTests(unittest.TestCase):
    def runtime(self, package_version: str, lockfile_sha256: str) -> dict:
        return {
            "python": "3.12.11",
            "implementation": "CPython",
            "lockfile_sha256": lockfile_sha256,
            "package_version": package_version,
            "dependencies": dict(RUNTIME_DEPENDENCIES),
        }

    def test_exact_historical_and_active_pairs_are_accepted(self) -> None:
        for package_version, lockfile_sha256 in (
            ("0.3.0", V03_LOCKFILE_SHA256),
            ("0.4.0", EXPECTED_LOCKFILE_SHA256),
        ):
            with self.subTest(package_version=package_version):
                self.assertTrue(
                    is_v03_compatible_runtime(
                        self.runtime(package_version, lockfile_sha256)
                    )
                )

    def test_mixed_and_arbitrary_pairs_are_rejected(self) -> None:
        for package_version, lockfile_sha256 in (
            ("0.3.0", EXPECTED_LOCKFILE_SHA256),
            ("0.4.0", V03_LOCKFILE_SHA256),
            ("0.3.1", V03_LOCKFILE_SHA256),
            ("0.4.0", "f" * 64),
        ):
            with self.subTest(
                package_version=package_version,
                lockfile_sha256=lockfile_sha256,
            ):
                self.assertFalse(
                    is_v03_compatible_runtime(
                        self.runtime(package_version, lockfile_sha256)
                    )
                )

    def test_python_dependency_and_shape_drift_are_rejected(self) -> None:
        cases = []
        for field, value in (
            ("python", "3.13.0"),
            ("implementation", "PyPy"),
            (
                "dependencies",
                {**RUNTIME_DEPENDENCIES, "docling-core": "0.0.0"},
            ),
        ):
            runtime = self.runtime("0.4.0", EXPECTED_LOCKFILE_SHA256)
            runtime[field] = value
            cases.append((field, runtime))
        runtime = self.runtime("0.4.0", EXPECTED_LOCKFILE_SHA256)
        runtime["unexpected"] = "value"
        cases.append(("unexpected", runtime))

        for field, runtime in cases:
            with self.subTest(field=field):
                self.assertFalse(is_v03_compatible_runtime(runtime))
