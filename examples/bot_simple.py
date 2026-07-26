"""
Minimal Bot — price > 0.9 + RSI > 50 on 5m BTC candles.

Usage:
    python examples/bot_simple.py
"""
import polyalpha
from polyalpha.conditions import and_, price_above, rsi_above

bot = polyalpha.Bot("BTC", "5m", balance=100)

@bot.on_tick
def strategy(ctx):
    if ctx.price.up > 0.9 and ctx.indicators.rsi(14) > 50:
        ctx.buy("UP", 20)

bot.when(
    and_(rsi_above(50), price_above("UP", 0.9))
).buy("UP", 20)

bot.run()
