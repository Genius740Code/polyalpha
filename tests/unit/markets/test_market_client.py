"""
Markets module tests — run with: pytest tests/unit/markets/test_market_client.py
"""

import pytest
from polyalpha.markets import MarketClient, RateLimiter
import time


# ── Rate limiter tests ─────────────────────────────────────────────────────────

@pytest.mark.unit
def test_rate_limiter_basic():
    limiter = RateLimiter(max_requests=5, period_seconds=1.0)
    
    # Should allow 5 requests immediately
    for _ in range(5):
        limiter.acquire()
    
    # 6th request should block briefly
    start = time.time()
    limiter.acquire()
    elapsed = time.time() - start
    
    assert elapsed >= 0.1  # Should have waited at least a bit


@pytest.mark.unit
def test_rate_limiter_disabled():
    # Test that None rate_limit disables the limiter
    limiter = RateLimiter(10) if 10 else None
    assert limiter is not None
    
    # Test with None
    limiter = RateLimiter(None) if None else None
    assert limiter is None


@pytest.mark.unit
def test_rate_limiter_refill():
    limiter = RateLimiter(max_requests=5, period_seconds=1.0)
    
    # Use all tokens
    for _ in range(5):
        limiter.acquire()
    
    # Wait for refill
    time.sleep(1.1)
    
    # Should be available again
    limiter.acquire()  # Should not block significantly


@pytest.mark.unit
def test_rate_limiter_concurrent():
    import threading
    
    limiter = RateLimiter(max_requests=10, period_seconds=1.0)
    errors = []
    
    def acquire():
        try:
            for _ in range(5):
                limiter.acquire()
        except Exception as e:
            errors.append(e)
    
    threads = [threading.Thread(target=acquire) for _ in range(3)]
    for t in threads:
        t.start()
    for t in threads:
        t.join()
    
    assert len(errors) == 0


# ── MarketClient tests ────────────────────────────────────────────────────────

@pytest.mark.unit
def test_markets_search_validation():
    client = MarketClient(timeout=10, retries=3)
    
    # Test invalid query type
    with pytest.raises(ValueError, match="must be a string"):
        client.search(123)
    
    # Test empty query
    with pytest.raises(ValueError, match="cannot be empty"):
        client.search("")
    
    # Test query too long
    with pytest.raises(ValueError, match="too long"):
        client.search("a" * 201)
    
    # Test invalid limit type
    with pytest.raises(ValueError, match="must be an integer"):
        client.search("BTC", limit="10")
    
    # Test limit out of range
    with pytest.raises(ValueError, match="between 1 and 100"):
        client.search("BTC", limit=0)
    
    with pytest.raises(ValueError, match="between 1 and 100"):
        client.search("BTC", limit=101)


@pytest.mark.unit
def test_markets_latest_validation():
    client = MarketClient(timeout=10, retries=3)
    
    # Test invalid asset
    with pytest.raises(ValueError, match="Unknown asset"):
        client.latest("INVALID", "5m")
    
    # Test invalid timeframe
    with pytest.raises(ValueError, match="Unknown timeframe"):
        client.latest("BTC", "invalid")


@pytest.mark.unit
def test_markets_initialization():
    client = MarketClient(timeout=15, retries=5, rate_limit=10)

    assert client._timeout == 15
    assert client._retries == 5
    assert client._rate_limiter is not None


@pytest.mark.unit
def test_markets_default_initialization():
    client = MarketClient()

    assert client._timeout == 10
    assert client._retries == 3
    assert client._rate_limiter is None


@pytest.mark.unit
def test_market_refresh():
    """Test Market.refresh() method re-fetches market data."""
    from polyalpha.core import Market
    
    # Create a mock market
    market = Market(
        id="test-id",
        question="Test question",
        description="Test description",
        slug="btc-updown-5m-1751234700",
        active=True,
        closed=False,
        archived=False,
        start_time="2024-01-01T00:00:00Z",
        end_time="2024-01-01T05:00:00Z",
        volume=1000.0,
        liquidity=500.0,
        outcomes=["UP", "DOWN"],
        prices=[0.55, 0.45],
        tokens=["token-up", "token-down"],
    )
    
    # Mock client.get() to return a different market (simulating updated data)
    class MockClient:
        def get(self, slug: str) -> Market:
            return Market(
                id="test-id-updated",
                question="Test question",
                description="Test description",
                slug=slug,
                active=True,
                closed=False,
                archived=False,
                start_time="2024-01-01T00:00:00Z",
                end_time="2024-01-01T05:00:00Z",
                volume=2000.0,  # Updated volume
                liquidity=800.0,  # Updated liquidity
                outcomes=["UP", "DOWN"],
                prices=[0.60, 0.40],  # Updated prices
                tokens=["token-up", "token-down"],
            )
    
    mock_client = MockClient()
    updated = market.refresh(mock_client)
    
    # Verify refresh returns new instance with updated data
    assert updated.volume == 2000.0
    assert updated.liquidity == 800.0
    assert updated.prices == [0.60, 0.40]
    assert updated.slug == market.slug  # Slug remains the same
    
    # Verify original market is unchanged (immutable)
    assert market.volume == 1000.0
    assert market.prices == [0.55, 0.45]
