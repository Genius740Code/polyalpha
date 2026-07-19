"""
Client-related fixtures for testing.

Provides fixtures for creating Polyalpha client instances,
API clients, and authentication fixtures.
"""

import pytest
from unittest.mock import Mock, MagicMock
from pathlib import Path


@pytest.fixture(scope="function")
def mock_polyalpha_client():
    """Create a mock Polyalpha client."""
    client = Mock()
    client.api_key = "test_api_key"
    client.api_secret = "test_api_secret"
    client.is_connected = True
    client.markets = Mock()
    client.trading = Mock()
    client.database = Mock()
    client.analysis = Mock()
    client.connect = Mock()
    client.disconnect = Mock()
    return client


@pytest.fixture(scope="function")
def mock_api_client():
    """Create a mock API client."""
    client = Mock()
    client.base_url = "https://api.test.com"
    client.api_key = "test_api_key"
    client.timeout = 30
    client.get = Mock()
    client.post = Mock()
    client.put = Mock()
    client.delete = Mock()
    return client


@pytest.fixture(scope="function")
def client_config():
    """Provide client configuration for testing."""
    return {
        "api_key": "test_api_key",
        "api_secret": "test_api_secret",
        "base_url": "https://api.test.com",
        "timeout": 30,
        "max_retries": 3,
        "environment": "test",
    }


@pytest.fixture(scope="function")
def mock_auth_response():
    """Provide a mock authentication response."""
    return {
        "access_token": "test_access_token",
        "refresh_token": "test_refresh_token",
        "token_type": "Bearer",
        "expires_in": 3600,
        "user_id": 1,
        "permissions": ["read", "write", "trade"],
    }


@pytest.fixture(scope="function")
def mock_http_response():
    """Provide a mock HTTP response."""
    response = Mock()
    response.status_code = 200
    response.json.return_value = {"success": True, "data": {}}
    response.text = '{"success": true, "data": {}}'
    response.headers = {"Content-Type": "application/json"}
    return response


@pytest.fixture(scope="function")
def mock_websocket_connection():
    """Provide a mock WebSocket connection."""
    ws = Mock()
    ws.is_connected = True
    ws.send = Mock()
    ws.recv = Mock()
    ws.close = Mock()
    ws.subscribe = Mock()
    ws.unsubscribe = Mock()
    return ws
