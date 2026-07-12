"""
Paper trading engine tests — run with: pytest tests/test_trading.py
"""

import sys, os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))

import pytest
import polyalpha
from polyalpha.trading.paper import PaperEngine, PaperConfig, _slug_label
from polyalpha.core.market import Market


def make_market(**overrides) -> Market:
    defaults = dict(
        id          = "test-id",
        question    = "Will BTC be higher in 5 minutes?",
        description = "",
        slug        = "btc-updown-5m-9999999",
        active      = True,
        closed      = False,
        archived    = False,
        start_time  = "2025-01-01T00:00:00Z",
        end_time    = "2025-01-01T00:05:00Z",
        volume      = 10_000.0,
        liquidity   = 5_000.0,
        outcomes    = ["UP", "DOWN"],
        prices      = [0.55, 0.45],
        tokens      = ["tok_up", "tok_down"],
    )
    defaults.update(overrides)
    return Market(**defaults)


# ── Paper engine basic tests ────────────────────────────────────────────────────

def test_paper_market_buy():
    engine = PaperEngine(balance=100.0)
    market = make_market()
    order  = engine.buy(market, side="UP", amount=10.0)

    assert order.status == "filled"
    assert order.side   == "UP"
    assert order.fee    == pytest.approx(10.0 * 0.02, abs=1e-6)
    assert order.shares == pytest.approx((10.0 - order.fee) / 0.55, abs=1e-4)
    assert engine.balance == pytest.approx(90.0, abs=1e-6)


def test_paper_both_sides():
    engine = PaperEngine(balance=100.0)
    market = make_market()
    engine.buy(market, side="UP",   amount=20.0)
    engine.buy(market, side="DOWN", amount=20.0)
    assert len(engine.positions()) == 2
    assert engine.balance == pytest.approx(60.0, abs=1e-6)


def test_paper_limit_reserves_balance():
    engine = PaperEngine(balance=100.0)
    market = make_market()
    order  = engine.limit(market, side="UP", price=0.92, amount=25.0)

    assert order.status == "open"
    assert engine.balance == pytest.approx(75.0, abs=1e-6)


def test_paper_limit_fills_on_price():
    engine = PaperEngine(balance=100.0)
    market = make_market()
    engine.limit(market, side="UP", price=0.90, amount=20.0)

    # Simulate a price update that crosses the limit
    engine.check_limits(market.id, up_price=0.92, down_price=0.08)

    orders = engine.orders()
    assert orders[0].status == "filled"


def test_paper_limit_does_not_fill_below_threshold():
    engine = PaperEngine(balance=100.0)
    market = make_market()
    engine.limit(market, side="UP", price=0.95, amount=20.0)

    engine.check_limits(market.id, up_price=0.90, down_price=0.10)

    assert engine.open()[0].status == "open"


def test_paper_cancel_refunds():
    engine = PaperEngine(balance=100.0)
    market = make_market()
    order  = engine.limit(market, side="UP", price=0.92, amount=30.0)
    assert engine.balance == pytest.approx(70.0)

    engine.cancel(order.id)
    assert engine.balance == pytest.approx(100.0)
    assert order.status   == "cancelled"


def test_paper_insufficient_balance():
    engine = PaperEngine(balance=5.0)
    market = make_market()
    with pytest.raises(polyalpha.InsufficientBalance):
        engine.buy(market, side="UP", amount=10.0)


def test_paper_resolve_won():
    engine = PaperEngine(balance=100.0)
    market = make_market()
    engine.buy(market, side="UP", amount=10.0)
    balance_after_buy = engine.balance  # 90.0

    engine.resolve(market, outcome="UP")

    pos = engine.all_positions()[0]
    assert pos.resolved
    assert pos.outcome == "WON"
    # Each winning share redeems at $1 — payout = pos.shares
    assert engine.balance == pytest.approx(balance_after_buy + pos.shares, abs=1e-4)


