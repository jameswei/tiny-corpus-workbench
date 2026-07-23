from __future__ import annotations

import io
import hashlib
import json
import os
import re
import shutil
import tempfile
import unittest
from concurrent.futures import ThreadPoolExecutor
from contextlib import redirect_stderr, redirect_stdout
from pathlib import Path
from threading import Barrier
from unittest import mock

from docling_core.types.doc import (
    DoclingDocument,
    DocItemLabel,
    TableCell,
    TableData,
)

from tiny_corpus_workbench import cli
from tiny_corpus_workbench.artifacts import canonical_json
from tiny_corpus_workbench.diagnosis import (
    RULESET_DESCRIPTOR,
    SEVERITY_BY_RULE,
    SUMMARY_BY_RULE,
    _summary,
    make_finding_set,
    render_report,
)
from tiny_corpus_workbench.diagnosis import AtomicDiagnosis, snapshot_tree
from tiny_corpus_workbench.domain import InputError, IntegrityError
from tiny_corpus_workbench.verification import verify_observation


SOURCE = Path("fixtures/golden/policy-memo.md")


def fake_docling(source: Path, destination: Path, model_root: Path):
    destination.mkdir(parents=True)
    document = DoclingDocument(name="diagnosis-workflow")
    document.add_text(DocItemLabel.TEXT, "Stable body content. " * 20)
    document.save_as_json(destination / "document.json")
    document.save_as_markdown(destination / "document.md")
    return "success", {"name": "DoclingDocument", "version": "1.10.0"}


def partial_docling(source: Path, destination: Path, model_root: Path):
    _, schema = fake_docling(source, destination, model_root)
    return "partial_success", schema


def unresolved_caption_docling(source: Path, destination: Path, model_root: Path):
    destination.mkdir(parents=True)
    document = DoclingDocument(name="unresolved-caption")
    document.add_text(DocItemLabel.TEXT, "Stable body content. " * 20)
    document.add_table(
        TableData(
            table_cells=[
                TableCell(
                    start_row_offset_idx=0,
                    end_row_offset_idx=1,
                    start_col_offset_idx=0,
                    end_col_offset_idx=1,
                    text="Cell",
                )
            ],
            num_rows=1,
            num_cols=1,
        )
    )
    payload = document.model_dump(mode="json", by_alias=True, exclude_none=True)
    payload["tables"][0]["captions"] = [
        {"$ref": "#/texts/99"},
        {"$ref": "#/texts/99"},
    ]
    DoclingDocument.model_validate(payload)
    (destination / "document.json").write_bytes(canonical_json(payload))
    (destination / "document.md").write_text("# unresolved caption\n", "utf-8")
    return "success", {"name": "DoclingDocument", "version": "1.10.0"}


def mismatched_path_docling(kind: str):
    def convert(source: Path, destination: Path, model_root: Path):
        destination.mkdir(parents=True)
        document = DoclingDocument(name=f"mismatched-{kind}")
        if kind in {"text", "body_ref"}:
            document.add_text(DocItemLabel.TEXT, "Broken \ufffd path")
        elif kind == "table":
            document.add_table(
                TableData(
                    table_cells=[],
                    num_rows=0,
                    num_cols=0,
                )
            )
        elif kind == "picture":
            document.add_picture()
        elif kind == "group":
            group = document.add_group()
            document.add_text(DocItemLabel.TEXT, "Grouped text", parent=group)
        payload = document.model_dump(mode="json", by_alias=True, exclude_none=True)
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


def fake_markitdown(source: Path, destination: Path):
    destination.mkdir(parents=True)
    (destination / "document.md").write_text("# stable view\n", "utf-8")


