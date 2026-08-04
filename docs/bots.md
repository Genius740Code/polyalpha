# Bot Utilities — Sniper, Tracker, WeatherConfig

High-level trading bots built on top of the paper trading engine. Accessible via `polyalpha.bots` or directly from `polyalpha`.

---

## Sniper

Time-window entry bot with threshold-based execution. Monitors market prices and executes limit orders only during a specified time window before market resolution. Auto-rolls over to the next market after resolution.

```python
from polyalpha import Client, Sniper

client = Client(balance=500)
sniper = Sniper(client, asset="BTC", timeframe="5m", side="UP",
                entry_price=0.92, exit_price=0.88,
                window_seconds=35, amount=20.0)
sniper.run()
```

### Constructor

```python
sniper = Sniper(
    client,
    config: SniperConfig | None = None,
    **kwargs,  # forwarded to SniperConfig if config is None
)
```

### State Machine

```
IDLE → DISCOVERING → WAITING → ARMED → FILLED → RESOLVING → ROLLOVER → IDLE
```

### Events

Register event handlers with the `@sniper.on(event)` decorator:

| Event | Args | Description |
|-------|------|-------------|
| `market_found` | `market` | New market discovered |
| `window_enter` | `market` | Entering the trading window |
| `entry` | `order` | Order filled |
| `exit` | `reason` | Order cancelled (`"exit_threshold"` or `"window_close"`) |
| `resolve` | `outcome, pnl` | Market resolved |
| `rollover` | `market` | Transitioning to next market |
| `error` | `exception` | Unrecoverable error |
| `stop` | `reason` | Bot stopped |

```python
@sniper.on("resolve")
def on_resolve(outcome, pnl):
    print(f"Resolved {outcome}: ${pnl:.2f}")

@sniper.on("entry")
def on_entry(order):
    print(f"Filled: {order.shares:.2f} shares @ {order.price:.4f}")

@sniper.on("error")
def on_error(exc):
    print(f"Error: {exc}")
```

### Methods

| Method | Description |
|--------|-------------|
| `on(event)` | Decorator to register an event handler |
| `add_handler(event, fn)` | Register an event handler without decorator syntax |
| `run()` | Start the Sniper bot (blocking) |
| `stop(reason="manual")` | Stop the Sniper bot |

### Properties

| Property | Returns | Description |
|----------|---------|-------------|
| `stats` | `SniperStats` | Current bot statistics |
| `state` | `str` | Current bot state (IDLE, DISCOVERING, WAITING, ARMED, FILLED, RESOLVING, ROLLOVER, STOP) |

### SniperStats

| Field | Type | Description |
|-------|------|-------------|
| `total_trades` | `int` | Total number of trades |
| `wins` | `int` | Winning trades |
| `losses` | `int` | Losing trades |
| `total_pnl` | `float` | Total P&L |
| `consecutive_losses` | `int` | Current consecutive loss streak |
| `win_rate` | `float` | Win rate percentage (0–100) |
| `avg_entry_price` | `float` | Average entry price |
| `avg_exit_price` | `float` | Average exit price |

### SniperConfig

```python
from polyalpha.bots.sniper import SniperConfig

config = SniperConfig(
    asset="BTC",
    timeframe="5m",
    side="UP",
    entry_price=0.92,
    exit_price=0.88,
    window_seconds=35,
    amount=20.0,
)
```

