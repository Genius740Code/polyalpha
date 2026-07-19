"""
Trading-related fixtures for testing.

Provides fixtures for creating trading engines, orders, positions,
and trading configurations.
"""

import pytest
from unittest.mock import Mock, MagicMock
from datetime import datetime
from decimal import Decimal


@pytest.fixture(scope="function")
def mock_paper_engine():
    """Create a mock paper trading engine."""
    engine = Mock()
    engine.balance = Decimal("100000.0")
    engine.positions = {}
    engine.orders = {}
    engine.is_active = True
    engine.place_order = Mock()
    engine.cancel_order = Mock()
    engine.get_position = Mock()
    engine.get_portfolio_value = Mock(return_value=Decimal("100000.0"))
    return engine


@pytest.fixture(scope="function")
def mock_real_engine():
    """Create a mock real trading engine."""
    engine = Mock()
    engine.is_connected = True
    engine.wallet_id = "test_wallet_123"
    engine.place_order = Mock()
    engine.cancel_order = Mock()
    engine.get_position = Mock()
    engine.get_balance = Mock(return_value=Decimal("100000.0"))
    return engine


@pytest.fixture(scope="function")
def mock_order():
    """Create a mock order."""
    order = Mock()
    order.id = "order_123"
    order.symbol = "BTC-USD"
    order.side = "buy"
    order.quantity = Decimal("0.1")
    order.price = Decimal("50000.0")
    order.order_type = "limit"
    order.status = "open"
    order.timestamp = datetime.now()
    order.filled_quantity = Decimal("0.0")
    order.average_fill_price = Decimal("0.0")
    return order


@pytest.fixture(scope="function")
def mock_position():
    """Create a mock position."""
    position = Mock()
    position.symbol = "BTC-USD"
    position.quantity = Decimal("0.5")
    position.average_price = Decimal("45000.0")
    position.current_price = Decimal("50000.0")
    position.unrealized_pnl = Decimal("2500.0")
    return position


@pytest.fixture(scope="function")
def paper_trading_config():
    """Provide paper trading configuration."""
    return {
        "initial_balance": 100000.0,
        "fee_rate": 0.001,
        "slippage": 0.0001,
        "allow_short": False,
        "max_position_size": 10000.0,
    }


@pytest.fixture(scope="function")
def real_trading_config():
    """Provide real trading configuration."""
    return {
        "wallet_id": "test_wallet_123",
        "api_key": "test_api_key",
        "api_secret": "test_api_secret",
        "fee_rate": 0.001,
        "max_position_size": 10000.0,
    }


@pytest.fixture(scope="function")
def risk_management_config():
    """Provide risk management configuration."""
    return {
        "max_position_value": 10000.0,
        "max_daily_loss": 1000.0,
        "max_drawdown": 0.1,
        "stop_loss_percentage": 0.05,
        "take_profit_percentage": 0.1,
    }


@pytest.fixture(scope="function")
def order_book():
    """Create a mock order book."""
    book = Mock()
    book.bids = [
        {"price": 49999.0, "quantity": 1.0},
        {"price": 49998.0, "quantity": 2.0},
        {"price": 49997.0, "quantity": 3.0},
    ]
    book.asks = [
        {"price": 50001.0, "quantity": 1.0},
        {"price": 50002.0, "quantity": 2.0},
        {"price": 50003.0, "quantity": 3.0},
    ]
    book.best_bid = 49999.0
    book.best_ask = 50001.0
    book.spread = 2.0
    return book
