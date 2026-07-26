from __future__ import annotations

import json
import os
import socket
import tempfile
import unittest
from contextlib import ExitStack, contextmanager
from pathlib import Path
from unittest import mock

from tiny_corpus_workbench.artifacts import canonical_json
from tiny_corpus_workbench.cli import observe
from tiny_corpus_workbench.corpus_publication import inspect_corpus
from tiny_corpus_workbench.corpus_verification import verify_corpus
from tiny_corpus_workbench.v03 import (
    diagnose,
    draft_refinement,
    resolve_refinement,
    verify_refinement,
)


ROOT = Path(__file__).resolve().parents[2]
MODEL_ROOT = Path(
    os.environ.get("TCW_DOCLING_ARTIFACTS", ".cache/docling/models")
).resolve()
GOLDEN_SPEC = ROOT / "fixtures/corpus/v0.5/golden-matrix.json"
QUALITY_SPEC = ROOT / "fixtures/corpus/v0.5/quality-corpus.json"


@contextmanager
def offline():
    def deny(*args, **kwargs):
        raise AssertionError("corpus workflow attempted network access")

    with ExitStack() as stack:
        stack.enter_context(mock.patch.object(socket, "create_connection", deny))
        stack.enter_context(mock.patch.object(socket.socket, "connect", deny))
        stack.enter_context(mock.patch.object(socket.socket, "connect_ex", deny))
        yield


def _absolute_spec(source: Path, destination: Path) -> dict:
    value = json.loads(source.read_text("utf-8"))
    source_directory = source.parent
    for member in value["members"]:
        member["source"] = str(
            (source_directory / member["source"]).resolve()
        )
    destination.write_bytes(canonical_json(value))
    return value


def _approve(
    *,
    diagnosis_root: Path,
    base_root: Path,
    rule_id: str,
    root: Path,
) -> Path:
    root.mkdir(parents=True, exist_ok=True)
    findings = json.loads((diagnosis_root / "findings.json").read_text("utf-8"))
    finding = next(
        item for item in findings["findings"] if item["rule_id"] == rule_id
    )
    decision_path = root / f"{finding['finding_id']}-decision.json"
    draft_refinement(
        diagnosis_root,
        finding["finding_id"],
        base_root,
        decision_path,
    )
    decision = json.loads(decision_path.read_text("utf-8"))
    decision["decision"] = {
        "state": "APPROVED",
        "decided_by": "integration-owner",
        "note": "Approved integration evidence.",
    }
    decision_path.write_bytes(canonical_json(decision))
    return resolve_refinement(
        decision_path,
        diagnosis_root,
        base_root,
        root / "revisions",
    )


class CorpusIntegrationTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        if not MODEL_ROOT.is_dir():
            raise unittest.SkipTest(
                f"prefetched Docling models are required: {MODEL_ROOT}"
            )

    def test_golden_matrix_completes_with_exact_d009_outcome(self) -> None:
        with tempfile.TemporaryDirectory() as directory, offline():
            root = Path(directory).resolve()
            published = inspect_corpus(
                GOLDEN_SPEC, root / "output", MODEL_ROOT
            )
            summary = json.loads(
                (published.directory / "summary.json").read_text("utf-8")
            )
            self.assertEqual(published.status, "COMPLETE")
            self.assertEqual(summary["totals"]["member_count"], 12)
            self.assertEqual(summary["totals"]["complete"], 12)
            self.assertEqual(summary["totals"]["finding_count"], 9)
            self.assertEqual(
                {item["name"] for item in summary["by_family"]},
                {"meeting-minutes", "policy-memo", "release-notice"},
            )
            self.assertEqual(
                {item["name"] for item in summary["by_format"]},
                {"pdf", "docx", "md", "txt"},
            )
            self.assertEqual(
                summary["extractors"],
                [
                    {"name": "docling", "available": 12, "unavailable": 0},
                    {
                        "name": "markitdown",
                        "available": 12,
                        "unavailable": 0,
                    },
                ],
            )
            self.assertEqual(
                {
                    (
                        item["rule_id"],
                        item["format"],
                        item["finding_count"],
                    )
                    for item in summary["findings"]
                },
                {("TCW-D009", "txt", 3)},
            )
            self.assertEqual(len(summary["findings"]), 3)
            self.assertEqual(
                verify_corpus(published.directory, GOLDEN_SPEC)[
                    "artifact_integrity"
                ]["status"],
                "VERIFIED",
            )

    def test_quality_corpus_has_exact_seven_rule_coverage(self) -> None:
        with tempfile.TemporaryDirectory() as directory, offline():
            root = Path(directory).resolve()
            published = inspect_corpus(
                QUALITY_SPEC, root / "output", MODEL_ROOT
            )
            summary = json.loads(
                (published.directory / "summary.json").read_text("utf-8")
            )
            self.assertEqual(published.status, "COMPLETE")
            self.assertEqual(summary["totals"]["member_count"], 5)
            self.assertEqual(summary["totals"]["finding_count"], 7)
            self.assertEqual(
                {item["rule_id"] for item in summary["findings"]},
                {
                    "TCW-D002",
                    "TCW-D003",
                    "TCW-D004",
                    "TCW-D005",
                    "TCW-D007",
                    "TCW-D009",
                    "TCW-D010",
                },
            )
            self.assertEqual(
                verify_corpus(published.directory, QUALITY_SPEC)[
                    "artifact_integrity"
                ]["status"],
                "VERIFIED",
            )

    def test_missing_pdf_models_publishes_partial_golden_report(self) -> None:
        with tempfile.TemporaryDirectory() as directory, offline():
            root = Path(directory).resolve()
            published = inspect_corpus(
                GOLDEN_SPEC, root / "output", root / "missing-models"
            )
            summary = json.loads(
                (published.directory / "summary.json").read_text("utf-8")
            )
            self.assertEqual(published.status, "PARTIAL")
            self.assertEqual(published.exit_code, 3)
            self.assertEqual(summary["totals"]["complete"], 9)
            self.assertEqual(summary["totals"]["partial"], 3)
            pdf_members = [
                member
                for member in summary["members"]
                if member["format"] == "pdf"
            ]
            self.assertTrue(
                all(
                    member["error"]["code"] == "MODEL_ARTIFACTS_MISSING"
                    for member in pdf_members
                )
            )
            verification = verify_corpus(
                published.directory, GOLDEN_SPEC
            )
            self.assertEqual(
                verification["artifact_integrity"]["status"], "VERIFIED"
            )
            self.assertEqual(verification["model_state"]["status"], "MISSING")

    def test_quality_spec_can_compare_one_explicit_d009_revision(self) -> None:
        with tempfile.TemporaryDirectory() as directory, offline():
            root = Path(directory).resolve()
            inputs = root / "inputs"
            inputs.mkdir()
            source = ROOT / "fixtures/refinement/v0.5/whitespace-cleanup.md"
            code, observation = observe(
                str(source), root / "observations", MODEL_ROOT
            )
            self.assertEqual(int(code), 0)
            diagnosis_root = diagnose(observation, root / "diagnoses")
            revision = _approve(
                diagnosis_root=diagnosis_root,
                base_root=observation,
                rule_id="TCW-D009",
                root=root,
            )
            verified = verify_refinement(
                revision, diagnosis_root, observation
            )
            self.assertEqual(
                verified["artifact_integrity"]["status"], "VERIFIED"
            )
            spec_path = inputs / "quality-with-revision.json"
            value = _absolute_spec(QUALITY_SPEC, spec_path)
            member = next(
                item
                for item in value["members"]
                if item["member_id"] == "whitespace-cleanup"
            )
            member["revisions"] = [
                {
                    "refinement": str(revision),
                    "diagnosis": str(diagnosis_root),
                    "base": str(observation),
                }
            ]
            spec_path.write_bytes(canonical_json(value))
            published = inspect_corpus(
                spec_path, root / "corpus-output", MODEL_ROOT
            )
            summary = json.loads(
                (published.directory / "summary.json").read_text("utf-8")
            )
            self.assertEqual(summary["totals"]["revision_count"], 1)
            self.assertEqual(
                (
                    summary["revisions"][0]["finding_rule"],
                    summary["revisions"][0]["refiner"]["refiner_id"],
                    summary["revisions"][0]["chain_length"],
                ),
                ("TCW-D009", "TCW-R001", 1),
            )
            report = (published.directory / "report/index.html").read_text(
                "utf-8"
            )
            for label in (
                "refinement",
                "decision",
                "transformation",
                "history",
                "prepared document",
            ):
                self.assertIn(label, report)
            verification = verify_corpus(published.directory, spec_path)
            self.assertEqual(
                verification["artifact_integrity"]["status"], "VERIFIED"
            )
            self.assertEqual(
                verification["revision_states"][0]["refinement_state"][
                    "status"
                ],
                "MATCH",
            )
            (revision / "decision.json").write_bytes(
                (revision / "decision.json").read_bytes() + b" "
            )
            drifted = verify_corpus(published.directory, spec_path)
            self.assertEqual(
                drifted["artifact_integrity"]["status"], "VERIFIED"
            )
            self.assertEqual(
                drifted["revision_states"][0]["refinement_state"]["status"],
                "CHANGED",
            )

    def test_two_step_revision_chain_is_reported(self) -> None:
        with tempfile.TemporaryDirectory() as directory, offline():
            root = Path(directory).resolve()
            inputs = root / "inputs"
            inputs.mkdir()
            source = inputs / "chain.md"
            source.write_text(
                "# Chain\n\n"
                "First  paragraph  contains  repeated  spaces  for  one "
                "controlled  decision. Additional words keep this paragraph "
                "long enough for diagnosis.\n\n"
                "Second  paragraph  contains  repeated  spaces  for  another "
                "controlled  decision. Additional words keep this paragraph "
                "long enough for diagnosis.\n",
                "utf-8",
            )
            code, observation = observe(
                str(source), root / "observations", MODEL_ROOT
            )
            self.assertEqual(int(code), 0)
            diagnosis1 = diagnose(observation, root / "diagnoses")
            revision1 = _approve(
                diagnosis_root=diagnosis1,
                base_root=observation,
                rule_id="TCW-D009",
                root=root / "first",
            )
            diagnosis2 = diagnose(revision1, root / "diagnoses")
            revision2 = _approve(
                diagnosis_root=diagnosis2,
                base_root=revision1,
                rule_id="TCW-D009",
                root=root / "second",
            )
            verified = verify_refinement(
                revision2, diagnosis2, revision1
            )
            self.assertEqual(
                verified["reversibility_state"]["status"], "MATCH"
            )
            spec_path = inputs / "chain-corpus.json"
            spec_path.write_bytes(
                canonical_json(
                    {
                        "schema_version": "tcw.corpus-spec/v0.5",
                        "corpus_id": "chain-corpus",
                        "title": "Two-step revision chain",
                        "members": [
                            {
                                "member_id": "chain",
                                "family": "chain",
                                "format": "md",
                                "source": "chain.md",
                                "revisions": [
                                    {
                                        "refinement": str(revision2),
                                        "diagnosis": str(diagnosis2),
                                        "base": str(revision1),
                                    }
                                ],
                            }
                        ],
                    }
                )
            )
            published = inspect_corpus(
                spec_path, root / "corpus-output", MODEL_ROOT
            )
            summary = json.loads(
                (published.directory / "summary.json").read_text("utf-8")
            )
            revision = summary["revisions"][0]
            self.assertEqual(revision["chain_length"], 2)
            self.assertEqual(revision["parent"]["kind"], "REVISION")
            self.assertNotEqual(
                revision["before_document_sha256"],
                revision["after_document_sha256"],
            )
            self.assertEqual(
                verify_corpus(published.directory, spec_path)[
                    "artifact_integrity"
                ]["status"],
                "VERIFIED",
            )


if __name__ == "__main__":
    unittest.main()
