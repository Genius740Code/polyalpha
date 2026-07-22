"""
Async stream example — stream prices without background threads.

Usage
-----
    python examples/async_stream.py
"""

import asyncio
import sys, os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))
import polyalpha

client = polyalpha.Client()
market = client.markets.latest("BTC", "5m")
stream = client.stream(market)

@stream.on("price")
def on_price(up, down):
    print(f"UP={up:.4f}  DOWN={down:.4f}")

@stream.on("close")
def on_close():
    print("Market resolved")

async def main():
    await stream.run_async()

try:
    asyncio.run(main())
except KeyboardInterrupt:
    stream.stop()
