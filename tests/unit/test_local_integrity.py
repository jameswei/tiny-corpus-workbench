from __future__ import annotations

import io
import json
import tempfile
import threading
import unittest
from concurrent.futures import ThreadPoolExecutor
from contextlib import redirect_stderr, redirect_stdout
from pathlib import Path
from unittest import mock

from tiny_corpus_workbench import cli
from tiny_corpus_workbench.artifacts import REQUIRED_MODEL_FILES, inventory_models
from tiny_corpus_workbench.domain import IntegrityError, RuntimeContractError
from tiny_corpus_workbench.source import SourceSnapshot
import tiny_corpus_workbench.source as source_module
import tiny_corpus_workbench.extractors.docling as docling_adapter


MARKDOWN_FIXTURE = Path("fixtures/golden/policy-memo.md")
PDF_FIXTURE = Path("fixtures/golden/policy-memo.pdf")


def fake_docling(source: Path, destination: Path, model_root: Path):
    destination.mkdir(parents=True)
    (destination / "document.json").write_text(
        '{"schema_name":"DoclingDocument","version":"1.10.0"}\n', "utf-8"
    )
    (destination / "document.md").write_text("# view\n", "utf-8")
    return "success", {"name": "DoclingDocument", "version": "1.10.0"}


def fake_markitdown(source: Path, destination: Path):
    destination.mkdir(parents=True)
    (destination / "document.md").write_text("# view\n", "utf-8")


def create_models(root: Path) -> None:
    for relative in REQUIRED_MODEL_FILES:
        path = root / relative
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(relative.encode("utf-8"))


