# Bot Framework

The `Bot` class is a one-line trading bot runner that handles the full market lifecycle:
discover → stream → tick → resolve → rollover → repeat.

```python
import polyalpha

bot = polyalpha.Bot("BTC", "5m", balance=500)

@bot.on_tick
def strategy(ctx):
    if ctx.price.up > 0.9 and ctx.rsi > 50:
        ctx.buy("UP", 20)

bot.run()
```

---

## Bot

```python
bot = polyalpha.Bot(
    asset="BTC",           # BTC, ETH, SOL, XRP, DOGE
    timeframe="5m",        # 5m, 15m, 1h, 4h, 24h
    balance=100.0,         # starting paper balance
    paper=True,            # True → paper trade, False → real trade
    mode="simple",         # "simple", "realistic", or "custom"
    paper_config=None,     # PaperConfig for mode="custom"
    **kwargs,              # forwarded to polyalpha.Client
)
```

### Constructor Parameters

| Param | Default | Description |
|-------|---------|-------------|
| `asset` | `"BTC"` | Trading asset. One of: BTC, ETH, SOL, XRP, DOGE |
| `timeframe` | `"5m"` | Market timeframe. One of: 5m, 15m, 1h, 4h, 24h |
| `balance` | `100.0` | Starting paper-trading balance in USDC |
| `paper` | `True` | `True` for paper trading, `False` for real trading |
| `mode` | `"simple"` | Execution template: `"simple"`, `"realistic"`, or `"custom"` |
| `paper_config` | `None` | `PaperConfig` instance (only used when `mode="custom"`) |
| `**kwargs` | — | Extra keyword arguments forwarded to `polyalpha.Client` |

Raises `ValueError` if the asset or timeframe is unsupported.

### Modes

The `mode` parameter controls fees, execution delay, slippage, and fill probability:

| Mode | Fees | Delay | Slippage | Fill prob | Use case |
|------|------|-------|----------|-----------|----------|
| `"simple"` (default) | Zero | Instant | 0% | 100% | Quick testing, strategy dev |
| `"realistic"` | Polymarket fees | 2000ms | 3% | 85% | Realistic simulation |
| `"custom"` | Your config | Your config | Your config | Your config | Full control |

```python
# Simple — zero fees, instant, 100% fill (default)
bot = polyalpha.Bot("BTC", "5m", balance=500)

# Realistic — polymarket fees, slippage, delay
bot = polyalpha.Bot("BTC", "5m", balance=500, mode="realistic")

# Custom — your own PaperConfig
from polyalpha.trading.paper_config import PaperConfig
bot = polyalpha.Bot("BTC", "5m", balance=500, mode="custom",
    paper_config=PaperConfig(fee_mode="custom", custom_fee_rate=0.015))
```

### Methods

#### `on_tick(fn)`

Decorator that registers your strategy function. The function receives a `TickContext` on every price update.

```python
@bot.on_tick
def strategy(ctx):
    ...
```

#### `when(condition)`

Declarative API — sets a `Condition` that triggers a trade. Chain with `.buy()`.

```python
from polyalpha.conditions import and_, rsi_above, price_above

bot.when(
    and_(rsi_above(50), price_above("up", 0.9))
).buy("UP", 20)
bot.run()
```

| Param | Type | Description |
|-------|------|-------------|
| `condition` | `Condition` | A composable condition from `polyalpha.conditions` |

Returns `self` for chaining.

#### `buy(side, amount)`

Sets the default trade action when the condition is met (declarative API).

```python
bot.when(...).buy("UP", 20)
```

| Param | Type | Description |
|-------|------|-------------|
| `side` | `str` | `"UP"` or `"DOWN"` |
| `amount` | `float` | USDC to spend per trade |

Returns `self` for chaining. Raises `ValueError` if side is not `"UP"` or `"DOWN"`.

#### `run()`

Starts the bot (blocking). Runs indefinitely until `stop()` is called or an unrecoverable error occurs.

```python
bot.run()
```

#### `run_async()`

Starts the bot using async IO. Runs multiple bots concurrently in a single event loop.

```python
import asyncio

async def main():
    await asyncio.gather(
        bot1.run_async(),
        bot2.run_async(),
    )
```

#### `stop()`

Signals the bot to stop gracefully. Cleans up the stream and stops the cycle loop.

```python
bot.stop()
```

### Properties

| Property | Returns | Description |
|----------|---------|-------------|
| `stats` | `dict` | Running bot statistics: ticks, trades, balance, pnl, open_positions |
| `asset` | `str` | Configured asset |
| `timeframe` | `str` | Configured timeframe |
| `paper_mode` | `bool` | Whether running in paper mode |

