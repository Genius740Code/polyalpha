"""
Bot example — ~10 lines for a working strategy.

Usage
-----
    python examples/bot_simple.py
    python examples/bot_simple.py --asset ETH --timeframe 15m
    python examples/bot_simple.py --balance 500
"""

import sys, os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))
import polyalpha

bot = polyalpha.Bot("BTC", "5m", balance=100.0)

@bot.on_tick
def strategy(ctx):
    if ctx.price.up > 0.9:
        ctx.buy("UP", 10)
        bot.stop()

try:
    bot.run()
except KeyboardInterrupt:
    bot.stop()

print(bot.stats)
