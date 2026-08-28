"""
polyalpha.history — Chainlink candle history with configurable retention.

User chooses how much to keep, e.g.:

    ChainlinkHistoryConfig(warmup={"1m":10, "1h":50, "1s":20})

Means: keep 10 closed 1-min candles, 50 1-h candles, 20 1-s candles.
Unused timeframes are deleted automatically (prune_unused).

Storage: SQLite WAL, WITHOUT ROWID, integer start_ts, REAL OHLC.
Best for incremental 1-s tick → candle with concurrent reads.

Exports
-------
- Candle
- ChainlinkHistoryConfig
- ChainlinkRecorder
- ChainlinkHistoryView
- Store
- Registry helpers (get_or_create, release)
"""

from __future__ import annotations

from .candle import Candle, HISTORY_TIMEFRAME_SECONDS, floor_ts, normalize_timeframe, timeframe_seconds
from .config import ChainlinkHistoryConfig
from .recorder import ChainlinkRecorder
from .store import Store
from .view import ChainlinkHistoryView
from . import registry

__all__ = [
    "Candle",
    "HISTORY_TIMEFRAME_SECONDS",
    "floor_ts",
    "normalize_timeframe",
    "timeframe_seconds",
    "ChainlinkHistoryConfig",
    "ChainlinkRecorder",
    "ChainlinkHistoryView",
    "Store",
    "registry",
]
