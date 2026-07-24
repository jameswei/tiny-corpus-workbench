from __future__ import annotations

import hashlib
import json
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from docling_core.types.doc import (
    DocItemLabel,
    DoclingDocument,
    TableCell,
    TableData,
)

from tiny_corpus_workbench import cli
from tiny_corpus_workbench.artifacts import canonical_json
from tiny_corpus_workbench.v03 import (
    _apply_edits,
    _normalize_whitespace,
    make_finding_set,
    verify_diagnosis,
    verify_refinement,
)


SOURCE = Path("fixtures/golden/policy-memo.md")
RUNTIME = {
    "python": "3.12.11",
    "implementation": "CPython",
    "lockfile_sha256": "1" * 64,
    "package_version": "0.3.0",
    "dependencies": {
        "docling": "2.113.0",
        "docling-core": "2.87.1",
        "markitdown": "0.1.6",
    },
}


def docling_with_refinements(source: Path, destination: Path, model_root: Path):
    destination.mkdir(parents=True)
    document = DoclingDocument(name="controlled-revision")
    document.add_text(
        DocItemLabel.TEXT,
        "  Stable\u00a0 body  text.\r\nInter-\noperable content remains long enough. "
        * 5,
    )
    document.save_as_json(destination / "document.json")
    document.save_as_markdown(destination / "document.md")
    return "success", {"name": "DoclingDocument", "version": "1.10.0"}


def markitdown(source: Path, destination: Path):
    destination.mkdir(parents=True)
    (destination / "document.md").write_text("# stable\n", "utf-8")


