"""
Unit tests for position sizing strategies.
"""

import pytest
from polyalpha.trading.real import (
    FixedPositionSizer,
    PercentagePositionSizer,
    KellyPositionSizer,
    HybridPositionSizer,
)


class MockMarket:
    """Mock market for testing."""
    def __init__(self, up_price=0.5, down_price=0.5):
        self.up_price = up_price
        self.down_price = down_price


class TestFixedPositionSizer:
    """Tests for FixedPositionSizer."""
    
    def test_fixed_amount_within_balance(self):
        """Test fixed amount when within balance."""
        sizer = FixedPositionSizer(amount=10.0)
        market = MockMarket()
        
        result = sizer.calculate_size(balance=100.0, market=market, side="UP")
        assert result == 10.0
    
    def test_fixed_amount_exceeds_balance(self):
        """Test fixed amount when it exceeds balance."""
        sizer = FixedPositionSizer(amount=100.0)
        market = MockMarket()
        
        result = sizer.calculate_size(balance=50.0, market=market, side="UP")
        assert result == 50.0  # Should cap at balance
    
    def test_fixed_amount_zero_balance(self):
        """Test fixed amount with zero balance."""
        sizer = FixedPositionSizer(amount=10.0)
        market = MockMarket()
        
        result = sizer.calculate_size(balance=0.0, market=market, side="UP")
        assert result == 0.0
    
    def test_fixed_amount_ignores_confidence(self):
        """Test that fixed amount ignores confidence parameter."""
        sizer = FixedPositionSizer(amount=10.0)
        market = MockMarket()
        
        result_low = sizer.calculate_size(balance=100.0, market=market, side="UP", confidence=0.1)
        result_high = sizer.calculate_size(balance=100.0, market=market, side="UP", confidence=0.9)
        
        assert result_low == 10.0
        assert result_high == 10.0


class TestPercentagePositionSizer:
    """Tests for PercentagePositionSizer."""
    
    def test_percentage_calculation(self):
        """Test percentage-based calculation."""
        sizer = PercentagePositionSizer(percentage=0.05)  # 5%
        market = MockMarket()
        
        result = sizer.calculate_size(balance=1000.0, market=market, side="UP")
        assert result == 50.0  # 5% of 1000
    
    def test_percentage_100_percent(self):
        """Test 100% percentage."""
        sizer = PercentagePositionSizer(percentage=1.0)
        market = MockMarket()
        
        result = sizer.calculate_size(balance=100.0, market=market, side="UP")
        assert result == 100.0
    
    def test_percentage_small_balance(self):
        """Test percentage with small balance."""
        sizer = PercentagePositionSizer(percentage=0.10)
        market = MockMarket()
        
        result = sizer.calculate_size(balance=10.0, market=market, side="UP")
        assert result == 1.0
    
    def test_percentage_ignores_confidence(self):
        """Test that percentage ignores confidence parameter."""
        sizer = PercentagePositionSizer(percentage=0.10)
        market = MockMarket()
        
        result = sizer.calculate_size(balance=100.0, market=market, side="UP", confidence=0.9)
        assert result == 10.0


class TestKellyPositionSizer:
    """Tests for KellyPositionSizer."""
    
    def test_kelly_with_edge(self):
        """Test Kelly calculation with positive edge."""
        sizer = KellyPositionSizer(kelly_fraction=0.25, min_confidence=0.55)
        market = MockMarket(up_price=0.50, down_price=0.50)
        
        # Confidence 0.70 vs implied 0.50 = edge
        result = sizer.calculate_size(balance=100.0, market=market, side="UP", confidence=0.70, price=0.50)
        
        # Kelly fraction = (0.70 - 0.50) / (1 - 0.50) = 0.40
        # With quarter Kelly: 0.40 * 0.25 = 0.10
        # Position size: 100 * 0.10 = 10
        assert result == pytest.approx(10.0, rel=0.01)
    
    def test_kelly_no_edge(self):
        """Test Kelly calculation with no edge."""
        sizer = KellyPositionSizer(kelly_fraction=0.25, min_confidence=0.55)
        market = MockMarket(up_price=0.50, down_price=0.50)
        
        # Confidence 0.50 vs implied 0.50 = no edge
        result = sizer.calculate_size(balance=100.0, market=market, side="UP", confidence=0.50, price=0.50)
        assert result == 0.0
    
    def test_kelly_low_confidence(self):
        """Test Kelly with confidence below minimum."""
        sizer = KellyPositionSizer(kelly_fraction=0.25, min_confidence=0.55)
        market = MockMarket(up_price=0.50, down_price=0.50)
        
        # Confidence 0.50 < min_confidence 0.55
        result = sizer.calculate_size(balance=100.0, market=market, side="UP", confidence=0.50, price=0.50)
        assert result == 0.0
    
    def test_kelly_cap_at_50_percent(self):
        """Test that Kelly never bets more than 50% of bankroll."""
        sizer = KellyPositionSizer(kelly_fraction=1.0, min_confidence=0.55)  # Full Kelly
        market = MockMarket(up_price=0.50, down_price=0.50)
        
        # Very high confidence
        result = sizer.calculate_size(balance=100.0, market=market, side="UP", confidence=0.90, price=0.50)
        
        # Kelly fraction = (0.90 - 0.50) / (1 - 0.50) = 0.80
        # But capped at 0.50
        assert result == pytest.approx(50.0, rel=0.01)
    
    def test_kelly_down_side(self):
        """Test Kelly calculation for DOWN side."""
        sizer = KellyPositionSizer(kelly_fraction=0.25, min_confidence=0.55)
        market = MockMarket(up_price=0.50, down_price=0.50)
        
        result = sizer.calculate_size(balance=100.0, market=market, side="DOWN", confidence=0.70, price=0.50)
        assert result == pytest.approx(10.0, rel=0.01)
    
    def test_kelly_fraction_parameter(self):
        """Test Kelly fraction parameter (quarter Kelly vs half Kelly)."""
        sizer_quarter = KellyPositionSizer(kelly_fraction=0.25, min_confidence=0.55)
        sizer_half = KellyPositionSizer(kelly_fraction=0.50, min_confidence=0.55)
        market = MockMarket(up_price=0.50, down_price=0.50)
        
        result_quarter = sizer_quarter.calculate_size(balance=100.0, market=market, side="UP", confidence=0.70, price=0.50)
        result_half = sizer_half.calculate_size(balance=100.0, market=market, side="UP", confidence=0.70, price=0.50)
        
        assert result_half > result_quarter


