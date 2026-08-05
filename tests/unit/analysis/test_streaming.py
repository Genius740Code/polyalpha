"""
ChainlinkStreamer and ChainlinkStreamerConfig tests — run with: pytest tests/unit/analysis/test_streaming.py
"""

import asyncio
import time
from datetime import datetime, timezone
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from polyalpha.analysis.streaming import ChainlinkStreamer, ChainlinkStreamerConfig


@pytest.mark.unit
class TestChainlinkStreamerConfig:
    """Test ChainlinkStreamerConfig dataclass."""

    def test_default_config(self):
        cfg = ChainlinkStreamerConfig()
        assert cfg.ws_url == "wss://ws-live-data.polymarket.com"
        assert cfg.timeout == 30
        assert cfg.recv_timeout == 30
        assert cfg.max_retries == 10
        assert cfg.base_delay == 3.0
        assert cfg.backoff_factor == 2.0
        assert cfg.jitter == 0.2
        assert cfg.stale_threshold == 30.0
        assert "BTC" in cfg.symbol_map
        assert cfg.symbol_map["BTC"] == "btc/usd"

    def test_custom_ws_url(self):
        cfg = ChainlinkStreamerConfig(ws_url="wss://custom.example.com")
        assert cfg.ws_url == "wss://custom.example.com"

    def test_custom_symbol_map(self):
        cfg = ChainlinkStreamerConfig(symbol_map={"BTC": "btc-usd"})
        assert cfg.symbol_map["BTC"] == "btc-usd"

    def test_custom_timeout(self):
        cfg = ChainlinkStreamerConfig(timeout=60)
        assert cfg.timeout == 60

    def test_custom_recv_timeout(self):
        cfg = ChainlinkStreamerConfig(recv_timeout=15)
        assert cfg.recv_timeout == 15

    def test_custom_max_retries(self):
        cfg = ChainlinkStreamerConfig(max_retries=5)
        assert cfg.max_retries == 5

    def test_custom_base_delay(self):
        cfg = ChainlinkStreamerConfig(base_delay=1.0)
        assert cfg.base_delay == 1.0

    def test_custom_stale_threshold(self):
        cfg = ChainlinkStreamerConfig(stale_threshold=60.0)
        assert cfg.stale_threshold == 60.0

    def test_custom_reconnect_delay(self):
        cfg = ChainlinkStreamerConfig(reconnect_delay=10.0)
        assert cfg.reconnect_delay == 10.0

    def test_default_window_seconds(self):
        cfg = ChainlinkStreamerConfig()
        assert cfg.window_seconds == 120.0

    def test_custom_window_seconds(self):
        cfg = ChainlinkStreamerConfig(window_seconds=60.0)
        assert cfg.window_seconds == 60.0


@pytest.mark.unit
class TestChainlinkStreamerWindow:
    """Test the built-in rolling window and pct calculations."""

    def test_window_none_before_start(self):
        streamer = ChainlinkStreamer()
        assert streamer.window is None
        assert streamer.value is None
        assert streamer.age_s == float("inf")
        assert streamer.change_pct(30) is None
        assert streamer.pct(30) is None
        assert streamer.trend(30) is None
        assert streamer.direction(30) is None

    def test_record_price_updates_window_and_value(self):
        streamer = ChainlinkStreamer()
        streamer._active_symbol = "BTC"
        ts = datetime.now(timezone.utc)

        streamer._record_price("BTC", 66000.0, ts)
        streamer._record_price("BTC", 66050.0, ts)

        assert streamer.last_price == 66050.0
        assert streamer.value == 66050.0
        assert streamer.window is not None
        assert streamer.window.value == 66050.0
        # Window holds at least the two recorded points
        assert len(streamer.window._window) >= 2

    def test_record_price_emits_event(self):
        streamer = ChainlinkStreamer()
        streamer._active_symbol = "BTC"
        ts = datetime.now(timezone.utc)
        called = []

        @streamer.on("price")
        def handler(symbol, price, timestamp):
            called.append((symbol, price, timestamp))

        streamer._record_price("BTC", 66000.0, ts)
        assert called == [("BTC", 66000.0, ts)]

    def test_per_symbol_windows_isolated(self):
        streamer = ChainlinkStreamer()
        ts = datetime.now(timezone.utc)
        streamer._record_price("BTC", 66000.0, ts)
        streamer._record_price("BTC", 66050.0, ts)
        streamer._record_price("ETH", 3500.0, ts)

        streamer._active_symbol = "BTC"
        assert streamer.window.value == 66050.0
        # ETH window is independent
        assert streamer.window.value != 3500.0

    def test_pct_returns_decimal_change(self):
        streamer = ChainlinkStreamer()
        streamer._active_symbol = "BTC"
        ts = datetime.now(timezone.utc)
        streamer._record_price("BTC", 90.0, ts)
        time.sleep(0.002)
        streamer._record_price("BTC", 99.0, ts)

        pct = streamer.change_pct(120)
        assert pct is not None
        assert pct == pytest.approx((99.0 - 90.0) / 90.0, rel=1e-6)


