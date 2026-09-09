import logging
import os
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

import scrapy
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


def make_spider(name, enabled=_UNSET, **kwargs):
    """Instantiate the spider class for `name` with injected Settings.

    Bare spider instances have no `settings` attribute (Scrapy 2.10 sets it
    only in from_crawler), so tests inject `spider.settings` directly.
    """
    spider = SPIDER_CLASSES[name](**kwargs)
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

    def test_comma_string_strips_entries(self):
        # Entries with surrounding whitespace must not silently misconfigure:
        # "wikiart, wikiart_artist" enables both, never " wikiart_artist".
        for name in SPIDER_CLASSES:
            spider = make_spider(name, enabled="wikiart, wikiart_artist")
            if name in ("wikiart", "wikiart_artist"):
                self.assertFalse(spider_is_disabled(spider), name)
            else:
                self.assertTrue(spider_is_disabled(spider), name)


class TestGuards(unittest.TestCase):
    """start_requests() no-op behavior for disabled spiders."""

    def test_default_config_disables_all_but_wikiart(self):
        # Default is ["wikiart"]: wikiart crawls, the other 9 no-op.
        for name in SPIDER_CLASSES:
            spider = make_spider(name)  # unset -> default
            if name == "wikiart":
                requests = list(spider.start_requests())
                self.assertEqual([r.url for r in requests], spider.start_urls)
            else:
                with self.assertLogs(logging.getLogger(spider.name), level="INFO") as captured:
                    requests = list(spider.start_requests())
                self.assertEqual(requests, [])
                self.assertEqual(
                    captured.output,
                    [
                        f"INFO:{spider.name}:Spider {name} is disabled via "
                        "SPIDERS_ENABLED, skipping"
                    ],
                )

    def test_disabled_logs_and_yields_zero(self):
        # Pinned message + empty stream, no exception (wikiart_artist).
        spider = make_spider("wikiart_artist")
        with self.assertLogs(logging.getLogger(spider.name), level="INFO") as captured:
            requests = list(spider.start_requests())
        self.assertEqual(requests, [])
        self.assertEqual(len(captured.output), 1)
        self.assertIn(
            "Spider wikiart_artist is disabled via SPIDERS_ENABLED, skipping",
            captured.output[0],
        )

    def test_empty_list_disables_even_wikiart(self):
        # Explicit [] is the kill switch: wikiart also no-ops (issue #45).
        spider = make_spider("wikiart", enabled=[])
        with self.assertLogs(logging.getLogger(spider.name), level="INFO"):
            requests = list(spider.start_requests())
        self.assertEqual(requests, [])

    def test_enabled_yields_start_urls(self):
        # Enabled spider crawls exactly as before the change.
        spider = make_spider("wikiart", enabled=["wikiart"])
        requests = list(spider.start_requests())
        self.assertEqual([r.url for r in requests], spider.start_urls)

    def test_custom_list_enables_only_named(self):
        # Custom single-spider enable: wikiart_style crawls, rest no-op.
        for name in SPIDER_CLASSES:
            spider = make_spider(name, enabled=["wikiart_style"])
            if name == "wikiart_style":
                requests = list(spider.start_requests())
                self.assertEqual([r.url for r in requests], spider.start_urls)
            else:
                with self.assertLogs(logging.getLogger(spider.name), level="INFO"):
                    requests = list(spider.start_requests())
                self.assertEqual(requests, [])


class TestDuckDuckGoGuard(unittest.TestCase):
    """The disabled check wins over input-file validation (issue #45)."""

    def test_disabled_without_input_file_no_close_spider(self):
        spider = make_spider("duck_duck_go_movement")  # default -> disabled
        self.assertIsNone(spider.input_file)
        with self.assertLogs(logging.getLogger(spider.name), level="INFO") as captured:
            requests = list(spider.start_requests())
        self.assertEqual(requests, [])
        self.assertIn(
            "Spider duck_duck_go_movement is disabled via SPIDERS_ENABLED, skipping",
            captured.output[0],
        )

    def test_disabled_all_variants_without_input_file(self):
        # Every DDG variant shares the base guard: zero requests, no raise.
        for name in (
            "duck_duck_go",
            "duck_duck_go_artist",
            "duck_duck_go_style",
            "duck_duck_go_movement",
            "duck_duck_go_school",
        ):
            spider = make_spider(name)
            with self.assertLogs(logging.getLogger(spider.name), level="INFO"):
                requests = list(spider.start_requests())
            self.assertEqual(requests, [], name)

    def test_enabled_without_input_file_still_raises(self):
        spider = make_spider("duck_duck_go_movement", enabled=["duck_duck_go_movement"])
        with self.assertRaises(scrapy.exceptions.CloseSpider):
            list(spider.start_requests())

    def test_enabled_with_input_file_yields_requests(self):
        # Two empty-Description rows -> two DDG API requests.
        with tempfile.NamedTemporaryFile(mode="w", suffix=".csv", delete=False) as f:
            f.write("Name,Description\nRow one,\nRow two,\n")
            path = f.name
        try:
            spider = make_spider(
                "duck_duck_go_movement",
                enabled=["duck_duck_go_movement"],
                input_file=path,
            )
            requests = list(spider.start_requests())
            self.assertEqual(len(requests), 2)
            self.assertTrue(
                all(r.url.startswith("https://api.duckduckgo.com/?q=") for r in requests)
            )
        finally:
            os.unlink(path)


class TestDisabledCrawl(unittest.TestCase):
    """Subprocess E2E: disabled spider exits 0 with the no-op log."""

    def test_disabled_cli_exits_zero(self):
        repo_root = Path(__file__).resolve().parent.parent
        proc = subprocess.run(
            [sys.executable, "-m", "scrapy", "crawl", "duck_duck_go_movement"],
            cwd=repo_root,
            capture_output=True,
            text=True,
            timeout=120,
        )
        self.assertEqual(proc.returncode, 0)
        self.assertIn(
            "Spider duck_duck_go_movement is disabled via SPIDERS_ENABLED, skipping",
            proc.stderr,
        )
        self.assertNotIn("CloseSpider", proc.stderr)


if __name__ == "__main__":
    unittest.main()