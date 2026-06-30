"""
Analysis module tests — run with: pytest tests/test_analysis.py
"""

import sys, os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))

import pytest
import pandas as pd
import tempfile
from polyalpha.analysis import DataFeed, DataFeedConfig, IndicatorCalculator, SignalGenerator


# ── DataFeed tests ─────────────────────────────────────────────────────────────

def test_datafeed_config_initialization():
    config = DataFeedConfig(
        asset="BTC",
        timeframe="5m",
        lookback_periods=100
    )
    
    assert config.asset == "BTC"
    assert config.timeframe == "5m"
    assert config.lookback_periods == 100
    assert config.source == "binance"  # default


def test_datafeed_config_custom_source():
    config = DataFeedConfig(
        asset="BTC",
        timeframe="5m",
        source="custom",
        custom_url="https://api.example.com/ohlcv"
    )
    
    assert config.source == "custom"
    assert config.custom_url == "https://api.example.com/ohlcv"


def test_datafeed_config_validation():
    # Custom source requires custom_url
    with pytest.raises(ValueError, match="custom_url required"):
        DataFeedConfig(
            asset="BTC",
            timeframe="5m",
            source="custom"
        )


def test_datafeed_initialization():
    config = DataFeedConfig(asset="BTC", timeframe="5m")
    
    with tempfile.TemporaryDirectory() as tmpdir:
        feed = DataFeed(config, cache_dir=tmpdir)
        
        assert feed.config == config
        assert feed._cache_dir == tmpdir


def test_datafeed_resampling():
    config = DataFeedConfig(asset="BTC", timeframe="5m")
    
    with tempfile.TemporaryDirectory() as tmpdir:
        feed = DataFeed(config, cache_dir=tmpdir)
        
        # Create test data with 1-minute candles
        data = pd.DataFrame({
            "timestamp": pd.date_range("2025-01-01", periods=10, freq="1min"),
            "open": [50000.0] * 10,
            "high": [50100.0] * 10,
            "low": [49900.0] * 10,
            "close": [50050.0] * 10,
            "volume": [100.0] * 10
        })
        
        # Resample to 5m
        resampled = feed._resample(data, "5m")
        
        assert len(resampled) <= len(data)
        assert "timestamp" in resampled.columns
        assert "open" in resampled.columns


def test_datafeed_cache_path():
    config = DataFeedConfig(asset="BTC", timeframe="5m")
    
    with tempfile.TemporaryDirectory() as tmpdir:
        feed = DataFeed(config, cache_dir=tmpdir)
        
        cache_path = feed._cache_path()
        
        assert "BTC" in cache_path
        assert "5m" in cache_path
        assert cache_path.endswith(".parquet")


# ── IndicatorCalculator tests ───────────────────────────────────────────────────

def test_indicator_calculator_validation():
    # Missing required columns
    data = pd.DataFrame({
        "timestamp": pd.date_range("2025-01-01", periods=20),
        "open": [50000.0] * 20,
        "close": [50050.0] * 20
    })
    
    with pytest.raises(ValueError, match="missing required columns"):
        IndicatorCalculator(data)


def test_indicator_calculator_short_data():
    # Data with fewer than 20 rows should warn but not fail
    data = pd.DataFrame({
        "timestamp": pd.date_range("2025-01-01", periods=10),
        "open": [50000.0] * 10,
        "high": [50100.0] * 10,
        "low": [49900.0] * 10,
        "close": [50050.0] * 10,
        "volume": [100.0] * 10
    })
    
    calc = IndicatorCalculator(data)
    assert calc is not None


def test_indicator_sma():
    data = pd.DataFrame({
        "timestamp": pd.date_range("2025-01-01", periods=50),
        "open": [50000.0 + i for i in range(50)],
        "high": [50100.0 + i for i in range(50)],
        "low": [49900.0 + i for i in range(50)],
        "close": [50050.0 + i for i in range(50)],
        "volume": [100.0] * 50
    })
    
    calc = IndicatorCalculator(data)
    sma = calc.sma(period=20)
    
    assert len(sma) == len(data)
    assert sma.name == "SMA20"


def test_indicator_ema():
    data = pd.DataFrame({
        "timestamp": pd.date_range("2025-01-01", periods=50),
        "open": [50000.0] * 50,
        "high": [50100.0] * 50,
        "low": [49900.0] * 50,
        "close": [50050.0] * 50,
        "volume": [100.0] * 50
    })
    
    calc = IndicatorCalculator(data)
    ema = calc.ema(period=20)
    
    assert len(ema) == len(data)
    assert ema.name == "EMA20"


