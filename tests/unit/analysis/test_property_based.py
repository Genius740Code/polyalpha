"""
Property-based tests for analysis modules using Hypothesis.

Tests mathematical invariants:
  - DeltaCalculator: delta properties, caching, edge cases
  - IndicatorCalculator: RSI range, SMA monotonicity relationships
  - DataFeedConfig: validation invariants

Run with: pytest tests/unit/analysis/test_property_based.py
"""

import pandas as pd
import pytest
from hypothesis import given, assume, settings, HealthCheck
from hypothesis import strategies as st

from polyalpha.analysis.data_feed import DataFeedConfig
from polyalpha.analysis.delta import DeltaCalculator
from polyalpha.analysis.indicators import IndicatorCalculator


# ── Helper strategies ────────────────────────────────────────────────────────

PRICE_COLUMNS = st.sampled_from(["open", "high", "low", "close", "volume"])

VALID_SOURCES = st.sampled_from(["binance", "chainlink", "custom", "websocket", "scraping"])
VALID_TIMEFRAMES = st.sampled_from(["1m", "5m", "15m", "1h", "4h", "1d"])
INVALID_SOURCES = st.text().filter(
    lambda s: s not in {"binance", "chainlink", "custom", "websocket", "scraping", ""}
)


_SUPPRESS = settings(suppress_health_check=[HealthCheck.too_slow], max_examples=20)


@st.composite
def ohlcv_data(draw, min_rows: int = 20, max_rows: int = 60):
    """Generate small random OHLCV DataFrame."""
    n = draw(st.integers(min_value=min_rows, max_value=max_rows))
    base = draw(st.floats(min_value=10.0, max_value=500.0))
    drift = draw(st.floats(min_value=-1.0, max_value=1.0))

    opens = [base + i * drift for i in range(n)]
    closes = [o + draw(st.floats(min_value=-5.0, max_value=5.0)) for o in opens]
    highs = [max(o, c) + abs(draw(st.floats(min_value=0.0, max_value=2.0))) for o, c in zip(opens, closes)]
    lows = [min(o, c) - abs(draw(st.floats(min_value=0.0, max_value=2.0))) for o, c in zip(opens, closes)]
    volumes = [abs(draw(st.floats(min_value=1.0, max_value=100_000.0))) for _ in range(n)]

    return pd.DataFrame({
        "open": opens,
        "high": highs,
        "low": lows,
        "close": closes,
        "volume": volumes,
    })


# ── DeltaCalculator Properties ──────────────────────────────────────────────

@pytest.mark.unit
class TestDeltaProperties:
    """Mathematical invariants for DeltaCalculator."""

    @given(data=ohlcv_data())
    @_SUPPRESS
    def test_delta_first_value_nan(self, data):
        dc = DeltaCalculator(data)
        result = dc.delta()
        assert pd.isna(result.iloc[0])

    @given(data=ohlcv_data(min_rows=5))
    @_SUPPRESS
    def test_delta_period_matches_manual(self, data):
        dc = DeltaCalculator(data)
        period = 3
        result = dc.delta_period(period=period)
        manual = data["close"].diff(periods=period)
        pd.testing.assert_series_equal(result, manual, check_names=False)

    @given(data=ohlcv_data(min_rows=5))
    @_SUPPRESS
    def test_delta_percent_range(self, data):
        dc = DeltaCalculator(data)
        result = dc.delta_percent().dropna()
        assume(len(result) > 0)
        assert result.abs().max() < 1e6

    @given(data=ohlcv_data(min_rows=5))
    @_SUPPRESS
    def test_delta_acceleration_is_delta_of_delta(self, data):
        dc = DeltaCalculator(data)
        accel = dc.delta_acceleration(period=1)
        d1 = dc.delta()
        manual = d1.diff()
        pd.testing.assert_series_equal(accel, manual, check_names=False)

    @given(data=ohlcv_data())
    @_SUPPRESS
    def test_cache_returns_same_object(self, data):
        dc = DeltaCalculator(data)
        r1 = dc.delta()
        r2 = dc.delta()
        assert r1 is r2

    @given(data=ohlcv_data())
    @_SUPPRESS
    def test_clear_cache_works(self, data):
        dc = DeltaCalculator(data)
        dc.delta()
        dc.clear_cache()
        assert dc._cache == {}

    @given(data=ohlcv_data(min_rows=5))
    @_SUPPRESS
    def test_delta_percent_period_matches_manual(self, data):
        dc = DeltaCalculator(data)
        period = 2
        result = dc.delta_percent_period(period=period)
        manual = data["close"].pct_change(periods=period) * 100
        pd.testing.assert_series_equal(result, manual, check_names=False)

    @given(data=ohlcv_data(min_rows=5))
    @_SUPPRESS
    def test_delta_smoothed_same_length(self, data):
        dc = DeltaCalculator(data)
        result = dc.delta_smoothed(period=1, smooth_period=3)
        assert len(result) == len(data)

    @given(data=ohlcv_data(min_rows=10))
    @_SUPPRESS
    def test_delta_period_n_equals_1_same_as_delta(self, data):
        dc = DeltaCalculator(data)
        d1 = dc.delta()
        d2 = dc.delta_period(period=1)
        pd.testing.assert_series_equal(d1, d2, check_names=False)

    @given(data=ohlcv_data())
    @_SUPPRESS
    def test_validate_data_invariant(self, data):
        dc = DeltaCalculator(data)
        assert set(dc.data.columns) == {"open", "high", "low", "close", "volume"}


# ── IndicatorCalculator Properties ──────────────────────────────────────────