@pytest.mark.unit
class TestChainlinkStreamer:
    """Test ChainlinkStreamer initialization and callbacks."""

    def test_init_default_config(self):
        streamer = ChainlinkStreamer()
        assert streamer.config is not None
        assert streamer.config.ws_url == "wss://ws-live-data.polymarket.com"
        assert streamer._running is False

    def test_init_custom_config(self):
        cfg = ChainlinkStreamerConfig(timeout=60)
        streamer = ChainlinkStreamer(cfg)
        assert streamer.config.timeout == 60

    def test_on_price_callback(self):
        streamer = ChainlinkStreamer()
        called = []

        @streamer.on("price")
        def handler(symbol, price, timestamp):
            called.append((symbol, price, timestamp))

        timestamp = datetime.now(timezone.utc)
        streamer._emit("price", "BTC", 50000.0, timestamp)

        assert len(called) == 1
        assert called[0] == ("BTC", 50000.0, timestamp)

    def test_on_error_callback(self):
        streamer = ChainlinkStreamer()
        called = []

        @streamer.on("error")
        def handler(exc):
            called.append(exc)

        exc = Exception("Test error")
        streamer._emit("error", exc)

        assert len(called) == 1
        assert called[0] == exc

    def test_on_connect_callback(self):
        streamer = ChainlinkStreamer()
        called = []

        @streamer.on("connect")
        def handler():
            called.append(True)

        streamer._emit("connect")

        assert len(called) == 1
        assert called[0] is True

    def test_on_disconnect_callback(self):
        streamer = ChainlinkStreamer()
        called = []

        @streamer.on("disconnect")
        def handler():
            called.append(True)

        streamer._emit("disconnect")

        assert len(called) == 1
        assert called[0] is True

    def test_multiple_callbacks_same_event(self):
        streamer = ChainlinkStreamer()
        called = []

        @streamer.on("price")
        def handler1(symbol, price, timestamp):
            called.append("handler1")

        @streamer.on("price")
        def handler2(symbol, price, timestamp):
            called.append("handler2")

        streamer._emit("price", "BTC", 50000.0, datetime.now(timezone.utc))

        assert len(called) == 2
        assert "handler1" in called
        assert "handler2" in called

    def test_invalid_event(self):
        streamer = ChainlinkStreamer()
        with pytest.raises(ValueError, match="Invalid event"):
            streamer.on("invalid_event")

    def test_callback_exception_handling(self):
        streamer = ChainlinkStreamer()
        called = []

        @streamer.on("price")
        def handler(symbol, price, timestamp):
            raise ValueError("Callback error")

        @streamer.on("price")
        def handler2(symbol, price, timestamp):
            called.append(True)

        streamer._emit("price", "BTC", 50000.0, datetime.now(timezone.utc))

        assert len(called) == 1

    def test_stop(self):
        streamer = ChainlinkStreamer()
        streamer._running = True
        streamer.stop()
        assert streamer._running is False

    def test_stop_with_task(self):
        streamer = ChainlinkStreamer()
        streamer._task = MagicMock()
        streamer._task.done.return_value = False
        streamer._running = True
        streamer.stop()
        assert streamer._running is False
        streamer._task.cancel.assert_called_once()

    def test_start_invalid_symbol(self):
        streamer = ChainlinkStreamer()
        with pytest.raises(ValueError, match="Symbol 'INVALID' not in symbol_map"):
            streamer.start("INVALID")

    def test_start_valid_symbol(self):
        streamer = ChainlinkStreamer()
        with patch("polyalpha.analysis.streaming.asyncio.run"):
            streamer.start("BTC")

    def test_stale_data_detection(self):
        streamer = ChainlinkStreamer()
        streamer._last_price_time = 0.0
        streamer._stale_warned = False

        streamer._check_stale_data()
        assert streamer._stale_warned is False

        streamer._last_price_time = 0.0
        streamer._check_stale_data()
        assert streamer._stale_warned is False

    def test_check_stale_data_triggers_warning(self):
        streamer = ChainlinkStreamer()
        streamer._stale_warned = False

        with patch("polyalpha.analysis.streaming.time.time", return_value=100.0):
            streamer._last_price_time = 50.0
            streamer._check_stale_data()
            assert streamer._stale_warned is True

    def test_check_stale_data_resets_after_fresh_data(self):
        streamer = ChainlinkStreamer()
        streamer._stale_warned = True
        with patch("polyalpha.analysis.streaming.time.time", return_value=100.0):
            streamer._last_price_time = 99.0
            streamer._check_stale_data()
            assert streamer._stale_warned is False


