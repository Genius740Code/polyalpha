"""
Technical indicator calculations using ta-lib.

Provides a clean interface to ta-lib indicators including:
- Trend indicators: SMA, EMA, MACD, ADX
- Momentum indicators: RSI, Stochastic, Williams %R, CCI
- Volatility indicators: Bollinger Bands, ATR, Keltner Channels
- Volume indicators: OBV, Volume SMA, Volume ROC

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

# Try to import ta-lib
try:
    import talib
    TALIB_AVAILABLE = True
except ImportError:
    TALIB_AVAILABLE = False
    log.warning(
        "ta-lib not installed. Install with: "
        "pip install TA-Lib (requires C compilation) or use pandas-ta as fallback"
    )


# ── Indicator Calculator ─────────────────────────────────────────────────────

class IndicatorCalculator:
    """
    Calculate technical indicators using ta-lib.

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

        if not TALIB_AVAILABLE:
            raise ImportError(
                "ta-lib is required for technical analysis. "
                "Install with: pip install TA-Lib"
            )

        self._log = logging.getLogger(__name__)

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

        return pd.Series(
            talib.SMA(self.data[price].values, timeperiod=period),
            index=self.data.index,
            name=f"SMA{period}"
        )

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

        return pd.Series(
            talib.EMA(self.data[price].values, timeperiod=period),
            index=self.data.index,
            name=f"EMA{period}"
        )

    def macd(
        self,
        fast: int = 12,
        slow: int = 26,
        signal: int = 9,
        price: str = "close"
    ) -> dict:
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
        dict
            Dictionary with keys: "macd", "signal", "histogram".
        """
        if fast <= 0 or slow <= 0 or signal <= 0:
            raise ValueError("periods must be positive")

        macd, signal_line, histogram = talib.MACD(
            self.data[price].values,
            fastperiod=fast,
            slowperiod=slow,
            signalperiod=signal
        )

        return {
            "macd": pd.Series(macd, index=self.data.index, name="MACD"),
            "signal": pd.Series(signal_line, index=self.data.index, name="MACD_Signal"),
            "histogram": pd.Series(histogram, index=self.data.index, name="MACD_Hist"),
        }

    def adx(self, period: int = 14) -> dict:
        """
        Average Directional Index.

        Parameters
        ----------
        period : int
            ADX period (default: 14).

        Returns
        -------
        dict
            Dictionary with keys: "adx", "plus_di", "minus_di".
        """
        if period <= 0:
            raise ValueError("period must be positive")

        adx, plus_di, minus_di = talib.ADX(
            self.data["high"].values,
            self.data["low"].values,
            self.data["close"].values,
            timeperiod=period
        )

        return {
            "adx": pd.Series(adx, index=self.data.index, name="ADX"),
            "plus_di": pd.Series(plus_di, index=self.data.index, name="+DI"),
            "minus_di": pd.Series(minus_di, index=self.data.index, name="-DI"),
        }

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

        return pd.Series(
            talib.RSI(self.data[price].values, timeperiod=period),
            index=self.data.index,
            name=f"RSI{period}"
        )

    def stochastic(
        self,
        k_period: int = 14,
        d_period: int = 3,
        smooth_k: int = 3
    ) -> dict:
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
        dict
            Dictionary with keys: "k", "d".
        """
        if k_period <= 0 or d_period <= 0 or smooth_k <= 0:
            raise ValueError("periods must be positive")

        slowk, slowd = talib.STOCH(
            self.data["high"].values,
            self.data["low"].values,
            self.data["close"].values,
            fastk_period=k_period,
            slowk_period=smooth_k,
            slowk_matype=0,
            slowd_period=d_period,
            slowd_matype=0
        )

        return {
            "k": pd.Series(slowk, index=self.data.index, name="Stoch_K"),
            "d": pd.Series(slowd, index=self.data.index, name="Stoch_D"),
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

        return pd.Series(
            talib.WILLR(
                self.data["high"].values,
                self.data["low"].values,
                self.data["close"].values,
                timeperiod=period
            ),
            index=self.data.index,
            name=f"WilliamsR{period}"
        )

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

        return pd.Series(
            talib.CCI(
                self.data["high"].values,
                self.data["low"].values,
                self.data["close"].values,
                timeperiod=period
            ),
            index=self.data.index,
            name=f"CCI{period}"
        )

    # ── Volatility Indicators ─────────────────────────────────────────────────

    def bollinger_bands(
        self,
        period: int = 20,
        std_dev: float = 2.0,
        price: str = "close"
    ) -> dict:
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
        dict
            Dictionary with keys: "upper", "middle", "lower".
        """
        if period <= 0:
            raise ValueError("period must be positive")
        if std_dev <= 0:
            raise ValueError("std_dev must be positive")

        upper, middle, lower = talib.BBANDS(
            self.data[price].values,
            timeperiod=period,
            nbdevup=std_dev,
            nbdevdn=std_dev,
            matype=0
        )

        return {
            "upper": pd.Series(upper, index=self.data.index, name="BB_Upper"),
            "middle": pd.Series(middle, index=self.data.index, name="BB_Middle"),
            "lower": pd.Series(lower, index=self.data.index, name="BB_Lower"),
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

        return pd.Series(
            talib.ATR(
                self.data["high"].values,
                self.data["low"].values,
                self.data["close"].values,
                timeperiod=period
            ),
            index=self.data.index,
            name=f"ATR{period}"
        )

    def keltner_channels(
        self,
        period: int = 20,
        atr_period: int = 10,
        atr_mult: float = 2.0
    ) -> dict:
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
        dict
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

    # ── Volume Indicators ────────────────────────────────────────────────────

    def obv(self) -> pd.Series:
        """
        On-Balance Volume.

        Returns
        -------
        pd.Series
            OBV values.
        """
        return pd.Series(
            talib.OBV(self.data["close"].values, self.data["volume"].values),
            index=self.data.index,
            name="OBV"
        )

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

        return pd.Series(
            talib.SMA(self.data["volume"].values, timeperiod=period),
            index=self.data.index,
            name=f"VolSMA{period}"
        )

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

        return pd.Series(
            talib.ROC(self.data["volume"].values, timeperiod=period),
            index=self.data.index,
            name=f"VolROC{period}"
        )

    # ── Combined Calculations ────────────────────────────────────────────────

    def calculate_all(self, config: Optional[dict] = None) -> dict:
        """
        Calculate multiple indicators at once.

        Parameters
        ----------
        config : dict, optional
            Configuration dictionary with indicator settings.
            If not provided, uses default settings.

        Returns
        -------
        dict
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

        results = {}

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

    def get_latest_values(self, indicators: dict) -> dict:
        """
        Get latest values from multiple indicators.

        Parameters
        ----------
        indicators : dict
            Dictionary of indicator series.

        Returns
        -------
        dict
            Dictionary of latest values.
        """
        latest = {}

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
