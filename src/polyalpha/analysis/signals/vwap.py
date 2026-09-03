"""VWAP signal mixin for :class:`SignalGenerator`."""

from __future__ import annotations

from typing import Optional

import numpy as np
from .base import SignalGeneratorBase


class VWAPSignalsMixin(SignalGeneratorBase):
    """Signal mixin. Inherits shared indicator state from SignalGeneratorBase."""

    def price_above_vwap(self) -> bool:
        """
        Check if current price is above VWAP.

        Returns
        -------
        bool
            True if close price > VWAP.
        """
        vwap = self.indicators.vwap()
        latest_vwap = self.indicators.get_latest_value(vwap)
        latest_price = self._data["close"].iloc[-1]

        if latest_vwap is None:
            self._log.warning("VWAP data unavailable")
            return False

        return bool(latest_price > latest_vwap)

    def price_below_vwap(self) -> bool:
        """
        Check if current price is below VWAP.

        Returns
        -------
        bool
            True if close price < VWAP.
        """
        vwap = self.indicators.vwap()
        latest_vwap = self.indicators.get_latest_value(vwap)
        latest_price = self._data["close"].iloc[-1]

        if latest_vwap is None:
            self._log.warning("VWAP data unavailable")
            return False

        return bool(latest_price < latest_vwap)

    def vwap_rising(self, periods: int = 5) -> bool:
        """
        Check if VWAP is rising over specified periods.

        Parameters
        ----------
        periods : int
            Number of periods to check (default: 5).

        Returns
        -------
        bool
            True if current VWAP > VWAP N periods ago.
        """
        if periods <= 0:
            raise ValueError("periods must be positive")

        vwap = self.indicators.vwap()
        if len(vwap) < periods + 1:
            self._log.warning(f"Insufficient VWAP data for {periods} periods")
            return False

        latest_vwap = vwap.iloc[-1]
        previous_vwap = vwap.iloc[-periods - 1]

        if latest_vwap is None or previous_vwap is None:
            self._log.warning("VWAP data unavailable")
            return False

        return bool(latest_vwap > previous_vwap)

    def vwap_falling(self, periods: int = 5) -> bool:
        """
        Check if VWAP is falling over specified periods.

        Parameters
        ----------
        periods : int
            Number of periods to check (default: 5).

        Returns
        -------
        bool
            True if current VWAP < VWAP N periods ago.
        """
        if periods <= 0:
            raise ValueError("periods must be positive")

        vwap = self.indicators.vwap()
        if len(vwap) < periods + 1:
            self._log.warning(f"Insufficient VWAP data for {periods} periods")
            return False

        latest_vwap = vwap.iloc[-1]
        previous_vwap = vwap.iloc[-periods - 1]

        if latest_vwap is None or previous_vwap is None:
            self._log.warning("VWAP data unavailable")
            return False

        return bool(latest_vwap < previous_vwap)

    def price_above_vwap_band(self, std_dev: float = 1.0) -> bool:
        """
        Check if price is above VWAP upper band (VWAP + std_dev * std).

        Parameters
        ----------
        std_dev : float
            Number of standard deviations for band (default: 1.0).

        Returns
        -------
        bool
            True if close price > VWAP upper band.
        """
        if std_dev <= 0:
            raise ValueError("std_dev must be positive")

        vwap = self.indicators.vwap()
        typical_price = (self._data["high"] + self._data["low"] + self._data["close"]) / 3
        
        # Calculate rolling standard deviation of typical price
        rolling_std = typical_price.rolling(window=20).std()
        
        latest_vwap = self.indicators.get_latest_value(vwap)
        latest_std = rolling_std.iloc[-1]
        latest_price = self._data["close"].iloc[-1]

        if latest_vwap is None or latest_std is None:
            self._log.warning("VWAP or standard deviation data unavailable")
            return False

        upper_band = latest_vwap + (std_dev * latest_std)
        return bool(latest_price > upper_band)

    def price_below_vwap_band(self, std_dev: float = 1.0) -> bool:
        """
        Check if price is below VWAP lower band (VWAP - std_dev * std).

        Parameters
        ----------
        std_dev : float
            Number of standard deviations for band (default: 1.0).

        Returns
        -------
        bool
            True if close price < VWAP lower band.
        """
        if std_dev <= 0:
            raise ValueError("std_dev must be positive")

        vwap = self.indicators.vwap()
        typical_price = (self._data["high"] + self._data["low"] + self._data["close"]) / 3
        
        # Calculate rolling standard deviation of typical price
        rolling_std = typical_price.rolling(window=20).std()
        
        latest_vwap = self.indicators.get_latest_value(vwap)
        latest_std = rolling_std.iloc[-1]
        latest_price = self._data["close"].iloc[-1]

        if latest_vwap is None or latest_std is None:
            self._log.warning("VWAP or standard deviation data unavailable")
            return False

        lower_band = latest_vwap - (std_dev * latest_std)
        return bool(latest_price < lower_band)

    def price_within_vwap_bands(self, std_dev: float = 1.0) -> bool:
        """
        Check if price is within VWAP bands.

        Parameters
        ----------
        std_dev : float
            Number of standard deviations for bands (default: 1.0).

        Returns
        -------
        bool
            True if close price is between VWAP lower and upper bands.
        """
        if std_dev <= 0:
            raise ValueError("std_dev must be positive")

        vwap = self.indicators.vwap()
        typical_price = (self._data["high"] + self._data["low"] + self._data["close"]) / 3
        
        # Calculate rolling standard deviation of typical price
        rolling_std = typical_price.rolling(window=20).std()
        
        latest_vwap = self.indicators.get_latest_value(vwap)
        latest_std = rolling_std.iloc[-1]
        latest_price = self._data["close"].iloc[-1]

        if latest_vwap is None or latest_std is None:
            self._log.warning("VWAP or standard deviation data unavailable")
            return False

        upper_band = latest_vwap + (std_dev * latest_std)
        lower_band = latest_vwap - (std_dev * latest_std)
        return bool(lower_band <= latest_price <= upper_band)

    def vwap_distance_pct(self) -> Optional[float]:
        """
        Calculate percentage distance of price from VWAP.

        Returns
        -------
        float | None
            Percentage distance from VWAP (positive if above, negative if below).
            Returns None if data unavailable.
        """
        vwap = self.indicators.vwap()
        latest_vwap = self.indicators.get_latest_value(vwap)
        latest_price = self._data["close"].iloc[-1]

        if latest_vwap is None or latest_vwap == 0:
            self._log.warning("VWAP data unavailable or zero")
            return None

        return float(((latest_price - latest_vwap) / latest_vwap) * 100)
