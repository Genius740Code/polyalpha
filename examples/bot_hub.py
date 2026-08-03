"""
BotHub with 3 strategies + on("tick") timer + every(30) timer.

Usage:
    python examples/bot_hub.py
"""
import polyalpha

hub = polyalpha.BotHub("ETH", "15m", default_balance=500)

@hub.strategy("bb_rsi")
def bb_rsi(ctx):
    rsi = ctx.indicators.rsi(14)
    bb = ctx.indicators.bollinger_bands(20, 2.0)
    if bb and ctx.price.down < bb.lower and rsi < 30:
        ctx.buy("DOWN", 20)
    elif bb and ctx.price.up > bb.upper and rsi > 70:
        ctx.buy("UP", 20)

@hub.strategy("sma_cross")
def sma_cross(ctx):
    sma_fast = ctx.indicators.sma(10)
    sma_slow = ctx.indicators.sma(30)
    if sma_fast and sma_slow and sma_fast > sma_slow and ctx.price.up > 0.85:
        ctx.buy("UP", 15)

@hub.strategy("mean_revert")
def mean_revert(ctx):
    bb = ctx.indicators.bollinger_bands(20, 2.0)
    if bb and ctx.price.down < bb.lower:
        ctx.buy("DOWN", 25)

_ticks = 0

@hub.on("tick")
def on_tick(up, down):
    global _ticks
    _ticks += 1
    if _ticks % 30 == 0:
        print(f"[Timer] Price: UP={up:.4f} DOWN={down:.4f}")

hub.run()
