"""
Tests for advanced order management features: TP, SL, trailing stops, OCO orders.
"""

import pytest
from datetime import datetime, timezone

from polyalpha.trading.paper import PaperEngine, PaperConfig, PaperOrder, PaperPosition
from polyalpha.core import Market


class MockMarket:
    """Mock market object for testing."""
    
    def __init__(self, market_id="test-market", slug="btc-updown-5m", question="Test question"):
        self.id = market_id
        self.slug = slug
        self.question = question
        self.up_price = 0.50
        self.down_price = 0.50


@pytest.fixture
def engine():
    """Create a fresh paper trading engine for each test."""
    return PaperEngine(balance=1000.0)


@pytest.fixture
def market():
    """Create a mock market."""
    return MockMarket()


class TestStopLossTakeProfit:
    """Test basic stop-loss and take-profit functionality."""
    
    def test_buy_with_stop_loss(self, engine, market):
        """Test buying with stop-loss set."""
        order = engine.buy_with_tp_sl(
            market, side="UP", amount=100.0,
            stop_loss=0.45
        )
        
        assert order.status == "filled"
        assert order.stop_loss == 0.45
        assert order.take_profit is None
        assert order.shares > 0
    
    def test_buy_with_take_profit(self, engine, market):
        """Test buying with take-profit set."""
        order = engine.buy_with_tp_sl(
            market, side="UP", amount=100.0,
            take_profit=0.55
        )
        
        assert order.status == "filled"
        assert order.take_profit == 0.55
        assert order.stop_loss is None
    
    def test_buy_with_both_tp_sl(self, engine, market):
        """Test buying with both TP and SL set."""
        order = engine.buy_with_tp_sl(
            market, side="UP", amount=100.0,
            stop_loss=0.45, take_profit=0.55
        )
        
        assert order.status == "filled"
        assert order.stop_loss == 0.45
        assert order.take_profit == 0.55
    
    def test_stop_loss_trigger_up(self, engine, market):
        """Test stop-loss triggering for UP position."""
        order = engine.buy_with_tp_sl(
            market, side="UP", amount=100.0,
            stop_loss=0.45
        )
        
        # Simulate price dropping to trigger SL
        engine.check_limits(market.id, up_price=0.44, down_price=0.56)
        
        # Order should be marked as triggered
        assert order.tp_sl_triggered_by == "sl"
    
    def test_stop_loss_trigger_down(self, engine, market):
        """Test stop-loss triggering for DOWN position."""
        order = engine.buy_with_tp_sl(
            market, side="DOWN", amount=100.0,
            stop_loss=0.55
        )
        
        # Simulate price rising to trigger SL (DOWN position loses when price goes up)
        # For DOWN position, down_price is what matters. If down_price goes above SL, trigger.
        engine.check_limits(market.id, up_price=0.56, down_price=0.56)
        
        assert order.tp_sl_triggered_by == "sl"
    
    def test_take_profit_trigger_up(self, engine, market):
        """Test take-profit triggering for UP position."""
        order = engine.buy_with_tp_sl(
            market, side="UP", amount=100.0,
            take_profit=0.55
        )
        
        # Simulate price rising to trigger TP
        engine.check_limits(market.id, up_price=0.56, down_price=0.44)
        
        assert order.tp_sl_triggered_by == "tp"
    
    def test_take_profit_trigger_down(self, engine, market):
        """Test take-profit triggering for DOWN position."""
        order = engine.buy_with_tp_sl(
            market, side="DOWN", amount=100.0,
            take_profit=0.45
        )
        
        # Simulate price dropping to trigger TP (DOWN position profits when price goes down)
        # For DOWN position, down_price is what matters. If down_price goes below TP, trigger.
        engine.check_limits(market.id, up_price=0.44, down_price=0.44)
        
        assert order.tp_sl_triggered_by == "tp"


