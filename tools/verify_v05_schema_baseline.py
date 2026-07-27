#!/usr/bin/env python3
"""Verify the complete checked-in v0.5-only reset baseline."""

from __future__ import annotations

import ast
import hashlib
import json
import re
import subprocess
from pathlib import Path
from typing import Any

from jsonschema import Draft202012Validator
from referencing import Registry, Resource

from tiny_corpus_workbench.canonical_json import canonical_json


ROOT = Path(__file__).resolve().parents[1]
INVENTORY_PATH = "tests/fixtures/v05-schema-evidence-inventory.json"
INVENTORY_SHA256 = (
    "5c069f1f96eb63eec82bf465e4e229abec5fe8019bc56fd05834410d74974ee2"
)
OLD_SCHEMA = re.compile(r"tcw\.[A-Za-z0-9-]+/v0\.[1-4]\b")
OLD_SCHEMA_FILE = re.compile(r"-v0\.[1-4]\.schema\.json\b")

USER_DOCUMENTS = (
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
)

REPOSITORY_METADATA = (
    ".gitattributes",
    ".github/workflows/ci.yml",
    ".github/workflows/pages.yml",
    ".gitignore",
    ".python-version",
    "AGENTS.md",
    "CURRENT.md",
    "LICENSE",
    "pyproject.toml",
    "uv.lock",
)

FIXTURE_FILES = (
    "fixtures/LICENSE-CC0-1.0.txt",
    "fixtures/README.md",
    "fixtures/authored/meeting-minutes.json",
    "fixtures/authored/policy-memo.json",
    "fixtures/authored/release-notice.json",
    "fixtures/corpus/v0.5/golden-matrix.json",
    "fixtures/corpus/v0.5/quality-corpus.json",
    "fixtures/diagnosis/v0.5/fixtures.json",
    "fixtures/diagnosis/v0.5/repeated-margin.pdf",
    "fixtures/diagnosis/v0.5/short-note.md",
    "fixtures/diagnosis/v0.5/structural-traps.md",
    "fixtures/golden/fixtures.json",
    "fixtures/golden/meeting-minutes.docx",
    "fixtures/golden/meeting-minutes.md",
    "fixtures/golden/meeting-minutes.pdf",
    "fixtures/golden/meeting-minutes.txt",
    "fixtures/golden/policy-memo.docx",
    "fixtures/golden/policy-memo.md",
    "fixtures/golden/policy-memo.pdf",
    "fixtures/golden/policy-memo.txt",
    "fixtures/golden/release-notice.docx",
    "fixtures/golden/release-notice.md",
    "fixtures/golden/release-notice.pdf",
    "fixtures/golden/release-notice.txt",
    "fixtures/refinement/v0.5/fixtures.json",
    "fixtures/refinement/v0.5/line-end-hyphenation.docx",
    "fixtures/refinement/v0.5/whitespace-cleanup.md",
)

TEST_FIXTURE_FILES = (
    "tests/fixtures/v05-provenance-examples.json",
    "tests/fixtures/v05-schema-evidence-inventory.json",
    "tests/fixtures/workbench-api/detail-corpus.json",
    "tests/fixtures/workbench-api/detail-diagnosis-refinement-subject.json",
    "tests/fixtures/workbench-api/detail-diagnosis.json",
    "tests/fixtures/workbench-api/detail-observation.json",
    "tests/fixtures/workbench-api/detail-refinement-applied.json",
    "tests/fixtures/workbench-api/detail-refinement-rejected.json",
    "tests/fixtures/workbench-api/errors.json",
    "tests/fixtures/workbench-api/projection-contained-dedup.json",
    "tests/fixtures/workbench-api/projection-missing-edge.json",
    "tests/fixtures/workbench-api/projection-observation.json",
    "tests/fixtures/workbench-api/startup.json",
)

