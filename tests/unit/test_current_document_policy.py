from __future__ import annotations

import shutil
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path


REPOSITORY = Path(__file__).resolve().parents[2]
VALIDATOR = REPOSITORY / "tools/verify_current_document_policy.py"
README_REFINEMENT_ROW = (
    "| Draft one refinement proposal | `corpus draft-refinement` |"
)
POLICY_PATHS = (
    Path("CURRENT.md"),
    Path("README.md"),
    Path("docs/controlled-revisions.md"),
    Path("docs/corpus-inspection-comparison.md"),
    Path("docs/evidence-based-diagnosis.md"),
    Path("docs/extraction-observatory.md"),
    Path("docs/local-visual-workbench.md"),
    Path("docs/plans/v0.5-learning-first-correction-ledger.md"),
    Path("docs/plans/v0.5-pre-release-amendment-ledger.md"),
    Path("docs/roadmap.md"),
    Path("docs/releases/v0.5.0.md"),
    Path("fixtures/README.md"),
    Path("learning/README.md"),
    Path("learning/v0.1-extraction-observatory.md"),
    Path("learning/v0.2-evidence-based-diagnosis.md"),
    Path("learning/v0.3-controlled-revisions.md"),
    Path("learning/v0.4-corpus-inspection-comparison.md"),
    Path("learning/v0.5-local-visual-workbench.md"),
    Path("site/index.html"),
)


