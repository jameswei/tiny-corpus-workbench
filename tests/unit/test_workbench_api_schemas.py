from __future__ import annotations

import json
import unittest
from pathlib import Path

from tiny_corpus_workbench.canonical_json import canonical_json
from tiny_corpus_workbench.schema_catalog import validate_document


FIXTURES = Path(__file__).resolve().parents[1] / "fixtures" / "workbench-api"


class WorkbenchApiSchemaTests(unittest.TestCase):
    def test_all_committed_examples_are_canonical_and_schema_valid(self) -> None:
        for path in sorted(FIXTURES.glob("*.json")):
            with self.subTest(path=path.name):
                raw = path.read_bytes()
                value = json.loads(raw)
                self.assertEqual(raw, canonical_json(value) + b"\n")
                if path.name == "startup.json":
                    validate_document("tcw.workbench-startup/v0.5", value)
                elif path.name.startswith("projection-"):
                    validate_document("tcw.workbench-projection/v0.5", value)
                elif path.name.startswith("detail-"):
                    validate_document("tcw.workbench-record-detail/v0.5", value)
                else:
                    for error in value:
                        validate_document("tcw.workbench-error/v0.5", error)


if __name__ == "__main__":
    unittest.main()
