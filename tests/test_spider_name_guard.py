import unittest

from ScrapWikiArt.spiders.wikiart_artist import WikiArtArtistSpider as ArtistSpider
from ScrapWikiArt.spiders.wikiart_style import WikiArtArtistSpider as StyleSpider
from ScrapWikiArt.spiders.wikiart_movement import WikiArtArtistSpider as MovementSpider
from ScrapWikiArt.spiders.wikiart_school import WikiArtArtistSpider as SchoolSpider


class FakeSelectorList:
    """Minimal parsel-like fake: get() returns value or None."""

    def __init__(self, value=None):
        self._value = value

    def get(self):
        return self._value

    def getall(self):
        return [self._value] if self._value is not None else []


class FakeResponse:
    def __init__(self, url, h1_value=None):
        self.url = url
        self._h1_value = h1_value

    def xpath(self, query):
        if "dictionary-illustration-container" in query or "main/header/h1" in query:
            return FakeSelectorList(self._h1_value)
        if "main/div/article/h3" in query and self._h1_value is not None:
            return FakeSelectorList(self._h1_value)
        return FakeSelectorList()  # description raw → None


class TestSpiderNameGuard(unittest.TestCase):
    def test_skips_item_without_name(self):
        for spider in (StyleSpider(), MovementSpider(), SchoolSpider()):
            with self.subTest(spider=spider.name):
                response = FakeResponse("https://example.com/style", h1_value=None)
                items = list(spider.parse_style(response))
                self.assertEqual(items, [])

    def test_yields_item_with_name(self):
        for spider in (StyleSpider(), MovementSpider(), SchoolSpider()):
            with self.subTest(spider=spider.name):
                response = FakeResponse("https://example.com/style", h1_value="  Impressionism  ")
                items = list(spider.parse_style(response))
                self.assertEqual(len(items), 1)
                self.assertEqual(items[0]["Name"], "Impressionism")
                self.assertEqual(items[0]["Link"], "https://example.com/style")

    def test_artist_name_is_none_without_h3(self):
        # Issue #28: missing <h3> must yield Name=None, not an empty SelectorList.
        spider = ArtistSpider()
        response = FakeResponse("https://example.com/artist", h1_value=None)
        items = list(spider.parse_artist(response))
        self.assertEqual(len(items), 1)
        self.assertIsNone(items[0]["Name"])

    def test_artist_name_cleaned_with_h3(self):
        spider = ArtistSpider()
        response = FakeResponse("https://example.com/artist", h1_value="  Claude  Monet  ")
        items = list(spider.parse_artist(response))
        self.assertEqual(len(items), 1)
        self.assertEqual(items[0]["Name"], "Claude Monet")


if __name__ == "__main__":
    unittest.main()
