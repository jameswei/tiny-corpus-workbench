from __future__ import annotations

import io
import copy
import hashlib
import importlib
import json
import os
import shutil
import tempfile
import unittest
import uuid
from concurrent.futures import ThreadPoolExecutor
from contextlib import redirect_stderr, redirect_stdout
from datetime import UTC, datetime
from pathlib import Path
from unittest import mock

from docling_core.types.doc import DocItemLabel, DoclingDocument, TableData

from tiny_corpus_workbench import cli
from tiny_corpus_workbench.artifacts import canonical_json
from tiny_corpus_workbench.domain import (
    InputError,
    IntegrityError,
    RuntimeContractError,
)
from tiny_corpus_workbench.v03 import (
    _diagnosis_report,
    diagnose,
    load_subject,
    verify_diagnosis,
)
from tiny_corpus_workbench.v03 import snapshot_tree
from tiny_corpus_workbench.verification import verify_observation
from tests.unit.test_unsupported_old_schemas import OLD_DIAGNOSIS_SCHEMA


SOURCE = Path("fixtures/golden/policy-memo.md")
# Frozen reviewed inventory for the v0.5 diagnosis migration.
BASE_REGRESSION_INVENTORY = {
    ("tests/unit/test_v03_diagnosis_workflow.py", "test_v03_diagnosis_is_deterministic_and_read_only"): ("restored", "tests.unit.test_diagnosis_workflow.DiagnosisWorkflowTests.test_observe_diagnose_verify_is_v05_deterministic_and_read_only"),
    ("tests/unit/test_v03_diagnosis_workflow.py", "test_partial_observation_is_supported"): ("restored", "tests.unit.test_diagnosis_workflow.DiagnosisWorkflowTests.test_partial_success_observation_with_canonical_docling_is_diagnosable"),
    ("tests/unit/test_v03_diagnosis_workflow.py", "test_existing_v02_diagnosis_remains_verifiable"): ("obsolete", "v0.5 deliberately rejects old diagnosis schemas with exit 2"),
    ("tests/unit/test_v03_diagnosis_workflow.py", "test_missing_or_inconsistent_canonical_document_never_publishes"): ("restored", "test_missing_canonical_artifact_is_exit_four_without_publication"),
    ("tests/unit/test_v03_diagnosis_workflow.py", "test_changed_input_and_schema_failure_never_publish"): ("restored", "test_input_and_staged_mutation_never_publish"),
    ("tests/unit/test_v03_diagnosis_workflow.py", "test_output_overlap_conflict_and_symlink_are_rejected"): ("restored", "test_unsafe_source_and_symlinked_publication_parent_are_rejected"),
    ("tests/unit/test_v03_diagnosis_workflow.py", "test_verifier_detects_inventory_hash_json_and_symlink_corruption"): ("restored", "test_verifier_detects_inventory_hash_json_and_node_tamper"),
    ("tests/unit/test_v03_diagnosis_workflow.py", "test_verifier_rejects_manifest_encoding_and_descriptor_mapping_tampering"): ("restored", "test_verifier_detects_inventory_hash_json_and_node_tamper"),
    ("tests/unit/test_v03_diagnosis_workflow.py", "test_verifier_rejects_self_consistent_v03_finding_metadata_tampering"): ("restored", "tests.unit.test_diagnosis_workflow.DiagnosisWorkflowTests.test_self_consistent_finding_metadata_tamper_is_rejected"),
    ("tests/unit/test_v03_diagnosis_workflow.py", "test_optional_subject_states_are_advisory"): ("restored", "test_subject_advisories_and_complete_source_identity"),
    ("tests/unit/test_v03_diagnosis_workflow.py", "test_diagnosis_identity_and_complete_subject_descriptor_are_verified"): ("restored", "test_subject_advisories_and_complete_source_identity"),
    ("tests/unit/test_v03_diagnosis_workflow.py", "test_runtime_drift_is_exit_six_without_publication"): ("restored", "test_cli_failures_have_exact_exit_and_stream_contracts"),
    ("tests/unit/test_v03_diagnosis_workflow.py", "test_v03_diagnosis_runtime_provenance_is_verified"): ("restored", "test_unsupported_recorded_provenance_is_exit_six"),
    ("tests/unit/test_v03_diagnosis_workflow.py", "test_cli_errors_are_sanitized_and_use_exact_streams"): ("restored", "test_cli_failures_have_exact_exit_and_stream_contracts"),
    ("tests/unit/test_diagnosis_workflow.py", "test_observe_diagnose_verify_is_deterministic_and_read_only"): ("restored", "tests.unit.test_diagnosis_workflow.DiagnosisWorkflowTests.test_observe_diagnose_verify_is_v05_deterministic_and_read_only"),
    ("tests/unit/test_diagnosis_workflow.py", "test_partial_success_is_accepted_and_corruption_is_detected"): ("restored", "tests.unit.test_diagnosis_workflow.DiagnosisWorkflowTests.test_partial_success_observation_corruption_is_rejected_and_advisory"),
    ("tests/unit/test_diagnosis_workflow.py", "test_unresolved_duplicate_caption_declarations_publish_one_valid_finding"): ("moved", "tests.unit.test_diagnosis_rules.DiagnosisRuleTests.test_duplicate_invalid_caption_declarations_emit_one_finding"),
    ("tests/unit/test_diagnosis_workflow.py", "test_canonical_collection_paths_are_required_before_publication"): ("restored", "tests.unit.test_diagnosis_workflow.DiagnosisWorkflowTests.test_canonical_collection_paths_are_required_before_publication"),
    ("tests/unit/test_diagnosis_workflow.py", "test_rerun_cannot_match_legacy_mismatched_self_refs"): ("restored", "tests.unit.test_diagnosis_workflow.DiagnosisWorkflowTests.test_rerun_cannot_match_legacy_mismatched_self_refs"),
    ("tests/unit/test_diagnosis_workflow.py", "test_output_overlap_is_rejected_without_observation_mutation"): ("restored", "test_diagnosis_output_cannot_be_inside_subject"),
    ("tests/unit/test_diagnosis_workflow.py", "test_unsafe_observation_source_key_cannot_escape_output_root"): ("restored", "test_unsafe_source_and_symlinked_publication_parent_are_rejected"),
    ("tests/unit/test_diagnosis_workflow.py", "test_symlinked_publication_parent_cannot_escape_output_root"): ("restored", "test_unsafe_source_and_symlinked_publication_parent_are_rejected"),
    ("tests/unit/test_diagnosis_workflow.py", "test_output_path_file_conflicts_are_invalid_input"): ("restored", "test_unsafe_source_and_symlinked_publication_parent_are_rejected"),
    ("tests/unit/test_diagnosis_workflow.py", "test_atomic_diagnosis_conflict_never_replaces_existing_run"): ("restored", "test_publication_collision_and_concurrent_race_are_atomic"),
    ("tests/unit/test_diagnosis_workflow.py", "test_concurrent_atomic_diagnosis_publication_has_one_winner"): ("restored", "test_publication_collision_and_concurrent_race_are_atomic"),
    ("tests/unit/test_diagnosis_workflow.py", "test_diagnosis_failures_are_sanitized_with_exact_exit_streams"): ("restored", "test_cli_failures_have_exact_exit_and_stream_contracts"),
    ("tests/unit/test_diagnosis_workflow.py", "test_usage_failures_have_no_stdout_and_publish_nothing"): ("restored", "test_cli_failures_have_exact_exit_and_stream_contracts"),
    ("tests/unit/test_diagnosis_workflow.py", "test_missing_canonical_artifact_is_exit_four_without_publication"): ("restored", "test_missing_canonical_artifact_is_exit_four_without_publication"),
    ("tests/unit/test_diagnosis_workflow.py", "test_observation_change_or_staged_failure_never_publishes"): ("restored", "test_input_and_staged_mutation_never_publish"),
    ("tests/unit/test_diagnosis_workflow.py", "test_staged_semantics_reject_duplicate_finding_identities"): ("restored", "tests.unit.test_diagnosis_workflow.DiagnosisWorkflowTests.test_staged_semantics_reject_duplicate_finding_identities"),
    ("tests/unit/test_diagnosis_workflow.py", "test_staged_byte_corruption_is_rejected_before_publication"): ("restored", "test_input_and_staged_mutation_never_publish"),
    ("tests/unit/test_diagnosis_workflow.py", "test_staged_directories_and_special_nodes_never_publish"): ("restored", "test_input_and_staged_mutation_never_publish"),
    ("tests/unit/test_diagnosis_workflow.py", "test_post_publication_manifest_loss_is_sanitized_integrity_exit"): ("restored", "test_verifier_detects_inventory_hash_json_and_node_tamper"),
    ("tests/unit/test_diagnosis_workflow.py", "test_post_publication_summary_requires_complete_integrity"): ("restored", "test_verifier_detects_inventory_hash_json_and_node_tamper"),
    ("tests/unit/test_diagnosis_workflow.py", "test_post_verification_publication_races_never_emit_summary"): ("restored", "test_publication_collision_and_concurrent_race_are_atomic"),
    ("tests/unit/test_diagnosis_workflow.py", "test_verifier_detects_inventory_and_content_failure_shapes"): ("restored", "test_verifier_detects_inventory_hash_json_and_node_tamper"),
    ("tests/unit/test_diagnosis_workflow.py", "test_optional_observation_states_are_advisory"): ("restored", "test_subject_advisories_and_complete_source_identity"),
    ("tests/unit/test_diagnosis_workflow.py", "test_supplied_observation_cross_checks_all_source_identity_fields"): ("restored", "test_subject_advisories_and_complete_source_identity"),
    ("tests/unit/test_diagnosis_workflow.py", "test_active_distribution_drift_is_runtime_exit"): ("restored", "test_cli_failures_have_exact_exit_and_stream_contracts"),
    ("tests/unit/test_diagnosis_workflow.py", "test_verifier_rejects_generic_evidence_for_every_rule"): ("moved", "tests.unit.test_diagnosis_rules.DiagnosisRuleTests.test_generic_evidence_is_rejected_for_every_base_rule"),
}
REVIEWED_TARGET_EQUIVALENCE = {
    (
        "tests/unit/test_v03_diagnosis_workflow.py",
        "test_partial_observation_is_supported",
    ): (
        "The restored workflow constructs PARTIAL_SUCCESS with a canonical "
        "Docling document and requires diagnosis plus exact verification."
    ),
    (
        "tests/unit/test_v03_diagnosis_workflow.py",
        "test_verifier_rejects_self_consistent_v03_finding_metadata_tampering",
    ): (
        "The restored verifier test rewrites schema-valid finding metadata, "
        "report bytes, and descriptors and still requires BROKEN integrity."
    ),
    (
        "tests/unit/test_diagnosis_workflow.py",
        "test_partial_success_is_accepted_and_corruption_is_detected",
    ): (
        "The restored workflow diagnoses a PARTIAL_SUCCESS observation, then "
        "requires corrupted subject rejection and advisory non-replay."
    ),
    (
        "tests/unit/test_diagnosis_workflow.py",
        "test_unresolved_duplicate_caption_declarations_publish_one_valid_finding",
    ): (
        "The rule test supplies the same duplicate unresolved caption reference "
        "and requires exactly one TCW-D006 finding."
    ),
    (
        "tests/unit/test_diagnosis_workflow.py",
        "test_verifier_rejects_generic_evidence_for_every_rule",
    ): (
        "The rule test supplies the same generic evidence shape to every base "
        "diagnosis rule and requires contract rejection."
    ),
    (
        "tests/unit/test_diagnosis_workflow.py",
        "test_canonical_collection_paths_are_required_before_publication",
    ): (
        "The restored workflow covers text, table, picture, group, and body "
        "reference path mismatches and requires no diagnosis publication."
    ),
    (
        "tests/unit/test_diagnosis_workflow.py",
        "test_rerun_cannot_match_legacy_mismatched_self_refs",
    ): (
        "The restored workflow applies the legacy index traversal and proves "
        "v0.5 rejects the mismatched self reference before publication."
    ),
    (
        "tests/unit/test_diagnosis_workflow.py",
        "test_staged_semantics_reject_duplicate_finding_identities",
    ): (
        "The restored workflow injects a duplicate finding identity and "
        "requires integrity exit 5 with no publication."
    ),
}


