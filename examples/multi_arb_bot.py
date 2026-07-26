"""
Multi-asset arbitrage with candle-window entry + BTC volatility guard.

Strategy:
  1. Hub discovers BTC, ETH, SOL on 15m timeframe
  2. Per-asset strategies calculate arb spread (UP vs DOWN pricing gap)
  3. Candle gate: only trade in first 300s of 900s (15m) candle
  4. BTC volatility guard: if BTC.roc(5) > 5% => skip ALL trades
  5. Entry: when spread > threshold AND BTC calm => buy undervalued side
  6. Output: per-strategy stats table (P&L, trades, win rate)

Usage:
    python examples/multi_arb_bot.py
"""
import polyalpha

hub = polyalpha.BotHub("BTC", "15m", default_balance=1000)


def btc_is_calm(ctx, max_roc_pct=5.0):
    roc = ctx.indicators.roc(5)
    if roc is None:
        return True
    return abs(roc) < max_roc_pct


def calc_spread(ctx):
    if ctx.price.up and ctx.price.down:
        return abs(ctx.price.up - ctx.price.down) / max(ctx.price.up, ctx.price.down) * 100
    return 0.0


@hub.strategy("btc_arb")
def btc_arb(ctx):
    if not btc_is_calm(ctx):
        return
    if ctx.seconds_in > 300:
        return
    spread = calc_spread(ctx)
    if spread > 2.0 and ctx.price.up > 0.9:
        ctx.buy_in_window("UP", 30, 0, 300)


@hub.strategy("eth_arb")
def eth_arb(ctx):
    if not btc_is_calm(ctx):
        return
    if ctx.seconds_in > 300:
        return
    spread = calc_spread(ctx)
    if spread > 3.0 and ctx.price.down < 0.15:
        ctx.buy_in_window("DOWN", 25, 0, 300)


@hub.strategy("sol_arb")
def sol_arb(ctx):
    if not btc_is_calm(ctx):
        return
    if ctx.seconds_in > 300:
        return
    spread = calc_spread(ctx)
    if spread > 2.5:
        side = "UP" if ctx.price.up > ctx.price.down else "DOWN"
        ctx.buy_in_window(side, 20, 0, 300)


hub.run()
print(f"\nFinal stats: {hub.stats}")
