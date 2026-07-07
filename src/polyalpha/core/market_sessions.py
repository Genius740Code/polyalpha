"""
Market session definitions and detection.

This module provides utilities for detecting which trading session a given
timestamp falls into, and filtering trades by market session.

Supported sessions:
- London (European session)
- New York (US session)
- Asia (Tokyo/Asian session)
- Sydney (Pacific session)

All times are in UTC.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, time, timezone
from typing import Optional


@dataclass
class MarketSession:
    """
    Definition of a trading session.
    
    Attributes
    ----------
    name : str
        Session name (e.g., "London", "New York").
    start_hour : int
        Session start hour in UTC (0-23).
    start_minute : int
        Session start minute in UTC (0-59).
    end_hour : int
        Session end hour in UTC (0-23).
    end_minute : int
        Session end minute in UTC (0-59).
    description : str
        Human-readable description of the session.
    """
    name: str
    start_hour: int
    start_minute: int
    end_hour: int
    end_minute: int
    description: str
    
    @property
    def start_time(self) -> time:
        """Session start time as time object."""
        return time(self.start_hour, self.start_minute)
    
    @property
    def end_time(self) -> time:
        """Session end time as time object."""
        return time(self.end_hour, self.end_minute)
    
    def contains(self, dt: datetime) -> bool:
        """
        Check if a datetime falls within this session.
        
        Parameters
        ----------
        dt : datetime
            Datetime to check (should be timezone-aware, preferably UTC).
        
        Returns
        -------
        bool
            True if the datetime falls within this session.
        """
        # Convert to UTC if not already
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        else:
            dt = dt.astimezone(timezone.utc)
        
        # Get time component
        t = dt.time()
        
        # Handle sessions that cross midnight
        if self.start_time <= self.end_time:
            # Normal session (e.g., 8:00 - 17:00)
            return self.start_time <= t <= self.end_time
        else:
            # Session crosses midnight (e.g., 22:00 - 6:00)
            return t >= self.start_time or t <= self.end_time


# Define market sessions
# Times are in UTC
MARKET_SESSIONS = {
    "london": MarketSession(
        name="London",
        start_hour=7,
        start_minute=0,
        end_hour=16,
        end_minute=0,
        description="European/London trading session (07:00-16:00 UTC)"
    ),
    "new_york": MarketSession(
        name="New York",
        start_hour=13,
        start_minute=0,
        end_hour=22,
        end_minute=0,
        description="US/New York trading session (13:00-22:00 UTC)"
    ),
    "asia": MarketSession(
        name="Asia",
        start_hour=23,
        start_minute=0,
        end_hour=8,
        end_minute=0,
        description="Asian/Tokyo trading session (23:00-08:00 UTC)"
    ),
    "sydney": MarketSession(
        name="Sydney",
        start_hour=21,
        start_minute=0,
        end_hour=6,
        end_minute=0,
        description="Pacific/Sydney trading session (21:00-06:00 UTC)"
    ),
}

SESSION_ALIASES = {
    "london": ["london", "european", "eu", "lon"],
    "new_york": ["new_york", "ny", "us", "america", "nyc"],
    "asia": ["asia", "tokyo", "asian", "jp", "japan"],
    "sydney": ["sydney", "pacific", "australia", "aus", "syd"],
}


def normalize_session_name(session: str) -> str:
    """
    Normalize a session name to its canonical form.
    
    Parameters
    ----------
    session : str
        Session name or alias.
    
    Returns
    -------
    str
        Canonical session name (e.g., "london", "new_york", "asia", "sydney").
    
    Raises
    ------
    ValueError
        If the session name is not recognized.
    """
    session_lower = session.lower().strip()
    
    # Check exact matches first
    if session_lower in MARKET_SESSIONS:
        return session_lower
    
    # Check aliases
    for canonical, aliases in SESSION_ALIASES.items():
        if session_lower in aliases:
            return canonical
    
    raise ValueError(
        f"Unknown session '{session}'. "
        f"Supported sessions: {list(MARKET_SESSIONS.keys())}"
    )


def get_session(dt: datetime) -> Optional[str]:
    """
    Determine which market session a datetime falls into.
    
    If the datetime falls into multiple overlapping sessions (e.g., London
    and New York overlap), returns the first matching session in priority order:
    London > New York > Asia > Sydney.
    
    Parameters
    ----------
    dt : datetime
        Datetime to check (should be timezone-aware, preferably UTC).
    
    Returns
    -------
    str or None
        Session name if the datetime falls within a session, None otherwise.
    """
    # Priority order for overlapping sessions
    priority_order = ["london", "new_york", "asia", "sydney"]
    
    for session_name in priority_order:
        session = MARKET_SESSIONS[session_name]
        if session.contains(dt):
            return session_name
    
    return None


def get_all_sessions(dt: datetime) -> list[str]:
    """
    Get all market sessions a datetime falls into.
    
    Parameters
    ----------
    dt : datetime
        Datetime to check (should be timezone-aware, preferably UTC).
    
    Returns
    -------
    list of str
        List of session names the datetime falls into.
    """
    sessions = []
    for session_name, session in MARKET_SESSIONS.items():
        if session.contains(dt):
            sessions.append(session_name)
    return sessions


def is_session_active(session: str, dt: Optional[datetime] = None) -> bool:
    """
    Check if a specific market session is currently active.
    
    Parameters
    ----------
    session : str
        Session name or alias.
    dt : datetime, optional
        Datetime to check. If None, uses current time.
    
    Returns
    -------
    bool
        True if the session is active at the given time.
    """
    if dt is None:
        dt = datetime.now(timezone.utc)
    
    canonical_name = normalize_session_name(session)
    market_session = MARKET_SESSIONS[canonical_name]
    return market_session.contains(dt)


def get_active_sessions(dt: Optional[datetime] = None) -> list[str]:
    """
    Get all currently active market sessions.
    
    Parameters
    ----------
    dt : datetime, optional
        Datetime to check. If None, uses current time.
    
    Returns
    -------
    list of str
        List of active session names.
    """
    if dt is None:
        dt = datetime.now(timezone.utc)
    
    return get_all_sessions(dt)


def validate_session_list(sessions: list[str]) -> list[str]:
    """
    Validate and normalize a list of session names.
    
    Parameters
    ----------
    sessions : list of str
        List of session names or aliases.
    
    Returns
    -------
    list of str
        List of canonical session names.
    
    Raises
    ------
    ValueError
        If any session name is not recognized.
    """
    normalized = []
    for session in sessions:
        normalized.append(normalize_session_name(session))
    return list(set(normalized))  # Remove duplicates
