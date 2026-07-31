"""Ichimoku Cloud signal mixin for :class:`SignalGenerator`."""

from __future__ import annotations

from .base import SignalGeneratorBase


class IchimokuSignalsMixin(SignalGeneratorBase):
    """Signal mixin. Inherits shared indicator state from SignalGeneratorBase."""
    def ichimoku_tenkan_above_kijun(self, tenkan: int = 9, kijun: int = 26) -> bool:
        """Check if Tenkan-sen (conversion line) is above Kijun-sen (base line).

        Parameters
        ----------
        tenkan : int
            Tenkan period (default: 9).
        kijun : int
            Kijun period (default: 26).

        Returns
        -------
        bool
            True if Tenkan > Kijun.
        """
        ichi = self.indicators.ichimoku(tenkan, kijun)
        tenkan_val = self.indicators.get_latest_value(ichi["tenkan"])
        kijun_val = self.indicators.get_latest_value(ichi["kijun"])
        if tenkan_val is None or kijun_val is None:
            self._log.warning("Ichimoku data unavailable")
            return False
        return bool(tenkan_val > kijun_val)


    def ichimoku_tenkan_below_kijun(self, tenkan: int = 9, kijun: int = 26) -> bool:
        """Check if Tenkan-sen is below Kijun-sen.

        Parameters
        ----------
        tenkan : int
            Tenkan period (default: 9).
        kijun : int
            Kijun period (default: 26).

        Returns
        -------
        bool
            True if Tenkan < Kijun.
        """
        ichi = self.indicators.ichimoku(tenkan, kijun)
        tenkan_val = self.indicators.get_latest_value(ichi["tenkan"])
        kijun_val = self.indicators.get_latest_value(ichi["kijun"])
        if tenkan_val is None or kijun_val is None:
            self._log.warning("Ichimoku data unavailable")
            return False
        return bool(tenkan_val < kijun_val)


    def ichimoku_tenkan_crossed_above_kijun(self, tenkan: int = 9, kijun: int = 26) -> bool:
        """Check if Tenkan-sen crossed above Kijun-sen (bullish TK cross).

        Parameters
        ----------
        tenkan : int
            Tenkan period (default: 9).
        kijun : int
            Kijun period (default: 26).

        Returns
        -------
        bool
            True on bullish TK cross.
        """
        ichi = self.indicators.ichimoku(tenkan, kijun)
        tenkan_vals = ichi["tenkan"].dropna().tail(2)
        kijun_vals = ichi["kijun"].dropna().tail(2)
        if len(tenkan_vals) < 2 or len(kijun_vals) < 2:
            self._log.warning("Insufficient Ichimoku data for TK cross")
            return False
        return bool(tenkan_vals.iloc[-2] <= kijun_vals.iloc[-2] and tenkan_vals.iloc[-1] > kijun_vals.iloc[-1])


    def ichimoku_tenkan_crossed_below_kijun(self, tenkan: int = 9, kijun: int = 26) -> bool:
        """Check if Tenkan-sen crossed below Kijun-sen (bearish TK cross).

        Parameters
        ----------
        tenkan : int
            Tenkan period (default: 9).
        kijun : int
            Kijun period (default: 26).

        Returns
        -------
        bool
            True on bearish TK cross.
        """
        ichi = self.indicators.ichimoku(tenkan, kijun)
        tenkan_vals = ichi["tenkan"].dropna().tail(2)
        kijun_vals = ichi["kijun"].dropna().tail(2)
        if len(tenkan_vals) < 2 or len(kijun_vals) < 2:
            self._log.warning("Insufficient Ichimoku data for TK cross")
            return False
        return bool(tenkan_vals.iloc[-2] >= kijun_vals.iloc[-2] and tenkan_vals.iloc[-1] < kijun_vals.iloc[-1])


    def ichimoku_price_above_cloud(self, tenkan: int = 9, kijun: int = 26, senkou: int = 52, price: str = "close") -> bool:
        """Check if price is above the Ichimoku cloud (bullish breakout).

        Parameters
        ----------
        tenkan : int
            Tenkan period (default: 9).
        kijun : int
            Kijun period (default: 26).
        senkou : int
            Senkou span B period (default: 52).
        price : str
            Price column to use (default: "close").

        Returns
        -------
        bool
            True if price > cloud top.
        """
        ichi = self.indicators.ichimoku(tenkan, kijun, senkou)
        cloud = ichi.get("cloud")
        if cloud is None:
            self._log.warning("Ichimoku cloud data unavailable")
            return False
        top = self.indicators.get_latest_value(cloud["top"])
        latest_price = self._data[price].iloc[-1]
        if top is None:
            self._log.warning("Ichimoku cloud top unavailable")
            return False
        return bool(latest_price > top)


    def ichimoku_price_below_cloud(self, tenkan: int = 9, kijun: int = 26, senkou: int = 52, price: str = "close") -> bool:
        """Check if price is below the Ichimoku cloud (bearish breakout).

        Parameters
        ----------
        tenkan : int
            Tenkan period (default: 9).
        kijun : int
            Kijun period (default: 26).
        senkou : int
            Senkou span B period (default: 52).
        price : str
            Price column to use (default: "close").

        Returns
        -------
        bool
            True if price < cloud bottom.
        """
        ichi = self.indicators.ichimoku(tenkan, kijun, senkou)
        cloud = ichi.get("cloud")
        if cloud is None:
            self._log.warning("Ichimoku cloud data unavailable")
            return False
        bottom = self.indicators.get_latest_value(cloud["bottom"])
        latest_price = self._data[price].iloc[-1]
        if bottom is None:
            self._log.warning("Ichimoku cloud bottom unavailable")
            return False
        return bool(latest_price < bottom)


    def ichimoku_price_inside_cloud(self, tenkan: int = 9, kijun: int = 26, senkou: int = 52, price: str = "close") -> bool:
        """Check if price is inside the Ichimoku cloud.

        Parameters
        ----------
        tenkan : int
            Tenkan period (default: 9).
        kijun : int
            Kijun period (default: 26).
        senkou : int
            Senkou span B period (default: 52).
        price : str
            Price column to use (default: "close").

        Returns
        -------
        bool
            True if cloud bottom < price < cloud top.
        """
        ichi = self.indicators.ichimoku(tenkan, kijun, senkou)
        cloud = ichi.get("cloud")
        if cloud is None:
            self._log.warning("Ichimoku cloud data unavailable")
            return False
        top = self.indicators.get_latest_value(cloud["top"])
        bottom = self.indicators.get_latest_value(cloud["bottom"])
        latest_price = self._data[price].iloc[-1]
        if top is None or bottom is None:
            self._log.warning("Ichimoku cloud data unavailable")
            return False
        return bool(bottom < latest_price < top)


    def ichimoku_chikou_above_price(self, tenkan: int = 9, kijun: int = 26, price: str = "close") -> bool:
        """Check if Chikou span is above current price (bullish confirmation).

        Parameters
        ----------
        tenkan : int
            Tenkan period (default: 9).
        kijun : int
            Kijun period (default: 26).
        price : str
            Price column to use (default: "close").

        Returns
        -------
        bool
            True if chikou > price.
        """
        ichi = self.indicators.ichimoku(tenkan, kijun)
        chikou = self.indicators.get_latest_value(ichi["chikou"])
        latest_price = self._data[price].iloc[-1]
        if chikou is None:
            self._log.warning("Ichimoku Chikou data unavailable")
            return False
        return bool(chikou > latest_price)


    def ichimoku_chikou_below_price(self, tenkan: int = 9, kijun: int = 26, price: str = "close") -> bool:
        """Check if Chikou span is below current price (bearish confirmation).

        Parameters
        ----------
        tenkan : int
            Tenkan period (default: 9).
        kijun : int
            Kijun period (default: 26).
        price : str
            Price column to use (default: "close").

        Returns
        -------
        bool
            True if chikou < price.
        """
        ichi = self.indicators.ichimoku(tenkan, kijun)
        chikou = self.indicators.get_latest_value(ichi["chikou"])
        latest_price = self._data[price].iloc[-1]
        if chikou is None:
            self._log.warning("Ichimoku Chikou data unavailable")
            return False
        return bool(chikou < latest_price)


    def ichimoku_bullish_breakout(
        self, tenkan: int = 9, kijun: int = 26, senkou: int = 52, price: str = "close"
    ) -> bool:
        """Combined bullish Ichimoku breakout: price above cloud + TK bullish cross.

        Parameters
        ----------
        tenkan : int
            Tenkan period (default: 9).
        kijun : int
            Kijun period (default: 26).
        senkou : int
            Senkou span B period (default: 52).
        price : str
            Price column to use (default: "close").

        Returns
        -------
        bool
            True for bullish breakout.
        """
        return (
            self.ichimoku_price_above_cloud(tenkan, kijun, senkou, price)
            and self.ichimoku_tenkan_above_kijun(tenkan, kijun)
        )


    def ichimoku_bearish_breakout(
        self, tenkan: int = 9, kijun: int = 26, senkou: int = 52, price: str = "close"
    ) -> bool:
        """Combined bearish Ichimoku breakout: price below cloud + TK bearish cross.

        Parameters
        ----------
        tenkan : int
            Tenkan period (default: 9).
        kijun : int
            Kijun period (default: 26).
        senkou : int
            Senkou span B period (default: 52).
        price : str
            Price column to use (default: "close").

        Returns
        -------
        bool
            True for bearish breakout.
        """
        return (
            self.ichimoku_price_below_cloud(tenkan, kijun, senkou, price)
            and self.ichimoku_tenkan_below_kijun(tenkan, kijun)
        )

