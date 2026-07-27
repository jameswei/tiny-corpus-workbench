from __future__ import annotations

import json
import shutil
import subprocess
import sys
import tempfile
import unittest
from copy import deepcopy
from pathlib import Path
from unittest.mock import patch

from jsonschema import Draft202012Validator, ValidationError
from referencing import Registry, Resource

from tiny_corpus_workbench.artifacts import canonical_json
from tiny_corpus_workbench.corpus import load_corpus_spec
from tiny_corpus_workbench.domain import InputError, IntegrityError


ROOT = Path(__file__).resolve().parents[2]
SCHEMAS = ROOT / "src/tiny_corpus_workbench/schemas"
CORPUS_FIXTURES = ROOT / "fixtures/corpus/v0.5"
SCHEMA_NAMES = (
    "corpus-spec-v0.5.schema.json",
    "corpus-manifest-v0.5.schema.json",
    "corpus-summary-v0.5.schema.json",
    "corpus-verification-result-v0.5.schema.json",
)
HASH = "a" * 64


def _build_provenance(command_id: str, *, extracting: bool = False) -> dict:
    entry = json.loads(
        (ROOT / "src/tiny_corpus_workbench/supported-provenance-v0.5.json").read_text(
            "utf-8"
        )
    )["entries"][0]
    value = {
        key: entry[key]
        for key in (
            "provenance_id",
            "package_version",
            "lockfile_sha256",
            "python",
            "dependencies",
        )
    }
    value["command_id"] = command_id
    if extracting:
        value["extractor_contract"] = entry["extractor_contract"]
    return value


def _write_spec(root: Path, members: list[dict], **updates: object) -> Path:
    value: dict[str, object] = {
        "schema_version": "tcw.corpus-spec/v0.5",
        "corpus_id": "test-corpus",
        "title": "Test corpus",
        "members": members,
    }
    value.update(updates)
    path = root / "corpus.json"
    path.write_text(json.dumps(value), "utf-8")
    return path


def _member(
    member_id: str,
    source: str,
    *,
    family: str = "sample",
    format_name: str = "md",
    revisions: list[dict[str, str]] | None = None,
) -> dict:
    value: dict[str, object] = {
        "member_id": member_id,
        "family": family,
        "format": format_name,
        "source": source,
    }
    if revisions is not None:
        value["revisions"] = revisions
    return value


def _assert_objects_closed(test: unittest.TestCase, value: object) -> None:
    if isinstance(value, dict):
        if value.get("type") == "object":
            test.assertIs(
                value.get("additionalProperties"),
                False,
                msg=f"object schema is not closed: {value}",
            )
        for child in value.values():
            _assert_objects_closed(test, child)
    elif isinstance(value, list):
        for child in value:
            _assert_objects_closed(test, child)


def _validator(name: str) -> Draft202012Validator:
    schemas = {
        path.name: json.loads(path.read_text("utf-8"))
        for path in SCHEMAS.glob("*.schema.json")
    }
    registry = Registry()
    for schema in schemas.values():
        registry = registry.with_resource(
            schema["$id"], Resource.from_contents(schema)
        )
    return Draft202012Validator(schemas[name], registry=registry)


