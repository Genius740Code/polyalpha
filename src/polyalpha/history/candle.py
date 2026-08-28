"""
Candle utilities for Chainlink history.

Defines the Candle dataclass and helpers to floor timestamps to
timeframe buckets. Storage is OHLC + count per (asset, timeframe, start_ts).

Best format: SQLite with WAL, WITHOUT ROWID, integer start_ts,
REAL OHLC, integer count. See store.py for DB details.
"""

from __future__ import annotations

import time
from dataclasses import dataclass


# Supported timeframe -> seconds. Extended beyond core TIMEFRAME_SECONDS
# to allow fine-grained history (1s) and coarse (1d/1w) for TA.
HISTORY_TIMEFRAME_SECONDS: dict[str, int] = {
    "1s": 1,
    "5s": 5,
    "15s": 15,
    "30s": 30,
    "1m": 60,
    "5m": 300,
    "15m": 900,
    "1h": 3600,
    "4h": 14400,
    "1d": 86400,
    "24h": 86400,
    "1w": 604800,
}

# Alias map: allow common names
_TF_ALIASES: dict[str, str] = {
    "24h": "1d",
}


def normalize_timeframe(tf: str) -> str:
    """Normalize timeframe string (strip, lower, alias)."""
    tf = tf.strip().lower()
    return _TF_ALIASES.get(tf, tf)


def timeframe_seconds(tf: str) -> int:
    """Return seconds for a timeframe string, or raise ValueError."""
    tf = normalize_timeframe(tf)
    if tf not in HISTORY_TIMEFRAME_SECONDS:
        raise ValueError(
            f"Unsupported timeframe {tf!r}. Supported: {sorted(HISTORY_TIMEFRAME_SECONDS)}"
        )
    return HISTORY_TIMEFRAME_SECONDS[tf]


def floor_ts(ts: float, tf: str) -> int:
    """Floor epoch seconds to the start of the timeframe bucket."""
    secs = timeframe_seconds(tf)
    return int(ts // secs) * secs


@dataclass
class Candle:
    """OHLC candle for one (asset, timeframe) bucket."""

    asset: str
    timeframe: str
    start_ts: int
    open: float
    high: float
    low: float
    close: float
    count: int = 1

    def __post_init__(self) -> None:
        self.asset = self.asset.upper()
        self.timeframe = normalize_timeframe(self.timeframe)

    def update(self, price: float) -> None:
        """Update candle with a new tick price."""
        if price > self.high:
            self.high = price
        if price < self.low:
            self.low = price
        self.close = price
        self.count += 1

    def to_tuple(self) -> tuple:
        """Tuple for SQL INSERT."""
        return (
            self.asset,
            self.timeframe,
            self.start_ts,
            self.open,
            self.high,
            self.low,
            self.close,
            self.count,
        )

    @classmethod
    def from_row(cls, row: tuple | dict) -> "Candle":
        """Create from DB row (asset, timeframe, start_ts, open, high, low, close, count)."""
        if isinstance(row, dict):
            return cls(
                asset=row["asset"],
                timeframe=row["timeframe"],
                start_ts=int(row["start_ts"]),
                open=float(row["open"]),
                high=float(row["high"]),
                low=float(row["low"]),
                close=float(row["close"]),
                count=int(row["count"]),
            )
        # tuple order: asset, timeframe, start_ts, open, high, low, close, count
        return cls(
            asset=row[0],
            timeframe=row[1],
            start_ts=int(row[2]),
            open=float(row[3]),
            high=float(row[4]),
            low=float(row[5]),
            close=float(row[6]),
            count=int(row[7]),
        )