@pytest.mark.unit
class TestIndicatorProperties:
    """Mathematical invariants for IndicatorCalculator."""

    @given(data=ohlcv_data())
    @_SUPPRESS
    def test_rsi_between_zero_and_hundred(self, data):
        calc = IndicatorCalculator(data)
        rsi = calc.rsi(14).dropna()
        assume(len(rsi) > 0)
        assert (rsi >= 0).all()
        assert (rsi <= 100).all()

    @given(data=ohlcv_data())
    @_SUPPRESS
    def test_sma_length_equals_input(self, data):
        calc = IndicatorCalculator(data)
        result = calc.sma(10)
        assert len(result) == len(data)

    @given(data=ohlcv_data())
    @_SUPPRESS
    def test_ema_length_equals_input(self, data):
        calc = IndicatorCalculator(data)
        result = calc.ema(10)
        assert len(result) == len(data)

    @given(data=ohlcv_data())
    @_SUPPRESS
    def test_sma_shorter_period_has_fewer_nans(self, data):
        calc = IndicatorCalculator(data)
        sma10 = calc.sma(10)
        sma50 = calc.sma(50)
        assert sma10.notna().sum() >= sma50.notna().sum()

    @given(data=ohlcv_data())
    @_SUPPRESS
    def test_get_latest_value_no_nan(self, data):
        calc = IndicatorCalculator(data)
        sma = calc.sma(10)
        val = calc.get_latest_value(sma)
        if val is not None:
            assert not pd.isna(val)

    @given(data=ohlcv_data())
    @_SUPPRESS
    def test_macd_returns_three_keys(self, data):
        calc = IndicatorCalculator(data)
        result = calc.macd()
        assert set(result.keys()) == {"macd", "signal", "histogram"}

    @given(data=ohlcv_data())
    @_SUPPRESS
    def test_bollinger_bands_three_keys(self, data):
        calc = IndicatorCalculator(data)
        result = calc.bollinger_bands()
        assert set(result.keys()) == {"upper", "middle", "lower"}

    @given(data=ohlcv_data())
    @_SUPPRESS
    def test_adx_three_keys(self, data):
        calc = IndicatorCalculator(data)
        result = calc.adx()
        assert set(result.keys()) == {"adx", "plus_di", "minus_di"}

    @given(data=ohlcv_data())
    @_SUPPRESS
    def test_stochastic_two_keys(self, data):
        calc = IndicatorCalculator(data)
        result = calc.stochastic()
        assert set(result.keys()) == {"k", "d"}

    @given(data=ohlcv_data())
    @_SUPPRESS
    def test_cache_returns_same_object(self, data):
        calc = IndicatorCalculator(data)
        r1 = calc.sma(20)
        r2 = calc.sma(20)
        assert r1 is r2

    @given(data=ohlcv_data())
    @_SUPPRESS
    def test_clear_cache_works(self, data):
        calc = IndicatorCalculator(data)
        calc.sma(10)
        calc.clear_cache()
        assert calc._cache == {}

    @given(data=ohlcv_data(min_rows=30))
    @_SUPPRESS
    def test_keltner_channels_three_keys(self, data):
        calc = IndicatorCalculator(data)
        result = calc.keltner_channels()
        assert set(result.keys()) == {"upper", "middle", "lower"}

    @given(data=ohlcv_data())
    @_SUPPRESS
    def test_obv_length_equals_input(self, data):
        calc = IndicatorCalculator(data)
        result = calc.obv()
        assert len(result) == len(data)

    @given(data=ohlcv_data())
    @_SUPPRESS
    def test_volume_sma_length_equals_input(self, data):
        calc = IndicatorCalculator(data)
        result = calc.volume_sma(10)
        assert len(result) == len(data)

    @given(data=ohlcv_data())
    @_SUPPRESS
    def test_volume_roc_length_equals_input(self, data):
        calc = IndicatorCalculator(data)
        result = calc.volume_roc(10)
        assert len(result) == len(data)


# ── DataFeedConfig Properties ───────────────────────────────────────────────

@pytest.mark.unit
class TestDataFeedConfigProperties:
    """Invariants for DataFeedConfig validation."""

    @given(source=VALID_SOURCES, timeframe=VALID_TIMEFRAMES)
    @_SUPPRESS
    def test_valid_config_creates(self, source, timeframe):
        cfg = DataFeedConfig(
            source=source,
            timeframe=timeframe,
            use_cache=False,
            custom_url="http://example.com/api" if source == "custom" else None,
        )
        assert cfg.source == source
        assert cfg.timeframe == timeframe

    @given(source=INVALID_SOURCES, timeframe=VALID_TIMEFRAMES)
    @_SUPPRESS
    def test_invalid_source_raises(self, source, timeframe):
        assume(source != "")
        with pytest.raises(ValueError):
            DataFeedConfig(source=source, timeframe=timeframe, use_cache=False)

    @given(lookback=st.integers(min_value=-1000, max_value=0))
    @_SUPPRESS
    def test_non_positive_lookback_raises(self, lookback):
        with pytest.raises(ValueError, match="lookback_periods must be positive"):
            DataFeedConfig(lookback_periods=lookback, use_cache=False)

    @given(timeframe=st.text().filter(
        lambda t: t not in {"1m", "5m", "15m", "1h", "4h", "1d", ""}
    ))
    @_SUPPRESS
    def test_invalid_timeframe_raises(self, timeframe):
        assume(timeframe != "")
        with pytest.raises(ValueError, match="Invalid timeframe"):
            DataFeedConfig(timeframe=timeframe, use_cache=False)

    @given(
        source=st.sampled_from(["binance", "chainlink", "websocket", "scraping"]),
        timeframe=VALID_TIMEFRAMES,
    )
    @_SUPPRESS
    def test_non_custom_no_url_required(self, source, timeframe):
        cfg = DataFeedConfig(source=source, timeframe=timeframe, use_cache=False)
        assert cfg.source == source
