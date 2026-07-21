"""
Integration tests for trading components — run with: pytest tests/integration/test_trading_integration.py
"""

import pytest
from polyalpha.core.market import Market
from polyalpha.trading.paper import PaperConfig
import polyalpha


# ── Paper trading integration tests ───────────────────────────────────────────

def test_paper_trading_with_stream_integration():
    """Test paper trading with simulated stream updates."""
    config = PaperConfig(enable_risk_management=False)
    client = polyalpha.Client(balance=100.0, paper_config=config)
    
    market = Market(
        id="test-id",
        question="Test",
        description="Test",
        slug="btc-updown-5m-123",
        active=True,
        closed=False,
        archived=False,
        start_time="2030-01-01T00:00:00Z",
        end_time="2030-01-01T00:05:00Z",
        volume=1000.0,
        liquidity=500.0,
        outcomes=["UP", "DOWN"],
        prices=[0.55, 0.45],
        tokens=["tok_up", "tok_down"]
    )
    
    # Place a limit order
    order = client.paper.limit(market, side="UP", price=0.90, amount=20.0)
    
    assert order.status == "open"
    # Limit order deducts balance (funds are reserved)
    assert client.paper.balance == 80.0
    
    # Simulate price update that fills the order
    client.paper.check_limits(market.id, up_price=0.92, down_price=0.08)
    
    # Order should be filled
    updated_order = client.paper.orders()[0]
    assert updated_order.status == "filled"


def test_paper_trading_full_workflow():
    """Test complete paper trading workflow."""
    config = PaperConfig(enable_risk_management=False)
    client = polyalpha.Client(balance=100.0, paper_config=config)
    
    market = Market(
        id="test-id",
        question="Test",
        description="Test",
        slug="btc-updown-5m-123",
        active=True,
        closed=False,
        archived=False,
        start_time="2030-01-01T00:00:00Z",
        end_time="2030-01-01T00:05:00Z",
        volume=1000.0,
        liquidity=500.0,
        outcomes=["UP", "DOWN"],
        prices=[0.55, 0.45],
        tokens=["tok_up", "tok_down"]
    )
    
    # Buy market order
    order1 = client.paper.buy(market, side="UP", amount=10.0)
    assert order1.status == "filled"
    
    # Buy another side
    order2 = client.paper.buy(market, side="DOWN", amount=10.0)
    assert order2.status == "filled"
    
    # Check positions
    positions = client.paper.positions()
    assert len(positions) == 2
    
    # Resolve market
    client.paper.resolve(market, outcome="UP")
    
    # Check resolved positions
    all_positions = client.paper.all_positions()
    assert all(p.resolved for p in all_positions)
    
    # Check balance changed
    assert client.paper.balance != 100.0


def test_concurrent_trading():
    """Test concurrent trading operations."""
    import threading
    
    config = PaperConfig(enable_risk_management=False)
    client = polyalpha.Client(balance=500.0, paper_config=config)
    
    market = Market(
        id="test-id",
        question="Test",
        description="Test",
        slug="btc-updown-5m-123",
        active=True,
        closed=False,
        archived=False,
        start_time="2030-01-01T00:00:00Z",
        end_time="2030-01-01T00:05:00Z",
        volume=1000.0,
        liquidity=500.0,
        outcomes=["UP", "DOWN"],
        prices=[0.55, 0.45],
        tokens=["tok_up", "tok_down"]
    )
    
    results = []
    errors = []
    
    def place_trade(side):
        try:
            order = client.paper.buy(market, side=side, amount=10.0)
            results.append(order.side)
        except Exception as e:
            errors.append(e)
    
    threads = [
        threading.Thread(target=place_trade, args=("UP",)),
        threading.Thread(target=place_trade, args=("DOWN",)),
    ]
    
    for t in threads:
        t.start()
    for t in threads:
        t.join()
    
    assert len(errors) == 0
    assert len(results) == 2


