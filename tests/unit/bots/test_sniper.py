"""
Sniper bot tests — run with: pytest tests/unit/bots/test_sniper.py
"""

from unittest.mock import MagicMock
from datetime import datetime, timezone

import polyalpha
import pytest

from polyalpha.bots import Sniper
from polyalpha.bots.sniper import SniperConfig, TradeRecord, SniperStats, TimeWindow, ConditionalWindow, TimeFilter


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
def test_sniper_config_requires_timeframe():
    """timeframe must be explicitly provided — no silent 5m default."""
    with pytest.raises(TypeError):
        SniperConfig(asset="BTC")

    with pytest.raises(TypeError):
        SniperConfig()


@pytest.mark.unit
def test_sniper_config_buy_once_per_market_default():
    """buy_once_per_market defaults to True (one buy per market)."""
    config = SniperConfig(asset="BTC", timeframe="5m")
    assert config.buy_once_per_market is True


@pytest.mark.unit
def test_sniper_config_buy_once_per_market_override():
    """buy_once_per_market can be disabled for multiple buys per market."""
    config = SniperConfig(asset="BTC", timeframe="5m", buy_once_per_market=False)
    assert config.buy_once_per_market is False


def _make_sniper_armed(buy_once_per_market=True):
    """Build an ARMED sniper with a fake stream + mocked paper engine."""
    from unittest.mock import MagicMock
    client = polyalpha.Client(balance=100.0)
    config = SniperConfig(
        asset="BTC", timeframe="5m", buy_once_per_market=buy_once_per_market,
    )
    sniper = Sniper(client, config)
    sniper._market = _make_market()
    sniper._stream = MagicMock(up=0.95, down=0.45, running=True)
    sniper._set_state(sniper.STATE_ARMED)
    order = MagicMock(side="UP", price=0.95, amount=20.0, id="order-1")
    order.status = "pending"
    client.paper.limit = MagicMock(return_value=order)
    return sniper


@pytest.mark.unit
def test_sniper_buy_once_per_market_blocks_second_entry():
    """Default (True): no second order once the market has a fill."""
    sniper = _make_sniper_armed(buy_once_per_market=True)
    sniper._filled_order = object()  # already filled this market
    sniper._on_price_update(0.95, 0.45)
    assert sniper._pending_order is None


@pytest.mark.unit
def test_sniper_buy_once_per_market_false_allows_reentry():
    """False: another order can be placed after a fill."""
    sniper = _make_sniper_armed(buy_once_per_market=False)
    sniper._filled_order = object()  # already filled this market
    sniper._on_price_update(0.95, 0.45)
    assert sniper._pending_order is not None


# ── Staleness Guard Tests ───────────────────────────────────────────────────

def _make_stale_stream(age_seconds):
    """A fake stream whose price is ``age_seconds`` seconds old."""
    from unittest.mock import MagicMock
    stream = MagicMock(up=0.95, down=0.45, running=True)
    stream.price_age_seconds = MagicMock(return_value=age_seconds)
    return stream


@pytest.mark.unit
def test_sniper_config_stale_data_max_age_default():
    """stale_data_max_age defaults to 5.0 seconds."""
    config = SniperConfig(asset="BTC", timeframe="5m")
    assert config.stale_data_max_age == 5.0


@pytest.mark.unit
def test_sniper_config_stale_data_max_age_validation():
    """stale_data_max_age must be positive."""
    with pytest.raises(ValueError, match="stale_data_max_age must be positive"):
        SniperConfig(asset="BTC", timeframe="5m", stale_data_max_age=0)
    with pytest.raises(ValueError, match="stale_data_max_age must be positive"):
        SniperConfig(asset="BTC", timeframe="5m", stale_data_max_age=-1)


@pytest.mark.unit
def test_sniper_entry_skipped_when_price_frozen_past_threshold():
    """Frozen price (older than threshold) → no order is placed."""
    sniper = _make_sniper_armed()
    sniper._stream = _make_stale_stream(age_seconds=90.0)
    sniper._on_price_update(0.95, 0.45)
    assert sniper._pending_order is None


