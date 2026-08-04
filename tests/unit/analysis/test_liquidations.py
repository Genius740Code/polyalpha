"""
LiquidationTracker tests — run with: pytest tests/unit/analysis/test_liquidations.py
"""

import asyncio
import json
from unittest.mock import AsyncMock, patch

import pytest

from polyalpha.analysis.liquidations import LiquidationTracker, LiquidationTrackerConfig


def _feed(tracker, events, t0=100.0):
    """Drive forceOrder messages with ``(side, qty, price)`` triples at increasing ts."""
    for i, (side, qty, price) in enumerate(events):
        raw = json.dumps({"o": {"S": side, "q": str(qty), "p": str(price)}})
        with patch("polyalpha.analysis.liquidations.time.time", return_value=t0 + i):
            tracker._handle(raw)


@pytest.fixture
def tracker():
    return LiquidationTracker()


@pytest.mark.unit
class TestLiquidationTrackerConfig:
    def test_defaults(self):
        cfg = LiquidationTrackerConfig()
        assert cfg.ws_url == "wss://fstream.binance.com/ws/btcusdt@forceOrder"
        assert cfg.ping_interval == 20.0
        assert cfg.reconnect_delay == 3.0
        assert cfg.events_maxlen == 500

    def test_custom(self):
        cfg = LiquidationTrackerConfig(ping_interval=5, reconnect_delay=1.0, events_maxlen=50)
        assert cfg.ping_interval == 5
        assert cfg.reconnect_delay == 1.0
        assert cfg.events_maxlen == 50


@pytest.mark.unit
class TestHandle:
    def test_sell_event_appends_notional(self, tracker):
        _feed(tracker, [("SELL", 1.5, 65000)], t0=100.0)
        assert tracker.events[-1] == (100.0, "SELL", 1.5 * 65000)

    def test_buy_event_appends_notional(self, tracker):
        _feed(tracker, [("BUY", 0.5, 40000)], t0=100.0)
        assert tracker.events[-1] == (100.0, "BUY", 0.5 * 40000)

    def test_invalid_json_ignored(self, tracker):
        tracker._handle("not-json{")
        assert len(tracker.events) == 0

    def test_bad_qty_swallowed(self, tracker):
        raw = json.dumps({"o": {"S": "SELL", "q": "nope", "p": "65000"}})
        tracker._handle(raw)
        assert len(tracker.events) == 0

    def test_bad_price_swallowed(self, tracker):
        raw = json.dumps({"o": {"S": "SELL", "q": "1.0", "p": "abc"}})
        tracker._handle(raw)
        assert len(tracker.events) == 0

    def test_missing_fields_ignored(self, tracker):
        tracker._handle(json.dumps({"o": {"S": "SELL"}}))
        tracker._handle(json.dumps({"e": "forceOrder"}))
        assert len(tracker.events) == 0

    def test_bytes_payload_decoded(self, tracker):
        raw = json.dumps({"o": {"S": "BUY", "q": "2.0", "p": "100.5"}})
        with patch("polyalpha.analysis.liquidations.time.time", return_value=100.0):
            tracker._handle(raw.encode())
        assert tracker.events[-1] == (100.0, "BUY", 201.0)

    def test_events_deque_capped(self):
        cfg = LiquidationTrackerConfig(events_maxlen=500)
        tracker = LiquidationTracker(cfg)
        _feed(tracker, [("SELL", 1.0, 100.0)] * 510, t0=100.0)
        assert len(tracker.events) == 500


