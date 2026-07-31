# Examples Guide

The `examples/` directory contains runnable scripts demonstrating every major SDK pattern.

---

## Bot Strategies

### `bot_simple.py`
Minimal working strategy bot (~10 lines). Uses `Bot.on_tick` with a basic price and RSI check. Best starting point.

```python
bot = polyalpha.Bot("BTC", "5m", balance=500)

@bot.on_tick
def strategy(ctx):
    if ctx.price.up > 0.9 and ctx.rsi > 50:
        ctx.buy("UP", 20)

bot.run()
```

### `sniper.py`
Full Sniper bot example with time-window trading, dual-threshold strategy (entry/exit), auto-rollover, event callbacks (`market_found`, `window_enter`, `entry`, `resolve`), and risk management.

### `sniper_minimal.py`
Minimal Sniper bot (~10 lines). Demonstrates the quick-start promise of the Sniper.

### `sniper_ta.py`
Sniper bot with technical analysis integration — configures RSI threshold and SMA period filters, with event callbacks for monitoring.

### `sniper_advanced_windows.py`
Sniper bot with advanced time window features: multiple disjoint windows, burst patterns, absolute time windows, conditional windows (indicator-based), and day/hour filtering. Demonstrates sophisticated trading schedules and indicator-based entry conditions.

### `bot_hub.py`
BotHub — multi-strategy hub running multiple strategies from a single WebSocket connection.

### `strategy_framework.py`
Declarative strategy framework — custom `Strategy` subclass, parameter-only strategies via `ConfigurableStrategy.from_config`, and multiple strategies on one shared stream via `StrategySuite`. See also [Strategies](strategies.md).

### `multi_arb_bot.py`
Multi-arbitrage bot monitoring and executing across different markets.

---

## Paper Trading

### `paper.py`
Comprehensive paper trading example: configurable fee modes, delays, slippage simulation, limit orders, pre-trade checks, live price streaming via `attach_stream()`, and manual resolution.

### `advanced_orders.py`
Advanced order management: stop-loss and take-profit (`buy_with_tp_sl`), trailing stop-loss and take-profit, OCO (one-cancels-other) orders, position selling/closing.

### `conditions.py`
Composable trading conditions: `rsi_above()`, `price_above()`, `and_()`, `or_()`, and operator overloading.

### `multi_wallet_paper.py`
Multi-wallet paper trading with different wallet selection strategies: round-robin, balance-based (prefer highest balance), and random. Shows per-wallet and aggregated summaries.

### `risk_management.py`
Risk management features: daily loss limits, trade count limits, position size limits, stop-loss / take-profit threshold checks, risk-based position sizing.

---

## Market Data

### `stream.py`
Real-time price streaming with a visual UP/DOWN terminal bar chart. Handles all event types: `connect`, `price`, `book`, `trade`, `close`.

---

## Analysis

### `analysis.py`
Standalone technical analysis: configures `DataFeedConfig` with source/timeframe/lookback, fetches data, calculates indicators (SMA, RSI), generates and evaluates trading signals.

### `price_change_signals.py`
Uses price change detection signals: `price_change_above()`, `price_up()`, `price_change_percent_above()`, combined with RSI for multi-condition strategies.

### `chainlink_btc_scraper.py`
Chainlink BTC oracle data scraping for trading strategies.

---

## Utilities

### `telegram_notifications.py`
Sends trade notifications via Telegram bot.

### `pairsum_arb.py`
Cross-asset pair-sum scanner. Scans combinations of assets, computes speculative pair sums, and places trades when the combined price is below a threshold. Demonstrates threading-based execution with multiple simultaneous price handlers.
