from __future__ import annotations

import unittest
from copy import deepcopy
from pathlib import Path

from docling_core.types.doc import (
    BoundingBox,
    DoclingDocument,
    DocItemLabel,
    ProvenanceItem,
    Size,
    TableCell,
    TableData,
)
from jsonschema import Draft202012Validator

from tiny_corpus_workbench.diagnosis_rules import (
    CURRENT_FINDING_METADATA,
    RULESET as BASE_RULESET,
    analyze_document,
    validate_finding_contract,
)
from tiny_corpus_workbench.domain import IntegrityError
from tiny_corpus_workbench.schema_catalog import load_schema


DIAGNOSIS_ID = "a" * 64


def contract_finding(
    rule_id: str,
    document_refs: list[str],
    evidence: dict,
) -> dict:
    return {
        "finding_id": "0" * 64,
        "rule_id": rule_id,
        **CURRENT_FINDING_METADATA[rule_id],
        "document_refs": document_refs,
        "evidence": evidence,
    }


def document(
    texts: list[dict] | None = None,
    tables: list[dict] | None = None,
    pictures: list[dict] | None = None,
    *,
    body_refs: list[str] | None = None,
    furniture_refs: list[str] | None = None,
    pages: dict | None = None,
) -> dict:
    texts = texts or []
    tables = tables or []
    pictures = pictures or []
    return {
        "schema_name": "DoclingDocument",
        "version": "1.10.0",
        "name": "diagnosis-test",
        "body": {
            "self_ref": "#/body",
            "children": [
                {"$ref": reference}
                for reference in (
                    body_refs
                    if body_refs is not None
                    else [
                        item["self_ref"]
                        for item in [*texts, *tables, *pictures]
                        if item.get("content_layer", "body") == "body"
                    ]
                )
            ],
            "content_layer": "body",
        },
        "furniture": {
            "self_ref": "#/furniture",
            "children": [
                {"$ref": reference} for reference in furniture_refs or []
            ],
            "content_layer": "furniture",
        },
        "groups": [],
        "texts": texts,
        "tables": tables,
        "pictures": pictures,
        "key_value_items": [],
        "form_items": [],
        "field_regions": [],
        "field_items": [],
        "pages": pages or {},
    }


def text(
    index: int,
    value: str,
    *,
    label: str = "text",
    level: int | None = None,
    layer: str = "body",
    prov: list[dict] | None = None,
) -> dict:
    item = {
        "self_ref": f"#/texts/{index}",
        "children": [],
        "content_layer": layer,
        "label": label,
        "text": value,
        "prov": [] if prov is None else prov,
    }
    if level is not None:
        item["level"] = level
    return item


def rules(payload: dict, media_type: str = "text/markdown") -> list[str]:
    return [
        item["rule_id"]
        for item in analyze_document(
            payload, media_type=media_type, diagnosis_id=DIAGNOSIS_ID
        )
    ]


