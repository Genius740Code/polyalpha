"""
Market-related fixtures for testing.

Provides fixtures for creating market instances, market data,
and market sessions.
"""

import pytest
from unittest.mock import Mock, MagicMock
from datetime import datetime, timedelta


@pytest.fixture(scope="function")
def mock_market():
    """Create a mock market instance."""
    market = Mock()
    market.symbol = "BTC-USD"
    market.base_currency = "BTC"
    market.quote_currency = "USD"
    market.price = 50000.0
    market.bid = 49999.0
    market.ask = 50001.0
    market.volume = 100.0
    market.timestamp = datetime.now()
    return market


@pytest.fixture(scope="function")
def mock_market_session():
    """Create a mock market session."""
    session = Mock()
    session.is_connected = True
    session.symbol = "BTC-USD"
    session.last_ping = datetime.now()
    session.connect = Mock()
    session.disconnect = Mock()
    session.subscribe = Mock()
    session.unsubscribe = Mock()
    return session


@pytest.fixture(scope="function")
def sample_market_data_list():
    """Provide a list of sample market data points."""
    base_time = datetime.now()
    return [
        {
            "symbol": "BTC-USD",
            "price": 50000.0 + i * 10,
            "bid": 49999.0 + i * 10,
            "ask": 50001.0 + i * 10,
            "volume": 100.0 + i,
            "timestamp": base_time + timedelta(seconds=i),
        }
        for i in range(10)
    ]


@pytest.fixture(scope="function")
def mock_market_client():
    """Create a mock market client."""
    client = Mock()
    client.get_markets = Mock(return_value=[])
    client.get_market = Mock(return_value=mock_market())
    client.subscribe = Mock()
    client.unsubscribe = Mock()
    client.connect = Mock()
    client.disconnect = Mock()
    client.is_connected = True
    return client


@pytest.fixture(scope="function")
def multi_market_data():
    """Provide sample data for multiple markets."""
    return {
        "BTC-USD": {"price": 50000.0, "bid": 49999.0, "ask": 50001.0},
        "ETH-USD": {"price": 3000.0, "bid": 2999.0, "ask": 3001.0},
        "SOL-USD": {"price": 100.0, "bid": 99.0, "ask": 101.0},
    }
