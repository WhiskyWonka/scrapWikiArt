import os
import tempfile
import unittest
from unittest import mock

from fastapi.testclient import TestClient

from api.main import app

client = TestClient(app)


class TestHealthz(unittest.TestCase):
    def test_returns_ok(self):
        response = client.get("/healthz")
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json(), {"status": "ok"})

    def test_returns_503_when_db_missing(self):
        fd, path = tempfile.mkstemp(suffix=".db")
        os.close(fd)
        os.unlink(path)  # nonexistent database path
        with mock.patch.dict(os.environ, {"WIKIART_DB_PATH": path}):
            response = client.get("/healthz")
        self.assertEqual(response.status_code, 503)


class TestCors(unittest.TestCase):
    def test_preflight_allows_origin(self):
        response = client.options(
            "/healthz",
            headers={
                "Origin": "http://localhost:8000",
                "Access-Control-Request-Method": "GET",
            },
        )
        self.assertIn("access-control-allow-origin", response.headers)