class CurrentDocumentPolicyTests(unittest.TestCase):
    def copied_policy_tree(self, destination: Path) -> None:
        for relative in POLICY_PATHS:
            target = destination / relative
            target.parent.mkdir(parents=True, exist_ok=True)
            shutil.copyfile(REPOSITORY / relative, target)

    def invoke(self, root: Path) -> subprocess.CompletedProcess[str]:
        return subprocess.run(
            [sys.executable, str(VALIDATOR), "--root", str(root)],
            check=False,
            capture_output=True,
            text=True,
        )

    def assert_policy_failure(
        self,
        relative: Path,
        addition: str,
        topic: str,
    ) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            self.copied_policy_tree(root)
            target = root / relative
            target.write_text(target.read_text("utf-8") + addition, "utf-8")
            result = self.invoke(root)
            self.assertEqual(result.returncode, 1)
            self.assertEqual(result.stdout, "")
            self.assertIn(relative.as_posix(), result.stderr)
            self.assertIn(topic, result.stderr)
            self.assertNotIn("Traceback", result.stderr)
            self.assertLessEqual(len(result.stderr.splitlines()), 1)

    def assert_replacement_failure(
        self,
        relative: Path,
        old: str,
        new: str,
        topic: str,
    ) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            self.copied_policy_tree(root)
            target = root / relative
            text = target.read_text("utf-8")
            self.assertIn(old, text)
            target.write_text(text.replace(old, new, 1), "utf-8")
            result = self.invoke(root)
            self.assertEqual(result.returncode, 1)
            self.assertEqual(result.stdout, "")
            self.assertIn(relative.as_posix(), result.stderr)
            self.assertIn(topic, result.stderr)
            self.assertNotIn("Traceback", result.stderr)
            self.assertLessEqual(len(result.stderr.splitlines()), 1)

    def assert_association_failure(
        self,
        relative: Path,
        old: str,
        new: str,
        retained_fact: str,
        row_label: str,
        topic: str,
    ) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            self.copied_policy_tree(root)
            target = root / relative
            text = target.read_text("utf-8")
            self.assertEqual(text.count(old), 1)
            target.write_text(
                text.replace(old, new, 1)
                + f"\nUnrelated retained evidence: {retained_fact}\n",
                "utf-8",
            )
            result = self.invoke(root)
            self.assertEqual(result.returncode, 1)
            self.assertEqual(result.stdout, "")
            self.assertIn(relative.as_posix(), result.stderr)
            self.assertIn(row_label, result.stderr)
            self.assertIn(topic, result.stderr)
            self.assertNotIn("Traceback", result.stderr)
            self.assertLessEqual(len(result.stderr.splitlines()), 1)

    def test_current_policy_surfaces_pass(self) -> None:
        self.assertIn(
            README_REFINEMENT_ROW,
            (REPOSITORY / "README.md").read_text("utf-8"),
        )
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            self.copied_policy_tree(root)
            result = self.invoke(root)
            self.assertEqual(result.returncode, 0)
            self.assertEqual(result.stdout, "")
            self.assertEqual(result.stderr, "")

    def test_rejects_stale_readme_refinement_wording(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            self.copied_policy_tree(root)
            readme_path = root / "README.md"
            readme = readme_path.read_text("utf-8")
            self.assertIn(README_REFINEMENT_ROW, readme)
            readme_path.write_text(
                readme.replace(
                    README_REFINEMENT_ROW,
                    "| Draft one decision | `corpus draft-refinement` |",
                ),
                "utf-8",
            )
            result = self.invoke(root)
            self.assertEqual(result.returncode, 1)
            self.assertEqual(result.stdout, "")
            self.assertIn("README.md", result.stderr)
            self.assertIn("stale refinement draft wording", result.stderr)
            self.assertNotIn("Traceback", result.stderr)
            self.assertLessEqual(len(result.stderr.splitlines()), 1)

    def test_rejects_unified_public_schema_promise(self) -> None:
        self.assert_policy_failure(
            Path("docs/roadmap.md"),
            "\nThe project provides one unified public schema baseline.\n",
            "public schema promise",
        )

    def test_rejects_stable_public_loopback_api(self) -> None:
        self.assert_policy_failure(
            Path("docs/roadmap.md"),
            "\nThe Workbench provides a stable loopback HTTP API.\n",
            "public loopback API promise",
        )

    def test_rejects_released_v05_claim(self) -> None:
        self.assert_policy_failure(
            Path("docs/releases/v0.5.0.md"),
            "\nStatus: Released\n",
            "released v0.5 claim",
        )

    def test_closeout_documents_contain_independent_expected_facts(self) -> None:
        expected = {
            Path("CURRENT.md"): (
                "The v0.5 learning-first correction is complete and merged.",
                "9780d87faf1337e4c8acf28ea2e704b39fcb402e",
                "8b04885a9471091cdfce17560e395a2d103d2806",
                "c80842cec401d6110ad60ccac696cebb1028d640",
                "PR #31 was independently reviewed",
                "5e5a3772a85b44111121ff057f2971db421df1a4",
                "30476653488",
                "40b2083de70cfe9f7ad2dfa2cea8435b377a5ecc",
                "30477806685",
                "30477806662",
                "v0.5 is unreleased.",
                "Tag and GitHub Release creation are not authorized.",
                "Any current release-readiness verdict and exact-SHA owner authorization are",
                "external to this source snapshot.",
            ),
            Path("docs/plans/v0.5-learning-first-correction-ledger.md"): (
                "Overall correction status: `complete`",
                "PR #26",
                "9780d87faf1337e4c8acf28ea2e704b39fcb402e",
                "8b04885a9471091cdfce17560e395a2d103d2806",
                "30376868533",
                "30377410412",
                "30377410609",
                "`PASS`",
            ),
            Path("docs/plans/v0.5-pre-release-amendment-ledger.md"): (
                "Overall implementation and integration status: `complete`",
                "729bb89d5ad82db09851c5602a985e7b9d4f7d5c",
                "bb4341f6a995a702a89f9bfb6f0873c4671f06f6",
                "30452529395",
                "30453075126",
                "30453075891",
                "e256fe20897c20399ccbf6a2bb9fad8acfdd43cc",
                "a829991ded2e6203122e428a990f9893e4c0b41d",
                "30457725350",
                "30460335836",
                "30460335643",
                "ebbe06a20917b2a0d8f16433a09b009ec37ff8b6",
                "c03b70ed04dc07f9d5f94e53ca944814ec61f08d",
                "30468716510",
                "30470529695",
                "30470529661",
                "59fc1df7ef26f914bc828df6a6bd3edc8d3298e0",
                "c80842cec401d6110ad60ccac696cebb1028d640",
                "30472255094",
                "30472763206",
                "30472763290",
                "Fresh independent reviewer returned `PASS` with zero findings",
                "All 169 focused unit tests and 8 integration tests passed",
                "Tag and GitHub Release: `not authorized`",
                "| Closeout | `complete` | PR #31;",
                "5e5a3772a85b44111121ff057f2971db421df1a4",
                "30476653488",
                "40b2083de70cfe9f7ad2dfa2cea8435b377a5ecc",
                "30477806685",
                "30477806662",
                "| Release readiness | `external release gate` |",
                "fresh zero-finding `PASS` for the exact current `main` candidate",
                "separate owner authorization for that exact SHA",
            ),
            Path("docs/releases/v0.5.0.md"): (
                "four verifier outputs",
                "dependency-free frozen Python dataclasses",
                "deterministic compact JSON on standard output",
                "no verification-result JSON Schemas",
                "11 retained self-contained JSON Schemas",
                "canonical proposal-only `proposal.json`",
                "exactly one of `--approve` or `--reject`",
                "manifest decision is the only persisted structured authority",
                "There is no actor, note, manifest status, or `decision.json`",
                "only fully verified approved revisions",
                "read-only local internal bridge",
                "source-only",
                "v0.5 remains unreleased",
            ),
        }
        for relative, markers in expected.items():
            text = (REPOSITORY / relative).read_text("utf-8")
            for marker in markers:
                with self.subTest(relative=relative.as_posix(), marker=marker):
                    self.assertIn(marker, text)

    def test_rejects_stale_correction_closeout_status(self) -> None:
        self.assert_replacement_failure(
            Path("docs/plans/v0.5-learning-first-correction-ledger.md"),
            "Overall correction status: `complete`",
            "Overall status: `building`",
            "complete correction status",
        )
        self.assert_replacement_failure(
            Path("docs/plans/v0.5-learning-first-correction-ledger.md"),
            "| PR 9 — Rewrite current documentation and close the correction | "
            "`452fcd2d8ca39bbb5b92d20d1a7996588baf8ad5` | `complete` |",
            "| PR 9 — Rewrite current documentation and close the correction | "
            "`452fcd2d8ca39bbb5b92d20d1a7996588baf8ad5` | `reviewing` |",
            "complete status",
        )

    def test_rejects_false_release_authorization(self) -> None:
        self.assert_replacement_failure(
            Path("docs/plans/v0.5-pre-release-amendment-ledger.md"),
            "Tag and GitHub Release: `not authorized`",
            "Tag and GitHub Release: authorized",
            "release authorization claim",
        )

    def test_rejects_stale_or_false_current_behavior(self) -> None:
        self.assert_policy_failure(
            Path("docs/releases/v0.5.0.md"),
            "\nVerification-result JSON Schemas remain part of the release.\n",
            "verification-result schema claim",
        )
        self.assert_replacement_failure(
            Path("docs/releases/v0.5.0.md"),
            "The four verifier outputs",
            "The five verifier outputs",
            "verifier output count",
        )

    def test_rejects_stale_closeout_and_release_gate_statuses(self) -> None:
        for stale_status in ("`external gate`", "`pending`"):
            with self.subTest(stale_status=stale_status):
                self.assert_replacement_failure(
                    Path("docs/plans/v0.5-pre-release-amendment-ledger.md"),
                    "| Closeout | `complete` |",
                    f"| Closeout | {stale_status} |",
                    "Closeout row",
                )
        self.assert_replacement_failure(
            Path("docs/plans/v0.5-pre-release-amendment-ledger.md"),
            "| Release readiness | `external release gate` |",
            "| Release readiness | `not started` |",
            "stale release-readiness status",
        )
        self.assert_replacement_failure(
            Path("CURRENT.md"),
            "The amendment closeout is complete.",
            "Closeout evidence must be established externally.",
            "stale closeout evidence status",
        )
        self.assert_policy_failure(
            Path("docs/plans/v0.5-pre-release-amendment-ledger.md"),
            "\nRemaining closeout gates: release approval only.\n",
            "stale remaining closeout gates",
        )

    def test_rejects_cross_row_or_unrelated_amendment_evidence(self) -> None:
        ledger = Path("docs/plans/v0.5-pre-release-amendment-ledger.md")
        cases = (
            (
                "reviewed head `729bb89d5ad82db09851c5602a985e7b9d4f7d5c`",
                "reviewed head `0000000000000000000000000000000000000000`",
                "729bb89d5ad82db09851c5602a985e7b9d4f7d5c",
                "Establishment PR",
                "reviewed head",
            ),
            (
                "squash merge `a829991ded2e6203122e428a990f9893e4c0b41d`",
                "squash merge `0000000000000000000000000000000000000000`",
                "a829991ded2e6203122e428a990f9893e4c0b41d",
                "PR A — Transient typed verification results",
                "squash merge",
            ),
            (
                "exact-head PR CI `30468716510` passed",
                "exact-head PR CI `00000000000` passed",
                "30468716510",
                "PR B — Proposal-only refinement and one persisted authority",
                "exact-head PR CI",
            ),
            (
                "post-main CI `30472763206` passed",
                "post-main CI `00000000000` passed",
                "30472763206",
                "Narrow corrective PR",
                "post-main CI",
            ),
            (
                "post-main Pages `30453075891` passed",
                "post-main Pages `00000000000` passed",
                "30453075891",
                "Establishment PR",
                "post-main Pages",
            ),
            (
                "PR #31; reviewed head",
                "PR #99; reviewed head",
                "PR #31",
                "Closeout",
                "complete status and PR number",
            ),
            (
                "reviewed head `5e5a3772a85b44111121ff057f2971db421df1a4`",
                "reviewed head `0000000000000000000000000000000000000000`",
                "5e5a3772a85b44111121ff057f2971db421df1a4",
                "Closeout",
                "reviewed head",
            ),
            (
                "fresh independent reviewer returned `PASS` with zero findings; "
                "exact-head",
                "fresh independent reviewer returned `FAIL` with findings; exact-head",
                "fresh independent reviewer returned `PASS` with zero findings",
                "Closeout",
                "independent verdict",
            ),
            (
                "exact-head PR CI `30476653488` passed",
                "exact-head PR CI `00000000000` passed",
                "30476653488",
                "Closeout",
                "exact-head PR CI",
            ),
            (
                "squash merge `40b2083de70cfe9f7ad2dfa2cea8435b377a5ecc`",
                "squash merge `0000000000000000000000000000000000000000`",
                "40b2083de70cfe9f7ad2dfa2cea8435b377a5ecc",
                "Closeout",
                "squash merge",
            ),
            (
                "post-main CI `30477806685` passed",
                "post-main CI `00000000000` passed",
                "30477806685",
                "Closeout",
                "post-main CI",
            ),
            (
                "post-main Pages `30477806662` passed",
                "post-main Pages `00000000000` passed",
                "30477806662",
                "Closeout",
                "post-main Pages",
            ),
        )
        for old, new, retained, label, topic in cases:
            with self.subTest(label=label, topic=topic):
                self.assert_association_failure(
                    ledger,
                    old,
                    new,
                    retained,
                    label,
                    topic,
                )

    def test_rejects_prefixed_row_fact_phrases(self) -> None:
        ledger = Path("docs/plans/v0.5-pre-release-amendment-ledger.md")
        cases = (
            (
                "reviewed head `729bb89d5ad82db09851c5602a985e7b9d4f7d5c`",
                "unreviewed head `729bb89d5ad82db09851c5602a985e7b9d4f7d5c`",
                "reviewed head `729bb89d5ad82db09851c5602a985e7b9d4f7d5c`",
                "Establishment PR",
                "reviewed head",
            ),
            (
                "squash merge `a829991ded2e6203122e428a990f9893e4c0b41d`",
                "unsquash merge `a829991ded2e6203122e428a990f9893e4c0b41d`",
                "squash merge `a829991ded2e6203122e428a990f9893e4c0b41d`",
                "PR A — Transient typed verification results",
                "squash merge",
            ),
            (
                "Fresh independent reviewer returned `PASS` with zero findings "
                "for exact base",
                "Fresh independent reviewer returned `PASS` with nonzero findings "
                "for exact base",
                "zero findings",
                "Combined technical integration review",
                "findings",
            ),
        )
        for old, new, retained, label, topic in cases:
            with self.subTest(label=label, topic=topic):
                self.assert_association_failure(
                    ledger,
                    old,
                    new,
                    retained,
                    label,
                    topic,
                )

    def test_rejects_correction_pr_number_outside_pr9_row(self) -> None:
        self.assert_association_failure(
            Path("docs/plans/v0.5-learning-first-correction-ledger.md"),
            "PR #26; PR CI run `30376868533` passed",
            "PR #99; PR CI run `30376868533` passed",
            "PR #26",
            "PR 9 — Rewrite current documentation and close the correction",
            "PR number",
        )

    def test_rejects_explicit_cross_row_reviewed_head_swap(self) -> None:
        relative = Path("docs/plans/v0.5-pre-release-amendment-ledger.md")
        first = "729bb89d5ad82db09851c5602a985e7b9d4f7d5c"
        second = "e256fe20897c20399ccbf6a2bb9fad8acfdd43cc"
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            self.copied_policy_tree(root)
            target = root / relative
            text = target.read_text("utf-8")
            self.assertEqual(text.count(first), 1)
            self.assertEqual(text.count(second), 1)
            text = text.replace(first, "SWAPPED_REVIEW_HEAD", 1)
            text = text.replace(second, first, 1)
            target.write_text(
                text.replace("SWAPPED_REVIEW_HEAD", second, 1),
                "utf-8",
            )
            result = self.invoke(root)
            self.assertEqual(result.returncode, 1)
            self.assertEqual(result.stdout, "")
            self.assertIn(relative.as_posix(), result.stderr)
            self.assertIn("Establishment PR", result.stderr)
            self.assertIn("reviewed head", result.stderr)
            self.assertNotIn("Traceback", result.stderr)
            self.assertLessEqual(len(result.stderr.splitlines()), 1)

    def test_rejects_binary_docker_and_registry_deliverables(self) -> None:
        claims = (
            "The release delivers a prebuilt binary.",
            "The release ships a Docker image.",
            "The release provides packages on a registry.",
        )
        for claim in claims:
            with self.subTest(claim=claim):
                self.assert_policy_failure(
                    Path("docs/releases/v0.5.0.md"),
                    f"\n{claim}\n",
                    "binary or registry deliverable",
                )

    def test_rejects_stale_cli_commands(self) -> None:
        for command in ("tcw observe SOURCE", "corpus inspect-corpus SPEC"):
            with self.subTest(command=command):
                self.assert_policy_failure(
                    Path("README.md"),
                    f"\n```bash\n{command}\n```\n",
                    "stale CLI command",
                )

    def test_rejects_misclassified_historical_paths(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            self.copied_policy_tree(root)
            current_path = root / "CURRENT.md"
            current = current_path.read_text("utf-8")
            current = current.replace(
                "are historical\nrecords of the superseded implementation direction",
                "are current\nrecords of the implementation direction",
            )
            current_path.write_text(current, "utf-8")
            result = self.invoke(root)
            self.assertEqual(result.returncode, 1)
            self.assertEqual(result.stdout, "")
            self.assertIn("CURRENT.md", result.stderr)
            self.assertIn("historical path", result.stderr)
            self.assertNotIn("Traceback", result.stderr)
            self.assertLessEqual(len(result.stderr.splitlines()), 1)

    def test_requires_current_refinement_authority_and_matrix_markers(self) -> None:
        markers = (
            (
                Path("docs/controlled-revisions.md"),
                "Inspect `proposal.json`. Do not edit it.",
                "proposal inspection",
            ),
            (
                Path("docs/controlled-revisions.md"),
                "only machine-authoritative persisted decision field",
                "decision authority",
            ),
            (
                Path("docs/controlled-revisions.md"),
                "--approve",
                "approval flag",
            ),
            (
                Path("docs/controlled-revisions.md"),
                "--reject",
                "rejection flag",
            ),
            (
                Path("docs/controlled-revisions.md"),
                "path: proposal.json",
                "proposal path",
            ),
            (
                Path("docs/controlled-revisions.md"),
                "An approved publication contains",
                "approved inventory",
            ),
            (
                Path("docs/controlled-revisions.md"),
                "A rejected publication contains",
                "rejected inventory",
            ),
            (
                Path("docs/controlled-revisions.md"),
                "non-authoritative human rendering",
                "derived report",
            ),
            (
                Path("docs/controlled-revisions.md"),
                "role: refinement-proposal",
                "proposal role",
            ),
            (
                Path("docs/controlled-revisions.md"),
                "media_type: application/json",
                "proposal media type",
            ),
            (
                Path("docs/controlled-revisions.md"),
                "Only a record with manifest decision `APPROVED`",
                "corpus eligibility",
            ),
            (
                Path("docs/corpus-inspection-comparison.md"),
                "does not copy the approval decision",
                "corpus decision isolation",
            ),
            (
                Path("docs/local-visual-workbench.md"),
                "only from `refinement-manifest.json.decision`",
                "workbench decision derivation",
            ),
        )
        for relative, marker, topic in markers:
            with self.subTest(marker=marker):
                with tempfile.TemporaryDirectory() as directory:
                    root = Path(directory)
                    self.copied_policy_tree(root)
                    target = root / relative
                    text = target.read_text("utf-8")
                    self.assertIn(marker, text)
                    target.write_text(text.replace(marker, "removed marker"), "utf-8")
                    result = self.invoke(root)
                    self.assertEqual(result.returncode, 1)
                    self.assertIn(topic, result.stderr)


if __name__ == "__main__":
    unittest.main()
