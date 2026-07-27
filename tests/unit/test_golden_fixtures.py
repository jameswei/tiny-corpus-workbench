from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from tiny_corpus_workbench.golden_fixtures import (
    fixture_anchors,
    fixture_id_for_path,
)
from tools import verify_fixtures


class GoldenFixtureRuntimeTests(unittest.TestCase):
    def assert_runtime_fallback(self, value: object) -> None:
        with tempfile.TemporaryDirectory() as directory:
            registry = Path(directory) / "fixtures.json"
            registry.write_text(json.dumps(value), "utf-8")
            with mock.patch(
                "tiny_corpus_workbench.golden_fixtures._registry_path",
                return_value=registry,
            ):
                self.assertIsNone(
                    fixture_id_for_path(Path(directory) / "source.md")
                )
                self.assertEqual(fixture_anchors("fixture-id"), {})

    def test_non_object_registry_values_are_optional_empty_data(self) -> None:
        for value in (None, [], "registry", 7):
            with self.subTest(value=value):
                self.assert_runtime_fallback(value)

    def test_malformed_registry_entries_are_optional_empty_data(self) -> None:
        for entry in (None, "fixture", 7, [], {}, {"id": 7}, {"path": 7}):
            with self.subTest(entry=entry):
                self.assert_runtime_fallback({"fixtures": [entry]})


class FixtureVerifierFailureTests(unittest.TestCase):
    def invoke(
        self, value: object, fixture_names: tuple[str, ...] = ()
    ) -> str:
        with tempfile.TemporaryDirectory() as directory:
            golden = Path(directory) / "fixtures/golden"
            golden.mkdir(parents=True)
            for name in fixture_names:
                (golden / name).touch()
            (golden / "fixtures.json").write_text(
                json.dumps(value), "utf-8"
            )
            with mock.patch.object(
                verify_fixtures, "ROOT", Path(directory)
            ), mock.patch.object(
                verify_fixtures, "GOLDEN", golden
            ), self.assertRaises(SystemExit) as raised:
                verify_fixtures.main()
        return str(raised.exception)

    def test_non_object_registry_values_exit_cleanly(self) -> None:
        for value in (None, [], "registry", 7):
            with self.subTest(value=value):
                self.assertEqual(
                    self.invoke(value),
                    "fixture registry must contain only a fixture list",
                )

    def test_malformed_entries_exit_cleanly(self) -> None:
        for entry in (None, "fixture", 7, [], {}, {"id": 7}):
            with self.subTest(entry=entry):
                self.assertEqual(
                    self.invoke({"fixtures": [entry]}),
                    "fixture registry entries must be objects with string IDs",
                )

    def test_malformed_nested_entry_exits_cleanly(self) -> None:
        entries = []
        names = []
        for family in ("meeting-minutes", "policy-memo", "release-notice"):
            for format_name in ("docx", "md", "pdf", "txt"):
                fixture_id = f"{family}-{format_name}"
                name = f"{fixture_id}.{format_name}"
                names.append(name)
                entries.append(
                    {
                        "anchors": {},
                        "authored_source": None,
                        "expected_docling_table_count": 0,
                        "family": family,
                        "format": format_name,
                        "id": fixture_id,
                        "license": "CC0-1.0",
                        "media_type": "text/plain",
                        "ownership": "project-authored",
                        "path": f"fixtures/golden/{name}",
                        "recipe": "tools/generate_fixtures.py",
                        "sha256": "0" * 64,
                        "size": 0,
                    }
                )
        self.assertEqual(
            self.invoke({"fixtures": entries}, tuple(names)),
            "fixture registry or fixture files are malformed",
        )
