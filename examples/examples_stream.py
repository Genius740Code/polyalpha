"""
Phase 2 example — market discovery + real-time price streaming.

Run from the project root:
    python examples/examples_stream.py
    python examples/examples_stream.py --asset ETH --timeframe 15m
    python examples/examples_stream.py --slug btc-updown-5m-1751234700
"""

import sys
import os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))

import argparse
import polyalpha

parser = argparse.ArgumentParser()
parser.add_argument("--asset",     default="BTC",  help="BTC, ETH, SOL, XRP, DOGE")
parser.add_argument("--timeframe", default="5m",   help="5m, 15m, 1h, 4h, 24h")
parser.add_argument("--slug",      default=None,   help="Pin a specific market slug")
args = parser.parse_args()

client = polyalpha.Client(log_level="INFO")

# ── 1. Find market ──────────────────────────────────────────────────
if args.slug:
    market = client.markets.get(args.slug)
else:
    print(f"Finding latest {args.asset} {args.timeframe} market...")
    market = client.markets.latest(args.asset, args.timeframe)

market.show()
print()
print(f"UP   token: {market.yes_token[:20]}...")
print(f"DOWN token: {market.no_token[:20]}...")
print()

# ── 2. Stream prices ─────────────────────────────────────────────────
stream = client.stream(market)

@stream.on("connect")
def on_connect():
    print(f"Connected — streaming {market.slug}\n")

@stream.on("price")
def on_price(up: float, down: float):
    bar_up   = "█" * int(up   * 30)
    bar_dn   = "█" * int(down * 30)
    print(f"  UP  {up:.3f}  {bar_up}")
    print(f"  DN  {down:.3f}  {bar_dn}")
    print()

@stream.on("trade")
def on_trade(data: dict):
    print(f"  TRADE: {data.get('price')} size={data.get('size')}")

@stream.on("close")
def on_close():
    print("Market resolved.")

@stream.on("error")
def on_error(exc: Exception):
    print(f"Error: {exc}")

stream.start()  # blocking — Ctrl+C to stop