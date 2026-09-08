import unittest

from scrapy.settings import Settings

from ScrapWikiArt.spiders.duck_duck_go import DuckDuckGoSpider
from ScrapWikiArt.spiders.duck_duck_go_artist import DuckDuckGoArtistSpider
from ScrapWikiArt.spiders.duck_duck_go_movement import DuckDuckGoMovementSpider
from ScrapWikiArt.spiders.duck_duck_go_school import DuckDuckGoSchoolSpider
from ScrapWikiArt.spiders.duck_duck_go_style import DuckDuckGoStyleSpider
from ScrapWikiArt.spiders.wikiart import WikiArtSpider
from ScrapWikiArt.spiders.wikiart_artist import WikiArtArtistSpider as WikiArtArtistSpider
from ScrapWikiArt.spiders.wikiart_movement import WikiArtArtistSpider as WikiArtMovementSpider
from ScrapWikiArt.spiders.wikiart_school import WikiArtArtistSpider as WikiArtSchoolSpider
from ScrapWikiArt.spiders.wikiart_style import WikiArtArtistSpider as WikiArtStyleSpider
from ScrapWikiArt.utils import spider_is_disabled

# All 10 spiders. wikiart_style/movement/school intentionally reuse the
# copy-pasted WikiArtArtistSpider class name (do not rename — issue #45).
SPIDER_CLASSES = {
    "wikiart": WikiArtSpider,
    "wikiart_artist": WikiArtArtistSpider,
    "wikiart_style": WikiArtStyleSpider,
    "wikiart_movement": WikiArtMovementSpider,
    "wikiart_school": WikiArtSchoolSpider,
    "duck_duck_go": DuckDuckGoSpider,
    "duck_duck_go_artist": DuckDuckGoArtistSpider,
    "duck_duck_go_style": DuckDuckGoStyleSpider,
    "duck_duck_go_movement": DuckDuckGoMovementSpider,
    "duck_duck_go_school": DuckDuckGoSchoolSpider,
}

_UNSET = object()


def make_spider(name, enabled=_UNSET):
    """Instantiate the spider class for `name` with injected Settings.

    Bare spider instances have no `settings` attribute (Scrapy 2.10 sets it
    only in from_crawler), so tests inject `spider.settings` directly.
    """
    spider = SPIDER_CLASSES[name]()
    settings = Settings()
    if enabled is not _UNSET:
        settings.set("SPIDERS_ENABLED", enabled)
    spider.settings = settings
    return spider


class TestSpiderIsDisabled(unittest.TestCase):
    """Three-state fail-closed determination via SPIDERS_ENABLED."""

    def test_unset_falls_back_to_default(self):
        # Default is ["wikiart"]: only wikiart is enabled, the other 9 are not.
        for name in SPIDER_CLASSES:
            spider = make_spider(name)
            if name == "wikiart":
                self.assertFalse(spider_is_disabled(spider), name)
            else:
                self.assertTrue(spider_is_disabled(spider), name)

    def test_none_falls_back_to_default(self):
        # Explicit None behaves like unset -> default ["wikiart"].
        for name in SPIDER_CLASSES:
            spider = make_spider(name, enabled=None)
            if name == "wikiart":
                self.assertFalse(spider_is_disabled(spider), name)
            else:
                self.assertTrue(spider_is_disabled(spider), name)

    def test_empty_list_disables_all(self):
        # Explicit [] is the CI-safe kill switch: every spider disabled.
        for name in SPIDER_CLASSES:
            spider = make_spider(name, enabled=[])
            self.assertTrue(spider_is_disabled(spider), name)

    def test_custom_list_enables_only_named(self):
        for name in SPIDER_CLASSES:
            spider = make_spider(name, enabled=["duck_duck_go_artist"])
            if name == "duck_duck_go_artist":
                self.assertFalse(spider_is_disabled(spider), name)
            else:
                self.assertTrue(spider_is_disabled(spider), name)

    def test_comma_string_splits(self):
        # Defensive for the unsupported -s side channel: a comma-string value
        # behaves like the equivalent list (mirrors getlist).
        for name in SPIDER_CLASSES:
            spider = make_spider(name, enabled="wikiart_movement,wikiart_school")
            if name in ("wikiart_movement", "wikiart_school"):
                self.assertFalse(spider_is_disabled(spider), name)
            else:
                self.assertTrue(spider_is_disabled(spider), name)


if __name__ == "__main__":
    unittest.main()