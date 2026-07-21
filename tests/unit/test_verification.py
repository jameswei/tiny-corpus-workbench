from __future__ import annotations

import hashlib
import io
import json
import os
import shutil
import tempfile
import unittest
from contextlib import redirect_stderr, redirect_stdout
from pathlib import Path
from unittest import mock

from jsonschema import Draft202012Validator

from tiny_corpus_workbench import cli
from tiny_corpus_workbench.artifacts import REQUIRED_MODEL_FILES
from tiny_corpus_workbench.domain import RuntimeContractError


SOURCE = Path("fixtures/golden/policy-memo.md")
PDF_SOURCE = Path("fixtures/golden/policy-memo.pdf")
RESULT_SCHEMA = Path(
    "src/tiny_corpus_workbench/schemas/verification-result-v0.1.schema.json"
)


def fake_docling(source: Path, destination: Path, model_root: Path):
    destination.mkdir(parents=True)
    (destination / "document.json").write_text(
        '{"schema_name":"DoclingDocument","version":"1.10.0"}\n', "utf-8"
    )
    (destination / "document.md").write_text("# view\n", "utf-8")
    return "success", {"name": "DoclingDocument", "version": "1.10.0"}


def partial_docling(source: Path, destination: Path, model_root: Path):
    _, schema = fake_docling(source, destination, model_root)
    return "partial_success", schema


def fake_markitdown(source: Path, destination: Path):
    destination.mkdir(parents=True)
    (destination / "document.md").write_text("# view\n", "utf-8")


def fail(*args, **kwargs):
    raise RuntimeError("conversion failed")


def create_models(root: Path) -> None:
    for relative in REQUIRED_MODEL_FILES:
        path = root / relative
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(relative.encode("utf-8"))


def snapshot(root: Path) -> dict[str, tuple[int, int, bytes]]:
    return {
        path.relative_to(root).as_posix(): (
            path.stat().st_mode,
            path.stat().st_mtime_ns,
            path.read_bytes(),
        )
        for path in sorted(root.rglob("*"))
        if path.is_file()
    }


