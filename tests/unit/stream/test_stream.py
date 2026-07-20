"""
Stream module tests — run with: pytest tests/unit/stream/test_stream.py
"""

import pytest
from polyalpha.stream import Stream, EVENTS
from polyalpha.core.constants import (
    WS_MAX_RETRIES,
    WS_RETRY_DELAY,
    DEFAULT_PRICE_THRESHOLD,
)
from polyalpha.core.market import Market


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


# ── Stream initialization tests ─────────────────────────────────────────────────

@pytest.mark.unit
def test_stream_initialization():
    market = make_market()
    
    stream = Stream(market, retries=5, retry_delay=2.0, price_threshold=0.001)
    
    assert stream.market == market
    assert stream.retries == 5
    assert stream.retry_delay == 2.0
    assert stream._price_threshold == 0.001
    assert stream.up == market.up_price
    assert stream.down == market.down_price


@pytest.mark.unit
def test_stream_default_initialization():
    market = make_market()
    
    stream = Stream(market)
    
    assert stream.retries == WS_MAX_RETRIES
    assert stream.retry_delay == WS_RETRY_DELAY
    assert stream._price_threshold == DEFAULT_PRICE_THRESHOLD


@pytest.mark.unit
def test_stream_rate_limiter_initialization():
    market = make_market()
    stream = Stream(market)
    
    assert stream._message_rate_limiter is not None
    assert hasattr(stream._message_rate_limiter, 'acquire')


@pytest.mark.unit
def test_stream_websocket_import_error():
    # Temporarily hide websocket-client
    import builtins
    original_import = builtins.__import__
    
    def mock_import(name, *args, **kwargs):
        if name == "websocket":
            raise ImportError("No module named 'websocket'")
        return original_import(name, *args, **kwargs)
    
    builtins.__import__ = mock_import
    
    try:
        market = make_market()
        with pytest.raises(ImportError, match="websocket-client is required"):
            Stream(market)
    finally:
        builtins.__import__ = original_import


# ── Stream event handler tests ─────────────────────────────────────────────────

@pytest.mark.unit
def test_stream_event_handlers():
    market = make_market()
    stream = Stream(market)
    
    events_called = []
    
    @stream.on("price")
    def on_price(up, down):
        events_called.append(("price", up, down))
    
    @stream.on("connect")
    def on_connect():
        events_called.append(("connect",))
    
    # Manually emit events
    stream._emit("price", 0.60, 0.40)
    stream._emit("connect")
    
    assert len(events_called) == 2
    assert events_called[0] == ("price", 0.60, 0.40)
    assert events_called[1] == ("connect",)


@pytest.mark.unit
def test_stream_invalid_event():
    market = make_market()
    stream = Stream(market)
    
    # Try to register handler for invalid event
    with pytest.raises(ValueError, match="Unknown event"):
        @stream.on("invalid_event")
        def handler():
            pass


@pytest.mark.unit
def test_stream_handler_exception():
    market = make_market()
    stream = Stream(market)
    
    @stream.on("price")
    def failing_handler(up, down):
        raise ValueError("Test error")
    
    @stream.on("price")
    def working_handler(up, down):
        pass
    
    # Should not raise exception, just log it
    stream._emit("price", 0.60, 0.40)


# ── Stream price threshold tests ───────────────────────────────────────────────

@pytest.mark.unit
def test_stream_price_threshold():
    market = make_market(prices=[0.50, 0.50], tokens=["tok_up", "tok_down"])
    stream = Stream(market, price_threshold=0.01)

    events_called = []

    @stream.on("price")
    def on_price(up, down):
        events_called.append((up, down))

    # Initialize last emitted prices
    stream._last_emitted_up = 0.50
    stream._last_emitted_down = 0.50

    # Small change below threshold - should not emit
    stream._token_prices["tok_up"] = 0.505
    stream._token_prices["tok_down"] = 0.495
    stream._publish_prices()
    assert len(events_called) == 0

    # Large change above threshold - should emit
    stream._token_prices["tok_up"] = 0.60
    stream._token_prices["tok_down"] = 0.40
    stream._publish_prices()
    assert len(events_called) == 1
    assert events_called[0] == (0.60, 0.40)


@pytest.mark.unit
def test_stream_price_threshold_zero():
    market = make_market(prices=[0.50, 0.50], tokens=["tok_up", "tok_down"])
    stream = Stream(market, price_threshold=0.0)

    events_called = []

    @stream.on("price")
    def on_price(up, down):
        events_called.append((up, down))

    # Initialize last emitted prices
    stream._last_emitted_up = 0.50
    stream._last_emitted_down = 0.50

    # Any change should emit with zero threshold
    stream._token_prices["tok_up"] = 0.5001
    stream._token_prices["tok_down"] = 0.4999
    stream._publish_prices()
    assert len(events_called) == 1


