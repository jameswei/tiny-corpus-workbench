from __future__ import annotations

import json
import tempfile
import unittest
from copy import deepcopy
from pathlib import Path
from unittest import mock

from jsonschema import Draft202012Validator, ValidationError

from tiny_corpus_workbench.application.observation import observe
from tiny_corpus_workbench.schema_catalog import validator


SCHEMAS = Path("src/tiny_corpus_workbench/schemas")


def fake_docling(source: Path, destination: Path, model_root: Path):
    destination.mkdir(parents=True)
    (destination / "document.json").write_text(
        '{"schema_name":"DoclingDocument","version":"1.10.0"}\n', "utf-8"
    )
    (destination / "document.md").write_text("# view\n", "utf-8")
    return "success", {"name": "DoclingDocument", "version": "1.10.0"}


def fake_markitdown(source: Path, destination: Path):
    destination.mkdir(parents=True)
    (destination / "document.md").write_text("# view\n", "utf-8")


def observation_documents() -> tuple[dict, dict]:
    with tempfile.TemporaryDirectory() as directory, mock.patch(
        "tiny_corpus_workbench.extractors.docling.convert", wraps=fake_docling
    ), mock.patch(
        "tiny_corpus_workbench.extractors.markitdown.convert",
        wraps=fake_markitdown,
    ):
        code, published = observe(
            "fixtures/golden/policy-memo.md", Path(directory), Path("unused")
        )
        if int(code) != 0:
            raise AssertionError(f"observation failed with exit {code}")
        return (
            json.loads((published / "manifest.json").read_text("utf-8")),
            json.loads((published / "comparison.json").read_text("utf-8")),
        )


