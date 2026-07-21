"""
Tests for price-aware buy() functionality with attached streams.
"""

import pytest
from unittest.mock import Mock
from datetime import datetime, timezone, timedelta

from polyalpha.trading.paper import PaperEngine, PaperConfig

pytestmark = pytest.mark.unit


def _make_engine():
    config = PaperConfig(enable_risk_management=False)
    return PaperEngine(balance=100.0, config=config)


def _make_market(**kwargs):
    m = Mock()
    m.id = kwargs.get("id", "test-market")
    m.slug = kwargs.get("slug", "test-market")
    m.question = kwargs.get("question", "Test question")
    m.up_price = kwargs.get("up_price", 0.55)
    m.down_price = kwargs.get("down_price", 0.45)
    m.end_time = kwargs.get("end_time", None)
    return m


class TestPriceAwareBuy:

    def test_buy_without_stream_uses_market_price(self):
        engine = _make_engine()
        market = _make_market()

        order = engine.buy(market, side="UP", amount=10.0)

        assert order.price == 0.55
        assert order.status == "filled"

    def test_buy_with_running_stream_uses_stream_price(self):
        engine = _make_engine()
        market = _make_market(id="test-market-2")

        stream = Mock()
        stream.up = 0.60
        stream.down = 0.40
        stream.running = True

        engine._attached_streams[market.id] = stream

        order = engine.buy(market, side="UP", amount=10.0)

        assert order.price == 0.60
        assert order.status == "filled"

    def test_buy_with_stopped_stream_uses_market_price(self):
        engine = _make_engine()
        market = _make_market(id="test-market-3")

        stream = Mock()
        stream.up = 0.60
        stream.down = 0.40
        stream.running = False

        engine._attached_streams[market.id] = stream

        order = engine.buy(market, side="UP", amount=10.0)

        assert order.price == 0.55
        assert order.status == "filled"

    def test_buy_with_stream_zero_price_falls_back(self):
        engine = _make_engine()
        market = _make_market(id="test-market-4")

        stream = Mock()
        stream.up = 0.0
        stream.down = 0.0
        stream.running = True

        engine._attached_streams[market.id] = stream

        order = engine.buy(market, side="UP", amount=10.0)

        assert order.price == 0.55
        assert order.status == "filled"

    def test_get_price_for_side_with_stream(self):
        engine = _make_engine()
        market = _make_market(id="test-market-5")

        stream = Mock()
        stream.up = 0.70
        stream.down = 0.30
        stream.running = True

        engine._attached_streams[market.id] = stream

        price, source = engine._get_price_for_side(market, "UP")

        assert price == 0.70
        assert source == "stream"

    def test_get_price_for_side_without_stream(self):
        engine = _make_engine()
        market = _make_market(id="test-market-6")

        price, source = engine._get_price_for_side(market, "UP")

        assert price == 0.55
        assert source == "market"

    def test_get_price_for_side_with_stale_market(self):
        engine = _make_engine()
        end_time = datetime.now(timezone.utc) + timedelta(seconds=10)
        market = _make_market(id="test-market-7", end_time=end_time.isoformat())

        price, source = engine._get_price_for_side(market, "UP")

        assert price == 0.55
        assert source == "market"

    def test_get_price_for_side_with_closed_market(self):
        engine = _make_engine()
        end_time = datetime.now(timezone.utc) - timedelta(seconds=60)
        market = _make_market(id="test-market-8", end_time=end_time.isoformat())

        price, source = engine._get_price_for_side(market, "UP")

        assert price == 0.55
        assert source == "market"

    def test_attach_stream_tracks_reference(self):
        engine = _make_engine()
        market = _make_market(id="test-market-9")

        stream = Mock()
        stream.on = Mock(return_value=lambda fn: fn)

        engine.attach_stream(stream, market)

        assert market.id in engine._attached_streams
        assert engine._attached_streams[market.id] == stream

    def test_detach_stream_on_close(self):
        engine = _make_engine()
        market = _make_market(id="test-market-10")

        stream = Mock()
        stream.on = Mock(return_value=lambda fn: fn)

        engine.attach_stream(stream, market)

        engine._attached_streams.pop(market.id, None)

        assert market.id not in engine._attached_streams