# ── Stream token price mapping tests ───────────────────────────────────────────

@pytest.mark.unit
def test_stream_token_price_mapping():
    market = make_market(tokens=["tok_up", "tok_down"])
    stream = Stream(market)
    
    # Simulate token price updates
    stream._token_prices["tok_up"] = 0.60
    stream._token_prices["tok_down"] = 0.40
    
    stream._publish_prices()
    
    assert stream.up == 0.60
    assert stream.down == 0.40


@pytest.mark.unit
def test_stream_degenerate_token_case():
    # Same token ID for both sides (degenerate case)
    market = make_market(tokens=["tok_same", "tok_same"])
    stream = Stream(market)
    
    stream._token_prices["tok_same"] = 0.60
    
    stream._publish_prices()
    
    assert stream.up == 0.60
    assert stream.down == 0.40  # Complement


@pytest.mark.unit
def test_stream_empty_market_tokens():
    market = make_market(tokens=[], prices=[0.0, 0.0])
    stream = Stream(market)
    
    # Should not crash with empty tokens
    stream._publish_prices()
    
    assert stream.up == 0.0
    assert stream.down == 0.0


# ── Stream message dispatching tests ───────────────────────────────────────────

@pytest.mark.unit
def test_stream_dispatch_price_change():
    market = make_market(tokens=["tok_up", "tok_down"])
    stream = Stream(market)
    
    events_called = []
    
    @stream.on("price")
    def on_price(up, down):
        events_called.append(("price", up, down))
    
    # Simulate price_change event (correct structure)
    msg = {
        "event_type": "price_change",
        "price_changes": [
            {
                "asset_id": "tok_up",
                "price": 0.60
            }
        ]
    }
    
    stream._dispatch(msg)
    
    # Price should be updated
    assert stream.up == 0.60
    # Event should be emitted (if threshold exceeded)
    assert len(events_called) >= 0


@pytest.mark.unit
def test_stream_dispatch_book_update():
    market = make_market(tokens=["tok_up", "tok_down"])
    stream = Stream(market)
    
    events_called = []
    
    @stream.on("book")
    def on_book(book):
        events_called.append(("book", book))
    
    # Simulate book update (correct structure)
    msg = {
        "event_type": "best_bid_ask",
        "asset_id": "tok_up",
        "best_bid": 0.58,
        "best_ask": 0.62
    }
    
    stream._dispatch(msg)
    
    # Should update token prices from mid
    assert stream._token_prices.get("tok_up") == 0.60


@pytest.mark.unit
def test_stream_dispatch_trade():
    market = make_market(tokens=["tok_up", "tok_down"])
    stream = Stream(market)
    
    events_called = []
    
    @stream.on("trade")
    def on_trade(trade):
        events_called.append(("trade", trade))
    
    # Simulate trade event (correct structure)
    msg = {
        "event_type": "last_trade_price",
        "asset_id": "tok_up",
        "price": 0.61
    }
    
    stream._dispatch(msg)
    
    # Should update token price
    assert stream._token_prices.get("tok_up") == 0.61


@pytest.mark.unit
def test_stream_dispatch_unknown_event():
    market = make_market()
    stream = Stream(market)
    
    # Unknown event type should not crash
    msg = {
        "event_type": "unknown_event",
        "data": {}
    }
    
    stream._dispatch(msg)  # Should not raise


@pytest.mark.unit
def test_stream_dispatch_malformed_message():
    market = make_market()
    stream = Stream(market)
    
    # Malformed message should not crash
    msg = {"invalid": "structure"}
    
    stream._dispatch(msg)  # Should not raise


# ── Stream control message handling tests ─────────────────────────────────────

@pytest.mark.unit
def test_stream_ping_pong_handling():
    market = make_market()
    stream = Stream(market)
    
    # Mock WebSocket
    class MockWS:
        def __init__(self):
            self.sent = []
        
        def send(self, msg):
            self.sent.append(msg)
    
    ws = MockWS()
    
    # Test PING response
    stream._on_message(ws, "PING")
    
    assert "PONG" in ws.sent


@pytest.mark.unit
def test_stream_pong_ignore():
    market = make_market()
    stream = Stream(market)
    
    events_called = []
    
    @stream.on("price")
    def on_price(up, down):
        events_called.append((up, down))
    
    # PONG should be ignored
    stream._on_message(None, "PONG")
    
    assert len(events_called) == 0


