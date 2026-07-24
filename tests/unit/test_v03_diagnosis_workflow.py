from __future__ import annotations

import hashlib
import io
import json
import platform
import shutil
import tempfile
import unittest
from collections import Counter
from contextlib import redirect_stderr, redirect_stdout
from pathlib import Path
from unittest import mock

from docling_core.types.doc import DocItemLabel, DoclingDocument

from tiny_corpus_workbench import cli
from tiny_corpus_workbench.artifacts import canonical_json
from tiny_corpus_workbench.diagnosis import (
    _canonicalize_findings,
    diagnose as diagnose_v02,
)
from tiny_corpus_workbench.diagnosis_verification import verify_diagnosis as verify_v02
from tiny_corpus_workbench.domain import InputError, IntegrityError
from tiny_corpus_workbench.v03 import (
    _diagnosis_report,
    snapshot_tree,
    verify_diagnosis,
)


SOURCE = Path("fixtures/golden/policy-memo.md")
V02_RUNTIME = {
    "python": platform.python_version(),
    "implementation": "CPython",
    "lockfile_sha256": "c708fe8c2ce3a516a8a0e219b5b81bc0ee7b787e62c70c6b470a40ebc8dc55d0",
    "package_version": "0.2.0",
    "dependencies": {
        "docling": "2.113.0",
        "docling-core": "2.87.1",
        "markitdown": "0.1.6",
    },
}


def fake_docling(source: Path, destination: Path, model_root: Path):
    destination.mkdir(parents=True)
    document = DoclingDocument(name="diagnosis-workflow")
    document.add_text(DocItemLabel.TEXT, "Stable body content." * 20)
    document.save_as_json(destination / "document.json")
    document.save_as_markdown(destination / "document.md")
    return "success", {"name": "DoclingDocument", "version": "1.10.0"}


def partial_docling(source: Path, destination: Path, model_root: Path):
    _, schema = fake_docling(source, destination, model_root)
    return "partial_success", schema


def whitespace_docling(source: Path, destination: Path, model_root: Path):
    destination.mkdir(parents=True)
    document = DoclingDocument(name="diagnosis-workflow")
    document.add_text(
        DocItemLabel.TEXT,
        "Stable\u00a0 body  content.\r\nInter-\noperable " + "text " * 40,
    )
    document.save_as_json(destination / "document.json")
    document.save_as_markdown(destination / "document.md")
    return "success", {"name": "DoclingDocument", "version": "1.10.0"}


def fake_markitdown(source: Path, destination: Path):
    destination.mkdir(parents=True)
    (destination / "document.md").write_text("# stable view\n", "utf-8")