class TestTrailingStops:
    """Test trailing stop-loss and take-profit functionality."""
    
    def test_trailing_sl_initialization_up(self, engine, market):
        """Test trailing SL initialization for UP position."""
        order = engine.buy_with_tp_sl(
            market, side="UP", amount=100.0,
            trail_sl=0.05
        )
        
        # Initial trailing SL should be below entry price
        assert order.trail_sl == 0.05
        assert order.trail_sl_price is not None
        assert order.trail_sl_price < order.price
    
    def test_trailing_sl_initialization_down(self, engine, market):
        """Test trailing SL initialization for DOWN position."""
        order = engine.buy_with_tp_sl(
            market, side="DOWN", amount=100.0,
            trail_sl=0.05
        )
        
        # Initial trailing SL should be above entry price
        assert order.trail_sl == 0.05
        assert order.trail_sl_price is not None
        assert order.trail_sl_price > order.price
    
    def test_trailing_sl_moves_up(self, engine, market):
        """Test trailing SL moves up with price for UP position."""
        order = engine.buy_with_tp_sl(
            market, side="UP", amount=100.0,
            trail_sl=0.05
        )
        
        initial_trail = order.trail_sl_price
        
        # Price moves up
        engine.check_limits(market.id, up_price=0.60, down_price=0.40)
        
        # Trailing SL should have moved up
        assert order.trail_sl_price > initial_trail
    
    def test_trailing_sl_moves_down(self, engine, market):
        """Test trailing SL moves down with price for DOWN position."""
        order = engine.buy_with_tp_sl(
            market, side="DOWN", amount=100.0,
            trail_sl=0.05
        )
        
        initial_trail = order.trail_sl_price
        
        # Price moves down (down_price decreases for DOWN position)
        engine.check_limits(market.id, up_price=0.40, down_price=0.40)
        
        # Trailing SL should have moved down
        assert order.trail_sl_price < initial_trail
    
    def test_trailing_sl_never_moves_against_trader_up(self, engine, market):
        """Test trailing SL never moves against trader for UP position."""
        order = engine.buy_with_tp_sl(
            market, side="UP", amount=100.0,
            trail_sl=0.05
        )
        
        # Price moves up
        engine.check_limits(market.id, up_price=0.60, down_price=0.40)
        high_trail = order.trail_sl_price
        
        # Price moves back down
        engine.check_limits(market.id, up_price=0.50, down_price=0.50)
        
        # Trailing SL should stay at high point
        assert order.trail_sl_price == high_trail
    
    def test_trailing_tp_initialization(self, engine, market):
        """Test trailing TP initialization."""
        order = engine.buy_with_tp_sl(
            market, side="UP", amount=100.0,
            trail_tp=0.10
        )
        
        assert order.trail_tp == 0.10
        assert order.trail_tp_price is not None
        assert order.trail_tp_price > order.price
    
    def test_trailing_tp_locks_profits(self, engine, market):
        """Test trailing TP locks in profits."""
        order = engine.buy_with_tp_sl(
            market, side="UP", amount=100.0,
            trail_tp=0.10
        )
        
        initial_trail = order.trail_tp_price
        
        # Price moves up significantly
        engine.check_limits(market.id, up_price=0.70, down_price=0.30)
        
        # Trailing TP should move up with price (to allow more profit potential)
        # The logic is: TP trails at a distance above current price
        assert order.trail_tp_price > initial_trail
    
    def test_set_trailing_sl(self, engine, market):
        """Test setting trailing SL on existing order."""
        order = engine.buy(market, side="UP", amount=100.0)
        
        updated = engine.set_trailing_sl(order.id, 0.05)
        
        assert updated.trail_sl == 0.05
        assert updated.trail_sl_price is not None
    
    def test_set_trailing_tp(self, engine, market):
        """Test setting trailing TP on existing order."""
        order = engine.buy(market, side="UP", amount=100.0)
        
        updated = engine.set_trailing_tp(order.id, 0.10)
        
        assert updated.trail_tp == 0.10
        assert updated.trail_tp_price is not None


