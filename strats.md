# Strategy & Example Catalog

## Overview

This directory (`examples/`) contains 15 runnable Python scripts demonstrating every major SDK pattern in `polyalpha`.

**Run any example:**

```bash
python examples/bot_simple.py
python examples/sniper.py
python examples/paper.py
```

All examples use **paper trading** by default. No API keys required — just `pip install polyalpha[analysis]` and go.

---

## Example Index

| # | File | Category | Purpose |
|---|------|----------|---------|
| 1 | `bot_simple.py` | Bot | Minimal `Bot.on_tick` — price > 0.9 + RSI > 50 |
| 2 | `bot_hub.py` | Bot | BotHub with 3 strategies + `on("tick")` + `every(30)` timer |
| 3 | `sniper.py` | Sniper | Full Sniper: time-window, entry/exit thresholds, event callbacks |
| 4 | `sniper_minimal.py` | Sniper | ~10-line Sniper quickstart |
| 5 | `sniper_ta.py` | Sniper | Sniper + RSI threshold + SMA period |
| 6 | `paper.py` | Paper Trading | PaperEngine: buy, sell, limit, `attach_stream`, summary |
| 7 | `advanced_orders.py` | Paper Trading | TP/SL, trailing stop, OCO |
| 8 | `risk_management.py` | Paper Trading | Daily loss limit, position size cap, pre-trade checks |
| 9 | `multi_wallet_paper.py` | Paper Trading | Round-robin / balance-based wallet selection |
| 10 | `stream.py` | Market Data | Price stream with UP/DOWN bar chart |
| 11 | `analysis.py` | Market Data | DataFeed + RSI/MACD/BB + signal generation |
| 12 | `price_change_signals.py` | Market Data | Price change detection + RSI combo |
| 13 | `pairsum_arb.py` | Arbitrage | Cross-asset pair-sum scanner via OrderBookFeed |
| 14 | `multi_arb_bot.py` | Arbitrage | Multi-asset arbitrage with candle-window + BTC volatility guard |
| 15 | `conditions.py` | Conditions | Declarative API: `and_`, `or_`, RSI + price combos, custom `when` |

---

## Per-Strategy Breakdown

### 1. `bot_simple.py` — Minimal Bot

**Goal:** Demonstrate the simplest possible `Bot` with two entry conditions.

| | |
|---|---|
| **Logic flow** | `Bot.on_tick` → check `ctx.price.up > 0.9` AND `ctx.rsi > 50` → `ctx.buy("UP", 20)` |
| **Key SDK APIs** | `Bot(asset, timeframe)`, `@bot.on_tick`, `TickContext.price.up`, `TickContext.rsi`, `ctx.buy()` |
| **Params** | `asset="BTC"`, `timeframe="5m"`, `balance=100` |
| **Expected** | Logs ticks, enters a UP position when both conditions align, prints P&L on exit. |

---

### 2. `bot_hub.py` — BotHub Multi-Strategy

**Goal:** Run 3 strategies side-by-side under one `BotHub`, compare results.

| | |
|---|---|
| **Logic flow** | `BotHub(asset, timeframe)` → register 3 `@hub.strategy("name")` callbacks → `hub.run()` → compare equity curves |
| **Key SDK APIs** | `BotHub()`, `@hub.strategy()`, `hub.run()`, `hub.chart()`, `TickContext`, `ctx.engine.balance` |
| **Params** | `asset="ETH"`, `timeframe="15m"`, `balance=500` |
| **Expected** | Three strategies run independently. Terminal shows per-strategy P&L, trade count, win rate. `hub.chart()` draws overlaid equity curves. |

**Tick handler pattern:**

```python
@hub.strategy("bb_rsi")
def bb_rsi(ctx):
    if ctx.price.down < ctx.bb_lower and ctx.rsi < 30:
        ctx.buy("DOWN", 20)
```

**Timer pattern** via `hub.on("tick")` + custom counters:

