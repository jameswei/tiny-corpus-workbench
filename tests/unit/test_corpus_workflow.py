from __future__ import annotations

import io
import json
import shutil
import tempfile
import unittest
from contextlib import redirect_stderr, redirect_stdout
from datetime import UTC, datetime
from pathlib import Path
from types import SimpleNamespace
from unittest import mock

from docling_core.types.doc import DocItemLabel, DoclingDocument

from tiny_corpus_workbench import cli
from tiny_corpus_workbench.artifacts import canonical_json
from tiny_corpus_workbench.corpus_publication import inspect_corpus
from tiny_corpus_workbench.corpus_verification import verify_corpus
from tiny_corpus_workbench.domain import IntegrityError
from tiny_corpus_workbench.source import sha256_file


SECRET = "PRIVATE SOURCE SENTENCE MUST NOT APPEAR"


def _docling(source: Path, destination: Path, model_root: Path):
    destination.mkdir(parents=True)
    document = DoclingDocument(name="corpus-unit")
    document.add_text(
        DocItemLabel.TEXT,
        "Stable corpus evidence is long enough for diagnosis. " * 8,
    )
    document.save_as_json(destination / "document.json")
    document.save_as_markdown(destination / "document.md")
    return "success", {"name": "DoclingDocument", "version": "1.10.0"}


def _markitdown(source: Path, destination: Path):
    destination.mkdir(parents=True)
    (destination / "document.md").write_text(
        "# Corpus unit\n\nStable comparison evidence.\n", "utf-8"
    )


def _fail(*args, **kwargs):
    raise RuntimeError(SECRET)


def _write_spec(root: Path) -> Path:
    source = root / "source.md"
    source.write_text(f"# Source\n\n{SECRET}\n", "utf-8")
    spec = root / "corpus.json"
    spec.write_bytes(
        canonical_json(
            {
                "schema_version": "tcw.corpus-spec/v0.4",
                "corpus_id": "unit-corpus",
                "title": "Unit <Corpus>",
                "members": [
                    {
                        "member_id": "unit-member",
                        "family": "unit-family",
                        "format": "md",
                        "source": "source.md",
                    }
                ],
            }
        )
    )
    return spec


