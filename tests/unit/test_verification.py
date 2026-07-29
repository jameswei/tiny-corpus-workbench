from __future__ import annotations

import hashlib
import io
import json
import os
import shutil
import tempfile
import unittest
from contextlib import redirect_stderr, redirect_stdout
from dataclasses import FrozenInstanceError
from pathlib import Path
from unittest import mock

from tiny_corpus_workbench import cli
from tiny_corpus_workbench.artifacts import (
    REQUIRED_MODEL_FILES,
    canonical_json,
    compute_observation_id,
)
from tiny_corpus_workbench.domain import RuntimeContractError
from tiny_corpus_workbench.verification import verify_observation


SOURCE = Path("fixtures/golden/policy-memo.md")
PDF_SOURCE = Path("fixtures/golden/policy-memo.pdf")


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
        return code, json.loads(stdout) if stdout else {}, stdout, stderr

    def test_success_partial_and_failed_observations_verify(self) -> None:
        cases = (
            (fake_docling, fake_markitdown),
            (partial_docling, fake_markitdown),
            (fail, fail),
        )
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

    def test_records_and_results_keep_only_domain_evidence(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            _, published = self.observation(Path(directory))
            manifest = json.loads(
                (published / "manifest.json").read_text("utf-8")
            )
            comparison = json.loads(
                (published / "comparison.json").read_text("utf-8")
            )
            self.assertEqual(
                {
                    "record_type": manifest["record_type"],
                    "format_version": manifest["format_version"],
                },
                {"record_type": "observation", "format_version": 1},
            )
            self.assertNotIn("schema_version", manifest)
            self.assertNotIn("schema_version", comparison)
            self.assertEqual(
                set(manifest["docling_document_schema"]), {"name", "version"}
            )
            self.assertEqual(
                [item["name"] for item in manifest["extractors"]],
                ["docling", "markitdown"],
            )
            code, report, _, _ = self.verify(published)
            self.assertEqual(code, 0)
            self.assertNotIn("schema_version", report)

    def test_invalid_record_headers_exit_two_with_regeneration_guidance(
        self,
    ) -> None:
        with tempfile.TemporaryDirectory() as directory:
            _, baseline = self.observation(Path(directory) / "baseline")
            cases = (
                ("missing-record-type", lambda value: value.pop("record_type")),
                (
                    "missing-format-version",
                    lambda value: value.pop("format_version"),
                ),
                (
                    "boolean-format-version",
                    lambda value: value.update(format_version=True),
                ),
                (
                    "zero-format-version",
                    lambda value: value.update(format_version=0),
                ),
                (
                    "negative-format-version",
                    lambda value: value.update(format_version=-1),
                ),
                (
                    "unknown-format-version",
                    lambda value: value.update(format_version=2),
                ),
                (
                    "wrong-record-type",
                    lambda value: value.update(record_type="diagnosis"),
                ),
            )
            for name, mutate in cases:
                with self.subTest(name=name):
                    copied = Path(directory) / name / baseline.name
                    copied.parent.mkdir()
                    shutil.copytree(baseline, copied)
                    manifest_path = copied / "manifest.json"
                    manifest = json.loads(manifest_path.read_text("utf-8"))
                    mutate(manifest)
                    manifest_path.write_bytes(canonical_json(manifest))
                    code, stdout, stderr = self.invoke("verify", str(copied))
                    self.assertEqual(code, 2)
                    self.assertEqual(stdout, "")
                    self.assertIn("regenerate", stderr)

    def test_artifact_tampering_is_integrity_json(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            _, published = self.observation(Path(directory))
            (published / "docling/document.md").write_text("# tampered\n", "utf-8")
            code, report, stdout, stderr = self.verify(published)
            self.assertEqual(code, 5)
            self.assertEqual(stderr, "")
            self.assertEqual(len(stdout.splitlines()), 1)
            self.assertEqual(
                report["artifact_integrity"]["status"], "INTEGRITY_MISMATCH"
            )
            self.assertIn(
                "HASH_MISMATCH",
                {
                    issue["code"]
                    for issue in report["artifact_integrity"]["issues"]
                },
            )

    def test_domain_identity_changes_only_for_domain_evidence(self) -> None:
        source = {"sha256": "a" * 64, "size": 1, "media_type": "text/plain"}
        configurations = {"docling": {"mode": "a"}, "markitdown": {"mode": "b"}}
        extractors = [
            {"name": "docling", "version": "1"},
            {"name": "markitdown", "version": "2"},
        ]
        document_schema = {"name": "DoclingDocument", "version": "1.10.0"}

        def identity(**overrides):
            return compute_observation_id(
                overrides.get("source", source),
                overrides.get("configurations", configurations),
                overrides.get("model_inventory_hash"),
                overrides.get("extractors", extractors),
                overrides.get("document_schema", document_schema),
            )

        baseline = identity()
        self.assertNotEqual(
            baseline,
            identity(
                source={**source, "sha256": "b" * 64},
            ),
        )
        self.assertNotEqual(
            baseline,
            identity(
                configurations={
                    **configurations,
                    "docling": {"mode": "changed"},
                }
            ),
        )
        self.assertNotEqual(baseline, identity(model_inventory_hash="c" * 64))
        self.assertNotEqual(
            baseline,
            identity(
                extractors=[
                    {"name": "docling", "version": "9"},
                    extractors[1],
                ]
            ),
        )

    def test_checkout_and_runtime_metadata_do_not_affect_observation(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            original_cwd = Path.cwd()
            absolute_source = SOURCE.resolve()
            try:
                first_code, first = self.observation(
                    root / "first", source=absolute_source
                )
                sandbox = root / "different-cwd"
                sandbox.mkdir()
                (sandbox / "uv.lock").write_text("changed lock\n", "utf-8")
                (sandbox / "pyproject.toml").write_text(
                    "[project]\nname='other'\nversion='9.9.9'\n", "utf-8"
                )
                os.chdir(sandbox)
                second_code, second = self.observation(
                    root / "second", source=absolute_source
                )
            finally:
                os.chdir(original_cwd)
            self.assertEqual((first_code, second_code), (0, 0))
            first_manifest = json.loads(
                (first / "manifest.json").read_text("utf-8")
            )
            second_manifest = json.loads(
                (second / "manifest.json").read_text("utf-8")
            )
            first_comparison = json.loads(
                (first / "comparison.json").read_text("utf-8")
            )
            second_comparison = json.loads(
                (second / "comparison.json").read_text("utf-8")
            )
            self.assertEqual(
                first_manifest["source"]["fixture_id"],
                second_manifest["source"]["fixture_id"],
            )
            self.assertEqual(
                first_manifest["source"]["fixture_id"], "policy-memo-md"
            )
            self.assertEqual(
                first_manifest["source"]["key"],
                second_manifest["source"]["key"],
            )
            self.assertEqual(first_manifest["source"]["key"], "policy-memo-md")
            self.assertEqual(
                first_comparison["anchors"],
                second_comparison["anchors"],
            )
            self.assertNotEqual(first_comparison["anchors"], [])
            self.assertEqual(
                first_manifest["observation_id"],
                second_manifest["observation_id"],
            )

    def test_source_and_model_advisories_do_not_change_integrity(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            source = root / "source.md"
            source.write_text("# source\n", "utf-8")
            _, published = self.observation(root / "output", source=source)
            source.write_text("# changed\n", "utf-8")
            code, report, _, stderr = self.verify(
                published, "--source", str(source)
            )
            self.assertEqual(code, 0)
            self.assertEqual(stderr, "")
            self.assertEqual(report["source_state"]["status"], "CHANGED")
            self.assertEqual(report["model_state"]["status"], "NOT_CHECKED")

    def test_result_is_frozen_and_cli_stdout_matches_explicit_serializer(
        self,
    ) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            _, published = self.observation(root / "observations")
            matching = root / "matching.md"
            matching.write_bytes(SOURCE.read_bytes())
            changed = root / "changed.md"
            changed.write_text("# Changed\n", "utf-8")
            missing = root / "missing.md"
            invalid = root / "not-a-file"
            invalid.mkdir()

            result = verify_observation(published, matching)
            with self.assertRaises(FrozenInstanceError):
                result.observation_directory = "changed"

            for source, state in (
                (matching, "MATCH"),
                (changed, "CHANGED"),
                (missing, "MISSING"),
                (invalid, "ERROR"),
            ):
                with self.subTest(state=state):
                    expected = {
                        "observation_directory": str(published.resolve()),
                        "artifact_integrity": {
                            "status": "VERIFIED",
                            "issues": [],
                        },
                        "source_state": {"status": state},
                        "model_state": {"status": "NOT_CHECKED"},
                    }
                    code, stdout, stderr = self.invoke(
                        "verify",
                        str(published),
                        "--source",
                        str(source),
                    )
                    self.assertEqual(code, 0)
                    self.assertEqual(stderr, "")
                    self.assertEqual(
                        stdout,
                        json.dumps(
                            expected,
                            ensure_ascii=False,
                            sort_keys=True,
                            separators=(",", ":"),
                        )
                        + "\n",
                    )

    def test_verifier_is_read_only_and_needs_no_extractor_import(self) -> None:
        from tiny_corpus_workbench.verification import verify_observation

        with tempfile.TemporaryDirectory() as directory:
            _, published = self.observation(Path(directory))
            before = snapshot(published)
            with mock.patch(
                "builtins.__import__",
                side_effect=ImportError("extractors unavailable"),
            ):
                report = verify_observation(published)
            self.assertEqual(
                report.artifact_integrity.status, "VERIFIED"
            )
            self.assertEqual(snapshot(published), before)

    def test_pdf_model_inventory_is_verified(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            models = root / "models"
            create_models(models)
            _, published = self.observation(
                root / "output", source=PDF_SOURCE, models=models
            )
            code, report, _, _ = self.verify(
                published, "--docling-artifacts", str(models)
            )
            self.assertEqual(code, 0)
            self.assertEqual(report["model_state"]["status"], "MATCH")
            manifest = json.loads(
                (published / "manifest.json").read_text("utf-8")
            )
            self.assertNotIn("path", manifest["models"])

    def test_runtime_and_unexpected_verifier_failures_have_safe_streams(
        self,
    ) -> None:
        with tempfile.TemporaryDirectory() as directory:
            _, published = self.observation(Path(directory))
            with mock.patch(
                "tiny_corpus_workbench.verification._schema",
                side_effect=RuntimeContractError("schema runtime unavailable"),
            ):
                code, stdout, stderr = self.invoke("verify", str(published))
            self.assertEqual(code, 6)
            self.assertEqual(stdout, "")
            self.assertEqual(stderr, "schema runtime unavailable\n")

            with mock.patch(
                "tiny_corpus_workbench.verification.verify_observation",
                side_effect=RuntimeError("unexpected\x00 failure"),
            ):
                code, stdout, stderr = self.invoke("verify", str(published))
            self.assertEqual(code, 1)
            self.assertEqual(stdout, "")
            self.assertEqual(
                stderr, "internal verifier failure: unexpected failure\n"
            )


if __name__ == "__main__":
    unittest.main()
