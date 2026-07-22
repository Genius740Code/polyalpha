"""Paper trading dataclasses — PaperOrder and PaperPosition."""

from __future__ import annotations

import uuid
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Optional

from ..core import (
    PRICE_ROUNDING,
    DISPLAY_ROUNDING_SHARES,
    DISPLAY_ROUNDING_PRICES,
    DISPLAY_ROUNDING_PNL,
    DISPLAY_ROUNDING_PNL_PCT,
)


@dataclass
class PaperOrder:
    """A single simulated order (market or limit)."""

    id:        str
    market_id: str
    slug:      str
    side:      str           # "UP" | "DOWN"
    price:     float         # fill price, or limit threshold if pending
    amount:    float         # USDC spent (or reserved)
    shares:    float         # shares received after fee
    fee:       float         # USDC fee paid
    status:    str           # "open" | "filled" | "cancelled"
    is_limit:  bool
    filled_at: Optional[datetime] = None

    # Fee rebate tracking
    fee_type: str = "taker"  # "taker" or "maker"
    rebate_amount: float = 0.0
    rebate_rate: float = 0.0

    # Advanced order management
    stop_loss: Optional[float] = None
    take_profit: Optional[float] = None
    stop_loss_pct: Optional[float] = None
    take_profit_pct: Optional[float] = None
    trail_sl: Optional[float] = None
    trail_tp: Optional[float] = None
    trail_sl_price: Optional[float] = None
    trail_tp_price: Optional[float] = None
    oco_order_id: Optional[str] = None
    tp_sl_triggered_by: Optional[str] = None

    # Time window for order execution
    time_window_start: Optional[datetime] = None
    time_window_end: Optional[datetime] = None

    # Condition check tracking
    check_count: int = 0

    def dump(self) -> dict:
        return {
            "id":        self.id,
            "market":    self.slug,
            "side":      self.side,
            "price":     self.price,
            "amount":    self.amount,
            "shares":    self.shares,
            "fee":       self.fee,
            "status":    self.status,
            "is_limit":  self.is_limit,
            "filled_at": self.filled_at.isoformat() if self.filled_at else None,
            "fee_type":  self.fee_type,
            "rebate_amount": self.rebate_amount,
            "rebate_rate": self.rebate_rate,
            "stop_loss": self.stop_loss,
            "take_profit": self.take_profit,
            "stop_loss_pct": self.stop_loss_pct,
            "take_profit_pct": self.take_profit_pct,
            "trail_sl": self.trail_sl,
            "trail_tp": self.trail_tp,
            "trail_sl_price": self.trail_sl_price,
            "trail_tp_price": self.trail_tp_price,
            "oco_order_id": self.oco_order_id,
            "tp_sl_triggered_by": self.tp_sl_triggered_by,
            "time_window_start": self.time_window_start.isoformat() if self.time_window_start else None,
            "time_window_end": self.time_window_end.isoformat() if self.time_window_end else None,
            "check_count": self.check_count,
        }


