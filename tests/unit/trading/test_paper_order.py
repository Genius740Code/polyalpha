"""
Paper trading order management tests — run with: pytest tests/unit/trading/test_paper_order.py
"""

import pytest
from polyalpha.trading.paper import PaperEngine, PaperConfig, _slug_label
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


# ── Order dump tests ───────────────────────────────────────────────────────────

@pytest.mark.unit
def test_order_dump(engine, make_market):
    """Test order dump functionality."""
    market = make_market()
    order = engine.buy(market, side="UP", amount=10.0)
    
    dump = order.dump()
    
    assert dump["id"] == order.id
    assert dump["side"] == "UP"
    assert dump["status"] == "filled"
    assert dump["is_limit"] == False
    assert "filled_at" in dump


# ── Slug label helper tests ───────────────────────────────────────────────────

@pytest.mark.unit
def test_slug_label():
    """Test slug label helper function."""
    assert _slug_label("btc-updown-5m-1234567") == "BTC 5m"
    assert _slug_label("eth-updown-15m-9999") == "ETH 15m"


# ── Fee calculation tests ────────────────────────────────────────────────────────

@pytest.mark.unit
def test_fee_mode_zero(make_market):
    """Test zero fee mode."""
    config = PaperConfig(fee_mode="zero")
    engine = PaperEngine(balance=100.0, config=config)
    market = make_market()
    order = engine.buy(market, side="UP", amount=10.0)
    assert order.fee == 0.0


@pytest.mark.unit
def test_fee_mode_custom(make_market):
    """Test custom fee mode."""
    config = PaperConfig(fee_mode="custom", custom_fee_rate=0.03)
    engine = PaperEngine(balance=100.0, config=config)
    market = make_market()
    order = engine.buy(market, side="UP", amount=10.0)
    assert order.fee == pytest.approx(10.0 * 0.03, abs=1e-6)


@pytest.mark.unit
def test_fee_mode_polymarket_geopolitical(make_market):
    """Test Polymarket fee mode for geopolitical markets."""
    config = PaperConfig(fee_mode="polymarket", market_category="geopolitical")
    engine = PaperEngine(balance=100.0, config=config)
    market = make_market()
    order = engine.buy(market, side="UP", amount=10.0)
    assert order.fee == 0.0


@pytest.mark.unit
def test_fee_mode_polymarket_crypto(make_market):
    """Test Polymarket fee mode for crypto markets."""
    config = PaperConfig(fee_mode="polymarket", market_category="crypto")
    engine = PaperEngine(balance=100.0, config=config)
    market = make_market()
    order = engine.buy(market, side="UP", amount=10.0)
    # Fee should be calculated using Polymarket formula
    assert order.fee >= 0.0


@pytest.mark.unit
def test_fee_mode_polymarket_sports(make_market):
    """Test Polymarket fee mode for sports markets."""
    config = PaperConfig(fee_mode="polymarket", market_category="sports")
    engine = PaperEngine(balance=100.0, config=config)
    market = make_market()
    order = engine.buy(market, side="UP", amount=10.0)
    # Fee should be calculated using sports fee rate
    assert order.fee >= 0.0


# ── Slippage tests ───────────────────────────────────────────────────────────────

@pytest.mark.unit
def test_slippage_disabled(make_market):
    """Test slippage disabled."""
    config = PaperConfig(slippage_pct=0.0)
    engine = PaperEngine(balance=100.0, config=config)
    market = make_market()
    order = engine.buy(market, side="UP", amount=10.0)
    assert order.status == "filled"


@pytest.mark.unit
def test_slippage_enabled(make_market):
    """Test slippage enabled."""
    config = PaperConfig(slippage_pct=0.05)
    engine = PaperEngine(balance=100.0, config=config)
    market = make_market(prices=[0.50, 0.50])
    order = engine.buy(market, side="UP", amount=10.0)
    assert order.status == "filled"
    # Price should be higher due to slippage
    assert order.price > 0.50


@pytest.mark.unit
def test_slippage_no_fill_threshold(make_market):
    """Test slippage no-fill threshold."""
    config = PaperConfig(slippage_pct=0.15, max_slippage_no_fill=0.10)
    engine = PaperEngine(balance=100.0, config=config)
    market = make_market(prices=[0.50, 0.50])
    order = engine.buy(market, side="UP", amount=10.0)
    # Order should not fill due to excessive slippage
    assert order.status == "cancelled"