class ControlledRevisionTests(unittest.TestCase):
    def observation(self, root: Path) -> Path:
        with mock.patch(
            "tiny_corpus_workbench.extractors.docling.convert",
            side_effect=docling_with_refinements,
        ), mock.patch(
            "tiny_corpus_workbench.extractors.markitdown.convert",
            side_effect=markitdown,
        ):
            code, published = cli.observe(str(SOURCE), root, Path("unused"))
        self.assertEqual(int(code), 0)
        return published

    def subject(self) -> dict:
        document = DoclingDocument(name="rules")
        document.add_text(
            DocItemLabel.TEXT,
            "  Alpha\u2003 beta\r\nInter-\noperable " + "content " * 30,
        )
        payload = document.model_dump(mode="json", by_alias=True, exclude_none=True)
        raw = canonical_json(payload)
        return {
            "kind": "OBSERVATION",
            "subject_id": "a" * 64,
            "origin_observation_id": "a" * 64,
            "document_path": "docling/document.json",
            "document_bytes": raw,
            "payload": payload,
            "source": {"media_type": "text/markdown"},
        }

    def test_d009_and_d010_are_deterministic_and_keep_one_finding_per_target(self) -> None:
        first = make_finding_set(self.subject())
        second = make_finding_set(self.subject())
        self.assertEqual(first, second)
        by_rule = {
            rule: [item for item in first["findings"] if item["rule_id"] == rule]
            for rule in ("TCW-D009", "TCW-D010")
        }
        self.assertEqual(len(by_rule["TCW-D009"]), 1)
        self.assertEqual(len(by_rule["TCW-D010"]), 1)
        self.assertEqual(
            by_rule["TCW-D009"][0]["evidence"]["code_point_offsets"],
            sorted(by_rule["TCW-D009"][0]["evidence"]["code_point_offsets"]),
        )
        self.assertEqual(
            _normalize_whitespace(" a\u00a0  b\r\n c "),
            "a b\nc",
        )

    def test_code_and_formula_are_excluded(self) -> None:
        for label in ("code", "formula"):
            with self.subTest(label=label):
                subject = self.subject()
                subject["payload"]["texts"][0]["label"] = label
                subject["document_bytes"] = canonical_json(subject["payload"])
                rules = [
                    item["rule_id"]
                    for item in make_finding_set(subject)["findings"]
                ]
                self.assertNotIn("TCW-D009", rules)
                self.assertNotIn("TCW-D010", rules)

    def test_d010_boundaries_unicode_and_blank_lines(self) -> None:
        cases = {
            "one-letter-left": ("a-\nword " + "x" * 200, False),
            "uppercase-right": ("alpha-\nWord " + "x" * 200, False),
            "blank-line": ("alpha-\n\nword " + "x" * 200, False),
            "crlf-horizontal": ("alpha- \t\r\n \tword " + "x" * 200, True),
            "unicode": ("άλφα-\nβήτα " + "x" * 200, True),
        }
        for name, (value, expected) in cases.items():
            with self.subTest(name=name):
                document = DoclingDocument(name=name)
                document.add_text(DocItemLabel.TEXT, value)
                payload = document.model_dump(
                    mode="json", by_alias=True, exclude_none=True
                )
                subject = self.subject()
                subject["payload"] = payload
                subject["document_bytes"] = canonical_json(payload)
                rules = {
                    item["rule_id"]
                    for item in make_finding_set(subject)["findings"]
                }
                self.assertEqual("TCW-D010" in rules, expected)

    def test_d009_and_d010_cover_table_cells_with_coordinates(self) -> None:
        document = DoclingDocument(name="table-cells")
        document.add_text(DocItemLabel.TEXT, "x" * 200)
        document.add_table(
            TableData(
                num_rows=1,
                num_cols=1,
                table_cells=[
                    TableCell(
                        start_row_offset_idx=0,
                        end_row_offset_idx=1,
                        start_col_offset_idx=0,
                        end_col_offset_idx=1,
                        text="Cell\u00a0 value and inter-\noperable text",
                    )
                ],
            )
        )
        payload = document.model_dump(mode="json", by_alias=True, exclude_none=True)
        subject = self.subject()
        subject["payload"] = payload
        subject["document_bytes"] = canonical_json(payload)
        findings = [
            item
            for item in make_finding_set(subject)["findings"]
            if item["rule_id"] in {"TCW-D009", "TCW-D010"}
            and item["document_refs"] == ["#/tables/0"]
        ]
        self.assertEqual([item["rule_id"] for item in findings], ["TCW-D009", "TCW-D010"])
        self.assertTrue(
            all(
                item["evidence"]["row"] == 0
                and item["evidence"]["column"] == 0
                for item in findings
            )
        )

    def test_repeated_boilerplate_edit_moves_body_to_furniture(self) -> None:
        document = DoclingDocument(name="margin")
        item = document.add_text(DocItemLabel.TEXT, "Footer")
        payload = document.model_dump(mode="json", by_alias=True, exclude_none=True)
        changed = _apply_edits(
            payload,
            [
                {
                    "target": {"ref": item.self_ref, "field": "content_layer"},
                    "before": {"content_layer": "body", "body_index": 0},
                    "after": {"content_layer": "furniture"},
                }
            ],
        )
        self.assertEqual(changed["texts"][0]["content_layer"], "furniture")
        self.assertEqual(changed["body"]["children"], [])
        self.assertEqual(changed["furniture"]["children"], [{"$ref": "#/texts/0"}])
        self.assertEqual(payload["texts"][0]["content_layer"], "body")

    def test_approve_verify_rediagnose_chain_and_reject(self) -> None:
        with tempfile.TemporaryDirectory() as directory, mock.patch(
            "tiny_corpus_workbench.v03.active_locked_runtime", return_value=RUNTIME
        ):
            root = Path(directory)
            observation = self.observation(root / "observations")
            diagnosis = cli._diagnosis_callable("v03", "diagnose")(
                observation, root / "diagnoses"
            )
            self.assertEqual(
                verify_diagnosis(diagnosis, observation)["derivation_state"]["status"],
                "MATCH",
            )
            findings = json.loads((diagnosis / "findings.json").read_text("utf-8"))
            whitespace = next(
                item for item in findings["findings"] if item["rule_id"] == "TCW-D009"
            )
            draft = root / "whitespace-decision.json"
            cli._diagnosis_callable("v03", "draft_refinement")(
                diagnosis, whitespace["finding_id"], observation, draft
            )
            value = json.loads(draft.read_text("utf-8"))
            value["decision"] = {
                "state": "APPROVED",
                "decided_by": "test-owner",
                "note": "Mechanical cleanup.",
            }
            draft.write_bytes(canonical_json(value))
            revision = cli._diagnosis_callable("v03", "resolve_refinement")(
                draft, diagnosis, observation, root / "revisions"
            )
            result = verify_refinement(revision, diagnosis, observation)
            self.assertEqual(result["artifact_integrity"]["status"], "VERIFIED")
            self.assertEqual(result["derivation_state"]["status"], "MATCH")
            self.assertEqual(result["reversibility_state"]["status"], "MATCH")
            original = json.loads(
                (observation / "docling/document.json").read_text("utf-8")
            )
            prepared = json.loads(
                (revision / "prepared/document.json").read_text("utf-8")
            )
            self.assertEqual(
                original["texts"][0]["orig"], prepared["texts"][0]["orig"]
            )
            self.assertEqual(
                original["texts"][0]["self_ref"], prepared["texts"][0]["self_ref"]
            )

            diagnosis2 = cli._diagnosis_callable("v03", "diagnose")(
                revision, root / "diagnoses"
            )
            findings2 = json.loads((diagnosis2 / "findings.json").read_text("utf-8"))
            self.assertEqual(findings2["subject"]["kind"], "REVISION")
            dehyphenation = next(
                item for item in findings2["findings"] if item["rule_id"] == "TCW-D010"
            )
            rejected_draft = root / "rejected-decision.json"
            cli._diagnosis_callable("v03", "draft_refinement")(
                diagnosis2, dehyphenation["finding_id"], revision, rejected_draft
            )
            rejected = json.loads(rejected_draft.read_text("utf-8"))
            rejected["decision"] = {
                "state": "REJECTED",
                "decided_by": "test-owner",
                "note": "Keep this line ending.",
            }
            rejected_draft.write_bytes(canonical_json(rejected))
            record = cli._diagnosis_callable("v03", "resolve_refinement")(
                rejected_draft, diagnosis2, revision, root / "rejected"
            )
            manifest = json.loads(
                (record / "refinement-manifest.json").read_text("utf-8")
            )
            self.assertEqual(manifest["status"], "REJECTED")
            self.assertIsNone(manifest["revision_id"])
            self.assertFalse((record / "prepared").exists())
            self.assertEqual(
                verify_refinement(record)["reversibility_state"]["status"],
                "NOT_APPLICABLE",
            )

            draft2 = root / "dehyphenation-decision.json"
            cli._diagnosis_callable("v03", "draft_refinement")(
                diagnosis2, dehyphenation["finding_id"], revision, draft2
            )
            value2 = json.loads(draft2.read_text("utf-8"))
            value2["decision"] = {
                "state": "APPROVED",
                "decided_by": "test-owner",
                "note": None,
            }
            draft2.write_bytes(canonical_json(value2))
            revision2 = cli._diagnosis_callable("v03", "resolve_refinement")(
                draft2, diagnosis2, revision, root / "revisions"
            )
            history = json.loads((revision2 / "history.json").read_text("utf-8"))
            self.assertEqual(len(history["transformations"]), 2)


if __name__ == "__main__":
    unittest.main()