class SchemaTests(unittest.TestCase):
    def test_all_schemas_are_valid_draft_2020_12(self) -> None:
        for path in SCHEMAS.glob("*.schema.json"):
            with self.subTest(path=path):
                Draft202012Validator.check_schema(
                    json.loads(path.read_text("utf-8"))
                )

    def test_observation_schemas_use_small_symbolic_catalog_keys(self) -> None:
        manifest, comparison = observation_documents()
        validator("observation-manifest").validate(manifest)
        validator("comparison").validate(comparison)
        self.assertEqual(
            (manifest["record_type"], manifest["format_version"]),
            ("observation", 1),
        )
        self.assertNotIn("schema_version", manifest)
        self.assertNotIn("schema_version", comparison)
        self.assertNotIn("build_provenance", manifest)
        self.assertNotIn("path", manifest["models"])

    def test_observation_schemas_are_closed_and_require_domain_evidence(
        self,
    ) -> None:
        manifest, comparison = observation_documents()
        cases = (
            ("observation-manifest", manifest, (), "record_type"),
            ("observation-manifest", manifest, (), "format_version"),
            ("observation-manifest", manifest, ("source",), "sha256"),
            (
                "observation-manifest",
                manifest,
                ("configurations", "docling"),
                "accelerator",
            ),
            (
                "observation-manifest",
                manifest,
                ("docling_document_schema",),
                "version",
            ),
            ("observation-manifest", manifest, ("models",), "files"),
            (
                "observation-manifest",
                manifest,
                ("extractors", 0),
                "version",
            ),
            ("comparison", comparison, (), "observation_id"),
            ("comparison", comparison, ("views",), "docling"),
        )
        for schema_key, document, path, required in cases:
            with self.subTest(schema=schema_key, path=path):
                missing = deepcopy(document)
                target = missing
                for part in path:
                    target = target[part]
                del target[required]
                with self.assertRaises(ValidationError):
                    validator(schema_key).validate(missing)

                unknown = deepcopy(document)
                target = unknown
                for part in path:
                    target = target[part]
                target["unexpected"] = True
                with self.assertRaises(ValidationError):
                    validator(schema_key).validate(unknown)

    def test_observation_manifest_requires_ordered_extractors(self) -> None:
        manifest, _ = observation_documents()
        schema = validator("observation-manifest")
        schema.validate(manifest)
        reversed_manifest = deepcopy(manifest)
        reversed_manifest["extractors"].reverse()
        with self.assertRaises(ValidationError):
            schema.validate(reversed_manifest)

    def test_table_coordinates_are_an_all_or_nothing_pair(self) -> None:
        draft_schema = json.loads(
            (SCHEMAS / "refinement-draft.schema.json").read_text("utf-8")
        )
        target_validator = Draft202012Validator(draft_schema["$defs"]["target"])
        target_validator.validate(
            {"ref": "#/tables/0", "field": "text", "row": 0, "column": 0}
        )
        for incomplete in (
            {"ref": "#/tables/0", "field": "text", "row": 0},
            {"ref": "#/tables/0", "field": "text", "column": 0},
        ):
            with self.assertRaises(ValidationError):
                target_validator.validate(incomplete)

    def test_refinement_relationship_definitions_are_coupled(self) -> None:
        draft = json.loads(
            (SCHEMAS / "refinement-draft.schema.json").read_text("utf-8")
        )
        manifest = json.loads(
            (SCHEMAS / "refinement-manifest.schema.json").read_text("utf-8")
        )

        refiner_validator = Draft202012Validator(draft["$defs"]["refiner"])
        refiners = (
            ("TCW-R001", "WHITESPACE_NORMALIZATION"),
            ("TCW-R002", "REPEATED_BOILERPLATE_REMOVAL"),
            ("TCW-R003", "DETERMINISTIC_DEHYPHENATION"),
        )
        for refiner_id, name in refiners:
            refiner_validator.validate(
                {"refiner_id": refiner_id, "name": name, "version": "1"}
            )
        with self.assertRaises(ValidationError):
            refiner_validator.validate(
                {
                    "refiner_id": "TCW-R001",
                    "name": "DETERMINISTIC_DEHYPHENATION",
                    "version": "1",
                }
            )

        decision_validator = Draft202012Validator(
            draft["properties"]["decision"]
        )
        decision_validator.validate(
            {"state": "PENDING", "decided_by": None, "note": None}
        )
        decision_validator.validate(
            {"state": "APPROVED", "decided_by": "owner", "note": None}
        )
        for invalid in (
            {"state": "PENDING", "decided_by": "owner", "note": None},
            {"state": "REJECTED", "decided_by": None, "note": None},
        ):
            with self.assertRaises(ValidationError):
                decision_validator.validate(invalid)

        edit_validator = Draft202012Validator(
            {"$ref": "#/$defs/edit", "$defs": draft["$defs"]}
        )
        text_edit = {
            "target": {"ref": "#/texts/0", "field": "text"},
            "before": "before",
            "after": "after",
        }
        edit_validator.validate(text_edit)
        invalid_text = deepcopy(text_edit)
        invalid_text["after"] = {
            "content_layer": "body",
            "body_index": 0,
            "parent": {"$ref": "#/body"},
        }
        with self.assertRaises(ValidationError):
            edit_validator.validate(invalid_text)

        membership_edit = {
            "target": {"ref": "#/texts/0", "field": "content_layer"},
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
        edit_validator.validate(membership_edit)
        invalid_membership = deepcopy(membership_edit)
        invalid_membership["after"] = "furniture"
        with self.assertRaises(ValidationError):
            edit_validator.validate(invalid_membership)

        base_validator = Draft202012Validator(
            {"$ref": "#/$defs/base", "$defs": manifest["$defs"]}
        )
        observation_base = {
            "kind": "OBSERVATION",
            "identity_type": "observation_id",
            "identity_value": "a" * 64,
            "run_id": "run",
            "base_manifest_sha256": "b" * 64,
            "canonical_document_sha256": "c" * 64,
        }
        base_validator.validate(observation_base)
        mismatched_base = deepcopy(observation_base)
        mismatched_base["identity_type"] = "revision_id"
        with self.assertRaises(ValidationError):
            base_validator.validate(mismatched_base)


if __name__ == "__main__":
    unittest.main()
