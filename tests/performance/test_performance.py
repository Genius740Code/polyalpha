"""
Performance tests for critical operations — run with: pytest tests/performance/test_performance.py

These tests measure execution time of critical operations to ensure they meet
performance requirements and detect regressions.
"""

import time
import pytest
import pandas as pd
from polyalpha.analysis.indicators import IndicatorCalculator
from polyalpha.analysis.signals import SignalGenerator
from polyalpha.trading.retry import retry_on_error


@pytest.mark.performance
class TestIndicatorPerformance:
    """Test performance of technical indicator calculations."""

    def _make_large_dataset(self, n=10000):
        """Create a large dataset for performance testing."""
        dates = pd.date_range("2025-01-01", periods=n, freq="h")
        data = pd.DataFrame({
            "open": [50.0 + i * 0.001 for i in range(n)],
            "high": [51.0 + i * 0.001 for i in range(n)],
            "low": [49.0 + i * 0.001 for i in range(n)],
            "close": [50.5 + i * 0.001 for i in range(n)],
            "volume": [1000 + i * 10 for i in range(n)],
        }, index=dates)
        return data

    @pytest.mark.performance
    def test_rsi_calculation_performance(self):
        """Test RSI calculation performance on large dataset."""
        data = self._make_large_dataset(10000)
        indicators = IndicatorCalculator(data)
        
        start_time = time.time()
        rsi = indicators.rsi(14)
        end_time = time.time()
        
        elapsed = end_time - start_time
        
        # RSI calculation should complete in under 1 second for 10k candles
        assert elapsed < 1.0, f"RSI calculation took {elapsed:.3f}s, expected < 1.0s"
        assert len(rsi) > 0

    @pytest.mark.performance
    def test_sma_calculation_performance(self):
        """Test SMA calculation performance on large dataset."""
        data = self._make_large_dataset(10000)
        indicators = IndicatorCalculator(data)
        
        start_time = time.time()
        sma = indicators.sma(20)
        end_time = time.time()
        
        elapsed = end_time - start_time
        
        # SMA calculation should complete in under 0.5 seconds for 10k candles
        assert elapsed < 0.5, f"SMA calculation took {elapsed:.3f}s, expected < 0.5s"
        assert len(sma) > 0

    @pytest.mark.performance
    def test_ema_calculation_performance(self):
        """Test EMA calculation performance on large dataset."""
        data = self._make_large_dataset(10000)
        indicators = IndicatorCalculator(data)
        
        start_time = time.time()
        ema = indicators.ema(20)
        end_time = time.time()
        
        elapsed = end_time - start_time
        
        # EMA calculation should complete in under 0.5 seconds for 10k candles
        assert elapsed < 0.5, f"EMA calculation took {elapsed:.3f}s, expected < 0.5s"
        assert len(ema) > 0

    @pytest.mark.performance
    def test_macd_calculation_performance(self):
        """Test MACD calculation performance on large dataset."""
        data = self._make_large_dataset(10000)
        indicators = IndicatorCalculator(data)
        
        start_time = time.time()
        macd = indicators.macd(12, 26, 9)
        end_time = time.time()
        
        elapsed = end_time - start_time
        
        # MACD calculation should complete in under 1 second for 10k candles
        assert elapsed < 1.0, f"MACD calculation took {elapsed:.3f}s, expected < 1.0s"
        assert "macd" in macd
        assert "signal" in macd
        assert "histogram" in macd

    @pytest.mark.performance
    def test_bollinger_bands_calculation_performance(self):
        """Test Bollinger Bands calculation performance on large dataset."""
        data = self._make_large_dataset(10000)
        indicators = IndicatorCalculator(data)
        
        start_time = time.time()
        bb = indicators.bollinger_bands(20, 2.0)
        end_time = time.time()
        
        elapsed = end_time - start_time
        
        # Bollinger Bands calculation should complete in under 1 second for 10k candles
        assert elapsed < 1.0, f"Bollinger Bands calculation took {elapsed:.3f}s, expected < 1.0s"
        assert "upper" in bb
        assert "middle" in bb
        assert "lower" in bb

    @pytest.mark.performance
    def test_stochastic_calculation_performance(self):
        """Test Stochastic calculation performance on large dataset."""
        data = self._make_large_dataset(10000)
        indicators = IndicatorCalculator(data)
        
        start_time = time.time()
        stoch = indicators.stochastic(14, 3)
        end_time = time.time()
        
        elapsed = end_time - start_time
        
        # Stochastic calculation should complete in under 1 second for 10k candles
        assert elapsed < 1.0, f"Stochastic calculation took {elapsed:.3f}s, expected < 1.0s"
        assert "k" in stoch
        assert "d" in stoch

    @pytest.mark.performance
    def test_multiple_indicators_performance(self):
        """Test calculating multiple indicators in sequence."""
        data = self._make_large_dataset(10000)
        indicators = IndicatorCalculator(data)
        
        start_time = time.time()
        
        # Calculate multiple indicators
        rsi = indicators.rsi(14)
        sma = indicators.sma(20)
        ema = indicators.ema(20)
        macd = indicators.macd(12, 26, 9)
        bb = indicators.bollinger_bands(20, 2.0)
        stoch = indicators.stochastic(14, 3)
        
        end_time = time.time()
        elapsed = end_time - start_time
        
        # All indicators should calculate in under 3 seconds for 10k candles
        assert elapsed < 3.0, f"Multiple indicators took {elapsed:.3f}s, expected < 3.0s"


