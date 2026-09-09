import hashlib
import random
import re

import pandas as pd
from bs4 import BeautifulSoup


def should_sample(rng: random.Random, p: float) -> bool:
    """Bernoulli gate: True -> enqueue, False -> skip.

    Rejects p <= 0 or p > 1 with ValueError (never clamp, never skip
    silently). Returns True unconditionally when p == 1.0 (no-op, no RNG
    call). Otherwise samples with probability p: rng.random() < p.
    """
    if p <= 0 or p > 1:
        raise ValueError(f"WIKIART_SAMPLE_RATIO must be > 0 and <= 1, got {p}")
    if p >= 1.0:
        return True
    return rng.random() < p


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


def image_urls_or_empty(variant_urls, fallback_url):
    """Resolve image URLs for an item, never producing None entries.

    - Uses variant URLs when present (filters out empty strings).
    - Falls back to the single <img> src when no variants exist.
    - Returns [] when nothing is found — ImagesPipeline safely skips
      empty image_urls lists (issue #7).
    """
    urls = [u for u in variant_urls if u]
    if not urls and fallback_url:
        urls = [fallback_url]
    return urls


def pipe_join(values):
    """Join an iterable of strings with " | ", skipping None and empty values.

    Returns "" for a None or empty iterable.
    """
    if not values:
        return ""
    return " | ".join(v for v in values if v)


def clean_name(*candidates):
    """Return the first non-empty candidate stripped of whitespace, or None.

    Guards against None from XPath selectors (issue #12) while normalizing
    whitespace when a value exists.
    """
    for candidate in candidates:
        if candidate is not None and candidate.strip():
            return candidate.strip()
    return None


def clean_whitespace(value):
    """Collapse runs of whitespace to a single space and strip edges.

    None-safe: returns None for None input. Empty/whitespace-only strings
    become "".
    """
    if not value:
        return value
    return re.sub(r"\s+", " ", value).strip()


# Fallback used when SPIDERS_ENABLED is unset or explicitly None. Kept as a
# module constant so tests and settings.py share one source of truth.
DEFAULT_ENABLED_SPIDERS = ["wikiart"]


def spider_is_disabled(spider):
    """Fail-closed, three-state enablement check for a spider (issue #45).

    Reads SPIDERS_ENABLED from ``spider.settings`` (Scrapy Settings):

    - key absent or None  -> DEFAULT_ENABLED_SPIDERS (only wikiart enabled)
    - explicit []         -> every spider disabled (CI-safe kill switch)
    - list of names       -> only those spiders enabled

    A comma-separated string splits like getlist would (defensive for the
    undocumented ``-s`` side channel). Relies on ``"SPIDERS_ENABLED" in
    settings`` plus ``get()``: getlist() cannot distinguish unset from None
    from [] in Scrapy 2.10. Side-effect free (no logging).
    """
    settings = spider.settings
    if "SPIDERS_ENABLED" not in settings:
        enabled = DEFAULT_ENABLED_SPIDERS
    else:
        enabled = settings.get("SPIDERS_ENABLED", DEFAULT_ENABLED_SPIDERS)
        if isinstance(enabled, str):
            enabled = [entry.strip() for entry in enabled.split(",")]
    return spider.name not in enabled
