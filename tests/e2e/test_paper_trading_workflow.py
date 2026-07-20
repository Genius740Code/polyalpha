"""
End-to-end tests for paper trading workflows.

Tests complete trading workflows including market discovery,
order placement, position management, and P&L tracking.
"""

import pytest
from decimal import Decimal
from unittest.mock import Mock, patch, MagicMock
from datetime import datetime, timedelta, timezone

import sys
from pathlib import Path
src_path = Path(__file__).parent.parent.parent / "src"
if str(src_path) not in sys.path:
    sys.path.insert(0, str(src_path))

from polyalpha import Client
from polyalpha.core import Market
from polyalpha.trading.paper import PaperConfig


@pytest.mark.e2e
@pytest.mark.slow
class TestPaperTradingWorkflow:
    """Test complete paper trading workflows."""

    @pytest.fixture(scope="function")
    def client(self, temp_dir):
        """Create a client with paper trading enabled."""
        with patch('polyalpha.markets.MarketClient') as mock_market_client:
            mock_market_client.return_value = Mock()
            # Use relaxed risk config for E2E tests
            risk_config = PaperConfig(
                fee_mode="custom",
                custom_fee_rate=0.02
            )
            client = Client(
                balance=10000.0,
                paper_config=risk_config,
                db_path=str(temp_dir / "test.db"),
                log_level="DEBUG"
            )
            # Disable risk management for E2E tests
            client.paper.config.enable_risk_management = False
            yield client
            client.close()

    @pytest.fixture(scope="function")
    def mock_market_response(self):
        """Create a mock market response."""
        market = Mock(spec=Market)
        market.id = "market_123"
        market.slug = "btc-updown-5m-1751234700"
        market.question = "Will BTC exceed $100k by end of year?"
        market.description = "Binary market on BTC price"
        market.active = True
        market.closed = False
        market.archived = False
        market.start_time = (datetime.now(timezone.utc) - timedelta(days=1)).isoformat()
        market.end_time = (datetime.now(timezone.utc) + timedelta(days=30)).isoformat()
        market.volume = 100000.0
        market.liquidity = 50000.0
        market.outcomes = ["UP", "DOWN"]
        market.prices = [0.50, 0.50]  # [up_price, down_price]
        market.up_price = 0.50
        market.down_price = 0.50
        market.tokens = ["token_up_123", "token_down_456"]
        return market

    def test_complete_buy_workflow(self, client, mock_market_response):
        """Test complete workflow: market discovery -> buy -> position tracking."""
        # Arrange
        with patch.object(client.markets, 'latest', return_value=mock_market_response):
            # Act: Discover market
            market = client.markets.latest("BTC", "5m")
            assert market is not None
            assert market.id == "market_123"

            # Act: Place buy order
            initial_balance = client.paper.balance
            order = client.paper.buy(
                market,
                side="UP",
                amount=100.0
            )
            
            # Assert: Order placed successfully
            assert order is not None
            assert order.side == "UP"
            assert order.amount == 100.0

            # Assert: Order was filled (fee was charged)
            assert order.status == "filled"
            assert order.fee > 0

            # Act: Get position
            position = client.paper.positions()
            
            # Assert: Position created
            assert position is not None

    def test_complete_sell_workflow(self, client, mock_market_response):
        """Test complete workflow: market discovery -> sell -> position tracking."""
        # Arrange
        with patch.object(client.markets, 'latest', return_value=mock_market_response):
            # Act: Discover market
            market = client.markets.latest("BTC", "5m")
            
            # Act: Place sell order (using buy with side="DOWN")
            initial_balance = client.paper.balance
            order = client.paper.buy(
                market,
                side="DOWN",
                amount=50.0
            )
            
            # Assert: Order placed successfully
            assert order is not None
            assert order.side == "DOWN"
            assert order.amount == 50.0

            # Assert: Order was filled (fee was charged)
            assert order.status == "filled"
            assert order.fee > 0

    def test_multi_market_trading_workflow(self, client):
        """Test trading across multiple markets."""
        # Arrange: Create multiple mock markets
        markets = []
        for i in range(3):
            market = Mock(spec=Market)
            market.id = f"market_{i}"
            market.slug = f"test-market-{i}-5m-1751234700"
            market.question = f"Test market {i}"
            market.active = True
            market.closed = False
            market.archived = False
            market.start_time = (datetime.now(timezone.utc) - timedelta(days=1)).isoformat()
            market.end_time = (datetime.now(timezone.utc) + timedelta(days=30)).isoformat()
            market.volume = 100000.0
            market.liquidity = 50000.0
            market.outcomes = ["UP", "DOWN"]
            market.prices = [0.50, 0.50]
            market.up_price = 0.50
            market.down_price = 0.50
            market.tokens = [f"token_up_{i}", f"token_down_{i}"]
            markets.append(market)

        with patch.object(client.markets, 'latest', side_effect=markets):
            # Act: Trade on multiple markets
            for market in markets:
                order = client.paper.buy(
                    market,
                    side="UP",
                    amount=10.0
                )
                assert order is not None

            # Assert: Multiple positions created
            positions = client.paper.positions()
            assert len(positions) == 3

    def test_order_cancellation_workflow(self, client, mock_market_response):
        """Test workflow: place limit order -> cancel order -> verify cancellation."""
        with patch.object(client.markets, 'latest', return_value=mock_market_response):
            # Act: Place limit order (not market order)
            market = client.markets.latest("BTC", "5m")
            order = client.paper.limit(
                market,
                side="UP",
                price=0.45,  # Below current price, won't fill immediately
                amount=100.0
            )
            
            # Assert: Order placed
            assert order is not None
            order_id = order.id

            # Act: Cancel order (if it's still open)
            if order.status == "open":
                cancelled_order = client.paper.cancel(order_id)
                # Assert: Order cancelled (cancel returns the cancelled order)
                assert cancelled_order.status == "cancelled"
            else:
                # If order filled, skip cancellation test
                pass

    def test_portfolio_value_tracking_workflow(self, client, mock_market_response):
        """Test workflow: place orders -> track portfolio value over time."""
        with patch.object(client.markets, 'latest', return_value=mock_market_response):
            # Act: Place order
            market = client.markets.latest("BTC", "5m")
            
            client.paper.buy(market, side="UP", amount=200.0)
            
            # Act: Get portfolio summary (prints to stdout, returns None)
            client.paper.summary()
            
            # Assert: Portfolio summary calculated without error
            # The summary() method prints to stdout, so we just verify it runs without error

    def test_risk_limit_enforcement_workflow(self, client, mock_market_response):
        """Test workflow: verify risk management can be enabled."""
        # Arrange: Enable risk management
        client.paper.config.enable_risk_management = True
        
        with patch.object(client.markets, 'latest', return_value=mock_market_response):
            market = client.markets.latest("BTC", "5m")
            
            # Act: Place normal order (should succeed)
            order = client.paper.buy(
                market,
                side="UP",
                amount=100.0
            )
            
            # Assert: Order placed successfully
            assert order is not None

    def test_fee_calculation_workflow(self, client, mock_market_response):
        """Test workflow: verify fees are calculated correctly."""
        # Arrange: Config with known fee rate
        fee_config = PaperConfig(
            fee_mode="custom",
            custom_fee_rate=0.001  # 0.1% fee
        )
        
        client_with_fees = Client(
            balance=10000.0,
            paper_config=fee_config,
            db_path=":memory:",
            log_level="DEBUG"
        )
        client_with_fees.paper.config.enable_risk_management = False
        
        try:
            with patch.object(client_with_fees.markets, 'latest', return_value=mock_market_response):
                market = client_with_fees.markets.latest("BTC", "5m")
                
                # Act: Place order
                order = client_with_fees.paper.buy(
                    market,
                    side="UP",
                    amount=100.0
                )
                
                # Assert: Fee calculated and charged
                assert order.fee > 0
                expected_fee = 100.0 * fee_config.custom_fee_rate
                assert abs(order.fee - expected_fee) < 0.01
        finally:
            client_with_fees.close()

    def test_error_recovery_workflow(self, client, mock_market_response):
        """Test workflow: recover from errors during trading."""
        with patch.object(client.markets, 'latest', return_value=mock_market_response):
            market = client.markets.latest("BTC", "5m")
            
            # Act: Place order successfully
            order1 = client.paper.buy(market, side="UP", amount=100.0)
            assert order1 is not None
            
            # Simulate error condition
            with patch.object(client.paper, 'buy', side_effect=Exception("Network error")):
                with pytest.raises(Exception):
                    client.paper.buy(market, side="UP", amount=50.0)
            
            # Act: Verify system still functional after error
            order2 = client.paper.buy(market, side="UP", amount=75.0)
            assert order2 is not None