class DiagnosisWorkflowTests(unittest.TestCase):
    def invoke(self, *arguments: str) -> tuple[int, str, str]:
        stdout, stderr = io.StringIO(), io.StringIO()
        with redirect_stdout(stdout), redirect_stderr(stderr):
            code = cli.main(list(arguments))
        return code, stdout.getvalue(), stderr.getvalue()

    def observation(self, root: Path, docling=fake_docling) -> Path:
        with mock.patch(
            "tiny_corpus_workbench.extractors.docling.convert", side_effect=docling
        ), mock.patch(
            "tiny_corpus_workbench.extractors.markitdown.convert",
            side_effect=fake_markitdown,
        ):
            code, published = cli.observe(str(SOURCE), root, Path("unused"))
        self.assertIn(int(code), (0, 3))
        return published

    def test_observe_diagnose_verify_is_deterministic_and_read_only(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            observation = self.observation(root / "observations")
            before = {
                path.relative_to(observation).as_posix(): (
                    path.stat().st_mode,
                    path.stat().st_mtime_ns,
                    path.read_bytes(),
                )
                for path in observation.rglob("*")
                if path.is_file()
            }
            outputs = []
            for output_name in ("first", "second"):
                code, stdout, stderr = self.invoke(
                    "diagnose",
                    str(observation),
                    "--output-root",
                    str(root / output_name),
                )
                self.assertEqual(code, 0)
                self.assertEqual(stderr, "")
                self.assertEqual(len(stdout.splitlines()), 1)
                summary = json.loads(stdout)
                self.assertEqual(summary["status"], "NO_FINDINGS")
                outputs.append(Path(summary["manifest"]).parent)
            self.assertEqual(
                (outputs[0] / "findings.json").read_bytes(),
                (outputs[1] / "findings.json").read_bytes(),
            )
            self.assertEqual(
                (outputs[0] / "report.md").read_bytes(),
                (outputs[1] / "report.md").read_bytes(),
            )
            self.assertNotEqual(outputs[0].name, outputs[1].name)
            self.assertEqual(
                json.loads((outputs[0] / "findings.json").read_text("utf-8"))[
                    "diagnosis_id"
                ],
                json.loads((outputs[1] / "findings.json").read_text("utf-8"))[
                    "diagnosis_id"
                ],
            )
            code, stdout, stderr = self.invoke(
                "verify-diagnosis",
                str(outputs[0]),
                "--observation",
                str(observation),
            )
            self.assertEqual(code, 0)
            self.assertEqual(stderr, "")
            result = json.loads(stdout)
            self.assertEqual(result["artifact_integrity"]["status"], "VERIFIED")
            self.assertEqual(result["observation_state"]["status"], "MATCH")
            self.assertEqual(result["derivation_state"]["status"], "MATCH")
            after = {
                path.relative_to(observation).as_posix(): (
                    path.stat().st_mode,
                    path.stat().st_mtime_ns,
                    path.read_bytes(),
                )
                for path in observation.rglob("*")
                if path.is_file()
            }
            self.assertEqual(after, before)

    def test_partial_success_is_accepted_and_corruption_is_detected(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            observation = self.observation(root / "observations", partial_docling)
            code, stdout, stderr = self.invoke(
                "diagnose", str(observation), "--output-root", str(root / "diagnoses")
            )
            self.assertEqual(code, 0)
            self.assertEqual(stderr, "")
            diagnosis = Path(json.loads(stdout)["manifest"]).parent
            copied = root / "corrupt" / diagnosis.name
            copied.parent.mkdir()
            shutil.copytree(diagnosis, copied)
            (copied / "report.md").write_text("# replaced\n", "utf-8")
            code, stdout, stderr = self.invoke("verify-diagnosis", str(copied))
            self.assertEqual(code, 5)
            self.assertEqual(stderr, "")
            self.assertEqual(
                json.loads(stdout)["artifact_integrity"]["status"],
                "INTEGRITY_MISMATCH",
            )

    def test_unresolved_duplicate_caption_declarations_publish_one_valid_finding(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            observation = self.observation(
                root / "observations", unresolved_caption_docling
            )
            code, stdout, stderr = self.invoke(
                "diagnose", str(observation), "--output-root", str(root / "diagnoses")
            )
            self.assertEqual(code, 0)
            self.assertEqual(stderr, "")
            diagnosis = Path(json.loads(stdout)["manifest"]).parent
            finding_set = json.loads(
                (diagnosis / "findings.json").read_text("utf-8")
            )
            invalid = [
                item
                for item in finding_set["findings"]
                if item["rule_id"] == "TCW-D006"
                and item["evidence"]["relationship_kind"]
                == "invalid_declared_caption"
            ]
            self.assertEqual(len(invalid), 1)
            self.assertEqual(invalid[0]["evidence"]["declared_ref"], "#/texts/99")
            code, stdout, stderr = self.invoke(
                "verify-diagnosis",
                str(diagnosis),
                "--observation",
                str(observation),
            )
            self.assertEqual(code, 0)
            self.assertEqual(stderr, "")
            result = json.loads(stdout)
            self.assertEqual(result["artifact_integrity"]["status"], "VERIFIED")
            self.assertEqual(result["derivation_state"]["status"], "MATCH")

    def test_canonical_collection_paths_are_required_before_publication(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            for kind in ("text", "table", "picture", "group", "body_ref"):
                with self.subTest(kind=kind):
                    case_root = root / kind
                    observation = self.observation(
                        case_root / "observations",
                        mismatched_path_docling(kind),
                    )
                    self.assertEqual(
                        verify_observation(observation)["artifact_integrity"][
                            "status"
                        ],
                        "VERIFIED",
                    )
                    before = snapshot_tree(observation)
                    output = case_root / "diagnoses"
                    code, stdout, stderr = self.invoke(
                        "diagnose",
                        str(observation),
                        "--output-root",
                        str(output),
                    )
                    self.assertEqual(code, 4)
                    self.assertEqual(stdout, "")
                    self.assertTrue(
                        "canonical Docling artifact paths" in stderr
                        or "no usable Docling result" in stderr
                    )
                    self.assertFalse(output.exists())
                    self.assertEqual(snapshot_tree(observation), before)

    def test_rerun_cannot_match_legacy_mismatched_self_refs(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            observation = self.observation(
                root / "observations", mismatched_path_docling("text")
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
                "tiny_corpus_workbench.diagnosis._index",
                side_effect=legacy_index,
            ), mock.patch(
                "tiny_corpus_workbench.diagnosis._reading_order",
                side_effect=legacy_reading,
            ):
                code, stdout, stderr = self.invoke(
                    "diagnose",
                    str(observation),
                    "--output-root",
                    str(root / "legacy-diagnoses"),
                )
            self.assertEqual(code, 0)
            self.assertEqual(stderr, "")
            diagnosis = Path(json.loads(stdout)["manifest"]).parent
            code, stdout, stderr = self.invoke(
                "verify-diagnosis",
                str(diagnosis),
                "--observation",
                str(observation),
            )
            self.assertEqual(code, 0)
            self.assertEqual(stderr, "")
            result = json.loads(stdout)
            self.assertEqual(result["artifact_integrity"]["status"], "VERIFIED")
            self.assertEqual(result["observation_state"]["status"], "MATCH")
            self.assertEqual(result["derivation_state"]["status"], "ERROR")

    def test_output_overlap_is_rejected_without_observation_mutation(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            observation = self.observation(root / "observations")
            alias = root / "observation-alias"
            alias.symlink_to(observation, target_is_directory=True)
            cases = (
                observation,
                observation.parents[1],
                alias,
            )
            for output in cases:
                with self.subTest(output=output):
                    before = snapshot_tree(observation)
                    code, stdout, stderr = self.invoke(
                        "diagnose",
                        str(observation),
                        "--output-root",
                        str(output),
                    )
                    self.assertEqual(code, 2)
                    self.assertEqual(stdout, "")
                    self.assertIn("must not overlap", stderr)
                    self.assertEqual(snapshot_tree(observation), before)

    def test_unsafe_observation_source_key_cannot_escape_output_root(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            for label in ("traversal", "absolute"):
                with self.subTest(label=label):
                    case_root = root / label
                    observation = self.observation(case_root / "observations")
                    manifest_path = observation / "manifest.json"
                    manifest = json.loads(manifest_path.read_text("utf-8"))
                    escaped = (
                        case_root / "escaped"
                        if label == "traversal"
                        else root / "absolute-escaped"
                    )
                    manifest["source"]["key"] = (
                        "../escaped" if label == "traversal" else str(escaped)
                    )
                    manifest_path.write_bytes(canonical_json(manifest))
                    self.assertEqual(
                        verify_observation(observation)["artifact_integrity"][
                            "status"
                        ],
                        "VERIFIED",
                    )
                    before = snapshot_tree(observation)
                    output = case_root / "diagnoses"
                    code, stdout, stderr = self.invoke(
                        "diagnose",
                        str(observation),
                        "--output-root",
                        str(output),
                    )
                    self.assertEqual(code, 2)
                    self.assertEqual(stdout, "")
                    self.assertIn("not a safe path component", stderr)
                    self.assertFalse(output.exists())
                    self.assertFalse(escaped.exists())
                    self.assertEqual(snapshot_tree(observation), before)

    def test_symlinked_publication_parent_cannot_escape_output_root(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            observation = self.observation(root / "observations")
            manifest_path = observation / "manifest.json"
            manifest = json.loads(manifest_path.read_text("utf-8"))
            manifest["source"]["key"] = "redirect"
            manifest_path.write_bytes(canonical_json(manifest))
            output = root / "diagnoses"
            output.mkdir()
            escaped = root / "escaped"
            escaped.mkdir()
            (output / "redirect").symlink_to(escaped, target_is_directory=True)
            before = snapshot_tree(observation)
            code, stdout, stderr = self.invoke(
                "diagnose",
                str(observation),
                "--output-root",
                str(output),
            )
            self.assertEqual(code, 2)
            self.assertEqual(stdout, "")
            self.assertIn("escapes the output root", stderr)
            self.assertEqual(list(escaped.iterdir()), [])
            self.assertEqual(snapshot_tree(observation), before)

    def test_output_path_file_conflicts_are_invalid_input(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            observation = self.observation(root / "observations")
            observation_manifest = json.loads(
                (observation / "manifest.json").read_text("utf-8")
            )
            direct = root / "direct-file"
            direct.write_text("occupied", "utf-8")
            intermediate_root = root / "intermediate"
            intermediate_root.mkdir()
            (intermediate_root / observation_manifest["source"]["key"]).write_text(
                "occupied", "utf-8"
            )
            for output in (direct, intermediate_root):
                with self.subTest(output=output):
                    before = snapshot_tree(observation)
                    code, stdout, stderr = self.invoke(
                        "diagnose",
                        str(observation),
                        "--output-root",
                        str(output),
                    )
                    self.assertEqual(code, 2)
                    self.assertEqual(stdout, "")
                    self.assertIn("conflicts with a non-directory", stderr)
                    self.assertEqual(snapshot_tree(observation), before)

    def test_atomic_diagnosis_conflict_never_replaces_existing_run(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            first = AtomicDiagnosis(root, "source", "observation", "run")
            with first as staging:
                (staging / "sentinel").write_bytes(b"first")
                published = first.publish()
            second = AtomicDiagnosis(root, "source", "observation", "run")
            with self.assertRaises(IntegrityError), second as staging:
                (staging / "sentinel").write_bytes(b"second")
                second.publish()
            self.assertEqual((published / "sentinel").read_bytes(), b"first")
            self.assertEqual(
                list((root / "source/observation").glob(".staging-*")), []
            )

    def test_concurrent_atomic_diagnosis_publication_has_one_winner(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            barrier = Barrier(2)

            def publish(value: bytes) -> str:
                publisher = AtomicDiagnosis(
                    root, "source", "observation", "shared-run"
                )
                try:
                    with publisher as staging:
                        (staging / "sentinel").write_bytes(value)
                        barrier.wait()
                        publisher.publish()
                    return "published"
                except IntegrityError:
                    return "conflict"

            with ThreadPoolExecutor(max_workers=2) as pool:
                results = list(pool.map(publish, (b"first", b"second")))
            self.assertEqual(sorted(results), ["conflict", "published"])
            destination = root / "source/observation/shared-run/sentinel"
            self.assertIn(destination.read_bytes(), (b"first", b"second"))
            self.assertEqual(
                list((root / "source/observation").glob(".staging-*")), []
            )

    def test_diagnosis_failures_are_sanitized_with_exact_exit_streams(self) -> None:
        cases = (
            (InputError("bad\x01 input\npath"), 2, "bad input path"),
            (ValueError("boom\x01\ntrace"), 1, "internal diagnosis failure"),
        )
        for error, expected_code, expected_text in cases:
            with self.subTest(code=expected_code), mock.patch.object(
                cli,
                "_diagnosis_callable",
                return_value=mock.Mock(side_effect=error),
            ):
                code, stdout, stderr = self.invoke("diagnose", "observation")
            self.assertEqual(code, expected_code)
            self.assertEqual(stdout, "")
            self.assertEqual(len(stderr.splitlines()), 1)
            self.assertIn(expected_text, stderr)
            self.assertNotIn("\x01", stderr)
            self.assertNotIn("Traceback", stderr)

    def test_usage_failures_have_no_stdout_and_publish_nothing(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            output = root / "output"
            code, stdout, stderr = self.invoke(
                "diagnose", str(root / "missing"), "--output-root", str(output)
            )
            self.assertEqual(code, 2)
            self.assertEqual(stdout, "")
            self.assertTrue(stderr)
            self.assertFalse(output.exists())
            code, stdout, stderr = self.invoke(
                "verify-diagnosis", str(root / "missing")
            )
            self.assertEqual(code, 2)
            self.assertEqual(stdout, "")
            self.assertTrue(stderr)

    def test_missing_canonical_artifact_is_exit_four_without_publication(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            observation = self.observation(root / "observations")
            (observation / "docling/document.json").unlink()
            output = root / "diagnoses"
            code, stdout, stderr = self.invoke(
                "diagnose", str(observation), "--output-root", str(output)
            )
            self.assertEqual(code, 4)
            self.assertEqual(stdout, "")
            self.assertIn("canonical Docling artifact", stderr)
            self.assertFalse(output.exists())

    def test_observation_change_or_staged_failure_never_publishes(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            observation = self.observation(root / "observations")
            baseline = snapshot_tree(observation)
            changed = baseline + (("concurrent", "file"),)
            output = root / "changed"
            with mock.patch(
                "tiny_corpus_workbench.diagnosis.snapshot_tree",
                side_effect=[baseline, changed],
            ):
                code, stdout, stderr = self.invoke(
                    "diagnose", str(observation), "--output-root", str(output)
                )
            self.assertEqual(code, 5)
            self.assertEqual(stdout, "")
            self.assertIn("changed during diagnosis", stderr)
            self.assertEqual(list(output.glob("*/*/*")), [])

            output = root / "schema-failure"
            with mock.patch(
                "tiny_corpus_workbench.diagnosis._validate",
                side_effect=IntegrityError("staged diagnosis is invalid"),
            ):
                code, stdout, stderr = self.invoke(
                    "diagnose", str(observation), "--output-root", str(output)
                )
            self.assertEqual(code, 5)
            self.assertEqual(stdout, "")
            self.assertIn("staged diagnosis is invalid", stderr)
            self.assertEqual(list(output.glob("*/*/*")), [])

    def test_staged_semantics_reject_duplicate_finding_identities(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            observation = self.observation(
                root / "observations", unresolved_caption_docling
            )
            original = make_finding_set

            def duplicate(*args, **kwargs):
                finding_set = original(*args, **kwargs)
                finding_set["findings"].append(
                    dict(finding_set["findings"][0])
                )
                finding_set["summary"]["total"] += 1
                return finding_set

            output = root / "diagnoses"
            with mock.patch(
                "tiny_corpus_workbench.diagnosis.make_finding_set",
                side_effect=duplicate,
            ):
                code, stdout, stderr = self.invoke(
                    "diagnose", str(observation), "--output-root", str(output)
                )
            self.assertEqual(code, 5)
            self.assertEqual(stdout, "")
            self.assertIn("unique and canonically ordered", stderr)
            self.assertFalse(output.exists())

    def test_staged_byte_corruption_is_rejected_before_publication(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            observation = self.observation(root / "observations")
            from tiny_corpus_workbench import diagnosis as diagnosis_module

            original = diagnosis_module._artifact

            def corrupt(path, artifact_root, role, media_type):
                descriptor = original(path, artifact_root, role, media_type)
                if role == "diagnostic-report":
                    path.write_bytes(b"corrupt after descriptor")
                return descriptor

            output = root / "diagnoses"
            with mock.patch(
                "tiny_corpus_workbench.diagnosis._artifact",
                side_effect=corrupt,
            ):
                code, stdout, stderr = self.invoke(
                    "diagnose", str(observation), "--output-root", str(output)
                )
            self.assertEqual(code, 5)
            self.assertEqual(stdout, "")
            self.assertIn("staged diagnosis content changed", stderr)
            self.assertEqual(list(output.glob("*/*/*")), [])

    def test_staged_directories_and_special_nodes_never_publish(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            observation = self.observation(root / "observations")
            output = root / "diagnoses"
            code, stdout, _ = self.invoke(
                "diagnose", str(observation), "--output-root", str(output)
            )
            self.assertEqual(code, 0)
            baseline = Path(json.loads(stdout)["manifest"]).parent
            baseline_snapshot = snapshot_tree(baseline)
            parent = baseline.parent
            operations = ["directory"]
            if hasattr(os, "mkfifo"):
                operations.append("fifo")

            from tiny_corpus_workbench import diagnosis as diagnosis_module

            write_json = diagnosis_module.write_json
            for operation in operations:
                with self.subTest(operation=operation):

                    def inject(path: Path, value: object) -> None:
                        write_json(path, value)
                        if path.name != "diagnosis-manifest.json":
                            return
                        injected = path.parent / f"unexpected-{operation}"
                        if operation == "directory":
                            injected.mkdir()
                        else:
                            os.mkfifo(injected)

                    with mock.patch(
                        "tiny_corpus_workbench.diagnosis.write_json",
                        side_effect=inject,
                    ):
                        code, stdout, stderr = self.invoke(
                            "diagnose",
                            str(observation),
                            "--output-root",
                            str(output),
                        )
                    self.assertEqual(code, 5)
                    self.assertEqual(stdout, "")
                    self.assertEqual(
                        stderr, "staged diagnosis inventory is invalid\n"
                    )
                    self.assertEqual(
                        [path for path in parent.iterdir() if path.is_dir()],
                        [baseline],
                    )
                    self.assertEqual(snapshot_tree(baseline), baseline_snapshot)

    def test_post_publication_manifest_loss_is_sanitized_integrity_exit(self) -> None:
        for operation in ("missing", "malformed"):
            with self.subTest(
                operation=operation
            ), tempfile.TemporaryDirectory() as directory:
                published = Path(directory) / "published-run"
                published.mkdir()
                if operation == "malformed":
                    (published / "diagnosis-manifest.json").write_text(
                        "{", "utf-8"
                    )
                command = mock.Mock(return_value=published)
                from tiny_corpus_workbench.diagnosis_verification import (
                    verify_diagnosis,
                )

                def route(module_name: str, name: str):
                    if name == "diagnose":
                        return command
                    if name == "snapshot_tree":
                        return snapshot_tree
                    return verify_diagnosis

                with mock.patch.object(
                    cli, "_diagnosis_callable", side_effect=route
                ):
                    code, stdout, stderr = self.invoke(
                        "diagnose", "observation"
                    )
                self.assertEqual(code, 5)
                self.assertEqual(stdout, "")
                self.assertEqual(
                    stderr,
                    "published diagnosis manifest is unavailable or invalid\n",
                )
                self.assertNotIn("Traceback", stderr)

    def test_post_publication_summary_requires_complete_integrity(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            observation = self.observation(root / "observations")
            code, stdout, _ = self.invoke(
                "diagnose",
                str(observation),
                "--output-root",
                str(root / "diagnoses"),
            )
            self.assertEqual(code, 0)
            diagnosis = Path(json.loads(stdout)["manifest"]).parent
            from tiny_corpus_workbench.diagnosis_verification import (
                verify_diagnosis,
            )

            for operation in ("non_hex_id", "inconsistent_status_count"):
                with self.subTest(operation=operation):
                    published = root / operation / diagnosis.name
                    published.parent.mkdir()
                    shutil.copytree(diagnosis, published)
                    manifest_path = published / "diagnosis-manifest.json"
                    manifest = json.loads(manifest_path.read_text("utf-8"))
                    if operation == "non_hex_id":
                        manifest["diagnosis_id"] = "z" * 64
                    else:
                        manifest["summary"]["total"] = 3
                        manifest["status"] = "NO_FINDINGS"
                    manifest_path.write_bytes(canonical_json(manifest))
                    command = mock.Mock(return_value=published)

                    def route(module_name: str, name: str):
                        if name == "diagnose":
                            return command
                        if name == "snapshot_tree":
                            return snapshot_tree
                        return verify_diagnosis

                    with mock.patch.object(
                        cli, "_diagnosis_callable", side_effect=route
                    ):
                        code, stdout, stderr = self.invoke(
                            "diagnose", "observation"
                        )
                    self.assertEqual(code, 5)
                    self.assertEqual(stdout, "")
                    self.assertEqual(
                        stderr,
                        "published diagnosis manifest is unavailable or invalid\n",
                    )
                    self.assertNotIn("Traceback", stderr)

    def test_post_verification_publication_races_never_emit_summary(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            observation = self.observation(root / "observations")
            code, stdout, _ = self.invoke(
                "diagnose",
                str(observation),
                "--output-root",
                str(root / "diagnoses"),
            )
            self.assertEqual(code, 0)
            diagnosis = Path(json.loads(stdout)["manifest"]).parent
            from tiny_corpus_workbench.diagnosis_verification import (
                verify_diagnosis,
            )

            for operation in ("manifest", "findings", "inventory"):
                with self.subTest(operation=operation):
                    published = root / operation / diagnosis.name
                    published.parent.mkdir()
                    shutil.copytree(diagnosis, published)
                    command = mock.Mock(return_value=published)

                    def mutate_after_verify(path: Path) -> dict:
                        result = verify_diagnosis(path)
                        if operation == "manifest":
                            manifest_path = path / "diagnosis-manifest.json"
                            manifest_path.write_bytes(
                                manifest_path.read_bytes() + b" "
                            )
                        elif operation == "findings":
                            findings_path = path / "findings.json"
                            findings_path.write_bytes(
                                findings_path.read_bytes() + b" "
                            )
                        else:
                            (path / "unexpected").write_bytes(b"unexpected")
                        return result

                    def route(module_name: str, name: str):
                        if name == "diagnose":
                            return command
                        if name == "snapshot_tree":
                            return snapshot_tree
                        return mutate_after_verify

                    with mock.patch.object(
                        cli, "_diagnosis_callable", side_effect=route
                    ):
                        code, stdout, stderr = self.invoke(
                            "diagnose", "observation"
                        )
                    self.assertEqual(code, 5)
                    self.assertEqual(stdout, "")
                    self.assertEqual(
                        stderr,
                        "published diagnosis changed before summary output\n",
                    )
                    self.assertNotIn("Traceback", stderr)

    def test_verifier_detects_inventory_and_content_failure_shapes(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            observation = self.observation(root / "observations")
            code, stdout, _ = self.invoke(
                "diagnose", str(observation), "--output-root", str(root / "diagnoses")
            )
            self.assertEqual(code, 0)
            diagnosis = Path(json.loads(stdout)["manifest"]).parent
            for operation in ("missing", "added", "malformed", "symlink"):
                with self.subTest(operation=operation):
                    copied = root / operation / diagnosis.name
                    copied.parent.mkdir()
                    shutil.copytree(diagnosis, copied)
                    if operation == "missing":
                        (copied / "report.md").unlink()
                    elif operation == "added":
                        (copied / "extra.txt").write_text("extra", "utf-8")
                    elif operation == "malformed":
                        (copied / "findings.json").write_text("{", "utf-8")
                    else:
                        (copied / "report.md").unlink()
                        (copied / "report.md").symlink_to(copied / "findings.json")
                    code, stdout, stderr = self.invoke(
                        "verify-diagnosis", str(copied)
                    )
                    self.assertEqual(code, 5)
                    self.assertEqual(stderr, "")
                    self.assertIn(
                        json.loads(stdout)["artifact_integrity"]["status"],
                        ("INTEGRITY_MISMATCH", "BROKEN"),
                    )

    def test_optional_observation_states_are_advisory(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            observation = self.observation(root / "observations")
            code, stdout, _ = self.invoke(
                "diagnose", str(observation), "--output-root", str(root / "diagnoses")
            )
            self.assertEqual(code, 0)
            diagnosis = Path(json.loads(stdout)["manifest"]).parent
            code, stdout, _ = self.invoke("verify-diagnosis", str(diagnosis))
            self.assertEqual(code, 0)
            result = json.loads(stdout)
            self.assertEqual(result["observation_state"]["status"], "NOT_CHECKED")
            self.assertEqual(result["derivation_state"]["status"], "NOT_CHECKED")
            code, stdout, _ = self.invoke(
                "verify-diagnosis",
                str(diagnosis),
                "--observation",
                str(root / "missing"),
            )
            self.assertEqual(code, 0)
            result = json.loads(stdout)
            self.assertEqual(result["observation_state"]["status"], "MISSING")
            self.assertEqual(result["derivation_state"]["status"], "NOT_CHECKED")

            other_observation = self.observation(root / "other-observations")
            code, stdout, _ = self.invoke(
                "verify-diagnosis",
                str(diagnosis),
                "--observation",
                str(other_observation),
            )
            self.assertEqual(code, 0)
            result = json.loads(stdout)
            self.assertEqual(result["observation_state"]["status"], "CHANGED")
            self.assertEqual(result["derivation_state"]["status"], "NOT_CHECKED")

            bad_observation = root / "bad-observation"
            bad_observation.mkdir()
            code, stdout, _ = self.invoke(
                "verify-diagnosis",
                str(diagnosis),
                "--observation",
                str(bad_observation),
            )
            self.assertEqual(code, 0)
            result = json.loads(stdout)
            self.assertEqual(result["observation_state"]["status"], "ERROR")
            self.assertEqual(result["derivation_state"]["status"], "NOT_CHECKED")

            with mock.patch(
                "tiny_corpus_workbench.diagnosis_verification.verify_observation",
                side_effect=OSError("observation read failed"),
            ):
                code, stdout, _ = self.invoke(
                    "verify-diagnosis",
                    str(diagnosis),
                    "--observation",
                    str(observation),
                )
            self.assertEqual(code, 0)
            result = json.loads(stdout)
            self.assertEqual(result["observation_state"]["status"], "ERROR")
            self.assertEqual(result["derivation_state"]["status"], "NOT_CHECKED")

            with mock.patch(
                "tiny_corpus_workbench.diagnosis_verification.make_finding_set",
                side_effect=ValueError("rerun failed"),
            ):
                code, stdout, _ = self.invoke(
                    "verify-diagnosis",
                    str(diagnosis),
                    "--observation",
                    str(observation),
                )
            self.assertEqual(code, 0)
            result = json.loads(stdout)
            self.assertEqual(result["observation_state"]["status"], "MATCH")
            self.assertEqual(result["derivation_state"]["status"], "ERROR")

            observation_manifest = json.loads(
                (observation / "manifest.json").read_text("utf-8")
            )
            observation_bytes = (observation / "manifest.json").read_bytes()
            document_bytes = (observation / "docling/document.json").read_bytes()
            changed_payload = json.loads(document_bytes)
            changed_payload["texts"][0]["text"] = "x"
            mismatched = make_finding_set(
                changed_payload,
                observation_manifest,
                manifest_hash=hashlib.sha256(observation_bytes).hexdigest(),
                document_hash=hashlib.sha256(document_bytes).hexdigest(),
            )
            findings_bytes = canonical_json(mismatched)
            report_bytes = render_report(mismatched)
            (diagnosis / "findings.json").write_bytes(findings_bytes)
            (diagnosis / "report.md").write_bytes(report_bytes)
            manifest_path = diagnosis / "diagnosis-manifest.json"
            manifest = json.loads(manifest_path.read_text("utf-8"))
            manifest["status"] = "FINDINGS"
            manifest["summary"] = mismatched["summary"]
            for descriptor in manifest["artifacts"]:
                raw = (
                    findings_bytes
                    if descriptor["path"] == "findings.json"
                    else report_bytes
                )
                descriptor["size"] = len(raw)
                descriptor["sha256"] = hashlib.sha256(raw).hexdigest()
            manifest_path.write_bytes(canonical_json(manifest))
            code, stdout, _ = self.invoke(
                "verify-diagnosis",
                str(diagnosis),
                "--observation",
                str(observation),
            )
            self.assertEqual(code, 0)
            result = json.loads(stdout)
            self.assertEqual(result["artifact_integrity"]["status"], "VERIFIED")
            self.assertEqual(result["observation_state"]["status"], "MATCH")
            self.assertEqual(result["derivation_state"]["status"], "MISMATCH")

    def test_supplied_observation_cross_checks_all_source_identity_fields(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            observation = self.observation(root / "observations")
            code, stdout, _ = self.invoke(
                "diagnose", str(observation), "--output-root", str(root / "diagnoses")
            )
            self.assertEqual(code, 0)
            diagnosis = Path(json.loads(stdout)["manifest"]).parent
            manifest_path = diagnosis / "diagnosis-manifest.json"
            original = json.loads(manifest_path.read_text("utf-8"))
            mutations = {
                "key": f"{original['source']['key']}-changed",
                "media_type": "text/plain",
                "size": original["source"]["size"] + 1,
                "sha256": "0" * 64,
            }
            for field, value in mutations.items():
                with self.subTest(field=field):
                    changed = json.loads(json.dumps(original))
                    changed["source"][field] = value
                    manifest_path.write_bytes(canonical_json(changed))
                    code, stdout, stderr = self.invoke(
                        "verify-diagnosis",
                        str(diagnosis),
                        "--observation",
                        str(observation),
                    )
                    self.assertEqual(code, 0)
                    self.assertEqual(stderr, "")
                    result = json.loads(stdout)
                    self.assertEqual(
                        result["artifact_integrity"]["status"], "VERIFIED"
                    )
                    self.assertEqual(
                        result["observation_state"]["status"], "CHANGED"
                    )
                    self.assertEqual(
                        result["derivation_state"]["status"], "NOT_CHECKED"
                    )

    def test_active_distribution_drift_is_runtime_exit(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            observation = self.observation(root / "observations")

            def drift(name: str) -> str:
                return "0.0.0" if name == "docling-core" else {
                    "docling": "2.113.0",
                    "markitdown": "0.1.6",
                    "tiny-corpus-workbench": "0.2.0",
                }[name]

            output = root / "drifted-diagnosis"
            with mock.patch(
                "tiny_corpus_workbench.runtime.importlib.metadata.version",
                side_effect=drift,
            ):
                code, stdout, stderr = self.invoke(
                    "diagnose",
                    str(observation),
                    "--output-root",
                    str(output),
                )
            self.assertEqual(code, 6)
            self.assertEqual(stdout, "")
            self.assertIn("installed extractor versions", stderr)
            self.assertFalse(output.exists())

            from tiny_corpus_workbench import runtime as runtime_module

            lock_text = Path("uv.lock").read_text("utf-8")
            changed_lock, replacements = re.subn(
                r'(?m)(name = "pydantic"\nversion = ")[^"]+',
                r"\g<1>0.0.0",
                lock_text,
                count=1,
            )
            self.assertEqual(replacements, 1)
            changed_lock_path = root / "changed-uv.lock"
            changed_lock_path.write_text(changed_lock, "utf-8")
            lock_output = root / "drifted-lock"
            with mock.patch.object(
                runtime_module, "LOCK_PATH", changed_lock_path
            ):
                code, stdout, stderr = self.invoke(
                    "diagnose",
                    str(observation),
                    "--output-root",
                    str(lock_output),
                )
            self.assertEqual(code, 6)
            self.assertEqual(stdout, "")
            self.assertIn("uv.lock bytes", stderr)
            self.assertFalse(lock_output.exists())

            stale_output = root / "stale-project"

            def stale_project(name: str) -> str:
                if name == "tiny-corpus-workbench":
                    return "0.1.0"
                return {
                    "docling": "2.113.0",
                    "docling-core": "2.87.1",
                    "markitdown": "0.1.6",
                }[name]

            with mock.patch(
                "tiny_corpus_workbench.runtime.importlib.metadata.version",
                side_effect=stale_project,
            ):
                code, stdout, stderr = self.invoke(
                    "diagnose",
                    str(observation),
                    "--output-root",
                    str(stale_output),
                )
            self.assertEqual(code, 6)
            self.assertEqual(stdout, "")
            self.assertIn("installed tiny-corpus-workbench metadata", stderr)
            self.assertFalse(stale_output.exists())

            code, stdout, _ = self.invoke(
                "diagnose",
                str(observation),
                "--output-root",
                str(root / "diagnoses"),
            )
            self.assertEqual(code, 0)
            diagnosis = Path(json.loads(stdout)["manifest"]).parent
            for label, patcher, expected in (
                (
                    "stale-project",
                    mock.patch(
                        "tiny_corpus_workbench.runtime.importlib.metadata.version",
                        side_effect=stale_project,
                    ),
                    "installed tiny-corpus-workbench metadata",
                ),
                (
                    "changed-lock",
                    mock.patch.object(
                        runtime_module, "LOCK_PATH", changed_lock_path
                    ),
                    "uv.lock bytes",
                ),
            ):
                with self.subTest(verifier=label), patcher:
                    code, stdout, stderr = self.invoke(
                        "verify-diagnosis",
                        str(diagnosis),
                        "--observation",
                        str(observation),
                    )
                self.assertEqual(code, 6)
                self.assertEqual(stdout, "")
                self.assertIn(expected, stderr)
            with mock.patch(
                "tiny_corpus_workbench.runtime.importlib.metadata.version",
                side_effect=drift,
            ):
                code, stdout, stderr = self.invoke(
                    "verify-diagnosis",
                    str(diagnosis),
                    "--observation",
                    str(observation),
                )
            self.assertEqual(code, 6)
            self.assertEqual(stdout, "")
            self.assertIn("installed extractor versions", stderr)

    def test_verifier_rejects_generic_evidence_for_every_rule(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            observation = self.observation(root / "observations")
            code, stdout, _ = self.invoke(
                "diagnose",
                str(observation),
                "--output-root",
                str(root / "diagnoses"),
            )
            self.assertEqual(code, 0)
            diagnosis = Path(json.loads(stdout)["manifest"]).parent
            original_manifest = json.loads(
                (diagnosis / "diagnosis-manifest.json").read_text("utf-8")
            )
            original_findings = json.loads(
                (diagnosis / "findings.json").read_text("utf-8")
            )
            for rule in RULESET_DESCRIPTOR["rules"]:
                with self.subTest(rule_id=rule["rule_id"]):
                    copied = root / rule["rule_id"] / diagnosis.name
                    copied.parent.mkdir()
                    shutil.copytree(diagnosis, copied)
                    finding = {
                        "finding_id": "0" * 64,
                        "rule_id": rule["rule_id"],
                        "rule_version": "1",
                        "severity": SEVERITY_BY_RULE[rule["rule_id"]],
                        "summary": SUMMARY_BY_RULE[rule["rule_id"]]
                        .replace("_", " ")
                        .title(),
                        "document_refs": ["#/body"],
                        "evidence": {"band": "top"},
                    }
                    identity = {
                        "diagnosis_id": original_findings["diagnosis_id"],
                        "rule_id": finding["rule_id"],
                        "rule_version": finding["rule_version"],
                        "document_refs": finding["document_refs"],
                        "evidence": finding["evidence"],
                    }
                    finding["finding_id"] = hashlib.sha256(
                        canonical_json(identity).rstrip(b"\n")
                    ).hexdigest()
                    finding_set = dict(original_findings)
                    finding_set["findings"] = [finding]
                    finding_set["summary"] = _summary([finding])
                    findings_bytes = canonical_json(finding_set)
                    report_bytes = render_report(finding_set)
                    (copied / "findings.json").write_bytes(findings_bytes)
                    (copied / "report.md").write_bytes(report_bytes)
                    manifest = json.loads(json.dumps(original_manifest))
                    manifest["status"] = "FINDINGS"
                    manifest["summary"] = finding_set["summary"]
                    for descriptor in manifest["artifacts"]:
                        raw = (
                            findings_bytes
                            if descriptor["path"] == "findings.json"
                            else report_bytes
                        )
                        descriptor["size"] = len(raw)
                        descriptor["sha256"] = hashlib.sha256(raw).hexdigest()
                    (copied / "diagnosis-manifest.json").write_bytes(
                        canonical_json(manifest)
                    )
                    code, stdout, stderr = self.invoke(
                        "verify-diagnosis", str(copied)
                    )
                    self.assertEqual(code, 5)
                    self.assertEqual(stderr, "")
                    result = json.loads(stdout)
                    self.assertEqual(
                        result["artifact_integrity"]["status"], "BROKEN"
                    )
                    self.assertTrue(
                        any(
                            issue["code"] == "FINDINGS_INVALID"
                            for issue in result["artifact_integrity"]["issues"]
                        )
                    )


if __name__ == "__main__":
    unittest.main()
