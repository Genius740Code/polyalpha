"""
TokenPairTracker tests — run with: pytest tests/unit/orderbook/test_tracker.py
"""

import asyncio
import inspect
import json
import statistics
from contextlib import suppress
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from polyalpha.orderbook.tracker import TokenPairTracker, TokenPairTrackerConfig

UP_ID = "up-token-123"
DOWN_ID = "down-token-456"


class _FakeWebSocket:
    """Minimal async context-manager websocket that yields raw messages."""

    def __init__(self, messages, on_connect=None, on_exhausted=None):
        self.messages = list(messages)
        self.sent = []
        self.on_connect = on_connect
        self.on_exhausted = on_exhausted

    async def __aenter__(self):
        return self

    async def __aexit__(self, *args):
        return None

    async def send(self, raw):
        self.sent.append(raw)
        if self.on_connect:
            out = self.on_connect()
            if inspect.isawaitable(out):
                await out

    def __aiter__(self):
        return self._gen()

    async def _gen(self):
        for msg in self.messages:
            yield msg
            await asyncio.sleep(0)
        if self.on_exhausted:
            self.on_exhausted()


@pytest.fixture
def tracker():
    return TokenPairTracker(UP_ID, DOWN_ID)


@pytest.mark.unit
class TestTokenPairTrackerConfig:
    def test_defaults(self):
        cfg = TokenPairTrackerConfig()
        assert cfg.ws_url == "wss://ws-subscriptions-clob.polymarket.com/ws/market"
        assert cfg.clob_api == "https://clob.polymarket.com"
        assert cfg.max_age == 20
        assert cfg.ping_interval == 10.0
        assert cfg.reconnect_delay == 3.0

    def test_custom(self):
        cfg = TokenPairTrackerConfig(max_age=5, ping_interval=7, reconnect_delay=1.0)
        assert cfg.max_age == 5
        assert cfg.ping_interval == 7
        assert cfg.reconnect_delay == 1.0


@pytest.mark.unit
class TestTokenPairTrackerInit:
    def test_tracks_both_tokens(self, tracker):
        assert set(tracker.best_bid) == {UP_ID, DOWN_ID}
        assert set(tracker.best_ask) == {UP_ID, DOWN_ID}

    def test_starts_stale(self, tracker):
        assert tracker.fresh() is False
        assert tracker.up_mid is None
        assert tracker.down_mid is None


@pytest.mark.unit
class TestFreshAndMid:
    def test_fresh_after_update(self, tracker):
        with patch("polyalpha.orderbook.tracker.time.time", return_value=100.0):
            tracker._last_update = 99.0
            assert tracker.fresh() is True

    def test_stale_after_max_age(self, tracker):
        with patch("polyalpha.orderbook.tracker.time.time", return_value=100.0):
            tracker._last_update = 100.0 - tracker.config.max_age
            assert tracker.fresh() is False

    def test_mid_requires_both_sides(self, tracker):
        tracker.best_bid[UP_ID] = 0.55
        with patch("polyalpha.orderbook.tracker.time.time", return_value=100.0):
            tracker._last_update = 99.0
            assert tracker.mid(UP_ID) is None
            tracker.best_ask[UP_ID] = 0.60
            assert tracker.mid(UP_ID) == pytest.approx(0.575)

    def test_mid_stale_returns_none(self, tracker):
        tracker.best_bid[UP_ID] = 0.55
        tracker.best_ask[UP_ID] = 0.60
        with patch("polyalpha.orderbook.tracker.time.time", return_value=100.0):
            tracker._last_update = 1.0
            assert tracker.mid(UP_ID) is None

    def test_up_down_mids(self, tracker):
        tracker.best_bid = {UP_ID: 0.60, DOWN_ID: 0.35}
        tracker.best_ask = {UP_ID: 0.65, DOWN_ID: 0.40}
        with patch("polyalpha.orderbook.tracker.time.time", return_value=100.0):
            tracker._last_update = 99.0
            assert tracker.up_mid == pytest.approx(0.625)
            assert tracker.down_mid == pytest.approx(0.375)


