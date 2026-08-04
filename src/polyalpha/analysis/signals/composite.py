"""Assembled :class:`SignalGenerator` composing all signal mixins."""

from __future__ import annotations

from typing import Any

from .base import SignalGeneratorBase
from .bollinger import BollingerSignalsMixin
from .donchian import DonchianSignalsMixin
from .ichimoku import IchimokuSignalsMixin
from .macd import MACDSignalsMixin
from .moving_average import MovingAverageSignalsMixin
from .price_change import PriceChangeSignalsMixin
from .psar import PSARSignalsMixin
from .rsi import RSISignalsMixin
from .stochastic import StochasticSignalsMixin
from .supertrend import SupertrendSignalsMixin
from .volume import VolumeSignalsMixin


class SignalGenerator(RSISignalsMixin, MovingAverageSignalsMixin, BollingerSignalsMixin, DonchianSignalsMixin, MACDSignalsMixin, StochasticSignalsMixin, VolumeSignalsMixin, SupertrendSignalsMixin, PSARSignalsMixin, IchimokuSignalsMixin, PriceChangeSignalsMixin, SignalGeneratorBase):
    """
    Generate trading signals from technical indicators.

    Composed from per-indicator mixins; exposes a single public class.
    Import from ``polyalpha.analysis`` or ``polyalpha.analysis.signals``.

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

    def evaluate(self, rules: list[dict[str, Any]]) -> dict[str, Any]:
        """
        Evaluate multiple signal rules.

        Parameters
        ----------
        rules : list[dict[str, Any]]
            List of rule dictionaries. Each rule has:
            - "condition": str or Callable
            - "params": dict (optional)
            - "operator": "AND" | "OR" (optional, for chaining)

        Returns
        -------
        dict[str, Any]
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
        results: dict[str, Any] = {
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


    def summary(self) -> dict[str, Any]:
        """
        Generate a summary of current signal states.

        Returns
        -------
        dict[str, Any]
            Dictionary with common signal states.
        """
        summary: dict[str, Any] = {
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