def _valid_manifest() -> dict:
    source = {
        "path": "../../golden/sample.md",
        "name": "sample.md",
        "media_type": "text/markdown",
        "size": 10,
        "sha256": HASH,
    }
    descriptor = {"path": "members/sample/manifest.json", "size": 10, "sha256": HASH}
    return {
        "schema_version": "tcw.corpus-manifest/v0.5",
        "corpus_id": "sample",
        "snapshot_id": HASH,
        "run_id": "run",
        "created_at": "2026-07-25T00:00:00Z",
        "status": "COMPLETE",
        "input_specification": {
            "size": 10,
            "sha256": HASH,
            "normalized_sha256": HASH,
        },
        "runtime": {
            "ruleset_id": HASH,
            "configurations": {
                "docling": {
                    "accelerator": "cpu",
                    "ocr": False,
                    "table_structure": True,
                    "remote_services": False,
                    "external_plugins": False,
                    "artifacts_path": "explicit-local-path",
                },
                "markitdown": {
                    "convert_method": "convert_local",
                    "plugins": False,
                    "llm_client": False,
                    "text_hints": "extension-media-type-utf8",
                },
            },
            "model_inventory": {
                "required": False,
                "path": "/tmp/models",
                "state": "NOT_REQUIRED",
                "inventory_hash": None,
                "files": [],
            },
        },
        "summary": {"member_count": 1, "complete": 1, "partial": 0, "failed": 0},
        "members": [
            {
                "member_id": "sample",
                "family": "sample",
                "format": "md",
                "status": "COMPLETE",
                "source": source,
                "observation": {
                    "status": "SUCCESS",
                    "observation_id": HASH,
                    "run_id": "observation-run",
                    "manifest": descriptor,
                    "canonical_document_sha256": HASH,
                },
                "diagnosis": {
                    "status": "NO_FINDINGS",
                    "diagnosis_id": HASH,
                    "run_id": "diagnosis-run",
                    "manifest": descriptor,
                    "findings_sha256": HASH,
                },
                "error": None,
            }
        ],
        "revisions": [
            {
                "member_id": "sample",
                "revision_id": HASH,
                "refinement_run_id": "refinement-run",
                "diagnosis_id": HASH,
                "parent": {
                    "kind": "OBSERVATION",
                    "subject_id": HASH,
                    "canonical_document_sha256": HASH,
                },
                "source": {
                    "key": "sample",
                    "media_type": "text/markdown",
                    "size": 10,
                    "sha256": HASH,
                },
                "chain_length": 1,
                "finding_id": HASH,
                "finding_rule": "TCW-D009",
                "refiner": {
                    "refiner_id": "TCW-R001",
                    "name": "WHITESPACE_NORMALIZATION",
                    "version": "1",
                },
                "affected_reference_count": 1,
                "prepared_document_sha256": HASH,
                "refinement_manifest_sha256": HASH,
                "bundle_paths": {
                    "refinement": "../../revision",
                    "diagnosis": "../../diagnosis",
                    "base": "../../base",
                },
                "inventory_fingerprints": {
                    "refinement": HASH,
                    "diagnosis": HASH,
                    "base": HASH,
                },
            }
        ],
        "artifacts": [
            {
                "path": path,
                "role": role,
                "media_type": media_type,
                "size": 10,
                "sha256": HASH,
                "application_immutable": True,
            }
            for path, role, media_type in (
                ("corpus-spec.json", "normalized-corpus-specification", "application/json"),
                ("summary.json", "corpus-summary", "application/json"),
                ("report/index.html", "corpus-report", "text/html"),
                ("report/styles.css", "corpus-stylesheet", "text/css"),
            )
        ],
        "build_provenance": _build_provenance(
            "tcw.inspect-corpus", extracting=True
        ),
    }


def _metrics(value: int) -> dict[str, int]:
    return {
        name: value
        for name in (
            "bytes",
            "characters",
            "non_whitespace_characters",
            "lines",
            "non_empty_lines",
            "atx_headings",
            "unordered_list_items",
            "ordered_list_items",
            "pipe_table_rows",
            "visible_urls",
        )
    }


def _valid_summary() -> dict:
    deltas: dict[str, object] = _metrics(0)
    deltas["normalized_equal"] = True
    return {
        "schema_version": "tcw.corpus-summary/v0.5",
        "corpus_id": "sample",
        "snapshot_id": HASH,
        "run_id": "run",
        "status": "COMPLETE",
        "totals": {
            "member_count": 1,
            "complete": 1,
            "partial": 0,
            "failed": 0,
            "finding_count": 1,
            "revision_count": 1,
        },
        "by_family": [
            {"name": "sample", "member_count": 1, "complete": 1, "partial": 0, "failed": 0}
        ],
        "by_format": [
            {"name": "md", "member_count": 1, "complete": 1, "partial": 0, "failed": 0}
        ],
        "extractors": [
            {"name": "docling", "available": 1, "unavailable": 0},
            {"name": "markitdown", "available": 1, "unavailable": 0},
        ],
        "comparisons": [
            {
                "member_id": "sample",
                "status": "COMPLETE",
                "docling": _metrics(1),
                "markitdown": _metrics(1),
                "docling_minus_markitdown": deltas,
            }
        ],
        "findings": [
            {
                "rule_id": "TCW-D009",
                "severity": "INFO",
                "family": "sample",
                "format": "md",
                "finding_count": 1,
                "affected_member_count": 1,
            }
        ],
        "revision_groups": [
            {
                "family": "sample",
                "format": "md",
                "finding_rule": "TCW-D009",
                "refiner_id": "TCW-R001",
                "revision_count": 1,
            }
        ],
        "revisions": [
            {
                "member_id": "sample",
                "family": "sample",
                "format": "md",
                "revision_id": HASH,
                "parent": {
                    "kind": "OBSERVATION",
                    "subject_id": HASH,
                    "canonical_document_sha256": HASH,
                },
                "chain_length": 1,
                "finding_id": HASH,
                "finding_rule": "TCW-D009",
                "refiner": {
                    "refiner_id": "TCW-R001",
                    "name": "WHITESPACE_NORMALIZATION",
                    "version": "1",
                },
                "affected_reference_count": 1,
                "before_document_sha256": HASH,
                "after_document_sha256": HASH,
            }
        ],
        "members": [
            {
                "member_id": "sample",
                "family": "sample",
                "format": "md",
                "status": "COMPLETE",
                "error": None,
            }
        ],
    }