class TestHybridPositionSizer:
    """Tests for HybridPositionSizer."""
    
    def test_hybrid_fixed_base(self):
        """Test hybrid with fixed base strategy."""
        sizer = HybridPositionSizer(
            base_strategy="fixed",
            base_amount=10.0,
            enable_kelly_adjustment=False,
        )
        market = MockMarket()
        
        result = sizer.calculate_size(balance=100.0, market=market, side="UP")
        assert result == 10.0
    
    def test_hybrid_percentage_base(self):
        """Test hybrid with percentage base strategy."""
        sizer = HybridPositionSizer(
            base_strategy="percentage",
            base_amount=0.05,
            enable_kelly_adjustment=False,
        )
        market = MockMarket()
        
        result = sizer.calculate_size(balance=100.0, market=market, side="UP")
        assert result == 5.0
    
    def test_hybrid_with_kelly_adjustment(self):
        """Test hybrid with Kelly adjustment enabled."""
        sizer = HybridPositionSizer(
            base_strategy="percentage",
            base_amount=0.05,
            enable_kelly_adjustment=True,
            kelly_fraction=0.25,
        )
        market = MockMarket(up_price=0.50, down_price=0.50)
        
        # Base: 5% of 100 = 5
        # With Kelly adjustment (confidence 0.70 vs implied 0.50): should increase
        result = sizer.calculate_size(balance=100.0, market=market, side="UP", confidence=0.70, price=0.50)
        
        assert result > 5.0
    
    def test_hybrid_max_size_limit(self):
        """Test hybrid max size limit."""
        sizer = HybridPositionSizer(
            base_strategy="percentage",
            base_amount=0.50,  # 50%
            enable_kelly_adjustment=False,
            max_size=20.0,
        )
        market = MockMarket()
        
        result = sizer.calculate_size(balance=100.0, market=market, side="UP")
        assert result == 20.0  # Capped at max_size
    
    def test_hybrid_min_size_limit(self):
        """Test hybrid min size limit."""
        sizer = HybridPositionSizer(
            base_strategy="percentage",
            base_amount=0.001,  # 0.1%
            enable_kelly_adjustment=False,
            min_size=5.0,
        )
        market = MockMarket()
        
        result = sizer.calculate_size(balance=100.0, market=market, side="UP")
        assert result == 5.0  # Raised to min_size
    
    def test_hybrid_balance_limit(self):
        """Test hybrid respects balance limit."""
        sizer = HybridPositionSizer(
            base_strategy="percentage",
            base_amount=0.50,  # 50%
            enable_kelly_adjustment=False,
        )
        market = MockMarket()
        
        result = sizer.calculate_size(balance=10.0, market=market, side="UP")
        assert result == 10.0  # Capped at balance
    
    def test_hybrid_no_kelly_adjustment_low_confidence(self):
        """Test hybrid without Kelly adjustment ignores low confidence."""
        sizer = HybridPositionSizer(
            base_strategy="percentage",
            base_amount=0.05,
            enable_kelly_adjustment=False,
        )
        market = MockMarket()
        
        result = sizer.calculate_size(balance=100.0, market=market, side="UP", confidence=0.1)
        assert result == 5.0  # Still uses base percentage


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
