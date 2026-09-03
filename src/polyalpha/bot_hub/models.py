"""bot_hub.models — shared data models for BotHub.

Extracted from the monolithic ``bot_hub.py`` (2662 lines) to keep
single-responsibility modules. Contains:

* ``PriceSnapshot`` — current UP/DOWN prices
* ``MACDResult``, ``BBResult``, ``DonchianResult`` — TA namedtuples
* ``_RegisteredStrategy`` / ``Variant`` — registered strategy dataclass
"""

from __future__ import annotations

from collections import namedtuple
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Callable, Optional

# ── Price Snapshot ─────────────────────────────────────────────────────────────

@dataclass
class PriceSnapshot:
    """Current UP/DOWN prices from the shared stream."""

    up: float
    down: float


# ── TA Result tuples ─────────────────────────────────────────────────────────

MACDResult = namedtuple("MACDResult", ["macd", "signal", "histogram"])
BBResult = namedtuple("BBResult", ["upper", "mid", "lower"])
DonchianResult = namedtuple("DonchianResult", ["upper", "mid", "lower"])


# ── Registered strategy ──────────────────────────────────────────────────────

@dataclass
class _RegisteredStrategy:
    """A registered strategy with optional comparison metadata.

    Every strategy (whether registered via ``strategy()`` or ``variant()``)
    is stored as this type.  Strategies with non-empty ``params`` are
    considered "variants" for comparison purposes.
    """

    name: str
    fn: Callable[[object], None]
    balance: float
    params: dict = field(default_factory=dict)
    id: str = ""
    created_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
    run_count: int = 0
    paper: Optional[object] = None  # lazily built on first cycle (or RealTradingEngine when engine=real)
    _engine: Optional[object] = None  # unified engine ref (paper or real)
    ctx: Optional[object] = None

    def __post_init__(self) -> None:
        if not self.id:
            self.id = self.name


Variant = _RegisteredStrategy  # backward compat alias