def docling(source: Path, destination: Path, model_root: Path):
    destination.mkdir(parents=True)
    document = DoclingDocument(name="v05-diagnosis")
    document.add_text(
        DocItemLabel.TEXT,
        "Stable\u00a0 body  content.\r\nInter-\noperable " + "text " * 40,
    )
    document.save_as_json(destination / "document.json")
    document.save_as_markdown(destination / "document.md")
    return "success", {"name": "DoclingDocument", "version": "1.10.0"}


def partial_docling(source: Path, destination: Path, model_root: Path):
    _status, schema = docling(source, destination, model_root)
    return "partial_success", schema


def mismatched_path_docling(kind: str):
    def convert(source: Path, destination: Path, model_root: Path):
        destination.mkdir(parents=True)
        document = DoclingDocument(name=f"mismatched-{kind}")
        if kind in {"text", "body_ref"}:
            document.add_text(DocItemLabel.TEXT, "Broken path")
        elif kind == "table":
            document.add_table(
                TableData(table_cells=[], num_rows=0, num_cols=0)
            )
        elif kind == "picture":
            document.add_picture()
        else:
            group = document.add_group()
            document.add_text(DocItemLabel.TEXT, "Grouped text", parent=group)
        payload = document.model_dump(
            mode="json",
            by_alias=True,
            exclude_none=True,
        )
        if kind == "body_ref":
            payload["body"]["children"][0]["$ref"] = "#/texts/99"
        else:
            collection = {
                "text": "texts",
                "table": "tables",
                "picture": "pictures",
                "group": "groups",
            }[kind]
            payload[collection][0]["self_ref"] = f"#/{collection}/99"
        DoclingDocument.model_validate(payload)
        (destination / "document.json").write_bytes(canonical_json(payload))
        (destination / "document.md").write_text("# mismatched path\n", "utf-8")
        return "success", {"name": "DoclingDocument", "version": "1.10.0"}

    return convert


