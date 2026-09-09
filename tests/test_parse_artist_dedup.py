import logging
import os
import sqlite3
import tempfile
import unittest
from unittest.mock import patch

import scrapy.http
from scrapy.settings import Settings

from ScrapWikiArt import db
from ScrapWikiArt.spiders.wikiart import WikiArtSpider

ARTIST_LISTING_BODY = b"""
<html><body><main><div><ul>
<li><a href="/en/paintings/one">One</a></li>
<li><a href="/en/paintings/two">Two</a></li>
</ul></div></main></body></html>
"""


def _artist_response():
    return scrapy.http.HtmlResponse(
        url="https://www.wikiart.org/en/artist/test/all-works/text-list",
        body=ARTIST_LISTING_BODY,
        encoding="utf-8",
    )


def _make_spider(db_path=None, enabled=None):
    spider = WikiArtSpider()
    settings = Settings()
    if db_path is not None:
        settings.set("WIKIART_DB_PATH", db_path)
    if enabled is not None:
        settings.set("SPIDERS_ENABLED", enabled)
    spider.settings = settings
    return spider


class TestParseArtistDedup(unittest.TestCase):
    def test_first_pass_yields_all_urls(self):
        spider = _make_spider()
        spider.seen = set()
        response = _artist_response()
        requests = list(spider.parse_artist(response))
        self.assertEqual(len(requests), 2)
        self.assertEqual(
            {r.url for r in requests},
            {
                "https://www.wikiart.org/en/paintings/one",
                "https://www.wikiart.org/en/paintings/two",
            },
        )

    def test_second_pass_yields_zero(self):
        spider = _make_spider()
        spider.seen = set()
        response = _artist_response()
        list(spider.parse_artist(response))
        requests = list(spider.parse_artist(response))
        self.assertEqual(requests, [])

    def test_pre_seeded_seen_skips_urls(self):
        spider = _make_spider()
        spider.seen = {"https://www.wikiart.org/en/paintings/one"}
        requests = list(spider.parse_artist(_artist_response()))
        self.assertEqual(len(requests), 1)
        self.assertEqual(
            requests[0].url, "https://www.wikiart.org/en/paintings/two"
        )

    def test_seen_initialized_in_init(self):
        spider = _make_spider()
        self.assertEqual(spider.seen, set())


class TestStartRequestsSeeding(unittest.TestCase):
    def test_seeds_seen_from_existing_db(self):
        fd, path = tempfile.mkstemp(suffix=".db")
        os.close(fd)
        try:
            conn = db.connect(path)
            db.create_tables(conn)
            db.insert_ignore(conn, "works", {
                "Id": "a", "URL": "https://www.wikiart.org/en/paintings/one",
                "scraped_at": "2024-01-01",
            })
            db.insert_ignore(conn, "works", {
                "Id": "b", "URL": "https://www.wikiart.org/en/paintings/two",
                "scraped_at": "2024-01-01",
            })
            conn.close()

            spider = _make_spider(db_path=path, enabled=["wikiart"])
            list(spider.start_requests())
            self.assertEqual(
                spider.seen,
                {
                    "https://www.wikiart.org/en/paintings/one",
                    "https://www.wikiart.org/en/paintings/two",
                },
            )
        finally:
            os.unlink(path)

    def test_fresh_db_missing_table_no_crash(self):
        fd, path = tempfile.mkstemp(suffix=".db")
        os.close(fd)
        try:
            # No create_tables call: the works table does not exist yet
            # (pipeline creates it only after start_requests is consumed).
            spider = _make_spider(db_path=path, enabled=["wikiart"])
            list(spider.start_requests())  # must not raise
            self.assertEqual(spider.seen, set())
        finally:
            os.unlink(path)

    def test_disabled_spider_skips_seeding(self):
        fd, path = tempfile.mkstemp(suffix=".db")
        os.close(fd)
        try:
            conn = db.connect(path)
            db.create_tables(conn)
            db.insert_ignore(conn, "works", {
                "Id": "a", "URL": "https://www.wikiart.org/en/paintings/one",
                "scraped_at": "2024-01-01",
            })
            conn.close()

            spider = _make_spider(db_path=path, enabled=[])  # kill switch
            with self.assertLogs(logging.getLogger(spider.name), level="INFO"):
                requests = list(spider.start_requests())
            self.assertEqual(requests, [])
            self.assertEqual(spider.seen, set())
        finally:
            os.unlink(path)

    def test_db_error_during_seeding_logs_warning_and_continues(self):
        """F7: If load_seen_urls raises sqlite3.Error, spider still starts."""
        fd, path = tempfile.mkstemp(suffix=".db")
        os.close(fd)
        try:
            # Create a valid DB with a works table
            conn = db.connect(path)
            db.create_tables(conn)
            db.insert_ignore(conn, "works", {
                "Id": "a", "URL": "https://www.wikiart.org/en/paintings/one",
                "scraped_at": "2024-01-01",
            })
            conn.close()

            spider = _make_spider(db_path=path, enabled=["wikiart"])
            # Patch load_seen_urls to raise sqlite3.Error
            def _explode(conn):
                raise sqlite3.Error("simulated failure")
            with patch.object(db, "load_seen_urls", _explode):
                with self.assertLogs(logging.getLogger(spider.name), level="WARNING"):
                    requests = list(spider.start_requests())
            # seen set should be empty but spider still yields its start URLs
            self.assertEqual(spider.seen, set())
            self.assertEqual(
                [r.url for r in requests], spider.start_urls
            )
        finally:
            os.unlink(path)


if __name__ == "__main__":
    unittest.main()
