"""
CVDTracker tests — run with: pytest tests/unit/analysis/test_cvd_tracker.py
"""

import asyncio
import json
from contextlib import suppress
from unittest.mock import AsyncMock, patch

import pytest

from polyalpha.analysis.delta import CVDTracker, CVDTrackerConfig


def _feed(tracker, trades, t0=100.0):
    """Drive aggTrade messages with ``(price, qty, m)`` triples at increasing ts.

    ``m=True`` is an aggressive sell (buyer is maker), ``m=False`` an aggressive
    buy (buyer is taker).
    """
    for i, (px, qty, m) in enumerate(trades):
        raw = json.dumps({"e": "aggTrade", "p": str(px), "q": str(qty), "m": m})
        with patch("polyalpha.analysis.delta.time.time", return_value=t0 + i):
            tracker._handle(raw)


def _snapshots(tracker, values, t0=200.0):
    """Append ``(cvd30, cvd60)`` snapshot tuples directly at increasing ts."""
    for i, (c30, c60) in enumerate(values):
        tracker.history.append({"ts": t0 + i, "cvd30": c30, "cvd60": c60})


@pytest.fixture
def tracker():
    return CVDTracker()


@pytest.mark.unit
class TestCVDTrackerConfig:
    def test_defaults(self):
        cfg = CVDTrackerConfig()
        assert cfg.ws_url == "wss://stream.binance.com:9443/ws/btcusdt@aggTrade"
        assert cfg.ping_interval == 20.0
        assert cfg.reconnect_delay == 3.0
        assert cfg.snapshot_interval == 10.0
        assert cfg.sample_max_age == 180.0
        assert cfg.history_maxlen == 200

    def test_custom(self):
        cfg = CVDTrackerConfig(ping_interval=5, reconnect_delay=1.0, snapshot_interval=2.0)
        assert cfg.ping_interval == 5
        assert cfg.reconnect_delay == 1.0
        assert cfg.snapshot_interval == 2.0


@pytest.mark.unit
class TestHandle:
    def test_buy_is_positive(self, tracker):
        _feed(tracker, [(65000, 0.5, False)], t0=100.0)
        assert tracker.samples[-1] == (100.0, 0.5)

    def test_sell_is_negative(self, tracker):
        _feed(tracker, [(65000, 0.5, True)], t0=100.0)
        assert tracker.samples[-1] == (100.0, -0.5)

    def test_invalid_json_ignored(self, tracker):
        tracker._handle("not-json{")
        assert len(tracker.samples) == 0

    def test_bad_qty_swallowed(self, tracker):
        raw = json.dumps({"e": "aggTrade", "p": "65000", "q": "nope", "m": False})
        tracker._handle(raw)
        assert len(tracker.samples) == 0

    def test_missing_qty_ignored(self, tracker):
        raw = json.dumps({"e": "aggTrade", "p": "65000", "m": False})
        tracker._handle(raw)
        assert len(tracker.samples) == 0

    def test_bytes_payload_decoded(self, tracker):
        raw = json.dumps({"e": "aggTrade", "p": "65000", "q": "1.0", "m": False})
        with patch("polyalpha.analysis.delta.time.time", return_value=100.0):
            tracker._handle(raw.encode())
        assert tracker.samples[-1] == (100.0, 1.0)


@pytest.mark.unit
class TestCVD:
    def test_sum_of_signed_qty(self, tracker):
        _feed(tracker, [
            (65000, 1.0, False),  # +1.0
            (65000, 0.5, True),   # -0.5
            (65000, 2.0, False),  # +2.0
        ], t0=100.0)
        with patch("polyalpha.analysis.delta.time.time", return_value=100.0):
            assert tracker.cvd(60) == pytest.approx(2.5)

    def test_only_counts_within_window(self, tracker):
        _feed(tracker, [(65000, 1.0, False)] * 5, t0=100.0)
        with patch("polyalpha.analysis.delta.time.time", return_value=200.0):
            assert tracker.cvd(60) == 0.0
            assert tracker.cvd(200) == pytest.approx(5.0)

    def test_prunes_older_than_max_age(self, tracker):
        _feed(tracker, [(65000, 1.0, False)] * 3, t0=100.0)
        with patch("polyalpha.analysis.delta.time.time", return_value=400.0):
            assert tracker.cvd(3600) == 0.0
            assert len(tracker.samples) == 0

    def test_empty_samples(self, tracker):
        with patch("polyalpha.analysis.delta.time.time", return_value=100.0):
            assert tracker.cvd(60) == 0.0


@pytest.mark.unit
class TestSnapshotLoop:
    @pytest.mark.asyncio
    async def test_appends_snapshot(self, tracker):
        cfg = CVDTrackerConfig(snapshot_interval=0.001)
        tracker = CVDTracker(cfg)
        tracker.samples.append((100.0, 3.0))
        tracker.samples.append((100.0, -1.0))
        task = asyncio.create_task(tracker._snapshot_loop())
        await asyncio.sleep(0.05)
        task.cancel()
        with suppress(asyncio.CancelledError):
            await task
        assert len(tracker.history) >= 1
        snap = tracker.history[-1]
        assert "ts" in snap
        assert "cvd30" in snap
        assert "cvd60" in snap

    def test_history_capped(self, tracker):
        cfg = CVDTrackerConfig(history_maxlen=5)
        tracker = CVDTracker(cfg)
        _snapshots(tracker, [(1.0, 1.0)] * 20)
        assert len(tracker.history) == 5


