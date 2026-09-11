"""Endpoint tests for ``GET /api/random`` against a temporary database.

Each test uses a UNIQUE token (``self._testMethodName``) so the module-level
deck store's per-token state does not leak between tests.
"""

import os
import sqlite3
import tempfile
import unittest
from unittest import mock

from fastapi.testclient import TestClient

from api.main import app

client = TestClient(app)

_WORK_COLUMNS = (
    "Id",
    "URL",
    "Title",
    "Author",
    "Date",
    "Styles",
    "Genre",
    "Media",
    "Location",
    "Description",
    "WikiLink",
    "ImagePath",
)

_IMAGE_COUNT = 120
_NO_IMAGE_COUNT = 6


def _create_db(path, image_count=_IMAGE_COUNT, no_image_count=_NO_IMAGE_COUNT):
    """Create a works table with the API's 12 columns.

    ``image_count`` rows get an ``ImagePath`` (the dealable pool);
    ``no_image_count`` rows have ``ImagePath IS NULL`` and must never
    be served.
    """
    conn = sqlite3.connect(path)
    try:
        conn.execute("CREATE TABLE works (" + ", ".join(_WORK_COLUMNS) + ")")
        for i in range(image_count):
            conn.execute(
                "INSERT INTO works VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
                (
                    f"id-{i:03d}",
                    f"https://example.test/work/{i}",
                    f"Title {i}",
                    f"Author {i}",
                    f"19{i % 90 + 10}",
                    "Style",
                    "Genre",
                    "Media",
                    "Location",
                    f"Description {i}",
                    f"https://example.test/wiki/{i}",
                    f"full/{i:03d}.jpg",
                ),
            )
        for i in range(no_image_count):
            conn.execute(
                "INSERT INTO works VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
                (
                    f"noimg-{i:02d}",
                    f"https://example.test/work/noimg-{i}",
                    f"No Image {i}",
                    "Author",
                    "1900",
                    "Style",
                    "Genre",
                    "Media",
                    "Location",
                    "Description",
                    "WikiLink",
                    None,  # ImagePath — must never be served
                ),
            )
        conn.commit()
    finally:
        conn.close()


class TestRandomEndpoint(unittest.TestCase):
    def setUp(self):
        fd, self._db_path = tempfile.mkstemp(suffix=".db")
        os.close(fd)
        _create_db(self._db_path)

    def tearDown(self):
        if os.path.exists(self._db_path):
            os.unlink(self._db_path)

    def _get(self, n, token):
        query = f"?token={token}" if n is None else f"?n={n}&token={token}"
        with mock.patch.dict(os.environ, {"WIKIART_DB_PATH": self._db_path}):
            return client.get(f"/api/random{query}")

    def test_default_n_is_12(self):
        response = self._get(None, self._testMethodName)
        self.assertEqual(response.status_code, 200)
        self.assertEqual(len(response.json()), 12)

    def test_same_token_deck_advances(self):
        token = self._testMethodName
        first = self._get(12, token).json()
        second = self._get(12, token).json()
        self.assertEqual(len(first), 12)
        self.assertEqual(len(second), 12)
        first_ids = {work["Id"] for work in first}
        second_ids = {work["Id"] for work in second}
        self.assertTrue(first_ids.isdisjoint(second_ids))

    def test_clamps_n_to_min_1(self):
        response = self._get(0, self._testMethodName)
        self.assertEqual(response.status_code, 200)
        self.assertEqual(len(response.json()), 1)

    def test_clamps_n_to_max_50(self):
        response = self._get(999, self._testMethodName)
        self.assertEqual(response.status_code, 200)
        self.assertEqual(len(response.json()), 50)

    def test_non_integer_n_returns_422(self):
        with mock.patch.dict(os.environ, {"WIKIART_DB_PATH": self._db_path}):
            response = client.get(f"/api/random?n=abc&token={self._testMethodName}")
        self.assertEqual(response.status_code, 422)

    def test_never_returns_rows_without_image(self):
        conn = sqlite3.connect(self._db_path)
        try:
            null_count = conn.execute(
                "SELECT COUNT(*) FROM works WHERE ImagePath IS NULL"
            ).fetchone()[0]
        finally:
            conn.close()
        self.assertEqual(null_count, _NO_IMAGE_COUNT)  # fixture sanity check

        token = self._testMethodName
        seen = set()
        for _ in range(10):  # drains the full 120-id deck
            works = self._get(12, token).json()
            self.assertEqual(len(works), 12)
            for work in works:
                self.assertIsNotNone(work["ImagePath"])
                seen.add(work["Id"])
        self.assertNotIn("noimg-00", seen)

    def test_image_url_matches_image_path(self):
        for work in self._get(12, self._testMethodName).json():
            self.assertEqual(work["image_url"], work["ImagePath"])

    def test_missing_db_returns_503(self):
        fd, missing = tempfile.mkstemp(suffix=".db")
        os.close(fd)
        os.unlink(missing)  # nonexistent database path
        with mock.patch.dict(os.environ, {"WIKIART_DB_PATH": missing}):
            response = client.get(f"/api/random?n=3&token={self._testMethodName}")
        self.assertEqual(response.status_code, 503)

    def test_empty_catalog_returns_empty_list(self):
        fd, empty_path = tempfile.mkstemp(suffix=".db")
        os.close(fd)
        _create_db(empty_path, image_count=0, no_image_count=0)
        with mock.patch.dict(os.environ, {"WIKIART_DB_PATH": empty_path}):
            response = client.get(f"/api/random?n=12&token={self._testMethodName}")
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json(), [])
        os.unlink(empty_path)

    def test_cross_token_independence(self):
        first = self._get(12, self._testMethodName + "-a").json()
        second = self._get(12, self._testMethodName + "-b").json()
        first_ids = {work["Id"] for work in first}
        second_ids = {work["Id"] for work in second}
        # 120-image catalog makes two independent 12-id batches differ almost surely
        self.assertNotEqual(first_ids, second_ids)


if __name__ == "__main__":
    unittest.main()