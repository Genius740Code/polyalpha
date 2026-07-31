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
import time
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

    def _handle_book(self, ev: dict) -> None:
        tid = ev.get("asset_id")
        if tid not in self.best_bid:
            return
        if ev.get("bids"):
            self.best_bid[tid] = float(ev["bids"][-1]["price"])
        if ev.get("asks"):
            self.best_ask[tid] = float(ev["asks"][-1]["price"])
        self._last_update = time.time()

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
