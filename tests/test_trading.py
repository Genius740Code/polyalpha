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
