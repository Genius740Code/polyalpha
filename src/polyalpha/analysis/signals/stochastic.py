"""Stochastic oscillator signal mixin for :class:`SignalGenerator`."""

from __future__ import annotations

from .base import SignalGeneratorBase


class StochasticSignalsMixin(SignalGeneratorBase):
    """Signal mixin. Inherits shared indicator state from SignalGeneratorBase."""
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

        return bool(latest > threshold)


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

        return bool(latest < threshold)

