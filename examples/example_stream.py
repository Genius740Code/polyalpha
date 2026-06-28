"""
Phase 2 example — real-time WebSocket price streaming.

Run from the project root:
    python examples/example_stream.py
    python examples/example_stream.py --asset ETH --timeframe 15m
    python examples/example_stream.py --asset BTC --timeframe 5m --log DEBUG
"""

import sys
import os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))

import argparse
import time
import polyalpha

parser = argparse.ArgumentParser()
parser.add_argument("--asset",     default="BTC",     help="BTC, ETH, SOL, XRP, DOGE")
parser.add_argument("--timeframe", default="5m",      help="5m, 15m, 1h, 4h, 24h")
parser.add_argument("--log",       default="WARNING", help="DEBUG, INFO, WARNING")
args = parser.parse_args()

client = polyalpha.Client(log_level=args.log)

# ── 1. Discover market ────────────────────────────────────────────────
print(f"Finding {args.asset} {args.timeframe} market...")
market = client.markets.latest(args.asset, args.timeframe)
print(f"  {market.question}")
print(f"  UP={market.yes_price:.3f}  DOWN={market.no_price:.3f}")
print(f"  URL: {market.url}\n")

# ── 2. Create stream ──────────────────────────────────────────────────
stream = client.stream(market)

# ── 3. Register event handlers ────────────────────────────────────────

@stream.on("connect")
def on_connect():
    print(f"Connected — streaming {market.slug}")
    print("Press Ctrl+C to stop.\n")

@stream.on("price")
def on_price(up: float, down: float):
    bar_len = 30
    fill = int(round(up * bar_len))
    bar  = "█" * fill + "░" * (bar_len - fill)
    ts   = time.strftime("%H:%M:%S")
    print(f"  [{ts}]  UP={up:.4f}  DOWN={down:.4f}  [{bar}]")

@stream.on("book")
def on_book(data: dict):
    bids = data.get("bids", [])
    asks = data.get("asks", [])
    if bids and asks:
        best_bid = bids[0].get("price", "?")
        best_ask = asks[0].get("price", "?")
        print(f"  [book]   bid={best_bid}  ask={best_ask}")

@stream.on("trade")
def on_trade(data: dict):
    price = data.get("price", "?")
    size  = data.get("size",  "?")
    print(f"  [trade]  price={price}  size={size}")

@stream.on("close")
def on_close():
    print("\nMarket resolved — stream closed.")
    sys.exit(0)

@stream.on("error")
def on_error(exc: Exception):
    print(f"\nStream error: {exc}")

# ── 4. Start (blocking) ───────────────────────────────────────────────
try:
    stream.start()
except KeyboardInterrupt:
    print("\nStopped.")
    stream.stop()