from __future__ import annotations

import re
import unittest
from pathlib import Path


REPOSITORY_ROOT = Path(__file__).resolve().parents[2]
WORKFLOW_PATH = REPOSITORY_ROOT / ".github" / "workflows" / "ci.yml"

FAST_MODULES = {
    "tests.integration.test_v05_workflows",
    "tests.integration.test_workbench_integration",
}
FULL_MODULES = {
    "tests.compatibility.test_extractor_compatibility",
    "tests.integration.test_golden_observations",
    "tests.integration.test_diagnosis_integration",
    "tests.integration.test_corpus_integration",
}
FAST_TOOLS = {
    "tools/verify_current_document_policy.py",
    "tools/validate_workbench_assets.py",
    "tools/validate_site.py",
    "tools/generate_fixtures.py",
    "tools/generate_diagnosis_fixtures.py",
    "tools/generate_refinement_fixtures.py",
    "tools/verify_fixtures.py",
    "tools/verify_corpus_specs.py",
    "tools/verify_checkout_portability.py",
}


def _job(workflow: str, name: str, next_name: str | None = None) -> str:
    start = workflow.index(f"  {name}:\n")
    end = workflow.index(f"  {next_name}:\n", start) if next_name else len(workflow)
    return workflow[start:end]


def _explicit_test_modules(job: str) -> set[str]:
    return set(re.findall(r"\btests\.(?:compatibility|integration)\.[a-z0-9_]+\b", job))


class CIWorkflowTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.workflow = WORKFLOW_PATH.read_text("utf-8")
        cls.fast = _job(cls.workflow, "fast-validation", "full-extraction")
        cls.full = _job(cls.workflow, "full-extraction")

    def test_supported_triggers_remain_enabled(self) -> None:
        workflow_header = self.workflow[: self.workflow.index("permissions:\n")]
        self.assertIn("  pull_request:\n", workflow_header)
        self.assertIn("  push:\n", workflow_header)
        self.assertIn("  workflow_dispatch:\n", workflow_header)
        self.assertEqual(workflow_header.count("      - main\n"), 2)

    def test_fast_owns_model_free_tests_and_shared_tools(self) -> None:
        self.assertIn("unittest discover -s tests/unit -v", self.fast)
        self.assertEqual(_explicit_test_modules(self.fast), FAST_MODULES)
        for tool in FAST_TOOLS:
            with self.subTest(tool=tool):
                self.assertIn(tool, self.fast)
        self.assertEqual(self.fast.count("tools/verify_checkout_portability.py"), 1)
        self.assertIn("python -m compileall -q src tests tools", self.fast)

    def test_full_runs_only_model_dependent_test_modules(self) -> None:
        self.assertEqual(_explicit_test_modules(self.full), FULL_MODULES)
        self.assertNotIn("unittest discover", self.full)
        self.assertNotIn("tests.integration.test_v05_workflows", self.full)
        self.assertNotIn("tests.integration.test_workbench_integration", self.full)
        for tool in FAST_TOOLS:
            with self.subTest(tool=tool):
                self.assertNotIn(tool, self.full)
        self.assertNotIn("python -m compileall", self.full)

    def test_explicit_test_module_ownership_is_disjoint(self) -> None:
        self.assertFalse(
            _explicit_test_modules(self.fast) & _explicit_test_modules(self.full)
        )


if __name__ == "__main__":
    unittest.main()
