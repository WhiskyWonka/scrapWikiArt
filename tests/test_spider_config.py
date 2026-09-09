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


def make_spider(name, enabled=_UNSET, db_path=None, **kwargs):
    """Instantiate the spider class for `name` with injected Settings.

    Bare spider instances have no `settings` attribute (Scrapy 2.10 sets it
    only in from_crawler), so tests inject `spider.settings` directly.
    """
    spider = SPIDER_CLASSES[name](db_path=db_path, **kwargs)
    settings = Settings()
    if enabled is not _UNSET:
        settings.set("SPIDERS_ENABLED", enabled)
    if db_path is not None:
        settings.set("WIKIART_DB_PATH", db_path)
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
    """DDG spiders read source data from SQLite (issue #47, DD.1-DD.4)."""

    def _temp_db(self):
        fd, path = tempfile.mkstemp(suffix=".db")
        os.close(fd)
        self.addCleanup(os.unlink, path)
        return path

    def _seed(self, path, table="works", rows=()):
        from ScrapWikiArt import db
        conn = db.connect(path)
        try:
            db.create_tables(conn)
            for row in rows:
                db.insert_ignore(conn, table, row)
        finally:
            conn.close()

    def test_no_input_file_attribute(self):
        # DD.2: no input_file param, no CloseSpider on absence.
        spider = make_spider("duck_duck_go")
        self.assertFalse(hasattr(spider, "input_file"))

    def test_disabled_skips_db_read_and_yields_zero(self):
        # The disabled check wins over everything (issue #45).
        spider = make_spider("duck_duck_go_movement")
        with self.assertLogs(logging.getLogger(spider.name), level="INFO") as captured:
            requests = list(spider.start_requests())
        self.assertEqual(requests, [])
        self.assertIn(
            "Spider duck_duck_go_movement is disabled via SPIDERS_ENABLED, skipping",
            captured.output[0],
        )

    def test_disabled_all_variants_without_input_file(self):
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

    def test_enabled_with_unenriched_rows_yields_requests(self):
        # Two rows with empty Description AND WikiDescription -> 2 requests.
        path = self._temp_db()
        self._seed(path, "works", [
            {"Id": "a", "URL": "https://a.com", "Title": "Painting A",
             "Description": "", "WikiDescription": None, "scraped_at": "2024"},
            {"Id": "b", "URL": "https://b.com", "Title": "Painting B",
             "Description": None, "WikiDescription": None, "scraped_at": "2024"},
        ])
        spider = make_spider(
            "duck_duck_go",
            enabled=["duck_duck_go"],
            db_path=path,
        )
        requests = list(spider.start_requests())
        self.assertEqual(len(requests), 2)
        self.assertTrue(
            all(r.url.startswith("https://api.duckduckgo.com/?q=") for r in requests)
        )
        # The query is built from the item's query_feature (Title).
        self.assertTrue(any("q=Painting%20A" in r.url for r in requests))

    def test_enriched_rows_excluded(self):
        # A row with WikiDescription filled is NOT re-queried (DD.3).
        path = self._temp_db()
        self._seed(path, "works", [
            {"Id": "a", "URL": "https://a.com", "Title": "Painting A",
             "Description": "", "WikiDescription": "already enriched",
             "scraped_at": "2024"},
        ])
        spider = make_spider(
            "duck_duck_go",
            enabled=["duck_duck_go"],
            db_path=path,
        )
        requests = list(spider.start_requests())
        self.assertEqual(requests, [])

    def test_empty_table_yields_zero_requests(self):
        path = self._temp_db()
        self._seed(path, "works", [])
        spider = make_spider(
            "duck_duck_go",
            enabled=["duck_duck_go"],
            db_path=path,
        )
        self.assertEqual(list(spider.start_requests()), [])

    def test_missing_table_yields_zero_requests_and_warning(self):
        path = self._temp_db()  # file exists, no tables created
        spider = make_spider(
            "duck_duck_go",
            enabled=["duck_duck_go"],
            db_path=path,
        )
        with self.assertLogs(logging.getLogger(spider.name), level="WARNING") as captured:
            requests = list(spider.start_requests())
        self.assertEqual(requests, [])
        self.assertTrue(any("works" in msg for msg in captured.output))

    def test_artist_subclass_reads_from_db(self):
        # DD.4: duck_duck_go_artist reads the artists table.
        path = self._temp_db()
        self._seed(path, "artists", [
            {"Id": "a1", "Name": "Picasso", "Description": "", "WikiDescription": None},
        ])
        spider = make_spider(
            "duck_duck_go_artist",
            enabled=["duck_duck_go_artist"],
            db_path=path,
        )
        requests = list(spider.start_requests())
        self.assertEqual(len(requests), 1)
        self.assertTrue(any("Picasso" in r.url for r in requests))

    def test_ddg_init_explicit_db_path_parameter(self):
        """F8: DuckDuckGoSpider.__init__ accepts db_path as an explicit parameter."""
        spider = make_spider("duck_duck_go", db_path="/custom/path.db")
        self.assertEqual(spider.db_path, "/custom/path.db")

    def test_ddg_init_no_db_path_defaults_none(self):
        """F8: Without db_path, defaults to None."""
        spider = make_spider("duck_duck_go")
        self.assertIsNone(spider.db_path)

    def test_ddg_subclass_inherits_init(self):
        """F8: Subclasses inherit the explicit __init__ and instantiate fine."""
        for name in (
            "duck_duck_go_artist",
            "duck_duck_go_style",
            "duck_duck_go_movement",
            "duck_duck_go_school",
        ):
            spider = make_spider(name, db_path="/test.db")
            self.assertEqual(spider.db_path, "/test.db", name)


