from __future__ import annotations

import io
import json
import tempfile
import unittest
from contextlib import redirect_stderr, redirect_stdout
from pathlib import Path
from unittest import mock

from tiny_corpus_workbench import cli


FIXTURE = Path("fixtures/golden/policy-memo.md")


def fake_docling(source: Path, destination: Path, model_root: Path):
    destination.mkdir(parents=True)
    (destination / "document.json").write_text('{"schema_name":"DoclingDocument","version":"1.10.0"}\n', "utf-8")
    (destination / "document.md").write_text("# view\n", "utf-8")
    return "success", {"name": "DoclingDocument", "version": "1.10.0"}


def fake_markitdown(source: Path, destination: Path):
    destination.mkdir(parents=True)
    (destination / "document.md").write_text("# view\n", "utf-8")


class CliFailureTests(unittest.TestCase):
    def invoke(self, *arguments: str) -> tuple[int, str, str]:
        stdout, stderr = io.StringIO(), io.StringIO()
        with redirect_stdout(stdout), redirect_stderr(stderr):
            code = cli.main(list(arguments))
        return code, stdout.getvalue(), stderr.getvalue()

    def test_validation_failure_has_no_stdout(self) -> None:
        code, stdout, stderr = self.invoke("observe", "LICENSE")
        self.assertEqual(code, 2)
        self.assertEqual(stdout, "")
        self.assertIn("unsupported media type", stderr)

    def test_each_single_failure_and_total_failure_publish_evidence(self) -> None:
        cases = ((RuntimeError("docling failed"), fake_markitdown, 3, "INCOMPLETE"), (fake_docling, RuntimeError("markitdown failed"), 3, "INCOMPLETE"), (RuntimeError("docling failed"), RuntimeError("markitdown failed"), 4, "NOT_AVAILABLE"))
        for docling_behavior, markitdown_behavior, expected_code, comparison_status in cases:
            with self.subTest(expected_code=expected_code), tempfile.TemporaryDirectory() as directory:
                docling_side = docling_behavior if isinstance(docling_behavior, Exception) else None
                markitdown_side = markitdown_behavior if isinstance(markitdown_behavior, Exception) else None
                docling_patch = mock.patch("tiny_corpus_workbench.extractors.docling.convert", side_effect=docling_side, wraps=None if docling_side else docling_behavior)
                markitdown_patch = mock.patch("tiny_corpus_workbench.extractors.markitdown.convert", side_effect=markitdown_side, wraps=None if markitdown_side else markitdown_behavior)
                with docling_patch, markitdown_patch:
                    code, stdout, _ = self.invoke("observe", str(FIXTURE), "--output-root", directory)
                self.assertEqual(code, expected_code)
                published = json.loads(stdout)
                manifest = json.loads(Path(published["manifest"]).read_text("utf-8"))
                comparison = json.loads(Path(published["manifest"]).with_name("comparison.json").read_text("utf-8"))
                self.assertEqual(manifest["comparison"]["status"], comparison_status)
                self.assertEqual(comparison["status"], comparison_status)

    def test_source_mutation_discards_staging(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            source = Path(directory) / "source.md"
            source.write_text("# original\n", "utf-8")

            def mutate(source_path: Path, destination: Path):
                fake_markitdown(source_path, destination)
                source_path.write_text("# changed\n", "utf-8")

            output = Path(directory) / "output"
            with mock.patch("tiny_corpus_workbench.extractors.docling.convert", wraps=fake_docling), mock.patch("tiny_corpus_workbench.extractors.markitdown.convert", wraps=mutate):
                code, stdout, stderr = self.invoke("observe", str(source), "--output-root", str(output))
            self.assertEqual(code, 5)
            self.assertEqual(stdout, "")
            self.assertIn("changed during extraction", stderr)
            self.assertEqual(list(output.glob("*/*")), [])


if __name__ == "__main__":
    unittest.main()
