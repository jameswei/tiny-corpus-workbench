from __future__ import annotations

import argparse
import _thread
import http.client
import importlib.metadata
import io
import json
import shutil
import socket
import subprocess
import sys
import tempfile
import threading
import time
import unittest
from contextlib import redirect_stderr, redirect_stdout
from pathlib import Path
from unittest.mock import patch

from tiny_corpus_workbench import cli
from tiny_corpus_workbench.application.lifecycle import WorkbenchLifecycleService
from tiny_corpus_workbench.workbench_server import (
    WorkbenchApplication,
    validate_port,
)
from tests.unit.workbench_server_test_support import available_port
from tests.unit.workbench_test_support import PublishedObservation


class WorkbenchCliTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.published = PublishedObservation()

    @classmethod
    def tearDownClass(cls) -> None:
        cls.published.close()

    def test_parser_exposes_exactly_ten_subcommands(self) -> None:
        subparsers = next(
            action
            for action in cli.parser()._actions
            if isinstance(action, argparse._SubParsersAction)
        )
        self.assertEqual(
            set(subparsers.choices),
            {
                "observe",
                "verify",
                "diagnose",
                "verify-diagnosis",
                "draft-refinement",
                "resolve-refinement",
                "verify-refinement",
                "inspect",
                "verify-corpus",
                "workbench",
            },
        )

    def test_console_script_metadata_contains_only_corpus(self) -> None:
        project_scripts = {
            entry_point.name
            for entry_point in importlib.metadata.entry_points(group="console_scripts")
            if entry_point.value == "tiny_corpus_workbench.cli:main"
        }
        self.assertEqual(project_scripts, {"corpus"})

    def test_top_level_version_is_exact(self) -> None:
        executable = shutil.which("corpus")
        self.assertIsNotNone(executable)
        completed = subprocess.run(
            [executable, "--version"],
            check=False,
            capture_output=True,
            text=True,
        )
        expected = importlib.metadata.version("tiny-corpus-workbench")
        self.assertEqual(completed.returncode, 0)
        self.assertEqual(completed.stdout, f"{expected}\n")
        self.assertEqual(completed.stderr, "")

    def test_module_version_is_exact(self) -> None:
        completed = subprocess.run(
            [sys.executable, "-m", "tiny_corpus_workbench", "--version"],
            check=False,
            capture_output=True,
            text=True,
        )
        self.assertEqual(completed.returncode, 0)
        expected = importlib.metadata.version("tiny-corpus-workbench")
        self.assertEqual(completed.stdout, f"{expected}\n")
        self.assertEqual(completed.stderr, "")

    def test_removed_inspect_corpus_name_is_rejected(self) -> None:
        completed = subprocess.run(
            [sys.executable, "-m", "tiny_corpus_workbench", "inspect-corpus"],
            check=False,
            capture_output=True,
            text=True,
        )
        self.assertEqual(completed.returncode, 2)
        self.assertEqual(completed.stdout, "")
        self.assertTrue(completed.stderr.startswith("usage: corpus "))

    def test_parser_exposes_workspace_models_port_and_browser_options(self) -> None:
        args = cli.parser().parse_args(
            [
                "workbench",
                "--workspace",
                "/tmp/example",
                "--docling-artifacts",
                "/tmp/models",
                "--port",
                "9123",
                "--no-open",
            ]
        )
        self.assertEqual(args.command, "workbench")
        self.assertEqual(args.workspace, Path("/tmp/example"))
        self.assertEqual(args.docling_artifacts, Path("/tmp/models"))
        self.assertEqual(args.port, "9123")
        self.assertTrue(args.no_open)
        self.assertFalse(hasattr(args, "host"))
        self.assertFalse(hasattr(args, "records"))

    def test_workspace_defaults_to_build_and_old_record_syntax_exits_two(self) -> None:
        args = cli.parser().parse_args(["workbench", "--no-open"])
        self.assertEqual(args.workspace, Path("build"))
        self.assertEqual(
            args.docling_artifacts, Path(".cache/docling/models")
        )
        with redirect_stderr(io.StringIO()), self.assertRaisesRegex(SystemExit, "2"):
            cli.parser().parse_args(["workbench", str(self.published.root)])

    def test_port_contract_is_closed(self) -> None:
        self.assertEqual(validate_port("1024"), 1024)
        self.assertEqual(validate_port("65535"), 65535)
        for value in ("0", "1023", "65536", "08765", "not-a-port"):
            with self.subTest(value=value), self.assertRaises(Exception):
                validate_port(value)

    def test_ready_line_is_canonical_and_ctrl_c_is_clean(self) -> None:
        port = available_port()
        stdout, stderr = io.StringIO(), io.StringIO()
        with (
            patch(
                "tiny_corpus_workbench.workbench_server."
                "WorkbenchHTTPServer.serve_forever",
                side_effect=KeyboardInterrupt,
            ),
            redirect_stdout(stdout),
            redirect_stderr(stderr),
        ):
            code = cli.main(
                [
                    "workbench",
                    "--workspace",
                    str(self.published.root.parent),
                    "--port",
                    str(port),
                    "--no-open",
                ]
            )
        self.assertEqual(code, 0)
        self.assertEqual(stderr.getvalue(), "")
        self.assertEqual(stdout.getvalue(), f"http://127.0.0.1:{port}/\n")

    def test_browser_failure_is_nonfatal_warning(self) -> None:
        port = available_port()
        stdout, stderr = io.StringIO(), io.StringIO()
        with (
            patch(
                "tiny_corpus_workbench.workbench_server."
                "WorkbenchHTTPServer.serve_forever",
                side_effect=KeyboardInterrupt,
            ),
            patch(
                "tiny_corpus_workbench.workbench_server.open_browser",
                return_value="browser could not be opened",
            ),
            redirect_stdout(stdout),
            redirect_stderr(stderr),
        ):
            code = cli.main(
                [
                    "workbench",
                    "--workspace",
                    str(self.published.root.parent),
                    "--port",
                    str(port),
                ]
            )
        self.assertEqual(code, 0)
        self.assertTrue(stdout.getvalue())
        self.assertEqual(stderr.getvalue(), "browser could not be opened\n")

    def test_ctrl_c_during_browser_open_closes_server_and_exits_cleanly(
        self,
    ) -> None:
        port = available_port()
        stdout, stderr = io.StringIO(), io.StringIO()
        with (
            patch(
                "tiny_corpus_workbench.workbench_server.open_browser",
                side_effect=KeyboardInterrupt,
            ),
            patch(
                "tiny_corpus_workbench.workbench_server."
                "WorkbenchHTTPServer.serve_forever",
                side_effect=AssertionError("serve must not start"),
            ),
            redirect_stdout(stdout),
            redirect_stderr(stderr),
        ):
            code = cli.main(
                [
                    "workbench",
                    "--workspace",
                    str(self.published.root.parent),
                    "--port",
                    str(port),
                ]
            )
        self.assertEqual(code, 0)
        self.assertEqual(stderr.getvalue(), "")
        self.assertEqual(stdout.getvalue(), f"http://127.0.0.1:{port}/\n")
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as probe:
            probe.bind(("127.0.0.1", port))

    def test_sigint_waits_for_synchronous_lifecycle_handler_before_close(
        self,
    ) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            workspace = Path(temporary) / "workspace"
            copied = (
                workspace
                / "extraction-observatory"
                / "observation"
                / self.published.root.name
            )
            copied.parent.mkdir(parents=True)
            shutil.copytree(self.published.root, copied)
            port = available_port()
            entered = threading.Event()
            release = threading.Event()
            completed = threading.Event()
            closed_after_completion: list[bool] = []
            interrupt_ready: list[bool] = []
            response_status: list[int] = []
            original_close = WorkbenchApplication.close

            def slow_diagnose(_service, _key):
                entered.set()
                release.wait(5)
                completed.set()
                return {
                    "publication": {
                        "kind": "DIAGNOSIS",
                        "run_id": "completed-before-shutdown",
                        "record_key": None,
                    },
                    "refresh": {"status": "FAILED", "message": "test"},
                }

            def checked_close(application):
                closed_after_completion.append(completed.is_set())
                return original_close(application)

            def request_lifecycle() -> None:
                deadline = time.monotonic() + 5
                while True:
                    connection = http.client.HTTPConnection(
                        "127.0.0.1", port, timeout=5
                    )
                    try:
                        connection.request("GET", "/api/workbench")
                        projection_response = connection.getresponse()
                        projection = json.loads(projection_response.read())
                        key = projection["records"][0]["record_key"]
                        connection.close()

                        connection = http.client.HTTPConnection(
                            "127.0.0.1", port, timeout=5
                        )
                        connection.request("GET", "/api/lifecycle/action-token")
                        token_response = connection.getresponse()
                        token = json.loads(token_response.read())["action_token"]
                        connection.close()

                        connection = http.client.HTTPConnection(
                            "127.0.0.1", port, timeout=5
                        )
                        connection.request(
                            "POST",
                            f"/api/lifecycle/diagnoses/{key}",
                            headers={
                                "Content-Length": "0",
                                "X-TCW-Action-Token": token,
                            },
                        )
                        response = connection.getresponse()
                        response.read()
                        response_status.append(response.status)
                        connection.close()
                        return
                    except ConnectionRefusedError:
                        connection.close()
                        if time.monotonic() >= deadline:
                            raise
                        time.sleep(0.01)

            client = threading.Thread(target=request_lifecycle, daemon=False)

            def interrupt_and_release() -> None:
                interrupt_ready.append(entered.wait(5))
                _thread.interrupt_main()
                time.sleep(0.1)
                release.set()

            interrupter = threading.Thread(
                target=interrupt_and_release, daemon=False
            )
            client.start()
            interrupter.start()
            with (
                patch.object(
                    WorkbenchLifecycleService,
                    "diagnose",
                    new=slow_diagnose,
                ),
                patch.object(
                    WorkbenchApplication,
                    "close",
                    new=checked_close,
                ),
                redirect_stdout(io.StringIO()),
                redirect_stderr(io.StringIO()),
            ):
                code = cli.main(
                    [
                        "workbench",
                        "--workspace",
                        str(workspace),
                        "--port",
                        str(port),
                        "--no-open",
                    ]
                )
            client.join(5)
            interrupter.join(5)

        self.assertEqual(code, 0)
        self.assertEqual(interrupt_ready, [True])
        self.assertEqual(response_status, [200])
        self.assertTrue(completed.is_set())
        self.assertEqual(closed_after_completion, [True])

    def test_missing_workspace_is_created_and_starts_empty(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            workspace = Path(temporary) / "missing"
            port = available_port()
            stdout, stderr = io.StringIO(), io.StringIO()
            with (
                patch(
                    "tiny_corpus_workbench.workbench_server."
                    "WorkbenchHTTPServer.serve_forever",
                    side_effect=KeyboardInterrupt,
                ),
                redirect_stdout(stdout),
                redirect_stderr(stderr),
            ):
                code = cli.main(
                    [
                        "workbench",
                        "--workspace",
                        str(workspace),
                        "--port",
                        str(port),
                        "--no-open",
                    ]
                )
            self.assertEqual(code, 0)
            self.assertTrue(workspace.is_dir())
            self.assertEqual(stderr.getvalue(), "")
            self.assertEqual(stdout.getvalue(), f"http://127.0.0.1:{port}/\n")

    def test_non_directory_workspace_fails_without_ready_output(self) -> None:
        stdout, stderr = io.StringIO(), io.StringIO()
        with tempfile.NamedTemporaryFile() as workspace:
            with redirect_stdout(stdout), redirect_stderr(stderr):
                code = cli.main(
                    ["workbench", "--workspace", workspace.name, "--no-open"]
                )
        self.assertEqual(code, 2)
        self.assertEqual(stdout.getvalue(), "")
        self.assertEqual(stderr.getvalue(), "workspace must be a directory\n")


if __name__ == "__main__":
    unittest.main()
