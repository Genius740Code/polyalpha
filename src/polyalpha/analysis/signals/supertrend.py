"""SuperTrend signal mixin for :class:`SignalGenerator`."""

from __future__ import annotations

from .base import SignalGeneratorBase


class SupertrendSignalsMixin(SignalGeneratorBase):
    """Signal mixin. Inherits shared indicator state from SignalGeneratorBase."""
    def supertrend_uptrend(self, period: int = 7, multiplier: float = 3.0) -> bool:
        """
        Check if SuperTrend indicates an uptrend (direction == 1).

        Parameters
        ----------
        period : int
            ATR period (default: 7).
        multiplier : float
            ATR multiplier (default: 3.0).

        Returns
        -------
        bool
            True if in uptrend.
        """
        st = self.indicators.supertrend(period, multiplier)
        direction = self.indicators.get_latest_value(st["direction"])
        if direction is None:
            self._log.warning("SuperTrend data unavailable")
            return False
        return bool(direction == 1)


    def supertrend_downtrend(self, period: int = 7, multiplier: float = 3.0) -> bool:
        """
        Check if SuperTrend indicates a downtrend (direction == -1).

        Parameters
        ----------
        period : int
            ATR period (default: 7).
        multiplier : float
            ATR multiplier (default: 3.0).

        Returns
        -------
        bool
            True if in downtrend.
        """
        st = self.indicators.supertrend(period, multiplier)
        direction = self.indicators.get_latest_value(st["direction"])
        if direction is None:
            self._log.warning("SuperTrend data unavailable")
            return False
        return bool(direction == -1)


    def supertrend_turned_up(self, period: int = 7, multiplier: float = 3.0) -> bool:
        """
        Check if SuperTrend just turned up from downtrend to uptrend.

        Parameters
        ----------
        period : int
            ATR period (default: 7).
        multiplier : float
            ATR multiplier (default: 3.0).

        Returns
        -------
        bool
            True if just turned up.
        """
        st = self.indicators.supertrend(period, multiplier)
        direction = st["direction"].dropna()
        if len(direction) < 2:
            self._log.warning("Insufficient SuperTrend data for crossover check")
            return False
        prev = direction.iloc[-2]
        curr = direction.iloc[-1]
        return bool(prev == -1 and curr == 1)


    def supertrend_turned_down(self, period: int = 7, multiplier: float = 3.0) -> bool:
        """
        Check if SuperTrend just turned down from uptrend to downtrend.

        Parameters
        ----------
        period : int
            ATR period (default: 7).
        multiplier : float
            ATR multiplier (default: 3.0).

        Returns
        -------
        bool
            True if just turned down.
        """
        st = self.indicators.supertrend(period, multiplier)
        direction = st["direction"].dropna()
        if len(direction) < 2:
            self._log.warning("Insufficient SuperTrend data for crossover check")
            return False
        prev = direction.iloc[-2]
        curr = direction.iloc[-1]
        return bool(prev == 1 and curr == -1)

