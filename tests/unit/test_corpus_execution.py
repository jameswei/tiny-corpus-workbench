from __future__ import annotations

import json
import tempfile
import unittest
from copy import deepcopy
from pathlib import Path
from unittest.mock import patch

from tiny_corpus_workbench.artifacts import canonical_json
from tiny_corpus_workbench.comparison import NUMERIC_METRICS
from tiny_corpus_workbench.corpus import (
    AdmittedCorpusSpec,
    _tree_inventory,
    load_corpus_spec,
)
from tiny_corpus_workbench.corpus_execution import (
    _expected_member_error_code,
    execute_corpus,
    recheck_corpus_inputs,
)
from tiny_corpus_workbench.domain import (
    ExitCode,
    IntegrityError,
    RuntimeContractError,
)
from tiny_corpus_workbench.source import sha256_file


HASH_A = "a" * 64
HASH_B = "b" * 64
HASH_C = "c" * 64


def _models(root: Path, *, required: bool) -> dict:
    return {
        "required": required,
        "path": str(root),
        "inventory_hash": HASH_B if required else None,
        "files": (
            [{"path": "model.bin", "size": 1, "sha256": HASH_C}]
            if required
            else []
        ),
    }


def _metrics(value: int) -> dict[str, object]:
    return {
        "artifact_sha256": HASH_A,
        "normalized_sha256": HASH_B,
        "anchors": {},
        **{name: value for name in NUMERIC_METRICS},
    }


def _artifact(path: Path, root: Path) -> dict[str, object]:
    return {
        "path": path.relative_to(root).as_posix(),
        "size": path.stat().st_size,
        "sha256": sha256_file(path),
    }


def _write_spec(root: Path, members: list[dict[str, object]]) -> Path:
    path = root / "corpus.json"
    path.write_text(
        json.dumps(
            {
                "corpus_id": "unit-corpus",
                "title": "Unit corpus",
                "members": members,
            }
        ),
        "utf-8",
    )
    return path


