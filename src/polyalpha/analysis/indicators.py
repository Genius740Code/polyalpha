"""
Technical indicator calculations using pandas-ta.

Provides a clean interface to pandas-ta indicators including:
        - Trend indicators: SMA, EMA, MACD, ADX, SuperTrend
        - Momentum indicators: RSI, Stochastic, Williams %R, CCI
- Volatility indicators: Bollinger Bands, ATR, Keltner Channels
- Volume indicators: OBV, Volume SMA, Volume ROC
- Additional: VWAP, Fair Value Gap, Pivot Points

Usage
-----
    from polyalpha.analysis import IndicatorCalculator

    indicators = IndicatorCalculator(data)
    rsi = indicators.rsi(period=14)
    bb = indicators.bollinger_bands(period=20, std_dev=2.0)
    macd = indicators.macd(fast=12, slow=26, signal=9)
"""

from __future__ import annotations

import logging
from typing import Optional

import numpy as np
import pandas as pd

log = logging.getLogger(__name__)

# Try to import pandas-ta, fall back to native implementations
try:
    import pandas_ta as ta
    PANDAS_TA_AVAILABLE = True
except ImportError:
    from polyalpha.analysis import _native_ta as ta
    PANDAS_TA_AVAILABLE = False
    log.info("pandas-ta not installed; using native TA implementations")


# ── Indicator Calculator ─────────────────────────────────────────────────────