def _valid_verification() -> dict:
    return {
        "schema_version": "tcw.corpus-verification-result/v0.5",
        "corpus_directory": "/corpus",
        "artifact_integrity": {"status": "VERIFIED", "issues": []},
        "specification_state": {"status": "MATCH"},
        "source_states": [
            {"member_id": "sample", "state": {"status": "MATCH"}}
        ],
        "model_state": {"status": "NOT_CHECKED"},
        "revision_states": [
            {
                "member_id": "sample",
                "revision_id": HASH,
                "refinement_state": {"status": "MATCH"},
                "diagnosis_state": {"status": "CHANGED"},
                "base_state": {"status": "MISSING"},
            }
        ],
        "build_provenance": _build_provenance("tcw.verify-corpus"),
    }


class CorpusSchemaTests(unittest.TestCase):
    def test_four_schemas_are_draft_2020_12_closed_and_have_exact_versions(self) -> None:
        expected = {
            "corpus-spec-v0.5.schema.json": "tcw.corpus-spec/v0.5",
            "corpus-manifest-v0.5.schema.json": "tcw.corpus-manifest/v0.5",
            "corpus-summary-v0.5.schema.json": "tcw.corpus-summary/v0.5",
            "corpus-verification-result-v0.5.schema.json": "tcw.corpus-verification-result/v0.5",
        }
        for name in SCHEMA_NAMES:
            with self.subTest(name=name):
                schema = json.loads((SCHEMAS / name).read_text("utf-8"))
                Draft202012Validator.check_schema(schema)
                self.assertEqual(
                    schema["$schema"],
                    "https://json-schema.org/draft/2020-12/schema",
                )
                self.assertEqual(
                    schema["properties"]["schema_version"]["const"], expected[name]
                )
                _assert_objects_closed(self, schema)

    def test_corpus_spec_schema_rejects_extra_properties_at_each_level(self) -> None:
        schema = json.loads(
            (SCHEMAS / "corpus-spec-v0.5.schema.json").read_text("utf-8")
        )
        validator = Draft202012Validator(schema)
        valid = {
            "schema_version": "tcw.corpus-spec/v0.5",
            "corpus_id": "sample",
            "title": "Sample",
            "members": [
                {
                    "member_id": "one",
                    "family": "sample",
                    "format": "md",
                    "source": "one.md",
                    "revisions": [
                        {
                            "refinement": "revision",
                            "diagnosis": "diagnosis",
                            "base": "base",
                        }
                    ],
                }
            ],
        }
        validator.validate(valid)
        for target in ((), ("members", 0), ("members", 0, "revisions", 0)):
            changed = deepcopy(valid)
            cursor = changed
            for part in target:
                cursor = cursor[part]  # type: ignore[index]
            cursor["unexpected"] = True  # type: ignore[index]
            with self.subTest(target=target):
                with self.assertRaises(ValidationError):
                    validator.validate(changed)

    def test_committed_specs_have_canonical_normalized_serialization(self) -> None:
        for path in sorted(CORPUS_FIXTURES.glob("*.json")):
            with self.subTest(path=path.name):
                admitted = load_corpus_spec(path)
                self.assertEqual(
                    admitted.canonical_bytes, canonical_json(admitted.normalized)
                )
                self.assertEqual(
                    json.loads(admitted.canonical_bytes), admitted.normalized
                )

    def test_manifest_requires_separate_record_and_revision_identities(self) -> None:
        validator = _validator("corpus-manifest-v0.5.schema.json")
        valid = _valid_manifest()
        validator.validate(valid)
        mutations = (
            lambda value: value["members"][0].pop("observation"),
            lambda value: value["members"][0]["diagnosis"].pop("status"),
            lambda value: value["revisions"][0].pop("inventory_fingerprints"),
            lambda value: value["revisions"][0]["inventory_fingerprints"].pop(
                "diagnosis"
            ),
        )
        for mutate in mutations:
            changed = deepcopy(valid)
            mutate(changed)
            with self.assertRaises(ValidationError):
                validator.validate(changed)

    def test_manifest_rejects_wrong_enum_valid_stage_error_codes(self) -> None:
        validator = _validator("corpus-manifest-v0.5.schema.json")
        null_diagnosis = {
            "status": "NOT_RUN",
            "diagnosis_id": None,
            "run_id": None,
            "manifest": None,
            "findings_sha256": None,
        }
        cases = (
            (
                {
                    "status": "FAILED",
                    "observation_id": None,
                    "run_id": None,
                    "manifest": None,
                    "canonical_document_sha256": None,
                },
                null_diagnosis,
                "OBSERVATION_FAILED",
                "MEMBER_INCOMPLETE",
            ),
            (
                {
                    "status": "NOT_RUN",
                    "observation_id": None,
                    "run_id": None,
                    "manifest": None,
                    "canonical_document_sha256": None,
                },
                null_diagnosis,
                "MEMBER_INCOMPLETE",
                "OBSERVATION_FAILED",
            ),
            (
                _valid_manifest()["members"][0]["observation"],
                {
                    **null_diagnosis,
                    "status": "FAILED",
                },
                "DIAGNOSIS_FAILED",
                "OBSERVATION_INCOMPLETE",
            ),
        )
        for observation, diagnosis, expected, wrong in cases:
            with self.subTest(expected=expected):
                valid = _valid_manifest()
                member = valid["members"][0]
                member["status"] = "FAILED"
                member["observation"] = deepcopy(observation)
                member["diagnosis"] = deepcopy(diagnosis)
                member["error"] = {"code": expected, "message": "expected"}
                validator.validate(valid)
                member["error"]["code"] = wrong
                with self.assertRaises(ValidationError):
                    validator.validate(valid)

    def test_summary_requires_all_metrics_groups_and_revision_details(self) -> None:
        validator = _validator("corpus-summary-v0.5.schema.json")
        valid = _valid_summary()
        validator.validate(valid)
        mutations = (
            lambda value: value["comparisons"][0][
                "docling_minus_markitdown"
            ].pop("normalized_equal"),
            lambda value: value["comparisons"][0]["docling"].pop("bytes"),
            lambda value: value.pop("revision_groups"),
            lambda value: value["revisions"][0].pop("before_document_sha256"),
            lambda value: value["revisions"][0].pop("affected_reference_count"),
        )
        for mutate in mutations:
            changed = deepcopy(valid)
            mutate(changed)
            with self.assertRaises(ValidationError):
                validator.validate(changed)

    def test_verification_advisories_are_attributed_per_input(self) -> None:
        validator = _validator("corpus-verification-result-v0.5.schema.json")
        valid = _valid_verification()
        validator.validate(valid)
        mutations = (
            lambda value: value["source_states"][0].pop("member_id"),
            lambda value: value["revision_states"][0].pop("revision_id"),
            lambda value: value["revision_states"][0].pop("diagnosis_state"),
        )
        for mutate in mutations:
            changed = deepcopy(valid)
            mutate(changed)
            with self.assertRaises(ValidationError):
                validator.validate(changed)


