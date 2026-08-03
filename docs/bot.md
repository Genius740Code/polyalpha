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
    asset="BTC",              # required: BTC, ETH, SOL, XRP, DOGE, HYPE, BNB
    timeframe="5m",           # required: 5m, 15m, 1h, 4h, 24h
    balance=100.0,            # starting paper balance
    paper=True,               # True → paper trade, False → real trade
    mode="simple",            # "simple", "realistic", or "custom"
    paper_config=None,        # PaperConfig for mode="custom"
    log_dir=None,             # directory for rotating log files
    buy_once_per_market=True, # buy only once per market
    **kwargs,                 # forwarded to polyalpha.Client
)
```

### Constructor Parameters

| Param | Default | Description |
|-------|---------|-------------|
| `asset` | *(required)* | Trading asset. One of: BTC, ETH, SOL, XRP, DOGE, HYPE, BNB |
| `timeframe` | *(required)* | Market timeframe. One of: 5m, 15m, 1h, 4h, 24h |
| `balance` | `100.0` | Starting paper-trading balance in USDC |
| `paper` | `True` | `True` for paper trading, `False` for real trading |
| `mode` | `"simple"` | Execution template: `"simple"`, `"realistic"`, or `"custom"` |
| `paper_config` | `None` | `PaperConfig` instance (only used when `mode="custom"`) |
| `log_dir` | `None` | Directory for rotating per-bot log files (5 MB max, 3 backups) |
| `buy_once_per_market` | `True` | Buy only once per market. Set `False` to allow multiple buys within a market. |
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
| `candle_id` | `int` | Current candle identifier (increments on each new candle) |
| `seconds_in` | `float` | Seconds elapsed since the start of the current candle |
| `indicators` | `IndicatorAccessor` | First-class indicator access — see below |
| `rsi` | `float \| None` | RSI(14) — legacy, prefer `ctx.indicators.rsi(14)` |
| `sma_20` | `float \| None` | SMA(20) — legacy, prefer `ctx.indicators.sma(20)` |
| `ema_12` | `float \| None` | EMA(12) — legacy, prefer `ctx.indicators.ema(12)` |
| `chainlink` | `ChainlinkStreamer \| None` | Latest BTC/USD spot price from Polymarket's Chainlink oracle — see below |
| `binance` | `BinanceAccessor \| None` | Binance BTC market data for external TA (MACD, price change, RSI, etc.) — see below |

### IndicatorAccessor (`ctx.indicators`)

First-class indicator API with per-tick caching. All methods accept parameterized periods.

```python
# Query which indicators are available at runtime
available = ctx.indicators.available()
# → ["rsi", "sma", "ema", "macd", "bollinger_bands", "roc", "vwap", "donchian"]

# RSI with custom period
rsi = ctx.indicators.rsi(14)

# MACD with custom fast/slow/signal
macd = ctx.indicators.macd(12, 26, 9)  # → MACDResult(macd, signal, histogram)

# Bollinger Bands
bb = ctx.indicators.bollinger_bands(20, 2)  # → BBResult(upper, mid, lower)

# Moving averages
sma = ctx.indicators.sma(20)
ema = ctx.indicators.ema(12)

# Rate of Change
roc = ctx.indicators.roc(12)
```

| Method | Returns | Description |
|--------|---------|-------------|
| `available()` | `list[str]` | List of available indicator names |
| `rsi(period=14)` | `float \| None` | Relative Strength Index |
| `sma(period=20)` | `float \| None` | Simple Moving Average |
| `ema(period=12)` | `float \| None` | Exponential Moving Average |
| `macd(fast=12, slow=26, signal=9)` | `MACDResult \| None` | MACD line, signal, histogram |
| `bollinger_bands(period=20, std=2)` | `BBResult \| None` | Upper, mid, lower bands |
| `roc(period=12)` | `float \| None` | Rate of Change (percent) |
| `vwap()` | `float \| None` | Volume Weighted Average Price |
| `donchian(length=20)` | `DonchianResult \| None` | Upper, mid, lower Donchian bands |

All return `None` when `pandas` is not installed or there is insufficient price history.

### Chainlink Spot Price (`ctx.chainlink`)

Exposes the live BTC/USD spot price from Polymarket's Chainlink oracle WebSocket feed. Auto-started when `Bot` or `BotHub` initializes — no manual setup needed.

```python
@bot.on_tick
def strategy(ctx):
    spot = ctx.chainlink.last_price       # float | None — latest BTC/USD spot
    updated = ctx.chainlink.last_update    # float | None — timestamp
    symbol = ctx.chainlink.last_symbol     # str — e.g. "BTC/USD"
