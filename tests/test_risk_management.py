"""
Unit tests for risk management validation.
"""

import pytest
from polyalpha.trading.real import RiskManager, RealTradingConfig, RealPosition
from polyalpha.core import RiskLimitExceeded


class MockMarket:
    """Mock market for testing."""
    def __init__(self, market_id="test-market"):
        self.id = market_id
        self.slug = "test-market"
        self.question = "Test market"


class TestRiskManagerValidation:
    """Tests for RiskManager order validation."""
    
    def setup_method(self):
        """Set up test fixtures."""
        self.config = RealTradingConfig(
            private_key="test-key",
            rpc_url="https://test.com",
            polymarket_api_key="test-api-key",
            max_order_size=100.0,
            max_daily_loss=50.0,
            max_position_size=200.0,
            max_open_positions=5,
            max_risk_per_trade=0.02,
        )
        self.risk_manager = RiskManager(self.config)
    
    def test_max_order_size_pass(self):
        """Test order within max order size limit."""
        market = MockMarket()
        positions = {}
        
        # Should not raise
        self.risk_manager.validate_order(
            amount=50.0,
            balance=1000.0,
            market=market,
            positions=positions,
        )
    
    def test_max_order_size_exceeded(self):
        """Test order exceeding max order size."""
        market = MockMarket()
        positions = {}
        
        with pytest.raises(RiskLimitExceeded) as exc_info:
            self.risk_manager.validate_order(
                amount=150.0,
                balance=1000.0,
                market=market,
                positions=positions,
            )
        
        assert "exceeds maximum" in str(exc_info.value)
    
    def test_max_position_size_pass(self):
        """Test position within max position size limit."""
        market = MockMarket()
        positions = {}  # No existing exposure
        
        # Should not raise
        self.risk_manager.validate_order(
            amount=100.0,
            balance=1000.0,
            market=market,
            positions=positions,
        )
    
    def test_max_position_size_exceeded(self):
        """Test position exceeding max position size."""
        market = MockMarket()
        
        # Create existing position
        existing_position = RealPosition(
            market_id=market.id,
            slug=market.slug,
            question=market.question,
            side="UP",
            shares=100.0,
            avg_price=0.5,
            current_price=0.5,
            cost_basis=150.0,
            current_value=150.0,
        )
        positions = {f"{market.id}:UP": existing_position}
        
        with pytest.raises(RiskLimitExceeded) as exc_info:
            self.risk_manager.validate_order(
                amount=100.0,  # Would make total 250 > 200 limit
                balance=1000.0,
                market=market,
                positions=positions,
            )
        
        assert "exceed maximum size" in str(exc_info.value)
    
    def test_max_open_positions_pass(self):
        """Test within max open positions limit."""
        market = MockMarket()
        positions = {}
        
        # Should not raise
        self.risk_manager.validate_order(
            amount=10.0,
            balance=1000.0,
            market=market,
            positions=positions,
        )
    
    def test_max_open_positions_exceeded(self):
        """Test exceeding max open positions."""
        market = MockMarket()
        positions = {}
        
        # Create 5 existing positions (at the limit)
        for i in range(5):
            pos = RealPosition(
                market_id=f"market-{i}",
                slug=f"market-{i}",
                question=f"Market {i}",
                side="UP",
                shares=10.0,
                avg_price=0.5,
                current_price=0.5,
                cost_basis=10.0,
                current_value=10.0,
            )
            positions[f"market-{i}:UP"] = pos
        
        with pytest.raises(RiskLimitExceeded) as exc_info:
            self.risk_manager.validate_order(
                amount=10.0,
                balance=1000.0,
                market=market,
                positions=positions,
            )
        
        assert "Maximum open positions" in str(exc_info.value)
    
    def test_daily_loss_limit_pass(self):
        """Test within daily loss limit."""
        market = MockMarket()
        positions = {}
        
        # Set some daily P&L but within limit
        self.risk_manager.daily_pnl = -30.0  # Under 50 limit
        
        # Should not raise
        self.risk_manager.validate_order(
            amount=10.0,
            balance=1000.0,
            market=market,
            positions=positions,
        )
    
    def test_daily_loss_limit_exceeded(self):
        """Test exceeding daily loss limit."""
        market = MockMarket()
        positions = {}
        
        # Set daily P&L beyond limit
        self.risk_manager.daily_pnl = -60.0  # Over 50 limit
        
        with pytest.raises(RiskLimitExceeded) as exc_info:
            self.risk_manager.validate_order(
                amount=10.0,
                balance=1000.0,
                market=market,
                positions=positions,
            )
        
        assert "Daily loss" in str(exc_info.value)
    
    def test_max_risk_per_trade_pass(self):
        """Test within max risk per trade."""
        market = MockMarket()
        positions = {}
        
        # 2% of 1000 = 20, so 10 should be fine
        self.risk_manager.validate_order(
            amount=10.0,
            balance=1000.0,
            market=market,
            positions=positions,
        )
    
    def test_max_risk_per_trade_exceeded(self):
        """Test exceeding max risk per trade."""
        market = MockMarket()
        positions = {}
        
        # 2% of 1000 = 20, so 30 should fail
        with pytest.raises(RiskLimitExceeded) as exc_info:
            self.risk_manager.validate_order(
                amount=30.0,
                balance=1000.0,
                market=market,
                positions=positions,
            )
        
        assert "max risk" in str(exc_info.value)


