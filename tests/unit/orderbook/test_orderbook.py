"""
Order book module tests — run with: pytest tests/unit/orderbook/test_orderbook.py
"""

import asyncio
from datetime import datetime, timezone
from unittest.mock import Mock, patch

import pytest

from polyalpha.core.market import Market
from polyalpha.orderbook import (
    BacktestEngine,
    BookSide,
    ClobBookClient,
    ImbalanceStrategy,
    MomentumStrategy,
    OrderBookFeed,
    OrderBookManager,
    OrderBookSnapshot,
    RiskManager,
    SpreadStrategy,
    estimate_fill,
    estimate_market_buy_usdc,
    book_summary,
)
from polyalpha.orderbook.manager import SimulatedOrderBookManager
from polyalpha.orderbook.models import BookLevel, Portfolio
from polyalpha.core.errors import OrderBookNotFound


SAMPLE_CLOB_RESPONSE = {
    "market": "0xcondition",
    "asset_id": "tok_up",
    "timestamp": "2024-01-01T12:00:00Z",
    "bids": [
        {"price": "0.48", "size": "1000"},
        {"price": "0.47", "size": "2500"},
    ],
    "asks": [
        {"price": "0.52", "size": "800"},
        {"price": "0.53", "size": "1500"},
    ],
    "tick_size": "0.01",
    "min_order_size": "5",
    "neg_risk": False,
    "hash": "0xabc",
}


def make_market(**overrides) -> Market:
    defaults = dict(
        id="test-id",
        question="Will BTC be higher in 5 minutes?",
        description="",
        slug="btc-updown-5m-9999999",
        active=True,
        closed=False,
        archived=False,
        start_time="2025-01-01T00:00:00Z",
        end_time="2025-01-01T00:05:00Z",
        volume=10_000.0,
        liquidity=5_000.0,
        outcomes=["UP", "DOWN"],
        prices=[0.50, 0.50],
        tokens=["tok_up", "tok_down"],
    )
    defaults.update(overrides)
    return Market(**defaults)


def make_snapshot(**overrides) -> OrderBookSnapshot:
    snapshot = OrderBookSnapshot.from_clob_response(SAMPLE_CLOB_RESPONSE)
    if not overrides:
        return snapshot
    return OrderBookSnapshot(
        token_id=overrides.get("token_id", snapshot.token_id),
        market_id=overrides.get("market_id", snapshot.market_id),
        bids=overrides.get("bids", snapshot.bids),
        asks=overrides.get("asks", snapshot.asks),
        timestamp=overrides.get("timestamp", snapshot.timestamp),
        tick_size=overrides.get("tick_size", snapshot.tick_size),
        min_order_size=overrides.get("min_order_size", snapshot.min_order_size),
        neg_risk=overrides.get("neg_risk", snapshot.neg_risk),
        hash=overrides.get("hash", snapshot.hash),
        sequence=overrides.get("sequence", snapshot.sequence),
    )


# ── Model tests ────────────────────────────────────────────────────────────────

@pytest.mark.unit
def test_orderbook_snapshot_from_clob_response():
    book = OrderBookSnapshot.from_clob_response(SAMPLE_CLOB_RESPONSE)

    assert book.token_id == "tok_up"
    assert book.best_bid == 0.48
    assert book.best_ask == 0.52
    assert book.spread == pytest.approx(0.04)
    assert book.mid_price == pytest.approx(0.50)
    assert book.total_bid_volume == pytest.approx(3500)
    assert book.total_ask_volume == pytest.approx(2300)


@pytest.mark.unit
def test_orderbook_snapshot_imbalance():
    book = make_snapshot()
    imbalance = book.order_book_imbalance
    assert imbalance > 0  # more bid volume than ask volume


@pytest.mark.unit
def test_orderbook_snapshot_get_depth():
    book = make_snapshot()
    depth = book.get_depth(levels=1)

    assert len(depth["bids"]) == 1
    assert len(depth["asks"]) == 1
    assert depth["spread"] == book.spread
    assert depth["mid_price"] == book.mid_price


@pytest.mark.unit
def test_orderbook_snapshot_from_ws_message():
    msg = dict(SAMPLE_CLOB_RESPONSE)
    msg["event_type"] = "book"
    book = OrderBookSnapshot.from_ws_message(msg, sequence=42)
    assert book.sequence == 42
    assert book.best_bid == 0.48


# ── Analytics tests ────────────────────────────────────────────────────────────

@pytest.mark.unit
def test_estimate_fill_buy_full():
    book = make_snapshot()
    fill = estimate_fill(book, BookSide.BUY, 500)

    assert fill.filled_size == 500
    assert fill.fully_filled is True
    assert fill.average_price == pytest.approx(0.52)
    assert fill.total_cost == pytest.approx(260.0)


