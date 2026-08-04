"""
Binance futures liquidation tracker.

Streams the USDT-M ``btcusdt@forceOrder`` feed and detects one-sided
liquidation clusters — bursts of SELL or BUY liquidations that signal
forced deleveraging pressure.

Semantics: a SELL liquidation closes a long (bearish pressure); a BUY
liquidation closes a short (bullish pressure).

Usage
-----
    from polyalpha.analysis import LiquidationTracker

    liq = LiquidationTracker()
    liq.start()

    # Any time: is a cluster forming?
    cluster = liq.cluster()
    if cluster:
        # {"direction": "DOWN", "notional": ..., "count": ...}
        ...

    liq.stop()
"""

from __future__ import annotations

import asyncio
import json
import logging
import statistics
import time
from collections import deque
from dataclasses import dataclass
from typing import Optional

from ..core.constants import BINANCE_WS_FORCE_ORDER

log = logging.getLogger(__name__)


@dataclass
class LiquidationTrackerConfig:
    """Configuration for :class:`LiquidationTracker`.

    Parameters
    ----------
    ws_url            : Binance futures forceOrder WebSocket endpoint.
    ping_interval     : Seconds between WebSocket-level pings (the websockets
                        library drives these; Binance drops idle sockets).
    reconnect_delay   : Fixed delay between reconnect attempts on WS drop.
    events_maxlen     : Max number of liquidation events retained.
    """

    ws_url: str = BINANCE_WS_FORCE_ORDER
    ping_interval: float = 20.0
    reconnect_delay: float = 3.0
    events_maxlen: int = 500


class LiquidationTracker:
    """One-sided liquidation-cluster detection for Binance BTC futures.

    Each force-order event ``{"o": {"S": "SELL"|"BUY", "q": qty, "p": price}}``
    is appended as ``(ts, side, notional=qty*price)`` to a rolling
    ``events`` deque. :meth:`cluster` then checks whether a single side is
    spiking relative to the hourly baseline.

    Starts its own connection and reconnects forever on drop.

    Usage
    -----
        liq = LiquidationTracker()
        liq.start()

        if (c := liq.cluster()) is not None:
            print(c["direction"], c["notional"], c["count"])

        liq.stop()
    """

    def __init__(self, config: LiquidationTrackerConfig | None = None):
        self.config = config or LiquidationTrackerConfig()
        self.events: deque[tuple[float, str, float]] = deque(maxlen=self.config.events_maxlen)
        self._stop = False
        self._task: asyncio.Task | None = None

    # ── Signals ──────────────────────────────────────────────────────────────

    def cluster(
        self,
        window_s: float = 20,
        min_count: int = 3,
        notional_mult: float = 2.0,
    ) -> Optional[dict]:
        """Detect a one-sided liquidation cluster in the last ``window_s``.

        A cluster is ``min_count``+ liquidations on the same side within the
        window whose total notional is at least ``notional_mult`` x the
        hourly average notional.

        Parameters
        ----------
        window_s      : Cluster lookback window in seconds (default 20).
        min_count     : Minimum same-side liquidations required (default 3).
        notional_mult : Multiplier against the hourly average before a
                        cluster is considered significant (default 2.0).

        Returns
        -------
        dict | None
            ``{"direction": "DOWN"|"UP", "notional": float, "count": int}``,
            or ``None`` when there is no cluster. ``SELL`` liquidations close
            longs → ``DOWN``; ``BUY`` liquidations close shorts → ``UP``.
        """
        now = time.time()
        recent = [e for e in self.events if now - e[0] <= window_s]
        if len(recent) < min_count:
            return None

        side = recent[-1][1]
        same = [e for e in recent if e[1] == side]
        if len(same) < min_count:
            return None

        notional = sum(e[2] for e in same)

        hourly = [e for e in self.events if now - e[0] <= 3600]
        if hourly:
            avg = statistics.mean(e[2] for e in hourly)
            if notional < avg * notional_mult:
                return None

        return {
            "direction": "DOWN" if side == "SELL" else "UP",
            "notional": notional,
            "count": len(same),
        }

    # ── Lifecycle ─────────────────────────────────────────────────────────────

    def start(self) -> None:
        """Start the background reconnect loop. No-op if already running."""
        if self._task and not self._task.done():
            return
        self._stop = False
        self._task = asyncio.create_task(self._run())

    def stop(self) -> None:
        """Stop the reconnect loop and cancel any in-flight task."""
        self._stop = True
        if self._task and not self._task.done():
            self._task.cancel()

    # ── Internals ─────────────────────────────────────────────────────────────

    def _handle(self, raw: str | bytes) -> None:
        if isinstance(raw, bytes):
            try:
                raw = raw.decode()
            except UnicodeDecodeError:
                return
        try:
            data = json.loads(raw)
        except (json.JSONDecodeError, TypeError):
            return
        if not isinstance(data, dict):
            return
        o = data.get("o")
        if not isinstance(o, dict):
            return
        try:
            side = o["S"]
            qty = float(o["q"])
            price = float(o["p"])
        except (TypeError, ValueError, KeyError):
            return
        self.events.append((time.time(), side, qty * price))

    async def _run(self) -> None:
        import websockets

        while not self._stop:
            try:
                async with websockets.connect(
                    self.config.ws_url,
                    ping_interval=self.config.ping_interval,
                    ping_timeout=5,
                ) as ws:
                    async for raw in ws:
                        if self._stop:
                            break
                        self._handle(raw)
            except asyncio.CancelledError:
                break
            except Exception as exc:  # noqa: BLE001 — keep the loop alive
                if self._stop:
                    break
                log.warning(
                    "Binance forceOrder WS dropped (%s), reconnecting in %.1fs",
                    exc,
                    self.config.reconnect_delay,
                )
                await asyncio.sleep(self.config.reconnect_delay)