class TestRiskManagerDailyTracking:
    """Tests for RiskManager daily P&L tracking."""
    
    def setup_method(self):
        """Set up test fixtures."""
        self.config = RealTradingConfig(
            private_key="test-key",
            rpc_url="https://test.com",
            polymarket_api_key="test-api-key",
            max_daily_loss=50.0,
        )
        self.risk_manager = RiskManager(self.config)
    
    def test_record_trade_pnl(self):
        """Test recording trade P&L."""
        self.risk_manager.record_trade(10.0)
        assert self.risk_manager.daily_pnl == 10.0
        assert self.risk_manager.daily_trades == 1
    
    def test_record_multiple_trades(self):
        """Test recording multiple trades."""
        self.risk_manager.record_trade(10.0)
        self.risk_manager.record_trade(-5.0)
        self.risk_manager.record_trade(15.0)
        
        assert self.risk_manager.daily_pnl == 20.0
        assert self.risk_manager.daily_trades == 3
    
    def test_record_loss(self):
        """Test recording a loss."""
        self.risk_manager.record_trade(-25.0)
        assert self.risk_manager.daily_pnl == -25.0
        assert self.risk_manager.daily_trades == 1
    
    def test_initialize_daily_balance(self):
        """Test initializing daily balance."""
        self.risk_manager.initialize_daily_balance(1000.0)
        assert self.risk_manager.daily_start_balance == 1000.0
    
    def test_initialize_daily_balance_only_once(self):
        """Test that daily balance only initializes once."""
        self.risk_manager.initialize_daily_balance(1000.0)
        self.risk_manager.initialize_daily_balance(2000.0)
        
        # Should still be 1000
        assert self.risk_manager.daily_start_balance == 1000.0
    
    def test_get_daily_stats(self):
        """Test getting daily statistics."""
        self.risk_manager.initialize_daily_balance(1000.0)
        self.risk_manager.record_trade(50.0)
        
        stats = self.risk_manager.get_daily_stats()
        
        assert stats["daily_pnl"] == 50.0
        assert stats["daily_trades"] == 1
        assert stats["daily_start_balance"] == 1000.0
        assert stats["daily_pct_change"] == 5.0  # 50/1000 * 100
        assert stats["daily_loss_limit"] == 50.0
    
    def test_get_daily_stats_with_loss(self):
        """Test daily stats with loss."""
        self.risk_manager.initialize_daily_balance(1000.0)
        self.risk_manager.record_trade(-30.0)
        
        stats = self.risk_manager.get_daily_stats()
        
        assert stats["daily_pnl"] == -30.0
        assert stats["daily_pct_change"] == -3.0
        assert stats["daily_loss_remaining"] == 20.0  # 50 - 30


class TestRiskManagerStopLoss:
    """Tests for RiskManager stop loss checks."""
    
    def setup_method(self):
        """Set up test fixtures."""
        self.config = RealTradingConfig(
            private_key="test-key",
            rpc_url="https://test.com",
            polymarket_api_key="test-api-key",
        )
        self.risk_manager = RiskManager(self.config)
    
    def test_check_stop_loss_up_triggered(self):
        """Test stop loss trigger for UP position."""
        position = RealPosition(
            market_id="test",
            slug="test",
            question="Test",
            side="UP",
            shares=10.0,
            avg_price=0.5,
            current_price=0.5,
            cost_basis=5.0,
            current_value=5.0,
            stop_loss=0.45,
        )
        
        # Price at or below stop loss should trigger
        assert self.risk_manager.check_stop_loss(position, 0.45) == True
        assert self.risk_manager.check_stop_loss(position, 0.44) == True
        assert self.risk_manager.check_stop_loss(position, 0.50) == False
    
    def test_check_stop_loss_down_triggered(self):
        """Test stop loss trigger for DOWN position."""
        position = RealPosition(
            market_id="test",
            slug="test",
            question="Test",
            side="DOWN",
            shares=10.0,
            avg_price=0.5,
            current_price=0.5,
            cost_basis=5.0,
            current_value=5.0,
            stop_loss=0.55,
        )
        
        # Price at or above stop loss should trigger
        assert self.risk_manager.check_stop_loss(position, 0.55) == True
        assert self.risk_manager.check_stop_loss(position, 0.56) == True
        assert self.risk_manager.check_stop_loss(position, 0.50) == False
    
    def test_check_stop_loss_none(self):
        """Test stop loss check when stop_loss is None."""
        position = RealPosition(
            market_id="test",
            slug="test",
            question="Test",
            side="UP",
            shares=10.0,
            avg_price=0.5,
            current_price=0.5,
            cost_basis=5.0,
            current_value=5.0,
            stop_loss=None,
        )
        
        assert self.risk_manager.check_stop_loss(position, 0.40) == False