def test_paper_resolve_lost():
    engine = PaperEngine(balance=100.0)
    market = make_market()
    engine.buy(market, side="UP", amount=10.0)

    engine.resolve(market, outcome="DOWN")

    pos = engine.all_positions()[0]
    assert pos.outcome == "LOST"
    assert pos.pnl < 0


def test_paper_invalid_side():
    engine = PaperEngine(balance=100.0)
    market = make_market()
    with pytest.raises(ValueError):
        engine.buy(market, side="YES", amount=10.0)


# ── Paper engine edge cases ────────────────────────────────────────────────────

def test_paper_set_balance():
    engine = PaperEngine(balance=100.0)
    engine.set_balance(250.0)
    assert engine.balance == 250.0


def test_paper_set_negative_balance():
    engine = PaperEngine(balance=100.0)
    with pytest.raises(ValueError):
        engine.set_balance(-50.0)


def test_paper_cancel_nonexistent_order():
    engine = PaperEngine(balance=100.0)
    with pytest.raises(polyalpha.OrderNotFound):
        engine.cancel("nonexistent-id")


def test_paper_cancel_filled_order():
    engine = PaperEngine(balance=100.0)
    market = make_market()
    order = engine.buy(market, side="UP", amount=10.0)
    with pytest.raises(ValueError):
        engine.cancel(order.id)


def test_paper_position_aggregation():
    engine = PaperEngine(balance=100.0)
    market = make_market()
    
    # Buy same side twice - should aggregate
    engine.buy(market, side="UP", amount=10.0)
    engine.buy(market, side="UP", amount=10.0)
    
    positions = engine.positions()
    assert len(positions) == 1
    assert positions[0].shares > 0


def test_paper_zero_price_fallback():
    engine = PaperEngine(balance=100.0)
    market = make_market(prices=[0.0, 0.0])
    order = engine.buy(market, side="UP", amount=10.0)
    # Should use 0.5 fallback price
    assert order.price == 0.5


def test_paper_resolve_invalid_outcome():
    engine = PaperEngine(balance=100.0)
    market = make_market()
    engine.buy(market, side="UP", amount=10.0)
    with pytest.raises(ValueError):
        engine.resolve(market, outcome="INVALID")


# ── Position calculations tests ─────────────────────────────────────────────────

def test_position_pnl_calculations():
    engine = PaperEngine(balance=100.0)
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


def test_position_dump():
    engine = PaperEngine(balance=100.0)
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


# ── Order dump tests ───────────────────────────────────────────────────────────

def test_order_dump():
    engine = PaperEngine(balance=100.0)
    market = make_market()
    order = engine.buy(market, side="UP", amount=10.0)
    
    dump = order.dump()
    
    assert dump["id"] == order.id
    assert dump["side"] == "UP"
    assert dump["status"] == "filled"
    assert dump["is_limit"] == False
    assert "filled_at" in dump


# ── Slug label helper tests ───────────────────────────────────────────────────

def test_slug_label():
    assert _slug_label("btc-updown-5m-1234567") == "BTC 5m"
    assert _slug_label("eth-updown-15m-9999")   == "ETH 15m"


# ── PaperConfig tests ─────────────────────────────────────────────────────────────

def test_paper_config_defaults():
    config = PaperConfig()
    assert config.fee_mode == "custom"
    assert config.custom_fee_rate == 0.02
    assert config.market_category == "crypto"
    assert config.execution_delay_ms == 0
    assert config.slippage_pct == 0.0
    assert config.fill_probability == 1.0


def test_paper_config_validation_invalid_fee_mode():
    with pytest.raises(ValueError):
        PaperConfig(fee_mode="invalid")


def test_paper_config_validation_negative_fee():
    with pytest.raises(ValueError):
        PaperConfig(custom_fee_rate=-0.01)


def test_paper_config_validation_negative_delay():
    with pytest.raises(ValueError):
        PaperConfig(execution_delay_ms=-100)


def test_paper_config_validation_invalid_randomness():
    with pytest.raises(ValueError):
        PaperConfig(delay_randomness=1.5)
    with pytest.raises(ValueError):
        PaperConfig(slippage_randomness=-0.1)


