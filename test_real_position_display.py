"""
Example usage for real trading position display functionality.

Note: This requires actual Polymarket API credentials and a wallet with USDC on Polygon.
For testing without real credentials, use the paper trading engine instead.
"""

import sys
sys.path.insert(0, 'src')

from polyalpha.trading.real import RealTradingEngine, RealTradingConfig

# Example configuration for real trading
config = RealTradingConfig(
    private_key="your-private-key-here",  # Replace with actual private key
    rpc_url="https://polygon-rpc.com",
    polymarket_api_key="your-polymarket-api-key",  # Replace with actual API key
    position_sizing="fixed",
    fixed_amount=10.0,  # $10 per trade
    max_order_size=100.0,  # Maximum $100 per order
    max_risk_per_trade=0.02,  # 2% risk per trade
)

# Initialize real trading engine
# engine = RealTradingEngine(
#     private_key="your-private-key-here",
#     rpc_url="https://polygon-rpc.com",
#     polymarket_api_key="your-polymarket-api-key",
#     config=config,
#     simulate=False,  # Set to False for production trading
# )

print("Real Trading Position Display - Example Usage")
print("=" * 60)
print()
print("To use real trading position display:")
print()
print("1. Set up your Polymarket API credentials")
print("2. Ensure you have USDC in your Polygon wallet")
print("3. Initialize the RealTradingEngine with your credentials")
print("4. Use the following methods:")
print()
print("   # Show live positions")
print("   engine.show_positions()")
print()
print("   # Show all positions including closed")
print("   engine.show_positions(show_all=True)")
print()
print("   # Get position history statistics")
print("   history = engine.position_history()")
print("   print(f'Win rate: {history[\"win_rate\"]:.2f}%')")
print()
print("Note: For testing without real credentials, use paper trading:")
print("   client = polyalpha.Client(balance=1000.0)")
print("   client.paper.show_positions()")
print()
print("=" * 60)
