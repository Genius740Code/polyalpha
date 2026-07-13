"""
Real Trading Example

This example demonstrates how to set up and use the real trading engine
for actual fund execution via Polymarket CLOB.

IMPORTANT: This uses real money. Use with caution and start with small amounts.
"""

import polyalpha

# ── Basic Real Trading Setup ─────────────────────────────────────────────────────

def basic_real_trading():
    """Basic real trading setup with default configuration."""

    # Initialize client with real trading credentials
    client = polyalpha.Client(
        private_key="your-private-key-here",  # Your wallet private key
        rpc_url="https://polygon-rpc.com",  # Polygon RPC URL
        polymarket_api_key="your-polymarket-api-key",  # Polymarket API key
        real_config=polyalpha.RealTradingConfig(
            # Safety settings
            require_confirmation=True,  # Always confirm orders
            max_order_size=100.0,  # Maximum $100 per order
            max_daily_loss=50.0,  # Stop if daily loss exceeds $50
            max_position_size=200.0,  # Maximum position size
            max_open_positions=5,  # Maximum concurrent positions

            # Position sizing
            position_sizing="fixed",  # Use fixed amount sizing
            fixed_amount=10.0,  # $10 per trade

            # Risk management
            enable_stop_loss=True,
            default_stop_loss_pct=0.20,  # 20% stop loss
            enable_take_profit=True,
            default_take_profit_pct=0.50,  # 50% take profit
            max_risk_per_trade=0.02,  # 2% of balance per trade
        ),
    )
    
    # Check balance
    print(f"Current balance: ${client.real.balance:.2f}")
    
    # Get a market
    market = client.markets.get("btc-updown-5m-9999999")
    
    # Place a market order (will require confirmation)
    order = client.real.buy(
        market=market,
        side="UP",
        amount=10.0,
        confirm=True,
    )
    
    print(f"Order placed: {order.id}")
    print(f"Status: {order.status}")
    print(f"Amount: ${order.amount:.2f}")
    print(f"Price: ${order.price:.4f}")


# ── Percentage-Based Position Sizing ─────────────────────────────────────────────

def percentage_position_sizing():
    """Real trading with percentage-based position sizing."""
    
    client = polyalpha.Client(
        private_key="your-private-key-here",
        rpc_url="https://polygon-rpc.com",
        polymarket_api_key="your-polymarket-api-key",
        real_config=polyalpha.RealTradingConfig(
            # Use percentage-based sizing
            position_sizing="percentage",
            percentage_of_balance=0.05,  # 5% of balance per trade
            
            # Safety settings
            require_confirmation=True,
            max_order_size=500.0,
            max_daily_loss=100.0,
        ),
    )
    
    market = client.markets.get("btc-updown-5m-9999999")
    
    # This will use 5% of current balance
    order = client.real.buy(
        market=market,
        side="UP",
        confirm=True,
    )
    
    print(f"Order amount: ${order.amount:.2f} (5% of balance)")


# ── Kelly Criterion Position Sizing ───────────────────────────────────────────────

def kelly_position_sizing():
    """Real trading with Kelly criterion position sizing."""
    
    client = polyalpha.Client(
        private_key="your-private-key-here",
        rpc_url="https://polygon-rpc.com",
        polymarket_api_key="your-polymarket-api-key",
        real_config=polyalpha.RealTradingConfig(
            # Use Kelly criterion sizing
            position_sizing="kelly",
            kelly_fraction=0.25,  # Quarter Kelly for safety
            
            # Safety settings
            require_confirmation=True,
            max_order_size=200.0,
            max_daily_loss=100.0,
        ),
    )
    
    market = client.markets.get("btc-updown-5m-9999999")
    
    # High confidence trade (65%)
    order = client.real.buy(
        market=market,
        side="UP",
        confidence=0.65,
        confirm=True,
    )
    
    print(f"Order amount: ${order.amount:.2f} (Kelly sized with 65% confidence)")


# ── Limit Orders ─────────────────────────────────────────────────────────────────

def limit_order_example():
    """Real trading with limit orders."""
    
    client = polyalpha.Client(
        private_key="your-private-key-here",
        rpc_url="https://polygon-rpc.com",
        polymarket_api_key="your-polymarket-api-key",
        real_config=polyalpha.RealTradingConfig(
            position_sizing="fixed",
            fixed_amount=10.0,
        ),
    )
    
    market = client.markets.get("btc-updown-5m-9999999")
    
    # Place a limit order at a specific price
    order = client.real.limit(
        market=market,
        side="UP",
        price=0.92,  # Buy at $0.92 or better
        amount=10.0,
        confirm=True,
    )
    
    print(f"Limit order placed at ${order.price:.4f}")
    print(f"Status: {order.status}")
    
    # Check open orders
    open_orders = client.real.open_orders()
    print(f"Open orders: {len(open_orders)}")