PLACEMENT = {
    "tcw.fixture-registry/v0.5": (
        "BUILD_GENERATOR",
        "tools.generate_fixtures",
    ),
    "tcw.preparation-manifest/v0.5": (
        "BUILD_EXTRACTING_COMMAND",
        "tcw.observe",
    ),
    "tcw.verification-result/v0.5": ("BUILD_COMMAND", "tcw.verify"),
    "tcw.diagnosis-fixture-registry/v0.5": (
        "BUILD_GENERATOR",
        "tools.generate_diagnosis_fixtures",
    ),
    "tcw.diagnosis-manifest/v0.5": (
        "BUILD_COMMAND",
        "tcw.diagnose",
    ),
    "tcw.diagnosis-verification-result/v0.5": (
        "BUILD_COMMAND",
        "tcw.verify-diagnosis",
    ),
    "tcw.refinement-fixture-registry/v0.5": (
        "BUILD_GENERATOR",
        "tools.generate_refinement_fixtures",
    ),
    "tcw.refinement-draft/v0.5": (
        "BUILD_COMMAND",
        "tcw.draft-refinement",
    ),
    "tcw.refinement-manifest/v0.5": (
        "BUILD_COMMAND",
        "tcw.resolve-refinement",
    ),
    "tcw.refinement-verification-result/v0.5": (
        "BUILD_COMMAND",
        "tcw.verify-refinement",
    ),
    "tcw.corpus-manifest/v0.5": (
        "BUILD_EXTRACTING_COMMAND",
        "tcw.inspect-corpus",
    ),
    "tcw.corpus-verification-result/v0.5": (
        "BUILD_COMMAND",
        "tcw.verify-corpus",
    ),
}

ARTIFACT_SCHEMAS = {
    "base-fixtures": "tcw.fixture-registry/v0.5",
    "comparison-summary": "tcw.comparison-summary/v0.5",
    "corpus": "tcw.corpus-manifest/v0.5",
    "corpus-spec": "tcw.corpus-spec/v0.5",
    "corpus-summary": "tcw.corpus-summary/v0.5",
    "corpus-verification-result": "tcw.corpus-verification-result/v0.5",
    "diagnosis": "tcw.diagnosis-manifest/v0.5",
    "diagnosis-fixtures": "tcw.diagnosis-fixture-registry/v0.5",
    "diagnosis-verification-result": (
        "tcw.diagnosis-verification-result/v0.5"
    ),
    "normalized-corpus-specification": "tcw.corpus-spec/v0.5",
    "observation": "tcw.preparation-manifest/v0.5",
    "observation-verification-result": "tcw.verification-result/v0.5",
    "refinement": "tcw.refinement-manifest/v0.5",
    "refinement-draft": "tcw.refinement-draft/v0.5",
    "refinement-fixtures": "tcw.refinement-fixture-registry/v0.5",
    "refinement-verification-result": (
        "tcw.refinement-verification-result/v0.5"
    ),
    "transformation": "tcw.transformation/v0.5",
    "transformation-history": "tcw.transformation-history/v0.5",
}

FAMILY_SCHEMAS = {
    "authored-fixture": "tcw.authored-fixture/v0.5",
    "base-fixture-registry": "tcw.fixture-registry/v0.5",
    "comparison-summary": "tcw.comparison-summary/v0.5",
    "corpus": "tcw.corpus-manifest/v0.5",
    "corpus-spec": "tcw.corpus-spec/v0.5",
    "corpus-summary": "tcw.corpus-summary/v0.5",
    "corpus-verification-result": "tcw.corpus-verification-result/v0.5",
    "diagnosis": "tcw.diagnosis-manifest/v0.5",
    "diagnosis-fixture-registry": "tcw.diagnosis-fixture-registry/v0.5",
    "diagnosis-verification-result": (
        "tcw.diagnosis-verification-result/v0.5"
    ),
    "finding-set": "tcw.finding-set/v0.5",
    "observation": "tcw.preparation-manifest/v0.5",
    "observation-verification-result": "tcw.verification-result/v0.5",
    "refinement": "tcw.refinement-manifest/v0.5",
    "refinement-draft": "tcw.refinement-draft/v0.5",
    "refinement-fixture-registry": (
        "tcw.refinement-fixture-registry/v0.5"
    ),
    "refinement-verification-result": (
        "tcw.refinement-verification-result/v0.5"
    ),
    "supported-provenance-registry": (
        "tcw.supported-provenance-registry/v0.5"
    ),
    "transformation": "tcw.transformation/v0.5",
    "transformation-history": "tcw.transformation-history/v0.5",
    "workbench-error": "tcw.workbench-error/v0.5",
    "workbench-projection": "tcw.workbench-projection/v0.5",
    "workbench-record-detail": "tcw.workbench-record-detail/v0.5",
    "workbench-startup": "tcw.workbench-startup/v0.5",
}