`stats` dictionary keys:

```python
{
    "ticks": 142,          # price ticks received
    "trades": 5,           # trades executed
    "balance": 480.0,      # current paper balance
    "pnl": -20.0,          # total realised P&L
    "open_positions": 2,   # currently open positions
}
```

---

## Lifecycle

The Bot runs a cycle loop:

1. **Discover** — finds the latest market for the configured asset/timeframe via `client.markets.latest()`
2. **Stream** — sets up a price stream and attaches the paper engine for limit-order fills
3. **Tick** — calls the strategy function on every price tick
4. **Resolve** — checks for resolved positions, records P&L
5. **Rollover** — cleans up, waits 2 seconds, repeats from step 1

If no market is found, it retries every 30 seconds.

---

## TickContext

The `TickContext` is passed to your strategy function on every price tick. It provides access to prices, account state, and indicators.

```python
@bot.on_tick
def strategy(ctx):
    # Prices
    print(ctx.price.up, ctx.price.down)

    # Account
    print(ctx.balance)
    print(ctx.positions)
    print(ctx.pnl)

    # Market info
    print(ctx.market)

    # Trade
    ctx.buy("UP", 20)
    ctx.limit("DOWN", 0.1, 10)
    ctx.close_position("UP")
```

### Properties

| Property | Returns | Description |
|----------|---------|-------------|
| `price` | `PriceSnapshot` | Current UP and DOWN mid-prices from the live stream |
| `balance` | `float` | Current paper-trading balance |
| `positions` | `list` | Open (unresolved) positions from the paper engine |
| `pnl` | `float` | Total realised P&L from all resolved positions |
| `market` | `Market \| None` | The currently active market |
| `tick_count` | `int` | Number of price ticks received this session |
| `trade_count` | `int` | Number of trades executed |
| `rsi` | `float \| None` | RSI(14) — requires `pandas` |
| `sma_20` | `float \| None` | SMA(20) — requires `pandas` |
| `ema_12` | `float \| None` | EMA(12) — requires `pandas` |

Indicator properties return `None` if:
- `pandas` is not installed
- The native TA module is unavailable
- Not enough price history (minimum 14 ticks for RSI)

### Methods

#### `buy(side, amount)`

Place a market buy order.

| Param | Type | Description |
|-------|------|-------------|
| `side` | `str` | `"UP"` or `"DOWN"` |
| `amount` | `float` | USDC to spend |

Returns a `PaperOrder`.

#### `limit(side, price, amount)`

Place a limit order.

| Param | Type | Description |
|-------|------|-------------|
| `side` | `str` | `"UP"` or `"DOWN"` |
| `price` | `float` | Trigger price |
| `amount` | `float` | USDC to spend |

Returns a `PaperOrder`.

#### `close_position(side, amount=None)`

Close (sell) an open position.

| Param | Type | Description |
|-------|------|-------------|
| `side` | `str` | `"UP"` or `"DOWN"` |
| `amount` | `float \| None` | USDC amount to sell. Defaults to the full position |

Returns a `PaperOrder`.

---

## PriceSnapshot

A simple dataclass with the current UP/DOWN prices.

```python
@dataclass
class PriceSnapshot:
    up: float
    down: float
```

---

## Declarative API

Instead of writing a manual strategy function, use `when()` + `buy()` for a declarative approach:

```python
from polyalpha.conditions import and_, rsi_above, price_above

bot = polyalpha.Bot("BTC", "5m", balance=500)
bot.when(
    and_(rsi_above(50), price_above("up", 0.9))
).buy("UP", 20)
bot.run()
```

When both conditions are met on a tick, the bot executes a market buy. The condition is checked on every tick but only triggers once per market cycle.

---

## Async Multi-Bot

Run multiple bots concurrently using `run_async()`:

```python
import asyncio
import polyalpha

btc_bot = polyalpha.Bot("BTC", "5m", balance=500)
eth_bot = polyalpha.Bot("ETH", "5m", balance=500)

@btc_bot.on_tick
def btc_strategy(ctx):
    if ctx.price.up > 0.9:
        ctx.buy("UP", 10)

@eth_bot.on_tick
def eth_strategy(ctx):
    if ctx.rsi < 30:
        ctx.buy("UP", 10)

async def main():
    await asyncio.gather(
        btc_bot.run_async(),
        eth_bot.run_async(),
    )

asyncio.run(main())
```

---

## Env Var Configuration

`Bot` forwards `**kwargs` to `Client`, so you can use environment variables or pass config directly:

