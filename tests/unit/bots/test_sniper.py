"""
Sniper bot tests — run with: pytest tests/unit/bots/test_sniper.py
"""

import pytest
import polyalpha
from polyalpha.bots import Sniper
from polyalpha.bots.sniper import SniperConfig, TradeRecord, SniperStats
from datetime import datetime, timezone


@pytest.mark.unit
def test_sniper_config_initialization():
    config = SniperConfig(
        asset="BTC",
        timeframe="5m",
        max_position_size=50.0
    )

    assert config.asset == "BTC"
    assert config.timeframe == "5m"
    assert config.max_position_size == 50.0


@pytest.mark.unit
def test_sniper_config_defaults():
    config = SniperConfig(asset="BTC", timeframe="5m")

    assert config.max_position_size is None
    assert config.entry_price == 0.92
    assert config.exit_price == 0.88


@pytest.mark.unit
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


@pytest.mark.unit
def test_sniper_stats_initialization():
    stats = SniperStats(
        total_trades=10,
        wins=6,
        losses=4,
        total_pnl=50.0
    )

    assert stats.total_trades == 10
    assert stats.wins == 6
    assert stats.win_rate == 60.0


@pytest.mark.unit
def test_sniper_initialization():
    client = polyalpha.Client(balance=100.0)
    config = SniperConfig(asset="BTC", timeframe="5m")

    sniper = Sniper(client, config)

    assert sniper.client == client
    assert sniper.config == config


@pytest.mark.unit
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

    sniper._emit("entry", _make_market(), None)
    sniper._emit("exit", _make_market(), 10.0)

    assert len(events_called) == 2


def _make_market(**overrides):
    from polyalpha.core.market import Market
    from datetime import datetime, timedelta, timezone
    now = datetime.now(timezone.utc)
    future_start = now + timedelta(minutes=5)
    future_end = now + timedelta(minutes=10)
    defaults = dict(
        id="test-id",
        question="Test question",
        description="",
        slug="btc-updown-5m-9999999",
        active=True,
        closed=False,
        archived=False,
        start_time=future_start.strftime("%Y-%m-%dT%H:%M:%SZ"),
        end_time=future_end.strftime("%Y-%m-%dT%H:%M:%SZ"),
        volume=10_000.0,
        liquidity=5_000.0,
        outcomes=["UP", "DOWN"],
        prices=[0.55, 0.45],
        tokens=["tok_up", "tok_down"],
    )
    defaults.update(overrides)
    return Market(**defaults)
