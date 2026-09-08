import hashlib


def item_id(url: str) -> str:
    """Deterministic, collision-resistant item id derived from the URL.

    Same URL -> same id across runs and processes (pure function, no state).
    Uses full SHA-1 hex (40 chars, 160 bits); birthday-bound collision risk is
    negligible even for tens of millions of items.
    """
    return hashlib.sha1(url.encode()).hexdigest()
