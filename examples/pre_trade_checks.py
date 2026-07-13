"""
Pre-trade checks example.

This example demonstrates the pre-trade checks feature in paper trading,
which validates various conditions before allowing a trade to proceed.

Usage
-----
    python examples/pre_trade_checks.py
    python examples/pre_trade_checks.py --skip-checks
"""

import argparse
import sys
import os

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))
import polyalpha

parser = argparse.ArgumentParser(description="polyalpha pre-trade checks example")
parser.add_argument("--asset", default="BTC", help="BTC | ETH | SOL | XRP | DOGE")
parser.add_argument("--timeframe", default="5m", help="5m | 15m | 1h | 4h | 24h")
parser.add_argument("--side", default="UP", help="UP | DOWN")
parser.add_argument("--amount", default=10.0, type=float, help="USDC to spend")
parser.add_argument("--balance", default=100.0, type=float, help="Starting paper balance")
parser.add_argument("--skip-checks", action="store_true", help="Skip pre-trade checks and proceed directly")
args = parser.parse_args()

client = polyalpha.Client(balance=args.balance, log_level="INFO")

print(f"Paper balance: ${client.paper.balance:.2f}")
print()

# ── 1. Discover market ─────────────────────────────────────────────────────────
print(f"Finding {args.asset} {args.timeframe} market…")
market = client.markets.latest(args.asset, args.timeframe)
print(f"  {market.question}")
print(f"  UP={market.up_price:.3f}  DOWN={market.down_price:.3f}\n")

# ── 2. Run pre-trade checks ─────────────────────────────────────────────────────
print("Running pre-trade checks...")
checks = client.paper.pre_trade_checks(market, side=args.side, amount=args.amount)

print(f"  Balance OK: {checks['balance_ok']}")
print(f"  Market Open: {checks['market_open']}")
print(f"  Price Reasonable: {checks['price_reasonable']}")
print(f"  Can Proceed: {checks['can_proceed']}")

if checks['warnings']:
    print("\n  Warnings:")
    for warning in checks['warnings']:
        print(f"    - {warning}")

print()

# ── 3. Place order based on checks ────────────────────────────────────────────────
if not checks['can_proceed']:
    print("Pre-trade checks failed. Order not placed.")
    if args.skip_checks:
        print("  --skip-checks flag set, proceeding anyway...")
        print(f"  Placing market {args.side} for ${args.amount:.2f}…")
        order = client.paper.buy(market, side=args.side, amount=args.amount)
        print(f"  Filled {order.shares:.4f} shares @ {order.price:.3f}")
        print(f"  Fee: ${order.fee:.4f}  status={order.status}\n")
    else:
        print("  Use --skip-checks to proceed anyway (not recommended).")
        sys.exit(1)
else:
    print("Pre-trade checks passed. Placing order...")
    print(f"  Placing market {args.side} for ${args.amount:.2f}…")
    order = client.paper.buy(market, side=args.side, amount=args.amount)
    print(f"  Filled {order.shares:.4f} shares @ {order.price:.3f}")
    print(f"  Fee: ${order.fee:.4f}  status={order.status}\n")

# ── 4. Show position ─────────────────────────────────────────────────────────────
positions = client.paper.positions()
if positions:
    print("Current position:")
    for pos in positions:
        print(f"  {pos.side:<4}  shares={pos.shares:.4f}  avg_price=${pos.avg_price:.3f}  pnl=${pos.pnl:>+.4f}")
else:
    print("No open positions.")