# ── Risk Management with Stop Loss ───────────────────────────────────────────────

def stop_loss_example():
    """Real trading with stop loss."""
    
    client = polyalpha.Client(
        private_key="your-private-key-here",
        rpc_url="https://polygon-rpc.com",
        polymarket_api_key="your-polymarket-api-key",
        real_config=polyalpha.RealTradingConfig(
            position_sizing="fixed",
            fixed_amount=10.0,
            enable_stop_loss=True,
        ),
    )
    
    market = client.markets.get("btc-updown-5m-9999999")
    
    # Place order with custom stop loss
    order = client.real.buy(
        market=market,
        side="UP",
        amount=10.0,
        stop_loss=0.45,  # Stop loss at $0.45
        confirm=True,
    )
    
    print(f"Order placed with stop loss at ${order.stop_loss:.4f}")


# ── Position Management ─────────────────────────────────────────────────────────

def position_management():
    """Managing positions and viewing P&L."""
    
    client = polyalpha.Client(
        private_key="your-private-key-here",
        rpc_url="https://polygon-rpc.com",
        polymarket_api_key="your-polymarket-api-key",
        real_config=polyalpha.RealTradingConfig(),
    )
    
    # View all open positions
    positions = client.real.positions()
    print(f"Open positions: {len(positions)}")
    
    for position in positions:
        print(f"\nMarket: {position.slug}")
        print(f"Question: {position.question}")
        print(f"Side: {position.side}")
        print(f"Shares: {position.shares:.4f}")
        print(f"Avg Price: ${position.avg_price:.4f}")
        print(f"Current Price: ${position.current_price:.4f}")
        print(f"Cost Basis: ${position.cost_basis:.2f}")
        print(f"Current Value: ${position.current_value:.2f}")
        print(f"P&L: ${position.pnl:.2f} ({position.pnl_pct:.2f}%)")
        print(f"Stop Loss: ${position.stop_loss:.4f}" if position.stop_loss else "Stop Loss: None")
        print(f"Take Profit: ${position.take_profit:.4f}" if position.take_profit else "Take Profit: None")
        print(f"Resolved: {position.resolved}")
        if position.resolved:
            print(f"Outcome: {position.outcome}")
        print(f"Order IDs: {len(position.order_ids)} orders")


def position_details_example():
    """Getting detailed position information."""
    
    client = polyalpha.Client(
        private_key="your-private-key-here",
        rpc_url="https://polygon-rpc.com",
        polymarket_api_key="your-polymarket-api-key",
        real_config=polyalpha.RealTradingConfig(),
    )
    
    market = client.markets.get("btc-updown-5m-9999999")
    
    # Get a specific position by market and side
    try:
        position = client.real.get_position(market.id, "UP")
        
        print(f"Position Details:")
        print(f"  Market ID: {position.market_id}")
        print(f"  Slug: {position.slug}")
        print(f"  Question: {position.question}")
        print(f"  Side: {position.side}")
        print(f"  Shares: {position.shares}")
        print(f"  Average Price: ${position.avg_price}")
        print(f"  Current Price: ${position.current_price}")
        print(f"  Cost Basis: ${position.cost_basis}")
        print(f"  Current Value: ${position.current_value}")
        print(f"  P&L: ${position.pnl} ({position.pnl_pct}%)")
        print(f"  Resolved: {position.resolved}")
        print(f"  Outcome: {position.outcome}")
        print(f"  Stop Loss: {position.stop_loss}")
        print(f"  Take Profit: {position.take_profit}")
        print(f"  Order IDs: {position.order_ids}")
        
        # Export position data as dictionary
        position_dict = position.dump()
        print(f"\nPosition data (dict): {position_dict}")
        
    except polyalpha.PositionNotFound:
        print("No position found for this market and side")


# ── Emergency Stop ────────────────────────────────────────────────────────────────

def emergency_stop_example():
    """Emergency stop functionality."""
    
    client = polyalpha.Client(
        private_key="your-private-key-here",
        rpc_url="https://polygon-rpc.com",
        polymarket_api_key="your-polymarket-api-key",
        real_config=polyalpha.RealTradingConfig(),
    )
    
    # Emergency stop - cancels all open orders and halts trading
    client.real.emergency_stop(reason="Manual emergency stop")
    
    print("Emergency stop activated")
    print(f"Emergency mode: {client.real.emergency_mode}")
    
    # Resume trading (requires confirmation)
    client.real.resume_trading(confirm=False)
    
    print("Trading resumed")


# ── Database Integration ────────────────────────────────────────────────────────

