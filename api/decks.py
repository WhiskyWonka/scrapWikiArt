"""In-memory per-token decks of work ids for the ``/api/random`` endpoint.

Each token (a client-supplied session id) owns an independent FIFO deck of
work ``Id``s.  A request *deals* ids off the top of the deck instead of
re-selecting from the database, so the deck advances deterministically until
it runs out, at which point it is rebuilt (re-fetch + reshuffle).
"""

import collections
import threading
import time

EMPTY_REBUILD_COOLDOWN = 30.0


class DeckStore:
    """Per-token FIFO decks of work ids.

    The store is deliberately DB-agnostic: it is constructed with a
    ``build_deck`` callable that returns a fresh list of ids; the caller owns
    the database fetch.

    ``max_decks`` caps the number of per-token decks held in memory.
    When the cap is exceeded the least-recently-used deck is evicted.
    An optional ``clock`` callable (default :func:`time.monotonic`) is
    exposed for testing the empty-catalog cooldown.

    All deck mutation is guarded by a single lock so concurrent requests for
    the same token never deal overlapping ids.  The expensive rebuild
    (DB fetch + shuffle) happens *outside* the lock so concurrent rebuilds
    for different tokens do not serialize.
    """

    def __init__(self, build_deck, max_decks=1000, clock=None):
        self._build_deck = build_deck
        self._decks = collections.OrderedDict()
        self._lock = threading.Lock()
        self._max_decks = max_decks
        self._last_empty_build = collections.OrderedDict()  # token → monotonic timestamp
        self._clock = clock if clock is not None else time.monotonic

    def deal(self, token, n):
        """Deal up to ``n`` ids from ``token``'s deck, in deck order.

        An empty deck is rebuilt (re-fetch + reshuffle) before dealing, so an
        empty result is only possible if the catalog itself is empty.  Unknown
        tokens silently get a fresh deck.

        When the catalog is confirmed empty, rebuilding is throttled per-token
        for ``EMPTY_REBUILD_COOLDOWN`` seconds to avoid a DB-scan storm.

        Raises ``ValueError`` if ``n < 1``.
        """
        if n < 1:
            raise ValueError("n must be >= 1")

        # Fast path — deck exists; pop under the lock, no rebuild.
        with self._lock:
            deck = self._decks.get(token)
            if deck is not None:
                self._decks.move_to_end(token)
                if len(deck) >= n:
                    return [deck.popleft() for _ in range(n)]
                if deck:
                    # Partial deck — return what's available without rebuilding.
                    return [deck.popleft() for _ in range(len(deck))]

        # Slow path — deck missing or empty.

        # Check per-token empty-catalog cooldown before rebuilding.
        now = self._clock()
        with self._lock:
            last_empty = self._last_empty_build.get(token, float("-inf"))
            if now - last_empty < EMPTY_REBUILD_COOLDOWN:
                return []

        # Rebuild *outside* the lock so concurrent rebuilds for different
        # tokens do not block each other.
        built = self._build_deck()

        with self._lock:
            if not built:
                self._last_empty_build[token] = self._clock()
                self._last_empty_build.move_to_end(token)
                # Cap _last_empty_build to the same bound as _decks.
                while len(self._last_empty_build) > self._max_decks:
                    self._last_empty_build.popitem(last=False)

            deck = self._decks.get(token)
            if deck is None or not deck:
                deck = collections.deque(built)
                self._decks[token] = deck
                self._decks.move_to_end(token)
                # Evict LRU if over cap.
                while len(self._decks) > self._max_decks:
                    evicted_token, _ = self._decks.popitem(last=False)
                    self._last_empty_build.pop(evicted_token, None)

            return [deck.popleft() for _ in range(min(n, len(deck)))]
