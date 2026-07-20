"""
Tests for market session detection and filtering.
"""

from datetime import datetime, time, timezone
import pytest

from polyalpha.core.market_sessions import (
    MarketSession,
    MARKET_SESSIONS,
    SESSION_ALIASES,
    normalize_session_name,
    get_session,
    get_all_sessions,
    is_session_active,
    get_active_sessions,
    validate_session_list,
)


@pytest.mark.unit
class TestMarketSession:
    """Test MarketSession dataclass and methods."""

    def test_session_properties(self):
        """Test session property methods."""
        london = MARKET_SESSIONS["london"]
        assert london.name == "London"
        assert london.start_time == time(7, 0)
        assert london.end_time == time(16, 0)

    def test_session_contains_normal_hours(self):
        """Test session detection for normal hours (no midnight crossing)."""
        london = MARKET_SESSIONS["london"]
        
        # Inside session
        dt_inside = datetime(2024, 1, 1, 10, 0, 0, tzinfo=timezone.utc)
        assert london.contains(dt_inside) is True
        
        # Before session
        dt_before = datetime(2024, 1, 1, 6, 0, 0, tzinfo=timezone.utc)
        assert london.contains(dt_before) is False
        
        # After session
        dt_after = datetime(2024, 1, 1, 17, 0, 0, tzinfo=timezone.utc)
        assert london.contains(dt_after) is False

    def test_session_contains_midnight_crossing(self):
        """Test session detection for sessions that cross midnight."""
        asia = MARKET_SESSIONS["asia"]
        
        # Inside session (before midnight)
        dt_before_midnight = datetime(2024, 1, 1, 23, 30, 0, tzinfo=timezone.utc)
        assert asia.contains(dt_before_midnight) is True
        
        # Inside session (after midnight)
        dt_after_midnight = datetime(2024, 1, 2, 2, 0, 0, tzinfo=timezone.utc)
        assert asia.contains(dt_after_midnight) is True
        
        # Outside session
        dt_outside = datetime(2024, 1, 1, 10, 0, 0, tzinfo=timezone.utc)
        assert asia.contains(dt_outside) is False


@pytest.mark.unit
class TestNormalizeSessionName:
    """Test session name normalization."""

    def test_exact_match(self):
        """Test exact session name match."""
        assert normalize_session_name("london") == "london"
        assert normalize_session_name("new_york") == "new_york"
        assert normalize_session_name("asia") == "asia"
        assert normalize_session_name("sydney") == "sydney"

    def test_case_insensitive(self):
        """Test case-insensitive matching."""
        assert normalize_session_name("LONDON") == "london"
        assert normalize_session_name("New_York") == "new_york"
        assert normalize_session_name("ASIA") == "asia"

    def test_aliases(self):
        """Test session name aliases."""
        assert normalize_session_name("eu") == "london"
        assert normalize_session_name("ny") == "new_york"
        assert normalize_session_name("tokyo") == "asia"
        assert normalize_session_name("pacific") == "sydney"

    def test_invalid_session(self):
        """Test invalid session name raises error."""
        with pytest.raises(ValueError, match="Unknown session"):
            normalize_session_name("invalid")


@pytest.mark.unit
class TestGetSession:
    """Test get_session function."""

    def test_london_session(self):
        """Test London session detection."""
        dt = datetime(2024, 1, 1, 10, 0, 0, tzinfo=timezone.utc)
        assert get_session(dt) == "london"

    def test_new_york_session(self):
        """Test New York session detection."""
        dt = datetime(2024, 1, 1, 17, 0, 0, tzinfo=timezone.utc)
        assert get_session(dt) == "new_york"

    def test_asia_session(self):
        """Test Asia session detection."""
        dt = datetime(2024, 1, 1, 2, 0, 0, tzinfo=timezone.utc)
        assert get_session(dt) == "asia"

    def test_sydney_session(self):
        """Test Sydney session detection."""
        dt = datetime(2024, 1, 1, 22, 30, 0, tzinfo=timezone.utc)
        assert get_session(dt) == "sydney"

    def test_no_session(self):
        """Test session coverage (all times have at least one session)."""
        dt = datetime(2024, 1, 1, 18, 0, 0, tzinfo=timezone.utc)
        assert get_session(dt) == "new_york"

    def test_priority_order(self):
        """Test priority order for overlapping sessions."""
        # London and New York overlap (13:00-16:00 UTC)
        # London should have priority
        dt = datetime(2024, 1, 1, 14, 0, 0, tzinfo=timezone.utc)
        assert get_session(dt) == "london"


