from __future__ import annotations

import io
import json
import tempfile
import unittest
from contextlib import redirect_stderr, redirect_stdout
from pathlib import Path
from unittest import mock

from tiny_corpus_workbench import cli
from tiny_corpus_workbench.artifacts import AtomicObservation


FIXTURE = Path("fixtures/golden/policy-memo.md")
PDF_FIXTURE = Path("fixtures/golden/policy-memo.pdf")


def fake_docling(source: Path, destination: Path, model_root: Path):
    destination.mkdir(parents=True)
    (destination / "document.json").write_text('{"schema_name":"DoclingDocument","version":"1.10.0"}\n', "utf-8")
    (destination / "document.md").write_text("# view\n", "utf-8")
    return "success", {"name": "DoclingDocument", "version": "1.10.0"}


def fake_markitdown(source: Path, destination: Path):
    destination.mkdir(parents=True)
    (destination / "document.md").write_text("# view\n", "utf-8")


def partial_docling(source: Path, destination: Path, model_root: Path):
    destination.mkdir(parents=True)
    (destination / "partial.json").write_text("partial", "utf-8")
    raise RuntimeError("failed after writing")


def partial_markitdown(source: Path, destination: Path):
    destination.mkdir(parents=True)
    (destination / "partial.md").write_text("partial", "utf-8")
    raise RuntimeError("failed after writing")


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

    def test_failed_extractors_remove_partial_untracked_files(self) -> None:
        cases = ((partial_docling, fake_markitdown, "docling"), (fake_docling, partial_markitdown, "markitdown"))
        for docling_behavior, markitdown_behavior, failed_name in cases:
            with self.subTest(failed=failed_name), tempfile.TemporaryDirectory() as directory:
                with mock.patch("tiny_corpus_workbench.extractors.docling.convert", wraps=docling_behavior), mock.patch("tiny_corpus_workbench.extractors.markitdown.convert", wraps=markitdown_behavior):
                    code, stdout, _ = self.invoke("observe", str(FIXTURE), "--output-root", directory)
                self.assertEqual(code, 3)
                run = Path(json.loads(stdout)["manifest"]).parent
                manifest = json.loads((run / "manifest.json").read_text("utf-8"))
                tracked = {"manifest.json", "comparison.json"}
                for result in manifest["extractors"]:
                    tracked.update(artifact["path"] for artifact in result["artifacts"])
                actual = {path.relative_to(run).as_posix() for path in run.rglob("*") if path.is_file()}
                self.assertEqual(actual, tracked)
                self.assertFalse((run / failed_name).exists())

    def test_unrelated_pdf_models_are_invalid_runtime_artifacts(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            models = root / "models"
            models.mkdir()
            (models / "unrelated.bin").write_bytes(b"not a model")
            code, stdout, _ = self.invoke(
                "observe",
                str(PDF_FIXTURE),
                "--output-root",
                str(root / "output"),
                "--docling-artifacts",
                str(models),
            )
            self.assertEqual(code, 6)
            manifest = json.loads(Path(json.loads(stdout)["manifest"]).read_text("utf-8"))
            self.assertEqual(
                manifest["extractors"][0]["error"]["code"],
                "MODEL_ARTIFACTS_INVALID",
            )

    def test_non_pdf_ignores_irrelevant_bad_model_path(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            alias = root / "bad-model-link"
            alias.symlink_to(root / "missing-target")
            with mock.patch("tiny_corpus_workbench.extractors.docling.convert", wraps=fake_docling), mock.patch("tiny_corpus_workbench.extractors.markitdown.convert", wraps=fake_markitdown):
                code, stdout, _ = self.invoke(
                    "observe",
                    str(FIXTURE),
                    "--output-root",
                    str(root / "output"),
                    "--docling-artifacts",
                    str(alias),
                )
            self.assertEqual(code, 0)
            self.assertTrue(stdout)

    def test_unavailable_dependency_metadata_is_runtime_exit(self) -> None:
        with mock.patch("tiny_corpus_workbench.cli.importlib.metadata.version", side_effect=cli.importlib.metadata.PackageNotFoundError("docling")):
            code, stdout, stderr = self.invoke("observe", str(FIXTURE))
        self.assertEqual(code, 6)
        self.assertEqual(stdout, "")
        self.assertIn("package metadata is unavailable", stderr)

    def test_publication_races_are_integrity_exit_without_replacement(self) -> None:
        original_publish = AtomicObservation.publish
        for with_content in (False, True):
            with self.subTest(with_content=with_content), tempfile.TemporaryDirectory() as directory:
                sentinel = b"existing"

                def race_publish(publisher):
                    publisher.destination.mkdir()
                    if with_content:
                        (publisher.destination / "sentinel").write_bytes(sentinel)
                    return original_publish(publisher)

                with mock.patch("tiny_corpus_workbench.extractors.docling.convert", wraps=fake_docling), mock.patch("tiny_corpus_workbench.extractors.markitdown.convert", wraps=fake_markitdown), mock.patch.object(AtomicObservation, "publish", autospec=True, side_effect=race_publish):
                    code, stdout, stderr = self.invoke(
                        "observe", str(FIXTURE), "--output-root", directory
                    )
                self.assertEqual(code, 5)
                self.assertEqual(stdout, "")
                self.assertIn("publication conflict", stderr)
                destinations = [path for path in Path(directory).glob("*/*") if not path.name.startswith(".staging-")]
                self.assertEqual(len(destinations), 1)
                self.assertFalse((destinations[0] / "manifest.json").exists())
                if with_content:
                    self.assertEqual((destinations[0] / "sentinel").read_bytes(), sentinel)

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
