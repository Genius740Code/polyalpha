"""
CLOB Client tests — run with: pytest tests/unit/orderbook/test_clob.py
"""

import pytest
from polyalpha.trading.clob_client import ClobClient
from polyalpha.core.errors import NetworkError, OrderRejected


# ── ClobClient Initialization Tests ─────────────────────────────────────────────

@pytest.mark.unit
def test_clob_client_initialization():
    client = ClobClient(
        api_key="test-api-key",
        private_key="test-private-key",
        rpc_url="https://polygon-rpc.com",
        simulate=True,
    )
    assert client.api_key == "test-api-key"
    assert client.private_key == "test-private-key"
    assert client.rpc_url == "https://polygon-rpc.com"
    assert client.base_url == "https://clob.polymarket.com"
    assert client.timeout == 10
    assert client.retry_attempts == 3
    assert client.retry_delay == 1.0
    assert client.simulate == True


@pytest.mark.unit
def test_clob_client_custom_base_url():
    client = ClobClient(
        api_key="test-api-key",
        private_key="test-private-key",
        rpc_url="https://polygon-rpc.com",
        base_url="https://custom-clob.com",
        simulate=True,
    )
    assert client.base_url == "https://custom-clob.com"


@pytest.mark.unit
def test_clob_client_custom_timeout():
    client = ClobClient(
        api_key="test-api-key",
        private_key="test-private-key",
        rpc_url="https://polygon-rpc.com",
        timeout=30,
        simulate=True,
    )
    assert client.timeout == 30


@pytest.mark.unit
def test_clob_client_custom_retry_settings():
    client = ClobClient(
        api_key="test-api-key",
        private_key="test-private-key",
        rpc_url="https://polygon-rpc.com",
        retry_attempts=5,
        retry_delay=2.0,
        simulate=True,
    )
    assert client.retry_attempts == 5
    assert client.retry_delay == 2.0


# ── ClobClient Place Order Tests ─────────────────────────────────────────────────

@pytest.mark.unit
def test_clob_client_place_order_buy():
    client = ClobClient(
        api_key="test-api-key",
        private_key="test-private-key",
        rpc_url="https://polygon-rpc.com",
        simulate=True,
    )
    response = client.place_order(
        token_id="token-123",
        side="buy",
        price=0.55,
        size=10.0,
        order_type="limit",
    )
    assert "order_id" in response
    assert response["status"] == "pending"
    assert response["token_id"] == "token-123"
    assert response["side"] == "buy"
    assert response["price"] == 0.55
    assert response["size"] == 10.0


@pytest.mark.unit
def test_clob_client_place_order_sell():
    client = ClobClient(
        api_key="test-api-key",
        private_key="test-private-key",
        rpc_url="https://polygon-rpc.com",
        simulate=True,
    )
    response = client.place_order(
        token_id="token-123",
        side="sell",
        price=0.55,
        size=10.0,
        order_type="limit",
    )
    assert "order_id" in response
    assert response["side"] == "sell"


@pytest.mark.unit
def test_clob_client_place_order_market():
    client = ClobClient(
        api_key="test-api-key",
        private_key="test-private-key",
        rpc_url="https://polygon-rpc.com",
        simulate=True,
    )
    response = client.place_order(
        token_id="token-123",
        side="buy",
        price=0.55,
        size=10.0,
        order_type="market",
    )
    assert "order_id" in response
    assert response["status"] == "pending"


@pytest.mark.unit
def test_clob_client_place_order_with_custom_nonce():
    client = ClobClient(
        api_key="test-api-key",
        private_key="test-private-key",
        rpc_url="https://polygon-rpc.com",
        simulate=True,
    )
    response = client.place_order(
        token_id="token-123",
        side="buy",
        price=0.55,
        size=10.0,
        order_type="limit",
        nonce=1234567890,
    )
    assert "order_id" in response


@pytest.mark.unit
def test_clob_client_place_order_invalid_side():
    client = ClobClient(
        api_key="test-api-key",
        private_key="test-private-key",
        rpc_url="https://polygon-rpc.com",
        simulate=True,
    )
    with pytest.raises(ValueError):
        client.place_order(
            token_id="token-123",
            side="invalid",
            price=0.55,
            size=10.0,
        )