@pytest.mark.unit
class TestZScore:
    def test_needs_five_snapshots(self, tracker):
        _snapshots(tracker, [(1.0, 1.0)] * 4)
        assert tracker.z() is None

    def test_computes_z(self, tracker):
        _snapshots(tracker, [(1.0, 1.0), (2.0, 2.0), (3.0, 3.0), (4.0, 4.0), (5.0, 5.0)])
        _feed(tracker, [(65000, 5.0, False)], t0=100.0)
        with patch("polyalpha.analysis.delta.time.time", return_value=100.0):
            assert tracker.z() == pytest.approx((5.0 - 3.0) / 2**0.5)

    def test_zero_std_returns_none(self, tracker):
        _snapshots(tracker, [(1.0, 1.0)] * 5)
        _feed(tracker, [(65000, 1.0, False)], t0=100.0)
        with patch("polyalpha.analysis.delta.time.time", return_value=100.0):
            assert tracker.z() is None

    def test_key_selection(self, tracker):
        # window_s >= 60 uses the cvd60 history; < 60 uses the cvd30 history.
        import statistics

        cvd30_hist = [10.0, 10.0, 10.0, 10.0, 12.0]
        cvd60_hist = [1.0, 1.0, 1.0, 1.0, 3.0]
        _snapshots(tracker, list(zip(cvd30_hist, cvd60_hist)))
        # current cvd(30) and cvd(60) are equal, so the only difference between
        # the two z-scores is which history provides mean/std.
        _feed(tracker, [(65000, 13.4, False)], t0=100.0)
        with patch("polyalpha.analysis.delta.time.time", return_value=100.0):
            z30 = tracker.z(30)
            z60 = tracker.z(60)
        assert z30 == pytest.approx((13.4 - statistics.mean(cvd30_hist)) / statistics.pstdev(cvd30_hist))
        assert z60 == pytest.approx((13.4 - statistics.mean(cvd60_hist)) / statistics.pstdev(cvd60_hist))
        assert z30 != z60


@pytest.mark.unit
class TestDecelerating:
    def test_needs_two_snapshots(self, tracker):
        _snapshots(tracker, [(1.0, 1.0)])
        assert tracker.decelerating() is None

    def test_shrinking_same_sign(self, tracker):
        _snapshots(tracker, [(-5.0, -5.0), (-2.0, -2.0)])
        assert tracker.decelerating() is True

    def test_growing_same_sign_is_not_decelerating(self, tracker):
        _snapshots(tracker, [(-2.0, -2.0), (-5.0, -5.0)])
        assert tracker.decelerating() is False

    def test_opposite_sign_is_not_decelerating(self, tracker):
        _snapshots(tracker, [(-2.0, -2.0), (2.0, 2.0)])
        assert tracker.decelerating() is False

    def test_both_zero_not_decelerating(self, tracker):
        _snapshots(tracker, [(0.0, 0.0), (0.0, 0.0)])
        assert tracker.decelerating() is False


@pytest.mark.unit
class TestVelocity:
    def test_needs_two_snapshots(self, tracker):
        _snapshots(tracker, [(1.0, 1.0)])
        assert tracker.velocity() is None

    def test_delta_between_last_two(self, tracker):
        _snapshots(tracker, [(1.0, 10.0), (1.0, 14.0)])
        assert tracker.velocity() == pytest.approx(4.0)
        assert tracker.velocity("cvd30") == pytest.approx(0.0)


@pytest.mark.unit
class TestAcceleration:
    def test_needs_three_snapshots(self, tracker):
        _snapshots(tracker, [(1.0, 1.0), (2.0, 2.0)])
        assert tracker.acceleration() is None

    def test_second_difference(self, tracker):
        # velocities: 1, 3  => acceleration 2
        _snapshots(tracker, [(0.0, 1.0), (1.0, 2.0), (1.0, 5.0)])
        assert tracker.acceleration() == pytest.approx(2.0)


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
        tracker = CVDTracker()

        ws = _FakeWebSocket([
            json.dumps({"e": "aggTrade", "p": "65000", "q": "1.5", "m": False}),
            json.dumps({"e": "aggTrade", "p": "65000", "q": "0.5", "m": True}),
        ], on_exhausted=lambda: setattr(tracker, "_stop", True))

        with patch("websockets.connect", return_value=ws), \
             patch("polyalpha.analysis.delta.time.time", return_value=100.0):
            await tracker._run()
            assert tracker.cvd(60) == pytest.approx(1.0)

    @pytest.mark.asyncio
    async def test_run_reconnects_on_drop(self):
        tracker = CVDTracker()

        calls = {"n": 0}

        def fake_connect(*args, **kwargs):
            if calls["n"] == 0:
                calls["n"] += 1
                raise ConnectionError("drop")
            calls["n"] += 1
            tracker._stop = True  # exit loop after the reconnect
            return _FakeWebSocket([])

        with patch("websockets.connect", side_effect=fake_connect), \
             patch("polyalpha.analysis.delta.asyncio.sleep", new=AsyncMock()):
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