EXPECTED_INITIAL_PROVENANCE = {
    "lockfile_sha256": (
        "2a06114acb4804c445ff5d562123c7ef9930f86d18bf98d6d51fb615e40f5cca"
    ),
    "package_version": "0.5.0",
    "provenance_id": (
        "f27bf80e8a5c17a5ea7567ccdca6335d955f09a616ac4ec750567a1e98715f04"
    ),
    "python": {"implementation": "CPython", "major_minor": "3.12"},
    "dependencies": {
        "docling": "2.113.0",
        "docling-core": "2.87.1",
        "jsonschema": "4.26.0",
        "markitdown": "0.1.6",
    },
    "extractor_contract": {
        "docling": {
            "document_schema_name": "DoclingDocument",
            "document_schema_version": "1.10.0",
            "package_version": "2.113.0",
        },
        "markitdown": {"package_version": "0.1.6"},
    },
}


class AuditError(ValueError):
    """The checked-in reset baseline is incomplete or inconsistent."""


def fail(message: str) -> None:
    raise AuditError(message)


def _canonical_sha256(value: object) -> str:
    return hashlib.sha256(canonical_json(value)).hexdigest()


def _ast_value(path: Path, name: str) -> object:
    tree = ast.parse(path.read_text("utf-8"), filename=str(path))
    for node in tree.body:
        if isinstance(node, (ast.Assign, ast.AnnAssign)):
            targets = (
                node.targets
                if isinstance(node, ast.Assign)
                else [node.target]
            )
            if any(
                isinstance(target, ast.Name) and target.id == name
                for target in targets
            ):
                value = node.value
                if (
                    isinstance(value, ast.Call)
                    and isinstance(value.func, ast.Name)
                    and value.func.id == "MappingProxyType"
                ):
                    value = value.args[0]
                return ast.literal_eval(value)
    fail(f"declaration is missing: {path}:{name}")


def _function_names_and_strings(path: Path) -> tuple[set[str], set[str]]:
    tree = ast.parse(path.read_text("utf-8"), filename=str(path))
    names = {
        node.name
        for node in ast.walk(tree)
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef))
    }
    strings = {
        node.value
        for node in ast.walk(tree)
        if isinstance(node, ast.Constant) and isinstance(node.value, str)
    }
    return names, strings


def _walk_keys(value: object):
    if isinstance(value, dict):
        yield from value
        for child in value.values():
            yield from _walk_keys(child)
    elif isinstance(value, list):
        for child in value:
            yield from _walk_keys(child)


def _schema_version_consts(value: object) -> set[str]:
    values: set[str] = set()
    if isinstance(value, dict):
        schema_version = value.get("properties", {}).get("schema_version")
        if (
            isinstance(schema_version, dict)
            and isinstance(schema_version.get("const"), str)
        ):
            values.add(schema_version["const"])
        for child in value.values():
            values.update(_schema_version_consts(child))
    elif isinstance(value, list):
        for child in value:
            values.update(_schema_version_consts(child))
    return values


def _resolve_pointer(document: object, pointer: str) -> object:
    value = document
    for token in pointer.removeprefix("#/").split("/"):
        token = token.replace("~1", "/").replace("~0", "~")
        if token == "*" and isinstance(value, dict):
            token = "items"
        value = value[int(token)] if isinstance(value, list) else value[token]
    return value


def _resolve_instance_schema(
    schema: dict[str, Any],
    pointer: str,
    schemas: dict[str, dict[str, Any]],
) -> object:
    by_filename = {
        value["$id"].rsplit("/", 1)[-1]: value
        for value in schemas.values()
    }
    root = schema
    value: object = schema

    def dereference(candidate: object) -> object:
        nonlocal root
        while isinstance(candidate, dict) and "$ref" in candidate:
            reference = candidate["$ref"]
            filename, _, fragment = reference.partition("#")
            if filename:
                root = by_filename[filename.rsplit("/", 1)[-1]]
            candidate = (
                _resolve_pointer(root, f"#{fragment}")
                if fragment
                else root
            )
        return candidate

    for token in pointer.removeprefix("#/").split("/"):
        value = dereference(value)
        if token == "*":
            value = value["items"]
            continue
        if not isinstance(value, dict):
            raise KeyError(token)
        properties = value.get("properties", {})
        if token not in properties:
            matches = [
                branch["properties"][token]
                for keyword in ("oneOf", "anyOf", "allOf")
                for branch in value.get(keyword, [])
                if isinstance(branch, dict)
                and token in branch.get("properties", {})
            ]
            if not matches:
                raise KeyError(token)
            value = matches[0]
        else:
            value = properties[token]
    return dereference(value)


