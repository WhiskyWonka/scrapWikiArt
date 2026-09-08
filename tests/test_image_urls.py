import unittest

from ScrapWikiArt.utils import image_urls_or_empty


class TestImageUrlsOrEmpty(unittest.TestCase):
    def test_uses_variants_when_present(self):
        variants = ["/img/a.jpg", "/img/b.jpg"]
        self.assertEqual(image_urls_or_empty(variants, "/img/fallback.jpg"), variants)

    def test_filters_empty_strings_from_variants(self):
        self.assertEqual(image_urls_or_empty(["", "/img/a.jpg"], "/f.jpg"), ["/img/a.jpg"])

    def test_falls_back_when_no_variants(self):
        self.assertEqual(image_urls_or_empty([], "/img/fallback.jpg"), ["/img/fallback.jpg"])

    def test_returns_empty_when_nothing_found(self):
        self.assertEqual(image_urls_or_empty([], None), [])
        self.assertEqual(image_urls_or_empty([], ""), [])

    def test_no_none_in_result(self):
        self.assertNotIn(None, image_urls_or_empty([], None))
        self.assertNotIn(None, image_urls_or_empty([], ""))


if __name__ == "__main__":
    unittest.main()
