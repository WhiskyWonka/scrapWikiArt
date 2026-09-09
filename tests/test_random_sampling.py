"""Spider-level tests for random sampling in the wikiart spider (issue #48).

Covers: deterministic seeds, exact enqueue/skip with a patched RNG, p=1.0
no-op, invalid-p ValueError, dedupe-wins-over-sampling, and a robust
(CAN differ) statistical non-determinism check.
"""

import random
import unittest
from unittest import mock

import scrapy.http
from scrapy.settings import Settings

from ScrapWikiArt.spiders.wikiart import WikiArtSpider

ARTIST_LISTING_BODY = b"""
<html><body><main><div><ul>
<li><a href="/en/paintings/one">One</a></li>
<li><a href="/en/paintings/two">Two</a></li>
<li><a href="/en/paintings/three">Three</a></li>
<li><a href="/en/paintings/four">Four</a></li>
</ul></div></main></body></html>
"""

MANY_LISTING_BODY = b"""
<html><body><main><div><ul>
%s
</ul></div></main></body></html>
""" % b"\n".join(
    f'<li><a href="/en/paintings/work-{i}">Work {i}</a></li>'.encode()
    for i in range(50)
)

URLS = {
    "one": "https://www.wikiart.org/en/paintings/one",
    "two": "https://www.wikiart.org/en/paintings/two",
    "three": "https://www.wikiart.org/en/paintings/three",
    "four": "https://www.wikiart.org/en/paintings/four",
}


def _artist_response(body=ARTIST_LISTING_BODY):
    return scrapy.http.HtmlResponse(
        url="https://www.wikiart.org/en/artist/test/all-works/text-list",
        body=body,
        encoding="utf-8",
    )


def _make_sampling_spider(p=1.0, seed=None):
    """Build a wikiart spider with sampling settings injected and initialized.

    Selects the real _init_sampling() path: settings are injected, then the
    method validates p, reads the seed (three-state), and builds self._rng.
    """
    spider = WikiArtSpider()
    settings = Settings()
    settings.set("WIKIART_SAMPLE_RATIO", p)
    if seed is not None:
        settings.set("WIKIART_RANDOM_SEED", seed)
    spider.settings = settings
    spider._init_sampling()
    return spider


class TestSamplingDeterminism(unittest.TestCase):

    def test_same_seed_same_subset(self):
        """Spec: same seed + ratio + page -> identical enqueued subsets."""
        spider_a = _make_sampling_spider(p=0.5, seed=42)
        spider_b = _make_sampling_spider(p=0.5, seed=42)
        response = _artist_response(MANY_LISTING_BODY)
        yields_a = [r.url for r in spider_a.parse_artist(response)]
        yields_b = [r.url for r in spider_b.parse_artist(response)]
        self.assertEqual(yields_a, yields_b)
        self.assertGreater(len(yields_a), 0)
        self.assertLess(len(yields_a), 50)

    def test_seed_zero_is_deterministic(self):
        """Spec: seed 0 is a valid deterministic seed, not 'unset'."""
        spider_a = _make_sampling_spider(p=0.5, seed=0)
        spider_b = _make_sampling_spider(p=0.5, seed=0)
        response = _artist_response(MANY_LISTING_BODY)
        yields_a = [r.url for r in spider_a.parse_artist(response)]
        yields_b = [r.url for r in spider_b.parse_artist(response)]
        self.assertEqual(yields_a, yields_b)
        self.assertGreater(len(yields_a), 0)

    def test_different_seeds_can_differ(self):
        """Spec: different seeds MAY yield different subsets (CAN differ)."""
        spider_a = _make_sampling_spider(p=0.5, seed=1)
        spider_b = _make_sampling_spider(p=0.5, seed=2)
        yields_a = [r.url for r in spider_a.parse_artist(_artist_response(MANY_LISTING_BODY))]
        yields_b = [r.url for r in spider_b.parse_artist(_artist_response(MANY_LISTING_BODY))]
        # 50 URLs at p=0.5: probability two seeds agree on every draw is ~2^-50.
        self.assertNotEqual(yields_a, yields_b)


class TestSamplingGate(unittest.TestCase):

    def test_patched_rng_exact_enqueue_skip(self):
        """Fixed RNG sequence -> exact enqueue/skip set, seen marks rejected."""
        spider = _make_sampling_spider(p=0.5, seed=1)
        spider._p = 0.5
        spider._rng = mock.MagicMock()
        # rng.random() < 0.5: 0.3 enqueue, 0.7 skip, 0.2 enqueue, 0.8 skip
        spider._rng.random.side_effect = [0.3, 0.7, 0.2, 0.8]
        requests = list(spider.parse_artist(_artist_response()))
        self.assertEqual(
            {r.url for r in requests},
            {URLS["one"], URLS["three"]},
        )
        # Rejected URLs were still marked seen (sampling never re-evaluates).
        self.assertEqual(
            spider.seen,
            {URLS["one"], URLS["two"], URLS["three"], URLS["four"]},
        )

    def test_p1_noop_yields_all_without_rng(self):
        """Spec: default p=1.0 enqueues every unseen URL, RNG never called."""
        spider = _make_sampling_spider(p=1.0, seed=None)
        spider._rng = mock.MagicMock()
        requests = list(spider.parse_artist(_artist_response()))
        self.assertEqual(
            {r.url for r in requests},
            {URLS["one"], URLS["two"], URLS["three"], URLS["four"]},
        )
        spider._rng.random.assert_not_called()

    def test_dedupe_wins_over_sampling(self):
        """Spec: URL already in seen is skipped before the sampling check."""
        spider = _make_sampling_spider(p=0.5, seed=1)
        spider.seen = {URLS["one"]}
        spider._p = 0.5
        spider._rng = mock.MagicMock()
        spider._rng.random.return_value = 0.0  # would accept everything
        requests = list(spider.parse_artist(_artist_response()))
        urls = {r.url for r in requests}
        self.assertNotIn(URLS["one"], urls)
        self.assertEqual(
            urls,
            {URLS["two"], URLS["three"], URLS["four"]},
        )

    def test_rejected_url_not_reevaluated(self):
        """Spec: a URL rejected by sampling is seen on the next pass."""
        spider = _make_sampling_spider(p=0.5, seed=3)
        response = _artist_response()
        first = list(spider.parse_artist(response))
        self.assertLess(len(first), 4)  # sampling actually rejected something
        second = list(spider.parse_artist(response))
        self.assertEqual(second, [])


class TestSamplingInit(unittest.TestCase):

    def test_invalid_p_zero_raises(self):
        with self.assertRaises(ValueError):
            _make_sampling_spider(p=0, seed=None)

    def test_invalid_p_negative_raises(self):
        with self.assertRaises(ValueError):
            _make_sampling_spider(p=-0.5, seed=None)

    def test_invalid_p_above_one_raises(self):
        with self.assertRaises(ValueError):
            _make_sampling_spider(p=1.5, seed=None)

    def test_sampling_state_set_by_init(self):
        spider = _make_sampling_spider(p=0.25, seed=42)
        self.assertEqual(spider._p, 0.25)
        self.assertIsInstance(spider._rng, random.Random)
        # Same-seed equivalence across fresh spiders (reproducibility wiring).
        other = _make_sampling_spider(p=0.25, seed=42)
        self.assertEqual(
            [spider._rng.random() for _ in range(10)],
            [other._rng.random() for _ in range(10)],
        )


if __name__ == "__main__":
    unittest.main()