```

| Property | Returns | Description |
|----------|---------|-------------|
| `last_price` | `float \| None` | Latest BTC/USD spot price from the Chainlink oracle |
| `last_update` | `float \| None` | Unix timestamp of the last price update |
| `last_symbol` | `str \| None` | Symbol string (e.g. `"BTC/USD"`) |

Returns `None` if no price has been received yet (initial connect may take a few seconds).

### Chainlink Calculations (`ctx.cl`)

Enhanced Chainlink price window with calculation methods for price analysis.

```python
@bot.on_tick
def strategy(ctx):
    # Basic price window access
    latest = ctx.cl.value              # latest Chainlink price
    age = ctx.cl.age_s                # seconds since last update
    
    # Price change calculations
    change_30s = ctx.cl.change_pct(30)   # % change over 30 seconds
    change_60s = ctx.cl.change_pct(60)   # % change over 60 seconds
    change_abs = ctx.cl.change_abs(30)    # absolute price change
    
    # Trend analysis
    trend = ctx.cl.trend(60)              # UP/DOWN/NEUTRAL
    direction = ctx.cl.direction(30)      # "up"/"down"/"flat"
    
    # Volatility
    volatility = ctx.cl.volatility(120)   # price volatility
    
    # Price range
    high = ctx.cl.high(60)               # highest price in period
    low = ctx.cl.low(60)                # lowest price in period
    price_range = ctx.cl.range(60)       # price range (high - low)
```

| Method | Returns | Description |
|--------|---------|-------------|
| `value` | `float \| None` | Latest Chainlink price |
| `age_s` | `float` | Seconds since last update |
| `change_pct(seconds)` | `float \| None` | Percentage change over time period |
| `change_abs(seconds)` | `float \| None` | Absolute price change over time period |
| `trend(seconds, threshold=0.0)` | `TrendDirection` | UP/DOWN/NEUTRAL trend direction |
| `direction(seconds)` | `str \| None` | Simple direction: "up"/"down"/"flat" |
| `volatility(seconds)` | `float \| None` | Price volatility (standard deviation) |
| `high(seconds)` | `float \| None` | Highest price in time period |
| `low(seconds)` | `float \| None` | Lowest price in time period |
| `range(seconds)` | `float \| None` | Price range (high - low) |

### Binance Accessor (`ctx.binance`)

Enhanced Binance market data accessor with calculation library integration.

```python
@bot.on_tick
def strategy(ctx):
    # Basic Binance data
    close = ctx.binance.close          # latest Binance close price
    high = ctx.binance.high            # latest high
    low = ctx.binance.low             # latest low
    volume = ctx.binance.volume        # latest volume
    
    # Price calculations (using calculation library)
    change_pct = ctx.binance.change_pct(3)    # % change over 3 candles
    change_abs = ctx.binance.change_abs(3)    # absolute change over 3 candles
    trend = ctx.binance.trend(3)              # trend direction
    direction = ctx.binance.direction(3)      # "up"/"down"/"flat"
    volatility = ctx.binance.volatility(10)   # price volatility
    
    # Volume calculations (Binance has volume data)
    vol_ratio = ctx.binance.vol_ratio(10)          # current / avg volume
    volume_trend = ctx.binance.volume_trend(5)    # INCREASING/DECREASING/STABLE
    volume_surge = ctx.binance.volume_surge(2.0)  # detect volume spikes
    avg_volume = ctx.binance.avg_volume(10)        # average volume
    
    # Technical indicators (existing functionality)
    macd = ctx.binance.macd(12, 26, 9)    # MACD from Binance data
    rsi = ctx.binance.rsi(14)              # RSI from Binance data
    sma = ctx.binance.sma(20)              # SMA from Binance data
    ema = ctx.binance.ema(12)              # EMA from Binance data
