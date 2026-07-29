from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

from tiny_corpus_workbench.cli import observe
from tiny_corpus_workbench.v03 import (
    diagnose,
    draft_refinement,
    resolve_refinement,
    verify_refinement,
)


class V05RefinementWorkflowTests(unittest.TestCase):
    def decision(
        self,
        diagnosis: Path,
        base: Path,
        output: Path,
        *,
        state: str,
        rule_id: str = "TCW-D009",
    ) -> Path:
        findings = json.loads((diagnosis / "findings.json").read_text("utf-8"))
        finding_id = next(
            item["finding_id"]
            for item in findings["findings"]
            if item["rule_id"] == rule_id
        )
        draft_refinement(diagnosis, finding_id, base, output)
        draft = json.loads(output.read_text("utf-8"))
        draft["decision"] = {
            "state": state,
            "decided_by": "integration-owner",
            "note": "v0.5 workflow",
        }
        output.write_text(
            json.dumps(draft, sort_keys=True, separators=(",", ":")) + "\n",
            "utf-8",
        )
        return output

    def test_approved_rejected_and_chained_records_verify(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            source = root / "combined.md"
            source.write_text(
                "# Combined Refinement\n\n"
                "This\u00a0 first  paragraph contains stable project-authored text. "
                + "Evidence remains visible. " * 12
                + "\n\n"
                + "This\u00a0 second  paragraph preserves another independent target. "
                + "Lineage remains inspectable. " * 12,
                "utf-8",
            )
            source_before = source.read_bytes()
            code, observation = observe(
                str(source), root / "observations", Path("unused")
            )
            self.assertEqual(int(code), 0)
            first_diagnosis = diagnose(observation, root / "diagnoses")

            approved_decision = self.decision(
                first_diagnosis,
                observation,
                root / "approved.json",
                state="APPROVED",
            )
            first_revision = resolve_refinement(
                approved_decision,
                first_diagnosis,
                observation,
                root / "revisions",
            )
            approved = verify_refinement(
                first_revision, first_diagnosis, observation
            )
            self.assertEqual(approved.artifact_integrity.status, "VERIFIED")
            self.assertEqual(approved.derivation_state.status, "MATCH")
            self.assertEqual(approved.reversibility_state.status, "MATCH")

            rejected_decision = self.decision(
                first_diagnosis,
                observation,
                root / "rejected.json",
                state="REJECTED",
            )
            rejected_revision = resolve_refinement(
                rejected_decision,
                first_diagnosis,
                observation,
                root / "rejected-revisions",
            )
            rejected = verify_refinement(
                rejected_revision, first_diagnosis, observation
            )
            self.assertEqual(rejected.artifact_integrity.status, "VERIFIED")
            self.assertEqual(
                rejected.derivation_state.status, "NOT_APPLICABLE"
            )
            self.assertFalse((rejected_revision / "prepared").exists())

            second_diagnosis = diagnose(first_revision, root / "diagnoses")
            second_findings = json.loads(
                (second_diagnosis / "findings.json").read_text("utf-8")
            )
            self.assertEqual(
                sum(
                    item["rule_id"] == "TCW-D009"
                    for item in second_findings["findings"]
                ),
                1,
            )
            chained_decision = self.decision(
                second_diagnosis,
                first_revision,
                root / "chained.json",
                state="APPROVED",
                rule_id="TCW-D009",
            )
            second_revision = resolve_refinement(
                chained_decision,
                second_diagnosis,
                first_revision,
                root / "chained-revisions",
            )
            chained = verify_refinement(
                second_revision, second_diagnosis, first_revision
            )
            self.assertEqual(chained.artifact_integrity.status, "VERIFIED")
            self.assertEqual(chained.derivation_state.status, "MATCH")
            self.assertEqual(chained.reversibility_state.status, "MATCH")
            first_manifest = json.loads(
                (first_revision / "refinement-manifest.json").read_text("utf-8")
            )
            self.assertIsNone(first_manifest["parent"])
            second_manifest = json.loads(
                (second_revision / "refinement-manifest.json").read_text("utf-8")
            )
            self.assertEqual(
                second_manifest["parent"]["revision_id"],
                first_manifest["revision_id"],
            )
            self.assertEqual(source.read_bytes(), source_before)


if __name__ == "__main__":
    unittest.main()
