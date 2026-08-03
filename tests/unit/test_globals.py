"""
Shared Globals / one-connection-many-strategies tests.

Run with: pytest tests/unit/test_globals.py
"""

import asyncio
from unittest.mock import AsyncMock

import pytest

from polyalpha import Globals, MarketCtx, watch_market
from polyalpha.analysis.delta import CVDTracker
from polyalpha.analysis.streaming import ChainlinkStreamer
from polyalpha.bot_hub import StrategyContext


# ── Fakes ─────────────────────────────────────────────────────────────────────

class FakeStart:
    """Feed with a start()/stop() that records calls."""
    def __init__(self):
        self.start_count = 0
        self.stop_count = 0

    def start(self):
        self.start_count += 1

    def stop(self):
        self.stop_count += 1


class FakeStreamer:
    """price_feed stand-in that records start() args."""
    def __init__(self):
        self.start_args = None
        self.stop_count = 0

    def start(self, *args, **kwargs):
        self.start_args = (args, kwargs)

    def stop(self):
        self.stop_count += 1


class StartlessFeed:
    """Feed with no start()/stop() — must be skipped by lifecycle."""
    pass


class FakeTracker:
    """TokenPairTracker stand-in with the same observation surface."""
    def __init__(self, up_id="U1", down_id="D1"):
        self.up_id = up_id
        self.down_id = down_id
        self.best_bid = {up_id: 0.60, down_id: 0.38}
        self.best_ask = {up_id: 0.62, down_id: 0.40}
        self.up_mid = 0.61
        self.down_mid = 0.39
        self.started = False
        self.stopped = False

    def start(self):
        self.started = True

    def stop(self):
        self.stopped = True

    def favourite(self):
        return ("UP", self.up_mid)

    def spread_stats(self, tid):
        return (0.02, 0.001)

    def spread_expansion(self, tid):
        return {"spread": 0.05, "mean": 0.02, "std": 0.001, "side_pulled": "ask"}

    def sweep(self, tid, **kwargs):
        return {"side": "BUY", "count": 5, "notional": 3.0}


class FakeMarket:
    def __init__(self, end_time):
        self.up_token = "U1"
        self.down_token = "D1"
        self.end_time = end_time
        self.up_price = 0.61


# ── Globals lifecycle ─────────────────────────────────────────────────────────

@pytest.mark.unit
class TestGlobalsDefaults:
    def test_empty(self):
        g = Globals()
        assert g.asset == "BTC"
        for field in (
            "price_feed", "klines", "cvd", "obi_cache", "futures",
            "liq", "db", "eth_feed", "klines_15m", "klines_1h",
        ):
            assert getattr(g, field) is None
        assert g.started == []

    def test_defaults_builds_in_scope_feeds(self):
        g = Globals.defaults("BTC")
        assert g.asset == "BTC"
        assert isinstance(g.price_feed, ChainlinkStreamer)
        assert isinstance(g.cvd, CVDTracker)
        assert g.liq is None
        assert g.klines is None

    def test_defaults_with_liq_degrades_when_unavailable(self):
        # LiquidationTracker is plan item 6 — until it ships, liq=True
        # gracefully leaves the feed None instead of raising.
        g = Globals.defaults("BTC", liq=True)
        assert g.liq is None