| Field | Default | Description |
|-------|---------|-------------|
| `asset` | `"BTC"` | Trading asset |
| `timeframe` | *(required)* | Market timeframe. One of: 5m, 15m, 1h, 4h, 24h |
| `side` | `"UP"` | `"UP"` or `"DOWN"` |
| `entry_price` | `0.92` | Entry price threshold (0–1) |
| `entry_price_max` | `None` | Maximum entry price for price range (must be > entry) |
| `exit_price` | `0.88` | Exit price threshold (must be < entry) |
| `excluded_price_ranges` | `None` | List of (min, max) tuples to exclude from entry |
| `window_seconds` | `35` | Trading window before market end (simple mode) |
| `time_windows` | `None` | Advanced time windows (list of `TimeWindow` objects) |
| `conditional_windows` | `None` | Indicator-based conditional windows (list of `ConditionalWindow` objects) |
| `time_filter` | `None` | Day/hour filtering (`TimeFilter` object) |
| `amount` | `20.0` | USDC amount per trade |
| `buy_once_per_market` | `True` | Buy only once per market. Set `False` to keep buying as long as entry conditions are met within the same market. |
| `max_position_size` | `None` | Maximum position exposure |
| `max_consecutive_losses` | `3` | Stop after this many consecutive losses |
| `max_trades` | `None` | Maximum total trades before stopping |
| `allowed_market_sessions` | `None` | Filter by market session (e.g., `["london", "new_york"]`) |
| `pre_window_buffer` | `5` | Seconds before window to start checking |
| `post_window_timeout` | `10` | Seconds after window close to wait for fill |
| `log_level` | `"INFO"` | Logging level |
| `log_trades` | `True` | Log trade details |
| `log_prices` | `False` | Log individual price updates |
| `use_ta` | `False` | Enable technical analysis filters |
| `ta_data_source` | `None` | TA data source (`"binance"`, `"chainlink"`, `"custom"`) |
| `ta_rsi_threshold` | `None` | Minimum RSI for entry |
| `ta_sma_period` | `None` | Minimum SMA period for entry |
| `ta_rules` | `None` | Custom TA evaluation rules |
| `max_btc_change_pct` | `None` | Max BTC spot price change % to allow entry (e.g., `2.0` = 2%) |
| `btc_change_periods` | `5` | Lookback periods for BTC change calculation |
| `max_price` | `1.0` | Maximum valid price from the stream; prices above this are treated as edge cases (log + proceed) |

All parameters are validated on initialization. Invalid values raise `ValueError` with descriptive messages.

#### `timeframe` is required

`timeframe` has **no default** — you must always pass it explicitly (e.g. `"5m"`, `"15m"`, `"1h"`, `"4h"`, `"24h"`). Omitting it raises `TypeError`.

```python
SniperConfig(asset="BTC")                 # ❌ TypeError: timeframe required
SniperConfig(asset="BTC", timeframe="1h") # ✅
```

#### `buy_once_per_market`

Controls how many entries the sniper makes within a single market:

| Value | Behavior |
|-------|----------|
| `True` (default) | Buys at most **once** per market. After the first fill, no further entries are attempted until the next market. |
| `False` | Keeps placing entries whenever the entry conditions are met during the trading window, until the window closes. |

```python
config = SniperConfig(
    asset="BTC",
    timeframe="1h",
    side="UP",
    entry_price=0.92,
    amount=20.0,
    buy_once_per_market=False,  # allow multiple entries in the same market
)
```

### Market Session Filtering

Restrict trading to specific global market sessions:

```python
config = SniperConfig(
    asset="BTC",
    timeframe="5m",
    side="UP",
    entry_price=0.92,
    amount=20.0,
    allowed_market_sessions=["london", "new_york"],  # only these sessions
)
```

Available sessions: `"london"`, `"new_york"`, `"asia"`, `"sydney"`.

### TA-Enhanced Sniper

```python
config = SniperConfig(
    asset="BTC",
    timeframe="5m",
    side="UP",
    entry_price=0.92,
    window_seconds=35,
    amount=20.0,
    use_ta=True,
    ta_data_source="binance",
    ta_rsi_threshold=50,
    ta_sma_period=20,
)
```

### Price Range Filtering

Control entry with a price range instead of a single threshold:

```python
# Only enter when price is between 0.90 and 0.95
config = SniperConfig(
    asset="BTC",
    timeframe="5m",
    side="UP",
    entry_price=0.90,
    entry_price_max=0.95,
    window_seconds=35,
    amount=20.0,
)
```

