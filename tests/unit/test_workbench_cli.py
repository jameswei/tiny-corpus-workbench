from __future__ import annotations

import io
import json
import socket
import unittest
from contextlib import redirect_stderr, redirect_stdout
from unittest.mock import patch

from tiny_corpus_workbench import cli
from tiny_corpus_workbench.workbench_server import validate_port
from tests.unit.workbench_server_test_support import available_port
from tests.unit.workbench_test_support import PublishedObservation


class WorkbenchCliTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.published = PublishedObservation()

    @classmethod
    def tearDownClass(cls) -> None:
        cls.published.close()

    def test_parser_exposes_only_fixed_port_and_browser_options(self) -> None:
        args = cli.parser().parse_args(
            ["workbench", str(self.published.root), "--port", "9123", "--no-open"]
        )
        self.assertEqual(args.command, "workbench")
        self.assertEqual(args.port, "9123")
        self.assertTrue(args.no_open)
        self.assertFalse(hasattr(args, "host"))

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
                    str(self.published.root),
                    "--port",
                    str(port),
                    "--no-open",
                ]
            )
        self.assertEqual(code, 0)
        self.assertEqual(stderr.getvalue(), "")
        raw = stdout.getvalue()
        value = json.loads(raw)
        self.assertEqual(
            raw,
            json.dumps(value, sort_keys=True, separators=(",", ":")) + "\n",
        )
        self.assertEqual(value["status"], "READY")
        self.assertEqual(value["record_count"], 1)
        self.assertEqual(value["top_level_record_count"], 1)
        self.assertEqual(value["contained_record_count"], 0)
        self.assertEqual(value["url"], f"http://127.0.0.1:{port}/")

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
                ["workbench", str(self.published.root), "--port", str(port)]
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
                ["workbench", str(self.published.root), "--port", str(port)]
            )
        self.assertEqual(code, 0)
        self.assertEqual(stderr.getvalue(), "")
        self.assertEqual(json.loads(stdout.getvalue())["status"], "READY")
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as probe:
            probe.bind(("127.0.0.1", port))

    def test_missing_root_and_unavailable_port_fail_without_ready_output(self) -> None:
        stdout, stderr = io.StringIO(), io.StringIO()
        with redirect_stdout(stdout), redirect_stderr(stderr):
            code = cli.main(["workbench", "/does/not/exist", "--no-open"])
        self.assertEqual(code, 2)
        self.assertEqual(stdout.getvalue(), "")
        self.assertNotIn("/does/not/exist", stderr.getvalue())


if __name__ == "__main__":
    unittest.main()