```python
ticks = 0
@hub.on("tick")
def on_tick(price):
    nonlocal ticks; ticks += 1
    if ticks % 30 == 0:
        print(f"[Timer] Price: UP={price.up:.4f} DOWN={price.down:.4f}")
```

---

### 3. `sniper.py` — Full Sniper

**Goal:** Complete time-window sniper with lifecycle event callbacks.

| | |
|---|---|
| **Logic flow** | `Sniper(client=..., side="UP", entry_price=0.92, exit_price=0.88, window_seconds=35)` → state machine: `IDLE → DISCOVERING → WAITING → ARMED → FILLED → RESOLVING → ROLLOVER → IDLE` |
| **Key SDK APIs** | `Sniper()`, `SniperConfig`, `sniper.on("resolve")`, `sniper.on("entry")`, `sniper.run()` |
| **Params** | `asset="BTC"`, `side="UP"`, `entry_price=0.92`, `exit_price=0.88`, `window_seconds=35`, `amount=20` |
| **Expected** | Sniper waits for market open, enters at threshold, auto-exits at target or expiry, fires callbacks at each stage. |

**Events:** `market_found`, `window_enter`, `entry`, `exit`, `resolve`, `rollover`, `error`, `stop`

---

### 4. `sniper_minimal.py` — Sniper Quickstart

**Goal:** 10-line sniper to show how little code is needed.

| | |
|---|---|
| **Logic flow** | Create `Client` + `Sniper` + `sniper.run()` |
| **Key SDK APIs** | `Client(balance=100)`, `Sniper(client=..., side="UP")`, `sniper.run()` |
| **Params** | `asset="BTC"`, `side="UP"`, default entry/exit, `amount=10` |
| **Expected** | Runs a sniper session with no custom callbacks. Prints state transitions to console. |

---

### 5. `sniper_ta.py` — Sniper + Technical Analysis

**Goal:** Add RSI and SMA thresholds to sniper entry logic.

| | |
|---|---|
| **Logic flow** | Sniper base + pre-entry check: `ctx.rsi(14) > 50` AND `ctx.price.up > ctx.sma(20)` |
| **Key SDK APIs** | `Sniper(client=...)`, `TickContext.rsi(period)`, `TickContext.sma(period)` |
| **Params** | `asset="BTC"`, `side="UP"`, RSI > 50, SMA filter active |
| **Expected** | Sniper only arms when TA conditions are met, reducing false entries. |

---

### 6. `paper.py` — PaperEngine Basics

**Goal:** Demonstrate core paper trading operations.

| | |
|---|---|
| **Logic flow** | `client.paper.buy()` → `client.paper.positions()` → `client.paper.sell_position()` → `client.paper.balance` |
| **Key SDK APIs** | `Client(paper_mode="realistic").paper`, `.buy(market, side, amount)`, `.limit(market, side, price, amount)`, `.sell_position()`, `.positions()`, `.balance`, `.show_positions()`, `.attach_stream()` |
| **Params** | `balance=200`, `paper_mode="realistic"` |
| **Expected** | Opens market + limit orders, partially fills limit order via stream, closes positions, prints summary table. |

---

### 7. `advanced_orders.py` — TP/SL, Trailing Stop, OCO

**Goal:** Show advanced order types in PaperEngine.

| | |
|---|---|
| **Logic flow** | `buy_with_tp_sl(take_profit_pct=5, stop_loss_pct=3)` → monitor fills → `oco_order()` → trailing stop adjusts |
| **Key SDK APIs** | `.buy_with_tp_sl(market, side, amount, stop_loss, take_profit)`, `.oco_order(market, side, amount, stop_loss, take_profit)`, `.cancel()` |
| **Params** | `balance=300`, realistic mode |
| **Expected** | Position auto-closes at TP/SL. OCO brackets both sides. Trailing stop locks in profit as price moves. |

---

### 8. `risk_management.py` — Pre-Trade Risk Checks

**Goal:** Prevent over-trading with daily loss limits and position size caps.

