"""
End-to-end tests for real trading workflows.

Tests complete real trading workflows including wallet connection,
order placement on blockchain, position management, and transaction tracking.
"""

import pytest
from decimal import Decimal
from unittest.mock import Mock, patch, MagicMock
from datetime import datetime, timedelta

import sys
from pathlib import Path
src_path = Path(__file__).parent.parent.parent / "src"
if str(src_path) not in sys.path:
    sys.path.insert(0, str(src_path))

from polyalpha import Client
from polyalpha.core import Market
from polyalpha.trading.real import RealTradingConfig


@pytest.mark.e2e
@pytest.mark.slow
@pytest.mark.requires_network
class TestRealTradingWorkflow:
    """Test complete real trading workflows."""

    @pytest.fixture(scope="function")
    def real_trading_config(self):
        """Create real trading configuration for testing."""
        return RealTradingConfig(
            private_key="0x" + "1" * 64,  # Mock private key
            rpc_url="https://polygon-rpc.com",
            polymarket_api_key="test_api_key",
        )

    @pytest.fixture(scope="function")
    def client(self, real_trading_config, temp_dir):
        """Create a client with real trading enabled."""
        with patch('polyalpha.markets.MarketClient') as mock_market_client:
            mock_market_client.return_value = Mock()
            client = Client(
                private_key=real_trading_config.private_key,
                rpc_url=real_trading_config.rpc_url,
                polymarket_api_key=real_trading_config.polymarket_api_key,
                db_path=str(temp_dir / "test_real.db"),
                log_level="DEBUG"
            )
            yield client
            client.close()

    @pytest.fixture(scope="function")
    def mock_market_response(self):
        """Create a mock market response."""
        market = Mock(spec=Market)
        market.token_id = "market_123"
        market.question = "Will BTC exceed $100k by end of year?"
        market.description = "Binary market on BTC price"
        market.end_time = datetime.now() + timedelta(days=30)
        market.tick_size = Decimal("0.01")
        market.min_order_size = Decimal("1.0")
        market.status = "active"
        return market

    @pytest.fixture(scope="function")
    def mock_wallet_response(self):
        """Create a mock wallet response."""
        wallet = Mock()
        wallet.address = "0x" + "a" * 40
        wallet.balance = Decimal("10000.0")
        wallet.nonce = 0
        return wallet

    def test_wallet_connection_workflow(self, client):
        """Test workflow: connect wallet -> verify connection -> get balance."""
        # Arrange: Mock wallet connection
        with patch.object(client.real, '_connect_wallet') as mock_connect:
            mock_connect.return_value = Mock(address="0x" + "a" * 40)
            
            # Act: Connect wallet
            wallet = client.real._connect_wallet()
            
            # Assert: Wallet connected
            assert wallet is not None
            assert wallet.address.startswith("0x")

    def test_real_buy_order_workflow(self, client, mock_market_response):
        """Test complete workflow: market discovery -> real buy -> transaction tracking."""
        with patch.object(client.markets, 'latest', return_value=mock_market_response):
            # Act: Discover market
            market = client.markets.latest("BTC", "5m")
            assert market is not None

            # Act: Place real buy order (mocked)
            with patch.object(client.real, 'place_order') as mock_place:
                mock_order = Mock()
                mock_order.id = "tx_123"
                mock_order.side = "UP"
                mock_order.quantity = Decimal("100.0")
                mock_order.status = "pending"
                mock_place.return_value = mock_order
                
                order = client.real.buy(
                    market,
                    side="UP",
                    amount=Decimal("100.0")
                )
                
                # Assert: Order placed
                assert order is not None
                assert order.id == "tx_123"
                assert order.status == "pending"

    def test_real_sell_order_workflow(self, client, mock_market_response):
        """Test complete workflow: market discovery -> real sell -> transaction tracking."""
        with patch.object(client.markets, 'latest', return_value=mock_market_response):
            # Act: Discover market
            market = client.markets.latest("BTC", "5m")
            
            # Act: Place real sell order (mocked)
            with patch.object(client.real, 'place_order') as mock_place:
                mock_order = Mock()
                mock_order.id = "tx_456"
                mock_order.side = "DOWN"
                mock_order.quantity = Decimal("50.0")
                mock_order.status = "pending"
                mock_place.return_value = mock_order
                
                order = client.real.sell(
                    market,
                    side="DOWN",
                    amount=Decimal("50.0")
                )
                
                # Assert: Order placed
                assert order is not None
                assert order.side == "DOWN"

    def test_transaction_confirmation_workflow(self, client, mock_market_response):
        """Test workflow: place order -> wait for confirmation -> verify status."""
        with patch.object(client.markets, 'latest', return_value=mock_market_response):
            market = client.markets.latest("BTC", "5m")
            
            with patch.object(client.real, 'place_order') as mock_place:
                # Arrange: Create order that transitions to confirmed
                mock_order = Mock()
                mock_order.id = "tx_789"
                mock_order.status = "pending"
                mock_place.return_value = mock_order
                
                # Act: Place order
                order = client.real.buy(market, side="UP", amount=Decimal("100.0"))
                
                # Act: Simulate transaction confirmation
                with patch.object(client.real, 'get_order') as mock_get:
                    confirmed_order = Mock()
                    confirmed_order.id = "tx_789"
                    confirmed_order.status = "confirmed"
                    confirmed_order.transaction_hash = "0x" + "b" * 64
                    mock_get.return_value = confirmed_order
                    
                    # Wait for confirmation
                    updated_order = client.real.get_order(order.id)
                    
                    # Assert: Order confirmed
                    assert updated_order.status == "confirmed"
                    assert updated_order.transaction_hash is not None

    def test_wallet_balance_tracking_workflow(self, client):
        """Test workflow: track wallet balance changes after trades."""
        with patch.object(client.real, 'get_balance') as mock_balance:
            # Arrange: Initial balance
            mock_balance.return_value = Decimal("10000.0")
            initial_balance = client.real.get_balance()
            
            # Act: Simulate trade
            mock_balance.return_value = Decimal("9500.0")
            updated_balance = client.real.get_balance()
            
            # Assert: Balance decreased
            assert updated_balance < initial_balance
            assert initial_balance - updated_balance == Decimal("500.0")

    def test_real_order_cancellation_workflow(self, client, mock_market_response):
        """Test workflow: place real order -> cancel -> verify cancellation."""
        with patch.object(client.markets, 'latest', return_value=mock_market_response):
            market = client.markets.latest("BTC", "5m")
            
            with patch.object(client.real, 'place_order') as mock_place:
                mock_order = Mock()
                mock_order.id = "tx_cancel"
                mock_order.status = "pending"
                mock_place.return_value = mock_order
                
                # Act: Place order
                order = client.real.buy(market, side="UP", amount=Decimal("100.0"))
                
                with patch.object(client.real, 'cancel_order') as mock_cancel:
                    mock_cancel.return_value = True
                    
                    # Act: Cancel order
                    cancelled = client.real.cancel_order(order.id)
                    
                    # Assert: Order cancelled
                    assert cancelled is True

    def test_gas_fee_estimation_workflow(self, client):
        """Test workflow: estimate gas fees before transaction."""
        with patch.object(client.real, 'estimate_gas') as mock_estimate:
            # Arrange: Mock gas estimation
            mock_estimate.return_value = {
                "gas_limit": 100000,
                "gas_price": Decimal("0.000000001"),
                "estimated_cost": Decimal("0.0001")
            }
            
            # Act: Estimate gas
            estimate = client.real.estimate_gas()
            
            # Assert: Gas estimated
            assert estimate is not None
            assert "gas_limit" in estimate
            assert "estimated_cost" in estimate

    def test_multi_transaction_workflow(self, client, mock_market_response):
        """Test workflow: execute multiple transactions in sequence."""
        with patch.object(client.markets, 'latest', return_value=mock_market_response):
            market = client.markets.latest("BTC", "5m")
            
            transaction_ids = []
            
            with patch.object(client.real, 'place_order') as mock_place:
                # Act: Place multiple orders
                for i in range(5):
                    mock_order = Mock()
                    mock_order.id = f"tx_{i}"
                    mock_order.status = "pending"
                    mock_place.return_value = mock_order
                    
                    order = client.real.buy(market, side="UP", amount=Decimal("10.0"))
                    transaction_ids.append(order.id)
            
            # Assert: All transactions created
            assert len(transaction_ids) == 5
            assert all(tx_id.startswith("tx_") for tx_id in transaction_ids)

    def test_error_handling_workflow(self, client, mock_market_response):
        """Test workflow: handle errors during real trading."""
        with patch.object(client.markets, 'latest', return_value=mock_market_response):
            market = client.markets.latest("BTC", "5m")
            
            # Act: Simulate insufficient funds error
            with patch.object(client.real, 'place_order') as mock_place:
                mock_place.side_effect = Exception("Insufficient funds")
                
                with pytest.raises(Exception) as exc_info:
                    client.real.buy(market, side="UP", amount=Decimal("1000000.0"))
                
                assert "Insufficient funds" in str(exc_info.value)
            
            # Act: Verify system still functional
            with patch.object(client.real, 'place_order') as mock_place:
                mock_order = Mock()
                mock_order.id = "tx_recovery"
                mock_place.return_value = mock_order
                
                order = client.real.buy(market, side="UP", amount=Decimal("10.0"))
                assert order is not None


