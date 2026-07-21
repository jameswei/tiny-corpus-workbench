from __future__ import annotations

import os
import tempfile
import unittest
from pathlib import Path

from tiny_corpus_workbench.domain import InputError
from tiny_corpus_workbench.source import validate_source


class SourceValidationTests(unittest.TestCase):
    def test_valid_utf8_text_records_identity(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "Hello world.txt"
            path.write_text("hello\n", "utf-8")
            identity = validate_source(path)
        self.assertEqual(identity.media_type, "text/plain")
        self.assertRegex(identity.key, r"^hello-world-[0-9a-f]{12}$")
        self.assertEqual(identity.size, 6)

    def test_rejects_url_directory_fifo_and_unsupported_suffix(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            unsupported = root / "file.csv"
            unsupported.write_text("x", "utf-8")
            fifo = root / "pipe.txt"
            os.mkfifo(fifo)
            for value in ("https://example.invalid/file.pdf", root, unsupported, fifo):
                with self.subTest(value=value), self.assertRaises(InputError):
                    validate_source(value)

    def test_rejects_extension_content_mismatch_and_invalid_text(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            cases = {"bad.pdf": b"not pdf", "bad.docx": b"not zip", "bad.md": b"\xff", "nul.txt": b"a\x00b"}
            for name, content in cases.items():
                path = root / name
                path.write_bytes(content)
                with self.subTest(name=name), self.assertRaises(InputError):
                    validate_source(path)

    def test_rejects_empty_markdown_and_text(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            for name in ("empty.md", "empty.txt"):
                path = root / name
                path.touch()
                with self.subTest(name=name), self.assertRaisesRegex(
                    InputError, "must not be empty"
                ):
                    validate_source(path)


if __name__ == "__main__":
    unittest.main()
