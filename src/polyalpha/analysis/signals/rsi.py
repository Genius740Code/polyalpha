"""RSI-based signal mixin for :class:`SignalGenerator`."""

from __future__ import annotations

from .base import SignalGeneratorBase


class RSISignalsMixin(SignalGeneratorBase):
    """Signal mixin. Inherits shared indicator state from SignalGeneratorBase."""
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

        return bool(latest > threshold)


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

        return bool(latest < threshold)


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

        return bool(lower < latest < upper)


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

