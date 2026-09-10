import json
import os
import sqlite3
import tempfile
import unittest

from ScrapWikiArt.db import (
    connect,
    create_tables,
    default_db_path,
    insert_ignore,
    load_seen_urls,
    table_exists,
    table_for_class,
    table_for_item,
    to_db_value,
    unenriched_sql,
    update_fields,
)
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


def _temp_conn():
    """Open a temp-file SQLite connection via db.connect (caller must close)."""
    fd, path = tempfile.mkstemp(suffix=".db")
    os.close(fd)
    os.unlink(path)  # connect() creates the file
    conn = connect(path)
    return conn, path


class TestDefaultDbPath(unittest.TestCase):
    def test_returns_setting_value(self):
        class FakeSettings:
            def get(self, key, default=None):
                if key == "WIKIART_DB_PATH":
                    return "/custom/path.db"
                return default
        self.assertEqual(default_db_path(FakeSettings()), "/custom/path.db")

    def test_falls_back_when_none(self):
        self.assertEqual(default_db_path(None), "data/works.db")

    def test_falls_back_when_missing_key(self):
        class FakeSettings:
            def get(self, key, default=None):
                return default
        self.assertEqual(default_db_path(FakeSettings()), "data/works.db")


class TestTableExists(unittest.TestCase):
    def test_returns_false_for_missing_table(self):
        conn, path = _temp_conn()
        try:
            self.assertFalse(table_exists(conn, "works"))
        finally:
            conn.close()
            os.unlink(path)

    def test_returns_true_after_create(self):
        conn, path = _temp_conn()
        try:
            create_tables(conn)
            self.assertTrue(table_exists(conn, "works"))
        finally:
            conn.close()
            os.unlink(path)


class TestCreateTables(unittest.TestCase):
    def test_creates_all_five_tables(self):
        conn, path = _temp_conn()
        try:
            create_tables(conn)
            for table in ("works", "artists", "styles", "movements", "schools"):
                self.assertTrue(table_exists(conn, table), table)
        finally:
            conn.close()
            os.unlink(path)

    def test_idempotent(self):
        conn, path = _temp_conn()
        try:
            create_tables(conn)
            create_tables(conn)  # second call must not raise
            self.assertTrue(table_exists(conn, "works"))
        finally:
            conn.close()
            os.unlink(path)

    def test_works_has_expected_columns(self):
        conn, path = _temp_conn()
        try:
            create_tables(conn)
            cursor = conn.execute("PRAGMA table_info(works)")
            columns = {row[1] for row in cursor.fetchall()}
            expected = {
                "Id", "URL", "Title", "OriginalTitle",
                "Author", "AuthorLink", "Date", "Styles", "StylesLinks",
                "Series", "SeriesLink", "Genre", "GenreLink", "Media",
                "Location", "Dimensions", "Description", "WikiDescription",
                "WikiLink", "Tags", "ImagePath",
                "scraped_at",
                "ValidatedRaw", "Validated",
            }
            self.assertEqual(columns, expected)
        finally:
            conn.close()
            os.unlink(path)


class TestTableForItem(unittest.TestCase):
    def test_image_item_maps_to_works(self):
        item = ImageItem()
        self.assertEqual(table_for_item(item), "works")

    def test_artist_item_maps_to_artists(self):
        item = ArtistItem()
        self.assertEqual(table_for_item(item), "artists")

    def test_style_item_maps_to_styles(self):
        item = StyleItem()
        self.assertEqual(table_for_item(item), "styles")

    def test_movement_item_maps_to_movements(self):
        item = MovementItem()
        self.assertEqual(table_for_item(item), "movements")

    def test_school_item_maps_to_schools(self):
        item = SchoolItem()
        self.assertEqual(table_for_item(item), "schools")

    def test_updated_style_item_maps_to_styles(self):
        item = UpdatedStyleItem()
        self.assertEqual(table_for_item(item), "styles")

    def test_updated_movement_item_maps_to_movements(self):
        item = UpdatedMovementItem()
        self.assertEqual(table_for_item(item), "movements")

    def test_updated_school_item_maps_to_schools(self):
        item = UpdatedSchoolItem()
        self.assertEqual(table_for_item(item), "schools")

    def test_unknown_item_returns_none(self):
        item = object()
        self.assertIsNone(table_for_item(item))


class TestTableForClass(unittest.TestCase):
    def test_class_dispatch(self):
        self.assertEqual(table_for_class(ImageItem), "works")
        self.assertEqual(table_for_class(ArtistItem), "artists")
        self.assertEqual(table_for_class(StyleItem), "styles")
        self.assertEqual(table_for_class(MovementItem), "movements")
        self.assertEqual(table_for_class(SchoolItem), "schools")

    def test_updated_classes_map_to_base_tables(self):
        # DDG dict spiders use Updated* classes; they must resolve to the
        # same tables their crawlers populated.
        self.assertEqual(table_for_class(UpdatedStyleItem), "styles")
        self.assertEqual(table_for_class(UpdatedMovementItem), "movements")
        self.assertEqual(table_for_class(UpdatedSchoolItem), "schools")

    def test_unknown_class_returns_none(self):
        self.assertIsNone(table_for_class(dict))


