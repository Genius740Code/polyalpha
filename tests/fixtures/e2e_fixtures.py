"""
E2E test fixtures for end-to-end testing.

Provides realistic test data and scenarios for complete workflow testing.
"""

import pytest
import pandas as pd
from decimal import Decimal
from unittest.mock import Mock
from datetime import datetime, timedelta
from pathlib import Path
import tempfile


@pytest.fixture(scope="function")
def realistic_market_data():
    """
    Provide realistic market data for E2E testing.
    
    Returns a DataFrame with OHLCV data that simulates real market behavior
    including trends, volatility, and volume patterns.
    """
    base_time = datetime.now() - timedelta(days=7)
    data = []
    
    # Simulate realistic price movement with trend and volatility
    price = 50000.0
    trend = 0.5  # Slight uptrend
    volatility = 0.02  # 2% volatility
    
    for i in range(1000):
        # Add trend component
        price += trend
        
        # Add random volatility
        import random
        change = random.gauss(0, volatility * price)
        price += change
        
        # Ensure price doesn't go negative
        price = max(price, 1000.0)
        
        # Calculate OHLC
        high = price + abs(random.gauss(0, volatility * price * 0.5))
        low = price - abs(random.gauss(0, volatility * price * 0.5))
        open_price = low + (high - low) * random.random()
        close_price = low + (high - low) * random.random()
        
        # Volume with some patterns
        base_volume = 100.0
        volume = base_volume + random.gauss(0, 50) + abs(change) * 10
        
        data.append({
            "timestamp": base_time + timedelta(minutes=i),
            "open": open_price,
            "high": high,
            "low": low,
            "close": close_price,
            "volume": max(volume, 10.0),
        })
    
    return pd.DataFrame(data)


@pytest.fixture(scope="function")
def multi_market_scenario():
    """
    Provide data for multiple markets for cross-market testing.
    
    Returns a dictionary with data for different markets showing
    correlated and uncorrelated movements.
    """
    base_time = datetime.now() - timedelta(days=3)
    markets = {
        "BTC-USD": [],
        "ETH-USD": [],
        "SOL-USD": [],
    }
    
    # BTC as primary driver
    btc_price = 50000.0
    eth_price = 3000.0
    sol_price = 100.0
    
    for i in range(500):
        # BTC movement
        import random
        btc_change = random.gauss(0, 200)
        btc_price += btc_change
        
        # ETH correlated with BTC but more volatile
        eth_change = btc_change * 0.8 + random.gauss(0, 50)
        eth_price += eth_change
        
        # SOL less correlated
        sol_change = random.gauss(0, 5)
        sol_price += sol_change
        
        markets["BTC-USD"].append({
            "timestamp": base_time + timedelta(minutes=i),
            "price": max(btc_price, 1000.0),
            "volume": 100.0 + random.gauss(0, 20),
        })
        
        markets["ETH-USD"].append({
            "timestamp": base_time + timedelta(minutes=i),
            "price": max(eth_price, 100.0),
            "volume": 50.0 + random.gauss(0, 10),
        })
        
        markets["SOL-USD"].append({
            "timestamp": base_time + timedelta(minutes=i),
            "price": max(sol_price, 10.0),
            "volume": 200.0 + random.gauss(0, 40),
        })
    
    # Convert to DataFrames
    for symbol in markets:
        markets[symbol] = pd.DataFrame(markets[symbol])
    
    return markets


@pytest.fixture(scope="function")
def trading_scenario_data():
    """
    Provide realistic trading scenario data for workflow testing.
    
    Includes market conditions, order history, and position data
    that simulate a complete trading session.
    """
    return {
        "market_conditions": {
            "trend": "bullish",
            "volatility": "medium",
            "volume": "high",
            "support_level": 49500.0,
            "resistance_level": 50500.0,
        },
        "order_history": [
            {
                "id": "order_001",
                "symbol": "BTC-USD",
                "side": "buy",
                "quantity": Decimal("0.5"),
                "price": Decimal("50000.0"),
                "status": "filled",
                "timestamp": datetime.now() - timedelta(hours=2),
            },
            {
                "id": "order_002",
                "symbol": "BTC-USD",
                "side": "sell",
                "quantity": Decimal("0.2"),
                "price": Decimal("50200.0"),
                "status": "filled",
                "timestamp": datetime.now() - timedelta(hours=1),
            },
        ],
        "positions": [
            {
                "symbol": "BTC-USD",
                "quantity": Decimal("0.3"),
                "average_price": Decimal("50000.0"),
                "current_price": Decimal("50100.0"),
                "unrealized_pnl": Decimal("30.0"),
            }
        ],
        "portfolio": {
            "cash": Decimal("5000.0"),
            "positions_value": Decimal("15030.0"),
            "total_value": Decimal("20030.0"),
        }
    }


@pytest.fixture(scope="function")
def stress_test_data():
    """
    Provide data for stress testing E2E workflows.
    
    Includes edge cases, error conditions, and high-load scenarios.
    """
    return {
        "large_order": {
            "quantity": Decimal("10000.0"),
            "price": Decimal("50000.0"),
            "total_value": Decimal("500000000.0"),
        },
        "rapid_orders": [
            {
                "id": f"rapid_{i}",
                "quantity": Decimal("1.0"),
                "price": Decimal("50000.0"),
            }
            for i in range(100)
        ],
        "extreme_volatility": {
            "price_changes": [
                random.gauss(0, 1000) for _ in range(100)
            ],
            "max_drawdown": 0.20,  # 20% drawdown
        },
        "network_conditions": {
            "high_latency": 500,  # ms
            "packet_loss": 0.01,  # 1%
            "timeout": 30,  # seconds
        }
    }