@pytest.mark.unit
def test_slippage_down_side(make_market):
    """Test slippage for DOWN side."""
    config = PaperConfig(slippage_pct=0.05)
    engine = PaperEngine(balance=100.0, config=config)
    market = make_market(prices=[0.50, 0.50])
    order = engine.buy(market, side="DOWN", amount=10.0)
    assert order.status == "filled"
    # Price should be lower due to slippage for DOWN side
    assert order.price < 0.50


# ── Fill probability tests ───────────────────────────────────────────────────────

@pytest.mark.unit
def test_fill_probability_always(make_market):
    """Test fill probability always fills."""
    config = PaperConfig(fill_probability=1.0)
    engine = PaperEngine(balance=100.0, config=config)
    market = make_market()
    engine.limit(market, side="UP", price=0.90, amount=20.0)
    engine.check_limits(market.id, up_price=0.92, down_price=0.08)
    orders = engine.orders()
    assert orders[0].status == "filled"


@pytest.mark.unit
def test_fill_probability_never(make_market):
    """Test fill probability never fills."""
    config = PaperConfig(fill_probability=0.0)
    engine = PaperEngine(balance=100.0, config=config)
    market = make_market()
    engine.limit(market, side="UP", price=0.90, amount=20.0)
    engine.check_limits(market.id, up_price=0.92, down_price=0.08)
    orders = engine.orders()
    # Order should be cancelled due to fill probability
    assert orders[0].status == "cancelled"


# ── Config update tests ───────────────────────────────────────────────────────────

@pytest.mark.unit
def test_set_config(make_market):
    """Test setting config."""
    engine = PaperEngine(balance=100.0)
    config = PaperConfig(fee_mode="zero")
    engine.set_config(config)
    assert engine.config.fee_mode == "zero"


@pytest.mark.unit
def test_backward_compatibility_no_config(make_market):
    """Test backward compatibility without config."""
    engine = PaperEngine(balance=100.0)
    market = make_market()
    order = engine.buy(market, side="UP", amount=10.0)
    assert order.status == "filled"
    # Should use default custom fee mode with 2% fee
    assert order.fee == pytest.approx(10.0 * 0.02, abs=1e-6)


# ── Fee Rebate Tests ───────────────────────────────────────────────────────────────

@pytest.mark.unit
def test_rebate_tracking_enabled(make_market):
    """Test that rebates are tracked when enabled."""
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


@pytest.mark.unit
def test_rebate_tracking_disabled(make_market):
    """Test that rebates are not tracked when disabled."""
    config = PaperConfig(enable_rebates=False, custom_fee_rate=0.02)
    engine = PaperEngine(balance=100.0, config=config)
    market = make_market()
    
    order = engine.buy(market, side="UP", amount=10.0)
    
    # Check no rebates
    assert order.rebate_amount == 0.0
    assert order.rebate_rate == 0.0
    assert engine._total_rebates_earned == 0.0


@pytest.mark.unit
def test_volume_based_rebate_tiers(make_market):
    """Test volume-based rebate tier progression."""
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


@pytest.mark.unit
def test_maker_vs_taker_rebate(make_market):
    """Test that maker orders get additional rebate."""
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


@pytest.mark.unit
def test_rebate_statistics(make_market):
    """Test rebate statistics calculation."""
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


@pytest.mark.unit
def test_fee_summary_output(make_market):
    """Test fee summary method (just ensures it runs without error)."""
    config = PaperConfig(enable_rebates=True, custom_fee_rate=0.02)
    engine = PaperEngine(balance=100.0, config=config)
    market = make_market()
    
    engine.buy(market, side="UP", amount=10.0)
    
    # Should not raise any exceptions
    engine.fee_summary()


@pytest.mark.unit
def test_rebate_config_validation():
    """Test rebate configuration validation."""
    # Invalid maker rebate percentage
    with pytest.raises(ValueError):
        PaperConfig(maker_rebate_pct=1.5)  # > 100%
    
    with pytest.raises(ValueError):
        PaperConfig(maker_rebate_pct=-0.1)  # < 0%
    
    # Invalid rebate tier rates
    with pytest.raises(ValueError):
        PaperConfig(rebate_tiers={0: 1.5})  # > 100%


@pytest.mark.unit
def test_rebate_includes_in_summary(make_market):
    """Test that rebates are shown in the summary."""
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


@pytest.mark.unit
def test_polymarket_fee_with_rebates(make_market):
    """Test Polymarket fee mode with rebates."""
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


@pytest.mark.unit
def test_geopolitical_zero_fee_with_rebates(make_market):
    """Test geopolitical markets have zero fee and no rebates."""
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


@pytest.mark.unit
def test_rebate_accumulation_across_trades(make_market):
    """Test that rebates accumulate correctly across multiple trades."""
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
