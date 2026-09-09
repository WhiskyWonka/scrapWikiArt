"""Shared SQLite helpers for crawl pipelines, DDG spiders, and validation.

stdlib sqlite3 only — no external dependencies. Module-level functions are
connection-free; pipelines/spiders own the connection lifecycle.
"""

import json
import os
import sqlite3

from ScrapWikiArt.items import (
    ArtistItem,
    ImageItem,
    MovementItem,
    SchoolItem,
    StyleItem,
)
from ScrapWikiArt.settings import WIKIART_DB_PATH

# ---------------------------------------------------------------------------
# Schema DDL — all tables created upfront (design decision D1)
# ---------------------------------------------------------------------------

_SCHEMA = """
CREATE TABLE IF NOT EXISTS works (
  Id TEXT PRIMARY KEY, URL TEXT, Title TEXT, OriginalTitle TEXT,
  Author TEXT, AuthorLink TEXT, Date TEXT, Styles TEXT, StylesLinks TEXT,
  Series TEXT, SeriesLink TEXT, Genre TEXT, GenreLink TEXT, Media TEXT,
  Location TEXT, Dimensions TEXT, Description TEXT, WikiDescription TEXT,
  WikiLink TEXT, Tags TEXT,
  scraped_at TEXT NOT NULL,
  ValidatedRaw TEXT, Validated TEXT
);

CREATE TABLE IF NOT EXISTS artists (
  Id TEXT PRIMARY KEY, URL TEXT, Name TEXT,
  OriginalName TEXT, BirthDate TEXT, BirthPlace TEXT, DeathDate TEXT,
  DeathPlace TEXT, ActiveYears TEXT, Nationality TEXT, ArtMovements TEXT,
  PaintingSchool TEXT, Genres TEXT, Fields TEXT, InfluencedOn TEXT,
  InfluencedBy TEXT, Teachers TEXT, Pupils TEXT, ArtInstitutions TEXT,
  FriendsAndCoworkers TEXT,
  Description TEXT, WikiDescription TEXT, WikiLink TEXT
);

CREATE TABLE IF NOT EXISTS styles (
  Id TEXT PRIMARY KEY, Name TEXT, Link TEXT,
  Description TEXT, WikiDescription TEXT, WikiLink TEXT
);

CREATE TABLE IF NOT EXISTS movements (
  Id TEXT PRIMARY KEY, Name TEXT, Link TEXT,
  Description TEXT, WikiDescription TEXT, WikiLink TEXT
);

CREATE TABLE IF NOT EXISTS schools (
  Id TEXT PRIMARY KEY, Name TEXT, Link TEXT,
  Description TEXT, WikiDescription TEXT, WikiLink TEXT
);
"""

# Item-class → table name mapping (design decision D2 / D5)
# INVARIANT: must NOT contain Updated* subclasses — first-match issubclass
# dispatch relies on base classes appearing first.
_ITEM_TABLE_MAP = {
    ImageItem: "works",
    ArtistItem: "artists",
    StyleItem: "styles",
    MovementItem: "movements",
    SchoolItem: "schools",
}

# List-type columns that need JSON serialization on insert
_LIST_COLUMNS = frozenset({
    "Tags", "Media", "Styles", "StylesLinks", "ArtMovements",
    "PaintingSchool", "Genres", "Fields", "InfluencedOn", "InfluencedBy",
    "Teachers", "Pupils", "ArtInstitutions", "FriendsAndCoworkers",
})


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def default_db_path(settings):
    """Resolve WIKIART_DB_PATH from Scrapy settings, falling back to default.

    None-safe: handles settings=None and settings where the key is absent.
    The default matches settings.py:74 (single source of truth).
    """
    if settings is None:
        return WIKIART_DB_PATH
    val = settings.get("WIKIART_DB_PATH", WIKIART_DB_PATH)
    return val if val else WIKIART_DB_PATH


def connect(db_path):
    """Open a SQLite connection, creating parent directories as needed.

    Uses autocommit mode (isolation_level=None): every INSERT/UPDATE is
    committed immediately, one transaction per row (design D4, crash-safe).

    Sets PRAGMA journal_mode=WAL and busy_timeout=30000 for safe concurrent
    access from multiple processes (e.g. crawl + validation script).
    """
    os.makedirs(os.path.dirname(db_path) or ".", exist_ok=True)
    conn = sqlite3.connect(db_path, isolation_level=None)
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("PRAGMA busy_timeout=30000")
    return conn


