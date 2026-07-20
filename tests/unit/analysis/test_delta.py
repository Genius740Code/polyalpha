"""
DeltaCalculator tests — run with: pytest tests/unit/analysis/test_delta.py
"""

import pandas as pd
import pytest

from polyalpha.analysis.delta import DeltaCalculator


@pytest.mark.unit
class TestDeltaCalculator:
    """Test DeltaCalculator class."""

    @pytest.fixture
    def sample_data(self):
        dates = pd.date_range("2025-01-01", periods=50, freq="1h")
        return pd.DataFrame({
            "open": [float(i) for i in range(50)],
            "high": [float(i + 1) for i in range(50)],
            "low": [float(max(0, i - 1)) for i in range(50)],
            "close": [float(i + 0.5) for i in range(50)],
            "volume": [1000.0 + i * 10 for i in range(50)],
        })

    def test_initialization(self, sample_data):
        delta = DeltaCalculator(sample_data)
        assert delta.data is not None
        assert delta._cache == {}

    def test_initialization_missing_columns(self):
        data = pd.DataFrame({"close": [1.0, 2.0]})
        with pytest.raises(ValueError, match="missing required columns"):
            DeltaCalculator(data)

    def test_initialization_copies_data(self, sample_data):
        delta = DeltaCalculator(sample_data)
        sample_data["open"] = 999.0
        assert delta.data["open"].iloc[0] != 999.0

    def test_clear_cache(self, sample_data):
        delta = DeltaCalculator(sample_data)
        delta.delta()
        assert len(delta._cache) > 0
        delta.clear_cache()
        assert delta._cache == {}

    def test_delta_default(self, sample_data):
        delta = DeltaCalculator(sample_data)
        result = delta.delta()
        assert result.name == "Delta_close"
        assert len(result) == 50
        assert result.iloc[0] != result.iloc[0]

    def test_delta_custom_price(self, sample_data):
        delta = DeltaCalculator(sample_data)
        result = delta.delta(price="open")
        assert result.name == "Delta_open"

    def test_delta_period_default(self, sample_data):
        delta = DeltaCalculator(sample_data)
        result = delta.delta_period()
        assert result.name == "Delta_close_1"
        assert len(result) == 50

    def test_delta_period_n_5(self, sample_data):
        delta = DeltaCalculator(sample_data)
        result = delta.delta_period(period=5)
        assert result.name == "Delta_close_5"
        assert result.iloc[5] == pytest.approx(sample_data["close"].iloc[5] - sample_data["close"].iloc[0])

    def test_delta_period_invalid(self, sample_data):
        delta = DeltaCalculator(sample_data)
        with pytest.raises(ValueError, match="period must be positive"):
            delta.delta_period(period=0)

    def test_delta_period_negative(self, sample_data):
        delta = DeltaCalculator(sample_data)
        with pytest.raises(ValueError, match="period must be positive"):
            delta.delta_period(period=-1)

    def test_delta_percent_default(self, sample_data):
        delta = DeltaCalculator(sample_data)
        result = delta.delta_percent()
        assert result.name == "DeltaPct_close"
        assert len(result) == 50

    def test_delta_percent_period_default(self, sample_data):
        delta = DeltaCalculator(sample_data)
        result = delta.delta_percent_period()
        assert result.name == "DeltaPct_close_1"

    def test_delta_percent_period_n_3(self, sample_data):
        delta = DeltaCalculator(sample_data)
        result = delta.delta_percent_period(period=3)
        assert result.name == "DeltaPct_close_3"

    def test_delta_percent_period_invalid(self, sample_data):
        delta = DeltaCalculator(sample_data)
        with pytest.raises(ValueError, match="period must be positive"):
            delta.delta_percent_period(period=0)

    def test_delta_acceleration_default(self, sample_data):
        delta = DeltaCalculator(sample_data)
        result = delta.delta_acceleration()
        assert result.name == "DeltaAcc_close_1"
        assert len(result) == 50

    def test_delta_acceleration_n_3(self, sample_data):
        delta = DeltaCalculator(sample_data)
        result = delta.delta_acceleration(period=3)
        assert result.name == "DeltaAcc_close_3"

    def test_delta_acceleration_invalid(self, sample_data):
        delta = DeltaCalculator(sample_data)
        with pytest.raises(ValueError, match="period must be positive"):
            delta.delta_acceleration(period=0)

    def test_delta_smoothed_default(self, sample_data):
        delta = DeltaCalculator(sample_data)
        result = delta.delta_smoothed()
        assert "DeltaSmooth" in result.name
        assert len(result) == 50

    def test_delta_smoothed_custom_periods(self, sample_data):
        delta = DeltaCalculator(sample_data)
        result = delta.delta_smoothed(period=2, smooth_period=5)
        assert "DeltaSmooth" in result.name

    def test_delta_smoothed_invalid_period(self, sample_data):
        delta = DeltaCalculator(sample_data)
        with pytest.raises(ValueError, match="periods must be positive"):
            delta.delta_smoothed(period=0, smooth_period=3)

    def test_delta_smoothed_invalid_smooth_period(self, sample_data):
        delta = DeltaCalculator(sample_data)
        with pytest.raises(ValueError, match="periods must be positive"):
            delta.delta_smoothed(period=1, smooth_period=0)

    def test_cache_hit(self, sample_data):
        delta = DeltaCalculator(sample_data)
        result1 = delta.delta()
        result2 = delta.delta()
        assert result1 is result2

    def test_get_latest_value(self, sample_data):
        delta = DeltaCalculator(sample_data)
        series = delta.delta()
        latest = delta.get_latest_value(series)
        if latest is not None:
            assert isinstance(latest, float)

    def test_get_latest_value_empty_series(self, sample_data):
        delta = DeltaCalculator(sample_data)
        empty = pd.Series([], dtype=float)
        assert delta.get_latest_value(empty) is None

    def test_get_latest_value_all_nan(self, sample_data):
        delta = DeltaCalculator(sample_data)
        all_nan = pd.Series([None, None, float("nan")])
        assert delta.get_latest_value(all_nan) is None

    def test_delta_price_open(self, sample_data):
        delta = DeltaCalculator(sample_data)
        result = delta.delta(price="open")
        assert len(result) == 50

    def test_delta_price_high(self, sample_data):
        delta = DeltaCalculator(sample_data)
        result = delta.delta(price="high")
        assert len(result) == 50

    def test_delta_price_low(self, sample_data):
        delta = DeltaCalculator(sample_data)
        result = delta.delta(price="low")
        assert len(result) == 50

    def test_delta_price_volume(self, sample_data):
        delta = DeltaCalculator(sample_data)
        result = delta.delta(price="volume")
        assert len(result) == 50