def markitdown(source: Path, destination: Path):
    destination.mkdir(parents=True)
    (destination / "document.md").write_text("# stable view\n", "utf-8")


class FixedDateTime(datetime):
    @classmethod
    def now(cls, tz=None):
        return cls(2026, 7, 26, 12, 0, tzinfo=UTC)


class DiagnosisWorkflowTests(unittest.TestCase):
    def invoke(self, *arguments: str) -> tuple[int, str, str]:
        stdout, stderr = io.StringIO(), io.StringIO()
        with redirect_stdout(stdout), redirect_stderr(stderr):
            code = cli.main(list(arguments))
        return code, stdout.getvalue(), stderr.getvalue()

    def observation(self, root: Path, converter=docling) -> Path:
        with mock.patch(
            "tiny_corpus_workbench.extractors.docling.convert",
            side_effect=converter,
        ), mock.patch(
            "tiny_corpus_workbench.extractors.markitdown.convert",
            side_effect=markitdown,
        ):
            code, published = cli.observe(str(SOURCE), root, Path("unused"))
        self.assertIn(int(code), (0, 3))
        return published

    def diagnose(self, observation: Path, output: Path) -> Path:
        code, stdout, stderr = self.invoke(
            "diagnose",
            str(observation),
            "--output-root",
            str(output),
        )
        self.assertEqual(code, 0, stderr)
        self.assertEqual(stderr, "")
        return Path(json.loads(stdout)["manifest"]).parent

    def test_observe_diagnose_verify_is_v05_deterministic_and_read_only(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            observation = self.observation(root / "observations")
            before = snapshot_tree(observation)
            first = self.diagnose(observation, root / "first")
            second = self.diagnose(observation, root / "second")
            self.assertEqual(snapshot_tree(observation), before)
            self.assertEqual(
                (first / "findings.json").read_bytes(),
                (second / "findings.json").read_bytes(),
            )
            findings = json.loads((first / "findings.json").read_text("utf-8"))
            manifest = json.loads(
                (first / "diagnosis-manifest.json").read_text("utf-8")
            )
            self.assertEqual(findings["schema_version"], "tcw.finding-set/v0.5")
            self.assertEqual(
                manifest["schema_version"], "tcw.diagnosis-manifest/v0.5"
            )
            self.assertEqual(
                manifest["build_provenance"]["command_id"], "tcw.diagnose"
            )
            self.assertNotIn("runtime", manifest)
            self.assertNotIn("milestone", manifest)
            self.assertEqual(
                manifest["build_provenance"]["python"]["major_minor"], "3.12"
            )
            self.assertIn(
                "jsonschema", manifest["build_provenance"]["dependencies"]
            )
            code, stdout, stderr = self.invoke(
                "verify-diagnosis",
                str(first),
                "--subject",
                str(observation),
            )
            self.assertEqual((code, stderr), (0, ""))
            result = json.loads(stdout)
            self.assertEqual(result["artifact_integrity"]["status"], "VERIFIED")
            self.assertEqual(result["subject_state"]["status"], "MATCH")
            self.assertEqual(result["derivation_state"]["status"], "MATCH")
            self.assertEqual(
                result["build_provenance"]["command_id"],
                "tcw.verify-diagnosis",
            )

    def test_partial_success_observation_with_canonical_docling_is_diagnosable(
        self,
    ) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            observation = self.observation(
                root / "observations",
                partial_docling,
            )
            observation_manifest = json.loads(
                (observation / "manifest.json").read_text("utf-8")
            )
            self.assertEqual(observation_manifest["status"], "PARTIAL_SUCCESS")
            docling_result = next(
                result
                for result in observation_manifest["extractors"]
                if result["name"] == "docling"
            )
            self.assertEqual(docling_result["status"], "PARTIAL_SUCCESS")
            self.assertTrue((observation / "docling/document.json").is_file())

            diagnosis = self.diagnose(observation, root / "diagnoses")
            result = verify_diagnosis(diagnosis, observation)
            self.assertEqual(result["artifact_integrity"]["status"], "VERIFIED")
            self.assertEqual(result["subject_state"]["status"], "MATCH")
            self.assertEqual(result["derivation_state"]["status"], "MATCH")

    def test_partial_success_observation_corruption_is_rejected_and_advisory(
        self,
    ) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            observation = self.observation(
                root / "observations",
                partial_docling,
            )
            diagnosis = self.diagnose(observation, root / "diagnoses")
            corrupted = root / "corrupted-observation" / observation.name
            corrupted.parent.mkdir()
            shutil.copytree(observation, corrupted)
            (corrupted / "docling/document.json").write_text("{", "utf-8")

            output = root / "rejected-diagnosis"
            code, stdout, stderr = self.invoke(
                "diagnose",
                str(corrupted),
                "--output-root",
                str(output),
            )
            self.assertEqual(code, 2)
            self.assertEqual(stdout, "")
            self.assertNotEqual(stderr, "")
            self.assertFalse(output.exists())

            result = verify_diagnosis(diagnosis, corrupted)
            self.assertEqual(result["artifact_integrity"]["status"], "VERIFIED")
            self.assertNotEqual(result["subject_state"]["status"], "MATCH")
            self.assertEqual(result["derivation_state"]["status"], "NOT_CHECKED")

    def test_canonical_collection_paths_are_required_before_publication(
        self,
    ) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            for kind in ("text", "table", "picture", "group", "body_ref"):
                with self.subTest(kind=kind):
                    case = root / kind
                    observation = self.observation(
                        case / "observations",
                        mismatched_path_docling(kind),
                    )
                    self.assertEqual(
                        verify_observation(observation)["artifact_integrity"][
                            "status"
                        ],
                        "VERIFIED",
                    )
                    output = case / "diagnoses"
                    code, stdout, stderr = self.invoke(
                        "diagnose",
                        str(observation),
                        "--output-root",
                        str(output),
                    )
                    self.assertIn(code, (2, 4))
                    self.assertEqual(stdout, "")
                    self.assertNotEqual(stderr, "")
                    self.assertFalse(output.exists())

    def test_rerun_cannot_match_legacy_mismatched_self_refs(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            observation = self.observation(
                root / "observations",
                mismatched_path_docling("text"),
            )

            def legacy_index(payload: dict) -> dict:
                values = {
                    payload[name]["self_ref"]: payload[name]
                    for name in ("body", "furniture")
                }
                for collection in (
                    "texts",
                    "pictures",
                    "tables",
                    "key_value_items",
                    "form_items",
                    "field_regions",
                    "field_items",
                    "groups",
                ):
                    for item in payload.get(collection, []):
                        values[item["self_ref"]] = item
                return values

            def legacy_reading(payload: dict, index: dict) -> list[dict]:
                ordered: list[dict] = []
                visited: set[str] = set()

                def visit(item: dict) -> None:
                    reference = item["self_ref"]
                    if reference in visited:
                        return
                    visited.add(reference)
                    if reference != "#/body":
                        ordered.append(item)
                    for child in item.get("children", []):
                        target = index.get(child["$ref"])
                        if target is not None:
                            visit(target)

                visit(payload["body"])
                return ordered

            with mock.patch(
                "tiny_corpus_workbench.v03._index",
                side_effect=legacy_index,
            ), mock.patch(
                "tiny_corpus_workbench.v03._reading_order",
                side_effect=legacy_reading,
            ):
                output = root / "legacy-diagnoses"
                code, stdout, stderr = self.invoke(
                    "diagnose",
                    str(observation),
                    "--output-root",
                    str(output),
                )
            self.assertEqual(code, 5)
            self.assertEqual(stdout, "")
            self.assertIn("self_ref", stderr)
            self.assertFalse(output.exists())

    def test_old_diagnosis_input_exits_two(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root / "diagnosis-manifest.json").write_text(
                json.dumps({"schema_version": OLD_DIAGNOSIS_SCHEMA}) + "\n",
                "utf-8",
            )
            code, stdout, stderr = self.invoke("verify-diagnosis", str(root))
            self.assertEqual(code, 2)
            self.assertEqual(stdout, "")
            self.assertIn("v0.5 diagnosis", stderr)

    def test_missing_canonical_artifact_is_exit_four_without_publication(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            observation = self.observation(root / "observations")
            (observation / "docling/document.json").unlink()
            output = root / "diagnoses"
            code, stdout, stderr = self.invoke(
                "diagnose",
                str(observation),
                "--output-root",
                str(output),
            )
            self.assertEqual(code, 4)
            self.assertEqual(stdout, "")
            self.assertIn("canonical Docling artifact", stderr)
            self.assertFalse(output.exists())

    def test_diagnosis_output_cannot_be_inside_subject(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            observation = self.observation(root / "observations")
            before = snapshot_tree(observation)
            code, stdout, stderr = self.invoke(
                "diagnose",
                str(observation),
                "--output-root",
                str(observation / "nested"),
            )
            self.assertEqual(code, 2)
            self.assertEqual(stdout, "")
            self.assertIn("output must not be inside", stderr)
            self.assertEqual(snapshot_tree(observation), before)

    def test_unsupported_recorded_provenance_is_exit_six(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            observation = self.observation(root / "observations")
            diagnosis = self.diagnose(observation, root / "diagnoses")
            manifest_path = diagnosis / "diagnosis-manifest.json"
            manifest = json.loads(manifest_path.read_text("utf-8"))
            manifest["build_provenance"]["provenance_id"] = "0" * 64
            manifest_path.write_text(
                json.dumps(manifest, sort_keys=True, separators=(",", ":")) + "\n",
                "utf-8",
            )
            code, stdout, stderr = self.invoke(
                "verify-diagnosis", str(diagnosis)
            )
            self.assertEqual(code, 6)
            self.assertEqual(stdout, "")
            self.assertEqual(
                stderr,
                "recorded provenance is unsupported by this v0.5 package\n",
            )

    def test_publication_collision_and_concurrent_race_are_atomic(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            observation = self.observation(root / "observations")
            fixed_uuid = uuid.UUID("11111111-1111-1111-1111-111111111111")
            with mock.patch(
                "tiny_corpus_workbench.v03.datetime", FixedDateTime
            ), mock.patch(
                "tiny_corpus_workbench.v03.uuid.uuid4",
                return_value=fixed_uuid,
            ):
                first = diagnose(observation, root / "diagnoses")
                with self.assertRaises(IntegrityError):
                    diagnose(observation, root / "diagnoses")
            self.assertTrue((first / "diagnosis-manifest.json").is_file())

            race_output = root / "race"

            def publish() -> int:
                try:
                    diagnose(observation, race_output)
                    return 0
                except IntegrityError:
                    return 5

            with mock.patch(
                "tiny_corpus_workbench.v03.datetime", FixedDateTime
            ), mock.patch(
                "tiny_corpus_workbench.v03.uuid.uuid4",
                return_value=fixed_uuid,
            ), ThreadPoolExecutor(max_workers=2) as executor:
                outcomes = list(executor.map(lambda _: publish(), range(2)))
            self.assertEqual(sorted(outcomes), [0, 5])
            self.assertEqual(
                len(list(race_output.rglob("diagnosis-manifest.json"))), 1
            )
            self.assertFalse(
                any(path.name.startswith(".staging-") for path in root.rglob("*"))
            )

    def test_unsafe_source_and_symlinked_publication_parent_are_rejected(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            observation = self.observation(root / "observations")
            subject = load_subject(observation)
            unsafe = copy.deepcopy(subject)
            unsafe["source"]["key"] = "../escape"
            with mock.patch(
                "tiny_corpus_workbench.v03.load_subject",
                return_value=unsafe,
            ), self.assertRaises(InputError):
                diagnose(observation, root / "unsafe")

            output = root / "output"
            outside = root / "outside"
            output.mkdir()
            outside.mkdir()
            (output / subject["source"]["key"]).symlink_to(
                outside, target_is_directory=True
            )
            with self.assertRaises(InputError):
                diagnose(observation, output)
            self.assertFalse(
                any(outside.rglob("diagnosis-manifest.json"))
            )

    def test_input_and_staged_mutation_never_publish(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            observation = self.observation(root / "observations")
            output = root / "input-mutation"
            original_report = _diagnosis_report

            def mutate_input(findings):
                (observation / "comparison.json").write_bytes(b"changed")
                return original_report(findings)

            with mock.patch(
                "tiny_corpus_workbench.v03._diagnosis_report",
                side_effect=mutate_input,
            ), self.assertRaises(IntegrityError):
                diagnose(observation, output)
            self.assertFalse(any(output.rglob("diagnosis-manifest.json")))

            clean_observation = self.observation(root / "clean-observations")
            staged_output = root / "staged-mutation"
            from tiny_corpus_workbench.v03 import _artifact as real_artifact

            injected = False

            def inject_staged_node(path, staging, role, media_type):
                nonlocal injected
                if not injected:
                    (staging / "unexpected").mkdir()
                    injected = True
                return real_artifact(path, staging, role, media_type)

            with mock.patch(
                "tiny_corpus_workbench.v03._artifact",
                side_effect=inject_staged_node,
            ), self.assertRaises(IntegrityError):
                diagnose(clean_observation, staged_output)
            self.assertFalse(
                any(staged_output.rglob("diagnosis-manifest.json"))
            )

    def test_staged_semantics_reject_duplicate_finding_identities(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            observation = self.observation(root / "observations")
            from tiny_corpus_workbench.v03 import (
                make_finding_set as real_make_finding_set,
            )

            def duplicate(subject):
                finding_set = real_make_finding_set(subject)
                finding_set["findings"].append(
                    copy.deepcopy(finding_set["findings"][0])
                )
                finding_set["summary"]["total"] += 1
                return finding_set

            output = root / "diagnoses"
            with mock.patch(
                "tiny_corpus_workbench.v03.make_finding_set",
                side_effect=duplicate,
            ):
                code, stdout, stderr = self.invoke(
                    "diagnose",
                    str(observation),
                    "--output-root",
                    str(output),
                )
            self.assertEqual(code, 5)
            self.assertEqual(stdout, "")
            self.assertNotEqual(stderr, "")
            self.assertFalse(
                any(output.rglob("diagnosis-manifest.json"))
            )

    def test_verifier_detects_inventory_hash_json_and_node_tamper(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            observation = self.observation(root / "observations")
            diagnosis = self.diagnose(observation, root / "diagnoses")

            operations = {}
            unexpected = root / "unexpected"
            shutil.copytree(diagnosis, unexpected)
            (unexpected / "extra.txt").write_text("extra", "utf-8")
            operations["inventory"] = unexpected

            changed_hash = root / "changed-hash"
            shutil.copytree(diagnosis, changed_hash)
            (changed_hash / "report.md").write_text("changed\n", "utf-8")
            operations["hash"] = changed_hash

            invalid_json = root / "invalid-json"
            shutil.copytree(diagnosis, invalid_json)
            (invalid_json / "findings.json").write_text("{", "utf-8")
            operations["json"] = invalid_json

            invalid_node = root / "invalid-node"
            shutil.copytree(diagnosis, invalid_node)
            (invalid_node / "report.md").unlink()
            (invalid_node / "report.md").symlink_to(root / "missing")
            operations["node"] = invalid_node

            for name, changed in operations.items():
                with self.subTest(operation=name):
                    result = verify_diagnosis(changed)
                    self.assertNotEqual(
                        result["artifact_integrity"]["status"], "VERIFIED"
                    )

    def test_self_consistent_finding_metadata_tamper_is_rejected(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            observation = self.observation(root / "observations")
            diagnosis = self.diagnose(observation, root / "diagnoses")
            manifest_path = diagnosis / "diagnosis-manifest.json"
            findings_path = diagnosis / "findings.json"
            manifest = json.loads(manifest_path.read_text("utf-8"))
            findings = json.loads(findings_path.read_text("utf-8"))
            findings["findings"][0]["summary"] = "Tampered but schema-valid"
            findings_path.write_bytes(canonical_json(findings))
            (diagnosis / "report.md").write_bytes(_diagnosis_report(findings))
            for descriptor in manifest["artifacts"]:
                path = diagnosis / descriptor["path"]
                descriptor["size"] = path.stat().st_size
                descriptor["sha256"] = hashlib.sha256(
                    path.read_bytes()
                ).hexdigest()
            manifest_path.write_bytes(canonical_json(manifest))

            result = verify_diagnosis(diagnosis)
            self.assertEqual(result["artifact_integrity"]["status"], "BROKEN")
            self.assertTrue(
                any(
                    issue["code"] == "MANIFEST_INVALID"
                    for issue in result["artifact_integrity"]["issues"]
                ),
                result,
            )

    def test_subject_advisories_and_complete_source_identity(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            observation = self.observation(root / "observations")
            diagnosis = self.diagnose(observation, root / "diagnoses")
            self.assertEqual(
                verify_diagnosis(diagnosis)["subject_state"]["status"],
                "NOT_CHECKED",
            )
            self.assertEqual(
                verify_diagnosis(
                    diagnosis, root / "missing-subject"
                )["subject_state"]["status"],
                "MISSING",
            )
            subject = load_subject(observation)
            replacements = {
                "key": subject["source"]["key"] + "-changed",
                "media_type": "text/plain",
                "size": subject["source"]["size"] + 1,
                "sha256": "f" * 64,
            }
            for field, replacement in replacements.items():
                with self.subTest(field=field):
                    changed = copy.deepcopy(subject)
                    changed["source"][field] = replacement
                    with mock.patch(
                        "tiny_corpus_workbench.v03.load_subject",
                        return_value=changed,
                    ):
                        result = verify_diagnosis(diagnosis, observation)
                    self.assertEqual(
                        result["subject_state"]["status"], "CHANGED"
                    )
                    self.assertEqual(
                        result["derivation_state"]["status"], "NOT_CHECKED"
                    )

    def test_cli_failures_have_exact_exit_and_stream_contracts(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            cases = [
                (
                    ("verify-diagnosis", str(root / "missing")),
                    2,
                    "verification requires a v0.5 diagnosis\n",
                ),
                (
                    ("diagnose", str(root / "missing")),
                    2,
                    "DOCUMENT_DIRECTORY must be one local non-symlink directory\n",
                ),
            ]
            for arguments, expected_code, expected_stderr in cases:
                with self.subTest(arguments=arguments):
                    code, stdout, stderr = self.invoke(*arguments)
                    self.assertEqual(code, expected_code)
                    self.assertEqual(stdout, "")
                    self.assertEqual(stderr, expected_stderr)

            observation = self.observation(root / "observations")
            with mock.patch(
                "tiny_corpus_workbench.v03.active_build_provenance",
                side_effect=RuntimeContractError(
                    "active runtime does not match this package provenance registry"
                ),
            ):
                code, stdout, stderr = self.invoke(
                    "diagnose",
                    str(observation),
                    "--output-root",
                    str(root / "diagnoses"),
                )
            self.assertEqual(code, 6)
            self.assertEqual(stdout, "")
            self.assertEqual(
                stderr,
                "active runtime does not match this package provenance registry\n",
            )

    def test_base_regression_inventory_is_complete_and_classified(self) -> None:
        self.assertEqual(len(BASE_REGRESSION_INVENTORY), 40)
        source_counts = {
            source: sum(
                base_source == source
                for base_source, _test_name in BASE_REGRESSION_INVENTORY
            )
            for source in {
                "tests/unit/test_v03_diagnosis_workflow.py",
                "tests/unit/test_diagnosis_workflow.py",
            }
        }
        self.assertEqual(
            source_counts,
            {
                "tests/unit/test_v03_diagnosis_workflow.py": 14,
                "tests/unit/test_diagnosis_workflow.py": 26,
            },
        )
        classifications = {
            classification
            for classification, _target in BASE_REGRESSION_INVENTORY.values()
        }
        self.assertEqual(classifications, {"restored", "moved", "obsolete"})
        counts = {
            classification: sum(
                value[0] == classification
                for value in BASE_REGRESSION_INVENTORY.values()
            )
            for classification in classifications
        }
        self.assertEqual(counts, {"restored": 37, "moved": 2, "obsolete": 1})
        moved = {
            key: target
            for key, (classification, target) in BASE_REGRESSION_INVENTORY.items()
            if classification == "moved"
        }
        self.assertEqual(
            set(moved),
            {
                key
                for key in REVIEWED_TARGET_EQUIVALENCE
                if BASE_REGRESSION_INVENTORY[key][0] == "moved"
            },
        )
        self.assertEqual(len(REVIEWED_TARGET_EQUIVALENCE), 8)
        for key, equivalence in REVIEWED_TARGET_EQUIVALENCE.items():
            target = BASE_REGRESSION_INVENTORY[key][1]
            with self.subTest(base_test=key, current_target=target):
                module_name, class_name, method_name = target.rsplit(".", 2)
                module = importlib.import_module(module_name)
                test_class = getattr(module, class_name)
                self.assertTrue(callable(getattr(test_class, method_name)))
                self.assertNotEqual(equivalence.strip(), "")
        obsolete = {
            key
            for key, (classification, _reason) in BASE_REGRESSION_INVENTORY.items()
            if classification == "obsolete"
        }
        self.assertEqual(
            obsolete,
            {
                (
                    "tests/unit/test_v03_diagnosis_workflow.py",
                    "test_existing_v02_diagnosis_remains_verifiable",
                )
            },
        )


if __name__ == "__main__":
    unittest.main()
