"""
Tests for auto-redeem functionality.
"""

import pytest
from datetime import datetime, timezone, timedelta
from polyalpha import Client, AutoRedeemConfig

pytestmark = pytest.mark.unit
from polyalpha.trading.auto_redeem import (
    AutoRedeemEngine,
    RedeemablePosition,
    RedeemRecord,
    RedeemResult,
)


# ── Fixtures ───────────────────────────────────────────────────────────────────

@pytest.fixture
def paper_client():
    """Create a paper trading client for testing."""
    return Client(balance=1000.0)


@pytest.fixture
def auto_redeem_config():
    """Create a basic auto-redeem configuration."""
    return AutoRedeemConfig(
        time_interval="1d",
        min_value_usd=100.0,
        dry_run=True,
    )


@pytest.fixture
def auto_redeem_engine(paper_client, auto_redeem_config):
    """Create an auto-redeem engine for testing."""
    return AutoRedeemEngine(paper_client.paper, auto_redeem_config)


@pytest.fixture
def sample_redeemable_positions():
    """Create sample redeemable positions for testing."""
    now = datetime.now(timezone.utc)
    return [
        RedeemablePosition(
            market_id="market1",
            slug="btc-updown-5m-123",
            side="UP",
            shares=10.0,
            outcome="WON",
            value_usd=150.0,
            resolved_at=now - timedelta(hours=2),
            token_id="token1",
        ),
        RedeemablePosition(
            market_id="market2",
            slug="eth-updown-15m-456",
            side="DOWN",
            shares=5.0,
            outcome="WON",
            value_usd=75.0,
            resolved_at=now - timedelta(hours=3),
            token_id="token2",
        ),
        RedeemablePosition(
            market_id="market3",
            slug="sol-updown-1h-789",
            side="UP",
            shares=20.0,
            outcome="LOST",
            value_usd=0.0,
            resolved_at=now - timedelta(hours=1),
            token_id="token3",
        ),
    ]


# ── AutoRedeemConfig Tests ────────────────────────────────────────────────────

def test_auto_redeem_config_defaults():
    """Test that AutoRedeemConfig has correct defaults."""
    config = AutoRedeemConfig()
    
    assert config.enabled is True
    assert config.trigger_on_time is True
    assert config.trigger_on_count is True
    assert config.trigger_on_value is False
    assert config.time_interval == "1d"
    assert config.min_markets == 10
    assert config.max_markets == 100
    assert config.min_value_usd == 100.0
    assert config.max_value_usd == 10000.0
    assert config.require_confirmation is False
    assert config.dry_run is False
    assert config.only_winning is False
    assert config.min_age_hours == 1


def test_auto_redeem_config_custom():
    """Test custom AutoRedeemConfig values."""
    config = AutoRedeemConfig(
        enabled=False,
        time_interval="6h",
        min_markets=5,
        max_markets=50,
        min_value_usd=50.0,
        max_value_usd=500.0,
        require_confirmation=True,
        dry_run=True,
        only_winning=True,
        min_age_hours=2,
    )
    
    assert config.enabled is False
    assert config.time_interval == "6h"
    assert config.min_markets == 5
    assert config.max_markets == 50
    assert config.min_value_usd == 50.0
    assert config.max_value_usd == 500.0
    assert config.require_confirmation is True
    assert config.dry_run is True
    assert config.only_winning is True
    assert config.min_age_hours == 2


# ── AutoRedeemEngine Tests ───────────────────────────────────────────────────

def test_auto_redeem_engine_initialization(auto_redeem_engine):
    """Test AutoRedeemEngine initialization."""
    assert auto_redeem_engine is not None
    assert auto_redeem_engine._config is not None
    assert auto_redeem_engine.get_pending_count() == 0
    assert len(auto_redeem_engine.get_redeem_history()) == 0
    assert auto_redeem_engine.is_running() is False


