from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from tiny_corpus_workbench.artifacts import AtomicObservation, inventory_models
from tiny_corpus_workbench.domain import IntegrityError, RuntimeContractError


class ArtifactTests(unittest.TestCase):
    def test_atomic_publication_and_no_overwrite(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            publisher = AtomicObservation(root, "source", "run")
            with publisher as staging:
                (staging / "evidence.txt").write_text("evidence", "utf-8")
                published = publisher.publish()
            self.assertEqual((published / "evidence.txt").read_text("utf-8"), "evidence")
            with self.assertRaises(IntegrityError):
                with AtomicObservation(root, "source", "run"):
                    pass

    def test_staging_is_discarded_after_failure(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            with self.assertRaisesRegex(RuntimeError, "stop"):
                with AtomicObservation(root, "source", "run") as staging:
                    (staging / "partial").write_text("x", "utf-8")
                    raise RuntimeError("stop")
            self.assertFalse((root / "source/run").exists())
            self.assertEqual(list((root / "source").iterdir()), [])

    def test_model_inventory_is_sorted_and_rejects_symlinks(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root / "b").write_bytes(b"b")
            (root / "a").write_bytes(b"a")
            result = inventory_models(root, required=True)
            self.assertEqual([item["path"] for item in result["files"]], ["a", "b"])
            (root / "link").symlink_to(root / "a")
            with self.assertRaises(RuntimeContractError):
                inventory_models(root, required=True)
            alias = root.parent / "model-root-alias"
            alias.symlink_to(root)
            try:
                with self.assertRaises(RuntimeContractError):
                    inventory_models(alias, required=True)
            finally:
                alias.unlink()


if __name__ == "__main__":
    unittest.main()
