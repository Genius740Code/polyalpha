"""
Tests for candle-aware trading guards — buy_once_per_candle & buy_in_window.

Covers both:
- ``BotHub.StrategyContext`` (multi-strategy hub)
- ``Bot.TickContext`` (single-bot)

Run with: pytest tests/unit/bots/test_candle_guards.py -v
"""

from unittest.mock import MagicMock

import pytest

from polyalpha.bot import TickContext
from polyalpha.bot_hub import StrategyContext


# ── Helpers ────────────────────────────────────────────────────────────────────

def make_mock_paper():
    paper = MagicMock()
    paper.balance = 1000.0
    paper.positions.return_value = []
    paper.all_positions.return_value = []
    paper.buy.return_value = MagicMock(status="filled")
    return paper


class FakeBot:
    """Minimal Bot stand-in for TickContext tests."""
    def __init__(self):
        self._client = MagicMock()
        self._client.paper = make_mock_paper()
        self._market = MagicMock()
        self._market.id = "test_market_id"
        self._market.slug = "btc-updown-5m-123"
        self._stream = None
        self._tick_count = 0
        self._trade_count = 0
        self._telegram = None
        self._candle_start_time = 1000.0
        self._candle_open_price = 0.5
        self._candle_id = 1
        self._bought_this_candle = {1: set()}
        self.buy_once_per_market = True
        self._bought_this_market = False


# ── Fixtures ───────────────────────────────────────────────────────────────────

@pytest.fixture
def fake_bot():
    return FakeBot()


@pytest.fixture
def tick_ctx(fake_bot):
    return TickContext(fake_bot)


@pytest.fixture
def strategy_ctx():
    bought: dict[int, dict[str, set[str]]] = {1: {}}
    ctx = StrategyContext(
        name="test_strat",
        stream=MagicMock(),
        paper=make_mock_paper(),
        market=MagicMock(),
        price_history=MagicMock(),
        asset="BTC",
        get_candle_open=lambda: 0.5,
        get_seconds_in=lambda: 30.0,
        get_candle_id=lambda: 1,
        bought_this_candle=bought,
    )
    return ctx


# ── TickContext tests ──────────────────────────────────────────────────────────

@pytest.mark.unit
class TestTickContextCandleGuards:
    def test_buy_once_per_candle_first_buy(self, tick_ctx):
        result = tick_ctx.buy_once_per_candle("UP", 20)
        assert result is not None
        assert result.status == "filled"
        assert "UP" in tick_ctx._bot._bought_this_candle[1]

    def test_buy_once_per_candle_skips_duplicate(self, tick_ctx):
        tick_ctx._bot._bought_this_candle[1].add("UP")
        result = tick_ctx.buy_once_per_candle("UP", 20)
        assert result is None

    def test_buy_once_per_candle_allows_opposite_side(self, tick_ctx):
        tick_ctx.buy_once_per_candle("UP", 20)
        result = tick_ctx.buy_once_per_candle("DOWN", 20)
        assert result is not None
        assert result.status == "filled"
        assert "DOWN" in tick_ctx._bot._bought_this_candle[1]

    def test_buy_once_per_candle_new_candle(self, tick_ctx):
        tick_ctx._bot._bought_this_candle[1].add("UP")
        tick_ctx._bot._candle_id = 2
        tick_ctx._bot._bought_this_candle[2] = set()
        result = tick_ctx.buy_once_per_candle("UP", 20)
        assert result is not None
        assert result.status == "filled"
        assert "UP" in tick_ctx._bot._bought_this_candle[2]

    def test_seconds_in_property(self, tick_ctx, fake_bot):
        fake_bot._candle_start_time = 0.0
        val = tick_ctx.seconds_in
        assert val > 0.0

    def test_candle_id_property(self, tick_ctx, fake_bot):
        fake_bot._candle_id = 5
        assert tick_ctx.candle_id == 5


# ── StrategyContext tests ──────────────────────────────────────────────────────

@pytest.mark.unit
class TestStrategyContextCandleGuards:
    def test_buy_once_per_candle_first_buy(self, strategy_ctx):
        result = strategy_ctx.buy_once_per_candle("UP", 20)
        assert result is not None
        assert result.status == "filled"
        assert "UP" in strategy_ctx._bought_this_candle[1]["test_strat"]

    def test_buy_once_per_candle_skips_duplicate(self, strategy_ctx):
        strategy_ctx._bought_this_candle[1]["test_strat"] = {"UP"}
        result = strategy_ctx.buy_once_per_candle("UP", 20)
        assert result is None

    def test_buy_once_per_candle_allows_opposite_side(self, strategy_ctx):
        strategy_ctx.buy_once_per_candle("UP", 20)
        result = strategy_ctx.buy_once_per_candle("DOWN", 20)
        assert result is not None
        assert result.status == "filled"
        assert strategy_ctx._bought_this_candle[1]["test_strat"] == {"UP", "DOWN"}

    def test_buy_once_per_candle_isolation_between_strategies(self, strategy_ctx):
        strategy_ctx._bought_this_candle[1]["other_strat"] = {"UP"}
        result = strategy_ctx.buy_once_per_candle("UP", 20)
        assert result is not None
        assert result.status == "filled"

    def test_buy_once_per_candle_new_candle(self, strategy_ctx):
        strategy_ctx._bought_this_candle[1]["test_strat"] = {"UP"}
        new_bought = strategy_ctx._bought_this_candle
        new_bought[2] = {}
        ctx2 = StrategyContext(
            name="test_strat",
            stream=MagicMock(),
            paper=make_mock_paper(),
            market=MagicMock(),
            price_history=MagicMock(),
            asset="BTC",
            get_candle_open=lambda: 0.6,
            get_seconds_in=lambda: 5.0,
            get_candle_id=lambda: 2,
            bought_this_candle=new_bought,
        )
        result = ctx2.buy_once_per_candle("UP", 20)
        assert result is not None
        assert result.status == "filled"
        assert "UP" in ctx2._bought_this_candle[2]["test_strat"]

    def test_buy_in_window_within_bounds(self, strategy_ctx):
        result = strategy_ctx.buy_in_window("UP", 20, 10, 60)
        assert result is not None
        assert result.status == "filled"

    def test_buy_in_window_before_min(self, strategy_ctx):
        result = strategy_ctx.buy_in_window("UP", 20, 60, 120)
        assert result is None

    def test_buy_in_window_after_max(self, strategy_ctx):
        result = strategy_ctx.buy_in_window("UP", 20, 0, 10)
        assert result is None

    def test_buy_in_window_at_boundary(self, strategy_ctx):
        strategy_ctx._get_seconds_in = lambda: 60.0
        result = strategy_ctx.buy_in_window("UP", 20, 0, 60)
        assert result is not None
        assert result.status == "filled"