@pytest.mark.unit
def test_sniper_entry_allowed_when_price_fresh():
    """Fresh price (within threshold) → order is placed."""
    sniper = _make_sniper_armed()
    sniper._stream = _make_stale_stream(age_seconds=0.5)
    sniper._on_price_update(0.95, 0.45)
    assert sniper._pending_order is not None


@pytest.mark.unit
def test_sniper_place_order_skips_stale():
    """_place_order refuses to fill on a stale price."""
    sniper = _make_sniper_armed()
    sniper._stream = _make_stale_stream(age_seconds=90.0)
    sniper._place_order()
    assert sniper._pending_order is None


@pytest.mark.unit
def test_sniper_place_order_blocked_without_stream():
    """No live stream → treated as stale, no order placed."""
    sniper = _make_sniper_armed()
    sniper._stream = None
    sniper._place_order()
    assert sniper._pending_order is None


# ── External Hub Feed (issue #2) ────────────────────────────────────────────

@pytest.mark.unit
def test_sniper_setup_uses_injected_feed(monkeypatch):
    """A Sniper given an external feed must NOT open its own WebSocket."""
    import polyalpha.bots.sniper as sniper_mod
    from polyalpha.bots import HubFeed
    monkeypatch.setattr(sniper_mod, "STREAM_SETUP_DELAY", 0)
    sniper = _make_sniper_armed()
    feed = HubFeed(market=sniper._market, up=0.95, down=0.45)
    sniper._injected_stream = feed

    sniper.client.stream = MagicMock(side_effect=AssertionError("must not open own stream"))
    sniper._setup_stream()

    assert sniper._stream is feed
    sniper.client.stream.assert_not_called()


@pytest.mark.unit
def test_sniper_cleanup_keeps_injected_feed_running():
    """The Sniper must not stop a feed it does not own (shared hub feed)."""
    from polyalpha.bots import HubFeed
    sniper = _make_sniper_armed()
    feed = HubFeed(market=sniper._market, up=0.95, down=0.45)
    feed.start()
    sniper._injected_stream = feed
    sniper._stream = feed

    sniper._cleanup_stream()

    assert feed.running is True


@pytest.mark.unit
def test_sniper_cleanup_stops_native_stream():
    """A stream the Sniper opened itself must still be stopped on cleanup."""
    sniper = _make_sniper_armed()
    native = MagicMock()
    sniper._stream = native
    sniper._injected_stream = None

    sniper._cleanup_stream()

    native.stop.assert_called_once_with()


@pytest.mark.unit
def test_sniper_injected_feed_fresh_price_places_order(monkeypatch):
    """Pushing a fresh price into an injected HubFeed triggers entry."""
    import polyalpha.bots.sniper as sniper_mod
    from polyalpha.bots import HubFeed
    monkeypatch.setattr(sniper_mod, "STREAM_SETUP_DELAY", 0)
    sniper = _make_sniper_armed()
    feed = HubFeed(market=sniper._market, up=0.95, down=0.45)
    sniper._injected_stream = feed
    sniper._setup_stream()

    feed.push(0.95, 0.45)  # emits a fresh 'price' event → sniper entry

    assert sniper._pending_order is not None


@pytest.mark.unit
def test_sniper_injected_feed_stale_price_skips(monkeypatch):
    """A frozen external feed (no push) must trip the staleness guard."""
    import polyalpha.bots.sniper as sniper_mod
    from polyalpha.bots import HubFeed
    monkeypatch.setattr(sniper_mod, "STREAM_SETUP_DELAY", 0)
    sniper = _make_sniper_armed()
    feed = HubFeed(market=sniper._market, up=0.95, down=0.45)
    feed._last_price_time = 0.0  # pretend it went quiet long ago
    sniper._injected_stream = feed
    sniper._setup_stream()

    sniper._on_price_update(0.95, 0.45)

    assert sniper._pending_order is None


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


# ── Time Window Tests ───────────────────────────────────────────────────────