| | |
|---|---|
| **Logic flow** | `RiskManager(daily_loss_limit=50, max_position_size=30)` → validate before each `buy()` → reject if limits exceeded |
| **Key SDK APIs** | `RiskManager(daily_loss_limit, max_position_size, max_positions)`, `.can_trade(engine)`, `.validate_order(amount)`, engine risk integration |
| **Params** | `daily_loss_limit=50`, `max_position_size=30`, `max_positions=3` |
| **Expected** | Simulates a day of trading. Some trades are rejected when limits hit. Terminal shows risk check pass/fail per attempt. |

---

### 9. `multi_wallet_paper.py` — Wallet Selection

**Goal:** Route trades across multiple paper wallets.

| | |
|---|---|
| **Logic flow** | Create 3 `PaperWallet` instances → `WalletManager(wallets, strategy="round_robin")` → each trade picks next wallet |
| **Key SDK APIs** | `PaperWallet(balance)`, `WalletManager(wallets, strategy)`, strategies: `"round_robin"`, `"balance_weighted"`, `"sequential"` |
| **Params** | 3 wallets with 100, 200, 300 USDC |
| **Expected** | Trades are distributed per strategy. Final output shows per-wallet P&L and total across all. |

---

### 10. `stream.py` — Real-Time Price Stream

**Goal:** Subscribe to a market price stream and render a live UP/DOWN bar chart.

| | |
|---|---|
| **Logic flow** | `client.stream(market)` → `stream.on("update")` → collect prices → print/plot UP/DOWN bars |
| **Key SDK APIs** | `Client.stream(market)`, `Stream.on("update")`, `Stream.on("error")`, `Stream.on("close")` |
| **Params** | Any active market |
| **Expected** | Live price updates printed as ASCII bars. UP and DOWN prices update in real-time. Stream auto-reconnects on disconnect. |

---

### 11. `analysis.py` — DataFeed + Indicators + Signals

**Goal:** Fetch historical data, compute indicators, generate trading signals.

| | |
|---|---|
| **Logic flow** | `DataFeed(source="binance").fetch(asset, timeframe, limit=200)` → `IndicatorCalculator(symbol).rsi(14)` → `SignalGenerator.rsi_above(50)` → evaluate on latest bar |
| **Key SDK APIs** | `DataFeed(source, config)`, `.fetch()`, `IndicatorCalculator`, `.rsi()`, `.macd()`, `.bollinger_bands()`, `SignalGenerator`, `.rsi_above()`, `.macd_cross_above()`, `.all_true()` |
| **Params** | `asset="BTC"`, `timeframe="1h"`, `limit=200`, `source="binance"` |
| **Expected** | Fetches 200 1h candles, computes RSI(14), MACD(12,26,9), BB(20,2). Prints latest values and a composite BUY/SELL/HOLD signal. |

**Composite signal example:**

```python
signal = SignalGenerator(data)
entry = signal.all_true(
    signal.rsi_above(30),
    signal.price_above_sma(20),
    signal.macd_cross_above()
)
```

---

### 12. `price_change_signals.py` — Price Change + RSI

**Goal:** Detect significant price moves combined with RSI extremes.

| | |
|---|---|
| **Logic flow** | `SignalGenerator.price_changed_pct(2.0)` + `SignalGenerator.rsi_below(30)` → combined signal |
| **Key SDK APIs** | `SignalGenerator.price_changed_pct(pct)`, `.rsi_above()`, `.rsi_below()`, `.price_up()`, `.price_down()` |
| **Params** | `asset="ETH"`, `timeframe="5m"`, price change threshold 2% |
| **Expected** | Alerts when ETH moves >2% in a 5m candle AND RSI is oversold (<30) — potential reversal entry. |

---

### 13. `pairsum_arb.py` — Cross-Asset Pair-Sum Arbitrage

**Goal:** Scan multiple markets for pricing gaps between related assets.