class DiagnosisRuleTests(unittest.TestCase):
    def test_compact_schema_defers_all_rule_contracts_to_domain_validation(
        self,
    ) -> None:
        schema_path = Path(
            "src/tiny_corpus_workbench/schemas/"
            "finding-set-v0.5.schema.json"
        )
        schema = load_schema("finding-set")
        finding_schema = {
            "$schema": schema["$schema"],
            "$defs": schema["$defs"],
            "$ref": "#/$defs/finding",
        }
        structural = Draft202012Validator(finding_schema)
        self.assertLess(len(schema_path.read_text("utf-8").splitlines()), 300)
        self.assertNotIn("oneOf", schema["$defs"]["finding"])

        valid = [
            contract_finding(
                "TCW-D001",
                ["#/body"],
                {"non_whitespace_characters": 0},
            ),
            contract_finding(
                "TCW-D002",
                ["#/body"],
                {"non_whitespace_characters": 42},
            ),
            contract_finding(
                "TCW-D003",
                ["#/texts/0"],
                {"code_point_offsets": [1], "occurrence_count": 1},
            ),
            contract_finding(
                "TCW-D003",
                ["#/tables/0"],
                {
                    "code_point_offsets": [1],
                    "occurrence_count": 1,
                    "row": 0,
                    "column": 1,
                },
            ),
            contract_finding(
                "TCW-D004",
                ["#/texts/0", "#/texts/1"],
                {
                    "count": 2,
                    "normalized_character_count": 80,
                    "normalized_text_sha256": "a" * 64,
                },
            ),
            contract_finding(
                "TCW-D005",
                ["#/texts/0"],
                {"current_level": 2, "previous_level": 0},
            ),
            contract_finding(
                "TCW-D005",
                ["#/texts/1"],
                {
                    "current_level": 4,
                    "previous_level": 2,
                    "previous_ref": "#/texts/0",
                },
            ),
            contract_finding(
                "TCW-D006",
                ["#/texts/0"],
                {"relationship_kind": "orphan_caption"},
            ),
            contract_finding(
                "TCW-D006",
                ["#/tables/0", "#/texts/1"],
                {
                    "relationship_kind": "invalid_declared_caption",
                    "declared_ref": "#/texts/1",
                },
            ),
            contract_finding(
                "TCW-D007",
                ["#/texts/0", "#/texts/1", "#/texts/2"],
                {
                    "band": "top",
                    "normalized_character_count": 8,
                    "normalized_text_sha256": "b" * 64,
                    "page_count": 3,
                    "page_numbers": [1, 2, 3],
                },
            ),
            contract_finding(
                "TCW-D008",
                ["#/pictures/0"],
                {"content_layer": "body"},
            ),
            contract_finding(
                "TCW-D009",
                ["#/texts/0"],
                {
                    "code_point_offsets": [1],
                    "occurrence_count": 1,
                    "original_text_sha256": "c" * 64,
                    "normalized_text_sha256": "d" * 64,
                },
            ),
            contract_finding(
                "TCW-D009",
                ["#/field_items/0"],
                {
                    "code_point_offsets": [1],
                    "occurrence_count": 1,
                    "original_text_sha256": "c" * 64,
                    "normalized_text_sha256": "d" * 64,
                },
            ),
            contract_finding(
                "TCW-D009",
                ["#/tables/0"],
                {
                    "code_point_offsets": [1],
                    "occurrence_count": 1,
                    "original_text_sha256": "c" * 64,
                    "normalized_text_sha256": "d" * 64,
                    "row": 0,
                    "column": 1,
                },
            ),
            contract_finding(
                "TCW-D010",
                ["#/texts/0"],
                {
                    "hyphen_code_point_offsets": [1],
                    "occurrence_count": 1,
                    "original_text_sha256": "e" * 64,
                    "repaired_text_sha256": "f" * 64,
                },
            ),
            contract_finding(
                "TCW-D010",
                ["#/field_items/0"],
                {
                    "hyphen_code_point_offsets": [1],
                    "occurrence_count": 1,
                    "original_text_sha256": "e" * 64,
                    "repaired_text_sha256": "f" * 64,
                },
            ),
            contract_finding(
                "TCW-D010",
                ["#/tables/0"],
                {
                    "hyphen_code_point_offsets": [1],
                    "occurrence_count": 1,
                    "original_text_sha256": "e" * 64,
                    "repaired_text_sha256": "f" * 64,
                    "row": 0,
                    "column": 1,
                },
            ),
        ]
        for finding in valid:
            with self.subTest(
                rule_id=finding["rule_id"],
                evidence=tuple(finding["evidence"]),
            ):
                structural.validate(finding)
                validate_finding_contract(finding)

        by_rule = {}
        for finding in valid:
            by_rule.setdefault(finding["rule_id"], finding)
        for rule_id, finding in by_rule.items():
            with self.subTest(rule_id=rule_id, defect="evidence"):
                invalid = deepcopy(finding)
                invalid["evidence"] = {"band": "top"}
                structural.validate(invalid)
                with self.assertRaises(IntegrityError):
                    validate_finding_contract(invalid)
            with self.subTest(rule_id=rule_id, defect="metadata"):
                invalid = deepcopy(finding)
                invalid["severity"] = (
                    "INFO" if invalid["severity"] != "INFO" else "WARNING"
                )
                structural.validate(invalid)
                with self.assertRaises(IntegrityError):
                    validate_finding_contract(invalid)

    def test_d006_and_refinable_target_constraints_are_domain_owned(
        self,
    ) -> None:
        schema = load_schema("finding-set")
        structural = Draft202012Validator(
            {
                "$schema": schema["$schema"],
                "$defs": schema["$defs"],
                "$ref": "#/$defs/finding",
            }
        )
        empty_declared = contract_finding(
            "TCW-D006",
            ["#/tables/0"],
            {
                "relationship_kind": "invalid_declared_caption",
                "declared_ref": "",
            },
        )
        structural.validate(empty_declared)
        with self.assertRaises(IntegrityError):
            validate_finding_contract(empty_declared)

        valid_evidence = {
            "TCW-D009": {
                "code_point_offsets": [1],
                "occurrence_count": 1,
                "original_text_sha256": "a" * 64,
                "normalized_text_sha256": "b" * 64,
            },
            "TCW-D010": {
                "hyphen_code_point_offsets": [1],
                "occurrence_count": 1,
                "original_text_sha256": "c" * 64,
                "repaired_text_sha256": "d" * 64,
            },
        }
        for rule_id, evidence in valid_evidence.items():
            for reference in ("#/texts/0", "#/field_items/0"):
                with self.subTest(
                    rule_id=rule_id,
                    reference=reference,
                    valid=True,
                ):
                    validate_finding_contract(
                        contract_finding(rule_id, [reference], evidence)
                    )
            for reference in (
                "#/body",
                "#/groups/0",
                "#/pages/1",
                "#/pictures/0",
                "#/tables/0",
                "#/field_regions/0",
            ):
                with self.subTest(
                    rule_id=rule_id,
                    reference=reference,
                    valid=False,
                ):
                    invalid = contract_finding(
                        rule_id,
                        [reference],
                        evidence,
                    )
                    structural.validate(invalid)
                    with self.assertRaises(IntegrityError):
                        validate_finding_contract(invalid)

    def test_generic_evidence_is_rejected_for_every_base_rule(self) -> None:
        for rule in BASE_RULESET:
            finding = {
                "finding_id": "0" * 64,
                "rule_id": rule["rule_id"],
                **CURRENT_FINDING_METADATA[rule["rule_id"]],
                "document_refs": ["#/body"],
                "evidence": {"band": "top"},
            }
            with self.subTest(rule_id=rule["rule_id"]):
                with self.assertRaises(IntegrityError):
                    validate_finding_contract(finding)

    def test_d005_d007_d008_reference_prefix_and_cardinality_negatives(self) -> None:
        valid = {
            "TCW-D005": {
                "rule_id": "TCW-D005",
                "document_refs": ["#/texts/1"],
                "evidence": {"current_level": 3, "previous_level": 0},
            },
            "TCW-D007": {
                "rule_id": "TCW-D007",
                "document_refs": ["#/texts/1", "#/texts/2", "#/texts/3"],
                "evidence": {
                    "band": "top",
                    "normalized_character_count": 8,
                    "normalized_text_sha256": "a" * 64,
                    "page_count": 3,
                    "page_numbers": [1, 2, 3],
                },
            },
            "TCW-D008": {
                "rule_id": "TCW-D008",
                "document_refs": ["#/pictures/0"],
                "evidence": {"content_layer": "body"},
            },
        }
        for rule_id, finding in valid.items():
            finding.update(CURRENT_FINDING_METADATA[rule_id])
            validate_finding_contract(finding)

        negatives = []
        for rule_id, references in (
            ("TCW-D005", ["#/tables/0"]),
            ("TCW-D005", ["#/texts/0", "#/texts/1"]),
            ("TCW-D007", ["#/tables/0"]),
            ("TCW-D007", []),
            ("TCW-D008", ["#/body"]),
            ("TCW-D008", ["#/texts/0", "#/pictures/0"]),
        ):
            finding = deepcopy(valid[rule_id])
            finding["document_refs"] = references
            negatives.append(finding)
        d005_previous = deepcopy(valid["TCW-D005"])
        d005_previous["evidence"] = {
            "current_level": 4,
            "previous_level": 2,
            "previous_ref": "#/tables/0",
        }
        negatives.append(d005_previous)
        d007_pages = deepcopy(valid["TCW-D007"])
        d007_pages["evidence"]["page_count"] = 2
        negatives.append(d007_pages)

        for finding in negatives:
            with self.subTest(
                rule_id=finding["rule_id"],
                references=finding["document_refs"],
            ):
                with self.assertRaises(IntegrityError):
                    validate_finding_contract(finding)

    def test_schema_valid_constructed_documents_cover_d001_d006_and_d008(self) -> None:
        empty = DoclingDocument(name="empty")
        empty_payload = empty.model_dump(mode="json", by_alias=True, exclude_none=True)
        self.assertEqual(rules(empty_payload), ["TCW-D001"])

        orphan = DoclingDocument(name="orphan")
        orphan.add_text(DocItemLabel.CAPTION, "A caption without an owner")
        orphan_payload = orphan.model_dump(
            mode="json", by_alias=True, exclude_none=True
        )
        self.assertIn("TCW-D006", rules(orphan_payload))

        missing_provenance = DoclingDocument(name="missing-provenance")
        missing_provenance.add_text(DocItemLabel.TEXT, "x" * 200)
        pdf_payload = missing_provenance.model_dump(
            mode="json", by_alias=True, exclude_none=True
        )
        self.assertEqual(rules(pdf_payload, "application/pdf"), ["TCW-D008"])

    def test_empty_suppresses_short_and_short_boundaries_are_fixed(self) -> None:
        self.assertEqual(rules(document()), ["TCW-D001"])
        one = document([text(0, "x")])
        self.assertEqual(rules(one), ["TCW-D002"])
        boundary = document([text(0, "x" * 199)])
        self.assertEqual(rules(boundary), ["TCW-D002"])
        clear = document([text(0, "x" * 200)])
        self.assertEqual(rules(clear), [])

    def test_short_document_count_uses_nfc_normalized_content(self) -> None:
        decomposed = "e\u0301"
        self.assertEqual(
            rules(document([text(0, decomposed * 199)])),
            ["TCW-D002"],
        )
        self.assertEqual(rules(document([text(0, decomposed * 200)])), [])

    def test_replacement_character_offsets_cover_text_and_table_cells(self) -> None:
        table = {
            "self_ref": "#/tables/0",
            "children": [],
            "content_layer": "body",
            "label": "table",
            "prov": [],
            "captions": [],
            "data": {
                "table_cells": [
                    {
                        "text": "a\ufffdb",
                        "start_row_offset_idx": 2,
                        "start_col_offset_idx": 3,
                    }
                ]
            },
        }
        payload = document([text(0, "x\ufffdy")], [table])
        findings = analyze_document(
            payload, media_type="text/markdown", diagnosis_id=DIAGNOSIS_ID
        )
        replacement = [
            item for item in findings if item["rule_id"] == "TCW-D003"
        ]
        self.assertEqual(len(replacement), 2)
        by_ref = {item["document_refs"][0]: item for item in replacement}
        self.assertEqual(
            by_ref["#/texts/0"]["evidence"]["code_point_offsets"], [1]
        )
        self.assertEqual(by_ref["#/tables/0"]["evidence"]["row"], 2)
        self.assertEqual(by_ref["#/tables/0"]["evidence"]["column"], 3)

    def test_duplicate_grouping_is_normalized_case_sensitive_and_body_only(self) -> None:
        repeated = "A" * 80
        payload = document(
            [
                text(0, repeated),
                text(1, f"  {repeated}  "),
                text(2, "a" * 80),
                text(3, repeated, layer="furniture"),
            ]
        )
        findings = analyze_document(
            payload, media_type="text/markdown", diagnosis_id=DIAGNOSIS_ID
        )
        duplicate = [
            item for item in findings if item["rule_id"] == "TCW-D004"
        ]
        self.assertEqual(len(duplicate), 1)
        self.assertEqual(
            duplicate[0]["document_refs"], ["#/texts/0", "#/texts/1"]
        )
        self.assertEqual(duplicate[0]["evidence"]["count"], 2)

    def test_heading_first_and_later_jumps_follow_reading_order(self) -> None:
        payload = document(
            [
                text(0, "First", label="section_header", level=2),
                text(1, "Next", label="section_header", level=3),
                text(2, "Jump", label="section_header", level=5),
                text(3, "x" * 200),
            ]
        )
        findings = analyze_document(
            payload, media_type="text/markdown", diagnosis_id=DIAGNOSIS_ID
        )
        jumps = [item for item in findings if item["rule_id"] == "TCW-D005"]
        self.assertEqual(
            [item["document_refs"] for item in jumps],
            [["#/texts/0"], ["#/texts/2"]],
        )

    def test_caption_relationships_distinguish_orphans_and_invalid_targets(self) -> None:
        caption = text(0, "Caption", label="caption")
        not_caption = text(1, "Not a caption")
        table = {
            "self_ref": "#/tables/0",
            "children": [],
            "content_layer": "body",
            "label": "table",
            "prov": [],
            "captions": [{"$ref": "#/texts/1"}, {"$ref": "#/texts/99"}],
            "data": {"table_cells": [{"text": "x" * 200}]},
        }
        findings = analyze_document(
            document([caption, not_caption], [table]),
            media_type="text/markdown",
            diagnosis_id=DIAGNOSIS_ID,
        )
        caption_findings = [
            item for item in findings if item["rule_id"] == "TCW-D006"
        ]
        self.assertEqual(len(caption_findings), 3)
        self.assertEqual(
            sorted(item["evidence"]["relationship_kind"] for item in caption_findings),
            [
                "invalid_declared_caption",
                "invalid_declared_caption",
                "orphan_caption",
            ],
        )

    def test_duplicate_invalid_caption_declarations_emit_one_finding(self) -> None:
        owner = {
            "self_ref": "#/tables/0",
            "children": [],
            "content_layer": "body",
            "label": "table",
            "prov": [],
            "captions": [{"$ref": "#/texts/99"}, {"$ref": "#/texts/99"}],
            "data": {"table_cells": [{"text": "x" * 200}]},
        }
        findings = analyze_document(
            document(tables=[owner]),
            media_type="text/markdown",
            diagnosis_id=DIAGNOSIS_ID,
        )
        invalid = [
            item
            for item in findings
            if item["rule_id"] == "TCW-D006"
            and item["evidence"]["relationship_kind"]
            == "invalid_declared_caption"
        ]
        self.assertEqual(len(invalid), 1)
        self.assertEqual(invalid[0]["evidence"]["declared_ref"], "#/texts/99")

    def test_non_caption_owner_reference_is_valid_d006_evidence(self) -> None:
        owner = {
            "self_ref": "#/tables/0",
            "children": [],
            "content_layer": "body",
            "label": "table",
            "prov": [],
            "captions": [{"$ref": "#/tables/1"}],
            "data": {"table_cells": [{"text": "owner"}]},
        }
        non_caption_target = {
            "self_ref": "#/tables/1",
            "children": [],
            "content_layer": "body",
            "label": "table",
            "prov": [],
            "captions": [],
            "data": {"table_cells": [{"text": "target"}]},
        }
        findings = analyze_document(
            document(tables=[owner, non_caption_target]),
            media_type="text/markdown",
            diagnosis_id=DIAGNOSIS_ID,
        )
        invalid = [
            item
            for item in findings
            if item["rule_id"] == "TCW-D006"
            and item["evidence"]["relationship_kind"]
            == "invalid_declared_caption"
        ]
        self.assertEqual(len(invalid), 1)
        self.assertEqual(
            invalid[0]["document_refs"],
            ["#/tables/0", "#/tables/1"],
        )
        self.assertEqual(
            invalid[0]["evidence"]["declared_ref"],
            "#/tables/1",
        )
        validate_finding_contract(invalid[0])

    def test_valid_caption_and_no_caption_are_not_d006_findings(self) -> None:
        cell = TableCell(
            start_row_offset_idx=0,
            end_row_offset_idx=1,
            start_col_offset_idx=0,
            end_col_offset_idx=1,
            text="x" * 200,
        )
        valid = DoclingDocument(name="valid-caption")
        caption = valid.add_text(DocItemLabel.CAPTION, "Valid caption")
        valid.add_table(
            TableData(table_cells=[cell], num_rows=1, num_cols=1),
            caption=caption,
        )
        valid_payload = valid.model_dump(
            mode="json", by_alias=True, exclude_none=True
        )
        self.assertNotIn("TCW-D006", rules(valid_payload))

        absent = DoclingDocument(name="no-caption")
        absent.add_text(DocItemLabel.TEXT, "x" * 200)
        absent.add_table(
            TableData(table_cells=[cell], num_rows=1, num_cols=1)
        )
        absent_payload = absent.model_dump(
            mode="json", by_alias=True, exclude_none=True
        )
        self.assertNotIn("TCW-D006", rules(absent_payload))

    def test_pdf_margin_group_uses_three_pages_and_excludes_furniture(self) -> None:
        pages = {
            str(number): {
                "page_no": number,
                "size": {"width": 612, "height": 792},
            }
            for number in range(1, 4)
        }
        repeated = []
        for index, page in enumerate(range(1, 4)):
            repeated.append(
                text(
                    index,
                    "Repeated margin text",
                    prov=[
                        {
                            "page_no": page,
                            "bbox": {
                                "l": 72,
                                "t": 40,
                                "r": 200,
                                "b": 20,
                                "coord_origin": "TOPLEFT",
                            },
                        }
                    ],
                )
            )
        furniture = text(
            3,
            "Furniture negative",
            layer="furniture",
            prov=[
                {
                    "page_no": page,
                    "bbox": {
                        "l": 72,
                        "t": 780,
                        "r": 200,
                        "b": 770,
                        "coord_origin": "TOPLEFT",
                    },
                }
                for page in range(1, 4)
            ],
        )
        payload = document(
            [*repeated, furniture],
            body_refs=[item["self_ref"] for item in repeated],
            furniture_refs=[furniture["self_ref"]],
            pages=pages,
        )
        findings = analyze_document(
            payload, media_type="application/pdf", diagnosis_id=DIAGNOSIS_ID
        )
        margin = [item for item in findings if item["rule_id"] == "TCW-D007"]
        self.assertEqual(len(margin), 1)
        self.assertEqual(margin[0]["evidence"]["page_numbers"], [1, 2, 3])
        self.assertEqual(margin[0]["evidence"]["band"], "top")

    def test_pdf_margin_length_page_band_and_origin_boundaries(self) -> None:
        def has_margin(
            value: str,
            *,
            page_count: int = 3,
            ratio: float = 0.10,
            origin: str = "TOPLEFT",
        ) -> bool:
            pages = {
                str(number): {
                    "page_no": number,
                    "size": {"width": 612, "height": 792},
                }
                for number in range(1, page_count + 1)
            }
            raw_ratio = 1 - ratio if origin == "BOTTOMLEFT" else ratio
            midpoint = raw_ratio * 792
            items = [
                text(
                    index,
                    value,
                    prov=[
                        {
                            "page_no": page,
                            "bbox": {
                                "l": 72,
                                "t": midpoint,
                                "r": 200,
                                "b": midpoint,
                                "coord_origin": origin,
                            },
                        }
                    ],
                )
                for index, page in enumerate(range(1, page_count + 1))
            ]
            payload = document(items, pages=pages)
            return "TCW-D007" in rules(payload, "application/pdf")

        cases = (
            ("xx", 3, 0.10, "TOPLEFT", False),
            ("xxx", 3, 0.10, "TOPLEFT", True),
            ("x" * 200, 3, 0.10, "TOPLEFT", True),
            ("x" * 201, 3, 0.10, "TOPLEFT", False),
            ("margin", 2, 0.10, "TOPLEFT", False),
            ("margin", 3, 0.10, "TOPLEFT", True),
            ("margin", 3, 0.1000000000004, "TOPLEFT", False),
            ("margin", 3, 0.1001, "TOPLEFT", False),
            ("margin", 3, 0.90, "TOPLEFT", True),
            ("margin", 3, 0.8999999999996, "TOPLEFT", False),
            ("margin", 3, 0.8999, "TOPLEFT", False),
            ("margin", 3, 0.10, "BOTTOMLEFT", True),
            ("margin", 3, 0.1000000000004, "BOTTOMLEFT", False),
            ("margin", 3, 0.90, "BOTTOMLEFT", True),
            ("margin", 3, 0.8999999999996, "BOTTOMLEFT", False),
        )
        for value, page_count, ratio, origin, expected in cases:
            with self.subTest(
                length=len(value),
                pages=page_count,
                ratio=ratio,
                origin=origin,
            ):
                self.assertEqual(
                    has_margin(
                        value,
                        page_count=page_count,
                        ratio=ratio,
                        origin=origin,
                    ),
                    expected,
                )

    def test_pdf_missing_provenance_covers_each_supported_item_and_non_pdf_does_not(self) -> None:
        payload = document(
            [text(0, "x" * 200)],
            [
                {
                    "self_ref": "#/tables/0",
                    "children": [],
                    "content_layer": "body",
                    "label": "table",
                    "prov": [],
                    "captions": [],
                    "data": {"table_cells": []},
                }
            ],
            [
                {
                    "self_ref": "#/pictures/0",
                    "children": [],
                    "content_layer": "body",
                    "label": "picture",
                    "prov": [],
                    "captions": [],
                }
            ],
        )
        self.assertEqual(rules(payload).count("TCW-D008"), 0)
        self.assertEqual(
            rules(payload, "application/pdf").count("TCW-D008"), 3
        )

    def test_pdf_items_with_provenance_are_not_d008_findings(self) -> None:
        provenance = ProvenanceItem(
            page_no=1,
            bbox=BoundingBox(l=72, t=100, r=200, b=120),
            charspan=(0, 1),
        )
        payload_document = DoclingDocument(name="provenance-present")
        payload_document.add_page(1, Size(width=612, height=792))
        payload_document.add_text(
            DocItemLabel.TEXT, "x" * 200, prov=provenance
        )
        payload_document.add_table(
            TableData(
                table_cells=[
                    TableCell(
                        start_row_offset_idx=0,
                        end_row_offset_idx=1,
                        start_col_offset_idx=0,
                        end_col_offset_idx=1,
                        text="cell",
                    )
                ],
                num_rows=1,
                num_cols=1,
            ),
            prov=provenance,
        )
        payload_document.add_picture(prov=provenance)
        payload = payload_document.model_dump(
            mode="json", by_alias=True, exclude_none=True
        )
        self.assertNotIn("TCW-D008", rules(payload, "application/pdf"))

    def test_finding_identity_and_order_are_stable(self) -> None:
        payload = document([text(0, "x\ufffd")])
        first = analyze_document(
            payload, media_type="text/markdown", diagnosis_id=DIAGNOSIS_ID
        )
        second = analyze_document(
            payload, media_type="text/markdown", diagnosis_id=DIAGNOSIS_ID
        )
        self.assertEqual(first, second)
        self.assertEqual(
            [item["finding_id"] for item in first],
            sorted(item["finding_id"] for item in first),
        )


if __name__ == "__main__":
    unittest.main()