def create_tables(conn):
    """Create all five tables (idempotent — IF NOT EXISTS)."""
    conn.executescript(_SCHEMA)


def table_exists(conn, name):
    """Check whether a table exists in the database."""
    cursor = conn.execute(
        "SELECT name FROM sqlite_master WHERE type='table' AND name=?",
        (name,),
    )
    return cursor.fetchone() is not None


def table_for_item(item):
    """Map a Scrapy item instance to its SQLite table name, or None.

    isinstance dispatch (design D2) — UpdatedStyleItem matches StyleItem, etc.
    """
    return table_for_class(type(item))


def table_for_class(item_class):
    """Map a Scrapy item *class* to its SQLite table name, or None.

    issubclass dispatch: UpdatedStyleItem derives from StyleItem -> styles.
    Used by DDG spiders which know their item class, not an instance.
    """
    for cls, table in _ITEM_TABLE_MAP.items():
        if issubclass(item_class, cls):
            return table
    return None


def to_db_value(v):
    """Serialize a value for SQLite storage.

    Lists/tuples become JSON text; scalars pass through unchanged.
    None passes through (stored as NULL by sqlite3).
    """
    if isinstance(v, (list, tuple)):
        return json.dumps(v)
    return v


def insert_ignore(conn, table, row):
    """INSERT OR IGNORE a single row dict into the given table.

    List-type columns are automatically serialized to JSON via to_db_value.
    Keys not present in the table schema (e.g. pipeline-only item fields
    like ``image_urls``/``images``) are silently dropped.
    """
    columns = [key for key in row if _column_exists(conn, table, key)]
    if not columns:
        return
    placeholders = ", ".join("?" for _ in columns)
    cols_str = ", ".join(columns)
    values = [
        to_db_value(row[key]) if key in _LIST_COLUMNS else row[key]
        for key in columns
    ]
    conn.execute(
        f"INSERT OR IGNORE INTO {table} ({cols_str}) VALUES ({placeholders})",
        values,
    )


# Cache for _column_exists results: {id(conn): {table: {columns}}}
_column_cache: dict[int, dict[str, set[str]]] = {}


def _column_exists(conn, table, column):
    """Check whether a column exists in a table.

    Results are cached per connection to avoid repeated PRAGMA table_info
    queries per insert (F3 perf fix).
    """
    conn_id = id(conn)
    cache = _column_cache.get(conn_id)
    if cache is None:
        cache = {}
        _column_cache[conn_id] = cache
    if table not in cache:
        cursor = conn.execute(f"PRAGMA table_info({table})")
        cache[table] = {row[1] for row in cursor.fetchall()}
    return column in cache[table]


def _clear_column_cache(conn):
    """Remove cached column data for a closed connection (cleanup helper)."""
    _column_cache.pop(id(conn), None)


def update_fields(conn, table, item_id, fields):
    """UPDATE specific fields for a row identified by Id.

    Does nothing if the row does not exist (no error raised).
    """
    if not fields:
        return
    set_parts = []
    values = []
    for key, value in fields.items():
        set_parts.append(f"{key} = ?")
        values.append(value)
    values.append(item_id)
    set_str = ", ".join(set_parts)
    conn.execute(
        f"UPDATE {table} SET {set_str} WHERE Id = ?",
        values,
    )


def load_seen_urls(conn):
    """Return the set of all URL values from the works table."""
    cursor = conn.execute("SELECT URL FROM works")
    return {row[0] for row in cursor.fetchall()}


def unenriched_sql(table, columns):
    """Build a SELECT query for rows where ALL listed columns are missing.

    Matches NULL or whitespace-only values (mirrors filter_missing_descriptions).
    """
    conditions = []
    for col in columns:
        conditions.append(f"({col} IS NULL OR TRIM(COALESCE({col}, '')) = '')")
    where = " AND ".join(conditions)
    return f"SELECT * FROM {table} WHERE {where}"
