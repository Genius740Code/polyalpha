"""
Market calculations - universal price calculations for all data sources.

These calculations work with any time series data from Chainlink, Binance, 
Coinbase, or other price sources. They are independent of volume data.
"""

from typing import Optional, Tuple, List
from enum import Enum


class TrendDirection(Enum):
    """Enumeration for trend direction."""
    UP = "up"
    DOWN = "down"
    NEUTRAL = "neutral"


class MarketCalculations:
    """
    Universal market price calculations.
    
    Provides calculation methods that work with any time series price data.
    Uses a sliding window approach to calculate changes over custom time periods.
    
    Example
    -------
    >>> calc = MarketCalculations()
    >>> calc.change_pct([100, 105, 103], period=2)
    0.03
    >>> calc.trend([100, 105, 103, 108], period=3)
    TrendDirection.UP
    """
    
    @staticmethod
    def change_pct(data: List[float], period: int = 1) -> Optional[float]:
        """
        Calculate percentage change over a given period.
        
        Parameters
        ----------
        data : list[float]
            Time series data points (oldest to newest).
        period : int
            Number of periods back to compare (default: 1).
        
        Returns
        -------
        float | None
            Percentage change as decimal (e.g., 0.12 for 12%).
            Returns None if insufficient data.
        
        Example
        -------
        >>> MarketCalculations.change_pct([100, 105, 103], period=2)
        0.03
        """
        if len(data) < period + 1:
            return None
        
        current = data[-1]
        previous = data[-period - 1]
        
        if previous == 0:
            return None
        
        return (current - previous) / previous
    
    @staticmethod
    def change_abs(data: List[float], period: int = 1) -> Optional[float]:
        """
        Calculate absolute price change over a given period.
        
        Parameters
        ----------
        data : list[float]
            Time series data points (oldest to newest).
        period : int
            Number of periods back to compare (default: 1).
        
        Returns
        -------
        float | None
            Absolute price difference (current - previous).
            Returns None if insufficient data.
        
        Example
        -------
        >>> MarketCalculations.change_abs([100, 105, 103], period=2)
        3.0
        """
        if len(data) < period + 1:
            return None
        
        return data[-1] - data[-period - 1]
    
    @staticmethod
    def rate_of_change(data: List[float], period: int = 1, time_interval: Optional[float] = None) -> Optional[float]:
        """
        Calculate rate of change per second (derivative).
        
        Parameters
        ----------
        data : list[float]
            Time series data points (oldest to newest).
        period : int
            Number of periods back to sample (default: 1).
        time_interval : float | None
            Time between data points in seconds. Required to produce a
            per-second rate; if None the true interval is unknown and the
            function returns None rather than silently assuming 1 second
            per data point (default: None).
        
        Returns
        -------
        float | None
            Rate of change per second.
            Returns None if insufficient data, time_interval is None, or
            time_interval is 0.
        
        Example
        -------
        >>> MarketCalculations.rate_of_change([100, 105, 103], period=2, time_interval=5.0)
        0.3  # 3.0 change over 10 seconds (2 periods * 5s) = 0.3 per second
        """
        if time_interval is None or time_interval <= 0:
            return None
        if len(data) < period + 1:
            return None
        
        abs_change = MarketCalculations.change_abs(data, period)
        if abs_change is None:
            return None
        
        # Total time elapsed is period * time_interval
        total_time = period * time_interval
        return abs_change / total_time
    
    @staticmethod
    def trend(data: List[float], period: int = 1, threshold: float = 0.0) -> TrendDirection:
        """
        Determine overall trend direction over a period.
        
        Parameters
        ----------
        data : list[float]
            Time series data points (oldest to newest).
        period : int
            Number of periods back to analyze (default: 1).
        threshold : float
            Minimum absolute change to consider a trend (default: 0.0).
        
        Returns
        -------
        TrendDirection
            UP, DOWN, or NEUTRAL based on price movement.
        
        Example
        -------
        >>> MarketCalculations.trend([100, 105, 103, 108], period=3)
        TrendDirection.UP
        """
        if len(data) < period + 1:
            return TrendDirection.NEUTRAL
        
        change = MarketCalculations.change_abs(data, period)
        if change is None:
            return TrendDirection.NEUTRAL
        
        if abs(change) < threshold:
            return TrendDirection.NEUTRAL
        
        return TrendDirection.UP if change > 0 else TrendDirection.DOWN
    
    @staticmethod
    def direction(data: List[float], period: int = 1) -> Optional[str]:
        """
        Get simple direction of change (up/down/flat).
        
        Parameters
        ----------
        data : list[float]
            Time series data points (oldest to newest).
        period : int
            Number of periods back to compare (default: 1).
        
        Returns
        -------
        str | None
            "up", "down", or "flat". Returns None if insufficient data.
        
        Example
        -------
        >>> MarketCalculations.direction([100, 105, 103], period=2)
        "up"
        """
        if len(data) < period + 1:
            return None
        
        change = MarketCalculations.change_abs(data, period)
        if change is None:
            return None
        
        if change > 0:
            return "up"
        elif change < 0:
            return "down"
        else:
            return "flat"
    
    @staticmethod
    def volatility(data: List[float], period: int = 10) -> Optional[float]:
        """
        Calculate price volatility (standard deviation) over a period.
        
        Uses sample standard deviation (dividing by n-1) for better statistical
        estimation of the underlying population variance.
        
        Parameters
        ----------
        data : list[float]
            Time series data points (oldest to newest).
        period : int
            Number of periods to analyze (default: 10).
        
        Returns
        -------
        float | None
            Standard deviation of prices over the period.
            Returns None if insufficient data.
        
        Example
        -------
        >>> MarketCalculations.volatility([100, 105, 103, 108, 102], period=5)
        2.68
        """
        if len(data) < 2:
            return None
        
        window = data[-period:] if len(data) >= period else data
        n = len(window)
        
        if n < 2:
            return None
        
        mean = sum(window) / n
        # Use sample variance (n-1) for better statistical estimation
        variance = sum((x - mean) ** 2 for x in window) / (n - 1)
        return variance ** 0.5
    
    @staticmethod
    def high(data: List[float], period: int = 10) -> Optional[float]:
        """
        Get highest price over a period.
        
        Parameters
        ----------
        data : list[float]
            Time series data points (oldest to newest).
        period : int
            Number of periods to analyze (default: 10).
        
        Returns
        -------
        float | None
            Highest price in the period. Returns None if no data.
        """
        if not data:
            return None
        
        window = data[-period:] if len(data) >= period else data
        return max(window)
    
    @staticmethod
    def low(data: List[float], period: int = 10) -> Optional[float]:
        """
        Get lowest price over a period.
        
        Parameters
        ----------
        data : list[float]
            Time series data points (oldest to newest).
        period : int
            Number of periods to analyze (default: 10).
        
        Returns
        -------
        float | None
            Lowest price in the period. Returns None if no data.
        """
        if not data:
            return None
        
        window = data[-period:] if len(data) >= period else data
        return min(window)
    
    @staticmethod
    def range(data: List[float], period: int = 10) -> Optional[float]:
        """
        Calculate price range (high - low) over a period.
        
        Parameters
        ----------
        data : List[float]
            Time series data points (oldest to newest).
        period : int
            Number of periods to analyze (default: 10).
        
        Returns
        -------
        float | None
            Price range (high - low). Returns None if insufficient data.
        """
        if not data:
            return None
        
        high = MarketCalculations.high(data, period)
        low = MarketCalculations.low(data, period)
        
        if high is None or low is None:
            return None
        
        return high - low
