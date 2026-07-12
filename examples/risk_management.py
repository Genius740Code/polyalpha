"""
Risk Management Example for Paper Trading

This example demonstrates the new risk management features in paper trading,
including daily loss limits, trade limits, position size limits, and more.
"""

import polyalpha

# Example 1: Basic risk management with default settings
print("=== Example 1: Default Risk Management ===")
client = polyalpha.Client(balance=100.0)

# Get risk summary
summary = client.paper.get_risk_summary()
print(f"Daily P&L: ${summary['daily_pnl']:.2f}")
print(f"Trades today: {summary['daily_trades']}")
print(f"Max daily loss: ${summary['max_daily_loss']:.2f}")
print(f"Max trades per day: {summary['max_trades_per_day']}")
print(f"Remaining loss limit: ${summary['remaining_loss_limit']:.2f}")
print(f"Remaining trades: {summary['remaining_trades']}")
print()

# Example 2: Custom risk management configuration
print("=== Example 2: Custom Risk Configuration ===")
from polyalpha.trading.paper import PaperConfig

config = PaperConfig(
    enable_risk_management=True,
    max_daily_loss=100.0,          # Stop trading if daily loss exceeds $100
    max_trades_per_day=20,         # Maximum 20 trades per day
    max_order_size=50.0,           # Maximum $50 per order
    max_position_size=100.0,      # Maximum $100 position per market
    max_open_positions=5,          # Maximum 5 concurrent positions
    max_risk_per_trade=0.05,      # Maximum 5% of balance per trade
)

client = polyalpha.Client(balance=100.0, paper_config=config)
print("Custom risk configuration applied")
print()

# Example 3: Risk limits in action
print("=== Example 3: Risk Limits Enforcement ===")
config = PaperConfig(
    max_order_size=25.0,
    max_risk_per_trade=0.30,  # Allow larger orders for this example
)

client = polyalpha.Client(balance=100.0, paper_config=config)

# Create a mock market for demonstration
class MockMarket:
    def __init__(self):
        self.id = "test-market"
        self.slug = "test-market"
        self.up_price = 0.55
        self.down_price = 0.45

market = MockMarket()

# This order should succeed (under limit)
try:
    order = client.paper.buy(market, side="UP", amount=20.0)
    print(f"✓ Order succeeded: ${order.amount:.2f}")
except ValueError as e:
    print(f"✗ Order failed: {e}")

# This order should fail (over limit)
try:
    order = client.paper.buy(market, side="UP", amount=30.0)
    print(f"✓ Order succeeded: ${order.amount:.2f}")
except ValueError as e:
    print(f"✗ Order failed: {e}")

print()

# Example 4: Daily trade limit
print("=== Example 4: Daily Trade Limit ===")
config = PaperConfig(
    max_trades_per_day=3,
    max_risk_per_trade=0.20,
)

client = polyalpha.Client(balance=100.0, paper_config=config)

# First 3 trades should succeed
for i in range(3):
    try:
        order = client.paper.buy(market, side="UP", amount=10.0)
        print(f"✓ Trade {i+1} succeeded")
    except ValueError as e:
        print(f"✗ Trade {i+1} failed: {e}")

# 4th trade should fail due to daily limit
try:
    order = client.paper.buy(market, side="UP", amount=10.0)
    print(f"✓ Trade 4 succeeded")
except ValueError as e:
    print(f"✗ Trade 4 failed: {e}")

print()

# Example 5: Reset daily limits
print("=== Example 5: Reset Daily Limits ===")
client.paper.reset_daily_limits()
print("Daily limits reset")

# Now the 4th trade should succeed
try:
    order = client.paper.buy(market, side="UP", amount=10.0)
    print(f"✓ Trade after reset succeeded")
except ValueError as e:
    print(f"✗ Trade after reset failed: {e}")

print()

# Example 6: Disable risk management
print("=== Example 6: Disable Risk Management ===")
config = PaperConfig(
    enable_risk_management=False,
    max_order_size=10.0,  # This limit will be ignored
)

client = polyalpha.Client(balance=100.0, paper_config=config)

# This order should succeed even though it exceeds the "limit"
try:
    order = client.paper.buy(market, side="UP", amount=50.0)
    print(f"✓ Order succeeded with risk management disabled: ${order.amount:.2f}")
except ValueError as e:
    print(f"✗ Order failed: {e}")

print()

print("=== Risk Management Summary ===")
print("Risk management helps protect your paper trading account by:")
print("- Limiting daily losses to prevent catastrophic drawdowns")
print("- Limiting the number of trades per day to prevent overtrading")
print("- Limiting order sizes to control risk per trade")
print("- Limiting position sizes to manage exposure per market")
print("- Limiting open positions to prevent over-diversification")
print("- Automatically tracking daily P&L and trade count")
print("- Resetting daily limits automatically at midnight UTC")
