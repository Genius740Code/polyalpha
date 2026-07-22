"""
Bot tests — run with: pytest tests/unit/bots/test_bot.py
"""

from unittest.mock import MagicMock, patch

import pytest

from polyalpha.bot import TickContext


class FakeBot:
    """Minimal Bot stand-in for TickContext tests."""
    def __init__(self):
        self._client = MagicMock()
        self._market = MagicMock()
        self._market.id = "test_market_id"
        self._market.slug = "btc-updown-5m-123"
        self._stream = None
        self._tick_count = 0
        self._trade_count = 0


@pytest.fixture
def fake_bot():
    return FakeBot()


@pytest.mark.unit
class TestTickContextClosePosition:
    def test_close_position_calls_sell_position(self, fake_bot):
        ctx = TickContext(fake_bot)
        ctx.close_position("UP")
        fake_bot._client.paper.sell_position.assert_called_once_with(
            market=fake_bot._market, side="UP", amount=None
        )

    def test_close_position_with_amount(self, fake_bot):
        ctx = TickContext(fake_bot)
        ctx.close_position("UP", amount=50.0)
        fake_bot._client.paper.sell_position.assert_called_once_with(
            market=fake_bot._market, side="UP", amount=50.0
        )

    def test_close_position_down_side(self, fake_bot):
        ctx = TickContext(fake_bot)
        ctx.close_position("DOWN")
        fake_bot._client.paper.sell_position.assert_called_once_with(
            market=fake_bot._market, side="DOWN", amount=None
        )

    def test_close_position_returns_order(self, fake_bot):
        fake_order = MagicMock()
        fake_order.status = "filled"
        fake_bot._client.paper.sell_position.return_value = fake_order
        ctx = TickContext(fake_bot)
        result = ctx.close_position("UP")
        assert result.status == "filled"
