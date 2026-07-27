"""
Signal generation for trading strategies.

Provides a clean interface for generating trading signals from technical
indicators. Supports simple conditions, composite signals, and custom logic.

Usage
-----
    from polyalpha.analysis import SignalGenerator

    signals = SignalGenerator(indicators)
    if signals.rsi_above(40) and signals.price_above_sma(20):
        print("BUY signal")
"""

from __future__ import annotations

import logging
from typing import Any, Callable

from .indicators import IndicatorCalculator

log = logging.getLogger(__name__)


# ── Signal Generator ───────────────────────────────────────────────────────

class SignalGenerator:
    """
    Generate trading signals from technical indicators.

    Parameters
    ----------
    indicators : IndicatorCalculator
        Indicator calculator with calculated indicators.

    Example
    -------
    >>> signals = SignalGenerator(indicators)
    >>> if signals.rsi_above(40):
    ...     print("RSI signal triggered")
    """

    def __init__(self, indicators: IndicatorCalculator):
        """Initialize signal generator."""
        self.indicators = indicators
        self._data = indicators.data
        self._log = logging.getLogger(__name__)

    # ── Simple Signals ───────────────────────────────────────────────────────

    def rsi_above(self, threshold: float, period: int = 14) -> bool:
        """
        Check if RSI is above threshold.

        Parameters
        ----------
        threshold : float
            RSI threshold (0-100).
        period : int
            RSI period (default: 14).

        Returns
        -------
        bool
            True if RSI > threshold.
        """
        if not (0 <= threshold <= 100):
            raise ValueError("RSI threshold must be between 0 and 100")

        rsi = self.indicators.rsi(period)
        latest = self.indicators.get_latest_value(rsi)

        if latest is None:
            self._log.warning("RSI data unavailable")
            return False

        return bool(latest > threshold)

    def rsi_below(self, threshold: float, period: int = 14) -> bool:
        """
        Check if RSI is below threshold.

        Parameters
        ----------
        threshold : float
            RSI threshold (0-100).
        period : int
            RSI period (default: 14).

        Returns
        -------
        bool
            True if RSI < threshold.
        """
        if not (0 <= threshold <= 100):
            raise ValueError("RSI threshold must be between 0 and 100")

        rsi = self.indicators.rsi(period)
        latest = self.indicators.get_latest_value(rsi)

        if latest is None:
            self._log.warning("RSI data unavailable")
            return False

        return bool(latest < threshold)

    def rsi_between(self, lower: float, upper: float, period: int = 14) -> bool:
        """
        Check if RSI is between two thresholds.

        Parameters
        ----------
        lower : float
            Lower threshold (0-100).
        upper : float
            Upper threshold (0-100).
        period : int
            RSI period (default: 14).

        Returns
        -------
        bool
            True if lower < RSI < upper.
        """
        if not (0 <= lower <= 100 and 0 <= upper <= 100):
            raise ValueError("RSI thresholds must be between 0 and 100")
        if lower >= upper:
            raise ValueError("lower threshold must be less than upper")

        rsi = self.indicators.rsi(period)
        latest = self.indicators.get_latest_value(rsi)

        if latest is None:
            self._log.warning("RSI data unavailable")
            return False

        return bool(lower < latest < upper)

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

    def stochastic_above(
        self,
        threshold: float,
        k_period: int = 14,
        d_period: int = 3,
        line: str = "k"
    ) -> bool:
        """
        Check if Stochastic line is above threshold.

        Parameters
        ----------
        threshold : float
            Threshold (0-100).
        k_period : int
            %K period (default: 14).
        d_period : int
            %D period (default: 3).
        line : str
            Line to check: "k" or "d" (default: "k").

        Returns
        -------
        bool
            True if line > threshold.
        """
        if not (0 <= threshold <= 100):
            raise ValueError("Stochastic threshold must be between 0 and 100")
        if line not in ["k", "d"]:
            raise ValueError("line must be 'k' or 'd'")

        stoch = self.indicators.stochastic(k_period, d_period)
        latest = self.indicators.get_latest_value(stoch[line])

        if latest is None:
            self._log.warning("Stochastic data unavailable")
            return False

        return bool(latest > threshold)

    def stochastic_below(
        self,
        threshold: float,
        k_period: int = 14,
        d_period: int = 3,
        line: str = "k"
    ) -> bool:
        """
        Check if Stochastic line is below threshold.

        Parameters
        ----------
        threshold : float
            Threshold (0-100).
        k_period : int
            %K period (default: 14).
        d_period : int
            %D period (default: 3).
        line : str
            Line to check: "k" or "d" (default: "k").

        Returns
        -------
        bool
            True if line < threshold.
        """
        if not (0 <= threshold <= 100):
            raise ValueError("Stochastic threshold must be between 0 and 100")
        if line not in ["k", "d"]:
            raise ValueError("line must be 'k' or 'd'")

        stoch = self.indicators.stochastic(k_period, d_period)
        latest = self.indicators.get_latest_value(stoch[line])

        if latest is None:
            self._log.warning("Stochastic data unavailable")
            return False

        return bool(latest < threshold)

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

    # ── SuperTrend Signals ──────────────────────────────────────────────────────

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

    # ── PSAR Signals ──────────────────────────────────────────────────────────

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

    # ── Ichimoku Signals ─────────────────────────────────────────────────────

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

    # ── Price Change Signals ───────────────────────────────────────────────────

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

    # ── Custom Signals ───────────────────────────────────────────────────────

    def custom(self, condition: Callable[[IndicatorCalculator], bool]) -> bool:
        """
        Evaluate custom condition function.

        Parameters
        ----------
        condition : Callable
            Function that takes IndicatorCalculator and returns bool.

        Returns
        -------
        bool
            Result of custom condition.

        Example
        -------
        >>> def my_strategy(indicators):
        ...     rsi = indicators.rsi(14)
        ...     sma = indicators.sma(20)
        ...     latest_rsi = indicators.get_latest_value(rsi)
        ...     latest_sma = indicators.get_latest_value(sma)
        ...     price = indicators.data["close"].iloc[-1]
        ...     return latest_rsi > 40 and price > latest_sma
        >>>
        >>> signals.custom(my_strategy)
        """
        try:
            return condition(self.indicators)
        except Exception as exc:
            self._log.error("Custom condition error: %s", exc)
            return False

    # ── Composite Signals ───────────────────────────────────────────────────

    def evaluate(self, rules: list[dict[str, Any]]) -> dict[str, Any]:
        """
        Evaluate multiple signal rules.

        Parameters
        ----------
        rules : list[dict[str, Any]]
            List of rule dictionaries. Each rule has:
            - "condition": str or Callable
            - "params": dict (optional)
            - "operator": "AND" | "OR" (optional, for chaining)

        Returns
        -------
        dict[str, Any]
            Dictionary with evaluation results.

        Example
        -------
        >>> rules = [
        ...     {"condition": "rsi_above", "params": {"threshold": 40}},
        ...     {"condition": "price_above_sma", "params": {"period": 20}},
        ...     {"operator": "AND"},
        ... ]
        >>> result = signals.evaluate(rules)
        """
        results: dict[str, Any] = {
            "signals": [],
            "result": True,
            "details": [],
        }

        current_result = True
        current_operator = "AND"

        for rule in rules:
            # Check for operator
            if "operator" in rule:
                current_operator = rule["operator"].upper()
                continue

            # Get condition
            condition = rule["condition"]
            params = rule.get("params", {})

            # Evaluate condition
            if isinstance(condition, str):
                # Built-in condition
                if hasattr(self, condition):
                    method = getattr(self, condition)
                    try:
                        result = method(**params)
                    except Exception as exc:
                        self._log.error("Error evaluating %s: %s", condition, exc)
                        result = False
                else:
                    self._log.error("Unknown condition: %s", condition)
                    result = False
            elif callable(condition):
                # Custom condition
                result = self.custom(condition)
            else:
                self._log.error("Invalid condition type: %s", type(condition))
                result = False

            # Store result
            results["signals"].append(result)
            results["details"].append({
                "condition": str(condition),
                "params": params,
                "result": result,
            })

            # Apply operator
            if current_operator == "AND":
                current_result = current_result and result
            elif current_operator == "OR":
                current_result = current_result or result

        results["result"] = current_result
        return results

    # ── Signal Summary ─────────────────────────────────────────────────────

    def summary(self) -> dict[str, Any]:
        """
        Generate a summary of current signal states.

        Returns
        -------
        dict[str, Any]
            Dictionary with common signal states.
        """
        summary: dict[str, Any] = {
            "rsi": self.indicators.get_latest_value(self.indicators.rsi(14)),
            "rsi_status": self._get_rsi_status(),
            "price_vs_sma20": self.price_above_sma(20),
            "price_vs_ema20": self.price_above_ema(20),
            "macd_histogram": self.indicators.get_latest_value(
                self.indicators.macd()["histogram"]
            ),
            "macd_status": "bullish" if self.macd_above_zero() else "bearish",
            "bb_position": self._get_bb_position(),
            "volume_vs_sma": self.volume_above_sma(20),
        }

        return summary

    def _get_rsi_status(self) -> str:
        """Get RSI status description."""
        rsi = self.indicators.get_latest_value(self.indicators.rsi(14))
        if rsi is None:
            return "unknown"

        if rsi > 70:
            return "overbought"
        elif rsi < 30:
            return "oversold"
        elif rsi > 50:
            return "bullish"
        else:
            return "bearish"

    def _get_bb_position(self) -> str:
        """Get Bollinger Band position description."""
        if self.price_above_bb_upper():
            return "above_upper"
        elif self.price_below_bb_lower():
            return "below_lower"
        else:
            return "inside"
