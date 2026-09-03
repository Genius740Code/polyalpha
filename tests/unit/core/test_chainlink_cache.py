"""
ChainlinkPriceCache staleness tests — hgroup4 finding #29.
"""

import time
from datetime import datetime, timezone

import pytest

from polyalpha.core.chainlink_cache import ChainlinkPriceCache


class _FakeStreamer:
    """ChainlinkStreamer stand-in that captures the price handler."""

    def __init__(self):
        self._handler = None

    def on(self, event):
        def deco(fn):
            if event == "price":
                self._handler = fn
            return fn

        return deco

    def start(self, symbol, background=False):
        pass


def _make_cache(monkeypatch, max_age=60.0, now=1000.0):
    monkeypatch.setattr(time, "time", lambda: now)
    streamer = _FakeStreamer()
    cache = ChainlinkPriceCache(symbol="BTC", max_age=max_age, streamer=streamer)
    return cache, streamer


@pytest.mark.unit
def test_fresh_even_when_oracle_timestamp_is_old(monkeypatch):
    """Staleness must be measured from receive time, not the oracle-reported timestamp."""
    cache, streamer = _make_cache(monkeypatch, now=1000.0)

    # Oracle reports a timestamp 200s in the past, but we just received it.
    old_oracle = datetime.fromtimestamp(800.0, tz=timezone.utc)
    streamer._handler("BTC", 67_000.0, old_oracle)

    assert cache.get_price("BTC") == 67_000.0


@pytest.mark.unit
def test_returns_none_after_max_age_without_update(monkeypatch):
    """A price ages out once no fresh update has been received for max_age."""
    cache, streamer = _make_cache(monkeypatch, max_age=60.0, now=1000.0)

    streamer._handler("BTC", 67_000.0, datetime.now(timezone.utc))
    assert cache.get_price("BTC") == 67_000.0

    monkeypatch.setattr(time, "time", lambda: 1000.0 + 120.0)
    assert cache.get_price("BTC") is None


@pytest.mark.unit
def test_returns_none_before_first_update():
    """No price received yet → get_price returns None."""
    import threading

    cache = ChainlinkPriceCache.__new__(ChainlinkPriceCache)
    cache._prices = {}
    cache._lock = threading.Lock()
    cache._max_age = 60.0
    cache._streamer = None

    assert cache.get_price("BTC") is None
