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
| `client.real` | `RealTradingEngine` | Real trading engine (optional) |

**Methods**

#### `client.stream(market, retries=None) → Stream`

Create a WebSocket price stream for a market.

| Parameter | Type | Default | Description |
|---|---|---|---|
| `market` | `Market` | — | Market from `client.markets.latest()` |
| `retries` | `int \| None` | `None` | Override reconnect budget; uses client default if `None` |

#### `client.orderbook(market) → OrderBookFeed`

Create a real-time order book feed for a market.

| Parameter | Type | Default | Description |
|---|---|---|---|
| `market` | `Market` | — | Market from `client.markets.latest()` |

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

## polyalpha.RealTradingEngine

Access via `client.real`. Requires real trading credentials to initialize. Do not instantiate directly.

**Constructor** (internal — use `Client` with real trading parameters)

```python
RealTradingEngine(
    private_key: str,
    rpc_url: str,
    polymarket_api_key: str,
    config: RealTradingConfig | None = None,
    db_path: str | None = None,
)
```

**Attributes**

| Attribute | Type | Description |
|---|---|---|
| `real.balance` | `float` | Current USDC balance |
| `real.config` | `RealTradingConfig` | Current configuration |
| `real.emergency_mode` | `bool` | Emergency stop status |

**Methods**

#### `buy(market, side, amount=None, confidence=0.5, price=None, stop_loss=None, take_profit=None, confirm=True) → RealOrder`

Execute a real buy order on the CLOB.

| Parameter | Type | Default | Description |
|---|---|---|---|
| `market` | `Market` | — | Target market |
| `side` | `str` | — | `"UP"` or `"DOWN"` |
| `amount` | `float \| None` | `None` | USDC to spend (uses position sizing if None) |
| `confidence` | `float` | `0.5` | Confidence level (0-1) for position sizing |
| `price` | `float \| None` | `None` | Limit price (market order if None) |
| `stop_loss` | `float \| None` | `None` | Stop loss price trigger |
| `take_profit` | `float \| None` | `None` | Take profit price trigger |
| `confirm` | `bool` | `True` | Require manual confirmation |

Raises `InsufficientBalance`, `InsufficientAllowance`, `RiskLimitExceeded`, `OrderCancelled`.

#### `limit(market, side, price, amount=None, confidence=0.5, stop_loss=None, take_profit=None, confirm=True) → RealOrder`

Execute a real limit order on the CLOB.

| Parameter | Type | Default | Description |
|---|---|---|---|
| `market` | `Market` | — | Target market |
| `side` | `str` | — | `"UP"` or `"DOWN"` |
| `price` | `float` | — | Limit price |
| `amount` | `float \| None` | `None` | USDC to spend |
| `confidence` | `float` | `0.5` | Confidence level for position sizing |
| `stop_loss` | `float \| None` | `None` | Stop loss price trigger |
| `take_profit` | `float \| None` | `None` | Take profit price trigger |
| `confirm` | `bool` | `True` | Require manual confirmation |

#### `cancel(order_id) → None`

Cancel an open order.

| Parameter | Type | Description |
|---|---|---|
| `order_id` | `str` | Order ID to cancel |

Raises `OrderNotFound`.

#### `get_order(order_id) → RealOrder`

Get order by ID.

| Parameter | Type | Description |
|---|---|---|
| `order_id` | `str` | Order ID |

Raises `OrderNotFound`.

#### `open_orders() → list[RealOrder]`

Get all open orders.

#### `positions() → list[RealPosition]`

Get all open positions.

#### `get_position(market_id, side) → RealPosition`

Get position for a market and side.

| Parameter | Type | Description |
|---|---|---|
| `market_id` | `str` | Market ID |
| `side` | `str` | `"UP"` or `"DOWN"` |

Raises `PositionNotFound`.

#### `refresh_balance() → None`

Refresh balance from blockchain.

#### `emergency_stop(reason="Manual") → None`

Emergency stop - cancel all open orders and prevent new trades.

| Parameter | Type | Default | Description |
|---|---|---|---|
| `reason` | `str` | `"Manual"` | Reason for emergency stop |

#### `resume_trading(confirm=True) → None`

Resume trading after emergency stop.

| Parameter | Type | Default | Description |
|---|---|---|---|
| `confirm` | `bool` | `True` | Require confirmation |

---

## polyalpha.RealTradingConfig

Configuration for real trading with safety checks.

**Parameters**

