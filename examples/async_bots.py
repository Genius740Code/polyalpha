"""
Async bot example — run multiple strategies concurrently in one event loop.

Usage
-----
    python examples/async_bots.py
"""

import asyncio
import sys, os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))
import polyalpha

btc = polyalpha.Bot("BTC", "5m", balance=100.0)
eth = polyalpha.Bot("ETH", "5m", balance=100.0)

@btc.on_tick
def btc_strategy(ctx):
    if ctx.price.up > 0.9:
        ctx.buy("UP", 10)

@eth.on_tick
def eth_strategy(ctx):
    if ctx.price.down > 0.85:
        ctx.buy("DOWN", 10)

async def main():
    await asyncio.gather(
        btc.run_async(),
        eth.run_async(),
    )

try:
    asyncio.run(main())
except KeyboardInterrupt:
    btc.stop()
    eth.stop()

print("BTC:", btc.stats)
print("ETH:", eth.stats)
