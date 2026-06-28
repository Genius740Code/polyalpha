"""
Phase 1 example — market discovery.

Run from the project root:
    python examples/examples_markets.py
    python examples/examples_markets.py --timeframe 15m
    python examples/examples_markets.py --asset ETH
"""

import sys
import os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))

import argparse
import polyalpha

parser = argparse.ArgumentParser()
parser.add_argument("--asset",     default=None,  help="BTC, ETH, SOL, XRP, DOGE (default: all)")
parser.add_argument("--timeframe", default="5m",  help="5m, 15m, 1h, 4h, 24h")
args = parser.parse_args()

client = polyalpha.Client(log_level="INFO")

# ── Single asset ──────────────────────────────────────────────────────
if args.asset:
    print(f"=== {args.asset} {args.timeframe} ===")
    try:
        market = client.markets.latest(args.asset, args.timeframe)
        market.show()
        print(f"\nUP   token : {market.yes_token}")
        print(f"DOWN token : {market.no_token}")
        print(f"UP   price : {market.yes_price}")
        print(f"DOWN price : {market.no_price}")
    except polyalpha.MarketNotFound as e:
        print(f"Not found: {e}")
    sys.exit(0)

# ── All timeframes for BTC ────────────────────────────────────────────
print("=== BTC across timeframes ===")
for tf in ["5m", "15m", "1h", "4h", "24h"]:
    try:
        m = client.markets.latest("BTC", tf)
        print(f"BTC {tf:>4s}  UP={m.yes_price:.3f}  DN={m.no_price:.3f}  ends={m.end_time[:19]}")
    except polyalpha.MarketNotFound:
        print(f"BTC {tf:>4s}  (not found)")

print()

# ── All assets at a timeframe ─────────────────────────────────────────
print(f"=== All assets at {args.timeframe} ===")
markets = client.markets.available(args.timeframe)
if not markets:
    print("No markets found.")
else:
    for m in markets:
        asset = m.slug.split("-")[0].upper()
        print(f"{asset:>4s}  UP={m.yes_price:.3f}  DN={m.no_price:.3f}  vol=${m.volume:,.0f}  liq=${m.liquidity:,.0f}")

print()

# ── Direct slug lookup ────────────────────────────────────────────────
print("=== Direct slug lookup ===")
btc = client.markets.latest("BTC", "5m")
same = client.markets.get(btc.slug)
print(f"Fetched by slug: {same.question}")