"""Tests for the should_sample Bernoulli gate (issue #48)."""

import random
import unittest
from unittest import mock

from ScrapWikiArt.utils import should_sample


class TestShouldSample(unittest.TestCase):
    """Unit tests for the pure should_sample(rng, p) helper."""

    def test_p1_always_returns_true(self):
        """p=1.0 is a no-op: always returns True without calling RNG."""
        rng = random.Random(42)
        for _ in range(100):
            self.assertTrue(should_sample(rng, 1.0))

    def test_p1_never_calls_rng(self):
        """p=1.0 short-circuits: rng.random() must never be called."""
        rng = random.Random(42)
        rng.random = mock.MagicMock(return_value=0.0)
        for _ in range(10):
            should_sample(rng, 1.0)
        rng.random.assert_not_called()

    def test_p0_rejects_all(self):
        """p approaching 0.0 rejects almost all URLs (with a seeded RNG)."""
        rng = random.Random(42)
        results = [should_sample(rng, 0.0001) for _ in range(1000)]
        # With p=0.0001, expect very few True — at most a handful
        self.assertLess(sum(results), 10)

    def test_p05_approximately_half(self):
        """p=0.5 yields roughly half over many calls."""
        rng = random.Random(42)
        results = [should_sample(rng, 0.5) for _ in range(10000)]
        ratio = sum(results) / len(results)
        # Allow wide tolerance for flakiness resistance
        self.assertGreater(ratio, 0.40)
        self.assertLess(ratio, 0.60)

    def test_invalid_p_zero_raises(self):
        """p=0 raises ValueError (not clamped, not skipped)."""
        rng = random.Random(42)
        with self.assertRaises(ValueError):
            should_sample(rng, 0)

    def test_invalid_p_negative_raises(self):
        """p=-0.5 raises ValueError."""
        rng = random.Random(42)
        with self.assertRaises(ValueError):
            should_sample(rng, -0.5)

    def test_invalid_p_above_one_raises(self):
        """p=1.5 raises ValueError."""
        rng = random.Random(42)
        with self.assertRaises(ValueError):
            should_sample(rng, 1.5)

    def test_determinism_same_seed_same_results(self):
        """Same seed + same p → same sequence of True/False."""
        p = 0.5
        results_a = []
        results_b = []
        for seed in (42, 42):
            rng = random.Random(seed)
            results = [should_sample(rng, p) for _ in range(100)]
            if seed == 42 and not results_a:
                results_a = results
            else:
                results_b = results
        self.assertEqual(results_a, results_b)

    def test_different_seeds_may_differ(self):
        """Different seeds CAN produce different sequences (statistical)."""
        p = 0.5
        rng_a = random.Random(1)
        rng_b = random.Random(2)
        results_a = [should_sample(rng_a, p) for _ in range(100)]
        results_b = [should_sample(rng_b, p) for _ in range(100)]
        self.assertNotEqual(results_a, results_b)


if __name__ == "__main__":
    unittest.main()