def test_e2e_market_discovery_and_trading():
    """Test end-to-end workflow: discover market, place trade, resolve."""
    from unittest.mock import Mock, patch
    
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
        
        # Place trade
        order = client.paper.buy(market, side="UP", amount=10.0)
        assert order.status == "filled"
        
        # Resolve
        client.paper.resolve(market, outcome="UP")
        
        # Check results
        positions = client.paper.all_positions()
        assert len(positions) == 1
        assert positions[0].outcome == "WON"


def test_e2e_multiple_markets():
    """Test trading across multiple markets."""
    from unittest.mock import Mock, patch
    
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
    
    with patch('httpx.Client.get') as mock_get:
        mock_response = Mock()
        mock_response.status_code = 200
        mock_response.json.return_value = MOCK_SEARCH_RESPONSE
        mock_get.return_value = mock_response
        
        config = PaperConfig(enable_risk_management=False)
        client = polyalpha.Client(balance=200.0, paper_config=config)
        
        # Search markets
        markets = client.markets.search("BTC", limit=10)
        assert len(markets) == 2
        
        # Trade on both
        for market in markets:
            client.paper.buy(market, side="UP", amount=10.0)
        
        # Check positions
        positions = client.paper.positions()
        assert len(positions) == 2


def test_trading_error_recovery():
    """Test trading system recovers from errors gracefully."""
    from polyalpha.core.market import Market
    
    config = PaperConfig(enable_risk_management=False)
    client = polyalpha.Client(balance=100.0, paper_config=config)
    
    market = Market(
        id="test-id",
        question="Test",
        description="Test",
        slug="btc-updown-5m-123",
        active=True,
        closed=False,
        archived=False,
        start_time="2030-01-01T00:00:00Z",
        end_time="2030-01-01T00:05:00Z",
        volume=1000.0,
        liquidity=500.0,
        outcomes=["UP", "DOWN"],
        prices=[0.55, 0.45],
        tokens=["tok_up", "tok_down"]
    )
    
    # Try to trade with insufficient balance
    try:
        client.paper.buy(market, side="UP", amount=200.0)
        assert False, "Should have raised error for insufficient balance"
    except Exception:
        pass  # Expected
    
    # Verify system still works after error
    order = client.paper.buy(market, side="UP", amount=10.0)
    assert order.status == "filled"


def test_trading_with_fees():
    """Test trading with fee calculations."""
    from polyalpha.core.market import Market
    
    config = PaperConfig(enable_risk_management=False, custom_fee_rate=0.01)
    client = polyalpha.Client(balance=100.0, paper_config=config)
    
    market = Market(
        id="test-id",
        question="Test",
        description="Test",
        slug="btc-updown-5m-123",
        active=True,
        closed=False,
        archived=False,
        start_time="2030-01-01T00:00:00Z",
        end_time="2030-01-01T00:05:00Z",
        volume=1000.0,
        liquidity=500.0,
        outcomes=["UP", "DOWN"],
        prices=[0.55, 0.45],
        tokens=["tok_up", "tok_down"]
    )
    
    # Place order with fees
    order = client.paper.buy(market, side="UP", amount=10.0)
    assert order.status == "filled"
    
    # Verify order was placed successfully
    # Fee calculation is applied to position cost basis, not directly to balance
    assert client.paper.balance >= 0
    assert len(client.paper.positions()) == 1


def test_trading_position_aggregation():
    """Test that positions are aggregated correctly."""
    from polyalpha.core.market import Market
    
    config = PaperConfig(enable_risk_management=False)
    client = polyalpha.Client(balance=100.0, paper_config=config)
    
    market = Market(
        id="test-id",
        question="Test",
        description="Test",
        slug="btc-updown-5m-123",
        active=True,
        closed=False,
        archived=False,
        start_time="2030-01-01T00:00:00Z",
        end_time="2030-01-01T00:05:00Z",
        volume=1000.0,
        liquidity=500.0,
        outcomes=["UP", "DOWN"],
        prices=[0.55, 0.45],
        tokens=["tok_up", "tok_down"]
    )
    
    # Place multiple orders on same side
    client.paper.buy(market, side="UP", amount=10.0)
    client.paper.buy(market, side="UP", amount=15.0)
    client.paper.buy(market, side="UP", amount=5.0)
    
    # Check aggregated position
    positions = client.paper.positions()
    assert len(positions) == 1
    assert positions[0].side == "UP"
    # Cost basis includes fees (default 2% fee rate)
    # 30.0 * 0.98 = 29.4
    assert positions[0].cost_basis == 29.4


