from __future__ import annotations

import json
import unittest
from copy import deepcopy

from jsonschema import ValidationError

from tiny_corpus_workbench.canonical_json import canonical_sha256
from tiny_corpus_workbench.supported_provenance import (
    ACTIVE_RUNTIME_ERROR,
    COMMAND_IDS,
    GENERATOR_IDS,
    MALFORMED_RECORDED_PROVENANCE_ERROR,
    RECORDED_PROVENANCE_ERROR,
    load_registry,
    provenance_tuple,
    resolve_active_provenance,
    resolve_provenance,
    validate_recorded_provenance,
    validate_registry,
)


class SupportedProvenanceTests(unittest.TestCase):
    def appended_entry(self, registry: dict) -> dict:
        entry = deepcopy(registry["entries"][-1])
        patch = 1
        while True:
            entry["package_version"] = f"0.5.{patch}"
            entry["provenance_id"] = canonical_sha256(provenance_tuple(entry))
            if entry["provenance_id"] > registry["entries"][-1]["provenance_id"]:
                return entry
            patch += 1

    def test_checked_in_registry_fixes_the_initial_truthful_tuple(self) -> None:
        registry = load_registry()
        self.assertEqual(registry["contract_schema_version"], "v0.5")
        self.assertEqual(len(registry["entries"]), 1)
        entry = registry["entries"][0]
        self.assertEqual(entry["package_version"], "0.5.0")
        self.assertEqual(entry["lockfile_sha256"], "2db4442fd44959691f9a391fec9fd46f8f14cf38b03679d97f6224dd2f1b3f0b")
        self.assertEqual(entry["python"], {"implementation": "CPython", "major_minor": "3.12"})
        self.assertEqual(entry["dependencies"], {"docling": "2.113.0", "docling-core": "2.87.1", "jsonschema": "4.26.0", "markitdown": "0.1.6"})
        self.assertEqual(entry["commands"], list(COMMAND_IDS))
        self.assertEqual(entry["generators"], list(GENERATOR_IDS))
        self.assertEqual(entry["provenance_id"], canonical_sha256(provenance_tuple(entry)))
        self.assertIs(resolve_provenance(entry["provenance_id"], registry), entry)

    def test_registry_rejects_unknown_ids_mutation_duplicates_and_bad_order(self) -> None:
        registry = load_registry()
        with self.assertRaisesRegex(ValueError, "unsupported"):
            resolve_provenance("f" * 64, registry)

        mutated = deepcopy(registry)
        mutated["entries"][0]["package_version"] = "0.5.1"
        with self.assertRaisesRegex(ValueError, "does not match"):
            validate_registry(mutated)

        duplicate = deepcopy(registry)
        duplicate["entries"].append(deepcopy(duplicate["entries"][0]))
        with self.assertRaisesRegex(ValueError, "ordered and unique"):
            validate_registry(duplicate)

        unordered = deepcopy(registry)
        unordered["entries"][0]["commands"] = list(reversed(COMMAND_IDS))
        with self.assertRaisesRegex(ValueError, "not ordered"):
            validate_registry(unordered)

    def test_registry_extension_is_append_only_in_contract_terms(self) -> None:
        original = load_registry()
        candidate = json.loads(json.dumps(original))
        entry = self.appended_entry(candidate)
        candidate["entries"].append(entry)
        validate_registry(candidate)
        self.assertEqual(
            candidate["entries"][: len(original["entries"])],
            original["entries"],
        )

    def test_registry_rejects_deletion_mutation_replacement_reordering_and_duplicate(
        self,
    ) -> None:
        baseline = load_registry()

        deleted = deepcopy(baseline)
        deleted["entries"] = []
        with self.assertRaises((ValidationError, ValueError)):
            validate_registry(deleted)

        mutated = deepcopy(baseline)
        mutated["entries"][0]["commands"].remove("tcw.workbench")
        with self.assertRaisesRegex(ValueError, "preserve checked-in"):
            validate_registry(mutated)

        replacement = deepcopy(baseline)
        replacement["entries"][0]["package_version"] = "0.5.99"
        replacement["entries"][0]["provenance_id"] = canonical_sha256(
            provenance_tuple(replacement["entries"][0])
        )
        with self.assertRaisesRegex(ValueError, "preserve checked-in"):
            validate_registry(replacement)

        extended = deepcopy(baseline)
        extended["entries"].append(self.appended_entry(extended))
        reordered = deepcopy(extended)
        reordered["entries"].reverse()
        with self.assertRaises(ValueError):
            validate_registry(reordered)

        duplicate = deepcopy(extended)
        duplicate["entries"].append(deepcopy(duplicate["entries"][-1]))
        with self.assertRaises(ValueError):
            validate_registry(duplicate)

    def test_recorded_lookup_is_by_id_then_compares_every_applicable_field(self) -> None:
        registry = load_registry()
        entry = registry["entries"][0]
        recorded = {
            key: entry[key]
            for key in ("provenance_id", "package_version", "lockfile_sha256", "python", "dependencies")
        }
        recorded["command_id"] = "tcw.observe"
        recorded["extractor_contract"] = entry["extractor_contract"]
        self.assertIs(
            validate_recorded_provenance(
                recorded,
                command_id="tcw.observe",
                extracting=True,
                registry=registry,
            ),
            entry,
        )
        for mutation in (
            {**recorded, "package_version": "0.5.1"},
            {**recorded, "command_id": "tcw.verify"},
            {**recorded, "provenance_id": "f" * 64},
        ):
            with self.assertRaisesRegex(ValueError, RECORDED_PROVENANCE_ERROR):
                validate_recorded_provenance(
                    mutation,
                    command_id="tcw.observe",
                    extracting=True,
                    registry=registry,
                )
        malformed = deepcopy(recorded)
        del malformed["python"]
        with self.assertRaisesRegex(
            ValueError, MALFORMED_RECORDED_PROVENANCE_ERROR
        ):
            validate_recorded_provenance(
                malformed,
                command_id="tcw.observe",
                extracting=True,
                registry=registry,
            )

    def test_active_runtime_resolution_has_distinct_failure(self) -> None:
        registry = load_registry()
        entry = registry["entries"][0]
        active = provenance_tuple(entry)
        self.assertIs(
            resolve_active_provenance(
                active, command_id="tcw.workbench", registry=registry
            ),
            entry,
        )
        invalid = deepcopy(active)
        invalid["package_version"] = "0.5.1"
        with self.assertRaisesRegex(ValueError, ACTIVE_RUNTIME_ERROR):
            resolve_active_provenance(
                invalid, command_id="tcw.workbench", registry=registry
            )


if __name__ == "__main__":
    unittest.main()