@pytest.mark.unit
class TestHandleBook:
    def test_updates_best_bid_ask(self, tracker):
        raw = json.dumps({
            "event_type": "book",
            "asset_id": UP_ID,
            "bids": [{"price": "0.49"}, {"price": "0.50"}],
            "asks": [{"price": "0.53"}, {"price": "0.52"}],
        })
        with patch("polyalpha.orderbook.tracker.time.time", return_value=200.0):
            tracker._handle(raw)
            assert tracker.best_bid[UP_ID] == 0.50
            assert tracker.best_ask[UP_ID] == 0.52
            assert tracker.fresh() is True

    def test_ignores_unknown_token(self, tracker):
        raw = json.dumps({
            "event_type": "book",
            "asset_id": "stranger-token",
            "bids": [{"price": "0.50"}],
            "asks": [{"price": "0.52"}],
        })
        with patch("polyalpha.orderbook.tracker.time.time", return_value=200.0):
            tracker._handle(raw)
        assert "stranger-token" not in tracker.best_bid
        assert tracker.fresh() is False

    def test_ignores_missing_side(self, tracker):
        raw = json.dumps({
            "event_type": "book",
            "asset_id": DOWN_ID,
            "asks": [{"price": "0.40"}],
        })
        tracker._handle(raw)
        assert tracker.best_ask[DOWN_ID] == 0.40
        assert tracker.best_bid[DOWN_ID] is None


@pytest.mark.unit
class TestHandlePriceChange:
    def test_updates_from_price_changes(self, tracker):
        raw = json.dumps({
            "event_type": "price_change",
            "price_changes": [
                {"asset_id": UP_ID, "best_bid": "0.58", "best_ask": "0.61"},
                {"asset_id": DOWN_ID, "best_bid": "0.39", "best_ask": "0.42"},
            ],
        })
        with patch("polyalpha.orderbook.tracker.time.time", return_value=300.0):
            tracker._handle(raw)
            assert tracker.best_bid[UP_ID] == 0.58
            assert tracker.best_ask[UP_ID] == 0.61
            assert tracker.best_bid[DOWN_ID] == 0.39
            assert tracker.best_ask[DOWN_ID] == 0.42
            assert tracker.fresh() is True

    def test_partial_update_preserves_other_side(self, tracker):
        tracker.best_bid[UP_ID] = 0.58
        raw = json.dumps({
            "event_type": "price_change",
            "price_changes": [
                {"asset_id": UP_ID, "best_ask": "0.61"},
            ],
        })
        tracker._handle(raw)
        assert tracker.best_bid[UP_ID] == 0.58
        assert tracker.best_ask[UP_ID] == 0.61

    def test_ignores_unknown_token(self, tracker):
        raw = json.dumps({
            "event_type": "price_change",
            "price_changes": [{"asset_id": "stranger", "best_bid": "0.50"}],
        })
        tracker._handle(raw)
        assert tracker.fresh() is False


@pytest.mark.unit
class TestHandleEdgeCases:
    def test_pong_ignored(self, tracker):
        tracker._handle("PONG")
        assert tracker.fresh() is False

    def test_invalid_json_ignored(self, tracker):
        tracker._handle("not-json{")
        assert tracker.fresh() is False

    def test_list_of_events(self, tracker):
        raw = json.dumps([
            {"event_type": "book", "asset_id": UP_ID,
             "bids": [{"price": "0.60"}], "asks": [{"price": "0.65"}]},
            {"event_type": "price_change", "price_changes": [
                {"asset_id": DOWN_ID, "best_bid": "0.35", "best_ask": "0.40"}]},
        ])
        with patch("polyalpha.orderbook.tracker.time.time", return_value=100.0):
            tracker._handle(raw)
        assert tracker.best_bid[UP_ID] == 0.60
        assert tracker.best_bid[DOWN_ID] == 0.35


def _feed_quotes(tracker, tid, quotes, t0=100.0):
    """Drive book events with the given ``(bid, ask)`` pairs at increasing ts."""
    for i, (bid, ask) in enumerate(quotes):
        raw = json.dumps({
            "event_type": "book",
            "asset_id": tid,
            "bids": [{"price": str(bid)}],
            "asks": [{"price": str(ask)}],
        })
        with patch("polyalpha.orderbook.tracker.time.time", return_value=t0 + i):
            tracker._handle(raw)