@pytest.mark.unit
def test_time_window_offset():
    """Test offset-based time window."""
    window = TimeWindow(start_offset=-120, end_offset=-60)
    assert window.start_offset == -120
    assert window.end_offset == -60


@pytest.mark.unit
def test_time_window_absolute():
    """Test absolute time window."""
    window = TimeWindow(start_time="01:00", end_time="02:00")
    assert window.start_time == "01:00"
    assert window.end_time == "02:00"


@pytest.mark.unit
def test_time_window_burst():
    """Test burst pattern time window."""
    window = TimeWindow(burst_on=10, burst_off=20)
    assert window.burst_on == 10
    assert window.burst_off == 20


@pytest.mark.unit
def test_time_window_validation_offset_order():
    """Test that offset windows validate start < end."""
    with pytest.raises(ValueError, match="start_offset.*must be less than end_offset"):
        TimeWindow(start_offset=-60, end_offset=-120)


@pytest.mark.unit
def test_time_window_validation_absolute_both_required():
    """Test that absolute time windows require both start and end."""
    with pytest.raises(ValueError, match="Both start_time and end_time must be provided"):
        TimeWindow(start_time="01:00")


@pytest.mark.unit
def test_time_window_validation_absolute_format():
    """Test that absolute time windows validate HH:MM format."""
    with pytest.raises(ValueError, match="Time must be in HH:MM format"):
        TimeWindow(start_time="1:00", end_time="2:00")


@pytest.mark.unit
def test_time_window_validation_burst_both_required():
    """Test that burst patterns require both on and off."""
    with pytest.raises(ValueError, match="Both burst_on and burst_off must be provided"):
        TimeWindow(burst_on=10)


@pytest.mark.unit
def test_time_window_validation_burst_positive():
    """Test that burst on/off must be positive."""
    with pytest.raises(ValueError, match="burst_on and burst_off must be positive"):
        TimeWindow(burst_on=0, burst_off=20)


@pytest.mark.unit
def test_time_window_validation_single_type():
    """Test that only one window type can be specified."""
    with pytest.raises(ValueError, match="Only one window type can be specified"):
        TimeWindow(start_offset=-60, end_offset=0, start_time="01:00", end_time="02:00")


@pytest.mark.unit
def test_time_window_validation_at_least_one():
    """Test that at least one window type must be specified."""
    with pytest.raises(ValueError, match="At least one window type must be specified"):
        TimeWindow()


# ── Conditional Window Tests ──────────────────────────────────────────────────

@pytest.mark.unit
def test_conditional_window_btc_change():
    """Test conditional window for BTC change."""
    window = ConditionalWindow(
        indicator="btc_change",
        operator="lt",
        threshold=2.0,
        periods=5
    )
    assert window.indicator == "btc_change"
    assert window.operator == "lt"
    assert window.threshold == 2.0


@pytest.mark.unit
def test_conditional_window_rsi():
    """Test conditional window for RSI."""
    window = ConditionalWindow(
        indicator="rsi",
        operator="lt",
        threshold=30.0,
        source="binance"
    )
    assert window.indicator == "rsi"
    assert window.source == "binance"


@pytest.mark.unit
def test_conditional_window_custom():
    """Test conditional window with custom check."""
    def custom_check():
        return True
    
    window = ConditionalWindow(
        indicator="custom",
        operator="gt",
        threshold=0.5,
        custom_check=custom_check
    )
    assert window.indicator == "custom"
    assert window.custom_check == custom_check


@pytest.mark.unit
def test_conditional_window_validation_operator():
    """Test that conditional windows validate operators."""
    with pytest.raises(ValueError, match="Invalid operator"):
        ConditionalWindow(indicator="btc_change", operator="invalid", threshold=2.0)


@pytest.mark.unit
def test_conditional_window_validation_indicator():
    """Test that conditional windows validate indicators."""
    with pytest.raises(ValueError, match="Invalid indicator"):
        ConditionalWindow(indicator="invalid", operator="lt", threshold=2.0)


@pytest.mark.unit
def test_conditional_window_validation_custom_requires_check():
    """Test that custom indicator requires custom_check."""
    with pytest.raises(ValueError, match="custom_check must be provided"):
        ConditionalWindow(indicator="custom", operator="lt", threshold=2.0)


