import os
import sqlite3
import tempfile
import unittest
from unittest.mock import MagicMock

from ScrapWikiArt.db import connect, create_tables, insert_ignore, table_exists
from ScrapWikiArt.items import (
    ArtistItem,
    ImageItem,
    MovementItem,
    SchoolItem,
    StyleItem,
    UpdatedMovementItem,
    UpdatedSchoolItem,
    UpdatedStyleItem,
)
from ScrapWikiArt.pipelines import (
    SQLiteDictionaryPipeline,
    SQLiteUpdatePipeline,
    SQLiteWorksPipeline,
)


def _temp_db_path():
    fd, path = tempfile.mkstemp(suffix=".db")
    os.close(fd)
    os.unlink(path)  # pipeline will create it via connect()
    return path


class TestSQLiteWorksPipeline(unittest.TestCase):
    def setUp(self):
        self.db_path = _temp_db_path()
        self.pipeline = None

    def tearDown(self):
        if self.pipeline is not None:
            self.pipeline.close_spider(MagicMock())
        if os.path.exists(self.db_path):
            os.unlink(self.db_path)

    def _make_pipeline(self):
        self.pipeline = SQLiteWorksPipeline()
        spider = MagicMock()
        spider.settings = {"WIKIART_DB_PATH": self.db_path}
        self.pipeline.open_spider(spider)
        return self.pipeline, spider

    def test_open_creates_table(self):
        p, _ = self._make_pipeline()
        conn = connect(self.db_path)
        try:
            self.assertTrue(table_exists(conn, "works"))
        finally:
            conn.close()

    def test_insert_round_trip(self):
        p, _ = self._make_pipeline()
        item = ImageItem({
            "Id": "abc123",
            "URL": "https://example.com/art",
            "Title": "Test Painting",
            "Author": "Test Author",
            "Description": "A test",
            "image_urls": ["https://example.com/img.jpg"],
        })
        result = p.process_item(item, MagicMock())
        self.assertIs(result, item)
        conn = sqlite3.connect(self.db_path)
        try:
            cursor = conn.execute("SELECT Title, Author FROM works WHERE Id = 'abc123'")
            self.assertEqual(cursor.fetchone(), ("Test Painting", "Test Author"))
        finally:
            conn.close()

    def test_duplicate_id_ignored(self):
        p, _ = self._make_pipeline()
        item1 = ImageItem({"Id": "dup", "Title": "First", "URL": "u"})
        item2 = ImageItem({"Id": "dup", "Title": "Second", "URL": "u"})
        p.process_item(item1, MagicMock())
        p.process_item(item2, MagicMock())
        conn = sqlite3.connect(self.db_path)
        try:
            cursor = conn.execute("SELECT Title FROM works WHERE Id = 'dup'")
            self.assertEqual(cursor.fetchone(), ("First",))
            cursor = conn.execute("SELECT COUNT(*) FROM works")
            self.assertEqual(cursor.fetchone()[0], 1)
        finally:
            conn.close()

    def test_non_image_item_passthrough(self):
        p, _ = self._make_pipeline()
        item = ArtistItem({"Id": "artist1", "Name": "Picasso"})
        result = p.process_item(item, MagicMock())
        self.assertIs(result, item)
        conn = sqlite3.connect(self.db_path)
        try:
            cursor = conn.execute("SELECT COUNT(*) FROM works")
            self.assertEqual(cursor.fetchone()[0], 0)
        finally:
            conn.close()

    def test_list_fields_serialized(self):
        p, _ = self._make_pipeline()
        item = ImageItem({
            "Id": "lst",
            "Tags": ["tag1", "tag2"],
            "Media": ["oil"],
            "URL": "u",
        })
        p.process_item(item, MagicMock())
        conn = sqlite3.connect(self.db_path)
        try:
            cursor = conn.execute("SELECT Tags, Media FROM works WHERE Id = 'lst'")
            tags_raw, media_raw = cursor.fetchone()
            import json
            self.assertEqual(json.loads(tags_raw), ["tag1", "tag2"])
            self.assertEqual(json.loads(media_raw), ["oil"])
        finally:
            conn.close()

    def test_close_frees_connection(self):
        p, _ = self._make_pipeline()
        p.close_spider(MagicMock())
        # After close, the pipeline's conn should be None
        self.assertIsNone(p.conn)