def _git_json(
    repository: Path,
    revision: str,
    relative: str,
) -> dict[str, Any]:
    result = subprocess.run(
        ["git", "show", f"{revision}:{relative}"],
        cwd=repository,
        check=True,
        capture_output=True,
        text=True,
    )
    value = json.loads(result.stdout)
    if not isinstance(value, dict):
        fail(f"base schema is not an object: {relative}")
    return value


def _schema_registry(
    schemas: dict[str, dict[str, Any]],
) -> Registry:
    registry = Registry()
    for schema in schemas.values():
        Draft202012Validator.check_schema(schema)
        registry = registry.with_resource(
            schema["$id"], Resource.from_contents(schema)
        )
    return registry


def _verify_inventory_scopes(
    root: Path,
    inventory: dict[str, Any],
    schema_paths: set[str],
) -> None:
    actual_sources = {
        path.relative_to(root).as_posix()
        for directory in ("src", "tools")
        for path in (root / directory).rglob("*.py")
        if "__pycache__" not in path.parts
    }
    classified_sources = {
        item["path"] for item in inventory["schema_emission_sources"]
    }
    if actual_sources != classified_sources:
        fail("executable schema scope is incomplete or stale")

    actual_tests = {
        path.relative_to(root).as_posix()
        for path in (root / "tests").rglob("*.py")
        if "__pycache__" not in path.parts
    }
    if actual_tests != {item["path"] for item in inventory["tests"]}:
        fail("test scope is incomplete or stale")

    if schema_paths != {item["path"] for item in inventory["schemas"]}:
        fail("schema evidence inventory differs from packaged schemas")

    actual_fixtures = {
        path.relative_to(root).as_posix()
        for path in (root / "fixtures").rglob("*")
        if path.is_file()
    }
    if actual_fixtures != set(FIXTURE_FILES):
        fail("fixture file inventory is incomplete or stale")

    actual_test_fixtures = {
        path.relative_to(root).as_posix()
        for path in (root / "tests/fixtures").rglob("*")
        if path.is_file()
    }
    if actual_test_fixtures != set(TEST_FIXTURE_FILES):
        fail("test-fixture file inventory is incomplete or stale")

    if tuple(item["path"] for item in inventory["public_references"]) != (
        USER_DOCUMENTS
    ):
        fail("current user-document scope differs")
    for relative in (*REPOSITORY_METADATA, *USER_DOCUMENTS):
        if not (root / relative).is_file():
            fail(f"classified repository file is missing: {relative}")


