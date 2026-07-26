"""
BotHub example — run multiple BTC 5-minute strategies from ONE data connection.

Compare this to running 20 separate Bot instances, each of which opens its
own WebSocket to Polymarket. With BotHub you get:

  • ONE market discovery REST call
  • ONE WebSocket stream
  • N isolated paper engines (one per strategy)

Each strategy has its own balance, positions, and P&L, but they all read
from the same price feed — so rate-limit pressure is 1x, not Nx.

This example demonstrates:
  - Basic strategy registration (@hub.strategy)
  - Variant registration with params (@hub.variant)
  - Event hooks (@hub.on)
  - Periodic timers (@hub.every)
  - Cross-variant comparison (hub.compare_variants)
  - Comparison report persistence (hub.load_run / hub.list_runs)

Usage:
    python examples/bot_hub.py
"""

import polyalpha

# Create a hub for BTC 5-minute markets. Every registered strategy gets
# default_balance unless overridden in @hub.strategy(...).
hub = polyalpha.BotHub("BTC", "5m", default_balance=500)


# ── Strategies ────────────────────────────────────────────────────────────

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


# ═══ Variants ═════════════════════════════════════════════════════════════
# `variant()` is identical to `strategy()`. Use it when you want to
# emphasise that this entry carries parameter metadata for comparison.
# Strategies with non-empty `params` are included in compare_variants().

@hub.variant("contrarian_95", params={"threshold": 0.95})
def contrarian_95(ctx):
    if ctx.price.up > 0.95:
        ctx.buy("DOWN", 5)
    elif ctx.price.down < 0.05:
        ctx.buy("UP", 5)


@hub.variant("contrarian_98", params={"threshold": 0.98})
def contrarian_98(ctx):
    if ctx.price.up > 0.98:
        ctx.buy("DOWN", 5)
    elif ctx.price.down < 0.02:
        ctx.buy("UP", 5)


# Strategy 5 — SMA crossover (requires pandas for indicators).
@hub.strategy("sma_cross", balance=1000)
def sma_cross(ctx):
    sma = ctx.sma_20
    if sma is None:
        return
    if ctx.price.up > sma:
        ctx.buy("UP", 10)


# ── Event hooks ───────────────────────────────────────────────────────────

@hub.on("start")
def on_start():
    print("BotHub started!")


@hub.on("tick")
def on_tick(up, down):
    if up > 0.95:
        print(f"  [TICK] UP heavily favored: {up:.3f}")


@hub.on("candle_open")
def on_candle_open(open_price, candle_id):
    print(f"  [CANDLE] #{candle_id} opened at {open_price:.4f}")


@hub.on("error")
def on_error(name, exc):
    print(f"  [ERROR] Strategy '{name}' failed: {exc}")


# ── Periodic timer (every 30 seconds) ─────────────────────────────────────

@hub.every(30)
def status_check(up, down):
    print(f"  [STATUS] UP={up:.3f} DOWN={down:.3f} | "
          f"strategies={hub.strategy_count} ticks={hub.tick_count}")


# ── Main ──────────────────────────────────────────────────────────────────

if __name__ == "__main__":
    print(f"Starting BotHub with {hub.strategy_count} strategies/variants...")
    print(f"  asset={hub.asset} timeframe={hub.timeframe}")
    print(f"  names: {[s.name for s in hub.strategies]}")
    print(f"  variants: {[s.name for s in hub.variants if s.params]}")
    print()

    try:
        hub.run()
    except KeyboardInterrupt:
        hub.stop()
        print()
        print("── Comparison Report ──────────────────────────────────────")
        report = hub.compare_variants()
        report.print()
