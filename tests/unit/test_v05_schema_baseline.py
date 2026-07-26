from __future__ import annotations

import json
import re
import subprocess
import unittest
from collections import Counter
from copy import deepcopy
from pathlib import Path

from jsonschema import Draft202012Validator, ValidationError

from tiny_corpus_workbench.canonical_json import canonical_json
from tiny_corpus_workbench.canonical_json import (
    artifact_key,
    edge_key,
    record_key,
    session_id,
)
from tiny_corpus_workbench.schema_catalog import (
    PRIVATE_MIGRATION_SCHEMAS,
    SCHEMA_FILES,
    SCHEMA_ROOT,
    load_schema,
    validate_document,
    validator,
)
from tiny_corpus_workbench.semantic_validation import SemanticValidationError
from tiny_corpus_workbench.supported_provenance import load_registry


API_FIXTURES = Path("tests/fixtures/workbench-api")
INVENTORY = Path("tests/fixtures/v05-schema-evidence-inventory.json")
PROVENANCE_EXAMPLES = Path("tests/fixtures/v05-provenance-examples.json")

PLACEMENT = {
    "tcw.fixture-registry/v0.5": ("BUILD_GENERATOR", "tools.generate_fixtures"),
    "tcw.preparation-manifest/v0.5": ("BUILD_EXTRACTING_COMMAND", "tcw.observe"),
    "tcw.verification-result/v0.5": ("BUILD_COMMAND", "tcw.verify"),
    "tcw.diagnosis-fixture-registry/v0.5": ("BUILD_GENERATOR", "tools.generate_diagnosis_fixtures"),
    "tcw.diagnosis-manifest/v0.5": ("BUILD_COMMAND", "tcw.diagnose"),
    "tcw.diagnosis-verification-result/v0.5": ("BUILD_COMMAND", "tcw.verify-diagnosis"),
    "tcw.refinement-fixture-registry/v0.5": ("BUILD_GENERATOR", "tools.generate_refinement_fixtures"),
    "tcw.refinement-draft/v0.5": ("BUILD_COMMAND", "tcw.draft-refinement"),
    "tcw.refinement-manifest/v0.5": ("BUILD_COMMAND", "tcw.resolve-refinement"),
    "tcw.refinement-verification-result/v0.5": ("BUILD_COMMAND", "tcw.verify-refinement"),
    "tcw.corpus-manifest/v0.5": ("BUILD_EXTRACTING_COMMAND", "tcw.inspect-corpus"),
    "tcw.corpus-verification-result/v0.5": ("BUILD_COMMAND", "tcw.verify-corpus"),
}
PROHIBITED = {
    "tcw.authored-fixture/v0.5",
    "tcw.comparison-summary/v0.5",
    "tcw.finding-set/v0.5",
    "tcw.transformation/v0.5",
    "tcw.transformation-history/v0.5",
    "tcw.corpus-spec/v0.5",
    "tcw.corpus-summary/v0.5",
    "tcw.workbench-startup/v0.5",
    "tcw.workbench-projection/v0.5",
    "tcw.workbench-record-detail/v0.5",
    "tcw.workbench-error/v0.5",
}


def resolve_pointer(document: object, pointer: str) -> object:
    value = document
    for token in pointer.removeprefix("#/").split("/"):
        token = token.replace("~1", "/").replace("~0", "~")
        value = value[int(token)] if isinstance(value, list) else value[token]
    return value


def nested_object(
    document: dict, path: tuple[str | int, ...]
) -> dict:
    value = document
    for part in path:
        value = value[part]
    return value


def walk_keys(value: object):
    if isinstance(value, dict):
        yield from value
        for child in value.values():
            yield from walk_keys(child)
    elif isinstance(value, list):
        for child in value:
            yield from walk_keys(child)


def top_properties(schema: dict) -> list[dict]:
    if "properties" in schema:
        return [schema["properties"]]
    return [
        branch["properties"]
        for branch in schema.get("oneOf", ())
        if "properties" in branch
    ]


def object_paths(value: object, path: tuple[str | int, ...] = ()):
    if isinstance(value, dict):
        yield path
        for key, child in value.items():
            yield from object_paths(child, (*path, key))
    elif isinstance(value, list):
        for index, child in enumerate(value):
            yield from object_paths(child, (*path, index))


def schema_object_nodes(value: object):
    if isinstance(value, dict):
        kind = value.get("type")
        if kind == "object" or (
            isinstance(kind, list) and "object" in kind
        ):
            yield value
        for child in value.values():
            yield from schema_object_nodes(child)
    elif isinstance(value, list):
        for child in value:
            yield from schema_object_nodes(child)


def git_tree_paths(base: str, *scopes: str) -> set[str]:
    result = subprocess.run(
        ["git", "ls-tree", "-r", "--name-only", base, *scopes],
        check=True,
        capture_output=True,
        text=True,
    )
    return {line for line in result.stdout.splitlines() if line}