@pytest.mark.unit
def test_estimate_fill_buy_partial():
    book = make_snapshot()
    fill = estimate_fill(book, BookSide.BUY, 5000)

    assert fill.fully_filled is False
    assert fill.filled_size == pytest.approx(2300)


@pytest.mark.unit
def test_estimate_market_buy_usdc():
    book = make_snapshot()
    fill = estimate_market_buy_usdc(book, 100.0)

    assert fill.total_cost == pytest.approx(100.0)
    assert fill.filled_size > 0


@pytest.mark.unit
def test_book_summary():
    book = make_snapshot()
    summary = book_summary(book)

    assert summary["token_id"] == "tok_up"
    assert summary["best_bid"] == 0.48
    assert "imbalance" in summary


# ── CLOB client tests ──────────────────────────────────────────────────────────

@pytest.mark.unit
def test_clob_get_book_mocked():
    client = ClobBookClient(cache_ttl=0)

    with patch.object(client._client, "request") as mock_request:
        mock_response = Mock()
        mock_response.status_code = 200
        mock_response.json.return_value = SAMPLE_CLOB_RESPONSE
        mock_response.raise_for_status = Mock()
        mock_request.return_value = mock_response

        book = client.get_book("tok_up")

    assert book.token_id == "tok_up"
    assert book.best_bid == 0.48
    client.close()


@pytest.mark.unit
def test_clob_get_book_not_found():
    client = ClobBookClient(cache_ttl=0)

    with patch.object(client._client, "request") as mock_request:
        mock_response = Mock()
        mock_response.status_code = 404
        mock_request.return_value = mock_response

        with pytest.raises(OrderBookNotFound):
            client.get_book("missing")

    client.close()


@pytest.mark.unit
def test_clob_cache():
    client = ClobBookClient(cache_ttl=60.0)

    with patch.object(client._client, "request") as mock_request:
        mock_response = Mock()
        mock_response.status_code = 200
        mock_response.json.return_value = SAMPLE_CLOB_RESPONSE
        mock_response.raise_for_status = Mock()
        mock_request.return_value = mock_response

        client.get_book("tok_up")
        client.get_book("tok_up")

    assert mock_request.call_count == 1
    client.close()


# ── Manager tests ──────────────────────────────────────────────────────────────

@pytest.mark.asyncio
@pytest.mark.unit
async def test_manager_apply_snapshot():
    manager = OrderBookManager(symbol="btc")
    snapshot = make_snapshot()

    await manager.apply_snapshot(snapshot)
    book = manager.get_book("tok_up")

    assert book is not None
    assert book.best_bid == 0.48


@pytest.mark.asyncio
@pytest.mark.unit
async def test_manager_price_change():
    manager = OrderBookManager()
    await manager.apply_snapshot(make_snapshot())

    await manager.apply_price_change(
        {
            "price_changes": [
                {"asset_id": "tok_up", "price": "0.49", "size": "500", "side": "BUY"},
            ]
        }
    )

    book = manager.get_book("tok_up")
    assert book is not None
    assert any(level.price == 0.49 for level in book.bids)


@pytest.mark.asyncio
@pytest.mark.unit
async def test_manager_record_trade():
    manager = OrderBookManager()
    await manager.apply_snapshot(make_snapshot())

    trade = await manager.record_trade(
        {"asset_id": "tok_up", "price": "0.51", "size": "100", "side": "BUY"}
    )

    assert trade.price == 0.51
    assert len(manager.trades) == 1


@pytest.mark.asyncio
@pytest.mark.unit
async def test_simulated_matching():
    from polyalpha.orderbook.models import Order, OrderType

    sim = SimulatedOrderBookManager()
    buy = Order(
        id="buy1",
        user_id="test",
        side=BookSide.BUY,
        order_type=OrderType.LIMIT,
        price=0.55,
        quantity=10,
        timestamp=datetime.now(timezone.utc),
    )
    sell = Order(
        id="sell1",
        user_id="test",
        side=BookSide.SELL,
        order_type=OrderType.LIMIT,
        price=0.50,
        quantity=10,
        timestamp=datetime.now(timezone.utc),
    )

    await sim.add_order(buy)
    await sim.add_order(sell)
    trades = await sim.match_orders()

    assert len(trades) == 1
    assert trades[0].quantity == 10


# ── Feed tests ─────────────────────────────────────────────────────────────────

@pytest.mark.unit
def test_feed_refresh_mocked():
    market = make_market()
    clob = ClobBookClient(cache_ttl=0)

    with patch.object(clob, "get_books") as mock_books:
        mock_books.return_value = {
            "tok_up": make_snapshot(),
            "tok_down": make_snapshot(token_id="tok_down"),
        }
        feed = OrderBookFeed(market=market, clob=clob)
        book = feed.refresh()

    assert book.up is not None
    assert book.down is not None
    assert feed.book.up_mid > 0
    clob.close()


