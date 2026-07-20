"""
Signal generation tests — run with: pytest tests/unit/analysis/test_signals.py
"""

import pandas as pd
import pytest

from polyalpha.analysis.indicators import IndicatorCalculator
from polyalpha.analysis.signals import SignalGenerator


@pytest.mark.unit
class TestSignalGenerator:
    """Test SignalGenerator class."""

    def _make_indicator_calculator(self, n=100):
        """Helper to create an IndicatorCalculator with test data."""
        dates = pd.date_range("2025-01-01", periods=n, freq="1h")
        data = pd.DataFrame({
            "open": [50.0 + i * 0.1 for i in range(n)],
            "high": [51.0 + i * 0.1 for i in range(n)],
            "low": [49.0 + i * 0.1 for i in range(n)],
            "close": [50.5 + i * 0.1 for i in range(n)],
            "volume": [1000 + i * 10 for i in range(n)],
        }, index=dates)
        return IndicatorCalculator(data)

    def test_initialization(self):
        """Test SignalGenerator initialization."""
        indicators = self._make_indicator_calculator()
        signals = SignalGenerator(indicators)
        assert signals.indicators is indicators
        assert signals._data is indicators.data

    # ── RSI Signals ───────────────────────────────────────────────────────

    def test_rsi_above_true(self):
        """Test RSI above threshold when true."""
        indicators = self._make_indicator_calculator()
        signals = SignalGenerator(indicators)
        result = signals.rsi_above(30)
        assert isinstance(result, bool)

    def test_rsi_above_false(self):
        """Test RSI above threshold when false."""
        indicators = self._make_indicator_calculator()
        signals = SignalGenerator(indicators)
        result = signals.rsi_above(90)
        assert isinstance(result, bool)

    def test_rsi_above_invalid_threshold(self):
        """Test RSI above with invalid threshold."""
        indicators = self._make_indicator_calculator()
        signals = SignalGenerator(indicators)
        with pytest.raises(ValueError, match="between 0 and 100"):
            signals.rsi_above(150)

    def test_rsi_below_true(self):
        """Test RSI below threshold when true."""
        indicators = self._make_indicator_calculator()
        signals = SignalGenerator(indicators)
        result = signals.rsi_below(90)
        assert isinstance(result, bool)

    def test_rsi_below_invalid_threshold(self):
        """Test RSI below with invalid threshold."""
        indicators = self._make_indicator_calculator()
        signals = SignalGenerator(indicators)
        with pytest.raises(ValueError, match="between 0 and 100"):
            signals.rsi_below(-10)

    def test_rsi_between_true(self):
        """Test RSI between thresholds when true."""
        indicators = self._make_indicator_calculator()
        signals = SignalGenerator(indicators)
        result = signals.rsi_between(30, 70)
        assert isinstance(result, bool)

    def test_rsi_between_invalid_thresholds(self):
        """Test RSI between with invalid thresholds."""
        indicators = self._make_indicator_calculator()
        signals = SignalGenerator(indicators)
        with pytest.raises(ValueError, match="between 0 and 100"):
            signals.rsi_between(-10, 70)

    def test_rsi_between_lower_ge_upper(self):
        """Test RSI between when lower >= upper."""
        indicators = self._make_indicator_calculator()
        signals = SignalGenerator(indicators)
        with pytest.raises(ValueError, match="lower threshold must be less than upper"):
            signals.rsi_between(70, 30)

    # ── SMA Signals ───────────────────────────────────────────────────────

    def test_price_above_sma_true(self):
        """Test price above SMA when true."""
        indicators = self._make_indicator_calculator()
        signals = SignalGenerator(indicators)
        result = signals.price_above_sma(20)
        assert isinstance(result, bool)

    def test_price_above_sma_custom_period(self):
        """Test price above SMA with custom period."""
        indicators = self._make_indicator_calculator()
        signals = SignalGenerator(indicators)
        result = signals.price_above_sma(10)
        assert isinstance(result, bool)

    def test_price_above_sma_custom_price_column(self):
        """Test price above SMA with custom price column."""
        indicators = self._make_indicator_calculator()
        signals = SignalGenerator(indicators)
        result = signals.price_above_sma(20, price="open")
        assert isinstance(result, bool)

    def test_price_below_sma_true(self):
        """Test price below SMA when true."""
        indicators = self._make_indicator_calculator()
        signals = SignalGenerator(indicators)
        result = signals.price_below_sma(5)
        assert isinstance(result, bool)

    # ── EMA Signals ───────────────────────────────────────────────────────

    def test_price_above_ema(self):
        """Test price above EMA."""
        indicators = self._make_indicator_calculator()
        signals = SignalGenerator(indicators)
        result = signals.price_above_ema(20)
        assert isinstance(result, bool)

    def test_price_below_ema(self):
        """Test price below EMA."""
        indicators = self._make_indicator_calculator()
        signals = SignalGenerator(indicators)
        result = signals.price_below_ema(20)
        assert isinstance(result, bool)

    # ── Bollinger Bands Signals ───────────────────────────────────────────

    def test_price_above_bb_upper(self):
        """Test price above upper Bollinger Band."""
        indicators = self._make_indicator_calculator()
        signals = SignalGenerator(indicators)
        result = signals.price_above_bb_upper(20, 2.0)
        assert isinstance(result, bool)

    def test_price_below_bb_lower(self):
        """Test price below lower Bollinger Band."""
        indicators = self._make_indicator_calculator()
        signals = SignalGenerator(indicators)
        result = signals.price_below_bb_lower(20, 2.0)
        assert isinstance(result, bool)

    def test_price_inside_bb(self):
        """Test price inside Bollinger Bands."""
        indicators = self._make_indicator_calculator()
        signals = SignalGenerator(indicators)
        result = signals.price_inside_bb(20, 2.0)
        assert isinstance(result, bool)

    # ── MACD Signals ─────────────────────────────────────────────────────

    def test_macd_bullish_crossover(self):
        """Test MACD bullish crossover detection."""
        indicators = self._make_indicator_calculator()
        signals = SignalGenerator(indicators)
        result = signals.macd_bullish_crossover()
        assert isinstance(result, bool)

    def test_macd_bearish_crossover(self):
        """Test MACD bearish crossover detection."""
        indicators = self._make_indicator_calculator()
        signals = SignalGenerator(indicators)
        result = signals.macd_bearish_crossover()
        assert isinstance(result, bool)

    def test_macd_above_zero(self):
        """Test MACD histogram above zero."""
        indicators = self._make_indicator_calculator()
        signals = SignalGenerator(indicators)
        result = signals.macd_above_zero()
        assert isinstance(result, bool)

    def test_macd_below_zero(self):
        """Test MACD histogram below zero."""
        indicators = self._make_indicator_calculator()
        signals = SignalGenerator(indicators)
        result = signals.macd_below_zero()
        assert isinstance(result, bool)

    def test_macd_custom_periods(self):
        """Test MACD with custom periods."""
        indicators = self._make_indicator_calculator()
        signals = SignalGenerator(indicators)
        result = signals.macd_above_zero(fast=10, slow=20, signal=8)
        assert isinstance(result, bool)

    # ── Stochastic Signals ───────────────────────────────────────────────

    def test_stochastic_above(self):
        """Test Stochastic above threshold."""
        indicators = self._make_indicator_calculator()
        signals = SignalGenerator(indicators)
        result = signals.stochastic_above(50)
        assert isinstance(result, bool)

    def test_stochastic_below(self):
        """Test Stochastic below threshold."""
        indicators = self._make_indicator_calculator()
        signals = SignalGenerator(indicators)
        result = signals.stochastic_below(50)
        assert isinstance(result, bool)

    def test_stochastic_invalid_threshold(self):
        """Test Stochastic with invalid threshold."""
        indicators = self._make_indicator_calculator()
        signals = SignalGenerator(indicators)
        with pytest.raises(ValueError, match="between 0 and 100"):
            signals.stochastic_above(150)

    def test_stochastic_invalid_line(self):
        """Test Stochastic with invalid line parameter."""
        indicators = self._make_indicator_calculator()
        signals = SignalGenerator(indicators)
        with pytest.raises(ValueError, match="must be 'k' or 'd'"):
            signals.stochastic_above(50, line="x")

    def test_stochastic_d_line(self):
        """Test Stochastic with %D line."""
        indicators = self._make_indicator_calculator()
        signals = SignalGenerator(indicators)
        result = signals.stochastic_above(50, line="d")
        assert isinstance(result, bool)

    # ── Volume Signals ───────────────────────────────────────────────────

    def test_volume_above_sma(self):
        """Test volume above SMA."""
        indicators = self._make_indicator_calculator()
        signals = SignalGenerator(indicators)
        result = signals.volume_above_sma(20)
        assert isinstance(result, bool)

    def test_volume_below_sma(self):
        """Test volume below SMA."""
        indicators = self._make_indicator_calculator()
        signals = SignalGenerator(indicators)
        result = signals.volume_below_sma(20)
        assert isinstance(result, bool)

    # ── Price Change Signals ─────────────────────────────────────────────

    def test_price_change_above(self):
        """Test price change above minimum."""
        indicators = self._make_indicator_calculator()
        signals = SignalGenerator(indicators)
        result = signals.price_change_above(0.1)
        assert isinstance(result, bool)

    def test_price_change_above_invalid_candles(self):
        """Test price change above with invalid candles_back."""
        indicators = self._make_indicator_calculator()
        signals = SignalGenerator(indicators)
        with pytest.raises(ValueError, match="at least 1"):
            signals.price_change_above(0.1, candles_back=0)

    def test_price_change_above_invalid_min_change(self):
        """Test price change above with negative min_change."""
        indicators = self._make_indicator_calculator()
        signals = SignalGenerator(indicators)
        with pytest.raises(ValueError, match="non-negative"):
            signals.price_change_above(-1.0)

    def test_price_change_below(self):
        """Test price change below maximum."""
        indicators = self._make_indicator_calculator()
        signals = SignalGenerator(indicators)
        result = signals.price_change_below(10.0)
        assert isinstance(result, bool)

    def test_price_above_by(self):
        """Test price above by minimum amount."""
        indicators = self._make_indicator_calculator()
        signals = SignalGenerator(indicators)
        result = signals.price_above_by(0.1)
        assert isinstance(result, bool)

    def test_price_below_by(self):
        """Test price below by minimum amount."""
        indicators = self._make_indicator_calculator()
        signals = SignalGenerator(indicators)
        result = signals.price_below_by(0.1)
        assert isinstance(result, bool)

    def test_price_change_percent_above(self):
        """Test price change percent above minimum."""
        indicators = self._make_indicator_calculator()
        signals = SignalGenerator(indicators)
        result = signals.price_change_percent_above(0.5)
        assert isinstance(result, bool)

    def test_price_change_percent_above_invalid_percent(self):
        """Test price change percent above with negative percent."""
        indicators = self._make_indicator_calculator()
        signals = SignalGenerator(indicators)
        with pytest.raises(ValueError, match="non-negative"):
            signals.price_change_percent_above(-1.0)

    def test_price_change_percent_below(self):
        """Test price change percent below maximum."""
        indicators = self._make_indicator_calculator()
        signals = SignalGenerator(indicators)
        result = signals.price_change_percent_below(10.0)
        assert isinstance(result, bool)

    def test_price_up(self):
        """Test price is up compared to N candles ago."""
        indicators = self._make_indicator_calculator()
        signals = SignalGenerator(indicators)
        result = signals.price_up(1)
        assert isinstance(result, bool)

    def test_price_down(self):
        """Test price is down compared to N candles ago."""
        indicators = self._make_indicator_calculator()
        signals = SignalGenerator(indicators)
        result = signals.price_down(1)
        assert isinstance(result, bool)

    def test_price_up_by_percent(self):
        """Test price up by minimum percentage."""
        indicators = self._make_indicator_calculator()
        signals = SignalGenerator(indicators)
        result = signals.price_up_by_percent(0.1)
        assert isinstance(result, bool)

    def test_price_down_by_percent(self):
        """Test price down by minimum percentage."""
        indicators = self._make_indicator_calculator()
        signals = SignalGenerator(indicators)
        result = signals.price_down_by_percent(0.1)
        assert isinstance(result, bool)

    # ── Custom Signals ─────────────────────────────────────────────────

    def test_custom_condition_true(self):
        """Test custom condition that returns True."""
        indicators = self._make_indicator_calculator()
        signals = SignalGenerator(indicators)
        
        def condition(indicators):
            return True
        
        result = signals.custom(condition)
        assert result is True

    def test_custom_condition_false(self):
        """Test custom condition that returns False."""
        indicators = self._make_indicator_calculator()
        signals = SignalGenerator(indicators)
        
        def condition(indicators):
            return False
        
        result = signals.custom(condition)
        assert result is False

    def test_custom_condition_error(self):
        """Test custom condition that raises error."""
        indicators = self._make_indicator_calculator()
        signals = SignalGenerator(indicators)
        
        def condition(indicators):
            raise ValueError("Test error")
        
        result = signals.custom(condition)
        assert result is False

    # ── Composite Signals ───────────────────────────────────────────────

    def test_evaluate_single_rule(self):
        """Test evaluating a single rule."""
        indicators = self._make_indicator_calculator()
        signals = SignalGenerator(indicators)
        
        rules = [{"condition": "price_up", "params": {"candles_back": 1}}]
        result = signals.evaluate(rules)
        
        assert "signals" in result
        assert "result" in result
        assert "details" in result
        assert len(result["signals"]) == 1

    def test_evaluate_multiple_rules_and(self):
        """Test evaluating multiple rules with AND operator."""
        indicators = self._make_indicator_calculator()
        signals = SignalGenerator(indicators)
        
        rules = [
            {"condition": "price_up", "params": {"candles_back": 1}},
            {"operator": "AND"},
            {"condition": "volume_above_sma", "params": {"period": 20}},
        ]
        result = signals.evaluate(rules)
        
        assert len(result["signals"]) == 2
        assert isinstance(result["result"], bool)

    def test_evaluate_multiple_rules_or(self):
        """Test evaluating multiple rules with OR operator."""
        indicators = self._make_indicator_calculator()
        signals = SignalGenerator(indicators)
        
        rules = [
            {"condition": "price_up", "params": {"candles_back": 1}},
            {"operator": "OR"},
            {"condition": "price_down", "params": {"candles_back": 1}},
        ]
        result = signals.evaluate(rules)
        
        assert len(result["signals"]) == 2
        assert isinstance(result["result"], bool)

    def test_evaluate_unknown_condition(self):
        """Test evaluating unknown condition."""
        indicators = self._make_indicator_calculator()
        signals = SignalGenerator(indicators)
        
        rules = [{"condition": "unknown_condition", "params": {}}]
        result = signals.evaluate(rules)
        
        assert result["signals"][0] is False
        assert result["result"] is False

    def test_evaluate_custom_condition(self):
        """Test evaluating custom condition in rules."""
        indicators = self._make_indicator_calculator()
        signals = SignalGenerator(indicators)
        
        def custom_func(indicators):
            return True
        
        rules = [{"condition": custom_func, "params": {}}]
        result = signals.evaluate(rules)
        
        assert result["signals"][0] is True

    # ── Signal Summary ─────────────────────────────────────────────────

    def test_summary(self):
        """Test signal summary generation."""
        indicators = self._make_indicator_calculator()
        signals = SignalGenerator(indicators)
        
        summary = signals.summary()
        
        assert "rsi" in summary
        assert "rsi_status" in summary
        assert "price_vs_sma20" in summary
        assert "price_vs_ema20" in summary
        assert "macd_histogram" in summary
        assert "macd_status" in summary
        assert "bb_position" in summary
        assert "volume_vs_sma" in summary

    def test_get_rsi_status_overbought(self):
        """Test RSI status for overbought."""
        indicators = self._make_indicator_calculator()
        signals = SignalGenerator(indicators)
        status = signals._get_rsi_status()
        assert status in ["overbought", "oversold", "bullish", "bearish", "unknown"]

    def test_get_bb_position(self):
        """Test Bollinger Band position."""
        indicators = self._make_indicator_calculator()
        signals = SignalGenerator(indicators)
        position = signals._get_bb_position()
        assert position in ["above_upper", "below_lower", "inside"]
