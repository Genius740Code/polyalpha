"""
Property-based tests using Hypothesis — run with: pytest tests/property/test_property_based.py

These tests use Hypothesis to generate random inputs and test invariants and properties
that should always hold true, regardless of the input values.
"""

import pytest
from hypothesis import given, strategies as st, assume
import pandas as pd

from polyalpha.analysis.indicators import IndicatorCalculator
from polyalpha.trading.retry import retry_on_error
from polyalpha.trading.real_config import get_preset, add_preset


@pytest.mark.property
class TestIndicatorProperties:
    """Property-based tests for technical indicators."""

    def _make_dataset(self, prices):
        """Create a dataset from a list of prices."""
        n = len(prices)
        dates = pd.date_range("2025-01-01", periods=n, freq="1h")
        data = pd.DataFrame({
            "open": [p - 0.5 for p in prices],
            "high": [p + 0.5 for p in prices],
            "low": [p - 0.5 for p in prices],
            "close": prices,
            "volume": [1000 + i * 10 for i in range(n)],
        }, index=dates)
        return data

    @pytest.mark.property
    @given(st.lists(st.floats(min_value=1.0, max_value=1000.0), min_size=50, max_size=1000))
    def test_sma_always_between_min_and_max(self, prices):
        """Test that SMA is always between min and max of the data."""
        data = self._make_dataset(prices)
        indicators = IndicatorCalculator(data)
        
        sma = indicators.sma(20)
        valid_sma = sma.dropna()
        
        if len(valid_sma) > 0:
            min_price = data["close"].min()
            max_price = data["close"].max()
            
            # All SMA values should be within the price range
            for val in valid_sma:
                assert min_price <= val <= max_price

    @pytest.mark.property
    @given(st.lists(st.floats(min_value=1.0, max_value=1000.0), min_size=50, max_size=1000))
    def test_rsi_always_between_0_and_100(self, prices):
        """Test that RSI is always between 0 and 100."""
        data = self._make_dataset(prices)
        indicators = IndicatorCalculator(data)
        
        rsi = indicators.rsi(14)
        valid_rsi = rsi.dropna()
        
        # All RSI values should be between 0 and 100
        for val in valid_rsi:
            assert 0 <= val <= 100

    @pytest.mark.property
    @given(st.lists(st.floats(min_value=1.0, max_value=1000.0), min_size=50, max_size=1000))
    def test_ema_always_between_min_and_max(self, prices):
        """Test that EMA is always between min and max of the data."""
        data = self._make_dataset(prices)
        indicators = IndicatorCalculator(data)
        
        ema = indicators.ema(20)
        valid_ema = ema.dropna()
        
        if len(valid_ema) > 0:
            min_price = data["close"].min()
            max_price = data["close"].max()
            
            # All EMA values should be within the price range
            for val in valid_ema:
                assert min_price <= val <= max_price

    @pytest.mark.property
    @given(st.lists(st.floats(min_value=1.0, max_value=1000.0), min_size=50, max_size=1000))
    def test_bollinger_bands_ordering(self, prices):
        """Test that Bollinger Bands are ordered: lower <= middle <= upper."""
        data = self._make_dataset(prices)
        indicators = IndicatorCalculator(data)
        
        bb = indicators.bollinger_bands(20, 2.0)
        
        valid_lower = bb["lower"].dropna()
        valid_middle = bb["middle"].dropna()
        valid_upper = bb["upper"].dropna()
        
        # Check ordering for valid values
        for i in range(min(len(valid_lower), len(valid_middle), len(valid_upper))):
            assert valid_lower.iloc[i] <= valid_middle.iloc[i] <= valid_upper.iloc[i]

    @pytest.mark.property
    @given(st.lists(st.floats(min_value=1.0, max_value=1000.0), min_size=50, max_size=1000))
    def test_stochastic_always_between_0_and_100(self, prices):
        """Test that Stochastic oscillator is always between 0 and 100."""
        data = self._make_dataset(prices)
        indicators = IndicatorCalculator(data)
        
        stoch = indicators.stochastic(14, 3)
        
        valid_k = stoch["k"].dropna()
        valid_d = stoch["d"].dropna()
        
        # All Stochastic values should be between 0 and 100
        for val in valid_k:
            assert 0 <= val <= 100
        for val in valid_d:
            assert 0 <= val <= 100

    @pytest.mark.property
    @given(st.lists(st.floats(min_value=1.0, max_value=1000.0), min_size=50, max_size=1000))
    def test_macd_histogram_equals_macd_minus_signal(self, prices):
        """Test that MACD histogram equals MACD line minus signal line."""
        data = self._make_dataset(prices)
        indicators = IndicatorCalculator(data)
        
        macd = indicators.macd(12, 26, 9)
        
        valid_macd = macd["macd"].dropna()
        valid_signal = macd["signal"].dropna()
        valid_histogram = macd["histogram"].dropna()
        
        # Check that histogram = macd - signal for valid values
        min_len = min(len(valid_macd), len(valid_signal), len(valid_histogram))
        for i in range(min_len):
            expected = valid_macd.iloc[i] - valid_signal.iloc[i]
            actual = valid_histogram.iloc[i]
            assert abs(expected - actual) < 0.01  # Allow small floating point error


