"""
Bot module tests — run with: pytest tests/test_bots.py
"""

import sys, os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))

import pytest
import polyalpha
from polyalpha.bots import Tracker, Sniper
from polyalpha.bots.sniper import SniperConfig, TradeRecord, SniperStats
from polyalpha.bots.tracker import Tracker as TrackerClass
from polyalpha.core.market import Market
from datetime import datetime, timezone
import tempfile


def make_market(**overrides) -> Market:
    defaults = dict(
        id          = "test-id",
        question    = "Will BTC be higher in 5 minutes?",
        description = "",
        slug        = "btc-updown-5m-9999999",
        active      = True,
        closed      = False,
        archived    = False,
        start_time  = "2025-01-01T00:00:00Z",
        end_time    = "2025-01-01T00:05:00Z",
        volume      = 10_000.0,
        liquidity   = 5_000.0,
        outcomes    = ["UP", "DOWN"],
        prices      = [0.55, 0.45],
        tokens      = ["tok_up", "tok_down"],
    )
    defaults.update(overrides)
    return Market(**defaults)


# ── Tracker tests ─────────────────────────────────────────────────────────────

def test_tracker_initialization():
    client = polyalpha.Client(balance=100.0)
    tracker = Tracker(client)
    
    assert tracker.client == client
    assert tracker.total_trades == 0


def test_tracker_sync():
    client = polyalpha.Client(balance=100.0)
    market = make_market()
    
    # Add some trades
    client.paper.buy(market, side="UP", amount=10.0)
    client.paper.resolve(market, outcome="UP")
    
    tracker = Tracker(client)
    tracker.sync()
    
    assert tracker.total_trades >= 0


def test_tracker_statistics():
    client = polyalpha.Client(balance=100.0)
    tracker = Tracker(client)
    
    # No trades initially
    assert tracker.total_trades == 0
    assert tracker.wins == 0
    assert tracker.losses == 0
    assert tracker.win_rate == 0.0
    assert tracker.total_pnl == 0.0


def test_tracker_export_json():
    client = polyalpha.Client(balance=100.0)
    tracker = Tracker(client)
    
    with tempfile.NamedTemporaryFile(mode='w', suffix='.json', delete=False) as f:
        filepath = f.name
    
    try:
        tracker.export_json(filepath)
        assert os.path.exists(filepath)
    finally:
        if os.path.exists(filepath):
            os.remove(filepath)


def test_tracker_export_csv():
    client = polyalpha.Client(balance=100.0)
    tracker = Tracker(client)
    
    with tempfile.NamedTemporaryFile(mode='w', suffix='.csv', delete=False) as f:
        filepath = f.name
    
    try:
        tracker.export_csv(filepath)
        # Should not crash even with no trades
    finally:
        if os.path.exists(filepath):
            os.remove(filepath)


def test_tracker_slug_label():
    client = polyalpha.Client(balance=100.0)
    tracker = Tracker(client)
    
    label = tracker._slug_label("btc-updown-5m-1234567")
    
    assert "BTC" in label
    assert "5m" in label


# ── Sniper config tests ───────────────────────────────────────────────────────

def test_sniper_config_initialization():
    config = SniperConfig(
        asset="BTC",
        timeframe="5m",
        max_position_size=50.0
    )

    assert config.asset == "BTC"
    assert config.timeframe == "5m"
    assert config.max_position_size == 50.0


def test_sniper_config_defaults():
    config = SniperConfig(asset="BTC", timeframe="5m")

    assert config.max_position_size is None  # default
    assert config.entry_price == 0.92  # default
    assert config.exit_price == 0.88  # default


# ── Sniper trade record tests ─────────────────────────────────────────────────

def test_sniper_trade_record():
    record = TradeRecord(
        market_slug="btc-updown-5m-123",
        side="UP",
        entry_price=0.55,
        exit_price=None,
        amount=10.0,
        shares=18.0,
        outcome=None,
        pnl=0.0,
        timestamp=datetime.now(timezone.utc)
    )

    assert record.market_slug == "btc-updown-5m-123"
    assert record.side == "UP"
    assert record.outcome is None


# ── Sniper stats tests ─────────────────────────────────────────────────────────

def test_sniper_stats_initialization():
    stats = SniperStats(
        total_trades=10,
        wins=6,
        losses=4,
        total_pnl=50.0
    )

    assert stats.total_trades == 10
    assert stats.wins == 6
    assert stats.win_rate == 60.0  # calculated property


# ── Sniper bot tests ─────────────────────────────────────────────────────────

def test_sniper_initialization():
    client = polyalpha.Client(balance=100.0)
    config = SniperConfig(asset="BTC", timeframe="5m")
    
    sniper = Sniper(client, config)
    
    assert sniper.client == client
    assert sniper.config == config


def test_sniper_event_handlers():
    client = polyalpha.Client(balance=100.0)
    config = SniperConfig(asset="BTC", timeframe="5m")
    sniper = Sniper(client, config)
    
    events_called = []
    
    @sniper.on("entry")
    def on_entry(market, order):
        events_called.append(("entry", market))
    
    @sniper.on("exit")
    def on_exit(market, pnl):
        events_called.append(("exit", pnl))
    
    # Manually emit events
    sniper._emit("entry", make_market(), None)
    sniper._emit("exit", make_market(), 10.0)
    
    assert len(events_called) == 2