```python
# Via env vars (POLYALPHA_API_KEY, etc.)
bot = polyalpha.Bot("SOL", "15m", balance=1000)

# Via explicit kwargs
bot = polyalpha.Bot("SOL", "15m", balance=1000, api_key="...")
```

---

## BotHub — Multi-Strategy Hub

`BotHub` runs **multiple strategies from a single data connection**. One market discovery, one WebSocket stream — N isolated paper engines. Eliminates redundant rate-limited connections when running many strategies on the same asset/timeframe.

```python
import polyalpha

hub = polyalpha.BotHub("BTC", "5m", default_balance=500)

@hub.strategy("momentum")
def momentum(ctx):
    if ctx.price.up > 0.9 and ctx.rsi > 50:
        ctx.buy("UP", 20)

@hub.strategy("value", balance=1000)
def value(ctx):
    if ctx.price.down < 0.10:
        ctx.buy("DOWN", 10)

hub.run()
```

### When to use BotHub vs Bot

| Scenario | Use |
|----------|-----|
| One strategy, one connection | `Bot` |
| 20+ strategies on the same asset/timeframe | `BotHub` |
| Different assets or timeframes per strategy | Multiple `Bot` instances with `run_async()` |

With 20 separate `Bot` instances on the same asset/timeframe, each opens its own WebSocket — hitting rate limits 20x harder. `BotHub` fans one stream to all strategies, with error isolation (one crash doesn't stop the others).

### Constructor

```python
hub = polyalpha.BotHub(
    asset="BTC",              # BTC, ETH, SOL, XRP, DOGE, HYPE, BNB
    timeframe="5m",           # 5m, 15m, 1h, 4h, 24h
    default_balance=100.0,    # default starting balance per strategy
    mode="simple",            # "simple", "realistic", or "custom"
    paper_config=None,        # PaperConfig for mode="custom"
    **kwargs,                 # forwarded to polyalpha.Client
)
```

### Registration

#### `@hub.strategy(name, balance=None)`

Decorator that registers a strategy function. Each strategy gets its own `PaperEngine` (isolated balance, positions, P&L).

```python
@hub.strategy("momentum")           # uses default_balance
def momentum(ctx):
    ...

@hub.strategy("value", balance=1000)  # overrides default_balance
def value(ctx):
    ...
```

Raises `ValueError` if a strategy with the same name is already registered.

#### `hub.add_strategy(name, fn, balance=None)`

Non-decorator equivalent:

```python
hub.add_strategy("momentum", momentum_fn, balance=500)
```

### StrategyContext

Same public API as `TickContext` (`.price`, `.buy()`, `.limit()`, `.rsi`, `.sma_20`, etc.), plus a `.name` property identifying which strategy is running.

| Property | Returns | Description |
|----------|---------|-------------|
| `price` | `PriceSnapshot` | Current UP/DOWN prices from the shared stream |
| `balance` | `float` | This strategy's paper balance |
| `positions` | `list` | This strategy's open positions |
| `pnl` | `float` | This strategy's realised P&L |
| `market` | `Market \| None` | The current shared market |
| `name` | `str` | This strategy's registered name |
| `rsi` | `float \| None` | RSI(14) — requires `pandas` |
| `sma_20` | `float \| None` | SMA(20) — requires `pandas` |
| `ema_12` | `float \| None` | EMA(12) — requires `pandas` |

Methods: `buy(side, amount)`, `limit(side, price, amount)`, `close_position(side, amount=None)` — same signatures as `TickContext`.

### Running

```python
# Blocking
hub.run()

# Async
await hub.run_async()

# Stop gracefully
hub.stop()
```

### Properties

| Property | Returns | Description |
|----------|---------|-------------|
| `stats` | `dict` | Per-strategy running stats |
| `tick_count` | `int` | Total price ticks received |
| `strategy_count` | `int` | Number of registered strategies |

`stats` format:

```python
{
    "ticks": 142,
    "strategies": {
        "momentum": {"balance": 480.0, "pnl": -20.0, "open_positions": 2},
        "value":    {"balance": 520.0, "pnl": 20.0,  "open_positions": 0},
    },
}
```

### Lifecycle

Same cycle as `Bot`, but runs once for all strategies:

1. **Discover** — one `client.markets.latest()` call for the shared market
2. **Stream** — one WebSocket stream; every strategy's `PaperEngine` attaches to it for limit-order fills
3. **Tick** — on each price tick, calls every strategy's function with error isolation
4. **Resolve** — checks resolved positions for all strategies
5. **Rollover** — cleans up, waits 2 seconds, repeats

If no market is found, retries every 30 seconds.

### Example

See [`examples/bot_hub.py`](../examples/bot_hub.py) for a complete runnable example with 4 strategies.
