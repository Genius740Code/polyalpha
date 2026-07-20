"""
Performance benchmarks for analysis modules.

Measures execution time of critical operations:
  - DataFeedConfig validation
  - DeltaCalculator methods
  - IndicatorCalculator methods

Run with: pytest tests/unit/analysis/test_performance.py --benchmark-only
"""

import pandas as pd
import pytest

from polyalpha.analysis.data_feed import DataFeed, DataFeedConfig
from polyalpha.analysis.delta import DeltaCalculator
from polyalpha.analysis.indicators import IndicatorCalculator


@pytest.fixture(scope="module")
def large_ohlcv():
    dates = pd.date_range("2024-01-01", periods=10_000, freq="1h")
    return pd.DataFrame({
        "timestamp": dates,
        "open": [50.0 + i * 0.01 for i in range(10_000)],
        "high": [51.0 + i * 0.01 for i in range(10_000)],
        "low": [49.0 + i * 0.01 for i in range(10_000)],
        "close": [50.5 + i * 0.01 for i in range(10_000)],
        "volume": [1000 + i for i in range(10_000)],
    })


@pytest.mark.unit
class TestDataFeedPerformance:
    """Benchmark DataFeed operations."""

    def test_config_creation(self, benchmark):
        benchmark(DataFeedConfig, source="binance", timeframe="5m", use_cache=False)

    def test_datafeed_init(self, benchmark):
        cfg = DataFeedConfig(use_cache=False)
        benchmark(DataFeed, cfg)

    def test_get_timeframe_seconds(self, benchmark):
        cfg = DataFeedConfig(use_cache=False)
        feed = DataFeed(cfg)
        benchmark(feed._get_timeframe_seconds)

    def test_normalize_ohlcv(self, benchmark, large_ohlcv):
        cfg = DataFeedConfig(use_cache=False)
        feed = DataFeed(cfg)
        benchmark(feed._normalize_ohlcv, large_ohlcv.copy())

    def test_update_ticks(self, benchmark):
        cfg = DataFeedConfig(use_cache=False)
        feed = DataFeed(cfg)

        def _update_many():
            for i in range(100):
                feed.update(float(i))
        benchmark(_update_many)

    def test_get_latest(self, benchmark, large_ohlcv):
        cfg = DataFeedConfig(use_cache=False)
        feed = DataFeed(cfg)
        feed._data = large_ohlcv
        benchmark(feed.get_latest, 100)


@pytest.mark.unit
class TestDeltaPerformance:
    """Benchmark DeltaCalculator operations."""

    def test_delta_creation(self, benchmark, large_ohlcv):
        benchmark(DeltaCalculator, large_ohlcv)

    def test_delta(self, benchmark, large_ohlcv):
        dc = DeltaCalculator(large_ohlcv)
        benchmark(dc.delta)

    def test_delta_period(self, benchmark, large_ohlcv):
        dc = DeltaCalculator(large_ohlcv)
        benchmark(dc.delta_period, 10)

    def test_delta_percent(self, benchmark, large_ohlcv):
        dc = DeltaCalculator(large_ohlcv)
        benchmark(dc.delta_percent)

    def test_delta_acceleration(self, benchmark, large_ohlcv):
        dc = DeltaCalculator(large_ohlcv)
        benchmark(dc.delta_acceleration, 5)

    def test_delta_smoothed(self, benchmark, large_ohlcv):
        dc = DeltaCalculator(large_ohlcv)
        benchmark(dc.delta_smoothed, 5, 10)

    def test_get_latest_value(self, benchmark, large_ohlcv):
        dc = DeltaCalculator(large_ohlcv)
        series = dc.delta()
        benchmark(dc.get_latest_value, series)

    def test_all_delta_methods(self, benchmark, large_ohlcv):
        dc = DeltaCalculator(large_ohlcv)
        def _run_all():
            dc.delta()
            dc.delta_period(5)
            dc.delta_period(10)
            dc.delta_percent()
            dc.delta_percent_period(5)
            dc.delta_acceleration(3)
            dc.delta_smoothed(5, 10)
        benchmark(_run_all)


@pytest.mark.unit
class TestIndicatorPerformance:
    """Benchmark IndicatorCalculator operations."""

    def test_indicator_creation(self, benchmark, large_ohlcv):
        benchmark(IndicatorCalculator, large_ohlcv)

    def test_sma(self, benchmark, large_ohlcv):
        calc = IndicatorCalculator(large_ohlcv)
        benchmark(calc.sma, 50)

    def test_ema(self, benchmark, large_ohlcv):
        calc = IndicatorCalculator(large_ohlcv)
        benchmark(calc.ema, 50)

    def test_rsi(self, benchmark, large_ohlcv):
        calc = IndicatorCalculator(large_ohlcv)
        benchmark(calc.rsi, 14)

    def test_macd(self, benchmark, large_ohlcv):
        calc = IndicatorCalculator(large_ohlcv)
        benchmark(calc.macd)

    def test_bollinger_bands(self, benchmark, large_ohlcv):
        calc = IndicatorCalculator(large_ohlcv)
        benchmark(calc.bollinger_bands, 20, 2.0)

    def test_adx(self, benchmark, large_ohlcv):
        calc = IndicatorCalculator(large_ohlcv)
        benchmark(calc.adx, 14)

    def test_stochastic(self, benchmark, large_ohlcv):
        calc = IndicatorCalculator(large_ohlcv)
        benchmark(calc.stochastic)

    def test_atr(self, benchmark, large_ohlcv):
        calc = IndicatorCalculator(large_ohlcv)
        benchmark(calc.atr, 14)

    def test_williams_r(self, benchmark, large_ohlcv):
        calc = IndicatorCalculator(large_ohlcv)
        benchmark(calc.williams_r, 14)

    def test_cci(self, benchmark, large_ohlcv):
        calc = IndicatorCalculator(large_ohlcv)
        benchmark(calc.cci, 20)

    def test_keltner_channels(self, benchmark, large_ohlcv):
        calc = IndicatorCalculator(large_ohlcv)
        benchmark(calc.keltner_channels, 20, 10, 2.0)

    def test_obv(self, benchmark, large_ohlcv):
        calc = IndicatorCalculator(large_ohlcv)
        benchmark(calc.obv)

    def test_volume_sma(self, benchmark, large_ohlcv):
        calc = IndicatorCalculator(large_ohlcv)
        benchmark(calc.volume_sma, 20)

    def test_volume_roc(self, benchmark, large_ohlcv):
        calc = IndicatorCalculator(large_ohlcv)
        benchmark(calc.volume_roc, 12)

    def test_calculate_all(self, benchmark, large_ohlcv):
        calc = IndicatorCalculator(large_ohlcv)
        benchmark(calc.calculate_all)

    def test_get_latest_values(self, benchmark, large_ohlcv):
        calc = IndicatorCalculator(large_ohlcv)
        indicators = {
            "sma_20": calc.sma(20),
            "rsi_14": calc.rsi(14),
            "macd": calc.macd(),
        }
        benchmark(calc.get_latest_values, indicators)

    def test_all_indicators(self, benchmark, large_ohlcv):
        calc = IndicatorCalculator(large_ohlcv)
        def _run_all():
            calc.sma(20)
            calc.ema(20)
            calc.rsi(14)
            calc.macd()
            calc.bollinger_bands()
            calc.atr(14)
            calc.adx()
            calc.stochastic()
            calc.williams_r(14)
            calc.cci(20)
            calc.keltner_channels()
            calc.obv()
            calc.volume_sma(20)
            calc.volume_roc(12)
        benchmark(_run_all)
