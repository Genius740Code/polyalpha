"""Base class for :class:`SignalGenerator` — shared state and custom signals."""

from __future__ import annotations

import logging
from typing import Callable

from ..indicators import IndicatorCalculator

log = logging.getLogger(__name__)


class SignalGeneratorBase:
    """
    Base for :class:`SignalGenerator`.

    Provides the shared ``indicators`` / ``data`` / logger state consumed by
    every signal mixin, plus the :meth:`custom` escape hatch.

    Parameters
    ----------
    indicators : IndicatorCalculator
        Indicator calculator with calculated indicators.
    """

    def __init__(self, indicators: IndicatorCalculator):
        """Initialize signal generator."""
        self.indicators = indicators
        self._data = indicators.data
        self._log = logging.getLogger(__name__)

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