class LocalIntegrityTests(unittest.TestCase):
    def invoke(self, *arguments: str) -> tuple[int, str, str]:
        stdout, stderr = io.StringIO(), io.StringIO()
        with redirect_stdout(stdout), redirect_stderr(stderr):
            code = cli.main(list(arguments))
        return code, stdout.getvalue(), stderr.getvalue()

    def adapters(self):
        return (
            mock.patch(
                "tiny_corpus_workbench.extractors.docling.convert",
                wraps=fake_docling,
            ),
            mock.patch(
                "tiny_corpus_workbench.extractors.markitdown.convert",
                wraps=fake_markitdown,
            ),
        )

    def test_source_change_during_capture_fails_and_snapshot_is_removed(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            source = root / "source.md"
            source.write_text("# before\n", "utf-8")
            output = root / "output"
            original_copy = source_module._copy_descriptor

            def copy_then_change(source_fd, destination_fd):
                result = original_copy(source_fd, destination_fd)
                source.write_text("# during\n", "utf-8")
                return result

            with mock.patch(
                "tiny_corpus_workbench.source._copy_descriptor",
                side_effect=copy_then_change,
            ):
                code, stdout, stderr = self.invoke(
                    "observe", str(source), "--output-root", str(output)
                )
            self.assertEqual(code, 5)
            self.assertEqual(stdout, "")
            self.assertIn("snapshot", stderr)
            self.assertEqual(list(output.glob("*/*")), [])

    def test_source_symlink_is_rejected(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            source = root / "source.md"
            source.write_text("# source\n", "utf-8")
            alias = root / "alias.md"
            alias.symlink_to(source)
            code, stdout, stderr = self.invoke("observe", str(alias))
            self.assertEqual(code, 2)
            self.assertEqual(stdout, "")
            self.assertIn("non-symlink", stderr)

    def test_snapshot_cleanup_failure_prevents_publication(self) -> None:
        original_cleanup = SourceSnapshot.cleanup
        calls = 0

        def fail_once(snapshot):
            nonlocal calls
            calls += 1
            if calls == 1:
                raise IntegrityError("private SOURCE snapshot cleanup failed")
            return original_cleanup(snapshot)

        with tempfile.TemporaryDirectory() as directory:
            output = Path(directory) / "output"
            docling_patch, markitdown_patch = self.adapters()
            with docling_patch, markitdown_patch, mock.patch.object(
                SourceSnapshot, "cleanup", autospec=True, side_effect=fail_once
            ):
                code, stdout, stderr = self.invoke(
                    "observe",
                    str(MARKDOWN_FIXTURE),
                    "--output-root",
                    str(output),
                )
            self.assertEqual(code, 5)
            self.assertEqual(stdout, "")
            self.assertIn("cleanup", stderr)
            self.assertEqual(list(output.glob("*/*")), [])
            self.assertGreaterEqual(calls, 2)

    def test_broken_import_or_adapter_api_fails_before_capture(self) -> None:
        for failure in (ImportError("broken import"), RuntimeError("broken API")):
            with self.subTest(failure=type(failure).__name__), mock.patch.object(
                SourceSnapshot, "capture", autospec=True
            ) as capture:
                if isinstance(failure, ImportError):
                    patcher = mock.patch(
                        "tiny_corpus_workbench.cli.importlib.import_module",
                        side_effect=failure,
                    )
                else:
                    patcher = mock.patch(
                        "tiny_corpus_workbench.extractors.docling.preflight",
                        side_effect=failure,
                    )
                with patcher:
                    code, stdout, stderr = self.invoke(
                        "observe", str(MARKDOWN_FIXTURE)
                    )
                self.assertEqual(code, 6)
                self.assertEqual(stdout, "")
                self.assertIn("preflight", stderr)
                capture.assert_not_called()

    def test_missing_docling_serialization_apis_fail_before_capture(self) -> None:
        for method in ("save_as_json", "save_as_markdown", "model_dump"):
            with self.subTest(method=method), mock.patch.object(
                docling_adapter.DoclingDocument, method, None
            ), mock.patch.object(
                SourceSnapshot, "capture", autospec=True
            ) as capture:
                code, stdout, stderr = self.invoke(
                    "observe", str(MARKDOWN_FIXTURE)
                )
                self.assertEqual(code, 6)
                self.assertEqual(stdout, "")
                self.assertIn("preflight", stderr)
                capture.assert_not_called()

    def test_non_cpython_or_non_312_runtime_fails_before_capture(self) -> None:
        cases = (
            mock.patch(
                "tiny_corpus_workbench.cli.platform.python_implementation",
                return_value="PyPy",
            ),
            mock.patch(
                "tiny_corpus_workbench.cli.sys.version_info", (3, 13, 0)
            ),
        )
        for index, runtime_patch in enumerate(cases):
            with self.subTest(index=index), runtime_patch, mock.patch.object(
                SourceSnapshot, "capture", autospec=True
            ) as capture:
                code, stdout, stderr = self.invoke(
                    "observe", str(MARKDOWN_FIXTURE)
                )
                self.assertEqual(code, 6)
                self.assertEqual(stdout, "")
                self.assertIn("CPython 3.12", stderr)
                capture.assert_not_called()

    def test_pdf_model_changes_between_inventories_fail(self) -> None:
        operations = ("add", "remove", "bytes", "replace", "symlink")
        for operation in operations:
            with self.subTest(operation=operation), tempfile.TemporaryDirectory() as directory:
                root = Path(directory)
                models = root / "models"
                create_models(models)
                required = models / REQUIRED_MODEL_FILES[0]

                def mutate_models(source, destination, model_root):
                    result = fake_docling(source, destination, model_root)
                    if operation == "add":
                        (models / "added.bin").write_bytes(b"added")
                    elif operation == "remove":
                        required.unlink()
                    elif operation == "bytes":
                        required.write_bytes(b"changed")
                    elif operation == "replace":
                        replacement = models / "replacement"
                        replacement.write_bytes(required.read_bytes())
                        replacement.replace(required)
                    else:
                        (models / "new-link").symlink_to(required)
                    return result

                with mock.patch(
                    "tiny_corpus_workbench.extractors.docling.convert",
                    wraps=mutate_models,
                ), mock.patch(
                    "tiny_corpus_workbench.extractors.markitdown.convert",
                    wraps=fake_markitdown,
                ):
                    code, stdout, stderr = self.invoke(
                        "observe",
                        str(PDF_FIXTURE),
                        "--output-root",
                        str(root / "output"),
                        "--docling-artifacts",
                        str(models),
                    )
                self.assertEqual(code, 5)
                self.assertEqual(stdout, "")
                self.assertIn("model inventory changed", stderr)
                self.assertEqual(list((root / "output").glob("*/*")), [])

    def test_non_pdf_does_not_inspect_model_files(self) -> None:
        calls = []

        def record_inventory(root, *, required):
            calls.append(required)
            return {
                "required": False,
                "path": str(root.absolute()),
                "inventory_hash": None,
                "files": [],
            }

        with tempfile.TemporaryDirectory() as directory:
            docling_patch, markitdown_patch = self.adapters()
            with docling_patch, markitdown_patch, mock.patch(
                "tiny_corpus_workbench.cli.inventory_models",
                side_effect=record_inventory,
            ), mock.patch(
                "tiny_corpus_workbench.cli.model_filesystem_identity"
            ) as filesystem_identity:
                code, _, _ = self.invoke(
                    "observe",
                    str(MARKDOWN_FIXTURE),
                    "--output-root",
                    directory,
                    "--docling-artifacts",
                    str(Path(directory) / "irrelevant"),
                )
            self.assertEqual(code, 0)
            self.assertEqual(calls, [False])
            filesystem_identity.assert_not_called()

    def test_pdf_model_becoming_unreadable_is_integrity_failure(self) -> None:
        calls = 0

        def unreadable_on_second_inventory(root, *, required):
            nonlocal calls
            calls += 1
            if calls == 2:
                raise RuntimeContractError("Docling model artifacts are unreadable")
            return inventory_models(root, required=required)

        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            models = root / "models"
            create_models(models)
            docling_patch, markitdown_patch = self.adapters()
            with docling_patch, markitdown_patch, mock.patch(
                "tiny_corpus_workbench.cli.inventory_models",
                side_effect=unreadable_on_second_inventory,
            ):
                code, stdout, stderr = self.invoke(
                    "observe",
                    str(PDF_FIXTURE),
                    "--output-root",
                    str(root / "output"),
                    "--docling-artifacts",
                    str(models),
                )
            self.assertEqual(code, 5)
            self.assertEqual(stdout, "")
            self.assertIn("model inventory changed", stderr)
            self.assertEqual(list((root / "output").glob("*/*")), [])

    def test_two_concurrent_observations_use_independent_private_paths(self) -> None:
        seen: list[Path] = []
        lock = threading.Lock()

        def record_docling(source, destination, model_root):
            with lock:
                seen.append(source)
            return fake_docling(source, destination, model_root)

        with tempfile.TemporaryDirectory() as directory, mock.patch(
            "tiny_corpus_workbench.extractors.docling.convert",
            wraps=record_docling,
        ), mock.patch(
            "tiny_corpus_workbench.extractors.markitdown.convert",
            wraps=fake_markitdown,
        ):
            with ThreadPoolExecutor(max_workers=2) as executor:
                futures = [
                    executor.submit(
                        cli.observe,
                        str(MARKDOWN_FIXTURE),
                        Path(directory),
                        Path("unused"),
                    )
                    for _ in range(2)
                ]
                results = [future.result() for future in futures]
        self.assertEqual([int(code) for code, _ in results], [0, 0])
        self.assertEqual(len({published for _, published in results}), 2)
        self.assertEqual(len(set(seen)), 2)
        self.assertTrue(all(not path.exists() for path in seen))


if __name__ == "__main__":
    unittest.main()
