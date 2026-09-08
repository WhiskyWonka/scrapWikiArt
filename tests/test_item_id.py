import re
import unittest

from ScrapWikiArt.utils import item_id


class TestItemId(unittest.TestCase):
    def test_deterministic(self):
        url = "https://www.wikiart.org/en/paintings/mona-lisa"
        self.assertEqual(item_id(url), item_id(url))

    def test_different_urls_differ(self):
        a = item_id("https://www.wikiart.org/en/paintings/a")
        b = item_id("https://www.wikiart.org/en/paintings/b")
        self.assertNotEqual(a, b)

    def test_format(self):
        self.assertRegex(item_id("https://example.com/x"), re.compile(r"[0-9a-f]{40}"))


if __name__ == "__main__":
    unittest.main()
