# API Reference

Complete reference for every public class, method, constant, and exception in `polyalpha`.

---

## polyalpha.Client

The main entry point for the SDK.

```python
client = polyalpha.Client(
    balance=100.0,
    timeout=10,
    retries=3,
    log_level="WARNING",
)
```

**Parameters**

| Parameter | Type | Default | Description |
|---|---|---|---|
| `balance` | `float` | `100.0` | Starting paper USDC balance |
| `timeout` | `int` | `10` | HTTP request timeout in seconds |
| `retries` | `int` | `3` | HTTP retries on 5xx errors |
| `log_level` | `str` | `"WARNING"` | Python logging level |

**Attributes**

| Attribute | Type | Description |
|---|---|---|
| `client.markets` | `MarketClient` | Market discovery |
| `client.paper` | `PaperEngine` | Paper trading engine |

**Methods**

#### `client.stream(market, retries=None) → Stream`

Create a WebSocket price stream for a market.

| Parameter | Type | Default | Description |
|---|---|---|---|
| `market` | `Market` | — | Market from `client.markets.latest()` |
| `retries` | `int \| None` | `None` | Override reconnect budget; uses client default if `None` |

---

## polyalpha.MarketClient

Access via `client.markets`. Do not instantiate directly.

#### `latest(asset, timeframe="5m") → Market`

Return the active market for an asset/timeframe pair using deterministic slug generation.

| Parameter | Type | Default | Description |
|---|---|---|---|
| `asset` | `str` | — | `"BTC"`, `"ETH"`, `"SOL"`, `"XRP"`, `"DOGE"` |
| `timeframe` | `str` | `"5m"` | `"5m"`, `"15m"`, `"1h"`, `"4h"`, `"24h"` |

Raises `ValueError` for unsupported inputs; `MarketNotFound` if no active market exists.

#### `get(slug) → Market`

Fetch a market by its exact event slug.

| Parameter | Type | Description |
|---|---|---|
| `slug` | `str` | e.g. `"btc-updown-5m-1751234700"` |

Raises `MarketNotFound` if the event doesn't exist.

#### `search(query, limit=10) → list[Market]`

Search open markets by keyword.

| Parameter | Type | Default | Description |
|---|---|---|---|
| `query` | `str` | — | Free-text search query |
| `limit` | `int` | `10` | Maximum results to return |

#### `available(timeframe="5m") → list[Market]`

Return active markets for all supported assets at the given timeframe. Assets with no active market are silently skipped.

---

## polyalpha.Market

A dataclass representing a single Polymarket Up/Down event.

**Fields**

| Field | Type | Description |
|---|---|---|
| `id` | `str` | Condition/event ID |
| `question` | `str` | Human-readable market question |
| `description` | `str` | Full event description |
| `slug` | `str` | Deterministic event slug |
| `active` | `bool` | True while accepting orders |
| `closed` | `bool` | True once the window closed |
| `archived` | `bool` | True when fully settled |
| `start_time` | `str` | ISO-8601 window open time |
| `end_time` | `str` | ISO-8601 window close time |
| `volume` | `float` | Total USDC traded |
| `liquidity` | `float` | Available USDC liquidity |
| `outcomes` | `list[str]` | Always `["UP", "DOWN"]` |
| `prices` | `list[float]` | `[up_price, down_price]` |
| `tokens` | `list[str]` | `[up_token_id, down_token_id]` |
| `raw` | `dict` | Original API response (excluded from `dump()`/`json()`) |

**Properties**

| Property | Type | Description |
|---|---|---|
| `up_price` | `float` | `prices[0]` |
| `down_price` | `float` | `prices[1]` |
| `up_token` | `str` | `tokens[0]` |
| `down_token` | `str` | `tokens[1]` |
| `url` | `str` | `https://polymarket.com/event/{slug}` |
| `yes_price` | `float` | Alias for `up_price` |
| `no_price` | `float` | Alias for `down_price` |
| `yes_token` | `str` | Alias for `up_token` |
| `no_token` | `str` | Alias for `down_token` |

**Methods**

| Method | Returns | Description |
|---|---|---|
| `dump()` | `dict` | All fields as a plain dict (excludes `raw`, adds `url`) |
| `json(indent=2)` | `str` | Pretty JSON string |
| `show()` | `None` | Prints a formatted summary table to stdout |

---

## polyalpha.Stream

Access via `client.stream(market)`. Do not instantiate directly.

**Constructor** (internal — use `client.stream()`)

```python
Stream(market, retries=WS_MAX_RETRIES, retry_delay=WS_RETRY_DELAY)
```

**Attributes**

| Attribute | Type | Description |
|---|---|---|
| `stream.market` | `Market` | The market being streamed |
| `stream.up` | `float` | Latest UP mid-price |
| `stream.down` | `float` | Latest DOWN mid-price |
| `stream.retries` | `int` | Reconnect budget |
| `stream.running` | `bool` | True while background thread is alive |

**Methods**

#### `on(event) → decorator`

Register an event handler via decorator.

```python
@stream.on("price")
def handler(up: float, down: float): ...
```

#### `add_handler(event, fn) → None`

