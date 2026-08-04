"""
Shared Globals — every continuously-running feed created once.

Plan item 5: one connection, many strategies. Construct a :class:`Globals`
once in ``main()``, ``.start()`` it, then let every per-market
:class:`MarketCtx` read from the same instances. Adding a strategy costs 0
extra connections — the feeds below are the only continuously-running
connections the whole program opens.

Pattern to reproduce (from the deleted ``polymarket_signal_bot_v3``)::

    async def main():
        globals_ = Globals.defaults("BTC")
        globals_.start()
        try:
            while True:
                market = client.markets.latest("BTC", "5m")
                await watch_market(globals_, market, on_tick)
        finally:
            globals_.stop()

    def on_tick(ctx):
        if ctx.remaining <= 0:
            return
        favourite, price = ctx.favourite()
        if favourite and ctx.globals.cvd is not None:
            ...

Per-market scope is ONLY the market-specific data: a
:class:`~polyalpha.orderbook.tracker.TokenPairTracker` wrapped in a
:class:`MarketCtx`, ticked every ``interval`` seconds until the window
expires, then stopped.

Feeds that are not yet built in polyalpha (Binance klines / OBI / futures
caches, the trade DB) are tracked separately under TOD — the corresponding
``Globals`` fields stay ``None`` and ``start()`` / ``stop()`` simply skip
them.
"""

from __future__ import annotations

import asyncio
import logging
import time
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Callable, Optional

log = logging.getLogger(__name__)

DEFAULT_TICK_INTERVAL = 2.0

_FEED_FIELDS = (
    "price_feed",
    "klines",
    "cvd",
    "obi_cache",
    "futures",
    "liq",
    "db",
    "eth_feed",
    "klines_15m",
    "klines_1h",
)


@dataclass
class Globals:
    """One instance of every continuously-running global feed.

    Attributes
    ----------
    asset : str
        The spot asset the shared feeds track (used to start ``price_feed``).
    price_feed : object | None
        BTC spot price — ``ChainlinkStreamer`` (Polymarket's own Chainlink
        oracle WS, the exact feed that decides up/down resolution). Started
        once with ``background=True``; every strategy reads the same instance.
    cvd : object | None
        Binance BTC aggTrade cumulative volume delta — ``CVDTracker``.
    liq : object | None
        Liquidation cluster feed — ``LiquidationTracker`` (plan item 6).
    klines, obi_cache, futures, db, eth_feed, klines_15m, klines_1h :
        Optional global feeds. Out of scope for this plan (None by default),
        skipped by ``start()`` / ``stop()``.
    """

    asset: str = "BTC"
    price_feed: Optional[object] = None
    klines: Optional[object] = None
    cvd: Optional[object] = None
    obi_cache: Optional[object] = None
    futures: Optional[object] = None
    liq: Optional[object] = None
    db: Optional[object] = None
    eth_feed: Optional[object] = None
    klines_15m: Optional[object] = None
    klines_1h: Optional[object] = None

    _started: list[object] = field(default_factory=list, init=False, repr=False)

    @classmethod
    def defaults(
        cls,
        asset: str = "BTC",
        *,
        price_feed: bool = True,
        cvd: bool = True,
        liq: bool = False,
    ) -> "Globals":
        """Build the standard in-scope shared feeds.

        Constructs (but does not start) a ``ChainlinkStreamer`` as
        ``price_feed``, a ``CVDTracker`` as ``cvd`` and a
        ``LiquidationTracker`` as ``liq`` (when ``liq=True``).

        Returns
        -------
        Globals
            A ``Globals`` with the requested feeds set.
        """
        g = cls(asset=asset)
        if price_feed:
            from .analysis.streaming import ChainlinkStreamer

            g.price_feed = ChainlinkStreamer()
        if cvd:
            from .analysis.delta import CVDTracker

            g.cvd = CVDTracker()
        if liq:
            from .analysis.liquidations import LiquidationTracker

            g.liq = LiquidationTracker()
        return g

    # ── Lifecycle ──────────────────────────────────────────────────────────────

    def start(self) -> None:
        """Start every non-None feed exactly once (idempotent).

        ``price_feed`` starts with ``background=True`` in its own daemon
        thread; async feeds (``cvd``, ``liq``) must be started inside a
        running event loop — call this from an ``async`` ``main()``.
        """
        for name in _FEED_FIELDS:
            feed = getattr(self, name)
            if feed is None or feed in self._started:
                continue
            try:
                if name == "price_feed":
                    feed.start(self.asset, background=True)
                else:
                    start = getattr(feed, "start", None)
                    if start is None:
                        continue
                    start()
            except Exception as exc:  # noqa: BLE001 — one bad feed shouldn't kill the rest
                log.warning("Globals.%s failed to start: %s", name, exc)
                continue
            self._started.append(feed)

    def stop(self) -> None:
        """Stop every started feed, in reverse order (idempotent)."""
        for feed in reversed(self._started):
            try:
                stop = getattr(feed, "stop", None)
                if stop is not None:
                    stop()
            except Exception as exc:  # noqa: BLE001 — best-effort shutdown
                log.warning("Globals feed stop failed: %s", exc)
        self._started.clear()

    @property
    def started(self) -> list[object]:
        """Feeds currently started by this ``Globals``."""
        return list(self._started)


def _to_epoch(value) -> Optional[float]:
    """Coerce ``end_time`` (ISO-8601 str, epoch float, or None) to epoch."""
    if value is None:
        return None
    if isinstance(value, (int, float)):
        return float(value)
    s = str(value).strip()
    if not s:
        return None
    if s.endswith("Z"):
        s = s[:-1] + "+00:00"
    try:
        dt = datetime.fromisoformat(s)
    except ValueError:
        return None
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return dt.timestamp()