def _verify_provenance(
    root: Path,
    schemas: dict[str, dict[str, Any]],
    schema_files: dict[str, str],
) -> None:
    provenance_source = root / "src/tiny_corpus_workbench/supported_provenance.py"
    commands = tuple(_ast_value(provenance_source, "COMMAND_IDS"))
    generators = tuple(_ast_value(provenance_source, "GENERATOR_IDS"))
    if commands != tuple(sorted(commands)) or len(commands) != len(set(commands)):
        fail("runtime command declarations are not canonical and unique")
    if generators != tuple(sorted(generators)) or len(generators) != len(
        set(generators)
    ):
        fail("runtime generator declarations are not canonical and unique")

    common = schemas["common-v0.5.schema.json"]
    command_enum = tuple(
        common["$defs"]["BUILD_COMMAND"]["properties"]["command_id"]["enum"]
    )
    extracting_command_enum = tuple(
        common["$defs"]["BUILD_EXTRACTING_COMMAND"]["properties"]["command_id"][
            "enum"
        ]
    )
    generator_enum = tuple(
        common["$defs"]["BUILD_GENERATOR"]["properties"]["generator_id"]["enum"]
    )
    if set(command_enum) != set(commands) or len(command_enum) != len(commands):
        fail("shared command identifiers differ from runtime declarations")
    if set(generator_enum) != set(generators) or len(generator_enum) != len(
        generators
    ):
        fail("shared generator identifiers differ from runtime declarations")
    if set(extracting_command_enum) != set(commands) or len(
        extracting_command_enum
    ) != len(commands):
        fail("extracting command identifiers differ from runtime declarations")

    registry_path = root / "src/tiny_corpus_workbench/supported-provenance-v0.5.json"
    raw = registry_path.read_bytes()
    registry_value = json.loads(raw)
    if raw != canonical_json(registry_value) + b"\n":
        fail("supported provenance registry is not canonical JSON")
    validator = Draft202012Validator(
        schemas[schema_files["tcw.supported-provenance-registry/v0.5"]],
        registry=_schema_registry(schemas),
    )
    validator.validate(registry_value)
    entries = registry_value["entries"]
    ids = [entry["provenance_id"] for entry in entries]
    tuples = [
        {
            key: value
            for key, value in entry.items()
            if key not in {"provenance_id", "commands", "generators"}
        }
        for entry in entries
    ]
    if ids != sorted(ids) or len(ids) != len(set(ids)):
        fail("supported provenance IDs are not strictly ordered and unique")
    if len({canonical_json(value) for value in tuples}) != len(tuples):
        fail("supported provenance tuples are not unique")
    for entry, value in zip(entries, tuples):
        if entry["provenance_id"] != _canonical_sha256(value):
            fail("supported provenance ID does not match its tuple")
        if tuple(entry["commands"]) != commands:
            fail("registry commands differ from runtime declarations")
        if tuple(entry["generators"]) != generators:
            fail("registry generators differ from runtime declarations")
        matches = [
            candidate
            for candidate in entries
            if candidate["provenance_id"] == entry["provenance_id"]
        ]
        if matches != [entry]:
            fail("direct provenance-ID resolution differs")
    if len(entries) < 1:
        fail("supported provenance registry has no initial entry")
    for key, expected in EXPECTED_INITIAL_PROVENANCE.items():
        if entries[0].get(key) != expected:
            fail(f"initial supported provenance tuple differs: {key}")


def _verify_placement(
    schemas: dict[str, dict[str, Any]],
    schema_files: dict[str, str],
    inventory: dict[str, Any],
) -> None:
    common = schemas["common-v0.5.schema.json"]
    for schema_version, filename in schema_files.items():
        schema = schemas[filename]
        properties = schema.get("properties", {})
        required = schema.get("required", [])
        placement = PLACEMENT.get(schema_version)
        if placement is None:
            if (
                "build_provenance" in properties
                or "build_provenance" in required
            ):
                fail(
                    f"prohibited build provenance placement: {schema_version}"
                )
            continue
        shape, identifier = placement
        if properties.get("build_provenance") != {
            "$ref": f"common-v0.5.schema.json#/$defs/{shape}"
        } or "build_provenance" not in required:
            fail(f"wrong build provenance placement: {schema_version}")
        field = "generator_id" if shape == "BUILD_GENERATOR" else "command_id"
        if identifier not in common["$defs"][shape]["properties"][field]["enum"]:
            fail(f"fixed provenance identifier is undeclared: {identifier}")

    writer_artifacts = {item["artifact"] for item in inventory["writers"]}
    expected_writer_requirements = {
        artifact: (
            "prohibited"
            if schema not in PLACEMENT
            else f"{PLACEMENT[schema][0]}:{PLACEMENT[schema][1]}"
        )
        for artifact, schema in ARTIFACT_SCHEMAS.items()
        if artifact in writer_artifacts
    }
    actual_writer_requirements = {
        item["artifact"]: item["provenance_requirement"]
        for item in inventory["writers"]
    }
    if actual_writer_requirements != expected_writer_requirements:
        fail("writer provenance placement table differs")