@pytest.mark.unit
def test_clob_client_place_order_invalid_order_type():
    client = ClobClient(
        api_key="test-api-key",
        private_key="test-private-key",
        rpc_url="https://polygon-rpc.com",
        simulate=True,
    )
    with pytest.raises(ValueError):
        client.place_order(
            token_id="token-123",
            side="buy",
            price=0.55,
            size=10.0,
            order_type="invalid",
        )


# ── ClobClient Cancel Order Tests ────────────────────────────────────────────────

@pytest.mark.unit
def test_clob_client_cancel_order():
    client = ClobClient(
        api_key="test-api-key",
        private_key="test-private-key",
        rpc_url="https://polygon-rpc.com",
        simulate=True,
    )
    response = client.cancel_order(order_id="order-123")
    assert "order_id" in response
    assert response["status"] == "cancelled"


@pytest.mark.unit
def test_clob_client_cancel_order_with_simulated_response():
    client = ClobClient(
        api_key="test-api-key",
        private_key="test-private-key",
        rpc_url="https://polygon-rpc.com",
        simulate=True,
    )
    response = client.cancel_order(order_id="order-456")
    assert response["order_id"] == "order-456"
    assert response["status"] == "cancelled"


# ── ClobClient Get Order Status Tests ────────────────────────────────────────────

@pytest.mark.unit
def test_clob_client_get_order_status():
    client = ClobClient(
        api_key="test-api-key",
        private_key="test-private-key",
        rpc_url="https://polygon-rpc.com",
        simulate=True,
    )
    response = client.get_order_status(order_id="order-123")
    assert "order_id" in response
    assert "status" in response
    assert "filled_size" in response
    assert "avg_price" in response


@pytest.mark.unit
def test_clob_client_get_order_status_filled():
    client = ClobClient(
        api_key="test-api-key",
        private_key="test-private-key",
        rpc_url="https://polygon-rpc.com",
        simulate=True,
    )
    response = client.get_order_status(order_id="order-123")
    assert response["status"] == "filled"
    assert response["filled_size"] == 10.0
    assert response["avg_price"] == 0.55


# ── ClobClient Get Orderbook Tests ──────────────────────────────────────────────

@pytest.mark.unit
def test_clob_client_get_orderbook():
    client = ClobClient(
        api_key="test-api-key",
        private_key="test-private-key",
        rpc_url="https://polygon-rpc.com",
        simulate=True,
    )
    response = client.get_orderbook(token_id="token-123")
    assert "bids" in response
    assert "asks" in response
    assert isinstance(response["bids"], list)
    assert isinstance(response["asks"], list)


@pytest.mark.unit
def test_clob_client_get_orderbook_structure():
    client = ClobClient(
        api_key="test-api-key",
        private_key="test-private-key",
        rpc_url="https://polygon-rpc.com",
        simulate=True,
    )
    response = client.get_orderbook(token_id="token-123")
    # Check that bids and asks have [price, size] structure
    if response["bids"]:
        assert len(response["bids"][0]) == 2
        assert isinstance(response["bids"][0][0], (int, float))  # price
        assert isinstance(response["bids"][0][1], (int, float))  # size
    if response["asks"]:
        assert len(response["asks"][0]) == 2
        assert isinstance(response["asks"][0][0], (int, float))  # price
        assert isinstance(response["asks"][0][1], (int, float))  # size


@pytest.mark.unit
def test_clob_client_get_orderbook_simulated_data():
    client = ClobClient(
        api_key="test-api-key",
        private_key="test-private-key",
        rpc_url="https://polygon-rpc.com",
        simulate=True,
    )
    response = client.get_orderbook(token_id="token-123")
    # Simulated data should have specific structure
    assert len(response["bids"]) >= 2
    assert len(response["asks"]) >= 2
    assert response["bids"][0][0] == 0.54  # First bid price
    assert response["bids"][0][1] == 100.0  # First bid size
    assert response["asks"][0][0] == 0.56  # First ask price
    assert response["asks"][0][1] == 100.0  # First ask size


# ── ClobClient Get Balance Tests ─────────────────────────────────────────────────

