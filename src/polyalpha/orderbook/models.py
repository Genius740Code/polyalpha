"""
Typed order book data models for Polymarket CLOB.

Snapshots are immutable value objects parsed from REST or WebSocket payloads.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum
from typing import Any

from ..core.constants import PRICE_ROUNDING


def _parse_float(value: Any, default: float = 0.0) -> float:
    try:
        return float(value)
    except (TypeError, ValueError):
        return default


def _parse_timestamp(value: Any) -> datetime:
    if isinstance(value, datetime):
        return value if value.tzinfo else value.replace(tzinfo=timezone.utc)
    if isinstance(value, (int, float)):
        ts = float(value)
        if ts > 1e12:
            ts /= 1000.0
        return datetime.fromtimestamp(ts, tz=timezone.utc)
    if isinstance(value, str) and value:
        text = value.replace("Z", "+00:00")
        try:
            return datetime.fromisoformat(text)
        except ValueError:
            pass
    return datetime.now(timezone.utc)


class BookSide(str, Enum):
    BUY = "buy"
    SELL = "sell"


class OrderStatus(str, Enum):
    PENDING = "pending"
    FILLED = "filled"
    PARTIALLY_FILLED = "partially_filled"
    CANCELLED = "cancelled"
    REJECTED = "rejected"


class OrderType(str, Enum):
    LIMIT = "limit"
    MARKET = "market"
    STOP_LIMIT = "stop_limit"
    STOP_MARKET = "stop_market"


@dataclass(frozen=True)
class BookLevel:
    """Single price level in the order book."""

    price: float
    size: float

    @property
    def notional(self) -> float:
        return self.price * self.size


def _parse_levels(raw_levels: list[Any] | None) -> tuple[BookLevel, ...]:
    levels: list[BookLevel] = []
    for item in raw_levels or []:
        if not isinstance(item, dict):
            continue
        price = _parse_float(item.get("price"))
        size = _parse_float(item.get("size", item.get("volume", item.get("quantity"))))
        if price > 0 and size > 0:
            levels.append(BookLevel(price=round(price, PRICE_ROUNDING), size=size))
    return tuple(levels)


@dataclass
class Order:
    """Strategy or simulation order."""

    id: str
    user_id: str
    side: BookSide
    order_type: OrderType
    price: float
    quantity: float
    filled_quantity: float = 0.0
    status: OrderStatus = OrderStatus.PENDING
    timestamp: datetime | None = None
    stop_price: float | None = None
    time_in_force: str = "GTC"

    @property
    def remaining_quantity(self) -> float:
        return self.quantity - self.filled_quantity

    @property
    def is_filled(self) -> bool:
        return self.remaining_quantity <= 0

    @property
    def fill_percentage(self) -> float:
        if self.quantity == 0:
            return 0.0
        return (self.filled_quantity / self.quantity) * 100


@dataclass(frozen=True)
class Trade:
    """Executed trade record."""

    id: str
    order_id: str
    price: float
    quantity: float
    timestamp: datetime
    taker_order_id: str
    maker_order_id: str
    token_id: str = ""
    side: BookSide | None = None


@dataclass(frozen=True)
class FillEstimate:
    """Result of walking the book for a market order."""

    side: BookSide
    requested_size: float
    filled_size: float
    average_price: float
    total_cost: float
    levels_used: tuple[tuple[float, float], ...]
    fully_filled: bool

    @property
    def slippage(self) -> float:
        if not self.levels_used:
            return 0.0
        top_price = self.levels_used[0][0]
        if top_price <= 0:
            return 0.0
        return abs(self.average_price - top_price)


@dataclass
class OrderBookSnapshot:
    """
    Immutable order book snapshot for one CLOB token.

    Bids are sorted highest-first; asks lowest-first (Polymarket convention).
    """

    token_id: str
    market_id: str
    bids: tuple[BookLevel, ...]
    asks: tuple[BookLevel, ...]
    timestamp: datetime
    tick_size: float = 0.01
    min_order_size: float = 1.0
    neg_risk: bool = False
    hash: str = ""
    sequence: int = 0
    last_trade_price: float = 0.0
    last_trade_size: float = 0.0

    @classmethod
    def from_clob_response(cls, data: dict[str, Any]) -> OrderBookSnapshot:
        bids = _parse_levels(data.get("bids"))
        asks = _parse_levels(data.get("asks"))
        bids = tuple(sorted(bids, key=lambda level: level.price, reverse=True))
        asks = tuple(sorted(asks, key=lambda level: level.price))
        return cls(
            token_id=str(data.get("asset_id", data.get("token_id", ""))),
            market_id=str(data.get("market", "")),
            bids=bids,
            asks=asks,
            timestamp=_parse_timestamp(data.get("timestamp")),
            tick_size=_parse_float(data.get("tick_size"), 0.01),
            min_order_size=_parse_float(data.get("min_order_size"), 1.0),
            neg_risk=bool(data.get("neg_risk", False)),
            hash=str(data.get("hash", "")),
        )

    @classmethod
    def from_ws_message(cls, msg: dict[str, Any], sequence: int = 0) -> OrderBookSnapshot:
        snapshot = cls.from_clob_response(msg)
        return OrderBookSnapshot(
            token_id=snapshot.token_id,
            market_id=snapshot.market_id,
            bids=snapshot.bids,
            asks=snapshot.asks,
            timestamp=snapshot.timestamp,
            tick_size=snapshot.tick_size,
            min_order_size=snapshot.min_order_size,
            neg_risk=snapshot.neg_risk,
            hash=snapshot.hash,
            sequence=sequence,
            last_trade_price=_parse_float(msg.get("last_trade_price")),
            last_trade_size=_parse_float(msg.get("size", msg.get("last_trade_size"))),
        )

    @property
    def best_bid(self) -> float:
        return self.bids[0].price if self.bids else 0.0

    @property
    def best_ask(self) -> float:
        return self.asks[0].price if self.asks else 0.0

    @property
    def best_bid_size(self) -> float:
        return self.bids[0].size if self.bids else 0.0

    @property
    def best_ask_size(self) -> float:
        return self.asks[0].size if self.asks else 0.0

    @property
    def spread(self) -> float:
        if self.best_bid <= 0 or self.best_ask <= 0:
            return 0.0
        return round(self.best_ask - self.best_bid, PRICE_ROUNDING)

    @property
    def spread_percentage(self) -> float:
        if self.best_bid <= 0:
            return 0.0
        return (self.spread / self.best_bid) * 100

    @property
    def mid_price(self) -> float:
        if self.best_bid > 0 and self.best_ask > 0:
            return round((self.best_bid + self.best_ask) / 2, PRICE_ROUNDING)
        if self.last_trade_price > 0:
            return round(self.last_trade_price, PRICE_ROUNDING)
        return 0.0

    @property
    def total_bid_volume(self) -> float:
        return sum(level.size for level in self.bids)

    @property
    def total_ask_volume(self) -> float:
        return sum(level.size for level in self.asks)

    @property
    def order_book_imbalance(self) -> float:
        total = self.total_bid_volume + self.total_ask_volume
        if total <= 0:
            return 0.0
        return (self.total_bid_volume - self.total_ask_volume) / total

    def get_depth(self, levels: int = 10) -> dict[str, Any]:
        """Return top N bid/ask levels with spread and mid price."""
        return {
            "token_id": self.token_id,
            "bids": [
                {"price": level.price, "size": level.size}
                for level in self.bids[:levels]
            ],
            "asks": [
                {"price": level.price, "size": level.size}
                for level in self.asks[:levels]
            ],
            "spread": self.spread,
            "mid_price": self.mid_price,
            "imbalance": self.order_book_imbalance,
            "timestamp": self.timestamp.isoformat(),
            "sequence": self.sequence,
        }

    def dump(self) -> dict[str, Any]:
        return self.get_depth(levels=max(len(self.bids), len(self.asks)))


@dataclass
class MarketOrderBook:
    """UP and DOWN token books for a Polymarket market."""

    market_slug: str
    up: OrderBookSnapshot | None = None
    down: OrderBookSnapshot | None = None
    trades: list[Trade] = field(default_factory=list)

    @property
    def up_mid(self) -> float:
        return self.up.mid_price if self.up else 0.0

    @property
    def down_mid(self) -> float:
        return self.down.mid_price if self.down else 0.0

    def get_depth(self, levels: int = 10) -> dict[str, Any]:
        return {
            "market_slug": self.market_slug,
            "up": self.up.get_depth(levels) if self.up else None,
            "down": self.down.get_depth(levels) if self.down else None,
        }


@dataclass
class Position:
    symbol: str
    quantity: float
    average_price: float
    unrealized_pnl: float = 0.0
    realized_pnl: float = 0.0

    @property
    def market_value(self) -> float:
        return self.quantity * self.average_price

    @property
    def is_long(self) -> bool:
        return self.quantity > 0

    @property
    def is_short(self) -> bool:
        return self.quantity < 0


@dataclass
class Portfolio:
    user_id: str
    positions: dict[str, Position]
    cash_balance: float
    total_value: float

    @property
    def total_pnl(self) -> float:
        return sum(pos.realized_pnl + pos.unrealized_pnl for pos in self.positions.values())

    def get_position(self, symbol: str) -> Position:
        return self.positions.get(symbol, Position(symbol, 0, 0.0))
