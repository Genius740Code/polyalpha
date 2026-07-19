"""
Database-related fixtures for testing.

Provides fixtures for creating temporary databases, database connections,
and database test data.
"""

import pytest
import sqlite3
import tempfile
from pathlib import Path
from unittest.mock import Mock, MagicMock


@pytest.fixture(scope="function")
def temp_database(tmp_path):
    """Create a temporary SQLite database for testing."""
    db_path = tmp_path / "test.db"
    conn = sqlite3.connect(str(db_path))
    
    # Create basic tables
    cursor = conn.cursor()
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS users (
            id INTEGER PRIMARY KEY,
            username TEXT UNIQUE,
            email TEXT UNIQUE,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    """)
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS orders (
            id INTEGER PRIMARY KEY,
            symbol TEXT,
            side TEXT,
            quantity REAL,
            price REAL,
            status TEXT,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    """)
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS positions (
            id INTEGER PRIMARY KEY,
            symbol TEXT,
            quantity REAL,
            average_price REAL,
            updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    """)
    conn.commit()
    
    yield conn
    
    conn.close()


@pytest.fixture(scope="function")
def mock_database_connection():
    """Create a mock database connection."""
    conn = Mock()
    cursor = Mock()
    conn.cursor.return_value = cursor
    conn.execute = Mock()
    conn.commit = Mock()
    conn.rollback = Mock()
    conn.close = Mock()
    return conn


@pytest.fixture(scope="function")
def sample_database_data():
    """Provide sample data for database testing."""
    return {
        "users": [
            {"id": 1, "username": "test_user", "email": "test@example.com"},
            {"id": 2, "username": "test_user2", "email": "test2@example.com"},
        ],
        "orders": [
            {"id": 1, "symbol": "BTC-USD", "side": "buy", "quantity": 0.1, "price": 50000.0, "status": "filled"},
            {"id": 2, "symbol": "ETH-USD", "side": "sell", "quantity": 1.0, "price": 3000.0, "status": "open"},
        ],
        "positions": [
            {"id": 1, "symbol": "BTC-USD", "quantity": 0.5, "average_price": 45000.0},
            {"id": 2, "symbol": "ETH-USD", "quantity": 2.0, "average_price": 2800.0},
        ],
    }


@pytest.fixture(scope="function")
def mock_encryption_key():
    """Provide a mock encryption key for testing."""
    return b"test_encryption_key_32_bytes_long!"


@pytest.fixture(scope="function")
def mock_authenticated_user():
    """Provide a mock authenticated user."""
    user = Mock()
    user.id = 1
    user.username = "test_user"
    user.email = "test@example.com"
    user.is_authenticated = True
    user.permissions = ["read", "write", "trade"]
    return user


@pytest.fixture(scope="function")
def mock_api_key():
    """Provide a mock API key for testing."""
    return {
        "id": "key_123",
        "user_id": 1,
        "key": "test_api_key_xyz",
        "secret": "test_api_secret_abc",
        "permissions": ["read", "trade"],
        "is_active": True,
        "created_at": "2024-01-01T00:00:00Z",
    }