```

| Method | Returns | Description |
|--------|---------|-------------|
| `close` | `float \| None` | Latest Binance close price |
| `high` | `float \| None` | Latest high price |
| `low` | `float \| None` | Latest low price |
| `volume` | `float \| None` | Latest volume |
| `change_pct(candles_back)` | `float \| None` | % price change over N candles |
| `change_abs(candles_back)` | `float \| None` | Absolute price change over N candles |
| `trend(candles_back, threshold=0.0)` | `str \| None` | Trend direction: "up"/"down"/"neutral" |
| `direction(candles_back)` | `str \| None` | Simple direction: "up"/"down"/"flat" |
| `volatility(candles_back)` | `float \| None` | Price volatility |
| `vol_ratio(period)` | `float \| None` | Current volume / average volume |
| `volume_trend(period, threshold=0.1)` | `str \| None` | Volume trend: "increasing"/"decreasing"/"stable" |
| `volume_surge(multiplier, period)` | `bool \| None` | True if volume surge detected |
| `avg_volume(period)` | `float \| None` | Average volume over period |
| `macd(fast, slow, signal)` | `MACDResult \| None` | MACD indicator |
| `rsi(period)` | `float \| None` | RSI indicator |
| `sma(period)` | `float \| None` | SMA indicator |
| `ema(period)` | `float \| None` | EMA indicator |

### Binance Market Data (`ctx.binance`)

Pulls OHLCV data from the free Binance REST API for external technical analysis (MACD, RSI, price momentum, etc.). Auto-refreshes once per candle — no redundant API calls.

```python
@bot.on_tick
def strategy(ctx):
    # Raw market data
    close = ctx.binance.close             # float — latest close price
    high = ctx.binance.high               # float — current candle high
    low = ctx.binance.low                 # float — current candle low
    volume = ctx.binance.volume           # float — current candle volume

    # Indicators (computed from Binance OHLCV data)
    macd = ctx.binance.macd(12, 26, 9)    # MACDResult(macd, signal, histogram)
    rsi = ctx.binance.rsi(14)             # float | None
    sma = ctx.binance.sma(20)             # float | None
    ema = ctx.binance.ema(12)             # float | None

    # Price movement helpers
    change = ctx.binance.price_change(3)           # float — BTC price change over last 3 candles
    change_pct = ctx.binance.price_change_percent(3)  # float — percent change
    up = ctx.binance.price_up(2)                   # bool — close higher than 2 candles ago?
    jumped = ctx.binance.price_above_by(50)        # bool — moved up at least $50?
```

| Property / Method | Returns | Description |
|-------------------|---------|-------------|
| `close` | `float \| None` | Latest Binance close price |
| `high` | `float \| None` | Current candle high |
| `low` | `float \| None` | Current candle low |
| `volume` | `float \| None` | Current candle volume |
| `macd(fast=12, slow=26, signal=9)` | `MACDResult \| None` | MACD line, signal, histogram |
| `rsi(period=14)` | `float \| None` | Relative Strength Index |
| `sma(period=20)` | `float \| None` | Simple Moving Average |
| `ema(period=12)` | `float \| None` | Exponential Moving Average |
| `price_change(candles=1)` | `float \| None` | BTC close price change over N candles |
| `price_change_percent(candles=1)` | `float \| None` | BTC percent change over N candles |
| `price_up(candles=1)` | `bool` | Close higher than N candles ago |
| `price_above_by(amount=50)` | `bool` | Close at least $amount higher than N candles ago |

### Chainlink Price Window (`ctx.cl`)

Provides a rolling window of Chainlink BTC prices with convenient methods for calculating percentage changes over custom time periods. This eliminates the need for manual deque management in strategies.

```python
@bot.on_tick
def strategy(ctx):
    # Latest Chainlink price
    price = ctx.cl.value                     # float | None — latest CL price
    
    # Percentage change over custom time periods
    change_30s = ctx.cl.change_pct(30)       # float | None — % change over 30 seconds
    change_60s = ctx.cl.change_pct(60)       # float | None — % change over 60 seconds
    change_90s = ctx.cl.change_pct(90)       # float | None — % change over 90 seconds
    
    # Time since last update
    age = ctx.cl.age_s                       # float — seconds since last CL price update
    
    # Example strategy: buy UP when BTC jumps > 8% in 30 seconds
    if change_30s and change_30s > 0.08 and ctx.price.up < 0.60:
        ctx.buy("UP", 20)
