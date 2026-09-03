"""
polyalpha.bot_hub — multi-strategy hub package.

This package is the split refactor of the former monolithic
``src/polyalpha/bot_hub.py`` (2662 lines) into focused single-responsibility
modules:

* ``models``      — PriceSnapshot, MACDResult, BBResult, DonchianResult, _RegisteredStrategy
* ``indicators``  — IndicatorAccessor, _log_indicators
* ``binance``     — BinanceAccessor (≈560 lines)
* ``orderbook``   — OrderBookAccessor
* ``context``     — StrategyContext (≈580 lines)
* ``history``     — _resolve_chainlink_history helper
* ``hub``         — BotHub (≈1100 lines, lifecycle + streaming + comparison)

All public symbols are re-exported here so existing imports
``from polyalpha.bot_hub import BotHub`` continue to work, and
``import polyalpha.bot_hub as m; m.BotHub`` is unchanged.

New code may also import directly from submodules, e.g.
``from polyalpha.bot_hub.context import StrategyContext``.
"""

from __future__ import annotations

from .binance import BinanceAccessor
from .context import StrategyContext
from .history import _resolve_chainlink_history
from .hub import BotHub
from .indicators import IndicatorAccessor, _log_indicators
from .models import (
    BBResult,
    DonchianResult,
    MACDResult,
    PriceSnapshot,
    Variant,
    _RegisteredStrategy,
)
from .orderbook import OrderBookAccessor

__all__ = [
    "BotHub",
    "StrategyContext",
    "IndicatorAccessor",
    "BinanceAccessor",
    "OrderBookAccessor",
    "PriceSnapshot",
    "MACDResult",
    "BBResult",
    "DonchianResult",
    "Variant",
    "_RegisteredStrategy",
    "_resolve_chainlink_history",
    "_log_indicators",
]
