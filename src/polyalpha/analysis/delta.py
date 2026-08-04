"""
Delta change (rate of change) indicators.

Measures the velocity and acceleration of price movements,
providing momentum signals for trading strategies.

Usage
-----
    from polyalpha.analysis import DeltaCalculator

    delta = DeltaCalculator(data)
    simple_delta = delta.delta()
    period_delta = delta.delta_period(period=5)
    acceleration = delta.delta_acceleration()
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

import pandas as pd

from ..core.constants import BINANCE_WS_AGGTRADE

try:
    import pandas_ta as ta
    PANDAS_TA_AVAILABLE = True
except ImportError:
    from polyalpha.analysis import _native_ta as ta
    PANDAS_TA_AVAILABLE = False

log = logging.getLogger(__name__)


class DeltaCalculator:
    """
    Calculate delta change (rate of change) indicators.

    Parameters
    ----------
    data : pd.DataFrame
        OHLCV data with columns: timestamp, open, high, low, close, volume.

    Example
    -------
    >>> delta = DeltaCalculator(data)
    >>> simple = delta.delta()
    >>> pct_change = delta.delta_percent()
    """

    def __init__(self, data: pd.DataFrame):
        """Initialize delta calculator."""
        self.data = data.copy()
        self._validate_data()
        self._log = logging.getLogger(__name__)
        self._cache: dict[str, pd.Series] = {}

    def _get_cache_key(self, indicator: str, **kwargs) -> str:
        """Generate cache key for indicator with parameters."""
        params_str = "_".join(f"{k}_{v}" for k, v in sorted(kwargs.items()))
        return f"{indicator}_{params_str}" if params_str else indicator

    def clear_cache(self) -> None:
        """Clear the indicator cache."""
        self._cache.clear()

    def _validate_data(self) -> None:
        """Validate input data."""
        required_columns = ["open", "high", "low", "close", "volume"]
        missing = [col for col in required_columns if col not in self.data.columns]

        if missing:
            raise ValueError(
                f"Data missing required columns: {missing}. "
                f"Required: {required_columns}"
            )

    # ── Delta Methods ───────────────────────────────────────────────────────

    def delta(self, price: str = "close") -> pd.Series:
        """
        Simple delta: price change between consecutive periods.

        Parameters
        ----------
        price : str
            Price column to use: "open" | "high" | "low" | "close" (default: "close").

        Returns
        -------
        pd.Series
            Delta values (current - previous).
        """
        cache_key = self._get_cache_key("delta", price=price)
        if cache_key in self._cache:
            return self._cache[cache_key]

        delta = self.data[price].diff()
        series = delta.rename(f"Delta_{price}")
        self._cache[cache_key] = series
        return series

    def delta_period(self, period: int = 1, price: str = "close") -> pd.Series:
        """
        Delta over N periods: price change over specified lookback.

        Parameters
        ----------
        period : int
            Number of periods to look back (default: 1).
        price : str
            Price column to use: "open" | "high" | "low" | "close" (default: "close").

        Returns
        -------
        pd.Series
            Delta values (current - N periods ago).
        """
        if period <= 0:
            raise ValueError("period must be positive")

        cache_key = self._get_cache_key("delta_period", period=period, price=price)
        if cache_key in self._cache:
            return self._cache[cache_key]

        delta = self.data[price].diff(periods=period)
        series = delta.rename(f"Delta_{price}_{period}")
        self._cache[cache_key] = series
        return series

    def delta_percent(self, price: str = "close") -> pd.Series:
        """
        Delta percentage: percentage change between consecutive periods.

        Parameters
        ----------
        price : str
            Price column to use: "open" | "high" | "low" | "close" (default: "close").

        Returns
        -------
        pd.Series
            Percentage change values ((current - previous) / previous * 100).
        """
        cache_key = self._get_cache_key("delta_percent", price=price)
        if cache_key in self._cache:
            return self._cache[cache_key]

        delta_pct = self.data[price].pct_change() * 100
        series = delta_pct.rename(f"DeltaPct_{price}")
        self._cache[cache_key] = series
        return series

    def delta_percent_period(self, period: int = 1, price: str = "close") -> pd.Series:
        """
        Delta percentage over N periods: percentage change over specified lookback.

        Parameters
        ----------
        period : int
            Number of periods to look back (default: 1).
        price : str
            Price column to use: "open" | "high" | "low" | "close" (default: "close").

        Returns
        -------
        pd.Series
            Percentage change values over N periods.
        """
        if period <= 0:
            raise ValueError("period must be positive")

        cache_key = self._get_cache_key("delta_percent_period", period=period, price=price)
        if cache_key in self._cache:
            return self._cache[cache_key]

        delta_pct = self.data[price].pct_change(periods=period) * 100
        series = delta_pct.rename(f"DeltaPct_{price}_{period}")
        self._cache[cache_key] = series
        return series

    def delta_acceleration(self, period: int = 1, price: str = "close") -> pd.Series:
        """
        Delta acceleration: rate of change of delta (second derivative).

        Measures how quickly the rate of change itself is changing.
        Positive acceleration = momentum is increasing, negative = momentum is decreasing.

        Parameters
        ----------
        period : int
            Period for delta calculation (default: 1).
        price : str
            Price column to use: "open" | "high" | "low" | "close" (default: "close").

        Returns
        -------
        pd.Series
            Acceleration values (change in delta).
        """
        if period <= 0:
            raise ValueError("period must be positive")

        cache_key = self._get_cache_key("delta_acceleration", period=period, price=price)
        if cache_key in self._cache:
            return self._cache[cache_key]

        delta = self.delta_period(period, price)
        acceleration = delta.diff()
        series = acceleration.rename(f"DeltaAcc_{price}_{period}")
        self._cache[cache_key] = series
        return series

    def delta_smoothed(
        self,
        period: int = 1,
        smooth_period: int = 3,
        price: str = "close"
    ) -> pd.Series:
        """
        Smoothed delta: delta with smoothing to reduce noise.

        Parameters
        ----------
        period : int
            Delta period (default: 1).
        smooth_period : int
            SMA smoothing period (default: 3).
        price : str
            Price column to use: "open" | "high" | "low" | "close" (default: "close").

        Returns
        -------
        pd.Series
            Smoothed delta values.
        """
        if period <= 0 or smooth_period <= 0:
            raise ValueError("periods must be positive")

        cache_key = self._get_cache_key("delta_smoothed", period=period, smooth_period=smooth_period, price=price)
        if cache_key in self._cache:
            return self._cache[cache_key]

        delta = self.delta_period(period, price)
        smoothed = ta.sma(delta, length=smooth_period)
        series = smoothed.rename(f"DeltaSmooth_{price}_{period}_{smooth_period}")
        self._cache[cache_key] = series
        return series

    # ── Helpers ─────────────────────────────────────────────────────────────

    def get_latest_value(self, series: pd.Series) -> Optional[float]:
        """
        Get the latest non-NaN value from a series.

        Parameters
        ----------
        series : pd.Series
            Delta series.

        Returns
        -------
        float or None
            Latest value or None if all NaN.
        """
        if series.empty:
            return None

        valid_values = series.dropna()
        if valid_values.empty:
            return None

        return valid_values.iloc[-1]


@dataclass
class CVDTrackerConfig:
    """Configuration for :class:`CVDTracker`.

    Parameters
    ----------
    ws_url            : Binance aggTrade WebSocket endpoint.
    ping_interval     : Seconds between WebSocket-level pings (the websockets
                        library drives these; Binance drops idle sockets).
    reconnect_delay   : Fixed delay between reconnect attempts on WS drop.
    snapshot_interval : Seconds between cumulative-volume-delta snapshots.
    sample_max_age    : Seconds a signed trade is kept before being pruned.
    history_maxlen    : Max number of ``cvd30``/``cvd60`` snapshots to retain.
    """

    ws_url: str = BINANCE_WS_AGGTRADE
    ping_interval: float = 20.0
    reconnect_delay: float = 3.0
    snapshot_interval: float = 10.0
    sample_max_age: float = 180.0
    history_maxlen: int = 200


class CVDTracker:
    """Cumulative volume delta for Binance BTC spot, streamed from aggTrades.

    Each aggregate trade is signed by aggressor side: ``m=false`` (buyer is the
    taker) contributes ``+qty``; ``m=true`` (seller is the taker) contributes
    ``-qty``. Signed quantities accumulate into a rolling ``samples`` deque and
    are snapshotted every ``snapshot_interval`` seconds into ``history`` as
    ``{"ts", "cvd30", "cvd60"}``, which drives the ``z`` / ``decelerating`` /
    ``velocity`` / ``acceleration`` signals.

    Starts its own connection and reconnects forever on drop.

    Usage
    -----
        cvd = CVDTracker()
        cvd.start()

        # Read the latest signals anytime
        if cvd.z() > 2.0 and not cvd.decelerating():
            ...

        cvd.stop()
    """

    def __init__(self, config: CVDTrackerConfig | None = None):
        self.config = config or CVDTrackerConfig()
        self.samples: deque[tuple[float, float]] = deque()
        self.history: deque[dict[str, float]] = deque(maxlen=self.config.history_maxlen)
        self._stop = False
        self._task: asyncio.Task | None = None
        self._snapshot_task: asyncio.Task | None = None

    # ── Signals ──────────────────────────────────────────────────────────────

    def cvd(self, window_s: float = 60) -> float:
        """Sum of signed trade qty whose ``ts >= now - window_s``."""
        self._prune()
        cutoff = time.time() - window_s
        return sum(signed for ts, signed in self.samples if ts >= cutoff)

    def z(self, window_s: float = 60) -> float | None:
        """Current CVD z-score against the snapshot history.

        Uses the ``cvd60`` history when ``window_s >= 60`` else ``cvd30``.
        Needs ``>= 5`` snapshots; ``None`` when insufficient history or the
        history has zero variance.
        """
        key = "cvd60" if window_s >= 60 else "cvd30"
        if len(self.history) < 5:
            return None
        values = [h[key] for h in self.history]
        mean = statistics.mean(values)
        std = statistics.pstdev(values)
        if std == 0:
            return None
        return (self.cvd(window_s) - mean) / std

    def decelerating(self) -> bool | None:
        """True when the last two ``cvd30`` snapshots share a sign and the
        magnitude is shrinking (momentum exhausting). ``None`` with ``< 2``
        snapshots.
        """
        if len(self.history) < 2:
            return None
        last = self.history[-1]["cvd30"]
        prev = self.history[-2]["cvd30"]
        same_sign = (last > 0 and prev > 0) or (last < 0 and prev < 0)
        return same_sign and abs(last) < abs(prev)

    def velocity(self, key: str = "cvd60") -> float | None:
        """Change in ``key`` between the last two snapshots. ``None`` with
        ``< 2`` snapshots.
        """
        if len(self.history) < 2:
            return None
        return self.history[-1][key] - self.history[-2][key]

    def acceleration(self, key: str = "cvd60") -> float | None:
        """Rate of change of ``key``'s velocity (second difference).
        ``None`` with ``< 3`` snapshots.
        """
        if len(self.history) < 3:
            return None
        d1 = self.history[-1][key] - self.history[-2][key]
        d2 = self.history[-2][key] - self.history[-3][key]
        return d1 - d2

    # ── Lifecycle ─────────────────────────────────────────────────────────────

    def start(self) -> None:
        """Start the background reconnect loop. No-op if already running."""
        if self._task and not self._task.done():
            return
        self._stop = False
        self._task = asyncio.create_task(self._run())

    def stop(self) -> None:
        """Stop the reconnect loop and cancel any in-flight tasks."""
        self._stop = True
        if self._snapshot_task and not self._snapshot_task.done():
            self._snapshot_task.cancel()
        if self._task and not self._task.done():
            self._task.cancel()

    # ── Internals ─────────────────────────────────────────────────────────────

    def _prune(self) -> None:
        cutoff = time.time() - self.config.sample_max_age
        while self.samples and self.samples[0][0] < cutoff:
            self.samples.popleft()

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
        try:
            qty = float(data["q"])
        except (TypeError, ValueError, KeyError):
            return
        signed = -qty if data.get("m") is True else qty
        self.samples.append((time.time(), signed))

    async def _run(self) -> None:
        import websockets

        while not self._stop:
            try:
                async with websockets.connect(
                    self.config.ws_url,
                    ping_interval=self.config.ping_interval,
                    ping_timeout=5,
                ) as ws:
                    self._snapshot_task = asyncio.create_task(self._snapshot_loop())
                    try:
                        async for raw in ws:
                            if self._stop:
                                break
                            self._handle(raw)
                    finally:
                        self._snapshot_task.cancel()
            except asyncio.CancelledError:
                break
            except Exception as exc:  # noqa: BLE001 — keep the loop alive
                if self._stop:
                    break
                log.warning(
                    "Binance aggTrade WS dropped (%s), reconnecting in %.1fs",
                    exc,
                    self.config.reconnect_delay,
                )
                await asyncio.sleep(self.config.reconnect_delay)

    async def _snapshot_loop(self) -> None:
        try:
            while not self._stop:
                await asyncio.sleep(self.config.snapshot_interval)
                now = time.time()
                self.history.append(
                    {"ts": now, "cvd30": self.cvd(30), "cvd60": self.cvd(60)}
                )
        except asyncio.CancelledError:
            pass
