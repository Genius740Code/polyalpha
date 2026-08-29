"""
HubFeed — Stream-compatible price source driven by an external hub feed.

The polyalpha ``Sniper`` normally opens its own Polymarket CLOB WebSocket
via ``client.stream(market)``. That socket drops / reconnects frequently and,
between reconnects, serves a stale price. The plain comparison bot instead
consumes the *shared* CLOB feed aggregated by the hub (``HubClient``), so it
always acts on fresh ``book`` / ``price_change`` / ``best_bid_ask`` data.

To route the Sniper onto that shared feed (instead of its own WebSocket),
build a :class:`HubFeed`, wire the hub's CLOB events into it, and hand it to
the Sniper::

    feed = HubFeed(market=market, up=market.up_price, down=market.down_price)

    def on_book(msg):
        # msg exposes best bid/ask per side — push the UP/DOWN mids
        feed.push(up, down)

    hub.subscribe(on_book=on_book)          # external hub wiring
    sniper = Sniper(client, config, stream=feed)
    sniper.run()

The adapter exposes exactly the surface the Sniper expects from its stream
(``up``/``down``, ``on(event)``, ``price_age_seconds()``, ``running``,
``start()``, ``stop()``), so the Sniper's own logic — including the staleness
guard — works unchanged and the market's UP/DOWN orientation is preserved:
prices are pushed in (up, down) order and read back the same way.

It can also act as a **market provider** for parity with the hub's
``on_market → slug`` event. Call :meth:`set_market` / :meth:`push_market`
when the hub discovers a new slug, then pass ``market_provider=feed`` to the
``Sniper`` so it reuses the hub's slug instead of calling
``client.markets.latest()`` on its own and racing the 5-min boundary.

Events
------
``price``  (up: float, down: float) — emitted on every ``push()``
``close``  ()                       — market resolved (call :meth:`close`)
``error``  (exc: Exception)         — feed failure surfaced to the Sniper
"""

from __future__ import annotations

import logging
import threading
import time
from collections import defaultdict
from typing import Any, Callable

log = logging.getLogger(__name__)

EVENTS = frozenset({"price", "close", "error", "connect"})


class HubFeed:
    """A shared hub feed wrapped to look like a polyalpha ``Stream``.

    Instead of owning a WebSocket, this container is *pushed into* by the
    external hub. ``push()`` records a timestamped UP/DOWN price pair so the
    Sniper can both read ``feed.up`` / ``feed.down`` and gate on its age via
    :meth:`price_age_seconds`.

    It doubles as a :class:`MarketProvider` for parity: push the hub's current
    market via :meth:`set_market` / :meth:`push_market` and the Sniper will
    consume it through ``market_provider=feed`` instead of discovering its own
    slug.
    """

    def __init__(
        self,
        market: Any = None,
        up: float = 0.0,
        down: float = 0.0,
    ) -> None:
        self.market = market
        self.up = float(up)
        self.down = float(down)

        self._handlers: dict[str, list[Callable]] = defaultdict(list)
        self._lock = threading.Lock()
        self._thread: threading.Thread | None = None
        self._stop = threading.Event()
        self._running = False
        self._market_lock = threading.Lock()

        # Staleness clock — mirrors Stream._last_price_time
        self._last_price_time: float = time.time()

    # ── Prices ──────────────────────────────────────────────────────────────

    def push(self, up: float, down: float) -> None:
        """Publish a fresh UP/DOWN price pair from the hub feed.

        Records the timestamp (so ``price_age_seconds()`` reflects this
        update) and emits a ``price`` event for the Sniper's entry trigger.
        """
        self.up = float(up)
        self.down = float(down)
        self._last_price_time = time.time()
        self.emit("price", self.up, self.down)

    def push_book(self, side: str, bids, asks, last_trade_price: float = 0.0) -> None:
        """Update one leg's mid price from a CLOB ``book`` event.

        Uses the best (top-of-book) bid/ask level, matching the reference
        CLOB feed. ``side`` is ``"UP"`` or ``"DOWN"`` (case-insensitive).
        """
        price = _best_mid(bids, asks, last_trade_price)
        if price is None:
            return
        if str(side).upper() == "UP":
            self.push(price, self.down)
        else:
            self.push(self.up, price)

    # ── Market provider (for parity with hub's on_market → slug) ──────────

    def get_market(self) -> Any | None:
        """Return the last market pushed via :meth:`set_market` (or ``self.market``)."""
        with self._market_lock:
            return self.market

    def set_market(self, market: Any) -> None:
        """Store *market* as the current hub market."""
        with self._market_lock:
            self.market = market

    def push_market(self, market: Any) -> None:
        """Alias for :meth:`set_market` — mirrors :meth:`push` naming."""
        self.set_market(market)

    def close(self, *args, **kwargs) -> None:
        """Tell the Sniper the market resolved / the feed shut down."""
        self.emit("close")
        self._running = False

    def price_age_seconds(self) -> float:
        """Seconds since the last ``push()`` — large → the feed went quiet."""
        return time.time() - self._last_price_time

    # ── Stream-compatible lifecycle (Sniper calls these) ─────────────────────

    @property
    def running(self) -> bool:
        """True while the feed is active. Sniper waits on it during resolve."""
        return self._running or (self._thread is not None and self._thread.is_alive())

    def start(self, background: bool = False) -> None:
        """Mark the feed active. No connection is opened — the hub drives it."""
        self._stop.clear()
        self._running = True
        if background and self._thread is None:
            self._thread = threading.Thread(
                target=self._run,
                daemon=True,
                name="polyalpha-hub-feed",
            )
            self._thread.start()
        self.emit("connect")

    def stop(self) -> None:
        """Stop the keepalive thread and mark the feed inactive."""
        self._stop.set()
        self._running = False
        if self._thread is not None:
            self._thread = None

    def _run(self) -> None:
        """Liveness thread — no-op until ``stop()`` is called."""
        while not self._stop.wait(1.0):
            pass

    # ── Events ──────────────────────────────────────────────────────────────

    def on(self, event: str) -> Callable:
        """Decorator — register *fn* for *event* (same API as ``Stream.on``)."""
        def decorator(fn: Callable) -> Callable:
            self.add_handler(event, fn)
            return fn
        return decorator

    def add_handler(self, event: str, fn: Callable) -> None:
        if event not in EVENTS:
            raise ValueError(f"Unknown event '{event}'. Valid: {sorted(EVENTS)}")
        self._handlers[event].append(fn)

    def emit(self, event: str, *args) -> None:
        for fn in self._handlers.get(event, []):
            try:
                fn(*args)
            except Exception as exc:
                log.exception("HubFeed: handler '%s' raised: %s", event, exc)


def _best_mid(bids, asks, last_trade_price: float = 0.0) -> float | None:
    """Best-level bid/ask mid-price with last-trade fallback (like Stream._mid).

    Returns ``None`` when no usable price can be derived.
    """
    try:
        best_bid = float(bids[0]["price"]) if bids else 0.0
        best_ask = float(asks[0]["price"]) if asks else 0.0
        if best_bid > 0 and best_ask > 0:
            return round((best_bid + best_ask) / 2.0, 6)
        if last_trade_price > 0:
            return round(float(last_trade_price), 6)
    except (TypeError, ValueError, KeyError, IndexError):
        return None
    return None


__all__ = ["HubFeed"]
