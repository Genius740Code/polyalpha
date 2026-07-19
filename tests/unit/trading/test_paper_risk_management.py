"""
Paper trading risk management tests — run with: pytest tests/unit/trading/test_paper_risk_management.py
"""

import pytest
from polyalpha.trading.paper import PaperEngine, PaperConfig, PaperPosition
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


# ── Risk Management Tests ─────────────────────────────────────────────────────

@pytest.mark.unit
def test_risk_manager_max_order_size(make_market):
    """Test that orders exceeding max_order_size are rejected."""
    config = PaperConfig(max_order_size=50.0, max_risk_per_trade=0.50)  # 50% to allow larger orders
    engine = PaperEngine(balance=100.0, config=config)
    market = make_market()
    
    # Should accept order under limit
    order = engine.buy(market, side="UP", amount=40.0)
    assert order.status == "filled"
    
    # Should reject order over limit
    with pytest.raises(ValueError, match="exceeds maximum"):
        engine.buy(market, side="UP", amount=60.0)


@pytest.mark.unit
def test_risk_manager_max_position_size(make_market):
    """Test that position size limits are enforced."""
    config = PaperConfig(max_position_size=30.0, max_risk_per_trade=0.50)
    engine = PaperEngine(balance=100.0, config=config)
    market = make_market()
    
    # First order should succeed
    order1 = engine.buy(market, side="UP", amount=20.0)
    assert order1.status == "filled"
    
    # Second order should exceed position limit
    with pytest.raises(ValueError, match="Position would exceed maximum size"):
        engine.buy(market, side="UP", amount=15.0)


@pytest.mark.unit
def test_risk_manager_max_open_positions(make_market):
    """Test that max open positions limit is enforced."""
    config = PaperConfig(max_open_positions=2, max_risk_per_trade=0.20)
    engine = PaperEngine(balance=100.0, config=config)
    
    # Create different markets
    market1 = make_market(id="m1", slug="market1")
    market2 = make_market(id="m2", slug="market2")
    market3 = make_market(id="m3", slug="market3")
    
    # First two positions should succeed
    engine.buy(market1, side="UP", amount=10.0)
    engine.buy(market2, side="UP", amount=10.0)
    assert len(engine.positions()) == 2
    
    # Third should exceed limit
    with pytest.raises(ValueError, match="Maximum open positions"):
        engine.buy(market3, side="UP", amount=10.0)


@pytest.mark.unit
def test_risk_manager_daily_loss_limit(make_market):
    """Test that daily loss limit stops trading."""
    config = PaperConfig(max_daily_loss=20.0, max_risk_per_trade=0.50)
    engine = PaperEngine(balance=100.0, config=config)
    market = make_market()
    
    # Make a losing trade
    engine.buy(market, side="UP", amount=30.0)
    
    # Simulate a loss by resolving at a loss
    engine.resolve(market, outcome="DOWN")  # UP position loses
    
    # Try another trade - should be blocked due to loss limit
    with pytest.raises(ValueError, match="Daily loss"):
        engine.buy(market, side="UP", amount=10.0)


@pytest.mark.unit
def test_risk_manager_max_trades_per_day(make_market):
    """Test that max trades per day limit is enforced."""
    config = PaperConfig(max_trades_per_day=3, max_risk_per_trade=0.20)
    engine = PaperEngine(balance=100.0, config=config)
    market = make_market()
    
    # First three trades should succeed (trades counted on order entry)
    for _ in range(3):
        engine.buy(market, side="UP", amount=10.0)
    
    # Fourth should exceed daily limit
    with pytest.raises(ValueError, match="Maximum daily trades"):
        engine.buy(market, side="UP", amount=10.0)


@pytest.mark.unit
def test_risk_manager_max_risk_per_trade(make_market):
    """Test that max risk per trade percentage is enforced."""
    config = PaperConfig(max_risk_per_trade=0.10)  # 10% of balance
    engine = PaperEngine(balance=100.0, config=config)
    market = make_market()
    
    # Should accept order under 10% of balance
    order = engine.buy(market, side="UP", amount=5.0)
    assert order.status == "filled"
    
    # Should reject order over 10% of balance
    with pytest.raises(ValueError, match="exceeds max risk"):
        engine.buy(market, side="UP", amount=15.0)


@pytest.mark.unit
def test_risk_manager_disable(make_market):
    """Test that risk management can be disabled."""
    config = PaperConfig(
        enable_risk_management=False,
        max_order_size=10.0
    )
    engine = PaperEngine(balance=100.0, config=config)
    market = make_market()
    
    # Should succeed even though it exceeds the limit
    order = engine.buy(market, side="UP", amount=50.0)
    assert order.status == "filled"