class TestRiskManagerTakeProfit:
    """Tests for RiskManager take profit checks."""
    
    def setup_method(self):
        """Set up test fixtures."""
        self.config = RealTradingConfig(
            private_key="test-key",
            rpc_url="https://test.com",
            polymarket_api_key="test-api-key",
        )
        self.risk_manager = RiskManager(self.config)
    
    def test_check_take_profit_up_triggered(self):
        """Test take profit trigger for UP position."""
        position = RealPosition(
            market_id="test",
            slug="test",
            question="Test",
            side="UP",
            shares=10.0,
            avg_price=0.5,
            current_price=0.5,
            cost_basis=5.0,
            current_value=5.0,
            take_profit=0.60,
        )
        
        # Price at or above take profit should trigger
        assert self.risk_manager.check_take_profit(position, 0.60) == True
        assert self.risk_manager.check_take_profit(position, 0.65) == True
        assert self.risk_manager.check_take_profit(position, 0.55) == False
    
    def test_check_take_profit_down_triggered(self):
        """Test take profit trigger for DOWN position."""
        position = RealPosition(
            market_id="test",
            slug="test",
            question="Test",
            side="DOWN",
            shares=10.0,
            avg_price=0.5,
            current_price=0.5,
            cost_basis=5.0,
            current_value=5.0,
            take_profit=0.40,
        )
        
        # Price at or below take profit should trigger
        assert self.risk_manager.check_take_profit(position, 0.40) == True
        assert self.risk_manager.check_take_profit(position, 0.35) == True
        assert self.risk_manager.check_take_profit(position, 0.45) == False
    
    def test_check_take_profit_none(self):
        """Test take profit check when take_profit is None."""
        position = RealPosition(
            market_id="test",
            slug="test",
            question="Test",
            side="UP",
            shares=10.0,
            avg_price=0.5,
            current_price=0.5,
            cost_basis=5.0,
            current_value=5.0,
            take_profit=None,
        )
        
        assert self.risk_manager.check_take_profit(position, 0.70) == False


class TestRiskManagerPositionSizeCalculation:
    """Tests for RiskManager position size calculation."""
    
    def setup_method(self):
        """Set up test fixtures."""
        self.config = RealTradingConfig(
            private_key="test-key",
            rpc_url="https://test.com",
            polymarket_api_key="test-api-key",
            max_risk_per_trade=0.02,
        )
        self.risk_manager = RiskManager(self.config)
    
    def test_calculate_position_size_with_risk(self):
        """Test position size calculation based on risk."""
        # Balance 1000, risk 2% = $20 risk
        # Entry 0.50, stop 0.45, diff = 0.05
        # Position size = 20 / (0.05/0.50) = 20 / 0.10 = 200
        result = self.risk_manager.calculate_position_size_with_risk(
            balance=1000.0,
            entry_price=0.50,
            stop_loss=0.45,
            side="UP",
        )
        
        assert result == pytest.approx(200.0, rel=0.01)
    
    def test_calculate_position_size_capped_at_balance(self):
        """Test position size capped at balance."""
        result = self.risk_manager.calculate_position_size_with_risk(
            balance=100.0,
            entry_price=0.50,
            stop_loss=0.49,  # Very tight stop
            side="UP",
        )
        
        # Should not exceed balance
        assert result <= 100.0
    
    def test_calculate_position_size_zero_diff(self):
        """Test position size with zero price diff."""
        result = self.risk_manager.calculate_position_size_with_risk(
            balance=1000.0,
            entry_price=0.50,
            stop_loss=0.50,  # Same as entry
            side="UP",
        )
        
        # Should use fallback calculation
        assert result > 0


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
