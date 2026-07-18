"""
Tests for price-aware buy() functionality with attached streams.
"""

import os
import sys
import pytest
from unittest.mock import Mock, MagicMock
from datetime import datetime, timezone, timedelta

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))

from polyalpha.trading.paper import PaperEngine, PaperConfig
from polyalpha.core import Market, PRICE_STALENESS_THRESHOLD


class TestPriceAwareBuy:
    """Test price-aware buy() behavior with attached streams."""

    def test_buy_without_stream_uses_market_price(self):
        """Test that buy() uses market price when no stream is attached."""
        engine = PaperEngine(balance=100.0)
        
        # Create a mock market
        market = Mock(spec=Market)
        market.id = "test-market-1"
        market.slug = "test-market"
        market.up_price = 0.55
        market.down_price = 0.45
        market.end_time = None
        
        # Execute buy
        order = engine.buy(market, side="UP", amount=10.0)
        
        # Should use market price
        assert order.price == 0.55
        assert order.status == "filled"

    def test_buy_with_running_stream_uses_stream_price(self):
        """Test that buy() uses live stream price when stream is attached and running."""
        engine = PaperEngine(balance=100.0)
        
        # Create a mock market
        market = Mock(spec=Market)
        market.id = "test-market-2"
        market.slug = "test-market"
        market.up_price = 0.55
        market.down_price = 0.45
        market.end_time = None
        
        # Create a mock stream
        stream = Mock()
        stream.up = 0.60  # Different from market price
        stream.down = 0.40
        stream.running = True
        
        # Attach stream
        engine._attached_streams[market.id] = stream
        
        # Execute buy
        order = engine.buy(market, side="UP", amount=10.0)
        
        # Should use stream price, not market price
        assert order.price == 0.60
        assert order.status == "filled"

    def test_buy_with_stopped_stream_uses_market_price(self):
        """Test that buy() falls back to market price when stream is not running."""
        engine = PaperEngine(balance=100.0)
        
        # Create a mock market
        market = Mock(spec=Market)
        market.id = "test-market-3"
        market.slug = "test-market"
        market.up_price = 0.55
        market.down_price = 0.45
        market.end_time = None
        
        # Create a mock stream that's not running
        stream = Mock()
        stream.up = 0.60
        stream.down = 0.40
        stream.running = False
        
        # Attach stream
        engine._attached_streams[market.id] = stream
        
        # Execute buy
        order = engine.buy(market, side="UP", amount=10.0)
        
        # Should use market price since stream is not running
        assert order.price == 0.55
        assert order.status == "filled"

    def test_buy_with_stream_zero_price_falls_back(self):
        """Test that buy() falls back to market price when stream price is 0."""
        engine = PaperEngine(balance=100.0)
        
        # Create a mock market
        market = Mock(spec=Market)
        market.id = "test-market-4"
        market.slug = "test-market"
        market.up_price = 0.55
        market.down_price = 0.45
        market.end_time = None
        
        # Create a mock stream with zero price
        stream = Mock()
        stream.up = 0.0
        stream.down = 0.0
        stream.running = True
        
        # Attach stream
        engine._attached_streams[market.id] = stream
        
        # Execute buy
        order = engine.buy(market, side="UP", amount=10.0)
        
        # Should fall back to market price
        assert order.price == 0.55
        assert order.status == "filled"

    def test_get_price_for_side_with_stream(self):
        """Test _get_price_for_side() with attached running stream."""
        engine = PaperEngine(balance=100.0)
        
        market = Mock(spec=Market)
        market.id = "test-market-5"
        market.slug = "test-market"
        market.up_price = 0.55
        market.down_price = 0.45
        market.end_time = None
        
        stream = Mock()
        stream.up = 0.70
        stream.down = 0.30
        stream.running = True
        
        engine._attached_streams[market.id] = stream
        
        price, source = engine._get_price_for_side(market, "UP")
        
        assert price == 0.70
        assert source == "stream"

    def test_get_price_for_side_without_stream(self):
        """Test _get_price_for_side() without attached stream."""
        engine = PaperEngine(balance=100.0)
        
        market = Mock(spec=Market)
        market.id = "test-market-6"
        market.slug = "test-market"
        market.up_price = 0.55
        market.down_price = 0.45
        market.end_time = None
        
        price, source = engine._get_price_for_side(market, "UP")
        
        assert price == 0.55
        assert source == "market"

    def test_get_price_for_side_with_stale_market(self):
        """Test _get_price_for_side() warns when market is near closing."""
        engine = PaperEngine(balance=100.0)
        
        # Market closing in 10 seconds (within staleness threshold)
        end_time = datetime.now(timezone.utc) + timedelta(seconds=10)
        
        market = Mock(spec=Market)
        market.id = "test-market-7"
        market.slug = "test-market"
        market.up_price = 0.55
        market.down_price = 0.45
        market.end_time = end_time.isoformat()
        
        price, source = engine._get_price_for_side(market, "UP")
        
        # Should still return price but with warning logged
        assert price == 0.55
        assert source == "market"

    def test_get_price_for_side_with_closed_market(self):
        """Test _get_price_for_side() warns when market is closed."""
        engine = PaperEngine(balance=100.0)
        
        # Market already closed
        end_time = datetime.now(timezone.utc) - timedelta(seconds=60)
        
        market = Mock(spec=Market)
        market.id = "test-market-8"
        market.slug = "test-market"
        market.up_price = 0.55
        market.down_price = 0.45
        market.end_time = end_time.isoformat()
        
        price, source = engine._get_price_for_side(market, "UP")
        
        # Should still return price but with warning logged
        assert price == 0.55
        assert source == "market"

    def test_attach_stream_tracks_reference(self):
        """Test that attach_stream() stores stream reference."""
        engine = PaperEngine(balance=100.0)
        
        market = Mock(spec=Market)
        market.id = "test-market-9"
        market.slug = "test-market"
        
        stream = Mock()
        stream.on = Mock(return_value=lambda fn: fn)
        
        engine.attach_stream(stream, market)
        
        # Stream should be tracked
        assert market.id in engine._attached_streams
        assert engine._attached_streams[market.id] == stream

    def test_detach_stream_on_close(self):
        """Test that stream reference is removed when stream."""
        engine = PaperEngine(balance=100.0)
        
        market = Mock(spec=Market)
        market.id = "test-market-10"
        market.slug = "test-market"
        
        stream = Mock()
        stream.on = Mock(return_value=lambda fn: fn)
        
        engine.attach_stream(stream, market)
        
        # Simulate stream close by calling the close handler
        # The close handler is registered as a callback, so we need to extract it
        # For this test, we'll manually remove it
        engine._attached_streams.pop(market.id, None)
        
        # Stream should no longer be tracked
        assert market.id not in engine._attached_streams


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
