"""
BotHub example — run multiple BTC 5-minute strategies from ONE data connection.

Compare this to running 20 separate Bot instances, each of which opens its
own WebSocket to Polymarket. With BotHub you get:

  • ONE market discovery REST call
  • ONE WebSocket stream
  • N isolated paper engines (one per strategy)

Each strategy has its own balance, positions, and P&L, but they all read
from the same price feed — so rate-limit pressure is 1x, not Nx.

Usage:
    python examples/bot_hub.py
"""

import polyalpha

# Create a hub for BTC 5-minute markets. Every registered strategy gets
# default_balance unless overridden in @hub.strategy(...).
hub = polyalpha.BotHub("BTC", "5m", default_balance=500)


# Strategy 1 — momentum: bet UP when the price is already high.
@hub.strategy("momentum", balance=500)
def momentum(ctx):
    if ctx.price.up > 0.90 and (ctx.rsi is None or ctx.rsi > 50):
        ctx.buy("UP", 20)


# Strategy 2 — value: bet DOWN when the UP price is very low.
@hub.strategy("value", balance=300)
def value(ctx):
    if ctx.price.up < 0.10:
        ctx.buy("DOWN", 15)


# Strategy 3 — contrarian: fade extreme moves.
@hub.strategy("contrarian", balance=200)
def contrarian(ctx):
    if ctx.price.up > 0.95:
        ctx.buy("DOWN", 5)
    elif ctx.price.down < 0.05:
        ctx.buy("UP", 5)


# Strategy 4 — SMA crossover (requires pandas for indicators).
@hub.strategy("sma_cross", balance=1000)
def sma_cross(ctx):
    sma = ctx.sma_20
    if sma is None:
        return
    if ctx.price.up > sma:
        ctx.buy("UP", 10)


if __name__ == "__main__":
    print(f"Starting BotHub with {hub.strategy_count} strategies...")
    print(f"  asset      = {hub.asset}")
    print(f"  timeframe  = {hub.timeframe}")
    print(f"  total bal  = ${sum(s.balance for s in hub._strategies):.2f}")
    print()
    hub.run()