class TestSQLiteDictionaryPipeline(unittest.TestCase):
    def setUp(self):
        self.db_path = _temp_db_path()
        self.pipeline = None

    def tearDown(self):
        if self.pipeline is not None:
            self.pipeline.close_spider(MagicMock())
        if os.path.exists(self.db_path):
            os.unlink(self.db_path)

    def _make_pipeline(self):
        self.pipeline = SQLiteDictionaryPipeline()
        spider = MagicMock()
        spider.settings = {"WIKIART_DB_PATH": self.db_path}
        self.pipeline.open_spider(spider)
        return self.pipeline, spider

    def test_open_creates_all_tables(self):
        p, _ = self._make_pipeline()
        conn = connect(self.db_path)
        try:
            for table in ("works", "artists", "styles", "movements", "schools"):
                self.assertTrue(table_exists(conn, table), table)
        finally:
            conn.close()

    def test_writes_artist_item(self):
        p, _ = self._make_pipeline()
        item = ArtistItem({"Id": "a1", "Name": "Picasso", "URL": "u"})
        result = p.process_item(item, MagicMock())
        self.assertIs(result, item)
        conn = sqlite3.connect(self.db_path)
        try:
            cursor = conn.execute("SELECT Name FROM artists WHERE Id = 'a1'")
            self.assertEqual(cursor.fetchone(), ("Picasso",))
        finally:
            conn.close()

    def test_writes_style_item(self):
        p, _ = self._make_pipeline()
        item = StyleItem({"Id": "s1", "Name": "Cubism", "Link": "l"})
        p.process_item(item, MagicMock())
        conn = sqlite3.connect(self.db_path)
        try:
            cursor = conn.execute("SELECT Name FROM styles WHERE Id = 's1'")
            self.assertEqual(cursor.fetchone(), ("Cubism",))
        finally:
            conn.close()

    def test_writes_movement_item(self):
        p, _ = self._make_pipeline()
        item = MovementItem({"Id": "m1", "Name": "Impressionism", "Link": "l"})
        p.process_item(item, MagicMock())
        conn = sqlite3.connect(self.db_path)
        try:
            cursor = conn.execute("SELECT Name FROM movements WHERE Id = 'm1'")
            self.assertEqual(cursor.fetchone(), ("Impressionism",))
        finally:
            conn.close()

    def test_writes_school_item(self):
        p, _ = self._make_pipeline()
        item = SchoolItem({"Id": "sc1", "Name": "Bauhaus", "Link": "l"})
        p.process_item(item, MagicMock())
        conn = sqlite3.connect(self.db_path)
        try:
            cursor = conn.execute("SELECT Name FROM schools WHERE Id = 'sc1'")
            self.assertEqual(cursor.fetchone(), ("Bauhaus",))
        finally:
            conn.close()

    def test_non_dict_item_passthrough(self):
        p, _ = self._make_pipeline()
        item = ImageItem({"Id": "x", "Title": "Test"})
        result = p.process_item(item, MagicMock())
        self.assertIs(result, item)
        conn = sqlite3.connect(self.db_path)
        try:
            cursor = conn.execute("SELECT COUNT(*) FROM works")
            self.assertEqual(cursor.fetchone()[0], 0)
        finally:
            conn.close()


