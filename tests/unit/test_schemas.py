from __future__ import annotations

import json
import tempfile
import unittest
from copy import deepcopy
from pathlib import Path
from unittest import mock

from jsonschema import Draft202012Validator, ValidationError

from tiny_corpus_workbench.cli import observe
from tiny_corpus_workbench.runtime import RUNTIME_DEPENDENCIES


SCHEMAS = Path("src/tiny_corpus_workbench/schemas")


def fake_docling(source: Path, destination: Path, model_root: Path):
    destination.mkdir(parents=True)
    (destination / "document.json").write_text(
        '{"schema_name":"DoclingDocument","version":"1.10.0"}\n',
        "utf-8",
    )
    (destination / "document.md").write_text("# view\n", "utf-8")
    return "success", {"name": "DoclingDocument", "version": "1.10.0"}


def fake_markitdown(source: Path, destination: Path):
    destination.mkdir(parents=True)
    (destination / "document.md").write_text("# view\n", "utf-8")


def real_observation_documents() -> tuple[dict, dict]:
    with tempfile.TemporaryDirectory() as directory, mock.patch(
        "tiny_corpus_workbench.extractors.docling.convert", wraps=fake_docling
    ), mock.patch(
        "tiny_corpus_workbench.extractors.markitdown.convert", wraps=fake_markitdown
    ):
        code, published = observe(
            "fixtures/golden/policy-memo.md", Path(directory), Path("unused")
        )
        if int(code) != 0:
            raise AssertionError(f"real observation fixture failed with exit {code}")
        return (
            json.loads((published / "manifest.json").read_text("utf-8")),
            json.loads((published / "comparison.json").read_text("utf-8")),
        )


def nested_object(document: dict, path: tuple[str | int, ...]) -> dict:
    value = document
    for part in path:
        value = value[part]
    return value


