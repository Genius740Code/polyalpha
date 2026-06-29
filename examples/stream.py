"""
Real-time price streaming example.

Usage
-----
    python examples/stream.py
    python examples/stream.py --asset ETH --timeframe 15m
    python examples/stream.py --asset BTC --log DEBUG
    python examples/stream.py --rate-limit 10
"""

import argparse
import sys
import os
import time

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))
import polyalpha

parser = argparse.ArgumentParser(description="polyalpha WebSocket stream")
parser.add_argument("--asset",     default="BTC",     help="BTC | ETH | SOL | XRP | DOGE")
parser.add_argument("--timeframe", default="5m",      help="5m | 15m | 1h | 4h | 24h")
parser.add_argument("--log",       default="WARNING",  help="DEBUG | INFO | WARNING")
parser.add_argument("--rate-limit", type=int, default=None, help="Max API requests per second (default: unlimited)")
args = parser.parse_args()

client = polyalpha.Client(log_level=args.log, rate_limit=args.rate_limit)

# ── 1. Discover market ─────────────────────────────────────────────────────────
print(f"Finding {args.asset} {args.timeframe} market…")
market = client.markets.latest(args.asset, args.timeframe)
print(f"  {market.question}")
print(f"  UP={market.up_price:.3f}  DOWN={market.down_price:.3f}")
print(f"  {market.url}\n")

# ── 2. Set up stream ───────────────────────────────────────────────────────────
stream = client.stream(market)

@stream.on("connect")
def on_connect():
    print(f"Connected — streaming {market.slug}")
    print("Press Ctrl+C to stop.\n")

@stream.on("price")
def on_price(up: float, down: float):
    bar_len = 30
    fill    = int(round(up * bar_len))
    bar     = "█" * fill + "░" * (bar_len - fill)
    ts      = time.strftime("%H:%M:%S")
    print(f"  [{ts}]  UP={up:.4f}  DOWN={down:.4f}  [{bar}]")

@stream.on("book")
def on_book(data: dict):
    bids = data.get("bids", [])
    asks = data.get("asks", [])
    if bids and asks:
        print(f"  [book]  bid={bids[0].get('price')}  ask={asks[0].get('price')}")

@stream.on("trade")
def on_trade(data: dict):
    print(f"  [trade]  price={data.get('price')}  size={data.get('size')}")

@stream.on("close")
def on_close():
    print("\nMarket resolved — stream closed.")
    sys.exit(0)

@stream.on("error")
def on_error(exc: Exception):
    print(f"\nStream error: {exc}")

# ── 3. Start (blocking) ────────────────────────────────────────────────────────
try:
    stream.start()
except KeyboardInterrupt:
    print("\nStopped.")
    stream.stop()