@pytest.mark.unit
def test_risk_manager_summary(make_market):
    """Test risk summary reporting."""
    config = PaperConfig(max_daily_loss=50.0, max_trades_per_day=10, max_risk_per_trade=0.20)
    engine = PaperEngine(balance=100.0, config=config)
    market = make_market()
    
    # Make some trades (trades counted on order entry)
    engine.buy(market, side="UP", amount=10.0)
    engine.buy(market, side="DOWN", amount=10.0)
    
    summary = engine.get_risk_summary()
    
    assert summary["daily_trades"] == 2
    assert summary["max_daily_loss"] == 50.0
    assert summary["max_trades_per_day"] == 10
    assert summary["remaining_trades"] == 8
    assert "daily_pnl" in summary


@pytest.mark.unit
def test_risk_manager_reset_daily_limits(make_market):
    """Test manual reset of daily limits."""
    config = PaperConfig(max_trades_per_day=2, max_risk_per_trade=0.20)
    engine = PaperEngine(balance=100.0, config=config)
    market = make_market()
    
    # Use up daily limit (trades counted on order entry)
    for _ in range(2):
        engine.buy(market, side="UP", amount=10.0)
    
    # Should be blocked
    with pytest.raises(ValueError, match="Maximum daily trades"):
        engine.buy(market, side="UP", amount=10.0)
    
    # Reset limits
    engine.reset_daily_limits()
    
    # Should now work
    order = engine.buy(market, side="UP", amount=10.0)
    assert order.status == "filled"


@pytest.mark.unit
def test_risk_manager_pnl_tracking(make_market):
    """Test that P&L is tracked correctly."""
    config = PaperConfig(max_daily_loss=100.0, max_risk_per_trade=0.50)
    engine = PaperEngine(balance=100.0, config=config)
    market = make_market()
    
    # Make a trade
    engine.buy(market, side="UP", amount=20.0)
    
    # Resolve as a win
    engine.resolve(market, outcome="UP")
    
    summary = engine.get_risk_summary()
    assert summary["daily_pnl"] > 0  # Should have profit


@pytest.mark.unit
def test_risk_manager_sell_position_pnl(make_market):
    """Test that P&L is tracked when selling positions."""
    config = PaperConfig(max_daily_loss=100.0, max_risk_per_trade=0.50)
    engine = PaperEngine(balance=100.0, config=config)
    market = make_market()
    
    # Buy a position
    engine.buy(market, side="UP", amount=20.0)
    
    # Update price and sell
    engine.check_limits(market.id, up_price=0.60, down_price=0.40)
    engine.sell_position(market, side="UP")
    
    summary = engine.get_risk_summary()
    # Should have tracked the trade
    assert summary["daily_trades"] >= 1


@pytest.mark.unit
def test_risk_manager_check_stop_loss_up():
    """Test stop loss check for UP position."""
    config = PaperConfig(max_risk_per_trade=0.50)
    engine = PaperEngine(balance=100.0, config=config)
    
    # Create a position with stop loss
    position = PaperPosition(
        market_id="test",
        slug="test",
        question="Test",
        side="UP",
        shares=10.0,
        avg_price=0.50,
        current_price=0.50,
        stop_loss=0.45,
        take_profit=None
    )
    
    # Should trigger when price drops to or below stop loss
    assert engine._risk_manager.check_stop_loss(position, 0.45) == True
    assert engine._risk_manager.check_stop_loss(position, 0.44) == True
    assert engine._risk_manager.check_stop_loss(position, 0.46) == False


@pytest.mark.unit
def test_risk_manager_check_stop_loss_down():
    """Test stop loss check for DOWN position."""
    config = PaperConfig(max_risk_per_trade=0.50)
    engine = PaperEngine(balance=100.0, config=config)
    
    # Create a DOWN position with stop loss
    position = PaperPosition(
        market_id="test",
        slug="test",
        question="Test",
        side="DOWN",
        shares=10.0,
        avg_price=0.50,
        current_price=0.50,
        stop_loss=0.55,
        take_profit=None
    )
    
    # Should trigger when price rises to or above stop loss (DOWN loses when price goes up)
    assert engine._risk_manager.check_stop_loss(position, 0.55) == True
    assert engine._risk_manager.check_stop_loss(position, 0.56) == True
    assert engine._risk_manager.check_stop_loss(position, 0.54) == False


@pytest.mark.unit
def test_risk_manager_check_stop_loss_none():
    """Test stop loss check when no stop loss is set."""
    config = PaperConfig(max_risk_per_trade=0.50)
    engine = PaperEngine(balance=100.0, config=config)
    
    position = PaperPosition(
        market_id="test",
        slug="test",
        question="Test",
        side="UP",
        shares=10.0,
        avg_price=0.50,
        current_price=0.50,
        stop_loss=None,
        take_profit=None
    )
    
    # Should never trigger when stop loss is None
    assert engine._risk_manager.check_stop_loss(position, 0.30) == False
    assert engine._risk_manager.check_stop_loss(position, 0.70) == False


