import unittest

from ScrapWikiArt.utils import clean_name


class TestCleanName(unittest.TestCase):
    def test_returns_first_non_empty_stripped(self):
        self.assertEqual(clean_name("  Impressionism  ", None), "Impressionism")

    def test_skips_none_and_empty(self):
        self.assertEqual(clean_name(None, "", "  Baroque  "), "Baroque")

    def test_returns_none_when_all_missing(self):
        self.assertIsNone(clean_name(None, None))
        self.assertIsNone(clean_name("", None))
        self.assertIsNone(clean_name(None, "", "   "))

    def test_strips_whitespace_only_value(self):
        self.assertIsNone(clean_name("   "))

    def test_preserves_internal_whitespace(self):
        self.assertEqual(clean_name("Art Nouveau"), "Art Nouveau")


if __name__ == "__main__":
    unittest.main()