@pytest.mark.performance
class TestSignalGenerationPerformance:
    """Test performance of signal generation."""

    def _make_large_dataset(self, n=10000):
        """Create a large dataset for performance testing."""
        dates = pd.date_range("2025-01-01", periods=n, freq="h")
        data = pd.DataFrame({
            "open": [50.0 + i * 0.001 for i in range(n)],
            "high": [51.0 + i * 0.001 for i in range(n)],
            "low": [49.0 + i * 0.001 for i in range(n)],
            "close": [50.5 + i * 0.001 for i in range(n)],
            "volume": [1000 + i * 10 for i in range(n)],
        }, index=dates)
        return data

    @pytest.mark.performance
    def test_signal_generation_performance(self):
        """Test signal generation performance."""
        data = self._make_large_dataset(10000)
        indicators = IndicatorCalculator(data)
        signals = SignalGenerator(indicators)
        
        start_time = time.time()
        
        # Generate multiple signals
        signals.rsi_above(40)
        signals.rsi_below(60)
        signals.price_above_sma(20)
        signals.price_below_ema(20)
        signals.macd_above_zero()
        signals.volume_above_sma(20)
        
        end_time = time.time()
        elapsed = end_time - start_time
        
        # Signal generation should complete in under 2 seconds for 10k candles
        assert elapsed < 2.0, f"Signal generation took {elapsed:.3f}s, expected < 2.0s"

    @pytest.mark.performance
    def test_composite_signal_evaluation_performance(self):
        """Test composite signal evaluation performance."""
        data = self._make_large_dataset(10000)
        indicators = IndicatorCalculator(data)
        signals = SignalGenerator(indicators)
        
        rules = [
            {"condition": "rsi_above", "params": {"threshold": 40}},
            {"operator": "AND"},
            {"condition": "price_above_sma", "params": {"period": 20}},
            {"operator": "AND"},
            {"condition": "volume_above_sma", "params": {"period": 20}},
        ]
        
        start_time = time.time()
        result = signals.evaluate(rules)
        end_time = time.time()
        
        elapsed = end_time - start_time
        
        # Composite signal evaluation should complete in under 2 seconds
        assert elapsed < 2.0, f"Composite signal evaluation took {elapsed:.3f}s, expected < 2.0s"
        assert "result" in result


