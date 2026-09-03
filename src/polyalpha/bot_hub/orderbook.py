"""bot_hub.orderbook — OrderBookAccessor for live order-book access."""

from __future__ import annotations

from typing import TYPE_CHECKING

from ..orderbook import ClobBookClient, OrderBookFeed

if TYPE_CHECKING:
    from ..core import Market
    from ..orderbook import MarketOrderBook, OrderBookSnapshot
    from .context import StrategyContext


class OrderBookAccessor:
    """
    Live order book for the strategy's current market.

    Lazily creates and auto-attaches an ``OrderBookFeed`` to the shared
    WebSocket stream on first property access.  Fetches an initial REST
    snapshot so data is available immediately even before the stream
    connects.

    Usage
    -----
        >>> ctx.orderbook.up.bids            # tuple[BookLevel] — UP bids
        >>> ctx.orderbook.down.asks          # tuple[BookLevel] — DOWN asks
        >>> ctx.orderbook.up.spread          # float — UP bid-ask spread
        >>> ctx.orderbook.up.mid_price       # float — UP mid price
        >>> ctx.orderbook.down.best_bid      # float — best DOWN bid
        >>> ctx.orderbook.refresh()          # force REST refresh

    Properties
    ----------
    up : OrderBookSnapshot | None
        UP token order book (bids, asks, spread, mid_price, …).
    down : OrderBookSnapshot | None
        DOWN token order book (bids, asks, spread, mid_price, …).
    book : MarketOrderBook
        Combined UP + DOWN market book.
    """

    def __init__(
        self,
        ctx: StrategyContext,
        market: Market,
        clob: ClobBookClient,
    ):
        self._ctx = ctx
        self._feed = OrderBookFeed(market=market, clob=clob)
        self._stream_attached = False

    def _ensure(self) -> None:
        if self._stream_attached:
            return
        self._feed.refresh()
        stream = self._ctx._stream  # type: ignore[attr-defined]
        if stream is not None:
            self._feed.attach_stream(stream)
        self._stream_attached = True

    @property
    def up(self) -> OrderBookSnapshot | None:  # type: ignore[name-defined]
        """UP token order book snapshot."""
        self._ensure()
        return self._feed.up

    @property
    def down(self) -> OrderBookSnapshot | None:  # type: ignore[name-defined]
        """DOWN token order book snapshot."""
        self._ensure()
        return self._feed.down

    @property
    def book(self) -> MarketOrderBook:  # type: ignore[name-defined]
        """Combined UP + DOWN market order book."""
        self._ensure()
        return self._feed.book

    def refresh(self) -> MarketOrderBook:  # type: ignore[name-defined]
        """Fetch fresh REST snapshots for UP and DOWN tokens."""
        self._ensure()
        return self._feed.refresh()