```

| Property / Method | Returns | Description |
|-------------------|---------|-------------|
| `value` | `float \| None` | Latest Chainlink BTC price |
| `change_pct(seconds)` | `float \| None` | Percentage change over the given time period (in seconds) |
| `age_s` | `float` | Seconds since the last price update (∞ if no data) |
| `get_value_at(seconds_ago)` | `float \| None` | Price at a specific time in the past |

**Note:** Returns `None` if insufficient data is available (e.g., requesting change over 60 seconds when only 10 seconds of data exists).
| `price_above_by(min_change)` | `bool` | Close moved up by at least `min_change` USD |

Returns `None` on indicator methods when insufficient data.

### Mixing Data Sources in One Bot

Combine Polymarket UP/DOWN prices, Chainlink BTC spot, and Binance TA in a single strategy:

```python
from polyalpha.conditions import and_, price_above, macd_bullish_crossover

bot = polyalpha.Bot("BTC", "5m", balance=500)

bot.when(
    and_(
        price_above("UP", 0.90),           # Polymarket WSS
        macd_bullish_crossover(),           # Binance API (MACD on BTC)
    )
).buy("UP", 20)

bot.run()
```

Or in an `on_tick` strategy:

```python
@bot.on_tick
def strategy(ctx):
    # Polymarket market price
    up_price = ctx.price.up
    # Chainlink BTC spot
    btc_spot = ctx.chainlink.last_price
    # Binance MACD
    macd = ctx.binance.macd(12, 26, 9)

    if up_price > 0.9 and btc_spot and btc_spot > 60000 and macd and macd.histogram > 0:
        ctx.buy("UP", 20)
```

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

#### `buy_once_per_candle(side, amount)`

Buy only if `side` hasn't been bought yet in the current candle. Safe to call repeatedly — subsequent calls within the same candle for the same side are silently skipped.

| Param | Type | Description |
|-------|------|-------------|
| `side` | `str` | `"UP"` or `"DOWN"` |
| `amount` | `float` | USDC to spend |

Returns a `PaperOrder` or `None` (if already bought this candle).

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

### Price Filtering Conditions

The conditions module includes powerful price filtering capabilities:

```python
from polyalpha.conditions import (
    and_, price_in_range, price_not_in_ranges
)

# Only enter when UP price is in range [0.90, 0.95]
bot.when(price_in_range("up", 0.90, 0.95)).buy("UP", 20)

# Avoid specific price segments (e.g., low liquidity zones)
bot.when(
    and_(
        price_in_range("up", 0.90, 0.98),
        price_not_in_ranges("up", [(0.93, 0.94), (0.96, 0.97)])
    )
).buy("UP", 20)
```

Available price conditions:
- `price_above(side, threshold)` — price > threshold
- `price_below(side, threshold)` — price < threshold
- `price_in_range(side, min, max)` — price in range [min, max]
- `price_not_in_ranges(side, ranges)` — price NOT in excluded ranges

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

Unlike `strategy()`, `variant()` is identical — it is an alias that exists purely for readability. The only distinction is the `params` argument: strategies with non-empty `params` metadata are treated as "variants" for comparison via `compare_variants()`.

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
    asset="BTC",              # required: BTC, ETH, SOL, XRP, DOGE, HYPE, BNB
    timeframe="5m",           # required: 5m, 15m, 1h, 4h, 24h
    default_balance=100.0,    # default starting balance per strategy
    mode="simple",            # "simple", "realistic", or "custom"
    paper_config=None,        # PaperConfig for mode="custom"
    chainlink=True,           # enable Chainlink oracle price feed (also starts Binance TA stream)
    log_dir=None,             # directory for per-strategy rotating log files
    buy_once_per_market=True, # buy only once per market, per strategy
    **kwargs,                 # forwarded to polyalpha.Client
)
```

