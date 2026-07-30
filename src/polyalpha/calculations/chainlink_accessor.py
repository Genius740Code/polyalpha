"""
Chainlink accessor - Chainlink-specific data accessor with price calculations.

Provides Chainlink/Polymarket price data access with calculation methods.
Chainlink data does not include volume information, so only price calculations
are available.
"""

from typing import Optional, List
from .base_accessor import BaseAccessor

try:
    from ..windows import TimeWindow
except ImportError:
    TimeWindow = None  # type: ignore[assignment]


class ChainlinkAccessor(BaseAccessor):
    """
    Chainlink/Polymarket data accessor with price calculations.
    
    Provides access to Chainlink BTC price data from Polymarket with
    comprehensive price calculation methods. Does not support volume
    calculations as Chainlink data lacks volume information.
    
    Example
    -------
    >>> from polyalpha.windows import TimeWindow
    >>> from polyalpha.calculations import ChainlinkAccessor
    >>> 
    >>> window = TimeWindow(max_age=120)
    >>> accessor = ChainlinkAccessor(window)
    >>> 
    >>> # Update with Chainlink prices
    >>> accessor.update(67850.0)
    >>> accessor.update(67900.0)
    >>> 
    >>> # Calculate changes
    >>> accessor.change_pct(30)  # % change over 30 seconds
    >>> accessor.trend(60)       # trend direction over 60 seconds
    >>> accessor.volatility(120) # price volatility
    """
    
    def __init__(self, window: Optional['TimeWindow'] = None, max_age: float = 120.0):
        """
        Initialize Chainlink accessor.
        
        Parameters
        ----------
        window : TimeWindow | None
            Existing TimeWindow with Chainlink price data.
        max_age : float
            Maximum age in seconds for TimeWindow if creating new one.
        """
        super().__init__(window, max_age)
        self._asset = "BTC"  # Chainlink default asset
    
    def _get_price_data(self) -> List[float]:
        """
        Get price data from the Chainlink TimeWindow.
        
        Returns
        -------
        list[float]
            Price data points from the TimeWindow, ordered oldest to newest.
        """
        if self._window is None:
            return []
        
        # Extract values from TimeWindow data points
        return [point.value for point in self._window._data]
    
    def _get_volume_data(self) -> List[float]:
        """
        Chainlink does not provide volume data.
        
        Returns
        -------
        list[float]
            Empty list - volume not available for Chainlink.
        """
        return []
    
    # ── Chainlink-Specific Convenience Methods ───────────────────────────────
    
    @property
    def asset(self) -> str:
        """Get the asset symbol (default: BTC)."""
        return self._asset
    
    @asset.setter
    def asset(self, value: str) -> None:
        """Set the asset symbol."""
        self._asset = value.upper()
    
    def is_fresh(self, max_age_seconds: float = 60.0) -> bool:
        """
        Check if the Chainlink data is fresh (recently updated).
        
        Parameters
        ----------
        max_age_seconds : float
            Maximum age in seconds to consider data fresh (default: 60).
        
        Returns
        -------
        bool
            True if data was updated within max_age_seconds.
        """
        return self.age_s <= max_age_seconds
    
    def is_valid_price(self) -> bool:
        """
        Check if the current Chainlink price is valid.
        
        Returns
        -------
        bool
            True if price exists and is positive.
        """
        price = self.value
        return price is not None and price > 0
    
    def price_change_since(self, seconds: float) -> Optional[float]:
        """
        Get absolute price change since a given time ago.
        
        Convenience method combining change_abs with time-based period.
        
        Parameters
        ----------
        seconds : float
            Time period in seconds.
        
        Returns
        -------
        float | None
            Absolute price change, or None if insufficient data.
        """
        return self.change_abs(seconds)
    
    def price_change_pct_since(self, seconds: float) -> Optional[float]:
        """
        Get percentage price change since a given time ago.
        
        Convenience method for change_pct.
        
        Parameters
        ----------
        seconds : float
            Time period in seconds.
        
        Returns
        -------
        float | None
            Percentage change as decimal, or None if insufficient data.
        """
        return self.change_pct(seconds)
    
    def is_rising(self, seconds: float = 30.0) -> Optional[bool]:
        """
        Check if price is rising over the given time period.
        
        Parameters
        ----------
        seconds : float
            Time period in seconds (default: 30).
        
        Returns
        -------
        bool | None
            True if price increased, False if decreased, None if insufficient data.
        """
        direction = self.direction(seconds)
        if direction is None:
            return None
        return direction == "up"
    
    def is_falling(self, seconds: float = 30.0) -> Optional[bool]:
        """
        Check if price is falling over the given time period.
        
        Parameters
        ----------
        seconds : float
            Time period in seconds (default: 30).
        
        Returns
        -------
        bool | None
            True if price decreased, False if increased, None if insufficient data.
        """
        direction = self.direction(seconds)
        if direction is None:
            return None
        return direction == "down"
    
    def __repr__(self) -> str:
        """String representation of Chainlink accessor."""
        return f"ChainlinkAccessor(asset={self._asset}, value={self.value}, age_s={self.age_s:.1f})"