### BTC Price Change Filter

Skip entry when BTC spot price moves too much (high volatility guard):

```python
# Skip entry if BTC moved more than 2% in the last 5 candles
config = SniperConfig(
    asset="BTC",
    timeframe="5m",
    side="UP",
    entry_price=0.92,
    window_seconds=35,
    amount=20.0,
    max_btc_change_pct=2.0,     # skip if BTC changed > 2%
    btc_change_periods=5,       # lookback over 5 candles
)
```

Uses Binance spot price data to calculate the absolute percentage change. If the
change exceeds `max_btc_change_pct`, the entry is skipped. Errors gracefully —
if the data feed fails, entry is allowed to proceed.

### Excluded Price Ranges

Avoid specific price segments by defining excluded ranges:

```python
# Enter between 0.90 and 0.98, but avoid 0.93-0.94 and 0.96-0.97
config = SniperConfig(
    asset="BTC",
    timeframe="5m",
    side="UP",
    entry_price=0.90,
    entry_price_max=0.98,
    excluded_price_ranges=[(0.93, 0.94), (0.96, 0.97)],
    window_seconds=35,
    amount=20.0,
)
```

This is useful for avoiding price zones with low liquidity or unfavorable conditions.

### Advanced Time Windows

The Sniper bot supports advanced time window configuration for complex trading schedules. Use `TimeWindow`, `ConditionalWindow`, and `TimeFilter` classes to create sophisticated trading strategies.

#### TimeWindow

Flexible time window specification supporting multiple window types:

```python
from polyalpha.bots import TimeWindow, ConditionalWindow, TimeFilter
```

**Offset-based windows** (relative to market end):
```python
# Trade between 2 min to 1 min before market end, and last 30 seconds
config = SniperConfig(
    asset="BTC",
    timeframe="5m",
    side="UP",
    entry_price=0.92,
    exit_price=0.88,
    time_windows=[
        TimeWindow(start_offset=-120, end_offset=-60),  # 2 min to 1 min before end
        TimeWindow(start_offset=-30, end_offset=0),     # Last 30 seconds
    ],
    amount=20.0,
)
```

**Absolute time windows** (specific UTC times):
```python
# Trade only during 01:00-02:00 and 02:30-03:00 UTC
config = SniperConfig(
    asset="BTC",
    timeframe="5m",
    side="UP",
    entry_price=0.92,
    exit_price=0.88,
    time_windows=[
        TimeWindow(start_time="01:00", end_time="02:00"),
        TimeWindow(start_time="02:30", end_time="03:00"),
    ],
    amount=20.0,
)
```

**Burst patterns** (repeating on/off intervals):
```python
# Trade in 10-second bursts with 20-second pauses
config = SniperConfig(
    asset="BTC",
    timeframe="5m",
    side="UP",
    entry_price=0.92,
    exit_price=0.88,
    time_windows=[
        TimeWindow(burst_on=10, burst_off=20),  # 10s on, 20s off, repeating
    ],
    amount=20.0,
)
```

**TimeWindow parameters**:
| Parameter | Type | Description |
|-----------|------|-------------|
| `start_offset` | `int \| None` | Seconds before market end (negative) or after start (positive) |
| `end_offset` | `int \| None` | Seconds before market end (negative) or after start (positive) |
| `start_time` | `str \| None` | Start time in HH:MM format (UTC) |
| `end_time` | `str \| None` | End time in HH:MM format (UTC) |
| `burst_on` | `int \| None` | Seconds to stay ON in burst pattern |
| `burst_off` | `int \| None` | Seconds to stay OFF in burst pattern |

Only one window type can be specified per `TimeWindow` instance.

#### ConditionalWindow

Indicator-based conditional windows that only open when specified conditions are met:

