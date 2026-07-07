"""
Live order book feed — REST snapshots + Stream WebSocket integration.
"""

from __future__ import annotations

import asyncio
import logging
from collections import defaultdict
from typing import TYPE_CHECKING, Any, Callable

from ..core.market import Market
from .clob import ClobBookClient
from .manager import OrderBookManager
from .models import MarketOrderBook, OrderBookSnapshot, Trade

if TYPE_CHECKING:
    from ..stream import Stream

log = logging.getLogger(__name__)

FeedEvent = Callable[..., Any]
FEED_EVENTS = frozenset({"book", "trade", "update", "connect"})


class OrderBookFeed:
    """
    Real-time order book for a Polymarket market (UP + DOWN tokens).

    Fetches initial snapshots via REST, then applies live WebSocket updates
    from an attached :class:`~polyalpha.Stream`.

    Example
    -------
    >>> feed = client.orderbook(market)
    >>> feed.refresh()  # REST snapshot
    >>>
    >>> @feed.on("update")
    ... def on_update(book: MarketOrderBook):
    ...     print(book.up_mid, book.down_mid)
    >>>
    >>> stream = client.stream(market)
    >>> feed.attach_stream(stream)
    >>> stream.start(background=True)
    """

    def __init__(
        self,
        market: Market,
        clob: ClobBookClient | None = None,
        manager: OrderBookManager | None = None,
    ):
        self.market = market
        self._clob = clob or ClobBookClient()
        self._owns_clob = clob is None
        self._manager = manager or OrderBookManager(symbol=market.slug)
        self._handlers: dict[str, list[FeedEvent]] = defaultdict(list)
        self._attached = False
        self._loop: asyncio.AbstractEventLoop | None = None

    @property
    def manager(self) -> OrderBookManager:
        return self._manager

    @property
    def up(self) -> OrderBookSnapshot | None:
        return self._manager.get_book(self.market.up_token)

    @property
    def down(self) -> OrderBookSnapshot | None:
        return self._manager.get_book(self.market.down_token)

    @property
    def book(self) -> MarketOrderBook:
        return self._manager.get_market_book(
            self.market.slug,
            self.market.up_token,
            self.market.down_token,
        )

    def on(self, event: str) -> Callable[[FeedEvent], FeedEvent]:
        if event not in FEED_EVENTS:
            raise ValueError(f"Unknown event '{event}'. Valid: {sorted(FEED_EVENTS)}")

        def decorator(fn: FeedEvent) -> FeedEvent:
            self._handlers[event].append(fn)
            return fn

        return decorator

    def add_handler(self, event: str, fn: FeedEvent) -> None:
        if event not in FEED_EVENTS:
            raise ValueError(f"Unknown event '{event}'. Valid: {sorted(FEED_EVENTS)}")
        self._handlers[event].append(fn)

    def _emit(self, event: str, *args: Any) -> None:
        for fn in self._handlers.get(event, []):
            try:
                fn(*args)
            except Exception as exc:
                log.exception("OrderBookFeed handler '%s' raised: %s", event, exc)

    def refresh(self) -> MarketOrderBook:
        """Fetch fresh REST snapshots for UP and DOWN tokens."""
        tokens = [token for token in self.market.tokens if token]
        if not tokens:
            return self.book

        books = self._clob.get_books(tokens) if len(tokens) > 1 else {
            tokens[0]: self._clob.get_book(tokens[0]),
        }
        for snapshot in books.values():
            self._run_async(self._manager.apply_snapshot(snapshot))

        market_book = self.book
        self._emit("book", market_book)
        self._emit("update", market_book)
        return market_book

    def get_book(self, side: str = "UP") -> OrderBookSnapshot | None:
        """Return book for UP or DOWN side."""
        token = self.market.up_token if side.upper() == "UP" else self.market.down_token
        return self._manager.get_book(token)

    def attach_stream(self, stream: Stream) -> None:
        """Wire CLOB WebSocket events from an existing Stream."""
        if self._attached:
            return

        @stream.on("book")
        def on_book(msg: dict[str, Any]) -> None:
            self._run_async(self._manager.apply_ws_book(msg))
            self._emit("book", self.book)
            self._emit("update", self.book)

        @stream.on("trade")
        def on_trade(msg: dict[str, Any]) -> None:
            trade = self._run_async(self._manager.record_trade(msg))
            self._emit("trade", trade)
            self._emit("update", self.book)

        original_dispatch = stream._dispatch

        def patched_dispatch(msg: dict[str, Any]) -> None:
            original_dispatch(msg)
            if msg.get("event_type") == "price_change":
                self._run_async(self._manager.apply_price_change(msg))
                self._emit("update", self.book)

        stream._dispatch = patched_dispatch  # type: ignore[method-assign]
        self._attached = True
        self._emit("connect")

    def _run_async(self, coro: Any) -> Any:
        try:
            loop = asyncio.get_running_loop()
        except RuntimeError:
            loop = None

        if loop and loop.is_running():
            future = asyncio.run_coroutine_threadsafe(coro, loop)
            return future.result(timeout=5)
        return asyncio.run(coro)

    def close(self) -> None:
        if self._owns_clob:
            self._clob.close()
