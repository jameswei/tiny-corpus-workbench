from __future__ import annotations

import io
import hashlib
import json
import shutil
import tempfile
import unittest
from contextlib import redirect_stderr, redirect_stdout
from pathlib import Path
from unittest import mock

from docling_core.types.doc import DoclingDocument, DocItemLabel

from tiny_corpus_workbench import cli
from tiny_corpus_workbench.artifacts import canonical_json
from tiny_corpus_workbench.diagnosis import make_finding_set, render_report
from tiny_corpus_workbench.diagnosis import snapshot_tree
from tiny_corpus_workbench.domain import IntegrityError


SOURCE = Path("fixtures/golden/policy-memo.md")


def fake_docling(source: Path, destination: Path, model_root: Path):
    destination.mkdir(parents=True)
    document = DoclingDocument(name="diagnosis-workflow")
    document.add_text(DocItemLabel.TEXT, "Stable body content. " * 20)
    document.save_as_json(destination / "document.json")
    document.save_as_markdown(destination / "document.md")
    return "success", {"name": "DoclingDocument", "version": "1.10.0"}


def partial_docling(source: Path, destination: Path, model_root: Path):
    _, schema = fake_docling(source, destination, model_root)
    return "partial_success", schema


def fake_markitdown(source: Path, destination: Path):
    destination.mkdir(parents=True)
    (destination / "document.md").write_text("# stable view\n", "utf-8")