@pytest.mark.unit
class TestChainlinkStreamerIntegration:
    """Integration tests with mocked WebSocket."""

    @pytest.mark.asyncio
    async def test_websocket_connection_mock(self):
        """Test WebSocket connection with mocked websockets library."""
        streamer = ChainlinkStreamer()
        streamer._running = True
        streamer._active_symbol = "BTC"
        called = []

        @streamer.on("connect")
        def handler():
            called.append("connect")

        @streamer.on("price")
        def price_handler(symbol, price, timestamp):
            called.append(("price", symbol, price))

        mock_ws = AsyncMock()
        mock_ws.recv = AsyncMock(side_effect=[
            '{"payload": {"symbol": "btc/usd", "timestamp": 1721640000000, "value": 66000.0}}',
            asyncio.TimeoutError(),
        ])
        mock_ws.send = AsyncMock()
        mock_ws.__aenter__ = AsyncMock(return_value=mock_ws)
        mock_ws.__aexit__ = AsyncMock(return_value=None)

        with patch("websockets.connect", return_value=mock_ws):
            task = asyncio.create_task(streamer._connect_and_stream("btc/usd", "BTC"))
            await asyncio.sleep(0.1)
            streamer._running = False
            try:
                await task
            except asyncio.TimeoutError:
                pass

        assert "connect" in called
        assert any(c == ("price", "BTC", 66000.0) for c in called)
        # The streamer's built-in window is populated by the WS price update
        assert streamer.last_price == 66000.0
        assert streamer.value == 66000.0
        assert streamer.window is not None
        assert streamer.window.value == 66000.0

    @pytest.mark.asyncio
    async def test_websocket_timeout_raises(self):
        """Test that recv timeout propagates as exception (not silent break)."""
        streamer = ChainlinkStreamer()
        streamer._running = True

        mock_ws = AsyncMock()
        mock_ws.recv = AsyncMock(side_effect=asyncio.TimeoutError())
        mock_ws.send = AsyncMock()
        mock_ws.__aenter__ = AsyncMock(return_value=mock_ws)
        mock_ws.__aexit__ = AsyncMock(return_value=None)

        with patch("websockets.connect", return_value=mock_ws):
            with pytest.raises(asyncio.TimeoutError):
                await streamer._connect_and_stream("btc/usd", "BTC")

    @pytest.mark.asyncio
    async def test_server_ping_responded_with_pong(self):
        """Test that server PING is responded to with PONG."""
        streamer = ChainlinkStreamer()
        streamer._running = True

        mock_ws = AsyncMock()
        mock_ws.recv = AsyncMock(side_effect=[
            "PING",
            asyncio.TimeoutError(),
        ])
        mock_ws.send = AsyncMock()
        mock_ws.__aenter__ = AsyncMock(return_value=mock_ws)
        mock_ws.__aexit__ = AsyncMock(return_value=None)

        with patch("websockets.connect", return_value=mock_ws):
            task = asyncio.create_task(streamer._connect_and_stream("btc/usd", "BTC"))
            await asyncio.sleep(0.1)
            streamer._running = False
            try:
                await task
            except asyncio.TimeoutError:
                pass

        pong_calls = [c for c in mock_ws.send.call_args_list if c[0][0] == "PONG"]
        assert len(pong_calls) >= 1

    @pytest.mark.asyncio
    async def test_server_pong_is_tracked(self):
        """Test that received PONG updates _last_pong_time."""
        streamer = ChainlinkStreamer()
        streamer._running = True

        mock_ws = AsyncMock()
        mock_ws.recv = AsyncMock(side_effect=[
            "PONG",
            asyncio.TimeoutError(),
        ])
        mock_ws.send = AsyncMock()
        mock_ws.__aenter__ = AsyncMock(return_value=mock_ws)
        mock_ws.__aexit__ = AsyncMock(return_value=None)

        with patch("websockets.connect", return_value=mock_ws):
            task = asyncio.create_task(streamer._connect_and_stream("btc/usd", "BTC"))
            await asyncio.sleep(0.1)
            streamer._running = False
            try:
                await task
            except asyncio.TimeoutError:
                pass

        assert streamer._last_pong_time > 0

    def test_symbol_validation(self):
        """Test that symbols are properly validated."""
        streamer = ChainlinkStreamer()
        assert "BTC" in streamer.config.symbol_map
        assert "ETH" in streamer.config.symbol_map
        assert "SOL" in streamer.config.symbol_map
        assert "XRP" in streamer.config.symbol_map
        assert "DOGE" in streamer.config.symbol_map

    def test_symbol_case_insensitive(self):
        """Test that symbol lookup is case-insensitive."""
        streamer = ChainlinkStreamer()
        with patch("polyalpha.analysis.streaming.asyncio.run"):
            streamer.start("btc")