class IndicatorCalculator:
    """
    Calculate technical indicators using pandas-ta.

    Parameters
    ----------
    data : pd.DataFrame
        OHLCV data with columns: timestamp, open, high, low, close, volume.

    Example
    -------
    >>> indicators = IndicatorCalculator(data)
    >>> rsi = indicators.rsi(14)
    >>> sma = indicators.sma(20)
    """

    def __init__(self, data: pd.DataFrame):
        """Initialize indicator calculator."""
        self.data = data.copy()
        self._validate_data()

        self._log = logging.getLogger(__name__)
        self._cache: dict[str, pd.Series | dict[str, pd.Series]] = {}

    def _get_cache_key(self, indicator: str, **kwargs) -> str:
        """Generate cache key for indicator with parameters."""
        params_str = "_".join(f"{k}_{v}" for k, v in sorted(kwargs.items()))
        return f"{indicator}_{params_str}" if params_str else indicator

    def clear_cache(self) -> None:
        """Clear the indicator cache."""
        self._cache.clear()

    def _validate_data(self) -> None:
        """Validate input data."""
        required_columns = ["open", "high", "low", "close", "volume"]
        missing = [col for col in required_columns if col not in self.data.columns]

        if missing:
            raise ValueError(
                f"Data missing required columns: {missing}. "
                f"Required: {required_columns}"
            )

        if len(self.data) < 20:
            log.warning(
                "Data has fewer than 20 rows. Some indicators may not work correctly."
            )

    # ── Trend Indicators ─────────────────────────────────────────────────────

    def sma(self, period: int = 20, price: str = "close") -> pd.Series:
        """
        Simple Moving Average.

        Parameters
        ----------
        period : int
            SMA period (default: 20).
        price : str
            Price column to use: "open" | "high" | "low" | "close" (default: "close").

        Returns
        -------
        pd.Series
            SMA values.
        """
        if period <= 0:
            raise ValueError("period must be positive")

        cache_key = self._get_cache_key("sma", period=period, price=price)
        if cache_key in self._cache:
            return self._cache[cache_key]

        try:
            result = ta.sma(self.data[price], length=period)
        except Exception as exc:
            self._log.error("pandas-ta SMA calculation failed: %s", exc)
            raise RuntimeError(f"SMA calculation failed: {exc}") from exc

        series = result.rename(f"SMA{period}")
        self._cache[cache_key] = series
        return series

    def ema(self, period: int = 20, price: str = "close") -> pd.Series:
        """
        Exponential Moving Average.

        Parameters
        ----------
        period : int
            EMA period (default: 20).
        price : str
            Price column to use: "open" | "high" | "low" | "close" (default: "close").

        Returns
        -------
        pd.Series
            EMA values.
        """
        if period <= 0:
            raise ValueError("period must be positive")

        cache_key = self._get_cache_key("ema", period=period, price=price)
        if cache_key in self._cache:
            return self._cache[cache_key]

        try:
            result = ta.ema(self.data[price], length=period)
        except Exception as exc:
            self._log.error("pandas-ta EMA calculation failed: %s", exc)
            raise RuntimeError(f"EMA calculation failed: {exc}") from exc

        series = result.rename(f"EMA{period}")
        self._cache[cache_key] = series
        return series

    def macd(
        self,
        fast: int = 12,
        slow: int = 26,
        signal: int = 9,
        price: str = "close"
    ) -> dict[str, pd.Series]:
        """
        Moving Average Convergence Divergence.

        Parameters
        ----------
        fast : int
            Fast period (default: 12).
        slow : int
            Slow period (default: 26).
        signal : int
            Signal period (default: 9).
        price : str
            Price column to use (default: "close").

        Returns
        -------
        dict[str, pd.Series]
            Dictionary with keys: "macd", "signal", "histogram".
        """
        if fast <= 0 or slow <= 0 or signal <= 0:
            raise ValueError("periods must be positive")

        try:
            macd_result = ta.macd(self.data[price], fast=fast, slow=slow, signal=signal)
        except Exception as exc:
            self._log.error("pandas-ta MACD calculation failed: %s", exc)
            raise RuntimeError(f"MACD calculation failed: {exc}") from exc

        return {
            "macd": macd_result[f"MACD_{fast}_{slow}_{signal}"].rename("MACD"),
            "signal": macd_result[f"MACDs_{fast}_{slow}_{signal}"].rename("MACD_Signal"),
            "histogram": macd_result[f"MACDh_{fast}_{slow}_{signal}"].rename("MACD_Hist"),
        }

    def adx(self, period: int = 14) -> dict[str, pd.Series]:
        """
        Average Directional Index.

        Parameters
        ----------
        period : int
            ADX period (default: 14).

        Returns
        -------
        dict[str, pd.Series]
            Dictionary with keys: "adx", "plus_di", "minus_di".
        """
        if period <= 0:
            raise ValueError("period must be positive")

        try:
            adx_result = ta.adx(self.data["high"], self.data["low"], self.data["close"], length=period)
        except Exception as exc:
            self._log.error("pandas-ta ADX calculation failed: %s", exc)
            raise RuntimeError(f"ADX calculation failed: {exc}") from exc

        return {
            "adx": adx_result[f"ADX_{period}"].rename("ADX"),
            "plus_di": adx_result[f"DMP_{period}"].rename("+DI"),
            "minus_di": adx_result[f"DMN_{period}"].rename("-DI"),
        }

    def supertrend(self, period: int = 7, multiplier: float = 3.0) -> dict[str, pd.Series]:
        """
        SuperTrend indicator.

        A trend-following indicator that uses ATR to create trailing bands.
        Direction: 1 = uptrend (above band), -1 = downtrend (below band).

        Parameters
        ----------
        period : int
            ATR period (default: 7).
        multiplier : float
            ATR multiplier (default: 3.0).

        Returns
        -------
        dict[str, pd.Series]
            Dictionary with keys: "trend" (band value), "direction" (1 or -1).
        """
        if period <= 0:
            raise ValueError("period must be positive")
        if multiplier <= 0:
            raise ValueError("multiplier must be positive")

        try:
            st_result = ta.supertrend(
                self.data["high"], self.data["low"], self.data["close"],
                length=period, multiplier=multiplier
            )
        except Exception as exc:
            self._log.error("pandas-ta SuperTrend calculation failed: %s", exc)
            raise RuntimeError(f"SuperTrend calculation failed: {exc}") from exc

        trend_key = f"SUPERT_{period}_{multiplier}"
        dir_key = f"SUPERTd_{period}_{multiplier}"

        if trend_key not in st_result.columns:
            trend_col = [c for c in st_result.columns if c.startswith("SUPERT_")][0]
            dir_col = [c for c in st_result.columns if c.startswith("SUPERTd_")][0]
            trend_key, dir_key = trend_col, dir_col

        return {
            "trend": st_result[trend_key].rename(f"SuperTrend_{period}_{multiplier}"),
            "direction": st_result[dir_key].rename(f"SuperTrend_Dir_{period}_{multiplier}"),
        }

    def psar(self, af: float = 0.02, af_max: float = 0.2) -> dict[str, pd.Series]:
        """
        Parabolic SAR (PSAR) — trend-following indicator.

        Shows potential reversal points via dots that accelerate as the trend
        develops. Use ``psar["value"]`` for the raw SAR value and
        ``psar["trend"]`` for position relative to price (1 = above, -1 = below).

        Parameters
        ----------
        af : float
            Acceleration factor start value (default: 0.02).
        af_max : float
            Maximum acceleration factor (default: 0.2).

        Returns
        -------
        dict[str, pd.Series]
            Dictionary with keys: "value" (SAR level), "trend" (1 or -1).
        """
        if af <= 0 or af_max <= 0:
            raise ValueError("acceleration factors must be positive")
        if af > af_max:
            raise ValueError("af must be <= af_max")

        try:
            psar_result = ta.psar(self.data["high"], self.data["low"], self.data["close"], af=af, af_max=af_max)
        except Exception as exc:
            self._log.error("pandas-ta PSAR calculation failed: %s", exc)
            raise RuntimeError(f"PSAR calculation failed: {exc}") from exc

        long_col = f"PSARl_{af}_{af_max}"
        short_col = f"PSARs_{af}_{af_max}"

        if long_col not in psar_result.columns:
            long_col = [c for c in psar_result.columns if c.startswith("PSARl_")][0]
            short_col = [c for c in psar_result.columns if c.startswith("PSARs_")][0]

        long_series = psar_result[long_col].rename("PSAR")
        short_series = psar_result[short_col].rename("PSAR")

        # Build unified value + trend
        value = long_series.copy()
        trend = pd.Series(-1, index=self.data.index)

        # Where long is not NaN, PSAR is below price (uptrend) -> trend = 1
        # Where short is not NaN, PSAR is above price (downtrend) -> trend = -1
        value = short_series.fillna(long_series)
        trend = trend.where(short_series.notna(), 1)
        trend[value.isna()] = 0

        return {
            "value": value.rename("PSAR_Value"),
            "trend": trend.rename("PSAR_Trend"),
        }

    def ichimoku(
        self,
        tenkan: int = 9,
        kijun: int = 26,
        senkou: int = 52,
    ) -> dict[str, pd.Series | dict[str, pd.Series]]:
        """
        Ichimoku Kinko Hyo — cloud-based trend and breakout indicator.

        Components:
        - **tenkan** (conversion line): short-term trend signal.
        - **kijun** (base line): medium-term trend signal.
        - **span_a / span_b**: leading spans that form the \"kumo\" (cloud).
        - **chikou** (lagging span): price action confirmation.
        - **cloud** (kumo): dict with ``"top"`` and ``"bottom"`` series.

        Parameters
        ----------
        tenkan : int
            Tenkan-sen period (default: 9).
        kijun : int
            Kijun-sen period (default: 26).
        senkou : int
            Senkou span B period (default: 52).

        Returns
        -------
        dict[str, pd.Series | dict[str, pd.Series]]
            Dictionary with keys: "tenkan", "kijun", "span_a", "span_b",
            "chikou", "cloud" (nested dict with "top", "bottom").
        """
        if tenkan <= 0 or kijun <= 0 or senkou <= 0:
            raise ValueError("periods must be positive")

        try:
            ichi_result = ta.ichimoku(
                self.data["high"], self.data["low"], self.data["close"],
                tenkan=tenkan, kijun=kijun, senkou=senkou
            )
        except Exception as exc:
            self._log.error("pandas-ta Ichimoku calculation failed: %s", exc)
            raise RuntimeError(f"Ichimoku calculation failed: {exc}") from exc

        if isinstance(ichi_result, tuple):
            ichimoku_df = ichi_result[0]
            span_df = ichi_result[1]
        else:
            ichimoku_df = ichi_result
            span_df = None

        tenkan_col = f"ITS_{tenkan}"
        kijun_col = f"IKS_{kijun}"
        chikou_col = f"ICS_{kijun}"

        if tenkan_col not in ichimoku_df.columns:
            tenkan_col = [c for c in ichimoku_df.columns if c.startswith("ITS_")][0]
            kijun_col = [c for c in ichimoku_df.columns if c.startswith("IKS_")][0]
            chikou_col = [c for c in ichimoku_df.columns if c.startswith("ICS_")][0]

        result: dict = {
            "tenkan": ichimoku_df[tenkan_col].rename(f"Tenkan_{tenkan}"),
            "kijun": ichimoku_df[kijun_col].rename(f"Kijun_{kijun}"),
            "chikou": ichimoku_df[chikou_col].rename(f"Chikou_{kijun}"),
        }

        if span_df is not None:
            span_a_col = f"ISA_{kijun}"
            span_b_col = f"ISB_{kijun}"

            if span_a_col not in span_df.columns:
                span_a_col = [c for c in span_df.columns if c.startswith("ISA_")][0]
                span_b_col = [c for c in span_df.columns if c.startswith("ISB_")][0]

            span_a = span_df[span_a_col].rename(f"Span_A_{kijun}")
            span_b = span_df[span_b_col].rename(f"Span_B_{kijun}")

            result["span_a"] = span_a
            result["span_b"] = span_b
            result["cloud"] = {
                "top": pd.concat([span_a, span_b], axis=1).max(axis=1).rename("Cloud_Top"),
                "bottom": pd.concat([span_a, span_b], axis=1).min(axis=1).rename("Cloud_Bottom"),
            }

        return result

    # ── Momentum Indicators ───────────────────────────────────────────────────

    def rsi(self, period: int = 14, price: str = "close") -> pd.Series:
        """
        Relative Strength Index.

        Parameters
        ----------
        period : int
            RSI period (default: 14).
        price : str
            Price column to use (default: "close").

        Returns
        -------
        pd.Series
            RSI values (0-100).
        """
        if period <= 0:
            raise ValueError("period must be positive")

        cache_key = self._get_cache_key("rsi", period=period, price=price)
        if cache_key in self._cache:
            return self._cache[cache_key]

        try:
            result = ta.rsi(self.data[price], length=period)
        except Exception as exc:
            self._log.error("pandas-ta RSI calculation failed: %s", exc)
            raise RuntimeError(f"RSI calculation failed: {exc}") from exc

        series = result.rename(f"RSI{period}")
        self._cache[cache_key] = series
        return series

    def stochastic(
        self,
        k_period: int = 14,
        d_period: int = 3,
        smooth_k: int = 3
    ) -> dict[str, pd.Series]:
        """
        Stochastic Oscillator.

        Parameters
        ----------
        k_period : int
            %K period (default: 14).
        d_period : int
            %D period (default: 3).
        smooth_k : int
            %K smoothing (default: 3).

        Returns
        -------
        dict[str, pd.Series]
            Dictionary with keys: "k", "d".
        """
        if k_period <= 0 or d_period <= 0 or smooth_k <= 0:
            raise ValueError("periods must be positive")

        try:
            stoch_result = ta.stoch(
                self.data["high"],
                self.data["low"],
                self.data["close"],
                k=k_period,
                d=d_period,
                smooth_k=smooth_k
            )
        except Exception as exc:
            self._log.error("pandas-ta Stochastic calculation failed: %s", exc)
            raise RuntimeError(f"Stochastic calculation failed: {exc}") from exc

        return {
            "k": stoch_result[f"STOCHk_{k_period}_{d_period}_{smooth_k}"].rename("Stoch_K"),
            "d": stoch_result[f"STOCHd_{k_period}_{d_period}_{smooth_k}"].rename("Stoch_D"),
        }

    def williams_r(self, period: int = 14) -> pd.Series:
        """
        Williams %R.

        Parameters
        ----------
        period : int
            Williams %R period (default: 14).

        Returns
        -------
        pd.Series
            Williams %R values (-100 to 0).
        """
        if period <= 0:
            raise ValueError("period must be positive")

        try:
            result = ta.willr(self.data["high"], self.data["low"], self.data["close"], length=period)
        except Exception as exc:
            self._log.error("pandas-ta Williams %R calculation failed: %s", exc)
            raise RuntimeError(f"Williams %R calculation failed: {exc}") from exc

        return result.rename(f"WilliamsR{period}")

    def cci(self, period: int = 20) -> pd.Series:
        """
        Commodity Channel Index.

        Parameters
        ----------
        period : int
            CCI period (default: 20).

        Returns
        -------
        pd.Series
            CCI values.
        """
        if period <= 0:
            raise ValueError("period must be positive")

        try:
            result = ta.cci(self.data["high"], self.data["low"], self.data["close"], length=period)
        except Exception as exc:
            self._log.error("pandas-ta CCI calculation failed: %s", exc)
            raise RuntimeError(f"CCI calculation failed: {exc}") from exc

        return result.rename(f"CCI{period}")

    # ── Volatility Indicators ─────────────────────────────────────────────────

    def bollinger_bands(
        self,
        period: int = 20,
        std_dev: float = 2.0,
        price: str = "close"
    ) -> dict[str, pd.Series]:
        """
        Bollinger Bands.

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
        dict[str, pd.Series]
            Dictionary with keys: "upper", "middle", "lower".
        """
        if period <= 0:
            raise ValueError("period must be positive")
        if std_dev <= 0:
            raise ValueError("std_dev must be positive")

        try:
            bb_result = ta.bbands(self.data[price], length=period, std=std_dev)
        except Exception as exc:
            self._log.error("pandas-ta Bollinger Bands calculation failed: %s", exc)
            raise RuntimeError(f"Bollinger Bands calculation failed: {exc}") from exc

        # Robust column lookup - handle different naming conventions
        lower_key = f"BBL_{period}_{std_dev}_0"
        middle_key = f"BBM_{period}_{std_dev}_0"
        upper_key = f"BBU_{period}_{std_dev}_0"

        # Fallback to finding columns by pattern if exact match fails
        if lower_key not in bb_result.columns:
            lower_col = [c for c in bb_result.columns if c.startswith("BBL")][0]
            middle_col = [c for c in bb_result.columns if c.startswith("BBM")][0]
            upper_col = [c for c in bb_result.columns if c.startswith("BBU")][0]
            lower_key, middle_key, upper_key = lower_col, middle_col, upper_col

        return {
            "lower": bb_result[lower_key].rename("BB_Lower"),
            "middle": bb_result[middle_key].rename("BB_Middle"),
            "upper": bb_result[upper_key].rename("BB_Upper"),
        }

    def atr(self, period: int = 14) -> pd.Series:
        """
        Average True Range.

        Parameters
        ----------
        period : int
            ATR period (default: 14).

        Returns
        -------
        pd.Series
            ATR values.
        """
        if period <= 0:
            raise ValueError("period must be positive")

        cache_key = self._get_cache_key("atr", period=period)
        if cache_key in self._cache:
            return self._cache[cache_key]

        try:
            result = ta.atr(self.data["high"], self.data["low"], self.data["close"], length=period)
        except Exception as exc:
            self._log.error("pandas-ta ATR calculation failed: %s", exc)
            raise RuntimeError(f"ATR calculation failed: {exc}") from exc

        series = result.rename(f"ATR{period}")
        self._cache[cache_key] = series
        return series

    def keltner_channels(
        self,
        period: int = 20,
        atr_period: int = 10,
        atr_mult: float = 2.0
    ) -> dict[str, pd.Series]:
        """
        Keltner Channels.

        Parameters
        ----------
        period : int
        EMA period (default: 20).
        atr_period : int
            ATR period (default: 10).
        atr_mult : float
            ATR multiplier (default: 2.0).

        Returns
        -------
        dict[str, pd.Series]
            Dictionary with keys: "upper", "middle", "lower".
        """
        if period <= 0 or atr_period <= 0:
            raise ValueError("periods must be positive")
        if atr_mult <= 0:
            raise ValueError("atr_mult must be positive")

        ema = self.ema(period)
        atr = self.atr(atr_period)

        return {
            "upper": ema + (atr * atr_mult),
            "middle": ema,
            "lower": ema - (atr * atr_mult),
        }

    def donchian(
        self,
        length: int = 20,
    ) -> dict[str, pd.Series]:
        """
        Donchian Channels — breakout indicator using rolling high/low.

        Parameters
        ----------
        length : int
            Donchian channel period (default: 20).

        Returns
        -------
        dict[str, pd.Series]
            Dictionary with keys: "upper", "middle", "lower".
        """
        if length <= 0:
            raise ValueError("length must be positive")

        try:
            dc_result = ta.donchian(self.data["high"], self.data["low"], length=length)
        except Exception as exc:
            self._log.error("Donchian Channels calculation failed: %s", exc)
            raise RuntimeError(f"Donchian Channels calculation failed: {exc}") from exc

        upper_key = f"DCU_{length}"
        middle_key = f"DCM_{length}"
        lower_key = f"DCL_{length}"

        if upper_key not in dc_result.columns:
            upper_key = [c for c in dc_result.columns if c.startswith("DCU_")][0]
            middle_key = [c for c in dc_result.columns if c.startswith("DCM_")][0]
            lower_key = [c for c in dc_result.columns if c.startswith("DCL_")][0]

        return {
            "upper": dc_result[upper_key].rename("DC_Upper"),
            "middle": dc_result[middle_key].rename("DC_Middle"),
            "lower": dc_result[lower_key].rename("DC_Lower"),
        }

    # ── Volume Indicators ────────────────────────────────────────────────────

    def obv(self) -> pd.Series:
        """
        On-Balance Volume.

        Returns
        -------
        pd.Series
            OBV values.
        """
        try:
            result = ta.obv(self.data["close"], self.data["volume"])
        except Exception as exc:
            self._log.error("pandas-ta OBV calculation failed: %s", exc)
            raise RuntimeError(f"OBV calculation failed: {exc}") from exc

        return result.rename("OBV")

    def volume_sma(self, period: int = 20) -> pd.Series:
        """
        Volume Simple Moving Average.

        Parameters
        ----------
        period : int
            SMA period (default: 20).

        Returns
        -------
        pd.Series
            Volume SMA values.
        """
        if period <= 0:
            raise ValueError("period must be positive")

        try:
            result = ta.sma(self.data["volume"], length=period)
        except Exception as exc:
            self._log.error("pandas-ta Volume SMA calculation failed: %s", exc)
            raise RuntimeError(f"Volume SMA calculation failed: {exc}") from exc

        return result.rename(f"VolSMA{period}")

    def volume_roc(self, period: int = 12) -> pd.Series:
        """
        Volume Rate of Change.

        Parameters
        ----------
        period : int
            ROC period (default: 12).

        Returns
        -------
        pd.Series
            Volume ROC values.
        """
        if period <= 0:
            raise ValueError("period must be positive")

        try:
            result = ta.roc(self.data["volume"], length=period)
        except Exception as exc:
            self._log.error("pandas-ta Volume ROC calculation failed: %s", exc)
            raise RuntimeError(f"Volume ROC calculation failed: {exc}") from exc

        return result.rename(f"VolROC{period}")

    def vwap(self) -> pd.Series:
        """
        Volume Weighted Average Price using high/low/close typical price.

        Returns
        -------
        pd.Series
            VWAP values.
        """
        tp = (self.data["high"] + self.data["low"] + self.data["close"]) / 3
        cum_vol_price = (tp * self.data["volume"]).cumsum()
        cum_vol = self.data["volume"].cumsum()
        return (cum_vol_price / cum_vol).rename("VWAP")

    # ── Combined Calculations ────────────────────────────────────────────────

    def calculate_all(self, config: Optional[dict] = None) -> dict[str, pd.Series | dict[str, pd.Series]]:
        """
        Calculate multiple indicators at once.

        Parameters
        ----------
        config : dict, optional
            Configuration dictionary with indicator settings.
            If not provided, uses default settings.

        Returns
        -------
        dict[str, pd.Series | dict[str, pd.Series]]
            Dictionary with all calculated indicators.
        """
        if config is None:
            config = {
                "sma": [20, 50],
                "ema": [12, 26],
                "rsi": [14],
                "macd": {"fast": 12, "slow": 26, "signal": 9},
                "bollinger_bands": {"period": 20, "std_dev": 2.0},
                "atr": [14],
            }

        results: dict[str, pd.Series | dict[str, pd.Series]] = {}

        # SMAs
        if "sma" in config:
            for period in config["sma"]:
                results[f"sma_{period}"] = self.sma(period)

        # EMAs
        if "ema" in config:
            for period in config["ema"]:
                results[f"ema_{period}"] = self.ema(period)

        # RSI
        if "rsi" in config:
            for period in config["rsi"]:
                results[f"rsi_{period}"] = self.rsi(period)

        # MACD
        if "macd" in config:
            macd_config = config["macd"]
            results["macd"] = self.macd(
                macd_config.get("fast", 12),
                macd_config.get("slow", 26),
                macd_config.get("signal", 9)
            )

        # Bollinger Bands
        if "bollinger_bands" in config:
            bb_config = config["bollinger_bands"]
            results["bollinger_bands"] = self.bollinger_bands(
                bb_config.get("period", 20),
                bb_config.get("std_dev", 2.0)
            )

        # ATR
        if "atr" in config:
            for period in config["atr"]:
                results[f"atr_{period}"] = self.atr(period)

        # SuperTrend
        if "supertrend" in config:
            st_config = config["supertrend"]
            results["supertrend"] = self.supertrend(
                st_config.get("period", 7),
                st_config.get("multiplier", 3.0)
            )

        # PSAR
        if "psar" in config:
            psar_config = config["psar"]
            results["psar"] = self.psar(
                psar_config.get("af", 0.02),
                psar_config.get("af_max", 0.2),
            )

        # Donchian Channels
        if "donchian" in config:
            dc_config = config["donchian"]
            results["donchian"] = self.donchian(
                dc_config.get("length", 20)
            )

        # Ichimoku
        if "ichimoku" in config:
            ichi_config = config["ichimoku"]
            results["ichimoku"] = self.ichimoku(
                ichi_config.get("tenkan", 9),
                ichi_config.get("kijun", 26),
                ichi_config.get("senkou", 52),
            )

        return results

    # ── Helpers ─────────────────────────────────────────────────────────────

    def get_latest_value(self, series: pd.Series) -> Optional[float]:
        """
        Get the latest non-NaN value from a series.

        Parameters
        ----------
        series : pd.Series
            Indicator series.

        Returns
        -------
        float or None
            Latest value or None if all NaN.
        """
        if series.empty:
            return None

        # Drop NaN values and get last
        valid_values = series.dropna()
        if valid_values.empty:
            return None

        return valid_values.iloc[-1]

    def get_latest_values(self, indicators: dict[str, pd.Series | dict[str, pd.Series]]) -> dict[str, float | dict[str, float | None]]:
        """
        Get latest values from multiple indicators.

        Parameters
        ----------
        indicators : dict[str, pd.Series | dict[str, pd.Series]]
            Dictionary of indicator series.

        Returns
        -------
        dict[str, float | dict[str, float | None]]
            Dictionary of latest values.
        """
        latest: dict[str, float | dict[str, float | None]] = {}

        for key, value in indicators.items():
            if isinstance(value, dict):
                # Nested dict (e.g., MACD)
                latest[key] = {
                    k: self.get_latest_value(v) for k, v in value.items()
                }
            else:
                # Simple series
                latest[key] = self.get_latest_value(value)

        return latest
