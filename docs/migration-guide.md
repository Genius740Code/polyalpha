# Migration Guide

Breaking changes from the old API (pre-v0.2) to the current API, organized by module.

---

## Client

### Old API
```python
client = polyalpha.Client()
client.start()  # No longer exists
```

### New API
```python
client = polyalpha.Client(balance=1000.0, timeout=10, retries=3)
# Client is ready immediately — no .start() needed
```

**Changes:**
- `Client()` no longer takes `api_key` as a positional parameter
- `client.start()` removed — Client is ready on construction
- `client.stop()` → `client.close()`

---

## Paper Trading

### Renamed Methods

| Old | New |
|-----|-----|
| `client.paper.sell(market, side)` | `client.paper.sell_position(market, side)` |
| `client.paper.get_order(id)` | `client.paper.order(id)` |
| `client.paper.get_position(id)` | `client.paper.position(id)` |
| `client.paper.get_positions()` | `client.paper.positions()` |
| `client.paper.get_orders()` | `client.paper.orders()` |
| `client.paper.balance()` | `client.paper.balance` (property, not method) |

### New Methods
- `client.paper.limit(market, side, price, amount)` — place limit orders
- `client.paper.open(market)` — get open position for a market
- `client.paper.attach_stream(stream)` — auto-fill from live prices
- `client.paper.pre_trade_checks(market, side, amount)` — validate before trading
- `client.paper.portfolio_analytics` — performance analysis (property)

### Removed
- `client.paper.auto_redeem()` — replaced by `AutoRedeemEngine`
- `client.payer` — typo removed
- Position `.slug()` → `.market_slug`

---

## Markets

### Old API
```python
market = client.markets.get("BTC", "5m")  # positional args
```

### New API
```python
market = client.markets.latest("BTC", "5m")  # renamed from get()
market = client.markets.get("btc-updown-5m-1751234700")  # now takes a slug
market = client.markets.search("BTC")     # partial slug search
market = client.markets.available("BTC")  # all available markets
market = client.markets.latest_tweet("BTC")  # tweet-based markets
```

**Changes:**
- `markets.get()` now takes a slug string, not asset + timeframe
- `markets.latest()` replaces the old `markets.get("BTC", "5m")` behavior
- `Market` dataclass renamed `slug` field (was `market_slug`)

---

## Streaming

### Old API
```python
stream = client.stream(market)
stream.on_price(lambda up, down: ...)
stream.start()
```

### New API
```python
stream = client.stream(market, retries=5)

@stream.on("price")
def on_price(up, down):
    ...

stream.start(background=True)  # or use run_async()
```

**Changes:**
- `on_price()` → `@stream.on("price")`
- `on_book()` → `@stream.on("book")`
- `on_trade()` → `@stream.on("trade")`
- `on_close()` → `@stream.on("close")`
- New events: `connect`, `error`
- New properties: `connection_quality`, `circuit_breaker_state`
- `start()` supports `background=True` flag for threaded operation
- `run_async()` for asyncio-native usage

---

## Order Book

### Old API
```python
book = client.orderbook(market)
book.get_up_book()
book.get_down_book()
```

### New API
```python
feed = client.orderbook(market)
feed.refresh()                     # REST snapshot

@feed.on("update")                 # live updates
def on_update(book):
    print(book.up_mid, book.down_mid)

feed.attach_stream(stream)         # WebSocket integration
```

**Changes:**
- `orderbook()` returns `OrderBookFeed`, not a raw book object
- `get_up_book()` → `feed.up` property
- `get_down_book()` → `feed.down` property
- Live updates via decorator pattern
- Requires explicit `attach_stream()` for WebSocket

---

## Bots

### Old API
```python
bot = polyalpha.Bot("BTC", "5m")
bot.run()
```

### New API
```python
bot = polyalpha.Bot("BTC", "5m", balance=1000.0)

@bot.on_tick
def strategy(ctx):
    if ctx.rsi and ctx.rsi < 30:
        ctx.buy("UP", 10.0)

bot.run()
```

**Changes:**
- Strategy is now a decorated function receiving `TickContext`
- `TickContext` provides all market state (price, balance, positions, PnL, indicators)
- New declarative API: `bot.when(condition).buy(side, amount)`
- `bot.stats` property replaces manual tracking
- `bot.run_async()` for concurrent multi-bot operation

### Sniper