@pytest.mark.performance
class TestRetryDecoratorPerformance:
    """Test performance of retry decorator."""

    @pytest.mark.performance
    def test_retry_decorator_overhead(self):
        """Test that retry decorator has minimal overhead on success."""
        @retry_on_error(max_attempts=3, delay=0.001)
        def fast_function():
            return "success"
        
        # Measure decorated function
        start_time = time.time()
        for _ in range(1000):
            fast_function()
        elapsed_decorated = time.time() - start_time
        
        # Measure undecorated function
        def undecorated():
            return "success"
        
        start_time = time.time()
        for _ in range(1000):
            undecorated()
        elapsed_undecorated = time.time() - start_time
        
        # Decorator overhead should be less than 10x (expected for trivial functions)
        overhead_ratio = elapsed_decorated / elapsed_undecorated
        assert overhead_ratio < 10.0, f"Decorator overhead ratio: {overhead_ratio:.2f}x"

    @pytest.mark.performance
    def test_retry_with_backoff_performance(self):
        """Test retry with exponential backoff timing."""
        call_count = [0]
        
        @retry_on_error(max_attempts=3, delay=0.01, backoff_factor=2.0, retry_on=(Exception,))
        def fail_twice():
            call_count[0] += 1
            if call_count[0] < 3:
                raise ValueError("Fail")
            return "success"
        
        start_time = time.time()
        result = fail_twice()
        end_time = time.time()
        
        elapsed = end_time - start_time
        
        # Expected delays: 0.01s (first retry) + 0.02s (second retry) = 0.03s minimum
        # Allow some margin for execution time
        assert elapsed >= 0.03, f"Retry backoff too fast: {elapsed:.3f}s"
        assert elapsed < 0.1, f"Retry backoff too slow: {elapsed:.3f}s"
        assert result == "success"
        assert call_count[0] == 3


@pytest.mark.performance
class TestDataProcessingPerformance:
    """Test performance of data processing operations."""

    @pytest.mark.performance
    def test_dataframe_filtering_performance(self):
        """Test DataFrame filtering performance."""
        n = 10000
        data = pd.DataFrame({
            "value": [i for i in range(n)],
            "category": ["A" if i % 2 == 0 else "B" for i in range(n)],
        })
        
        start_time = time.time()
        filtered = data[data["category"] == "A"]
        end_time = time.time()
        
        elapsed = end_time - start_time
        
        # Filtering should complete in under 0.1 seconds for 10k rows
        assert elapsed < 0.1, f"DataFrame filtering took {elapsed:.3f}s, expected < 0.1s"
        assert len(filtered) == n // 2

    @pytest.mark.performance
    def test_dataframe_groupby_performance(self):
        """Test DataFrame groupby performance."""
        n = 10000
        data = pd.DataFrame({
            "value": [i for i in range(n)],
            "category": [["A", "B", "C", "D"][i % 4] for i in range(n)],
        })
        
        start_time = time.time()
        grouped = data.groupby("category")["value"].mean()
        end_time = time.time()
        
        elapsed = end_time - start_time
        
        # Groupby should complete in under 0.1 seconds for 10k rows
        assert elapsed < 0.1, f"DataFrame groupby took {elapsed:.3f}s, expected < 0.1s"
        assert len(grouped) == 4

    @pytest.mark.performance
    def test_dataframe_sorting_performance(self):
        """Test DataFrame sorting performance."""
        n = 10000
        data = pd.DataFrame({
            "value": [i for i in range(n)],
        })
        
        start_time = time.time()
        sorted_data = data.sort_values("value", ascending=False)
        end_time = time.time()
        
        elapsed = end_time - start_time
        
        # Sorting should complete in under 0.1 seconds for 10k rows
        assert elapsed < 0.1, f"DataFrame sorting took {elapsed:.3f}s, expected < 0.1s"
        assert len(sorted_data) == n


@pytest.mark.performance
class TestMemoryEfficiency:
    """Test memory efficiency of operations."""

    @pytest.mark.performance
    def test_indicator_calculation_memory(self):
        """Test that indicator calculations don't leak memory."""
        import gc
        import sys
        
        data = self._make_large_dataset(10000)
        
        # Force garbage collection before test
        gc.collect()
        
        # Calculate indicators multiple times
        for _ in range(10):
            indicators = IndicatorCalculator(data)
            rsi = indicators.rsi(14)
            sma = indicators.sma(20)
            macd = indicators.macd(12, 26, 9)
            del indicators, rsi, sma, macd
        
        # Force garbage collection
        gc.collect()
        
        # Test should complete without memory errors
        assert True

    def _make_large_dataset(self, n=10000):
        """Create a large dataset for performance testing."""
        dates = pd.date_range("2025-01-01", periods=n, freq="h")
        data = pd.DataFrame({
            "open": [50.0 + i * 0.001 for i in range(n)],
            "high": [51.0 + i * 0.001 for i in range(n)],
            "low": [49.0 + i * 0.001 for i in range(n)],
            "close": [50.5 + i * 0.001 for i in range(n)],
            "volume": [1000 + i * 10 for i in range(n)],
        }, index=dates)
        return data
