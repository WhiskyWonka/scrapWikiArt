import os
import sqlite3
import tempfile
import unittest
from unittest import mock

from api import db


class TestDefaultDbPath(unittest.TestCase):
    def test_respects_env_var(self):
        with mock.patch.dict(os.environ, {"WIKIART_DB_PATH": "/custom/path.db"}):
            self.assertEqual(db.default_db_path(), "/custom/path.db")

    def test_fallback_points_to_repo_works_db(self):
        with mock.patch.dict(os.environ, {}, clear=True):
            fallback = db.default_db_path()
        expected = os.path.join(db._PROJECT_ROOT, "data", "works.db")
        self.assertEqual(fallback, expected)
        # data/ is gitignored, so the DB is NOT guaranteed to exist in a
        # fresh CI checkout; the path contract is what we assert here.
        self.assertNotEqual(fallback, "/custom/path.db")

    def test_clears_env_var_after_patch(self):
        # Sanity: the environment is restored once the patch exits.
        self.assertNotEqual(os.environ.get("WIKIART_DB_PATH"), "/custom/path.db")


class TestDefaultImgStore(unittest.TestCase):
    def test_respects_env_var(self):
        with mock.patch.dict(os.environ, {"WIKIART_IMG_STORE": "/custom/img"}):
            self.assertEqual(db.default_img_store(), "/custom/img")

    def test_fallback_points_to_repo_img_dir(self):
        with mock.patch.dict(os.environ, {}, clear=True):
            fallback = db.default_img_store()
        expected = os.path.join(db._PROJECT_ROOT, "data", "img")
        self.assertEqual(fallback, expected)


class TestConnectRo(unittest.TestCase):
    def test_select_1_on_real_db(self):
        fd, path = tempfile.mkstemp(suffix=".db")
        os.close(fd)
        try:
            conn = sqlite3.connect(path)
            conn.execute("CREATE TABLE works (Id TEXT PRIMARY KEY)")
            conn.execute("INSERT INTO works VALUES ('a')")
            conn.commit()
            conn.close()
            ro = db.connect_ro(path)
            try:
                cursor = ro.execute("SELECT Id FROM works")
                self.assertEqual(cursor.fetchone()[0], "a")
            finally:
                ro.close()
        finally:
            if os.path.exists(path):
                os.unlink(path)

    def test_readonly_blocks_insert(self):
        fd, path = tempfile.mkstemp(suffix=".db")
        os.close(fd)
        try:
            conn = sqlite3.connect(path)
            conn.execute("CREATE TABLE works (Id TEXT, Title TEXT)")
            conn.execute("INSERT INTO works VALUES ('a', 'Test')")
            conn.commit()
            conn.close()

            ro = db.connect_ro(path)
            try:
                with self.assertRaises(sqlite3.OperationalError):
                    ro.execute("INSERT INTO works VALUES ('b', 'No')")
            finally:
                ro.close()
        finally:
            if os.path.exists(path):
                os.unlink(path)

    def test_missing_file_raises(self):
        fd, path = tempfile.mkstemp(suffix=".db")
        os.close(fd)
        os.unlink(path)  # ensure the file does not exist
        with self.assertRaises(sqlite3.OperationalError):
            db.connect_ro(path)