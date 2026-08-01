from __future__ import annotations

import hashlib
import io
import json
import shutil
import tempfile
import unittest
from copy import deepcopy
from concurrent.futures import ThreadPoolExecutor
from contextlib import redirect_stderr, redirect_stdout
from datetime import UTC, datetime
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

from tiny_corpus_workbench import cli, v03 as v03_module
from tiny_corpus_workbench.artifacts import REQUIRED_MODEL_FILES, canonical_json
from tiny_corpus_workbench.domain import (
    InputError,
    IntegrityError,
)
from tiny_corpus_workbench.v03 import (
    _apply_edits,
    _diagnosis_identity,
    _diagnosis_report,
    _normalize_whitespace,
    _prepared_bytes,
    _render_refinement,
    _target,
    make_finding_set,
    snapshot_tree,
    verify_diagnosis,
    verify_refinement,
)
SOURCE = Path("fixtures/golden/policy-memo.md")
PDF_SOURCE = Path("fixtures/diagnosis/repeated-margin.pdf")


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
    def test_refiner_identifiers_and_rule_mappings_are_exact(self) -> None:
        self.assertEqual(
            v03_module.REFINERS,
            {
                "D009": {
                    "refiner_id": "R001",
                    "name": "WHITESPACE_NORMALIZATION",
                    "version": "1",
                },
                "D007": {
                    "refiner_id": "R002",
                    "name": "REPEATED_BOILERPLATE_REMOVAL",
                    "version": "1",
                },
                "D010": {
                    "refiner_id": "R003",
                    "name": "DETERMINISTIC_DEHYPHENATION",
                    "version": "1",
                },
            },
        )

    def invoke(self, *arguments: str) -> tuple[int, str, str]:
        stdout, stderr = io.StringIO(), io.StringIO()
        with redirect_stdout(stdout), redirect_stderr(stderr):
            code = cli.main(list(arguments))
        return code, stdout.getvalue(), stderr.getvalue()

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
        draft = root / f"{rule_id}-proposal.json"
        cli._diagnosis_callable("v03", "draft_refinement")(
            diagnosis, finding["finding_id"], observation, draft
        )
        revision = cli._diagnosis_callable("v03", "resolve_refinement")(
            draft, diagnosis, observation, root / output_name, "APPROVED"
        )
        return observation, diagnosis, revision

    def copy_and_break_inverse(self, revision: Path, destination: Path) -> Path:
        copied = destination / revision.name
        destination.mkdir(parents=True)
        shutil.copytree(revision, copied)
        manifest = json.loads(
            (copied / "refinement-manifest.json").read_text("utf-8")
        )
        proposal = json.loads((copied / "proposal.json").read_text("utf-8"))
        transformation = json.loads(
            (copied / "transformation.json").read_text("utf-8")
        )
        history = json.loads((copied / "history.json").read_text("utf-8"))
        broken = transformation["inverse_edits"]
        if broken[0]["target"]["field"] == "text":
            broken[0]["after"] += "BROKEN"
        else:
            broken[0]["after"]["body_index"] += 100
        proposal["inverse_edits"] = broken
        proposal_identity = {
            key: value
            for key, value in proposal.items()
            if key != "draft_id"
        }
        draft_id = hashlib.sha256(
            canonical_json(proposal_identity).rstrip(b"\n")
        ).hexdigest()
        proposal["draft_id"] = draft_id
        manifest["draft_id"] = draft_id
        prepared_sha256 = hashlib.sha256(
            (copied / "prepared/document.json").read_bytes()
        ).hexdigest()
        revision_id = hashlib.sha256(
            canonical_json(
                {
                    "parent": manifest["base"]["identity_value"],
                    "base_sha256": manifest["base"]["canonical_document_sha256"],
                    "draft_id": draft_id,
                    "prepared_sha256": prepared_sha256,
                }
            ).rstrip(b"\n")
        ).hexdigest()
        transformation["inverse_edits"] = broken
        transformation["draft_id"] = draft_id
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
            ("proposal.json", proposal),
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

    def approve_existing(
        self,
        root: Path,
        diagnosis: Path,
        base: Path,
        rule_id: str,
    ) -> Path:
        findings = json.loads((diagnosis / "findings.json").read_text("utf-8"))
        finding = next(
            item for item in findings["findings"] if item["rule_id"] == rule_id
        )
        draft = root / f"{rule_id}-proposal.json"
        cli._diagnosis_callable("v03", "draft_refinement")(
            diagnosis, finding["finding_id"], base, draft
        )
        return cli._diagnosis_callable("v03", "resolve_refinement")(
            draft, diagnosis, base, root / "revisions", "APPROVED"
        )

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

    def rewrite_proposal_identity_chain(
        self,
        record: Path,
        mutate,
    ) -> None:
        manifest = json.loads(
            (record / "refinement-manifest.json").read_text("utf-8")
        )
        proposal = json.loads((record / "proposal.json").read_text("utf-8"))
        transformation = json.loads(
            (record / "transformation.json").read_text("utf-8")
        )
        history = json.loads((record / "history.json").read_text("utf-8"))
        mutate(proposal)
        proposal_identity = {
            key: value for key, value in proposal.items() if key != "draft_id"
        }
        draft_id = hashlib.sha256(
            canonical_json(proposal_identity).rstrip(b"\n")
        ).hexdigest()
        proposal["draft_id"] = draft_id
        manifest["draft_id"] = draft_id
        prepared_sha256 = hashlib.sha256(
            (record / "prepared/document.json").read_bytes()
        ).hexdigest()
        revision_id = hashlib.sha256(
            canonical_json(
                {
                    "parent": manifest["base"]["identity_value"],
                    "base_sha256": manifest["base"][
                        "canonical_document_sha256"
                    ],
                    "draft_id": draft_id,
                    "prepared_sha256": prepared_sha256,
                }
            ).rstrip(b"\n")
        ).hexdigest()
        transformation.update(
            {
                "revision_id": revision_id,
                "finding_id": proposal["finding"]["finding_id"],
                "draft_id": draft_id,
                "refiner": proposal["refiner"],
                "affected_refs": proposal["affected_refs"],
                "forward_edits": proposal["forward_edits"],
                "inverse_edits": proposal["inverse_edits"],
                "prepared_document_sha256": prepared_sha256,
            }
        )
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
            ("proposal.json", proposal),
            ("transformation.json", transformation),
            ("history.json", history),
        ):
            (record / name).write_bytes(canonical_json(value))
        (record / "report.md").write_bytes(_render_refinement(manifest, proposal))
        self.refresh_descriptors(
            record,
            manifest,
            "proposal.json",
            "transformation.json",
            "history.json",
            "prepared/document.json",
            "prepared/document.md",
            "report.md",
        )

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
            for rule in ("D009", "D010")
        }
        self.assertEqual(len(by_rule["D009"]), 1)
        self.assertEqual(len(by_rule["D010"]), 1)
        self.assertEqual(
            by_rule["D009"][0]["evidence"]["code_point_offsets"],
            sorted(by_rule["D009"][0]["evidence"]["code_point_offsets"]),
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
            if item["rule_id"] == "D009"
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
                self.assertNotIn("D009", rules)
                self.assertNotIn("D010", rules)

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
                self.assertEqual("D010" in rules, expected)

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
            if item["rule_id"] in {"D009", "D010"}
            and item["document_refs"] == ["#/tables/0"]
        ]
        self.assertEqual([item["rule_id"] for item in findings], ["D009", "D010"])
        self.assertTrue(
            all(
                item["evidence"]["row"] == 0
                and item["evidence"]["column"] == 0
                for item in findings
            )
        )

    def test_table_cell_target_rejects_incomplete_coordinates(self) -> None:
        document = DoclingDocument(name="table-cell-target")
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
                        text="Cell value",
                    )
                ],
            )
        )
        payload = document.model_dump(
            mode="json", by_alias=True, exclude_none=True
        )
        for incomplete in ({"row": 0}, {"column": 0}):
            with self.subTest(coordinates=incomplete), self.assertRaisesRegex(
                IntegrityError, "coordinates are incomplete"
            ):
                _target(payload, "#/tables/0", incomplete)

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

    def test_apply_edits_rejects_noncanonical_target_and_membership_matrix(
        self,
    ) -> None:
        document = DoclingDocument(name="invalid-membership")
        item = document.add_text(DocItemLabel.TEXT, "Footer")
        payload = document.model_dump(
            mode="json", by_alias=True, exclude_none=True
        )
        valid = {
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
        cases = {}

        content_coordinates = deepcopy(valid)
        content_coordinates["target"].update({"row": 0, "column": 0})
        cases["content-layer-coordinates"] = content_coordinates

        body_with_furniture_index = deepcopy(valid)
        body_with_furniture_index["before"] = {
            "content_layer": "body",
            "furniture_index": 0,
            "parent": {"$ref": "#/body"},
        }
        cases["body-with-furniture-index"] = body_with_furniture_index

        furniture_with_body_index = deepcopy(valid)
        furniture_with_body_index["after"] = {
            "content_layer": "furniture",
            "body_index": 0,
            "parent": {"$ref": "#/furniture"},
        }
        cases["furniture-with-body-index"] = furniture_with_body_index

        mismatched_parent = deepcopy(valid)
        mismatched_parent["after"]["parent"] = {"$ref": "#/body"}
        cases["mismatched-parent"] = mismatched_parent

        text_coordinates = {
            "target": {
                "ref": item.self_ref,
                "field": "text",
                "row": 0,
                "column": 0,
            },
            "before": "Footer",
            "after": "Changed",
        }
        cases["non-table-text-coordinates"] = text_coordinates

        table_without_coordinates = {
            "target": {"ref": "#/tables/0", "field": "text"},
            "before": "Footer",
            "after": "Changed",
        }
        cases["table-without-coordinates"] = table_without_coordinates

        baseline = canonical_json(payload)
        for label, edit in cases.items():
            with self.subTest(label=label), self.assertRaises(IntegrityError):
                _apply_edits(payload, [edit])
            self.assertEqual(canonical_json(payload), baseline)

    def test_repeated_boilerplate_inverse_restores_lexical_refs_by_position(
        self,
    ) -> None:
        document = DoclingDocument(name="many-margin-items")
        for index in range(12):
            document.add_text(DocItemLabel.TEXT, f"Margin {index}")
        payload = document.model_dump(
            mode="json", by_alias=True, exclude_none=True
        )
        references = ["#/texts/10", "#/texts/11", "#/texts/2"]
        edits = []
        for furniture_index, reference in enumerate(references):
            body_index = int(reference.rsplit("/", 1)[1])
            edits.append(
                {
                    "target": {
                        "ref": reference,
                        "field": "content_layer",
                    },
                    "before": {
                        "content_layer": "body",
                        "body_index": body_index,
                        "parent": {"$ref": "#/body"},
                    },
                    "after": {
                        "content_layer": "furniture",
                        "furniture_index": furniture_index,
                        "parent": {"$ref": "#/furniture"},
                    },
                }
            )
        changed = _apply_edits(payload, edits)
        inverse = [
            {
                "target": edit["target"],
                "before": edit["after"],
                "after": edit["before"],
            }
            for edit in edits
        ]
        restored = _apply_edits(changed, inverse)
        self.assertEqual(canonical_json(restored), canonical_json(payload))

    def test_all_refiners_replay_forward_and_inverse_edits(self) -> None:
        cases = (
            ("D009", docling_with_refinements, SOURCE),
            ("D010", docling_with_refinements, SOURCE),
            ("D007", docling_with_repeated_margins, PDF_SOURCE),
        )
        with tempfile.TemporaryDirectory() as directory:
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
                    self.assertEqual(result.artifact_integrity.status, "VERIFIED")
                    self.assertEqual(result.derivation_state.status, "MATCH")
                    self.assertEqual(result.reversibility_state.status, "MATCH")
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
                        broken_result.artifact_integrity.status, "BROKEN"
                    )
                    self.assertEqual(
                        broken_result.derivation_state.status, "MATCH"
                    )
                    self.assertEqual(
                        broken_result.reversibility_state.status,
                        "MISMATCH",
                    )
                    code, stdout, stderr = self.invoke(
                        "verify-refinement", str(broken)
                    )
                    self.assertEqual(code, 5)
                    self.assertEqual(stderr, "")
                    self.assertEqual(
                        json.loads(stdout)["artifact_integrity"]["status"],
                        "BROKEN",
                    )
                    code, stdout, stderr = self.invoke(
                        "verify-refinement",
                        str(broken),
                        "--diagnosis",
                        str(diagnosis),
                        "--base",
                        str(observation),
                    )
                    self.assertEqual(code, 5)
                    self.assertEqual(stderr, "")
                    self.assertEqual(
                        json.loads(stdout)["reversibility_state"]["status"],
                        "MISMATCH",
                    )

    def test_hash_consistent_forged_edits_fail_canonical_refiner_replay(
        self,
    ) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            observation, diagnosis, revision = self.approve_rule(
                root / "base", "D009"
            )
            forged = self.copy_record(revision, root / "forged")
            proposal = json.loads(
                (forged / "proposal.json").read_text("utf-8")
            )
            forward = deepcopy(proposal["forward_edits"])
            forward[0]["after"] += " Forged deterministic-looking output."
            inverse = [
                {
                    "target": deepcopy(edit["target"]),
                    "before": deepcopy(edit["after"]),
                    "after": deepcopy(edit["before"]),
                }
                for edit in forward
            ]
            base_payload = json.loads(
                (observation / "docling/document.json").read_text("utf-8")
            )
            prepared_payload = _apply_edits(base_payload, forward)
            prepared_bytes, markdown_bytes = _prepared_bytes(prepared_payload)
            (forged / "prepared/document.json").write_bytes(prepared_bytes)
            (forged / "prepared/document.md").write_bytes(markdown_bytes)

            def replace_edits(proposal: dict) -> None:
                proposal["forward_edits"] = forward
                proposal["inverse_edits"] = inverse

            self.rewrite_proposal_identity_chain(forged, replace_edits)
            intrinsic = verify_refinement(forged)
            self.assertEqual(
                intrinsic.artifact_integrity.status, "VERIFIED"
            )
            self.assertEqual(
                intrinsic.derivation_state.status, "NOT_CHECKED"
            )
            checked = verify_refinement(forged, diagnosis, observation)
            self.assertEqual(
                checked.artifact_integrity.status, "VERIFIED"
            )
            self.assertEqual(
                checked.diagnosis_state.status, "MATCH"
            )
            self.assertEqual(checked.base_state.status, "MATCH")
            self.assertEqual(
                checked.derivation_state.status, "MISMATCH"
            )
            self.assertEqual(
                checked.reversibility_state.status, "MISMATCH"
            )

            code, stdout, stderr = self.invoke(
                "verify-refinement", str(forged)
            )
            self.assertEqual(code, 0)
            self.assertEqual(stderr, "")
            self.assertEqual(
                json.loads(stdout)["derivation_state"]["status"],
                "NOT_CHECKED",
            )
            code, stdout, stderr = self.invoke(
                "verify-refinement",
                str(forged),
                "--diagnosis",
                str(diagnosis),
                "--base",
                str(observation),
            )
            self.assertEqual(code, 5)
            self.assertEqual(stderr, "")
            expected = {
                "refinement_directory": str(forged.resolve()),
                "artifact_integrity": {
                    "status": "VERIFIED",
                    "issues": [],
                },
                "diagnosis_state": {"status": "MATCH"},
                "base_state": {"status": "MATCH"},
                "derivation_state": {"status": "MISMATCH"},
                "reversibility_state": {"status": "MISMATCH"},
            }
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
            self.assertEqual(
                json.loads(stdout)["derivation_state"]["status"],
                "MISMATCH",
            )

            findings = json.loads(
                (diagnosis / "findings.json").read_text("utf-8")
            )
            finding_id = next(
                item["finding_id"]
                for item in findings["findings"]
                if item["rule_id"] == "D009"
            )
            rejected_draft = root / "rejected.json"
            cli._diagnosis_callable("v03", "draft_refinement")(
                diagnosis, finding_id, observation, rejected_draft
            )
            rejected = cli._diagnosis_callable(
                "v03", "resolve_refinement"
            )(
                rejected_draft,
                diagnosis,
                observation,
                root / "rejected-records",
                "REJECTED",
            )
            forged_rejected = self.copy_record(
                rejected, root / "forged-rejected"
            )
            proposal_path = forged_rejected / "proposal.json"
            manifest_path = forged_rejected / "refinement-manifest.json"
            proposal = json.loads(proposal_path.read_text("utf-8"))
            manifest = json.loads(manifest_path.read_text("utf-8"))
            proposal["forward_edits"] = forward
            proposal["inverse_edits"] = inverse
            proposal["draft_id"] = hashlib.sha256(
                canonical_json(
                    {
                        key: value
                        for key, value in proposal.items()
                        if key != "draft_id"
                    }
                ).rstrip(b"\n")
            ).hexdigest()
            manifest["draft_id"] = proposal["draft_id"]
            proposal_path.write_bytes(canonical_json(proposal))
            (forged_rejected / "report.md").write_bytes(
                _render_refinement(manifest, proposal)
            )
            self.refresh_descriptors(
                forged_rejected, manifest, "proposal.json", "report.md"
            )
            self.assertEqual(
                verify_refinement(
                    forged_rejected
                ).artifact_integrity.status,
                "VERIFIED",
            )
            checked_rejected = verify_refinement(
                forged_rejected, diagnosis, observation
            )
            self.assertEqual(
                checked_rejected.artifact_integrity.status, "BROKEN"
            )
            self.assertEqual(
                checked_rejected.derivation_state.status,
                "NOT_APPLICABLE",
            )
            code, stdout, stderr = self.invoke(
                "verify-refinement",
                str(forged_rejected),
                "--diagnosis",
                str(diagnosis),
                "--base",
                str(observation),
            )
            self.assertEqual(code, 5)
            self.assertEqual(stderr, "")
            self.assertEqual(
                json.loads(stdout)["artifact_integrity"]["status"], "BROKEN"
            )

    def test_hash_consistent_semantic_tampering_is_rejected(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            observation, diagnosis, revision = self.approve_rule(
                root / "base", "D009"
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
                        history["transformations"][-1]["draft_id"] = "f" * 64
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
                        result.artifact_integrity.status, "BROKEN"
                    )

    def test_hash_consistent_base_and_refiner_relationship_tampering_exits_five(
        self,
    ) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            _, _, revision = self.approve_rule(root / "base", "D009")

            def assert_broken(record: Path) -> None:
                result = verify_refinement(record)
                self.assertEqual(
                    result.artifact_integrity.status, "BROKEN"
                )
                code, stdout, stderr = self.invoke(
                    "verify-refinement", str(record)
                )
                self.assertEqual(code, 5)
                self.assertEqual(stderr, "")
                self.assertEqual(
                    json.loads(stdout)["artifact_integrity"]["status"],
                    "BROKEN",
                )

            mismatched_base = self.copy_record(
                revision, root / "base-identity-type"
            )
            manifest_path = mismatched_base / "refinement-manifest.json"
            manifest = json.loads(manifest_path.read_text("utf-8"))
            manifest["base"]["identity_type"] = "revision_id"
            manifest_path.write_bytes(canonical_json(manifest))
            assert_broken(mismatched_base)

            for label, replacement in (
                (
                    "refiner-descriptor",
                    {
                        "refiner_id": "R001",
                        "name": "DETERMINISTIC_DEHYPHENATION",
                        "version": "1",
                    },
                ),
                (
                    "proposal-refiner",
                    {
                        "refiner_id": "R003",
                        "name": "DETERMINISTIC_DEHYPHENATION",
                        "version": "1",
                    },
                ),
            ):
                with self.subTest(label=label):
                    copied = self.copy_record(revision, root / label)
                    manifest = json.loads(
                        (copied / "refinement-manifest.json").read_text("utf-8")
                    )
                    proposal = json.loads(
                        (copied / "proposal.json").read_text("utf-8")
                    )
                    transformation = json.loads(
                        (copied / "transformation.json").read_text("utf-8")
                    )
                    history = json.loads(
                        (copied / "history.json").read_text("utf-8")
                    )

                    proposal["refiner"] = replacement
                    proposal_identity = {
                        key: value
                        for key, value in proposal.items()
                        if key != "draft_id"
                    }
                    draft_id = hashlib.sha256(
                        canonical_json(proposal_identity).rstrip(b"\n")
                    ).hexdigest()
                    proposal["draft_id"] = draft_id
                    manifest["draft_id"] = draft_id
                    prepared_sha256 = hashlib.sha256(
                        (copied / "prepared/document.json").read_bytes()
                    ).hexdigest()
                    revision_id = hashlib.sha256(
                        canonical_json(
                            {
                                "parent": manifest["base"]["identity_value"],
                                "base_sha256": manifest["base"][
                                    "canonical_document_sha256"
                                ],
                                "draft_id": draft_id,
                                "prepared_sha256": prepared_sha256,
                            }
                        ).rstrip(b"\n")
                    ).hexdigest()
                    transformation["refiner"] = replacement
                    transformation["draft_id"] = draft_id
                    transformation["revision_id"] = revision_id
                    transformation["transformation_id"] = hashlib.sha256(
                        canonical_json(
                            {
                                "revision_id": revision_id,
                                "draft_id": draft_id,
                                "refiner": replacement,
                            }
                        ).rstrip(b"\n")
                    ).hexdigest()
                    manifest["revision_id"] = revision_id
                    history["revision_id"] = revision_id
                    history["transformations"][-1] = transformation
                    for name, value in (
                        ("proposal.json", proposal),
                        ("transformation.json", transformation),
                        ("history.json", history),
                    ):
                        (copied / name).write_bytes(canonical_json(value))
                    self.refresh_descriptors(
                        copied,
                        manifest,
                        "proposal.json",
                        "transformation.json",
                        "history.json",
                    )
                    assert_broken(copied)

    def test_hash_consistent_finding_and_edit_contract_tampering_exits_five(
        self,
    ) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            _, _, text_revision = self.approve_rule(
                root / "text-base", "D009"
            )
            _, _, membership_revision = self.approve_rule(
                root / "membership-base",
                "D007",
                converter=docling_with_repeated_margins,
                source=PDF_SOURCE,
            )

            def assert_broken(record: Path) -> None:
                result = verify_refinement(record)
                self.assertEqual(
                    result.artifact_integrity.status, "BROKEN"
                )
                code, stdout, stderr = self.invoke(
                    "verify-refinement", str(record)
                )
                self.assertEqual(code, 5)
                self.assertEqual(stderr, "")
                self.assertEqual(
                    json.loads(stdout)["artifact_integrity"]["status"],
                    "BROKEN",
                )

            def finding_id(proposal: dict) -> str:
                finding = proposal["finding"]
                return hashlib.sha256(
                    canonical_json(
                        {
                            "diagnosis_id": proposal["diagnosis_id"],
                            "rule_id": finding["rule_id"],
                            "rule_version": finding["rule_version"],
                            "document_refs": finding["document_refs"],
                            "evidence": finding["evidence"],
                        }
                    ).rstrip(b"\n")
                ).hexdigest()

            finding_mutations = {
                "finding-metadata": lambda proposal: proposal["finding"].update(
                    {"severity": "ERROR"}
                ),
                "finding-identity": lambda proposal: proposal["finding"].update(
                    {"finding_id": "f" * 64}
                ),
            }

            def invalidate_evidence(proposal: dict) -> None:
                proposal["finding"]["evidence"]["occurrence_count"] += 1
                proposal["finding"]["finding_id"] = finding_id(proposal)

            finding_mutations["finding-evidence"] = invalidate_evidence
            for label, mutate in finding_mutations.items():
                with self.subTest(label=label):
                    copied = self.copy_record(text_revision, root / label)
                    self.rewrite_proposal_identity_chain(copied, mutate)
                    assert_broken(copied)

            def add_content_coordinates(proposal: dict) -> None:
                for collection in ("forward_edits", "inverse_edits"):
                    for edit in proposal[collection]:
                        edit["target"].update({"row": 0, "column": 0})

            def contradict_membership(proposal: dict) -> None:
                invalid = {
                    "content_layer": "body",
                    "furniture_index": 0,
                    "parent": {"$ref": "#/body"},
                }
                proposal["forward_edits"][0]["after"] = invalid
                proposal["inverse_edits"][0]["before"] = invalid

            membership_mutations = {
                "content-layer-coordinates": add_content_coordinates,
                "contradictory-membership": contradict_membership,
            }
            for label, mutate in membership_mutations.items():
                with self.subTest(label=label):
                    copied = self.copy_record(
                        membership_revision, root / label
                    )
                    self.rewrite_proposal_identity_chain(copied, mutate)
                    assert_broken(copied)

            def make_table_target_without_coordinates(proposal: dict) -> None:
                for collection in ("forward_edits", "inverse_edits"):
                    for edit in proposal[collection]:
                        edit["target"] = {
                            "ref": "#/tables/0",
                            "field": "text",
                        }

            copied = self.copy_record(
                text_revision, root / "noncanonical-text-target"
            )
            self.rewrite_proposal_identity_chain(
                copied, make_table_target_without_coordinates
            )
            assert_broken(copied)

    def test_rejected_status_requires_exact_inventory_and_null_revision(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            observation = self.observation(root / "observations")
            diagnosis = cli._diagnosis_callable("v03", "diagnose")(
                observation, root / "diagnoses"
            )
            findings = json.loads((diagnosis / "findings.json").read_text("utf-8"))
            finding = next(
                item for item in findings["findings"] if item["rule_id"] == "D009"
            )
            draft = root / "rejected.json"
            cli._diagnosis_callable("v03", "draft_refinement")(
                diagnosis, finding["finding_id"], observation, draft
            )
            rejected = cli._diagnosis_callable("v03", "resolve_refinement")(
                draft, diagnosis, observation, root / "rejected", "REJECTED"
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
                        verify_refinement(copied).artifact_integrity.status,
                        "BROKEN",
                    )

    def test_refinement_nested_publication_symlinks_are_rejected(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            observation = self.observation(root / "observations")
            diagnosis = cli._diagnosis_callable("v03", "diagnose")(
                observation, root / "diagnoses"
            )
            findings = json.loads((diagnosis / "findings.json").read_text("utf-8"))
            finding = next(
                item for item in findings["findings"] if item["rule_id"] == "D009"
            )
            draft = root / "approved.json"
            cli._diagnosis_callable("v03", "draft_refinement")(
                diagnosis, finding["finding_id"], observation, draft
            )
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
                            draft, diagnosis, observation, output, "APPROVED"
                        )
                    self.assertFalse(
                        any(outside.rglob("refinement-manifest.json"))
                    )

    def test_complete_refinement_base_descriptor_is_verified(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            observation, diagnosis, revision = self.approve_rule(
                root / "base", "D009"
            )
            for operation in (
                "manifest-hash",
                "run-id",
                "source",
                "origin-run",
            ):
                with self.subTest(operation=operation):
                    copied = self.copy_record(revision, root / operation)
                    manifest_path = copied / "refinement-manifest.json"
                    manifest = json.loads(manifest_path.read_text("utf-8"))
                    if operation == "manifest-hash":
                        manifest["base"]["base_manifest_sha256"] = "f" * 64
                    elif operation == "run-id":
                        manifest["base"]["run_id"] += "-changed"
                    elif operation == "source":
                        manifest["source"]["key"] += "-changed"
                    else:
                        manifest["origin_observation_run_id"] += "-changed"
                    manifest_path.write_bytes(canonical_json(manifest))
                    result = verify_refinement(
                        copied, diagnosis, observation
                    )
                    self.assertEqual(
                        result.artifact_integrity.status, "VERIFIED"
                    )
                    self.assertEqual(
                        result.base_state.status, "CHANGED"
                    )
                    code, stdout, stderr = self.invoke(
                        "verify-refinement",
                        str(copied),
                        "--diagnosis",
                        str(diagnosis),
                        "--base",
                        str(observation),
                    )
                    self.assertEqual(code, 5)
                    self.assertEqual(stderr, "")
                    self.assertEqual(
                        json.loads(stdout)["base_state"]["status"], "CHANGED"
                    )

    def test_refinement_records_use_current_headers_only_at_the_root(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            observation, diagnosis, revision = self.approve_rule(
                root / "base", "D009"
            )
            manifest = json.loads(
                (revision / "refinement-manifest.json").read_text("utf-8")
            )
            self.assertEqual(
                (manifest["record_type"], manifest["format_version"]),
                ("refinement", 1),
            )
            for name in ("proposal.json", "transformation.json", "history.json"):
                value = json.loads((revision / name).read_text("utf-8"))
                self.assertNotIn("record_type", value)
                self.assertNotIn("format_version", value)
                self.assertNotIn("schema_version", value)
            result = verify_refinement(revision, diagnosis, observation)
            self.assertNotIn("schema_version", result.to_json_object())

    def test_replay_requires_exact_diagnosis_and_base(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            observation, diagnosis, revision = self.approve_rule(
                root / "base", "D009"
            )
            missing_diagnosis = verify_refinement(
                revision, root / "missing-diagnosis", observation
            )
            self.assertEqual(
                missing_diagnosis.diagnosis_state.status, "MISSING"
            )
            self.assertEqual(
                missing_diagnosis.base_state.status, "MATCH"
            )
            self.assertEqual(
                missing_diagnosis.derivation_state.status,
                "NOT_CHECKED",
            )
            self.assertEqual(
                missing_diagnosis.reversibility_state.status,
                "NOT_CHECKED",
            )
            code, stdout, stderr = self.invoke(
                "verify-refinement",
                str(revision),
                "--diagnosis",
                str(root / "missing-diagnosis"),
                "--base",
                str(observation),
            )
            self.assertEqual(code, 5)
            self.assertEqual(stderr, "")
            expected = {
                "refinement_directory": str(revision.resolve()),
                "artifact_integrity": {
                    "status": "VERIFIED",
                    "issues": [],
                },
                "diagnosis_state": {"status": "MISSING"},
                "base_state": {"status": "MATCH"},
                "derivation_state": {"status": "NOT_CHECKED"},
                "reversibility_state": {"status": "NOT_CHECKED"},
            }
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
            self.assertEqual(
                json.loads(stdout)["diagnosis_state"]["status"], "MISSING"
            )

            missing_base = verify_refinement(
                revision, diagnosis, root / "missing-base"
            )
            self.assertEqual(
                missing_base.diagnosis_state.status, "MATCH"
            )
            self.assertEqual(missing_base.base_state.status, "MISSING")
            self.assertEqual(
                missing_base.derivation_state.status, "NOT_CHECKED"
            )
            self.assertEqual(
                missing_base.reversibility_state.status, "NOT_CHECKED"
            )
            code, stdout, stderr = self.invoke(
                "verify-refinement",
                str(revision),
                "--diagnosis",
                str(diagnosis),
                "--base",
                str(root / "missing-base"),
            )
            self.assertEqual(code, 5)
            self.assertEqual(stderr, "")
            self.assertEqual(
                json.loads(stdout)["base_state"]["status"], "MISSING"
            )

            changed = self.copy_record(
                diagnosis, root / "changed-diagnosis"
            )
            findings_path = changed / "findings.json"
            manifest_path = changed / "diagnosis-manifest.json"
            findings = json.loads(findings_path.read_text("utf-8"))
            manifest = json.loads(manifest_path.read_text("utf-8"))
            finding = next(
                item
                for item in findings["findings"]
                if item["rule_id"] == "D009"
            )
            finding["evidence"]["original_text_sha256"] = "f" * 64
            findings["diagnosis_id"] = _diagnosis_identity(
                findings["subject"],
                findings["ruleset"],
                findings["findings"],
            )
            for item in findings["findings"]:
                item["finding_id"] = hashlib.sha256(
                    canonical_json(
                        {
                            "diagnosis_id": findings["diagnosis_id"],
                            "rule_id": item["rule_id"],
                            "rule_version": item["rule_version"],
                            "document_refs": item["document_refs"],
                            "evidence": item["evidence"],
                        }
                    ).rstrip(b"\n")
                ).hexdigest()
            findings["findings"].sort(key=lambda item: item["finding_id"])
            manifest["diagnosis_id"] = findings["diagnosis_id"]
            findings_path.write_bytes(canonical_json(findings))
            (changed / "report.md").write_bytes(_diagnosis_report(findings))
            for descriptor in manifest["artifacts"]:
                artifact = changed / descriptor["path"]
                descriptor["size"] = artifact.stat().st_size
                descriptor["sha256"] = hashlib.sha256(
                    artifact.read_bytes()
                ).hexdigest()
            manifest_path.write_bytes(canonical_json(manifest))
            changed_result = verify_refinement(
                revision, changed, observation
            )
            self.assertEqual(
                changed_result.diagnosis_state.status, "CHANGED"
            )
            self.assertEqual(changed_result.base_state.status, "MATCH")
            self.assertEqual(
                changed_result.derivation_state.status, "NOT_CHECKED"
            )
            self.assertEqual(
                changed_result.reversibility_state.status,
                "NOT_CHECKED",
            )
            code, stdout, stderr = self.invoke(
                "verify-refinement",
                str(revision),
                "--diagnosis",
                str(changed),
                "--base",
                str(observation),
            )
            self.assertEqual(code, 5)
            self.assertEqual(stderr, "")
            self.assertEqual(
                json.loads(stdout)["diagnosis_state"]["status"], "CHANGED"
            )

    def test_chained_parent_reference_is_exact_and_bound_to_base(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            observation, diagnosis, first = self.approve_rule(
                root / "base", "D009"
            )
            second_diagnosis = cli._diagnosis_callable("v03", "diagnose")(
                first, root / "second-diagnosis"
            )
            second = self.approve_existing(
                root / "second",
                second_diagnosis,
                first,
                "D010",
            )
            baseline = verify_refinement(second, second_diagnosis, first)
            self.assertEqual(baseline.artifact_integrity.status, "VERIFIED")
            self.assertEqual(baseline.base_state.status, "MATCH")

            mutations = {
                "revision_id": "f" * 64,
                "run_id": "changed-run",
                "refinement_manifest_sha256": "e" * 64,
                "prepared_document_sha256": "d" * 64,
            }
            for field, replacement in mutations.items():
                with self.subTest(field=field):
                    copied = self.copy_record(second, root / f"parent-{field}")
                    manifest_path = copied / "refinement-manifest.json"
                    manifest = json.loads(manifest_path.read_text("utf-8"))
                    manifest["parent"][field] = replacement
                    manifest_path.write_bytes(canonical_json(manifest))
                    result = verify_refinement(
                        copied, second_diagnosis, first
                    )
                    self.assertEqual(
                        result.artifact_integrity.status, "BROKEN"
                    )
                    self.assertNotEqual(
                        result.base_state.status, "MATCH"
                    )
                    self.assertEqual(
                        result.derivation_state.status, "NOT_CHECKED"
                    )

            copied = self.copy_record(second, root / "parent-all")
            manifest_path = copied / "refinement-manifest.json"
            manifest = json.loads(manifest_path.read_text("utf-8"))
            manifest["parent"].update(mutations)
            manifest_path.write_bytes(canonical_json(manifest))
            result = verify_refinement(copied, second_diagnosis, first)
            self.assertEqual(result.artifact_integrity.status, "BROKEN")
            self.assertNotEqual(result.base_state.status, "MATCH")

    def test_supplied_relationship_format_failures_use_exact_cli_streams(
        self,
    ) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            observation, diagnosis, revision = self.approve_rule(
                root / "base", "D009"
            )

            cases = []
            unsupported_diagnosis = self.copy_record(
                diagnosis, root / "unsupported-diagnosis"
            )
            diagnosis_manifest = unsupported_diagnosis / "diagnosis-manifest.json"
            value = json.loads(diagnosis_manifest.read_text("utf-8"))
            value["format_version"] = 99
            diagnosis_manifest.write_bytes(canonical_json(value))
            cases.append(
                (
                    "diagnosis-unknown-format",
                    unsupported_diagnosis,
                    observation,
                    5,
                    "supplied diagnosis integrity is not verified\n",
                )
            )

            malformed_diagnosis = self.copy_record(
                diagnosis, root / "malformed-diagnosis"
            )
            diagnosis_manifest = malformed_diagnosis / "diagnosis-manifest.json"
            value = json.loads(diagnosis_manifest.read_text("utf-8"))
            del value["record_type"]
            diagnosis_manifest.write_bytes(canonical_json(value))
            cases.append(
                (
                    "diagnosis-missing-header",
                    malformed_diagnosis,
                    observation,
                    5,
                    "supplied diagnosis integrity is not verified\n",
                )
            )

            unsupported_base = self.copy_record(
                observation, root / "unsupported-base"
            )
            base_manifest = unsupported_base / "manifest.json"
            value = json.loads(base_manifest.read_text("utf-8"))
            value["format_version"] = 99
            base_manifest.write_bytes(canonical_json(value))
            cases.append(
                (
                    "base-unknown-format",
                    diagnosis,
                    unsupported_base,
                    2,
                    "observation record format is unsupported; "
                    "regenerate the record with the current project\n",
                )
            )

            malformed_base = self.copy_record(
                observation, root / "malformed-base"
            )
            base_manifest = malformed_base / "manifest.json"
            value = json.loads(base_manifest.read_text("utf-8"))
            del value["record_type"]
            base_manifest.write_bytes(canonical_json(value))
            cases.append(
                (
                    "base-missing-header",
                    diagnosis,
                    malformed_base,
                    2,
                    "observation record format is unsupported; "
                    "regenerate the record with the current project\n",
                )
            )

            second_diagnosis = cli._diagnosis_callable("v03", "diagnose")(
                revision, root / "second-diagnosis"
            )
            second = self.approve_existing(
                root / "second",
                second_diagnosis,
                revision,
                "D010",
            )
            unsupported_parent = self.copy_record(
                revision, root / "unsupported-parent"
            )
            parent_manifest = unsupported_parent / "refinement-manifest.json"
            value = json.loads(parent_manifest.read_text("utf-8"))
            value["format_version"] = 99
            parent_manifest.write_bytes(canonical_json(value))
            parent_cases = [
                (
                    "parent-unknown-format",
                    unsupported_parent,
                    2,
                    "refinement record format is unsupported; "
                    "regenerate the record with the current project\n",
                )
            ]
            malformed_parent = self.copy_record(
                revision, root / "malformed-parent"
            )
            parent_manifest = malformed_parent / "refinement-manifest.json"
            value = json.loads(parent_manifest.read_text("utf-8"))
            del value["record_type"]
            parent_manifest.write_bytes(canonical_json(value))
            parent_cases.append(
                (
                    "parent-missing-header",
                    malformed_parent,
                    2,
                    "refinement record format is unsupported; "
                    "regenerate the record with the current project\n",
                )
            )

            for name, supplied_diagnosis, supplied_base, code, message in cases:
                with self.subTest(case=name):
                    actual, stdout, stderr = self.invoke(
                        "verify-refinement",
                        str(revision),
                        "--diagnosis",
                        str(supplied_diagnosis),
                        "--base",
                        str(supplied_base),
                    )
                    self.assertEqual(actual, code)
                    self.assertEqual(stdout, "")
                    self.assertEqual(stderr, message)
            for name, supplied_parent, code, message in parent_cases:
                with self.subTest(case=name):
                    actual, stdout, stderr = self.invoke(
                        "verify-refinement",
                        str(second),
                        "--diagnosis",
                        str(second_diagnosis),
                        "--base",
                        str(supplied_parent),
                    )
                    self.assertEqual(actual, code)
                    self.assertEqual(stdout, "")
                    self.assertEqual(stderr, message)

    def test_refinement_destination_collision_and_concurrency_are_atomic(
        self,
    ) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            observation = self.observation(root / "observations")
            diagnosis = cli._diagnosis_callable("v03", "diagnose")(
                observation, root / "diagnoses"
            )
            findings = json.loads((diagnosis / "findings.json").read_text("utf-8"))
            finding = next(
                item for item in findings["findings"] if item["rule_id"] == "D009"
            )
            draft = root / "approved.json"
            cli._diagnosis_callable("v03", "draft_refinement")(
                diagnosis, finding["finding_id"], observation, draft
            )
            fixed_datetime = mock.Mock()
            fixed_datetime.now.return_value = datetime(
                2026, 7, 24, 12, 0, tzinfo=UTC
            )
            fixed_uuid = mock.Mock(hex="a" * 32)

            output = root / "collision"
            with mock.patch(
                "tiny_corpus_workbench.v03.datetime", fixed_datetime
            ), mock.patch(
                "tiny_corpus_workbench.v03.uuid.uuid4",
                return_value=fixed_uuid,
            ):
                winner = cli._diagnosis_callable(
                    "v03", "resolve_refinement"
                )(draft, diagnosis, observation, output, "APPROVED")
                before = {
                    path.relative_to(winner).as_posix(): path.read_bytes()
                    for path in winner.rglob("*")
                    if path.is_file()
                }
                code, stdout, _ = self.invoke(
                    "resolve-refinement",
                    str(draft),
                    "--diagnosis",
                    str(diagnosis),
                    "--base",
                    str(observation),
                    "--output-root",
                    str(output),
                    "--approve",
                )
            self.assertEqual(code, 5)
            self.assertEqual(stdout, "")
            self.assertEqual(
                before,
                {
                    path.relative_to(winner).as_posix(): path.read_bytes()
                    for path in winner.rglob("*")
                    if path.is_file()
                },
            )

            concurrent_output = root / "concurrent"

            def resolve_once() -> tuple[int, Path | None]:
                try:
                    published = cli._diagnosis_callable(
                        "v03", "resolve_refinement"
                    )(
                        draft,
                        diagnosis,
                        observation,
                        concurrent_output,
                        "APPROVED",
                    )
                    return 0, published
                except IntegrityError:
                    return 5, None

            with mock.patch(
                "tiny_corpus_workbench.v03.datetime", fixed_datetime
            ), mock.patch(
                "tiny_corpus_workbench.v03.uuid.uuid4",
                return_value=fixed_uuid,
            ):
                with ThreadPoolExecutor(max_workers=2) as executor:
                    outcomes = list(
                        executor.map(lambda _: resolve_once(), range(2))
                    )
            self.assertEqual(sorted(code for code, _ in outcomes), [0, 5])
            self.assertEqual(
                len(
                    [
                        published
                        for code, published in outcomes
                        if code == 0 and isinstance(published, Path)
                    ]
                ),
                1,
            )
            self.assertFalse(
                any(
                    path.name.startswith(".staging-")
                    for path in concurrent_output.rglob("*")
                )
            )

    def test_approve_verify_rediagnose_chain_and_reject(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            observation = self.observation(root / "observations")
            diagnosis = cli._diagnosis_callable("v03", "diagnose")(
                observation, root / "diagnoses"
            )
            self.assertEqual(
                verify_diagnosis(diagnosis, observation).derivation_state.status,
                "MATCH",
            )
            findings = json.loads((diagnosis / "findings.json").read_text("utf-8"))
            whitespace = next(
                item for item in findings["findings"] if item["rule_id"] == "D009"
            )
            draft = root / "whitespace-proposal.json"
            cli._diagnosis_callable("v03", "draft_refinement")(
                diagnosis, whitespace["finding_id"], observation, draft
            )
            revision = cli._diagnosis_callable("v03", "resolve_refinement")(
                draft, diagnosis, observation, root / "revisions", "APPROVED"
            )
            proposal_record = json.loads(
                (revision / "proposal.json").read_text("utf-8")
            )
            refinement_manifest = json.loads(
                (revision / "refinement-manifest.json").read_text("utf-8")
            )
            self.assertNotIn("schema_version", proposal_record)
            self.assertEqual(refinement_manifest["record_type"], "refinement")
            self.assertEqual(refinement_manifest["format_version"], 1)
            self.assertNotIn("schema_version", refinement_manifest)
            self.assertNotIn("runtime", refinement_manifest)
            self.assertNotIn("milestone", refinement_manifest)
            result = verify_refinement(revision, diagnosis, observation)
            self.assertEqual(result.artifact_integrity.status, "VERIFIED")
            self.assertEqual(result.derivation_state.status, "MATCH")
            self.assertEqual(result.reversibility_state.status, "MATCH")
            code, _, stderr = self.invoke(
                "verify-refinement",
                str(revision),
                "--diagnosis",
                str(diagnosis),
                "--base",
                str(observation),
            )
            self.assertEqual(code, 0)
            self.assertEqual(stderr, "")
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
                item for item in findings2["findings"] if item["rule_id"] == "D010"
            )
            rejected_draft = root / "rejected-proposal.json"
            cli._diagnosis_callable("v03", "draft_refinement")(
                diagnosis2, dehyphenation["finding_id"], revision, rejected_draft
            )
            record = cli._diagnosis_callable("v03", "resolve_refinement")(
                rejected_draft, diagnosis2, revision, root / "rejected", "REJECTED"
            )
            manifest = json.loads(
                (record / "refinement-manifest.json").read_text("utf-8")
            )
            self.assertEqual(manifest["decision"], "REJECTED")
            self.assertIsNone(manifest["revision_id"])
            self.assertFalse((record / "prepared").exists())
            self.assertEqual(
                verify_refinement(record).reversibility_state.status,
                "NOT_APPLICABLE",
            )
            code, stdout, stderr = self.invoke(
                "verify-refinement",
                str(record),
                "--diagnosis",
                str(diagnosis2),
                "--base",
                str(revision),
            )
            self.assertEqual(code, 0)
            self.assertEqual(stderr, "")
            self.assertEqual(
                json.loads(stdout)["reversibility_state"]["status"],
                "NOT_APPLICABLE",
            )

            draft2 = root / "dehyphenation-proposal.json"
            cli._diagnosis_callable("v03", "draft_refinement")(
                diagnosis2, dehyphenation["finding_id"], revision, draft2
            )
            revision2 = cli._diagnosis_callable("v03", "resolve_refinement")(
                draft2, diagnosis2, revision, root / "revisions", "APPROVED"
            )
            history = json.loads((revision2 / "history.json").read_text("utf-8"))
            self.assertEqual(len(history["transformations"]), 2)
            code, stdout, stderr = self.invoke(
                "verify-refinement",
                str(revision2),
                "--diagnosis",
                str(diagnosis2),
                "--base",
                str(revision),
            )
            self.assertEqual(code, 0)
            self.assertEqual(stderr, "")
            self.assertEqual(
                json.loads(stdout)["derivation_state"]["status"], "MATCH"
            )

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
                verify_refinement(broken_chain).artifact_integrity.status,
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
            changed_history["transformations"][0]["affected_refs"].append(
                "#/texts/999"
            )
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
                changed_result.artifact_integrity.status, "VERIFIED"
            )
            self.assertEqual(changed_result.base_state.status, "CHANGED")

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
            with self.assertRaisesRegex(
                IntegrityError,
                "supplied diagnosis integrity is not verified",
            ):
                verify_refinement(revision2, changed_diagnosis, revision)

    def test_proposal_stdout_and_required_resolution_flags_are_exact(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            source_sha256 = (
                "7d2fe694613a437af02d379f8b8ea627bc2f93425046182465bc4651f6913785"
            )
            base_sha256 = (
                "6ae5cbdcd09b2a34c616a850957c8e5a4806a92574940475eec7af62aa6c2e2d"
            )
            findings_sha256 = (
                "4cbbfebc681e222bae7f425e0df72239cf53a6123162090b95e346c5f97d93ef"
            )
            proposal_sha256 = (
                "a871fb4b42b79db2236b5fe83b40f9b2f88167c9589da61f62686113e8d71615"
            )
            origin_id = (
                "a3a83013f87635a1137c4409e69495da63f2ad0a725011292455bc99deecee62"
            )
            diagnosis_id = (
                "e4cd828c7905d941f9eb9be88bf747c62ec2e45212a9bd5c5662e43d8e23668f"
            )
            finding_id = (
                "f108ebb9d0097c0664f0a976d3cf9c928991296c2676ece2922fe6da7889789e"
            )
            draft_id = (
                "288a97fa6df3de54641f5fe905dfce9dabd4c9fade7db825dd7cbe70944acd6c"
            )
            approved_revision_id = (
                "2f99aecccbad245f96d885d432ef39450b8f92981b59cc0d8f7b1ba23eac2b4f"
            )
            self.assertEqual(
                hashlib.sha256(SOURCE.read_bytes()).hexdigest(),
                source_sha256,
            )
            observation = self.observation(root / "observations")
            self.assertEqual(
                hashlib.sha256(
                    (observation / "docling/document.json").read_bytes()
                ).hexdigest(),
                base_sha256,
            )
            diagnosis = cli._diagnosis_callable("v03", "diagnose")(
                observation, root / "diagnoses"
            )
            self.assertEqual(
                hashlib.sha256((diagnosis / "findings.json").read_bytes()).hexdigest(),
                findings_sha256,
            )
            proposal = root / "proposal.json"
            code, stdout, stderr = self.invoke(
                "draft-refinement",
                str(diagnosis),
                "--finding",
                finding_id,
                "--base",
                str(observation),
                "--output",
                str(proposal),
            )
            self.assertEqual((code, stderr), (0, ""))
            self.assertEqual(
                hashlib.sha256(proposal.read_bytes()).hexdigest(),
                proposal_sha256,
            )
            produced_proposal = json.loads(proposal.read_text("utf-8"))
            self.assertEqual(produced_proposal["diagnosis_id"], diagnosis_id)
            self.assertEqual(produced_proposal["base"]["subject_id"], origin_id)
            self.assertEqual(
                produced_proposal["base"]["canonical_document_sha256"],
                base_sha256,
            )
            self.assertEqual(produced_proposal["finding"]["finding_id"], finding_id)
            self.assertEqual(produced_proposal["draft_id"], draft_id)
            self.assertEqual(
                stdout.encode(),
                (
                    f'{{"draft_id":"{draft_id}","proposal":"'
                    f'{proposal.resolve()}"}}\n'
                ).encode(),
            )
            for flags in ((), ("--approve", "--reject")):
                with self.subTest(flags=flags):
                    stdout, stderr = io.StringIO(), io.StringIO()
                    with (
                        redirect_stdout(stdout),
                        redirect_stderr(stderr),
                        self.assertRaises(SystemExit) as raised,
                    ):
                        cli.main(
                            [
                                "resolve-refinement",
                                str(proposal),
                                "--diagnosis",
                                str(diagnosis),
                                "--base",
                                str(observation),
                                "--output-root",
                                str(root / "invalid"),
                                *flags,
                            ]
                        )
                    self.assertEqual(raised.exception.code, 2)
                    self.assertEqual(stdout.getvalue(), "")
                    self.assertFalse((root / "invalid").exists())
            for omitted in ("diagnosis", "base"):
                with self.subTest(omitted=omitted):
                    arguments = ["resolve-refinement", str(proposal), "--approve"]
                    if omitted != "diagnosis":
                        arguments.extend(["--diagnosis", str(diagnosis)])
                    if omitted != "base":
                        arguments.extend(["--base", str(observation)])
                    with self.assertRaises(SystemExit) as raised:
                        with redirect_stderr(io.StringIO()):
                            cli.main(arguments)
                    self.assertEqual(raised.exception.code, 2)

            for decision, flag, second, uuid_hex, run_id, created_at in (
                (
                    "APPROVED",
                    "--approve",
                    1,
                    "1" * 32,
                    "20260729T101101.000000Z-111111111111",
                    "2026-07-29T10:11:01Z",
                ),
                (
                    "REJECTED",
                    "--reject",
                    2,
                    "2" * 32,
                    "20260729T101102.000000Z-222222222222",
                    "2026-07-29T10:11:02Z",
                ),
            ):
                current = proposal
                if decision == "REJECTED":
                    current = root / "rejected-proposal.json"
                    current.write_bytes(proposal.read_bytes())
                fixed_now = datetime(2026, 7, 29, 10, 11, second, tzinfo=UTC)
                fixed_datetime = mock.Mock()
                fixed_datetime.now.return_value = fixed_now
                fixed_uuid = mock.Mock(hex=uuid_hex)
                output_root = root / decision.lower()
                expected_record = (
                    output_root
                    / "policy-memo-md"
                    / origin_id
                    / run_id
                ).resolve()
                with mock.patch(
                    "tiny_corpus_workbench.v03.datetime", fixed_datetime
                ), mock.patch(
                    "tiny_corpus_workbench.v03.uuid.uuid4",
                    return_value=fixed_uuid,
                ):
                    code, stdout, stderr = self.invoke(
                        "resolve-refinement",
                        str(current),
                        "--diagnosis",
                        str(diagnosis),
                        "--base",
                        str(observation),
                        flag,
                        "--output-root",
                        str(output_root),
                    )
                self.assertEqual((code, stderr), (0, ""))
                expected_manifest = expected_record / "refinement-manifest.json"
                if decision == "APPROVED":
                    expected_stdout = (
                        f'{{"decision":"APPROVED","manifest":"{expected_manifest}",'
                        f'"revision_id":"{approved_revision_id}","run_id":"{run_id}"}}\n'
                    ).encode()
                    expected_report = (
                        "# Controlled Refinement\n\n"
                        "- Decision: `APPROVED`\n"
                        "- Draft ID: "
                        "`288a97fa6df3de54641f5fe905dfce9dabd4c9fade7db825dd7cbe70944acd6c`\n"
                        "- Finding: "
                        "`f108ebb9d0097c0664f0a976d3cf9c928991296c2676ece2922fe6da7889789e`\n"
                        "- Refiner: `R001`\n"
                        "- Revision ID: "
                        "`2f99aecccbad245f96d885d432ef39450b8f92981b59cc0d8f7b1ba23eac2b4f`\n\n"
                        "The source, observation, diagnosis, base, and earlier "
                        "revisions remain unchanged.\n"
                    ).encode()
                else:
                    expected_stdout = (
                        f'{{"decision":"REJECTED","manifest":"{expected_manifest}",'
                        f'"revision_id":null,"run_id":"{run_id}"}}\n'
                    ).encode()
                    expected_report = (
                        "# Controlled Refinement\n\n"
                        "- Decision: `REJECTED`\n"
                        "- Draft ID: "
                        "`288a97fa6df3de54641f5fe905dfce9dabd4c9fade7db825dd7cbe70944acd6c`\n"
                        "- Finding: "
                        "`f108ebb9d0097c0664f0a976d3cf9c928991296c2676ece2922fe6da7889789e`\n"
                        "- Refiner: `R001`\n\n"
                        "The source, observation, diagnosis, base, and earlier "
                        "revisions remain unchanged.\n"
                    ).encode()
                self.assertEqual(stdout.encode(), expected_stdout)
                self.assertEqual(
                    (expected_record / "report.md").read_bytes(),
                    expected_report,
                )
                produced_manifest = json.loads(expected_manifest.read_text("utf-8"))
                self.assertEqual(produced_manifest["run_id"], run_id)
                self.assertEqual(produced_manifest["created_at"], created_at)
                self.assertEqual(
                    produced_manifest["revision_id"],
                    approved_revision_id if decision == "APPROVED" else None,
                )
                changed_report = expected_report + b"tampered\n"
                (expected_record / "report.md").write_bytes(changed_report)
                descriptor = next(
                    item
                    for item in produced_manifest["artifacts"]
                    if item["path"] == "report.md"
                )
                descriptor["size"] = len(changed_report)
                descriptor["sha256"] = hashlib.sha256(changed_report).hexdigest()
                expected_manifest.write_bytes(canonical_json(produced_manifest))
                checked = verify_refinement(expected_record)
                self.assertEqual(
                    checked.artifact_integrity.status,
                    "INTEGRITY_MISMATCH",
                )
                self.assertIn(
                    "REPORT_INVALID",
                    {issue.code for issue in checked.artifact_integrity.issues},
                )
                self.assertNotIn(
                    "HASH_MISMATCH",
                    {issue.code for issue in checked.artifact_integrity.issues},
                )

    def test_noncanonical_proposal_bytes_publish_nothing_and_preserve_inputs(
        self,
    ) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            observation = self.observation(root / "observations")
            diagnosis = cli._diagnosis_callable("v03", "diagnose")(
                observation, root / "diagnoses"
            )
            findings = json.loads((diagnosis / "findings.json").read_text("utf-8"))
            finding_id = next(
                item["finding_id"]
                for item in findings["findings"]
                if item["rule_id"] == "D009"
            )
            canonical = root / "canonical.json"
            cli._diagnosis_callable("v03", "draft_refinement")(
                diagnosis, finding_id, observation, canonical
            )
            value = json.loads(canonical.read_text("utf-8"))
            semantic_edit = deepcopy(value)
            semantic_edit["forward_edits"][0]["after"] += " changed"
            extra_field = deepcopy(value)
            extra_field["unexpected"] = True
            missing_field = deepcopy(value)
            del missing_field["inverse_edits"]
            variants = {
                "semantic-edit": canonical_json(semantic_edit),
                "extra-field": canonical_json(extra_field),
                "missing-field": canonical_json(missing_field),
                "reordered": (
                    json.dumps(
                        dict(reversed(list(value.items()))),
                        ensure_ascii=False,
                        separators=(",", ":"),
                    )
                    + "\n"
                ).encode(),
                "indented": (json.dumps(value, ensure_ascii=False, indent=2) + "\n").encode(),
                "bom": b"\xef\xbb\xbf" + canonical.read_bytes(),
                "missing-newline": canonical.read_bytes().rstrip(b"\n"),
                "extra-newline": canonical.read_bytes() + b"\n",
                "utf16": json.dumps(value, ensure_ascii=False).encode("utf-16"),
            }
            diagnosis_before = snapshot_tree(diagnosis)
            observation_before = snapshot_tree(observation)
            for label, raw in variants.items():
                with self.subTest(label=label):
                    proposal = root / f"{label}.json"
                    proposal.write_bytes(raw)
                    proposal_before = proposal.read_bytes()
                    with self.assertRaises((InputError, IntegrityError)):
                        cli._diagnosis_callable("v03", "resolve_refinement")(
                            proposal,
                            diagnosis,
                            observation,
                            root / f"{label}-output",
                            "APPROVED",
                        )
                    self.assertEqual(proposal.read_bytes(), proposal_before)
                    self.assertEqual(snapshot_tree(diagnosis), diagnosis_before)
                    self.assertEqual(snapshot_tree(observation), observation_before)
                    self.assertFalse(
                        any((root / f"{label}-output").rglob("refinement-manifest.json"))
                        if (root / f"{label}-output").exists()
                        else False
                    )

    def test_stale_diagnosis_or_base_recomputation_publishes_nothing(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            observation = self.observation(root / "observations")
            diagnosis = cli._diagnosis_callable("v03", "diagnose")(
                observation, root / "diagnoses"
            )
            findings = json.loads((diagnosis / "findings.json").read_text("utf-8"))
            finding_id = next(
                item["finding_id"]
                for item in findings["findings"]
                if item["rule_id"] == "D009"
            )
            proposal = root / "proposal.json"
            cli._diagnosis_callable("v03", "draft_refinement")(
                diagnosis, finding_id, observation, proposal
            )
            proposal_before = proposal.read_bytes()
            diagnosis_before = snapshot_tree(diagnosis)
            observation_before = snapshot_tree(observation)
            make_proposal = v03_module._proposal

            for label, mutate in (
                (
                    "diagnosis",
                    lambda expected: expected.__setitem__("diagnosis_id", "0" * 64),
                ),
                (
                    "base",
                    lambda expected: expected["base"].__setitem__(
                        "canonical_document_sha256", "0" * 64
                    ),
                ),
            ):
                with self.subTest(label=label):
                    def stale_recomputation(
                        diagnosis_root: Path,
                        selected_finding_id: str,
                        base_root: Path,
                    ):
                        expected, base = make_proposal(
                            diagnosis_root, selected_finding_id, base_root
                        )
                        mutate(expected)
                        return expected, base

                    output = root / f"{label}-output"
                    with mock.patch(
                        "tiny_corpus_workbench.v03._proposal",
                        side_effect=stale_recomputation,
                    ):
                        with self.assertRaisesRegex(
                            IntegrityError,
                            "proposal was modified, non-canonical, or stale",
                        ):
                            v03_module.resolve_refinement(
                                proposal,
                                diagnosis,
                                observation,
                                output,
                                "APPROVED",
                            )
                    self.assertEqual(proposal.read_bytes(), proposal_before)
                    self.assertEqual(snapshot_tree(diagnosis), diagnosis_before)
                    self.assertEqual(snapshot_tree(observation), observation_before)
                    self.assertFalse(
                        any(output.rglob("refinement-manifest.json"))
                        if output.exists()
                        else False
                    )

    def test_proposal_removal_during_resolution_publishes_nothing(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            observation = self.observation(root / "observations")
            diagnosis = cli._diagnosis_callable("v03", "diagnose")(
                observation, root / "diagnoses"
            )
            findings = json.loads((diagnosis / "findings.json").read_text("utf-8"))
            finding_id = next(
                item["finding_id"]
                for item in findings["findings"]
                if item["rule_id"] == "D009"
            )
            proposal = root / "proposal.json"
            cli._diagnosis_callable("v03", "draft_refinement")(
                diagnosis, finding_id, observation, proposal
            )
            diagnosis_before = snapshot_tree(diagnosis)
            observation_before = snapshot_tree(observation)
            capture = v03_module._capture_proposal
            calls = 0

            def remove_before_final(path: Path):
                nonlocal calls
                calls += 1
                if calls == 2:
                    path.unlink()
                return capture(path)

            output = root / "output"
            with mock.patch(
                "tiny_corpus_workbench.v03._capture_proposal",
                side_effect=remove_before_final,
            ):
                with self.assertRaises((InputError, IntegrityError)):
                    v03_module.resolve_refinement(
                        proposal,
                        diagnosis,
                        observation,
                        output,
                        "APPROVED",
                    )
            self.assertEqual(calls, 2)
            self.assertFalse(proposal.exists())
            self.assertEqual(snapshot_tree(diagnosis), diagnosis_before)
            self.assertEqual(snapshot_tree(observation), observation_before)
            self.assertFalse(
                any(output.rglob("refinement-manifest.json"))
                if output.exists()
                else False
            )

    def test_proposal_mutation_during_resolution_publishes_nothing(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            observation = self.observation(root / "observations")
            diagnosis = cli._diagnosis_callable("v03", "diagnose")(
                observation, root / "diagnoses"
            )
            findings = json.loads((diagnosis / "findings.json").read_text("utf-8"))
            finding_id = next(
                item["finding_id"]
                for item in findings["findings"]
                if item["rule_id"] == "D009"
            )
            proposal = root / "proposal.json"
            cli._diagnosis_callable("v03", "draft_refinement")(
                diagnosis, finding_id, observation, proposal
            )
            changed = json.loads(proposal.read_text("utf-8"))
            changed["forward_edits"][0]["after"] += " changed concurrently"
            changed_bytes = canonical_json(changed)
            diagnosis_before = snapshot_tree(diagnosis)
            observation_before = snapshot_tree(observation)
            capture = v03_module._capture_proposal
            calls = 0

            def mutate_before_final(path: Path):
                nonlocal calls
                calls += 1
                if calls == 2:
                    path.write_bytes(changed_bytes)
                return capture(path)

            output = root / "output"
            with mock.patch(
                "tiny_corpus_workbench.v03._capture_proposal",
                side_effect=mutate_before_final,
            ):
                with self.assertRaisesRegex(
                    IntegrityError, "input changed during resolution"
                ):
                    v03_module.resolve_refinement(
                        proposal,
                        diagnosis,
                        observation,
                        output,
                        "APPROVED",
                    )
            self.assertEqual(calls, 2)
            self.assertEqual(proposal.read_bytes(), changed_bytes)
            self.assertEqual(snapshot_tree(diagnosis), diagnosis_before)
            self.assertEqual(snapshot_tree(observation), observation_before)
            self.assertFalse(
                any(output.rglob("refinement-manifest.json"))
                if output.exists()
                else False
            )

    def test_proposal_replacement_is_detected_before_publication(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            observation = self.observation(root / "observations")
            diagnosis = cli._diagnosis_callable("v03", "diagnose")(
                observation, root / "diagnoses"
            )
            findings = json.loads((diagnosis / "findings.json").read_text("utf-8"))
            finding_id = next(
                item["finding_id"]
                for item in findings["findings"]
                if item["rule_id"] == "D009"
            )
            proposal = root / "proposal.json"
            cli._diagnosis_callable("v03", "draft_refinement")(
                diagnosis, finding_id, observation, proposal
            )
            raw = proposal.read_bytes()
            capture = v03_module._capture_proposal
            calls = 0

            def replace_before_final(path: Path):
                nonlocal calls
                calls += 1
                if calls == 2:
                    replacement = root / "replacement.json"
                    replacement.write_bytes(raw)
                    replacement.replace(proposal)
                return capture(path)

            output = root / "output"
            with mock.patch(
                "tiny_corpus_workbench.v03._capture_proposal",
                side_effect=replace_before_final,
            ):
                with self.assertRaisesRegex(
                    IntegrityError, "input changed during resolution"
                ):
                    v03_module.resolve_refinement(
                        proposal,
                        diagnosis,
                        observation,
                        output,
                        "APPROVED",
                    )
            self.assertEqual(proposal.read_bytes(), raw)
            self.assertFalse(
                any(output.rglob("refinement-manifest.json"))
                if output.exists()
                else False
            )

    def test_post_final_check_mutation_cannot_change_staged_proposal(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            observation = self.observation(root / "observations")
            diagnosis = cli._diagnosis_callable("v03", "diagnose")(
                observation, root / "diagnoses"
            )
            findings = json.loads((diagnosis / "findings.json").read_text("utf-8"))
            finding_id = next(
                item["finding_id"]
                for item in findings["findings"]
                if item["rule_id"] == "D009"
            )
            proposal = root / "proposal.json"
            cli._diagnosis_callable("v03", "draft_refinement")(
                diagnosis, finding_id, observation, proposal
            )
            captured = proposal.read_bytes()
            publish = v03_module._publish_directory

            def mutate_after_check(staging: Path, destination: Path) -> Path:
                proposal.write_bytes(b"changed after final check\n")
                return publish(staging, destination)

            with mock.patch(
                "tiny_corpus_workbench.v03._publish_directory",
                side_effect=mutate_after_check,
            ):
                record = v03_module.resolve_refinement(
                    proposal,
                    diagnosis,
                    observation,
                    root / "output",
                    "APPROVED",
                )
            self.assertEqual((record / "proposal.json").read_bytes(), captured)

    def test_staged_refinement_mutation_publishes_nothing(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            observation = self.observation(root / "observations")
            diagnosis = cli._diagnosis_callable("v03", "diagnose")(
                observation, root / "diagnoses"
            )
            findings = json.loads((diagnosis / "findings.json").read_text("utf-8"))
            finding_id = next(
                item["finding_id"]
                for item in findings["findings"]
                if item["rule_id"] == "D009"
            )
            proposal = root / "proposal.json"
            cli._diagnosis_callable("v03", "draft_refinement")(
                diagnosis, finding_id, observation, proposal
            )
            proposal_before = proposal.read_bytes()
            diagnosis_before = snapshot_tree(diagnosis)
            observation_before = snapshot_tree(observation)
            verify_staged = v03_module._verify_staged_refinement
            calls = 0

            def mutate_then_verify(
                staging: Path,
                manifest: dict,
                proposal_value: dict,
                proposal_bytes: bytes,
                transformation: dict | None,
                history: dict | None,
            ) -> None:
                nonlocal calls
                calls += 1
                if calls == 2:
                    (staging / "proposal.json").write_bytes(b"changed staging\n")
                verify_staged(
                    staging,
                    manifest,
                    proposal_value,
                    proposal_bytes,
                    transformation,
                    history,
                )

            output = root / "output"
            with mock.patch(
                "tiny_corpus_workbench.v03._verify_staged_refinement",
                side_effect=mutate_then_verify,
            ):
                with self.assertRaisesRegex(
                    IntegrityError, "staged refinement inventory changed"
                ):
                    v03_module.resolve_refinement(
                        proposal,
                        diagnosis,
                        observation,
                        output,
                        "APPROVED",
                    )
            self.assertEqual(calls, 2)
            self.assertEqual(proposal.read_bytes(), proposal_before)
            self.assertEqual(snapshot_tree(diagnosis), diagnosis_before)
            self.assertEqual(snapshot_tree(observation), observation_before)
            self.assertFalse(
                any(output.rglob("refinement-manifest.json"))
                if output.exists()
                else False
            )

    def test_hash_consistent_staged_semantic_mutation_publishes_nothing(
        self,
    ) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            observation = self.observation(root / "observations")
            diagnosis = cli._diagnosis_callable("v03", "diagnose")(
                observation, root / "diagnoses"
            )
            findings = json.loads((diagnosis / "findings.json").read_text("utf-8"))
            finding_id = next(
                item["finding_id"]
                for item in findings["findings"]
                if item["rule_id"] == "D009"
            )
            proposal = root / "proposal.json"
            cli._diagnosis_callable("v03", "draft_refinement")(
                diagnosis, finding_id, observation, proposal
            )
            proposal_before = proposal.read_bytes()
            diagnosis_before = snapshot_tree(diagnosis)
            observation_before = snapshot_tree(observation)
            verify_staged = v03_module._verify_staged_refinement
            calls = 0

            def mutate_descriptors_then_verify(
                staging: Path,
                manifest: dict,
                proposal_value: dict,
                proposal_bytes: bytes,
                transformation: dict | None,
                history: dict | None,
            ) -> None:
                nonlocal calls
                calls += 1
                checked_transformation = transformation
                checked_history = history
                if calls == 2:
                    assert transformation is not None
                    assert history is not None
                    changed_transformation = deepcopy(transformation)
                    changed_transformation["affected_refs"].append("#/texts/999")
                    changed_history = deepcopy(history)
                    changed_history["transformations"][-1] = changed_transformation
                    checked_transformation = changed_transformation
                    checked_history = changed_history
                    for relative, value in (
                        ("transformation.json", changed_transformation),
                        ("history.json", changed_history),
                    ):
                        raw = canonical_json(value)
                        (staging / relative).write_bytes(raw)
                        descriptor = next(
                            item
                            for item in manifest["artifacts"]
                            if item["path"] == relative
                        )
                        descriptor["size"] = len(raw)
                        descriptor["sha256"] = hashlib.sha256(raw).hexdigest()
                    (staging / "refinement-manifest.json").write_bytes(
                        canonical_json(manifest)
                    )
                verify_staged(
                    staging,
                    manifest,
                    proposal_value,
                    proposal_bytes,
                    checked_transformation,
                    checked_history,
                )

            output = root / "output"
            with mock.patch(
                "tiny_corpus_workbench.v03._verify_staged_refinement",
                side_effect=mutate_descriptors_then_verify,
            ):
                with self.assertRaisesRegex(
                    IntegrityError, "transformation references differ"
                ):
                    v03_module.resolve_refinement(
                        proposal,
                        diagnosis,
                        observation,
                        output,
                        "APPROVED",
                    )
            self.assertEqual(calls, 2)
            self.assertEqual(proposal.read_bytes(), proposal_before)
            self.assertEqual(snapshot_tree(diagnosis), diagnosis_before)
            self.assertEqual(snapshot_tree(observation), observation_before)
            self.assertFalse(
                any(output.rglob("refinement-manifest.json"))
                if output.exists()
                else False
            )


if __name__ == "__main__":
    unittest.main()