def test_indicator_rsi():
    data = pd.DataFrame({
        "timestamp": pd.date_range("2025-01-01", periods=50),
        "open": [50000.0] * 50,
        "high": [50100.0] * 50,
        "low": [49900.0] * 50,
        "close": [50050.0 + i * 10 for i in range(50)],  # Trending up
        "volume": [100.0] * 50
    })
    
    calc = IndicatorCalculator(data)
    rsi = calc.rsi(period=14)
    
    assert len(rsi) == len(data)
    assert rsi.name == "RSI14"


def test_indicator_macd():
    data = pd.DataFrame({
        "timestamp": pd.date_range("2025-01-01", periods=50),
        "open": [50000.0] * 50,
        "high": [50100.0] * 50,
        "low": [49900.0] * 50,
        "close": [50050.0] * 50,
        "volume": [100.0] * 50
    })
    
    calc = IndicatorCalculator(data)
    macd = calc.macd(fast=12, slow=26, signal=9)
    
    assert "macd" in macd
    assert "signal" in macd
    assert "histogram" in macd
    assert len(macd["macd"]) == len(data)


def test_indicator_bollinger_bands():
    data = pd.DataFrame({
        "timestamp": pd.date_range("2025-01-01", periods=50),
        "open": [50000.0] * 50,
        "high": [50100.0] * 50,
        "low": [49900.0] * 50,
        "close": [50050.0] * 50,
        "volume": [100.0] * 50
    })
    
    calc = IndicatorCalculator(data)
    bb = calc.bollinger_bands(period=20, std_dev=2.0)
    
    assert "upper" in bb
    assert "middle" in bb
    assert "lower" in bb
    assert len(bb["upper"]) == len(data)


def test_indicator_invalid_period():
    data = pd.DataFrame({
        "timestamp": pd.date_range("2025-01-01", periods=50),
        "open": [50000.0] * 50,
        "high": [50100.0] * 50,
        "low": [49900.0] * 50,
        "close": [50050.0] * 50,
        "volume": [100.0] * 50
    })
    
    calc = IndicatorCalculator(data)
    
    with pytest.raises(ValueError, match="must be positive"):
        calc.sma(period=-5)
    
    with pytest.raises(ValueError, match="must be positive"):
        calc.sma(period=0)


def test_indicator_get_latest_value():
    data = pd.DataFrame({
        "timestamp": pd.date_range("2025-01-01", periods=50),
        "open": [50000.0] * 50,
        "high": [50100.0] * 50,
        "low": [49900.0] * 50,
        "close": [50050.0] * 50,
        "volume": [100.0] * 50
    })
    
    calc = IndicatorCalculator(data)
    sma = calc.sma(period=20)
    
    latest = calc.get_latest_value(sma)
    
    assert latest is not None
    assert isinstance(latest, float)


def test_indicator_get_latest_value_empty():
    data = pd.DataFrame({
        "timestamp": pd.date_range("2025-01-01", periods=50),
        "open": [50000.0] * 50,
        "high": [50100.0] * 50,
        "low": [49900.0] * 50,
        "close": [50050.0] * 50,
        "volume": [100.0] * 50
    })
    
    calc = IndicatorCalculator(data)
    
    # Empty series
    empty_series = pd.Series([], dtype=float)
    
    latest = calc.get_latest_value(empty_series)
    
    assert latest is None


def test_indicator_calculate_all():
    data = pd.DataFrame({
        "timestamp": pd.date_range("2025-01-01", periods=50),
        "open": [50000.0] * 50,
        "high": [50100.0] * 50,
        "low": [49900.0] * 50,
        "close": [50050.0] * 50,
        "volume": [100.0] * 50
    })
    
    calc = IndicatorCalculator(data)
    results = calc.calculate_all()
    
    assert "sma_20" in results
    assert "ema_12" in results
    assert "rsi_14" in results
    assert "macd" in results


# ── SignalGenerator tests ────────────────────────────────────────────────────

def test_signal_generator_initialization():
    data = pd.DataFrame({
        "timestamp": pd.date_range("2025-01-01", periods=50),
        "open": [50000.0] * 50,
        "high": [50100.0] * 50,
        "low": [49900.0] * 50,
        "close": [50050.0] * 50,
        "volume": [100.0] * 50
    })
    
    indicators = IndicatorCalculator(data)
    signals = SignalGenerator(indicators)
    
    assert signals.indicators == indicators