| Param | Default | Description |
|-------|---------|-------------|
| `asset` | *(required)* | Trading asset |
| `timeframe` | *(required)* | Market timeframe |
| `default_balance` | `100.0` | Default starting balance per strategy/variant |
| `mode` | `"simple"` | Fee/execution template |
| `paper_config` | `None` | `PaperConfig` for `mode="custom"` |
| `chainlink` | `True` | Enable background Chainlink oracle price feed (`ctx.spot_price`) |
| `log_dir` | `None` | Directory for per-strategy rotating log files (5 MB max, 3 backups) |
| `buy_once_per_market` | `True` | Each strategy buys only once per market. Set `False` to allow multiple buys. |

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

#### `@hub.variant(name, balance=None, params=None, id="")`

Identity alias for `@hub.strategy()`. Exists purely for readability — use it when you want to emphasise that a strategy carries parameter metadata for comparison.

The only distinction: strategies with **non-empty `params`** are included in `compare_variants()` output. Strategies registered via `strategy()` without `params` are still compared if no other strategy has `params`.

```python
@hub.variant("rsi_70", params={"threshold": 70})
def rsi_70(ctx):
    if ctx.indicators.rsi(14) and ctx.indicators.rsi(14) > 70:
        ctx.buy("DOWN", 10)

@hub.variant("rsi_30", params={"threshold": 30})
def rsi_30(ctx):
    if ctx.indicators.rsi(14) and ctx.indicators.rsi(14) < 30:
        ctx.buy("UP", 10)

hub.run()
report = hub.compare_variants()  # sorted by P&L
report.print()
```

| Param | Type | Default | Description |
|-------|------|---------|-------------|
| `name` | `str` | — | Unique variant name |
| `balance` | `float \| None` | `default_balance` | Per-variant starting balance |
| `params` | `dict \| None` | `{}` | Free-form metadata surfaced in comparison reports — this is what distinguishes a variant from a plain strategy |
| `id` | `str` | `""` | Stable identifier for persistence (defaults to name) |

#### `hub.add_variant(name, fn, balance=None, params=None, id="")`

Non-decorator equivalent. Identity alias for `hub.add_strategy()`.

### StrategyContext

Same public API as `TickContext` plus Chainlink/candle/orderbook properties and a `.name` identifier.

```python
@hub.strategy("example")
def strategy(ctx):
    # Chainlink spot price (requires chainlink=True)
    spot = ctx.chainlink.last_price
    
    # Chainlink price window with change helpers
    cl_price = ctx.cl.value                     # latest CL price
    change_30s = ctx.cl.change_pct(30)         # % change over 30 seconds
    cl_age = ctx.cl.age_s                      # seconds since last update

    # Binance BTC market data (auto-started for all BotHub instances)
    macd = ctx.binance.macd(12, 26, 9)
    change = ctx.binance.price_change(3)
    btc_close = ctx.binance.close

    # Order book (auto-attached to shared WebSocket stream)
    bids = ctx.orderbook.up.bids        # tuple[BookLevel]
    spread = ctx.orderbook.down.spread  # float
    ctx.orderbook.refresh()             # force REST refresh

    # Candle-aware trading
    ctx.buy_once_per_candle("UP", 20)
    ctx.buy_in_window("DOWN", 10, min_seconds=30, max_seconds=120)

    # Indicators
    macd = ctx.indicators.macd(12, 26, 9)
    bb = ctx.indicators.bollinger_bands(20, 2)

    # Query available indicators at runtime
    available = ctx.indicators.available()
    # → ["rsi", "sma", "ema", "macd", "bollinger_bands", "roc", "vwap", "donchian"]
```

