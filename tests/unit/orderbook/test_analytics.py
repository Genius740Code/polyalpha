"""
Analytics module tests — run with: pytest tests/unit/orderbook/test_analytics.py
"""

from datetime import datetime, timezone

import pytest

from polyalpha.orderbook.analytics import (
    book_summary,
    cumulative_depth,
    estimate_fill,
    estimate_market_buy_usdc,
    liquidity_at_price,
    support_resistance_levels,
    volatility_from_spread,
)
from polyalpha.orderbook.models import BookLevel, BookSide, OrderBookSnapshot


# ── Fixtures ────────────────────────────────────────────────────────────


@pytest.fixture
def sample_snapshot() -> OrderBookSnapshot:
    return OrderBookSnapshot(
        token_id="tok_up",
        market_id="0xcondition",
        bids=(
            BookLevel(0.50, 2000),
            BookLevel(0.49, 3000),
            BookLevel(0.48, 1000),
            BookLevel(0.47, 500),
        ),
        asks=(
            BookLevel(0.52, 1500),
            BookLevel(0.53, 2000),
            BookLevel(0.54, 800),
            BookLevel(0.55, 400),
        ),
        timestamp=datetime(2025, 6, 1, 12, 0, 0, tzinfo=timezone.utc),
        tick_size=0.01,
    )


@pytest.fixture
def empty_snapshot() -> OrderBookSnapshot:
    return OrderBookSnapshot(
        token_id="tok_up",
        market_id="0xcondition",
        bids=(),
        asks=(),
        timestamp=datetime(2025, 6, 1, 12, 0, 0, tzinfo=timezone.utc),
        tick_size=0.01,
    )


@pytest.fixture
def tight_snapshot() -> OrderBookSnapshot:
    return OrderBookSnapshot(
        token_id="tok_up",
        market_id="0xmarket",
        bids=(BookLevel(0.495, 5000),),
        asks=(BookLevel(0.505, 5000),),
        timestamp=datetime(2025, 6, 1, 12, 0, 0, tzinfo=timezone.utc),
        tick_size=0.001,
    )


# ── cumulative_depth ────────────────────────────────────────────────────


class TestCumulativeDepth:
    @pytest.mark.unit
    def test_bid_side(self, sample_snapshot):
        rows = cumulative_depth(sample_snapshot.bids, BookSide.SELL)

        assert len(rows) == 4

        assert rows[0]["price"] == 0.50
        assert rows[0]["size"] == 2000
        assert rows[0]["cumulative_size"] == 2000
        assert rows[0]["cumulative_notional"] == pytest.approx(1000.0)

        assert rows[1]["cumulative_size"] == 5000
        assert rows[1]["cumulative_notional"] == pytest.approx(1000.0 + 1470.0)

        assert rows[-1]["cumulative_size"] == pytest.approx(6500)
        assert rows[-1]["cumulative_notional"] == pytest.approx(
            2000 * 0.50 + 3000 * 0.49 + 1000 * 0.48 + 500 * 0.47
        )

    @pytest.mark.unit
    def test_ask_side(self, sample_snapshot):
        rows = cumulative_depth(sample_snapshot.asks, BookSide.BUY)

        assert len(rows) == 4
        assert rows[0]["price"] == 0.52
        notional_0 = 1500 * 0.52
        assert rows[0]["cumulative_notional"] == pytest.approx(notional_0)

        expected_total_notional = sum(l.price * l.size for l in sample_snapshot.asks)
        assert rows[-1]["cumulative_notional"] == pytest.approx(expected_total_notional)

    @pytest.mark.unit
    def test_empty_levels(self, empty_snapshot):
        rows = cumulative_depth(empty_snapshot.bids, BookSide.SELL)
        assert rows == []

        rows = cumulative_depth(empty_snapshot.asks, BookSide.BUY)
        assert rows == []

    @pytest.mark.unit
    def test_single_level(self):
        levels = (BookLevel(1.00, 100),)
        rows = cumulative_depth(levels, BookSide.BUY)

        assert len(rows) == 1
        assert rows[0]["cumulative_size"] == 100
        assert rows[0]["cumulative_notional"] == 100.0


# ── estimate_fill ───────────────────────────────────────────────────────