@pytest.mark.unit
def test_risk_manager_check_take_profit_up():
    """Test take profit check for UP position."""
    config = PaperConfig(max_risk_per_trade=0.50)
    engine = PaperEngine(balance=100.0, config=config)
    
    # Create a position with take profit
    position = PaperPosition(
        market_id="test",
        slug="test",
        question="Test",
        side="UP",
        shares=10.0,
        avg_price=0.50,
        current_price=0.50,
        stop_loss=None,
        take_profit=0.60
    )
    
    # Should trigger when price reaches or exceeds take profit
    assert engine._risk_manager.check_take_profit(position, 0.60) == True
    assert engine._risk_manager.check_take_profit(position, 0.61) == True
    assert engine._risk_manager.check_take_profit(position, 0.59) == False


@pytest.mark.unit
def test_risk_manager_check_take_profit_down():
    """Test take profit check for DOWN position."""
    config = PaperConfig(max_risk_per_trade=0.50)
    engine = PaperEngine(balance=100.0, config=config)
    
    # Create a DOWN position with take profit
    position = PaperPosition(
        market_id="test",
        slug="test",
        question="Test",
        side="DOWN",
        shares=10.0,
        avg_price=0.50,
        current_price=0.50,
        stop_loss=None,
        take_profit=0.40
    )
    
    # Should trigger when price drops to or below take profit (DOWN profits when price goes down)
    assert engine._risk_manager.check_take_profit(position, 0.40) == True
    assert engine._risk_manager.check_take_profit(position, 0.39) == True
    assert engine._risk_manager.check_take_profit(position, 0.41) == False


@pytest.mark.unit
def test_risk_manager_check_take_profit_none():
    """Test take profit check when no take profit is set."""
    config = PaperConfig(max_risk_per_trade=0.50)
    engine = PaperEngine(balance=100.0, config=config)
    
    position = PaperPosition(
        market_id="test",
        slug="test",
        question="Test",
        side="UP",
        shares=10.0,
        avg_price=0.50,
        current_price=0.50,
        stop_loss=None,
        take_profit=None
    )
    
    # Should never trigger when take profit is None
    assert engine._risk_manager.check_take_profit(position, 0.30) == False
    assert engine._risk_manager.check_take_profit(position, 0.70) == False


@pytest.mark.unit
def test_risk_manager_calculate_position_size_with_risk():
    """Test position size calculation based on risk."""
    config = PaperConfig(max_risk_per_trade=0.02)  # 2% risk per trade
    engine = PaperEngine(balance=1000.0, config=config)
    
    # Test with normal stop loss
    entry_price = 0.50
    stop_loss = 0.45
    size = engine._risk_manager.calculate_position_size_with_risk(
        balance=1000.0,
        entry_price=entry_price,
        stop_loss=stop_loss,
        side="UP"
    )
    
    # Risk amount = 1000 * 0.02 = 20
    # Price diff = 0.05
    # Position size = 20 / (0.05/0.50) = 20 / 0.10 = 200
    assert size == pytest.approx(200.0, abs=1e-6)
    
    # Test with tighter stop loss (should allow larger position)
    stop_loss = 0.48
    size = engine._risk_manager.calculate_position_size_with_risk(
        balance=1000.0,
        entry_price=entry_price,
        stop_loss=stop_loss,
        side="UP"
    )
    # Risk amount = 20
    # Price diff = 0.02
    # Position size = 20 / (0.02/0.50) = 20 / 0.04 = 500
    assert size == pytest.approx(500.0, abs=1e-6)
    
    # Test with wider stop loss (should allow smaller position)
    stop_loss = 0.40
    size = engine._risk_manager.calculate_position_size_with_risk(
        balance=1000.0,
        entry_price=entry_price,
        stop_loss=stop_loss,
        side="UP"
    )
    # Risk amount = 20
    # Price diff = 0.10
    # Position size = 20 / (0.10/0.50) = 20 / 0.20 = 100
    assert size == pytest.approx(100.0, abs=1e-6)


@pytest.mark.unit
def test_risk_manager_calculate_position_size_zero_diff():
    """Test position size calculation when entry equals stop loss."""
    config = PaperConfig(max_risk_per_trade=0.02)
    engine = PaperEngine(balance=1000.0, config=config)
    
    # When price diff is zero, should return risk amount (capped at balance)
    size = engine._risk_manager.calculate_position_size_with_risk(
        balance=1000.0,
        entry_price=0.50,
        stop_loss=0.50,
        side="UP"
    )
    
    # Should return risk amount = 1000 * 0.02 = 20
    assert size == pytest.approx(20.0, abs=1e-6)


@pytest.mark.unit
def test_risk_manager_calculate_position_size_exceeds_balance():
    """Test that calculated position size is capped at balance."""
    config = PaperConfig(max_risk_per_trade=0.50)  # 50% risk per trade
    engine = PaperEngine(balance=100.0, config=config)
    
    # With very tight stop loss, calculation might exceed balance
    size = engine._risk_manager.calculate_position_size_with_risk(
        balance=100.0,
        entry_price=0.50,
        stop_loss=0.49,
        side="UP"
    )
    
    # Should be capped at balance
    assert size <= 100.0