def test_paper_config_validation_invalid_fill_probability():
    with pytest.raises(ValueError):
        PaperConfig(fill_probability=1.5)


# ── Fee calculation tests ────────────────────────────────────────────────────────

def test_fee_mode_zero():
    config = PaperConfig(fee_mode="zero")
    engine = PaperEngine(balance=100.0, config=config)
    market = make_market()
    order = engine.buy(market, side="UP", amount=10.0)
    assert order.fee == 0.0


def test_fee_mode_custom():
    config = PaperConfig(fee_mode="custom", custom_fee_rate=0.03)
    engine = PaperEngine(balance=100.0, config=config)
    market = make_market()
    order = engine.buy(market, side="UP", amount=10.0)
    assert order.fee == pytest.approx(10.0 * 0.03, abs=1e-6)


def test_fee_mode_polymarket_geopolitical():
    config = PaperConfig(fee_mode="polymarket", market_category="geopolitical")
    engine = PaperEngine(balance=100.0, config=config)
    market = make_market()
    order = engine.buy(market, side="UP", amount=10.0)
    assert order.fee == 0.0


def test_fee_mode_polymarket_crypto():
    config = PaperConfig(fee_mode="polymarket", market_category="crypto")
    engine = PaperEngine(balance=100.0, config=config)
    market = make_market()
    order = engine.buy(market, side="UP", amount=10.0)
    # Fee should be calculated using Polymarket formula
    assert order.fee >= 0.0


def test_fee_mode_polymarket_sports():
    config = PaperConfig(fee_mode="polymarket", market_category="sports")
    engine = PaperEngine(balance=100.0, config=config)
    market = make_market()
    order = engine.buy(market, side="UP", amount=10.0)
    # Fee should be calculated using sports fee rate
    assert order.fee >= 0.0


# ── Slippage tests ───────────────────────────────────────────────────────────────

def test_slippage_disabled():
    config = PaperConfig(slippage_pct=0.0)
    engine = PaperEngine(balance=100.0, config=config)
    market = make_market()
    order = engine.buy(market, side="UP", amount=10.0)
    assert order.status == "filled"


def test_slippage_enabled():
    config = PaperConfig(slippage_pct=0.05)
    engine = PaperEngine(balance=100.0, config=config)
    market = make_market(prices=[0.50, 0.50])
    order = engine.buy(market, side="UP", amount=10.0)
    assert order.status == "filled"
    # Price should be higher due to slippage
    assert order.price > 0.50


def test_slippage_no_fill_threshold():
    config = PaperConfig(slippage_pct=0.15, max_slippage_no_fill=0.10)
    engine = PaperEngine(balance=100.0, config=config)
    market = make_market(prices=[0.50, 0.50])
    order = engine.buy(market, side="UP", amount=10.0)
    # Order should not fill due to excessive slippage
    assert order.status == "cancelled"


def test_slippage_down_side():
    config = PaperConfig(slippage_pct=0.05)
    engine = PaperEngine(balance=100.0, config=config)
    market = make_market(prices=[0.50, 0.50])
    order = engine.buy(market, side="DOWN", amount=10.0)
    assert order.status == "filled"
    # Price should be lower due to slippage for DOWN side
    assert order.price < 0.50


# ── Fill probability tests ───────────────────────────────────────────────────────

def test_fill_probability_always():
    config = PaperConfig(fill_probability=1.0)
    engine = PaperEngine(balance=100.0, config=config)
    market = make_market()
    engine.limit(market, side="UP", price=0.90, amount=20.0)
    engine.check_limits(market.id, up_price=0.92, down_price=0.08)
    orders = engine.orders()
    assert orders[0].status == "filled"


def test_fill_probability_never():
    config = PaperConfig(fill_probability=0.0)
    engine = PaperEngine(balance=100.0, config=config)
    market = make_market()
    engine.limit(market, side="UP", price=0.90, amount=20.0)
    engine.check_limits(market.id, up_price=0.92, down_price=0.08)
    orders = engine.orders()
    # Order should be cancelled due to fill probability
    assert orders[0].status == "cancelled"