# ── Time Filter Tests ────────────────────────────────────────────────────────

@pytest.mark.unit
def test_time_filter_days():
    """Test time filter with days."""
    time_filter = TimeFilter(days=[0, 1, 2, 3, 4])  # Monday-Friday
    assert time_filter.days == [0, 1, 2, 3, 4]


@pytest.mark.unit
def test_time_filter_hours():
    """Test time filter with hours."""
    time_filter = TimeFilter(hours=[9, 10, 11, 12, 13, 14, 15, 16, 17])  # 9AM-5PM
    assert time_filter.hours == [9, 10, 11, 12, 13, 14, 15, 16, 17]


@pytest.mark.unit
def test_time_filter_combined():
    """Test time filter with both days and hours."""
    time_filter = TimeFilter(
        days=[0, 1, 2, 3, 4],
        hours=[9, 10, 11, 12, 13, 14, 15, 16, 17]
    )
    assert time_filter.days == [0, 1, 2, 3, 4]
    assert time_filter.hours == [9, 10, 11, 12, 13, 14, 15, 16, 17]


@pytest.mark.unit
def test_time_filter_validation_days():
    """Test that time filter validates day range."""
    with pytest.raises(ValueError, match="Days must be 0-6"):
        TimeFilter(days=[0, 1, 2, 3, 4, 5, 6, 7])


@pytest.mark.unit
def test_time_filter_validation_hours():
    """Test that time filter validates hour range."""
    with pytest.raises(ValueError, match="Hours must be 0-23"):
        TimeFilter(hours=[0, 1, 2, 3, 4, 5, 6, 7, 8, 9, 10, 11, 12, 13, 14, 15, 16, 17, 18, 19, 20, 21, 22, 23, 24])


@pytest.mark.unit
def test_time_filter_is_allowed_days():
    """Test time filter day filtering."""
    time_filter = TimeFilter(days=[0, 1, 2, 3, 4])  # Monday-Friday
    
    # Monday (day 0)
    monday = datetime(2024, 1, 1, 12, 0, 0, tzinfo=timezone.utc)  # Jan 1, 2024 is Monday
    assert time_filter.is_allowed(monday) is True
    
    # Saturday (day 5)
    saturday = datetime(2024, 1, 6, 12, 0, 0, tzinfo=timezone.utc)  # Jan 6, 2024 is Saturday
    assert time_filter.is_allowed(saturday) is False


@pytest.mark.unit
def test_time_filter_is_allowed_hours():
    """Test time filter hour filtering."""
    time_filter = TimeFilter(hours=[9, 10, 11])  # 9AM-11AM
    
    # 10AM
    allowed_time = datetime(2024, 1, 1, 10, 0, 0, tzinfo=timezone.utc)
    assert time_filter.is_allowed(allowed_time) is True
    
    # 2PM
    blocked_time = datetime(2024, 1, 1, 14, 0, 0, tzinfo=timezone.utc)
    assert time_filter.is_allowed(blocked_time) is False


@pytest.mark.unit
def test_time_filter_is_allowed_combined():
    """Test time filter combined day and hour filtering."""
    time_filter = TimeFilter(days=[0], hours=[9, 10])  # Monday 9AM-10AM
    
    # Monday 10AM
    allowed = datetime(2024, 1, 1, 10, 0, 0, tzinfo=timezone.utc)
    assert time_filter.is_allowed(allowed) is True
    
    # Monday 2PM (wrong hour)
    wrong_hour = datetime(2024, 1, 1, 14, 0, 0, tzinfo=timezone.utc)
    assert time_filter.is_allowed(wrong_hour) is False
    
    # Tuesday 10AM (wrong day)
    wrong_day = datetime(2024, 1, 2, 10, 0, 0, tzinfo=timezone.utc)
    assert time_filter.is_allowed(wrong_day) is False


# ── SniperConfig Integration Tests ─────────────────────────────────────────────

