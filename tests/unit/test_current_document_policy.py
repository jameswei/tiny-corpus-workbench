from __future__ import annotations

import shutil
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path


REPOSITORY = Path(__file__).resolve().parents[2]
VALIDATOR = REPOSITORY / "tools/verify_current_document_policy.py"
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
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            self.copied_policy_tree(root)
            result = self.invoke(root)
            self.assertEqual(result.returncode, 0)
            self.assertEqual(result.stdout, "")
            self.assertEqual(result.stderr, "")

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
        for command in ("uv run tcw observe SOURCE", "uv run corpus inspect-corpus SPEC"):
            with self.subTest(command=command):
                self.assert_policy_failure(
                    Path("README.md"),
                    f"\n```bash\n{command}\n```\n",
                    "stale CLI command",
                )

    def test_rejects_frozen_normal_use_but_allows_validation_and_setup(self) -> None:
        self.assert_policy_failure(
            Path("README.md"),
            "\n```bash\nuv run --frozen corpus observe SOURCE\n```\n",
            "normal-use frozen uv command",
        )
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            self.copied_policy_tree(root)
            readme = root / "README.md"
            readme.write_text(
                readme.read_text("utf-8")
                + "\n```bash\n"
                + "uv sync --frozen --python 3.12\n"
                + "uv run --frozen --group test python -m unittest discover -s tests\n"
                + "uv run --frozen python tools/verify_fixtures.py\n"
                + "```\n",
                "utf-8",
            )
            result = self.invoke(root)
            self.assertEqual(result.returncode, 0)
            self.assertEqual(result.stdout, "")
            self.assertEqual(result.stderr, "")

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


if __name__ == "__main__":
    unittest.main()
