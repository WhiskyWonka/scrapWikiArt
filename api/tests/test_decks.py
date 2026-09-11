"""Unit tests for the per-token DeckStore (no database involved)."""

import collections
import threading
import unittest

from api.decks import DeckStore, EMPTY_REBUILD_COOLDOWN


def sequential_ids(size=100):
    """Deterministic id list: ``["id-001", ..., "id-100"]``."""
    return [f"id-{i:03d}" for i in range(1, size + 1)]


class TestDeal(unittest.TestCase):
    def test_returns_n_ids_and_advances(self):
        store = DeckStore(lambda: sequential_ids())
        first = store.deal("tok", 5)
        second = store.deal("tok", 5)
        self.assertEqual(first, [f"id-{i:03d}" for i in range(1, 6)])
        self.assertEqual(second, [f"id-{i:03d}" for i in range(6, 11)])
        self.assertTrue(set(first).isdisjoint(second))

    def test_two_tokens_get_independent_decks(self):
        store = DeckStore(lambda: sequential_ids())
        store.deal("a", 3)  # consume from a's deck
        # b's deck starts at the top: a's consumption must not advance it
        self.assertEqual(store.deal("b", 3), [f"id-{i:03d}" for i in range(1, 4)])

    def test_rebuilds_when_exhausted(self):
        builds = []

        def builder():
            builds.append(1)
            return sequential_ids(5)

        store = DeckStore(builder)
        self.assertEqual(store.deal("tok", 5), [f"id-{i:03d}" for i in range(1, 6)])
        self.assertEqual(len(builds), 1)
        # deck is empty: the next deal rebuilds and deals again (no empty response)
        self.assertEqual(store.deal("tok", 2), [f"id-{i:03d}" for i in range(1, 3)])
        self.assertEqual(len(builds), 2)

    def test_deal_more_than_remaining_returns_remaining_then_rebuilds(self):
        builds = []

        def builder():
            builds.append(1)
            return sequential_ids(5)

        store = DeckStore(builder)
        self.assertEqual(len(store.deal("tok", 4)), 4)
        # only 1 id remains: deal returns it without rebuilding (no infinite loop)
        self.assertEqual(store.deal("tok", 50), ["id-005"])
        self.assertEqual(len(builds), 1)
        # next call finds an empty deck, rebuilds, and deals again
        self.assertEqual(len(store.deal("tok", 50)), 5)
        self.assertEqual(len(builds), 2)

    def test_unknown_token_creates_deck(self):
        store = DeckStore(lambda: sequential_ids())
        self.assertEqual(store.deal("never-seen", 2), ["id-001", "id-002"])

    def test_empty_catalog_returns_empty_list(self):
        store = DeckStore(lambda: [])
        self.assertEqual(store.deal("tok", 12), [])
        self.assertEqual(store.deal("tok", 12), [])  # no infinite rebuild loop

    def test_thread_safety_no_duplicate_ids_within_window(self):
        store = DeckStore(lambda: sequential_ids(200))
        results = []
        errors = []

        def worker():
            try:
                results.extend(store.deal("shared", 20))
            except Exception as exc:  # pragma: no cover - surfaces via errors
                errors.append(exc)

        threads = [threading.Thread(target=worker) for _ in range(2)]
        for thread in threads:
            thread.start()
        for thread in threads:
            thread.join()

        self.assertEqual(errors, [])
        self.assertEqual(len(results), 40)
        # the 200-id deck window guarantees 40 strictly unique ids
        self.assertEqual(len(set(results)), 40)


    def test_concurrent_rebuilds_exercise_rebuild_guard(self):
        """Small deck window forces concurrent rebuilds; no duplicate ids."""
        build_counter = [0]
        build_lock = threading.Lock()  # protects only the counter

        def builder():
            with build_lock:
                build_counter[0] += 1
                seq = build_counter[0]
            # Each build returns globally unique ids so duplicates are detectable.
            return [f"b{seq}-{i}" for i in range(3)]

        store = DeckStore(builder, max_decks=1000)
        results = []
        errors = []

        def worker():
            try:
                local = []
                for _ in range(20):
                    local.extend(store.deal("shared", 1))
                results.extend(local)
            except Exception as exc:  # pragma: no cover
                errors.append(exc)

        threads = [threading.Thread(target=worker) for _ in range(2)]
        for t in threads:
            t.start()
        for t in threads:
            t.join()

        self.assertEqual(errors, [])
        # Every deal returns exactly 1 id (deck always has ≥1 after rebuild).
        self.assertEqual(len(results), 40)
        # Every id globally unique — no duplicates even across concurrent rebuilds.
        self.assertEqual(len(set(results)), 40)


class TestDealValidation(unittest.TestCase):
    """F6 — deal(token, n) raises ValueError for n < 1."""

    def test_zero_raises(self):
        store = DeckStore(lambda: sequential_ids())
        with self.assertRaises(ValueError):
            store.deal("tok", 0)

    def test_negative_raises(self):
        store = DeckStore(lambda: sequential_ids())
        with self.assertRaises(ValueError):
            store.deal("tok", -5)


