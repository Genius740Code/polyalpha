"""
Market discovery example.

Usage
-----
    python examples/market.py
    python examples/market.py --asset ETH --timeframe 15m
    python examples/market.py --asset BTC
"""

import argparse
import sys
import os

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))
import polyalpha

parser = argparse.ArgumentParser(description="polyalpha market discovery")
parser.add_argument("--asset",     default=None,  help="BTC, ETH, SOL, XRP, DOGE (default: all)")
parser.add_argument("--timeframe", default="5m",  help="5m | 15m | 1h | 4h | 24h")
args = parser.parse_args()

client = polyalpha.Client(log_level="INFO")

# ── Single asset ───────────────────────────────────────────────────────────────
if args.asset:
    try:
        market = client.markets.latest(args.asset, args.timeframe)
        market.show()
    except polyalpha.MarketNotFound as exc:
        print(f"Market not found: {exc}")
    sys.exit(0)

# ── BTC across all timeframes ──────────────────────────────────────────────────
print("BTC across timeframes")
print("─" * 50)
for tf in ["5m", "15m", "1h", "4h", "24h"]:
    try:
        m = client.markets.latest("BTC", tf)
        print(f"  BTC {tf:>4s}  UP={m.up_price:.3f}  DOWN={m.down_price:.3f}  ends {m.end_time[:19]}")
    except polyalpha.MarketNotFound:
        print(f"  BTC {tf:>4s}  (not found)")

print()

# ── All assets at the chosen timeframe ────────────────────────────────────────
print(f"All assets at {args.timeframe}")
print("─" * 50)
markets = client.markets.available(args.timeframe)
if not markets:
    print("  No markets found.")
else:
    for m in markets:
        asset = m.slug.split("-")[0].upper()
        print(
            f"  {asset:>4s}  UP={m.up_price:.3f}  DOWN={m.down_price:.3f}"
            f"  vol=${m.volume:>10,.0f}  liq=${m.liquidity:>10,.0f}"
        )

print()

# ── Direct slug lookup ─────────────────────────────────────────────────────────
print("Direct slug lookup")
print("─" * 50)
btc  = client.markets.latest("BTC", "5m")
same = client.markets.get(btc.slug)
print(f"  {same.question}")
