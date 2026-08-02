"""
Live CLOB book stream for one UP/DOWN token pair.

Tracks the best bid/ask for both legs of a Polymarket market over a single
CLOB WebSocket, seeding from REST on connect and dropping quotes once they
go stale.

Usage
-----
    tracker = TokenPairTracker(up_id, down_id)
    tracker.start()

    # Read the latest mid anytime (None once stale)
    mid = tracker.up_mid
    if tracker.fresh():
        ...

    tracker.stop()
"""

from __future__ import annotations

import asyncio
import json
import logging
import statistics
import time
from collections import deque
from dataclasses import dataclass

import httpx

from ..core.constants import CLOB_API, CLOB_MAX_AGE_S, CLOB_WS

log = logging.getLogger(__name__)


@dataclass
class TokenPairTrackerConfig:
    """Configuration for :class:`TokenPairTracker`.

    Parameters
    ----------
    ws_url          : CLOB WebSocket endpoint.
    clob_api        : CLOB REST base URL (used to seed the book on connect).
    max_age         : Seconds without a best-bid/ask update before the quote
                      is considered stale (``fresh()`` returns False).
    ping_interval   : Seconds between text ``PING`` keepalives.
    reconnect_delay : Fixed delay between reconnect attempts on WS drop.
    http_timeout    : Timeout for the REST book-seed request.
    """

    ws_url: str = CLOB_WS
    clob_api: str = CLOB_API
    max_age: float = CLOB_MAX_AGE_S
    ping_interval: float = 10.0
    reconnect_delay: float = 3.0
    http_timeout: float = 10.0