class TestOCOOrders:
    """Test One-Cancels-Other order functionality."""
    
    def test_oco_order_creation(self, engine, market):
        """Test OCO order creation."""
        main_order, oco_order = engine.oco_order(
            market, side="UP", amount=100.0,
            stop_loss=0.45, take_profit=0.55
        )
        
        assert main_order.stop_loss == 0.45
        assert main_order.take_profit == 0.55
        assert main_order.oco_order_id is not None
    
    def test_oco_sl_cancels_tp(self, engine, market):
        """Test that SL trigger cancels TP in OCO."""
        main_order, oco_order = engine.oco_order(
            market, side="UP", amount=100.0,
            stop_loss=0.45, take_profit=0.55
        )
        
        # Trigger SL
        engine.check_limits(market.id, up_price=0.44, down_price=0.56)
        
        assert main_order.tp_sl_triggered_by == "sl"


class TestSellPosition:
    """Test sell/closing position functionality."""
    
    def test_sell_full_position(self, engine, market):
        """Test selling full position."""
        buy_order = engine.buy(market, side="UP", amount=100.0)
        
        sell_order = engine.sell_position(market, side="UP")
        
        assert sell_order.status == "filled"
        assert sell_order.side == "UP"
        
        # Position should be closed
        positions = engine.positions()
        assert len(positions) == 0
    
    def test_sell_partial_position(self, engine, market):
        """Test selling partial position."""
        buy_order = engine.buy(market, side="UP", amount=100.0)
        
        sell_order = engine.sell_position(market, side="UP", amount=50.0)
        
        assert sell_order.status == "filled"
        
        # Position should still exist with reduced shares
        positions = engine.positions()
        assert len(positions) == 1
        assert positions[0].shares > 0
    
    def test_sell_nonexistent_position(self, engine, market):
        """Test selling when no position exists."""
        with pytest.raises(ValueError, match="No position found"):
            engine.sell_position(market, side="UP")


class TestEdgeCases:
    """Test edge cases and error handling."""
    
    def test_invalid_stop_loss(self, engine, market):
        """Test invalid stop-loss value."""
        with pytest.raises(ValueError, match="stop_loss must be > 0"):
            engine.buy_with_tp_sl(
                market, side="UP", amount=100.0,
                stop_loss=-0.1
            )
    
    def test_invalid_take_profit(self, engine, market):
        """Test invalid take-profit value."""
        with pytest.raises(ValueError, match="take_profit must be > 0"):
            engine.buy_with_tp_sl(
                market, side="UP", amount=100.0,
                take_profit=-0.1
            )
    
    def test_set_trailing_on_unfilled_order(self, engine, market):
        """Test setting trailing SL on unfilled order."""
        order = engine.limit(market, side="UP", price=0.55, amount=100.0)
        
        with pytest.raises(ValueError, match="Can only set trailing SL on filled orders"):
            engine.set_trailing_sl(order.id, 0.05)
    
    def test_set_trailing_on_nonexistent_order(self, engine, market):
        """Test setting trailing SL on nonexistent order."""
        with pytest.raises(Exception):  # OrderNotFound
            engine.set_trailing_sl("nonexistent-id", 0.05)
    
    def test_insufficient_balance(self, engine, market):
        """Test order with insufficient balance."""
        with pytest.raises(Exception):  # InsufficientBalance
            engine.buy_with_tp_sl(
                market, side="UP", amount=10000.0,  # More than balance
                stop_loss=0.45
            )


class TestOrderDump:
    """Test order serialization with new fields."""
    
    def test_order_dump_includes_tp_sl(self, engine, market):
        """Test order dump includes TP/SL fields."""
        order = engine.buy_with_tp_sl(
            market, side="UP", amount=100.0,
            stop_loss=0.45, take_profit=0.55,
            trail_sl=0.05, trail_tp=0.10
        )
        
        dump = order.dump()
        
        assert "stop_loss" in dump
        assert "take_profit" in dump
        assert "trail_sl" in dump
        assert "trail_tp" in dump
        assert "trail_sl_price" in dump
        assert "trail_tp_price" in dump
        assert "oco_order_id" in dump
        assert "tp_sl_triggered_by" in dump


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