class TestPipelineDBErrorResilience(unittest.TestCase):
    """F2: DB failures in pipeline.process_item must not crash the crawl."""

    def setUp(self):
        self.db_path = _temp_db_path()
        self.pipeline = None

    def tearDown(self):
        if self.pipeline is not None:
            self.pipeline.close_spider(MagicMock())
        if os.path.exists(self.db_path):
            os.unlink(self.db_path)

    def _make_pipeline_and_corrupt(self, pipeline_cls):
        pipeline = pipeline_cls()
        spider = MagicMock()
        spider.settings = {"WIKIART_DB_PATH": self.db_path}
        pipeline.open_spider(spider)
        # Close the connection so the next DB write fails with sqlite3.Error
        pipeline.conn.close()
        return pipeline, spider

    def test_works_pipeline_returns_item_on_db_error(self):
        p, spider = self._make_pipeline_and_corrupt(SQLiteWorksPipeline)
        item = ImageItem({"Id": "e1", "URL": "u"})
        with self.assertLogs("ScrapWikiArt.pipelines", level="WARNING") as cm:
            result = p.process_item(item, spider)
        self.assertIs(result, item)
        self.assertEqual(p._db_errors, 1)
        self.assertTrue(any("e1" in msg for msg in cm.output))

    def test_dict_pipeline_returns_item_on_db_error(self):
        p, spider = self._make_pipeline_and_corrupt(SQLiteDictionaryPipeline)
        item = ArtistItem({"Id": "e2", "Name": "Test"})
        with self.assertLogs("ScrapWikiArt.pipelines", level="WARNING") as cm:
            result = p.process_item(item, spider)
        self.assertIs(result, item)
        self.assertEqual(p._db_errors, 1)
        self.assertTrue(any("e2" in msg for msg in cm.output))

    def test_update_pipeline_returns_item_on_db_error(self):
        p, spider = self._make_pipeline_and_corrupt(SQLiteUpdatePipeline)
        item = ImageItem({
            "Id": "e3", "WikiDescription": "desc", "WikiLink": "https://w",
        })
        with self.assertLogs("ScrapWikiArt.pipelines", level="WARNING") as cm:
            result = p.process_item(item, spider)
        self.assertIs(result, item)
        self.assertEqual(p._db_errors, 1)
        self.assertTrue(any("e3" in msg for msg in cm.output))

    def test_db_errors_counter_increments(self):
        p, spider = self._make_pipeline_and_corrupt(SQLiteWorksPipeline)
        for i in range(3):
            item = ImageItem({"Id": f"err{i}", "URL": "u"})
            with self.assertLogs("ScrapWikiArt.pipelines", level="WARNING"):
                p.process_item(item, spider)
        self.assertEqual(p._db_errors, 3)