@pytest.fixture(scope="function")
def backtest_data():
    """
    Provide historical data for backtesting workflows.
    
    Returns a dataset spanning a longer time period with
    various market conditions (bull, bear, sideways).
    """
    base_time = datetime.now() - timedelta(days=90)
    data = []
    
    # Simulate different market regimes
    regimes = [
        {"duration": 30, "trend": 1.0, "volatility": 0.015},  # Bull
        {"duration": 20, "trend": -0.5, "volatility": 0.025},  # Bear
        {"duration": 25, "trend": 0.1, "volatility": 0.01},   # Sideways
        {"duration": 15, "trend": 0.8, "volatility": 0.02},   # Recovery
    ]
    
    price = 50000.0
    current_time = base_time
    
    for regime in regimes:
        for i in range(regime["duration"] * 24 * 12):  # 5-minute bars
            import random
            price += regime["trend"]
            change = random.gauss(0, regime["volatility"] * price)
            price += change
            price = max(price, 1000.0)
            
            high = price + abs(random.gauss(0, regime["volatility"] * price * 0.5))
            low = price - abs(random.gauss(0, regime["volatility"] * price * 0.5))
            open_price = low + (high - low) * random.random()
            close_price = low + (high - low) * random.random()
            
            data.append({
                "timestamp": current_time,
                "open": open_price,
                "high": high,
                "low": low,
                "close": close_price,
                "volume": 100.0 + random.gauss(0, 30),
            })
            
            current_time += timedelta(minutes=5)
    
    return pd.DataFrame(data)


@pytest.fixture(scope="function")
def error_scenario_data():
    """
    Provide data for testing error handling in E2E workflows.
    
    Includes various error conditions and expected responses.
    """
    return {
        "insufficient_funds": {
            "balance": Decimal("100.0"),
            "order_value": Decimal("10000.0"),
            "expected_error": "Insufficient funds",
        },
        "invalid_market": {
            "symbol": "INVALID-USD",
            "expected_error": "Market not found",
        },
        "invalid_order_size": {
            "quantity": Decimal("0.001"),  # Below minimum
            "min_order_size": Decimal("1.0"),
            "expected_error": "Order size below minimum",
        },
        "market_closed": {
            "status": "closed",
            "expected_error": "Market is closed",
        },
        "network_timeout": {
            "timeout": 0.001,  # Very short timeout
            "expected_error": "Network timeout",
        },
    }


@pytest.fixture(scope="function")
def performance_benchmark_data():
    """
    Provide data for performance benchmarking of E2E workflows.
    
    Includes expected performance metrics and thresholds.
    """
    return {
        "order_placement": {
            "max_time": 1.0,  # seconds
            "target_time": 0.5,
        },
        "portfolio_calculation": {
            "max_time": 0.5,
            "target_time": 0.1,
        },
        "indicator_calculation": {
            "max_time": 2.0,
            "target_time": 0.5,
        },
        "signal_generation": {
            "max_time": 0.5,
            "target_time": 0.1,
        },
        "data_fetch": {
            "max_time": 3.0,
            "target_time": 1.0,
        },
        "memory_usage": {
            "max_mb": 500,
            "target_mb": 200,
        },
    }


@pytest.fixture(scope="function")
def integration_test_data():
    """
    Provide data for testing integration between components.
    
    Includes scenarios that test interaction between trading,
    analysis, and database components.
    """
    return {
        "trading_analysis": {
            "market": "BTC-USD",
            "analysis_result": {
                "signal": "buy",
                "confidence": 0.85,
                "indicators": {
                    "rsi": 35,
                    "sma_trend": "up",
                    "macd_signal": "bullish",
                }
            },
            "expected_action": "place_buy_order",
        },
        "database_trading": {
            "order_id": "order_integration_001",
            "save_to_db": True,
            "verify_persistence": True,
        },
        "stream_trading": {
            "market": "BTC-USD",
            "stream_data": True,
            "auto_trade": False,
        },
    }


@pytest.fixture(scope="function")
def e2e_test_config():
    """
    Provide configuration for E2E test execution.
    
    Includes timeouts, retry counts, and other test parameters.
    """
    return {
        "timeouts": {
            "order_placement": 30,
            "market_data_fetch": 60,
            "portfolio_update": 10,
            "analysis_calculation": 30,
        },
        "retries": {
            "network_operations": 3,
            "database_operations": 2,
            "api_calls": 3,
        },
        "thresholds": {
            "max_slippage": 0.01,  # 1%
            "max_latency": 1000,  # ms
            "min_success_rate": 0.95,  # 95%
        },
    }


@pytest.fixture(scope="session")
def e2e_test_database():
    """
    Provide a temporary database for E2E testing.
    
    Creates a temporary SQLite database that can be used
    across multiple E2E tests for persistence testing.
    """
    import sqlite3
    import tempfile
    
    # Create temporary database
    db_path = tempfile.mktemp(suffix=".db")
    
    # Initialize database
    conn = sqlite3.connect(db_path)
    cursor = conn.cursor()
    
    # Create tables
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS orders (
            id TEXT PRIMARY KEY,
            symbol TEXT,
            side TEXT,
            quantity REAL,
            price REAL,
            status TEXT,
            timestamp DATETIME
        )
    """)
    
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS positions (
            symbol TEXT PRIMARY KEY,
            quantity REAL,
            average_price REAL,
            current_price REAL,
            unrealized_pnl REAL
        )
    """)
    
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS portfolio (
            id INTEGER PRIMARY KEY,
            cash REAL,
            positions_value REAL,
            total_value REAL,
            updated_at DATETIME
        )
    """)
    
    conn.commit()
    conn.close()
    
    yield db_path
    
    # Cleanup
    import os
    try:
        os.unlink(db_path)
    except:
        pass
