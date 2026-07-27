from __future__ import annotations

import shutil
import tempfile
import unittest
from pathlib import Path

from tiny_corpus_workbench.domain import InputError
from tiny_corpus_workbench.workbench_records import admit_record, admit_records
from tests.unit.workbench_test_support import PublishedObservation


class WorkbenchAdmissionTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.published = PublishedObservation()

    @classmethod
    def tearDownClass(cls) -> None:
        cls.published.close()

    def test_intrinsically_verified_explicit_root_is_admitted(self) -> None:
        admitted = admit_records([self.published.root])
        record = next(iter(admitted.records.values()))
        self.assertEqual(record.kind, "OBSERVATION")
        self.assertTrue(record.top_level)
        self.assertEqual(record.status, "SUCCESS")

    def test_repeated_explicit_root_is_rejected(self) -> None:
        with self.assertRaises(InputError):
            admit_records([self.published.root, self.published.root])

    def test_manifest_path_is_not_a_record_root(self) -> None:
        with self.assertRaises(InputError):
            admit_records([self.published.root / "manifest.json"])

    def _cancelled_alias_path(self, temporary: str) -> str:
        base = Path(temporary)
        copied = base / self.published.root.name
        shutil.copytree(self.published.root, copied)
        real = base / "real"
        real.mkdir()
        alias = base / "alias"
        alias.symlink_to(real, target_is_directory=True)
        return f"{alias}/../{copied.name}"

    def test_single_admission_rejects_cancelled_symlink_alias(self) -> None:
        with tempfile.TemporaryDirectory(dir="/private/tmp") as temporary:
            supplied = self._cancelled_alias_path(temporary)
            with self.assertRaises(InputError):
                admit_record(supplied)

    def test_batch_admission_rejects_cancelled_symlink_alias(self) -> None:
        with tempfile.TemporaryDirectory(dir="/private/tmp") as temporary:
            supplied = self._cancelled_alias_path(temporary)
            with self.assertRaises(InputError):
                admit_records([supplied])

    def test_dot_and_dot_dot_components_are_rejected(self) -> None:
        parent = self.published.root.parent
        supplied = (
            f"{parent}/./{self.published.root.name}",
            f"{self.published.root}/../{self.published.root.name}",
        )
        for path in supplied:
            with self.subTest(path=path), self.assertRaises(InputError):
                admit_record(path)

    def test_normal_absolute_path_remains_accepted(self) -> None:
        direct = admit_record(str(self.published.root))
        batch = admit_records([str(self.published.root)])
        self.assertEqual(direct.backing.root, self.published.root)
        self.assertEqual(
            next(iter(batch.records.values())).backing.root,
            self.published.root,
        )


if __name__ == "__main__":
    unittest.main()