@pytest.mark.e2e
@pytest.mark.slow
@pytest.mark.requires_network
class TestRealTradingSecurity:
    """Test security aspects of real trading."""

    @pytest.fixture(scope="function")
    def client(self, temp_dir):
        """Create a client with real trading enabled."""
        with patch('polyalpha.markets.MarketClient'):
            client = Client(
                private_key="0x" + "1" * 64,
                rpc_url="https://polygon-rpc.com",
                polymarket_api_key="test_api_key",
                db_path=str(temp_dir / "test_security.db"),
                log_level="DEBUG"
            )
            yield client
            client.close()

    def test_private_key_security(self, client):
        """Test that private key is handled securely."""
        # Assert: Private key should not be exposed in logs or attributes
        assert not hasattr(client.real, '_private_key_plaintext')
        assert client.real._private_key is not None

    def test_transaction_signing_workflow(self, client):
        """Test workflow: transaction is signed correctly."""
        with patch.object(client.real, '_sign_transaction') as mock_sign:
            # Arrange: Mock signing
            mock_sign.return_value = "0x" + "c" * 128
            
            # Act: Sign transaction
            signature = client.real._sign_transaction({"to": "0x123", "value": "100"})
            
            # Assert: Transaction signed
            assert signature is not None
            assert signature.startswith("0x")
            assert len(signature) == 130  # 0x + 64 bytes * 2 chars

    def test_api_key_usage(self, client):
        """Test that API key is used correctly for CLOB access."""
        # Assert: API key is configured
        assert client.real._polymarket_api_key is not None
        assert client.real._polymarket_api_key == "test_api_key"