# ── Config update tests ───────────────────────────────────────────────────────────

def test_set_config():
    engine = PaperEngine(balance=100.0)
    config = PaperConfig(fee_mode="zero")
    engine.set_config(config)
    assert engine.config.fee_mode == "zero"


def test_backward_compatibility_no_config():
    # Test that old code without config still works
    engine = PaperEngine(balance=100.0)
    market = make_market()
    order = engine.buy(market, side="UP", amount=10.0)
    assert order.status == "filled"
    # Should use default custom fee mode with 2% fee
    assert order.fee == pytest.approx(10.0 * 0.02, abs=1e-6)


# ── Fee Rebate Tests ───────────────────────────────────────────────────────────────

def test_rebate_tracking_enabled():
    """Test that rebates are tracked when enabled"""
    config = PaperConfig(enable_rebates=True, custom_fee_rate=0.02)
    engine = PaperEngine(balance=100.0, config=config)
    market = make_market()
    
    order = engine.buy(market, side="UP", amount=10.0)
    
    # Check rebate tracking
    assert engine._total_fees_paid > 0
    assert engine._total_volume == 10.0
    assert order.fee_type == "taker"
    assert order.rebate_amount >= 0
    assert order.rebate_rate >= 0


def test_rebate_tracking_disabled():
    """Test that rebates are not tracked when disabled"""
    config = PaperConfig(enable_rebates=False, custom_fee_rate=0.02)
    engine = PaperEngine(balance=100.0, config=config)
    market = make_market()
    
    order = engine.buy(market, side="UP", amount=10.0)
    
    # Check no rebates
    assert order.rebate_amount == 0.0
    assert order.rebate_rate == 0.0
    assert engine._total_rebates_earned == 0.0


def test_volume_based_rebate_tiers():
    """Test volume-based rebate tier progression"""
    config = PaperConfig(
        enable_rebates=True,
        custom_fee_rate=0.02,
        rebate_tiers={
            0: 0.00,
            100: 0.10,
            500: 0.15,
            1000: 0.20,
        }
    )
    engine = PaperEngine(balance=2000.0, config=config)
    market = make_market()
    
    # Start at 0% rebate
    assert engine._get_volume_rebate_rate() == 0.0
    
    # Trade $50 - still 0%
    engine.buy(market, side="UP", amount=50.0)
    assert engine._get_volume_rebate_rate() == 0.0
    
    # Trade $100 more - now 10% tier
    engine.buy(market, side="UP", amount=100.0)
    assert engine._get_volume_rebate_rate() == 0.10
    
    # Trade $400 more - now 15% tier
    engine.buy(market, side="UP", amount=400.0)
    assert engine._get_volume_rebate_rate() == 0.15
    
    # Trade $500 more - now 20% tier
    engine.buy(market, side="UP", amount=500.0)
    assert engine._get_volume_rebate_rate() == 0.20


def test_maker_vs_taker_rebate():
    """Test that maker orders get additional rebate"""
    config = PaperConfig(
        enable_rebates=True,
        custom_fee_rate=0.02,
        maker_fee_rate=0.015,  # 1.5% maker fee (lower than taker)
        rebate_tiers={0: 0.10},  # 10% rebate from $0
        maker_rebate_pct=0.25
    )
    engine = PaperEngine(balance=200.0, config=config)
    market = make_market()
    
    # Taker order (market buy)
    taker_order = engine.buy(market, side="UP", amount=50.0)
    taker_rebate_rate = taker_order.rebate_rate
    
    # Maker order (limit order)
    limit_order = engine.limit(market, side="UP", price=0.50, amount=50.0)
    engine._fill_limit(limit_order, 0.55)
    maker_rebate_rate = limit_order.rebate_rate
    
    # Maker should have higher rebate rate (10% + 25% = 35%)
    assert maker_rebate_rate > taker_rebate_rate
    assert maker_rebate_rate == pytest.approx(taker_rebate_rate + 0.25, abs=1e-6)