@pytest.mark.unit
def test_feed_handlers():
    market = make_market()
    feed = OrderBookFeed(market=market, clob=ClobBookClient(cache_ttl=0))
    events = []

    @feed.on("update")
    def on_update(book):
        events.append("update")

    with patch.object(feed._clob, "get_books") as mock_books:
        mock_books.return_value = {"tok_up": make_snapshot(), "tok_down": make_snapshot(token_id="tok_down")}
        feed.refresh()

    assert events == ["update"]
    feed.close()


@pytest.mark.unit
def test_feed_attach_stream():
    from polyalpha.stream import Stream

    market = make_market()
    stream = Stream(market)
    feed = OrderBookFeed(market=market, clob=ClobBookClient(cache_ttl=0))

    feed.attach_stream(stream)
    assert feed._attached is True
    feed.close()


# ── Strategy tests ─────────────────────────────────────────────────────────────

@pytest.mark.asyncio
@pytest.mark.unit
async def test_imbalance_strategy_signals():
    strategy = ImbalanceStrategy(side="UP", threshold=0.1, quantity=5)
    await strategy.start()

    up = make_snapshot(
        bids=(BookLevel(0.60, 5000),),
        asks=(BookLevel(0.62, 500),),
    )
    from polyalpha.orderbook.models import MarketOrderBook

    book = MarketOrderBook(market_slug="test", up=up, down=None)
    signals = await strategy.on_order_book_update(book)

    assert len(signals) == 1
    assert signals[0].side == BookSide.BUY


@pytest.mark.asyncio
@pytest.mark.unit
async def test_spread_strategy_quotes():
    strategy = SpreadStrategy(side="UP", spread=0.04, quantity=2)
    await strategy.start()

    from polyalpha.orderbook.models import MarketOrderBook

    book = MarketOrderBook(market_slug="test", up=make_snapshot(), down=None)
    signals = await strategy.generate_signals(book)

    assert len(signals) == 2
    assert signals[0].side == BookSide.BUY
    assert signals[1].side == BookSide.SELL


@pytest.mark.asyncio
@pytest.mark.unit
async def test_momentum_strategy_warmup():
    strategy = MomentumStrategy(side="UP", lookback=5, threshold=0.01)
    await strategy.start()

    from polyalpha.orderbook.models import MarketOrderBook

    book = MarketOrderBook(market_slug="test", up=make_snapshot(), down=None)

    for price in [0.50, 0.51, 0.52, 0.53, 0.54]:
        snapshot = make_snapshot(
            bids=(BookLevel(price - 0.01, 100),),
            asks=(BookLevel(price + 0.01, 100),),
        )
        book = MarketOrderBook(market_slug="test", up=snapshot, down=None)
        await strategy.on_order_book_update(book)

    signals = await strategy.generate_signals(book)
    assert isinstance(signals, list)


# ── Backtest tests ─────────────────────────────────────────────────────────────

@pytest.mark.asyncio
@pytest.mark.unit
async def test_backtest_engine():
    strategy = ImbalanceStrategy(side="UP", threshold=0.5, quantity=1)
    engine = BacktestEngine(strategy, initial_capital=1000.0)

    from polyalpha.orderbook.models import MarketOrderBook

    snapshots = []
    for _ in range(3):
        snapshots.append(
            MarketOrderBook(
                market_slug="test",
                up=make_snapshot(
                    bids=(BookLevel(0.60, 5000),),
                    asks=(BookLevel(0.62, 100),),
                ),
                down=None,
            )
        )

    await engine.load_snapshots(snapshots)
    report = await engine.run_backtest()

    assert "total_return" in report
    assert report["total_trades"] >= 0


# ── Risk manager tests ─────────────────────────────────────────────────────────

@pytest.mark.asyncio
@pytest.mark.unit
async def test_risk_manager_validate_order():
    from polyalpha.orderbook.models import Order, OrderType

    risk = RiskManager(max_order_size=50, max_position_size=100)
    portfolio = Portfolio(user_id="u1", positions={}, cash_balance=1000, total_value=1000)

    order = Order(
        id="o1",
        user_id="u1",
        side=BookSide.BUY,
        order_type=OrderType.LIMIT,
        price=0.5,
        quantity=10,
    )

    ok, msg = await risk.validate_order(order, portfolio)
    assert ok is True

    big_order = Order(
        id="o2",
        user_id="u1",
        side=BookSide.BUY,
        order_type=OrderType.LIMIT,
        price=0.5,
        quantity=200,
    )
    ok, msg = await risk.validate_order(big_order, portfolio)
    assert ok is False


# ── Client integration ─────────────────────────────────────────────────────────

@pytest.mark.unit
def test_client_orderbook():
    import polyalpha

    client = polyalpha.Client()
    market = make_market()
    feed = client.orderbook(market)

    assert feed.market == market
    client.close()
