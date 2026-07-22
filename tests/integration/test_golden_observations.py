from __future__ import annotations

import json
import os
import socket
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from docling_core.types.doc import DoclingDocument
from jsonschema import Draft202012Validator

from tiny_corpus_workbench.cli import observe


ROOT = Path(__file__).resolve().parents[2]
MODEL_ROOT = Path(os.environ.get("TCW_DOCLING_ARTIFACTS", ".cache/docling/models"))
SCHEMAS = ROOT / "src/tiny_corpus_workbench/schemas"


def snapshot(root: Path) -> dict[str, bytes]:
    return {path.relative_to(root).as_posix(): path.read_bytes() for path in sorted(root.rglob("*")) if path.is_file()}


class GoldenObservationTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        if not MODEL_ROOT.is_dir():
            raise unittest.SkipTest(f"prefetched Docling models are required: {MODEL_ROOT}")
        cls.registry = json.loads((ROOT / "fixtures/golden/fixtures.json").read_text("utf-8"))
        cls.manifest_validator = Draft202012Validator(json.loads((SCHEMAS / "preparation-manifest-v0.1.schema.json").read_text("utf-8")))
        cls.comparison_validator = Draft202012Validator(json.loads((SCHEMAS / "comparison-summary-v0.1.schema.json").read_text("utf-8")))

    def test_all_twelve_fixtures_through_both_extractors_twice_offline(self) -> None:
        self.assertEqual(len(self.registry["fixtures"]), 12)

        def deny(*args, **kwargs):
            raise AssertionError("observation-time network access attempted")

        with tempfile.TemporaryDirectory() as first_dir, tempfile.TemporaryDirectory() as second_dir:
            first_root, second_root = Path(first_dir), Path(second_dir)
            with mock.patch.object(socket, "create_connection", deny), mock.patch.object(socket.socket, "connect", deny), mock.patch.object(socket.socket, "connect_ex", deny):
                for fixture in self.registry["fixtures"]:
                    source = ROOT / fixture["path"]
                    source_before = source.read_bytes()
                    with self.subTest(fixture=fixture["id"]):
                        first_code, first = observe(str(source), first_root, MODEL_ROOT)
                        first_snapshot = snapshot(first)
                        second_code, second = observe(str(source), second_root, MODEL_ROOT)
                        self.assertEqual(int(first_code), 0)
                        self.assertEqual(int(second_code), 0)
                        self.assertEqual(source.read_bytes(), source_before)
                        self.assertEqual(snapshot(first), first_snapshot)

                        manifest = json.loads((first / "manifest.json").read_text("utf-8"))
                        comparison = json.loads((first / "comparison.json").read_text("utf-8"))
                        self.manifest_validator.validate(manifest)
                        self.comparison_validator.validate(comparison)
                        self.assertEqual(manifest["source"]["fixture_id"], fixture["id"])
                        self.assertEqual(manifest["source"]["sha256"], fixture["sha256"])
                        self.assertEqual([item["status"] for item in manifest["extractors"]], ["SUCCESS", "SUCCESS"])
                        self.assertEqual(comparison["status"], "COMPLETE")
                        for view in comparison["views"].values():
                            self.assertGreater(view["bytes"], 0)
                            self.assertTrue(all(view["anchors"].values()))
                        self.assertEqual((first / "comparison.json").read_bytes(), (second / "comparison.json").read_bytes())

                        document = DoclingDocument.load_from_json(first / "docling/document.json")
                        self.assertTrue(document.export_to_markdown().strip())
                        self.assertEqual(len(document.tables), fixture["expected_docling_table_count"])
                        self.assertTrue((first / "docling/document.md").read_text("utf-8").strip())
                        self.assertTrue((first / "markitdown/document.md").read_text("utf-8").strip())

                        manifest["unexpected"] = True
                        with self.assertRaises(Exception):
                            self.manifest_validator.validate(manifest)

    def test_missing_pdf_models_publishes_runtime_failure_evidence(self) -> None:
        fixture = next(item for item in self.registry["fixtures"] if item["id"] == "policy-memo-pdf")
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            code, published = observe(str(ROOT / fixture["path"]), root / "output", root / "missing-models")
            manifest = json.loads((published / "manifest.json").read_text("utf-8"))
            comparison = json.loads((published / "comparison.json").read_text("utf-8"))
            self.assertEqual(int(code), 6)
            self.assertEqual(manifest["extractors"][0]["error"]["code"], "MODEL_ARTIFACTS_MISSING")
            self.assertEqual(manifest["extractors"][1]["status"], "SUCCESS")
            self.assertEqual(comparison["status"], "INCOMPLETE")
            self.manifest_validator.validate(manifest)


if __name__ == "__main__":
    unittest.main()