| | |
|---|---|
| **Logic flow** | `OrderBookFeed(market)` per asset → compute `sum = UP(asset_A) + UP(asset_B)` → if sum deviates from expected → signal |
| **Key SDK APIs** | `OrderBookFeed(market)`, `feed.on("update")`, `book.best_bid`, `book.best_ask`, `client.markets.latest()` |
| **Params** | Assets: BTC, ETH, SOL. Threshold: 1% deviation from fair sum. |
| **Expected** | Prints real-time pair-sum values. Alerts when BTC+ETH price deviates >1% from expected. |

---

### 14. `multi_arb_bot.py` — Multi-Asset Arbitrage Bot

**Goal:** Flagship example combining candle-window entry, BTC volatility guard, and multi-asset BotHub.

| | |
|---|---|
| **Logic flow** | 1. Hub discovers BTC, ETH, SOL on 15m → 2. Per-asset spread calculator → 3. Candle gate (first 300s only) → 4. BTC volatility guard (ROC < 5%) → 5. Entry when spread > threshold → 6. Stats table |
| **Key SDK APIs** | `BotHub`, `StrategyContext.seconds_in`, `ctx.buy_in_window()`, `ctx.indicators.roc(5)`, `ctx.buy_once_per_candle` |
| **Params** | `asset="BTC"/"ETH"/"SOL"`, `timeframe="15m"`, `max_roc_pct=5.0`, `window_seconds=300` |
| **Expected** | Per-strategy stats table (P&L, trades, win rate). BTC volatility halts all trading during high volatility. |

---

### 15. `conditions.py` — Declarative Conditions API

**Goal:** Show every condition builder and combinator in action.

| | |
|---|---|
| **Logic flow** | Build `Condition` trees → evaluate against a `TickContext` → print pass/fail |
| **Key SDK APIs** | `and_()`, `or_()`, `not_()`, `rsi_above()`, `price_above()`, `crossed_above()`, `price_up()`, `price_changed_pct()`, `sma_above()`, `macd_above()`, `bb_upper()`, `adx_above()`, `stoch_overbought()`, `when(fn)`, `Condition.__and__`, `Condition.__or__` |
| **Params** | N/A — uses injected tick data |
| **Expected** | Prints each condition's evaluation result. Demonstrates chaining: `rsi_above(50) & price_above("UP", 0.85) \| when(my_custom_check)`. |

**Chaining example:**

```python
entry_condition = and_(
    rsi_above(50),
    price_above("UP", 0.85),
    or_(macd_cross_above("UP"), adx_above(25))
)
```

---

## Candle Window Trading

A shared pattern across several examples (`multi_arb_bot.py`, `sniper.py`). The idea: restrict trading to a specific portion of a candle to avoid late entries near the close.

### Core APIs

| API | Description |
|---|---|
| `ctx.seconds_in` | Seconds elapsed in the current candle (int). Resets at each new candle. |
| `ctx.buy_once_per_candle(side, amount)` | Buy at most once per candle. No-op if already bought this candle. |
| `ctx.buy_in_window(side, amount, max_seconds)` | Buy only if `seconds_in <= max_seconds`. No-op outside window. |

### Pattern

```python
@bot.on_tick
def strategy(ctx):
    # Only trade in first 5 minutes of a 15m candle
    if ctx.seconds_in <= 300:
        ctx.buy_in_window("UP", 20, 300)
```

**Why:** In 15m candles (900s), prices near the open are more reactive to new information. Trading in the last 600s risks entering on stale signals.

### Parameters

| Parameter | Typical Value | Description |
|---|---|---|
| `seconds_in` threshold | 300 (5m) for 15m candle | Must be <= candle total seconds |
| `buy_once_per_candle` | True | Prevents multiple entries in same candle |
| `buy_in_window` window | 300 | Seconds after open when entry is allowed |

---

## BTC Volatility Guard

Used in `multi_arb_bot.py`. Prevents trading across all assets when BTC shows extreme short-term volatility.

### Pattern

```python
def btc_is_calm(ctx, max_roc_pct=5.0):
    roc = ctx.indicators.roc(5)  # 5-period rate of change
    if roc is None:
        return True
    return abs(roc) < max_roc_pct
```

**Where it fits:**

