"""
Global pytest configuration for Polyalpha test suite.

This file contains shared fixtures, pytest markers, and configuration
for running tests across the entire test suite.
"""

import sys
import os
from pathlib import Path

# Add src directory to path for imports
src_path = Path(__file__).parent.parent / "src"
if str(src_path) not in sys.path:
    sys.path.insert(0, str(src_path))

import pytest


# Pytest markers
def pytest_configure(config):
    """Configure custom pytest markers."""
    config.addinivalue_line(
        "markers", "unit: Unit tests (no external dependencies)"
    )
    config.addinivalue_line(
        "markers", "integration: Integration tests (multiple components)"
    )
    config.addinivalue_line(
        "markers", "e2e: End-to-end tests (full workflows)"
    )
    config.addinivalue_line(
        "markers", "slow: Tests that take longer to run"
    )
    config.addinivalue_line(
        "markers", "requires_network: Tests that require network access"
    )
    config.addinivalue_line(
        "markers", "requires_database: Tests that require database access"
    )


# Global fixtures
@pytest.fixture(scope="session")
def project_root():
    """Get the project root directory."""
    return Path(__file__).parent.parent


@pytest.fixture(scope="session")
def src_dir(project_root):
    """Get the source directory."""
    return project_root / "src"


@pytest.fixture(scope="session")
def tests_dir(project_root):
    """Get the tests directory."""
    return project_root / "tests"


@pytest.fixture(scope="function")
def temp_dir(tmp_path):
    """Create a temporary directory for test files."""
    return tmp_path


@pytest.fixture(scope="function")
def mock_env_vars(monkeypatch):
    """Mock environment variables for testing."""
    env_vars = {
        "POLYALPHA_ENV": "test",
        "POLYALPHA_LOG_LEVEL": "DEBUG",
    }
    
    for key, value in env_vars.items():
        monkeypatch.setenv(key, value)
    
    return env_vars


@pytest.fixture(scope="function")
def sample_market_data():
    """Provide sample market data for testing."""
    return {
        "symbol": "BTC-USD",
        "price": 50000.0,
        "bid": 49999.0,
        "ask": 50001.0,
        "volume": 100.0,
        "timestamp": 1234567890,
    }


@pytest.fixture(scope="function")
def sample_order_data():
    """Provide sample order data for testing."""
    return {
        "symbol": "BTC-USD",
        "side": "buy",
        "quantity": 0.1,
        "price": 50000.0,
        "order_type": "limit",
    }


@pytest.fixture(scope="function")
def sample_portfolio_data():
    """Provide sample portfolio data for testing."""
    return {
        "cash": 100000.0,
        "positions": {
            "BTC-USD": {
                "quantity": 0.5,
                "average_price": 45000.0,
            }
        },
    }
