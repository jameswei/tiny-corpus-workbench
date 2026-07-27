from __future__ import annotations

import shutil
import tempfile
import unittest
from pathlib import Path

from tools.validate_workbench_assets import validate


ROOT = Path(__file__).resolve().parents[2]
ASSETS = ROOT / "src/tiny_corpus_workbench/workbench_assets"


class WorkbenchUIContractTests(unittest.TestCase):
    def test_bundled_assets_pass_the_offline_validator(self) -> None:
        self.assertEqual(validate(ASSETS), [])

    def test_asset_inventory_has_no_build_or_runtime_dependency(self) -> None:
        self.assertEqual(
            {path.name for path in ASSETS.iterdir() if path.is_file()},
            {"index.html", "workbench.css", "workbench.js"},
        )

    def test_html_has_semantic_navigation_and_live_focus_targets(self) -> None:
        html = (ASSETS / "index.html").read_text("utf-8")
        for marker in (
            '<a class="skip-link" href="#workspace">',
            "<header",
            "<nav",
            "<main",
            'role="status"',
            'aria-live="polite"',
            'id="record-heading" tabindex="-1"',
        ):
            with self.subTest(marker=marker):
                self.assertIn(marker, html)

    def test_styles_cover_focus_narrow_screen_reduced_motion_and_non_color_state(
        self,
    ) -> None:
        css = (ASSETS / "workbench.css").read_text("utf-8")
        for marker in (
            ":focus-visible",
            "@media (max-width:",
            "@media (prefers-reduced-motion: reduce)",
            ".status::before",
            ".status-na::before",
        ):
            with self.subTest(marker=marker):
                self.assertIn(marker, css)

    def test_script_contains_every_required_view_and_state_explanation(self) -> None:
        script = (ASSETS / "workbench.js").read_text("utf-8")
        for marker in (
            "renderObservation",
            "renderDiagnosis",
            "renderRefinement",
            "renderCorpus",
            "Source metadata",
            "Ten extractor comparison metrics",
            "Affected references",
            "Revision chain",
            "Family and format matrix",
            "Artifact integrity",
            "MATCH:",
            "MISSING:",
            "NOT_CHECKED:",
            "NOT_APPLICABLE:",
        ):
            with self.subTest(marker=marker):
                self.assertIn(marker, script)
        self.assertIn(
            "return `${displayName(record.status)} ${displayName(record.kind)}",
            script,
        )

    def test_ui_uses_exactly_the_ten_comparison_metrics(
        self,
    ) -> None:
        script = (ASSETS / "workbench.js").read_text("utf-8")
        start = script.index("const COMPARISON_METRICS = [")
        end = script.index("];", start)
        block = script[start:end]
        expected = {
            "bytes",
            "characters",
            "non_whitespace_characters",
            "lines",
            "non_empty_lines",
            "atx_headings",
            "unordered_list_items",
            "ordered_list_items",
            "pipe_table_rows",
            "visible_urls",
        }
        self.assertEqual(
            {
                line.strip().strip('",')
                for line in block.splitlines()[1:]
                if line.strip()
            },
            expected,
        )
        self.assertEqual(script.count("COMPARISON_METRICS.map"), 1)
        self.assertIn(
            '"Member extractor comparison metrics"',
            script,
        )
        self.assertIn(
            '"Member normalized equality"',
            script,
        )
        self.assertIn(
            '{label: "Docling", render: (row) => metricValue(row.docling, row.metric)}',
            script,
        )
        self.assertIn(
            '{label: "MarkItDown", render: (row) => metricValue(row.markitdown, row.metric)}',
            script,
        )
        self.assertIn(
            '{label: "Signed delta", render: (row) => signedMetricValue(row.delta, row.metric)}',
            script,
        )

    def test_corpus_comparison_unavailable_and_signed_values_are_explicit(
        self,
    ) -> None:
        script = (ASSETS / "workbench.js").read_text("utf-8")
        self.assertIn('return view === null ? "Not available" : view[metric];', script)
        self.assertIn('return value >= 0 ? `+${value}` : String(value);', script)
        self.assertIn(
            'row.docling_minus_markitdown === null ? "Not available"',
            script,
        )

    def test_artifact_content_requires_a_button_action_and_plain_text_fetch(
        self,
    ) -> None:
        script = (ASSETS / "workbench.js").read_text("utf-8")
        self.assertIn('"Retrieve plain text"', script)
        self.assertIn('headers: {"Accept": "text/plain"}', script)
        self.assertIn("await response.text()", script)
        self.assertIn('result.textContent = await response.text()', script)

    def test_script_has_no_html_execution_navigation_or_persistence_capability(
        self,
    ) -> None:
        script = (ASSETS / "workbench.js").read_text("utf-8")
        for forbidden in (
            "innerHTML",
            "outerHTML",
            "insertAdjacentHTML",
            "document.write",
            "eval(",
            "new Function",
            "window.open",
            "location",
            "localStorage",
            "sessionStorage",
            "indexedDB",
            "serviceWorker",
        ):
            with self.subTest(forbidden=forbidden):
                self.assertNotIn(forbidden, script)
        self.assertIn("document.createElement", script)
        self.assertIn(".textContent", script)

    def test_validator_rejects_remote_assets_and_unsafe_dom_construction(self) -> None:
        with tempfile.TemporaryDirectory(
            dir=Path(tempfile.gettempdir()).resolve()
        ) as temporary:
            copy = Path(temporary)
            for source in ASSETS.iterdir():
                shutil.copyfile(source, copy / source.name)
            js_path = copy / "workbench.js"
            js_path.write_text(
                js_path.read_text("utf-8")
                + '\ndocument.body.innerHTML = "<img>";\n'
                + 'fetch("https://example.invalid/data");\n',
                "utf-8",
            )
            errors = validate(copy)
        self.assertTrue(any("remote" in error for error in errors))
        self.assertTrue(any("innerHTML" in error for error in errors))

    def test_validator_rejects_external_html_resource(self) -> None:
        with tempfile.TemporaryDirectory(
            dir=Path(tempfile.gettempdir()).resolve()
        ) as temporary:
            copy = Path(temporary)
            for source in ASSETS.iterdir():
                shutil.copyfile(source, copy / source.name)
            html_path = copy / "index.html"
            html_path.write_text(
                html_path.read_text("utf-8").replace(
                    "</head>",
                    '<link rel="stylesheet" href="https://example.invalid/x.css"></head>',
                ),
                "utf-8",
            )
            errors = validate(copy)
        self.assertTrue(any("non-local" in error for error in errors))
        self.assertTrue(any("remote" in error for error in errors))


if __name__ == "__main__":
    unittest.main()