def test_check_positions_empty(auto_redeem_engine):
    """Test check_positions with no positions."""
    positions = auto_redeem_engine.check_positions()
    assert positions == []


def test_check_positions_disabled(auto_redeem_engine):
    """Test check_positions when disabled."""
    auto_redeem_engine._config.enabled = False
    positions = auto_redeem_engine.check_positions()
    assert positions == []


def test_parse_time_interval(auto_redeem_engine):
    """Test time interval parsing."""
    # Test hours
    assert auto_redeem_engine._parse_time_interval() == 86400  # Default 1d
    
    # Test custom intervals
    auto_redeem_engine._config.time_interval = "1h"
    assert auto_redeem_engine._parse_time_interval() == 3600
    
    auto_redeem_engine._config.time_interval = "6h"
    assert auto_redeem_engine._parse_time_interval() == 21600
    
    auto_redeem_engine._config.time_interval = "1d"
    assert auto_redeem_engine._parse_time_interval() == 86400
    
    auto_redeem_engine._config.time_interval = "1w"
    assert auto_redeem_engine._parse_time_interval() == 604800


def test_check_triggers_count_min(auto_redeem_engine, sample_redeemable_positions):
    """Test count-based trigger (minimum)."""
    auto_redeem_engine._config.trigger_on_count = True
    auto_redeem_engine._config.min_markets = 2
    
    should_redeem, reason = auto_redeem_engine._check_triggers(sample_redeemable_positions)
    assert should_redeem is True
    assert "count_min" in reason


def test_check_triggers_count_max(auto_redeem_engine, sample_redeemable_positions):
    """Test count-based trigger (maximum)."""
    auto_redeem_engine._config.trigger_on_count = True
    auto_redeem_engine._config.max_markets = 2
    
    should_redeem, reason = auto_redeem_engine._check_triggers(sample_redeemable_positions)
    assert should_redeem is True
    assert "count_max" in reason


def test_check_triggers_value_min(auto_redeem_engine, sample_redeemable_positions):
    """Test value-based trigger (minimum)."""
    auto_redeem_engine._config.trigger_on_value = True
    auto_redeem_engine._config.min_value_usd = 200.0
    
    should_redeem, reason = auto_redeem_engine._check_triggers(sample_redeemable_positions)
    assert should_redeem is True
    assert "value_min" in reason


def test_check_triggers_value_max(auto_redeem_engine, sample_redeemable_positions):
    """Test value-based trigger (maximum)."""
    auto_redeem_engine._config.trigger_on_value = True
    auto_redeem_engine._config.max_value_usd = 200.0
    
    should_redeem, reason = auto_redeem_engine._check_triggers(sample_redeemable_positions)
    assert should_redeem is True
    assert "value_max" in reason


def test_check_triggers_no_positions(auto_redeem_engine):
    """Test trigger check with no positions."""
    should_redeem, reason = auto_redeem_engine._check_triggers([])
    assert should_redeem is False
    assert "no_positions" in reason


def test_check_triggers_not_met(auto_redeem_engine, sample_redeemable_positions):
    """Test trigger check when triggers not met."""
    auto_redeem_engine._config.trigger_on_count = True
    auto_redeem_engine._config.min_markets = 100  # Too high
    
    should_redeem, reason = auto_redeem_engine._check_triggers(sample_redeemable_positions)
    assert should_redeem is False


def test_redeem_dry_run(auto_redeem_engine, sample_redeemable_positions):
    """Test redemption in dry run mode."""
    auto_redeem_engine._config.dry_run = True
    
    result = auto_redeem_engine.redeem(sample_redeemable_positions, force=True)
    
    assert result.success is True
    assert result.redeemed_count == len(sample_redeemable_positions)
    assert result.failed_count == 0
    assert result.total_value_usd == 225.0  # 150 + 75 + 0


