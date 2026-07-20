"""
IndicatorCalculator tests — run with: pytest tests/unit/analysis/test_indicators.py
"""

import pandas as pd
import pytest

from polyalpha.analysis.indicators import IndicatorCalculator


@pytest.mark.unit
class TestIndicatorCalculator:
    """Test IndicatorCalculator class."""

    @pytest.fixture
    def sample_data(self):
        dates = pd.date_range("2025-01-01", periods=100, freq="1h")
        return pd.DataFrame({
            "open": [50.0 + i * 0.1 for i in range(100)],
            "high": [51.0 + i * 0.1 for i in range(100)],
            "low": [49.0 + i * 0.1 for i in range(100)],
            "close": [50.5 + i * 0.1 for i in range(100)],
            "volume": [1000 + i * 10 for i in range(100)],
        })

    def test_initialization(self, sample_data):
        calc = IndicatorCalculator(sample_data)
        assert calc.data is not None
        assert calc._cache == {}

    def test_initialization_copies_data(self, sample_data):
        calc = IndicatorCalculator(sample_data)
        sample_data["close"] = 999.0
        assert calc.data["close"].iloc[0] != 999.0

    def test_initialization_missing_columns(self):
        data = pd.DataFrame({"close": [1.0]})
        with pytest.raises(ValueError, match="missing required columns"):
            IndicatorCalculator(data)

    def test_clear_cache(self, sample_data):
        calc = IndicatorCalculator(sample_data)
        calc.sma(20)
        assert len(calc._cache) > 0
        calc.clear_cache()
        assert calc._cache == {}

    def test_sma_default(self, sample_data):
        calc = IndicatorCalculator(sample_data)
        result = calc.sma()
        assert result.name == "SMA20"
        assert len(result) == 100

    def test_sma_period_10(self, sample_data):
        calc = IndicatorCalculator(sample_data)
        result = calc.sma(period=10)
        assert result.name == "SMA10"

    def test_sma_invalid_period(self, sample_data):
        calc = IndicatorCalculator(sample_data)
        with pytest.raises(ValueError, match="period must be positive"):
            calc.sma(period=0)

    def test_sma_custom_price_open(self, sample_data):
        calc = IndicatorCalculator(sample_data)
        result = calc.sma(period=5, price="open")
        assert result.name == "SMA5"

    def test_ema_default(self, sample_data):
        calc = IndicatorCalculator(sample_data)
        result = calc.ema()
        assert result.name == "EMA20"
        assert len(result) == 100

    def test_ema_invalid_period(self, sample_data):
        calc = IndicatorCalculator(sample_data)
        with pytest.raises(ValueError, match="period must be positive"):
            calc.ema(period=0)

    def test_rsi_default(self, sample_data):
        calc = IndicatorCalculator(sample_data)
        result = calc.rsi()
        assert "RSI" in result.name
        assert len(result) == 100

    def test_rsi_invalid_period(self, sample_data):
        calc = IndicatorCalculator(sample_data)
        with pytest.raises(ValueError, match="period must be positive"):
            calc.rsi(period=0)

    def test_macd_default(self, sample_data):
        calc = IndicatorCalculator(sample_data)
        result = calc.macd()
        assert "macd" in result
        assert "signal" in result
        assert "histogram" in result
        assert len(result["macd"]) == 100

    def test_macd_custom_periods(self, sample_data):
        calc = IndicatorCalculator(sample_data)
        result = calc.macd(fast=8, slow=18, signal=5)
        assert "macd" in result

    def test_macd_invalid_fast(self, sample_data):
        calc = IndicatorCalculator(sample_data)
        with pytest.raises(ValueError, match="periods must be positive"):
            calc.macd(fast=0)

    def test_macd_invalid_slow(self, sample_data):
        calc = IndicatorCalculator(sample_data)
        with pytest.raises(ValueError, match="periods must be positive"):
            calc.macd(slow=0)

    def test_bollinger_bands_default(self, sample_data):
        calc = IndicatorCalculator(sample_data)
        result = calc.bollinger_bands()
        assert "upper" in result
        assert "middle" in result
        assert "lower" in result
        assert len(result["upper"]) == 100

    def test_bollinger_bands_invalid_period(self, sample_data):
        calc = IndicatorCalculator(sample_data)
        with pytest.raises(ValueError, match="period must be positive"):
            calc.bollinger_bands(period=0)

    def test_bollinger_bands_invalid_std_dev(self, sample_data):
        calc = IndicatorCalculator(sample_data)
        with pytest.raises(ValueError, match="std_dev must be positive"):
            calc.bollinger_bands(std_dev=0)

    def test_bollinger_bands_structure(self, sample_data):
        calc = IndicatorCalculator(sample_data)
        result = calc.bollinger_bands(period=20, std_dev=2.0)
        valid = result["upper"].notna() & result["middle"].notna() & result["lower"].notna()
        assert (result["upper"][valid] >= result["middle"][valid]).all()
        assert (result["middle"][valid] >= result["lower"][valid]).all()

    def test_atr_default(self, sample_data):
        calc = IndicatorCalculator(sample_data)
        result = calc.atr()
        assert "ATR" in result.name
        assert len(result) == 100

    def test_atr_invalid_period(self, sample_data):
        calc = IndicatorCalculator(sample_data)
        with pytest.raises(ValueError, match="period must be positive"):
            calc.atr(period=0)

    def test_adx_default(self, sample_data):
        calc = IndicatorCalculator(sample_data)
        result = calc.adx()
        assert "adx" in result
        assert "plus_di" in result
        assert "minus_di" in result

    def test_adx_invalid_period(self, sample_data):
        calc = IndicatorCalculator(sample_data)
        with pytest.raises(ValueError, match="period must be positive"):
            calc.adx(period=0)

    def test_stochastic_default(self, sample_data):
        calc = IndicatorCalculator(sample_data)
        result = calc.stochastic()
        assert "k" in result
        assert "d" in result

    def test_stochastic_invalid_k_period(self, sample_data):
        calc = IndicatorCalculator(sample_data)
        with pytest.raises(ValueError, match="periods must be positive"):
            calc.stochastic(k_period=0)

    def test_williams_r_default(self, sample_data):
        calc = IndicatorCalculator(sample_data)
        result = calc.williams_r()
        assert result is not None
        assert len(result) == 100

    def test_williams_r_invalid_period(self, sample_data):
        calc = IndicatorCalculator(sample_data)
        with pytest.raises(ValueError, match="period must be positive"):
            calc.williams_r(period=0)

    def test_cci_default(self, sample_data):
        calc = IndicatorCalculator(sample_data)
        result = calc.cci()
        assert result is not None
        assert len(result) == 100

    def test_cci_invalid_period(self, sample_data):
        calc = IndicatorCalculator(sample_data)
        with pytest.raises(ValueError, match="period must be positive"):
            calc.cci(period=0)

    def test_keltner_channels_default(self, sample_data):
        calc = IndicatorCalculator(sample_data)
        result = calc.keltner_channels()
        assert "upper" in result
        assert "middle" in result
        assert "lower" in result
        assert len(result["upper"]) == 100

    def test_keltner_channels_invalid_period(self, sample_data):
        calc = IndicatorCalculator(sample_data)
        with pytest.raises(ValueError, match="periods must be positive"):
            calc.keltner_channels(period=0)

    def test_keltner_channels_invalid_atr_period(self, sample_data):
        calc = IndicatorCalculator(sample_data)
        with pytest.raises(ValueError, match="periods must be positive"):
            calc.keltner_channels(atr_period=0)

    def test_keltner_channels_invalid_atr_mult(self, sample_data):
        calc = IndicatorCalculator(sample_data)
        with pytest.raises(ValueError, match="atr_mult must be positive"):
            calc.keltner_channels(atr_mult=0)

    def test_obv(self, sample_data):
        calc = IndicatorCalculator(sample_data)
        result = calc.obv()
        assert result.name == "OBV"
        assert len(result) == 100

    def test_volume_sma(self, sample_data):
        calc = IndicatorCalculator(sample_data)
        result = calc.volume_sma()
        assert "VolSMA" in result.name

    def test_volume_sma_invalid_period(self, sample_data):
        calc = IndicatorCalculator(sample_data)
        with pytest.raises(ValueError, match="period must be positive"):
            calc.volume_sma(period=0)

    def test_volume_roc(self, sample_data):
        calc = IndicatorCalculator(sample_data)
        result = calc.volume_roc()
        assert "VolROC" in result.name

    def test_volume_roc_invalid_period(self, sample_data):
        calc = IndicatorCalculator(sample_data)
        with pytest.raises(ValueError, match="period must be positive"):
            calc.volume_roc(period=0)

    def test_calculate_all_default(self, sample_data):
        calc = IndicatorCalculator(sample_data)
        result = calc.calculate_all()
        assert "sma_20" in result
        assert "sma_50" in result
        assert "ema_12" in result
        assert "ema_26" in result
        assert "rsi_14" in result
        assert "macd" in result
        assert "bollinger_bands" in result
        assert "atr_14" in result

    def test_calculate_all_custom_config(self, sample_data):
        calc = IndicatorCalculator(sample_data)
        config = {
            "sma": [10],
            "rsi": [7],
        }
        result = calc.calculate_all(config)
        assert "sma_10" in result
        assert "rsi_7" in result
        assert "macd" not in result

    def test_calculate_all_empty_config(self, sample_data):
        calc = IndicatorCalculator(sample_data)
        result = calc.calculate_all(config={})
        assert len(result) == 0

    def test_cache_hit(self, sample_data):
        calc = IndicatorCalculator(sample_data)
        result1 = calc.sma(20)
        result2 = calc.sma(20)
        assert result1 is result2

    def test_get_latest_value(self, sample_data):
        calc = IndicatorCalculator(sample_data)
        series = calc.sma(20)
        latest = calc.get_latest_value(series)
        if latest is not None:
            assert isinstance(latest, float)

    def test_get_latest_value_empty_series(self, sample_data):
        calc = IndicatorCalculator(sample_data)
        empty = pd.Series([], dtype=float)
        assert calc.get_latest_value(empty) is None

    def test_get_latest_value_all_nan(self, sample_data):
        calc = IndicatorCalculator(sample_data)
        all_nan = pd.Series([None, None, float("nan")])
        assert calc.get_latest_value(all_nan) is None

    def test_get_latest_values(self, sample_data):
        calc = IndicatorCalculator(sample_data)
        indicators = {
            "sma_20": calc.sma(20),
            "rsi_14": calc.rsi(14),
            "macd": calc.macd(),
        }
        latest = calc.get_latest_values(indicators)
        assert "sma_20" in latest
        assert "rsi_14" in latest
        assert "macd" in latest
        if latest["sma_20"] is not None:
            assert isinstance(latest["sma_20"], float)
        if latest["macd"] is not None:
            assert isinstance(latest["macd"], dict)

    def test_rsi_values_in_range(self, sample_data):
        calc = IndicatorCalculator(sample_data)
        series = calc.rsi(14).dropna()
        assert ((series >= 0) & (series <= 100)).all()

    def test_sma_values_ordered(self, sample_data):
        calc = IndicatorCalculator(sample_data)
        sma10 = calc.sma(10).dropna()
        sma50 = calc.sma(50).dropna()
        assert len(sma10) >= len(sma50)
