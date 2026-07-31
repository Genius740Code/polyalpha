"""Moving-average (SMA/EMA) signal mixin for :class:`SignalGenerator`."""

from __future__ import annotations

from .base import SignalGeneratorBase


class MovingAverageSignalsMixin(SignalGeneratorBase):
    """Signal mixin. Inherits shared indicator state from SignalGeneratorBase."""
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

        return bool(latest_price > latest_sma)


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

        return bool(latest_price < latest_sma)


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

        return bool(latest_price > latest_ema)


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

        return bool(latest_price < latest_ema)


    def ema_bullish_crossover(
        self,
        fast: int = 9,
        slow: int = 21,
        price: str = "close"
    ) -> bool:
        """
        Check if fast EMA crossed above slow EMA (bullish).

        Parameters
        ----------
        fast : int
            Fast EMA period (default: 9).
        slow : int
            Slow EMA period (default: 21).
        price : str
            Price column to use (default: "close").

        Returns
        -------
        bool
            True if fast EMA crossed above slow EMA.
        """
        if fast >= slow:
            raise ValueError("fast period must be less than slow period")

        fast_ema = self.indicators.ema(fast, price)
        slow_ema = self.indicators.ema(slow, price)

        fast_values = fast_ema.dropna().tail(2)
        slow_values = slow_ema.dropna().tail(2)

        if len(fast_values) < 2 or len(slow_values) < 2:
            self._log.warning("Insufficient EMA data for crossover check")
            return False

        prev_fast = fast_values.iloc[-2]
        curr_fast = fast_values.iloc[-1]
        prev_slow = slow_values.iloc[-2]
        curr_slow = slow_values.iloc[-1]

        return bool(prev_fast <= prev_slow and curr_fast > curr_slow)


    def ema_bearish_crossover(
        self,
        fast: int = 9,
        slow: int = 21,
        price: str = "close"
    ) -> bool:
        """
        Check if fast EMA crossed below slow EMA (bearish).

        Parameters
        ----------
        fast : int
            Fast EMA period (default: 9).
        slow : int
            Slow EMA period (default: 21).
        price : str
            Price column to use (default: "close").

        Returns
        -------
        bool
            True if fast EMA crossed below slow EMA.
        """
        if fast >= slow:
            raise ValueError("fast period must be less than slow period")

        fast_ema = self.indicators.ema(fast, price)
        slow_ema = self.indicators.ema(slow, price)

        fast_values = fast_ema.dropna().tail(2)
        slow_values = slow_ema.dropna().tail(2)

        if len(fast_values) < 2 or len(slow_values) < 2:
            self._log.warning("Insufficient EMA data for crossover check")
            return False

        prev_fast = fast_values.iloc[-2]
        curr_fast = fast_values.iloc[-1]
        prev_slow = slow_values.iloc[-2]
        curr_slow = slow_values.iloc[-1]

        return bool(prev_fast >= prev_slow and curr_fast < curr_slow)