class TestEstimateFill:
    @pytest.mark.unit
    def test_buy_full_fill(self, sample_snapshot):
        fill = estimate_fill(sample_snapshot, BookSide.BUY, 1000)

        assert fill.side == BookSide.BUY
        assert fill.requested_size == 1000
        assert fill.filled_size == 1000
        assert fill.fully_filled is True
        assert fill.average_price == pytest.approx(0.52)
        assert fill.total_cost == pytest.approx(520.0)
        assert len(fill.levels_used) == 1
        assert fill.levels_used[0] == (0.52, 1000)

    @pytest.mark.unit
    def test_buy_multi_level(self, sample_snapshot):
        fill = estimate_fill(sample_snapshot, BookSide.BUY, 2500)

        assert fill.fully_filled is True
        assert fill.filled_size == 2500
        assert len(fill.levels_used) == 2
        assert fill.levels_used == ((0.52, 1500), (0.53, 1000))

        expected_cost = 1500 * 0.52 + 1000 * 0.53
        expected_avg = expected_cost / 2500
        assert fill.average_price == pytest.approx(expected_avg)
        assert fill.total_cost == pytest.approx(expected_cost)

    @pytest.mark.unit
    def test_buy_partial_fill(self, sample_snapshot):
        fill = estimate_fill(sample_snapshot, BookSide.BUY, 10000)

        assert fill.fully_filled is False
        assert fill.filled_size == pytest.approx(4700)
        assert len(fill.levels_used) == 4
        assert fill.levels_used == ((0.52, 1500), (0.53, 2000), (0.54, 800), (0.55, 400))

    @pytest.mark.unit
    def test_sell_full_fill(self, sample_snapshot):
        fill = estimate_fill(sample_snapshot, BookSide.SELL, 500)

        assert fill.side == BookSide.SELL
        assert fill.filled_size == 500
        assert fill.fully_filled is True
        assert fill.average_price == pytest.approx(0.50)
        assert fill.total_cost == pytest.approx(250.0)

    @pytest.mark.unit
    def test_sell_multi_level(self, sample_snapshot):
        fill = estimate_fill(sample_snapshot, BookSide.SELL, 5000)

        assert fill.filled_size == 5000
        assert fill.fully_filled is True
        assert len(fill.levels_used) == 2
        assert fill.levels_used == ((0.50, 2000), (0.49, 3000))

    @pytest.mark.unit
    def test_zero_size(self, sample_snapshot):
        fill = estimate_fill(sample_snapshot, BookSide.BUY, 0)

        assert fill.filled_size == 0
        assert fill.average_price == 0.0
        assert fill.total_cost == 0.0
        assert fill.levels_used == ()
        assert fill.fully_filled is False

    @pytest.mark.unit
    def test_negative_size(self, sample_snapshot):
        fill = estimate_fill(sample_snapshot, BookSide.BUY, -10)

        assert fill.filled_size == 0
        assert fill.fully_filled is False

    @pytest.mark.unit
    def test_slippage_property(self, sample_snapshot):
        fill = estimate_fill(sample_snapshot, BookSide.BUY, 2500)

        assert fill.slippage > 0

    @pytest.mark.unit
    def test_zero_slippage_single_level(self, sample_snapshot):
        fill = estimate_fill(sample_snapshot, BookSide.BUY, 500)

        assert fill.slippage == 0.0

    @pytest.mark.unit
    def test_empty_book(self, empty_snapshot):
        fill = estimate_fill(empty_snapshot, BookSide.BUY, 100)

        assert fill.filled_size == 0
        assert fill.average_price == 0.0
        assert fill.total_cost == 0.0
        assert fill.levels_used == ()
        assert fill.fully_filled is False


# ── estimate_market_buy_usdc ────────────────────────────────────────────