@pytest.mark.property
class TestRetryProperties:
    """Property-based tests for retry decorator."""

    @pytest.mark.property
    @given(st.integers(min_value=1, max_value=10), st.integers(min_value=0, max_value=5))
    def test_retry_attempts_respected(self, max_attempts, fail_before):
        """Test that retry decorator respects max_attempts."""
        call_count = [0]
        
        @retry_on_error(max_attempts=max_attempts, delay=0.001, retry_on=(Exception,))
        def failing_function():
            call_count[0] += 1
            if call_count[0] <= fail_before:
                raise ValueError("Fail")
            return "success"
        
        if fail_before >= max_attempts:
            # Should fail after max_attempts
            with pytest.raises(ValueError):
                failing_function()
            assert call_count[0] == max_attempts
        else:
            # Should succeed
            result = failing_function()
            assert result == "success"
            assert call_count[0] == fail_before + 1

    @pytest.mark.property
    @given(st.integers(min_value=1, max_value=5), st.floats(min_value=0.001, max_value=0.1))
    def test_retry_delay_non_negative(self, max_attempts, delay):
        """Test that retry delays are always non-negative."""
        call_count = [0]
        delays = []
        
        @retry_on_error(max_attempts=max_attempts, delay=delay)
        def always_fail():
            call_count[0] += 1
            raise ValueError("Fail")
        
        import time
        original_sleep = time.sleep
        def mock_sleep(d):
            delays.append(d)
        
        time.sleep = mock_sleep
        try:
            with pytest.raises(ValueError):
                always_fail()
        finally:
            time.sleep = original_sleep
        
        # All delays should be non-negative
        for d in delays:
            assert d >= 0


@pytest.mark.property
class TestConfigProperties:
    """Property-based tests for configuration presets."""

    @pytest.mark.property
    @given(st.text(min_size=1, max_size=20).filter(lambda x: x.isalnum()))
    def test_add_preset_retrievable(self, preset_name):
        """Test that added presets can be retrieved."""
        # Use a unique name to avoid conflicts
        unique_name = f"TEST_{preset_name}"
        
        config = {
            "require_confirmation": True,
            "max_order_size": 100.0,
            "max_daily_loss": 100.0,
            "max_position_size": 1000.0,
            "max_open_positions": 5,
            "max_positions_per_market": 1,
            "position_sizing": "fixed",
            "fixed_amount": 10.0,
            "percentage_of_balance": 0.05,
            "kelly_fraction": 0.25,
            "enable_stop_loss": True,
            "default_stop_loss_pct": 0.20,
            "enable_take_profit": True,
            "default_take_profit_pct": 0.50,
            "max_risk_per_trade": 0.02,
            "enable_position_scaling": True,
            "min_profit_for_scaling": 0.10,
            "max_scale_additions": 2,
            "enable_position_reduction": True,
            "enable_hedging": False,
            "max_hedge_ratio": 0.3,
            "slippage_tolerance": 0.05,
            "order_timeout": 60,
            "retry_attempts": 3,
            "retry_delay": 1.0,
            "fee_mode": "polymarket",
            "log_all_orders": True,
            "log_balance_updates": True,
        }
        
        add_preset(unique_name, config)
        retrieved = get_preset(unique_name)
        
        assert retrieved == config

    @pytest.mark.property
    @given(st.text(min_size=1, max_size=20).filter(lambda x: x.isalnum()))
    def test_preset_name_uppercase(self, preset_name):
        """Test that preset names are converted to uppercase."""
        unique_name = f"test_{preset_name}"
        
        config = {
            "require_confirmation": True,
            "max_order_size": 100.0,
            "max_daily_loss": 100.0,
            "max_position_size": 1000.0,
            "max_open_positions": 5,
            "max_positions_per_market": 1,
            "position_sizing": "fixed",
            "fixed_amount": 10.0,
            "percentage_of_balance": 0.05,
            "kelly_fraction": 0.25,
            "enable_stop_loss": True,
            "default_stop_loss_pct": 0.20,
            "enable_take_profit": True,
            "default_take_profit_pct": 0.50,
            "max_risk_per_trade": 0.02,
            "enable_position_scaling": True,
            "min_profit_for_scaling": 0.10,
            "max_scale_additions": 2,
            "enable_position_reduction": True,
            "enable_hedging": False,
            "max_hedge_ratio": 0.3,
            "slippage_tolerance": 0.05,
            "order_timeout": 60,
            "retry_attempts": 3,
            "retry_delay": 1.0,
            "fee_mode": "polymarket",
            "log_all_orders": True,
            "log_balance_updates": True,
        }
        
        add_preset(unique_name, config)
        
        # Should be retrievable with uppercase name
        retrieved = get_preset(unique_name.upper())
        assert retrieved == config