def test_rebate_statistics():
    """Test rebate statistics calculation"""
    config = PaperConfig(
        enable_rebates=True,
        custom_fee_rate=0.02,
        rebate_tiers={0: 0.10}
    )
    engine = PaperEngine(balance=200.0, config=config)
    market = make_market()
    
    # Make some trades
    engine.buy(market, side="UP", amount=50.0)
    engine.buy(market, side="DOWN", amount=30.0)
    
    stats = engine.get_rebate_stats()
    
    assert stats["total_volume"] == 80.0
    assert stats["total_fees_paid"] > 0
    assert stats["total_rebates_earned"] > 0
    assert stats["net_fees"] == stats["total_fees_paid"] - stats["total_rebates_earned"]
    assert stats["effective_fee_rate"] >= 0
    assert stats["current_rebate_rate"] == 0.10


def test_fee_summary_output():
    """Test fee summary method (just ensures it runs without error)"""
    config = PaperConfig(enable_rebates=True, custom_fee_rate=0.02)
    engine = PaperEngine(balance=100.0, config=config)
    market = make_market()
    
    engine.buy(market, side="UP", amount=10.0)
    
    # Should not raise any exceptions
    engine.fee_summary()


def test_rebate_config_validation():
    """Test rebate configuration validation"""
    # Invalid maker rebate percentage
    with pytest.raises(ValueError):
        PaperConfig(maker_rebate_pct=1.5)  # > 100%
    
    with pytest.raises(ValueError):
        PaperConfig(maker_rebate_pct=-0.1)  # < 0%
    
    # Invalid rebate tier rates
    with pytest.raises(ValueError):
        PaperConfig(rebate_tiers={0: 1.5})  # > 100%


def test_rebate_includes_in_summary():
    """Test that rebates are shown in the summary"""
    config = PaperConfig(
        enable_rebates=True,
        custom_fee_rate=0.02,
        rebate_tiers={0: 0.10}  # 10% rebate from $0
    )
    engine = PaperEngine(balance=100.0, config=config)
    market = make_market()
    
    engine.buy(market, side="UP", amount=10.0)
    
    # Summary should include rebate information
    # We can't easily test the output, but we can check the data
    filled_orders = [o for o in engine.orders() if o.status == "filled"]
    total_rebates = sum(o.rebate_amount for o in filled_orders)
    assert total_rebates > 0


def test_polymarket_fee_with_rebates():
    """Test Polymarket fee mode with rebates"""
    config = PaperConfig(
        fee_mode="polymarket",
        market_category="crypto",
        enable_rebates=True,
        rebate_tiers={0: 0.10}
    )
    engine = PaperEngine(balance=100.0, config=config)
    market = make_market(prices=[0.55, 0.45])
    
    order = engine.buy(market, side="UP", amount=10.0)
    
    # Should have rebate tracking
    assert order.rebate_amount >= 0
    assert order.fee_type == "taker"


def test_geopolitical_zero_fee_with_rebates():
    """Test geopolitical markets have zero fee and no rebates"""
    config = PaperConfig(
        fee_mode="polymarket",
        market_category="geopolitical",
        enable_rebates=True
    )
    engine = PaperEngine(balance=100.0, config=config)
    market = make_market(prices=[0.55, 0.45])
    
    order = engine.buy(market, side="UP", amount=10.0)
    
    # Should have zero fee
    assert order.fee == 0.0
    assert order.rebate_amount == 0.0


def test_rebate_accumulation_across_trades():
    """Test that rebates accumulate correctly across multiple trades"""
    config = PaperConfig(
        enable_rebates=True,
        custom_fee_rate=0.02,
        rebate_tiers={0: 0.05}
    )
    engine = PaperEngine(balance=500.0, config=config)
    market = make_market()
    
    # Make multiple trades
    for _ in range(5):
        engine.buy(market, side="UP", amount=20.0)
    
    # Check accumulation
    assert engine._total_volume == 100.0
    assert engine._total_fees_paid > 0
    assert engine._total_rebates_earned > 0
    
    # Each trade should have rebate
    filled_orders = [o for o in engine.orders() if o.status == "filled"]
    for order in filled_orders:
        assert order.rebate_amount > 0