class CorpusWorkflowTests(unittest.TestCase):
    def publish(
        self,
        root: Path,
        *,
        docling=_docling,
        markitdown=_markitdown,
    ):
        spec = _write_spec(root)
        output = root.parent / f"{root.name}-output"
        with mock.patch(
            "tiny_corpus_workbench.extractors.docling.convert",
            side_effect=docling,
        ), mock.patch(
            "tiny_corpus_workbench.extractors.markitdown.convert",
            side_effect=markitdown,
        ):
            published = inspect_corpus(spec, output, root / "unused-models")
        return spec, published

    def test_complete_publication_report_cli_and_verification(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory).resolve()
            spec, published = self.publish(root)
            self.assertEqual(published.status, "COMPLETE")
            self.assertEqual(published.exit_code, 0)
            self.assertEqual(
                {
                    path.relative_to(published.directory).as_posix()
                    for path in published.directory.rglob("*")
                    if path.is_file()
                }
                >= {
                    "corpus-manifest.json",
                    "corpus-spec.json",
                    "summary.json",
                    "report/index.html",
                    "report/styles.css",
                },
                True,
            )
            first = verify_corpus(published.directory)
            second = verify_corpus(published.directory, spec)
            self.assertEqual(
                first["artifact_integrity"]["status"], "VERIFIED"
            )
            self.assertEqual(
                second["artifact_integrity"]["status"], "VERIFIED"
            )
            self.assertEqual(
                second["specification_state"]["status"], "MATCH"
            )
            self.assertEqual(second["source_states"][0]["state"]["status"], "MATCH")
            report = (published.directory / "report/index.html").read_text(
                "utf-8"
            )
            self.assertIn("Unit &lt;Corpus&gt;", report)
            self.assertNotIn(SECRET, report)
            self.assertNotIn("<script", report.lower())
            self.assertNotIn("http://", report.lower())
            self.assertNotIn("https://", report.lower())

            stdout, stderr = io.StringIO(), io.StringIO()
            with redirect_stdout(stdout), redirect_stderr(stderr):
                code = cli.main(
                    [
                        "verify-corpus",
                        str(published.directory),
                        "--spec",
                        str(spec),
                    ]
                )
            self.assertEqual(code, 0)
            self.assertEqual(stderr.getvalue(), "")
            line = json.loads(stdout.getvalue())
            self.assertEqual(
                line["artifact_integrity"]["status"], "VERIFIED"
            )

    def test_inspect_cli_prints_one_compact_sorted_line(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory).resolve()
            spec = _write_spec(root)
            output = root.parent / f"{root.name}-output"
            stdout, stderr = io.StringIO(), io.StringIO()
            with mock.patch(
                "tiny_corpus_workbench.extractors.docling.convert",
                side_effect=_docling,
            ), mock.patch(
                "tiny_corpus_workbench.extractors.markitdown.convert",
                side_effect=_markitdown,
            ), redirect_stdout(stdout), redirect_stderr(stderr):
                code = cli.main(
                    [
                        "inspect-corpus",
                        str(spec),
                        "--output-root",
                        str(output),
                        "--docling-artifacts",
                        str(root / "unused-models"),
                    ]
                )
            self.assertEqual(code, 0)
            self.assertEqual(stderr.getvalue(), "")
            self.assertEqual(len(stdout.getvalue().splitlines()), 1)
            value = json.loads(stdout.getvalue())
            self.assertEqual(
                list(value),
                sorted(value),
            )
            self.assertEqual(value["corpus_id"], "unit-corpus")
            self.assertEqual(value["member_count"], 1)
            self.assertEqual(value["status"], "COMPLETE")
            self.assertTrue(Path(value["manifest"]).is_absolute())

    def test_partial_and_failed_statuses_and_exit_codes(self) -> None:
        cases = [
            (_docling, _fail, "PARTIAL", 3),
            (_fail, _fail, "FAILED", 4),
        ]
        for docling, markitdown, status, exit_code in cases:
            with self.subTest(status=status), tempfile.TemporaryDirectory() as directory:
                root = Path(directory).resolve()
                _, published = self.publish(
                    root,
                    docling=docling,
                    markitdown=markitdown,
                )
                self.assertEqual(published.status, status)
                self.assertEqual(published.exit_code, exit_code)
                self.assertEqual(
                    verify_corpus(published.directory)["artifact_integrity"][
                        "status"
                    ],
                    "VERIFIED",
                )

    def test_top_level_and_nested_corruption_is_detected(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory).resolve()
            _, published = self.publish(root)
            targets = [
                "corpus-manifest.json",
                "corpus-spec.json",
                "summary.json",
                "report/index.html",
                "report/styles.css",
            ]
            manifest = json.loads(
                (published.directory / "corpus-manifest.json").read_text(
                    "utf-8"
                )
            )
            targets.extend(
                [
                    manifest["members"][0]["observation"]["manifest"]["path"],
                    manifest["members"][0]["diagnosis"]["manifest"]["path"],
                ]
            )
            for index, relative in enumerate(targets):
                with self.subTest(relative=relative):
                    copied = (
                        root / f"broken-{index}" / published.directory.name
                    )
                    shutil.copytree(published.directory, copied)
                    path = copied / relative
                    path.write_bytes(path.read_bytes() + b"BROKEN")
                    self.assertNotEqual(
                        verify_corpus(copied)["artifact_integrity"]["status"],
                        "VERIFIED",
                    )

    def test_encoded_control_report_link_is_rejected(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory).resolve()
            _, published = self.publish(root)
            report_path = published.directory / "report/index.html"
            report = report_path.read_text("utf-8").replace(
                'href="styles.css"',
                'href="%0astyles.css"',
                1,
            )
            report_path.write_text(report, "utf-8")
            manifest_path = published.directory / "corpus-manifest.json"
            manifest = json.loads(manifest_path.read_text("utf-8"))
            descriptor = next(
                item
                for item in manifest["artifacts"]
                if item["path"] == "report/index.html"
            )
            descriptor["size"] = report_path.stat().st_size
            descriptor["sha256"] = sha256_file(report_path)
            manifest_path.write_bytes(canonical_json(manifest))
            verification = verify_corpus(published.directory)
            self.assertEqual(
                verification["artifact_integrity"]["status"],
                "INTEGRITY_MISMATCH",
            )
            self.assertTrue(
                any(
                    issue["code"] == "UNSAFE_REFERENCE"
                    and "encoded control character" in issue["message"]
                    for issue in verification["artifact_integrity"]["issues"]
                )
            )

    def test_manifest_date_time_format_is_enforced(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory).resolve()
            _, published = self.publish(root)
            manifest_path = published.directory / "corpus-manifest.json"
            manifest = json.loads(manifest_path.read_text("utf-8"))
            manifest["created_at"] = "not-a-date-time"
            manifest_path.write_bytes(canonical_json(manifest))
            verification = verify_corpus(published.directory)
            self.assertEqual(
                verification["artifact_integrity"]["status"], "BROKEN"
            )
            self.assertTrue(
                any(
                    issue["code"] == "MANIFEST_INVALID"
                    for issue in verification["artifact_integrity"]["issues"]
                )
            )

    def test_live_input_drift_is_advisory(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory).resolve()
            spec, published = self.publish(root)
            (root / "source.md").write_text("# Changed\n", "utf-8")
            report = verify_corpus(published.directory, spec)
            self.assertEqual(
                report["artifact_integrity"]["status"], "VERIFIED"
            )
            self.assertEqual(
                report["source_states"][0]["state"]["status"], "CHANGED"
            )
            spec.write_text("{}\n", "utf-8")
            report = verify_corpus(published.directory, spec)
            self.assertEqual(
                report["artifact_integrity"]["status"], "VERIFIED"
            )
            self.assertEqual(
                report["specification_state"]["status"], "CHANGED"
            )
            source = root / "source.md"
            source.unlink()
            report = verify_corpus(published.directory, spec)
            self.assertEqual(
                report["source_states"][0]["state"]["status"], "MISSING"
            )
            source.mkdir()
            report = verify_corpus(published.directory, spec)
            self.assertEqual(
                report["source_states"][0]["state"]["status"], "ERROR"
            )
            spec.unlink()
            report = verify_corpus(published.directory, spec)
            self.assertEqual(
                report["specification_state"]["status"], "MISSING"
            )
            spec.mkdir()
            report = verify_corpus(published.directory, spec)
            self.assertEqual(
                report["specification_state"]["status"], "ERROR"
            )

    def test_publication_conflict_is_exclusive_and_cleans_staging(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory).resolve()
            spec = _write_spec(root)
            output = root.parent / f"{root.name}-output"
            fixed_datetime = SimpleNamespace()
            fixed_datetime.now = mock.Mock(
                return_value=datetime(2026, 7, 25, 12, 0, tzinfo=UTC)
            )
            fixed_uuid = SimpleNamespace(hex="a" * 32)
            patches = (
                mock.patch(
                    "tiny_corpus_workbench.extractors.docling.convert",
                    side_effect=_docling,
                ),
                mock.patch(
                    "tiny_corpus_workbench.extractors.markitdown.convert",
                    side_effect=_markitdown,
                ),
                mock.patch(
                    "tiny_corpus_workbench.corpus_publication.datetime",
                    fixed_datetime,
                ),
                mock.patch(
                    "tiny_corpus_workbench.corpus_publication.uuid.uuid4",
                    return_value=fixed_uuid,
                ),
            )
            with patches[0], patches[1], patches[2], patches[3]:
                first = inspect_corpus(spec, output, root / "unused-models")
                before = {
                    path.relative_to(first.directory).as_posix(): path.read_bytes()
                    for path in first.directory.rglob("*")
                    if path.is_file()
                }
                with self.assertRaises(IntegrityError):
                    inspect_corpus(spec, output, root / "unused-models")
            self.assertEqual(
                before,
                {
                    path.relative_to(first.directory).as_posix(): path.read_bytes()
                    for path in first.directory.rglob("*")
                    if path.is_file()
                },
            )
            self.assertFalse(
                any(
                    path.name.startswith(".staging-")
                    for path in output.rglob("*")
                )
            )


if __name__ == "__main__":
    unittest.main()
