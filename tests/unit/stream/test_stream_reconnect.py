"""
Stream reconnect / async-path tests — hgroup4 findings #24, #25, #26.
"""

import asyncio
import json
import time

import pytest

from polyalpha.stream import Stream
from polyalpha.core.market import Market
from polyalpha.core.errors import StreamDisconnected


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


# ── #24 async reconnect ────────────────────────────────────────────────────────

class _RaisesClosedWS:
    def __aiter__(self):
        import websockets
        raise websockets.exceptions.ConnectionClosed(rcvd=None, sent=None)

    async def send(self, msg):
        pass


class _ClosedCtx:
    async def __aenter__(self):
        return _RaisesClosedWS()

    async def __aexit__(self, *exc):
        return False


@pytest.mark.asyncio
async def test_connect_async_raises_stream_disconnected_on_close(monkeypatch):
    """A dropped socket must surface as StreamDisconnected so run_async() retries."""
    import websockets

    stream = Stream(make_market())
    monkeypatch.setattr(websockets, "connect", lambda url: _ClosedCtx())

    with pytest.raises(StreamDisconnected, match="WebSocket closed unexpectedly"):
        await stream._connect_async()


@pytest.mark.asyncio
async def test_run_async_retries_after_disconnect(monkeypatch):
    """run_async() must retry a StreamDisconnected instead of returning."""
    stream = Stream(make_market(), retries=3, retry_delay=0.0)

    attempts = []

    async def flaky_connect():
        attempts.append(1)
        if len(attempts) == 1:
            raise StreamDisconnected("drop")

    monkeypatch.setattr(stream, "_connect_async", flaky_connect)

    await stream.run_async()

    assert len(attempts) == 2


@pytest.mark.asyncio
async def test_run_async_gives_up_after_max_retries(monkeypatch):
    """run_async() must emit an error and stop after exhausting the retry budget."""
    stream = Stream(make_market(), retries=2, retry_delay=0.0)

    errors = []

    @stream.on("error")
    def on_error(exc):
        errors.append(exc)

    async def always_fail():
        raise StreamDisconnected("drop")

    monkeypatch.setattr(stream, "_connect_async", always_fail)

    await stream.run_async()

    assert len(errors) == 1
    assert isinstance(errors[0], StreamDisconnected)


# ── #25 orphaned PONG task ─────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_ping_schedules_pong():
    stream = Stream(make_market())
    sent = []

    class MockWS:
        async def send(self, msg):
            sent.append(msg)

    stream._on_message_async(MockWS(), "PING")
    await asyncio.sleep(0.01)

    assert sent == ["PONG"]


@pytest.mark.asyncio
async def test_log_pong_result_retrieves_exception():
    """_log_pong_result must retrieve task exceptions instead of leaving them unhandled."""
    stream = Stream(make_market())

    async def boom():
        raise RuntimeError("socket closed")

    task = asyncio.ensure_future(boom())
    await asyncio.sleep(0)  # let the task run to completion

    stream._log_pong_result(task)  # should not raise

    assert task.exception() is not None


# ── #26 stale clock on flat markets ────────────────────────────────────────────

@pytest.mark.unit
def test_last_price_time_advances_on_any_frame(monkeypatch):
    """A healthy-but-flat market that still sends frames must not be reconnected."""
    stream = Stream(make_market(tokens=["tok_up", "tok_down"]))

    now = 1000.0
    monkeypatch.setattr(time, "time", lambda: now)
    stream._last_price_time = 500.0

    stream._on_message(None, "PING")

    assert stream._last_price_time == now


@pytest.mark.unit
def test_flat_price_frame_resets_stale_clock(monkeypatch):
    """Even a best_bid_ask frame with no price change refreshes the staleness clock."""
    stream = Stream(make_market(tokens=["tok_up", "tok_down"]))

    now = 1000.0
    monkeypatch.setattr(time, "time", lambda: now)
    stream._last_price_time = 500.0
    # Keep the token-bucket consistent with the frozen clock (it was built at
    # real wall-clock time, which would otherwise imply an enormous sleep).
    stream._message_rate_limiter.last_update = now
    stream._message_rate_limiter.tokens = float(stream._message_rate_limiter.max_requests)

    stream._on_message(None, json.dumps({
        "event_type": "best_bid_ask",
        "asset_id": "tok_up",
        "best_bid": "0.55",
        "best_ask": "0.57",
    }))

    assert stream._last_price_time == now
    assert stream._check_stale_data() is False


@pytest.mark.asyncio
async def test_async_path_refreshes_stale_clock_on_frame():
    stream = Stream(make_market(tokens=["tok_up", "tok_down"]))
    now = 1000.0
    stream._last_price_time = 500.0

    class MockWS:
        async def send(self, msg):
            pass

    stream._on_message_async(MockWS(), "PING")

    assert stream._last_price_time != 500.0


# ── issue #2: faster reconnect on stale data ──────────────────────────────────

@pytest.mark.unit
def test_stale_data_seconds_is_10():
    """STALE_DATA_SECONDS is tightened to 10s so stale feeds reconnect faster."""
    assert Stream.STALE_DATA_SECONDS == 10.0


@pytest.mark.unit
def test_check_stale_data_force_reconnects_at_2x(monkeypatch):
    """A quiet feed forces a reconnect at 2x STALE_DATA_SECONDS, not 3x."""
    stream = Stream(make_market())
    reconnects = []

    def fake_reconnect():
        reconnects.append(True)

    monkeypatch.setattr(stream, "_force_reconnect", fake_reconnect)

    # 1.9x → warn only, no reconnect
    stream._last_price_time = time.time() - (Stream.STALE_DATA_SECONDS * 1.9)
    assert stream._check_stale_data() is False
    assert reconnects == []

    # 2.1x → force reconnect
    stream._last_price_time = time.time() - (Stream.STALE_DATA_SECONDS * 2.1)
    assert stream._check_stale_data() is True
    assert len(reconnects) == 1
