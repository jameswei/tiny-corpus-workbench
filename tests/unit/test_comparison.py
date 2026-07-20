from __future__ import annotations

import hashlib
import unittest

from tiny_corpus_workbench.comparison import make_comparison, normalize_markdown


class ComparisonTests(unittest.TestCase):
    def test_normalization_is_exact_and_idempotent(self) -> None:
        source = "\r\nCafe\u0301  \r\n\t\r\n".encode("utf-8")
        expected = "Caf\u00e9\n"
        self.assertEqual(normalize_markdown(source), expected)
        self.assertEqual(normalize_markdown(expected), expected)

    def test_metrics_and_docling_minus_markitdown_deltas(self) -> None:
        docling = b"# Title\n\n- one\n1. two\n| A | B |\nhttps://example.invalid/x\n"
        markitdown = b"Title\n\n- one\nhttps://example.invalid/x\n"
        result = make_comparison(
            {"sha256": "a" * 64, "media_type": "text/markdown", "fixture_id": None},
            {"url": "https://example.invalid/x"},
            (docling, hashlib.sha256(docling).hexdigest()),
            (markitdown, hashlib.sha256(markitdown).hexdigest()),
        )
        self.assertEqual(result["status"], "COMPLETE")
        self.assertEqual(result["deltas"]["atx_headings"], 1)
        self.assertEqual(result["deltas"]["ordered_list_items"], 1)
        self.assertFalse(result["deltas"]["normalized_equal"])
        self.assertTrue(result["views"]["docling"]["anchors"]["url"])

    def test_unavailable_views_have_no_deltas(self) -> None:
        result = make_comparison(
            {"sha256": "a" * 64, "media_type": "text/plain", "fixture_id": None},
            {},
            None,
            None,
        )
        self.assertEqual(result["status"], "NOT_AVAILABLE")
        self.assertIsNone(result["deltas"])


if __name__ == "__main__":
    unittest.main()