class TestEstimateMarketBuyUsdc:
    @pytest.mark.unit
    def test_single_level(self, sample_snapshot):
        fill = estimate_market_buy_usdc(sample_snapshot, 780.0)

        assert fill.total_cost == pytest.approx(780.0)
        assert fill.filled_size == pytest.approx(1500)
        assert fill.average_price == pytest.approx(0.52)
        assert fill.levels_used == ((0.52, 1500),)
        assert fill.fully_filled is True

    @pytest.mark.unit
    def test_multi_level_partial_last(self, sample_snapshot):
        fill = estimate_market_buy_usdc(sample_snapshot, 1000.0)

        expected_shares_first = 1500
        remaining = 1000.0 - (1500 * 0.52)
        expected_shares_second = remaining / 0.53
        expected_total = expected_shares_first + expected_shares_second
        expected_avg = 1000.0 / expected_total

        assert fill.total_cost == pytest.approx(1000.0)
        assert fill.filled_size == pytest.approx(expected_total)
        assert fill.average_price == pytest.approx(expected_avg)
        assert len(fill.levels_used) == 2
        assert fill.fully_filled is True

    @pytest.mark.unit
    def test_sweep_all_levels(self, sample_snapshot):
        fill = estimate_market_buy_usdc(sample_snapshot, 1_000_000.0)

        total_notional = sum(l.price * l.size for l in sample_snapshot.asks)
        expected_filled = 4700

        assert fill.fully_filled is False
        assert fill.filled_size == pytest.approx(expected_filled)
        assert fill.total_cost == pytest.approx(total_notional)

    @pytest.mark.unit
    def test_zero_amount(self, sample_snapshot):
        fill = estimate_market_buy_usdc(sample_snapshot, 0)

        assert fill.filled_size == 0
        assert fill.average_price == 0.0
        assert fill.total_cost == 0.0
        assert fill.levels_used == ()
        assert fill.fully_filled is False

    @pytest.mark.unit
    def test_negative_amount(self, sample_snapshot):
        fill = estimate_market_buy_usdc(sample_snapshot, -50)

        assert fill.filled_size == 0
        assert fill.fully_filled is False

    @pytest.mark.unit
    def test_empty_book(self, empty_snapshot):
        fill = estimate_market_buy_usdc(empty_snapshot, 1000)

        assert fill.filled_size == 0
        assert fill.average_price == 0.0
        assert fill.total_cost == 0.0
        assert fill.fully_filled is False


# ── liquidity_at_price ──────────────────────────────────────────────────


class TestLiquidityAtPrice:
    @pytest.mark.unit
    def test_exact_match_ask_side(self, sample_snapshot):
        size = liquidity_at_price(sample_snapshot, 0.52, BookSide.BUY)
        assert size == 1500

    @pytest.mark.unit
    def test_exact_match_bid_side(self, sample_snapshot):
        size = liquidity_at_price(sample_snapshot, 0.50, BookSide.SELL)
        assert size == 2000

    @pytest.mark.unit
    def test_within_tolerance(self, sample_snapshot):
        size = liquidity_at_price(sample_snapshot, 0.525, BookSide.BUY, tolerance=0.01)
        assert size == 3500

    @pytest.mark.unit
    def test_within_tolerance_multiple_levels(self, sample_snapshot):
        size = liquidity_at_price(sample_snapshot, 0.525, BookSide.BUY, tolerance=0.02)
        assert size == pytest.approx(4300)

    @pytest.mark.unit
    def test_no_liquidity(self, sample_snapshot):
        size = liquidity_at_price(sample_snapshot, 99.0, BookSide.BUY)
        assert size == 0

    @pytest.mark.unit
    def test_default_tolerance(self, sample_snapshot):
        size = liquidity_at_price(sample_snapshot, 0.50, BookSide.SELL)
        assert size == 2000

    @pytest.mark.unit
    def test_empty_book(self, empty_snapshot):
        size = liquidity_at_price(empty_snapshot, 0.50, BookSide.BUY)
        assert size == 0

    @pytest.mark.unit
    def test_buy_side_reads_asks(self, sample_snapshot):
        size = liquidity_at_price(sample_snapshot, 0.53, BookSide.BUY)
        assert size == 2000

    @pytest.mark.unit
    def test_sell_side_reads_bids(self, sample_snapshot):
        size = liquidity_at_price(sample_snapshot, 0.49, BookSide.SELL)
        assert size == 3000


# ── support_resistance_levels ───────────────────────────────────────────


