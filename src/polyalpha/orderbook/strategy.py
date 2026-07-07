"""
Strategy framework for order-book-driven Polymarket trading.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from datetime import datetime, timezone
from typing import Any
from uuid import uuid4

from .models import BookSide, MarketOrderBook, Order, OrderBookSnapshot, OrderType, Trade


class Strategy(ABC):
    """Base class for order book strategies."""

    def __init__(self, name: str, parameters: dict[str, Any] | None = None):
        self.name = name
        self.parameters = parameters or {}
        self.positions: dict[str, float] = {}
        self.performance_metrics: dict[str, Any] = {}
        self.is_active = False

    @abstractmethod
    async def on_order_book_update(self, book: MarketOrderBook) -> list[Order]:
        """Handle order book updates and optionally return signals."""

    @abstractmethod
    async def on_trade(self, trade: Trade) -> None:
        """Handle trade executions."""

    @abstractmethod
    async def generate_signals(self, book: MarketOrderBook) -> list[Order]:
        """Generate trading signals from current book state."""

    async def start(self) -> None:
        self.is_active = True

    async def stop(self) -> None:
        self.is_active = False

    def update_performance(self, pnl: float, trade_count: int) -> None:
        self.performance_metrics["total_pnl"] = pnl
        self.performance_metrics["trade_count"] = trade_count


def _new_order_id(prefix: str) -> str:
    return f"{prefix}_{uuid4().hex[:12]}"


class ImbalanceStrategy(Strategy):
    """Trade when bid/ask volume imbalance exceeds a threshold."""

    def __init__(self, side: str = "UP", threshold: float = 0.2, quantity: float = 1.0):
        super().__init__("Imbalance", {"threshold": threshold, "quantity": quantity, "side": side})
        self.side = side.upper()
        self.threshold = threshold
        self.quantity = quantity

    def _target_book(self, book: MarketOrderBook) -> OrderBookSnapshot | None:
        return book.up if self.side == "UP" else book.down

    async def on_order_book_update(self, book: MarketOrderBook) -> list[Order]:
        if not self.is_active:
            return []
        return await self.generate_signals(book)

    async def on_trade(self, trade: Trade) -> None:
        return None

    async def generate_signals(self, book: MarketOrderBook) -> list[Order]:
        target = self._target_book(book)
        if target is None or target.mid_price <= 0:
            return []

        imbalance = target.order_book_imbalance
        if imbalance > self.threshold:
            return [
                Order(
                    id=_new_order_id("imb_buy"),
                    user_id="strategy",
                    side=BookSide.BUY,
                    order_type=OrderType.LIMIT,
                    price=target.best_bid or target.mid_price,
                    quantity=self.quantity,
                    timestamp=datetime.now(timezone.utc),
                )
            ]
        if imbalance < -self.threshold:
            return [
                Order(
                    id=_new_order_id("imb_sell"),
                    user_id="strategy",
                    side=BookSide.SELL,
                    order_type=OrderType.LIMIT,
                    price=target.best_ask or target.mid_price,
                    quantity=self.quantity,
                    timestamp=datetime.now(timezone.utc),
                )
            ]
        return []


class SpreadStrategy(Strategy):
    """Market making — quote around mid with a target spread."""

    def __init__(self, side: str = "UP", spread: float = 0.02, quantity: float = 1.0):
        super().__init__("Spread", {"spread": spread, "quantity": quantity, "side": side})
        self.side = side.upper()
        self.spread = spread
        self.quantity = quantity
        self.inventory = 0.0

    def _target_book(self, book: MarketOrderBook) -> OrderBookSnapshot | None:
        return book.up if self.side == "UP" else book.down

    async def on_order_book_update(self, book: MarketOrderBook) -> list[Order]:
        if not self.is_active:
            return []
        return await self.generate_signals(book)

    async def on_trade(self, trade: Trade) -> None:
        if trade.side == BookSide.BUY:
            self.inventory += trade.quantity
        elif trade.side == BookSide.SELL:
            self.inventory -= trade.quantity

    async def generate_signals(self, book: MarketOrderBook) -> list[Order]:
        target = self._target_book(book)
        if target is None or target.mid_price <= 0:
            return []

        half = self.spread / 2
        skew = self.inventory * 0.001
        bid_price = max(0.01, target.mid_price - half - skew)
        ask_price = min(0.99, target.mid_price + half + skew)

        return [
            Order(
                id=_new_order_id("mm_buy"),
                user_id="strategy",
                side=BookSide.BUY,
                order_type=OrderType.LIMIT,
                price=round(bid_price, 4),
                quantity=self.quantity,
                timestamp=datetime.now(timezone.utc),
            ),
            Order(
                id=_new_order_id("mm_sell"),
                user_id="strategy",
                side=BookSide.SELL,
                order_type=OrderType.LIMIT,
                price=round(ask_price, 4),
                quantity=self.quantity,
                timestamp=datetime.now(timezone.utc),
            ),
        ]


class MomentumStrategy(Strategy):
    """Momentum based on mid-price history."""

    def __init__(self, side: str = "UP", lookback: int = 20, threshold: float = 0.02):
        super().__init__(
            "Momentum",
            {"lookback": lookback, "threshold": threshold, "side": side},
        )
        self.side = side.upper()
        self.lookback = lookback
        self.threshold = threshold
        self._history: list[float] = []

    def _target_book(self, book: MarketOrderBook) -> OrderBookSnapshot | None:
        return book.up if self.side == "UP" else book.down

    async def on_order_book_update(self, book: MarketOrderBook) -> list[Order]:
        if not self.is_active:
            return []
        target = self._target_book(book)
        if target and target.mid_price > 0:
            self._history.append(target.mid_price)
            if len(self._history) > self.lookback * 2:
                self._history.pop(0)
        return await self.generate_signals(book)

    async def on_trade(self, trade: Trade) -> None:
        return None

    async def generate_signals(self, book: MarketOrderBook) -> list[Order]:
        if len(self._history) < self.lookback * 2:
            return []

        recent = self._history[-self.lookback :]
        older = self._history[-2 * self.lookback : -self.lookback]
        recent_avg = sum(recent) / len(recent)
        older_avg = sum(older) / len(older)
        if older_avg <= 0:
            return []

        momentum = (recent_avg - older_avg) / older_avg
        target = self._target_book(book)
        if target is None:
            return []

        if momentum > self.threshold:
            return [
                Order(
                    id=_new_order_id("mom_buy"),
                    user_id="strategy",
                    side=BookSide.BUY,
                    order_type=OrderType.MARKET,
                    price=target.mid_price,
                    quantity=1.0,
                    timestamp=datetime.now(timezone.utc),
                )
            ]
        if momentum < -self.threshold:
            return [
                Order(
                    id=_new_order_id("mom_sell"),
                    user_id="strategy",
                    side=BookSide.SELL,
                    order_type=OrderType.MARKET,
                    price=target.mid_price,
                    quantity=1.0,
                    timestamp=datetime.now(timezone.utc),
                )
            ]
        return []
