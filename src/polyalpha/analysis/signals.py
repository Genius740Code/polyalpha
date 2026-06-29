"""
Signal generation for trading strategies.

Provides a clean interface for generating trading signals from technical
indicators. Supports simple conditions, composite signals, and custom logic.

Usage
-----
    from polyalpha.analysis import SignalGenerator

    signals = SignalGenerator(indicators)
    if signals.rsi_above(40) and signals.price_above_sma(20):
        print("BUY signal")
"""

from __future__ import annotations

import logging
from typing import Callable, Optional, Any

import pandas as pd

from .indicators import IndicatorCalculator

log = logging.getLogger(__name__)


# ── Signal Generator ───────────────────────────────────────────────────────

class SignalGenerator:
    """
    Generate trading signals from technical indicators.

    Parameters
    ----------
    indicators : IndicatorCalculator
        Indicator calculator with calculated indicators.

    Example
    -------
    >>> signals = SignalGenerator(indicators)
    >>> if signals.rsi_above(40):
    ...     print("RSI signal triggered")
    """

    def __init__(self, indicators: IndicatorCalculator):
        """Initialize signal generator."""
        self.indicators = indicators
        self._data = indicators.data
        self._log = logging.getLogger(__name__)

    # ── Simple Signals ───────────────────────────────────────────────────────

    def rsi_above(self, threshold: float, period: int = 14) -> bool:
        """
        Check if RSI is above threshold.

        Parameters
        ----------
        threshold : float
            RSI threshold (0-100).
        period : int
            RSI period (default: 14).

        Returns
        -------
        bool
            True if RSI > threshold.
        """
        if not (0 <= threshold <= 100):
            raise ValueError("RSI threshold must be between 0 and 100")

        rsi = self.indicators.rsi(period)
        latest = self.indicators.get_latest_value(rsi)

        if latest is None:
            self._log.warning("RSI data unavailable")
            return False

        return latest > threshold

    def rsi_below(self, threshold: float, period: int = 14) -> bool:
        """
        Check if RSI is below threshold.

        Parameters
        ----------
        threshold : float
            RSI threshold (0-100).
        period : int
            RSI period (default: 14).

        Returns
        -------
        bool
            True if RSI < threshold.
        """
        if not (0 <= threshold <= 100):
            raise ValueError("RSI threshold must be between 0 and 100")

        rsi = self.indicators.rsi(period)
        latest = self.indicators.get_latest_value(rsi)

        if latest is None:
            self._log.warning("RSI data unavailable")
            return False

        return latest < threshold

    def rsi_between(self, lower: float, upper: float, period: int = 14) -> bool:
        """
        Check if RSI is between two thresholds.

        Parameters
        ----------
        lower : float
            Lower threshold (0-100).
        upper : float
            Upper threshold (0-100).
        period : int
            RSI period (default: 14).

        Returns
        -------
        bool
            True if lower < RSI < upper.
        """
        if not (0 <= lower <= 100 and 0 <= upper <= 100):
            raise ValueError("RSI thresholds must be between 0 and 100")
        if lower >= upper:
            raise ValueError("lower threshold must be less than upper")

        rsi = self.indicators.rsi(period)
        latest = self.indicators.get_latest_value(rsi)

        if latest is None:
            self._log.warning("RSI data unavailable")
            return False

        return lower < latest < upper

    def price_above_sma(self, period: int = 20, price: str = "close") -> bool:
        """
        Check if price is above SMA.

        Parameters
        ----------
        period : int
            SMA period (default: 20).
        price : str
            Price column to use (default: "close").

        Returns
        -------
        bool
            True if price > SMA.
        """
        sma = self.indicators.sma(period, price)
        latest_sma = self.indicators.get_latest_value(sma)
        latest_price = self._data[price].iloc[-1]

        if latest_sma is None:
            self._log.warning("SMA data unavailable")
            return False

        return latest_price > latest_sma

    def price_below_sma(self, period: int = 20, price: str = "close") -> bool:
        """
        Check if price is below SMA.

        Parameters
        ----------
        period : int
            SMA period (default: 20).
        price : str
            Price column to use (default: "close").

        Returns
        -------
        bool
            True if price < SMA.
        """
        sma = self.indicators.sma(period, price)
        latest_sma = self.indicators.get_latest_value(sma)
        latest_price = self._data[price].iloc[-1]

        if latest_sma is None:
            self._log.warning("SMA data unavailable")
            return False

        return latest_price < latest_sma

    def price_above_ema(self, period: int = 20, price: str = "close") -> bool:
        """
        Check if price is above EMA.

        Parameters
        ----------
        period : int
            EMA period (default: 20).
        price : str
            Price column to use (default: "close").

        Returns
        -------
        bool
            True if price > EMA.
        """
        ema = self.indicators.ema(period, price)
        latest_ema = self.indicators.get_latest_value(ema)
        latest_price = self._data[price].iloc[-1]

        if latest_ema is None:
            self._log.warning("EMA data unavailable")
            return False

        return latest_price > latest_ema

    def price_below_ema(self, period: int = 20, price: str = "close") -> bool:
        """
        Check if price is below EMA.

        Parameters
        ----------
        period : int
            EMA period (default: 20).
        price : str
            Price column to use (default: "close").

        Returns
        -------
        bool
            True if price < EMA.
        """
        ema = self.indicators.ema(period, price)
        latest_ema = self.indicators.get_latest_value(ema)
        latest_price = self._data[price].iloc[-1]

        if latest_ema is None:
            self._log.warning("EMA data unavailable")
            return False

        return latest_price < latest_ema

    def price_above_bb_upper(
        self,
        period: int = 20,
        std_dev: float = 2.0,
        price: str = "close"
    ) -> bool:
        """
        Check if price is above upper Bollinger Band.

        Parameters
        ----------
        period : int
            BB period (default: 20).
        std_dev : float
            Standard deviation multiplier (default: 2.0).
        price : str
            Price column to use (default: "close").

        Returns
        -------
        bool
            True if price > upper BB.
        """
        bb = self.indicators.bollinger_bands(period, std_dev, price)
        latest_upper = self.indicators.get_latest_value(bb["upper"])
        latest_price = self._data[price].iloc[-1]

        if latest_upper is None:
            self._log.warning("Bollinger Bands data unavailable")
            return False

        return latest_price > latest_upper

    def price_below_bb_lower(
        self,
        period: int = 20,
        std_dev: float = 2.0,
        price: str = "close"
    ) -> bool:
        """
        Check if price is below lower Bollinger Band.

        Parameters
        ----------
        period : int
            BB period (default: 20).
        std_dev : float
            Standard deviation multiplier (default: 2.0).
        price : str
            Price column to use (default: "close").

        Returns
        -------
        bool
            True if price < lower BB.
        """
        bb = self.indicators.bollinger_bands(period, std_dev, price)
        latest_lower = self.indicators.get_latest_value(bb["lower"])
        latest_price = self._data[price].iloc[-1]

        if latest_lower is None:
            self._log.warning("Bollinger Bands data unavailable")
            return False

        return latest_price < latest_lower

    def price_inside_bb(
        self,
        period: int = 20,
        std_dev: float = 2.0,
        price: str = "close"
    ) -> bool:
        """
        Check if price is inside Bollinger Bands.

        Parameters
        ----------
        period : int
            BB period (default: 20).
        std_dev : float
            Standard deviation multiplier (default: 2.0).
        price : str
            Price column to use (default: "close").

        Returns
        -------
        bool
            True if lower BB < price < upper BB.
        """
        bb = self.indicators.bollinger_bands(period, std_dev, price)
        latest_upper = self.indicators.get_latest_value(bb["upper"])
        latest_lower = self.indicators.get_latest_value(bb["lower"])
        latest_price = self._data[price].iloc[-1]

        if latest_upper is None or latest_lower is None:
            self._log.warning("Bollinger Bands data unavailable")
            return False

        return latest_lower < latest_price < latest_upper

    def macd_bullish_crossover(
        self,
        fast: int = 12,
        slow: int = 26,
        signal: int = 9
    ) -> bool:
        """
        Check if MACD line crossed above signal line (bullish).

        Parameters
        ----------
        fast : int
            Fast period (default: 12).
        slow : int
            Slow period (default: 26).
        signal : int
            Signal period (default: 9).

        Returns
        -------
        bool
            True if MACD crossed above signal.
        """
        macd_data = self.indicators.macd(fast, slow, signal)
        macd = macd_data["macd"]
        signal_line = macd_data["signal"]

        # Need at least 2 values to check crossover
        if len(macd) < 2:
            self._log.warning("Insufficient MACD data for crossover check")
            return False

        # Get last 2 non-NaN values
        macd_values = macd.dropna().tail(2)
        signal_values = signal_line.dropna().tail(2)

        if len(macd_values) < 2 or len(signal_values) < 2:
            self._log.warning("Insufficient MACD data for crossover check")
            return False

        # Check crossover: MACD was below signal, now above
        prev_macd = macd_values.iloc[-2]
        curr_macd = macd_values.iloc[-1]
        prev_signal = signal_values.iloc[-2]
        curr_signal = signal_values.iloc[-1]

        return prev_macd <= prev_signal and curr_macd > curr_signal

    def macd_bearish_crossover(
        self,
        fast: int = 12,
        slow: int = 26,
        signal: int = 9
    ) -> bool:
        """
        Check if MACD line crossed below signal line (bearish).

        Parameters
        ----------
        fast : int
            Fast period (default: 12).
        slow : int
            Slow period (default: 26).
        signal : int
            Signal period (default: 9).

        Returns
        -------
        bool
            True if MACD crossed below signal.
        """
        macd_data = self.indicators.macd(fast, slow, signal)
        macd = macd_data["macd"]
        signal_line = macd_data["signal"]

        # Need at least 2 values to check crossover
        if len(macd) < 2:
            self._log.warning("Insufficient MACD data for crossover check")
            return False

        # Get last 2 non-NaN values
        macd_values = macd.dropna().tail(2)
        signal_values = signal_line.dropna().tail(2)

        if len(macd_values) < 2 or len(signal_values) < 2:
            self._log.warning("Insufficient MACD data for crossover check")
            return False

        # Check crossover: MACD was above signal, now below
        prev_macd = macd_values.iloc[-2]
        curr_macd = macd_values.iloc[-1]
        prev_signal = signal_values.iloc[-2]
        curr_signal = signal_values.iloc[-1]

        return prev_macd >= prev_signal and curr_macd < curr_signal

    def macd_above_zero(
        self,
        fast: int = 12,
        slow: int = 26,
        signal: int = 9
    ) -> bool:
        """
        Check if MACD histogram is positive.

        Parameters
        ----------
        fast : int
            Fast period (default: 12).
        slow : int
            Slow period (default: 26).
        signal : int
            Signal period (default: 9).

        Returns
        -------
        bool
            True if MACD histogram > 0.
        """
        macd_data = self.indicators.macd(fast, slow, signal)
        histogram = macd_data["histogram"]
        latest = self.indicators.get_latest_value(histogram)

        if latest is None:
            self._log.warning("MACD histogram data unavailable")
            return False

        return latest > 0

    def macd_below_zero(
        self,
        fast: int = 12,
        slow: int = 26,
        signal: int = 9
    ) -> bool:
        """
        Check if MACD histogram is negative.

        Parameters
        ----------
        fast : int
            Fast period (default: 12).
        slow : int
            Slow period (default: 26).
        signal : int
            Signal period (default: 9).

        Returns
        -------
        bool
            True if MACD histogram < 0.
        """
        macd_data = self.indicators.macd(fast, slow, signal)
        histogram = macd_data["histogram"]
        latest = self.indicators.get_latest_value(histogram)

        if latest is None:
            self._log.warning("MACD histogram data unavailable")
            return False

        return latest < 0

    def stochastic_above(
        self,
        threshold: float,
        k_period: int = 14,
        d_period: int = 3,
        line: str = "k"
    ) -> bool:
        """
        Check if Stochastic line is above threshold.

        Parameters
        ----------
        threshold : float
            Threshold (0-100).
        k_period : int
            %K period (default: 14).
        d_period : int
            %D period (default: 3).
        line : str
            Line to check: "k" or "d" (default: "k").

        Returns
        -------
        bool
            True if line > threshold.
        """
        if not (0 <= threshold <= 100):
            raise ValueError("Stochastic threshold must be between 0 and 100")
        if line not in ["k", "d"]:
            raise ValueError("line must be 'k' or 'd'")

        stoch = self.indicators.stochastic(k_period, d_period)
        latest = self.indicators.get_latest_value(stoch[line])

        if latest is None:
            self._log.warning("Stochastic data unavailable")
            return False

        return latest > threshold

    def stochastic_below(
        self,
        threshold: float,
        k_period: int = 14,
        d_period: int = 3,
        line: str = "k"
    ) -> bool:
        """
        Check if Stochastic line is below threshold.

        Parameters
        ----------
        threshold : float
            Threshold (0-100).
        k_period : int
            %K period (default: 14).
        d_period : int
            %D period (default: 3).
        line : str
            Line to check: "k" or "d" (default: "k").

        Returns
        -------
        bool
            True if line < threshold.
        """
        if not (0 <= threshold <= 100):
            raise ValueError("Stochastic threshold must be between 0 and 100")
        if line not in ["k", "d"]:
            raise ValueError("line must be 'k' or 'd'")

        stoch = self.indicators.stochastic(k_period, d_period)
        latest = self.indicators.get_latest_value(stoch[line])

        if latest is None:
            self._log.warning("Stochastic data unavailable")
            return False

        return latest < threshold

    def volume_above_sma(self, period: int = 20) -> bool:
        """
        Check if volume is above SMA.

        Parameters
        ----------
        period : int
            SMA period (default: 20).

        Returns
        -------
        bool
            True if volume > volume SMA.
        """
        vol_sma = self.indicators.volume_sma(period)
        latest_sma = self.indicators.get_latest_value(vol_sma)
        latest_volume = self._data["volume"].iloc[-1]

        if latest_sma is None:
            self._log.warning("Volume SMA data unavailable")
            return False

        return latest_volume > latest_sma

    def volume_below_sma(self, period: int = 20) -> bool:
        """
        Check if volume is below SMA.

        Parameters
        ----------
        period : int
            SMA period (default: 20).

        Returns
        -------
        bool
            True if volume < volume SMA.
        """
        vol_sma = self.indicators.volume_sma(period)
        latest_sma = self.indicators.get_latest_value(vol_sma)
        latest_volume = self._data["volume"].iloc[-1]

        if latest_sma is None:
            self._log.warning("Volume SMA data unavailable")
            return False

        return latest_volume < latest_sma

    # ── Custom Signals ───────────────────────────────────────────────────────

    def custom(self, condition: Callable[[IndicatorCalculator], bool]) -> bool:
        """
        Evaluate custom condition function.

        Parameters
        ----------
        condition : Callable
            Function that takes IndicatorCalculator and returns bool.

        Returns
        -------
        bool
            Result of custom condition.

        Example
        -------
        >>> def my_strategy(indicators):
        ...     rsi = indicators.rsi(14)
        ...     sma = indicators.sma(20)
        ...     latest_rsi = indicators.get_latest_value(rsi)
        ...     latest_sma = indicators.get_latest_value(sma)
        ...     price = indicators.data["close"].iloc[-1]
        ...     return latest_rsi > 40 and price > latest_sma
        >>>
        >>> signals.custom(my_strategy)
        """
        try:
            return condition(self.indicators)
        except Exception as exc:
            self._log.error("Custom condition error: %s", exc)
            return False

    # ── Composite Signals ───────────────────────────────────────────────────

    def evaluate(self, rules: list[dict]) -> dict:
        """
        Evaluate multiple signal rules.

        Parameters
        ----------
        rules : list[dict]
            List of rule dictionaries. Each rule has:
            - "condition": str or Callable
            - "params": dict (optional)
            - "operator": "AND" | "OR" (optional, for chaining)

        Returns
        -------
        dict
            Dictionary with evaluation results.

        Example
        -------
        >>> rules = [
        ...     {"condition": "rsi_above", "params": {"threshold": 40}},
        ...     {"condition": "price_above_sma", "params": {"period": 20}},
        ...     {"operator": "AND"},
        ... ]
        >>> result = signals.evaluate(rules)
        """
        results = {
            "signals": [],
            "result": True,
            "details": [],
        }

        current_result = True
        current_operator = "AND"

        for rule in rules:
            # Check for operator
            if "operator" in rule:
                current_operator = rule["operator"].upper()
                continue

            # Get condition
            condition = rule["condition"]
            params = rule.get("params", {})

            # Evaluate condition
            if isinstance(condition, str):
                # Built-in condition
                if hasattr(self, condition):
                    method = getattr(self, condition)
                    try:
                        result = method(**params)
                    except Exception as exc:
                        self._log.error("Error evaluating %s: %s", condition, exc)
                        result = False
                else:
                    self._log.error("Unknown condition: %s", condition)
                    result = False
            elif callable(condition):
                # Custom condition
                result = self.custom(condition)
            else:
                self._log.error("Invalid condition type: %s", type(condition))
                result = False

            # Store result
            results["signals"].append(result)
            results["details"].append({
                "condition": str(condition),
                "params": params,
                "result": result,
            })

            # Apply operator
            if current_operator == "AND":
                current_result = current_result and result
            elif current_operator == "OR":
                current_result = current_result or result

        results["result"] = current_result
        return results

    # ── Signal Summary ─────────────────────────────────────────────────────

    def summary(self) -> dict:
        """
        Generate a summary of current signal states.

        Returns
        -------
        dict
            Dictionary with common signal states.
        """
        summary = {
            "rsi": self.indicators.get_latest_value(self.indicators.rsi(14)),
            "rsi_status": self._get_rsi_status(),
            "price_vs_sma20": self.price_above_sma(20),
            "price_vs_ema20": self.price_above_ema(20),
            "macd_histogram": self.indicators.get_latest_value(
                self.indicators.macd()["histogram"]
            ),
            "macd_status": "bullish" if self.macd_above_zero() else "bearish",
            "bb_position": self._get_bb_position(),
            "volume_vs_sma": self.volume_above_sma(20),
        }

        return summary

    def _get_rsi_status(self) -> str:
        """Get RSI status description."""
        rsi = self.indicators.get_latest_value(self.indicators.rsi(14))
        if rsi is None:
            return "unknown"

        if rsi > 70:
            return "overbought"
        elif rsi < 30:
            return "oversold"
        elif rsi > 50:
            return "bullish"
        else:
            return "bearish"

    def _get_bb_position(self) -> str:
        """Get Bollinger Band position description."""
        if self.price_above_bb_upper():
            return "above_upper"
        elif self.price_below_bb_lower():
            return "below_lower"
        else:
            return "inside"