class DiagnosisWorkflowTests(unittest.TestCase):
    def invoke(self, *arguments: str) -> tuple[int, str, str]:
        stdout, stderr = io.StringIO(), io.StringIO()
        with redirect_stdout(stdout), redirect_stderr(stderr):
            code = cli.main(list(arguments))
        return code, stdout.getvalue(), stderr.getvalue()

    def observation(self, root: Path, converter=fake_docling) -> Path:
        with mock.patch(
            "tiny_corpus_workbench.extractors.docling.convert",
            side_effect=converter,
        ), mock.patch(
            "tiny_corpus_workbench.extractors.markitdown.convert",
            side_effect=fake_markitdown,
        ):
            code, published = cli.observe(str(SOURCE), root, Path("unused"))
        self.assertIn(int(code), (0, 3))
        return published

    def publish(self, observation: Path, output: Path) -> Path:
        code, stdout, stderr = self.invoke(
            "diagnose", str(observation), "--output-root", str(output)
        )
        self.assertEqual(code, 0, stderr)
        self.assertEqual(stderr, "")
        return Path(json.loads(stdout)["manifest"]).parent

    def copy_diagnosis(self, diagnosis: Path, destination: Path) -> Path:
        copied = destination / diagnosis.name
        destination.mkdir(parents=True)
        shutil.copytree(diagnosis, copied)
        return copied

    def refresh_diagnosis_descriptors(
        self, diagnosis: Path, manifest: dict
    ) -> None:
        for descriptor in manifest["artifacts"]:
            path = diagnosis / descriptor["path"]
            descriptor["size"] = path.stat().st_size
            descriptor["sha256"] = hashlib.sha256(path.read_bytes()).hexdigest()

    def rewrite_diagnosis_identity(
        self,
        diagnosis: Path,
        findings: dict,
        manifest: dict,
        diagnosis_id: str,
    ) -> None:
        findings["diagnosis_id"] = diagnosis_id
        for finding in findings["findings"]:
            finding["finding_id"] = hashlib.sha256(
                canonical_json(
                    {
                        "diagnosis_id": diagnosis_id,
                        "rule_id": finding["rule_id"],
                        "rule_version": finding["rule_version"],
                        "document_refs": finding["document_refs"],
                        "evidence": finding["evidence"],
                    }
                ).rstrip(b"\n")
            ).hexdigest()
        findings["findings"] = _canonicalize_findings(findings["findings"])
        manifest["diagnosis_id"] = diagnosis_id
        manifest["subject"] = findings["subject"]
        (diagnosis / "findings.json").write_bytes(canonical_json(findings))
        (diagnosis / "report.md").write_bytes(_diagnosis_report(findings))
        self.refresh_diagnosis_descriptors(diagnosis, manifest)
        (diagnosis / "diagnosis-manifest.json").write_bytes(
            canonical_json(manifest)
        )

    def test_v03_diagnosis_is_deterministic_and_read_only(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            observation = self.observation(root / "observations", whitespace_docling)
            before = snapshot_tree(observation)
            first = self.publish(observation, root / "first")
            second = self.publish(observation, root / "second")
            self.assertEqual(
                (first / "findings.json").read_bytes(),
                (second / "findings.json").read_bytes(),
            )
            self.assertEqual(
                (first / "report.md").read_bytes(),
                (second / "report.md").read_bytes(),
            )
            findings = json.loads((first / "findings.json").read_text("utf-8"))
            self.assertEqual(findings["schema_version"], "tcw.finding-set/v0.3")
            self.assertEqual(
                {
                    item["rule_id"]
                    for item in findings["findings"]
                    if item["rule_id"] in {"TCW-D009", "TCW-D010"}
                },
                {"TCW-D009", "TCW-D010"},
            )
            code, stdout, stderr = self.invoke(
                "verify-diagnosis",
                str(first),
                "--subject",
                str(observation),
            )
            self.assertEqual(code, 0)
            self.assertEqual(stderr, "")
            result = json.loads(stdout)
            self.assertEqual(result["artifact_integrity"]["status"], "VERIFIED")
            self.assertEqual(result["subject_state"]["status"], "MATCH")
            self.assertEqual(result["derivation_state"]["status"], "MATCH")
            self.assertEqual(snapshot_tree(observation), before)

    def test_partial_observation_is_supported(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            observation = self.observation(root / "observations", partial_docling)
            diagnosis = self.publish(observation, root / "diagnoses")
            self.assertEqual(
                verify_diagnosis(diagnosis, observation)["artifact_integrity"][
                    "status"
                ],
                "VERIFIED",
            )

    def test_existing_v02_diagnosis_remains_verifiable(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            observation = self.observation(root / "observations")
            with mock.patch(
                "tiny_corpus_workbench.diagnosis.active_locked_runtime",
                return_value=V02_RUNTIME,
            ):
                legacy = diagnose_v02(observation, root / "legacy")
            manifest = json.loads(
                (legacy / "diagnosis-manifest.json").read_text("utf-8")
            )
            self.assertEqual(
                manifest["schema_version"], "tcw.diagnosis-manifest/v0.2"
            )
            result = verify_v02(legacy, observation)
            self.assertEqual(
                result["artifact_integrity"]["status"], "VERIFIED", result
            )
            self.assertEqual(result["observation_state"]["status"], "MATCH")
            self.assertEqual(result["derivation_state"]["status"], "MATCH")
            code, stdout, stderr = self.invoke(
                "verify-diagnosis",
                str(legacy),
                "--observation",
                str(observation),
            )
            self.assertEqual(code, 0)
            self.assertEqual(stderr, "")
            self.assertEqual(
                json.loads(stdout)["schema_version"],
                "tcw.diagnosis-verification-result/v0.2",
            )
            for field, replacement in (
                ("lockfile_sha256", "f" * 64),
                ("package_version", "0.1.0"),
                (
                    "dependencies",
                    {
                        **V02_RUNTIME["dependencies"],
                        "docling-core": "0.0.0",
                    },
                ),
            ):
                with self.subTest(v02_runtime=field):
                    copied = root / field / legacy.name
                    copied.parent.mkdir()
                    shutil.copytree(legacy, copied)
                    manifest_path = copied / "diagnosis-manifest.json"
                    changed_manifest = json.loads(
                        manifest_path.read_text("utf-8")
                    )
                    changed_manifest["runtime"][field] = replacement
                    manifest_path.write_bytes(canonical_json(changed_manifest))
                    self.assertNotEqual(
                        verify_v02(copied)["artifact_integrity"]["status"],
                        "VERIFIED",
                    )

    def test_missing_or_inconsistent_canonical_document_never_publishes(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            for operation in ("missing", "bad-reference"):
                with self.subTest(operation=operation):
                    observation = self.observation(
                        root / operation / "observations"
                    )
                    document_path = observation / "docling/document.json"
                    if operation == "missing":
                        document_path.unlink()
                    else:
                        payload = json.loads(document_path.read_text("utf-8"))
                        payload["texts"][0]["self_ref"] = "#/texts/99"
                        document_path.write_bytes(canonical_json(payload))
                    output = root / operation / "diagnoses"
                    code, stdout, stderr = self.invoke(
                        "diagnose",
                        str(observation),
                        "--output-root",
                        str(output),
                    )
                    self.assertIn(code, (2, 4, 5))
                    self.assertEqual(stdout, "")
                    self.assertTrue(stderr)
                    self.assertFalse(any(output.rglob("diagnosis-manifest.json")))

    def test_changed_input_and_schema_failure_never_publish(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            observation = self.observation(root / "observations")
            baseline = snapshot_tree(observation)
            output = root / "changed"
            with mock.patch(
                "tiny_corpus_workbench.v03.snapshot_tree",
                side_effect=[baseline, baseline + (("changed",),)],
            ):
                code, stdout, _ = self.invoke(
                    "diagnose", str(observation), "--output-root", str(output)
                )
            self.assertEqual(code, 5)
            self.assertEqual(stdout, "")
            self.assertFalse(any(output.rglob("diagnosis-manifest.json")))

            with mock.patch(
                "tiny_corpus_workbench.v03._validate",
                side_effect=IntegrityError("staged diagnosis is invalid"),
            ):
                code, stdout, stderr = self.invoke(
                    "diagnose",
                    str(observation),
                    "--output-root",
                    str(root / "invalid"),
                )
            self.assertEqual(code, 5)
            self.assertEqual(stdout, "")
            self.assertIn("staged diagnosis is invalid", stderr)

    def test_output_overlap_conflict_and_symlink_are_rejected(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            observation = self.observation(root / "observations")
            code, stdout, _ = self.invoke(
                "diagnose",
                str(observation),
                "--output-root",
                str(observation),
            )
            self.assertEqual(code, 2)
            self.assertEqual(stdout, "")

            output = root / "diagnoses"
            diagnosis = self.publish(observation, output)
            sentinel = diagnosis / "sentinel"
            sentinel.write_text("winner", "utf-8")
            self.assertEqual(sentinel.read_text("utf-8"), "winner")

            outside = root / "outside"
            outside.mkdir()
            alias = root / "alias"
            alias.symlink_to(outside, target_is_directory=True)
            code, stdout, _ = self.invoke(
                "diagnose",
                str(observation),
                "--output-root",
                str(alias),
            )
            self.assertIn(code, (2, 5))
            self.assertEqual(stdout, "")

            observation_manifest = json.loads(
                (observation / "manifest.json").read_text("utf-8")
            )
            source_key = observation_manifest["source"]["key"]
            subject_id = observation_manifest["observation_id"]
            for level in ("source-key", "subject-id"):
                with self.subTest(level=level):
                    nested_output = root / f"nested-{level}"
                    nested_output.mkdir()
                    if level == "source-key":
                        (nested_output / source_key).symlink_to(
                            outside, target_is_directory=True
                        )
                    else:
                        (nested_output / source_key).mkdir()
                        (nested_output / source_key / subject_id).symlink_to(
                            outside, target_is_directory=True
                        )
                    code, stdout, _ = self.invoke(
                        "diagnose",
                        str(observation),
                        "--output-root",
                        str(nested_output),
                    )
                    self.assertEqual(code, 2)
                    self.assertEqual(stdout, "")
                    self.assertFalse(any(outside.rglob("diagnosis-manifest.json")))

    def test_verifier_detects_inventory_hash_json_and_symlink_corruption(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            observation = self.observation(root / "observations")
            diagnosis = self.publish(observation, root / "diagnoses")
            for operation in ("missing", "added", "hash", "json", "symlink"):
                with self.subTest(operation=operation):
                    copied = root / operation / diagnosis.name
                    copied.parent.mkdir()
                    shutil.copytree(diagnosis, copied)
                    if operation == "missing":
                        (copied / "report.md").unlink()
                    elif operation == "added":
                        (copied / "extra").write_text("extra", "utf-8")
                    elif operation == "hash":
                        (copied / "report.md").write_text("changed", "utf-8")
                    elif operation == "json":
                        (copied / "findings.json").write_text("{", "utf-8")
                    else:
                        (copied / "report.md").unlink()
                        (copied / "report.md").symlink_to(
                            diagnosis / "report.md"
                        )
                    code, stdout, stderr = self.invoke(
                        "verify-diagnosis", str(copied)
                    )
                    self.assertEqual(code, 5)
                    self.assertEqual(stderr, "")
                    self.assertIn(
                        json.loads(stdout)["artifact_integrity"]["status"],
                        {"INTEGRITY_MISMATCH", "BROKEN"},
                    )

    def test_verifier_rejects_manifest_encoding_and_descriptor_mapping_tampering(
        self,
    ) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            observation = self.observation(
                root / "observations", whitespace_docling
            )
            diagnosis = self.publish(observation, root / "diagnoses")
            for operation in (
                "roles",
                "media-types",
                "paths",
                "immutability",
                "noncanonical-manifest",
            ):
                with self.subTest(operation=operation):
                    copied = self.copy_diagnosis(
                        diagnosis, root / operation
                    )
                    manifest_path = copied / "diagnosis-manifest.json"
                    manifest = json.loads(manifest_path.read_text("utf-8"))
                    first, second = manifest["artifacts"]
                    if operation == "roles":
                        first["role"], second["role"] = (
                            second["role"],
                            first["role"],
                        )
                    elif operation == "media-types":
                        first["media_type"], second["media_type"] = (
                            second["media_type"],
                            first["media_type"],
                        )
                    elif operation == "paths":
                        first["path"], second["path"] = (
                            second["path"],
                            first["path"],
                        )
                        self.refresh_diagnosis_descriptors(copied, manifest)
                    elif operation == "immutability":
                        first["application_immutable"] = False
                    else:
                        manifest_path.write_text(
                            json.dumps(manifest, indent=2), "utf-8"
                        )
                    if operation != "noncanonical-manifest":
                        manifest_path.write_bytes(canonical_json(manifest))
                    result = verify_diagnosis(copied)
                    self.assertEqual(
                        result["artifact_integrity"]["status"], "BROKEN"
                    )

    def test_verifier_rejects_self_consistent_v03_finding_metadata_tampering(
        self,
    ) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            observation = self.observation(
                root / "observations", whitespace_docling
            )
            diagnosis = self.publish(observation, root / "diagnoses")
            for rule_id, field, replacement in (
                ("TCW-D009", "severity", "WARNING"),
                ("TCW-D010", "severity", "INFO"),
                ("TCW-D009", "summary", "Changed whitespace summary"),
                ("TCW-D010", "summary", "Changed hyphenation summary"),
                ("TCW-D009", "rule_version", "2"),
            ):
                with self.subTest(rule_id=rule_id, field=field):
                    copied = self.copy_diagnosis(
                        diagnosis, root / f"{rule_id}-{field}"
                    )
                    findings_path = copied / "findings.json"
                    findings = json.loads(findings_path.read_text("utf-8"))
                    target = next(
                        item
                        for item in findings["findings"]
                        if item["rule_id"] == rule_id
                    )
                    target[field] = replacement
                    findings["findings"] = _canonicalize_findings(
                        findings["findings"]
                    )
                    severities = Counter(
                        item["severity"] for item in findings["findings"]
                    )
                    rules = Counter(
                        item["rule_id"] for item in findings["findings"]
                    )
                    findings["summary"] = {
                        "total": len(findings["findings"]),
                        "by_severity": {
                            name: severities.get(name, 0)
                            for name in ("ERROR", "WARNING", "INFO")
                        },
                        "by_rule": {
                            name: rules.get(name, 0)
                            for name in findings["summary"]["by_rule"]
                        },
                    }
                    findings_path.write_bytes(canonical_json(findings))
                    (copied / "report.md").write_bytes(
                        _diagnosis_report(findings)
                    )
                    manifest_path = copied / "diagnosis-manifest.json"
                    manifest = json.loads(manifest_path.read_text("utf-8"))
                    manifest["summary"] = findings["summary"]
                    self.refresh_diagnosis_descriptors(copied, manifest)
                    manifest_path.write_bytes(canonical_json(manifest))
                    result = verify_diagnosis(copied)
                    self.assertEqual(
                        result["artifact_integrity"]["status"], "BROKEN"
                    )

    def test_optional_subject_states_are_advisory(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            observation = self.observation(root / "observations")
            diagnosis = self.publish(observation, root / "diagnoses")
            result = verify_diagnosis(diagnosis)
            self.assertEqual(result["subject_state"]["status"], "NOT_CHECKED")
            self.assertEqual(result["derivation_state"]["status"], "NOT_CHECKED")
            missing = verify_diagnosis(diagnosis, root / "missing")
            self.assertEqual(missing["subject_state"]["status"], "MISSING")
            copied = root / "changed" / observation.name
            copied.parent.mkdir()
            shutil.copytree(observation, copied)
            manifest_path = copied / "manifest.json"
            manifest = json.loads(manifest_path.read_text("utf-8"))
            manifest["observation_id"] = "f" * 64
            manifest_path.write_bytes(canonical_json(manifest))
            changed = verify_diagnosis(diagnosis, copied)
            self.assertIn(changed["subject_state"]["status"], {"CHANGED", "ERROR"})

    def test_diagnosis_identity_and_complete_subject_descriptor_are_verified(
        self,
    ) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            observation = self.observation(
                root / "observations", whitespace_docling
            )
            diagnosis = self.publish(observation, root / "diagnoses")
            for operation in (
                "diagnosis-id",
                "document-size",
                "document-path",
                "subject-manifest-size",
                "subject-manifest-hash",
            ):
                with self.subTest(operation=operation):
                    copied = self.copy_diagnosis(
                        diagnosis, root / operation
                    )
                    findings = json.loads(
                        (copied / "findings.json").read_text("utf-8")
                    )
                    manifest = json.loads(
                        (copied / "diagnosis-manifest.json").read_text("utf-8")
                    )
                    if operation == "diagnosis-id":
                        diagnosis_id = "f" * 64
                    elif operation in {"document-size", "document-path"}:
                        if operation == "document-size":
                            findings["subject"][
                                "canonical_document_size"
                            ] += 1
                        else:
                            findings["subject"][
                                "canonical_document_path"
                            ] = "prepared/document.json"
                        diagnosis_id = hashlib.sha256(
                            canonical_json(
                                {
                                    "subject": findings["subject"],
                                    "canonical_document_sha256": findings[
                                        "subject"
                                    ]["canonical_document_sha256"],
                                    "ruleset": findings["ruleset"],
                                }
                            ).rstrip(b"\n")
                        ).hexdigest()
                    else:
                        key = (
                            "subject_manifest_size"
                            if operation == "subject-manifest-size"
                            else "subject_manifest_sha256"
                        )
                        manifest[key] = (
                            manifest[key] + 1
                            if key == "subject_manifest_size"
                            else "f" * 64
                        )
                        (copied / "diagnosis-manifest.json").write_bytes(
                            canonical_json(manifest)
                        )
                        result = verify_diagnosis(copied, observation)
                        self.assertEqual(
                            result["artifact_integrity"]["status"], "VERIFIED"
                        )
                        self.assertEqual(
                            result["subject_state"]["status"], "CHANGED"
                        )
                        continue
                    self.rewrite_diagnosis_identity(
                        copied, findings, manifest, diagnosis_id
                    )
                    result = verify_diagnosis(copied, observation)
                    if operation == "diagnosis-id":
                        self.assertEqual(
                            result["artifact_integrity"]["status"], "BROKEN"
                        )
                    else:
                        self.assertEqual(
                            result["artifact_integrity"]["status"], "VERIFIED"
                        )
                        self.assertEqual(
                            result["subject_state"]["status"], "CHANGED"
                        )

    def test_runtime_drift_is_exit_six_without_publication(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            observation = self.observation(root / "observations")

            def drift(name: str) -> str:
                if name == "docling-core":
                    return "0.0.0"
                return {
                    "docling": "2.113.0",
                    "markitdown": "0.1.6",
                    "tiny-corpus-workbench": "0.3.0",
                }[name]

            output = root / "diagnoses"
            with mock.patch(
                "tiny_corpus_workbench.runtime.importlib.metadata.version",
                side_effect=drift,
            ):
                code, stdout, stderr = self.invoke(
                    "diagnose",
                    str(observation),
                    "--output-root",
                    str(output),
                )
            self.assertEqual(code, 6)
            self.assertEqual(stdout, "")
            self.assertIn("installed extractor versions", stderr)
            self.assertFalse(any(output.rglob("diagnosis-manifest.json")))

    def test_v03_diagnosis_runtime_provenance_is_verified(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            observation = self.observation(
                root / "observations", whitespace_docling
            )
            diagnosis = self.publish(observation, root / "diagnoses")
            active = json.loads(
                (diagnosis / "diagnosis-manifest.json").read_text("utf-8")
            )["runtime"]
            for field, replacement in (
                ("lockfile_sha256", "f" * 64),
                ("package_version", "0.3.1"),
                (
                    "dependencies",
                    {
                        **active["dependencies"],
                        "docling-core": "0.0.0",
                    },
                ),
            ):
                with self.subTest(field=field):
                    copied = self.copy_diagnosis(
                        diagnosis, root / field
                    )
                    manifest_path = copied / "diagnosis-manifest.json"
                    manifest = json.loads(manifest_path.read_text("utf-8"))
                    manifest["runtime"][field] = replacement
                    manifest_path.write_bytes(canonical_json(manifest))
                    self.assertEqual(
                        verify_diagnosis(
                            copied, observation
                        )["artifact_integrity"]["status"],
                        "BROKEN",
                    )

    def test_cli_errors_are_sanitized_and_use_exact_streams(self) -> None:
        for error, expected in (
            (InputError("bad\x01 input\npath"), 2),
            (ValueError("boom\x01\ntrace"), 1),
        ):
            with self.subTest(expected=expected), mock.patch.object(
                cli,
                "_diagnosis_callable",
                return_value=mock.Mock(side_effect=error),
            ):
                code, stdout, stderr = self.invoke("diagnose", "observation")
            self.assertEqual(code, expected)
            self.assertEqual(stdout, "")
            self.assertEqual(len(stderr.splitlines()), 1)
            self.assertNotIn("\x01", stderr)
            self.assertNotIn("Traceback", stderr)


if __name__ == "__main__":
    unittest.main()