| Property | Returns | Description |
|----------|---------|-------------|
| `price` | `PriceSnapshot` | Current UP/DOWN prices from the shared stream |
| `spot_price` | `float \| None` | Current Chainlink oracle price (requires `chainlink=True`). Prefer `ctx.chainlink.last_price` for live WS feed. |
| `balance` | `float` | This strategy's paper balance |
| `positions` | `list` | This strategy's open positions |
| `pnl` | `float` | This strategy's realised P&L |
| `market` | `Market \| None` | The current shared market |
| `name` | `str` | This strategy's registered name |
| `candle_open` | `float \| None` | Opening price of the current candle |
| `seconds_in` | `float` | Seconds elapsed since the start of the current candle |
| `candle_id` | `int` | Current candle identifier (increments on each new candle) |
| `indicators` | `IndicatorAccessor` | Parameterized indicators — see below |
| `orderbook` | `OrderBookAccessor \| None` | Live order book for the current market (auto-attached) |
| `cl` | `TimeWindow \| None` | Chainlink price window with change percentage helpers |
| `rsi` | `float \| None` | RSI(14) — legacy, prefer `ctx.indicators.rsi(14)` |
| `sma_20` | `float \| None` | SMA(20) — legacy, prefer `ctx.indicators.sma(20)` |
| `ema_12` | `float \| None` | EMA(12) — legacy, prefer `ctx.indicators.ema(12)` |
| `chainlink` | `ChainlinkStreamer \| None` | Latest BTC/USD spot price from Polymarket's Chainlink oracle — see below |
| `binance` | `BinanceAccessor \| None` | Binance BTC market data for external TA (MACD, price change, RSI, etc.) — see below |

Methods: `buy(side, amount)`, `limit(side, price, amount)`, `close_position(side, amount=None)`, `buy_once_per_candle(side, amount)`, `buy_in_window(side, amount, min_seconds, max_seconds)` — same signatures as `TickContext`.

#### OrderBookAccessor (`ctx.orderbook`)

Lazily creates and auto-attaches an `OrderBookFeed` to the shared WebSocket stream. Fetches an initial REST snapshot on first access so data is available immediately.

```python
ctx.orderbook.up.bids        # tuple[BookLevel] — UP token bids
ctx.orderbook.down.asks      # tuple[BookLevel] — DOWN token asks
ctx.orderbook.up.spread      # float — UP bid-ask spread
ctx.orderbook.up.mid_price   # float — UP mid price
ctx.orderbook.book           # MarketOrderBook — combined book
ctx.orderbook.refresh()      # force fresh REST snapshot
```

| Property | Returns | Description |
|----------|---------|-------------|
| `up` | `OrderBookSnapshot \| None` | UP token order book (bids, asks, spread, mid_price) |
| `down` | `OrderBookSnapshot \| None` | DOWN token order book (bids, asks, spread, mid_price) |
| `book` | `MarketOrderBook` | Combined UP + DOWN market order book |
| `refresh()` | `MarketOrderBook` | Fetches fresh REST snapshots for both tokens |

### Cross-Variant Comparison

After running the hub, compare all registered variants:

```python
hub.run()
report = hub.compare_variants()
report.print()
```

Output is a Rich table sorted by P&L:

| Rank | Variant | Trades | Win% | P&L | Sharpe | DD | Balance |
|------|---------|--------|------|-----|--------|----|---------|

```python
# Access results programmatically
for r in report.results:
    print(f"{r.name}: P&L=${r.pnl:.2f} win%={r.win_rate:.1f}")

report.best           # VariantResult with highest P&L
report.worst          # VariantResult with lowest P&L
report.get("rsi_70")  # Look up a specific variant by name
report.variant_count  # number of variants
report.dump()         # JSON-serialisable dict
```