@pytest.mark.property
class TestDataProperties:
    """Property-based tests for data operations."""

    @pytest.mark.property
    @given(st.lists(st.floats(min_value=1.0, max_value=1000.0), min_size=10, max_size=100))
    def test_mean_within_range(self, values):
        """Test that mean is always within the range of values."""
        if len(values) == 0:
            return
        
        mean_val = sum(values) / len(values)
        min_val = min(values)
        max_val = max(values)
        
        assert min_val <= mean_val <= max_val

    @pytest.mark.property
    @given(st.lists(st.floats(min_value=1.0, max_value=1000.0), min_size=10, max_size=100))
    def test_sorted_list_monotonic(self, values):
        """Test that sorted list is monotonic."""
        sorted_values = sorted(values)
        
        for i in range(len(sorted_values) - 1):
            assert sorted_values[i] <= sorted_values[i + 1]

    @pytest.mark.property
    @given(st.lists(st.floats(min_value=1.0, max_value=1000.0), min_size=10, max_size=100))
    def test_reverse_sorted_monotonic_decreasing(self, values):
        """Test that reverse sorted list is monotonically decreasing."""
        reverse_sorted = sorted(values, reverse=True)
        
        for i in range(len(reverse_sorted) - 1):
            assert reverse_sorted[i] >= reverse_sorted[i + 1]

    @pytest.mark.property
    @given(st.lists(st.integers(min_value=0, max_value=100), min_size=10, max_size=100))
    def test_sum_of_parts_equals_whole(self, values):
        """Test that sum of individual values equals total sum."""
        total = sum(values)
        partial_sums = [sum(values[:i]) for i in range(1, len(values) + 1)]
        
        # Last partial sum should equal total
        if len(partial_sums) > 0:
            assert partial_sums[-1] == total


@pytest.mark.property
class TestMathProperties:
    """Property-based tests for mathematical operations."""

    @pytest.mark.property
    @given(st.floats(min_value=-1000.0, max_value=1000.0), st.floats(min_value=-1000.0, max_value=1000.0))
    def test_commutative_addition(self, a, b):
        """Test that addition is commutative."""
        assert a + b == b + a

    @pytest.mark.property
    @given(st.floats(min_value=-1000.0, max_value=1000.0), st.floats(min_value=-1000.0, max_value=1000.0), st.floats(min_value=-1000.0, max_value=1000.0))
    def test_associative_addition(self, a, b, c):
        """Test that addition is approximately associative (floating point)."""
        assert (a + b) + c == pytest.approx(a + (b + c))

    @pytest.mark.property
    @given(st.floats(min_value=-1000.0, max_value=1000.0))
    def test_additive_identity(self, a):
        """Test that adding zero returns the same value."""
        assert a + 0 == a

    @pytest.mark.property
    @given(st.floats(min_value=-1000.0, max_value=1000.0), st.floats(min_value=-1000.0, max_value=1000.0))
    def test_multiplication_commutative(self, a, b):
        """Test that multiplication is commutative."""
        assert a * b == b * a

    @pytest.mark.property
    @given(st.floats(min_value=0.1, max_value=1000.0))  # Avoid zero
    def test_multiplicative_identity(self, a):
        """Test that multiplying by one returns the same value."""
        assume(a != 0)
        assert a * 1 == a

    @pytest.mark.property
    @given(st.floats(min_value=-1000.0, max_value=1000.0))
    def test_absolute_value_non_negative(self, a):
        """Test that absolute value is always non-negative."""
        assert abs(a) >= 0

    @pytest.mark.property
    @given(st.floats(min_value=-1000.0, max_value=1000.0))
    def test_absolute_value_symmetric(self, a):
        """Test that abs(a) == abs(-a)."""
        assert abs(a) == abs(-a)