class TestDictSpidersSeenAttribute(unittest.TestCase):
    """CD.3: Dict spiders (artist/style/movement/school) must NOT have a `seen` attr."""

    def test_dict_spiders_no_seen(self):
        for name in ("wikiart_artist", "wikiart_style", "wikiart_movement", "wikiart_school"):
            spider = make_spider(name)
            self.assertFalse(hasattr(spider, "seen"), name)

    def test_dict_spiders_no_sampling(self):
        """Spec: sampling is exclusive to the wikiart spider (issue #48)."""
        for name in ("wikiart_artist", "wikiart_style", "wikiart_movement", "wikiart_school"):
            spider = make_spider(name)
            self.assertFalse(hasattr(spider, "_p"), name)
            self.assertFalse(hasattr(spider, "_rng"), name)
            self.assertFalse(hasattr(spider, "_init_sampling"), name)


class TestPipelineOrdering(unittest.TestCase):
    """ITEM_PIPELINES wiring across spiders (SP.5, D7)."""

    def test_wikiart_works_pipeline_before_images(self):
        spider = make_spider("wikiart")
        pipelines = spider.custom_settings["ITEM_PIPELINES"]
        self.assertEqual(
            pipelines["ScrapWikiArt.pipelines.SQLiteWorksPipeline"], 1
        )
        self.assertEqual(
            pipelines["scrapy.pipelines.images.ImagesPipeline"], 2
        )

    def test_dict_spiders_use_dictionary_pipeline(self):
        for name in ("wikiart_artist", "wikiart_style", "wikiart_movement", "wikiart_school"):
            spider = make_spider(name)
            self.assertEqual(
                spider.custom_settings["ITEM_PIPELINES"],
                {"ScrapWikiArt.pipelines.SQLiteDictionaryPipeline": 1},
                name,
            )

    def test_ddg_spiders_use_update_pipeline(self):
        # All 5 DDG spiders inherit the base custom_settings (D5).
        for name in (
            "duck_duck_go",
            "duck_duck_go_artist",
            "duck_duck_go_style",
            "duck_duck_go_movement",
            "duck_duck_go_school",
        ):
            spider = make_spider(name)
            self.assertEqual(
                spider.custom_settings["ITEM_PIPELINES"],
                {"ScrapWikiArt.pipelines.SQLiteUpdatePipeline": 1},
                name,
            )


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