class TokenPairTracker:
    """Best bid/ask for both UP and DOWN tokens of one market, one CLOB WS.

    Starts its own connection; multiple trackers can run independently.
    Quote data lives in :attr:`best_bid` / :attr:`best_ask` keyed by token
    ID. ``mid()`` / ``up_mid`` / ``down_mid`` return ``None`` when the book
    is stale (no update within ``max_age`` seconds).
    """

    def __init__(
        self,
        up_id: str,
        down_id: str,
        config: TokenPairTrackerConfig | None = None,
    ):
        self.up_id = up_id
        self.down_id = down_id
        self.config = config or TokenPairTrackerConfig()

        self.best_bid: dict[str, float | None] = {up_id: None, down_id: None}
        self.best_ask: dict[str, float | None] = {up_id: None, down_id: None}
        self._last_update: float = 0.0

        self.spread_history: dict[str, deque] = {
            up_id: deque(maxlen=120),
            down_id: deque(maxlen=120),
        }

        self.trade_tape: dict[str, deque] = {
            up_id: deque(maxlen=200),
            down_id: deque(maxlen=200),
        }

        self._stop = False
        self._task: asyncio.Task | None = None
        self._ping_task: asyncio.Task | None = None
        self._http = httpx.Client(timeout=self.config.http_timeout)

    # ── Quote access ───────────────────────────────────────────────────────────

    def fresh(self) -> bool:
        """True if the best bid/ask was updated within the last ``max_age`` s."""
        return self._last_update > 0 and (time.time() - self._last_update) < self.config.max_age

    def mid(self, tid: str) -> float | None:
        """Mid of best bid/ask for *tid*, or None when stale or missing a side."""
        if not self.fresh():
            return None
        bid, ask = self.best_bid.get(tid), self.best_ask.get(tid)
        if bid is not None and ask is not None:
            return (bid + ask) / 2
        return None

    @property
    def up_mid(self) -> float | None:
        return self.mid(self.up_id)

    @property
    def down_mid(self) -> float | None:
        return self.mid(self.down_id)

    # ── Favourite + spread metrics ────────────────────────────────────────────

    def favourite(self) -> tuple[str | None, float | None]:
        """Which leg is currently favoured: ``("UP", mid)`` or ``("DOWN", mid)``.

        Returns ``(None, None)`` when either mid is missing/stale or the two
        mids tie exactly (never bias toward either side).
        """
        u, d = self.up_mid, self.down_mid
        if u is None or d is None:
            return (None, None)
        if u > d:
            return ("UP", u)
        if d > u:
            return ("DOWN", d)
        return (None, None)

    def _record_spread(self, tid: str) -> None:
        """Append a spread sample for *tid* when both sides of the book exist."""
        bid, ask = self.best_bid.get(tid), self.best_ask.get(tid)
        if bid is None or ask is None:
            return
        self.spread_history[tid].append(
            {
                "ts": time.time(),
                "spread": ask - bid,
                "bid": bid,
                "ask": ask,
            }
        )

    def spread_stats(self, tid: str) -> tuple[float, float] | None:
        """``(mean, std)`` of the spread samples for *tid*, ``None`` if ``< 10``."""
        hist = self.spread_history.get(tid)
        if hist is None or len(hist) < 10:
            return None
        spreads = [s["spread"] for s in hist]
        return (statistics.mean(spreads), statistics.pstdev(spreads))

    def spread_expansion(
        self,
        tid: str,
        z: float = 2.0,
        lookback_samples: int = 6,
    ) -> dict | None:
        """Detect an abnormal spread widening and which side moved.

        Needs ``>= 10`` spread samples and a current spread beyond
        ``mean + z*std``; otherwise ``None``. Returns
        ``{"spread", "mean", "std", "side_pulled"}`` where ``side_pulled`` is
        ``"ask"`` when the ask pulled back (rising) — bullish pressure — or
        ``"bid"`` when the bid pulled back (falling) — bearish pressure.
        """
        hist = self.spread_history.get(tid)
        if hist is None or len(hist) < 10:
            return None
        stats = self.spread_stats(tid)
        if stats is None:
            return None
        mean, std = stats
        cur = hist[-1]
        if std <= 0 or cur["spread"] <= mean + z * std:
            return None
        baseline = hist[-lookback_samples] if len(hist) >= lookback_samples else hist[0]
        ask_move = cur["ask"] - baseline["ask"]
        bid_move = baseline["bid"] - cur["bid"]
        side_pulled = "ask" if ask_move > bid_move else "bid"
        return {
            "spread": cur["spread"],
            "mean": mean,
            "std": std,
            "side_pulled": side_pulled,
        }

    # ── Trade-burst / sweep detection ─────────────────────────────────────────

    def sweep(
        self,
        tid: str,
        window_s: float = 15,
        min_count: int = 4,
        min_notional: float = 0.0,
    ) -> dict | None:
        """Detect a one-sided trade burst on *tid* within the last ``window_s`` s.

        Returns ``{"side", "count", "notional"}`` for the dominant side (tie
        favours ``"BUY"``) or ``None`` when there are ``< min_count`` trades in
        the window, the dominant side alone has ``< min_count``, or its notional
        is below ``min_notional``.

        ``side`` is the taker/aggressor side as reported by the CLOB's
        ``last_trade_price`` event — verify against the live stream before
        trusting the direction interpretation in :meth:`trade_sweep`.
        """
        tape = self.trade_tape.get(tid)
        if tape is None:
            return None
        now = time.time()
        recent = [t for t in tape if now - t["ts"] <= window_s]
        if len(recent) < min_count:
            return None
        buys = [t for t in recent if t["side"] == "BUY"]
        sells = [t for t in recent if t["side"] == "SELL"]
        dom_side = "BUY" if len(buys) >= len(sells) else "SELL"
        dom = buys if dom_side == "BUY" else sells
        if len(dom) < min_count:
            return None
        notional = sum(t["price"] * t["size"] for t in dom)
        if notional < min_notional:
            return None
        return {"side": dom_side, "count": len(dom), "notional": notional}

    def trade_sweep(
        self,
        window_s: float = 15,
        min_count: int = 4,
        min_notional: float = 0.0,
    ) -> dict | None:
        """Combined UP/DOWN sweep → directional signal.

        Interprets each leg's :meth:`sweep`: a BUY sweep on the UP token is
        bullish (``"UP"``), a SELL sweep on the UP token bearish (``"DOWN"``),
        and the DOWN token inverts that. When both legs sweep, the larger-
        notional candidate wins. Returns ``{"direction", "side", "count",
        "notional"}`` or ``None`` when no leg sweeps or the chosen direction's
        token mid is missing/stale.
        """
        up = self.sweep(self.up_id, window_s, min_count, min_notional)
        down = self.sweep(self.down_id, window_s, min_count, min_notional)
        candidates: list[tuple[float, str, dict]] = []
        if up is not None:
            candidates.append((up["notional"], "UP" if up["side"] == "BUY" else "DOWN", up))
        if down is not None:
            candidates.append((down["notional"], "DOWN" if down["side"] == "BUY" else "UP", down))
        if not candidates:
            return None
        _, direction, res = max(candidates, key=lambda c: c[0])
        mid = self.up_mid if direction == "UP" else self.down_mid
        if mid is None:
            return None
        return {
            "direction": direction,
            "side": res["side"],
            "count": res["count"],
            "notional": res["notional"],
        }

    # ── Lifecycle ──────────────────────────────────────────────────────────────

    def start(self) -> None:
        """Start the background reconnect loop. No-op if already running."""
        if self._task and not self._task.done():
            return
        self._stop = False
        self._task = asyncio.create_task(self._run())

    def stop(self) -> None:
        """Stop the reconnect loop and cancel any in-flight tasks."""
        self._stop = True
        if self._ping_task and not self._ping_task.done():
            self._ping_task.cancel()
        if self._task and not self._task.done():
            self._task.cancel()
        self._http.close()

    # ── Internals ──────────────────────────────────────────────────────────────

    def _seed_from_rest(self) -> None:
        for tid in (self.up_id, self.down_id):
            try:
                r = self._http.get(
                    f"{self.config.clob_api}/book",
                    params={"token_id": tid},
                )
                r.raise_for_status()
                book = r.json()
                if book.get("bids"):
                    self.best_bid[tid] = float(book["bids"][-1]["price"])
                if book.get("asks"):
                    self.best_ask[tid] = float(book["asks"][-1]["price"])
                self._last_update = time.time()
            except Exception as exc:  # noqa: BLE001 — seed is best-effort
                log.warning("CLOB book seed failed for %s: %s", tid, exc)

    async def _run(self) -> None:
        import websockets

        sub = {
            "assets_ids": [self.up_id, self.down_id],
            "type": "market",
            "custom_feature_enabled": True,
        }
        while not self._stop:
            try:
                self._seed_from_rest()
                async with websockets.connect(self.config.ws_url, ping_interval=None) as ws:
                    await ws.send(json.dumps(sub))
                    self._ping_task = asyncio.create_task(self._keepalive(ws))
                    try:
                        async for raw in ws:
                            if self._stop:
                                break
                            self._handle(raw)
                    finally:
                        self._ping_task.cancel()
            except asyncio.CancelledError:
                break
            except Exception as exc:  # noqa: BLE001 — keep the loop alive
                if self._stop:
                    break
                log.warning(
                    "CLOB WS dropped (%s), reconnecting in %.1fs",
                    exc,
                    self.config.reconnect_delay,
                )
                await asyncio.sleep(self.config.reconnect_delay)

    async def _keepalive(self, ws) -> None:
        try:
            while not self._stop:
                await asyncio.sleep(self.config.ping_interval)
                await ws.send("PING")
        except asyncio.CancelledError:
            pass
        except Exception:  # noqa: BLE001 — socket gone; _run reconnects
            pass

    def _handle(self, raw: str | bytes) -> None:
        if isinstance(raw, bytes):
            try:
                raw = raw.decode()
            except UnicodeDecodeError:
                return
        if raw == "PONG":
            return
        try:
            data = json.loads(raw)
        except (json.JSONDecodeError, TypeError):
            return
        for ev in data if isinstance(data, list) else [data]:
            if not isinstance(ev, dict):
                continue
            et = ev.get("event_type")
            if et == "book":
                self._handle_book(ev)
            elif et == "price_change":
                self._handle_price_change(ev)
            elif et == "last_trade_price":
                self._handle_last_trade_price(ev)

    def _handle_book(self, ev: dict) -> None:
        tid = ev.get("asset_id")
        if tid not in self.best_bid:
            return
        if ev.get("bids"):
            self.best_bid[tid] = float(ev["bids"][-1]["price"])
        if ev.get("asks"):
            self.best_ask[tid] = float(ev["asks"][-1]["price"])
        self._last_update = time.time()
        self._record_spread(tid)

    def _handle_price_change(self, ev: dict) -> None:
        for pc in ev.get("price_changes", []):
            tid = pc.get("asset_id")
            if tid not in self.best_bid:
                continue
            if pc.get("best_bid") is not None:
                self.best_bid[tid] = float(pc["best_bid"])
            if pc.get("best_ask") is not None:
                self.best_ask[tid] = float(pc["best_ask"])
            self._last_update = time.time()
            self._record_spread(tid)

    def _handle_last_trade_price(self, ev: dict) -> None:
        tid = ev.get("asset_id")
        if tid not in self.trade_tape:
            return
        try:
            self.trade_tape[tid].append(
                {
                    "ts": time.time(),
                    "price": float(ev["price"]),
                    "size": float(ev["size"]),
                    "side": ev["side"],
                }
            )
        except (TypeError, ValueError):
            return
