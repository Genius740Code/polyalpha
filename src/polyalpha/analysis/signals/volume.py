"""Volume signal mixin for :class:`SignalGenerator`."""

from __future__ import annotations

from .base import SignalGeneratorBase


class VolumeSignalsMixin(SignalGeneratorBase):
    """Signal mixin. Inherits shared indicator state from SignalGeneratorBase."""
    def volume_above_sma(self, period: int = 20) -> bool:
        """
        Check if volume is above SMA.

        Parameters
        ----------
        period : int
            SMA period (default: 20).

        Returns
        -------
        bool
            True if volume > volume SMA.
        """
        vol_sma = self.indicators.volume_sma(period)
        latest_sma = self.indicators.get_latest_value(vol_sma)
        latest_volume = self._data["volume"].iloc[-1]

        if latest_sma is None:
            self._log.warning("Volume SMA data unavailable")
            return False

        return bool(latest_volume > latest_sma)


    def volume_below_sma(self, period: int = 20) -> bool:
        """
        Check if volume is below SMA.

        Parameters
        ----------
        period : int
            SMA period (default: 20).

        Returns
        -------
        bool
            True if volume < volume SMA.
        """
        vol_sma = self.indicators.volume_sma(period)
        latest_sma = self.indicators.get_latest_value(vol_sma)
        latest_volume = self._data["volume"].iloc[-1]

        if latest_sma is None:
            self._log.warning("Volume SMA data unavailable")
            return False

        return bool(latest_volume < latest_sma)