| Parameter | Type | Default | Description |
|---|---|---|---|
| `private_key` | `str` | — | Private key for wallet operations |
| `rpc_url` | `str` | — | Polygon RPC URL |
| `polymarket_api_key` | `str` | — | Polymarket API key |
| `require_confirmation` | `bool` | `True` | Require manual confirmation for orders |
| `max_order_size` | `float` | `1000.0` | Maximum USDC per order |
| `max_daily_loss` | `float` | `500.0` | Stop trading if daily loss exceeds this |
| `max_position_size` | `float` | `2000.0` | Maximum position size |
| `max_open_positions` | `int` | `10` | Maximum concurrent positions |
| `position_sizing` | `str` | `"fixed"` | `"fixed"`, `"percentage"`, or `"kelly"` |
| `fixed_amount` | `float` | `10.0` | Amount for fixed strategy |
| `percentage_of_balance` | `float` | `0.05` | Percentage for percentage strategy |
| `kelly_fraction` | `float` | `0.25` | Fraction of full Kelly for Kelly strategy |
| `enable_stop_loss` | `bool` | `True` | Enable stop loss |
| `default_stop_loss_pct` | `float` | `0.20` | Default stop loss percentage |
| `enable_take_profit` | `bool` | `True` | Enable take profit |
| `default_take_profit_pct` | `float` | `0.50` | Default take profit percentage |
| `max_risk_per_trade` | `float` | `0.02` | Maximum risk per trade (as % of balance) |
| `slippage_tolerance` | `float` | `0.05` | Slippage tolerance (5%) |
| `order_timeout` | `int` | `60` | Order timeout in seconds |
| `retry_attempts` | `int` | `3` | Retry attempts for failed orders |
| `retry_delay` | `float` | `1.0` | Delay between retries (seconds) |
| `fee_mode` | `str` | `"polymarket"` | Fee calculation mode |
| `log_all_orders` | `bool` | `True` | Log all orders |
| `log_balance_updates` | `bool` | `True` | Log balance updates |

---

## polyalpha.RealOrder

A real order executed on the CLOB.

| Attribute | Type | Description |
|---|---|---|
| `id` | `str` | Order ID |
| `market_id` | `str` | Market ID |
| `slug` | `str` | Market slug |
| `side` | `str` | `"UP"` or `"DOWN"` |
| `price` | `float` | Fill price |
| `amount` | `float` | USDC spent |
| `shares` | `float` | Shares received |
| `fee` | `float` | Fee paid |
| `status` | `str` | `"pending"`, `"open"`, `"filled"`, `"partially_filled"`, `"cancelled"` |
| `is_limit` | `bool` | Whether this is a limit order |
| `created_at` | `datetime` | Order creation time |
| `filled_at` | `datetime \| None` | Fill time (if filled) |
| `tx_hash` | `str \| None` | Transaction hash |
| `stop_loss` | `float \| None` | Stop loss price |
| `take_profit` | `float \| None` | Take profit price |
| `sizing_strategy` | `str` | Position sizing strategy used |
| `confidence` | `float` | Confidence level |
| `kelly_fraction` | `float` | Kelly fraction used |

**Methods**

#### `dump() → dict`

Return order data as a dictionary.

---

## polyalpha.RealPosition

A real position held on the CLOB.

| Attribute | Type | Description |
|---|---|---|
| `market_id` | `str` | Market ID |
| `slug` | `str` | Market slug |
| `question` | `str` | Market question |
| `side` | `str` | `"UP"` or `"DOWN"` |
| `shares` | `float` | Shares held |
| `avg_price` | `float` | Average entry price |
| `current_price` | `float` | Current price |
| `cost_basis` | `float` | Total cost basis |
| `current_value` | `float` | Current value |
| `resolved` | `bool` | Whether position is resolved |
| `outcome` | `str \| None` | `"WON"` or `"LOST"` (if resolved) |
| `order_ids` | `list[str]` | Order IDs in this position |
| `stop_loss` | `float \| None` | Stop loss price |
| `take_profit` | `float \| None` | Take profit price |

**Properties**

| Property | Type | Description |
|---|---|---|
| `pnl` | `float` | Unrealized P&L |
| `pnl_pct` | `float` | P&L as percentage |

**Methods**

#### `dump() → dict`

Return position data as a dictionary.

---

## polyalpha.WalletManager

Manages wallet operations for real trading. Access via `client.real._wallet`.

**Methods**

#### `get_address() → str`

Get wallet address.

#### `get_balance() → float`

Get current USDC balance.

#### `get_allowance() → float`

Get CLOB allowance for trading.

#### `approve_clob(amount) → str`

Approve CLOB contract to spend USDC.

| Parameter | Type | Description |
|---|---|---|
| `amount` | `float` | Amount to approve |

#### `refresh_balance() → None`

Refresh balance from blockchain.

#### `wait_for_transaction(tx_hash, timeout=60) → dict`

Wait for transaction confirmation.

| Parameter | Type | Default | Description |
|---|---|---|---|
| `tx_hash` | `str` | — | Transaction hash |
| `timeout` | `int` | `60` | Timeout in seconds |

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
| `InsufficientBalance` | Balance too low to place the order |
| `InsufficientAllowance` | Insufficient CLOB allowance for trading |
| `OrderNotFound` | No order matched the given ID |
| `OrderRejected` | Order rejected by CLOB |
| `OrderTimeout` | Order timed out |
| `NetworkError` | Network connectivity error |
| `TransientError` | Transient error that can be retried |
| `PositionNotFound` | Position not found |
| `RiskLimitExceeded` | Risk management limit exceeded |
| `OrderCancelled` | Order cancelled by user or system |
| `OrderBookError` | Order book fetch or parse failed |
| `OrderBookNotFound` | No order book data available for the requested token |

```python
from polyalpha import (
    PolyalphaError,
    MarketNotFound,
    MarketClosed,
    StreamDisconnected,
    InsufficientBalance,
    InsufficientAllowance,
    OrderNotFound,
    OrderRejected,
    OrderTimeout,
    NetworkError,
    TransientError,
    PositionNotFound,
    RiskLimitExceeded,
    OrderCancelled,
    OrderBookError,
    OrderBookNotFound,
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
