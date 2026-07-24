from __future__ import annotations

import hashlib
import json
import shutil
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from docling_core.types.doc import (
    DocItemLabel,
    DoclingDocument,
    BoundingBox,
    ProvenanceItem,
    Size,
    TableCell,
    TableData,
)

from tiny_corpus_workbench import cli
from tiny_corpus_workbench.artifacts import REQUIRED_MODEL_FILES, canonical_json
from tiny_corpus_workbench.domain import InputError
from tiny_corpus_workbench.v03 import (
    _apply_edits,
    _normalize_whitespace,
    make_finding_set,
    verify_diagnosis,
    verify_refinement,
)


SOURCE = Path("fixtures/golden/policy-memo.md")
PDF_SOURCE = Path("fixtures/diagnosis/v0.2/repeated-margin.pdf")
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


def docling_with_repeated_margins(source: Path, destination: Path, model_root: Path):
    destination.mkdir(parents=True)
    document = DoclingDocument(name="repeated-margins")
    for page in range(1, 4):
        document.add_page(page, Size(width=612, height=792))
        document.add_text(
            DocItemLabel.TEXT,
            "Repeated margin text",
            prov=ProvenanceItem(
                page_no=page,
                bbox=BoundingBox(l=72, t=40, r=200, b=20),
                charspan=(0, 20),
            ),
        )
    document.add_text(DocItemLabel.TEXT, "Body content " * 30)
    document.save_as_json(destination / "document.json")
    document.save_as_markdown(destination / "document.md")
    return "success", {"name": "DoclingDocument", "version": "1.10.0"}


