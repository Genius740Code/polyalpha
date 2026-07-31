"""Parabolic SAR signal mixin for :class:`SignalGenerator`."""

from __future__ import annotations

from .base import SignalGeneratorBase


class PSARSignalsMixin(SignalGeneratorBase):
    """Signal mixin. Inherits shared indicator state from SignalGeneratorBase."""
    def psar_uptrend(self, af: float = 0.02, af_max: float = 0.2) -> bool:
        """Check if PSAR indicates uptrend (price above SAR, trend == 1).

        Parameters
        ----------
        af : float
            Acceleration factor (default: 0.02).
        af_max : float
            Maximum acceleration factor (default: 0.2).

        Returns
        -------
        bool
            True if in uptrend.
        """
        psar = self.indicators.psar(af, af_max)
        trend = self.indicators.get_latest_value(psar["trend"])
        if trend is None:
            self._log.warning("PSAR data unavailable")
            return False
        return bool(trend == 1)


    def psar_downtrend(self, af: float = 0.02, af_max: float = 0.2) -> bool:
        """Check if PSAR indicates downtrend (price below SAR, trend == -1).

        Parameters
        ----------
        af : float
            Acceleration factor (default: 0.02).
        af_max : float
            Maximum acceleration factor (default: 0.2).

        Returns
        -------
        bool
            True if in downtrend.
        """
        psar = self.indicators.psar(af, af_max)
        trend = self.indicators.get_latest_value(psar["trend"])
        if trend is None:
            self._log.warning("PSAR data unavailable")
            return False
        return bool(trend == -1)


    def psar_turned_up(self, af: float = 0.02, af_max: float = 0.2) -> bool:
        """Check if PSAR just flipped from downtrend to uptrend.

        Parameters
        ----------
        af : float
            Acceleration factor (default: 0.02).
        af_max : float
            Maximum acceleration factor (default: 0.2).

        Returns
        -------
        bool
            True if just turned up.
        """
        psar = self.indicators.psar(af, af_max)
        trend = psar["trend"].dropna()
        if len(trend) < 2:
            self._log.warning("Insufficient PSAR data")
            return False
        return bool(trend.iloc[-2] == -1 and trend.iloc[-1] == 1)


    def psar_turned_down(self, af: float = 0.02, af_max: float = 0.2) -> bool:
        """Check if PSAR just flipped from uptrend to downtrend.

        Parameters
        ----------
        af : float
            Acceleration factor (default: 0.02).
        af_max : float
            Maximum acceleration factor (default: 0.2).

        Returns
        -------
        bool
            True if just turned down.
        """
        psar = self.indicators.psar(af, af_max)
        trend = psar["trend"].dropna()
        if len(trend) < 2:
            self._log.warning("Insufficient PSAR data")
            return False
        return bool(trend.iloc[-2] == 1 and trend.iloc[-1] == -1)


    def price_above_psar(self, af: float = 0.02, af_max: float = 0.2, price: str = "close") -> bool:
        """Check if price is above PSAR value.

        Parameters
        ----------
        af : float
            Acceleration factor (default: 0.02).
        af_max : float
            Maximum acceleration factor (default: 0.2).
        price : str
            Price column to use (default: "close").

        Returns
        -------
        bool
            True if price > PSAR.
        """
        psar = self.indicators.psar(af, af_max)
        latest_psar = self.indicators.get_latest_value(psar["value"])
        latest_price = self._data[price].iloc[-1]
        if latest_psar is None:
            self._log.warning("PSAR data unavailable")
            return False
        return bool(latest_price > latest_psar)


    def price_below_psar(self, af: float = 0.02, af_max: float = 0.2, price: str = "close") -> bool:
        """Check if price is below PSAR value.

        Parameters
        ----------
        af : float
            Acceleration factor (default: 0.02).
        af_max : float
            Maximum acceleration factor (default: 0.2).
        price : str
            Price column to use (default: "close").

        Returns
        -------
        bool
            True if price < PSAR.
        """
        psar = self.indicators.psar(af, af_max)
        latest_psar = self.indicators.get_latest_value(psar["value"])
        latest_price = self._data[price].iloc[-1]
        if latest_psar is None:
            self._log.warning("PSAR data unavailable")
            return False
        return bool(latest_price < latest_psar)