def test_signal_rsi_above():
    # Create data with high RSI
    data = pd.DataFrame({
        "timestamp": pd.date_range("2025-01-01", periods=50),
        "open": [50000.0] * 50,
        "high": [50100.0] * 50,
        "low": [49900.0] * 50,
        "close": [50050.0 + i * 100 for i in range(50)],  # Strong uptrend
        "volume": [100.0] * 50
    })
    
    indicators = IndicatorCalculator(data)
    signals = SignalGenerator(indicators)
    
    result = signals.rsi_above(50)
    
    assert isinstance(result, bool)


def test_signal_rsi_invalid_threshold():
    data = pd.DataFrame({
        "timestamp": pd.date_range("2025-01-01", periods=50),
        "open": [50000.0] * 50,
        "high": [50100.0] * 50,
        "low": [49900.0] * 50,
        "close": [50050.0] * 50,
        "volume": [100.0] * 50
    })
    
    indicators = IndicatorCalculator(data)
    signals = SignalGenerator(indicators)
    
    with pytest.raises(ValueError, match="between 0 and 100"):
        signals.rsi_above(150)
    
    with pytest.raises(ValueError, match="between 0 and 100"):
        signals.rsi_above(-10)


def test_signal_price_above_sma():
    # Price above SMA
    data = pd.DataFrame({
        "timestamp": pd.date_range("2025-01-01", periods=50),
        "open": [50000.0] * 50,
        "high": [50100.0] * 50,
        "low": [49900.0] * 50,
        "close": [52000.0] * 50,  # High price
        "volume": [100.0] * 50
    })
    
    indicators = IndicatorCalculator(data)
    signals = SignalGenerator(indicators)
    
    result = signals.price_above_sma(period=20)
    
    assert isinstance(result, bool)


def test_signal_macd_crossover():
    data = pd.DataFrame({
        "timestamp": pd.date_range("2025-01-01", periods=50),
        "open": [50000.0] * 50,
        "high": [50100.0] * 50,
        "low": [49900.0] * 50,
        "close": [50050.0] * 50,
        "volume": [100.0] * 50
    })
    
    indicators = IndicatorCalculator(data)
    signals = SignalGenerator(indicators)
    
    result = signals.macd_bullish_crossover()
    
    assert isinstance(result, bool)


def test_signal_custom_condition():
    data = pd.DataFrame({
        "timestamp": pd.date_range("2025-01-01", periods=50),
        "open": [50000.0] * 50,
        "high": [50100.0] * 50,
        "low": [49900.0] * 50,
        "close": [50050.0] * 50,
        "volume": [100.0] * 50
    })
    
    indicators = IndicatorCalculator(data)
    signals = SignalGenerator(indicators)
    
    def custom_strategy(indicators):
        rsi = indicators.rsi(14)
        latest = indicators.get_latest_value(rsi)
        return latest > 50 if latest else False
    
    result = signals.custom(custom_strategy)
    
    assert isinstance(result, bool)


def test_signal_evaluate():
    data = pd.DataFrame({
        "timestamp": pd.date_range("2025-01-01", periods=50),
        "open": [50000.0] * 50,
        "high": [50100.0] * 50,
        "low": [49900.0] * 50,
        "close": [50050.0] * 50,
        "volume": [100.0] * 50
    })
    
    indicators = IndicatorCalculator(data)
    signals = SignalGenerator(indicators)
    
    rules = [
        {"condition": "rsi_above", "params": {"threshold": 30}},
        {"operator": "AND"},
        {"condition": "price_above_sma", "params": {"period": 20}},
    ]
    
    result = signals.evaluate(rules)
    
    assert "result" in result
    assert "signals" in result
    assert "details" in result
    assert isinstance(result["result"], bool)


def test_signal_summary():
    data = pd.DataFrame({
        "timestamp": pd.date_range("2025-01-01", periods=50),
        "open": [50000.0] * 50,
        "high": [50100.0] * 50,
        "low": [49900.0] * 50,
        "close": [50050.0] * 50,
        "volume": [100.0] * 50
    })
    
    indicators = IndicatorCalculator(data)
    signals = SignalGenerator(indicators)
    
    summary = signals.summary()
    
    assert "rsi" in summary
    assert "rsi_status" in summary
    assert "price_vs_sma20" in summary
    assert "macd_status" in summary