class TestInsertIgnore(unittest.TestCase):
    def test_insert_round_trip(self):
        conn, path = _temp_conn()
        try:
            create_tables(conn)
            row = {
                "Id": "abc123",
                "URL": "https://example.com/art",
                "Title": "Test Painting",
                "Author": "Test Author",
                "scraped_at": "2024-01-01",
            }
            insert_ignore(conn, "works", row)
            cursor = conn.execute("SELECT Title, Author FROM works WHERE Id = 'abc123'")
            result = cursor.fetchone()
            self.assertEqual(result, ("Test Painting", "Test Author"))
        finally:
            conn.close()
            os.unlink(path)

    def test_duplicate_id_ignored(self):
        conn, path = _temp_conn()
        try:
            create_tables(conn)
            row = {"Id": "dup1", "Title": "First", "scraped_at": "2024-01-01"}
            insert_ignore(conn, "works", row)
            row["Title"] = "Second"
            insert_ignore(conn, "works", row)
            cursor = conn.execute("SELECT Title FROM works WHERE Id = 'dup1'")
            self.assertEqual(cursor.fetchone(), ("First",))
            cursor = conn.execute("SELECT COUNT(*) FROM works")
            self.assertEqual(cursor.fetchone()[0], 1)
        finally:
            conn.close()
            os.unlink(path)

    def test_list_field_serialized_as_json(self):
        conn, path = _temp_conn()
        try:
            create_tables(conn)
            row = {
                "Id": "lst1",
                "Tags": ["tag1", "tag2"],
                "Media": ["oil", "canvas"],
                "scraped_at": "2024-01-01",
            }
            insert_ignore(conn, "works", row)
            cursor = conn.execute("SELECT Tags, Media FROM works WHERE Id = 'lst1'")
            tags_raw, media_raw = cursor.fetchone()
            self.assertEqual(json.loads(tags_raw), ["tag1", "tag2"])
            self.assertEqual(json.loads(media_raw), ["oil", "canvas"])
        finally:
            conn.close()
            os.unlink(path)


class TestUpdateFields(unittest.TestCase):
    def test_updates_wiki_fields(self):
        conn, path = _temp_conn()
        try:
            create_tables(conn)
            insert_ignore(conn, "works", {
                "Id": "upd1", "Title": "Original", "scraped_at": "2024-01-01"
            })
            update_fields(conn, "works", "upd1", {
                "WikiDescription": "A description",
                "WikiLink": "https://wiki.org",
            })
            cursor = conn.execute(
                "SELECT WikiDescription, WikiLink, Title FROM works WHERE Id = 'upd1'"
            )
            row = cursor.fetchone()
            self.assertEqual(row[0], "A description")
            self.assertEqual(row[1], "https://wiki.org")
            self.assertEqual(row[2], "Original")  # untouched
        finally:
            conn.close()
            os.unlink(path)

    def test_noop_on_unknown_id(self):
        conn, path = _temp_conn()
        try:
            create_tables(conn)
            # Should not raise
            update_fields(conn, "works", "nonexistent", {"WikiDescription": "x"})
            cursor = conn.execute("SELECT COUNT(*) FROM works")
            self.assertEqual(cursor.fetchone()[0], 0)
        finally:
            conn.close()
            os.unlink(path)

    def test_updates_artists_table(self):
        conn, path = _temp_conn()
        try:
            create_tables(conn)
            insert_ignore(conn, "artists", {
                "Id": "art1", "Name": "Picasso",
            })
            update_fields(conn, "artists", "art1", {
                "WikiDescription": "Famous painter",
                "WikiLink": "https://wiki.org/picasso",
            })
            cursor = conn.execute(
                "SELECT WikiDescription, WikiLink FROM artists WHERE Id = 'art1'"
            )
            row = cursor.fetchone()
            self.assertEqual(row[0], "Famous painter")
            self.assertEqual(row[1], "https://wiki.org/picasso")
        finally:
            conn.close()
            os.unlink(path)