class V05SchemaBaselineTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.registry_entry = load_registry()["entries"][0]
        cls.common = json.loads((SCHEMA_ROOT / "common-v0.5.schema.json").read_text("utf-8"))

    def build_shape(self, shape: str, identifier: str) -> dict:
        entry = self.registry_entry
        result = {
            "provenance_id": entry["provenance_id"],
            "package_version": entry["package_version"],
            "lockfile_sha256": entry["lockfile_sha256"],
            "python": entry["python"],
            "dependencies": entry["dependencies"],
        }
        if shape == "BUILD_GENERATOR":
            result["generator_id"] = identifier
        else:
            result["command_id"] = identifier
            if shape == "BUILD_EXTRACTING_COMMAND":
                result["extractor_contract"] = entry["extractor_contract"]
        return result

    def assert_public_validation_rejects(
        self, schema_version: str, document: dict
    ) -> None:
        with self.assertRaises((ValidationError, SemanticValidationError)):
            validate_document(schema_version, document)

    def test_catalog_contains_exact_public_baseline_and_marks_old_schemas_private(self) -> None:
        self.assertEqual(len(SCHEMA_FILES), 24)
        for schema_version, filename in SCHEMA_FILES.items():
            with self.subTest(schema=schema_version):
                schema = load_schema(schema_version)
                self.assertTrue(
                    all(
                        properties["schema_version"]["const"] == schema_version
                        for properties in top_properties(schema)
                    )
                )
                self.assertEqual(filename, (SCHEMA_ROOT / filename).name)
        self.assertTrue(PRIVATE_MIGRATION_SCHEMAS)
        self.assertTrue(all("-v0.5." not in name for name in PRIVATE_MIGRATION_SCHEMAS))

    def test_shared_shapes_are_closed_exact_and_not_interchangeable(self) -> None:
        for schema_version, (shape, identifier) in PLACEMENT.items():
            candidate = self.build_shape(shape, identifier)
            shape_validator = validator(schema_version).evolve(
                schema=load_schema(schema_version)["properties"]["build_provenance"]
            )
            shape_validator.validate(candidate)
            for field in tuple(candidate):
                with self.subTest(schema=schema_version, missing=field):
                    invalid = deepcopy(candidate)
                    del invalid[field]
                    with self.assertRaises(ValidationError):
                        shape_validator.validate(invalid)
            invalid = deepcopy(candidate)
            invalid["unexpected"] = True
            with self.assertRaises(ValidationError):
                shape_validator.validate(invalid)
            wrong_field = (
                "command_id"
                if shape == "BUILD_GENERATOR"
                else "generator_id"
            )
            invalid = deepcopy(candidate)
            invalid[wrong_field] = (
                "tools.generate_fixtures"
                if wrong_field == "generator_id"
                else "tcw.verify"
            )
            with self.assertRaises(ValidationError):
                shape_validator.validate(invalid)

    def test_every_explicit_object_schema_is_closed(self) -> None:
        common = json.loads((SCHEMA_ROOT / "common-v0.5.schema.json").read_text("utf-8"))
        for schema_version in SCHEMA_FILES:
            schema = load_schema(schema_version)
            for node in schema_object_nodes(schema):
                with self.subTest(schema=schema_version):
                    self.assertIs(node.get("additionalProperties"), False)
        for node in schema_object_nodes(common):
            self.assertIs(node.get("additionalProperties"), False)

    def test_canonical_positive_examples_cover_every_provenance_placement(self) -> None:
        raw = PROVENANCE_EXAMPLES.read_bytes()
        document = json.loads(raw)
        self.assertEqual(raw, canonical_json(document) + b"\n")
        examples = {
            item["schema_version"]: item["build_provenance"]
            for item in document["examples"]
        }
        self.assertEqual(set(examples), set(PLACEMENT))
        for schema_version, build_provenance in examples.items():
            property_schema = load_schema(schema_version)["properties"][
                "build_provenance"
            ]
            validator(schema_version).evolve(schema=property_schema).validate(
                build_provenance
            )

    def test_complete_provenance_placement_and_reserved_namespace(self) -> None:
        self.assertEqual(set(PLACEMENT) | PROHIBITED | {"tcw.supported-provenance-registry/v0.5"}, set(SCHEMA_FILES))
        for schema_version in PROHIBITED:
            schema = load_schema(schema_version)
            for properties in top_properties(schema):
                self.assertNotIn("build_provenance", properties)
                self.assertNotIn("provenance", properties)
        for schema_version in PLACEMENT:
            schema = load_schema(schema_version)
            self.assertIn("build_provenance", schema["required"])
            self.assertNotIn("runtime", schema["properties"]["build_provenance"])

    def test_no_v05_schema_has_milestone_or_release_specific_constants(self) -> None:
        for schema_version in SCHEMA_FILES:
            schema = load_schema(schema_version)
            keys = tuple(walk_keys(schema))
            self.assertNotIn("milestone", keys)
            encoded = canonical_json(schema)
            self.assertNotIn(b'"const":"0.5.0"', encoded)
            self.assertNotIn(b'"const":"2.113.0"', encoded)
            self.assertNotIn(b'"const":"4.26.0"', encoded)

    def test_api_examples_are_canonical_and_validate(self) -> None:
        mapping = {
            "startup.json": "tcw.workbench-startup/v0.5",
            "projection-observation.json": "tcw.workbench-projection/v0.5",
            "projection-contained-dedup.json": "tcw.workbench-projection/v0.5",
            "projection-missing-edge.json": "tcw.workbench-projection/v0.5",
            "detail-observation.json": "tcw.workbench-record-detail/v0.5",
            "detail-diagnosis.json": "tcw.workbench-record-detail/v0.5",
            "detail-diagnosis-refinement-subject.json": (
                "tcw.workbench-record-detail/v0.5"
            ),
            "detail-refinement-applied.json": "tcw.workbench-record-detail/v0.5",
            "detail-refinement-rejected.json": "tcw.workbench-record-detail/v0.5",
            "detail-corpus.json": "tcw.workbench-record-detail/v0.5",
        }
        for filename, schema_version in mapping.items():
            raw = (API_FIXTURES / filename).read_bytes()
            document = json.loads(raw)
            with self.subTest(filename=filename):
                self.assertEqual(raw, canonical_json(document) + b"\n")
                validate_document(schema_version, document)
        errors_raw = (API_FIXTURES / "errors.json").read_bytes()
        errors = json.loads(errors_raw)
        self.assertEqual(errors_raw, canonical_json(errors) + b"\n")
        for error in errors:
            validator("tcw.workbench-error/v0.5").validate(error)

    def test_inline_plan_startup_and_error_examples_validate(self) -> None:
        plan = Path(
            "docs/plans/v0.5-local-visual-workbench.md"
        ).read_text("utf-8")
        startup_match = re.search(
            r'^\{"api_url":"http://127\.0\.0\.1:8765/api/v0\.5/workbench".+$',
            plan,
            re.MULTILINE,
        )
        error_match = re.search(
            r'^\{"error":\{"code":"METHOD_NOT_ALLOWED".+$',
            plan,
            re.MULTILINE,
        )
        self.assertIsNotNone(startup_match)
        self.assertIsNotNone(error_match)
        validator("tcw.workbench-startup/v0.5").validate(
            json.loads(startup_match.group())
        )
        error = json.loads(error_match.group())
        validator("tcw.workbench-error/v0.5").validate(error)
        self.assertNotIn("runtime", error)
        self.assertNotIn("build_provenance", error)

    def test_api_objects_reject_an_extra_field_at_every_nesting_level(self) -> None:
        mapping = {
            "startup.json": "tcw.workbench-startup/v0.5",
            "projection-observation.json": "tcw.workbench-projection/v0.5",
            "detail-observation.json": "tcw.workbench-record-detail/v0.5",
            "detail-diagnosis.json": "tcw.workbench-record-detail/v0.5",
            "detail-diagnosis-refinement-subject.json": (
                "tcw.workbench-record-detail/v0.5"
            ),
            "detail-refinement-applied.json": "tcw.workbench-record-detail/v0.5",
            "detail-refinement-rejected.json": "tcw.workbench-record-detail/v0.5",
            "detail-corpus.json": "tcw.workbench-record-detail/v0.5",
        }
        for filename, schema_version in mapping.items():
            original = json.loads((API_FIXTURES / filename).read_text("utf-8"))
            for path in object_paths(original):
                invalid = deepcopy(original)
                nested_object(invalid, path)["unexpected_test_field"] = True
                with self.subTest(filename=filename, path=path), self.assertRaises(
                    ValidationError
                ):
                    validator(schema_version).validate(invalid)

    def test_api_discriminator_and_nullability_negative_cases(self) -> None:
        projection = json.loads(
            (API_FIXTURES / "projection-missing-edge.json").read_text("utf-8")
        )
        invalid = deepcopy(projection)
        invalid["records"][0]["kind"] = "OBSERVATION"
        self.assert_public_validation_rejects(
            "tcw.workbench-projection/v0.5", invalid
        )
        invalid = deepcopy(projection)
        invalid["edges"][0]["state"] = "MATCH"
        self.assert_public_validation_rejects(
            "tcw.workbench-projection/v0.5", invalid
        )

        rejected = json.loads(
            (API_FIXTURES / "detail-refinement-rejected.json").read_text("utf-8")
        )
        rejected["detail"]["parent_target"] = json.loads(
            (API_FIXTURES / "detail-refinement-applied.json").read_text("utf-8")
        )["detail"]["base_target"]
        self.assert_public_validation_rejects(
            "tcw.workbench-record-detail/v0.5", rejected
        )

        corpus = json.loads(
            (API_FIXTURES / "detail-corpus.json").read_text("utf-8")
        )
        corpus["detail"]["external_revisions"][0]["record_key"] = "a" * 64
        self.assert_public_validation_rejects(
            "tcw.workbench-record-detail/v0.5", corpus
        )

    def test_d006_owner_declared_union_semantics_are_exact(self) -> None:
        diagnosis = json.loads(
            (API_FIXTURES / "detail-diagnosis.json").read_text("utf-8")
        )
        index = next(
            index
            for index, finding in enumerate(
                diagnosis["detail"]["findings"]
            )
            if finding["rule_id"] == "TCW-D006"
            and finding["evidence"]["relationship_kind"]
            == "invalid_declared_caption"
        )

        declared_owner = deepcopy(diagnosis)
        finding = declared_owner["detail"]["findings"][index]
        finding["document_refs"] = ["#/pictures/0", "#/tables/0"]
        finding["evidence"]["declared_ref"] = "#/tables/0"
        validate_document(
            "tcw.workbench-record-detail/v0.5", declared_owner
        )

        two_owners_external = deepcopy(diagnosis)
        finding = two_owners_external["detail"]["findings"][index]
        finding["document_refs"] = [
            "#/pictures/0",
            "#/tables/0",
            "#/texts/6",
        ]
        self.assert_public_validation_rejects(
            "tcw.workbench-record-detail/v0.5",
            two_owners_external,
        )

        declared_owner_extra_text = deepcopy(diagnosis)
        finding = declared_owner_extra_text["detail"]["findings"][index]
        finding["document_refs"] = ["#/tables/0", "#/texts/6"]
        finding["evidence"]["declared_ref"] = "#/tables/0"
        self.assert_public_validation_rejects(
            "tcw.workbench-record-detail/v0.5",
            declared_owner_extra_text,
        )

    def test_public_semantic_validation_rejects_cross_field_equation_defects(
        self,
    ) -> None:
        startup = json.loads(
            (API_FIXTURES / "startup.json").read_text("utf-8")
        )
        for field in (
            "record_count",
            "top_level_record_count",
            "contained_record_count",
        ):
            invalid = deepcopy(startup)
            invalid[field] += 1
            with self.subTest(contract="startup-count", field=field):
                self.assert_public_validation_rejects(
                    "tcw.workbench-startup/v0.5", invalid
                )

        projection = json.loads(
            (API_FIXTURES / "projection-contained-dedup.json").read_text(
                "utf-8"
            )
        )
        for field in (
            "record_count",
            "top_level_record_count",
            "contained_record_count",
        ):
            invalid = deepcopy(projection)
            invalid["counts"][field] += 1
            with self.subTest(contract="projection-count", field=field):
                self.assert_public_validation_rejects(
                    "tcw.workbench-projection/v0.5", invalid
                )
        for field in ("records", "edges"):
            invalid = deepcopy(projection)
            invalid[field].reverse()
            with self.subTest(contract="projection-order", field=field):
                self.assert_public_validation_rejects(
                    "tcw.workbench-projection/v0.5", invalid
                )
        invalid = deepcopy(projection)
        invalid["records"][0]["contained_by"] = ["f" * 64, "0" * 64]
        self.assert_public_validation_rejects(
            "tcw.workbench-projection/v0.5", invalid
        )
        invalid = deepcopy(projection)
        invalid["edges"][0]["relation"] = "REFINEMENT_PARENT"
        invalid["edges"][0]["edge_key"] = edge_key(
            relation=invalid["edges"][0]["relation"],
            from_record_key=invalid["edges"][0]["from_record_key"],
            expected_target=invalid["edges"][0]["expected_target"],
        )
        self.assert_public_validation_rejects(
            "tcw.workbench-projection/v0.5", invalid
        )
        invalid = deepcopy(projection)
        invalid["session_id"] = "0" * 64
        self.assert_public_validation_rejects(
            "tcw.workbench-projection/v0.5", invalid
        )

        diagnosis = json.loads(
            (API_FIXTURES / "detail-diagnosis.json").read_text("utf-8")
        )
        for rule_id, field in (
            ("TCW-D003", "occurrence_count"),
            ("TCW-D007", "page_count"),
        ):
            invalid = deepcopy(diagnosis)
            finding = next(
                item
                for item in invalid["detail"]["findings"]
                if item["rule_id"] == rule_id
            )
            finding["evidence"][field] += 1
            with self.subTest(contract="finding-count", rule=rule_id):
                self.assert_public_validation_rejects(
                    "tcw.workbench-record-detail/v0.5", invalid
                )
        invalid = deepcopy(diagnosis)
        d003 = next(
            item
            for item in invalid["detail"]["findings"]
            if item["rule_id"] == "TCW-D003"
        )
        d003["evidence"]["code_point_offsets"] = [2, 1]
        d003["evidence"]["occurrence_count"] = 2
        self.assert_public_validation_rejects(
            "tcw.workbench-record-detail/v0.5", invalid
        )
        invalid = deepcopy(diagnosis)
        d007 = next(
            item
            for item in invalid["detail"]["findings"]
            if item["rule_id"] == "TCW-D007"
        )
        d007["evidence"]["page_numbers"].reverse()
        self.assert_public_validation_rejects(
            "tcw.workbench-record-detail/v0.5", invalid
        )
        for field in ("findings",):
            invalid = deepcopy(diagnosis)
            invalid["detail"][field].reverse()
            self.assert_public_validation_rejects(
                "tcw.workbench-record-detail/v0.5", invalid
            )
        invalid = deepcopy(diagnosis)
        invalid["detail"]["ruleset"]["rules"].reverse()
        self.assert_public_validation_rejects(
            "tcw.workbench-record-detail/v0.5", invalid
        )

        refinement = json.loads(
            (API_FIXTURES / "detail-refinement-applied.json").read_text(
                "utf-8"
            )
        )
        for mutation in ("ordinal", "hash", "parent"):
            invalid = deepcopy(refinement)
            if mutation == "ordinal":
                invalid["detail"]["transformations"][0]["ordinal"] = 1
            elif mutation == "hash":
                invalid["detail"]["revision_chain"][0]["after_sha256"] = (
                    "0" * 64
                )
            else:
                invalid["detail"]["parent_target"] = invalid["detail"][
                    "base_target"
                ]
            with self.subTest(contract="refinement", mutation=mutation):
                self.assert_public_validation_rejects(
                    "tcw.workbench-record-detail/v0.5", invalid
                )

        corpus = json.loads(
            (API_FIXTURES / "detail-corpus.json").read_text("utf-8")
        )
        corpus_mutations = {
            "member-total": lambda value: value["detail"]["summary"][
                "totals"
            ].__setitem__("member_count", 4),
            "status-total": lambda value: value["detail"]["summary"][
                "totals"
            ].__setitem__("complete", 2),
            "named-count": lambda value: value["detail"]["aggregates"][
                "by_family"
            ][0].__setitem__("member_count", 2),
            "extractor-count": lambda value: value["detail"]["aggregates"][
                "extractors"
            ][0].__setitem__("available", 3),
            "matrix-order": lambda value: value["detail"]["matrix"].reverse(),
            "family-order": lambda value: value["detail"]["aggregates"][
                "by_family"
            ].reverse(),
            "format-order": lambda value: value["detail"]["aggregates"][
                "by_format"
            ].reverse(),
            "extractor-order": lambda value: value["detail"]["aggregates"][
                "extractors"
            ].reverse(),
            "comparison-order": lambda value: value["detail"]["aggregates"][
                "comparisons"
            ].reverse(),
            "contained-order": lambda value: value["detail"][
                "contained_record_keys"
            ].reverse(),
            "contained-union": lambda value: value["detail"][
                "contained_record_keys"
            ].pop(),
            "comparison-complete-nullability": lambda value: value["detail"][
                "aggregates"
            ]["comparisons"][0].__setitem__(
                "docling_minus_markitdown", None
            ),
            "comparison-incomplete-nullability": lambda value: value["detail"][
                "aggregates"
            ]["comparisons"][1].__setitem__(
                "docling_minus_markitdown",
                deepcopy(
                    value["detail"]["aggregates"]["comparisons"][0][
                        "docling_minus_markitdown"
                    ]
                ),
            ),
            "comparison-unavailable-nullability": lambda value: value[
                "detail"
            ]["aggregates"]["comparisons"][2].__setitem__(
                "docling",
                deepcopy(
                    value["detail"]["aggregates"]["comparisons"][0][
                        "docling"
                    ]
                ),
            ),
            "row-nullability": lambda value: value["detail"]["matrix"][
                0
            ].__setitem__(
                "error",
                {
                    "code": "MEMBER_INCOMPLETE",
                    "message": "Unexpected error.",
                },
            ),
            "external-nullability": lambda value: value["detail"][
                "external_revisions"
            ][0].__setitem__("record_key", None),
        }
        for name, mutate in corpus_mutations.items():
            invalid = deepcopy(corpus)
            mutate(invalid)
            with self.subTest(contract="corpus", mutation=name):
                self.assert_public_validation_rejects(
                    "tcw.workbench-record-detail/v0.5", invalid
                )

        observation = json.loads(
            (API_FIXTURES / "detail-observation.json").read_text("utf-8")
        )
        invalid = deepcopy(observation)
        invalid["artifacts"].reverse()
        self.assert_public_validation_rejects(
            "tcw.workbench-record-detail/v0.5", invalid
        )
        invalid = deepcopy(observation)
        invalid["detail"]["extractors"][0]["artifact_keys"].reverse()
        self.assert_public_validation_rejects(
            "tcw.workbench-record-detail/v0.5", invalid
        )
        invalid = deepcopy(observation)
        invalid["detail"]["extractors"][0]["error"] = {
            "code": "DOCLING_CONVERSION_FAILED",
            "message": "Unexpected error.",
        }
        self.assert_public_validation_rejects(
            "tcw.workbench-record-detail/v0.5", invalid
        )
        invalid = deepcopy(observation)
        invalid["detail"]["comparison"]["views"]["docling"]["anchors"] = [
            {"name": "zeta", "present": True},
            {"name": "alpha", "present": True},
        ]
        self.assert_public_validation_rejects(
            "tcw.workbench-record-detail/v0.5", invalid
        )
        invalid = deepcopy(refinement)
        invalid["relationships"].reverse()
        self.assert_public_validation_rejects(
            "tcw.workbench-record-detail/v0.5", invalid
        )

    def test_public_validation_composes_schema_and_semantics_for_artifacts(
        self,
    ) -> None:
        observation = json.loads(
            (API_FIXTURES / "detail-observation.json").read_text("utf-8")
        )
        projection = json.loads(
            (API_FIXTURES / "projection-contained-dedup.json").read_text(
                "utf-8"
            )
        )
        observation_record = next(
            item
            for item in projection["records"]
            if item["kind"] == "OBSERVATION"
            and item["identity"]["observation_id"]
            == next(
                edge["expected_target"]["identity_value"]
                for edge in projection["edges"]
                if edge["relation"] == "DIAGNOSIS_SUBJECT"
            )
        )
        comparison = observation["detail"]["comparison"]
        comparison_document = {
            "anchors": [{"name": "date", "value": "2026-07-26"}],
            "deltas": comparison["docling_minus_markitdown"],
            "normalization_algorithm": comparison[
                "normalization_algorithm"
            ],
            "observation_id": observation_record["identity"][
                "observation_id"
            ],
            "schema_version": "tcw.comparison-summary/v0.5",
            "source": {
                key: observation["detail"]["source"][key]
                for key in ("fixture_id", "media_type", "sha256")
            },
            "status": comparison["status"],
            "views": comparison["views"],
        }
        validate_document(
            "tcw.comparison-summary/v0.5", comparison_document
        )
        invalid = deepcopy(comparison_document)
        invalid["status"] = "INCOMPLETE"
        self.assert_public_validation_rejects(
            "tcw.comparison-summary/v0.5", invalid
        )

        diagnosis = json.loads(
            (API_FIXTURES / "detail-diagnosis.json").read_text("utf-8")
        )
        finding_set = {
            "diagnosis_id": next(
                item["identity"]["diagnosis_id"]
                for item in projection["records"]
                if item["kind"] == "DIAGNOSIS"
            ),
            "findings": diagnosis["detail"]["findings"],
            "ruleset": diagnosis["detail"]["ruleset"],
            "schema_version": "tcw.finding-set/v0.5",
            "subject": {
                "canonical_document_path": "docling/document.json",
                "canonical_document_sha256": diagnosis["detail"]["subject"][
                    "content_sha256"
                ],
                "canonical_document_size": 4096,
                "kind": "OBSERVATION",
                "origin_observation_id": observation_record["identity"][
                    "observation_id"
                ],
                "subject_id": observation_record["identity"][
                    "observation_id"
                ],
            },
            "summary": diagnosis["detail"]["summary"],
        }
        validate_document("tcw.finding-set/v0.5", finding_set)
        invalid = deepcopy(finding_set)
        invalid["summary"]["total"] += 1
        self.assert_public_validation_rejects(
            "tcw.finding-set/v0.5", invalid
        )

        corpus = json.loads(
            (API_FIXTURES / "detail-corpus.json").read_text("utf-8")
        )["detail"]
        corpus_summary = {
            **corpus["aggregates"],
            "corpus_id": corpus["corpus_id"],
            "members": [
                {
                    key: row[key]
                    for key in (
                        "member_id",
                        "family",
                        "format",
                        "status",
                        "error",
                    )
                }
                for row in corpus["matrix"]
            ],
            "run_id": "corpus-run-quality-matrix",
            "schema_version": "tcw.corpus-summary/v0.5",
            "snapshot_id": corpus["snapshot_id"],
            "status": corpus["summary"]["status"],
            "totals": corpus["summary"]["totals"],
        }
        validate_document("tcw.corpus-summary/v0.5", corpus_summary)
        invalid = deepcopy(corpus_summary)
        invalid["totals"]["revision_count"] += 1
        self.assert_public_validation_rejects(
            "tcw.corpus-summary/v0.5", invalid
        )
        invalid = deepcopy(corpus_summary)
        invalid["findings"][0]["affected_member_count"] = (
            invalid["findings"][0]["finding_count"] + 1
        )
        self.assert_public_validation_rejects(
            "tcw.corpus-summary/v0.5", invalid
        )
        invalid = deepcopy(corpus_summary)
        duplicate = deepcopy(invalid["findings"][0])
        invalid["findings"].append(duplicate)
        invalid["totals"]["finding_count"] += duplicate["finding_count"]
        self.assert_public_validation_rejects(
            "tcw.corpus-summary/v0.5", invalid
        )
        invalid = deepcopy(corpus_summary)
        duplicate = deepcopy(invalid["revision_groups"][0])
        invalid["revision_groups"].append(duplicate)
        second_revision = deepcopy(invalid["revisions"][0])
        second_revision["revision_id"] = "f" * 64
        invalid["revisions"].append(second_revision)
        invalid["revisions"].sort(
            key=lambda item: (
                item["member_id"],
                item["chain_length"],
                item["revision_id"],
            )
        )
        invalid["totals"]["revision_count"] = 2
        self.assert_public_validation_rejects(
            "tcw.corpus-summary/v0.5", invalid
        )
        invalid = deepcopy(corpus_summary)
        duplicate = deepcopy(invalid["revisions"][0])
        invalid["revisions"].append(duplicate)
        invalid["revision_groups"][0]["revision_count"] = 2
        invalid["totals"]["revision_count"] = 2
        self.assert_public_validation_rejects(
            "tcw.corpus-summary/v0.5", invalid
        )

    def test_reviewer_accepted_relationship_and_union_negatives(self) -> None:
        projection = json.loads(
            (API_FIXTURES / "projection-contained-dedup.json").read_text(
                "utf-8"
            )
        )
        partial_edge = next(
            edge
            for edge in projection["edges"]
            if edge["relation"] == "CORPUS_CONTAINS_OBSERVATION"
            and edge["expected_target"]["content_sha256"] is None
        )
        partial_target = next(
            record
            for record in projection["records"]
            if record["record_key"] == partial_edge["target_record_key"]
        )
        self.assertEqual(partial_target["status"], "PARTIAL_SUCCESS")
        validate_document("tcw.workbench-projection/v0.5", projection)
        invalid = deepcopy(projection)
        success_edge = next(
            edge
            for edge in invalid["edges"]
            if edge["relation"] == "CORPUS_CONTAINS_OBSERVATION"
            and edge["expected_target"]["content_sha256"] is not None
        )
        success_edge["expected_target"]["content_sha256"] = None
        success_edge["edge_key"] = edge_key(
            relation=success_edge["relation"],
            from_record_key=success_edge["from_record_key"],
            expected_target=success_edge["expected_target"],
        )
        invalid["edges"].sort(key=lambda item: item["edge_key"])
        invalid["session_id"] = session_id(
            top_level_record_keys=[
                item["record_key"]
                for item in invalid["records"]
                if item["admission_origin"] == "TOP_LEVEL"
            ],
            contained_record_keys=[
                item["record_key"]
                for item in invalid["records"]
                if item["admission_origin"] == "CORPUS_CONTAINED"
            ],
            edge_keys=[item["edge_key"] for item in invalid["edges"]],
        )
        self.assert_public_validation_rejects(
            "tcw.workbench-projection/v0.5", invalid
        )
        for hash_field in ("manifest_sha256", "content_sha256"):
            invalid = deepcopy(projection)
            edge = next(
                item
                for item in invalid["edges"]
                if item["relation"] == "DIAGNOSIS_SUBJECT"
            )
            edge["expected_target"][hash_field] = None
            edge["edge_key"] = edge_key(
                relation=edge["relation"],
                from_record_key=edge["from_record_key"],
                expected_target=edge["expected_target"],
            )
            invalid["edges"].sort(key=lambda item: item["edge_key"])
            invalid["session_id"] = session_id(
                top_level_record_keys=[
                    item["record_key"]
                    for item in invalid["records"]
                    if item["admission_origin"] == "TOP_LEVEL"
                ],
                contained_record_keys=[
                    item["record_key"]
                    for item in invalid["records"]
                    if item["admission_origin"] == "CORPUS_CONTAINED"
                ],
                edge_keys=[
                    item["edge_key"] for item in invalid["edges"]
                ],
            )
            with self.subTest(relation_hash=hash_field):
                self.assert_public_validation_rejects(
                    "tcw.workbench-projection/v0.5", invalid
                )

        invalid = deepcopy(projection)
        selected_edge = next(
            item
            for item in invalid["edges"]
            if item["relation"] == "DIAGNOSIS_SUBJECT"
        )
        source_record = next(
            item
            for item in invalid["records"]
            if item["record_key"] == selected_edge["from_record_key"]
        )
        source_record["contained_by"] = []
        invalid["records"] = [source_record]
        invalid["edges"] = [selected_edge]
        invalid["counts"] = {
            "contained_record_count": 0,
            "record_count": 1,
            "top_level_record_count": 1,
        }
        invalid["session_id"] = session_id(
            top_level_record_keys=[source_record["record_key"]],
            contained_record_keys=[],
            edge_keys=[selected_edge["edge_key"]],
        )
        self.assert_public_validation_rejects(
            "tcw.workbench-projection/v0.5", invalid
        )

        invalid = json.loads(
            (API_FIXTURES / "projection-missing-edge.json").read_text(
                "utf-8"
            )
        )
        missing_edge = invalid["edges"][0]
        candidate = deepcopy(
            next(
                item
                for item in projection["records"]
                if item["kind"] == "REFINEMENT"
                and item["status"] == "APPLIED"
            )
        )
        candidate["identity"]["revision_id"] = missing_edge[
            "expected_target"
        ]["identity_value"]
        candidate["run_id"] = missing_edge["expected_target"]["run_id"]
        candidate["manifest"]["sha256"] = missing_edge[
            "expected_target"
        ]["manifest_sha256"]
        candidate["record_key"] = record_key(
            kind=candidate["kind"],
            record_schema_version=candidate["record_schema_version"],
            identity=candidate["identity"],
            run_id=candidate["run_id"],
            manifest_sha256=candidate["manifest"]["sha256"],
        )
        candidate["manifest"]["record_key"] = candidate["record_key"]
        candidate["manifest"]["artifact_key"] = artifact_key(
            record_key=candidate["record_key"],
            role=candidate["manifest"]["role"],
            relative_path=candidate["manifest"]["relative_path"],
            sha256=candidate["manifest"]["sha256"],
        )
        candidate["contained_by"] = []
        invalid["records"].append(candidate)
        invalid["records"].sort(key=lambda item: item["record_key"])
        invalid["counts"] = {
            "contained_record_count": 0,
            "record_count": 2,
            "top_level_record_count": 2,
        }
        invalid["session_id"] = session_id(
            top_level_record_keys=[
                item["record_key"] for item in invalid["records"]
            ],
            contained_record_keys=[],
            edge_keys=[missing_edge["edge_key"]],
        )
        self.assert_public_validation_rejects(
            "tcw.workbench-projection/v0.5", invalid
        )

        invalid = deepcopy(projection)
        contained = next(
            item
            for item in invalid["records"]
            if item["admission_origin"] == "CORPUS_CONTAINED"
        )
        contained["contained_by"] = []
        self.assert_public_validation_rejects(
            "tcw.workbench-projection/v0.5", invalid
        )
        invalid = deepcopy(projection)
        contained = next(
            item
            for item in invalid["records"]
            if item["admission_origin"] == "CORPUS_CONTAINED"
        )
        contained["contained_by"] = ["0" * 64]
        self.assert_public_validation_rejects(
            "tcw.workbench-projection/v0.5", invalid
        )
        for status, revision_id in (
            ("APPLIED", None),
            ("REJECTED", "1" * 64),
        ):
            invalid = deepcopy(projection)
            refinement_record = next(
                item
                for item in invalid["records"]
                if item["kind"] == "REFINEMENT"
                and item["status"] == status
            )
            refinement_record["identity"]["revision_id"] = revision_id
            with self.subTest(refinement_status=status):
                self.assert_public_validation_rejects(
                    "tcw.workbench-projection/v0.5", invalid
                )

        invalid = json.loads(
            (API_FIXTURES / "projection-observation.json").read_text(
                "utf-8"
            )
        )
        record = invalid["records"][0]
        record["manifest"]["origin"] = "MANIFEST_LISTED"
        record["manifest"]["role"] = "comparison-summary"
        record["manifest"]["relative_path"] = "comparison-summary.json"
        record["manifest"]["artifact_key"] = artifact_key(
            record_key=record["record_key"],
            role=record["manifest"]["role"],
            relative_path=record["manifest"]["relative_path"],
            sha256=record["manifest"]["sha256"],
        )
        self.assert_public_validation_rejects(
            "tcw.workbench-projection/v0.5", invalid
        )

        observation = json.loads(
            (API_FIXTURES / "detail-observation.json").read_text("utf-8")
        )
        same_role = deepcopy(observation)
        first, second = same_role["artifacts"][:2]
        old_key = second["artifact_key"]
        second["role"] = first["role"]
        second["artifact_key"] = artifact_key(
            record_key=second["record_key"],
            role=second["role"],
            relative_path=second["relative_path"],
            sha256=second["sha256"],
        )
        for extractor in same_role["detail"]["extractors"]:
            extractor["artifact_keys"] = sorted(
                second["artifact_key"] if key == old_key else key
                for key in extractor["artifact_keys"]
            )
        same_role["artifacts"].sort(key=lambda item: item["artifact_key"])
        validate_document("tcw.workbench-record-detail/v0.5", same_role)

        invalid = deepcopy(observation)
        invalid["artifacts"][1] = deepcopy(invalid["artifacts"][0])
        invalid["artifacts"].sort(key=lambda item: item["artifact_key"])
        self.assert_public_validation_rejects(
            "tcw.workbench-record-detail/v0.5", invalid
        )
        for duplicate_pair in (True, False):
            invalid = deepcopy(observation)
            first, second = invalid["artifacts"][:2]
            second["relative_path"] = first["relative_path"]
            if duplicate_pair:
                second["role"] = first["role"]
            second["artifact_key"] = artifact_key(
                record_key=second["record_key"],
                role=second["role"],
                relative_path=second["relative_path"],
                sha256=second["sha256"],
            )
            invalid["artifacts"].sort(key=lambda item: item["artifact_key"])
            with self.subTest(duplicate_pair=duplicate_pair):
                self.assert_public_validation_rejects(
                    "tcw.workbench-record-detail/v0.5", invalid
                )

        for availability, size in (
            ("AVAILABLE", 16 * 1024 * 1024 + 1),
            ("TOO_LARGE", 16 * 1024 * 1024),
        ):
            invalid = deepcopy(observation)
            invalid["artifacts"][0]["availability"] = availability
            invalid["artifacts"][0]["size"] = size
            with self.subTest(availability=availability, size=size):
                self.assert_public_validation_rejects(
                    "tcw.workbench-record-detail/v0.5", invalid
                )

        diagnosis = json.loads(
            (API_FIXTURES / "detail-diagnosis.json").read_text("utf-8")
        )
        invalid = deepcopy(diagnosis)
        invalid["detail"]["ruleset"]["parameter_sha256"] = "0" * 64
        self.assert_public_validation_rejects(
            "tcw.workbench-record-detail/v0.5", invalid
        )
        invalid = deepcopy(diagnosis)
        invalid["detail"]["subject_state"] = "NOT_CHECKED"
        self.assert_public_validation_rejects(
            "tcw.workbench-record-detail/v0.5", invalid
        )
        invalid = deepcopy(diagnosis)
        subject_edge = invalid["relationships"][0]
        subject_edge["state"] = "MISSING"
        subject_edge["target_record_key"] = None
        invalid["detail"]["subject_state"] = "NOT_CHECKED"
        self.assert_public_validation_rejects(
            "tcw.workbench-record-detail/v0.5", invalid
        )
        invalid["detail"]["derivation_state"] = "NOT_CHECKED"
        validate_document("tcw.workbench-record-detail/v0.5", invalid)

        refinement = json.loads(
            (API_FIXTURES / "detail-refinement-applied.json").read_text(
                "utf-8"
            )
        )
        for field in ("diagnosis_state", "base_state"):
            invalid = deepcopy(refinement)
            invalid["detail"][field] = "NOT_CHECKED"
            with self.subTest(refinement_state=field):
                self.assert_public_validation_rejects(
                    "tcw.workbench-record-detail/v0.5", invalid
                )
        invalid = deepcopy(refinement)
        base_edge = next(
            edge
            for edge in invalid["relationships"]
            if edge["relation"] == "REFINEMENT_BASE"
        )
        base_edge["state"] = "MISSING"
        base_edge["target_record_key"] = None
        invalid["detail"]["base_state"] = "NOT_CHECKED"
        self.assert_public_validation_rejects(
            "tcw.workbench-record-detail/v0.5", invalid
        )
        invalid["detail"]["derivation_state"] = "NOT_CHECKED"
        invalid["detail"]["reversibility_state"] = "NOT_CHECKED"
        validate_document("tcw.workbench-record-detail/v0.5", invalid)
        invalid = deepcopy(refinement)
        invalid["detail"]["derivation_state"] = "NOT_CHECKED"
        self.assert_public_validation_rejects(
            "tcw.workbench-record-detail/v0.5", invalid
        )
        invalid = deepcopy(refinement)
        invalid["detail"]["reversibility_state"] = "NOT_CHECKED"
        self.assert_public_validation_rejects(
            "tcw.workbench-record-detail/v0.5", invalid
        )
        invalid = deepcopy(refinement)
        diagnosis_edge = next(
            edge
            for edge in invalid["relationships"]
            if edge["relation"] == "REFINEMENT_DIAGNOSIS"
        )
        diagnosis_edge["state"] = "MISSING"
        diagnosis_edge["target_record_key"] = None
        invalid["detail"]["diagnosis_state"] = "NOT_CHECKED"
        invalid["detail"]["derivation_state"] = "NOT_CHECKED"
        self.assert_public_validation_rejects(
            "tcw.workbench-record-detail/v0.5", invalid
        )
        invalid = deepcopy(refinement)
        invalid["detail"]["decision"]["state"] = "REJECTED"
        self.assert_public_validation_rejects(
            "tcw.workbench-record-detail/v0.5", invalid
        )
        invalid = deepcopy(refinement)
        refinement_target = next(
            edge["expected_target"]
            for edge in json.loads(
                (API_FIXTURES / "detail-corpus.json").read_text("utf-8")
            )["relationships"]
            if edge["relation"] == "CORPUS_EXTERNAL_REFINEMENT"
        )
        invalid["detail"]["base_target"] = refinement_target
        base_edge = next(
            edge
            for edge in invalid["relationships"]
            if edge["relation"] == "REFINEMENT_BASE"
        )
        base_edge["expected_target"] = refinement_target
        base_edge["edge_key"] = edge_key(
            relation=base_edge["relation"],
            from_record_key=base_edge["from_record_key"],
            expected_target=base_edge["expected_target"],
        )
        invalid["relationships"].sort(key=lambda item: item["edge_key"])
        self.assert_public_validation_rejects(
            "tcw.workbench-record-detail/v0.5", invalid
        )

        corpus = json.loads(
            (API_FIXTURES / "detail-corpus.json").read_text("utf-8")
        )
        validate_document("tcw.workbench-record-detail/v0.5", corpus)
        invalid = deepcopy(corpus)
        success_edge = next(
            edge
            for edge in invalid["relationships"]
            if edge["relation"] == "CORPUS_CONTAINS_OBSERVATION"
            and edge["expected_target"]["content_sha256"] is not None
        )
        success_edge["expected_target"]["content_sha256"] = None
        success_edge["edge_key"] = edge_key(
            relation=success_edge["relation"],
            from_record_key=success_edge["from_record_key"],
            expected_target=success_edge["expected_target"],
        )
        invalid["relationships"].sort(key=lambda item: item["edge_key"])
        self.assert_public_validation_rejects(
            "tcw.workbench-record-detail/v0.5", invalid
        )
        invalid = deepcopy(corpus)
        group = invalid["detail"]["aggregates"]["findings"][0]
        group["finding_count"] = 1
        group["affected_member_count"] = 2
        invalid["detail"]["summary"]["totals"]["finding_count"] = 1
        self.assert_public_validation_rejects(
            "tcw.workbench-record-detail/v0.5", invalid
        )
        invalid = deepcopy(corpus)
        invalid["relationships"] = [
            edge
            for edge in invalid["relationships"]
            if not (
                edge["relation"] == "CORPUS_CONTAINS_OBSERVATION"
                and edge["target_record_key"]
                == invalid["detail"]["matrix"][0][
                    "observation_record_key"
                ]
            )
        ]
        self.assert_public_validation_rejects(
            "tcw.workbench-record-detail/v0.5", invalid
        )
        invalid = deepcopy(corpus)
        extra_target = {
            "content_sha256": "1" * 64,
            "identity_type": "observation_id",
            "identity_value": "2" * 64,
            "kind": "OBSERVATION",
            "manifest_sha256": "3" * 64,
            "record_schema_version": "tcw.preparation-manifest/v0.5",
            "run_id": "extra-observation",
        }
        extra_edge = {
            "edge_key": edge_key(
                relation="CORPUS_CONTAINS_OBSERVATION",
                from_record_key=invalid["record_key"],
                expected_target=extra_target,
            ),
            "expected_target": extra_target,
            "from_record_key": invalid["record_key"],
            "relation": "CORPUS_CONTAINS_OBSERVATION",
            "state": "MATCH",
            "target_record_key": "4" * 64,
        }
        invalid["relationships"].append(extra_edge)
        invalid["relationships"].sort(key=lambda item: item["edge_key"])
        self.assert_public_validation_rejects(
            "tcw.workbench-record-detail/v0.5", invalid
        )

    def test_acceptance_root_manifests_edge_sources_and_refinement_subject(
        self,
    ) -> None:
        bindings = {
            "OBSERVATION": ("preparation-manifest", "manifest.json"),
            "DIAGNOSIS": (
                "diagnosis-manifest",
                "diagnosis-manifest.json",
            ),
            "REFINEMENT": (
                "refinement-manifest",
                "refinement-manifest.json",
            ),
            "CORPUS": ("corpus-manifest", "corpus-manifest.json"),
        }
        projection = json.loads(
            (API_FIXTURES / "projection-contained-dedup.json").read_text(
                "utf-8"
            )
        )

        def refresh_projection(document: dict) -> None:
            document["edges"].sort(key=lambda item: item["edge_key"])
            document["session_id"] = session_id(
                top_level_record_keys=[
                    item["record_key"]
                    for item in document["records"]
                    if item["admission_origin"] == "TOP_LEVEL"
                ],
                contained_record_keys=[
                    item["record_key"]
                    for item in document["records"]
                    if item["admission_origin"] == "CORPUS_CONTAINED"
                ],
                edge_keys=[item["edge_key"] for item in document["edges"]],
            )

        for record in projection["records"]:
            wrong_kind = next(kind for kind in bindings if kind != record["kind"])
            wrong_role, wrong_path = bindings[wrong_kind]
            for field, value in (
                ("role", wrong_role),
                ("relative_path", wrong_path),
            ):
                invalid = deepcopy(projection)
                changed = next(
                    item
                    for item in invalid["records"]
                    if item["record_key"] == record["record_key"]
                )
                changed["manifest"][field] = value
                changed["manifest"]["artifact_key"] = artifact_key(
                    record_key=changed["record_key"],
                    role=changed["manifest"]["role"],
                    relative_path=changed["manifest"]["relative_path"],
                    sha256=changed["manifest"]["sha256"],
                )
                with self.subTest(
                    projection_manifest=record["kind"], field=field
                ):
                    self.assert_public_validation_rejects(
                        "tcw.workbench-projection/v0.5", invalid
                    )

        detail_files = {
            "OBSERVATION": "detail-observation.json",
            "DIAGNOSIS": "detail-diagnosis.json",
            "REFINEMENT": "detail-refinement-applied.json",
            "CORPUS": "detail-corpus.json",
        }
        for kind, filename in detail_files.items():
            wrong_kind = next(item for item in bindings if item != kind)
            wrong_role, wrong_path = bindings[wrong_kind]
            for field, value in (
                ("role", wrong_role),
                ("relative_path", wrong_path),
            ):
                invalid = json.loads(
                    (API_FIXTURES / filename).read_text("utf-8")
                )
                invalid["manifest"][field] = value
                invalid["manifest"]["artifact_key"] = artifact_key(
                    record_key=invalid["record_key"],
                    role=invalid["manifest"]["role"],
                    relative_path=invalid["manifest"]["relative_path"],
                    sha256=invalid["manifest"]["sha256"],
                )
                with self.subTest(detail_manifest=kind, field=field):
                    self.assert_public_validation_rejects(
                        "tcw.workbench-record-detail/v0.5", invalid
                    )

        source_kinds = {
            "DIAGNOSIS_SUBJECT": "DIAGNOSIS",
            "REFINEMENT_DIAGNOSIS": "REFINEMENT",
            "REFINEMENT_BASE": "REFINEMENT",
            "REFINEMENT_PARENT": "REFINEMENT",
            "CORPUS_CONTAINS_OBSERVATION": "CORPUS",
            "CORPUS_CONTAINS_DIAGNOSIS": "CORPUS",
            "CORPUS_EXTERNAL_REFINEMENT": "CORPUS",
        }
        applied_record = next(
            record
            for record in projection["records"]
            if record["kind"] == "REFINEMENT"
            and record["status"] == "APPLIED"
        )
        applied_target = deepcopy(
            next(
                edge["expected_target"]
                for edge in projection["edges"]
                if edge["relation"] == "CORPUS_EXTERNAL_REFINEMENT"
            )
        )
        parent_edge = {
            "edge_key": edge_key(
                relation="REFINEMENT_PARENT",
                from_record_key=applied_record["record_key"],
                expected_target=applied_target,
            ),
            "expected_target": applied_target,
            "from_record_key": applied_record["record_key"],
            "relation": "REFINEMENT_PARENT",
            "state": "MATCH",
            "target_record_key": applied_record["record_key"],
        }
        for original_edge in [*projection["edges"], parent_edge]:
            for source_case in ("absent", "wrong-kind"):
                invalid = deepcopy(projection)
                matches = [
                    edge
                    for edge in invalid["edges"]
                    if edge["edge_key"] == original_edge["edge_key"]
                ]
                if matches:
                    changed = matches[0]
                else:
                    changed = deepcopy(original_edge)
                    invalid["edges"].append(changed)
                if source_case == "absent":
                    changed["from_record_key"] = "0" * 64
                else:
                    changed["from_record_key"] = next(
                        record["record_key"]
                        for record in invalid["records"]
                        if record["kind"]
                        != source_kinds[changed["relation"]]
                    )
                changed["edge_key"] = edge_key(
                    relation=changed["relation"],
                    from_record_key=changed["from_record_key"],
                    expected_target=changed["expected_target"],
                )
                refresh_projection(invalid)
                with self.subTest(
                    relation=original_edge["relation"],
                    source_case=source_case,
                ):
                    self.assert_public_validation_rejects(
                        "tcw.workbench-projection/v0.5", invalid
                    )

        refinement_subject = json.loads(
            (
                API_FIXTURES
                / "detail-diagnosis-refinement-subject.json"
            ).read_text("utf-8")
        )
        self.assertEqual(
            (
                refinement_subject["detail"]["subject"]["kind"],
                refinement_subject["detail"]["subject"]["identity_type"],
            ),
            ("REFINEMENT", "revision_id"),
        )
        validate_document(
            "tcw.workbench-record-detail/v0.5", refinement_subject
        )
        for filename, wrong_identity_type in (
            ("detail-diagnosis.json", "revision_id"),
            (
                "detail-diagnosis-refinement-subject.json",
                "observation_id",
            ),
        ):
            invalid = json.loads(
                (API_FIXTURES / filename).read_text("utf-8")
            )
            invalid["detail"]["subject"]["identity_type"] = (
                wrong_identity_type
            )
            subject_edge = invalid["relationships"][0]
            subject_edge["expected_target"] = deepcopy(
                invalid["detail"]["subject"]
            )
            subject_edge["edge_key"] = edge_key(
                relation=subject_edge["relation"],
                from_record_key=subject_edge["from_record_key"],
                expected_target=subject_edge["expected_target"],
            )
            with self.subTest(
                filename=filename, identity_type=wrong_identity_type
            ):
                self.assert_public_validation_rejects(
                    "tcw.workbench-record-detail/v0.5", invalid
                )

    def test_wrong_provenance_pointers_and_prohibited_placement_are_rejected(self) -> None:
        startup = json.loads(
            (API_FIXTURES / "startup.json").read_text("utf-8")
        )
        startup["build_provenance"] = self.build_shape(
            "BUILD_COMMAND", "tcw.workbench"
        )
        with self.assertRaises(ValidationError):
            validator("tcw.workbench-startup/v0.5").validate(startup)

        example = json.loads(PROVENANCE_EXAMPLES.read_text("utf-8"))[
            "examples"
        ][1]
        provenance = example["build_provenance"]
        schema = load_schema("tcw.preparation-manifest/v0.5")
        wrong_pointer = deepcopy(provenance)
        wrapper = {"runtime": {"provenance": wrong_pointer}}
        self.assertNotIn("runtime", schema["properties"])
        self.assertNotIn("provenance", schema["properties"])
        with self.assertRaises(ValidationError):
            validator("tcw.preparation-manifest/v0.5").validate(wrapper)

    def test_rule_specific_finding_discriminators_are_exact(self) -> None:
        detail = json.loads(
            (API_FIXTURES / "detail-diagnosis.json").read_text("utf-8")
        )
        finding_schema = load_schema("tcw.finding-set/v0.5")["$defs"][
            "finding"
        ]
        finding_validator = validator("tcw.finding-set/v0.5").evolve(
            schema=finding_schema
        )
        self.assertEqual(len(detail["detail"]["findings"]), 11)
        for finding in detail["detail"]["findings"]:
            finding_validator.validate(finding)
            invalid = deepcopy(finding)
            invalid["severity"] = (
                "ERROR" if finding["severity"] != "ERROR" else "INFO"
            )
            with self.assertRaises(ValidationError):
                finding_validator.validate(invalid)
        self.assertEqual(
            sum(
                finding["rule_id"] == "TCW-D006"
                for finding in detail["detail"]["findings"]
            ),
            2,
        )

    def test_corpus_stage_status_tuples_are_closed(self) -> None:
        schema = load_schema("tcw.corpus-manifest/v0.5")
        observation_validator = validator(
            "tcw.corpus-manifest/v0.5"
        ).evolve(schema=schema["$defs"]["observation"])
        diagnosis_validator = validator(
            "tcw.corpus-manifest/v0.5"
        ).evolve(schema=schema["$defs"]["diagnosis"])
        descriptor = {"path": "member/manifest.json", "size": 1, "sha256": "a" * 64}
        observation_validator.validate(
            {
                "status": "SUCCESS",
                "observation_id": "b" * 64,
                "run_id": "run",
                "manifest": descriptor,
                "canonical_document_sha256": "c" * 64,
            }
        )
        diagnosis_validator.validate(
            {
                "status": "FAILED",
                "diagnosis_id": None,
                "run_id": None,
                "manifest": None,
                "findings_sha256": None,
            }
        )
        with self.assertRaises(ValidationError):
            observation_validator.validate(
                {
                    "status": "NOT_RUN",
                    "observation_id": "b" * 64,
                    "run_id": None,
                    "manifest": None,
                    "canonical_document_sha256": None,
                }
            )
        with self.assertRaises(ValidationError):
            diagnosis_validator.validate(
                {
                    "status": "FINDINGS",
                    "diagnosis_id": "b" * 64,
                    "run_id": "run",
                    "manifest": descriptor,
                    "findings_sha256": None,
                }
            )

    def test_canonical_examples_use_frozen_semantic_ordering(self) -> None:
        projection = json.loads(
            (API_FIXTURES / "projection-contained-dedup.json").read_text("utf-8")
        )
        self.assertEqual(
            [item["record_key"] for item in projection["records"]],
            sorted(item["record_key"] for item in projection["records"]),
        )
        diagnosis = json.loads(
            (API_FIXTURES / "detail-diagnosis.json").read_text("utf-8")
        )
        self.assertEqual(
            [item["rule_id"] for item in diagnosis["detail"]["ruleset"]["rules"]],
            [f"TCW-D{number:03d}" for number in range(1, 11)],
        )
        self.assertEqual(
            [item["finding_id"] for item in diagnosis["detail"]["findings"]],
            sorted(item["finding_id"] for item in diagnosis["detail"]["findings"]),
        )

    def test_api_examples_satisfy_cross_field_count_invariants(self) -> None:
        startup = json.loads(
            (API_FIXTURES / "startup.json").read_text("utf-8")
        )
        self.assertEqual(
            startup["record_count"],
            startup["top_level_record_count"]
            + startup["contained_record_count"],
        )

        for path in API_FIXTURES.glob("projection-*.json"):
            projection = json.loads(path.read_text("utf-8"))
            counts = projection["counts"]
            self.assertEqual(counts["record_count"], len(projection["records"]))
            self.assertEqual(
                counts["record_count"],
                counts["top_level_record_count"]
                + counts["contained_record_count"],
            )
            self.assertEqual(
                counts["top_level_record_count"],
                sum(
                    record["admission_origin"] == "TOP_LEVEL"
                    for record in projection["records"]
                ),
            )
            self.assertEqual(
                counts["contained_record_count"],
                sum(
                    record["admission_origin"] == "CORPUS_CONTAINED"
                    for record in projection["records"]
                ),
            )

        corpus = json.loads(
            (API_FIXTURES / "detail-corpus.json").read_text("utf-8")
        )["detail"]
        totals = corpus["summary"]["totals"]
        self.assertEqual(totals["member_count"], len(corpus["matrix"]))
        self.assertEqual(
            totals["member_count"],
            totals["complete"] + totals["partial"] + totals["failed"],
        )
        for group in (
            corpus["aggregates"]["by_family"],
            corpus["aggregates"]["by_format"],
        ):
            for counts in group:
                self.assertEqual(
                    counts["member_count"],
                    counts["complete"] + counts["partial"] + counts["failed"],
                )
        for counts in corpus["aggregates"]["extractors"]:
            self.assertEqual(
                totals["member_count"],
                counts["available"] + counts["unavailable"],
            )

    def test_api_examples_cover_frozen_availability_and_comparison_branches(
        self,
    ) -> None:
        observation = json.loads(
            (API_FIXTURES / "detail-observation.json").read_text("utf-8")
        )
        self.assertGreater(len(observation["artifacts"]), 0)
        self.assertEqual(
            {item["origin"] for item in observation["artifacts"]},
            {"MANIFEST_LISTED"},
        )
        self.assertEqual(
            {item["availability"] for item in observation["artifacts"]},
            {"AVAILABLE", "TOO_LARGE"},
        )
        self.assertEqual(
            observation["detail"]["comparison"]["status"], "COMPLETE"
        )

        corpus = json.loads(
            (API_FIXTURES / "detail-corpus.json").read_text("utf-8")
        )
        comparisons = corpus["detail"]["aggregates"]["comparisons"]
        self.assertEqual(
            [item["status"] for item in comparisons],
            ["COMPLETE", "INCOMPLETE", "NOT_AVAILABLE"],
        )
        self.assertEqual(
            [item["member_id"] for item in comparisons],
            sorted(item["member_id"] for item in comparisons),
        )

    def test_api_runtime_display_requires_only_its_two_fields(self) -> None:
        for filename in ("startup.json", "projection-observation.json"):
            original = json.loads((API_FIXTURES / filename).read_text("utf-8"))
            runtime = original["runtime"]
            self.assertEqual(
                set(runtime), {"package_version", "provenance_id"}
            )
            schema_version = original["schema_version"]
            for field in tuple(runtime):
                invalid = deepcopy(original)
                del invalid["runtime"][field]
                with self.subTest(filename=filename, missing=field), self.assertRaises(
                    ValidationError
                ):
                    validator(schema_version).validate(invalid)

    def test_projection_example_keys_match_exact_identity_preimages(self) -> None:
        projections = [
            json.loads(path.read_text("utf-8"))
            for path in API_FIXTURES.glob("projection-*.json")
        ]
        for projection in projections:
            for item in projection["records"]:
                expected_record_key = record_key(
                    kind=item["kind"],
                    record_schema_version=item["record_schema_version"],
                    identity=item["identity"],
                    run_id=item["run_id"],
                    manifest_sha256=item["manifest"]["sha256"],
                )
                self.assertEqual(item["record_key"], expected_record_key)
                self.assertEqual(
                    item["manifest"]["artifact_key"],
                    artifact_key(
                        record_key=item["record_key"],
                        role=item["manifest"]["role"],
                        relative_path=item["manifest"]["relative_path"],
                        sha256=item["manifest"]["sha256"],
                    ),
                )
            for item in projection["edges"]:
                self.assertEqual(
                    item["edge_key"],
                    edge_key(
                        relation=item["relation"],
                        from_record_key=item["from_record_key"],
                        expected_target=item["expected_target"],
                    ),
                )
            self.assertEqual(
                projection["session_id"],
                session_id(
                    top_level_record_keys=sorted(
                        item["record_key"]
                        for item in projection["records"]
                        if item["admission_origin"] == "TOP_LEVEL"
                    ),
                    contained_record_keys=sorted(
                        item["record_key"]
                        for item in projection["records"]
                        if item["admission_origin"] == "CORPUS_CONTAINED"
                    ),
                    edge_keys=sorted(
                        item["edge_key"] for item in projection["edges"]
                    ),
                ),
            )

        full_projection = next(
            item for item in projections if len(item["records"]) > 1
        )
        records = {
            item["record_key"]: item for item in full_projection["records"]
        }
        detail_paths = (
            "detail-observation.json",
            "detail-diagnosis.json",
            "detail-refinement-applied.json",
            "detail-refinement-rejected.json",
            "detail-corpus.json",
        )
        for filename in detail_paths:
            detail = json.loads((API_FIXTURES / filename).read_text("utf-8"))
            record = records[detail["record_key"]]
            with self.subTest(filename=filename):
                self.assertEqual(detail["kind"], record["kind"])
                self.assertEqual(detail["manifest"], record["manifest"])
                self.assertEqual(
                    record["artifact_count"], len(detail["artifacts"]) + 1
                )
                self.assertNotIn(
                    detail["manifest"]["artifact_key"],
                    {
                        artifact["artifact_key"]
                        for artifact in detail["artifacts"]
                    },
                )
                for artifact in detail["artifacts"]:
                    self.assertEqual(
                        artifact["artifact_key"],
                        artifact_key(
                            record_key=detail["record_key"],
                            role=artifact["role"],
                            relative_path=artifact["relative_path"],
                            sha256=artifact["sha256"],
                        ),
                    )
                self.assertEqual(
                    detail["relationships"],
                    [
                        edge
                        for edge in full_projection["edges"]
                        if edge["from_record_key"] == detail["record_key"]
                    ],
                )

        applied = json.loads(
            (API_FIXTURES / "detail-refinement-applied.json").read_text(
                "utf-8"
            )
        )
        applied_record = records[applied["record_key"]]
        self.assertEqual(
            applied_record["identity"]["draft_id"],
            applied["detail"]["decision"]["draft_id"],
        )
        self.assertEqual(
            applied_record["identity"]["revision_id"],
            applied["detail"]["revision_chain"][-1]["revision_id"],
        )
        self.assertIsNone(applied["detail"]["parent_target"])

        rejected = json.loads(
            (API_FIXTURES / "detail-refinement-rejected.json").read_text(
                "utf-8"
            )
        )
        rejected_record = records[rejected["record_key"]]
        self.assertEqual(
            rejected_record["identity"]["draft_id"],
            rejected["detail"]["decision"]["draft_id"],
        )
        self.assertIsNone(rejected_record["identity"]["revision_id"])
        self.assertNotEqual(
            applied_record["identity"]["draft_id"],
            rejected_record["identity"]["draft_id"],
        )
        primary_identities = []
        for record in full_projection["records"]:
            identity = record["identity"]
            primary_identities.append(
                identity.get(
                    {
                        "OBSERVATION": "observation_id",
                        "DIAGNOSIS": "diagnosis_id",
                        "REFINEMENT": "draft_id",
                        "CORPUS": "snapshot_id",
                    }[record["kind"]]
                )
            )
            if identity.get("revision_id") is not None:
                primary_identities.append(identity["revision_id"])
        self.assertEqual(
            len(primary_identities), len(set(primary_identities))
        )
        self.assertTrue(
            all(len(set(identity)) > 1 for identity in primary_identities)
        )

    def test_inventory_paths_symbols_and_migration_source_pointers_exist(self) -> None:
        inventory_raw = INVENTORY.read_bytes()
        inventory = json.loads(inventory_raw)
        self.assertEqual(inventory_raw, canonical_json(inventory) + b"\n")
        approved_base = inventory["approved_base"]
        self.assertEqual(
            approved_base,
            "6545636f1ded597a0850ef35705ef0137ac8ea38",
        )

        def base_json(path: str) -> dict:
            return json.loads(
                subprocess.run(
                    ["git", "show", f"{approved_base}:{path}"],
                    check=True,
                    capture_output=True,
                    text=True,
                ).stdout
            )
        for group in ("writers", "verifiers", "identity_inputs"):
            for item in inventory[group]:
                path = Path(item["path"])
                with self.subTest(group=group, path=path):
                    self.assertTrue(path.is_file())
                    self.assertIn("classification", item)
                    if item.get("family") != "workbench":
                        subprocess.run(
                            [
                                "git",
                                "cat-file",
                                "-e",
                                f"{approved_base}:{path}",
                            ],
                            check=True,
                            capture_output=True,
                        )
                    if symbol := item.get("symbol"):
                        if item.get("family") == "workbench":
                            source = path.read_text("utf-8")
                        else:
                            source = subprocess.run(
                                [
                                    "git",
                                    "show",
                                    f"{approved_base}:{path}",
                                ],
                                check=True,
                                capture_output=True,
                                text=True,
                            ).stdout
                        for name in symbol.split(","):
                            self.assertIn(name, source)
        expected_provenance = {
            "observation": "BUILD_EXTRACTING_COMMAND:tcw.observe",
            "comparison-summary": "prohibited",
            "diagnosis": "BUILD_COMMAND:tcw.diagnose",
            "refinement-draft": "BUILD_COMMAND:tcw.draft-refinement",
            "refinement": "BUILD_COMMAND:tcw.resolve-refinement",
            "transformation": "prohibited",
            "transformation-history": "prohibited",
            "corpus": "BUILD_EXTRACTING_COMMAND:tcw.inspect-corpus",
            "corpus-summary": "prohibited",
            "base-fixtures": "BUILD_GENERATOR:tools.generate_fixtures",
            "diagnosis-fixtures": (
                "BUILD_GENERATOR:tools.generate_diagnosis_fixtures"
            ),
            "refinement-fixtures": (
                "BUILD_GENERATOR:tools.generate_refinement_fixtures"
            ),
            "observation-verification-result": "BUILD_COMMAND:tcw.verify",
            "diagnosis-verification-result": (
                "BUILD_COMMAND:tcw.verify-diagnosis"
            ),
            "refinement-verification-result": (
                "BUILD_COMMAND:tcw.verify-refinement"
            ),
            "corpus-verification-result": (
                "BUILD_COMMAND:tcw.verify-corpus"
            ),
            "normalized-corpus-specification": "prohibited",
        }
        by_artifact = {
            item["artifact"]: item["provenance_requirement"]
            for item in inventory["writers"]
            if item["classification"] == "current-writer"
        }
        self.assertEqual(by_artifact, expected_provenance)
        self.assertEqual(
            {
                (
                    item["artifact"],
                    item["path"],
                    item.get("symbol"),
                    item["classification"],
                )
                for item in inventory["writers"]
            },
            {
                (
                    artifact,
                    path,
                    symbol,
                    classification,
                )
                for artifact, path, symbol, classification in (
                    (
                        "observation",
                        "src/tiny_corpus_workbench/cli.py",
                        "observe",
                        "current-writer",
                    ),
                    (
                        "comparison-summary",
                        "src/tiny_corpus_workbench/comparison.py",
                        "make_comparison",
                        "current-writer",
                    ),
                    (
                        "diagnosis",
                        "src/tiny_corpus_workbench/v03.py",
                        "diagnose",
                        "current-writer",
                    ),
                    (
                        "refinement-draft",
                        "src/tiny_corpus_workbench/v03.py",
                        "draft_refinement",
                        "current-writer",
                    ),
                    (
                        "refinement",
                        "src/tiny_corpus_workbench/v03.py",
                        "resolve_refinement",
                        "current-writer",
                    ),
                    (
                        "transformation",
                        "src/tiny_corpus_workbench/v03.py",
                        "resolve_refinement",
                        "current-writer",
                    ),
                    (
                        "transformation-history",
                        "src/tiny_corpus_workbench/v03.py",
                        "resolve_refinement",
                        "current-writer",
                    ),
                    (
                        "corpus",
                        "src/tiny_corpus_workbench/corpus_publication.py",
                        "inspect_corpus",
                        "current-writer",
                    ),
                    (
                        "corpus-summary",
                        "src/tiny_corpus_workbench/corpus_execution.py",
                        "execute_corpus",
                        "current-writer",
                    ),
                    (
                        "base-fixtures",
                        "tools/generate_fixtures.py",
                        "main",
                        "current-writer",
                    ),
                    (
                        "diagnosis-fixtures",
                        "tools/generate_diagnosis_fixtures.py",
                        "main",
                        "current-writer",
                    ),
                    (
                        "refinement-fixtures",
                        "tools/generate_refinement_fixtures.py",
                        "main",
                        "current-writer",
                    ),
                    (
                        "legacy-diagnosis-private-staging",
                        "src/tiny_corpus_workbench/diagnosis.py",
                        "diagnose",
                        "private-migration-staging-writer",
                    ),
                    (
                        "observation-verification-result",
                        "src/tiny_corpus_workbench/verification.py",
                        "verify_observation",
                        "current-writer",
                    ),
                    (
                        "diagnosis-verification-result",
                        "src/tiny_corpus_workbench/diagnosis_verification.py",
                        "verify_diagnosis",
                        "current-writer",
                    ),
                    (
                        "refinement-verification-result",
                        "src/tiny_corpus_workbench/v03.py",
                        "verify_refinement",
                        "current-writer",
                    ),
                    (
                        "corpus-verification-result",
                        "src/tiny_corpus_workbench/corpus_verification.py",
                        "verify_corpus",
                        "current-writer",
                    ),
                    (
                        "normalized-corpus-specification",
                        "src/tiny_corpus_workbench/corpus.py",
                        "load_corpus_spec",
                        "current-writer",
                    ),
                )
            },
        )
        new_provenance_locations = {
            (item["family"], item["target_pointer"])
            for item in inventory["migration_fields"]
            if item["classification"] == "new"
            and item["target_pointer"]
            in {
                "#/build_provenance/provenance_id",
                "#/runtime/provenance_id",
            }
        }
        self.assertEqual(
            new_provenance_locations,
            {
                *{
                    (family, "#/build_provenance/provenance_id")
                    for family in (
                        "base-fixture-registry",
                        "observation",
                        "observation-verification-result",
                        "diagnosis-fixture-registry",
                        "diagnosis",
                        "diagnosis-verification-result",
                        "refinement-fixture-registry",
                        "refinement-draft",
                        "refinement",
                        "refinement-verification-result",
                        "corpus",
                        "corpus-verification-result",
                    )
                },
                ("workbench-startup", "#/runtime/provenance_id"),
                ("workbench-projection", "#/runtime/provenance_id"),
            },
        )
        self.assertFalse(
            {
                "all-generated",
                "api-startup-projection",
            }
            & {
                item["family"] for item in inventory["migration_fields"]
            }
        )
        build_base_targets = {
            "#/build_provenance/provenance_id",
            "#/build_provenance/package_version",
            "#/build_provenance/lockfile_sha256",
            "#/build_provenance/python/implementation",
            "#/build_provenance/python/major_minor",
            "#/build_provenance/dependencies/docling",
            "#/build_provenance/dependencies/docling-core",
            "#/build_provenance/dependencies/jsonschema",
            "#/build_provenance/dependencies/markitdown",
        }
        expected_migrations: list[tuple[str, str, str | None]] = []

        def expect(
            family: str, classification: str, *targets: str | None
        ) -> None:
            expected_migrations.extend(
                (family, classification, target) for target in targets
            )

        expect(
            "observation",
            "moved",
            "#/build_provenance/python/implementation",
            "#/build_provenance/lockfile_sha256",
            "#/build_provenance/dependencies/docling",
            "#/build_provenance/dependencies/docling-core",
            "#/build_provenance/dependencies/markitdown",
        )
        expect(
            "observation",
            "normalized",
            "#/build_provenance/python/major_minor",
        )
        expect("observation", "removed", None, None)
        expect(
            "observation",
            "retained",
            "#/extractors",
            "#/docling_document_schema",
        )
        expect(
            "observation",
            "new",
            "#/build_provenance/provenance_id",
            "#/build_provenance/package_version",
            "#/build_provenance/dependencies/jsonschema",
            "#/build_provenance/extractor_contract",
            "#/build_provenance/command_id",
        )

        expect(
            "base-fixture-registry",
            "moved",
            "#/build_provenance/lockfile_sha256",
        )
        expect(
            "base-fixture-registry",
            "retained",
            "#/generator",
            *(
                pointer
                for name in sorted(
                    resolve_pointer(
                        base_json(
                            "src/tiny_corpus_workbench/schemas/"
                            "fixture-registry-v0.1.schema.json"
                        ),
                        "#/$defs/fixture/properties/generator/properties",
                    )
                )
                for pointer in (
                    f"#/generator/{name}",
                    f"#/fixtures/*/generator/{name}",
                )
                if name != "lockfile_sha256"
            ),
        )
        expect("base-fixture-registry", "removed", None)
        expect(
            "base-fixture-registry",
            "new",
            *sorted(
                build_base_targets
                - {"#/build_provenance/lockfile_sha256"}
            ),
            "#/build_provenance/generator_id",
        )

        for family in (
            "diagnosis-fixture-registry",
            "refinement-fixture-registry",
        ):
            expect(family, "retained", "#/generator")
            expect(
                family,
                "new",
                *sorted(build_base_targets),
                "#/build_provenance/generator_id",
            )

        for family in ("diagnosis", "refinement"):
            expect(
                family,
                "moved",
                "#/build_provenance/python/implementation",
                "#/build_provenance/package_version",
                "#/build_provenance/lockfile_sha256",
                "#/build_provenance/dependencies/docling",
                "#/build_provenance/dependencies/docling-core",
                "#/build_provenance/dependencies/markitdown",
            )
            expect(
                family,
                "normalized",
                "#/build_provenance/python/major_minor",
            )
            expect(family, "removed", None)
            expect(
                family,
                "new",
                "#/build_provenance/provenance_id",
                "#/build_provenance/dependencies/jsonschema",
                "#/build_provenance/command_id",
            )
        expect(
            "diagnosis",
            "retained",
            "#/source",
            "#/ruleset",
            "#/summary",
        )
        expect(
            "refinement",
            "retained",
            "#/status",
            "#/revision_id",
            "#/origin_observation_id",
            "#/origin_observation_run_id",
            "#/source",
            "#/base",
            "#/draft_id",
            "#/artifacts",
        )

        expect(
            "corpus",
            "moved",
            "#/build_provenance/python/implementation",
            "#/build_provenance/package_version",
            "#/build_provenance/lockfile_sha256",
            "#/build_provenance/dependencies/docling",
            "#/build_provenance/dependencies/docling-core",
            "#/build_provenance/dependencies/markitdown",
        )
        expect(
            "corpus",
            "normalized",
            "#/build_provenance/python/major_minor",
        )
        expect(
            "corpus",
            "retained",
            "#/runtime/ruleset_id",
            "#/runtime/configurations",
            "#/runtime/model_inventory",
        )
        expect(
            "corpus",
            "new",
            "#/build_provenance/provenance_id",
            "#/build_provenance/dependencies/jsonschema",
            "#/build_provenance/command_id",
            "#/build_provenance/extractor_contract",
        )

        for family in (
            "observation-verification-result",
            "diagnosis-verification-result",
            "refinement-draft",
            "refinement-verification-result",
            "corpus-verification-result",
        ):
            expect(
                family,
                "new",
                *sorted(build_base_targets),
                "#/build_provenance/command_id",
            )
        expect("refinement-draft", "retained", "#/decision")
        expect(
            "transformation",
            "retained",
            *(
                f"#/{name}"
                for name in sorted(
                    resolve_pointer(
                        base_json(
                            "src/tiny_corpus_workbench/schemas/"
                            "transformation-history-v0.3.schema.json"
                        ),
                        "#/$defs/transformation/properties",
                    )
                )
            ),
        )
        expect(
            "transformation-history",
            "retained",
            *(
                f"#/{name}"
                for name in sorted(
                    base_json(
                        "src/tiny_corpus_workbench/schemas/"
                        "transformation-history-v0.3.schema.json"
                    )["properties"]
                )
                if name != "schema_version"
            ),
        )
        for family in (
            "authored-fixture",
            "comparison-summary",
            "finding-set",
            "transformation",
            "transformation-history",
            "corpus-spec",
            "corpus-summary",
            "workbench-record-detail",
            "workbench-error",
        ):
            expect(family, "prohibited", "#/build_provenance")
        expect("supported-provenance-registry", "new", "#/entries")
        for family in ("workbench-startup", "workbench-projection"):
            expect(
                family,
                "new",
                "#/runtime/package_version",
                "#/runtime/provenance_id",
            )
        self.assertEqual(
            Counter(
                (
                    item["family"],
                    item["classification"],
                    item["target_pointer"],
                )
                for item in inventory["migration_fields"]
            ),
            Counter(expected_migrations),
        )
        self.assertEqual(
            {
                (
                    item["family"],
                    item["target_pointer"],
                    item.get("derived_value"),
                )
                for item in inventory["migration_fields"]
                if item.get("derived_value")
            },
            {
                (
                    "base-fixture-registry",
                    "#/build_provenance/generator_id",
                    "tools.generate_fixtures",
                ),
                (
                    "diagnosis-fixture-registry",
                    "#/build_provenance/generator_id",
                    "tools.generate_diagnosis_fixtures",
                ),
                (
                    "refinement-fixture-registry",
                    "#/build_provenance/generator_id",
                    "tools.generate_refinement_fixtures",
                ),
                (
                    "observation",
                    "#/build_provenance/command_id",
                    "tcw.observe",
                ),
                (
                    "diagnosis",
                    "#/build_provenance/command_id",
                    "tcw.diagnose",
                ),
                (
                    "refinement",
                    "#/build_provenance/command_id",
                    "tcw.resolve-refinement",
                ),
                (
                    "corpus",
                    "#/build_provenance/command_id",
                    "tcw.inspect-corpus",
                ),
                (
                    "observation-verification-result",
                    "#/build_provenance/command_id",
                    "tcw.verify",
                ),
                (
                    "diagnosis-verification-result",
                    "#/build_provenance/command_id",
                    "tcw.verify-diagnosis",
                ),
                (
                    "refinement-draft",
                    "#/build_provenance/command_id",
                    "tcw.draft-refinement",
                ),
                (
                    "refinement-verification-result",
                    "#/build_provenance/command_id",
                    "tcw.verify-refinement",
                ),
                (
                    "corpus-verification-result",
                    "#/build_provenance/command_id",
                    "tcw.verify-corpus",
                ),
            },
        )
        self.assertEqual(
            {(item["artifact"], item["path"]) for item in inventory["verifiers"]},
            {
                ("observation", "src/tiny_corpus_workbench/verification.py"),
                (
                    "diagnosis",
                    "src/tiny_corpus_workbench/diagnosis_verification.py",
                ),
                ("refinement", "src/tiny_corpus_workbench/v03.py"),
                ("corpus", "src/tiny_corpus_workbench/corpus_verification.py"),
                ("base-fixtures", "tools/verify_fixtures.py"),
                ("corpus-spec", "tools/verify_corpus_specs.py"),
            },
        )
        self.assertEqual(
            {
                (item["family"], item["path"], item["symbol"])
                for item in inventory["identity_inputs"]
            },
            {
                (
                    "observation",
                    "src/tiny_corpus_workbench/artifacts.py",
                    "compute_observation_id",
                ),
                (
                    "diagnosis",
                    "src/tiny_corpus_workbench/v03.py",
                    "compute_diagnosis_id",
                ),
                (
                    "finding",
                    "src/tiny_corpus_workbench/v03.py",
                    "_v3_finding",
                ),
                (
                    "refinement-draft",
                    "src/tiny_corpus_workbench/v03.py",
                    "_draft_identity",
                ),
                (
                    "revision",
                    "src/tiny_corpus_workbench/v03.py",
                    "_revision_identity",
                ),
                (
                    "transformation",
                    "src/tiny_corpus_workbench/v03.py",
                    "_transformation_identity",
                ),
                (
                    "corpus-specification",
                    "src/tiny_corpus_workbench/corpus.py",
                    "load_corpus_spec",
                ),
                (
                    "corpus-snapshot",
                    "src/tiny_corpus_workbench/corpus_execution.py",
                    "_snapshot_identity",
                ),
                (
                    "workbench",
                    "src/tiny_corpus_workbench/canonical_json.py",
                    "logical_copy_key,record_key,edge_key,artifact_key,session_id",
                ),
            },
        )

        for item in (
            inventory["fixtures_registries_specs"]
            + inventory["public_references"]
        ):
            path = item["path"]
            self.assertTrue(Path(path).is_file(), path)
            self.assertTrue(item["classification"])
            subprocess.run(
                ["git", "cat-file", "-e", f"{approved_base}:{path}"],
                check=True,
                capture_output=True,
            )
        base_fixture_scope = {
            path
            for path in git_tree_paths(approved_base, "fixtures")
            if path == "fixtures/README.md"
            or re.fullmatch(r"fixtures/authored/[^/]+\.json", path)
            or path == "fixtures/golden/fixtures.json"
            or re.fullmatch(
                r"fixtures/(?:diagnosis|refinement)/[^/]+/fixtures\.json",
                path,
            )
            or re.fullmatch(r"fixtures/corpus/[^/]+/[^/]+\.json", path)
        }
        self.assertEqual(
            {
                item["path"]
                for item in inventory["fixtures_registries_specs"]
            },
            base_fixture_scope,
        )
        self.assertEqual(
            {item["path"] for item in inventory["public_references"]},
            {
                "README.md",
                "fixtures/README.md",
                "docs/extraction-observatory.md",
                "docs/evidence-based-diagnosis.md",
                "docs/controlled-revisions.md",
                "docs/corpus-inspection-comparison.md",
                "learning/README.md",
                "learning/v0.1-extraction-observatory.md",
                "learning/v0.2-evidence-based-diagnosis.md",
                "learning/v0.3-controlled-revisions.md",
                "learning/v0.4-corpus-inspection-comparison.md",
                "site/index.html",
            },
        )
        for item in inventory["schemas"]:
            self.assertTrue(Path(item["path"]).is_file(), item["path"])
            self.assertIn(
                item["state"], {"v0.5-active", "private-migration-staging"}
            )
            self.assertIn(
                item["classification"],
                {
                    "v0.5-active",
                    "v0.5-shared-definitions",
                    "private-migration-staging",
                },
            )
        self.assertEqual(
            {item["path"] for item in inventory["schemas"]},
            git_tree_paths(
                approved_base, "src/tiny_corpus_workbench/schemas"
            )
            | {
                str(path.relative_to(Path.cwd()))
                for path in SCHEMA_ROOT.glob("*-v0.5.schema.json")
            }
            | {
                "src/tiny_corpus_workbench/schemas/common-v0.5.schema.json"
            },
        )
        self.assertEqual(
            {item["path"] for item in inventory["tests"]},
            {
                path
                for path in git_tree_paths(approved_base, "tests")
                if path.endswith(".py")
            },
        )
        for item in inventory["tests"]:
            expected_classification = (
                "test-package-init"
                if item["path"].endswith("/__init__.py")
                else "compatibility-test"
                if item["path"].startswith("tests/compatibility/")
                else "integration-test"
                if item["path"].startswith("tests/integration/")
                else "unit-test"
            )
            self.assertEqual(
                item["classification"], expected_classification
            )
        for item in inventory["tests"] + inventory["schema_emission_sources"]:
            self.assertTrue(Path(item["path"]).is_file(), item["path"])
            self.assertTrue(item["classification"])
        self.assertEqual(
            {
                item["path"]
                for item in inventory["schema_emission_sources"]
            },
            {
                item["path"]
                for group in ("writers", "verifiers", "identity_inputs")
                for item in inventory[group]
            }
            | {
                "src/tiny_corpus_workbench/schema_catalog.py",
                "src/tiny_corpus_workbench/semantic_validation.py",
                "src/tiny_corpus_workbench/supported_provenance.py",
                "src/tiny_corpus_workbench/supported-provenance-v0.5.json",
            },
        )
        self.assertEqual(
            {
                item["classification"]
                for item in inventory["schema_emission_sources"]
            },
            {"contract-scope-source"},
        )
        for field in inventory["migration_fields"]:
            source = field["source_schema"]
            pointer = field["source_pointer"]
            if field["classification"] in {"new", "prohibited"}:
                self.assertIsNone(source)
                self.assertIsNone(pointer)
                continue
            raw = subprocess.run(
                ["git", "show", f"{approved_base}:{source}"],
                check=True,
                capture_output=True,
                text=True,
            ).stdout
            schema = json.loads(raw)
            with self.subTest(source=source, pointer=pointer):
                self.assertIsNotNone(resolve_pointer(schema, pointer))


if __name__ == "__main__":
    unittest.main()