@pytest.mark.unit
class TestGetAllSessions:
    """Test get_all_sessions function."""

    def test_single_session(self):
        """Test time in single session."""
        dt = datetime(2024, 1, 1, 10, 0, 0, tzinfo=timezone.utc)
        sessions = get_all_sessions(dt)
        assert sessions == ["london"]

    def test_overlapping_sessions(self):
        """Test time in overlapping sessions."""
        # London and New York overlap
        dt = datetime(2024, 1, 1, 14, 0, 0, tzinfo=timezone.utc)
        sessions = get_all_sessions(dt)
        assert "london" in sessions
        assert "new_york" in sessions

    def test_no_session(self):
        """Test time that falls only in New York session."""
        dt = datetime(2024, 1, 1, 18, 0, 0, tzinfo=timezone.utc)
        sessions = get_all_sessions(dt)
        assert sessions == ["new_york"]


@pytest.mark.unit
class TestIsSessionActive:
    """Test is_session_active function."""

    def test_active_session(self):
        """Test when session is active."""
        dt = datetime(2024, 1, 1, 10, 0, 0, tzinfo=timezone.utc)
        assert is_session_active("london", dt) is True

    def test_inactive_session(self):
        """Test when session is inactive."""
        dt = datetime(2024, 1, 1, 10, 0, 0, tzinfo=timezone.utc)
        assert is_session_active("asia", dt) is False

    def test_current_time(self):
        """Test with current time (no datetime provided)."""
        # Just test that it doesn't raise an error
        result = is_session_active("london")
        assert isinstance(result, bool)


@pytest.mark.unit
class TestGetActiveSessions:
    """Test get_active_sessions function."""

    def test_get_active_sessions(self):
        """Test getting all active sessions."""
        dt = datetime(2024, 1, 1, 14, 0, 0, tzinfo=timezone.utc)
        sessions = get_active_sessions(dt)
        assert isinstance(sessions, list)
        assert "london" in sessions
        assert "new_york" in sessions

    def test_current_time(self):
        """Test with current time (no datetime provided)."""
        # Just test that it doesn't raise an error
        sessions = get_active_sessions()
        assert isinstance(sessions, list)


@pytest.mark.unit
class TestValidateSessionList:
    """Test validate_session_list function."""

    def test_valid_sessions(self):
        """Test valid session list."""
        sessions = validate_session_list(["london", "new_york"])
        assert set(sessions) == {"london", "new_york"}

    def test_with_aliases(self):
        """Test session list with aliases."""
        sessions = validate_session_list(["lon", "ny", "tokyo"])
        assert set(sessions) == {"london", "new_york", "asia"}

    def test_remove_duplicates(self):
        """Test duplicate removal."""
        sessions = validate_session_list(["london", "london", "new_york"])
        assert sessions == ["london", "new_york"] or sessions == ["new_york", "london"]

    def test_invalid_session(self):
        """Test invalid session in list."""
        with pytest.raises(ValueError, match="Unknown session"):
            validate_session_list(["london", "invalid"])

    def test_empty_list(self):
        """Test empty list."""
        sessions = validate_session_list([])
        assert sessions == []


@pytest.mark.unit
class TestSessionDefinitions:
    """Test session definitions are correct."""

    def test_london_definition(self):
        """Test London session definition."""
        london = MARKET_SESSIONS["london"]
        assert london.name == "London"
        assert london.start_hour == 7
        assert london.start_minute == 0
        assert london.end_hour == 16
        assert london.end_minute == 0

    def test_new_york_definition(self):
        """Test New York session definition."""
        ny = MARKET_SESSIONS["new_york"]
        assert ny.name == "New York"
        assert ny.start_hour == 13
        assert ny.start_minute == 0
        assert ny.end_hour == 22
        assert ny.end_minute == 0

    def test_asia_definition(self):
        """Test Asia session definition."""
        asia = MARKET_SESSIONS["asia"]
        assert asia.name == "Asia"
        assert asia.start_hour == 23
        assert asia.start_minute == 0
        assert asia.end_hour == 8
        assert asia.end_minute == 0

    def test_sydney_definition(self):
        """Test Sydney session definition."""
        sydney = MARKET_SESSIONS["sydney"]
        assert sydney.name == "Sydney"
        assert sydney.start_hour == 21
        assert sydney.start_minute == 0
        assert sydney.end_hour == 6
        assert sydney.end_minute == 0

    def test_all_sessions_covered(self):
        """Test all expected sessions are defined."""
        expected = {"london", "new_york", "asia", "sydney"}
        assert set(MARKET_SESSIONS.keys()) == expected


@pytest.mark.unit
class TestSessionAliases:
    """Test session aliases are correct."""

    def test_london_aliases(self):
        """Test London session aliases."""
        assert SESSION_ALIASES["london"] == ["london", "european", "eu", "lon"]

    def test_new_york_aliases(self):
        """Test New York session aliases."""
        assert SESSION_ALIASES["new_york"] == ["new_york", "ny", "us", "america", "nyc"]

    def test_asia_aliases(self):
        """Test Asia session aliases."""
        assert SESSION_ALIASES["asia"] == ["asia", "tokyo", "asian", "jp", "japan"]

    def test_sydney_aliases(self):
        """Test Sydney session aliases."""
        assert SESSION_ALIASES["sydney"] == ["sydney", "pacific", "australia", "aus", "syd"]
