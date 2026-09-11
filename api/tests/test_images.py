"""Endpoint tests for ``GET /images`` static image serving.

Written first (RED) against the ``/images`` mount that did not yet exist in
``api.main``; ``api/main.py`` was then implemented to satisfy them (GREEN).
"""

import importlib
import os
import shutil
import tempfile
import unittest
from unittest import mock

from fastapi.testclient import TestClient

import api.main

# NOTE: there is intentionally NO module-level TestClient for /images requests.
# starlette 1.6.0 StaticFiles.check_config() re-stats the directory on the
# first request per mount instance and raises RuntimeError when it is missing;
# CI has no data/img (gitignored), so a module-level client would surface an
# opaque RuntimeError test ERROR instead of a clean assertion failure. Every
# /images request goes through _app_with_store() or an explicit lifespan
# context, both of which bind the app to a real temp store.

# Minimal JPEG fixture: SOI + APP0/JFIF header chunk (20 bytes) + padding.
_JPEG_MAGIC = (
    b"\xff\xd8\xff\xe0\x00\x10JFIF\x00\x01\x01\x00\x00\x01\x00\x01\x00\x00"
    + b"\x00" * 32
)

_CACHE_CONTROL = "public, max-age=86400"


def _app_with_store(store_root):
    """Reload ``api.main`` under ``WIKIART_IMG_STORE=store_root`` and return a client.

    The env patch is scoped to the reload: the app captures the store path at
    import time (``_IMAGE_STORE``), so the mount and lifespan keep reading the
    temp store even after the patch exits.
    """
    with mock.patch.dict(os.environ, {"WIKIART_IMG_STORE": store_root}):
        importlib.reload(api.main)
    return TestClient(api.main.app)


def _write_fixture(store_root, rel_path):
    """Write ``_JPEG_MAGIC`` bytes at ``store_root/rel_path``, creating parents."""
    full_path = os.path.join(store_root, rel_path)
    os.makedirs(os.path.dirname(full_path), exist_ok=True)
    with open(full_path, "wb") as fh:
        fh.write(_JPEG_MAGIC)


class TestImagesEndpoint(unittest.TestCase):
    def setUp(self):
        self._store_root = tempfile.mkdtemp(prefix="wikiart-img-")
        self.addCleanup(shutil.rmtree, self._store_root)

    def test_serves_existing_image(self):
        _write_fixture(self._store_root, "full/abc123.jpg")
        client = _app_with_store(self._store_root)
        response = client.get("/images/full/abc123.jpg")
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.headers["content-type"], "image/jpeg")

    def test_missing_image_returns_404(self):
        client = _app_with_store(self._store_root)
        response = client.get("/images/full/missing.jpg")
        self.assertEqual(response.status_code, 404)

    def test_cache_control_header_on_served_file(self):
        _write_fixture(self._store_root, "full/abc123.jpg")
        client = _app_with_store(self._store_root)
        response = client.get("/images/full/abc123.jpg")
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.headers["cache-control"], _CACHE_CONTROL)

    def test_env_override_serves_temp_store(self):
        # The fixture exists ONLY in the override store (WIKIART_IMG_STORE),
        # never in the repo's data/img — a 200 proves the env var changed the
        # directory the mount serves (IMAGE-SERVING-003).
        _write_fixture(self._store_root, "full/override-only.jpg")
        client = _app_with_store(self._store_root)
        response = client.get("/images/full/override-only.jpg")
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.headers["content-type"], "image/jpeg")

    def test_missing_store_dir_fails_startup(self):
        fd, missing = tempfile.mkstemp(suffix=".imgstore")
        os.close(fd)
        os.unlink(missing)  # ensure the path does not exist
        with mock.patch.dict(os.environ, {"WIKIART_IMG_STORE": missing}):
            importlib.reload(api.main)
        with self.assertRaises(RuntimeError):
            with TestClient(api.main.app):
                pass  # lifespan startup raises before any request

    def test_lifespan_passes_with_existing_store(self):
        # Positive lifespan: an existing store lets startup yield, and a
        # serving request inside the context succeeds (IMAGE-SERVING-005).
        _write_fixture(self._store_root, "full/abc123.jpg")
        client = _app_with_store(self._store_root)
        with client:
            response = client.get("/images/full/abc123.jpg")
        self.assertEqual(response.status_code, 200)

    def test_not_modified_304_keeps_cache_control(self):
        # The file_response hook must cover the 304 path too: RFC 9110 15.4.5
        # says 304 must mirror the 200 caching headers.
        _write_fixture(self._store_root, "full/abc123.jpg")
        client = _app_with_store(self._store_root)
        first = client.get("/images/full/abc123.jpg")
        self.assertEqual(first.status_code, 200)
        response = client.get(
            "/images/full/abc123.jpg",
            headers={"If-None-Match": first.headers["etag"]},
        )
        self.assertEqual(response.status_code, 304)
        self.assertEqual(response.headers["cache-control"], _CACHE_CONTROL)


if __name__ == "__main__":
    unittest.main()