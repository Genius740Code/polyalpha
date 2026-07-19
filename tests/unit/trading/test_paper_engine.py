"""
Paper trading engine core tests — run with: pytest tests/unit/trading/test_paper_engine.py
"""

import pytest
import polyalpha
from polyalpha.trading.paper import PaperEngine, PaperConfig
from polyalpha.core.market import Market


@pytest.fixture
def make_market():
    """Factory function to create test markets."""
    from datetime import datetime, timedelta, timezone
    def _make_market(**overrides) -> Market:
        now = datetime.now(timezone.utc)
        future_start = now + timedelta(minutes=5)
        future_end = now + timedelta(minutes=10)
        defaults = dict(
            id="test-id",
            question="Will BTC be higher in 5 minutes?",
            description="",
            slug="btc-updown-5m-9999999",
            active=True,
            closed=False,
            archived=False,
            start_time=future_start.strftime("%Y-%m-%dT%H:%M:%SZ"),
            end_time=future_end.strftime("%Y-%m-%dT%H:%M:%SZ"),
            volume=10_000.0,
            liquidity=5_000.0,
            outcomes=["UP", "DOWN"],
            prices=[0.55, 0.45],
            tokens=["tok_up", "tok_down"],
        )
        defaults.update(overrides)
        return Market(**defaults)
    return _make_market


@pytest.fixture
def engine():
    """Create a basic paper trading engine with risk management disabled."""
    config = PaperConfig(enable_risk_management=False)
    return PaperEngine(balance=100.0, config=config)


# ── Paper engine basic tests ────────────────────────────────────────────────────

@pytest.mark.unit
def test_paper_market_buy(engine, make_market):
    """Test basic market buy operation."""
    market = make_market()
    order = engine.buy(market, side="UP", amount=10.0)

    assert order.status == "filled"
    assert order.side == "UP"
    assert order.fee == pytest.approx(10.0 * 0.02, abs=1e-6)
    assert order.shares == pytest.approx((10.0 - order.fee) / 0.55, abs=1e-4)
    assert engine.balance == pytest.approx(90.0, abs=1e-6)


@pytest.mark.unit
def test_paper_both_sides(engine, make_market):
    """Test buying both sides of a market."""
    market = make_market()
    engine.buy(market, side="UP", amount=20.0)
    engine.buy(market, side="DOWN", amount=20.0)
    assert len(engine.positions()) == 2
    assert engine.balance == pytest.approx(60.0, abs=1e-6)


@pytest.mark.unit
def test_paper_limit_reserves_balance(engine, make_market):
    """Test that limit orders reserve balance."""
    market = make_market()
    order = engine.limit(market, side="UP", price=0.92, amount=25.0)

    assert order.status == "open"
    assert engine.balance == pytest.approx(75.0, abs=1e-6)


@pytest.mark.unit
def test_paper_limit_fills_on_price(engine, make_market):
    """Test that limit orders fill when price threshold is crossed."""
    market = make_market()
    engine.limit(market, side="UP", price=0.90, amount=20.0)

    # Simulate a price update that crosses the limit
    engine.check_limits(market.id, up_price=0.92, down_price=0.08)

    orders = engine.orders()
    assert orders[0].status == "filled"


@pytest.mark.unit
def test_paper_limit_does_not_fill_below_threshold(engine, make_market):
    """Test that limit orders don't fill below threshold."""
    market = make_market()
    engine.limit(market, side="UP", price=0.95, amount=20.0)

    engine.check_limits(market.id, up_price=0.90, down_price=0.10)

    assert engine.open()[0].status == "open"


@pytest.mark.unit
def test_paper_cancel_refunds(engine, make_market):
    """Test that canceling a limit order refunds the balance."""
    market = make_market()
    order = engine.limit(market, side="UP", price=0.92, amount=30.0)
    assert engine.balance == pytest.approx(70.0)

    engine.cancel(order.id)
    assert engine.balance == pytest.approx(100.0)
    assert order.status == "cancelled"


@pytest.mark.unit
def test_paper_insufficient_balance(make_market):
    """Test that insufficient balance raises error."""
    engine = PaperEngine(balance=5.0)
    market = make_market()
    with pytest.raises(polyalpha.InsufficientBalance):
        engine.buy(market, side="UP", amount=10.0)


@pytest.mark.unit
def test_paper_resolve_won(engine, make_market):
    """Test resolving a winning position."""
    market = make_market()
    engine.buy(market, side="UP", amount=10.0)
    balance_after_buy = engine.balance  # 90.0

    engine.resolve(market, outcome="UP")

    pos = engine.all_positions()[0]
    assert pos.resolved
    assert pos.outcome == "WON"
    # Each winning share redeems at $1 — payout = pos.shares
    assert engine.balance == pytest.approx(balance_after_buy + pos.shares, abs=1e-4)


@pytest.mark.unit
def test_paper_resolve_lost(engine, make_market):
    """Test resolving a losing position."""
    market = make_market()
    engine.buy(market, side="UP", amount=10.0)

    engine.resolve(market, outcome="DOWN")

    pos = engine.all_positions()[0]
    assert pos.outcome == "LOST"
    assert pos.pnl < 0


@pytest.mark.unit
def test_paper_invalid_side(engine, make_market):
    """Test that invalid side raises error."""
    market = make_market()
    with pytest.raises(ValueError):
        engine.buy(market, side="YES", amount=10.0)


# ── Paper engine edge cases ────────────────────────────────────────────────────

@pytest.mark.unit
def test_paper_set_balance(engine):
    """Test setting balance."""
    engine.set_balance(250.0)
    assert engine.balance == 250.0


@pytest.mark.unit
def test_paper_set_negative_balance(engine):
    """Test that negative balance raises error."""
    with pytest.raises(ValueError):
        engine.set_balance(-50.0)


@pytest.mark.unit
def test_paper_cancel_nonexistent_order(engine):
    """Test that canceling nonexistent order raises error."""
    with pytest.raises(polyalpha.OrderNotFound):
        engine.cancel("nonexistent-id")


@pytest.mark.unit
def test_paper_cancel_filled_order(engine, make_market):
    """Test that canceling filled order raises error."""
    market = make_market()
    order = engine.buy(market, side="UP", amount=10.0)
    with pytest.raises(ValueError):
        engine.cancel(order.id)


@pytest.mark.unit
def test_paper_position_aggregation(engine, make_market):
    """Test that same-side buys aggregate positions."""
    market = make_market()
    
    # Buy same side twice - should aggregate
    engine.buy(market, side="UP", amount=10.0)
    engine.buy(market, side="UP", amount=10.0)
    
    positions = engine.positions()
    assert len(positions) == 1
    assert positions[0].shares > 0


@pytest.mark.unit
def test_paper_zero_price_fallback(engine, make_market):
    """Test zero price fallback behavior."""
    market = make_market(prices=[0.0, 0.0])
    order = engine.buy(market, side="UP", amount=10.0)
    # Should use 0.5 fallback price
    assert order.price == 0.5


@pytest.mark.unit
def test_paper_resolve_invalid_outcome(engine, make_market):
    """Test that invalid outcome raises error."""
    market = make_market()
    engine.buy(market, side="UP", amount=10.0)
    with pytest.raises(ValueError):
        engine.resolve(market, outcome="INVALID")