class TestSupportResistanceLevels:
    @pytest.mark.unit
    def test_default_levels(self, sample_snapshot):
        result = support_resistance_levels(sample_snapshot)

        assert "support" in result
        assert "resistance" in result
        assert result["support"] == [0.50, 0.49, 0.48, 0.47]
        assert result["resistance"] == [0.52, 0.53, 0.54, 0.55]

    @pytest.mark.unit
    def test_custom_levels(self, sample_snapshot):
        result = support_resistance_levels(sample_snapshot, levels=2)

        assert result["support"] == [0.50, 0.49]
        assert result["resistance"] == [0.52, 0.53]

    @pytest.mark.unit
    def test_more_levels_than_book(self, sample_snapshot):
        result = support_resistance_levels(sample_snapshot, levels=10)

        assert len(result["support"]) == 4
        assert len(result["resistance"]) == 4

    @pytest.mark.unit
    def test_empty_book(self, empty_snapshot):
        result = support_resistance_levels(empty_snapshot)

        assert result["support"] == []
        assert result["resistance"] == []

    @pytest.mark.unit
    def test_support_descending(self, sample_snapshot):
        result = support_resistance_levels(sample_snapshot, levels=3)
        for i in range(len(result["support"]) - 1):
            assert result["support"][i] >= result["support"][i + 1]

    @pytest.mark.unit
    def test_resistance_ascending(self, sample_snapshot):
        result = support_resistance_levels(sample_snapshot, levels=3)
        for i in range(len(result["resistance"]) - 1):
            assert result["resistance"][i] <= result["resistance"][i + 1]


# ── volatility_from_spread ──────────────────────────────────────────────


class TestVolatilityFromSpread:
    @pytest.mark.unit
    def test_typical_book(self, sample_snapshot):
        v = volatility_from_spread(sample_snapshot)

        expected_spread = 0.52 - 0.50
        expected_mid = 0.51
        expected = expected_spread / expected_mid
        assert v == pytest.approx(expected)

    @pytest.mark.unit
    def test_tight_spread(self, tight_snapshot):
        v = volatility_from_spread(tight_snapshot)

        expected_spread = 0.505 - 0.495
        expected_mid = (0.495 + 0.505) / 2
        expected = expected_spread / expected_mid
        assert v == pytest.approx(expected)

    @pytest.mark.unit
    def test_zero_mid_price(self, empty_snapshot):
        v = volatility_from_spread(empty_snapshot)
        assert v == 0.0

    @pytest.mark.unit
    def test_zero_bids(self):
        book = OrderBookSnapshot(
            token_id="t",
            market_id="m",
            bids=(),
            asks=(BookLevel(0.55, 100),),
            timestamp=datetime(2025, 6, 1, 12, 0, 0, tzinfo=timezone.utc),
        )
        v = volatility_from_spread(book)
        assert v == 0.0

    @pytest.mark.unit
    def test_zero_asks(self):
        book = OrderBookSnapshot(
            token_id="t",
            market_id="m",
            bids=(BookLevel(0.45, 100),),
            asks=(),
            timestamp=datetime(2025, 6, 1, 12, 0, 0, tzinfo=timezone.utc),
        )
        v = volatility_from_spread(book)
        assert v == 0.0


# ── book_summary ────────────────────────────────────────────────────────


class TestBookSummary:
    @pytest.mark.unit
    def test_all_fields(self, sample_snapshot):
        summary = book_summary(sample_snapshot)

        assert summary["token_id"] == "tok_up"
        assert summary["best_bid"] == 0.50
        assert summary["best_ask"] == 0.52
        assert summary["spread"] == 0.02
        assert summary["mid_price"] == 0.51
        assert summary["bid_volume"] == 6500
        assert summary["ask_volume"] == 4700
        assert summary["levels"] == 8
        assert summary["timestamp"] == "2025-06-01T12:00:00+00:00"

    @pytest.mark.unit
    def test_imbalance(self, sample_snapshot):
        summary = book_summary(sample_snapshot)

        assert summary["imbalance"] > 0
        assert isinstance(summary["imbalance"], float)

    @pytest.mark.unit
    def test_empty_book(self, empty_snapshot):
        summary = book_summary(empty_snapshot)

        assert summary["best_bid"] == 0.0
        assert summary["best_ask"] == 0.0
        assert summary["spread"] == 0.0
        assert summary["mid_price"] == 0.0
        assert summary["bid_volume"] == 0.0
        assert summary["ask_volume"] == 0.0
        assert summary["levels"] == 0

    @pytest.mark.unit
    def test_negative_imbalance(self):
        book = OrderBookSnapshot(
            token_id="t",
            market_id="m",
            bids=(BookLevel(0.50, 100),),
            asks=(BookLevel(0.52, 1000),),
            timestamp=datetime(2025, 6, 1, 12, 0, 0, tzinfo=timezone.utc),
        )
        summary = book_summary(book)
        assert summary["imbalance"] < 0
