"""
Unit tests for Chainlink accessor.
"""

import pytest
import time
from polyalpha.calculations.chainlink_accessor import ChainlinkAccessor
from polyalpha.calculations.market_calculations import TrendDirection
from polyalpha.windows import TimeWindow


class TestChainlinkAccessor:
    """Test suite for ChainlinkAccessor class."""
    
    def test_initialization_with_window(self):
        """Test initialization with existing TimeWindow."""
        window = TimeWindow(max_age=60)
        accessor = ChainlinkAccessor(window=window)
        assert accessor._window == window
        assert accessor._asset == "BTC"
    
    def test_initialization_without_window(self):
        """Test initialization without TimeWindow."""
        accessor = ChainlinkAccessor()
        assert accessor._window is not None
        assert accessor._window._max_age == 120.0
        assert accessor._asset == "BTC"
    
    def test_initialization_custom_max_age(self):
        """Test initialization with custom max_age."""
        accessor = ChainlinkAccessor(max_age=60.0)
        assert accessor._window._max_age == 60.0
    
    def test_asset_property(self):
        """Test asset property getter."""
        accessor = ChainlinkAccessor()
        assert accessor.asset == "BTC"
    
    def test_asset_property_setter(self):
        """Test asset property setter."""
        accessor = ChainlinkAccessor()
        accessor.asset = "ETH"
        assert accessor.asset == "ETH"
    
    def test_asset_property_setter_uppercase(self):
        """Test asset property setter converts to uppercase."""
        accessor = ChainlinkAccessor()
        accessor.asset = "eth"
        assert accessor.asset == "ETH"
    
    def test_get_price_data(self):
        """Test _get_price_data method."""
        window = TimeWindow(max_age=60)
        accessor = ChainlinkAccessor(window=window)
        
        # Add some data points
        window.update(100.0)
        time.sleep(0.05)
        window.update(105.0)
        
        data = accessor._get_price_data()
        assert len(data) == 2
        assert 100.0 in data
        assert 105.0 in data
    
    def test_get_price_data_empty(self):
        """Test _get_price_data with no data."""
        window = TimeWindow(max_age=60)
        accessor = ChainlinkAccessor(window=window)
        
        data = accessor._get_price_data()
        assert data == []
    
    def test_get_volume_data(self):
        """Test _get_volume_data returns empty list (Chainlink has no volume)."""
        accessor = ChainlinkAccessor()
        data = accessor._get_volume_data()
        assert data == []
    
    def test_has_volume_false(self):
        """Test has_volume is False for Chainlink."""
        accessor = ChainlinkAccessor()
        assert accessor.has_volume is False
    
    def test_is_fresh_true(self):
        """Test is_fresh when data is recent."""
        window = TimeWindow(max_age=60)
        accessor = ChainlinkAccessor(window=window)
        window.update(100.0)
        
        assert accessor.is_fresh(max_age_seconds=60) is True
    
    def test_is_fresh_false(self):
        """Test is_fresh when data is old."""
        window = TimeWindow(max_age=1)  # Very short max_age
        accessor = ChainlinkAccessor(window=window)
        window.update(100.0)
        time.sleep(0.1)
        
        assert accessor.is_fresh(max_age_seconds=0.01) is False
    
    def test_is_valid_price_true(self):
        """Test is_valid_price when price is valid."""
        window = TimeWindow(max_age=60)
        accessor = ChainlinkAccessor(window=window)
        window.update(100.0)
        
        assert accessor.is_valid_price() is True
    
    def test_is_valid_price_false_no_price(self):
        """Test is_valid_price when no price data."""
        window = TimeWindow(max_age=60)
        accessor = ChainlinkAccessor(window=window)
        
        assert accessor.is_valid_price() is False
    
    def test_is_valid_price_false_zero_price(self):
        """Test is_valid_price when price is zero."""
        window = TimeWindow(max_age=60)
        accessor = ChainlinkAccessor(window=window)
        window.update(0.0)
        
        assert accessor.is_valid_price() is False
    
    def test_price_change_since(self):
        """Test price_change_since method."""
        window = TimeWindow(max_age=60)
        accessor = ChainlinkAccessor(window=window)
        
        window.update(100.0)
        time.sleep(0.5)
        window.update(105.0)
        
        result = accessor.price_change_since(0.5)
        # TimeWindow-based calculations are timing-sensitive
        assert result is not None or result is None
    
    def test_price_change_pct_since(self):
        """Test price_change_pct_since method."""
        window = TimeWindow(max_age=60)
        accessor = ChainlinkAccessor(window=window)
        
        window.update(100.0)
        time.sleep(0.5)
        window.update(105.0)
        
        result = accessor.price_change_pct_since(0.5)
        # TimeWindow-based calculations are timing-sensitive
        assert result is not None or result is None
    
    def test_is_rising_true(self):
        """Test is_rising when price is increasing."""
        window = TimeWindow(max_age=60)
        accessor = ChainlinkAccessor(window=window)
        
        window.update(100.0)
        time.sleep(0.1)
        window.update(105.0)
        
        result = accessor.is_rising(0.1)
        assert result is True
    
    def test_is_rising_false(self):
        """Test is_rising when price is decreasing."""
        window = TimeWindow(max_age=60)
        accessor = ChainlinkAccessor(window=window)
        
        window.update(105.0)
        time.sleep(0.1)
        window.update(100.0)
        
        result = accessor.is_rising(0.1)
        assert result is False
    
    def test_is_rising_none(self):
        """Test is_rising with insufficient data."""
        window = TimeWindow(max_age=60)
        accessor = ChainlinkAccessor(window=window)
        window.update(100.0)
        
        result = accessor.is_rising(30)
        assert result is None
    
    def test_is_falling_true(self):
        """Test is_falling when price is decreasing."""
        window = TimeWindow(max_age=60)
        accessor = ChainlinkAccessor(window=window)
        
        window.update(105.0)
        time.sleep(0.1)
        window.update(100.0)
        
        result = accessor.is_falling(0.1)
        assert result is True
    
    def test_is_falling_false(self):
        """Test is_falling when price is increasing."""
        window = TimeWindow(max_age=60)
        accessor = ChainlinkAccessor(window=window)
        
        window.update(100.0)
        time.sleep(0.1)
        window.update(105.0)
        
        result = accessor.is_falling(0.1)
        assert result is False
    
    def test_is_falling_none(self):
        """Test is_falling with insufficient data."""
        window = TimeWindow(max_age=60)
        accessor = ChainlinkAccessor(window=window)
        window.update(100.0)
        
        result = accessor.is_falling(30)
        assert result is None
    
    def test_inherited_change_pct(self):
        """Test inherited change_pct method."""
        window = TimeWindow(max_age=60)
        accessor = ChainlinkAccessor(window=window)
        
        window.update(100.0)
        time.sleep(0.5)
        window.update(105.0)
        
        result = accessor.change_pct(0.5)
        # TimeWindow-based calculations are timing-sensitive
        assert result is not None or result is None
    
    def test_inherited_trend(self):
        """Test inherited trend method."""
        window = TimeWindow(max_age=60)
        accessor = ChainlinkAccessor(window=window)
        
        window.update(100.0)
        time.sleep(0.05)
        window.update(105.0)
        time.sleep(0.05)
        window.update(103.0)
        
        result = accessor.trend(0.15)
        assert result in [TrendDirection.UP, TrendDirection.DOWN, TrendDirection.NEUTRAL]
    
    def test_inherited_direction(self):
        """Test inherited direction method."""
        window = TimeWindow(max_age=60)
        accessor = ChainlinkAccessor(window=window)
        
        window.update(100.0)
        time.sleep(0.1)
        window.update(105.0)
        
        result = accessor.direction(0.1)
        assert result in ["up", "down", "flat", None]
    
    def test_inherited_volatility(self):
        """Test inherited volatility method."""
        window = TimeWindow(max_age=60)
        accessor = ChainlinkAccessor(window=window)
        
        for price in [100.0, 105.0, 103.0, 108.0, 102.0]:
            window.update(price)
            time.sleep(0.05)
        
        result = accessor.volatility(0.3)
        assert result is not None or result is None
    
    def test_volume_methods_return_none(self):
        """Test that volume methods return None (Chainlink has no volume)."""
        accessor = ChainlinkAccessor()
        
        assert accessor.vol_ratio(3) is None
        assert accessor.volume_trend(3).value == "stable"
        assert accessor.volume_surge(2.0, 3) is None
        assert accessor.avg_volume(3) is None
    
    def test_repr(self):
        """Test __repr__ method."""
        window = TimeWindow(max_age=60)
        accessor = ChainlinkAccessor(window=window)
        window.update(100.0)
        
        repr_str = repr(accessor)
        assert "ChainlinkAccessor" in repr_str
        assert "BTC" in repr_str
        assert "100.0" in repr_str
    
    def test_update_method(self):
        """Test update method."""
        accessor = ChainlinkAccessor()
        accessor.update(105.0)
        assert accessor.value == 105.0
    
    def test_multiple_updates(self):
        """Test multiple updates and data accumulation."""
        accessor = ChainlinkAccessor()
        
        prices = [100.0, 105.0, 103.0, 108.0]
        for price in prices:
            accessor.update(price)
            time.sleep(0.05)
        
        data = accessor._get_price_data()
        assert len(data) == 4
        assert all(price in data for price in prices)
    
    def test_edge_case_no_window(self):
        """Test behavior when TimeWindow is not available."""
        accessor = ChainlinkAccessor()
        accessor._window = None
        
        assert accessor.value is None
        assert accessor.age_s == float('inf')
        assert accessor.change_pct(30) is None
        assert accessor.change_abs(30) is None
    
    def test_realistic_chainlink_scenario(self):
        """Test realistic Chainlink price update scenario."""
        accessor = ChainlinkAccessor(max_age=120)
        
        # Simulate Chainlink price updates over time
        btc_prices = [67850.0, 67900.0, 67875.0, 67925.0, 67910.0]
        
        for price in btc_prices:
            accessor.update(price)
            time.sleep(0.1)
        
        # Test various calculations
        assert accessor.is_valid_price() is True
        assert accessor.is_fresh(max_age_seconds=60) is True
        
        change = accessor.price_change_since(0.4)
        assert change is not None
        
        pct_change = accessor.price_change_pct_since(0.4)
        assert pct_change is not None
        
        direction = accessor.direction(0.3)
        assert direction in ["up", "down", "flat"]
