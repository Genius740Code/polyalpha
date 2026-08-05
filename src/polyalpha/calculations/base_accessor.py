"""
Base accessor - source-aware calculation methods for data sources.

Provides a base class that integrates TimeWindow with calculation functions
to create source-specific accessors for Chainlink, Binance, Coinbase, etc.
"""

from typing import Optional, Union, List
from abc import ABC, abstractmethod

try:
    from ..windows import TimeWindow
except ImportError:
    TimeWindow = None  # type: ignore[assignment]

from .market_calculations import MarketCalculations, TrendDirection
from .volume_calculations import VolumeCalculations, VolumeTrend


class BaseAccessor(ABC):
    """
    Base class for data source accessors with calculation methods.
    
    Integrates TimeWindow with calculation functions to provide source-specific
    calculation methods. Each data source (Chainlink, Binance, Coinbase) should
    subclass this and implement the data retrieval methods.
    
    Example
    -------
    class ChainlinkAccessor(BaseAccessor):
        def _get_price_data(self) -> list[float]:
            return self._window._data
        
        def _get_volume_data(self) -> list[float]:
            return []  # Chainlink has no volume
    
    Subclasses automatically get calculation methods like:
    - change_pct(seconds), change_abs(seconds), rate_of_change(seconds)
    - trend(seconds), direction(seconds), volatility(seconds)
    - vol_ratio(period), volume_trend(period) (if volume data available)
    """
    
    def __init__(self, window: Optional['TimeWindow'] = None, max_age: float = 120.0):
        """
        Initialize the base accessor.
        
        Parameters
        ----------
        window : TimeWindow | None
            Existing TimeWindow instance, or None to create a new one.
        max_age : float
            Maximum age in seconds for TimeWindow if creating new one.
        """
        if TimeWindow is None:
            self._window = None
        elif window is not None:
            self._window = window
        else:
            self._window = TimeWindow(max_age=max_age)
        
        self._market_calc = MarketCalculations()
        self._volume_calc = VolumeCalculations()
    
    @abstractmethod
    def _get_price_data(self) -> List[float]:
        """
        Get price data from the source.
        
        Subclasses must implement this to return price data as a list of floats.
        The data should be ordered from oldest to newest.
        
        Returns
        -------
        List[float]
            Price data points.
        """
        pass
    
    def _get_volume_data(self) -> List[float]:
        """
        Get volume data from the source.
        
        Subclasses can override this if they have volume data.
        Default returns empty list (no volume support).
        
        Returns
        -------
        List[float]
            Volume data points, or empty list if not available.
        """
        return []
    
    @property
    def has_volume(self) -> bool:
        """Check if this data source has volume data."""
        return len(self._get_volume_data()) > 0
    
    # ── Universal Price Calculations ────────────────────────────────────────
    
    def change_pct(self, seconds: float) -> Optional[float]:
        """
        Calculate percentage change over time period.
        
        Parameters
        ----------
        seconds : float
            Time period in seconds.
        
        Returns
        -------
        float | None
            Percentage change as decimal, or None if insufficient data.
        """
        if self._window is None:
            return None
        return self._window.change_pct(seconds)
    
    def change_abs(self, seconds: float) -> Optional[float]:
        """
        Calculate absolute price change over time period.
        
        Parameters
        ----------
        seconds : float
            Time period in seconds.
        
        Returns
        -------
        float | None
            Absolute price change, or None if insufficient data.
        """
        if self._window is None:
            return None
        return self._window.change_abs(seconds)
    
    def rate_of_change(self, seconds: float) -> Optional[float]:
        """
        Calculate rate of change per second (derivative).
        
        Parameters
        ----------
        seconds : float
            Time period in seconds.
        
        Returns
        -------
        float | None
            Rate of change per second, or None if insufficient data.
        """
        data = self._get_price_data()
        if not data:
            return None
        
        # Estimate periods from seconds and data
        # This is approximate; exact calculation requires timestamps
        period = max(1, int(len(data) * seconds / (self._window._max_age if self._window else 120)))
        return self._market_calc.rate_of_change(data, period)
    
    def trend(self, seconds: float, threshold: float = 0.0) -> TrendDirection:
        """
        Determine overall trend direction over time period.
        
        Parameters
        ----------
        seconds : float
            Time period in seconds.
        threshold : float
            Minimum absolute change to consider a trend.
        
        Returns
        -------
        TrendDirection
            UP, DOWN, or NEUTRAL.
        """
        data = self._get_price_data()
        if not data:
            return TrendDirection.NEUTRAL
        
        period = max(1, int(len(data) * seconds / (self._window._max_age if self._window else 120)))
        return self._market_calc.trend(data, period, threshold)
    
    def direction(self, seconds: float) -> Optional[str]:
        """
        Get simple direction of change (up/down/flat).
        
        Parameters
        ----------
        seconds : float
            Time period in seconds.
        
        Returns
        -------
        str | None
            "up", "down", or "flat". None if insufficient data.
        """
        data = self._get_price_data()
        if not data:
            return None
        
        period = max(1, int(len(data) * seconds / (self._window._max_age if self._window else 120)))
        return self._market_calc.direction(data, period)
    
    def volatility(self, seconds: float) -> Optional[float]:
        """
        Calculate price volatility over time period.
        
        Parameters
        ----------
        seconds : float
            Time period in seconds.
        
        Returns
        -------
        float | None
            Standard deviation of prices, or None if insufficient data.
        """
        data = self._get_price_data()
        if not data:
            return None
        
        period = max(2, int(len(data) * seconds / (self._window._max_age if self._window else 120)))
        return self._market_calc.volatility(data, period)
    
    def high(self, seconds: float) -> Optional[float]:
        """Get highest price over time period."""
        data = self._get_price_data()
        if not data:
            return None
        
        period = max(1, int(len(data) * seconds / (self._window._max_age if self._window else 120)))
        return self._market_calc.high(data, period)
    
    def low(self, seconds: float) -> Optional[float]:
        """Get lowest price over time period."""
        data = self._get_price_data()
        if not data:
            return None
        
        period = max(1, int(len(data) * seconds / (self._window._max_age if self._window else 120)))
        return self._market_calc.low(data, period)
    
    def range(self, seconds: float) -> Optional[float]:
        """Calculate price range (high - low) over time period."""
        data = self._get_price_data()
        if not data:
            return None
        
        period = max(1, int(len(data) * seconds / (self._window._max_age if self._window else 120)))
        return self._market_calc.range(data, period)
    
    # ── Volume Calculations (if available) ───────────────────────────────────
    
    def vol_ratio(self, period: int = 10) -> Optional[float]:
        """
        Calculate current volume as ratio to average volume.
        
        Only available for data sources with volume data.
        
        Parameters
        ----------
        period : int
            Number of periods to calculate average.
        
        Returns
        -------
        float | None
            Volume ratio, or None if no volume data.
        """
        if not self.has_volume:
            return None
        
        data = self._get_volume_data()
        return self._volume_calc.vol_ratio(data, period)
    
    def volume_trend(self, period: int = 5, threshold: float = 0.1) -> VolumeTrend:
        """
        Determine volume trend direction.
        
        Only available for data sources with volume data.
        
        Parameters
        ----------
        period : int
            Number of periods to analyze.
        threshold : float
            Minimum relative change to consider a trend.
        
        Returns
        -------
        VolumeTrend
            INCREASING, DECREASING, or STABLE.
        """
        if not self.has_volume:
            return VolumeTrend.STABLE
        
        data = self._get_volume_data()
        return self._volume_calc.volume_trend(data, period, threshold)
    
    def volume_surge(self, multiplier: float = 2.0, period: int = 10) -> Optional[bool]:
        """
        Detect sudden volume surge.
        
        Only available for data sources with volume data.
        
        Parameters
        ----------
        multiplier : float
            Multiple of average volume to consider a surge.
        period : int
            Number of periods to calculate average.
        
        Returns
        -------
        bool | None
            True if volume surge detected, None if no volume data.
        """
        if not self.has_volume:
            return None
        
        data = self._get_volume_data()
        return self._volume_calc.volume_surge(data, multiplier, period)
    
    def avg_volume(self, period: int = 10) -> Optional[float]:
        """Calculate average volume over period."""
        if not self.has_volume:
            return None
        
        data = self._get_volume_data()
        return self._volume_calc.avg_volume(data, period)
    
    # ── TimeWindow Direct Access ─────────────────────────────────────────────
    
    @property
    def value(self) -> Optional[float]:
        """Latest value from the TimeWindow."""
        return self._window.value if self._window else None
    
    @property
    def age_s(self) -> float:
        """Seconds since last update."""
        return self._window.age_s if self._window else float('inf')
    
    def update(self, value: float) -> None:
        """Update the TimeWindow with a new value."""
        if self._window is not None:
            self._window.update(value)