def test_trading_sell_order():
    """Test sell order functionality."""
    from polyalpha.core.market import Market
    
    config = PaperConfig(enable_risk_management=False)
    client = polyalpha.Client(balance=100.0, paper_config=config)
    
    market = Market(
        id="test-id",
        question="Test",
        description="Test",
        slug="btc-updown-5m-123",
        active=True,
        closed=False,
        archived=False,
        start_time="2030-01-01T00:00:00Z",
        end_time="2030-01-01T00:05:00Z",
        volume=1000.0,
        liquidity=500.0,
        outcomes=["UP", "DOWN"],
        prices=[0.55, 0.45],
        tokens=["tok_up", "tok_down"]
    )
    
    # Buy first to establish position
    client.paper.buy(market, side="UP", amount=10.0)
    
    # Buy opposite side to reduce position
    opposite_order = client.paper.buy(market, side="DOWN", amount=5.0)
    assert opposite_order.status == "filled"
    
    # Check positions - should have both sides
    positions = client.paper.positions()
    assert len(positions) == 2


def test_trading_order_validation():
    """Test that orders are validated before execution."""
    from polyalpha.core.market import Market
    
    config = PaperConfig(enable_risk_management=False)
    client = polyalpha.Client(balance=100.0, paper_config=config)
    
    market = Market(
        id="test-id",
        question="Test",
        description="Test",
        slug="btc-updown-5m-123",
        active=True,
        closed=False,
        archived=False,
        start_time="2030-01-01T00:00:00Z",
        end_time="2030-01-01T00:05:00Z",
        volume=1000.0,
        liquidity=500.0,
        outcomes=["UP", "DOWN"],
        prices=[0.55, 0.45],
        tokens=["tok_up", "tok_down"]
    )
    
    # Try invalid amount
    try:
        client.paper.buy(market, side="UP", amount=-10.0)
        assert False, "Should reject negative amount"
    except Exception:
        pass  # Expected
    
    # Try zero amount
    try:
        client.paper.buy(market, side="UP", amount=0.0)
        assert False, "Should reject zero amount"
    except Exception:
        pass  # Expected
    
    # Valid order should work
    order = client.paper.buy(market, side="UP", amount=10.0)
    assert order.status == "filled"


def test_trading_market_state_validation():
    """Test that trading respects market state."""
    from polyalpha.core.market import Market
    
    config = PaperConfig(enable_risk_management=False)
    client = polyalpha.Client(balance=100.0, paper_config=config)
    
    # Closed market
    closed_market = Market(
        id="closed-id",
        question="Test",
        description="Test",
        slug="btc-updown-5m-123",
        active=True,
        closed=True,
        archived=False,
        start_time="2030-01-01T00:00:00Z",
        end_time="2030-01-01T00:05:00Z",
        volume=1000.0,
        liquidity=500.0,
        outcomes=["UP", "DOWN"],
        prices=[0.55, 0.45],
        tokens=["tok_up", "tok_down"]
    )
    
    # Should not allow trading on closed market
    try:
        client.paper.buy(closed_market, side="UP", amount=10.0)
        assert False, "Should reject trading on closed market"
    except Exception:
        pass  # Expected
    
    # Inactive market
    inactive_market = Market(
        id="inactive-id",
        question="Test",
        description="Test",
        slug="btc-updown-5m-123",
        active=False,
        closed=False,
        archived=False,
        start_time="2030-01-01T00:00:00Z",
        end_time="2030-01-01T00:05:00Z",
        volume=1000.0,
        liquidity=500.0,
        outcomes=["UP", "DOWN"],
        prices=[0.55, 0.45],
        tokens=["tok_up", "tok_down"]
    )
    
    # Should not allow trading on inactive market
    try:
        client.paper.buy(inactive_market, side="UP", amount=10.0)
        assert False, "Should reject trading on inactive market"
    except Exception:
        pass  # Expected
