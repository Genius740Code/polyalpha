"""
Delta change (rate of change) indicators.

Measures the velocity and acceleration of price movements,
providing momentum signals for trading strategies.

Usage
-----
    from polyalpha.analysis import DeltaCalculator

    delta = DeltaCalculator(data)
    simple_delta = delta.delta()
    period_delta = delta.delta_period(period=5)
    acceleration = delta.delta_acceleration()
"""

from __future__ import annotations

import logging
from typing import Optional

import pandas as pd

try:
    import pandas_ta as ta
    PANDAS_TA_AVAILABLE = True
except ImportError:
    PANDAS_TA_AVAILABLE = False
    logging.getLogger(__name__).warning(
        "pandas-ta not installed. Install with: pip install pandas-ta"
    )

log = logging.getLogger(__name__)


class DeltaCalculator:
    """
    Calculate delta change (rate of change) indicators.

    Parameters
    ----------
    data : pd.DataFrame
        OHLCV data with columns: timestamp, open, high, low, close, volume.

    Example
    -------
    >>> delta = DeltaCalculator(data)
    >>> simple = delta.delta()
    >>> pct_change = delta.delta_percent()
    """

    def __init__(self, data: pd.DataFrame):
        """Initialize delta calculator."""
        self.data = data.copy()
        self._validate_data()

        if not PANDAS_TA_AVAILABLE:
            raise ImportError(
                "pandas-ta is required for delta calculations. "
                "Install with: pip install pandas-ta"
            )

        self._log = logging.getLogger(__name__)
        self._cache: dict[str, pd.Series] = {}

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

    # ── Delta Methods ───────────────────────────────────────────────────────

    def delta(self, price: str = "close") -> pd.Series:
        """
        Simple delta: price change between consecutive periods.

        Parameters
        ----------
        price : str
            Price column to use: "open" | "high" | "low" | "close" (default: "close").

        Returns
        -------
        pd.Series
            Delta values (current - previous).
        """
        cache_key = self._get_cache_key("delta", price=price)
        if cache_key in self._cache:
            return self._cache[cache_key]

        delta = self.data[price].diff()
        series = delta.rename(f"Delta_{price}")
        self._cache[cache_key] = series
        return series

    def delta_period(self, period: int = 1, price: str = "close") -> pd.Series:
        """
        Delta over N periods: price change over specified lookback.

        Parameters
        ----------
        period : int
            Number of periods to look back (default: 1).
        price : str
            Price column to use: "open" | "high" | "low" | "close" (default: "close").

        Returns
        -------
        pd.Series
            Delta values (current - N periods ago).
        """
        if period <= 0:
            raise ValueError("period must be positive")

        cache_key = self._get_cache_key("delta_period", period=period, price=price)
        if cache_key in self._cache:
            return self._cache[cache_key]

        delta = self.data[price].diff(periods=period)
        series = delta.rename(f"Delta_{price}_{period}")
        self._cache[cache_key] = series
        return series

    def delta_percent(self, price: str = "close") -> pd.Series:
        """
        Delta percentage: percentage change between consecutive periods.

        Parameters
        ----------
        price : str
            Price column to use: "open" | "high" | "low" | "close" (default: "close").

        Returns
        -------
        pd.Series
            Percentage change values ((current - previous) / previous * 100).
        """
        cache_key = self._get_cache_key("delta_percent", price=price)
        if cache_key in self._cache:
            return self._cache[cache_key]

        delta_pct = self.data[price].pct_change() * 100
        series = delta_pct.rename(f"DeltaPct_{price}")
        self._cache[cache_key] = series
        return series

    def delta_percent_period(self, period: int = 1, price: str = "close") -> pd.Series:
        """
        Delta percentage over N periods: percentage change over specified lookback.

        Parameters
        ----------
        period : int
            Number of periods to look back (default: 1).
        price : str
            Price column to use: "open" | "high" | "low" | "close" (default: "close").

        Returns
        -------
        pd.Series
            Percentage change values over N periods.
        """
        if period <= 0:
            raise ValueError("period must be positive")

        cache_key = self._get_cache_key("delta_percent_period", period=period, price=price)
        if cache_key in self._cache:
            return self._cache[cache_key]

        delta_pct = self.data[price].pct_change(periods=period) * 100
        series = delta_pct.rename(f"DeltaPct_{price}_{period}")
        self._cache[cache_key] = series
        return series

    def delta_acceleration(self, period: int = 1, price: str = "close") -> pd.Series:
        """
        Delta acceleration: rate of change of delta (second derivative).

        Measures how quickly the rate of change itself is changing.
        Positive acceleration = momentum is increasing, negative = momentum is decreasing.

        Parameters
        ----------
        period : int
            Period for delta calculation (default: 1).
        price : str
            Price column to use: "open" | "high" | "low" | "close" (default: "close").

        Returns
        -------
        pd.Series
            Acceleration values (change in delta).
        """
        if period <= 0:
            raise ValueError("period must be positive")

        cache_key = self._get_cache_key("delta_acceleration", period=period, price=price)
        if cache_key in self._cache:
            return self._cache[cache_key]

        delta = self.delta_period(period, price)
        acceleration = delta.diff()
        series = acceleration.rename(f"DeltaAcc_{price}_{period}")
        self._cache[cache_key] = series
        return series

    def delta_smoothed(
        self,
        period: int = 1,
        smooth_period: int = 3,
        price: str = "close"
    ) -> pd.Series:
        """
        Smoothed delta: delta with smoothing to reduce noise.

        Parameters
        ----------
        period : int
            Delta period (default: 1).
        smooth_period : int
            SMA smoothing period (default: 3).
        price : str
            Price column to use: "open" | "high" | "low" | "close" (default: "close").

        Returns
        -------
        pd.Series
            Smoothed delta values.
        """
        if period <= 0 or smooth_period <= 0:
            raise ValueError("periods must be positive")

        cache_key = self._get_cache_key("delta_smoothed", period=period, smooth_period=smooth_period, price=price)
        if cache_key in self._cache:
            return self._cache[cache_key]

        delta = self.delta_period(period, price)
        smoothed = ta.sma(delta, length=smooth_period)
        series = smoothed.rename(f"DeltaSmooth_{price}_{period}_{smooth_period}")
        self._cache[cache_key] = series
        return series

    # ── Helpers ─────────────────────────────────────────────────────────────

    def get_latest_value(self, series: pd.Series) -> Optional[float]:
        """
        Get the latest non-NaN value from a series.

        Parameters
        ----------
        series : pd.Series
            Delta series.

        Returns
        -------
        float or None
            Latest value or None if all NaN.
        """
        if series.empty:
            return None

        valid_values = series.dropna()
        if valid_values.empty:
            return None

        return valid_values.iloc[-1]
