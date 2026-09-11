"""WikiArt Data API.

The scraper (systemd service) owns writes; this API only reads, so a
read-only SQLite connection is the contract.  Every endpoint obtains its
connection through :func:`api.db.connect_ro` which enforces ``mode=ro``
at the driver level.

``/api/random`` serves random works from per-token in-memory decks of work
ids (see :mod:`api.decks`): each request *deals* ids off the deck instead of
re-selecting from the database, so a deck advances until it runs out and is
rebuilt (re-fetch + reshuffle).
"""

import contextlib
import random
import sqlite3

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware

from api import db
from api.decks import DeckStore

app = FastAPI(title="WikiArt Data API", version="0.1.0")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)


def _deck_builder():
    """Return the ids of all works with an image, freshly shuffled.

    Opens its own read-only connection so ``WIKIART_DB_PATH`` is resolved at
    call time (tests patch the env, not the store).  ``sqlite3.Error`` is
    deliberately re-raised so the endpoint can map it to a 503.
    """
    with contextlib.closing(db.connect_ro()) as conn:
        ids = db.image_ids(conn)
    random.Random().shuffle(ids)  # fresh entropy per build
    return ids


deck_store = DeckStore(_deck_builder)


@app.get("/healthz")
def healthz():
    """Liveness probe — verifies the database is reachable and readable."""
    path = db.default_db_path()
    try:
        with contextlib.closing(db.connect_ro(path)) as conn:
            conn.execute("SELECT 1")
    except sqlite3.Error as exc:
        raise HTTPException(
            status_code=503,
            detail=f"Database not reachable at {path}: {exc}",
        )
    return {"status": "ok"}


@app.get("/api/random")
def random_works(n: int = 12, token: str = ""):
    """Deal up to ``n`` random works from the session's deck.

    ``n`` is clamped to ``[1, 50]``; ``token`` identifies a session (absent
    tokens share an anonymous deck).  Each token owns an in-memory deck of
    work ids that advances on every request; when it runs out the deck is
    rebuilt, so works repeat only across deck rebuilds (every ~N requests per
    token when the deck exhausts) or after an API restart; within a single
    deck cycle there are no repeats.
    """
    n = max(1, min(n, 50))
    try:
        ids = deck_store.deal(token, n)
        with contextlib.closing(db.connect_ro()) as conn:
            rows = db.work_rows_by_ids(conn, ids)
    except sqlite3.Error as exc:
        raise HTTPException(
            status_code=503,
            detail=f"Database not reachable at {db.default_db_path()}: {exc}",
        )

    works = []
    for work_id in ids:  # keep dealt order
        row = rows.get(work_id)
        if row is None:
            continue  # defensive: id vanished between deal and fetch
        work = dict(row)
        work["image_url"] = work["ImagePath"]
        works.append(work)
    return works
