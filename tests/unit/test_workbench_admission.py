from __future__ import annotations

import json
import shutil
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from tiny_corpus_workbench.domain import InputError
from tiny_corpus_workbench import workbench_records
from tiny_corpus_workbench.workbench_records import admit_record, admit_records
from tests.unit.workbench_test_support import (
    PublishedCorpus,
    PublishedDiagnosis,
    PublishedObservation,
    PublishedRefinements,
)


class WorkbenchAdmissionTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.published = PublishedObservation()
        cls.diagnosis = PublishedDiagnosis()
        cls.refinements = PublishedRefinements()
        cls.corpus = PublishedCorpus()

    @classmethod
    def tearDownClass(cls) -> None:
        cls.published.close()
        cls.diagnosis.close()
        cls.refinements.close()
        cls.corpus.close()

    def test_intrinsically_verified_explicit_root_is_admitted(self) -> None:
        admitted = admit_records([self.published.root])
        record = next(iter(admitted.records.values()))
        self.assertEqual(record.kind, "OBSERVATION")
        self.assertTrue(record.top_level)
        self.assertEqual(record.status, "SUCCESS")
        metadata = record.backing.root.stat()
        self.assertEqual(
            (record.backing.device, record.backing.inode),
            (metadata.st_dev, metadata.st_ino),
        )

    def test_each_record_is_captured_once_for_the_workbench(self) -> None:
        with patch.object(
            workbench_records,
            "_capture_record",
            wraps=workbench_records._capture_record,
        ) as capture:
            admitted = admit_records([self.published.root])
        self.assertEqual(capture.call_count, 1)
        record = next(iter(admitted.records.values()))
        self.assertEqual(
            set(record.artifact_bytes),
            {
                (item["role"], item["path"], item["sha256"])
                for item in record.listed
            },
        )

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
        with tempfile.TemporaryDirectory(
            dir=Path(tempfile.gettempdir()).resolve()
        ) as temporary:
            supplied = self._cancelled_alias_path(temporary)
            with self.assertRaises(InputError):
                admit_record(supplied)

    def test_batch_admission_rejects_cancelled_symlink_alias(self) -> None:
        with tempfile.TemporaryDirectory(
            dir=Path(tempfile.gettempdir()).resolve()
        ) as temporary:
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

    def test_unknown_observation_header_is_rejected_with_guidance(self) -> None:
        with tempfile.TemporaryDirectory(
            dir=Path(tempfile.gettempdir()).resolve()
        ) as directory:
            copied = Path(directory) / self.published.root.name
            shutil.copytree(self.published.root, copied)
            manifest_path = copied / "manifest.json"
            manifest = json.loads(manifest_path.read_text("utf-8"))
            manifest["format_version"] = 99
            manifest_path.write_text(
                json.dumps(
                    manifest,
                    ensure_ascii=False,
                    sort_keys=True,
                    separators=(",", ":"),
                )
                + "\n",
                "utf-8",
            )
            with self.assertRaisesRegex(InputError, "regenerate"):
                admit_record(copied)

    def test_unknown_diagnosis_header_is_rejected_with_guidance(self) -> None:
        with tempfile.TemporaryDirectory(
            dir=Path(tempfile.gettempdir()).resolve()
        ) as directory:
            for name, mutation in (
                ("unknown", lambda value: value.update(format_version=99)),
                ("missing", lambda value: value.pop("record_type")),
            ):
                with self.subTest(name=name):
                    copied = Path(directory) / name / self.diagnosis.diagnosis.name
                    copied.parent.mkdir()
                    shutil.copytree(self.diagnosis.diagnosis, copied)
                    manifest_path = copied / "diagnosis-manifest.json"
                    manifest = json.loads(manifest_path.read_text("utf-8"))
                    mutation(manifest)
                    manifest_path.write_text(
                        json.dumps(
                            manifest,
                            ensure_ascii=False,
                            sort_keys=True,
                            separators=(",", ":"),
                        )
                        + "\n",
                        "utf-8",
                    )
                    with self.assertRaisesRegex(InputError, "regenerate"):
                        admit_record(copied)

    def test_unknown_refinement_header_is_rejected_with_guidance(self) -> None:
        with tempfile.TemporaryDirectory(
            dir=Path(tempfile.gettempdir()).resolve()
        ) as directory:
            copied = Path(directory) / self.refinements.applied.name
            shutil.copytree(self.refinements.applied, copied)
            manifest_path = copied / "refinement-manifest.json"
            manifest = json.loads(manifest_path.read_text("utf-8"))
            manifest["format_version"] = 99
            manifest_path.write_text(
                json.dumps(
                    manifest,
                    ensure_ascii=False,
                    sort_keys=True,
                    separators=(",", ":"),
                )
                + "\n",
                "utf-8",
            )
            with self.assertRaisesRegex(InputError, "regenerate"):
                admit_record(copied)

    def test_unknown_and_missing_corpus_header_are_rejected_with_guidance(
        self,
    ) -> None:
        with tempfile.TemporaryDirectory(
            dir=Path(tempfile.gettempdir()).resolve()
        ) as directory:
            for name, mutation in (
                ("unknown", lambda value: value.update(format_version=99)),
                ("missing", lambda value: value.pop("record_type")),
            ):
                with self.subTest(name=name):
                    copied = Path(directory) / name / self.corpus.root.name
                    copied.parent.mkdir()
                    shutil.copytree(self.corpus.root, copied)
                    manifest_path = copied / "corpus-manifest.json"
                    manifest = json.loads(manifest_path.read_text("utf-8"))
                    mutation(manifest)
                    manifest_path.write_text(
                        json.dumps(
                            manifest,
                            ensure_ascii=False,
                            sort_keys=True,
                            separators=(",", ":"),
                        )
                        + "\n",
                        "utf-8",
                    )
                    with self.assertRaisesRegex(InputError, "regenerate"):
                        admit_record(copied)


if __name__ == "__main__":
    unittest.main()
