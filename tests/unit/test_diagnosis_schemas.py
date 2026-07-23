from __future__ import annotations

import json
import unittest
from copy import deepcopy
from pathlib import Path

from jsonschema import Draft202012Validator, ValidationError

from tiny_corpus_workbench.diagnosis import (
    RULESET_DESCRIPTOR,
    _validator,
    make_finding_set,
    validate_finding_set_semantics,
)
from tiny_corpus_workbench.domain import IntegrityError
from tests.unit.test_diagnosis_rules import document, text


SCHEMAS = Path("src/tiny_corpus_workbench/schemas")


class DiagnosisSchemaTests(unittest.TestCase):
    def test_diagnosis_registry_is_closed_and_matches_committed_bytes(self) -> None:
        registry = json.loads(
            Path("fixtures/diagnosis/v0.2/fixtures.json").read_text("utf-8")
        )
        schema = json.loads(
            (SCHEMAS / "diagnosis-fixture-registry-v0.2.schema.json").read_text(
                "utf-8"
            )
        )
        validator = Draft202012Validator(schema)
        validator.validate(registry)
        self.assertEqual([item["id"] for item in registry["fixtures"]], [
            "short-note",
            "structural-traps",
            "repeated-margin",
        ])
        for item in registry["fixtures"]:
            path = Path(item["path"])
            self.assertEqual(path.stat().st_size, item["size"])
            import hashlib

            self.assertEqual(hashlib.sha256(path.read_bytes()).hexdigest(), item["sha256"])
        changed = deepcopy(registry)
        changed["unexpected"] = True
        with self.assertRaises(ValidationError):
            validator.validate(changed)

    def test_finding_set_and_nested_objects_are_closed(self) -> None:
        observation = {
            "observation_id": "a" * 64,
            "source": {"media_type": "text/markdown"},
        }
        finding_set = make_finding_set(
            document([text(0, "x\ufffd")]),
            observation,
            manifest_hash="b" * 64,
            document_hash="c" * 64,
        )
        validator = _validator("finding-set-v0.2.schema.json")
        validator.validate(finding_set)
        cases = [
            ((), "schema_version"),
            (("ruleset",), "name"),
            (("ruleset", "rules", 0), "rule_id"),
            (("summary",), "total"),
            (("summary", "by_severity"), "ERROR"),
            (("summary", "by_rule"), "TCW-D001"),
            (("findings", 0), "finding_id"),
        ]
        for path, required in cases:
            with self.subTest(path=path):
                missing = deepcopy(finding_set)
                target = missing
                for part in path:
                    target = target[part]
                del target[required]
                with self.assertRaises(ValidationError):
                    validator.validate(missing)
                unknown = deepcopy(finding_set)
                target = unknown
                for part in path:
                    target = target[part]
                target["unexpected"] = True
                with self.assertRaises(ValidationError):
                    validator.validate(unknown)

    def test_ruleset_contract_contains_exact_eight_ordered_rules(self) -> None:
        self.assertEqual(
            [rule["rule_id"] for rule in RULESET_DESCRIPTOR["rules"]],
            [f"TCW-D00{number}" for number in range(1, 9)],
        )

    def test_staged_semantic_validation_rejects_cross_field_mutations(self) -> None:
        payload = document([text(0, "x\ufffd")])
        observation = {
            "observation_id": "a" * 64,
            "source": {"media_type": "text/markdown"},
        }
        baseline = make_finding_set(
            payload,
            observation,
            manifest_hash="b" * 64,
            document_hash="c" * 64,
        )
        validate_finding_set_semantics(baseline, payload)
        mutations = []

        duplicate = deepcopy(baseline)
        duplicate["findings"].append(deepcopy(duplicate["findings"][0]))
        mutations.append(duplicate)

        summary = deepcopy(baseline)
        summary["summary"]["total"] += 1
        mutations.append(summary)

        identity = deepcopy(baseline)
        identity["findings"][0]["finding_id"] = "0" * 64
        mutations.append(identity)

        reference = deepcopy(baseline)
        reference["findings"][0]["document_refs"] = ["#/texts/99"]
        mutations.append(reference)

        for index, mutation in enumerate(mutations):
            with self.subTest(mutation=index):
                with self.assertRaises(IntegrityError):
                    validate_finding_set_semantics(mutation, payload)


if __name__ == "__main__":
    unittest.main()