def test_redeem_history(auto_redeem_engine, sample_redeemable_positions):
    """Test redemption history tracking."""
    auto_redeem_engine._config.dry_run = True
    
    # First redemption
    auto_redeem_engine.redeem(sample_redeemable_positions, force=True)
    history = auto_redeem_engine.get_redeem_history()
    assert len(history) == 1
    
    # Second redemption
    auto_redeem_engine.redeem(sample_redeemable_positions, force=True)
    history = auto_redeem_engine.get_redeem_history()
    assert len(history) == 2
    
    # Check record details
    record = history[0]
    assert isinstance(record, RedeemRecord)
    assert record.positions_count == len(sample_redeemable_positions)
    assert record.total_value_usd == 225.0
    assert record.success is True


def test_clear_history(auto_redeem_engine, sample_redeemable_positions):
    """Test clearing redemption history."""
    auto_redeem_engine._config.dry_run = True
    
    auto_redeem_engine.redeem(sample_redeemable_positions, force=True)
    assert len(auto_redeem_engine.get_redeem_history()) == 1
    
    auto_redeem_engine.clear_history()
    assert len(auto_redeem_engine.get_redeem_history()) == 0


def test_scheduler_start_stop(auto_redeem_engine):
    """Test scheduler start and stop."""
    assert auto_redeem_engine.is_running() is False
    
    auto_redeem_engine.start_scheduler()
    assert auto_redeem_engine.is_running() is True
    
    auto_redeem_engine.stop_scheduler()
    assert auto_redeem_engine.is_running() is False


def test_scheduler_already_running(auto_redeem_engine):
    """Test starting scheduler when already running."""
    auto_redeem_engine.start_scheduler()
    assert auto_redeem_engine.is_running() is True
    
    # Should not raise error
    auto_redeem_engine.start_scheduler()
    assert auto_redeem_engine.is_running() is True
    
    auto_redeem_engine.stop_scheduler()


def test_scheduler_time_trigger_disabled(auto_redeem_engine):
    """Test scheduler when time trigger is disabled."""
    auto_redeem_engine._config.trigger_on_time = False
    
    auto_redeem_engine.start_scheduler()
    assert auto_redeem_engine.is_running() is False  # Should not start


def test_pending_count(auto_redeem_engine):
    """Test pending count tracking."""
    assert auto_redeem_engine.get_pending_count() == 0
    
    # Simulate adding to queue
    auto_redeem_engine._resolved_queue.add("market1:UP")
    auto_redeem_engine._resolved_queue.add("market2:DOWN")
    
    assert auto_redeem_engine.get_pending_count() == 2


# ── Integration Tests ────────────────────────────────────────────────────────

def test_paper_client_auto_redeem_property(paper_client):
    """Test that paper client has auto_redeem property."""
    assert hasattr(paper_client.paper, 'auto_redeem')
    assert paper_client.paper.auto_redeem is not None


def test_paper_client_set_auto_redeem_config(paper_client):
    """Test setting custom auto-redeem config on paper client."""
    config = AutoRedeemConfig(
        time_interval="6h",
        min_value_usd=50.0,
    )
    
    paper_client.paper.set_auto_redeem_config(config)
    
    assert paper_client.paper.auto_redeem._config is config
    assert paper_client.paper.auto_redeem._config.time_interval == "6h"
    assert paper_client.paper.auto_redeem._config.min_value_usd == 50.0


def test_auto_redeem_with_only_winning_filter(auto_redeem_engine, sample_redeemable_positions):
    """Test only_winning filter."""
    auto_redeem_engine._config.only_winning = True
    auto_redeem_engine._config.dry_run = True
    
    # This would filter out the losing position in a real scenario
    # For now, just test the config is set
    assert auto_redeem_engine._config.only_winning is True


