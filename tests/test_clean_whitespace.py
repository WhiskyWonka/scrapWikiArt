import unittest

from ScrapWikiArt.utils import clean_whitespace


class TestCleanWhitespace(unittest.TestCase):
    def test_none_returns_none(self):
        self.assertIsNone(clean_whitespace(None))

    def test_empty_string(self):
        self.assertEqual(clean_whitespace(""), "")

    def test_whitespace_only(self):
        self.assertEqual(clean_whitespace("  "), "")

    def test_strips_surrounding_whitespace(self):
        self.assertEqual(clean_whitespace("  Hello  "), "Hello")

    def test_collapses_newline_to_space(self):
        self.assertEqual(clean_whitespace("Hello\nWorld"), "Hello World")

    def test_collapses_tabs_to_space(self):
        self.assertEqual(clean_whitespace("Hello\t\tWorld"), "Hello World")

    def test_collapses_multiple_spaces(self):
        self.assertEqual(clean_whitespace("Hello   World"), "Hello World")

    def test_strips_leading_and_trailing_newlines(self):
        self.assertEqual(clean_whitespace("\nHello\n"), "Hello")

    def test_no_change_already_clean(self):
        self.assertEqual(clean_whitespace("Hello World"), "Hello World")


if __name__ == "__main__":
    unittest.main()