class ControlledRevisionTests(unittest.TestCase):
    def observation(
        self,
        root: Path,
        converter=docling_with_refinements,
        source: Path = SOURCE,
    ) -> Path:
        model_root = Path("unused")
        if source.suffix == ".pdf":
            model_root = root.parent / "models"
            for relative in REQUIRED_MODEL_FILES:
                path = model_root / relative
                path.parent.mkdir(parents=True, exist_ok=True)
                path.write_text("test-model", "utf-8")
        with mock.patch(
            "tiny_corpus_workbench.extractors.docling.convert",
            side_effect=converter,
        ), mock.patch(
            "tiny_corpus_workbench.extractors.markitdown.convert",
            side_effect=markitdown,
        ):
            code, published = cli.observe(str(source), root, model_root)
        self.assertEqual(int(code), 0)
        return published

    def approve_rule(
        self,
        root: Path,
        rule_id: str,
        *,
        converter=docling_with_refinements,
        source: Path = SOURCE,
        output_name: str = "revisions",
    ) -> tuple[Path, Path, Path]:
        observation = self.observation(root / "observations", converter, source)
        diagnosis = cli._diagnosis_callable("v03", "diagnose")(
            observation, root / "diagnoses"
        )
        findings = json.loads((diagnosis / "findings.json").read_text("utf-8"))
        finding = next(
            item for item in findings["findings"] if item["rule_id"] == rule_id
        )
        draft = root / f"{rule_id}-decision.json"
        cli._diagnosis_callable("v03", "draft_refinement")(
            diagnosis, finding["finding_id"], observation, draft
        )
        value = json.loads(draft.read_text("utf-8"))
        value["decision"] = {
            "state": "APPROVED",
            "decided_by": "test-owner",
            "note": None,
        }
        draft.write_bytes(canonical_json(value))
        revision = cli._diagnosis_callable("v03", "resolve_refinement")(
            draft, diagnosis, observation, root / output_name
        )
        return observation, diagnosis, revision

    def copy_and_break_inverse(self, revision: Path, destination: Path) -> Path:
        copied = destination / revision.name
        destination.mkdir(parents=True)
        shutil.copytree(revision, copied)
        manifest = json.loads(
            (copied / "refinement-manifest.json").read_text("utf-8")
        )
        decision = json.loads((copied / "decision.json").read_text("utf-8"))
        transformation = json.loads(
            (copied / "transformation.json").read_text("utf-8")
        )
        history = json.loads((copied / "history.json").read_text("utf-8"))
        broken = transformation["inverse_edits"]
        if broken[0]["target"]["field"] == "text":
            broken[0]["after"] += "BROKEN"
        else:
            broken[0]["after"]["body_index"] += 100
        decision["proposal"]["inverse_edits"] = broken
        proposal_identity = {
            key: value
            for key, value in decision["proposal"].items()
            if key != "draft_id"
        }
        draft_id = hashlib.sha256(
            canonical_json(proposal_identity).rstrip(b"\n")
        ).hexdigest()
        decision["proposal"]["draft_id"] = draft_id
        manifest["draft_id"] = draft_id
        prepared_sha256 = hashlib.sha256(
            (copied / "prepared/document.json").read_bytes()
        ).hexdigest()
        revision_id = hashlib.sha256(
            canonical_json(
                {
                    "parent": manifest["base"]["subject_id"],
                    "base_sha256": manifest["base"]["canonical_document_sha256"],
                    "draft_id": draft_id,
                    "prepared_sha256": prepared_sha256,
                }
            ).rstrip(b"\n")
        ).hexdigest()
        transformation["inverse_edits"] = broken
        transformation["decision_id"] = draft_id
        transformation["revision_id"] = revision_id
        transformation["transformation_id"] = hashlib.sha256(
            canonical_json(
                {
                    "revision_id": revision_id,
                    "draft_id": draft_id,
                    "refiner": transformation["refiner"],
                }
            ).rstrip(b"\n")
        ).hexdigest()
        manifest["revision_id"] = revision_id
        history["revision_id"] = revision_id
        history["transformations"][-1] = transformation
        for name, value in (
            ("decision.json", decision),
            ("transformation.json", transformation),
            ("history.json", history),
        ):
            (copied / name).write_bytes(canonical_json(value))
        for descriptor in manifest["artifacts"]:
            path = copied / descriptor["path"]
            descriptor["size"] = path.stat().st_size
            descriptor["sha256"] = hashlib.sha256(path.read_bytes()).hexdigest()
        (copied / "refinement-manifest.json").write_bytes(canonical_json(manifest))
        return copied

    def copy_record(self, record: Path, destination: Path) -> Path:
        copied = destination / record.name
        destination.mkdir(parents=True)
        shutil.copytree(record, copied)
        return copied

    def refresh_descriptors(
        self, record: Path, manifest: dict, *relative_paths: str
    ) -> None:
        selected = set(relative_paths)
        for descriptor in manifest["artifacts"]:
            if descriptor["path"] in selected:
                path = record / descriptor["path"]
                descriptor["size"] = path.stat().st_size
                descriptor["sha256"] = hashlib.sha256(path.read_bytes()).hexdigest()
        (record / "refinement-manifest.json").write_bytes(canonical_json(manifest))

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

    def test_d009_offsets_include_only_changed_maximal_spans(self) -> None:
        subject = self.subject()
        value = "A B  C\u00a0D \n E\r\nF\rG"
        subject["payload"]["texts"][0]["text"] = value
        subject["payload"]["texts"][0]["orig"] = value
        subject["document_bytes"] = canonical_json(subject["payload"])
        finding = next(
            item
            for item in make_finding_set(subject)["findings"]
            if item["rule_id"] == "TCW-D009"
        )
        self.assertEqual(
            finding["evidence"]["code_point_offsets"],
            [3, 6, 8, 10, 12, 15],
        )
        self.assertNotIn(1, finding["evidence"]["code_point_offsets"])

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
            "numeric-left-boundary": ("alpha²-\nbeta " + "x" * 200, False),
            "numeric-right-boundary": ("alpha-\n²beta " + "x" * 200, False),
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
                    "before": {
                        "content_layer": "body",
                        "body_index": 0,
                        "parent": {"$ref": "#/body"},
                    },
                    "after": {
                        "content_layer": "furniture",
                        "furniture_index": 0,
                        "parent": {"$ref": "#/furniture"},
                    },
                }
            ],
        )
        self.assertEqual(changed["texts"][0]["content_layer"], "furniture")
        self.assertEqual(changed["body"]["children"], [])
        self.assertEqual(changed["furniture"]["children"], [{"$ref": "#/texts/0"}])
        self.assertEqual(payload["texts"][0]["content_layer"], "body")

    def test_all_refiners_replay_forward_and_inverse_edits(self) -> None:
        cases = (
            ("TCW-D009", docling_with_refinements, SOURCE),
            ("TCW-D010", docling_with_refinements, SOURCE),
            ("TCW-D007", docling_with_repeated_margins, PDF_SOURCE),
        )
        with tempfile.TemporaryDirectory() as directory, mock.patch(
            "tiny_corpus_workbench.v03.active_locked_runtime", return_value=RUNTIME
        ):
            root = Path(directory)
            for rule_id, converter, source in cases:
                with self.subTest(rule_id=rule_id):
                    case_root = root / rule_id
                    observation, diagnosis, revision = self.approve_rule(
                        case_root,
                        rule_id,
                        converter=converter,
                        source=source,
                    )
                    result = verify_refinement(revision, diagnosis, observation)
                    self.assertEqual(result["artifact_integrity"]["status"], "VERIFIED")
                    self.assertEqual(result["derivation_state"]["status"], "MATCH")
                    self.assertEqual(result["reversibility_state"]["status"], "MATCH")
                    transformation = json.loads(
                        (revision / "transformation.json").read_text("utf-8")
                    )
                    self.assertNotIn("base_document_base64", transformation)
                    broken = self.copy_and_break_inverse(
                        revision, case_root / "broken"
                    )
                    broken_result = verify_refinement(
                        broken, diagnosis, observation
                    )
                    self.assertEqual(
                        broken_result["artifact_integrity"]["status"], "VERIFIED"
                    )
                    self.assertEqual(
                        broken_result["derivation_state"]["status"], "MATCH"
                    )
                    self.assertIn(
                        broken_result["reversibility_state"]["status"],
                        {"MISMATCH", "ERROR"},
                    )

    def test_hash_consistent_semantic_tampering_is_rejected(self) -> None:
        with tempfile.TemporaryDirectory() as directory, mock.patch(
            "tiny_corpus_workbench.v03.active_locked_runtime", return_value=RUNTIME
        ):
            root = Path(directory)
            observation, diagnosis, revision = self.approve_rule(
                root / "base", "TCW-D009"
            )
            for operation in (
                "artifact-role",
                "duplicate-inventory",
                "history-tail",
                "history-noncanonical",
                "transformation-id",
                "revision-id",
                "null-revision",
            ):
                with self.subTest(operation=operation):
                    copied = self.copy_record(revision, root / operation)
                    manifest = json.loads(
                        (copied / "refinement-manifest.json").read_text("utf-8")
                    )
                    transformation = json.loads(
                        (copied / "transformation.json").read_text("utf-8")
                    )
                    history = json.loads(
                        (copied / "history.json").read_text("utf-8")
                    )
                    changed = []
                    if operation == "artifact-role":
                        descriptor = next(
                            item
                            for item in manifest["artifacts"]
                            if item["path"] == "transformation.json"
                        )
                        descriptor["role"] = "transformation-history"
                    elif operation == "duplicate-inventory":
                        manifest["artifacts"].append(manifest["artifacts"][0])
                    elif operation == "history-tail":
                        history["transformations"][-1]["decided_by"] = "other"
                        (copied / "history.json").write_bytes(canonical_json(history))
                        changed.append("history.json")
                    elif operation == "history-noncanonical":
                        (copied / "history.json").write_text(
                            json.dumps(history, indent=2), "utf-8"
                        )
                        changed.append("history.json")
                    elif operation == "transformation-id":
                        transformation["transformation_id"] = "f" * 64
                        history["transformations"][-1] = transformation
                        (copied / "transformation.json").write_bytes(
                            canonical_json(transformation)
                        )
                        (copied / "history.json").write_bytes(canonical_json(history))
                        changed.extend(("transformation.json", "history.json"))
                    elif operation == "revision-id":
                        manifest["revision_id"] = "e" * 64
                        transformation["revision_id"] = "e" * 64
                        history["revision_id"] = "e" * 64
                        history["transformations"][-1] = transformation
                        (copied / "transformation.json").write_bytes(
                            canonical_json(transformation)
                        )
                        (copied / "history.json").write_bytes(canonical_json(history))
                        changed.extend(("transformation.json", "history.json"))
                    else:
                        manifest["revision_id"] = None
                    self.refresh_descriptors(copied, manifest, *changed)
                    result = verify_refinement(copied, diagnosis, observation)
                    self.assertEqual(
                        result["artifact_integrity"]["status"], "BROKEN"
                    )

    def test_rejected_status_requires_exact_inventory_and_null_revision(self) -> None:
        with tempfile.TemporaryDirectory() as directory, mock.patch(
            "tiny_corpus_workbench.v03.active_locked_runtime", return_value=RUNTIME
        ):
            root = Path(directory)
            observation = self.observation(root / "observations")
            diagnosis = cli._diagnosis_callable("v03", "diagnose")(
                observation, root / "diagnoses"
            )
            findings = json.loads((diagnosis / "findings.json").read_text("utf-8"))
            finding = next(
                item for item in findings["findings"] if item["rule_id"] == "TCW-D009"
            )
            draft = root / "rejected.json"
            cli._diagnosis_callable("v03", "draft_refinement")(
                diagnosis, finding["finding_id"], observation, draft
            )
            value = json.loads(draft.read_text("utf-8"))
            value["decision"] = {
                "state": "REJECTED",
                "decided_by": "test-owner",
                "note": None,
            }
            draft.write_bytes(canonical_json(value))
            rejected = cli._diagnosis_callable("v03", "resolve_refinement")(
                draft, diagnosis, observation, root / "rejected"
            )
            for operation in ("revision-id", "extra-inventory"):
                with self.subTest(operation=operation):
                    copied = self.copy_record(rejected, root / operation)
                    manifest = json.loads(
                        (copied / "refinement-manifest.json").read_text("utf-8")
                    )
                    if operation == "revision-id":
                        manifest["revision_id"] = "f" * 64
                    else:
                        manifest["artifacts"].append(manifest["artifacts"][0])
                    (copied / "refinement-manifest.json").write_bytes(
                        canonical_json(manifest)
                    )
                    self.assertEqual(
                        verify_refinement(copied)["artifact_integrity"]["status"],
                        "BROKEN",
                    )

    def test_refinement_nested_publication_symlinks_are_rejected(self) -> None:
        with tempfile.TemporaryDirectory() as directory, mock.patch(
            "tiny_corpus_workbench.v03.active_locked_runtime", return_value=RUNTIME
        ):
            root = Path(directory)
            observation = self.observation(root / "observations")
            diagnosis = cli._diagnosis_callable("v03", "diagnose")(
                observation, root / "diagnoses"
            )
            findings = json.loads((diagnosis / "findings.json").read_text("utf-8"))
            finding = next(
                item for item in findings["findings"] if item["rule_id"] == "TCW-D009"
            )
            draft = root / "approved.json"
            cli._diagnosis_callable("v03", "draft_refinement")(
                diagnosis, finding["finding_id"], observation, draft
            )
            value = json.loads(draft.read_text("utf-8"))
            value["decision"] = {
                "state": "APPROVED",
                "decided_by": "test-owner",
                "note": None,
            }
            draft.write_bytes(canonical_json(value))
            observation_manifest = json.loads(
                (observation / "manifest.json").read_text("utf-8")
            )
            source_key = observation_manifest["source"]["key"]
            origin = observation_manifest["observation_id"]
            outside = root / "outside"
            outside.mkdir()
            for level in ("source-key", "origin"):
                with self.subTest(level=level):
                    output = root / f"output-{level}"
                    output.mkdir()
                    if level == "source-key":
                        (output / source_key).symlink_to(
                            outside, target_is_directory=True
                        )
                    else:
                        (output / source_key).mkdir()
                        (output / source_key / origin).symlink_to(
                            outside, target_is_directory=True
                        )
                    with self.assertRaises(InputError):
                        cli._diagnosis_callable("v03", "resolve_refinement")(
                            draft, diagnosis, observation, output
                        )
                    self.assertFalse(
                        any(outside.rglob("refinement-manifest.json"))
                    )

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

            broken_chain = self.copy_record(revision2, root / "broken-chain")
            broken_manifest = json.loads(
                (broken_chain / "refinement-manifest.json").read_text("utf-8")
            )
            broken_history = json.loads(
                (broken_chain / "history.json").read_text("utf-8")
            )
            broken_history["transformations"][0][
                "prepared_document_sha256"
            ] = "f" * 64
            (broken_chain / "history.json").write_bytes(
                canonical_json(broken_history)
            )
            self.refresh_descriptors(
                broken_chain, broken_manifest, "history.json"
            )
            self.assertEqual(
                verify_refinement(broken_chain)["artifact_integrity"]["status"],
                "BROKEN",
            )

            changed_parent_history = self.copy_record(
                revision2, root / "changed-parent-history"
            )
            changed_manifest = json.loads(
                (changed_parent_history / "refinement-manifest.json").read_text(
                    "utf-8"
                )
            )
            changed_history = json.loads(
                (changed_parent_history / "history.json").read_text("utf-8")
            )
            changed_history["transformations"][0]["decided_by"] = "changed"
            (changed_parent_history / "history.json").write_bytes(
                canonical_json(changed_history)
            )
            self.refresh_descriptors(
                changed_parent_history, changed_manifest, "history.json"
            )
            changed_result = verify_refinement(
                changed_parent_history, diagnosis2, revision
            )
            self.assertEqual(
                changed_result["artifact_integrity"]["status"], "VERIFIED"
            )
            self.assertEqual(changed_result["base_state"]["status"], "CHANGED")

            changed_diagnosis = root / "changed-diagnosis" / diagnosis2.name
            changed_diagnosis.parent.mkdir()
            shutil.copytree(diagnosis2, changed_diagnosis)
            diagnosis_manifest = json.loads(
                (changed_diagnosis / "diagnosis-manifest.json").read_text("utf-8")
            )
            (changed_diagnosis / "report.md").write_text(
                "hash-consistent but semantically false\n", "utf-8"
            )
            report_descriptor = next(
                item
                for item in diagnosis_manifest["artifacts"]
                if item["path"] == "report.md"
            )
            report_descriptor["size"] = (
                changed_diagnosis / "report.md"
            ).stat().st_size
            report_descriptor["sha256"] = hashlib.sha256(
                (changed_diagnosis / "report.md").read_bytes()
            ).hexdigest()
            (changed_diagnosis / "diagnosis-manifest.json").write_bytes(
                canonical_json(diagnosis_manifest)
            )
            diagnosis_result = verify_refinement(
                revision2, changed_diagnosis, revision
            )
            self.assertEqual(
                diagnosis_result["diagnosis_state"]["status"], "CHANGED"
            )


if __name__ == "__main__":
    unittest.main()