class DiagnosisWorkflowTests(unittest.TestCase):
    def invoke(self, *arguments: str) -> tuple[int, str, str]:
        stdout, stderr = io.StringIO(), io.StringIO()
        with redirect_stdout(stdout), redirect_stderr(stderr):
            code = cli.main(list(arguments))
        return code, stdout.getvalue(), stderr.getvalue()

    def observation(self, root: Path, docling=fake_docling) -> Path:
        with mock.patch(
            "tiny_corpus_workbench.extractors.docling.convert", side_effect=docling
        ), mock.patch(
            "tiny_corpus_workbench.extractors.markitdown.convert",
            side_effect=fake_markitdown,
        ):
            code, published = cli.observe(str(SOURCE), root, Path("unused"))
        self.assertIn(int(code), (0, 3))
        return published

    def test_observe_diagnose_verify_is_deterministic_and_read_only(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            observation = self.observation(root / "observations")
            before = {
                path.relative_to(observation).as_posix(): (
                    path.stat().st_mode,
                    path.stat().st_mtime_ns,
                    path.read_bytes(),
                )
                for path in observation.rglob("*")
                if path.is_file()
            }
            outputs = []
            for output_name in ("first", "second"):
                code, stdout, stderr = self.invoke(
                    "diagnose",
                    str(observation),
                    "--output-root",
                    str(root / output_name),
                )
                self.assertEqual(code, 0)
                self.assertEqual(stderr, "")
                self.assertEqual(len(stdout.splitlines()), 1)
                summary = json.loads(stdout)
                self.assertEqual(summary["status"], "NO_FINDINGS")
                outputs.append(Path(summary["manifest"]).parent)
            self.assertEqual(
                (outputs[0] / "findings.json").read_bytes(),
                (outputs[1] / "findings.json").read_bytes(),
            )
            self.assertEqual(
                (outputs[0] / "report.md").read_bytes(),
                (outputs[1] / "report.md").read_bytes(),
            )
            self.assertNotEqual(outputs[0].name, outputs[1].name)
            self.assertEqual(
                json.loads((outputs[0] / "findings.json").read_text("utf-8"))[
                    "diagnosis_id"
                ],
                json.loads((outputs[1] / "findings.json").read_text("utf-8"))[
                    "diagnosis_id"
                ],
            )
            code, stdout, stderr = self.invoke(
                "verify-diagnosis",
                str(outputs[0]),
                "--observation",
                str(observation),
            )
            self.assertEqual(code, 0)
            self.assertEqual(stderr, "")
            result = json.loads(stdout)
            self.assertEqual(result["artifact_integrity"]["status"], "VERIFIED")
            self.assertEqual(result["observation_state"]["status"], "MATCH")
            self.assertEqual(result["derivation_state"]["status"], "MATCH")
            after = {
                path.relative_to(observation).as_posix(): (
                    path.stat().st_mode,
                    path.stat().st_mtime_ns,
                    path.read_bytes(),
                )
                for path in observation.rglob("*")
                if path.is_file()
            }
            self.assertEqual(after, before)

    def test_partial_success_is_accepted_and_corruption_is_detected(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            observation = self.observation(root / "observations", partial_docling)
            code, stdout, stderr = self.invoke(
                "diagnose", str(observation), "--output-root", str(root / "diagnoses")
            )
            self.assertEqual(code, 0)
            self.assertEqual(stderr, "")
            diagnosis = Path(json.loads(stdout)["manifest"]).parent
            copied = root / "corrupt" / diagnosis.name
            copied.parent.mkdir()
            shutil.copytree(diagnosis, copied)
            (copied / "report.md").write_text("# replaced\n", "utf-8")
            code, stdout, stderr = self.invoke("verify-diagnosis", str(copied))
            self.assertEqual(code, 5)
            self.assertEqual(stderr, "")
            self.assertEqual(
                json.loads(stdout)["artifact_integrity"]["status"],
                "INTEGRITY_MISMATCH",
            )

    def test_usage_failures_have_no_stdout_and_publish_nothing(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            output = root / "output"
            code, stdout, stderr = self.invoke(
                "diagnose", str(root / "missing"), "--output-root", str(output)
            )
            self.assertEqual(code, 2)
            self.assertEqual(stdout, "")
            self.assertTrue(stderr)
            self.assertFalse(output.exists())
            code, stdout, stderr = self.invoke(
                "verify-diagnosis", str(root / "missing")
            )
            self.assertEqual(code, 2)
            self.assertEqual(stdout, "")
            self.assertTrue(stderr)

    def test_missing_canonical_artifact_is_exit_four_without_publication(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            observation = self.observation(root / "observations")
            (observation / "docling/document.json").unlink()
            output = root / "diagnoses"
            code, stdout, stderr = self.invoke(
                "diagnose", str(observation), "--output-root", str(output)
            )
            self.assertEqual(code, 4)
            self.assertEqual(stdout, "")
            self.assertIn("canonical Docling artifact", stderr)
            self.assertFalse(output.exists())

    def test_observation_change_or_staged_failure_never_publishes(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            observation = self.observation(root / "observations")
            baseline = snapshot_tree(observation)
            changed = baseline + (("concurrent", "file"),)
            output = root / "changed"
            with mock.patch(
                "tiny_corpus_workbench.diagnosis.snapshot_tree",
                side_effect=[baseline, changed],
            ):
                code, stdout, stderr = self.invoke(
                    "diagnose", str(observation), "--output-root", str(output)
                )
            self.assertEqual(code, 5)
            self.assertEqual(stdout, "")
            self.assertIn("changed during diagnosis", stderr)
            self.assertEqual(list(output.glob("*/*/*")), [])

            output = root / "schema-failure"
            with mock.patch(
                "tiny_corpus_workbench.diagnosis._validate",
                side_effect=IntegrityError("staged diagnosis is invalid"),
            ):
                code, stdout, stderr = self.invoke(
                    "diagnose", str(observation), "--output-root", str(output)
                )
            self.assertEqual(code, 5)
            self.assertEqual(stdout, "")
            self.assertIn("staged diagnosis is invalid", stderr)
            self.assertEqual(list(output.glob("*/*/*")), [])

    def test_verifier_detects_inventory_and_content_failure_shapes(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            observation = self.observation(root / "observations")
            code, stdout, _ = self.invoke(
                "diagnose", str(observation), "--output-root", str(root / "diagnoses")
            )
            self.assertEqual(code, 0)
            diagnosis = Path(json.loads(stdout)["manifest"]).parent
            for operation in ("missing", "added", "malformed", "symlink"):
                with self.subTest(operation=operation):
                    copied = root / operation / diagnosis.name
                    copied.parent.mkdir()
                    shutil.copytree(diagnosis, copied)
                    if operation == "missing":
                        (copied / "report.md").unlink()
                    elif operation == "added":
                        (copied / "extra.txt").write_text("extra", "utf-8")
                    elif operation == "malformed":
                        (copied / "findings.json").write_text("{", "utf-8")
                    else:
                        (copied / "report.md").unlink()
                        (copied / "report.md").symlink_to(copied / "findings.json")
                    code, stdout, stderr = self.invoke(
                        "verify-diagnosis", str(copied)
                    )
                    self.assertEqual(code, 5)
                    self.assertEqual(stderr, "")
                    self.assertIn(
                        json.loads(stdout)["artifact_integrity"]["status"],
                        ("INTEGRITY_MISMATCH", "BROKEN"),
                    )

    def test_optional_observation_states_are_advisory(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            observation = self.observation(root / "observations")
            code, stdout, _ = self.invoke(
                "diagnose", str(observation), "--output-root", str(root / "diagnoses")
            )
            self.assertEqual(code, 0)
            diagnosis = Path(json.loads(stdout)["manifest"]).parent
            code, stdout, _ = self.invoke("verify-diagnosis", str(diagnosis))
            self.assertEqual(code, 0)
            result = json.loads(stdout)
            self.assertEqual(result["observation_state"]["status"], "NOT_CHECKED")
            self.assertEqual(result["derivation_state"]["status"], "NOT_CHECKED")
            code, stdout, _ = self.invoke(
                "verify-diagnosis",
                str(diagnosis),
                "--observation",
                str(root / "missing"),
            )
            self.assertEqual(code, 0)
            result = json.loads(stdout)
            self.assertEqual(result["observation_state"]["status"], "MISSING")
            self.assertEqual(result["derivation_state"]["status"], "NOT_CHECKED")

            other_observation = self.observation(root / "other-observations")
            code, stdout, _ = self.invoke(
                "verify-diagnosis",
                str(diagnosis),
                "--observation",
                str(other_observation),
            )
            self.assertEqual(code, 0)
            result = json.loads(stdout)
            self.assertEqual(result["observation_state"]["status"], "CHANGED")
            self.assertEqual(result["derivation_state"]["status"], "NOT_CHECKED")

            bad_observation = root / "bad-observation"
            bad_observation.mkdir()
            code, stdout, _ = self.invoke(
                "verify-diagnosis",
                str(diagnosis),
                "--observation",
                str(bad_observation),
            )
            self.assertEqual(code, 0)
            result = json.loads(stdout)
            self.assertEqual(result["observation_state"]["status"], "ERROR")
            self.assertEqual(result["derivation_state"]["status"], "NOT_CHECKED")

            with mock.patch(
                "tiny_corpus_workbench.diagnosis_verification.make_finding_set",
                side_effect=ValueError("rerun failed"),
            ):
                code, stdout, _ = self.invoke(
                    "verify-diagnosis",
                    str(diagnosis),
                    "--observation",
                    str(observation),
                )
            self.assertEqual(code, 0)
            result = json.loads(stdout)
            self.assertEqual(result["observation_state"]["status"], "MATCH")
            self.assertEqual(result["derivation_state"]["status"], "ERROR")

            observation_manifest = json.loads(
                (observation / "manifest.json").read_text("utf-8")
            )
            observation_bytes = (observation / "manifest.json").read_bytes()
            document_bytes = (observation / "docling/document.json").read_bytes()
            changed_payload = json.loads(document_bytes)
            changed_payload["texts"][0]["text"] = "x"
            mismatched = make_finding_set(
                changed_payload,
                observation_manifest,
                manifest_hash=hashlib.sha256(observation_bytes).hexdigest(),
                document_hash=hashlib.sha256(document_bytes).hexdigest(),
            )
            findings_bytes = canonical_json(mismatched)
            report_bytes = render_report(mismatched)
            (diagnosis / "findings.json").write_bytes(findings_bytes)
            (diagnosis / "report.md").write_bytes(report_bytes)
            manifest_path = diagnosis / "diagnosis-manifest.json"
            manifest = json.loads(manifest_path.read_text("utf-8"))
            manifest["status"] = "FINDINGS"
            manifest["summary"] = mismatched["summary"]
            for descriptor in manifest["artifacts"]:
                raw = (
                    findings_bytes
                    if descriptor["path"] == "findings.json"
                    else report_bytes
                )
                descriptor["size"] = len(raw)
                descriptor["sha256"] = hashlib.sha256(raw).hexdigest()
            manifest_path.write_bytes(canonical_json(manifest))
            code, stdout, _ = self.invoke(
                "verify-diagnosis",
                str(diagnosis),
                "--observation",
                str(observation),
            )
            self.assertEqual(code, 0)
            result = json.loads(stdout)
            self.assertEqual(result["artifact_integrity"]["status"], "VERIFIED")
            self.assertEqual(result["observation_state"]["status"], "MATCH")
            self.assertEqual(result["derivation_state"]["status"], "MISMATCH")


if __name__ == "__main__":
    unittest.main()