def _verify_writers_and_verifiers(
    root: Path,
    inventory: dict[str, Any],
) -> None:
    for group in ("writers", "verifiers"):
        for item in inventory[group]:
            path = root / item["path"]
            if not path.is_file():
                fail(f"classified {group} source is missing: {item['path']}")
            names, strings = _function_names_and_strings(path)
            symbol = item.get("symbol")
            if symbol and symbol not in names:
                fail(f"classified writer symbol is missing: {symbol}")
            expected_schema = ARTIFACT_SCHEMAS[item["artifact"]]
            expected_filename = (
                expected_schema.removeprefix("tcw.")
                .removesuffix("/v0.5")
                + "-v0.5.schema.json"
            )
            if (
                expected_schema not in strings
                and expected_filename not in strings
                and not (
                    item["artifact"] == "corpus-spec"
                    and "fixtures/corpus/v0.5" in strings
                )
            ):
                fail(
                    f"{group} does not declare its exact v0.5 schema: "
                    f"{item['artifact']}"
                )


def _verify_migration_evidence(
    root: Path,
    base_repository: Path,
    inventory: dict[str, Any],
    schemas_by_version: dict[str, dict[str, Any]],
) -> None:
    allowed = {"moved", "normalized", "retained", "removed", "new", "prohibited"}
    approved_base = inventory["approved_base"]
    for item in inventory["migration_fields"]:
        classification = item["classification"]
        if classification not in allowed:
            fail("migration field has an unknown classification")
        source = item["source_schema"]
        source_pointer = item["source_pointer"]
        target_pointer = item["target_pointer"]
        if classification in {"new", "prohibited"}:
            if source is not None or source_pointer is not None:
                fail("new or prohibited migration field has legacy evidence")
        else:
            if not isinstance(source, str) or not isinstance(source_pointer, str):
                fail("migration field lacks immutable-base evidence")
            try:
                _resolve_pointer(
                    _git_json(
                        base_repository,
                        approved_base,
                        source,
                    ),
                    source_pointer,
                )
            except (KeyError, IndexError, TypeError):
                fail(
                    f"migration source pointer is absent at approved base: {source_pointer}"
                )
        if classification == "removed":
            if target_pointer is not None:
                fail("removed field has a target pointer")
        else:
            if not isinstance(target_pointer, str):
                fail("current migration field lacks a target pointer")
            target_schema_version = FAMILY_SCHEMAS[item["family"]]
            target_schema = schemas_by_version[target_schema_version]
            if classification == "prohibited":
                try:
                    _resolve_instance_schema(
                        target_schema,
                        target_pointer,
                        schemas_by_version,
                    )
                except (KeyError, IndexError, TypeError):
                    continue
                fail(
                    f"prohibited migration target exists: {target_pointer}"
                )
            try:
                if target_pointer.startswith("#/build_provenance/"):
                    if target_schema_version not in PLACEMENT:
                        raise KeyError("build_provenance")
                _resolve_instance_schema(
                    target_schema,
                    target_pointer,
                    schemas_by_version,
                )
            except (KeyError, IndexError, TypeError):
                fail(
                    f"migration target pointer is absent: {target_pointer}"
                )
        if "derived_value" in item and classification != "new":
            fail("derived migration value is not classified as new")


def _verify_repository_metadata(root: Path) -> None:
    attributes = (root / ".gitattributes").read_text("utf-8")
    required = {
        "fixtures/golden/*.pdf binary",
        "fixtures/golden/*.docx binary",
        "fixtures/diagnosis/v0.5/*.pdf binary",
        "fixtures/refinement/v0.5/*.docx binary",
    }
    lines = set(attributes.splitlines())
    if not required.issubset(lines):
        fail("v0.5 binary attribute rules are incomplete")
    if "fixtures/diagnosis/v0.2/*.pdf binary" in lines:
        fail("obsolete diagnosis v0.2 binary attribute remains")