# ── Risk Management Tests ─────────────────────────────────────────────────────

def test_risk_manager_max_order_size():
    """Test that orders exceeding max_order_size are rejected"""
    config = PaperConfig(max_order_size=50.0, max_risk_per_trade=0.50)  # 50% to allow larger orders
    engine = PaperEngine(balance=100.0, config=config)
    market = make_market()
    
    # Should accept order under limit
    order = engine.buy(market, side="UP", amount=40.0)
    assert order.status == "filled"
    
    # Should reject order over limit
    with pytest.raises(ValueError, match="exceeds maximum"):
        engine.buy(market, side="UP", amount=60.0)


def test_risk_manager_max_position_size():
    """Test that position size limits are enforced"""
    config = PaperConfig(max_position_size=30.0, max_risk_per_trade=0.50)
    engine = PaperEngine(balance=100.0, config=config)
    market = make_market()
    
    # First order should succeed
    order1 = engine.buy(market, side="UP", amount=20.0)
    assert order1.status == "filled"
    
    # Second order should exceed position limit
    with pytest.raises(ValueError, match="Position would exceed maximum size"):
        engine.buy(market, side="UP", amount=15.0)


def test_risk_manager_max_open_positions():
    """Test that max open positions limit is enforced"""
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


def test_risk_manager_daily_loss_limit():
    """Test that daily loss limit stops trading"""
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


def test_risk_manager_max_trades_per_day():
    """Test that max trades per day limit is enforced"""
    config = PaperConfig(max_trades_per_day=3, max_risk_per_trade=0.20)
    engine = PaperEngine(balance=100.0, config=config)
    market = make_market()
    
    # First three trades should succeed (trades counted on order entry)
    for _ in range(3):
        engine.buy(market, side="UP", amount=10.0)
    
    # Fourth should exceed daily limit
    with pytest.raises(ValueError, match="Maximum daily trades"):
        engine.buy(market, side="UP", amount=10.0)


def test_risk_manager_max_risk_per_trade():
    """Test that max risk per trade percentage is enforced"""
    config = PaperConfig(max_risk_per_trade=0.10)  # 10% of balance
    engine = PaperEngine(balance=100.0, config=config)
    market = make_market()
    
    # Should accept order under 10% of balance
    order = engine.buy(market, side="UP", amount=5.0)
    assert order.status == "filled"
    
    # Should reject order over 10% of balance
    with pytest.raises(ValueError, match="exceeds max risk"):
        engine.buy(market, side="UP", amount=15.0)


def test_risk_manager_disable():
    """Test that risk management can be disabled"""
    config = PaperConfig(
        enable_risk_management=False,
        max_order_size=10.0
    )
    engine = PaperEngine(balance=100.0, config=config)
    market = make_market()
    
    # Should succeed even though it exceeds the limit
    order = engine.buy(market, side="UP", amount=50.0)
    assert order.status == "filled"


def test_risk_manager_summary():
    """Test risk summary reporting"""
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


def test_risk_manager_reset_daily_limits():
    """Test manual reset of daily limits"""
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


def test_risk_manager_pnl_tracking():
    """Test that P&L is tracked correctly"""
    config = PaperConfig(max_daily_loss=100.0, max_risk_per_trade=0.50)
    engine = PaperEngine(balance=100.0, config=config)
    market = make_market()
    
    # Make a trade
    engine.buy(market, side="UP", amount=20.0)
    
    # Resolve as a win
    engine.resolve(market, outcome="UP")
    
    summary = engine.get_risk_summary()
    assert summary["daily_pnl"] > 0  # Should have profit


def test_risk_manager_sell_position_pnl():
    """Test that P&L is tracked when selling positions"""
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
