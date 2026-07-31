"""Bollinger Bands signal mixin for :class:`SignalGenerator`."""

from __future__ import annotations

from .base import SignalGeneratorBase


class BollingerSignalsMixin(SignalGeneratorBase):
    """Signal mixin. Inherits shared indicator state from SignalGeneratorBase."""
    def price_above_bb_upper(
        self,
        period: int = 20,
        std_dev: float = 2.0,
        price: str = "close"
    ) -> bool:
        """
        Check if price is above upper Bollinger Band.

        Parameters
        ----------
        period : int
            BB period (default: 20).
        std_dev : float
            Standard deviation multiplier (default: 2.0).
        price : str
            Price column to use (default: "close").

        Returns
        -------
        bool
            True if price > upper BB.
        """
        bb = self.indicators.bollinger_bands(period, std_dev, price)
        latest_upper = self.indicators.get_latest_value(bb["upper"])
        latest_price = self._data[price].iloc[-1]

        if latest_upper is None:
            self._log.warning("Bollinger Bands data unavailable")
            return False

        return bool(latest_price > latest_upper)


    def price_below_bb_lower(
        self,
        period: int = 20,
        std_dev: float = 2.0,
        price: str = "close"
    ) -> bool:
        """
        Check if price is below lower Bollinger Band.

        Parameters
        ----------
        period : int
            BB period (default: 20).
        std_dev : float
            Standard deviation multiplier (default: 2.0).
        price : str
            Price column to use (default: "close").

        Returns
        -------
        bool
            True if price < lower BB.
        """
        bb = self.indicators.bollinger_bands(period, std_dev, price)
        latest_lower = self.indicators.get_latest_value(bb["lower"])
        latest_price = self._data[price].iloc[-1]

        if latest_lower is None:
            self._log.warning("Bollinger Bands data unavailable")
            return False

        return bool(latest_price < latest_lower)


    def price_inside_bb(
        self,
        period: int = 20,
        std_dev: float = 2.0,
        price: str = "close"
    ) -> bool:
        """
        Check if price is inside Bollinger Bands.

        Parameters
        ----------
        period : int
            BB period (default: 20).
        std_dev : float
            Standard deviation multiplier (default: 2.0).
        price : str
            Price column to use (default: "close").

        Returns
        -------
        bool
            True if lower BB < price < upper BB.
        """
        bb = self.indicators.bollinger_bands(period, std_dev, price)
        latest_upper = self.indicators.get_latest_value(bb["upper"])
        latest_lower = self.indicators.get_latest_value(bb["lower"])
        latest_price = self._data[price].iloc[-1]

        if latest_upper is None or latest_lower is None:
            self._log.warning("Bollinger Bands data unavailable")
            return False

        return bool(latest_lower < latest_price < latest_upper)


    def bb_width(self, period: int = 20, std_dev: float = 2.0, price: str = "close") -> float | None:
        """Current Bollinger Band width (upper - lower).

        Parameters
        ----------
        period : int
            BB period (default: 20).
        std_dev : float
            Standard deviation multiplier (default: 2.0).
        price : str
            Price column to use (default: "close").

        Returns
        -------
        float or None
            BB width value.
        """
        bb = self.indicators.bollinger_bands(period, std_dev, price)
        upper = self.indicators.get_latest_value(bb["upper"])
        lower = self.indicators.get_latest_value(bb["lower"])
        if upper is None or lower is None:
            return None
        return upper - lower


    def bb_width_pct(self, period: int = 20, std_dev: float = 2.0, avg_period: int = 50, price: str = "close") -> float | None:
        """BB width as a percentage of its rolling average.

        Values below 1.0 (100%) indicate width is contracting vs. the
        historical average — a squeeze. Values significantly above 1.0
        indicate expansion.

        Parameters
        ----------
        period : int
            BB period (default: 20).
        std_dev : float
            Standard deviation multiplier (default: 2.0).
        avg_period : int
            Rolling average period for width comparison (default: 50).
        price : str
            Price column to use (default: "close").

        Returns
        -------
        float or None
            Width / avg_width ratio.
        """
        bb = self.indicators.bollinger_bands(period, std_dev, price)
        width = bb["upper"] - bb["lower"]
        avg_width = width.rolling(window=avg_period).mean()
        latest_width = self.indicators.get_latest_value(width)
        latest_avg = self.indicators.get_latest_value(avg_width)
        if latest_width is None or latest_avg is None or latest_avg == 0:
            return None
        return latest_width / latest_avg


    def bb_squeeze(self, period: int = 20, std_dev: float = 2.0, avg_period: int = 50, threshold: float = 1.0, price: str = "close") -> bool:
        """Check if Bollinger Bands are squeezing (width below threshold % of avg).

        Parameters
        ----------
        period : int
            BB period (default: 20).
        std_dev : float
            Standard deviation multiplier (default: 2.0).
        avg_period : int
            Rolling average period for width comparison (default: 50).
        threshold : float
            Width ratio threshold. Lower = tighter squeeze (default: 1.0).
        price : str
            Price column to use (default: "close").

        Returns
        -------
        bool
            True if BB width < threshold * avg width.
        """
        pct = self.bb_width_pct(period, std_dev, avg_period, price)
        if pct is None:
            return False
        return bool(pct < threshold)


    def _get_bb_position(self) -> str:
        """Get Bollinger Band position description."""
        if self.price_above_bb_upper():
            return "above_upper"
        elif self.price_below_bb_lower():
            return "below_lower"
        else:
            return "inside"