class TestFastSlowPath(unittest.TestCase):
    """F2 — fast path avoids unnecessary rebuilds; slow path rebuilds when empty."""

    def test_fast_path_no_rebuild_when_enough_remaining(self):
        builds = []

        def builder():
            builds.append(1)
            return sequential_ids(10)

        store = DeckStore(builder)
        store.deal("tok", 5)  # slow path → build (1), deal 5
        self.assertEqual(len(builds), 1)

        store.deal("tok", 5)  # fast path → 5 remaining, no rebuild
        self.assertEqual(len(builds), 1)  # key assertion: no extra build

    def test_slow_path_rebuilds_after_exhaustion(self):
        builds = []

        def builder():
            builds.append(1)
            return sequential_ids(5)

        store = DeckStore(builder)
        store.deal("tok", 5)  # build (1), deal all 5
        self.assertEqual(len(builds), 1)

        store.deal("tok", 2)  # fast path → empty → slow path → build (2)
        self.assertEqual(len(builds), 2)


class TestLruEviction(unittest.TestCase):
    """F3 — bounded store evicts least-recently-used deck when over cap."""

    def test_evicts_oldest_token_when_over_cap(self):
        builds = []

        def builder():
            builds.append(1)
            return sequential_ids(10)

        store = DeckStore(builder, max_decks=2)
        store.deal("a", 1)  # _decks = {a}
        store.deal("b", 1)  # _decks = {a, b} — at cap
        store.deal("c", 1)  # _decks = {a, b, c} → evicts a → {b, c}

        self.assertNotIn("a", store._decks)
        self.assertIn("b", store._decks)
        self.assertIn("c", store._decks)

    def test_accessing_existing_token_refreshes_recency(self):
        builds = []

        def builder():
            builds.append(1)
            return sequential_ids(10)

        store = DeckStore(builder, max_decks=2)
        store.deal("a", 1)  # _decks = {a}
        store.deal("b", 1)  # _decks = {a, b}
        store.deal("a", 1)  # fast path refreshes a → _decks = {b, a}
        store.deal("c", 1)  # _decks = {b, a, c} → evicts b → {a, c}

        self.assertIn("a", store._decks)
        self.assertNotIn("b", store._decks)
        self.assertIn("c", store._decks)

    def test_evicted_token_triggers_rebuild(self):
        builds = []

        def builder():
            builds.append(1)
            return sequential_ids(10)

        store = DeckStore(builder, max_decks=2)
        store.deal("a", 1)  # build 1
        store.deal("b", 1)  # build 2
        store.deal("c", 1)  # build 3, "a" evicted
        builds.clear()

        store.deal("a", 1)  # "a" evicted → rebuild (build 4)
        self.assertEqual(len(builds), 1)

    def test_eviction_prunes_last_empty_build(self):
        """Evicted token's _last_empty_build entry is removed."""
        store = DeckStore(lambda: [], max_decks=2)
        store.deal("a", 1)  # empty build → _last_empty_build["a"] set
        store.deal("b", 1)  # empty build → _last_empty_build["b"] set
        self.assertIn("a", store._last_empty_build)
        store.deal("c", 1)  # "a" evicted from _decks → should also leave _last_empty_build
        self.assertNotIn("a", store._last_empty_build)

    def test_last_empty_build_capped_at_max_decks(self):
        """_last_empty_build never exceeds max_decks entries."""
        fake_time = [0.0]

        def clock():
            return fake_time[0]

        max_d = 50
        store = DeckStore(lambda: [], max_decks=max_d, clock=clock)

        for i in range(max_d + 20):
            fake_time[0] += EMPTY_REBUILD_COOLDOWN + 1  # expire cooldown each time
            store.deal(f"tok-{i}", 1)

        self.assertLessEqual(len(store._last_empty_build), max_d)
        self.assertLessEqual(len(store._decks), max_d)


class TestEmptyCatalogCooldown(unittest.TestCase):
    """F4 — empty-catalog cooldown prevents DB-scan storm."""

    def test_cooldown_blocks_rebuild_within_window(self):
        fake_time = [0.0]

        def clock():
            return fake_time[0]

        builds = []

        def builder():
            builds.append(1)
            return []

        store = DeckStore(builder, clock=clock)

        store.deal("tok", 12)  # first empty build
        self.assertEqual(len(builds), 1)

        fake_time[0] += 10.0  # within cooldown
        store.deal("tok", 12)
        self.assertEqual(len(builds), 1)  # no rebuild

    def test_cooldown_expires_and_rebuilds(self):
        fake_time = [0.0]

        def clock():
            return fake_time[0]

        builds = []

        def builder():
            builds.append(1)
            return []

        store = DeckStore(builder, clock=clock)

        store.deal("tok", 12)
        self.assertEqual(len(builds), 1)

        fake_time[0] += 10.0
        store.deal("tok", 12)
        self.assertEqual(len(builds), 1)  # still within cooldown

        fake_time[0] += 25.0  # 35s total > 30s cooldown
        store.deal("tok", 12)
        self.assertEqual(len(builds), 2)  # cooldown expired → rebuild

    def test_cooldown_is_per_token(self):
        """A different token is NOT blocked by another token's cooldown."""
        fake_time = [0.0]

        def clock():
            return fake_time[0]

        builds = []

        def builder():
            builds.append(1)
            return []

        store = DeckStore(builder, clock=clock)

        store.deal("tok_a", 12)  # tok_a finds empty catalog
        self.assertEqual(len(builds), 1)

        fake_time[0] += 5.0  # within tok_a's cooldown
        store.deal("tok_b", 12)  # tok_b is a different token — should build
        self.assertEqual(len(builds), 2)  # tok_b was NOT blocked


if __name__ == "__main__":
    unittest.main()