### Persisting & Loading Runs

Comparison snapshots are automatically saved to `~/.polyalpha/variants/`.

```python
# Save manually (returns the Path written to)
path = report.save()

# List past runs
hub.list_runs()
# [{"timestamp": "...", "path": "...", "variants": ["rsi_70", "rsi_30"]}, ...]

# Load a previous run
report = hub.load_run("2026-07-24T15-30-00")
report.print()
```

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
| `stats` | `dict` | Per-strategy running stats (balance, pnl, open_positions, params) |
| `tick_count` | `int` | Total price ticks received |
| `strategy_count` | `int` | Number of registered strategies |
| `variant_count` | `int` | Number of registered variants (alias for `strategy_count`) |
| `total_count` | `int` | Combined strategies + variants |
| `strategies` | `list[RegisteredStrategy]` | Read-only view of all registered strategies |
| `variants` | `list[RegisteredStrategy]` | Read-only view of all registered strategies (alias for `strategies`) |

`stats` format:

```python
{
    "ticks": 142,
    "strategies": {
        "momentum": {"balance": 480.0, "pnl": -20.0, "open_positions": 2},
        "value":    {"balance": 520.0, "pnl": 20.0,  "open_positions": 0},
    },
    "variants": {
        "rsi_70": {"balance": 510.0, "pnl": 10.0, "open_positions": 1, "params": {"threshold": 70}},
        "rsi_30": {"balance": 490.0, "pnl": -10.0, "open_positions": 0, "params": {"threshold": 30}},
    },
}
```

### Event Hooks & Timers

BotHub provides a hook system for lifecycle events and periodic callbacks, so you don't need to register dummy strategies just for logging or maintenance tasks.

#### `hub.on(event)`

Register a handler for a lifecycle event. Works as a decorator or imperatively.

| Event | Handler Signature | Description |
|-------|-------------------|-------------|
| `"start"` | `()` | Hub started |
| `"stop"` | `()` | Hub stopping gracefully |
| `"tick"` | `(up, down)` | Every price tick |
| `"candle_open"` | `(open_price, candle_id)` | A new candle started |
| `"candle_close"` | `(candle_id, open_price, close_price)` | The current candle closed |
| `"error"` | `(strategy_name, exception)` | A strategy raised an exception |

```python
@hub.on("start")
def on_start():
    log("HUB", "BotHub started!")

@hub.on("tick")
def on_tick(up, down):
    if up > 0.95:
        log("TICK", f"UP heavily favored: {up:.3f}")

@hub.on("candle_open")
def on_candle_open(open_price, candle_id):
    log("CANDLE", f"Candle #{candle_id} opened at {open_price}")

@hub.on("error")
def on_error(name, exc):
    log("ERROR", f"Strategy '{name}' failed: {exc}")

# Imperative form
hub.on("stop", my_cleanup)

# Or use add_handler (equivalent)
hub.add_handler("start", my_start_fn)
```

#### `hub.every(seconds)`

Register a periodic timer callback that fires roughly every `seconds` seconds, checked on each price tick. The handler receives the latest `(up, down)` prices.

```python
@hub.every(30)
def status_check(up, down):
    print(f"Status tick: UP={up:.3f} DOWN={down:.3f}")

hub.every(60, my_minute_fn)
```

This replaces the old workaround of registering a dummy strategy just for periodic logging.



### Lifecycle

Same cycle as `Bot`, but runs once for all strategies:

1. **Discover** — one `client.markets.latest()` call for the shared market
2. **Stream** — one WebSocket stream; every strategy's `PaperEngine` attaches to it for limit-order fills
3. **Tick** — on each price tick, calls every strategy's function with error isolation
4. **Resolve** — checks resolved positions for all strategies
5. **Rollover** — cleans up, waits 2 seconds, repeats

If no market is found, retries every 30 seconds.

### Example

See [`examples/bot_hub.py`](../examples/bot_hub.py) for a complete runnable example with strategies, variants, event hooks, and periodic timers.