@pytest.mark.unit
class TestGlobalsStartStop:
    def test_start_skips_none(self):
        g = Globals()
        g.start()
        assert g.started == []

    def test_start_calls_each_feed_once_and_idempotent(self):
        g = Globals()
        f1, f2 = FakeStart(), FakeStart()
        g.cvd, g.liq = f1, f2
        g.start()
        g.start()
        assert g.started == [f1, f2]
        assert (f1.start_count, f1.stop_count) == (1, 0)
        assert (f2.start_count, f2.stop_count) == (1, 0)

    def test_start_skips_feed_without_start(self):
        g = Globals()
        g.cvd = StartlessFeed()
        g.start()
        assert g.started == []

    def test_price_feed_started_background_with_asset(self):
        g = Globals(asset="ETH")
        streamer = FakeStreamer()
        g.price_feed = streamer
        g.start()
        assert streamer.start_args == (("ETH",), {"background": True})
        assert g.started == [streamer]

    def test_stop_in_reverse_and_clears(self):
        g = Globals()
        f1, f2 = FakeStart(), FakeStart()
        g.cvd, g.liq = f1, f2
        g.start()
        g.stop()
        assert g.started == []
        assert (f1.stop_count, f2.stop_count) == (1, 1)

    def test_stop_idempotent(self):
        g = Globals()
        f = FakeStart()
        g.cvd = f
        g.start()
        g.stop()
        g.stop()
        assert f.stop_count == 1


# ── MarketCtx ─────────────────────────────────────────────────────────────────

@pytest.mark.unit
class TestMarketCtx:
    def test_remaining_with_epoch_end(self, monkeypatch):
        monkeypatch.setattr("polyalpha.globals.time.time", lambda: 100.0)
        ctx = MarketCtx(Globals(), FakeTracker(), end_time=500.0)
        assert ctx.remaining == 400.0
        assert not ctx.expired

    def test_remaining_unbounded(self):
        ctx = MarketCtx(Globals(), FakeTracker(), end_time=None)
        assert ctx.remaining == float("inf")
        assert not ctx.expired

    def test_remaining_floor_at_zero(self):
        ctx = MarketCtx(Globals(), FakeTracker(), end_time=-1000.0)
        assert ctx.remaining == 0.0
        assert ctx.expired

    def test_price_returns_mids(self):
        ctx = MarketCtx(Globals(), FakeTracker())
        assert ctx.price() == (0.61, 0.39)

    def test_favourite_delegates(self):
        ctx = MarketCtx(Globals(), FakeTracker())
        assert ctx.favourite() == ("UP", 0.61)

    def test_spread_up(self):
        ctx = MarketCtx(Globals(), FakeTracker())
        res = ctx.spread("UP")
        assert res["current"]["spread"] == pytest.approx(0.02)
        assert res["current"]["bid"] == 0.60
        assert res["current"]["ask"] == 0.62
        assert res["stats"] == (0.02, 0.001)
        assert res["expansion"]["side_pulled"] == "ask"

    def test_spread_down_maps_to_down_token(self):
        ctx = MarketCtx(Globals(), FakeTracker())
        res = ctx.spread("down")
        assert res["current"]["spread"] == pytest.approx(0.02)
        assert res["current"]["bid"] == 0.38
        assert res["current"]["ask"] == 0.40

    def test_trade_sweep_up(self):
        ctx = MarketCtx(Globals(), FakeTracker())
        res = ctx.trade_sweep("UP", window_s=15, min_count=4)
        assert res["side"] == "BUY"
        assert res["notional"] == 3.0


# ── watch_market ──────────────────────────────────────────────────────────────

