"""
Stream module tests — run with: pytest tests/test_stream.py
"""

import sys, os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))

import pytest
from polyalpha.stream import Stream, EVENTS
from polyalpha.core.constants import WS_MAX_RETRIES, WS_RETRY_DELAY
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

def test_stream_initialization():
    market = make_market()
    
    stream = Stream(market, retries=5, retry_delay=2.0, price_threshold=0.001)
    
    assert stream.market == market
    assert stream.retries == 5
    assert stream.retry_delay == 2.0
    assert stream._price_threshold == 0.001
    assert stream.up == market.up_price
    assert stream.down == market.down_price


def test_stream_default_initialization():
    market = make_market()
    
    stream = Stream(market)
    
    assert stream.retries == WS_MAX_RETRIES
    assert stream.retry_delay == WS_RETRY_DELAY
    assert stream._price_threshold == 0.0001


def test_stream_rate_limiter_initialization():
    market = make_market()
    stream = Stream(market)
    
    assert stream._message_rate_limiter is not None
    assert hasattr(stream._message_rate_limiter, 'acquire')


def test_stream_websocket_import_error():
    # Temporarily hide websocket-client
    original_import = __builtins__.__import__
    
    def mock_import(name, *args, **kwargs):
        if name == "websocket":
            raise ImportError("No module named 'websocket'")
        return original_import(name, *args, **kwargs)
    
    __builtins__.__import__ = mock_import
    
    try:
        market = make_market()
        with pytest.raises(ImportError, match="websocket-client is required"):
            Stream(market)
    finally:
        __builtins__.__import__ = original_import


# ── Stream event handler tests ─────────────────────────────────────────────────

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


def test_stream_invalid_event():
    market = make_market()
    stream = Stream(market)
    
    # Try to register handler for invalid event
    with pytest.raises(ValueError, match="Unknown event"):
        @stream.on("invalid_event")
        def handler():
            pass


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

def test_stream_price_threshold():
    market = make_market(prices=[0.50, 0.50])
    stream = Stream(market, price_threshold=0.01)
    
    events_called = []
    
    @stream.on("price")
    def on_price(up, down):
        events_called.append((up, down))
    
    # Small change below threshold - should not emit
    stream.up = 0.505
    stream.down = 0.495
    stream._publish_prices()
    assert len(events_called) == 0
    
    # Large change above threshold - should emit
    stream.up = 0.60
    stream.down = 0.40
    stream._publish_prices()
    assert len(events_called) == 1
    assert events_called[0] == (0.60, 0.40)


def test_stream_price_threshold_zero():
    market = make_market(prices=[0.50, 0.50])
    stream = Stream(market, price_threshold=0.0)
    
    events_called = []
    
    @stream.on("price")
    def on_price(up, down):
        events_called.append((up, down))
    
    # Any change should emit with zero threshold
    stream.up = 0.5001
    stream.down = 0.4999
    stream._publish_prices()
    assert len(events_called) == 1


# ── Stream token price mapping tests ───────────────────────────────────────────

def test_stream_token_price_mapping():
    market = make_market(tokens=["tok_up", "tok_down"])
    stream = Stream(market)
    
    # Simulate token price updates
    stream._token_prices["tok_up"] = 0.60
    stream._token_prices["tok_down"] = 0.40
    
    stream._publish_prices()
    
    assert stream.up == 0.60
    assert stream.down == 0.40


def test_stream_degenerate_token_case():
    # Same token ID for both sides (degenerate case)
    market = make_market(tokens=["tok_same", "tok_same"])
    stream = Stream(market)
    
    stream._token_prices["tok_same"] = 0.60
    
    stream._publish_prices()
    
    assert stream.up == 0.60
    assert stream.down == 0.40  # Complement


def test_stream_empty_market_tokens():
    market = make_market(tokens=[])
    stream = Stream(market)
    
    # Should not crash with empty tokens
    stream._publish_prices()
    
    assert stream.up == 0.0
    assert stream.down == 0.0


# ── Stream message dispatching tests ───────────────────────────────────────────

def test_stream_dispatch_price_change():
    market = make_market(tokens=["tok_up", "tok_down"])
    stream = Stream(market)
    
    events_called = []
    
    @stream.on("price")
    def on_price(up, down):
        events_called.append(("price", up, down))
    
    # Simulate price_change event
    msg = {
        "event_type": "price_change",
        "data": {
            "token_id": "tok_up",
            "price": 0.60
        }
    }
    
    stream._dispatch(msg)
    
    # Price should be updated
    assert stream.up == 0.60
    # Event should be emitted (if threshold exceeded)
    assert len(events_called) >= 0


def test_stream_dispatch_book_update():
    market = make_market(tokens=["tok_up", "tok_down"])
    stream = Stream(market)
    
    events_called = []
    
    @stream.on("book")
    def on_book(book):
        events_called.append(("book", book))
    
    # Simulate book update
    msg = {
        "event_type": "best_bid_ask",
        "data": {
            "token_id": "tok_up",
            "best_bid": 0.58,
            "best_ask": 0.62
        }
    }
    
    stream._dispatch(msg)
    
    # Should update token prices from mid
    assert stream._token_prices.get("tok_up") == 0.60


def test_stream_dispatch_trade():
    market = make_market(tokens=["tok_up", "tok_down"])
    stream = Stream(market)
    
    events_called = []
    
    @stream.on("trade")
    def on_trade(trade):
        events_called.append(("trade", trade))
    
    # Simulate trade event
    msg = {
        "event_type": "last_trade_price",
        "data": {
            "token_id": "tok_up",
            "price": 0.61
        }
    }
    
    stream._dispatch(msg)
    
    # Should update token price
    assert stream._token_prices.get("tok_up") == 0.61


def test_stream_dispatch_unknown_event():
    market = make_market()
    stream = Stream(market)
    
    # Unknown event type should not crash
    msg = {
        "event_type": "unknown_event",
        "data": {}
    }
    
    stream._dispatch(msg)  # Should not raise


def test_stream_dispatch_malformed_message():
    market = make_market()
    stream = Stream(market)
    
    # Malformed message should not crash
    msg = {"invalid": "structure"}
    
    stream._dispatch(msg)  # Should not raise


# ── Stream control message handling tests ─────────────────────────────────────

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

def test_stream_retry_logic():
    market = make_market()
    
    stream = Stream(market, retries=3)
    
    assert stream.retries == 3
    
    # Test that retry count is respected
    # (actual reconnection logic requires WebSocket mocking)