def database_integration():
    """Real trading with database persistence."""
    
    client = polyalpha.Client(
        private_key="your-private-key-here",
        rpc_url="https://polygon-rpc.com",
        polymarket_api_key="your-polymarket-api-key",
        real_config=polyalpha.RealTradingConfig(),
        db_path="real_trades.db",  # SQLite database for trade persistence
    )
    
    market = client.markets.get("btc-updown-5m-9999999")
    
    # Orders will be automatically saved to database
    order = client.real.buy(
        market=market,
        side="UP",
        amount=10.0,
        confirm=False,
    )
    
    print(f"Order saved to database: {order.id}")


# ── Pre-Trade Checks ─────────────────────────────────────────────────────────────

def pre_trade_checks_example():
    """Using pre-trade checks before placing orders."""

    client = polyalpha.Client(
        private_key="your-private-key-here",
        rpc_url="https://polygon-rpc.com",
        polymarket_api_key="your-polymarket-api-key",
        real_config=polyalpha.RealTradingConfig(
            position_sizing="fixed",
            fixed_amount=10.0,
        ),
    )

    market = client.markets.get("btc-updown-5m-9999999")

    # Run pre-trade checks before placing order
    checks = client.real.pre_trade_checks(market, side="UP", amount=10.0)

    print("Pre-Trade Check Results:")
    print(f"  Balance OK: {checks['balance_ok']}")
    print(f"  Allowance OK: {checks['allowance_ok']}")
    print(f"  Market Open: {checks['market_open']}")
    print(f"  Price Reasonable: {checks['price_reasonable']}")
    print(f"  Can Proceed: {checks['can_proceed']}")

    if checks['warnings']:
        print("\n  Warnings:")
        for warning in checks['warnings']:
            print(f"    - {warning}")

    # Only proceed if checks pass
    if checks['can_proceed']:
        print("\nAll checks passed. Placing order...")
        order = client.real.buy(
            market=market,
            side="UP",
            amount=10.0,
            confirm=True,
        )
        print(f"Order placed: {order.id}")
    else:
        print("\nPre-trade checks failed. Order not placed.")
        print("Review warnings and address issues before proceeding.")


# ── Wallet Management ───────────────────────────────────────────────────────────

def wallet_management():
    """Direct wallet management."""
    
    client = polyalpha.Client(
        private_key="your-private-key-here",
        rpc_url="https://polygon-rpc.com",
        polymarket_api_key="your-polymarket-api-key",
        real_config=polyalpha.RealTradingConfig(),
    )
    
    # Refresh balance from blockchain
    client.real.refresh_balance()
    print(f"Balance: ${client.real.balance:.2f}")
    
    # Check CLOB allowance
    allowance = client.real._wallet.get_allowance()
    print(f"CLOB Allowance: ${allowance:.2f}")
    
    # Approve CLOB if needed
    if allowance < 100.0:
        tx_hash = client.real._wallet.approve_clob(10000.0)
        print(f"CLOB approval transaction: {tx_hash}")


# ── Advanced Configuration ───────────────────────────────────────────────────────

def advanced_configuration():
    """Advanced real trading configuration."""
    
    config = polyalpha.RealTradingConfig(
        # Safety
        require_confirmation=True,
        max_order_size=500.0,
        max_daily_loss=200.0,
        max_position_size=1000.0,
        max_open_positions=10,
        
        # Position sizing
        position_sizing="percentage",
        percentage_of_balance=0.03,  # 3% of balance
        
        # Risk management
        enable_stop_loss=True,
        default_stop_loss_pct=0.15,  # 15% stop loss
        enable_take_profit=True,
        default_take_profit_pct=0.40,  # 40% take profit
        max_risk_per_trade=0.01,  # 1% of balance per trade
        
        # Execution
        slippage_tolerance=0.03,  # 3% slippage tolerance
        order_timeout=120,  # 2 minute timeout
        retry_attempts=5,
        retry_delay=2.0,
        
        # Fees
        fee_mode="polymarket",
        
        # Logging
        log_all_orders=True,
        log_balance_updates=True,
    )
    
    client = polyalpha.Client(
        private_key="your-private-key-here",
        rpc_url="https://polygon-rpc.com",
        polymarket_api_key="your-polymarket-api-key",
        real_config=config,
    )
    
    print("Real trading engine initialized with advanced configuration")


# ── Main Example ───────────────────────────────────────────────────────────────

if __name__ == "__main__":
    print("=" * 60)
    print("Real Trading Example")
    print("=" * 60)
    print()
    print("IMPORTANT: This example uses real money.")
    print("Always start with small amounts and test thoroughly.")
    print()
    print("To run this example, uncomment the function you want to test")
    print("and replace the placeholder credentials with your own.")
    print()
    print("=" * 60)
    
    # Uncomment one of the examples below to run:

    # basic_real_trading()
    # percentage_position_sizing()
    # kelly_position_sizing()
    # limit_order_example()
    # stop_loss_example()
    # position_management()
    # position_details_example()
    # emergency_stop_example()
    # database_integration()
    # pre_trade_checks_example()
    # wallet_management()
    # advanced_configuration()