class VerificationTests(unittest.TestCase):
    def invoke(self, *arguments: str) -> tuple[int, str, str]:
        stdout, stderr = io.StringIO(), io.StringIO()
        with redirect_stdout(stdout), redirect_stderr(stderr):
            code = cli.main(list(arguments))
        return code, stdout.getvalue(), stderr.getvalue()

    def observation(
        self,
        root: Path,
        docling=fake_docling,
        markitdown=fake_markitdown,
        source: Path = SOURCE,
        models: Path = Path("unused"),
    ) -> tuple[int, Path]:
        with mock.patch(
            "tiny_corpus_workbench.extractors.docling.convert", side_effect=docling
        ), mock.patch(
            "tiny_corpus_workbench.extractors.markitdown.convert",
            side_effect=markitdown,
        ):
            code, published = cli.observe(str(source), root, models)
        return int(code), published

    def verify(self, root: Path, *extra: str) -> tuple[int, dict, str, str]:
        code, stdout, stderr = self.invoke("verify", str(root), *extra)
        report = json.loads(stdout) if stdout else {}
        return code, report, stdout, stderr

    def test_success_partial_and_failed_observations_verify(self) -> None:
        cases = ((fake_docling, fake_markitdown), (partial_docling, fake_markitdown), (fail, fail))
        with tempfile.TemporaryDirectory() as directory:
            for index, (docling, markitdown) in enumerate(cases):
                with self.subTest(index=index):
                    _, published = self.observation(
                        Path(directory) / str(index), docling, markitdown
                    )
                    code, report, stdout, stderr = self.verify(published)
                    self.assertEqual(code, 0)
                    self.assertEqual(stderr, "")
                    self.assertEqual(len(stdout.splitlines()), 1)
                    self.assertEqual(
                        report["artifact_integrity"],
                        {"issues": [], "status": "VERIFIED"},
                    )
                    schema = json.loads(RESULT_SCHEMA.read_text("utf-8"))
                    Draft202012Validator(schema).validate(report)

    def test_verifier_detects_file_corruption_shapes(self) -> None:
        operations = ("missing", "extra", "edited", "truncated", "symlink", "special")
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            _, baseline = self.observation(root / "baseline")
            for operation in operations:
                with self.subTest(operation=operation):
                    copied = root / operation / baseline.name
                    copied.parent.mkdir()
                    shutil.copytree(baseline, copied)
                    target = copied / "docling/document.md"
                    if operation == "missing":
                        target.unlink()
                    elif operation == "extra":
                        (copied / "extra.bin").write_bytes(b"extra")
                    elif operation == "edited":
                        target.write_text("# edited\n", "utf-8")
                    elif operation == "truncated":
                        target.write_bytes(b"")
                    elif operation == "symlink":
                        target.unlink()
                        target.symlink_to(copied / "comparison.json")
                    else:
                        target.unlink()
                        os.mkfifo(target)
                    code, report, _, stderr = self.verify(copied)
                    self.assertEqual(code, 5)
                    self.assertEqual(stderr, "")
                    self.assertEqual(
                        report["artifact_integrity"]["status"],
                        "INTEGRITY_MISMATCH",
                    )

    def test_invalid_json_schema_identity_and_references_are_broken(self) -> None:
        operations = (
            "manifest-json",
            "manifest-schema",
            "comparison-json",
            "comparison-reference",
            "comparison-view",
            "observation-id",
            "run-id",
        )
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            _, baseline = self.observation(root / "baseline")
            for operation in operations:
                with self.subTest(operation=operation):
                    name = "wrong-run-id" if operation == "run-id" else baseline.name
                    copied = root / operation / name
                    copied.parent.mkdir()
                    shutil.copytree(baseline, copied)
                    manifest_path = copied / "manifest.json"
                    comparison_path = copied / "comparison.json"
                    if operation == "manifest-json":
                        manifest_path.write_text("{", "utf-8")
                    elif operation == "manifest-schema":
                        manifest = json.loads(manifest_path.read_text("utf-8"))
                        manifest["unexpected"] = True
                        manifest_path.write_text(json.dumps(manifest), "utf-8")
                    elif operation == "comparison-json":
                        comparison_path.write_text("{", "utf-8")
                    elif operation == "comparison-reference":
                        comparison = json.loads(comparison_path.read_text("utf-8"))
                        comparison["observation_id"] = "0" * 64
                        comparison_path.write_text(json.dumps(comparison), "utf-8")
                    elif operation == "comparison-view":
                        comparison = json.loads(comparison_path.read_text("utf-8"))
                        comparison["views"]["docling"]["normalized_sha256"] = "0" * 64
                        comparison_path.write_text(json.dumps(comparison), "utf-8")
                        manifest = json.loads(manifest_path.read_text("utf-8"))
                        raw = comparison_path.read_bytes()
                        manifest["comparison"]["size"] = len(raw)
                        manifest["comparison"]["sha256"] = hashlib.sha256(raw).hexdigest()
                        manifest_path.write_text(json.dumps(manifest), "utf-8")
                    elif operation == "observation-id":
                        manifest = json.loads(manifest_path.read_text("utf-8"))
                        manifest["observation_id"] = "0" * 64
                        manifest_path.write_text(json.dumps(manifest), "utf-8")
                    code, report, _, stderr = self.verify(copied)
                    self.assertEqual(code, 5)
                    self.assertEqual(stderr, "")
                    self.assertEqual(report["artifact_integrity"]["status"], "BROKEN")

    def test_verifier_does_not_change_observation_bytes_modes_or_mtimes(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            _, published = self.observation(Path(directory))
            before = snapshot(published)
            code, _, _, _ = self.verify(published)
            self.assertEqual(code, 0)
            self.assertEqual(snapshot(published), before)

    def test_verifier_operates_when_extractor_imports_are_broken(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            _, published = self.observation(Path(directory))
            with mock.patch(
                "tiny_corpus_workbench.cli.importlib.import_module",
                side_effect=ImportError("extractors broken"),
            ):
                code, report, _, stderr = self.verify(published)
            self.assertEqual(code, 0)
            self.assertEqual(stderr, "")
            self.assertEqual(report["artifact_integrity"]["status"], "VERIFIED")

    def test_source_advisory_states_do_not_change_integrity(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            _, published = self.observation(root / "observation")
            changed = root / "changed.md"
            changed.write_text("# changed\n", "utf-8")
            missing = root / "missing.md"
            error = root / "directory.md"
            error.mkdir()
            cases = (
                ((), "NOT_CHECKED"),
                (("--source", str(SOURCE)), "MATCH"),
                (("--source", str(changed)), "CHANGED"),
                (("--source", str(missing)), "MISSING"),
                (("--source", str(error)), "ERROR"),
            )
            for arguments, expected in cases:
                with self.subTest(expected=expected):
                    code, report, _, _ = self.verify(published, *arguments)
                    self.assertEqual(code, 0)
                    self.assertEqual(report["artifact_integrity"]["status"], "VERIFIED")
                    self.assertEqual(report["source_state"]["status"], expected)

    def test_model_advisory_states_do_not_change_integrity(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            models = root / "models"
            create_models(models)
            _, published = self.observation(
                root / "pdf-observation", source=PDF_SOURCE, models=models
            )
            code, report, _, _ = self.verify(published)
            self.assertEqual(code, 0)
            self.assertEqual(report["model_state"]["status"], "NOT_CHECKED")

            code, report, _, _ = self.verify(
                published, "--docling-artifacts", str(models)
            )
            self.assertEqual(code, 0)
            self.assertEqual(report["model_state"]["status"], "MATCH")

            target = models / REQUIRED_MODEL_FILES[0]
            original = target.read_bytes()
            target.write_bytes(b"changed")
            code, report, _, _ = self.verify(
                published, "--docling-artifacts", str(models)
            )
            self.assertEqual(code, 0)
            self.assertEqual(report["model_state"]["status"], "CHANGED")
            target.write_bytes(original)

            code, report, _, _ = self.verify(
                published, "--docling-artifacts", str(root / "missing")
            )
            self.assertEqual(code, 0)
            self.assertEqual(report["model_state"]["status"], "MISSING")

            invalid = root / "invalid-models"
            invalid.mkdir()
            code, report, _, _ = self.verify(
                published, "--docling-artifacts", str(invalid)
            )
            self.assertEqual(code, 0)
            self.assertEqual(report["model_state"]["status"], "ERROR")

            _, markdown = self.observation(root / "markdown-observation")
            code, report, _, _ = self.verify(
                markdown, "--docling-artifacts", str(models)
            )
            self.assertEqual(code, 0)
            self.assertEqual(report["model_state"]["status"], "NOT_APPLICABLE")

    def test_missing_optional_targets_are_reports_but_bad_root_is_usage_error(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            missing_root = Path(directory) / "missing-observation"
            code, stdout, stderr = self.invoke("verify", str(missing_root))
            self.assertEqual(code, 2)
            self.assertEqual(stdout, "")
            self.assertTrue(stderr)

            observation = Path(directory) / "empty-observation"
            observation.mkdir()
            code, report, _, stderr = self.verify(
                observation,
                "--source",
                str(Path(directory) / "missing-source"),
                "--docling-artifacts",
                str(Path(directory) / "missing-models"),
            )
            self.assertEqual(code, 5)
            self.assertEqual(stderr, "")
            self.assertEqual(report["source_state"]["status"], "MISSING")
            self.assertEqual(report["model_state"]["status"], "MISSING")

    def test_verifier_runtime_and_unexpected_failures_have_exact_streams(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            original_import = __import__

            def fail_verifier_import(name, *args, **kwargs):
                if name == "tiny_corpus_workbench.verification":
                    raise ImportError("jsonschema unavailable")
                return original_import(name, *args, **kwargs)

            with mock.patch("builtins.__import__", side_effect=fail_verifier_import):
                code, stdout, stderr = self.invoke("verify", str(root))
            self.assertEqual(code, 6)
            self.assertEqual(stdout, "")
            self.assertEqual(stderr, "bundled verifier runtime is unavailable\n")

            with mock.patch(
                "tiny_corpus_workbench.verification._schema",
                side_effect=RuntimeContractError("schema runtime unavailable"),
            ):
                code, stdout, stderr = self.invoke("verify", str(root))
            self.assertEqual(code, 6)
            self.assertEqual(stdout, "")
            self.assertEqual(stderr, "schema runtime unavailable\n")

            with mock.patch(
                "tiny_corpus_workbench.verification.verify_observation",
                side_effect=RuntimeError("unexpected\nverifier failure"),
            ):
                code, stdout, stderr = self.invoke("verify", str(root))
            self.assertEqual(code, 1)
            self.assertEqual(stdout, "")
            self.assertEqual(
                stderr, "internal verifier failure: unexpected verifier failure\n"
            )


if __name__ == "__main__":
    unittest.main()
