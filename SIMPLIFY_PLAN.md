# Simplify Plan — Make Bot Building Truly Minimal

## Problem

Users still write 60-100 lines to build a working bot. The library gives tools (stream, paper, markets) but no **bot framework**. Users wire everything themselves every time.

---

## 1. Add `Bot` — One-line bot runner

The single biggest change. A class that owns the full loop: discover → stream → tick → trade → resolve → repeat.

```python
bot = polyalpha.Bot("BTC", "5m", balance=500)

@bot.on_tick
def strategy(ctx):
    if ctx.price.up > 0.9 and ctx.rsi > 50:
        ctx.buy("UP", 20)

bot.run()  # blocking, auto-rollover
```

That's it. No manual stream setup, no resolution handling, no order management.

**Key design:**
- `ctx.price.up / .down` — always-live prices from the auto-stream
- `ctx.rsi / .sma / .ema` — calculated on incoming price data (optional dep)
- `ctx.buy("UP", 20)` — executes market or limit based on config
- Auto-resolves, auto-rolls to next market, tracks P&L
- `bot.run(paper=True)` / `bot.run(paper=False)` for live

Under the hood it wraps what the Sniper does, but the user sees 5 lines.

---

## 2. Pre-built condition library

```python
from polyalpha.conditions import rsi_above, crossed_above, and_

bot = polyalpha.Bot("BTC", "5m")
bot.when(
    and_(rsi_above(50), crossed_above("up", 0.9)),
).buy("UP", 20)
bot.run()
```

Common indicators as composable conditions. Users combine them without writing any logic.

---

## 3. One-call backtest

```python
bot = polyalpha.Bot("BTC", "5m")
bot.strategy = lambda ctx: ctx.buy("UP", 20) if ctx.price.up > 0.9 else None
result = bot.backtest(days=30)  # replays historical data
print(result.win_rate, result.total_pnl)
```

Replays the same strategy function against archived market data. Zero additional setup.

---

## 4. Kill the boilerplate in existing examples

Most example code is argparse + error handling + print statements. Provide:
- `bot.demo()` — dry-run with print output
- `bot.stats()` — running P&L, win rate, trades
- Sensible defaults everywhere (asset="BTC", timeframe="5m", balance=100)

---

## Priority

| # | Item | Effort | Impact |
|---|------|--------|--------|
| 1 | `Bot` class with `@on_tick` | Medium | High — the core abstraction |
| 2 | `ctx.price`, `ctx.buy()` API | Small | High — must exist for #1 |
| 3 | Auto-loop (discover → resolve → rollover) | Medium | High — removes 90% of user code |
| 4 | Pre-built conditions library | Medium | Medium — nice to have |
| 5 | Backtest on Bot | Large | Medium — valuable but complex |
| 6 | Clean up examples | Small | Medium — sets the right impression |

**Ship 1-3 first.** That alone cuts user code from ~80 lines → ~5 lines.
