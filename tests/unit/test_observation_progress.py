from __future__ import annotations

import tempfile
import unittest
from pathlib import Path
from unittest import mock

from tiny_corpus_workbench.application.observation import (
    OBSERVATION_STAGES,
    observe,
)


SOURCE = Path("fixtures/golden/policy-memo.md")


def fake_docling(source: Path, destination: Path, model_root: Path):
    destination.mkdir(parents=True)
    (destination / "document.json").write_text(
        '{"schema_name":"DoclingDocument","version":"1.10.0"}\n',
        "utf-8",
    )
    (destination / "document.md").write_text("# Docling view\n", "utf-8")
    return "success", {"name": "DoclingDocument", "version": "1.10.0"}


def fake_markitdown(source: Path, destination: Path):
    destination.mkdir(parents=True)
    (destination / "document.md").write_text("# MarkItDown view\n", "utf-8")


class ObservationProgressTests(unittest.TestCase):
    def test_model_free_markdown_reports_exact_service_stages_in_order(
        self,
    ) -> None:
        stages: list[str] = []
        with tempfile.TemporaryDirectory() as directory, mock.patch(
            "tiny_corpus_workbench.extractors.docling.convert",
            wraps=fake_docling,
        ), mock.patch(
            "tiny_corpus_workbench.extractors.markitdown.convert",
            wraps=fake_markitdown,
        ):
            code, published = observe(
                str(SOURCE),
                Path(directory),
                Path("unused"),
                progress=stages.append,
            )
            self.assertEqual(int(code), 0)
            self.assertTrue((published / "manifest.json").is_file())
        self.assertEqual(stages, list(OBSERVATION_STAGES))

    def test_progress_callback_is_optional(self) -> None:
        with tempfile.TemporaryDirectory() as directory, mock.patch(
            "tiny_corpus_workbench.extractors.docling.convert",
            wraps=fake_docling,
        ), mock.patch(
            "tiny_corpus_workbench.extractors.markitdown.convert",
            wraps=fake_markitdown,
        ):
            code, published = observe(
                str(SOURCE),
                Path(directory),
                Path("unused"),
            )
            self.assertEqual(int(code), 0)
            self.assertTrue((published / "manifest.json").is_file())


if __name__ == "__main__":
    unittest.main()
