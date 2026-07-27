from __future__ import annotations

import shutil
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

import tiny_corpus_workbench.workbench_records as workbench_records
from tiny_corpus_workbench.artifacts import canonical_json as artifact_json
from tiny_corpus_workbench.canonical_json import artifact_key
from tiny_corpus_workbench.domain import IntegrityError
from tiny_corpus_workbench.workbench_projection import build_projection
from tiny_corpus_workbench.workbench_records import (
    _equivalence,
    _collapse_physical,
    Backing,
    admit_record,
    admit_records,
)
from tests.unit.workbench_test_support import PublishedObservation


class WorkbenchPhysicalBackingTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.published = PublishedObservation()

    @classmethod
    def tearDownClass(cls) -> None:
        cls.published.close()

    def _copied_record(self, label: str) -> Path:
        copied = (
            Path(self.published.temporary.name)
            / label
            / self.published.root.name
        )
        copied.parent.mkdir()
        shutil.copytree(self.published.root, copied)
        return copied

    def test_detail_does_not_expose_physical_backing(self) -> None:
        built = build_projection(admit_records([self.published.root]))
        payload = built.detail_bytes(next(iter(built.details)))
        self.assertNotIn(str(self.published.root).encode(), payload)
        self.assertNotIn(b'"backing"', payload)

    def test_canonical_artifact_mutation_is_detected(self) -> None:
        copied = self._copied_record("copy")
        admitted = admit_records([copied])
        built = build_projection(admitted)
        descriptor = next(iter(built.details.values()))["artifacts"][0]
        target = copied / descriptor["relative_path"]
        target.write_bytes(target.read_bytes() + b"x")
        with self.assertRaises(IntegrityError):
            admitted.recheck_artifact(descriptor)

    def test_projection_uses_frozen_artifact_after_post_admission_mutation(self) -> None:
        copied = self._copied_record("mutation")
        admitted = admit_records([copied])
        before = build_projection(admitted).projection_bytes()
        record = next(iter(admitted.records.values()))
        comparison = copied / next(
            item["path"]
            for item in record.listed
            if item["role"] == "comparison-summary"
        )
        comparison.write_bytes(comparison.read_bytes() + b"x")
        after = build_projection(admitted).projection_bytes()
        self.assertEqual(after, before)

    def test_projection_uses_frozen_artifact_after_symlink_race(self) -> None:
        copied = self._copied_record("symlink")
        admitted = admit_records([copied])
        before = build_projection(admitted).projection_bytes()
        record = next(iter(admitted.records.values()))
        comparison = copied / next(
            item["path"]
            for item in record.listed
            if item["role"] == "comparison-summary"
        )
        replacement = copied / "replacement.json"
        replacement.write_bytes(comparison.read_bytes())
        comparison.unlink()
        comparison.symlink_to(replacement)
        self.assertEqual(build_projection(admitted).projection_bytes(), before)
        descriptor = next(
            item
            for item in next(iter(build_projection(admitted).details.values()))[
                "artifacts"
            ]
            if item["role"] == "comparison-summary"
        )
        with self.assertRaises(IntegrityError):
            admitted.recheck_artifact(descriptor)

    def test_fabricated_and_mismatched_descriptors_are_not_authorized(self) -> None:
        copied = self._copied_record("authorization")
        admitted = admit_records([copied])
        built = build_projection(admitted)
        record = next(iter(admitted.records.values()))
        fabricated_path = copied / "undeclared.json"
        fabricated_path.write_text("{}", encoding="utf-8")
        fabricated = {
            **next(iter(built.details.values()))["manifest"],
            "artifact_key": artifact_key(
                record_key=record.record_key,
                role="comparison-summary",
                relative_path="undeclared.json",
                sha256="0" * 64,
            ),
            "role": "comparison-summary",
            "relative_path": "undeclared.json",
            "sha256": "0" * 64,
            "size": 2,
            "origin": "MANIFEST_LISTED",
        }
        with self.assertRaises(IntegrityError):
            admitted.recheck_artifact(fabricated)
        authorized = next(iter(built.details.values()))["manifest"]
        changed = {**authorized, "relative_path": "undeclared.json"}
        with self.assertRaises(IntegrityError):
            admitted.recheck_artifact(changed)

    def test_record_key_is_absent_until_copy_equivalence(self) -> None:
        physical = admit_record(self.published.root)
        self.assertIsNone(physical.record_key)
        with patch(
            "tiny_corpus_workbench.workbench_records.record_key",
            side_effect=AssertionError("record key was computed during physical admission"),
        ):
            second = admit_record(self.published.root)
        self.assertEqual(_equivalence(physical), _equivalence(second))

    def test_unchanged_descriptor_capture_is_deterministic(self) -> None:
        copied = self._copied_record("stable-capture")
        first = admit_record(copied)
        second = admit_record(copied)
        self.assertEqual(first.manifest_bytes, second.manifest_bytes)
        self.assertEqual(first.artifact_bytes, second.artifact_bytes)
        self.assertEqual(_equivalence(first), _equivalence(second))

    def test_intrinsic_verifier_is_bound_to_broken_first_capture(self) -> None:
        copied = self._copied_record("captured-broken-aba")
        manifest_path = copied / "manifest.json"
        manifest = __import__("json").loads(
            manifest_path.read_text("utf-8")
        )
        manifest["run_id"] = "captured-but-never-verified"
        manifest_path.write_bytes(artifact_json(manifest))
        backup = copied.with_name(f".{copied.name}.broken")
        original_verify = workbench_records._verify_intrinsic

        def valid_live_only_during_verify(kind: str, snapshot: Path) -> None:
            self.assertNotEqual(snapshot.resolve(), copied.resolve())
            copied.rename(backup)
            shutil.copytree(self.published.root, copied)
            try:
                original_verify(kind, snapshot)
            finally:
                shutil.rmtree(copied)
                backup.rename(copied)

        with (
            patch.object(
                workbench_records,
                "_verify_intrinsic",
                side_effect=valid_live_only_during_verify,
            ),
            self.assertRaises(IntegrityError),
        ):
            admit_record(copied)

    def test_valid_capture_accepts_exact_live_restore_during_verify(self) -> None:
        copied = self._copied_record("valid-aba-restored")
        backup = copied.with_name(f".{copied.name}.original")
        original_verify = workbench_records._verify_intrinsic

        def replace_then_restore(kind: str, snapshot: Path) -> None:
            self.assertNotEqual(snapshot.resolve(), copied.resolve())
            copied.rename(backup)
            shutil.copytree(backup, copied)
            try:
                original_verify(kind, snapshot)
            finally:
                shutil.rmtree(copied)
                backup.rename(copied)

        with patch.object(
            workbench_records,
            "_verify_intrinsic",
            side_effect=replace_then_restore,
        ):
            admitted = admit_record(copied)
        self.assertEqual(admitted.manifest_bytes, (copied / "manifest.json").read_bytes())

    def test_valid_capture_rejects_changed_live_restore_during_verify(self) -> None:
        copied = self._copied_record("valid-aba-changed")
        backup = copied.with_name(f".{copied.name}.original")
        comparison = copied / "comparison.json"
        original = comparison.read_bytes()
        original_verify = workbench_records._verify_intrinsic

        def replace_restore_then_change(kind: str, snapshot: Path) -> None:
            self.assertNotEqual(snapshot.resolve(), copied.resolve())
            copied.rename(backup)
            shutil.copytree(backup, copied)
            try:
                original_verify(kind, snapshot)
            finally:
                shutil.rmtree(copied)
                backup.rename(copied)
                comparison.write_bytes(original + b"\n")

        try:
            with (
                patch.object(
                    workbench_records,
                    "_verify_intrinsic",
                    side_effect=replace_restore_then_change,
                ),
                self.assertRaises(IntegrityError),
            ):
                admit_record(copied)
        finally:
            comparison.write_bytes(original)

    def test_unrelated_private_tmp_churn_does_not_reject_admission(self) -> None:
        with tempfile.TemporaryDirectory(
            dir=Path(tempfile.gettempdir()).resolve()
        ) as temporary:
            copied = Path(temporary) / self.published.root.name
            shutil.copytree(self.published.root, copied)
            original_verify = workbench_records._verify_intrinsic

            def verify_with_unrelated_churn(kind: str, snapshot: Path) -> None:
                with tempfile.TemporaryDirectory(
                    dir=Path(tempfile.gettempdir()).resolve()
                ) as churn:
                    (Path(churn) / "unrelated.txt").write_text(
                        "unrelated", encoding="utf-8"
                    )
                    original_verify(kind, snapshot)

            with patch.object(
                workbench_records,
                "_verify_intrinsic",
                side_effect=verify_with_unrelated_churn,
            ):
                admitted = admit_record(copied)
            self.assertEqual(admitted.backing.root, copied)

    def test_parent_symlink_alias_is_rejected_before_canonicalization(self) -> None:
        with tempfile.TemporaryDirectory(
            dir=Path(tempfile.gettempdir()).resolve()
        ) as temporary:
            base = Path(temporary)
            real = base / "real"
            real.mkdir()
            copied = real / self.published.root.name
            shutil.copytree(self.published.root, copied)
            alias = base / "alias"
            alias.symlink_to(real, target_is_directory=True)

            with self.assertRaises(IntegrityError):
                admit_record(alias / copied.name)

    def test_nested_parent_symlink_alias_is_rejected(self) -> None:
        with tempfile.TemporaryDirectory(
            dir=Path(tempfile.gettempdir()).resolve()
        ) as temporary:
            base = Path(temporary)
            real = base / "real"
            nested = real / "nested"
            nested.mkdir(parents=True)
            copied = nested / self.published.root.name
            shutil.copytree(self.published.root, copied)
            alias = base / "alias"
            alias.symlink_to(real, target_is_directory=True)

            with self.assertRaises(IntegrityError):
                admit_record(alias / "nested" / copied.name)

    def test_final_component_symlink_alias_is_rejected(self) -> None:
        with tempfile.TemporaryDirectory(
            dir=Path(tempfile.gettempdir()).resolve()
        ) as temporary:
            base = Path(temporary)
            copied = base / self.published.root.name
            shutil.copytree(self.published.root, copied)
            alias = base / "record-alias"
            alias.symlink_to(copied, target_is_directory=True)

            with self.assertRaises(IntegrityError):
                admit_record(alias)

    def test_post_verifier_manifest_symlink_replacement_is_rejected(self) -> None:
        copied = self._copied_record("manifest-post-verifier")
        manifest = copied / "manifest.json"
        backup = copied / ".manifest.backup"
        original_verify = workbench_records._verify_intrinsic

        def verify_then_replace(kind: str, root: Path) -> None:
            original_verify(kind, root)
            manifest.rename(backup)
            manifest.symlink_to(backup.name)

        try:
            with (
                patch.object(
                    workbench_records,
                    "_verify_intrinsic",
                    side_effect=verify_then_replace,
                ),
                self.assertRaises(IntegrityError),
            ):
                admit_record(copied)
        finally:
            manifest.unlink(missing_ok=True)
            if backup.exists():
                backup.rename(manifest)

    def test_post_verifier_content_mutation_is_rejected(self) -> None:
        copied = self._copied_record("content-post-verifier")
        artifact = copied / "comparison.json"
        original = artifact.read_bytes()
        original_verify = workbench_records._verify_intrinsic

        def verify_then_mutate(kind: str, root: Path) -> None:
            original_verify(kind, root)
            artifact.write_bytes(original + b"\n")

        try:
            with (
                patch.object(
                    workbench_records,
                    "_verify_intrinsic",
                    side_effect=verify_then_mutate,
                ),
                self.assertRaises(IntegrityError),
            ):
                admit_record(copied)
        finally:
            artifact.write_bytes(original)

    def _assert_between_open_and_read_rejected(
        self, label: str, substitute
    ) -> None:
        copied = self._copied_record(label)
        target = copied / "comparison.json"
        restore = substitute(target)
        real_open = workbench_records._open_no_follow
        armed = True

        def open_then_substitute(
            path: str, flags: int, *, dir_fd: int | None = None
        ) -> int:
            nonlocal armed
            descriptor = real_open(path, flags, dir_fd=dir_fd)
            if armed and path == target.name:
                armed = False
                restore("MUTATE")
            return descriptor

        try:
            with (
                patch.object(
                    workbench_records,
                    "_open_no_follow",
                    side_effect=open_then_substitute,
                ),
                self.assertRaises(IntegrityError),
            ):
                admit_record(copied)
        finally:
            restore("RESTORE")

    def test_between_open_and_read_artifact_symlink_is_rejected(self) -> None:
        def substitution(target: Path):
            backup = target.with_name(".comparison.symlink-backup")

            def mutate(action: str) -> None:
                if action == "MUTATE":
                    target.rename(backup)
                    target.symlink_to(backup.name)
                else:
                    target.unlink(missing_ok=True)
                    if backup.exists():
                        backup.rename(target)

            return mutate

        self._assert_between_open_and_read_rejected(
            "capture-symlink", substitution
        )

    def test_between_open_and_read_artifact_hardlink_is_rejected(self) -> None:
        def substitution(target: Path):
            backup = target.with_name(".comparison.hardlink-backup")

            def mutate(action: str) -> None:
                if action == "MUTATE":
                    target.rename(backup)
                    target.hardlink_to(backup)
                else:
                    target.unlink(missing_ok=True)
                    if backup.exists():
                        backup.rename(target)

            return mutate

        self._assert_between_open_and_read_rejected(
            "capture-hardlink", substitution
        )

    def test_between_open_and_read_atomic_replacement_is_rejected(self) -> None:
        def substitution(target: Path):
            original = target.read_bytes()

            def mutate(action: str) -> None:
                if action == "MUTATE":
                    replacement = target.with_name(".comparison.replacement")
                    replacement.write_bytes(original)
                    replacement.replace(target)
                else:
                    target.write_bytes(original)

            return mutate

        self._assert_between_open_and_read_rejected(
            "capture-atomic-replacement", substitution
        )

    def test_post_verifier_directory_substitution_is_rejected(self) -> None:
        copied = self._copied_record("directory-substitution")
        directory = copied / "docling"
        backup = copied / ".docling.backup"
        original_verify = workbench_records._verify_intrinsic

        def verify_then_replace(kind: str, root: Path) -> None:
            original_verify(kind, root)
            directory.rename(backup)
            shutil.copytree(backup, directory)

        try:
            with (
                patch.object(
                    workbench_records,
                    "_verify_intrinsic",
                    side_effect=verify_then_replace,
                ),
                self.assertRaises(IntegrityError),
            ):
                admit_record(copied)
        finally:
            if directory.exists():
                shutil.rmtree(directory)
            if backup.exists():
                backup.rename(directory)

    def test_post_verifier_root_substitution_is_rejected(self) -> None:
        copied = self._copied_record("root-substitution")
        backup = copied.with_name(f".{copied.name}.backup")
        original_verify = workbench_records._verify_intrinsic

        def verify_then_replace(kind: str, root: Path) -> None:
            original_verify(kind, root)
            copied.rename(backup)
            shutil.copytree(backup, copied)

        try:
            with (
                patch.object(
                    workbench_records,
                    "_verify_intrinsic",
                    side_effect=verify_then_replace,
                ),
                self.assertRaises(IntegrityError),
            ):
                admit_record(copied)
        finally:
            if copied.exists():
                shutil.rmtree(copied)
            if backup.exists():
                backup.rename(copied)

    def _physical_copy(self, label: str, corpus_key: str):
        copied = (
            Path(self.published.temporary.name)
            / label
            / self.published.root.name
        )
        copied.parent.mkdir()
        shutil.copytree(self.published.root, copied)
        return admit_record(
            copied,
            backing=Backing(
                root=copied,
                containing_corpus_key=corpus_key,
                member_id=label,
                descriptor_path=f"members/{label}/manifest.json",
            ),
        )

    def test_contained_backing_tuple_order_and_top_level_precedence(self) -> None:
        later = self._physical_copy("z-member", "f" * 64)
        earlier = self._physical_copy("a-member", "0" * 64)
        collapsed = next(iter(_collapse_physical([later, earlier]).values()))
        self.assertEqual(collapsed.backing.root, earlier.backing.root)

        explicit = admit_record(self.published.root)
        collapsed = next(
            iter(_collapse_physical([earlier, explicit, later]).values())
        )
        self.assertEqual(collapsed.backing.root, self.published.root)
        self.assertTrue(collapsed.top_level)

    def test_conflict_rejects_before_record_key_computation(self) -> None:
        first = self._physical_copy("conflict-a", "1" * 64)
        second = self._physical_copy("conflict-b", "2" * 64)
        manifest_path = second.backing.root / "manifest.json"
        manifest = __import__("json").loads(manifest_path.read_text("utf-8"))
        manifest["created_at"] = "2026-07-27T00:00:00Z"
        manifest_path.write_bytes(artifact_json(manifest))
        second = admit_record(second.backing.root, backing=second.backing)
        self.assertEqual(first.logical_copy_key, second.logical_copy_key)
        with patch(
            "tiny_corpus_workbench.workbench_records.record_key",
            side_effect=AssertionError("conflict reached record-key computation"),
        ), self.assertRaises(IntegrityError):
            _collapse_physical([first, second])

    def test_noncanonical_mutation_does_not_change_frozen_authorization(self) -> None:
        canonical = self._physical_copy("canonical", "0" * 64)
        noncanonical = self._physical_copy("noncanonical", "f" * 64)
        records = _collapse_physical([noncanonical, canonical])
        admitted = type("_Session", (), {})()
        admitted.records = records
        record = next(iter(records.values()))
        descriptor = record.descriptors()[1][0]
        target = noncanonical.backing.root / descriptor["relative_path"]
        target.write_bytes(target.read_bytes() + b"x")
        # The canonical copy remains the only authorized backing.
        from tiny_corpus_workbench.workbench_records import AdmittedRecords

        session = AdmittedRecords(records, set(), [])
        self.assertEqual(
            session.recheck_artifact(descriptor),
            (
                canonical.backing.root / descriptor["relative_path"]
            ).read_bytes(),
        )
        with self.assertRaises(IntegrityError):
            admit_record(noncanonical.backing.root, backing=noncanonical.backing)

    def test_mutation_between_descriptor_read_and_name_recheck_is_rejected(
        self,
    ) -> None:
        copied = self._copied_record("during-content-capture")
        admitted = admit_records([copied])
        built = build_projection(admitted)
        descriptor = next(iter(built.details.values()))["manifest"]
        target = copied / descriptor["relative_path"]
        original = target.read_bytes()
        read_open_regular = workbench_records._read_open_regular

        def mutate_after_read(file_descriptor: int):
            captured = read_open_regular(file_descriptor)
            target.write_bytes(b"x" * len(original))
            return captured

        try:
            with (
                patch.object(
                    workbench_records,
                    "_read_open_regular",
                    side_effect=mutate_after_read,
                ),
                self.assertRaises(IntegrityError),
            ):
                admitted.recheck_artifact(descriptor)
        finally:
            target.write_bytes(original)


if __name__ == "__main__":
    unittest.main()
