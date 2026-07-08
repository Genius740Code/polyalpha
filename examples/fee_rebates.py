"""
Fee Rebate System Example

This example demonstrates the fee rebate tracking system in polyalpha.
It shows how volume-based rebates and maker rebates work to reduce trading costs.

Usage
-----
    python examples/fee_rebates.py
    python examples/fee_rebates.py --disable-rebates
    python examples/fee_rebates.py --custom-tiers '{"0":0.0,"500":0.10,"2000":0.20}'
"""

import argparse
import sys
import os

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))
import polyalpha
from polyalpha.trading.paper import PaperConfig

parser = argparse.ArgumentParser(description="polyalpha fee rebate demonstration")
parser.add_argument("--disable-rebates", action="store_true", help="Disable fee rebates for comparison")
parser.add_argument("--custom-tiers", type=str, help="Custom rebate tiers as JSON string")
parser.add_argument("--trades", type=int, default=10, help="Number of simulated trades")
args = parser.parse_args()

# Parse custom rebate tiers if provided
rebate_tiers = None
if args.custom_tiers:
    import json
    try:
        rebate_tiers = json.loads(args.custom_tiers)
        print(f"Using custom rebate tiers: {rebate_tiers}")
    except json.JSONDecodeError:
        print(f"Invalid JSON for custom-tiers: {args.custom_tiers}")
        print("Using default rebate tiers")
        rebate_tiers = None

# Create configuration with rebates enabled by default
config = PaperConfig(
    fee_mode="custom",
    custom_fee_rate=0.02,  # 2% fee
    enable_rebates=not args.disable_rebates,
    rebate_tiers=rebate_tiers,
    maker_rebate_pct=0.25,  # 25% additional rebate for maker orders
)

print("=" * 70)
print("FEE REBATE SYSTEM DEMONSTRATION")
print("=" * 70)
print(f"\nConfiguration:")
print(f"  Fee rate: {config.custom_fee_rate:.1%}")
print(f"  Rebates enabled: {config.enable_rebates}")
print(f"  Maker rebate bonus: {config.maker_rebate_pct:.1%}")
if config.rebate_tiers:
    print(f"  Volume rebate tiers:")
    for threshold, rate in sorted(config.rebate_tiers.items()):
        print(f"    ${threshold:>8.0f}+: {rate * 100:>5.1f}%")
print()

# Initialize client with $1000 balance
client = polyalpha.Client(balance=1000.0, paper_config=config, log_level="WARNING")

print(f"Starting balance: ${client.paper.balance:.2f}")
print()

# Simulate a series of trades to demonstrate volume-based rebates
print("Simulating trades to demonstrate volume-based rebates...")
print("-" * 70)

for i in range(args.trades):
    # Alternate between market (taker) and limit (maker) orders
    is_maker = (i % 2 == 0)
    
    # Simulate a market object (in real usage, this would come from client.markets)
    class MockMarket:
        def __init__(self, price):
            self.id = f"market_{i}"
            self.slug = f"btc-updown-5m-{i}"
            self.question = f"Will BTC be higher in 5 minutes? (Trade {i+1})"
            self.up_price = price
            self.down_price = 1.0 - price
    
    # Vary price slightly
    price = 0.5 + (i % 5) * 0.1
    market = MockMarket(price)
    
    # Place order
    amount = 100.0  # $100 per trade
    
    if is_maker:
        # Limit order (maker) - gets additional rebate
        order = client.paper.limit(market, side="UP", price=price, amount=amount)
        # Simulate immediate fill for demonstration
        client.paper._fill_limit(order, price)
        order_type = "LIMIT (maker)"
    else:
        # Market order (taker)
        order = client.paper.buy(market, side="UP", amount=amount)
        order_type = "MARKET (taker)"
    
    # Get current rebate stats
    stats = client.paper.get_rebate_stats()
    
    print(f"Trade {i+1:2d}: {order_type:20s} | Amount: ${amount:6.2f} | "
          f"Fee: ${order.fee:6.4f} | Rebate: ${order.rebate_amount:6.4f} | "
          f"Net Fee: ${order.fee - order.rebate_amount:6.4f} | "
          f"Volume: ${stats['total_volume']:7.2f} | "
          f"Tier: {stats['current_rebate_rate']*100:5.1f}%")

print("-" * 70)
print()

# Show final statistics
print("FINAL STATISTICS")
print("=" * 70)
client.paper.summary()
print()
client.paper.fee_summary()
print()

# Show comparison if rebates were disabled
if config.enable_rebates:
    print("COMPARISON: What if rebates were disabled?")
    print("-" * 70)
    print(f"  Total fees without rebates: ${client.paper._total_fees_paid + client.paper._total_rebates_earned:.4f}")
    print(f"  Total fees with rebates:    ${client.paper._total_fees_paid:.4f}")
    print(f"  Savings from rebates:       ${client.paper._total_rebates_earned:.4f}")
    print(f"  Effective fee reduction:    {(client.paper._total_rebates_earned / (client.paper._total_fees_paid + client.paper._total_rebates_earned)) * 100:.1f}%")
    print("-" * 70)
    print()

# Show breakdown by order type
print("ORDER TYPE BREAKDOWN")
print("-" * 70)
print(f"  Taker orders:")
print(f"    Fees paid:     ${client.paper._taker_fees:.4f}")
print(f"    Rebates earned: ${client.paper._taker_rebates:.4f}")
print(f"    Net fees:       ${client.paper._taker_fees - client.paper._taker_rebates:.4f}")
print()
print(f"  Maker orders:")
print(f"    Fees paid:     ${client.paper._maker_fees:.4f}")
print(f"    Rebates earned: ${client.paper._maker_rebates:.4f}")
print(f"    Net fees:       ${client.paper._maker_fees - client.paper._maker_rebates:.4f}")
print("-" * 70)
print()

print("Key Takeaways:")
print("  1. Volume-based rebates increase as your trading volume grows")
print("  2. Maker orders (limit orders) get an additional rebate bonus")
print("  3. Rebates can significantly reduce your effective trading costs")
print("  4. The system tracks both taker and maker fees separately")