@pytest.mark.unit
class TestFavourite:
    def test_prefers_higher_mid(self, tracker):
        _feed_quotes(tracker, UP_ID, [(0.55, 0.60)])
        _feed_quotes(tracker, DOWN_ID, [(0.35, 0.40)])
        with patch("polyalpha.orderbook.tracker.time.time", return_value=100.0):
            assert tracker.favourite() == ("UP", pytest.approx(0.575))

    def test_prefers_down_when_higher(self, tracker):
        _feed_quotes(tracker, UP_ID, [(0.35, 0.40)])
        _feed_quotes(tracker, DOWN_ID, [(0.55, 0.60)])
        with patch("polyalpha.orderbook.tracker.time.time", return_value=100.0):
            assert tracker.favourite() == ("DOWN", pytest.approx(0.575))

    def test_exact_tie_returns_none(self, tracker):
        _feed_quotes(tracker, UP_ID, [(0.50, 0.60)])
        _feed_quotes(tracker, DOWN_ID, [(0.50, 0.60)])
        with patch("polyalpha.orderbook.tracker.time.time", return_value=100.0):
            assert tracker.favourite() == (None, None)

    def test_missing_side_returns_none(self, tracker):
        _feed_quotes(tracker, UP_ID, [(0.55, 0.60)])
        with patch("polyalpha.orderbook.tracker.time.time", return_value=100.0):
            assert tracker.favourite() == (None, None)


@pytest.mark.unit
class TestSpreadHistory:
    def test_book_event_records_spread(self, tracker):
        _feed_quotes(tracker, UP_ID, [(0.50, 0.60)])
        assert len(tracker.spread_history[UP_ID]) == 1
        s = tracker.spread_history[UP_ID][-1]
        assert s["spread"] == pytest.approx(0.10)
        assert s["bid"] == 0.50
        assert s["ask"] == 0.60

    def test_price_change_records_spread(self, tracker):
        tracker.best_bid[UP_ID] = 0.58
        raw = json.dumps({
            "event_type": "price_change",
            "price_changes": [{"asset_id": UP_ID, "best_ask": "0.61"}],
        })
        with patch("polyalpha.orderbook.tracker.time.time", return_value=200.0):
            tracker._handle(raw)
        assert len(tracker.spread_history[UP_ID]) == 1

    def test_missing_side_not_recorded(self, tracker):
        tracker.best_ask[UP_ID] = 0.60
        raw = json.dumps({
            "event_type": "book",
            "asset_id": UP_ID,
            "asks": [{"price": "0.60"}],
        })
        tracker._handle(raw)
        assert len(tracker.spread_history[UP_ID]) == 0

    def test_history_capped_at_120(self, tracker):
        _feed_quotes(tracker, UP_ID, [(0.50, 0.60)] * 150)
        assert len(tracker.spread_history[UP_ID]) == 120


@pytest.mark.unit
class TestSpreadStats:
    def test_needs_ten_samples(self, tracker):
        _feed_quotes(tracker, UP_ID, [(0.50, 0.60)] * 9)
        assert tracker.spread_stats(UP_ID) is None

    def test_mean_and_std(self, tracker):
        spreads = [0.10, 0.12, 0.08, 0.11, 0.09, 0.13, 0.07, 0.12, 0.10, 0.11]
        _feed_quotes(tracker, UP_ID, [(0.50, 0.50 + s) for s in spreads])
        mean, std = tracker.spread_stats(UP_ID)
        assert mean == pytest.approx(sum(spreads) / len(spreads))
        assert std == pytest.approx(statistics.pstdev(spreads))

    def test_unknown_token_returns_none(self, tracker):
        assert tracker.spread_stats("nope") is None


@pytest.mark.unit
class TestSpreadExpansion:
    def _populate(self, tracker, tid, spreads):
        # stable spread of 0.10, then a final jump to `spreads[-1]`
        _feed_quotes(tracker, tid, [(0.50, 0.60)] * 12)
        last = spreads[-1]
        _feed_quotes(tracker, tid, [(0.50, 0.50 + last)])

    def test_needs_ten_samples(self, tracker):
        _feed_quotes(tracker, UP_ID, [(0.50, 0.60)] * 9)
        assert tracker.spread_expansion(UP_ID) is None

    def test_no_expansion_returns_none(self, tracker):
        self._populate(tracker, UP_ID, [0.10])
        assert tracker.spread_expansion(UP_ID) is None

    def test_zero_std_returns_none(self, tracker):
        # constant spread => std == 0, never a widening
        _feed_quotes(tracker, UP_ID, [(0.50, 0.60)] * 13)
        assert tracker.spread_expansion(UP_ID) is None

    def test_ask_pull_returns_ask(self, tracker):
        # widen via a rising ask: baseline ask 0.60 -> cur ask 0.70
        self._populate(tracker, UP_ID, [0.20])
        result = tracker.spread_expansion(UP_ID)
        assert result is not None
        assert result["side_pulled"] == "ask"
        assert result["spread"] == pytest.approx(0.20)
        assert result["mean"] == pytest.approx((12 * 0.10 + 0.20) / 13)
        assert result["std"] > 0

    def test_bid_pull_returns_bid(self, tracker):
        # widen via a falling bid: baseline bid 0.50 -> cur bid 0.40
        for i in range(12):
            raw = json.dumps({
                "event_type": "book",
                "asset_id": UP_ID,
                "bids": [{"price": "0.50"}],
                "asks": [{"price": "0.60"}],
            })
            with patch("polyalpha.orderbook.tracker.time.time", return_value=100.0 + i):
                tracker._handle(raw)
        raw = json.dumps({
            "event_type": "book",
            "asset_id": UP_ID,
            "bids": [{"price": "0.40"}],
            "asks": [{"price": "0.60"}],
        })
        with patch("polyalpha.orderbook.tracker.time.time", return_value=112.0):
            tracker._handle(raw)
        result = tracker.spread_expansion(UP_ID)
        assert result is not None
        assert result["side_pulled"] == "bid"

    def test_unknown_token_returns_none(self, tracker):
        assert tracker.spread_expansion("nope") is None


