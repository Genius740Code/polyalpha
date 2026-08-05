"""
Volume calculations - volume-specific calculations for data sources with volume data.

These calculations are designed for data sources that provide volume information
such as Binance and Coinbase. Chainlink/Polymarket data does not include volume.
"""

from typing import Optional, List
from enum import Enum


class VolumeTrend(Enum):
    """Enumeration for volume trend direction."""
    INCREASING = "increasing"
    DECREASING = "decreasing"
    STABLE = "stable"


class VolumeCalculations:
    """
    Volume-specific calculations for data sources with volume data.
    
    Provides methods to analyze volume patterns, trends, and anomalies.
    Not applicable to Chainlink/Polymarket data which lacks volume information.
    
    Example
    -------
    >>> calc = VolumeCalculations()
    >>> calc.vol_ratio([100, 120, 110, 130], period=3)
    1.18  # Current vol 130 / avg of last 3 = 130 / 110
    >>> calc.volume_trend([100, 120, 110, 130])
    VolumeTrend.INCREASING
    """
    
    @staticmethod
    def vol_ratio(data: List[float], period: int = 10) -> Optional[float]:
        """
        Calculate current volume as ratio to average volume over period.
        
        Parameters
        ----------
        data : list[float]
            Volume data points (oldest to newest).
        period : int
            Number of periods to calculate average (default: 10).
        
        Returns
        -------
        float | None
            Current volume / average volume over period.
            Returns None if insufficient data or average is 0.
        
        Example
        -------
        >>> VolumeCalculations.vol_ratio([100, 120, 110, 130], period=3)
        1.18  # 130 / 110 = 1.18
        """
        if len(data) < 2:
            return None
        
        current = data[-1]
        window = data[-period-1:-1] if len(data) >= period + 1 else data[:-1]
        
        if not window:
            return None
        
        avg_volume = sum(window) / len(window)
        
        if avg_volume == 0:
            return None
        
        return current / avg_volume
    
    @staticmethod
    def volume_trend(data: List[float], period: int = 5, threshold: float = 0.1) -> VolumeTrend:
        """
        Determine volume trend direction over a period.
        
        Parameters
        ----------
        data : list[float]
            Volume data points (oldest to newest).
        period : int
            Number of periods back to analyze (default: 5).
        threshold : float
            Minimum relative change to consider a trend (default: 0.1 for 10%).
        
        Returns
        -------
        VolumeTrend
            INCREASING, DECREASING, or STABLE based on volume movement.
        
        Example
        -------
        >>> VolumeCalculations.volume_trend([100, 120, 110, 130], period=3)
        VolumeTrend.INCREASING
        """
        if len(data) < period + 1:
            return VolumeTrend.STABLE
        
        from .market_calculations import MarketCalculations
        
        change_pct = MarketCalculations.change_pct(data, period)
        if change_pct is None:
            return VolumeTrend.STABLE
        
        if change_pct > threshold:
            return VolumeTrend.INCREASING
        elif change_pct < -threshold:
            return VolumeTrend.DECREASING
        else:
            return VolumeTrend.STABLE
    
    @staticmethod
    def volume_surge(data: List[float], multiplier: float = 2.0, period: int = 10) -> Optional[bool]:
        """
        Detect sudden volume surge compared to recent average.
        
        Parameters
        ----------
        data : list[float]
            Volume data points (oldest to newest).
        multiplier : float
            Multiple of average volume to consider a surge (default: 2.0).
        period : int
            Number of periods to calculate average (default: 10).
        
        Returns
        -------
        bool | None
            True if current volume is > multiplier * average volume.
            Returns None if insufficient data.
        
        Example
        -------
        >>> VolumeCalculations.volume_surge([100, 110, 105, 120, 250], multiplier=2.0)
        True  # 250 > 2.0 * 108.75
        """
        ratio = VolumeCalculations.vol_ratio(data, period)
        if ratio is None:
            return None
        
        return ratio > multiplier
    
    @staticmethod
    def avg_volume(data: List[float], period: int = 10) -> Optional[float]:
        """
        Calculate average volume over a period.
        
        Note: This excludes the current (most recent) value to be consistent
        with vol_ratio, which compares current value against historical average.
        
        Parameters
        ----------
        data : list[float]
            Volume data points (oldest to newest).
        period : int
            Number of periods to average (default: 10).
        
        Returns
        -------
        float | None
            Average volume over the period (excluding current). Returns None if no data.
        
        Example
        -------
        >>> VolumeCalculations.avg_volume([100, 120, 110, 130], period=3)
        110.0  # Average of [100, 120, 110], excluding current 130
        """
        if len(data) < 2:
            return None
        
        # Exclude current value for consistency with vol_ratio
        window = data[-period-1:-1] if len(data) >= period + 1 else data[:-1]
        
        if not window:
            return None
        
        return sum(window) / len(window)
    
    @staticmethod
    def volume_momentum(data: List[float], period: int = 5) -> Optional[float]:
        """
        Calculate volume momentum - rate of volume change.
        
        Parameters
        ----------
        data : list[float]
            Volume data points (oldest to newest).
        period : int
            Number of periods back to compare (default: 5).
        
        Returns
        -------
        float | None
            Percentage change in volume over period.
            Returns None if insufficient data.
        
        Example
        -------
        >>> VolumeCalculations.volume_momentum([100, 120, 110, 130], period=3)
        0.30  # 30% increase over 3 periods
        """
        from .market_calculations import MarketCalculations
        
        return MarketCalculations.change_pct(data, period)
    
    @staticmethod
    def relative_volume(data: List[float], percentile: float = 0.75, period: int = 20) -> Optional[bool]:
        """
        Calculate whether current volume is above a percentile of the last ``period`` volumes.
        
        Uses linear interpolation for more accurate percentile calculation.
        
        Parameters
        ----------
        data : list[float]
            Volume data points (oldest to newest).
        percentile : float
            Percentile threshold (0.0 to 1.0, default: 0.75 for 75th percentile).
        period : int
            Number of most recent periods to analyze (default: 20).
            The current value is compared against the previous ``period`` values.
        
        Returns
        -------
        bool | None
            True if current volume is above the specified percentile.
            Returns None if insufficient data.
        
        Example
        -------
        >>> VolumeCalculations.relative_volume([100, 110, 105, 120, 130], percentile=0.8, period=4)
        True  # 130 is above 80th percentile of [100, 110, 105, 120]
        """
        if len(data) < 2:
            return None
        
        current = data[-1]
        window = data[-period - 1:-1] if len(data) >= period + 1 else data[:-1]
        
        if not window:
            return None
        
        sorted_window = sorted(window)
        n = len(sorted_window)
        
        # Use linear interpolation for accurate percentile
        # Based on numpy's percentile method with linear interpolation
        index = percentile * (n - 1)
        lower_idx = int(index)
        upper_idx = min(lower_idx + 1, n - 1)
        fraction = index - lower_idx
        
        lower_val = sorted_window[lower_idx]
        upper_val = sorted_window[upper_idx]
        
        # Linear interpolation between adjacent values
        threshold = lower_val + fraction * (upper_val - lower_val)
        
        return current > threshold
