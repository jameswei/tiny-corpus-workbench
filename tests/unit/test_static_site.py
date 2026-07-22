from __future__ import annotations

import shutil
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path


REPOSITORY_ROOT = Path(__file__).resolve().parents[2]
VALIDATOR = REPOSITORY_ROOT / "tools" / "validate_site.py"
SOURCE_SITE = REPOSITORY_ROOT / "site"


class StaticSiteValidationTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temporary_directory = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary_directory.cleanup)
        self.site = Path(self.temporary_directory.name) / "site"
        shutil.copytree(SOURCE_SITE, self.site)

    def validate(self) -> subprocess.CompletedProcess[str]:
        return subprocess.run(
            [sys.executable, str(VALIDATOR), str(self.site)],
            check=False,
            capture_output=True,
            text=True,
        )

    def assert_invalid(self, expected: str) -> None:
        result = self.validate()
        self.assertNotEqual(result.returncode, 0, result.stdout)
        self.assertIn(expected, result.stdout)

    def replace(self, path: str, old: str, new: str) -> None:
        target = self.site / path
        target.write_text(target.read_text(encoding="utf-8").replace(old, new), encoding="utf-8")

    def test_valid_temporary_site(self) -> None:
        result = self.validate()
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assertIn("site validation passed: 4 files", result.stdout)

    def test_missing_asset_fails(self) -> None:
        (self.site / "assets" / "favicon.svg").unlink()
        self.assert_invalid("assets/favicon.svg:1: expected regular file is missing")

    def test_broken_fragment_fails(self) -> None:
        self.replace("index.html", 'href="#workflow"', 'href="#unknown"')
        self.assert_invalid("local fragment does not resolve: #unknown")

    def test_duplicate_id_fails(self) -> None:
        self.replace("index.html", '<section class="section"', '<section id="top" class="section"')
        self.assert_invalid("duplicate id: top")

    def test_path_escape_fails(self) -> None:
        self.replace("index.html", 'href="styles.css"', 'href="../outside.css"')
        self.assert_invalid("local reference escapes the site root")

    def test_root_relative_reference_fails(self) -> None:
        self.replace("index.html", 'href="styles.css"', 'href="/styles.css"')
        self.assert_invalid("root-relative reference is forbidden")

    def test_symbolic_link_fails(self) -> None:
        favicon = self.site / "assets" / "favicon.svg"
        favicon.unlink()
        favicon.symlink_to(self.site / "styles.css")
        self.assert_invalid("symbolic links are not allowed")

    def test_forbidden_interactive_element_fails(self) -> None:
        self.replace("index.html", "</main>", "<form><input></form></main>")
        self.assert_invalid("forbidden element: form")
        self.assert_invalid("forbidden element: input")

    def test_external_dependency_fails(self) -> None:
        self.replace(
            "index.html",
            '<link rel="stylesheet" href="styles.css">',
            '<link rel="stylesheet" href="https://example.com/site.css">',
        )
        self.assert_invalid("external style sheets are forbidden")
        self.assert_invalid("external runtime dependency is forbidden")


if __name__ == "__main__":
    unittest.main()
