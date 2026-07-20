from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from tiny_corpus_workbench.artifacts import (
    REQUIRED_MODEL_FILES,
    AtomicObservation,
    inventory_models,
)
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

    def test_publication_race_never_replaces_empty_or_non_empty_destination(self) -> None:
        for with_content in (False, True):
            with self.subTest(with_content=with_content), tempfile.TemporaryDirectory() as directory:
                root = Path(directory)
                publisher = AtomicObservation(root, "source", "run")
                with publisher as staging:
                    (staging / "new.txt").write_text("new", "utf-8")
                    publisher.destination.mkdir()
                    if with_content:
                        (publisher.destination / "existing.txt").write_text("existing", "utf-8")
                    with self.assertRaises(IntegrityError):
                        publisher.publish()
                self.assertFalse((publisher.destination / "new.txt").exists())
                if with_content:
                    self.assertEqual(
                        (publisher.destination / "existing.txt").read_text("utf-8"),
                        "existing",
                    )

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
            for relative in REQUIRED_MODEL_FILES:
                path = root / relative
                path.parent.mkdir(parents=True, exist_ok=True)
                path.write_bytes(relative.encode("utf-8"))
            result = inventory_models(root, required=True)
            self.assertEqual(
                [item["path"] for item in result["files"]],
                sorted(REQUIRED_MODEL_FILES),
            )
            (root / "link").symlink_to(root / REQUIRED_MODEL_FILES[0])
            with self.assertRaises(RuntimeContractError):
                inventory_models(root, required=True)
            alias = root.parent / "model-root-alias"
            alias.symlink_to(root)
            try:
                with self.assertRaises(RuntimeContractError):
                    inventory_models(alias, required=True)
            finally:
                alias.unlink()

    def test_required_inventory_rejects_unrelated_files(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root / "unrelated.bin").write_bytes(b"not a Docling model")
            with self.assertRaises(RuntimeContractError):
                inventory_models(root, required=True)

    def test_irrelevant_model_path_is_not_validated(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            alias = root / "irrelevant-model-link"
            alias.symlink_to(root / "missing-target")
            result = inventory_models(alias, required=False)
            self.assertFalse(result["required"])
            self.assertEqual(result["files"], [])


if __name__ == "__main__":
    unittest.main()
