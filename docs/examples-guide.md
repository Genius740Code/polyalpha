# Examples Guide

The `examples/` directory contains 32 runnable scripts demonstrating every feature of the SDK. They are organized loosely by category.

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

### `async_bots.py`
Runs multiple bot strategies concurrently in a single asyncio event loop using `Bot.run_async()` and `asyncio.gather()`.

### `sniper.py`
Full Sniper bot example with time-window trading, dual-threshold strategy (entry/exit), auto-rollover, event callbacks (`market_found`, `window_enter`, `entry`, `resolve`), and risk management.

### `sniper_minimal.py`
Minimal Sniper bot (~10 lines). Demonstrates the quick-start promise of the Sniper.

### `sniper_ta.py`
Sniper bot with technical analysis integration — configures RSI threshold and SMA period filters, with event callbacks for monitoring.

### `market_session_filtering.py`
Configures the Sniper bot to trade only during specific market sessions (London, New York, Asia, Sydney) using `SniperConfig.allowed_market_sessions`.

### `tracker.py`
P&L Tracker usage: syncs with paper engine state, prints a formatted summary with win rate and P&L, exports to JSON and CSV.

### `weather_config_example.py`
Demonstrates `CITIES`, `list_configs()`, `print_config()` for weather bot configurations. Shows how to get and customize city templates.

---

## Paper Trading

### `paper.py`
Comprehensive paper trading example: configurable fee modes, delays, slippage simulation, limit orders, pre-trade checks, live price streaming via `attach_stream()`, and manual resolution.

### `advanced_orders.py`
Advanced order management: stop-loss and take-profit (`buy_with_tp_sl`), trailing stop-loss and take-profit, OCO (one-cancels-other) orders, position selling/closing.

### `fee_rebates.py`
Volume-based fee rebates with configurable tiers (bronze/silver/gold/platinum). Compares rebate vs non-rebate mode, shows maker rebate bonuses.

### `multi_wallet_paper.py`
Multi-wallet paper trading with different wallet selection strategies: round-robin, balance-based (prefer highest balance), and random. Shows per-wallet and aggregated summaries.

### `pre_trade_checks.py`
Pre-trade validation: balance sufficiency, market open status, price reasonableness checks before order placement.

### `risk_management.py`
Risk management features: daily loss limits, trade count limits, position size limits, stop-loss / take-profit threshold checks, risk-based position sizing.

### `auto_redeem.py`
Auto-redeem feature for automatically resolving and redeeming Polymarket positions based on configurable triggers (time interval, trade count, value threshold).

### `portfolio_analytics.py`
Portfolio-level analytics: P&L tracking, time-based performance breakdown, Sharpe/Sortino/Calmar ratios, trade history summary, formatted report printing.

### `report.py`
Generates 60 synthetic trades and renders a full HTML analytics dashboard using `report.show()`, `report.html()`, with preset management (`save_preset()`, `list_presets()`).

### `reporting.py`
Comprehensive reporting system: portfolio summary, execution quality analysis, risk exposure report, tax lot reporting (FIFO), audit trail with config date range.

---

## Real Trading

### `real_trading.py`
Real trading engine setup: percentage/Kelly/fixed position sizing strategies, limit orders, stop-loss, emergency stop, database integration, wallet management. Uses real money — handle with care.

### `clob_client_example.py`
Polymarket CLOB API integration: order placement, cancellation, orderbook queries via `ClobClient`.

---

## Market Data

### `market.py`
Market discovery: `latest()` by asset/timeframe, `available()` with search, `get()` by slug, `latest_tweet()` for tweet markets, `market.show()` for formatted display.

### `stream.py`
Real-time price streaming with a visual UP/DOWN terminal bar chart. Handles all event types: `connect`, `price`, `book`, `trade`, `close`.

### `async_stream.py`
Async price streaming using `stream.run_async()` instead of `stream.start(background=False)`. No background threads.

### `orderbook_example.py`
Fetches initial REST order book snapshot via `client.orderbook()`, then attaches a WebSocket stream for live order book updates. Demonstrates `feed.refresh()`, `feed.attach_stream()`, `book.up.best_bid`.

---

## Analysis & AI

### `analysis.py`
Standalone technical analysis: configures `DataFeedConfig` with source/timeframe/lookback, fetches data, calculates indicators (SMA, RSI), generates and evaluates trading signals.

### `price_change_signals.py`
Uses price change detection signals: `price_change_above()`, `price_up()`, `price_change_percent_above()`, combined with RSI for multi-condition strategies.

### `ai_trading.py`
AI-powered trading via OpenRouter: `client.ai.chat()` for general queries, `client.ai.analyze_market()` for market analysis, `client.ai.generate_trading_signal()` for signal generation with automated paper trading.

---

## Database

### `database_example.py`
Enables database persistence for paper trading. Trades are automatically saved. Shows `db.save_trade()`, `db.load_all_trades()`, `db.get_statistics()`.

### `database_backup_example.py`
Database backup workflows: local file backup, timestamped backups, S3/GCS cloud backups, backup-before-migration, CSV/JSON export/import.

### `database_security_example.py`
Database security features: encryption at rest (`enable_encryption`), API key authentication, role-based authorization, data masking rules for sensitive fields.

### `test_advanced_queries.py`
Advanced database querying: `load_trades()` with filters (date range, side, outcome), sorting, pagination, and `aggregate_trades()` with grouping.

---

## Other

### `pairsum_arb.py`
Cross-asset pair-sum scanner. Scans combinations of assets, computes speculative pair sums, and places trades when the combined price is below a threshold. Demonstrates threading-based execution with multiple simultaneous price handlers.