Register an event handler without decorator syntax.

#### `start(background=False) → None`

Start the WebSocket connection.

| Parameter | Type | Default | Description |
|---|---|---|---|
| `background` | `bool` | `False` | If True, runs in a daemon thread and returns immediately |

#### `stop() → None`

Signal the stream to stop and close the WebSocket cleanly.

**Events**

| Event | Handler signature | Trigger |
|---|---|---|
| `"price"` | `(up: float, down: float)` | Any mid-price change |
| `"book"` | `(data: dict)` | Full order-book snapshot received |
| `"trade"` | `(data: dict)` | Last matched trade received |
| `"connect"` | `()` | Successful connection (including reconnects) |
| `"close"` | `()` | Market resolved |
| `"error"` | `(exc: Exception)` | Unrecoverable failure |

---

## polyalpha.PaperEngine

Access via `client.paper`. Do not instantiate directly.

**Attributes**

| Attribute | Type | Description |
|---|---|---|
| `paper.balance` | `float` | Current USDC balance |
| `paper.orders` | `list[PaperOrder]` | All filled orders in order |
| `paper.positions` | `list[PaperPosition]` | All open positions |

**Methods**

#### `buy(market, side, amount) → PaperOrder`

Simulate a market buy order.

| Parameter | Type | Description |
|---|---|---|
| `market` | `Market` | Target market |
| `side` | `str` | `"UP"` or `"DOWN"` |
| `amount` | `float` | USDC to spend (fee deducted from this) |

Raises `InsufficientBalance`.

#### `sell(market, side, shares) → PaperOrder`

Simulate a market sell order.

| Parameter | Type | Description |
|---|---|---|
| `market` | `Market` | Target market |
| `side` | `str` | `"UP"` or `"DOWN"` |
| `shares` | `float` | Shares to sell |

Raises `InsufficientBalance` if you don't hold enough shares.

#### `summary() → None`

Print balance, positions with live P&L, and totals to stdout.

#### `reset() → None`

Clear all orders and positions and restore the original balance.

---

## polyalpha.PaperOrder

Returned by `paper.buy()` and `paper.sell()`.

| Attribute | Type | Description |
|---|---|---|
| `id` | `str` | UUID |
| `market_slug` | `str` | Market slug |
| `side` | `str` | `"UP"` or `"DOWN"` |
| `direction` | `str` | `"BUY"` or `"SELL"` |
| `amount_usdc` | `float` | USDC spent or received |
| `shares` | `float` | Shares filled |
| `fill_price` | `float` | Price at fill |
| `fee` | `float` | Fee charged |
| `timestamp` | `str` | ISO-8601 fill time |

---

## polyalpha.PaperPosition

| Attribute | Type | Description |
|---|---|---|
| `market_slug` | `str` | Market slug |
| `side` | `str` | `"UP"` or `"DOWN"` |
| `shares` | `float` | Current share balance |
| `avg_cost` | `float` | Average cost basis per share |
| `total_cost` | `float` | Total USDC invested |
| `realized_pnl` | `float` | Realized P&L from sells |

**Methods**

#### `unrealized_pnl(current_price) → float`

```python
pnl = position.unrealized_pnl(current_price=market.up_price)
```

---

## Constants

```python
from polyalpha import (
    ASSETS,           # ["BTC", "ETH", "SOL", "XRP", "DOGE"]
    TIMEFRAME_SECONDS,  # {"5m": 300, "15m": 900, "1h": 3600, "4h": 14400, "24h": 86400}
    GAMMA_API,        # "https://gamma-api.polymarket.com"
    CLOB_WS,          # "wss://ws-subscriptions-clob.polymarket.com/ws/market"
    TAKER_FEE_RATE,   # 0.02  (2%)
    WS_PING_INTERVAL, # 10  (seconds)
    WS_PING_TIMEOUT,  # 5   (seconds)
    WS_RETRY_DELAY,   # 3.0 (seconds base)
    WS_MAX_RETRIES,   # 10
)
```

#### `build_slug(asset, timeframe, window_end_ts) → str`

```python
from polyalpha import build_slug
slug = build_slug("BTC", "5m", 1751234700)
# → "btc-updown-5m-1751234700"
```

---

## Exceptions

All exceptions inherit from `polyalpha.PolyalphaError`.

| Exception | Raised when |
|---|---|
| `PolyalphaError` | Base class — never raised directly |
| `MarketNotFound` | No market matched the given asset/timeframe or slug |
| `MarketClosed` | Market exists but is no longer active |
| `StreamDisconnected` | WebSocket dropped and retry budget exhausted |
| `InsufficientBalance` | Paper balance too low to place the order |
| `OrderNotFound` | No paper order matched the given ID |

```python
from polyalpha import (
    PolyalphaError,
    MarketNotFound,
    MarketClosed,
    StreamDisconnected,
    InsufficientBalance,
    OrderNotFound,
)

try:
    market = client.markets.latest("BTC", "5m")
except MarketNotFound:
    ...
except MarketClosed:
    ...
except PolyalphaError as e:
    # catch-all for any SDK error
    print(e)
```
