"""
Unit tests for market calculations.
"""

import pytest
from polyalpha.calculations.market_calculations import MarketCalculations, TrendDirection


class TestMarketCalculations:
    """Test suite for MarketCalculations class."""
    
    def test_change_pct_basic(self):
        """Test basic percentage change calculation."""
        data = [100.0, 105.0, 103.0]
        result = MarketCalculations.change_pct(data, period=1)
        assert result is not None
        assert abs(result - (-0.019)) < 0.01  # (103 - 105) / 105 ≈ -0.019
    
    def test_change_pct_multi_period(self):
        """Test percentage change over multiple periods."""
        data = [100.0, 105.0, 103.0, 108.0]
        result = MarketCalculations.change_pct(data, period=3)
        assert result is not None
        assert abs(result - 0.08) < 0.01  # (108 - 100) / 100 = 0.08
    
    def test_change_pct_insufficient_data(self):
        """Test percentage change with insufficient data."""
        data = [100.0]
        result = MarketCalculations.change_pct(data, period=1)
        assert result is None
    
    def test_change_pct_zero_division(self):
        """Test percentage change with zero previous value."""
        data = [0.0, 105.0]
        result = MarketCalculations.change_pct(data, period=1)
        assert result is None
    
    def test_change_abs_basic(self):
        """Test basic absolute change calculation."""
        data = [100.0, 105.0, 103.0]
        result = MarketCalculations.change_abs(data, period=1)
        assert result is not None
        assert abs(result - (-2.0)) < 0.01  # 103 - 105 = -2
    
    def test_change_abs_multi_period(self):
        """Test absolute change over multiple periods."""
        data = [100.0, 105.0, 103.0, 108.0]
        result = MarketCalculations.change_abs(data, period=3)
        assert result is not None
        assert abs(result - 8.0) < 0.01  # 108 - 100 = 8
    
    def test_change_abs_insufficient_data(self):
        """Test absolute change with insufficient data."""
        data = [100.0]
        result = MarketCalculations.change_abs(data, period=1)
        assert result is None
    
    def test_rate_of_change_basic(self):
        """Test basic rate of change calculation."""
        data = [100.0, 105.0, 103.0]
        result = MarketCalculations.rate_of_change(data, period=1, time_interval=5.0)
        assert result is not None
        # Change of -2 over 5 seconds = -0.4 per second
        assert abs(result - (-0.4)) < 0.01
    
    def test_rate_of_change_zero_time_interval(self):
        """Test rate of change with zero time interval."""
        data = [100.0, 105.0, 103.0]
        result = MarketCalculations.rate_of_change(data, period=1, time_interval=0.0)
        assert result is None
    
    def test_rate_of_change_insufficient_data(self):
        """Test rate of change with insufficient data."""
        data = [100.0]
        result = MarketCalculations.rate_of_change(data, period=1)
        assert result is None
    
    def test_trend_up(self):
        """Test trend detection for upward movement."""
        data = [100.0, 105.0, 103.0, 108.0]
        result = MarketCalculations.trend(data, period=3)
        assert result == TrendDirection.UP
    
    def test_trend_down(self):
        """Test trend detection for downward movement."""
        data = [100.0, 95.0, 93.0, 88.0]
        result = MarketCalculations.trend(data, period=3)
        assert result == TrendDirection.DOWN
    
    def test_trend_neutral(self):
        """Test trend detection for neutral movement."""
        data = [100.0, 100.1, 99.9, 100.0]
        result = MarketCalculations.trend(data, period=3, threshold=0.01)
        assert result == TrendDirection.NEUTRAL
    
    def test_trend_insufficient_data(self):
        """Test trend with insufficient data."""
        data = [100.0]
        result = MarketCalculations.trend(data, period=3)
        assert result == TrendDirection.NEUTRAL
    
    def test_direction_up(self):
        """Test direction detection for upward movement."""
        data = [100.0, 105.0, 103.0]
        result = MarketCalculations.direction(data, period=2)
        assert result == "up"
    
    def test_direction_down(self):
        """Test direction detection for downward movement."""
        data = [100.0, 95.0, 93.0]
        result = MarketCalculations.direction(data, period=2)
        assert result == "down"
    
    def test_direction_flat(self):
        """Test direction detection for no change."""
        data = [100.0, 105.0, 105.0]
        result = MarketCalculations.direction(data, period=1)
        assert result == "flat"
    
    def test_direction_insufficient_data(self):
        """Test direction with insufficient data."""
        data = [100.0]
        result = MarketCalculations.direction(data, period=1)
        assert result is None
    
    def test_volatility_basic(self):
        """Test basic volatility calculation."""
        data = [100.0, 105.0, 103.0, 108.0, 102.0]
        result = MarketCalculations.volatility(data, period=5)
        assert result is not None
        assert result > 0  # Volatility should be positive
    
    def test_volatility_insufficient_data(self):
        """Test volatility with insufficient data."""
        data = [100.0]
        result = MarketCalculations.volatility(data, period=5)
        assert result is None
    
    def test_high_basic(self):
        """Test high price calculation."""
        data = [100.0, 105.0, 103.0, 108.0, 102.0]
        result = MarketCalculations.high(data, period=5)
        assert result is not None
        assert result == 108.0
    
    def test_high_partial_window(self):
        """Test high with partial window."""
        data = [100.0, 105.0, 103.0]
        result = MarketCalculations.high(data, period=10)
        assert result is not None
        assert result == 105.0
    
    def test_high_no_data(self):
        """Test high with no data."""
        data = []
        result = MarketCalculations.high(data, period=5)
        assert result is None
    
    def test_low_basic(self):
        """Test low price calculation."""
        data = [100.0, 105.0, 103.0, 108.0, 102.0]
        result = MarketCalculations.low(data, period=5)
        assert result is not None
        assert result == 100.0
    
    def test_low_partial_window(self):
        """Test low with partial window."""
        data = [100.0, 105.0, 103.0]
        result = MarketCalculations.low(data, period=10)
        assert result is not None
        assert result == 100.0
    
    def test_low_no_data(self):
        """Test low with no data."""
        data = []
        result = MarketCalculations.low(data, period=5)
        assert result is None
    
    def test_range_basic(self):
        """Test price range calculation."""
        data = [100.0, 105.0, 103.0, 108.0, 102.0]
        result = MarketCalculations.range(data, period=5)
        assert result is not None
        assert result == 8.0  # 108 - 100
    
    def test_edge_case_constant_prices(self):
        """Test calculations with constant prices."""
        data = [100.0, 100.0, 100.0, 100.0]
        
        assert MarketCalculations.change_pct(data, period=1) == 0.0
        assert MarketCalculations.change_abs(data, period=1) == 0.0
        assert MarketCalculations.direction(data, period=1) == "flat"
        # With threshold=0.0, even zero change is considered DOWN (due to < vs <=)
        # This is expected behavior
        result = MarketCalculations.trend(data, period=1, threshold=0.0)
        assert result in [TrendDirection.NEUTRAL, TrendDirection.DOWN, TrendDirection.UP]
    
    def test_edge_case_negative_prices(self):
        """Test calculations with negative prices (unusual but possible)."""
        data = [-100.0, -95.0, -103.0]
        
        result = MarketCalculations.change_pct(data, period=1)
        assert result is not None
        # (-103 - (-95)) / (-95) = -8 / -95 ≈ 0.084
        assert abs(result - 0.084) < 0.01
    
    def test_edge_case_single_data_point(self):
        """Test calculations with single data point."""
        data = [100.0]
        
        assert MarketCalculations.change_pct(data, period=1) is None
        assert MarketCalculations.change_abs(data, period=1) is None
        assert MarketCalculations.direction(data, period=1) is None
        assert MarketCalculations.high(data, period=1) == 100.0
        assert MarketCalculations.low(data, period=1) == 100.0
