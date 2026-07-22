"""
ChainlinkStreamer and ChainlinkStreamerConfig tests — run with: pytest tests/unit/analysis/test_streaming.py
"""

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
        assert cfg.reconnect_delay == 5.0
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

    def test_custom_reconnect_delay(self):
        cfg = ChainlinkStreamerConfig(reconnect_delay=10.0)
        assert cfg.reconnect_delay == 10.0


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

        # Emit price event
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

        # Should not raise, but log error
        streamer._emit("price", "BTC", 50000.0, datetime.now(timezone.utc))

        # Second callback should still be called
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
        # Just test that it doesn't raise for valid symbol
        # Actual connection is mocked in integration tests
        with patch("polyalpha.analysis.streaming.asyncio.run"):
            streamer.start("BTC")


@pytest.mark.unit
class TestChainlinkStreamerIntegration:
    """Integration tests with mocked WebSocket."""

    @pytest.mark.asyncio
    async def test_websocket_connection_mock(self):
        """Test WebSocket connection with mocked websockets library."""
        streamer = ChainlinkStreamer()
        streamer._running = True
        called = []

        @streamer.on("connect")
        def handler():
            called.append("connect")

        @streamer.on("price")
        def price_handler(symbol, price, timestamp):
            called.append(("price", symbol, price))

        # Mock websockets
        mock_ws = AsyncMock()
        mock_ws.recv = AsyncMock(side_effect=[
            # Subscription response
            '{"payload": {"symbol": "btc/usd", "timestamp": 1721640000000, "value": 66000.0}}',
            asyncio.TimeoutError(),  # Trigger disconnect
        ])
        mock_ws.send = AsyncMock()
        mock_ws.__aenter__ = AsyncMock(return_value=mock_ws)
        mock_ws.__aexit__ = AsyncMock()

        with patch("polyalpha.analysis.streaming.websockets.connect", return_value=mock_ws):
            # Run for a short time
            task = asyncio.create_task(streamer._connect_and_stream("btc/usd", "BTC"))
            await asyncio.sleep(0.1)
            streamer._running = False
            try:
                await task
            except asyncio.TimeoutError:
                pass

        assert "connect" in called
        assert any(c == ("price", "BTC", 66000.0) for c in called)

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
        # Should work with lowercase
        with patch("polyalpha.analysis.streaming.asyncio.run"):
            streamer.start("btc")