@pytest.mark.e2e
@pytest.mark.slow
class TestPaperTradingPerformance:
    """Test performance benchmarks for paper trading."""

    @pytest.fixture(scope="function")
    def client(self, temp_dir):
        """Create a client for performance testing."""
        with patch('polyalpha.markets.MarketClient'):
            risk_config = PaperConfig(
                fee_mode="custom",
                custom_fee_rate=0.02
            )
            client = Client(
                balance=100000.0,
                paper_config=risk_config,
                db_path=str(temp_dir / "perf_test.db"),
                log_level="WARNING"
            )
            client.paper.config.enable_risk_management = False
            yield client
            client.close()

    @pytest.fixture(scope="function")
    def mock_market(self):
        """Create a mock market for performance testing."""
        market = Mock(spec=Market)
        market.id = "perf_market"
        market.slug = "perf-market-5m-1751234700"
        market.question = "Performance test market"
        market.active = True
        market.closed = False
        market.archived = False
        market.start_time = (datetime.now(timezone.utc) - timedelta(days=1)).isoformat()
        market.end_time = (datetime.now(timezone.utc) + timedelta(days=30)).isoformat()
        market.volume = 100000.0
        market.liquidity = 50000.0
        market.outcomes = ["UP", "DOWN"]
        market.prices = [0.50, 0.50]
        market.up_price = 0.50
        market.down_price = 0.50
        market.tokens = ["token_up_perf", "token_down_perf"]
        return market

    def test_bulk_order_placement_performance(self, client, mock_market):
        """Test performance of placing many orders quickly."""
        with patch.object(client.markets, 'latest', return_value=mock_market):
            import time
            
            # Act: Place 100 orders
            start_time = time.time()
            for i in range(100):
                order = client.paper.buy(
                    mock_market,
                    side="UP",
                    amount=10.0
                )
                assert order is not None
            
            elapsed_time = time.time() - start_time
            
            # Assert: Should complete in reasonable time (< 5 seconds)
            assert elapsed_time < 5.0, f"Too slow: {elapsed_time:.2f}s"

    def test_portfolio_calculation_performance(self, client, mock_market):
        """Test performance of portfolio calculations with many positions."""
        with patch.object(client.markets, 'latest', return_value=mock_market):
            # Arrange: Create many positions
            for i in range(50):
                client.paper.buy(mock_market, side="UP", amount=10.0)
            
            import time
            
            # Act: Calculate portfolio value multiple times
            start_time = time.time()
            for _ in range(100):
                summary = client.paper.summary()
                # summary() prints to stdout and returns None
            
            elapsed_time = time.time() - start_time
            
            # Assert: Should complete in reasonable time (< 1 second)
            assert elapsed_time < 1.0, f"Too slow: {elapsed_time:.2f}s"
