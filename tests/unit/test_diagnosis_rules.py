from __future__ import annotations

import unittest

from docling_core.types.doc import DoclingDocument, DocItemLabel

from tiny_corpus_workbench.diagnosis import analyze_document


DIAGNOSIS_ID = "a" * 64


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
            [item["rule_id"] for item in first],
            sorted(item["rule_id"] for item in first),
        )


if __name__ == "__main__":
    unittest.main()