class FakeEvidence:
    def __init__(
        self,
        outcomes: dict[str, str],
        *,
        diagnosis_failure: set[str] | None = None,
        secret: str = "PRIVATE SOURCE SENTENCE",
    ):
        self.outcomes = outcomes
        self.diagnosis_failure = diagnosis_failure or set()
        self.secret = secret
        self.order: list[str] = []
        self.diagnosed: list[str] = []
        self.observations: dict[str, str] = {}

    def observe(
        self, source: str, output_root: Path, model_root: Path
    ) -> tuple[ExitCode, Path]:
        member_id = output_root.parent.name
        self.order.append(member_id)
        outcome = self.outcomes[member_id]
        if outcome == "raise":
            raise RuntimeError(f"{self.secret}: {source}")
        source_key = f"{member_id}-source"
        published = output_root / source_key / "observation-run"
        published.mkdir(parents=True)
        missing_canonical = outcome.startswith("missing-canonical")
        docling_claimed = outcome in {
            "complete",
            "docling",
            "missing-canonical-both-success",
            "missing-canonical-both-partial",
            "missing-canonical-docling-success",
            "missing-canonical-docling-partial",
            "missing-docling-markdown",
        }
        docling = docling_claimed and not missing_canonical
        markitdown = outcome in {
            "complete",
            "markitdown",
            "model-missing",
            "missing-canonical-both-success",
            "missing-canonical-both-partial",
            "missing-docling-markdown",
        }
        extractors = []
        for name, available in (
            ("docling", docling_claimed),
            ("markitdown", markitdown),
        ):
            if (
                name == "docling"
                and outcome.endswith("partial")
                and available
            ):
                status = "PARTIAL_SUCCESS"
            else:
                status = "SUCCESS" if available else "FAILED"
            if name == "docling" and outcome == "model-missing":
                error = {
                    "code": "MODEL_ARTIFACTS_MISSING",
                    "message": (
                        f"missing models at {model_root}\x00 {self.secret}"
                    ),
                }
            else:
                error = (
                    None
                    if available
                    else {
                        "code": f"{name.upper()}_UNAVAILABLE",
                        "message": f"{name} view is unavailable",
                    }
                )
            extractors.append(
                {
                    "name": name,
                    "status": status,
                    "error": error,
                }
            )
        if docling:
            (published / "docling").mkdir()
            (published / "docling/document.json").write_text(
                json.dumps({"text": self.secret}), "utf-8"
            )
            if outcome != "missing-docling-markdown":
                (published / "docling/document.md").write_text(
                    self.secret, "utf-8"
                )
        if markitdown:
            (published / "markitdown").mkdir()
            (published / "markitdown/document.md").write_text(
                self.secret, "utf-8"
            )
        for extractor in extractors:
            name = extractor["name"]
            extractor_root = published / name
            extractor["artifacts"] = (
                [
                    _artifact(path, published)
                    for path in sorted(extractor_root.iterdir())
                    if path.is_file()
                ]
                if extractor_root.is_dir()
                else []
            )
        views = {
            "docling": _metrics(7) if docling_claimed else None,
            "markitdown": _metrics(5) if markitdown else None,
        }
        deltas = None
        if docling_claimed and markitdown:
            deltas = {name: 2 for name in NUMERIC_METRICS}
            deltas["normalized_equal"] = False
        comparison = {
            "views": views,
            "deltas": deltas,
        }
        (published / "comparison.json").write_bytes(canonical_json(comparison))
        status = (
            "SUCCESS"
            if docling_claimed and markitdown
            else "PARTIAL_SUCCESS"
            if docling_claimed or markitdown
            else "FAILED"
        )
        manifest = {
            "status": status,
            "run_id": "observation-run",
            "observation_id": HASH_A,
            "extractors": extractors,
        }
        (published / "manifest.json").write_bytes(canonical_json(manifest))
        self.observations[str(published)] = member_id
        return (
            ExitCode.SUCCESS if status == "SUCCESS" else ExitCode.PARTIAL,
            published,
        )

    def diagnose(self, observation_root: Path, output_root: Path) -> Path:
        member_id = self.observations[str(observation_root)]
        self.diagnosed.append(member_id)
        if member_id in self.diagnosis_failure:
            raise RuntimeError(f"{self.secret}: diagnosis detail")
        published = (
            output_root
            / f"{member_id}-source"
            / HASH_A
            / "diagnosis-run"
        )
        published.mkdir(parents=True)
        finding = {
            "finding_id": HASH_B,
            "rule_id": "TCW-D009",
            "severity": "INFO",
            "document_refs": ["#/texts/0"],
            "evidence": {"source_excerpt": self.secret},
        }
        (published / "findings.json").write_bytes(
            canonical_json({"findings": [finding]})
        )
        (published / "diagnosis-manifest.json").write_bytes(
            canonical_json(
                {
                    "status": "FINDINGS",
                    "run_id": "diagnosis-run",
                    "diagnosis_id": HASH_C,
                }
            )
        )
        return published


def _admitted_with_revisions(admitted: AdmittedCorpusSpec) -> AdmittedCorpusSpec:
    members = [deepcopy(member) for member in admitted.members]
    inventories = {}
    for name in ("refinement", "diagnosis", "base"):
        directory = admitted.path.parent / name
        directory.mkdir()
        (directory / "record.json").write_text("{}", "utf-8")
        inventories[name] = _tree_inventory(directory, name)
    members[0]["revisions"] = [
        {
            "revision_id": HASH_C,
            "refinement_run_id": "refinement-run",
            "diagnosis_id": HASH_B,
            "parent": {
                "kind": "OBSERVATION",
                "subject_id": HASH_A,
                "canonical_document_sha256": HASH_A,
            },
            "source": {
                "key": "a-source",
                "media_type": "text/markdown",
                "size": members[0]["source"]["size"],
                "sha256": members[0]["source"]["sha256"],
            },
            "chain_length": 2,
            "finding_id": HASH_B,
            "finding_rule": "TCW-D009",
            "refiner": {
                "refiner_id": "TCW-R001",
                "name": "WHITESPACE_NORMALIZATION",
                "version": "1",
            },
            "affected_refs": ["#/texts/0"],
            "affected_reference_count": 1,
            "prepared_document_sha256": HASH_B,
            "refinement_manifest_sha256": HASH_C,
            "bundle_paths": {
                "refinement": "refinement",
                "diagnosis": "diagnosis",
                "base": "base",
            },
            "inventory_fingerprints": {
                "refinement": HASH_A,
                "diagnosis": HASH_B,
                "base": HASH_C,
            },
            "inventories": inventories,
        }
    ]
    return AdmittedCorpusSpec(
        path=admitted.path,
        normalized=admitted.normalized,
        specification_identity=admitted.specification_identity,
        members=tuple(members),
    )


