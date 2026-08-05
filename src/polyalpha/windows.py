"""
TimeWindow — reusable rolling window with helper methods.

Provides a thread-safe rolling time window that can track any data source
and calculate percentage changes over custom time periods.
"""

import threading
import time
from collections import deque
from dataclasses import dataclass
from typing import Optional


@dataclass
class TimePoint:
    """A single timestamped data point."""
    value: float
    timestamp: float


class TimeWindow:
    """
    Thread-safe rolling time window with change percentage helpers.
    
    Automatically prunes old entries based on max_age and provides
    convenient methods for calculating percentage changes over custom
    time periods.
    
    Example
    -------
    >>> w = TimeWindow(max_age=120)
    >>> w.update(50000.0)  # from any source
    >>> w.value  # latest value
    50000.0
    >>> w.change_pct(30)  # % change over 30 seconds
    0.12
    >>> w.age_s  # seconds since last update
    0.5
    """
    
    def __init__(self, max_age: float = 120.0):
        """
        Initialize a TimeWindow.
        
        Parameters
        ----------
        max_age : float
            Maximum age in seconds to keep data points. Older points are
            automatically pruned.
        """
        self._max_age = max_age
        self._data: deque[TimePoint] = deque()
        self._lock = threading.RLock()
        self._latest_value: Optional[float] = None
        self._latest_timestamp: Optional[float] = None
    
    def update(self, value: float) -> None:
        """
        Add a new data point with current timestamp.
        
        Parameters
        ----------
        value : float
            The new data point value.
        """
        now = time.time()
        with self._lock:
            point = TimePoint(value=value, timestamp=now)
            self._data.append(point)
            self._latest_value = value
            self._latest_timestamp = now
            self._prune()
    
    def _prune(self) -> None:
        """Remove data points older than max_age."""
        now = time.time()
        cutoff = now - self._max_age
        while self._data and self._data[0].timestamp < cutoff:
            self._data.popleft()
    
    @property
    def value(self) -> Optional[float]:
        """
        Latest value in the window.
        
        Returns
        -------
        float | None
            The most recent value, or None if no data has been added.
        """
        with self._lock:
            return self._latest_value
    
    @property
    def age_s(self) -> float:
        """
        Seconds since the last update.
        
        Returns
        -------
        float
            Time elapsed since the most recent data point, in seconds.
            Returns float('inf') if no data has been added.
        """
        with self._lock:
            if self._latest_timestamp is None:
                return float('inf')
            return time.time() - self._latest_timestamp
    
    def change_pct(self, seconds: float) -> Optional[float]:
        """
        Calculate percentage change over a given time period.
        
        Parameters
        ----------
        seconds : float
            Time period in seconds to calculate change over.
        
        Returns
        -------
        float | None
            Percentage change as a decimal (e.g., 0.12 for 12%).
            Returns None if insufficient data is available.
        
        Example
        -------
        >>> w.change_pct(30)  # % change over last 30 seconds
        0.12
        """
        with self._lock:
            if not self._data or len(self._data) < 2:
                return None
            
            now = time.time()
            cutoff = now - seconds
            
            # Find the oldest point within the time window
            oldest_point = None
            for point in self._data:
                if point.timestamp >= cutoff:
                    oldest_point = point
                    break
            
            if oldest_point is None:
                # No data point within the requested time window
                return None
            
            if self._latest_value is None:
                return None
            
            # If the oldest point is the same as the latest (insufficient time spread)
            if oldest_point.timestamp == self._latest_timestamp:
                return None
            
            # Calculate percentage change
            if oldest_point.value == 0:
                return None
            
            change = (self._latest_value - oldest_point.value) / oldest_point.value
            return change

    def change_abs(self, seconds: float) -> Optional[float]:
        """
        Calculate absolute change over a given time period.

        Parameters
        ----------
        seconds : float
            Time period in seconds to calculate change over.

        Returns
        -------
        float | None
            Absolute change in value units over the period
            (current minus the value ``seconds`` ago).
            Returns None if insufficient data is available.

        Example
        -------
        >>> w.change_abs(30)  # absolute change over last 30 seconds
        120.0
        """
        with self._lock:
            if not self._data or len(self._data) < 2:
                return None

            now = time.time()
            cutoff = now - seconds

            # Find the oldest point within the time window
            oldest_point = None
            for point in self._data:
                if point.timestamp >= cutoff:
                    oldest_point = point
                    break

            if oldest_point is None:
                # No data point within the requested time window
                return None

            if self._latest_value is None or self._latest_timestamp is None:
                return None

            # If the oldest point is the same as the latest (insufficient time spread)
            if oldest_point.timestamp == self._latest_timestamp:
                return None

            return self._latest_value - oldest_point.value
    
    def get_value_at(self, seconds_ago: float) -> Optional[float]:
        """
        Get the value at a specific time in the past.
        
        Parameters
        ----------
        seconds_ago : float
            How many seconds into the past to look.
        
        Returns
        -------
        float | None
            The value at that time, or None if no data point exists.
        """
        with self._lock:
            if not self._data:
                return None
            
            now = time.time()
            target_time = now - seconds_ago
            
            # Find the closest point
            closest = None
            min_diff = float('inf')
            
            for point in self._data:
                diff = abs(point.timestamp - target_time)
                if diff < min_diff:
                    min_diff = diff
                    closest = point
            
            return closest.value if closest else None
    
    def clear(self) -> None:
        """Clear all data from the window."""
        with self._lock:
            self._data.clear()
            self._latest_value = None
            self._latest_timestamp = None
    
    def __len__(self) -> int:
        """Number of data points in the window."""
        with self._lock:
            return len(self._data)