@pytest.mark.unit
class TestCluster:
    def test_too_few_recent_events(self, tracker):
        _feed(tracker, [("SELL", 1.0, 100.0), ("SELL", 1.0, 100.0)], t0=100.0)
        with patch("polyalpha.analysis.liquidations.time.time", return_value=100.0):
            assert tracker.cluster() is None

    def test_side_is_last_event(self, tracker):
        # 4 events in window, but the LAST event's side only has 2 — no cluster.
        _feed(tracker, [("SELL", 1.0, 100.0), ("SELL", 1.0, 100.0), ("BUY", 1.0, 100.0)], t0=100.0)
        with patch("polyalpha.analysis.liquidations.time.time", return_value=100.0):
            assert tracker.cluster() is None

    def test_sell_cluster_direction_down(self, tracker):
        _feed(tracker, [
            ("SELL", 1.0, 100.0),
            ("SELL", 1.0, 100.0),
            ("SELL", 2.0, 100.0),
        ], t0=100.0)
        with patch("polyalpha.analysis.liquidations.time.time", return_value=100.0):
            res = tracker.cluster()
        assert res == {"direction": "DOWN", "notional": 400.0, "count": 3}

    def test_buy_cluster_direction_up(self, tracker):
        _feed(tracker, [
            ("BUY", 1.0, 100.0),
            ("BUY", 1.0, 100.0),
            ("BUY", 1.0, 100.0),
        ], t0=100.0)
        with patch("polyalpha.analysis.liquidations.time.time", return_value=100.0):
            res = tracker.cluster()
        assert res == {"direction": "UP", "notional": 300.0, "count": 3}

    def test_counts_only_same_side(self, tracker):
        # 3 tiny SELLs + 3 big BUYs; last event is BUY so only the BUYs count.
        _feed(tracker, [
            ("SELL", 1.0, 100.0),
            ("SELL", 1.0, 100.0),
            ("SELL", 1.0, 100.0),
            ("BUY", 5.0, 100.0),
            ("BUY", 5.0, 100.0),
            ("BUY", 5.0, 100.0),
        ], t0=100.0)
        with patch("polyalpha.analysis.liquidations.time.time", return_value=100.0):
            res = tracker.cluster()
        assert res == {"direction": "UP", "notional": 1500.0, "count": 3}

    def test_only_counts_events_within_window(self, tracker):
        # 3 SELLs far outside the window → too few recent events.
        _feed(tracker, [("SELL", 1.0, 100.0)] * 3, t0=0.0)
        with patch("polyalpha.analysis.liquidations.time.time", return_value=1000.0):
            assert tracker.cluster(window_s=20) is None

    def test_suppressed_below_hourly_avg(self, tracker):
        # A huge SELL an hour-ish ago lifts the baseline; the recent cluster
        # of tiny SELLs is below avg * mult → suppressed.
        _feed(tracker, [("SELL", 100.0, 100.0)], t0=0.0)     # 10_000 notional, outside window
        _feed(tracker, [("SELL", 0.1, 100.0)] * 3, t0=100.0)  # 30 notional, inside window
        with patch("polyalpha.analysis.liquidations.time.time", return_value=102.0):
            assert tracker.cluster(window_s=20) is None

    def test_not_suppressed_when_above_hourly_avg(self, tracker):
        # Big SELL is outside the 3600s baseline window (ts=-4000), so the
        # hourly avg is just the three in-window events; 3000 >= 2x avg.
        _feed(tracker, [("SELL", 100.0, 100.0)], t0=-4000.0)   # 10_000 notional, outside hourly
        _feed(tracker, [("SELL", 10.0, 100.0)] * 3, t0=100.0)  # 1_000 notional each, in window
        with patch("polyalpha.analysis.liquidations.time.time", return_value=102.0):
            res = tracker.cluster(window_s=20)
        assert res is not None
        assert res["notional"] == pytest.approx(3000.0)

    def test_empty_events(self, tracker):
        with patch("polyalpha.analysis.liquidations.time.time", return_value=100.0):
            assert tracker.cluster() is None


@pytest.mark.unit
class TestLifecycle:
    @pytest.mark.asyncio
    async def test_start_and_stop(self, tracker):
        tracker._run = AsyncMock()
        tracker.start()
        assert tracker._task is not None
        tracker.stop()
        assert tracker._stop is True

    @pytest.mark.asyncio
    async def test_start_is_idempotent(self, tracker):
        tracker._run = AsyncMock()
        tracker.start()
        task = tracker._task
        tracker.start()
        assert tracker._task is task

    @pytest.mark.asyncio
    async def test_run_applies_stream(self):
        tracker = LiquidationTracker()

        ws = _FakeWebSocket([
            json.dumps({"o": {"S": "SELL", "q": "1.5", "p": "65000"}}),
            json.dumps({"o": {"S": "SELL", "q": "0.5", "p": "65000"}}),
        ], on_exhausted=lambda: setattr(tracker, "_stop", True))

        with patch("websockets.connect", return_value=ws), \
             patch("polyalpha.analysis.liquidations.time.time", return_value=100.0):
            await tracker._run()
            assert len(tracker.events) == 2
            assert all(e[1] == "SELL" for e in tracker.events)

    @pytest.mark.asyncio
    async def test_run_reconnects_on_drop(self):
        tracker = LiquidationTracker()

        calls = {"n": 0}

        def fake_connect(*args, **kwargs):
            if calls["n"] == 0:
                calls["n"] += 1
                raise ConnectionError("drop")
            calls["n"] += 1
            tracker._stop = True  # exit loop after the reconnect
            return _FakeWebSocket([])

        with patch("websockets.connect", side_effect=fake_connect), \
             patch("polyalpha.analysis.liquidations.asyncio.sleep", new=AsyncMock()):
            await tracker._run()

        assert calls["n"] == 2


class _FakeWebSocket:
    """Minimal async context-manager websocket that yields raw messages."""

    def __init__(self, messages, on_exhausted=None):
        self.messages = list(messages)
        self.on_exhausted = on_exhausted

    async def __aenter__(self):
        return self

    async def __aexit__(self, *args):
        return None

    def __aiter__(self):
        return self._gen()

    async def _gen(self):
        for msg in self.messages:
            yield msg
            await asyncio.sleep(0)
        if self.on_exhausted:
            self.on_exhausted()
