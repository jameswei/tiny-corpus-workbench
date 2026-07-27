from __future__ import annotations

import io
import subprocess
import sys
import tempfile
import unittest
from contextlib import redirect_stderr, redirect_stdout
from pathlib import Path
from types import SimpleNamespace
from unittest import mock

import tiny_corpus_workbench
from tiny_corpus_workbench import cli


BLOCK_JSONSCHEMA = r"""
import importlib.abc
import sys

class BlockJsonschema(importlib.abc.MetaPathFinder):
    def find_spec(self, fullname, path=None, target=None):
        if fullname == "jsonschema" or fullname.startswith("jsonschema."):
            raise ModuleNotFoundError("blocked jsonschema for bootstrap test")
        return None

assert "jsonschema" not in sys.modules
sys.meta_path.insert(0, BlockJsonschema())
from tiny_corpus_workbench import cli
assert "jsonschema" not in sys.modules
assert "tiny_corpus_workbench.diagnosis_rules" not in sys.modules
"""
ACTIVE_RUNTIME_ERROR = (
    "active runtime does not match this package provenance registry\n"
)


class BootstrapTests(unittest.TestCase):
    def run_fresh(self, script: str, *arguments: str) -> subprocess.CompletedProcess:
        return subprocess.run(
            [sys.executable, "-c", script, *arguments],
            cwd=Path.cwd(),
            capture_output=True,
            text=True,
            check=False,
        )

    def assert_runtime_bootstrap_failure(
        self, completed: subprocess.CompletedProcess
    ) -> None:
        self.assertEqual(completed.returncode, 6)
        self.assertEqual(completed.stdout, "")
        self.assertEqual(completed.stderr, ACTIVE_RUNTIME_ERROR)
        self.assertNotIn("Traceback", completed.stderr)

    def test_fresh_process_without_jsonschema_handles_verify_bootstrap(self) -> None:
        script = BLOCK_JSONSCHEMA + r"""
from pathlib import Path

root = Path(sys.argv[1])
root.mkdir()
raise SystemExit(cli.main(["verify", str(root)]))
"""
        with tempfile.TemporaryDirectory() as directory:
            completed = self.run_fresh(script, str(Path(directory) / "observation"))
        self.assert_runtime_bootstrap_failure(completed)

    def test_fresh_process_without_jsonschema_handles_observe_bootstrap(self) -> None:
        script = BLOCK_JSONSCHEMA + r"""
from pathlib import Path
from types import SimpleNamespace
from unittest import mock

def fake_docling(source, destination, model_root):
    destination.mkdir(parents=True)
    (destination / "document.json").write_text(
        '{"schema_name":"DoclingDocument","version":"1.10.0"}\n',
        "utf-8",
    )
    (destination / "document.md").write_text("# view\n", "utf-8")
    return "success", {"name": "DoclingDocument", "version": "1.10.0"}

def fake_markitdown(source, destination):
    destination.mkdir(parents=True)
    (destination / "document.md").write_text("# view\n", "utf-8")

adapters = (
    SimpleNamespace(convert=fake_docling),
    SimpleNamespace(convert=fake_markitdown),
)
with mock.patch(
    "tiny_corpus_workbench.application.observation._preflight_extractors",
    return_value=adapters,
):
    code = cli.main(
        [
            "observe",
            "fixtures/golden/policy-memo.md",
            "--output-root",
            sys.argv[1],
        ]
    )
raise SystemExit(code)
"""
        with tempfile.TemporaryDirectory() as directory:
            output = Path(directory) / "output"
            completed = self.run_fresh(script, str(output))
            self.assertEqual(list(output.glob("*/*")), [])
        self.assert_runtime_bootstrap_failure(completed)

    def test_fresh_process_without_jsonschema_handles_diagnosis_bootstrap(self) -> None:
        script = BLOCK_JSONSCHEMA + r"""
from pathlib import Path

root = Path(sys.argv[1])
root.mkdir()
raise SystemExit(cli.main(["diagnose", str(root)]))
"""
        with tempfile.TemporaryDirectory() as directory:
            completed = self.run_fresh(script, str(Path(directory) / "observation"))
        self.assert_runtime_bootstrap_failure(completed)

    def test_fresh_process_without_jsonschema_handles_corpus_bootstrap(self) -> None:
        script = BLOCK_JSONSCHEMA + r"""
from pathlib import Path

root = Path(sys.argv[1])
root.mkdir()
raise SystemExit(cli.main(["verify-corpus", str(root)]))
"""
        with tempfile.TemporaryDirectory() as directory:
            completed = self.run_fresh(
                script, str(Path(directory) / "corpus")
            )
        self.assert_runtime_bootstrap_failure(completed)

        script = BLOCK_JSONSCHEMA + r"""
raise SystemExit(cli.main(["inspect-corpus", sys.argv[1]]))
"""
        with tempfile.TemporaryDirectory() as directory:
            completed = self.run_fresh(
                script, str(Path(directory) / "corpus.json")
            )
        self.assert_runtime_bootstrap_failure(completed)

    def test_incompatible_verification_module_is_runtime_exit(self) -> None:
        stdout, stderr = io.StringIO(), io.StringIO()
        with tempfile.TemporaryDirectory() as directory, mock.patch(
            "tiny_corpus_workbench.application.verification.verify_command",
            None,
        ), redirect_stdout(stdout), redirect_stderr(stderr):
            code = cli.main(["verify", directory])
        self.assertEqual(code, 6)
        self.assertEqual(stdout.getvalue(), "")
        self.assertIn("verification/schema runtime", stderr.getvalue())
        self.assertNotIn("Traceback", stderr.getvalue())


if __name__ == "__main__":
    unittest.main()