def test_auto_redeem_with_min_age_filter(auto_redeem_engine):
    """Test minimum age filter."""
    auto_redeem_engine._config.min_age_hours = 3
    auto_redeem_engine._config.dry_run = True
    
    # This would filter out positions younger than 3 hours
    # For now, just test the config is set
    assert auto_redeem_engine._config.min_age_hours == 3


# ── Data Structure Tests ─────────────────────────────────────────────────────

def test_redeemable_position():
    """Test RedeemablePosition dataclass."""
    now = datetime.now(timezone.utc)
    pos = RedeemablePosition(
        market_id="test",
        slug="test-slug",
        side="UP",
        shares=10.0,
        outcome="WON",
        value_usd=100.0,
        resolved_at=now,
        token_id="token",
    )
    
    assert pos.market_id == "test"
    assert pos.slug == "test-slug"
    assert pos.side == "UP"
    assert pos.shares == 10.0
    assert pos.outcome == "WON"
    assert pos.value_usd == 100.0
    assert pos.resolved_at == now
    assert pos.token_id == "token"


def test_redeem_record():
    """Test RedeemRecord dataclass."""
    now = datetime.now(timezone.utc)
    record = RedeemRecord(
        timestamp=now,
        positions_count=5,
        total_value_usd=500.0,
        trigger_reason="count_min",
        success=True,
    )
    
    assert record.timestamp == now
    assert record.positions_count == 5
    assert record.total_value_usd == 500.0
    assert record.trigger_reason == "count_min"
    assert record.success is True
    assert record.tx_hash is None
    assert record.error is None


def test_redeem_result():
    """Test RedeemResult dataclass."""
    result = RedeemResult(
        success=True,
        redeemed_count=3,
        total_value_usd=300.0,
        failed_count=0,
    )
    
    assert result.success is True
    assert result.redeemed_count == 3
    assert result.total_value_usd == 300.0
    assert result.failed_count == 0
    assert result.errors == []
    assert result.tx_hash is None


def test_redeem_result_with_errors():
    """Test RedeemResult with errors."""
    result = RedeemResult(
        success=False,
        redeemed_count=1,
        total_value_usd=100.0,
        failed_count=2,
        errors=["Error 1", "Error 2"],
        tx_hash="0x123",
    )
    
    assert result.success is False
    assert result.redeemed_count == 1
    assert result.failed_count == 2
    assert len(result.errors) == 2
    assert result.tx_hash == "0x123"


# ── Edge Cases ───────────────────────────────────────────────────────────────

def test_redeem_with_empty_positions(auto_redeem_engine):
    """Test redeeming with empty positions list."""
    result = auto_redeem_engine.redeem([])
    
    assert result.success is True
    assert result.redeemed_count == 0
    assert result.total_value_usd == 0.0


def test_redeem_with_none_positions(auto_redeem_engine):
    """Test redeeming with None positions (should trigger check_positions)."""
    result = auto_redeem_engine.redeem(None)
    
    # Should call check_positions and return no positions
    assert result.success is True
    assert result.redeemed_count == 0


def test_invalid_time_interval(auto_redeem_engine):
    """Test handling of invalid time interval."""
    auto_redeem_engine._config.time_interval = "invalid"
    
    with pytest.raises(ValueError):
        auto_redeem_engine._parse_time_interval()


def test_zero_min_markets(auto_redeem_engine, sample_redeemable_positions):
    """Test with zero min_markets threshold."""
    auto_redeem_engine._config.trigger_on_count = True
    auto_redeem_engine._config.min_markets = 0
    
    should_redeem, reason = auto_redeem_engine._check_triggers(sample_redeemable_positions)
    assert should_redeem is True


def test_zero_min_value(auto_redeem_engine, sample_redeemable_positions):
    """Test with zero min_value_usd threshold."""
    auto_redeem_engine._config.trigger_on_value = True
    auto_redeem_engine._config.min_value_usd = 0.0
    
    should_redeem, reason = auto_redeem_engine._check_triggers(sample_redeemable_positions)
    assert should_redeem is True