class MarketCtx:
    """Per-market scope — one :class:`TokenPairTracker` plus shared feeds.

    Holds ``globals`` (the shared :class:`Globals`), ``tracker`` (the
    per-market CLOB book), ``open_price`` and ``end_time``, and exposes the
    observation API used by the legacy per-market watch loop.

    Attributes
    ----------
    globals : Globals
        Shared feeds — every market reads the same instances.
    tracker : TokenPairTracker
        This market's UP/DOWN book + trade tape.
    open_price : float | None
        UP-leg price at market open.
    end_time : float | None
        Epoch seconds when the window expires (None = unbounded).
    """

    def __init__(
        self,
        globals: Globals,
        tracker,
        open_price: Optional[float] = None,
        end_time: Optional[float] = None,
    ):
        self.globals = globals
        self.tracker = tracker
        self.open_price = open_price
        self.end_time = end_time

    # ── Time ────────────────────────────────────────────────────────────────

    @property
    def remaining(self) -> float:
        """Seconds left in the market window (0 once expired).

        Returns ``float("inf")`` when no ``end_time`` was set.
        """
        if self.end_time is None:
            return float("inf")
        return max(0.0, self.end_time - time.time())

    @property
    def expired(self) -> bool:
        """True once ``remaining <= 0`` (only meaningful with an end_time)."""
        return self.end_time is not None and self.remaining <= 0

    # ── Observation API ─────────────────────────────────────────────────────

    def price(self) -> tuple[Optional[float], Optional[float]]:
        """Current ``(up_mid, down_mid)``; a leg is ``None`` when stale/missing."""
        return self.tracker.up_mid, self.tracker.down_mid

    def favourite(self) -> tuple[Optional[str], Optional[float]]:
        """Which leg is favoured: ``("UP", mid)`` / ``("DOWN", mid)`` / ``(None, None)``."""
        return self.tracker.favourite()

    def _tid(self, side: str) -> str:
        return self.tracker.down_id if (side or "").upper() == "DOWN" else self.tracker.up_id

    def spread(self, side: str) -> Optional[dict]:
        """Spread snapshot + stats for one leg.

        Returns ``{"current", "stats", "expansion"}`` — ``current`` is
        ``{"spread", "bid", "ask"}`` (or ``None`` when a side of the book is
        missing), ``stats`` is the ``(mean, std)`` spread stats and
        ``expansion`` the ``spread_expansion`` dict (each ``None`` when there
        is not enough history).
        """
        tid = self._tid(side)
        bid, ask = self.tracker.best_bid.get(tid), self.tracker.best_ask.get(tid)
        current = None
        if bid is not None and ask is not None:
            current = {"spread": ask - bid, "bid": bid, "ask": ask}
        return {
            "current": current,
            "stats": self.tracker.spread_stats(tid),
            "expansion": self.tracker.spread_expansion(tid),
        }

    def trade_sweep(self, side: str, **kwargs) -> Optional[dict]:
        """One-sided trade burst on a leg (``tracker.sweep``), or None.

        Parameters
        ----------
        side : "UP" | "DOWN"
            The leg to inspect.
        **kwargs
            Forwarded to :meth:`TokenPairTracker.sweep` (window_s, min_count,
            min_notional).
        """
        return self.tracker.sweep(self._tid(side), **kwargs)


async def watch_market(
    globals: Globals,
    market,
    tick: Callable[[MarketCtx], None],
    interval: float = DEFAULT_TICK_INTERVAL,
    timeframe: Optional[str] = None,
) -> None:
    """Run *tick* against one market until its window expires.

    Creates a per-market :class:`~polyalpha.orderbook.tracker.TokenPairTracker`,
    starts it, wraps it in a :class:`MarketCtx`, and calls ``tick(ctx)`` every
    ``interval`` seconds while ``ctx.remaining > 0``. The tracker is stopped
    in ``finally`` so one market leaving scope never leaks a connection.

    Parameters
    ----------
    globals : Globals
        The shared feeds for every market.
    market : Market
        The market being watched. ``market.up_token`` / ``market.down_token``
        give the CLOB token IDs; ``market.end_time`` bounds the window.
    tick : Callable[[MarketCtx], None]
        Called every ``interval`` seconds with the per-market context.
    interval : float
        Seconds between ticks (default 2.0).
    timeframe : str, optional
        Fallback duration (e.g. ``"5m"``) when ``market.end_time`` cannot be
        parsed.
    """
    from .core.constants import TIMEFRAME_SECONDS

    up_id = getattr(market, "up_token", None)
    down_id = getattr(market, "down_token", None)
    if not up_id or not down_id:
        raise ValueError("market must expose up_token and down_token token IDs")

    tracker = _new_tracker(up_id, down_id)
    tracker.start()
    end_epoch = _to_epoch(getattr(market, "end_time", None))
    if end_epoch is None and timeframe:
        end_epoch = time.time() + TIMEFRAME_SECONDS.get(timeframe, 300)
    ctx = MarketCtx(
        globals=globals,
        tracker=tracker,
        open_price=float(getattr(market, "up_price", 0.0) or 0.0),
        end_time=end_epoch,
    )
    try:
        while not ctx.expired:
            tick(ctx)
            await asyncio.sleep(interval)
    finally:
        tracker.stop()


def _new_tracker(up_id: str, down_id: str):
    """Instantiate a TokenPairTracker (imported lazily to avoid cycles)."""
    from .orderbook.tracker import TokenPairTracker

    return TokenPairTracker(up_id, down_id)


__all__ = ["Globals", "MarketCtx", "watch_market", "default_globals"]


def default_globals(asset: str = "BTC", **kwargs) -> Globals:
    """Convenience alias for ``Globals.defaults(asset, **kwargs)``."""
    return Globals.defaults(asset, **kwargs)