```python
@hub.strategy("eth_arb")
def eth_arb(ctx):
    if not btc_is_calm(ctx):
        return  # skip this tick — BTC is too volatile
    # ... normal arbitrage logic
```

### How It Works

| Component | Detail |
|---|---|
| **Indicator** | `ROC(5)` — Rate of Change over 5 periods |
| **Threshold** | `max_roc_pct = 5.0` (configurable) |
| **Behavior** | When `abs(ROC) >= 5%`, all asset strategies skip their tick |
| **Data window** | Needs 6+ ticks of BTC price data before producing a value; returns `True` (allow) until then |

### Variant with ATR

```python
def btc_is_calm_atr(ctx, max_atr_pct=2.0):
    atr = ctx.indicators.atr(14)
    if atr is None:
        return True
    return atr < max_atr_pct
```

---

## Conditions Reference

All functions return a `Condition` object that evaluates `(ctx) -> bool`.

### Combinators

| Function | Signature | Description |
|---|---|---|
| `and_` | `and_(*conditions) -> Condition` | All conditions must pass |
| `or_` | `or_(*conditions) -> Condition` | Any condition must pass |
| `not_` | `not_(condition) -> Condition` | Invert a condition |
| `&` | `c1 & c2` | Operator shorthand for `and_` |
| `\|` | `c1 \| c2` | Operator shorthand for `or_` |
| `~` | `~c` | Operator shorthand for `not_` |

### RSI Conditions

| Function | Returns `True` when |
|---|---|
| `rsi_above(threshold)` | RSI(14) > threshold |
| `rsi_below(threshold)` | RSI(14) < threshold |

### Price Conditions

| Function | Returns `True` when |
|---|---|
| `price_above(side, price)` | Current `side` price > `price` |
| `price_below(side, price)` | Current `side` price < `price` |
| `crossed_above(side, price)` | Price just crossed above `price` |
| `crossed_below(side, price)` | Price just crossed below `price` |
| `price_up(side)` | Price moved up from last tick |
| `price_down(side)` | Price moved down from last tick |
| `price_changed_pct(side, pct)` | Price change exceeded `pct`% |

### Moving Average Conditions

| Function | Returns `True` when |
|---|---|
| `sma_above(side, period)` | Price > SMA(period) |
| `sma_below(side, period)` | Price < SMA(period) |
| `ema_above(side, period)` | Price > EMA(period) |
| `ema_below(side, period)` | Price < EMA(period) |
| `ema_crossed_above(fast, slow)` | Fast EMA crossed **above** slow EMA since last tick |
| `ema_crossed_below(fast, slow)` | Fast EMA crossed **below** slow EMA since last tick |

### MACD Conditions

| Function | Returns `True` when |
|---|---|
| `macd_above(side)` | MACD line > signal line |
| `macd_below(side)` | MACD line < signal line |
| `macd_cross_above(side)` | MACD crossed above signal |
| `macd_cross_below(side)` | MACD crossed below signal |

### Bollinger Band Conditions

| Function | Returns `True` when |
|---|---|
| `bb_upper(side)` | Price > upper band |
| `bb_lower(side)` | Price < lower band |
| `bb_middle(side)` | Price at middle band |

### Volume Conditions

| Function | Returns `True` when |
|---|---|
| `volume_above(threshold)` | Volume > threshold |
| `volume_below(threshold)` | Volume < threshold |

### ADX Conditions

| Function | Returns `True` when |
|---|---|
| `adx_above(threshold)` | ADX > threshold (trending) |
| `adx_below(threshold)` | ADX < threshold (ranging) |

### Stochastic Conditions

| Function | Returns `True` when |
|---|---|
| `stoch_overbought(k_or_d)` | %K or %D > 80 |
| `stoch_oversold(k_or_d)` | %K or %D < 20 |
| `stoch_cross_above()` | %K crossed above %D |
| `stoch_cross_below()` | %K crossed below %D |

### Custom Condition

```python
def my_check(ctx):
    return ctx.price.up > 0.85 and ctx.engine.balance > 50

condition = when(my_check)
```
