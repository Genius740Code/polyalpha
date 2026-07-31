"""MACD signal mixin for :class:`SignalGenerator`."""

from __future__ import annotations

from .base import SignalGeneratorBase


class MACDSignalsMixin(SignalGeneratorBase):
    """Signal mixin. Inherits shared indicator state from SignalGeneratorBase."""
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

        return bool(prev_macd <= prev_signal and curr_macd > curr_signal)


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

        return bool(prev_macd >= prev_signal and curr_macd < curr_signal)


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

        return bool(latest > 0)


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

        return bool(latest < 0)

