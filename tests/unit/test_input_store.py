from __future__ import annotations

import hashlib
import os
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from tiny_corpus_workbench.application.input_store import (
    MAX_UPLOAD_BYTES,
    store_uploaded_input,
    validate_upload_filename,
)
from tiny_corpus_workbench.domain import IntegrityError, InputError


class InputStoreTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temporary = tempfile.TemporaryDirectory()
        self.root = Path(self.temporary.name)
        self.workspace = self.root / "workspace"

    def tearDown(self) -> None:
        self.temporary.cleanup()

    def staged_entries(self) -> list[Path]:
        inputs = self.workspace / "inputs"
        return list(inputs.glob(".staging-*")) if inputs.exists() else []

    def test_valid_upload_is_content_addressed_and_duplicate_is_reused(
        self,
    ) -> None:
        content = b"# Uploaded memo\n"
        stored = store_uploaded_input(self.workspace, "memo.md", content)
        expected_digest = hashlib.sha256(content).hexdigest()
        self.assertEqual(
            stored.path,
            self.workspace / "inputs" / expected_digest / "memo.md",
        )
        self.assertEqual(stored.path.read_bytes(), content)
        self.assertEqual(stored.sha256, expected_digest)
        self.assertEqual(stored.size, len(content))
        before = stored.path.stat()

        duplicate = store_uploaded_input(self.workspace, "memo.md", content)

        after = duplicate.path.stat()
        self.assertEqual(duplicate, stored)
        self.assertEqual((before.st_dev, before.st_ino), (after.st_dev, after.st_ino))
        self.assertEqual(self.staged_entries(), [])

    def test_exact_limit_is_accepted_and_larger_input_is_rejected(self) -> None:
        accepted = b"x" * MAX_UPLOAD_BYTES
        stored = store_uploaded_input(self.workspace, "limit.txt", accepted)
        self.assertEqual(stored.size, MAX_UPLOAD_BYTES)
        self.assertTrue(stored.path.is_file())

        with self.assertRaisesRegex(InputError, "33,554,432-byte limit"):
            store_uploaded_input(
                self.workspace,
                "too-large.txt",
                accepted + b"x",
            )
        self.assertFalse(
            any(
                path.name == "too-large.txt"
                for path in (self.workspace / "inputs").rglob("*")
            )
        )
        self.assertEqual(self.staged_entries(), [])

    def test_invalid_filenames_publish_nothing(self) -> None:
        invalid = (
            "",
            ".",
            "..",
            "nested/name.md",
            "nested\\name.md",
            "nul\x00name.md",
            "unsupported.csv",
            f"{'é' * 126}a.md",
        )
        for filename in invalid:
            with self.subTest(filename=filename), self.assertRaises(InputError):
                validate_upload_filename(filename)
        self.assertFalse(self.workspace.exists())

    def test_invalid_content_cleans_staging_and_publishes_nothing(self) -> None:
        cases = (
            ("empty.md", b""),
            ("invalid.md", b"\xff"),
            ("nul.txt", b"a\x00b"),
            ("mismatch.pdf", b"not a PDF"),
            ("mismatch.docx", b"not a ZIP"),
        )
        for filename, content in cases:
            with self.subTest(filename=filename), self.assertRaises(InputError):
                store_uploaded_input(self.workspace, filename, content)
            self.assertEqual(self.staged_entries(), [])
        inputs = self.workspace / "inputs"
        self.assertEqual(list(inputs.iterdir()), [])

    def test_existing_nonidentical_or_nonregular_target_is_never_overwritten(
        self,
    ) -> None:
        content = b"same claimed hash\n"
        digest = hashlib.sha256(content).hexdigest()
        digest_root = self.workspace / "inputs" / digest
        digest_root.mkdir(parents=True)
        target = digest_root / "conflict.txt"
        target.write_bytes(b"different bytes\n")

        with self.assertRaisesRegex(IntegrityError, "conflicts"):
            store_uploaded_input(self.workspace, target.name, content)
        self.assertEqual(target.read_bytes(), b"different bytes\n")
        self.assertEqual(self.staged_entries(), [])

        target.unlink()
        target.mkdir()
        with self.assertRaisesRegex(IntegrityError, "conflicts"):
            store_uploaded_input(self.workspace, target.name, content)
        self.assertTrue(target.is_dir())
        self.assertEqual(self.staged_entries(), [])

    def test_atomic_publication_failure_cleans_staging_and_target(self) -> None:
        with mock.patch(
            "tiny_corpus_workbench.application.input_store.os.link",
            side_effect=OSError("publication unavailable"),
        ), self.assertRaisesRegex(IntegrityError, "publication failed"):
            store_uploaded_input(self.workspace, "memo.md", b"# Memo\n")
        self.assertEqual(self.staged_entries(), [])
        inputs = self.workspace / "inputs"
        self.assertEqual(list(inputs.iterdir()), [])

    def test_unusable_inputs_directory_uses_domain_error(self) -> None:
        self.workspace.mkdir()
        (self.workspace / "inputs").write_text("not a directory", "utf-8")
        with self.assertRaisesRegex(InputError, "workspace inputs"):
            store_uploaded_input(self.workspace, "memo.md", b"# Memo\n")

        (self.workspace / "inputs").unlink()
        (self.workspace / "inputs").mkdir()
        with mock.patch(
            "tiny_corpus_workbench.application.input_store.os.access",
            return_value=False,
        ), self.assertRaisesRegex(InputError, "readable, writable, and searchable"):
            store_uploaded_input(self.workspace, "memo.md", b"# Memo\n")


if __name__ == "__main__":
    unittest.main()