@pytest.mark.unit
class TestWatchMarket:
    @pytest.mark.asyncio
    async def test_ticks_every_interval_until_expiry(self, monkeypatch):
        now = [100.0]
        monkeypatch.setattr("polyalpha.globals.time.time", lambda: now[0])
        monkeypatch.setattr("polyalpha.globals.asyncio.sleep", AsyncMock())
        tracker = FakeTracker()
        monkeypatch.setattr("polyalpha.globals._new_tracker", lambda u, d: tracker)

        seen = []

        def tick(ctx):
            seen.append(ctx.remaining)
            now[0] += 10

        await watch_market(Globals(), FakeMarket(end_time=130.0), tick, interval=2.0)

        assert seen == [30.0, 20.0, 10.0]
        assert tracker.started
        assert tracker.stopped

    @pytest.mark.asyncio
    async def test_parses_iso_end_time(self, monkeypatch):
        now = [100.0]
        monkeypatch.setattr("polyalpha.globals.time.time", lambda: now[0])
        monkeypatch.setattr("polyalpha.globals.asyncio.sleep", AsyncMock())
        tracker = FakeTracker()
        monkeypatch.setattr("polyalpha.globals._new_tracker", lambda u, d: tracker)

        def tick(ctx):
            now[0] = 1e12  # jump far past the 2099 window

        await watch_market(
            Globals(), FakeMarket(end_time="2099-01-01T00:00:00Z"), tick
        )
        assert tracker.stopped

    @pytest.mark.asyncio
    async def test_tracker_stopped_in_finally_on_error(self, monkeypatch):
        monkeypatch.setattr("polyalpha.globals.asyncio.sleep", AsyncMock())
        monkeypatch.setattr("polyalpha.globals.time.time", lambda: 100.0)
        tracker = FakeTracker()
        monkeypatch.setattr("polyalpha.globals._new_tracker", lambda u, d: tracker)

        def boom(ctx):
            raise RuntimeError("boom")

        with pytest.raises(RuntimeError):
            await watch_market(Globals(), FakeMarket(end_time=1000.0), boom)
        assert tracker.started
        assert tracker.stopped

    @pytest.mark.asyncio
    async def test_requires_both_tokens(self, monkeypatch):
        class NoTokens:
            up_token = ""
            down_token = ""

        with pytest.raises(ValueError):
            await watch_market(Globals(), NoTokens(), lambda ctx: None)

    @pytest.mark.asyncio
    async def test_timeframe_fallback_on_bad_end_time(self, monkeypatch):
        now = [100.0]
        monkeypatch.setattr("polyalpha.globals.time.time", lambda: now[0])
        monkeypatch.setattr("polyalpha.globals.asyncio.sleep", AsyncMock())
        tracker = FakeTracker()
        monkeypatch.setattr("polyalpha.globals._new_tracker", lambda u, d: tracker)

        seen = []

        def tick(ctx):
            seen.append(ctx.remaining)
            now[0] += 125

        await watch_market(
            Globals(), FakeMarket(end_time="not-a-date"), tick, timeframe="5m"
        )
        assert seen == [300.0, 175.0, 50.0]

    @pytest.mark.asyncio
    async def test_with_real_market_dataclass(self, monkeypatch):
        from polyalpha.core.market import Market

        now = [100.0]
        monkeypatch.setattr("polyalpha.globals.time.time", lambda: now[0])
        monkeypatch.setattr("polyalpha.globals.asyncio.sleep", AsyncMock())
        tracker = FakeTracker(up_id="U9", down_id="D9")
        monkeypatch.setattr("polyalpha.globals._new_tracker", lambda u, d: tracker)

        market = Market(
            id="cond-1", question="Q", description="", slug="btc-updown-5m-1",
            active=True, closed=False, archived=False,
            start_time="2026-01-01T00:00:00Z", end_time="2026-01-01T00:02:00Z",
            volume=0.0, liquidity=0.0,
            outcomes=["UP", "DOWN"], prices=[0.55, 0.45], tokens=["U9", "D9"],
        )

        seen = []

        def tick(ctx):
            seen.append((ctx.price(), ctx.open_price))
            now[0] = 1e12  # expire after first tick

        await watch_market(Globals(), market, tick)
        assert seen == [((0.61, 0.39), 0.55)]
        assert tracker.stopped


# ── Wiring ────────────────────────────────────────────────────────────────────

@pytest.mark.unit
class TestStrategyContextGlobals:
    def test_ctx_exposes_shared_globals(self):
        g = Globals()
        ctx = StrategyContext(
            name="s",
            stream=object(),
            paper=None,
            market=None,
            price_history=[],
            globals=g,
        )
        assert ctx.globals is g

    def test_ctx_globals_none_by_default(self):
        ctx = StrategyContext(
            name="s",
            stream=object(),
            paper=None,
            market=None,
            price_history=[],
        )
        assert ctx.globals is None
