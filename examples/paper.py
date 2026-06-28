"""
Paper trading example.

Usage
-----
    python examples/paper.py
    python examples/paper.py --side DOWN --amount 25
    python examples/paper.py --limit 0.92 --amount 20
"""

import argparse
import sys
import os

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))
import polyalpha

parser = argparse.ArgumentParser(description="polyalpha paper trading")
parser.add_argument("--asset",     default="BTC",   help="BTC | ETH | SOL | XRP | DOGE")
parser.add_argument("--timeframe", default="5m",    help="5m | 15m | 1h | 4h | 24h")
parser.add_argument("--side",      default="UP",    help="UP | DOWN")
parser.add_argument("--amount",    default=10.0,    type=float, help="USDC to spend")
parser.add_argument("--limit",     default=None,    type=float, help="Limit trigger price")
parser.add_argument("--balance",   default=100.0,   type=float, help="Starting paper balance")
args = parser.parse_args()

client = polyalpha.Client(balance=args.balance, log_level="INFO")

print(f"Paper balance: ${client.paper.balance:.2f}\n")

# ── 1. Discover market ─────────────────────────────────────────────────────────
print(f"Finding {args.asset} {args.timeframe} market…")
market = client.markets.latest(args.asset, args.timeframe)
print(f"  {market.question}")
print(f"  UP={market.up_price:.3f}  DOWN={market.down_price:.3f}\n")

# ── 2. Place order ─────────────────────────────────────────────────────────────
if args.limit:
    print(f"Placing limit {args.side} @ {args.limit} for ${args.amount:.2f}…")
    order = client.paper.limit(market, side=args.side, price=args.limit, amount=args.amount)
    print(f"  Order {order.id[:8]}  status={order.status}\n")
else:
    print(f"Placing market {args.side} for ${args.amount:.2f}…")
    order = client.paper.buy(market, side=args.side, amount=args.amount)
    print(f"  Filled {order.shares:.4f} shares @ {order.price:.3f}")
    print(f"  Fee: ${order.fee:.4f}  status={order.status}\n")

# ── 3. Stream prices + auto-fill limits ────────────────────────────────────────
stream = client.stream(market)
client.paper.attach_stream(stream, market)

@stream.on("connect")
def on_connect():
    print(f"Streaming {market.slug} — watching prices and pending limits.\n")

@stream.on("price")
def on_price(up: float, down: float):
    positions = client.paper.positions()
    for pos in positions:
        print(
            f"  {pos.side:<4}  price={pos.current_price:.4f}"
            f"  shares={pos.shares:.4f}  pnl=${pos.pnl:>+.4f}"
        )

@stream.on("close")
def on_close():
    print("\nMarket resolved.")
    outcome = input("Enter outcome (UP/DOWN): ").strip().upper()
    if outcome in ("UP", "DOWN"):
        client.paper.resolve(market, outcome)
    print()
    client.paper.summary()
    sys.exit(0)

@stream.on("error")
def on_error(exc: Exception):
    print(f"Stream error: {exc}")

print("Streaming live (Ctrl+C to stop and print summary)\n")
try:
    stream.start()
except KeyboardInterrupt:
    print()
    client.paper.summary()
