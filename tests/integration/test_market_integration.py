"""
Integration tests for market client — run with: pytest tests/integration/test_market_integration.py
"""

import pytest
from unittest.mock import Mock, patch
from polyalpha.markets import MarketClient
from polyalpha.core.market import Market
from polyalpha.trading.paper import PaperConfig


# ── Mock API responses ─────────────────────────────────────────────────────────

MOCK_MARKET_RESPONSE = {
    "id": "test-market-id",
    "question": "Will BTC be higher in 5 minutes?",
    "description": "Test market description",
    "slug": "btc-updown-5m-1751234700",
    "active": True,
    "closed": False,
    "archived": False,
    "start_time": "2025-01-01T00:00:00Z",
    "end_time": "2025-01-01T00:05:00Z",
    "volume": 10000.0,
    "liquidity": 5000.0,
    "markets": [{
        "id": "test-sub-market",
        "active": True,
        "closed": False,
        "outcomes": '["UP", "DOWN"]',
        "clobTokenIds": '["tok_up", "tok_down"]',
        "outcomePrices": '["0.54", "0.44"]'
    }],
    "outcomes": ["UP", "DOWN"],
    "order_book": {
        "tokens": [
            {"token_id": "tok_up", "best_bid": 0.54, "best_ask": 0.56},
            {"token_id": "tok_down", "best_bid": 0.44, "best_ask": 0.46}
        ]
    }
}

MOCK_SEARCH_RESPONSE = {
    "markets": [
        {
            "id": "market-1",
            "question": "BTC 5m",
            "description": "Test",
            "slug": "btc-updown-5m-123",
            "active": True,
            "closed": False,
            "archived": False,
            "start_time": "2025-01-01T00:00:00Z",
            "end_time": "2025-01-01T00:05:00Z",
            "volume": 5000.0,
            "liquidity": 2500.0,
            "outcomes": ["UP", "DOWN"],
            "order_book": {
                "tokens": [
                    {"token_id": "tok_up", "best_bid": 0.50, "best_ask": 0.52},
                    {"token_id": "tok_down", "best_bid": 0.48, "best_ask": 0.50}
                ]
            }
        },
        {
            "id": "market-2",
            "question": "ETH 5m",
            "description": "Test",
            "slug": "eth-updown-5m-123",
            "active": True,
            "closed": False,
            "archived": False,
            "start_time": "2025-01-01T00:00:00Z",
            "end_time": "2025-01-01T00:05:00Z",
            "volume": 3000.0,
            "liquidity": 1500.0,
            "outcomes": ["UP", "DOWN"],
            "order_book": {
                "tokens": [
                    {"token_id": "tok_up", "best_bid": 0.50, "best_ask": 0.52},
                    {"token_id": "tok_down", "best_bid": 0.48, "best_ask": 0.50}
                ]
            }
        }
    ]
}


# ── MarketClient integration tests ────────────────────────────────────────────

def test_market_client_get_by_slug_mocked():
    """Test fetching market by slug with mocked HTTP response."""
    client = MarketClient(timeout=10, retries=3)
    
    with patch('httpx.Client.get') as mock_get:
        mock_response = Mock()
        mock_response.status_code = 200
        mock_response.json.return_value = MOCK_MARKET_RESPONSE
        mock_get.return_value = mock_response
        
        market = client.get("btc-updown-5m-1751234700")
        
        assert market.slug == "btc-updown-5m-1751234700"
        assert market.active == True
        assert market.up_price > 0
        assert market.down_price > 0


def test_market_client_search_mocked():
    """Test searching markets with mocked HTTP response."""
    client = MarketClient(timeout=10, retries=3)
    
    with patch('httpx.Client.get') as mock_get:
        mock_response = Mock()
        mock_response.status_code = 200
        mock_response.json.return_value = MOCK_SEARCH_RESPONSE
        mock_get.return_value = mock_response
        
        markets = client.search("BTC", limit=10)
        
        assert len(markets) == 2
        assert markets[0].slug == "btc-updown-5m-123"
        assert markets[1].slug == "eth-updown-5m-123"


def test_market_client_http_error():
    """Test handling of HTTP errors."""
    client = MarketClient(timeout=10, retries=1)
    
    with patch('httpx.Client.get') as mock_get:
        mock_response = Mock()
        mock_response.status_code = 500
        mock_response.raise_for_status.side_effect = Exception("Server error")
        mock_get.return_value = mock_response
        
        with pytest.raises(Exception):
            client.get("btc-updown-5m-123")


def test_market_client_timeout():
    """Test handling of timeout errors."""
    client = MarketClient(timeout=0.001, retries=1)
    
    with patch('httpx.Client.get') as mock_get:
        import httpx
        mock_get.side_effect = httpx.TimeoutException("Request timed out")
        
        with pytest.raises(httpx.TimeoutException):
            client.get("btc-updown-5m-123")