class TestLoadSeenUrls(unittest.TestCase):
    def test_empty_table_returns_empty_set(self):
        conn, path = _temp_conn()
        try:
            create_tables(conn)
            self.assertEqual(load_seen_urls(conn), set())
        finally:
            conn.close()
            os.unlink(path)

    def test_returns_all_urls(self):
        conn, path = _temp_conn()
        try:
            create_tables(conn)
            insert_ignore(conn, "works", {"Id": "a", "URL": "https://a.com", "scraped_at": "2024"})
            insert_ignore(conn, "works", {"Id": "b", "URL": "https://b.com", "scraped_at": "2024"})
            urls = load_seen_urls(conn)
            self.assertEqual(urls, {"https://a.com", "https://b.com"})
        finally:
            conn.close()
            os.unlink(path)


class TestUnenrichedSql(unittest.TestCase):
    def test_single_column(self):
        sql = unenriched_sql("works", ["Description"])
        self.assertIn("Description", sql)
        self.assertIn("works", sql)
        self.assertIn("IS NULL", sql)
        self.assertIn("TRIM", sql)

    def test_two_columns(self):
        sql = unenriched_sql("works", ["Description", "WikiDescription"])
        self.assertIn("Description", sql)
        self.assertIn("WikiDescription", sql)
        self.assertIn("AND", sql)

    def test_returns_valid_select(self):
        sql = unenriched_sql("artists", ["Description", "WikiDescription"])
        self.assertTrue(sql.startswith("SELECT * FROM artists WHERE"))


class TestToDbValue(unittest.TestCase):
    def test_list_serializes_to_json(self):
        result = to_db_value(["a", "b"])
        self.assertEqual(json.loads(result), ["a", "b"])

    def test_tuple_serializes_to_json(self):
        result = to_db_value(("x", "y"))
        self.assertEqual(json.loads(result), ["x", "y"])

    def test_string_passthrough(self):
        self.assertEqual(to_db_value("hello"), "hello")

    def test_none_passthrough(self):
        self.assertIsNone(to_db_value(None))

    def test_int_passthrough(self):
        self.assertEqual(to_db_value(42), 42)


class TestConnect(unittest.TestCase):
    def test_creates_parent_directories(self):
        tmpdir = tempfile.mkdtemp()
        db_path = os.path.join(tmpdir, "subdir", "test.db")
        try:
            conn = connect(db_path)
            self.assertTrue(os.path.exists(db_path))
            conn.close()
        finally:
            import shutil
            shutil.rmtree(tmpdir, ignore_errors=True)

    def test_sets_wal_journal_mode(self):
        fd, path = tempfile.mkstemp(suffix=".db")
        os.close(fd)
        os.unlink(path)
        try:
            conn = connect(path)
            try:
                mode = conn.execute("PRAGMA journal_mode").fetchone()[0]
                self.assertEqual(mode, "wal")
            finally:
                conn.close()
        finally:
            if os.path.exists(path):
                os.unlink(path)

    def test_sets_busy_timeout(self):
        fd, path = tempfile.mkstemp(suffix=".db")
        os.close(fd)
        os.unlink(path)
        try:
            conn = connect(path)
            try:
                timeout = conn.execute("PRAGMA busy_timeout").fetchone()[0]
                self.assertEqual(timeout, 30000)
            finally:
                conn.close()
        finally:
            if os.path.exists(path):
                os.unlink(path)


class TestColumnCache(unittest.TestCase):
    def test_column_exists_cached_on_connection(self):
        """_column_exists results are cached; a second call does not re-query PRAGMA."""
        from ScrapWikiArt.db import _column_exists, _column_cache
        conn, path = _temp_conn()
        try:
            create_tables(conn)
            # First call populates cache
            result1 = _column_exists(conn, "works", "Title")
            self.assertTrue(result1)
            # Cache should be present for this connection
            self.assertIn(id(conn), _column_cache)
            self.assertIn("works", _column_cache[id(conn)])
            # Second call uses cache (same result)
            result2 = _column_exists(conn, "works", "Title")
            self.assertTrue(result2)
            # Non-existent column still returns False
            result3 = _column_exists(conn, "works", "NoSuchColumn")
            self.assertFalse(result3)
        finally:
            from ScrapWikiArt.db import _clear_column_cache
            _clear_column_cache(conn)
            conn.close()
            os.unlink(path)


class TestInsertIgnoreSilentDrop(unittest.TestCase):
    def test_unknown_column_not_created(self):
        """insert_ignore silently drops keys not in the table schema."""
        conn, path = _temp_conn()
        try:
            create_tables(conn)
            insert_ignore(conn, "works", {
                "Id": "x", "NoSuchColumn": "y", "scraped_at": "2024",
            })
            cursor = conn.execute("SELECT COUNT(*) FROM works WHERE Id = 'x'")
            self.assertEqual(cursor.fetchone()[0], 1)
            # NoSuchColumn must not exist as a real column
            columns = {
                row[1] for row in conn.execute("PRAGMA table_info(works)").fetchall()
            }
            self.assertNotIn("NoSuchColumn", columns)
        finally:
            conn.close()
            os.unlink(path)
