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
| `timeframe` | `"5m"` | Market timeframe |
| `side` | `"UP"` | `"UP"` or `"DOWN"` |
| `entry_price` | `0.92` | Entry price threshold (0–1) |
| `exit_price` | `0.88` | Exit price threshold (must be < entry) |
| `window_seconds` | `35` | Trading window before market end |
| `amount` | `20.0` | USDC amount per trade |
| `max_position_size` | `None` | Maximum position exposure |
| `max_consecutive_losses` | `3` | Stop after this many consecutive losses |
| `max_trades` | `None` | Maximum total trades before stopping |
| `allowed_market_sessions` | `None` | Filter by market session (e.g., `["london", "new_york"]`) |
| `pre_window_buffer` | `5` | Seconds before window to start checking |
| `post_window_timeout` | `30` | Seconds after window close to wait for fill |
| `log_level` | `"INFO"` | Logging level |
| `log_trades` | `True` | Log trade details |
| `log_prices` | `False` | Log individual price updates |
| `use_ta` | `False` | Enable technical analysis filters |
| `ta_data_source` | `None` | TA data source (`"binance"`, `"chainlink"`, `"custom"`) |
| `ta_rsi_threshold` | `None` | Minimum RSI for entry |
| `ta_sma_period` | `None` | Minimum SMA period for entry |
| `ta_rules` | `None` | Custom TA evaluation rules |

All parameters are validated on initialization. Invalid values raise `ValueError` with descriptive messages.

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