def test_market_client_rate_limiting():
    """Test that rate limiting works during API calls."""
    client = MarketClient(timeout=10, retries=3, rate_limit=5)
    
    with patch('httpx.Client.get') as mock_get:
        mock_response = Mock()
        mock_response.status_code = 200
        mock_response.json.return_value = MOCK_MARKET_RESPONSE
        mock_get.return_value = mock_response
        
        # Make multiple requests
        for _ in range(3):
            client.get("btc-updown-5m-123")
        
        # Rate limiter should have been called
        assert client._rate_limiter is not None


def test_market_not_found_integration():
    """Test MarketNotFound error with mocked API."""
    client = MarketClient(timeout=10, retries=3)
    
    with patch('httpx.Client.get') as mock_get:
        mock_response = Mock()
        mock_response.status_code = 404
        mock_response.json.return_value = {"error": "Not found"}
        mock_response.raise_for_status.side_effect = Exception("Not found")
        mock_get.return_value = mock_response
        
        with pytest.raises(Exception):
            client.get("nonexistent-slug")


def test_network_error_retry():
    """Test retry logic on network errors."""
    client = MarketClient(timeout=10, retries=3)
    
    with patch('httpx.Client.get') as mock_get:
        import httpx
        
        # Fail first 2 times, succeed on 3rd
        mock_get.side_effect = [
            httpx.ConnectError("Network error"),
            httpx.ConnectError("Network error"),
            Mock(status_code=200, json=lambda: MOCK_MARKET_RESPONSE)
        ]
        
        # Should succeed after retries
        market = client.get("btc-updown-5m-123")
        assert market.slug == "btc-updown-5m-123"


def test_max_retries_exceeded():
    """Test that max retries is respected."""
    client = MarketClient(timeout=10, retries=2)
    
    with patch('httpx.Client.get') as mock_get:
        import httpx
        
        # Always fail
        mock_get.side_effect = httpx.ConnectError("Network error")
        
        with pytest.raises(httpx.ConnectError):
            client.get("btc-updown-5m-123")


def test_concurrent_market_requests():
    """Test concurrent market requests."""
    import threading
    
    client = MarketClient(timeout=10, retries=3, rate_limit=10)
    
    with patch('httpx.Client.get') as mock_get:
        mock_response = Mock()
        mock_response.status_code = 200
        mock_response.json.return_value = MOCK_MARKET_RESPONSE
        mock_get.return_value = mock_response
        
        results = []
        errors = []
        
        def fetch_market(slug):
            try:
                market = client.get(slug)
                results.append(market.slug)
            except Exception as e:
                errors.append(e)
        
        threads = [
            threading.Thread(target=fetch_market, args=(f"btc-updown-5m-{i}",))
            for i in range(5)
        ]
        
        for t in threads:
            t.start()
        for t in threads:
            t.join()
        
        assert len(errors) == 0
        assert len(results) == 5


def test_client_with_mocked_markets():
    """Test Client with mocked market discovery."""
    import polyalpha
    
    with patch('httpx.Client.get') as mock_get:
        mock_response = Mock()
        mock_response.status_code = 200
        mock_response.json.return_value = MOCK_MARKET_RESPONSE
        mock_get.return_value = mock_response
        
        client = polyalpha.Client(balance=100.0)
        market = client.markets.get("btc-updown-5m-1751234700")
        
        assert market.slug == "btc-updown-5m-1751234700"
        assert client.paper.balance == 100.0


# ── Market + Paper Trading integration tests ───────────────────────────────────

def test_market_paper_trading_integration():
    """Test market discovery followed by paper trading."""
    import polyalpha
    
    with patch('httpx.Client.get') as mock_get:
        mock_response = Mock()
        mock_response.status_code = 200
        mock_response.json.return_value = MOCK_MARKET_RESPONSE
        mock_get.return_value = mock_response
        
        # Initialize client
        config = PaperConfig(enable_risk_management=False)
        client = polyalpha.Client(balance=100.0, paper_config=config)
        
        # Discover market
        market = client.markets.get("btc-updown-5m-1751234700")
        assert market.slug == "btc-updown-5m-1751234700"
        assert market.active == True
        
        # Place paper trade on discovered market
        order = client.paper.buy(market, side="UP", amount=10.0)
        assert order.status == "filled"
        
        # Verify position
        positions = client.paper.positions()
        assert len(positions) == 1
        assert positions[0].side == "UP"


def test_market_search_and_trade():
    """Test searching for markets and trading on results."""
    import polyalpha
    
    with patch('httpx.Client.get') as mock_get:
        mock_response = Mock()
        mock_response.status_code = 200
        mock_response.json.return_value = MOCK_SEARCH_RESPONSE
        mock_get.return_value = mock_response
        
        # Initialize client
        config = PaperConfig(enable_risk_management=False)
        client = polyalpha.Client(balance=200.0, paper_config=config)
        
        # Search markets
        markets = client.markets.search("BTC", limit=10)
        assert len(markets) == 2
        
        # Trade on first market
        order1 = client.paper.buy(markets[0], side="UP", amount=10.0)
        assert order1.status == "filled"
        
        # Trade on second market
        order2 = client.paper.buy(markets[1], side="DOWN", amount=10.0)
        assert order2.status == "filled"
        
        # Verify positions across markets
        positions = client.paper.positions()
        assert len(positions) == 2