```python
# Trade only when BTC price change < 2%
config = SniperConfig(
    asset="BTC",
    timeframe="5m",
    side="UP",
    entry_price=0.92,
    exit_price=0.88,
    time_windows=[
        TimeWindow(start_offset=-60, end_offset=0),
    ],
    conditional_windows=[
        ConditionalWindow(
            indicator="btc_change",
            operator="lt",
            threshold=2.0,
            periods=5
        ),
    ],
    amount=20.0,
)
```

**Supported indicators**:
- `btc_change`: BTC spot price change percentage
- `rsi`: Relative Strength Index
- `sma`: Simple Moving Average
- `custom`: Custom callable function

**Supported operators**: `lt`, `lte`, `gt`, `gte`, `eq`

**Data sources**: `binance`, `chainlink`, `custom`

**ConditionalWindow parameters**:
| Parameter | Type | Description |
|-----------|------|-------------|
| `indicator` | `str` | Indicator type (`btc_change`, `rsi`, `sma`, `custom`) |
| `operator` | `str` | Comparison operator (`lt`, `lte`, `gt`, `gte`, `eq`) |
| `threshold` | `float` | Threshold value for comparison |
| `source` | `str \| None` | Data source (`binance`, `chainlink`, `custom`) |
| `periods` | `int \| None` | Lookback periods for multi-period indicators |
| `custom_check` | `Callable \| None` | Custom callable for complex conditions |

**Custom conditional window**:
```python
def custom_condition():
    # Your custom logic here
    return True  # or False

config = SniperConfig(
    asset="BTC",
    timeframe="5m",
    side="UP",
    entry_price=0.92,
    exit_price=0.88,
    time_windows=[
        TimeWindow(start_offset=-60, end_offset=0),
    ],
    conditional_windows=[
        ConditionalWindow(
            indicator="custom",
            operator="gt",
            threshold=0.5,
            custom_check=custom_condition
        ),
    ],
    amount=20.0,
)
```

#### TimeFilter

Time-based filtering for day of week and hour of day restrictions:

```python
# Only trade weekdays (Monday-Friday) during business hours (9AM-5PM UTC)
config = SniperConfig(
    asset="BTC",
    timeframe="5m",
    side="UP",
    entry_price=0.92,
    exit_price=0.88,
    time_windows=[
        TimeWindow(start_offset=-60, end_offset=0),
    ],
    time_filter=TimeFilter(
        days=[0, 1, 2, 3, 4],  # Monday-Friday (0=Monday, 6=Sunday)
        hours=[9, 10, 11, 12, 13, 14, 15, 16, 17]  # 9AM-5PM UTC
    ),
    amount=20.0,
)
```

**TimeFilter parameters**:
| Parameter | Type | Description |
|-----------|------|-------------|
| `days` | `List[int] \| None` | Days of week (0=Monday, 6=Sunday) |
| `hours` | `List[int] \| None` | Hours of day in UTC (0-23) |

#### Combined Advanced Configuration

All advanced features can be combined for sophisticated trading strategies:

```python
config = SniperConfig(
    asset="BTC",
    timeframe="5m",
    side="UP",
    entry_price=0.92,
    exit_price=0.88,
    # Multiple time windows
    time_windows=[
        TimeWindow(start_time="01:00", end_time="02:00"),
        TimeWindow(start_time="02:30", end_time="03:00"),
    ],
    # Conditional windows (must also satisfy indicator conditions)
    conditional_windows=[
        ConditionalWindow(
            indicator="btc_change",
            operator="lt",
            threshold=2.0,
            periods=5
        ),
    ],
    # Time filtering (only on specific days/hours)
    time_filter=TimeFilter(
        days=[0, 1, 2, 3, 4],  # Weekdays only
        hours=[9, 10, 11, 12, 13, 14, 15, 16, 17]  # Business hours
    ),
    amount=20.0,
)
```

#### Backward Compatibility

The simple `window_seconds` parameter continues to work exactly as before:

