"""
In-memory order book manager — maintains live state from CLOB updates.

Uses dicts keyed by price for O(1) level updates; best bid/ask tracked incrementally.
"""

from __future__ import annotations

import asyncio
import logging
from datetime import datetime, timezone
from typing import Any, Callable

from ..core.constants import PRICE_ROUNDING
from .models import (
    BookLevel,
    BookSide,
    MarketOrderBook,
    Order,
    OrderBookSnapshot,
    OrderStatus,
    Trade,
)

log = logging.getLogger(__name__)

Subscriber = Callable[[str, Any], Any]


class OrderBookManager:
    """
    Maintain live order book state for one or more tokens.

    Accepts full snapshots from CLOB REST/WS and incremental price_change events.
    """

    def __init__(self, symbol: str = ""):
        self.symbol = symbol
        self._books: dict[str, OrderBookSnapshot] = {}
        self._trades: list[Trade] = []
        self._sequence = 0
        self._subscribers: list[Subscriber] = []
        self._lock = asyncio.Lock()

    @property
    def sequence(self) -> int:
        return self._sequence

    @property
    def trades(self) -> list[Trade]:
        return list(self._trades)

    def subscribe(self, callback: Subscriber) -> None:
        self._subscribers.append(callback)

    def unsubscribe(self, callback: Subscriber) -> None:
        if callback in self._subscribers:
            self._subscribers.remove(callback)

    async def _notify(self, event_type: str, data: Any) -> None:
        for callback in self._subscribers:
            try:
                result = callback(event_type, data)
                if asyncio.iscoroutine(result):
                    await result
            except Exception as exc:
                log.exception("OrderBookManager subscriber error: %s", exc)

    async def apply_snapshot(self, snapshot: OrderBookSnapshot) -> None:
        """Replace book state for a token with a full snapshot."""
        async with self._lock:
            self._sequence += 1
            updated = OrderBookSnapshot(
                token_id=snapshot.token_id,
                market_id=snapshot.market_id,
                bids=snapshot.bids,
                asks=snapshot.asks,
                timestamp=snapshot.timestamp,
                tick_size=snapshot.tick_size,
                min_order_size=snapshot.min_order_size,
                neg_risk=snapshot.neg_risk,
                hash=snapshot.hash,
                sequence=self._sequence,
                last_trade_price=snapshot.last_trade_price,
                last_trade_size=snapshot.last_trade_size,
            )
            self._books[snapshot.token_id] = updated
            await self._notify("book_update", updated)

    async def apply_ws_book(self, msg: dict[str, Any]) -> OrderBookSnapshot:
        snapshot = OrderBookSnapshot.from_ws_message(msg, sequence=self._sequence + 1)
        await self.apply_snapshot(snapshot)
        return self.get_book(snapshot.token_id)

    async def apply_price_change(self, msg: dict[str, Any]) -> None:
        """Apply incremental price_change event from CLOB WebSocket."""
        async with self._lock:
            for change in msg.get("price_changes", []):
                token_id = str(change.get("asset_id", ""))
                if not token_id:
                    continue

                book = self._books.get(token_id)
                if book is None:
                    continue

                bids = {level.price: level for level in book.bids}
                asks = {level.price: level for level in book.asks}
                price = round(float(change.get("price", 0)), PRICE_ROUNDING)
                size = float(change.get("size", 0))
                side = str(change.get("side", "")).upper()

                if price <= 0:
                    continue

                target = bids if side in ("BUY", "BID") else asks
                if size <= 0:
                    target.pop(price, None)
                else:
                    target[price] = BookLevel(price=price, size=size)

                sorted_bids = tuple(sorted(bids.values(), key=lambda level: level.price, reverse=True))
                sorted_asks = tuple(sorted(asks.values(), key=lambda level: level.price))

                self._sequence += 1
                updated = OrderBookSnapshot(
                    token_id=token_id,
                    market_id=book.market_id,
                    bids=sorted_bids,
                    asks=sorted_asks,
                    timestamp=datetime.now(timezone.utc),
                    tick_size=book.tick_size,
                    min_order_size=book.min_order_size,
                    neg_risk=book.neg_risk,
                    hash=book.hash,
                    sequence=self._sequence,
                    last_trade_price=book.last_trade_price,
                    last_trade_size=book.last_trade_size,
                )
                self._books[token_id] = updated
                await self._notify("book_update", updated)

    async def record_trade(self, msg: dict[str, Any]) -> Trade:
        """Record a last_trade_price WebSocket event."""
        async with self._lock:
            token_id = str(msg.get("asset_id", ""))
            trade = Trade(
                id=f"trade_{self._sequence}_{token_id}",
                order_id=str(msg.get("order_id", "")),
                price=float(msg.get("price", 0)),
                quantity=float(msg.get("size", msg.get("quantity", 0))),
                timestamp=datetime.now(timezone.utc),
                taker_order_id=str(msg.get("taker_order_id", "")),
                maker_order_id=str(msg.get("maker_order_id", "")),
                token_id=token_id,
                side=BookSide.BUY if str(msg.get("side", "")).upper() == "BUY" else BookSide.SELL,
            )
            self._trades.append(trade)
            self._sequence += 1

            book = self._books.get(token_id)
            if book:
                self._books[token_id] = OrderBookSnapshot(
                    token_id=book.token_id,
                    market_id=book.market_id,
                    bids=book.bids,
                    asks=book.asks,
                    timestamp=book.timestamp,
                    tick_size=book.tick_size,
                    min_order_size=book.min_order_size,
                    neg_risk=book.neg_risk,
                    hash=book.hash,
                    sequence=self._sequence,
                    last_trade_price=trade.price,
                    last_trade_size=trade.quantity,
                )

            await self._notify("trade", trade)
            return trade

    def get_book(self, token_id: str) -> OrderBookSnapshot | None:
        return self._books.get(token_id)

    def get_market_book(
        self,
        market_slug: str,
        up_token: str,
        down_token: str,
    ) -> MarketOrderBook:
        return MarketOrderBook(
            market_slug=market_slug,
            up=self._books.get(up_token),
            down=self._books.get(down_token),
            trades=list(self._trades),
        )

    def get_order_book_snapshot(self, token_id: str) -> OrderBookSnapshot:
        book = self._books.get(token_id)
        if book is None:
            return OrderBookSnapshot(
                token_id=token_id,
                market_id="",
                bids=(),
                asks=(),
                timestamp=datetime.now(timezone.utc),
                sequence=self._sequence,
            )
        return book