@pytest.mark.unit
def test_sniper_config_with_time_windows():
    """Test SniperConfig with time windows."""
    config = SniperConfig(
        asset="BTC",
        timeframe="5m",
        time_windows=[
            TimeWindow(start_offset=-120, end_offset=-60),
            TimeWindow(start_offset=-30, end_offset=0),
        ]
    )
    assert len(config.time_windows) == 2


@pytest.mark.unit
def test_sniper_config_with_conditional_windows():
    """Test SniperConfig with conditional windows."""
    config = SniperConfig(
        asset="BTC",
        timeframe="5m",
        conditional_windows=[
            ConditionalWindow(indicator="btc_change", operator="lt", threshold=2.0)
        ]
    )
    assert len(config.conditional_windows) == 1


@pytest.mark.unit
def test_sniper_config_with_time_filter():
    """Test SniperConfig with time filter."""
    config = SniperConfig(
        asset="BTC",
        timeframe="5m",
        time_filter=TimeFilter(days=[0, 1, 2, 3, 4])
    )
    assert config.time_filter is not None


@pytest.mark.unit
def test_sniper_config_time_windows_validation():
    """Test that SniperConfig validates time windows."""
    with pytest.raises(ValueError, match="time_windows must be a list"):
        SniperConfig(asset="BTC", timeframe="5m", time_windows="invalid")


@pytest.mark.unit
def test_sniper_config_conditional_windows_validation():
    """Test that SniperConfig validates conditional windows."""
    with pytest.raises(ValueError, match="conditional_windows must be a list"):
        SniperConfig(asset="BTC", timeframe="5m", conditional_windows="invalid")


@pytest.mark.unit
def test_sniper_config_time_filter_validation():
    """Test that SniperConfig validates time filter."""
    with pytest.raises(ValueError, match="time_filter must be a TimeFilter instance"):
        SniperConfig(asset="BTC", timeframe="5m", time_filter="invalid")


@pytest.mark.unit
def test_sniper_config_backward_compatibility():
    """Test that window_seconds still works (backward compatibility)."""
    config = SniperConfig(
        asset="BTC",
        timeframe="5m",
        window_seconds=35
    )
    assert config.window_seconds == 35
    assert config.time_windows is None


# ── Gamma resolution fallback (#4) ────────────────────────────────────────────

@pytest.mark.unit
def test_wait_for_resolution_gamma_fallback():
    """Stream dropped without close → Gamma resolves the outcome via API."""
    sniper = _make_sniper_armed()
    sniper._filled_order = MagicMock(side="UP", price=0.95, amount=20.0, id="order-1")
    sniper._final_up = None
    sniper._final_down = None
    sniper._stream.running = False
    sniper._stop_event.is_set()

    import polyalpha.bots.sniper as sniper_mod
    sniper_mod.RESOLUTION_TIMEOUT = 0
    sniper.client.markets.resolve_outcome = MagicMock(return_value="UP")
    sniper.client.paper.resolve = MagicMock()
    sniper.client.paper.positions = MagicMock(return_value=[])

    sniper._wait_for_resolution()

    sniper.client.markets.resolve_outcome.assert_called_once_with(sniper._market.slug)
    sniper.client.paper.resolve.assert_called_once()
    assert sniper.client.paper.resolve.call_args[0][1] == "UP"


@pytest.mark.unit
def test_wait_for_resolution_gamma_unresolved_warns():
    """Unresolved Gamma → warning path, no crash, no outcome recorded."""
    sniper = _make_sniper_armed()
    sniper._filled_order = MagicMock(side="UP", price=0.95, amount=20.0, id="order-1")
    sniper._final_up = None
    sniper._final_down = None
    sniper._stream.running = False
    sniper._stop_event.is_set()

    import polyalpha.bots.sniper as sniper_mod
    sniper_mod.RESOLUTION_TIMEOUT = 0
    sniper._gamma_resolve = MagicMock(return_value=None)
    sniper.client.paper.resolve = MagicMock()

    sniper._wait_for_resolution()

    sniper._gamma_resolve.assert_called_once()
    sniper.client.paper.resolve.assert_not_called()