```python
# Simple case (unchanged)
config = SniperConfig(
    asset="BTC",
    timeframe="5m",
    side="UP",
    entry_price=0.92,
    exit_price=0.88,
    window_seconds=35,  # Still works as before
    amount=20.0,
)
```

If both `window_seconds` and `time_windows` are provided, `time_windows` takes precedence.

---

## Tracker

P&L tracking and reporting utility. Aggregates trading data from the paper engine and provides statistics and export capabilities.

```python
from polyalpha import Client, Tracker

client = Client(balance=500)
tracker = Tracker(client)
tracker.summary()
tracker.export_json("trades.json")
tracker.export_csv("trades.csv")
```

### Constructor

```python
tracker = Tracker(client)
```

### Methods

| Method | Description |
|--------|-------------|
| `sync()` | Pull all completed trades from the paper engine. Called automatically by `summary()`, `export_json()`, `export_csv()` |
| `summary()` | Print a formatted P&L summary to stdout |
| `trades()` | Return list of `TradeRecord` objects |
| `export_json(filepath)` | Export trades to JSON file |
| `export_csv(filepath)` | Export trades to CSV file |

### Properties

| Property | Returns | Description |
|----------|---------|-------------|
| `total_trades` | `int` | Total tracked trades |
| `wins` | `int` | Winning trades |
| `losses` | `int` | Losing trades |
| `win_rate` | `float` | Win rate percentage (0–100) |
| `total_pnl` | `float` | Total P&L |
| `total_fees` | `float` | Total fees |
| `avg_entry_price` | `float` | Average entry price |
| `avg_pnl_per_trade` | `float` | Average P&L per trade |

### TradeRecord

| Field | Type | Description |
|-------|------|-------------|
| `market_slug` | `str` | Market identifier |
| `side` | `str` | `"UP"` or `"DOWN"` |
| `entry_price` | `float` | Entry price |
| `exit_price` | `float \| None` | Exit price |
| `amount` | `float` | Trade amount |
| `shares` | `float` | Shares traded |
| `fee` | `float` | Trading fee |
| `outcome` | `str \| None` | `"WON"`, `"LOST"`, or `None` |
| `pnl` | `float` | P&L |
| `timestamp` | `datetime` | Trade timestamp |

---

## WeatherConfig

Pre-configured city templates for weather trading bots. Provides station codes, coordinates, timezone, and bucket mode for 10 major Asian cities.

```python
from polyalpha.bots import CITIES, list_configs, print_config, get_config

# List available cities
print(list_configs())

# Get a config dictionary
config = get_config("Seoul")
# {"station": "RKSI", "source": "iem", "lat": 37.469, ...}

# Print for copy-paste
print_config("Tokyo")

# Add a custom config
from polyalpha.bots.weather_config import add_config
add_config("MyCity", {"station": "KJFK", "source": "iem", ...})
```

### Functions

| Function | Description |
|----------|-------------|
| `list_configs()` | Return list of all available city names |
| `get_config(name)` | Get a config dict by name (returns a copy) |
| `print_config(name)` | Print a config in copy-paste friendly format |
| `add_config(name, dict)` | Add a new configuration |

### Available Cities

| City | Station | Source | Timezone |
|------|---------|--------|----------|
| Seoul | RKSI | iem | Asia/Seoul |
| Shanghai | ZSPD | iem | Asia/Shanghai |
| Chengdu | ZUUU | iem | Asia/Shanghai |
| Shenzhen | ZGSZ | iem | Asia/Shanghai |
| Hong Kong | HKO | hko | Asia/Hong_Kong |
| Tokyo | RJTT | iem | Asia/Tokyo |
| Singapore | WSSS | iem | Asia/Singapore |
| Bangkok | VTBS | iem | Asia/Bangkok |
| Manila | RPLL | iem | Asia/Manila |
| Jakarta | WIII | iem | Asia/Jakarta |

Each config includes: `station`, `source`, `lat`, `lon`, `tz`, `bucket_mode`.