class CorpusExecutionTests(unittest.TestCase):
    def test_member_error_codes_cover_every_stage_status_tuple(self) -> None:
        descriptor = {"path": "nested/manifest.json"}

        def observation(
            status: str,
            *,
            published: bool,
            docling: bool,
            markitdown: bool,
        ) -> tuple[dict[str, object], dict[str, object] | None]:
            stage = {
                "status": status,
                "observation_id": HASH_A if published else None,
                "run_id": "observation-run" if published else None,
                "manifest": descriptor if published else None,
                "canonical_document_sha256": HASH_B if docling else None,
            }
            evidence = (
                {
                    "extractors": [
                        {
                            "name": "docling",
                            "status": "SUCCESS" if docling else "FAILED",
                            "error": (
                                None
                                if docling
                                else {
                                    "code": "DOCLING_CONVERSION_FAILED",
                                    "message": "failed",
                                }
                            ),
                        },
                        {
                            "name": "markitdown",
                            "status": "SUCCESS" if markitdown else "FAILED",
                            "error": (
                                None
                                if markitdown
                                else {
                                    "code": "MARKITDOWN_CONVERSION_FAILED",
                                    "message": "failed",
                                }
                            ),
                        },
                    ]
                }
                if published
                else None
            )
            return stage, evidence

        diagnosis_complete = {
            "status": "NO_FINDINGS",
            "diagnosis_id": HASH_A,
            "run_id": "diagnosis-run",
            "manifest": descriptor,
            "findings_sha256": HASH_B,
        }
        diagnosis_failed = {
            "status": "FAILED",
            "diagnosis_id": None,
            "run_id": None,
            "manifest": None,
            "findings_sha256": None,
        }
        diagnosis_not_run = {
            **diagnosis_failed,
            "status": "NOT_RUN",
        }
        cases = (
            (
                "successful observation and completed diagnosis",
                "COMPLETE",
                observation(
                    "SUCCESS", published=True, docling=True, markitdown=True
                ),
                diagnosis_complete,
                True,
                True,
                True,
                None,
            ),
            (
                "partial observation and completed diagnosis",
                "PARTIAL",
                observation(
                    "PARTIAL_SUCCESS",
                    published=True,
                    docling=True,
                    markitdown=False,
                ),
                diagnosis_complete,
                True,
                False,
                True,
                "MARKITDOWN_CONVERSION_FAILED",
            ),
            (
                "published failed observation",
                "FAILED",
                observation(
                    "FAILED",
                    published=True,
                    docling=False,
                    markitdown=False,
                ),
                diagnosis_not_run,
                False,
                False,
                False,
                "DOCLING_CONVERSION_FAILED",
            ),
            (
                "pre-publication failed observation",
                "FAILED",
                observation(
                    "FAILED",
                    published=False,
                    docling=False,
                    markitdown=False,
                ),
                diagnosis_not_run,
                False,
                False,
                False,
                "OBSERVATION_FAILED",
            ),
            (
                "observation not run",
                "FAILED",
                observation(
                    "NOT_RUN",
                    published=False,
                    docling=False,
                    markitdown=False,
                ),
                diagnosis_not_run,
                False,
                False,
                False,
                "MEMBER_INCOMPLETE",
            ),
            (
                "failed diagnosis",
                "PARTIAL",
                observation(
                    "SUCCESS", published=True, docling=True, markitdown=True
                ),
                diagnosis_failed,
                True,
                True,
                False,
                "DIAGNOSIS_FAILED",
            ),
            (
                "diagnosis not run after successful observation",
                "PARTIAL",
                observation(
                    "SUCCESS", published=True, docling=True, markitdown=True
                ),
                diagnosis_not_run,
                True,
                True,
                False,
                "MEMBER_INCOMPLETE",
            ),
            (
                "diagnosis not run because canonical extraction failed",
                "PARTIAL",
                observation(
                    "PARTIAL_SUCCESS",
                    published=True,
                    docling=False,
                    markitdown=True,
                ),
                diagnosis_not_run,
                False,
                True,
                False,
                "DOCLING_CONVERSION_FAILED",
            ),
        )
        for (
            name,
            status,
            (observation_stage, evidence),
            diagnosis_stage,
            docling_available,
            markitdown_available,
            completed,
            expected,
        ) in cases:
            with self.subTest(name=name):
                self.assertEqual(
                    _expected_member_error_code(
                        {
                            "status": status,
                            "observation": observation_stage,
                            "diagnosis": diagnosis_stage,
                        },
                        evidence,
                        docling_available=docling_available,
                        markitdown_available=markitdown_available,
                        diagnosis_complete=completed,
                    ),
                    expected,
                )

    def _admit(self, root: Path, *, include_pdf: bool = False) -> AdmittedCorpusSpec:
        (root / "z.md").write_text("# Z\n", "utf-8")
        (root / "a.md").write_text("# A\n", "utf-8")
        members: list[dict[str, object]] = [
            {
                "member_id": "z-member",
                "family": "family-z",
                "format": "md",
                "source": "z.md",
            },
            {
                "member_id": "a-member",
                "family": "family-a",
                "format": "md",
                "source": "a.md",
            },
        ]
        if include_pdf:
            (root / "p.pdf").write_bytes(b"%PDF-1.4\n")
            members.append(
                {
                    "member_id": "pdf-member",
                    "family": "family-p",
                    "format": "pdf",
                    "source": "p.pdf",
                }
            )
        return load_corpus_spec(_write_spec(root, members))

    def _execute(
        self,
        admitted: AdmittedCorpusSpec,
        staging: Path,
        evidence: FakeEvidence,
        **kwargs: object,
    ):
        return execute_corpus(
            admitted,
            staging,
            staging / "models",
            run_id="corpus-run",
            observe_member=evidence.observe,
            diagnose_member=evidence.diagnose,
            model_inventory_loader=kwargs.get("model_inventory_loader", _models),
        )

    def test_stable_snapshot_order_complete_and_nested_layout(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory).resolve()
            admitted = self._admit(root)
            outcomes = {"a-member": "complete", "z-member": "complete"}
            first_stage = root / "stage-one"
            second_stage = root / "stage-two"
            first_stage.mkdir()
            second_stage.mkdir()
            first_evidence = FakeEvidence(outcomes)
            second_evidence = FakeEvidence(outcomes)
            first = self._execute(admitted, first_stage, first_evidence)
            second = self._execute(admitted, second_stage, second_evidence)

            self.assertEqual(first.status, "COMPLETE")
            self.assertEqual(first.exit_code, ExitCode.SUCCESS)
            self.assertEqual(first.snapshot_id, second.snapshot_id)
            self.assertEqual(first_evidence.order, ["a-member", "z-member"])
            self.assertEqual(
                [member["member_id"] for member in first.members],
                ["a-member", "z-member"],
            )
            for member in first.members:
                self.assertTrue(
                    member["observation"]["manifest"]["path"].startswith(
                        f"members/{member['member_id']}/observations/"
                    )
                )
                self.assertTrue(
                    member["diagnosis"]["manifest"]["path"].startswith(
                        f"members/{member['member_id']}/diagnoses/"
                    )
                )

    def test_markitdown_only_docling_only_diagnosis_failure_and_failed(self) -> None:
        cases = (
            (
                {"a-member": "markitdown", "z-member": "complete"},
                set(),
                "PARTIAL",
                ("PARTIAL", "COMPLETE"),
            ),
            (
                {"a-member": "docling", "z-member": "complete"},
                set(),
                "PARTIAL",
                ("PARTIAL", "COMPLETE"),
            ),
            (
                {"a-member": "complete", "z-member": "complete"},
                {"a-member"},
                "PARTIAL",
                ("PARTIAL", "COMPLETE"),
            ),
            (
                {"a-member": "raise", "z-member": "raise"},
                set(),
                "FAILED",
                ("FAILED", "FAILED"),
            ),
        )
        for outcomes, diagnosis_failure, status, member_statuses in cases:
            with self.subTest(status=status, outcomes=outcomes):
                with tempfile.TemporaryDirectory() as directory:
                    root = Path(directory).resolve()
                    admitted = self._admit(root)
                    staging = root / "stage"
                    staging.mkdir()
                    result = self._execute(
                        admitted,
                        staging,
                        FakeEvidence(
                            outcomes, diagnosis_failure=diagnosis_failure
                        ),
                    )
                    self.assertEqual(result.status, status)
                    self.assertEqual(
                        tuple(member["status"] for member in result.members),
                        member_statuses,
                    )

    def test_missing_pdf_model_is_stable_and_non_pdf_members_continue(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory).resolve()
            admitted = self._admit(root, include_pdf=True)
            staging = root / "stage"
            staging.mkdir()
            evidence = FakeEvidence(
                {
                    "a-member": "complete",
                    "pdf-member": "markitdown",
                    "z-member": "complete",
                }
            )

            def missing_models(root: Path, *, required: bool) -> dict:
                raise RuntimeContractError("private path is missing")

            result = self._execute(
                admitted,
                staging,
                evidence,
                model_inventory_loader=missing_models,
            )
            self.assertEqual(result.status, "PARTIAL")
            self.assertEqual(
                result.input_capture["model_identity"]["state"], "MISSING"
            )
            self.assertEqual(
                result.configuration["model_inventory"]["inventory_hash"], None
            )
            self.assertEqual(
                [member["status"] for member in result.members],
                ["COMPLETE", "PARTIAL", "COMPLETE"],
            )

    def test_docling_availability_requires_safe_expected_artifacts(self) -> None:
        cases = (
            (
                "missing-docling-markdown",
                "PARTIAL",
                "PARTIAL",
                "COMPLETE",
                1,
            ),
            (
                "missing-canonical-both-success",
                "PARTIAL",
                "PARTIAL",
                "COMPLETE",
                1,
            ),
            (
                "missing-canonical-both-partial",
                "PARTIAL",
                "PARTIAL",
                "COMPLETE",
                1,
            ),
            (
                "missing-canonical-docling-success",
                "FAILED",
                "FAILED",
                "INCOMPLETE",
                0,
            ),
            (
                "missing-canonical-docling-partial",
                "FAILED",
                "FAILED",
                "INCOMPLETE",
                0,
            ),
        )
        for outcome, member_status, overall, comparison, markitdown_count in cases:
            with self.subTest(outcome=outcome):
                with tempfile.TemporaryDirectory() as directory:
                    root = Path(directory).resolve()
                    (root / "source.md").write_text("# Source\n", "utf-8")
                    spec = _write_spec(
                        root,
                        [
                            {
                                "member_id": "source",
                                "family": "sample",
                                "format": "md",
                                "source": "source.md",
                            }
                        ],
                    )
                    admitted = load_corpus_spec(spec)
                    staging = root / "stage"
                    staging.mkdir()
                    evidence = FakeEvidence({"source": outcome})
                    result = self._execute(admitted, staging, evidence)
                    self.assertEqual(result.status, overall)
                    self.assertEqual(result.members[0]["status"], member_status)
                    self.assertEqual(
                        result.members[0]["error"]["code"],
                        "CANONICAL_UNAVAILABLE",
                    )
                    self.assertEqual(
                        result.summary["comparisons"][0]["status"], comparison
                    )
                    self.assertEqual(
                        result.summary["extractors"],
                        [
                            {
                                "name": "docling",
                                "available": 0,
                                "unavailable": 1,
                            },
                            {
                                "name": "markitdown",
                                "available": markitdown_count,
                                "unavailable": 1 - markitdown_count,
                            },
                        ],
                    )
                    self.assertEqual(evidence.diagnosed, [])

    def test_missing_model_error_never_copies_upstream_detail(self) -> None:
        errors = []
        for _ in range(2):
            with tempfile.TemporaryDirectory() as directory:
                root = Path(directory).resolve()
                admitted = self._admit(root, include_pdf=True)
                staging = root / "stage"
                staging.mkdir()
                secret = "PRIVATE PDF SOURCE TEXT"
                evidence = FakeEvidence(
                    {
                        "a-member": "complete",
                        "pdf-member": "model-missing",
                        "z-member": "complete",
                    },
                    secret=secret,
                )

                def missing_models(root: Path, *, required: bool) -> dict:
                    raise RuntimeContractError(f"{root}\x00 {secret}")

                result = self._execute(
                    admitted,
                    staging,
                    evidence,
                    model_inventory_loader=missing_models,
                )
                pdf_member = next(
                    member
                    for member in result.members
                    if member["member_id"] == "pdf-member"
                )
                errors.append(pdf_member["error"])
                serialized = canonical_json(
                    {
                        "members": result.members,
                        "summary": result.summary,
                    }
                ).decode("utf-8")
                self.assertNotIn(str(staging / "models"), serialized)
                self.assertNotIn(secret, serialized)
                self.assertNotIn("\\u0000", serialized)
        self.assertEqual(errors[0], errors[1])
        self.assertEqual(
            errors[0],
            {
                "code": "MODEL_ARTIFACTS_MISSING",
                "message": "Required Docling model artifacts are missing",
            },
        )

    def test_aggregation_revision_summary_and_source_text_exclusion(self) -> None:
        secret = "PRIVATE SOURCE SENTENCE"
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory).resolve()
            admitted = _admitted_with_revisions(self._admit(root))
            staging = root / "stage"
            staging.mkdir()
            evidence = FakeEvidence(
                {"a-member": "complete", "z-member": "complete"},
                secret=secret,
            )
            with (
                patch("tiny_corpus_workbench.v03.draft_refinement") as draft,
                patch("tiny_corpus_workbench.v03.resolve_refinement") as resolve,
            ):
                result = self._execute(admitted, staging, evidence)
            draft.assert_not_called()
            resolve.assert_not_called()

            summary = result.summary
            self.assertEqual(summary["totals"]["finding_count"], 2)
            self.assertEqual(summary["findings"][0]["affected_member_count"], 1)
            self.assertEqual(len(summary["by_family"]), 2)
            self.assertEqual(len(summary["by_format"]), 1)
            self.assertEqual(summary["revision_groups"][0]["revision_count"], 1)
            self.assertEqual(summary["revisions"][0]["chain_length"], 2)
            self.assertEqual(
                summary["revisions"][0]["before_document_sha256"], HASH_A
            )
            self.assertEqual(
                summary["revisions"][0]["after_document_sha256"], HASH_B
            )
            serialized = canonical_json(summary).decode("utf-8").lower()
            self.assertNotIn(secret.lower(), serialized)
            for forbidden in (
                "quality_score",
                "ranking",
                "semantic",
                "recommendation",
                "severity_score",
                "source_excerpt",
            ):
                self.assertNotIn(forbidden, serialized)

    def test_member_exception_is_sanitized(self) -> None:
        secret = "PRIVATE SOURCE SENTENCE"
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory).resolve()
            admitted = self._admit(root)
            staging = root / "stage"
            staging.mkdir()
            evidence = FakeEvidence(
                {"a-member": "raise", "z-member": "complete"}, secret=secret
            )
            result = self._execute(admitted, staging, evidence)
            error = result.members[0]["error"]
            self.assertEqual(error["code"], "OBSERVATION_FAILED")
            self.assertNotIn(secret, error["message"])
            self.assertNotIn(str(root), error["message"])


    def test_snapshot_uses_normalized_spec_not_json_formatting(self) -> None:
        with (
            tempfile.TemporaryDirectory() as first_directory,
            tempfile.TemporaryDirectory() as second_directory,
        ):
            roots = [
                Path(first_directory).resolve(),
                Path(second_directory).resolve(),
            ]
            results = []
            for index, root in enumerate(roots):
                (root / "a.md").write_text("# A\n", "utf-8")
                member = {
                    "member_id": "a-member",
                    "family": "family-a",
                    "format": "md",
                    "source": "a.md",
                }
                spec = _write_spec(root, [member])
                if index:
                    value = json.loads(spec.read_text("utf-8"))
                    spec.write_text(
                        json.dumps(value, indent=4, ensure_ascii=False) + "\n",
                        "utf-8",
                    )
                admitted = load_corpus_spec(spec)
                staging = root / "stage"
                staging.mkdir()
                results.append(
                    self._execute(
                        admitted,
                        staging,
                        FakeEvidence({"a-member": "complete"}),
                    )
                )
            self.assertEqual(results[0].snapshot_id, results[1].snapshot_id)

    def test_rejects_source_drift_and_escaped_nested_result(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory).resolve()
            admitted = self._admit(root)
            staging = root / "stage"
            staging.mkdir()
            evidence = FakeEvidence(
                {"a-member": "complete", "z-member": "complete"}
            )
            admitted.members[0]["source_path"].write_text("# Changed\n", "utf-8")
            with self.assertRaisesRegex(
                IntegrityError, "source changed before corpus execution"
            ):
                self._execute(admitted, staging, evidence)
            self.assertEqual(evidence.order, [])

        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory).resolve()
            admitted = self._admit(root)
            staging = root / "stage"
            staging.mkdir()
            outside = root / "outside"
            outside.mkdir()

            def escaped_observe(
                source: str, output_root: Path, model_root: Path
            ) -> tuple[ExitCode, Path]:
                return ExitCode.SUCCESS, outside

            with self.assertRaisesRegex(
                IntegrityError, "escaped the corpus staging root"
            ):
                execute_corpus(
                    admitted,
                    staging,
                    staging / "models",
                    run_id="escaped",
                    observe_member=escaped_observe,
                    diagnose_member=lambda *_: outside,
                    model_inventory_loader=_models,
                )

    def test_final_input_recheck_detects_source_and_model_drift(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory).resolve()
            admitted = self._admit(root, include_pdf=True)
            staging = root / "stage"
            staging.mkdir()
            evidence = FakeEvidence(
                {
                    "a-member": "complete",
                    "pdf-member": "complete",
                    "z-member": "complete",
                }
            )
            result = self._execute(admitted, staging, evidence)
            recheck_corpus_inputs(
                result,
                model_inventory_loader=_models,
            )
            admitted.members[0]["source_path"].write_text("# Changed\n", "utf-8")
            with self.assertRaisesRegex(
                IntegrityError, "source changed during corpus execution"
            ):
                recheck_corpus_inputs(
                    result,
                    model_inventory_loader=_models,
                )

        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory).resolve()
            admitted = self._admit(root, include_pdf=True)
            staging = root / "stage"
            staging.mkdir()
            evidence = FakeEvidence(
                {
                    "a-member": "complete",
                    "pdf-member": "complete",
                    "z-member": "complete",
                }
            )
            result = self._execute(admitted, staging, evidence)

            def changed_models(root: Path, *, required: bool) -> dict:
                value = _models(root, required=required)
                value["inventory_hash"] = HASH_C
                return value

            with self.assertRaisesRegex(
                IntegrityError, "model inventory changed"
            ):
                recheck_corpus_inputs(
                    result,
                    model_inventory_loader=changed_models,
                )

        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory).resolve()
            admitted = self._admit(root)
            staging = root / "stage"
            staging.mkdir()
            evidence = FakeEvidence(
                {"a-member": "complete", "z-member": "complete"}
            )
            result = self._execute(admitted, staging, evidence)
            admitted.path.write_text("{}\n", "utf-8")
            with self.assertRaisesRegex(
                IntegrityError, "specification changed"
            ):
                recheck_corpus_inputs(
                    result,
                    model_inventory_loader=_models,
                )

        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory).resolve()
            admitted = _admitted_with_revisions(self._admit(root))
            staging = root / "stage"
            staging.mkdir()
            evidence = FakeEvidence(
                {"a-member": "complete", "z-member": "complete"}
            )
            result = self._execute(admitted, staging, evidence)
            (root / "refinement" / "changed.json").write_text(
                "{}\n",
                "utf-8",
            )
            with self.assertRaisesRegex(
                IntegrityError, "revision bundle changed"
            ):
                recheck_corpus_inputs(
                    result,
                    model_inventory_loader=_models,
                )


if __name__ == "__main__":
    unittest.main()