class SimulatedOrderBookManager(OrderBookManager):
    """
    Local matching engine for backtesting and paper strategy simulation.

    Adds limit orders to the book and matches crossing orders.
    """

    def __init__(self, symbol: str = ""):
        super().__init__(symbol)
        self._orders: dict[str, Order] = {}

    async def add_order(self, order: Order) -> bool:
        async with self._lock:
            if order.id in self._orders:
                return False
            self._orders[order.id] = order
            self._sequence += 1
            await self._notify("order_added", order)
            return True

    async def remove_order(self, order_id: str) -> bool:
        async with self._lock:
            order = self._orders.pop(order_id, None)
            if order is None:
                return False
            order.status = OrderStatus.CANCELLED
            self._sequence += 1
            await self._notify("order_cancelled", order)
            return True

    async def match_orders(self) -> list[Trade]:
        """Match simulated orders — simplified for backtesting."""
        async with self._lock:
            trades: list[Trade] = []
            buys = sorted(
                (order for order in self._orders.values() if order.side == BookSide.BUY),
                key=lambda order: (-order.price, order.timestamp or datetime.min),
            )
            sells = sorted(
                (order for order in self._orders.values() if order.side == BookSide.SELL),
                key=lambda order: (order.price, order.timestamp or datetime.min),
            )

            for buy in buys:
                if buy.is_filled:
                    continue
                for sell in sells:
                    if sell.is_filled:
                        continue
                    if buy.price < sell.price:
                        break
                    qty = min(buy.remaining_quantity, sell.remaining_quantity)
                    if qty <= 0:
                        continue

                    trade = Trade(
                        id=f"sim_{self._sequence}_{buy.id}_{sell.id}",
                        order_id=buy.id,
                        price=sell.price,
                        quantity=qty,
                        timestamp=datetime.now(timezone.utc),
                        taker_order_id=buy.id,
                        maker_order_id=sell.id,
                    )
                    trades.append(trade)
                    self._trades.append(trade)
                    buy.filled_quantity += qty
                    sell.filled_quantity += qty
                    if buy.is_filled:
                        buy.status = OrderStatus.FILLED
                        self._orders.pop(buy.id, None)
                    if sell.is_filled:
                        sell.status = OrderStatus.FILLED
                        self._orders.pop(sell.id, None)
                    self._sequence += 1

            for trade in trades:
                await self._notify("trade_executed", trade)
            return trades
