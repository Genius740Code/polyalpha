# Examples & Strategy Catalog — Implementation Plan

## Goal
Rebuild the empty `examples/` directory with 15 runnable `.py` scripts and create a `strats.md` catalog documenting every strategy's logic, features, and SDK usage.

---

## Phase 1 — `strats.md` (Strategy Catalog)

One file at repo root documenting all examples:

| Section | Content |
|---------|---------|
| Overview | What the examples are, how to run them (`python examples/bot_simple.py`) |
| Example Index | Table: #, file, category, one-line purpose |
| Per-Strategy Breakdown | Goal, logic flow, key SDK APIs, params, expected behavior |
| Candle Window Trading | Shared pattern: `seconds_in`, `buy_once_per_candle`, `buy_in_window` |
| BTC Volatility Guard | Pattern used in `multi_arb_bot.py` — ROC/ATR check on BTC price |
| Conditions Reference | `and_`, `or_`, `rsi_above`, `price_above`, `crossed_above`, `when()` |

---

## Phase 2 — Example Files (flat in `examples/`)

### Bot Strategies (5)
| File | Description |
|------|-------------|
| `bot_simple.py` | Minimal `Bot.on_tick` — price > 0.9 + RSI > 50 |
| `bot_hub.py` | BotHub with 3 strategies + `on("tick")` + `every(30)` timer |
| `sniper.py` | Full Sniper: time-window, entry/exit thresholds, event callbacks |
| `sniper_minimal.py` | ~10-line Sniper quickstart |
| `sniper_ta.py` | Sniper + RSI threshold + SMA period |

### Paper Trading (4)
| File | Description |
|------|-------------|
| `paper.py` | PaperEngine: buy, sell, limit, `attach_stream`, summary |
| `advanced_orders.py` | TP/SL, trailing stop, OCO |
| `risk_management.py` | Daily loss limit, position size cap, pre-trade checks |
| `multi_wallet_paper.py` | Round-robin / balance-based wallet selection |

### Market Data & Analysis (3)
| File | Description |
|------|-------------|
| `stream.py` | Price stream with UP/DOWN bar chart |
| `analysis.py` | DataFeed + RSI/MACD/BB + signal generation |
| `price_change_signals.py` | Price change detection + RSI combo |

### Arbitrage (2)
| File | Description |
|------|-------------|
| `pairsum_arb.py` | Cross-asset pair-sum scanner (existing concept, rewrite) |
| `multi_arb_bot.py` | **NEW flagship example** (see below) |

### Conditions (1)
| File | Description |
|------|-------------|
| `conditions.py` | Declarative API: `and_`, `or_`, RSI + price combos, custom `when` |

---

## `multi_arb_bot.py` — Design Details

**Strategy:** Multi-asset arbitrage with candle-window entry + BTC volatility guard.

```
SDK APIs:  BotHub, StrategyContext, indicators.roc(), seconds_in, buy_in_window()

Logic:
  1. Hub discovers markets for BTC, ETH, SOL (15m timeframe)
  2. Per-asset strategies calculate arb spread (UP vs DOWN pricing gap)
  3. Candle gate: only trade in first 300s of 900s (15m) candle
  4. BTC volatility guard: if BTC.roc(5) > 5% → skip ALL trades
  5. Entry: when spread > threshold AND BTC calm → buy undervalued side
  6. Output: per-strategy stats table (P&L, trades, win rate)
```

**BTC Volatility Guard Detail:**
```python
def btc_is_calm(ctx, max_roc_pct=5.0):
    roc = ctx.indicators.roc(5)  # 5-period rate of change
    if roc is None:
        return True  # not enough data → allow
    return abs(roc) < max_roc_pct
```

**Candle Window Detail:**
```python
# Only trade in first 5 minutes of 15m candle
if ctx.seconds_in <= 300:
    ctx.buy(side, amount)
```

---

## Execution Order

```
 1. Write strats.md
 2. Write bot_simple.py, bot_hub.py
 3. Write sniper.py, sniper_minimal.py, sniper_ta.py
 4. Write paper.py, advanced_orders.py
 5. Write risk_management.py, multi_wallet_paper.py
 6. Write stream.py, analysis.py, price_change_signals.py
 7. Write pairsum_arb.py
 8. Write multi_arb_bot.py  ← marquee example
 9. Write conditions.py
10. Update docs/examples-guide.md
11. Run ruff + mypy on all examples
```

---

## SDK APIs Used Across All Examples

| API | Used In |
|-----|---------|
| `Bot` / `BotHub` | bot_*.py, multi_arb_bot.py |
| `Sniper` / `SniperConfig` | sniper_*.py |
| `PaperEngine` | paper.py, advanced_orders.py, risk_management.py |
| `StrategyContext` | bot_hub.py, multi_arb_bot.py |
| `IndicatorAccessor` | analysis.py, sniper_ta.py, multi_arb_bot.py |
| `Condition` / `and_` / `or_` | conditions.py, bot_simple.py |
| `OrderBookFeed` | pairsum_arb.py |
| `Stream` | stream.py |
| `DataFeed` / `DataFeedConfig` | analysis.py |
| `WalletManager` | multi_wallet_paper.py |