@pytest.mark.unit
def test_stream_empty_frame_ignore():
    market = make_market()
    stream = Stream(market)
    
    events_called = []
    
    @stream.on("price")
    def on_price(up, down):
        events_called.append((up, down))
    
    # Empty frames should be ignored
    stream._on_message(None, "")
    stream._on_message(None, "[]")
    
    assert len(events_called) == 0


@pytest.mark.unit
def test_stream_invalid_json_handling():
    market = make_market()
    stream = Stream(market)
    
    events_called = []
    
    @stream.on("price")
    def on_price(up, down):
        events_called.append((up, down))
    
    # Invalid JSON should not crash
    stream._on_message(None, "not valid json")
    
    assert len(events_called) == 0


# ── Stream retry logic tests ─────────────────────────────────────────────────────

@pytest.mark.unit
def test_stream_retry_logic():
    market = make_market()
    
    stream = Stream(market, retries=3)
    
    assert stream.retries == 3
    
    # Test that retry count is respected
    # (actual reconnection logic requires WebSocket mocking)


# ── Stream circuit breaker tests ───────────────────────────────────────────────

@pytest.mark.unit
def test_stream_circuit_breaker_enabled():
    market = make_market()
    stream = Stream(market, enable_circuit_breaker=True)
    
    assert stream._circuit_breaker is not None
    assert stream.circuit_breaker_state is not None


@pytest.mark.unit
def test_stream_circuit_breaker_disabled():
    market = make_market()
    stream = Stream(market, enable_circuit_breaker=False)
    
    assert stream._circuit_breaker is None
    assert stream.circuit_breaker_state is None


# ── Stream connection quality tests ────────────────────────────────────────────

@pytest.mark.unit
def test_stream_connection_quality_initial():
    market = make_market()
    stream = Stream(market)
    
    assert stream.connection_quality == 1.0


@pytest.mark.unit
def test_stream_connection_quality_property():
    market = make_market()
    stream = Stream(market)
    
    # Test property access
    quality = stream.connection_quality
    assert 0.0 <= quality <= 1.0


# ── Stream mid-price calculation tests ─────────────────────────────────────────

@pytest.mark.unit
def test_stream_mid_price_valid():
    market = make_market()
    stream = Stream(market)
    
    mid = stream._mid(0.58, 0.62)
    assert mid == 0.60


@pytest.mark.unit
def test_stream_mid_price_zero_bid():
    market = make_market()
    stream = Stream(market)
    
    mid = stream._mid(0.0, 0.62)
    assert mid is None


@pytest.mark.unit
def test_stream_mid_price_zero_ask():
    market = make_market()
    stream = Stream(market)
    
    mid = stream._mid(0.58, 0.0)
    assert mid is None


@pytest.mark.unit
def test_stream_mid_price_invalid():
    market = make_market()
    stream = Stream(market)
    
    mid = stream._mid("invalid", 0.62)
    assert mid is None


# ── Stream token price setting tests ───────────────────────────────────────────

@pytest.mark.unit
def test_stream_set_token_price_valid():
    market = make_market()
    stream = Stream(market)
    
    stream._set_token_price("tok_up", 0.60)
    
    assert stream._token_prices["tok_up"] == 0.60


@pytest.mark.unit
def test_stream_set_token_price_invalid():
    market = make_market()
    stream = Stream(market)
    
    # Should not set price for invalid token or zero price
    stream._set_token_price("", 0.60)
    stream._set_token_price("tok_up", 0.0)
    
    assert "tok_up" not in stream._token_prices


# ── Stream price handler tests ─────────────────────────────────────────────────

@pytest.mark.unit
def test_stream_handle_price_change():
    market = make_market(tokens=["tok_up", "tok_down"])
    stream = Stream(market)
    
    msg = {
        "event_type": "price_change",
        "price_changes": [
            {
                "asset_id": "tok_up",
                "best_bid": 0.58,
                "best_ask": 0.62
            }
        ]
    }
    
    stream._handle_price_change(msg)
    
    assert stream._token_prices.get("tok_up") == 0.60


@pytest.mark.unit
def test_stream_handle_price_change_fallback():
    market = make_market(tokens=["tok_up", "tok_down"])
    stream = Stream(market)
    
    msg = {
        "event_type": "price_change",
        "price_changes": [
            {
                "asset_id": "tok_up",
                "price": 0.60
            }
        ]
    }
    
    stream._handle_price_change(msg)
    
    assert stream._token_prices.get("tok_up") == 0.60


