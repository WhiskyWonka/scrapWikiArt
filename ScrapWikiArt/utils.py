import hashlib

import pandas as pd
from bs4 import BeautifulSoup


def item_id(url: str) -> str:
    """Deterministic, collision-resistant item id derived from the URL.

    Same URL -> same id across runs and processes (pure function, no state).
    Uses full SHA-1 hex (40 chars, 160 bits); birthday-bound collision risk is
    negligible even for tens of millions of items.
    """
    return hashlib.sha1(url.encode()).hexdigest()


def filter_missing_descriptions(df, columns):
    """Return rows where EVERY column in `columns` is missing (NaN/None,
    empty string, or whitespace-only).

    pandas isna() does not detect empty strings: to_csv() writes missing
    cells as empty strings and read_csv() can parse them back as ''.
    """
    mask = pd.Series(True, index=df.index)
    for col in columns:
        mask &= df[col].isna() | df[col].astype(str).str.strip().eq("")
    return df[mask]


def labeled_text(raw_html):
    """Extract text from a '<li>' fragment, dropping '<s>' field labels.

    Robust to whitespace, indentation, class and attribute changes in
    wikiart.org's HTML — unlike string .replace() on raw markup.
    Returns None for None input, extracted text otherwise.
    """
    if raw_html is None:
        return None
    soup = BeautifulSoup(raw_html, features="lxml")
    for label in soup.find_all("s"):
        label.decompose()
    return soup.get_text().strip()
