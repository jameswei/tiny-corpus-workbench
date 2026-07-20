from __future__ import annotations

import json
import unittest
from pathlib import Path

from jsonschema import Draft202012Validator, ValidationError


SCHEMAS = Path("src/tiny_corpus_workbench/schemas")


class SchemaTests(unittest.TestCase):
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

    def test_empty_manifest_and_comparison_are_rejected(self) -> None:
        for name in ("preparation-manifest-v0.1.schema.json", "comparison-summary-v0.1.schema.json"):
            schema = json.loads((SCHEMAS / name).read_text("utf-8"))
            with self.subTest(schema=name), self.assertRaises(ValidationError):
                Draft202012Validator(schema).validate({})


if __name__ == "__main__":
    unittest.main()
