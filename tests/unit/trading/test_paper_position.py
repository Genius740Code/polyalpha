"""
Paper trading position tests — run with: pytest tests/unit/trading/test_paper_position.py
"""

import pytest
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
    """Create a basic paper trading engine."""
    return PaperEngine(balance=100.0)


# ── Position calculations tests ─────────────────────────────────────────────────

@pytest.mark.unit
def test_position_pnl_calculations(engine, make_market):
    """Test position P&L calculations."""
    market = make_market(prices=[0.50, 0.50])
    
    engine.buy(market, side="UP", amount=10.0)
    pos = engine.positions()[0]
    
    # Initial P&L should be 0 (price hasn't changed)
    assert pos.cost_basis > 0
    assert abs(pos.pnl) < 0.01  # Small rounding error allowed
    
    # Update price to higher value
    engine.check_limits(market.id, up_price=0.60, down_price=0.40)
    assert pos.current_price == 0.60
    assert pos.pnl > 0  # Should be profitable
    
    # Update price to lower value
    engine.check_limits(market.id, up_price=0.40, down_price=0.60)
    assert pos.current_price == 0.40
    assert pos.pnl < 0  # Should be loss


@pytest.mark.unit
def test_position_dump(engine, make_market):
    """Test position dump functionality."""
    market = make_market()
    engine.buy(market, side="UP", amount=10.0)
    
    pos = engine.positions()[0]
    dump = pos.dump()
    
    assert "market" in dump
    assert "side" in dump
    assert "shares" in dump
    assert "avg_price" in dump
    assert "pnl" in dump
    assert "resolved" in dump


@pytest.mark.unit
def test_position_dump_includes_stop_loss_take_profit(engine, make_market):
    """Test that position dump includes stop loss and take profit."""
    config = PaperConfig(max_risk_per_trade=0.50)
    engine = PaperEngine(balance=100.0, config=config)
    market = make_market()
    
    # Buy a position
    engine.buy(market, side="UP", amount=20.0)
    
    # Get the position
    positions = engine.positions()
    assert len(positions) == 1
    
    # Set stop loss and take profit on the position
    positions[0].stop_loss = 0.45
    positions[0].take_profit = 0.60
    
    # Check dump includes the fields
    dump = positions[0].dump()
    assert "stop_loss" in dump
    assert "take_profit" in dump
    assert dump["stop_loss"] == 0.45
    assert dump["take_profit"] == 0.60
