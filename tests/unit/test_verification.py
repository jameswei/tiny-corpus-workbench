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
from tiny_corpus_workbench.artifacts import (
    REQUIRED_MODEL_FILES,
    canonical_json,
    compute_observation_id,
)
from tiny_corpus_workbench.domain import RuntimeContractError
from tiny_corpus_workbench.runtime import RUNTIME_DEPENDENCIES


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


def rewrite_observation_identity(root: Path, manifest: dict) -> None:
    observation_id = compute_observation_id(
        manifest["source"],
        manifest["runtime"]["dependencies"],
        manifest["configurations"],
        manifest["runtime"]["lockfile"]["sha256"],
        manifest["models"]["inventory_hash"],
    )
    manifest["observation_id"] = observation_id
    comparison_path = root / "comparison.json"
    comparison = json.loads(comparison_path.read_text("utf-8"))
    comparison["observation_id"] = observation_id
    comparison_bytes = canonical_json(comparison)
    comparison_path.write_bytes(comparison_bytes)
    manifest["comparison"]["size"] = len(comparison_bytes)
    manifest["comparison"]["sha256"] = hashlib.sha256(comparison_bytes).hexdigest()
    (root / "manifest.json").write_bytes(canonical_json(manifest))


def write_comparison_with_descriptor(root: Path, comparison: object) -> None:
    comparison_bytes = canonical_json(comparison)
    (root / "comparison.json").write_bytes(comparison_bytes)
    manifest_path = root / "manifest.json"
    manifest = json.loads(manifest_path.read_text("utf-8"))
    manifest["comparison"]["size"] = len(comparison_bytes)
    manifest["comparison"]["sha256"] = hashlib.sha256(
        comparison_bytes
    ).hexdigest()
    manifest_path.write_bytes(canonical_json(manifest))


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
                    if index == 2:
                        manifest = json.loads(
                            (published / "manifest.json").read_text("utf-8")
                        )
                        self.assertEqual(
                            manifest["docling_document_schema"],
                            {"name": None, "version": None, "compatibility": None},
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

    def test_manifest_root_json_types_complete_as_broken(self) -> None:
        values = (
            ("null", None),
            ("boolean", True),
            ("number", 1),
            ("string", "manifest"),
            ("array", []),
            ("wrong-object", {}),
        )
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            _, baseline = self.observation(root / "baseline")
            advisory_root = root / "advisory"
            advisory_root.mkdir()
            for label, value in values:
                with self.subTest(label=label):
                    copied = root / label / baseline.name
                    copied.parent.mkdir()
                    shutil.copytree(baseline, copied)
                    (copied / "manifest.json").write_bytes(canonical_json(value))
                    code, report, stdout, stderr = self.verify(
                        copied,
                        "--source",
                        str(SOURCE),
                        "--docling-artifacts",
                        str(advisory_root),
                    )
                    self.assertEqual(code, 5)
                    self.assertEqual(stderr, "")
                    self.assertEqual(len(stdout.splitlines()), 1)
                    self.assertEqual(
                        report["artifact_integrity"]["status"], "BROKEN"
                    )
                    self.assertEqual(report["source_state"]["status"], "ERROR")
                    self.assertEqual(report["model_state"]["status"], "ERROR")

    def test_malformed_manifest_nested_types_complete_with_safe_advisories(self) -> None:
        cases = (
            ("source-null", ("source",), None),
            ("runtime-boolean", ("runtime",), True),
            ("models-number", ("models",), 1),
            ("extractors-string", ("extractors",), "extractors"),
            ("comparison-array", ("comparison",), []),
            ("source-wrong-object", ("source",), {}),
            ("dependencies-array", ("runtime", "dependencies"), []),
            ("extractor-elements", ("extractors",), [None, None]),
            ("model-files-object", ("models", "files"), {}),
            ("comparison-wrong-object", ("comparison",), {}),
        )
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            _, baseline = self.observation(root / "baseline")
            advisory_root = root / "advisory"
            advisory_root.mkdir()
            for label, path, value in cases:
                with self.subTest(label=label):
                    copied = root / label / baseline.name
                    copied.parent.mkdir()
                    shutil.copytree(baseline, copied)
                    manifest_path = copied / "manifest.json"
                    manifest = json.loads(manifest_path.read_text("utf-8"))
                    target = manifest
                    for part in path[:-1]:
                        target = target[part]
                    target[path[-1]] = value
                    manifest_path.write_bytes(canonical_json(manifest))

                    code, report, stdout, stderr = self.verify(
                        copied,
                        "--source",
                        str(SOURCE),
                        "--docling-artifacts",
                        str(advisory_root),
                    )
                    self.assertEqual(code, 5)
                    self.assertEqual(stderr, "")
                    self.assertEqual(len(stdout.splitlines()), 1)
                    self.assertEqual(
                        report["artifact_integrity"]["status"], "BROKEN"
                    )
                    expected_source = (
                        "ERROR" if path[0] == "source" else "MATCH"
                    )
                    expected_model = (
                        "ERROR" if label == "models-number" else "NOT_APPLICABLE"
                    )
                    self.assertEqual(
                        report["source_state"]["status"], expected_source
                    )
                    self.assertEqual(
                        report["model_state"]["status"], expected_model
                    )

    def test_invalid_manifest_preserves_missing_and_not_checked_advisories(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            _, baseline = self.observation(root / "baseline")
            (baseline / "manifest.json").write_bytes(canonical_json(None))

            code, report, _, stderr = self.verify(baseline)
            self.assertEqual(code, 5)
            self.assertEqual(stderr, "")
            self.assertEqual(report["source_state"]["status"], "NOT_CHECKED")
            self.assertEqual(report["model_state"]["status"], "NOT_CHECKED")

            code, report, _, stderr = self.verify(
                baseline,
                "--source",
                str(root / "missing.md"),
                "--docling-artifacts",
                str(root / "missing-models"),
            )
            self.assertEqual(code, 5)
            self.assertEqual(stderr, "")
            self.assertEqual(report["source_state"]["status"], "MISSING")
            self.assertEqual(report["model_state"]["status"], "MISSING")

    def test_comparison_root_and_nested_json_types_complete_as_broken(self) -> None:
        top_values = (
            ("null", None),
            ("boolean", False),
            ("number", 1),
            ("string", "comparison"),
            ("array", []),
            ("wrong-object", {}),
        )
        nested_values = (
            ("source-null", ("source",), None),
            ("views-boolean", ("views",), True),
            ("deltas-number", ("deltas",), 1),
            ("anchors-string", ("anchors",), "anchors"),
            ("docling-view-array", ("views", "docling"), []),
            ("source-wrong-object", ("source",), {}),
            ("views-wrong-object", ("views",), {}),
        )
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            _, baseline = self.observation(root / "baseline")
            for label, value in top_values:
                with self.subTest(kind="root", label=label):
                    copied = root / f"root-{label}" / baseline.name
                    copied.parent.mkdir()
                    shutil.copytree(baseline, copied)
                    write_comparison_with_descriptor(copied, value)
                    code, report, stdout, stderr = self.verify(copied)
                    self.assertEqual(code, 5)
                    self.assertEqual(stderr, "")
                    self.assertEqual(len(stdout.splitlines()), 1)
                    self.assertEqual(
                        report["artifact_integrity"]["status"], "BROKEN"
                    )

            for label, path, value in nested_values:
                with self.subTest(kind="nested", label=label):
                    copied = root / f"nested-{label}" / baseline.name
                    copied.parent.mkdir()
                    shutil.copytree(baseline, copied)
                    comparison = json.loads(
                        (copied / "comparison.json").read_text("utf-8")
                    )
                    target = comparison
                    for part in path[:-1]:
                        target = target[part]
                    target[path[-1]] = value
                    write_comparison_with_descriptor(copied, comparison)
                    code, report, stdout, stderr = self.verify(copied)
                    self.assertEqual(code, 5)
                    self.assertEqual(stderr, "")
                    self.assertEqual(len(stdout.splitlines()), 1)
                    self.assertEqual(
                        report["artifact_integrity"]["status"], "BROKEN"
                    )

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

            equivalent_models = root / "equivalent-models"
            shutil.copytree(models, equivalent_models)
            code, report, _, _ = self.verify(
                published, "--docling-artifacts", str(equivalent_models)
            )
            self.assertEqual(code, 0)
            self.assertEqual(report["artifact_integrity"]["status"], "VERIFIED")
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
            for model_path in (
                models,
                root / "missing-non-pdf-models",
                invalid,
            ):
                with self.subTest(non_pdf_model_path=model_path):
                    code, report, _, _ = self.verify(
                        markdown, "--docling-artifacts", str(model_path)
                    )
                    self.assertEqual(code, 0)
                    self.assertEqual(
                        report["artifact_integrity"]["status"], "VERIFIED"
                    )
                    self.assertEqual(
                        report["model_state"]["status"], "NOT_APPLICABLE"
                    )

    def test_schema_valid_manifest_contract_mutations_are_broken(self) -> None:
        cases = {
            "docling-version": "REFERENCE_MISMATCH",
            "markitdown-version": "REFERENCE_MISMATCH",
            "docling-upstream": "STATUS_MISMATCH",
            "docling-status": "STATUS_MISMATCH",
            "docling-failed": "STATUS_MISMATCH",
            "markitdown-failed": "STATUS_MISMATCH",
            "models-required": "STATUS_MISMATCH",
            "model-error-runtime": "STATUS_MISMATCH",
            "markitdown-error-code": "STATUS_MISMATCH",
            "artifact-role": "REFERENCE_MISMATCH",
            "artifact-media": "REFERENCE_MISMATCH",
            "artifact-path": "REFERENCE_MISMATCH",
            "comparison-status": "STATUS_MISMATCH",
            "comparison-size": "REFERENCE_MISMATCH",
            "comparison-hash": "REFERENCE_MISMATCH",
        }
        schema = json.loads(
            Path(
                "src/tiny_corpus_workbench/schemas/preparation-manifest-v0.1.schema.json"
            ).read_text("utf-8")
        )
        validator = Draft202012Validator(schema)
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            _, baseline = self.observation(root / "baseline")
            for operation, expected_code in cases.items():
                with self.subTest(operation=operation):
                    copied = root / operation / baseline.name
                    copied.parent.mkdir()
                    shutil.copytree(baseline, copied)
                    manifest_path = copied / "manifest.json"
                    manifest = json.loads(manifest_path.read_text("utf-8"))
                    if operation == "docling-version":
                        manifest["extractors"][0]["version"] = "0.1.6"
                    elif operation == "markitdown-version":
                        manifest["extractors"][1]["version"] = "2.113.0"
                    elif operation == "docling-upstream":
                        manifest["extractors"][0]["upstream_status"] = (
                            "partial_success"
                        )
                    elif operation == "docling-status":
                        manifest["extractors"][0]["status"] = "PARTIAL_SUCCESS"
                    elif operation == "docling-failed":
                        manifest["extractors"][0]["status"] = "FAILED"
                    elif operation == "markitdown-failed":
                        manifest["extractors"][1]["status"] = "FAILED"
                    elif operation == "models-required":
                        manifest["models"]["required"] = True
                    elif operation == "model-error-runtime":
                        manifest["extractors"][0]["error"] = {
                            "code": "MODEL_ARTIFACTS_MISSING",
                            "message": "mutated runtime state",
                        }
                    elif operation == "markitdown-error-code":
                        manifest["extractors"][1]["error"] = {
                            "code": "DOCLING_CONVERSION_FAILED",
                            "message": "wrong extractor error",
                        }
                    elif operation == "artifact-role":
                        manifest["extractors"][0]["artifacts"][0]["role"] = (
                            "docling-markdown"
                        )
                    elif operation == "artifact-media":
                        manifest["extractors"][0]["artifacts"][0][
                            "media_type"
                        ] = "text/markdown"
                    elif operation == "artifact-path":
                        manifest["extractors"][0]["artifacts"][0]["path"] = (
                            "markitdown/document.md"
                        )
                    elif operation == "comparison-status":
                        manifest["comparison"]["status"] = "INCOMPLETE"
                    elif operation == "comparison-size":
                        manifest["comparison"]["size"] += 1
                    else:
                        manifest["comparison"]["sha256"] = "0" * 64
                    validator.validate(manifest)
                    manifest_path.write_text(json.dumps(manifest), "utf-8")

                    code, report, stdout, stderr = self.verify(copied)
                    self.assertEqual(code, 5)
                    self.assertEqual(stderr, "")
                    self.assertEqual(len(stdout.splitlines()), 1)
                    self.assertEqual(
                        report["artifact_integrity"]["status"], "BROKEN"
                    )
                    self.assertIn(
                        expected_code,
                        {
                            issue["code"]
                            for issue in report["artifact_integrity"]["issues"]
                        },
                    )

    def test_every_runtime_dependency_mapping_mutation_is_broken(self) -> None:
        cases = []
        for name in RUNTIME_DEPENDENCIES:
            cases.append((f"changed-{name}", "change", name))
            cases.append((f"missing-{name}", "remove", name))
        cases.append(("unexpected-dependency", "add", "unexpected"))

        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            _, baseline = self.observation(root / "baseline")
            for operation, mutation, name in cases:
                with self.subTest(operation=operation):
                    copied = root / operation / baseline.name
                    copied.parent.mkdir()
                    shutil.copytree(baseline, copied)
                    manifest_path = copied / "manifest.json"
                    manifest = json.loads(manifest_path.read_text("utf-8"))
                    dependencies = manifest["runtime"]["dependencies"]
                    if mutation == "change":
                        dependencies[name] = "9.9.9"
                    elif mutation == "remove":
                        del dependencies[name]
                    else:
                        dependencies[name] = "9.9.9"
                    rewrite_observation_identity(copied, manifest)

                    code, report, stdout, stderr = self.verify(copied)
                    self.assertEqual(code, 5)
                    self.assertEqual(stderr, "")
                    self.assertEqual(len(stdout.splitlines()), 1)
                    self.assertEqual(
                        report["artifact_integrity"]["status"], "BROKEN"
                    )
                    self.assertIn(
                        "MANIFEST_INVALID",
                        {
                            issue["code"]
                            for issue in report["artifact_integrity"]["issues"]
                        },
                    )
                    if operation == "changed-docling-core":
                        self.assertEqual(
                            {
                                issue["code"]
                                for issue in report["artifact_integrity"]["issues"]
                            },
                            {"MANIFEST_INVALID"},
                        )

    def test_pdf_model_runtime_manifest_mutations_are_broken(self) -> None:
        schema = json.loads(
            Path(
                "src/tiny_corpus_workbench/schemas/preparation-manifest-v0.1.schema.json"
            ).read_text("utf-8")
        )
        validator = Draft202012Validator(schema)
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            models = root / "models"
            create_models(models)
            _, complete = self.observation(
                root / "complete", source=PDF_SOURCE, models=models
            )
            _, missing = self.observation(
                root / "missing", source=PDF_SOURCE, models=root / "absent"
            )
            cases = ((complete, "required"), (missing, "runtime-error"))
            for baseline, operation in cases:
                with self.subTest(operation=operation):
                    copied = root / operation / baseline.name
                    copied.parent.mkdir()
                    shutil.copytree(baseline, copied)
                    manifest_path = copied / "manifest.json"
                    manifest = json.loads(manifest_path.read_text("utf-8"))
                    if operation == "required":
                        manifest["models"]["required"] = False
                    else:
                        manifest["extractors"][0]["error"]["code"] = (
                            "DOCLING_CONVERSION_FAILED"
                        )
                    validator.validate(manifest)
                    manifest_path.write_text(json.dumps(manifest), "utf-8")

                    code, report, _, stderr = self.verify(copied)
                    self.assertEqual(code, 5)
                    self.assertEqual(stderr, "")
                    self.assertEqual(
                        report["artifact_integrity"]["status"], "BROKEN"
                    )
                    self.assertIn(
                        "STATUS_MISMATCH",
                        {
                            issue["code"]
                            for issue in report["artifact_integrity"]["issues"]
                        },
                    )

    def test_structural_and_docling_schema_mutations_are_broken(self) -> None:
        cases = {
            "schema-name": ("success", "REFERENCE_MISMATCH"),
            "schema-version": ("success", "REFERENCE_MISMATCH"),
            "schema-compatibility": ("success", "MANIFEST_INVALID"),
            "runtime-implementation": ("success", "MANIFEST_INVALID"),
            "runtime-version": ("success", "MANIFEST_INVALID"),
            "invalid-timestamp": ("success", "MANIFEST_INVALID"),
            "impossible-date": ("success", "MANIFEST_INVALID"),
            "missing-timezone": ("success", "MANIFEST_INVALID"),
            "invalid-offset": ("success", "MANIFEST_INVALID"),
            "negative-duration": ("success", "MANIFEST_INVALID"),
            "fractional-duration": ("success", "MANIFEST_INVALID"),
            "multiline-error": ("failed", "MANIFEST_INVALID"),
            "trailing-newline-error": ("failed", "MANIFEST_INVALID"),
            "control-error": ("failed", "MANIFEST_INVALID"),
            "empty-error": ("failed", "MANIFEST_INVALID"),
            "overlong-error": ("failed", "MANIFEST_INVALID"),
            "failed-schema-claim": ("failed", "REFERENCE_MISMATCH"),
            "document-schema-name": ("success", "REFERENCE_MISMATCH"),
            "document-schema-version": ("success", "REFERENCE_MISMATCH"),
            "document-invalid-json": ("success", "SCHEMA_INVALID"),
            "document-missing-identity": ("success", "SCHEMA_INVALID"),
        }
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            _, success = self.observation(root / "success")
            _, failed = self.observation(root / "failed", fail, fail)
            baselines = {"success": success, "failed": failed}
            for operation, (kind, expected_code) in cases.items():
                with self.subTest(operation=operation):
                    baseline = baselines[kind]
                    copied = root / operation / baseline.name
                    copied.parent.mkdir()
                    shutil.copytree(baseline, copied)
                    manifest_path = copied / "manifest.json"
                    manifest = json.loads(manifest_path.read_text("utf-8"))
                    if operation == "schema-name":
                        manifest["docling_document_schema"]["name"] = "Other"
                    elif operation == "schema-version":
                        manifest["docling_document_schema"]["version"] = "9.9.9"
                    elif operation == "schema-compatibility":
                        manifest["docling_document_schema"]["compatibility"] = (
                            "reloadable anywhere"
                        )
                    elif operation == "runtime-implementation":
                        manifest["runtime"]["implementation"] = "PyPy"
                    elif operation == "runtime-version":
                        manifest["runtime"]["python"] = "9.9.9"
                    elif operation == "invalid-timestamp":
                        manifest["created_at"] = "2026-99-99 12:00"
                    elif operation == "impossible-date":
                        manifest["created_at"] = "2026-02-30T12:00:00Z"
                    elif operation == "missing-timezone":
                        manifest["created_at"] = "2026-07-21T12:00:00"
                    elif operation == "invalid-offset":
                        manifest["created_at"] = "2026-07-21T12:00:00+24:00"
                    elif operation == "negative-duration":
                        manifest["extractors"][0]["duration_ms"] = -1
                    elif operation == "fractional-duration":
                        manifest["extractors"][1]["duration_ms"] = 1.5
                    elif operation == "multiline-error":
                        manifest["extractors"][0]["error"]["message"] = (
                            "first line\nsecond line"
                        )
                    elif operation == "trailing-newline-error":
                        manifest["extractors"][0]["error"]["message"] = (
                            "trailing newline\n"
                        )
                    elif operation == "control-error":
                        manifest["extractors"][1]["error"]["message"] = (
                            "control\u0001message"
                        )
                    elif operation == "empty-error":
                        manifest["extractors"][0]["error"]["message"] = ""
                    elif operation == "overlong-error":
                        manifest["extractors"][0]["error"]["message"] = "x" * 501
                    elif operation == "failed-schema-claim":
                        manifest["docling_document_schema"]["name"] = (
                            "DoclingDocument"
                        )
                    else:
                        document_path = copied / "docling/document.json"
                        if operation == "document-invalid-json":
                            raw = b"{"
                        else:
                            document = json.loads(document_path.read_text("utf-8"))
                            if operation == "document-schema-name":
                                document["schema_name"] = "Other"
                            elif operation == "document-schema-version":
                                document["version"] = "9.9.9"
                            else:
                                del document["schema_name"]
                            raw = json.dumps(document).encode("utf-8")
                        document_path.write_bytes(raw)
                        descriptor = next(
                            item
                            for item in manifest["extractors"][0]["artifacts"]
                            if item["role"] == "docling-document-json"
                        )
                        descriptor["size"] = len(raw)
                        descriptor["sha256"] = hashlib.sha256(raw).hexdigest()
                    manifest_path.write_text(json.dumps(manifest), "utf-8")

                    code, report, stdout, stderr = self.verify(copied)
                    self.assertEqual(code, 5)
                    self.assertEqual(stderr, "")
                    self.assertEqual(len(stdout.splitlines()), 1)
                    self.assertEqual(
                        report["artifact_integrity"]["status"], "BROKEN"
                    )
                    self.assertIn(
                        expected_code,
                        {
                            issue["code"]
                            for issue in report["artifact_integrity"]["issues"]
                        },
                    )

    def test_valid_nonderivable_timestamp_change_remains_verified(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            _, baseline = self.observation(root / "baseline")
            copied = root / "valid-created-at" / baseline.name
            copied.parent.mkdir()
            shutil.copytree(baseline, copied)
            manifest_path = copied / "manifest.json"
            manifest = json.loads(manifest_path.read_text("utf-8"))
            manifest["created_at"] = "2000-01-01T00:00:00Z"
            manifest_path.write_text(json.dumps(manifest), "utf-8")

            code, report, _, stderr = self.verify(copied)
            self.assertEqual(code, 0)
            self.assertEqual(stderr, "")
            self.assertEqual(report["artifact_integrity"]["status"], "VERIFIED")

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