class SchemaTests(unittest.TestCase):
    def assert_closed_object_contract(
        self,
        validator: Draft202012Validator,
        document: dict,
        path: tuple[str | int, ...],
        required_field: str,
    ) -> None:
        missing = deepcopy(document)
        del nested_object(missing, path)[required_field]
        with self.assertRaises(ValidationError):
            validator.validate(missing)

        unknown = deepcopy(document)
        nested_object(unknown, path)["unexpected_test_field"] = True
        with self.assertRaises(ValidationError):
            validator.validate(unknown)

    def test_all_schemas_are_valid_draft_2020_12(self) -> None:
        for path in SCHEMAS.glob("*.schema.json"):
            with self.subTest(path=path):
                Draft202012Validator.check_schema(json.loads(path.read_text("utf-8")))

    def test_fixture_registry_conforms_and_unknown_field_is_rejected(self) -> None:
        schema = json.loads((SCHEMAS / "fixture-registry-v0.1.schema.json").read_text("utf-8"))
        registry = json.loads(Path("fixtures/golden/fixtures.json").read_text("utf-8"))
        Draft202012Validator(schema).validate(registry)
        registry["unknown"] = True
        with self.assertRaises(ValidationError):
            Draft202012Validator(schema).validate(registry)

    def test_fixture_registry_nested_objects_are_closed_and_required(self) -> None:
        schema = json.loads(
            (SCHEMAS / "fixture-registry-v0.1.schema.json").read_text("utf-8")
        )
        validator = Draft202012Validator(schema)
        registry = json.loads(Path("fixtures/golden/fixtures.json").read_text("utf-8"))
        validator.validate(registry)
        cases = (
            ((), "schema_version"),
            (("generator",), "name"),
            (("fixtures", 0), "id"),
            (("fixtures", 0, "authored_source"), "id"),
            (("fixtures", 0, "generator"), "name"),
            (("fixtures", 0, "anchors"), "document_id"),
        )
        for path, required in cases:
            with self.subTest(path=path, required=required):
                self.assert_closed_object_contract(validator, registry, path, required)

    def test_empty_manifest_and_comparison_are_rejected(self) -> None:
        for name in ("preparation-manifest-v0.1.schema.json", "comparison-summary-v0.1.schema.json"):
            schema = json.loads((SCHEMAS / name).read_text("utf-8"))
            with self.subTest(schema=name), self.assertRaises(ValidationError):
                Draft202012Validator(schema).validate({})

    def test_v03_table_coordinates_are_an_all_or_nothing_pair(self) -> None:
        draft_schema = json.loads(
            (SCHEMAS / "refinement-draft-v0.3.schema.json").read_text("utf-8")
        )
        target_validator = Draft202012Validator(draft_schema["$defs"]["target"])
        target_validator.validate(
            {"ref": "#/tables/0", "field": "text", "row": 0, "column": 0}
        )
        target_validator.validate({"ref": "#/texts/0", "field": "text"})
        for incomplete in (
            {"ref": "#/tables/0", "field": "text", "row": 0},
            {"ref": "#/tables/0", "field": "text", "column": 0},
        ):
            with self.subTest(target=incomplete), self.assertRaises(
                ValidationError
            ):
                target_validator.validate(incomplete)

        finding_schema = json.loads(
            (SCHEMAS / "finding-set-v0.3.schema.json").read_text("utf-8")
        )
        evidence_schema = finding_schema["$defs"]["finding"]["properties"][
            "evidence"
        ]
        evidence_validator = Draft202012Validator(evidence_schema)
        evidence_validator.validate({"row": 0, "column": 0})
        for incomplete in ({"row": 0}, {"column": 0}):
            with self.subTest(evidence=incomplete), self.assertRaises(
                ValidationError
            ):
                evidence_validator.validate(incomplete)

    def test_manifest_requires_one_ordered_result_per_extractor(self) -> None:
        schema = json.loads(
            (SCHEMAS / "preparation-manifest-v0.1.schema.json").read_text("utf-8")
        )
        validator = Draft202012Validator(schema)
        manifest, _ = real_observation_documents()

        self.assertEqual(
            [result["name"] for result in manifest["extractors"]],
            ["docling", "markitdown"],
        )
        validator.validate(manifest)

        invalid_manifests = []
        duplicate_docling = deepcopy(manifest)
        duplicate_docling["extractors"][1] = deepcopy(
            duplicate_docling["extractors"][0]
        )
        invalid_manifests.append(duplicate_docling)

        duplicate_markitdown = deepcopy(manifest)
        duplicate_markitdown["extractors"][0] = deepcopy(
            duplicate_markitdown["extractors"][1]
        )
        invalid_manifests.append(duplicate_markitdown)

        for position in (0, 1):
            missing_identity = deepcopy(manifest)
            del missing_identity["extractors"][position]["name"]
            invalid_manifests.append(missing_identity)

            wrong_identity = deepcopy(manifest)
            wrong_identity["extractors"][position]["name"] = "other"
            invalid_manifests.append(wrong_identity)

        for invalid in invalid_manifests:
            with self.subTest(names=[item.get("name") for item in invalid["extractors"]]):
                with self.assertRaises(ValidationError):
                    validator.validate(invalid)

    def test_manifest_dependency_schema_matches_runtime_contract(self) -> None:
        schema = json.loads(
            (SCHEMAS / "preparation-manifest-v0.1.schema.json").read_text("utf-8")
        )
        dependency_schema = schema["$defs"]["runtime"]["properties"][
            "dependencies"
        ]
        manifest, _ = real_observation_documents()

        self.assertFalse(dependency_schema["additionalProperties"])
        self.assertEqual(
            dependency_schema["required"], list(RUNTIME_DEPENDENCIES)
        )
        self.assertEqual(
            {
                name: contract["const"]
                for name, contract in dependency_schema["properties"].items()
            },
            dict(RUNTIME_DEPENDENCIES),
        )
        self.assertEqual(
            manifest["runtime"]["dependencies"], dict(RUNTIME_DEPENDENCIES)
        )

    def test_manifest_nested_objects_are_closed_and_required(self) -> None:
        schema = json.loads(
            (SCHEMAS / "preparation-manifest-v0.1.schema.json").read_text("utf-8")
        )
        validator = Draft202012Validator(schema)
        manifest, _ = real_observation_documents()
        validator.validate(manifest)

        cases = (
            (manifest, (), "schema_version"),
            (manifest, ("source",), "sha256"),
            (manifest, ("runtime",), "python"),
            (manifest, ("runtime", "lockfile"), "sha256"),
            (manifest, ("runtime", "dependencies"), "docling"),
            (manifest, ("configurations",), "docling"),
            (manifest, ("configurations", "docling"), "accelerator"),
            (manifest, ("configurations", "markitdown"), "convert_method"),
            (manifest, ("docling_document_schema",), "name"),
            (manifest, ("models",), "required"),
            (manifest, ("extractors", 0), "name"),
            (manifest, ("extractors", 0, "artifacts", 0), "role"),
            (manifest, ("extractors", 1), "name"),
            (manifest, ("extractors", 1, "artifacts", 0), "role"),
            (manifest, ("comparison",), "status"),
        )

        model_manifest = deepcopy(manifest)
        model_manifest["models"] = {
            "required": True,
            "path": "/models",
            "inventory_hash": "a" * 64,
            "files": [{"path": "model.bin", "size": 1, "sha256": "b" * 64}],
        }
        validator.validate(model_manifest)
        cases += ((model_manifest, ("models", "files", 0), "path"),)

        error_manifest = deepcopy(manifest)
        error_manifest["extractors"][0]["status"] = "FAILED"
        error_manifest["extractors"][0]["artifacts"] = []
        error_manifest["extractors"][0]["error"] = {
            "code": "DOCLING_CONVERSION_FAILED",
            "message": "stable error",
        }
        validator.validate(error_manifest)
        cases += ((error_manifest, ("extractors", 0, "error"), "code"),)

        for document, path, required in cases:
            with self.subTest(path=path, required=required):
                self.assert_closed_object_contract(
                    validator, document, path, required
                )

    def test_comparison_nested_objects_are_closed_and_required(self) -> None:
        schema = json.loads(
            (SCHEMAS / "comparison-summary-v0.1.schema.json").read_text("utf-8")
        )
        validator = Draft202012Validator(schema)
        _, comparison = real_observation_documents()
        validator.validate(comparison)
        cases = (
            ((), "schema_version"),
            (("source",), "sha256"),
            (("views",), "docling"),
            (("views", "docling"), "artifact_sha256"),
            (("views", "markitdown"), "artifact_sha256"),
            (("deltas",), "normalized_equal"),
        )
        for path, required in cases:
            with self.subTest(path=path, required=required):
                self.assert_closed_object_contract(
                    validator, comparison, path, required
                )


if __name__ == "__main__":
    unittest.main()
