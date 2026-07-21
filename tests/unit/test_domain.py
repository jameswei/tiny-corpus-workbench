from __future__ import annotations

import unittest

from tiny_corpus_workbench.domain import StableError, sanitize_message


class MessageSanitizerTests(unittest.TestCase):
    def test_all_c0_c1_controls_are_replaced_before_collapse(self) -> None:
        cases = (
            ("nul", "left\x00right", "left right"),
            ("tab", "left\tright", "left right"),
            ("del", "left\x7fright", "left right"),
            ("c1", "left\x80\x85\x9fright", "left right"),
            ("lines", "left\r\nright", "left right"),
            ("unicode", "  你好\x01 café\t🙂  ", "你好 café 🙂"),
            ("fallback", "\x00\t\n\x7f\x80\x9f", "unspecified failure"),
        )
        for label, value, expected in cases:
            with self.subTest(label=label):
                self.assertEqual(sanitize_message(value), expected)

        controls = "".join(
            chr(codepoint)
            for codepoint in (*range(0x20), *range(0x7F, 0xA0))
        )
        sanitized = sanitize_message(f"start{controls}end")
        self.assertEqual(sanitized, "start end")
        self.assertLessEqual(len(sanitize_message("界" * 600)), 500)
        self.assertEqual(
            StableError("TEST", controls).message,
            "unspecified failure",
        )


if __name__ == "__main__":
    unittest.main()
