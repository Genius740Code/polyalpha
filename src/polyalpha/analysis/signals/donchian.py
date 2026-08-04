"""Donchian Channel signal mixin for :class:`SignalGenerator`."""

from __future__ import annotations

from .base import SignalGeneratorBase


class DonchianSignalsMixin(SignalGeneratorBase):
    """Signal mixin. Inherits shared indicator state from SignalGeneratorBase."""
    def price_above_dc_upper(self, length: int = 20, price: str = "close") -> bool:
        """Check if price is above upper Donchian Channel.

        Parameters
        ----------
        length : int
            Donchian period (default: 20).
        price : str
            Price column to use (default: "close").

        Returns
        -------
        bool
            True if price > upper DC.
        """
        dc = self.indicators.donchian(length)
        latest_upper = self.indicators.get_latest_value(dc["upper"])
        latest_price = self._data[price].iloc[-1]
        if latest_upper is None:
            self._log.warning("Donchian data unavailable")
            return False
        return bool(latest_price > latest_upper)


    def price_below_dc_lower(self, length: int = 20, price: str = "close") -> bool:
        """Check if price is below lower Donchian Channel.

        Parameters
        ----------
        length : int
            Donchian period (default: 20).
        price : str
            Price column to use (default: "close").

        Returns
        -------
        bool
            True if price < lower DC.
        """
        dc = self.indicators.donchian(length)
        latest_lower = self.indicators.get_latest_value(dc["lower"])
        latest_price = self._data[price].iloc[-1]
        if latest_lower is None:
            self._log.warning("Donchian data unavailable")
            return False
        return bool(latest_price < latest_lower)


    def price_inside_dc(self, length: int = 20, price: str = "close") -> bool:
        """Check if price is inside Donchian Channels.

        Parameters
        ----------
        length : int
            Donchian period (default: 20).
        price : str
            Price column to use (default: "close").

        Returns
        -------
        bool
            True if lower DC < price < upper DC.
        """
        dc = self.indicators.donchian(length)
        latest_upper = self.indicators.get_latest_value(dc["upper"])
        latest_lower = self.indicators.get_latest_value(dc["lower"])
        latest_price = self._data[price].iloc[-1]
        if latest_upper is None or latest_lower is None:
            self._log.warning("Donchian data unavailable")
            return False
        return bool(latest_lower < latest_price < latest_upper)


    def dc_breakout_above(self, length: int = 20, price: str = "close") -> bool:
        """Check for a bullish Donchian breakout (price crossed above upper).

        Parameters
        ----------
        length : int
            Donchian period (default: 20).
        price : str
            Price column to use (default: "close").

        Returns
        -------
        bool
            True on bullish breakout.
        """
        dc = self.indicators.donchian(length)
        upper = dc["upper"]
        prev_price = self._data[price].iloc[-2] if len(self._data[price]) >= 2 else None
        curr_price = self._data[price].iloc[-1]
        prev_upper = upper.iloc[-2] if len(upper) >= 2 else None
        curr_upper = upper.iloc[-1]
        if prev_price is None or prev_upper is None:
            return False
        return bool(prev_price <= prev_upper and curr_price > curr_upper)


    def dc_breakout_below(self, length: int = 20, price: str = "close") -> bool:
        """Check for a bearish Donchian breakout (price crossed below lower).

        Parameters
        ----------
        length : int
            Donchian period (default: 20).
        price : str
            Price column to use (default: "close").

        Returns
        -------
        bool
            True on bearish breakout.
        """
        dc = self.indicators.donchian(length)
        lower = dc["lower"]
        prev_price = self._data[price].iloc[-2] if len(self._data[price]) >= 2 else None
        curr_price = self._data[price].iloc[-1]
        prev_lower = lower.iloc[-2] if len(lower) >= 2 else None
        curr_lower = lower.iloc[-1]
        if prev_price is None or prev_lower is None:
            return False
        return bool(prev_price >= prev_lower and curr_price < curr_lower)