@dataclass
class PaperPosition:
    """An aggregated position for one side of one market.

    Multiple fills on the same market+side are merged into a single position
    using a volume-weighted average price.
    """

    market_id:     str
    slug:          str
    question:      str
    side:          str           # "UP" | "DOWN"
    shares:        float
    avg_price:     float
    current_price: float         # updated live from the attached stream
    resolved:      bool                = False
    outcome:       Optional[str]       = None   # "WON" | "LOST"
    order_ids:     list[str]           = field(default_factory=list)

    # Risk management — absolute price triggers
    stop_loss:       Optional[float]      = None
    take_profit:     Optional[float]      = None
    # Risk management — percentage-based triggers (e.g., 0.05 for 5%)
    stop_loss_pct:   Optional[float]      = None
    take_profit_pct: Optional[float]      = None

    # ── Computed ───────────────────────────────────────────────────────────────

    @property
    def cost_basis(self) -> float:
        return round(self.shares * self.avg_price, PRICE_ROUNDING)

    @property
    def current_value(self) -> float:
        """Shares × 1.0 if won, 0.0 if lost, else shares × live price."""
        if self.resolved:
            return round(self.shares, PRICE_ROUNDING) if self.outcome == "WON" else 0.0
        return round(self.shares * self.current_price, PRICE_ROUNDING)

    @property
    def pnl(self) -> float:
        return round(self.current_value - self.cost_basis, PRICE_ROUNDING)

    @property
    def pnl_pct(self) -> float:
        if self.cost_basis == 0:
            return 0.0
        return round((self.pnl / self.cost_basis) * 100, DISPLAY_ROUNDING_PNL_PCT)

    def dump(self) -> dict:
        return {
            "market":        self.slug,
            "question":      self.question,
            "side":          self.side,
            "shares":        round(self.shares,        DISPLAY_ROUNDING_SHARES),
            "avg_price":     round(self.avg_price,     DISPLAY_ROUNDING_PRICES),
            "current_price": round(self.current_price, DISPLAY_ROUNDING_PRICES),
            "cost_basis":    round(self.cost_basis,    DISPLAY_ROUNDING_PRICES),
            "current_value": round(self.current_value, DISPLAY_ROUNDING_PRICES),
            "pnl":           round(self.pnl,           DISPLAY_ROUNDING_PNL),
            "pnl_pct":       round(self.pnl_pct,       DISPLAY_ROUNDING_PNL_PCT),
            "resolved":      self.resolved,
            "outcome":       self.outcome,
            "stop_loss":       self.stop_loss,
            "take_profit":     self.take_profit,
            "stop_loss_pct":   self.stop_loss_pct,
            "take_profit_pct": self.take_profit_pct,
        }


# ── Helpers ────────────────────────────────────────────────────────────────────


import math


def new_id() -> str:
    return str(uuid.uuid4())


def now() -> datetime:
    return datetime.now(timezone.utc)


def slug_label(slug: str) -> str:
    """Shorten a slug for display.  btc-updown-5m-1234 -> BTC 5m"""
    parts = slug.split("-")
    try:
        return f"{parts[0].upper()} {parts[2]}"
    except IndexError:
        return slug[:20]


def validate_market(market) -> None:
    """Validate that market object has required attributes."""
    required_attrs = ['id', 'slug', 'question', 'up_price', 'down_price']
    for attr in required_attrs:
        if not hasattr(market, attr):
            raise ValueError(f"Market object missing required attribute: {attr}")
    if not isinstance(market.up_price, (int, float)):
        raise ValueError(f"Market up_price must be numeric, got {type(market.up_price)}")
    if not isinstance(market.down_price, (int, float)):
        raise ValueError(f"Market down_price must be numeric, got {type(market.down_price)}")
    if math.isnan(market.up_price) or math.isinf(market.up_price):
        raise ValueError(f"Market up_price is invalid: {market.up_price}")
    if math.isnan(market.down_price) or math.isinf(market.down_price):
        raise ValueError(f"Market down_price is invalid: {market.down_price}")


def validate_side(side: str) -> str:
    s = side.strip().upper()
    if s not in ("UP", "DOWN"):
        raise ValueError(f"side must be 'UP' or 'DOWN', got '{side!r}'")
    return s


def validate_positive(value: float, name: str) -> float:
    if value <= 0:
        raise ValueError(f"{name} must be > 0, got {value}")
    return value


def validate_price(price: float, name: str = "price") -> float:
    """Validate that price is within valid range for prediction markets (0-1)."""
    if not isinstance(price, (int, float)):
        raise ValueError(f"{name} must be numeric, got {type(price)}")
    if math.isnan(price) or math.isinf(price):
        raise ValueError(f"{name} is invalid: {price}")
    if price < 0 or price > 1:
        raise ValueError(f"{name} must be between 0 and 1, got {price}")
    return price