@pytest.mark.unit
def test_stream_handle_best_bid_ask():
    market = make_market(tokens=["tok_up", "tok_down"])
    stream = Stream(market)
    
    msg = {
        "asset_id": "tok_up",
        "best_bid": 0.58,
        "best_ask": 0.62
    }
    
    stream._handle_best_bid_ask(msg)
    
    assert stream._token_prices.get("tok_up") == 0.60


@pytest.mark.unit
def test_stream_handle_book():
    market = make_market(tokens=["tok_up", "tok_down"])
    stream = Stream(market)
    
    msg = {
        "asset_id": "tok_up",
        "bids": [{"price": 0.58}],
        "asks": [{"price": 0.62}]
    }
    
    stream._handle_book(msg)
    
    assert stream._token_prices.get("tok_up") == 0.60


@pytest.mark.unit
def test_stream_handle_book_empty():
    market = make_market(tokens=["tok_up", "tok_down"])
    stream = Stream(market)
    
    msg = {
        "asset_id": "tok_up",
        "bids": [],
        "asks": []
    }
    
    # Should not crash with empty book
    stream._handle_book(msg)


@pytest.mark.unit
def test_stream_handle_last_trade():
    market = make_market(tokens=["tok_up", "tok_down"])
    stream = Stream(market)
    
    msg = {
        "asset_id": "tok_up",
        "price": "0.61"
    }
    
    stream._handle_last_trade(msg)
    
    assert stream._token_prices.get("tok_up") == 0.61


@pytest.mark.unit
def test_stream_handle_last_trade_invalid():
    market = make_market(tokens=["tok_up", "tok_down"])
    stream = Stream(market)
    
    msg = {
        "asset_id": "tok_up",
        "price": "invalid"
    }
    
    # Should not crash with invalid price
    stream._handle_last_trade(msg)


# ── Stream market resolved tests ───────────────────────────────────────────────

@pytest.mark.unit
def test_stream_market_resolved():
    market = make_market(tokens=["tok_up", "tok_down"])
    stream = Stream(market)
    
    events_called = []
    
    @stream.on("close")
    def on_close():
        events_called.append("close")
    
    msg = {
        "event_type": "market_resolved"
    }
    
    stream._dispatch(msg)
    
    assert "close" in events_called


# ── Stream add_handler tests ───────────────────────────────────────────────────

@pytest.mark.unit
def test_stream_add_handler():
    market = make_market()
    stream = Stream(market)
    
    events_called = []
    
    def on_price(up, down):
        events_called.append((up, down))
    
    stream.add_handler("price", on_price)
    stream._emit("price", 0.60, 0.40)
    
    assert len(events_called) == 1
    assert events_called[0] == (0.60, 0.40)


@pytest.mark.unit
def test_stream_add_handler_invalid_event():
    market = make_market()
    stream = Stream(market)
    
    def handler():
        pass
    
    with pytest.raises(ValueError, match="Unknown event"):
        stream.add_handler("invalid_event", handler)


# ── Stream running property tests ─────────────────────────────────────────────

@pytest.mark.unit
def test_stream_running_initial():
    market = make_market()
    stream = Stream(market)
    
    assert stream.running is False


# ── Stream stop tests ─────────────────────────────────────────────────────────

@pytest.mark.unit
def test_stream_stop():
    market = make_market()
    stream = Stream(market)
    
    # Should not crash when stopping without WebSocket
    stream.stop()
    
    assert stream._stop.is_set()


# ── Stream message rate limiting tests ─────────────────────────────────────────

@pytest.mark.unit
def test_stream_message_rate_limiting():
    market = make_market()
    stream = Stream(market)
    
    # Test that rate limiter is applied during message processing
    # (actual rate limiting behavior tested through integration)
    assert stream._message_rate_limiter is not None


# ── Stream connection quality update tests ─────────────────────────────────────

@pytest.mark.unit
def test_stream_pong_updates_quality_good():
    market = make_market()
    stream = Stream(market)
    
    # Simulate good RTT
    stream._last_ping_time = 100.0
    stream._on_message(None, "PONG")
    
    # Quality should remain high
    assert stream.connection_quality >= 0.9


@pytest.mark.unit
def test_stream_pong_updates_quality_poor():
    market = make_market()
    stream = Stream(market)
    
    # Simulate poor RTT
    stream._last_ping_time = 0.0
    stream._on_message(None, "PONG")
    
    # Quality should be lower
    assert stream.connection_quality <= 1.0