class CorpusAdmissionTests(unittest.TestCase):
    def test_normalizes_members_and_repeated_loads_deterministically(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory).resolve()
            (root / "a.md").write_text("# A\n\nEnough text.\n", "utf-8")
            (root / "b.txt").write_text("Enough text.\n", "utf-8")
            spec = _write_spec(
                root,
                [
                    _member("z-member", "./b.txt", format_name="txt"),
                    _member("a-member", "a.md"),
                ],
            )
            first = load_corpus_spec(spec)
            second = load_corpus_spec(spec)
            self.assertEqual(first.normalized, second.normalized)
            self.assertEqual(
                first.specification_identity, second.specification_identity
            )
            self.assertEqual(
                [item["member_id"] for item in first.normalized["members"]],
                ["a-member", "z-member"],
            )
            self.assertEqual(
                [item["source"] for item in first.normalized["members"]],
                ["a.md", "b.txt"],
            )

    def test_final_spec_recheck_rejects_removal_and_replacement(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory).resolve()
            (root / "source.md").write_text("# Source\n", "utf-8")
            from tiny_corpus_workbench import corpus as corpus_module

            original_validate_source = corpus_module.validate_source
            for operation in ("remove", "replace"):
                with self.subTest(operation=operation):
                    spec = _write_spec(
                        root, [_member("source", "source.md")]
                    )

                    def mutate_spec(value: Path) -> object:
                        identity = original_validate_source(value)
                        spec.unlink()
                        if operation == "replace":
                            spec.write_text(
                                json.dumps(
                                    {
                                        "schema_version": "tcw.corpus-spec/v0.5",
                                        "corpus_id": "replacement",
                                        "title": "Replacement",
                                        "members": [
                                            _member("source", "source.md")
                                        ],
                                    }
                                ),
                                "utf-8",
                            )
                        return identity

                    with patch(
                        "tiny_corpus_workbench.corpus.validate_source",
                        side_effect=mutate_spec,
                    ):
                        with self.assertRaisesRegex(
                            IntegrityError,
                            "corpus specification changed during admission",
                        ):
                            load_corpus_spec(spec)

    def test_rejects_duplicate_member_ids_and_resolved_sources(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory).resolve()
            (root / "source.md").write_text("# Source\n", "utf-8")
            cases = (
                [
                    _member("same", "source.md"),
                    _member("same", "source.md"),
                ],
                [
                    _member("one", "source.md"),
                    _member("two", "./source.md"),
                ],
            )
            for members in cases:
                with self.subTest(members=members):
                    with self.assertRaises(InputError):
                        load_corpus_spec(_write_spec(root, members))

    def test_rejects_hard_link_source_aliases(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory).resolve()
            source = root / "source.md"
            alias = root / "alias.md"
            source.write_text("# Source\n", "utf-8")
            try:
                alias.hardlink_to(source)
            except OSError as error:
                self.skipTest(f"hard links are unavailable: {error}")
            with self.assertRaisesRegex(
                InputError, "sources must resolve to unique files"
            ):
                load_corpus_spec(
                    _write_spec(
                        root,
                        [
                            _member("source", "source.md"),
                            _member("alias", "alias.md"),
                        ],
                    )
                )

    def test_rejects_case_aliases_on_case_insensitive_filesystems(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory).resolve()
            source = root / "CaseSource.md"
            alias = root / "casesource.md"
            source.write_text("# Source\n", "utf-8")
            try:
                same_file = alias.exists() and source.samefile(alias)
            except OSError:
                same_file = False
            if not same_file:
                self.skipTest("filesystem does not provide case aliases")
            with self.assertRaisesRegex(
                InputError, "sources must resolve to unique files"
            ):
                load_corpus_spec(
                    _write_spec(
                        root,
                        [
                            _member("case-source", "CaseSource.md"),
                            _member("case-alias", "casesource.md"),
                        ],
                    )
                )

    def test_rejects_nonlocal_missing_directory_unsupported_and_mismatched_sources(
        self,
    ) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory).resolve()
            (root / "folder").mkdir()
            (root / "bad.pdf").write_text("not a PDF", "utf-8")
            (root / "wrong.md").write_text("# Markdown\n", "utf-8")
            (root / "unsupported.csv").write_text("a,b\n", "utf-8")
            cases = (
                _member("url", "https://example.invalid/a.md"),
                _member("stdin", "-"),
                _member("glob", "*.md"),
                _member("missing", "missing.md"),
                _member("directory", "folder"),
                _member("unsupported", "unsupported.csv", format_name="md"),
                _member("suffix", "wrong.md", format_name="txt"),
                _member("content", "bad.pdf", format_name="pdf"),
            )
            for member in cases:
                with self.subTest(member=member["member_id"]):
                    with self.assertRaises(InputError):
                        load_corpus_spec(_write_spec(root, [member]))

    def test_rejects_symlinked_spec_source_and_revision_nodes(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory).resolve()
            source = root / "source.md"
            source.write_text("# Source\n", "utf-8")
            source_link = root / "source-link.md"
            source_link.symlink_to(source)
            with self.assertRaises(IntegrityError):
                load_corpus_spec(
                    _write_spec(root, [_member("source-link", "source-link.md")])
                )
            linked_directory = root / "linked-directory"
            linked_directory.symlink_to(root, target_is_directory=True)
            with self.assertRaises(IntegrityError):
                load_corpus_spec(
                    _write_spec(
                        root,
                        [_member("linked-parent", "linked-directory/source.md")],
                    )
                )

            spec = _write_spec(root, [_member("source", "source.md")])
            spec_link = root / "spec-link.json"
            spec_link.symlink_to(spec)
            with self.assertRaises(IntegrityError):
                load_corpus_spec(spec_link)

            for name in ("revision", "diagnosis", "base"):
                (root / name).mkdir()
                (root / name / "record.json").write_text("{}", "utf-8")
            (root / "revision" / "unsafe").symlink_to(root / "source.md")
            revision = {
                "refinement": "revision",
                "diagnosis": "diagnosis",
                "base": "base",
            }
            with self.assertRaises(IntegrityError):
                load_corpus_spec(
                    _write_spec(
                        root,
                        [_member("revision-node", "source.md", revisions=[revision])],
                    )
                )

    def test_rejects_symlinks_in_absolute_and_parent_path_components(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory).resolve()
            real = root / "real"
            real.mkdir()
            (real / "source.md").write_text("# Source\n", "utf-8")
            linked = root / "linked"
            linked.symlink_to(real, target_is_directory=True)

            spec = _write_spec(
                root,
                [_member("absolute-source", str(linked / "source.md"))],
            )
            with self.assertRaisesRegex(IntegrityError, "must not use symlinks"):
                load_corpus_spec(spec)
            lexical_escape = _write_spec(
                root,
                [
                    _member(
                        "lexical-source",
                        str(linked / ".." / "real" / "source.md"),
                    )
                ],
            )
            with self.assertRaisesRegex(IntegrityError, "must not use symlinks"):
                load_corpus_spec(lexical_escape)

            nested_spec = _write_spec(
                real, [_member("parent-spec", "source.md")]
            )
            with self.assertRaisesRegex(IntegrityError, "must not use symlinks"):
                load_corpus_spec(linked / nested_spec.name)

            for name in ("revision", "diagnosis", "base"):
                path = real / name
                path.mkdir()
                (path / "record.json").write_text("{}", "utf-8")
            revision = {
                name: str(linked / name)
                for name in ("revision", "diagnosis", "base")
            }
            revision["refinement"] = revision.pop("revision")
            with self.assertRaisesRegex(IntegrityError, "must not use symlinks"):
                load_corpus_spec(
                    _write_spec(
                        root,
                        [
                            _member(
                                "absolute-revision",
                                str(real / "source.md"),
                                revisions=[revision],
                            )
                        ],
                    )
                )

    def test_revision_bundle_requires_all_match_states_applied_and_source_match(
        self,
    ) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory).resolve()
            source = root / "source.md"
            source.write_text("# Source\n\nStable source text.\n", "utf-8")
            admitted_source = load_corpus_spec(
                _write_spec(root, [_member("plain", "source.md")])
            ).members[0]["source"]
            revision_paths = {
                name: root / name for name in ("revision", "diagnosis", "base")
            }
            for path in revision_paths.values():
                path.mkdir()
                (path / "record.json").write_text("{}", "utf-8")
            (revision_paths["diagnosis"] / "diagnosis-manifest.json").write_text(
                json.dumps({"record_type": "diagnosis", "format_version": 1}),
                "utf-8",
            )
            prepared = revision_paths["revision"] / "prepared"
            prepared.mkdir()
            (prepared / "document.json").write_text("{}", "utf-8")
            manifest = {
                "status": "APPLIED",
                "revision_id": "a" * 64,
                "run_id": "run",
                "diagnosis": {
                    "diagnosis_id": "b" * 64,
                },
                "base": {
                    "kind": "OBSERVATION",
                    "identity_value": "c" * 64,
                    "canonical_document_sha256": "f" * 64,
                },
                "source": {
                    "key": "source",
                    "media_type": admitted_source["media_type"],
                    "size": admitted_source["size"],
                    "sha256": admitted_source["sha256"],
                },
            }
            (revision_paths["revision"] / "refinement-manifest.json").write_text(
                json.dumps(manifest), "utf-8"
            )
            history = {
                "transformations": [
                    {
                        "revision_id": "a" * 64,
                        "finding_id": "d" * 64,
                        "refiner": {"refiner_id": "TCW-R001"},
                        "affected_refs": ["#/texts/0"],
                        "prepared_document_sha256": "e" * 64,
                    }
                ]
            }
            (revision_paths["revision"] / "history.json").write_text(
                json.dumps(history), "utf-8"
            )
            (revision_paths["diagnosis"] / "findings.json").write_text(
                json.dumps(
                    {
                        "findings": [
                            {
                                "finding_id": "d" * 64,
                                "rule_id": "TCW-D009",
                            }
                        ]
                    }
                ),
                "utf-8",
            )
            bundle = {
                "refinement": "revision",
                "diagnosis": "diagnosis",
                "base": "base",
            }
            spec = _write_spec(
                root, [_member("with-revision", "source.md", revisions=[bundle])]
            )
            verified = {
                name: {"status": status}
                for name, status in (
                    ("artifact_integrity", "VERIFIED"),
                    ("diagnosis_state", "MATCH"),
                    ("base_state", "MATCH"),
                    ("derivation_state", "MATCH"),
                    ("reversibility_state", "MATCH"),
                )
            }
            with patch(
                "tiny_corpus_workbench.v03.verify_refinement",
                return_value=verified,
            ):
                admitted = load_corpus_spec(spec)
            self.assertEqual(
                admitted.members[0]["revisions"][0]["revision_id"], "a" * 64
            )
            self.assertEqual(
                admitted.members[0]["revisions"][0]["finding_rule"], "TCW-D009"
            )
            self.assertEqual(
                admitted.members[0]["revisions"][0][
                    "inventory_fingerprints"
                ].keys(),
                {"base", "diagnosis", "refinement"},
            )
            refinement_entries = admitted.members[0]["revisions"][0][
                "inventories"
            ]["refinement"]["entries"]
            self.assertIn(
                {"path": "prepared", "kind": "directory"},
                refinement_entries,
            )

            diagnosis_manifest_path = (
                revision_paths["diagnosis"] / "diagnosis-manifest.json"
            )
            current_diagnosis_header = {
                "record_type": "diagnosis",
                "format_version": 1,
            }
            for name, invalid_header in (
                ("unknown", {"record_type": "diagnosis", "format_version": 99}),
                ("missing", {"format_version": 1}),
            ):
                with self.subTest(diagnosis_header=name):
                    diagnosis_manifest_path.write_text(
                        json.dumps(invalid_header), "utf-8"
                    )
                    with self.assertRaisesRegex(InputError, "regenerate"):
                        load_corpus_spec(spec)
            diagnosis_manifest_path.write_text(
                json.dumps(current_diagnosis_header), "utf-8"
            )

            def mutate_source(*_args: object, **_kwargs: object) -> dict:
                source.write_text("# Changed source\n", "utf-8")
                return verified

            with patch(
                "tiny_corpus_workbench.v03.verify_refinement",
                side_effect=mutate_source,
            ):
                with self.assertRaisesRegex(
                    IntegrityError, "member source changed during admission"
                ):
                    load_corpus_spec(spec)
            source.write_text("# Source\n\nStable source text.\n", "utf-8")

            alternate_source = root / "alternate.md"
            alternate_source.write_text(
                "# Source\n\nStable source text.\n", "utf-8"
            )

            def substitute_source_symlink(
                *_args: object, **_kwargs: object
            ) -> dict:
                source.unlink()
                source.symlink_to(alternate_source)
                return verified

            with patch(
                "tiny_corpus_workbench.v03.verify_refinement",
                side_effect=substitute_source_symlink,
            ):
                with self.assertRaisesRegex(
                    IntegrityError, "member source changed during admission"
                ):
                    load_corpus_spec(spec)
            source.unlink()
            source.write_text("# Source\n\nStable source text.\n", "utf-8")

            unexpected = revision_paths["revision"] / "unexpected-empty"

            def add_empty_directory(*_args: object, **_kwargs: object) -> dict:
                unexpected.mkdir()
                return verified

            with patch(
                "tiny_corpus_workbench.v03.verify_refinement",
                side_effect=add_empty_directory,
            ):
                with self.assertRaisesRegex(
                    IntegrityError, "revision bundle changed during admission"
                ):
                    load_corpus_spec(spec)
            unexpected.rmdir()

            later_refinement = root / "revision-later"
            shutil.copytree(revision_paths["revision"], later_refinement)
            later_manifest_path = later_refinement / "refinement-manifest.json"
            later_manifest = json.loads(later_manifest_path.read_text("utf-8"))
            later_manifest["revision_id"] = "1" * 64
            later_manifest_path.write_text(json.dumps(later_manifest), "utf-8")
            later_history_path = later_refinement / "history.json"
            later_history = json.loads(later_history_path.read_text("utf-8"))
            later_history["transformations"][-1]["revision_id"] = "1" * 64
            later_history_path.write_text(json.dumps(later_history), "utf-8")
            later_bundle = {
                "refinement": "revision-later",
                "diagnosis": "diagnosis",
                "base": "base",
            }
            later_spec = _write_spec(
                root,
                [
                    _member(
                        "with-two-revisions",
                        "source.md",
                        revisions=[bundle, later_bundle],
                    )
                ],
            )
            from tiny_corpus_workbench import corpus as corpus_module

            original_admit_revision = corpus_module._admit_revision
            calls = 0

            def mutate_earlier_bundle(
                *args: object, **kwargs: object
            ) -> tuple[dict, dict, dict]:
                nonlocal calls
                result = original_admit_revision(*args, **kwargs)
                calls += 1
                if calls == 2:
                    unexpected.mkdir()
                return result

            with (
                patch(
                    "tiny_corpus_workbench.v03.verify_refinement",
                    return_value=verified,
                ),
                patch(
                    "tiny_corpus_workbench.corpus._admit_revision",
                    side_effect=mutate_earlier_bundle,
                ),
            ):
                with self.assertRaisesRegex(
                    IntegrityError, "revision bundle changed during admission"
                ):
                    load_corpus_spec(later_spec)
            unexpected.rmdir()

            saved_refinement = root / "revision-saved"

            def substitute_revision_root(
                *args: object, **kwargs: object
            ) -> tuple[dict, dict, dict]:
                result = original_admit_revision(*args, **kwargs)
                revision_paths["revision"].rename(saved_refinement)
                revision_paths["revision"].symlink_to(
                    saved_refinement, target_is_directory=True
                )
                return result

            spec = _write_spec(
                root, [_member("with-revision", "source.md", revisions=[bundle])]
            )
            with (
                patch(
                    "tiny_corpus_workbench.v03.verify_refinement",
                    return_value=verified,
                ),
                patch(
                    "tiny_corpus_workbench.corpus._admit_revision",
                    side_effect=substitute_revision_root,
                ),
            ):
                with self.assertRaisesRegex(
                    IntegrityError, "revision bundle changed during admission"
                ):
                    load_corpus_spec(spec)
            revision_paths["revision"].unlink()
            saved_refinement.rename(revision_paths["revision"])

            broken = deepcopy(verified)
            broken["derivation_state"]["status"] = "MISMATCH"
            with patch(
                "tiny_corpus_workbench.v03.verify_refinement",
                return_value=broken,
            ):
                with self.assertRaises(InputError):
                    load_corpus_spec(spec)

            removed_during_verification = revision_paths["base"] / "record.json"

            def remove_input_and_return_broken(
                *_args: object, **_kwargs: object
            ) -> dict:
                removed_during_verification.unlink()
                return broken

            with patch(
                "tiny_corpus_workbench.v03.verify_refinement",
                side_effect=remove_input_and_return_broken,
            ):
                with self.assertRaisesRegex(
                    IntegrityError, "revision bundle changed during admission"
                ):
                    load_corpus_spec(spec)
            removed_during_verification.write_text("{}", "utf-8")

            manifest["status"] = "REJECTED"
            manifest["revision_id"] = None
            (revision_paths["revision"] / "refinement-manifest.json").write_text(
                json.dumps(manifest), "utf-8"
            )
            with patch(
                "tiny_corpus_workbench.v03.verify_refinement",
                return_value=verified,
            ):
                with self.assertRaises(InputError):
                    load_corpus_spec(spec)

            manifest["status"] = "APPLIED"
            manifest["revision_id"] = "a" * 64
            manifest["source"]["sha256"] = "f" * 64
            (revision_paths["revision"] / "refinement-manifest.json").write_text(
                json.dumps(manifest), "utf-8"
            )
            with patch(
                "tiny_corpus_workbench.v03.verify_refinement",
                return_value=verified,
            ):
                with self.assertRaises(InputError):
                    load_corpus_spec(spec)


class CorpusSpecCheckerTests(unittest.TestCase):
    def test_checker_passes_twice_without_rewriting_specs(self) -> None:
        paths = sorted(CORPUS_FIXTURES.glob("*.json"))
        before = {path: path.read_bytes() for path in paths}
        command = [sys.executable, "tools/verify_corpus_specs.py"]
        first = subprocess.run(
            command, cwd=ROOT, check=False, capture_output=True, text=True
        )
        second = subprocess.run(
            command, cwd=ROOT, check=False, capture_output=True, text=True
        )
        self.assertEqual(first.returncode, 0, first.stderr)
        self.assertEqual(second.returncode, 0, second.stderr)
        self.assertEqual(first.stdout, second.stdout)
        self.assertEqual(before, {path: path.read_bytes() for path in paths})


if __name__ == "__main__":
    unittest.main()
