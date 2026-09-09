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
    """
    if settings is None:
        return "data/works.db"
    val = settings.get("WIKIART_DB_PATH", "data/works.db")
    return val if val else "data/works.db"


def connect(db_path):
    """Open a SQLite connection, creating parent directories as needed."""
    os.makedirs(os.path.dirname(db_path) or ".", exist_ok=True)
    return sqlite3.connect(db_path)


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
    """Map a Scrapy item instance to its SQLite table name, or None."""
    # isinstance dispatch (design D2) — UpdatedStyleItem matches StyleItem, etc.
    for cls, table in _ITEM_TABLE_MAP.items():
        if isinstance(item, cls):
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
    """
    columns = []
    placeholders = []
    values = []
    for key, value in row.items():
        columns.append(key)
        placeholders.append("?")
        values.append(to_db_value(value) if key in _LIST_COLUMNS else value)
    cols_str = ", ".join(columns)
    phs_str = ", ".join(placeholders)
    conn.execute(
        f"INSERT OR IGNORE INTO {table} ({cols_str}) VALUES ({phs_str})",
        values,
    )


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