class TestSQLiteUpdatePipeline(unittest.TestCase):
    def setUp(self):
        self.db_path = _temp_db_path()
        self.pipeline = None

    def tearDown(self):
        if self.pipeline is not None:
            self.pipeline.close_spider(MagicMock())
        if os.path.exists(self.db_path):
            os.unlink(self.db_path)

    def _make_pipeline(self):
        self.pipeline = SQLiteUpdatePipeline()
        spider = MagicMock()
        spider.settings = {"WIKIART_DB_PATH": self.db_path}
        self.pipeline.open_spider(spider)
        return self.pipeline, spider

    def test_updates_works_row(self):
        p, _ = self._make_pipeline()
        conn = connect(self.db_path)
        try:
            insert_ignore(conn, "works", {
                "Id": "w1", "Title": "Old", "URL": "u", "scraped_at": "2024",
            })
        finally:
            conn.close()
        item = ImageItem({
            "Id": "w1",
            "WikiDescription": "New description",
            "WikiLink": "https://wiki.org/art",
        })
        result = p.process_item(item, MagicMock())
        self.assertIs(result, item)
        conn = sqlite3.connect(self.db_path)
        try:
            cursor = conn.execute(
                "SELECT WikiDescription, WikiLink FROM works WHERE Id = 'w1'"
            )
            row = cursor.fetchone()
            self.assertEqual(row[0], "New description")
            self.assertEqual(row[1], "https://wiki.org/art")
        finally:
            conn.close()

    def test_updates_artists_row_for_updated_artist_item(self):
        p, _ = self._make_pipeline()
        conn = connect(self.db_path)
        try:
            insert_ignore(conn, "artists", {"Id": "a1", "Name": "Picasso"})
        finally:
            conn.close()
        # ArtistItem is used by duck_duck_go_artist (no Updated variant)
        item = ArtistItem({
            "Id": "a1",
            "WikiDescription": "Famous painter",
            "WikiLink": "https://wiki.org/picasso",
        })
        p.process_item(item, MagicMock())
        conn = sqlite3.connect(self.db_path)
        try:
            cursor = conn.execute(
                "SELECT WikiDescription, WikiLink FROM artists WHERE Id = 'a1'"
            )
            row = cursor.fetchone()
            self.assertEqual(row[0], "Famous painter")
            self.assertEqual(row[1], "https://wiki.org/picasso")
        finally:
            conn.close()

    def test_updates_styles_row_for_updated_style_item(self):
        p, _ = self._make_pipeline()
        conn = connect(self.db_path)
        try:
            insert_ignore(conn, "styles", {"Id": "s1", "Name": "Cubism"})
        finally:
            conn.close()
        item = UpdatedStyleItem({
            "Id": "s1",
            "WikiDescription": "20th century movement",
            "WikiLink": "https://wiki.org/cubism",
        })
        p.process_item(item, MagicMock())
        conn = sqlite3.connect(self.db_path)
        try:
            cursor = conn.execute(
                "SELECT WikiDescription, WikiLink FROM styles WHERE Id = 's1'"
            )
            row = cursor.fetchone()
            self.assertEqual(row[0], "20th century movement")
            self.assertEqual(row[1], "https://wiki.org/cubism")
        finally:
            conn.close()

    def test_noop_on_unknown_id(self):
        p, _ = self._make_pipeline()
        item = ImageItem({
            "Id": "missing",
            "WikiDescription": "Nope",
            "WikiLink": "https://wiki.org/nope",
        })
        p.process_item(item, MagicMock())
        conn = sqlite3.connect(self.db_path)
        try:
            cursor = conn.execute("SELECT COUNT(*) FROM works")
            self.assertEqual(cursor.fetchone()[0], 0)
        finally:
            conn.close()

    def test_partial_update_wiki_description_only(self):
        """Only WikiDescription set (WikiLink None) — only WikiDescription written."""
        p, _ = self._make_pipeline()
        conn = connect(self.db_path)
        try:
            insert_ignore(conn, "works", {
                "Id": "p1", "Title": "T", "URL": "u", "scraped_at": "2024",
                "WikiDescription": "old", "WikiLink": "https://old",
            })
        finally:
            conn.close()
        item = ImageItem({"Id": "p1", "WikiDescription": "new"})
        p.process_item(item, MagicMock())
        conn = sqlite3.connect(self.db_path)
        try:
            row = conn.execute(
                "SELECT WikiDescription, WikiLink FROM works WHERE Id = 'p1'"
            ).fetchone()
            self.assertEqual(row[0], "new")
            self.assertEqual(row[1], "https://old")  # unchanged
        finally:
            conn.close()

    def test_partial_update_wiki_link_only(self):
        """Only WikiLink set (WikiDescription None) — only WikiLink written."""
        p, _ = self._make_pipeline()
        conn = connect(self.db_path)
        try:
            insert_ignore(conn, "works", {
                "Id": "p2", "Title": "T", "URL": "u", "scraped_at": "2024",
                "WikiDescription": "old desc", "WikiLink": "https://old",
            })
        finally:
            conn.close()
        item = ImageItem({"Id": "p2", "WikiLink": "https://new"})
        p.process_item(item, MagicMock())
        conn = sqlite3.connect(self.db_path)
        try:
            row = conn.execute(
                "SELECT WikiDescription, WikiLink FROM works WHERE Id = 'p2'"
            ).fetchone()
            self.assertEqual(row[0], "old desc")  # unchanged
            self.assertEqual(row[1], "https://new")
        finally:
            conn.close()


if __name__ == "__main__":
    unittest.main()