def verify(
    root: Path = ROOT,
    *,
    base_repository: Path | None = None,
) -> None:
    """Verify one repository tree against the frozen V05-4 reset decision."""

    root = root.resolve()
    base_repository = (
        root if base_repository is None else base_repository.resolve()
    )
    inventory_file = root / INVENTORY_PATH
    inventory_raw = inventory_file.read_bytes()
    inventory = json.loads(inventory_raw)
    if inventory_raw != canonical_json(inventory) + b"\n":
        fail("schema evidence inventory is not canonical JSON")
    if hashlib.sha256(inventory_raw).hexdigest() != INVENTORY_SHA256:
        fail("schema evidence inventory differs from the accepted V05-1 decision")

    catalog_path = root / "src/tiny_corpus_workbench/schema_catalog.py"
    schema_files = dict(_ast_value(catalog_path, "SCHEMA_FILES"))
    schema_root = root / "src/tiny_corpus_workbench/schemas"
    actual_schema_paths = {
        path.relative_to(root).as_posix()
        for path in schema_root.glob("*.schema.json")
    }
    expected_schema_paths = {
        item["path"] for item in inventory["schemas"]
    }
    _verify_inventory_scopes(
        root,
        inventory,
        expected_schema_paths,
    )
    if actual_schema_paths != expected_schema_paths:
        fail("packaged schema inventory is not exactly the v0.5 baseline")
    if set(schema_files.values()) | {"common-v0.5.schema.json"} != {
        Path(path).name for path in actual_schema_paths
    }:
        fail("schema catalog differs from the packaged v0.5 baseline")

    schemas = {
        path.name: json.loads(path.read_text("utf-8"))
        for path in schema_root.glob("*.schema.json")
    }
    _schema_registry(schemas)
    for schema_version, filename in schema_files.items():
        schema = schemas[filename]
        if schema.get("$id") != f"https://example.invalid/tcw/{filename}":
            fail(f"schema $id differs from catalog filename: {filename}")
        if _schema_version_consts(schema) != {schema_version}:
            fail(f"schema_version const differs from catalog: {filename}")
        if "/v0.5" not in schema_version or OLD_SCHEMA_FILE.search(filename):
            fail(f"active schema is not v0.5: {filename}")
        if "milestone" in set(_walk_keys(schema)):
            fail(f"schema defines milestone: {filename}")
    common = schemas["common-v0.5.schema.json"]
    if common.get("$id") != (
        "https://example.invalid/tcw/common-v0.5.schema.json"
    ):
        fail("common schema $id differs")
    if "milestone" in set(_walk_keys(common)):
        fail("common schema defines milestone")

    _verify_placement(schemas, schema_files, inventory)
    _verify_provenance(root, schemas, schema_files)
    _verify_writers_and_verifiers(root, inventory)

    schemas_by_version = {
        schema_version: schemas[filename]
        for schema_version, filename in schema_files.items()
    }
    schemas_by_version["common"] = common
    _verify_migration_evidence(
        root,
        base_repository,
        inventory,
        schemas_by_version,
    )

    for relative in {
        item["path"] for item in inventory["schema_emission_sources"]
    }:
        _, strings = _function_names_and_strings(root / relative)
        if any(
            OLD_SCHEMA.search(value) or OLD_SCHEMA_FILE.search(value)
            for value in strings
        ):
            fail(f"old schema dispatch remains in {relative}")

    for relative in FIXTURE_FILES:
        path = root / relative
        if path.suffix == ".json":
            encoded = canonical_json(json.loads(path.read_text("utf-8"))).decode(
                "utf-8"
            )
            if OLD_SCHEMA.search(encoded) or OLD_SCHEMA_FILE.search(encoded):
                fail(f"current fixture JSON contains an old schema: {relative}")

    forbidden_paths = (
        "fixtures/corpus/v0.4/",
        "fixtures/diagnosis/v0.2/",
        "fixtures/refinement/v0.3/",
        "`corpus/v0.4/",
        "`diagnosis/v0.2/",
        "`refinement/v0.3/",
    )
    for relative in USER_DOCUMENTS:
        text = (root / relative).read_text("utf-8")
        if any(value in text for value in forbidden_paths):
            fail(f"old active fixture path remains in {relative}")
        if OLD_SCHEMA.search(text) or OLD_SCHEMA_FILE.search(text):
            fail(f"old active schema instruction remains in {relative}")

    _verify_repository_metadata(root)
    print(
        "verified v0.5-only schema baseline: "
        f"{len(actual_schema_paths)} schemas, "
        f"{len(inventory['schema_emission_sources'])} executable files, "
        f"{len(inventory['tests'])} test files, "
        f"{len(FIXTURE_FILES)} fixture files, "
        f"{len(USER_DOCUMENTS)} user documents, "
        f"{len(REPOSITORY_METADATA)} repository metadata files"
    )


if __name__ == "__main__":
    try:
        verify()
    except AuditError as error:
        raise SystemExit(str(error)) from error