@pytest.mark.unit
def test_clob_client_get_balance():
    client = ClobClient(
        api_key="test-api-key",
        private_key="test-private-key",
        rpc_url="https://polygon-rpc.com",
        simulate=True,
    )
    response = client.get_balance()
    assert "address" in response
    assert "usdc_balance" in response
    assert "allowance" in response


@pytest.mark.unit
def test_clob_client_get_balance_simulated_data():
    client = ClobClient(
        api_key="test-api-key",
        private_key="test-private-key",
        rpc_url="https://polygon-rpc.com",
        simulate=True,
    )
    response = client.get_balance()
    assert response["usdc_balance"] == 1000.0
    assert response["allowance"] == 10000.0
    assert response["address"].startswith("0x")


# ── ClobClient Address Tests ────────────────────────────────────────────────────

@pytest.mark.unit
def test_clob_client_get_address():
    client = ClobClient(
        api_key="test-api-key",
        private_key="test-private-key",
        rpc_url="https://polygon-rpc.com",
        simulate=True,
    )
    address = client._get_address()
    assert address.startswith("0x")
    assert len(address) == 42


# ── ClobClient Sign Order Tests ──────────────────────────────────────────────────

@pytest.mark.unit
def test_clob_client_sign_order():
    client = ClobClient(
        api_key="test-api-key",
        private_key="test-private-key",
        rpc_url="https://polygon-rpc.com",
        simulate=True,
    )
    order_data = {
        "token_id": "token-123",
        "side": "buy",
        "price": 0.55,
        "size": 10.0,
    }
    signature = client._sign_order(order_data)
    assert signature.startswith("0x")
    assert len(signature) == 132  # 0x + 130 hex chars


# ── ClobClient Close Tests ───────────────────────────────────────────────────────

@pytest.mark.unit
def test_clob_client_close():
    client = ClobClient(
        api_key="test-api-key",
        private_key="test-private-key",
        rpc_url="https://polygon-rpc.com",
        simulate=True,
    )
    # Should not raise any errors
    client.close()


@pytest.mark.unit
def test_clob_client_close_idempotent():
    client = ClobClient(
        api_key="test-api-key",
        private_key="test-private-key",
        rpc_url="https://polygon-rpc.com",
        simulate=True,
    )
    client.close()
    # Should be able to close again without errors
    client.close()


# ── ClobClient Integration Tests ────────────────────────────────────────────────

@pytest.mark.unit
def test_clob_client_full_order_lifecycle():
    client = ClobClient(
        api_key="test-api-key",
        private_key="test-private-key",
        rpc_url="https://polygon-rpc.com",
        simulate=True,
    )
    
    # Place order
    order = client.place_order(
        token_id="token-123",
        side="buy",
        price=0.55,
        size=10.0,
        order_type="limit",
    )
    order_id = order["order_id"]
    
    # Get order status
    status = client.get_order_status(order_id)
    assert "status" in status
    
    # Cancel order
    cancel_response = client.cancel_order(order_id)
    assert cancel_response["status"] == "cancelled"


@pytest.mark.unit
def test_clob_client_multiple_orders():
    client = ClobClient(
        api_key="test-api-key",
        private_key="test-private-key",
        rpc_url="https://polygon-rpc.com",
        simulate=True,
    )
    
    # Place multiple orders
    order1 = client.place_order(
        token_id="token-123",
        side="buy",
        price=0.55,
        size=10.0,
    )
    order2 = client.place_order(
        token_id="token-123",
        side="sell",
        price=0.56,
        size=5.0,
    )
    
    assert order1["order_id"] != order2["order_id"]
    assert order1["side"] == "buy"
    assert order2["side"] == "sell"


@pytest.mark.unit
def test_clob_client_orderbook_query():
    client = ClobClient(
        api_key="test-api-key",
        private_key="test-private-key",
        rpc_url="https://polygon-rpc.com",
        simulate=True,
    )
    
    # Get orderbook
    orderbook = client.get_orderbook(token_id="token-123")
    
    # Verify structure
    assert "bids" in orderbook
    assert "asks" in orderbook
    
    # Place order based on orderbook
    if orderbook["bids"]:
        best_bid_price = orderbook["bids"][0][0]
        order = client.place_order(
            token_id="token-123",
            side="buy",
            price=best_bid_price,
            size=1.0,
        )
        assert "order_id" in order
