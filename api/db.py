"""Read-only SQLite helpers for the WikiArt Data API.

The scraper (systemd service) owns all writes; this module provides
connections that *cannot* write, making the read-only contract structural.
"""

import os
import sqlite3

_PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def default_db_path() -> str:
    """Return the path to the works SQLite database.

    Controlled by the ``WIKIART_DB_PATH`` environment variable; falls back
    to ``<repo_root>/data/works.db``.
    """
    return os.environ.get("WIKIART_DB_PATH", os.path.join(_PROJECT_ROOT, "data", "works.db"))


def default_img_store() -> str:
    """Return the path to the image store directory.

    Controlled by the ``WIKIART_IMG_STORE`` environment variable; falls back
    to ``<repo_root>/data/img``.
    """
    return os.environ.get("WIKIART_IMG_STORE", os.path.join(_PROJECT_ROOT, "data", "img"))


def connect_ro(db_path=None):
    """Open a **read-only** SQLite connection.

    Uses the ``mode=ro`` URI parameter which makes the read-only guarantee
    *structural* — the API can never write to the database.  Missing DB files
    raise ``sqlite3.OperationalError`` which callers surface as unavailability.

    A ``busy_timeout`` of 30 s is set immediately so concurrent readers do not
    fail with ``SQLITE_BUSY``.
    """
    path = db_path or default_db_path()
    conn = sqlite3.connect(f"file:{path}?mode=ro", uri=True)
    conn.execute("PRAGMA busy_timeout=30000")
    return conn


# Columns served by the API, in fixed order.  Values are returned raw — the
# API performs no transformation on stored data.
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


def image_ids(conn):
    """Return the ``Id`` of every work that has an image.

    Only works with ``ImagePath IS NOT NULL`` are ever served by the API.
    """
    cursor = conn.execute("SELECT Id FROM works WHERE ImagePath IS NOT NULL")
    return [row[0] for row in cursor.fetchall()]


def work_rows_by_ids(conn, ids):
    """Fetch full work rows for ``ids``, keyed by ``Id``.

    Returns the raw stored values for every column served by the API.  An
    empty ``ids`` list returns ``{}`` without querying — a guard against the
    invalid SQL fragment ``IN ()``.  Ids that no longer exist in the table
    are silently skipped.
    """
    if not ids:
        return {}
    columns = ", ".join(_WORK_COLUMNS)
    placeholders = ", ".join("?" * len(ids))
    cursor = conn.execute(
        f"SELECT {columns} FROM works WHERE Id IN ({placeholders})",
        list(ids),
    )
    return {row[0]: dict(zip(_WORK_COLUMNS, row)) for row in cursor.fetchall()}