@pytest.mark.unit
class TestSeedFromRest:
    def test_seeds_both_tokens(self, tracker):
        def fake_get(url, params=None):
            resp = MagicMock()
            if params["token_id"] == UP_ID:
                resp.json.return_value = {
                    "bids": [{"price": "0.55"}],
                    "asks": [{"price": "0.60"}],
                }
            else:
                resp.json.return_value = {
                    "bids": [{"price": "0.40"}],
                    "asks": [{"price": "0.45"}],
                }
            return resp

        tracker._http = MagicMock()
        tracker._http.get.side_effect = fake_get
        with patch("polyalpha.orderbook.tracker.time.time", return_value=100.0):
            tracker._seed_from_rest()
            assert tracker.best_bid[UP_ID] == 0.55
            assert tracker.best_ask[UP_ID] == 0.60
            assert tracker.best_bid[DOWN_ID] == 0.40
            assert tracker.best_ask[DOWN_ID] == 0.45
            assert tracker.fresh() is True

    def test_seed_failure_logs_and_keeps_going(self, tracker):
        tracker._http = MagicMock()
        tracker._http.get.side_effect = [Exception("boom"), MagicMock()]
        with patch("polyalpha.orderbook.tracker.log") as mock_log:
            tracker._seed_from_rest()
        assert mock_log.warning.called


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
    async def test_run_sends_subscription_and_applies_stream(self):
        tracker = TokenPairTracker(UP_ID, DOWN_ID)
        tracker._seed_from_rest = MagicMock()

        ws = _FakeWebSocket([
            json.dumps({
                "event_type": "price_change",
                "price_changes": [{"asset_id": UP_ID, "best_bid": "0.60", "best_ask": "0.65"}],
            }),
            "PONG",
        ], on_exhausted=lambda: setattr(tracker, "_stop", True))

        with patch("websockets.connect", return_value=ws), \
             patch.object(tracker._http, "get") as mock_get:
            mock_get.return_value.json.return_value = {
                "bids": [{"price": "0.55"}],
                "asks": [{"price": "0.60"}],
            }
            await tracker._run()

        # Subscription sent on connect
        sent = [c for c in ws.sent]
        assert any(isinstance(s, str) and "assets_ids" in s for s in sent)

        # Streamed price_change applied
        assert tracker.best_bid[UP_ID] == 0.60
        assert tracker.best_ask[UP_ID] == 0.65

    @pytest.mark.asyncio
    async def test_keepalive_sends_ping(self):
        tracker = TokenPairTracker(
            UP_ID,
            DOWN_ID,
            config=TokenPairTrackerConfig(ping_interval=0.001),
        )
        ws = _FakeWebSocket([])
        task = asyncio.create_task(tracker._keepalive(ws))
        await asyncio.sleep(0.05)  # let the 1ms keepalive timer fire
        task.cancel()
        with suppress(asyncio.CancelledError):
            await task
        assert "PING" in ws.sent

    @pytest.mark.asyncio
    async def test_run_reconnects_on_drop(self):
        tracker = TokenPairTracker(UP_ID, DOWN_ID)
        tracker._seed_from_rest = MagicMock()

        calls = {"n": 0}

        def fake_connect(*args, **kwargs):
            if calls["n"] == 0:
                calls["n"] += 1
                raise ConnectionError("drop")
            calls["n"] += 1
            tracker._stop = True  # exit loop after the reconnect
            return _FakeWebSocket(["PONG"])

        with patch("websockets.connect", side_effect=fake_connect), \
             patch("polyalpha.orderbook.tracker.asyncio.sleep", new=AsyncMock()):
            await tracker._run()

        assert calls["n"] == 2
