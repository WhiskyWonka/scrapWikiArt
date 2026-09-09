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
)
from ScrapWikiArt.pipelines import (
    SQLiteDictionaryPipeline,
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


if __name__ == "__main__":
    unittest.main()
