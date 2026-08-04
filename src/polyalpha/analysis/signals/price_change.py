"""Price change signal mixin for :class:`SignalGenerator`."""

from __future__ import annotations

from .base import SignalGeneratorBase


class PriceChangeSignalsMixin(SignalGeneratorBase):
    """Signal mixin. Inherits shared indicator state from SignalGeneratorBase."""
    def price_change_above(self, min_change: float, candles_back: int = 1, price: str = "close") -> bool:
        """
        Check if price changed by at least a minimum amount from N candles ago.

        Parameters
        ----------
        min_change : float
            Minimum price change required (absolute value).
        candles_back : int
            Number of candles to look back (default: 1 = previous candle).
        price : str
            Price column to use (default: "close").

        Returns
        -------
        bool
            True if |current_price - price_N_candles_ago| >= min_change.
        """
        if candles_back < 1:
            raise ValueError("candles_back must be at least 1")
        if min_change < 0:
            raise ValueError("min_change must be non-negative")

        if len(self._data) <= candles_back:
            self._log.warning("Insufficient data for price change check")
            return False

        current_price = self._data[price].iloc[-1]
        past_price = self._data[price].iloc[-(candles_back + 1)]
        price_change = abs(current_price - past_price)

        return bool(price_change >= min_change)


    def price_change_below(self, max_change: float, candles_back: int = 1, price: str = "close") -> bool:
        """
        Check if price changed by less than a maximum amount from N candles ago.

        Parameters
        ----------
        max_change : float
            Maximum price change allowed (absolute value).
        candles_back : int
            Number of candles to look back (default: 1 = previous candle).
        price : str
            Price column to use (default: "close").

        Returns
        -------
        bool
            True if |current_price - price_N_candles_ago| <= max_change.
        """
        if candles_back < 1:
            raise ValueError("candles_back must be at least 1")
        if max_change < 0:
            raise ValueError("max_change must be non-negative")

        if len(self._data) <= candles_back:
            self._log.warning("Insufficient data for price change check")
            return False

        current_price = self._data[price].iloc[-1]
        past_price = self._data[price].iloc[-(candles_back + 1)]
        price_change = abs(current_price - past_price)

        return bool(price_change <= max_change)


    def price_above_by(self, min_change: float, candles_back: int = 1, price: str = "close") -> bool:
        """
        Check if current price is above price N candles ago by at least minimum amount.

        Parameters
        ----------
        min_change : float
            Minimum upward change required.
        candles_back : int
            Number of candles to look back (default: 1 = previous candle).
        price : str
            Price column to use (default: "close").

        Returns
        -------
        bool
            True if current_price - price_N_candles_ago >= min_change.
        """
        if min_change < 0:
            raise ValueError("min_change must be non-negative")
        if candles_back < 1:
            raise ValueError("candles_back must be at least 1")

        if len(self._data) <= candles_back:
            self._log.warning("Insufficient data for price change check")
            return False

        current_price = self._data[price].iloc[-1]
        past_price = self._data[price].iloc[-(candles_back + 1)]
        price_change = current_price - past_price

        return bool(price_change >= min_change)


    def price_below_by(self, min_change: float, candles_back: int = 1, price: str = "close") -> bool:
        """
        Check if current price is below price N candles ago by at least minimum amount.

        Parameters
        ----------
        min_change : float
            Minimum downward change required.
        candles_back : int
            Number of candles to look back (default: 1 = previous candle).
        price : str
            Price column to use (default: "close").

        Returns
        -------
        bool
            True if price_N_candles_ago - current_price >= min_change.
        """
        if min_change < 0:
            raise ValueError("min_change must be non-negative")
        if candles_back < 1:
            raise ValueError("candles_back must be at least 1")

        if len(self._data) <= candles_back:
            self._log.warning("Insufficient data for price change check")
            return False

        current_price = self._data[price].iloc[-1]
        past_price = self._data[price].iloc[-(candles_back + 1)]
        price_change = past_price - current_price

        return bool(price_change >= min_change)


    def price_change_percent_above(self, min_percent: float, candles_back: int = 1, price: str = "close") -> bool:
        """
        Check if price changed by at least a minimum percentage from N candles ago.

        Parameters
        ----------
        min_percent : float
            Minimum percentage change required (e.g., 0.5 for 0.5%).
        candles_back : int
            Number of candles to look back (default: 1 = previous candle).
        price : str
            Price column to use (default: "close").

        Returns
        -------
        bool
            True if |percent_change| >= min_percent.
        """
        if candles_back < 1:
            raise ValueError("candles_back must be at least 1")
        if min_percent < 0:
            raise ValueError("min_percent must be non-negative")

        if len(self._data) <= candles_back:
            self._log.warning("Insufficient data for price change check")
            return False

        current_price = self._data[price].iloc[-1]
        past_price = self._data[price].iloc[-(candles_back + 1)]

        if past_price == 0:
            self._log.warning("Past price is zero, cannot calculate percentage")
            return False

        percent_change = abs((current_price - past_price) / past_price * 100)

        return bool(percent_change >= min_percent)


    def price_change_percent_below(self, max_percent: float, candles_back: int = 1, price: str = "close") -> bool:
        """
        Check if price changed by less than a maximum percentage from N candles ago.

        Parameters
        ----------
        max_percent : float
            Maximum percentage change allowed (e.g., 0.5 for 0.5%).
        candles_back : int
            Number of candles to look back (default: 1 = previous candle).
        price : str
            Price column to use (default: "close").

        Returns
        -------
        bool
            True if |percent_change| <= max_percent.
        """
        if candles_back < 1:
            raise ValueError("candles_back must be at least 1")
        if max_percent < 0:
            raise ValueError("max_percent must be non-negative")

        if len(self._data) <= candles_back:
            self._log.warning("Insufficient data for price change check")
            return False

        current_price = self._data[price].iloc[-1]
        past_price = self._data[price].iloc[-(candles_back + 1)]

        if past_price == 0:
            self._log.warning("Past price is zero, cannot calculate percentage")
            return False

        percent_change = abs((current_price - past_price) / past_price * 100)

        return bool(percent_change <= max_percent)


    def price_up(self, candles_back: int = 1, price: str = "close") -> bool:
        """
        Check if price is up compared to N candles ago.

        Parameters
        ----------
        candles_back : int
            Number of candles to look back (default: 1 = previous candle).
        price : str
            Price column to use (default: "close").

        Returns
        -------
        bool
            True if current_price > price_N_candles_ago.
        """
        if candles_back < 1:
            raise ValueError("candles_back must be at least 1")

        if len(self._data) <= candles_back:
            self._log.warning("Insufficient data for price direction check")
            return False

        current_price = self._data[price].iloc[-1]
        past_price = self._data[price].iloc[-(candles_back + 1)]

        return bool(current_price > past_price)


    def price_down(self, candles_back: int = 1, price: str = "close") -> bool:
        """
        Check if price is down compared to N candles ago.

        Parameters
        ----------
        candles_back : int
            Number of candles to look back (default: 1 = previous candle).
        price : str
            Price column to use (default: "close").

        Returns
        -------
        bool
            True if current_price < price_N_candles_ago.
        """
        if candles_back < 1:
            raise ValueError("candles_back must be at least 1")

        if len(self._data) <= candles_back:
            self._log.warning("Insufficient data for price direction check")
            return False

        current_price = self._data[price].iloc[-1]
        past_price = self._data[price].iloc[-(candles_back + 1)]

        return bool(current_price < past_price)


    def price_up_by_percent(self, min_percent: float, candles_back: int = 1, price: str = "close") -> bool:
        """
        Check if price is up by at least a minimum percentage from N candles ago.

        Parameters
        ----------
        min_percent : float
            Minimum upward percentage change required (e.g., 0.5 for 0.5%).
        candles_back : int
            Number of candles to look back (default: 1 = previous candle).
        price : str
            Price column to use (default: "close").

        Returns
        -------
        bool
            True if (current_price - past_price) / past_price * 100 >= min_percent.
        """
        if min_percent < 0:
            raise ValueError("min_percent must be non-negative")
        if candles_back < 1:
            raise ValueError("candles_back must be at least 1")

        if len(self._data) <= candles_back:
            self._log.warning("Insufficient data for price change check")
            return False

        current_price = self._data[price].iloc[-1]
        past_price = self._data[price].iloc[-(candles_back + 1)]

        if past_price == 0:
            self._log.warning("Past price is zero, cannot calculate percentage")
            return False

        percent_change = (current_price - past_price) / past_price * 100

        return bool(percent_change >= min_percent)


    def price_down_by_percent(self, min_percent: float, candles_back: int = 1, price: str = "close") -> bool:
        """
        Check if price is down by at least a minimum percentage from N candles ago.

        Parameters
        ----------
        min_percent : float
            Minimum downward percentage change required (e.g., 0.5 for 0.5%).
        candles_back : int
            Number of candles to look back (default: 1 = previous candle).
        price : str
            Price column to use (default: "close").

        Returns
        -------
        bool
            True if (past_price - current_price) / past_price * 100 >= min_percent.
        """
        if candles_back < 1:
            raise ValueError("candles_back must be at least 1")

        if len(self._data) <= candles_back:
            self._log.warning("Insufficient data for price change check")
            return False

        current_price = self._data[price].iloc[-1]
        past_price = self._data[price].iloc[-(candles_back + 1)]

        if past_price == 0:
            self._log.warning("Past price is zero, cannot calculate percentage")
            return False

        percent_change = (past_price - current_price) / past_price * 100

        return bool(percent_change >= min_percent)