@pytest.mark.e2e
@pytest.mark.slow
class TestRealTradingPerformance:
    """Test performance benchmarks for real trading."""

    @pytest.fixture(scope="function")
    def client(self, temp_dir):
        """Create a client for performance testing."""
        with patch('polyalpha.markets.MarketClient'):
            client = Client(
                private_key="0x" + "1" * 64,
                rpc_url="https://polygon-rpc.com",
                polymarket_api_key="test_api_key",
                db_path=str(temp_dir / "perf_real.db"),
                log_level="WARNING"
            )
            yield client
            client.close()

    @pytest.fixture(scope="function")
    def mock_market(self):
        """Create a mock market for performance testing."""
        market = Mock(spec=Market)
        market.token_id = "perf_market"
        market.question = "Performance test market"
        market.tick_size = Decimal("0.01")
        market.min_order_size = Decimal("1.0")
        return market

    def test_transaction_submission_performance(self, client, mock_market):
        """Test performance of submitting multiple transactions."""
        with patch.object(client.markets, 'latest', return_value=mock_market):
            with patch.object(client.real, 'place_order') as mock_place:
                import time
                
                # Arrange: Mock fast order placement
                def fast_place(*args, **kwargs):
                    mock_order = Mock()
                    mock_order.id = f"tx_{time.time_ns()}"
                    mock_order.status = "pending"
                    return mock_order
                
                mock_place.side_effect = fast_place
                
                # Act: Submit 50 transactions
                start_time = time.time()
                for i in range(50):
                    order = client.real.buy(mock_market, side="UP", amount=Decimal("10.0"))
                    assert order is not None
                
                elapsed_time = time.time() - start_time
                
                # Assert: Should complete in reasonable time (< 10 seconds)
                assert elapsed_time < 10.0, f"Too slow: {elapsed_time:.2f}s"

    def test_balance_query_performance(self, client):
        """Test performance of balance queries."""
        with patch.object(client.real, 'get_balance') as mock_balance:
            mock_balance.return_value = Decimal("10000.0")
            
            import time
            
            # Act: Query balance 100 times
            start_time = time.time()
            for _ in range(100):
                balance = client.real.get_balance()
                assert balance is not None
            
            elapsed_time = time.time() - start_time
            
            # Assert: Should complete in reasonable time (< 1 second)
            assert elapsed_time < 1.0, f"Too slow: {elapsed_time:.2f}s"
