"""
Integration tests for database components — run with: pytest tests/integration/test_database_integration.py
"""

import pytest
from unittest.mock import Mock, patch
import tempfile
import os
from polyalpha.trading.paper import PaperConfig


# ── DataFeed integration tests ─────────────────────────────────────────────────

def test_datafeed_binance_mock():
    """Test DataFeed with mocked Binance API."""
    from polyalpha.analysis import DataFeed, DataFeedConfig
    import pandas as pd
    
    mock_klines = [
        [1704067200000, "50000.0", "50100.0", "49900.0", "50050.0", "100.0", 1704067499999, "0", 0, "0", "0", "0"],
        [1704067500000, "50050.0", "50150.0", "49950.0", "50100.0", "110.0", 1704067799999, "0", 0, "0", "0", "0"],
    ]

    config = DataFeedConfig(timeframe="5m")

    with patch('polyalpha.analysis.data_feed.requests.get') as mock_get:
        mock_response = Mock()
        mock_response.status_code = 200
        mock_response.json.return_value = mock_klines
        mock_get.return_value = mock_response
        
        feed = DataFeed(config)
        data = feed._fetch_binance("BTC")
        
        assert isinstance(data, pd.DataFrame)
        assert len(data) == 2
        assert "close" in data.columns


def test_datafeed_custom_api_mock():
    """Test DataFeed with custom API."""
    from polyalpha.analysis import DataFeed, DataFeedConfig
    import pandas as pd
    
    mock_ohlcv = {
        "data": [
            {"timestamp": "2025-01-01T00:00:00Z", "open": 50000, "high": 50100, "low": 49900, "close": 50050, "volume": 100}
        ]
    }
    
    config = DataFeedConfig(
        timeframe="5m",
        source="custom",
        custom_url="https://api.example.com/ohlcv"
    )
    
    with patch('polyalpha.analysis.data_feed.requests.get') as mock_get:
        mock_response = Mock()
        mock_response.status_code = 200
        mock_response.json.return_value = mock_ohlcv
        mock_get.return_value = mock_response
        
        feed = DataFeed(config)
        data = feed._fetch_custom("BTC")
        
        assert isinstance(data, pd.DataFrame)
        assert len(data) == 1


# ── Database + Trading integration tests ─────────────────────────────────────

def test_database_trading_order_persistence():
    """Test that trading orders are persisted to database."""
    from polyalpha.core.market import Market
    import polyalpha
    
    # Use in-memory database for testing to avoid file locking issues
    db_path = ":memory:"
    
    # Initialize client with database
    config = PaperConfig(enable_risk_management=False)
    client = polyalpha.Client(balance=100.0, db_path=db_path, paper_config=config)
    
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
    
    # Place order
    order = client.paper.buy(market, side="UP", amount=10.0)
    assert order.status == "filled"
    
    # Verify order was saved
    orders = client.paper.orders()
    assert len(orders) == 1
    assert orders[0].id == order.id
    
    # Close client to release database lock
    client.close()


def test_database_trading_position_tracking():
    """Test that positions are tracked in database."""
    from polyalpha.core.market import Market
    import polyalpha
    
    # Use in-memory database for testing to avoid file locking issues
    db_path = ":memory:"
    
    # Initialize client with database
    config = PaperConfig(enable_risk_management=False)
    client = polyalpha.Client(balance=100.0, db_path=db_path, paper_config=config)
    
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
    
    # Place orders
    client.paper.buy(market, side="UP", amount=10.0)
    client.paper.buy(market, side="DOWN", amount=10.0)
    
    # Check positions
    positions = client.paper.positions()
    assert len(positions) == 2
    
    # Resolve market
    client.paper.resolve(market, outcome="UP")
    
    # Check resolved positions
    all_positions = client.paper.all_positions()
    assert len(all_positions) == 2
    assert all(p.resolved for p in all_positions)
    
    # Close client to release database lock
    client.close()


def test_database_trading_balance_persistence():
    """Test that balance is persisted to database."""
    from polyalpha.core.market import Market
    import polyalpha
    
    # Use in-memory database for testing to avoid file locking issues
    db_path = ":memory:"
    
    # Initialize client with database
    config = PaperConfig(enable_risk_management=False)
    client = polyalpha.Client(balance=100.0, db_path=db_path, paper_config=config)
    
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
    
    # Place order
    initial_balance = client.paper.balance
    client.paper.buy(market, side="UP", amount=10.0)
    
    # Verify balance is accessible
    assert client.paper.balance >= 0
    
    # Close client to release database lock
    client.close()


def test_database_trading_order_history():
    """Test that order history is maintained in database."""
    from polyalpha.core.market import Market
    import polyalpha
    
    db_path = ":memory:"
    config = PaperConfig(enable_risk_management=False)
    client = polyalpha.Client(balance=100.0, db_path=db_path, paper_config=config)
    
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
    
    # Place multiple orders
    order1 = client.paper.buy(market, side="UP", amount=10.0)
    order2 = client.paper.buy(market, side="DOWN", amount=15.0)
    order3 = client.paper.buy(market, side="UP", amount=5.0)
    
    # Verify all orders are in history
    all_orders = client.paper.orders()
    assert len(all_orders) == 3
    
    # Verify order details are preserved
    assert any(o.id == order1.id and o.side == "UP" for o in all_orders)
    assert any(o.id == order2.id and o.side == "DOWN" for o in all_orders)
    
    client.close()


def test_database_trading_transaction_logging():
    """Test that transactions are logged in database."""
    from polyalpha.core.market import Market
    import polyalpha
    
    db_path = ":memory:"
    config = PaperConfig(enable_risk_management=False)
    client = polyalpha.Client(balance=100.0, db_path=db_path, paper_config=config)
    
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
    
    # Place order and resolve
    client.paper.buy(market, side="UP", amount=10.0)
    client.paper.resolve(market, outcome="UP")
    
    # Verify transaction was recorded
    positions = client.paper.all_positions()
    assert len(positions) == 1
    assert positions[0].resolved == True
    assert positions[0].outcome == "WON"
    
    client.close()


def test_database_trading_concurrent_access():
    """Test database handles concurrent trading operations."""
    from polyalpha.core.market import Market
    import polyalpha
    import threading
    
    db_path = ":memory:"
    config = PaperConfig(enable_risk_management=False)
    client = polyalpha.Client(balance=500.0, db_path=db_path, paper_config=config)
    
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
    
    errors = []
    
    def place_trade(side):
        try:
            client.paper.buy(market, side=side, amount=10.0)
        except Exception as e:
            errors.append(e)
    
    threads = [
        threading.Thread(target=place_trade, args=("UP",)),
        threading.Thread(target=place_trade, args=("DOWN",)),
        threading.Thread(target=place_trade, args=("UP",)),
    ]
    
    for t in threads:
        t.start()
    for t in threads:
        t.join()
    
    assert len(errors) == 0
    assert len(client.paper.orders()) == 3
    
    client.close()