```python
# New declarative sniper
sniper = Sniper(client, config=SniperConfig(
    asset="BTC", timeframe="5m", side="UP",
    entry_price=0.92, exit_price=0.88, amount=20.0
))

@sniper.on("entry")
def on_entry(ctx):
    print(f"Entered at {ctx.entry_price}")

sniper.run()
```

**Changes:**
- `SniperConfig` dataclass replaces flat constructor params
- Event callbacks via `@sniper.on(event)` decorator
- 8 event types: `market_found`, `window_enter`, `entry`, `exit`, `resolve`, `rollover`, `error`, `stop`

---

## Conditions

### Old API
```python
condition = rsi_below(30) & price_above("UP", 0.5)
```

### New API (same syntax, new factories)
```python
condition = rsi_above(70) | price_below("DOWN", 0.3)
```

**Changes:**
- New conditions: `crossed_above(threshold)`, `crossed_below(threshold)` (stateful — tracks cross events between ticks)
- New `when(fn)` for arbitrary callable conditions
- Operator overloading unchanged: `&`, `|`, `~`

---

## Configuration

### Old API
```python
client = Client(balance=500.0)
```

### New API
```python
from polyalpha import PaperConfig

config = PaperConfig(
    fee_mode="custom",
    custom_fee_rate=0.02,
    slippage_pct=0.001,
    enable_rebates=True,
)

client = Client(balance=500.0, paper_config=config)
# Or load from env:
client = Client(balance=500.0, paper_config_from_env=True)
```

**Changes:**
- `PaperConfig` dataclass replaces inline fee/risk parameters
- `paper_config_from_env=True` loads all `POLYALPHA_PAPER_*` env vars
- New fields: `maker_fee_rate`, `enable_rebates`, `maker_rebate_pct`, `execution_delay_ms`, `delay_randomness`, `slippage_randomness`, `max_slippage_no_fill`, `fill_probability`, `check_mode`

---

## Database

### Old API
```python
client = Client(db_path="trades.db")
client.paper.enable_database("trades.db")
```

### New API
```python
client = Client(db_path="trades.db")
# or later:
client.paper.enable_database("trades.db")
```

**Changes:**
- New fields on `TradeRecord`: `market_session`, `order_id`, `status`
- New methods: `save_trades_bulk()`, `update_trade_status()`, `stream_trades()`, `export_parquet()`, `export_excel()`, `backup_to_s3()`, `backup_to_gcs()`
- `enable_cache()`/`disable_cache()` for query cache control
- `operation_context()` for operation tracing
- Background optimization thread via `start_background_optimization()`

---

## AI

### Old API
```python
result = client.ai.analyze("What do you think about BTC?")
```

### New API
```python
# Chat
response = client.ai.chat("What do you think about BTC?")

# Market analysis
analysis = client.ai.analyze_market(market)
print(f"Sentiment: {analysis.sentiment}, Confidence: {analysis.confidence}")

# Trading signals
signal = client.ai.generate_trading_signal(market, analysis_data)
print(f"Action: {signal.action}, Entry: {signal.entry_price}")
```

**Changes:**
- `analyze()` split into `chat()`, `analyze_market()`, `generate_trading_signal()`
- Structured return types: `MarketAnalysis`, `TradingSignal`
- 7 distinct AI error classes instead of generic exceptions
- Prompt injection guardrails built in

---

## Error Handling

### Old API
```python
try:
    client.paper.buy(market, "UP", 10.0)
except polyalpha.PolyalphaError as e:
    print(e)
```

### New API
```python
try:
    client.paper.buy(market, side="UP", amount=10.0)
except InsufficientBalance:
    print("Not enough funds")
except MarketClosed:
    print("Market is closed")
```

**Changes:**
- All errors available from top-level `polyalpha`
- Named error classes for every failure mode
- New errors: `CircuitBreakerOpenError`, `ManualInterventionRequiredError`, `TransactionRollbackError`, `BackupError`, `RateLimitExceeded`, `GasEstimationError`, `TransactionRebroadcastError`

---

## Upgrade Steps

1. Replace `client.start()` with nothing (Client is ready immediately)
2. Replace `.sell()` → `.sell_position()`, `.get_*()` → shortened names
3. Replace `markets.get("BTC", "5m")` → `markets.latest("BTC", "5m")`
4. Replace `stream.on_*()` → `@stream.on("*")` decorators
5. Use `PaperConfig` dataclass instead of raw constructor params
6. Use `SniperConfig` dataclass for sniper configuration
7. Replace `.analyze()` → `.chat()` / `.analyze_market()` / `.generate_trading_signal()`
8. Import errors from top-level `polyalpha` instead of submodules
