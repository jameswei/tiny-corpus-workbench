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
