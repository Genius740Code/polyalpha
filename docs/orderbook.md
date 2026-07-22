# Order Book

The `polyalpha.orderbook` module provides real-time and historical access to Polymarket's Central Limit Order Book (CLOB), strategy-building abstractions, risk management, and backtesting.

---

## Module Overview

| Sub-module | File | Purpose |
|-----------|------|---------|
| Models | `models.py` | Dataclasses and enums for book levels, orders, trades, snapshots, positions, portfolios |
| CLOB Client | `clob.py` | REST client for Polymarket CLOB endpoints |
| Feed | `feed.py` | Live order book via REST snapshots + WebSocket |
| Manager | `manager.py` | In-memory book state management with subscriber notifications |
| Strategy | `strategy.py` | Abstract strategy base + 3 concrete implementations |
| Risk | `risk.py` | Pre-trade risk validation |
| Backtest | `backtest.py` | Historical snapshot replay against a strategy |
| Analytics | `analytics.py` | Pure functions for depth, fill estimation, liquidity, S/R levels |

All public symbols are re-exported from `polyalpha.orderbook` and accessible as `polyalpha.orderbook.<name>`.

---

## Models (`polyalpha.orderbook.models`)

### Enums

**`BookSide`**
- `BUY = "buy"`, `SELL = "sell"`

**`OrderStatus`**
- `PENDING`, `FILLED`, `PARTIALLY_FILLED`, `CANCELLED`, `REJECTED`

**`OrderType`**
- `LIMIT`, `MARKET`, `STOP_LIMIT`, `STOP_MARKET`

### Dataclasses

**`BookLevel`** (frozen)
| Field | Type | Description |
|-------|------|-------------|
| `price` | `float` | Price at this level |
| `size` | `float` | Available size |
- `notional -> float`: `price * size`

**`Order`**
| Field | Type | Default |
|-------|------|---------|
| `id` | `str` | required |
| `user_id` | `str` | required |
| `side` | `BookSide` | required |
| `order_type` | `OrderType` | required |
| `price` | `float` | required |
| `quantity` | `float` | required |
| `filled_quantity` | `float` | `0.0` |
| `status` | `OrderStatus` | `PENDING` |
| `timestamp` | `datetime \| None` | `None` |
| `stop_price` | `float \| None` | `None` |
| `time_in_force` | `str` | `"GTC"` |

Properties: `remaining_quantity`, `is_filled`, `fill_percentage`

**`Trade`** (frozen)
| Field | Type |
|-------|------|
| `id` | `str` |
| `order_id` | `str` |
| `price` | `float` |
| `quantity` | `float` |
| `timestamp` | `datetime` |
| `taker_order_id` | `str` |
| `maker_order_id` | `str` |
| `token_id` | `str` |
| `side` | `BookSide \| None` |

**`FillEstimate`** (frozen)
| Field | Type |
|-------|------|
| `side` | `BookSide` |
| `requested_size` | `float` |
| `filled_size` | `float` |
| `average_price` | `float` |
| `total_cost` | `float` |
| `levels_used` | `tuple[tuple[float, float], ...]` |
| `fully_filled` | `bool` |

Property: `slippage -> float`: absolute difference between average price and top level

**`OrderBookSnapshot`**
| Field | Type |
|-------|------|
| `token_id` | `str` |
| `market_id` | `str` |
| `bids` | `tuple[BookLevel, ...]` |
| `asks` | `tuple[BookLevel, ...]` |
| `timestamp` | `datetime` |
| `tick_size` | `float` (default `0.01`) |
| `min_order_size` | `float` (default `1.0`) |
| `neg_risk` | `bool` |
| `hash` | `str` |
| `sequence` | `int` |
| `last_trade_price` | `float` |
| `last_trade_size` | `float` |

Class methods:
- `from_clob_response(data: dict) -> OrderBookSnapshot`: Parse REST JSON response (sorts bids desc, asks asc)
- `from_ws_message(msg: dict, sequence: int = 0) -> OrderBookSnapshot`: Parse WebSocket message

Properties: `best_bid`, `best_ask`, `best_bid_size`, `best_ask_size`, `spread`, `spread_percentage`, `mid_price`, `total_bid_volume`, `total_ask_volume`, `order_book_imbalance`

Methods:
- `get_depth(levels: int = 10) -> dict`: Top N levels with spread, mid, imbalance
- `dump() -> dict`: Full depth snapshot

**`MarketOrderBook`**
| Field | Type |
|-------|------|
| `market_slug` | `str` |
| `up` | `OrderBookSnapshot \| None` |
| `down` | `OrderBookSnapshot \| None` |
| `trades` | `list[Trade]` |

Properties: `up_mid`, `down_mid`
Method: `get_depth(levels: int = 10) -> dict`

**`Position`**
| Field | Type |
|-------|------|
| `symbol` | `str` |
| `quantity` | `float` |
| `average_price` | `float` |
| `unrealized_pnl` | `float` |
| `realized_pnl` | `float` |

Properties: `market_value`, `is_long`, `is_short`

**`Portfolio`**
| Field | Type |
|-------|------|
| `user_id` | `str` |
| `positions` | `dict[str, Position]` |
| `cash_balance` | `float` |
| `total_value` | `float` |

Property: `total_pnl`
Method: `get_position(symbol: str) -> Position`

---

## CLOB Client (`ClobBookClient`)

REST client for Polymarket CLOB endpoints.

```python
from polyalpha.orderbook import ClobBookClient

client = ClobBookClient(timeout=10, retries=3, rate_limit=None, cache_ttl=2.0)
```

Constructor params:
- `timeout`: HTTP timeout in seconds (default `10`)
- `retries`: Number of retries on failure (default `3`)
- `rate_limit`: Max requests per second, or `None` for unlimited
- `cache_ttl`: TTL for cached snapshots in seconds (default `2.0`)

Supports context manager: `with ClobBookClient() as client:`

| Method | Description |
|--------|-------------|
| `get_book(token_id, *, use_cache=True) -> OrderBookSnapshot` | Fetch order book for a token |
| `get_books(token_ids) -> dict[str, OrderBookSnapshot]` | Batch fetch (up to 500 tokens) |
| `get_price(token_id, side="BUY") -> float` | Best price for side |
| `get_midpoint(token_id) -> float` | Midpoint price |
| `get_spread(token_id) -> float` | Bid-ask spread |
| `get_last_trade_price(token_id) -> dict` | Last trade price data |
| `clear_cache()` | Clear cached snapshots |

---

## Order Book Feed (`OrderBookFeed`)

Combines REST snapshots and WebSocket streaming for live book management.

```python
from polyalpha import Client

client = Client()
market = client.markets.latest("BTC", "5m")
feed = client.orderbook(market)
# Or: feed = OrderBookFeed(market, clob=..., manager=...)
```

| Property | Returns |
|----------|---------|
| `manager` | `OrderBookManager` |
| `up` | `OrderBookSnapshot \| None` |
| `down` | `OrderBookSnapshot \| None` |
| `book` | `MarketOrderBook` |

| Method | Description |
|--------|-------------|
| `refresh() -> MarketOrderBook` | Fetch REST snapshots and emit `"book"` + `"update"` |
| `get_book(side="UP") -> OrderBookSnapshot \| None` | Get snapshot for UP or DOWN side |
| `on(event) -> decorator` | Register a handler decorator for events |
| `add_handler(event, fn)` | Register a handler programmatically |
| `attach_stream(stream)` | Wire WebSocket events to book updates |
| `close()` | Clean up CLOB client if owned |

Events: `"book"`, `"trade"`, `"update"`, `"connect"`

```python
# Full example
stream = client.stream(market)
feed.attach_stream(stream)

@feed.on("update")
def on_update(book: MarketOrderBook):
    print(f"UP mid: {book.up_mid:.4f}, DOWN mid: {book.down_mid:.4f}")

stream.start(background=True)
```

---

## Order Book Manager (`OrderBookManager`)

In-memory book state with subscriber notifications for live updates.

| Method | Description |
|--------|-------------|
| `subscribe(callback)` | Subscribe to book events (callback receives event_type, data) |
| `unsubscribe(callback)` | Remove subscription |
| `apply_snapshot(snapshot)` | Replace book for a token, notify `"book_update"` |
| `apply_ws_book(msg)` | Parse WS message and apply snapshot |
| `apply_price_change(msg)` | Incremental price change from WS |
| `record_trade(msg) -> Trade` | Record a trade from WS, notify `"trade"` |
| `get_book(token_id) -> OrderBookSnapshot \| None` | O(1) lookup by token |
| `get_market_book(slug, up_token, down_token) -> MarketOrderBook` | Build combined market book |
| `get_order_book_snapshot(token_id) -> OrderBookSnapshot` | Return book or zero-filled empty |

Properties: `sequence -> int`, `trades -> list[Trade]`

### `SimulatedOrderBookManager(OrderBookManager)`

Extends manager with a local matching engine.

| Method | Description |
|--------|-------------|
| `add_order(order) -> bool` | Add order (rejects duplicate IDs) |
| `remove_order(order_id) -> bool` | Cancel an order |
| `match_orders() -> list[Trade]` | Price-time priority matching |

---

## Strategies (`polyalpha.orderbook.strategy`)

### Base: `Strategy` (ABC)

```python
from polyalpha.orderbook import Strategy

class MyStrategy(Strategy):
    async def on_order_book_update(self, book: MarketOrderBook) -> list[Order]: ...
    async def on_trade(self, trade: Trade) -> None: ...
    async def generate_signals(self, book: MarketOrderBook) -> list[Order]: ...
```

| Field | Description |
|-------|-------------|
| `name` | Strategy identifier |
| `parameters` | Arbitrary config dict |
| `positions` | Current position dict |
| `performance_metrics` | PnL tracking |
| `is_active` | Whether strategy is running |

Methods: `start()`, `stop()`, `update_performance(pnl, trade_count)`

### `ImbalanceStrategy`

Trades when order book imbalance exceeds a threshold.

| Param | Default | Description |
|-------|---------|-------------|
| `side` | `"UP"` | Target side |
| `threshold` | `0.2` | Imbalance threshold |
| `quantity` | `1.0` | Order size |

Generates BUY limit at best bid when imbalance > threshold, SELL limit at best ask when imbalance < -threshold.

### `SpreadStrategy`

Quotes both sides around mid price with inventory skew.

| Param | Default | Description |
|-------|---------|-------------|
| `side` | `"UP"` | Target side |
| `spread` | `0.02` | Half-spread from mid |
| `quantity` | `1.0` | Order size |
| `inventory` | `0.0` | Current inventory (updated on trades) |

### `MomentumStrategy`

Trades on price momentum over a lookback window.

| Param | Default | Description |
|-------|---------|-------------|
| `side` | `"UP"` | Target side |
| `lookback` | `20` | Number of periods |
| `threshold` | `0.02` | Momentum threshold |

Generates MARKET orders when momentum exceeds threshold.

---

## Risk Manager (`RiskManager`)

Pre-trade risk validation.

```python
from polyalpha.orderbook import RiskManager

risk = RiskManager(max_position_size=1000.0, max_daily_loss=0.05, max_order_size=100.0)
```

| Method | Description |
|--------|-------------|
| `validate_order(order, portfolio) -> (bool, str)` | Check position size, daily loss, cash balance |
| `check_position_limit(symbol, quantity) -> bool` | Check position size limit |
| `update_daily_pnl(pnl)` | Accumulate daily P&L |
| `reset_daily_limits()` | Reset daily P&L and trade count |

Validation checks:
1. `order.quantity <= max_order_size`
2. `abs(current_position + quantity) <= max_position_size`
3. `daily_pnl >= -max_daily_loss * portfolio.total_value`
4. BUY orders: `cash_balance >= order.quantity * order.price`

---

## Backtest Engine (`BacktestEngine`)

Replay historical order book snapshots against a strategy.

```python
from polyalpha.orderbook import BacktestEngine, ImbalanceStrategy

strategy = ImbalanceStrategy(threshold=0.3, quantity=10.0)
engine = BacktestEngine(strategy, initial_capital=100_000.0)
```

| Method | Description |
|--------|-------------|
| `load_snapshots(snapshots)` | Load historical snapshots |
| `run_backtest(start_date=None, end_date=None) -> dict` | Run backtest over date range |

Returns report dict with:
- `total_return`, `sharpe_ratio` (annualized, 252 days), `max_drawdown` (fraction), `total_trades`, `final_equity`, `equity_curve` (list)

Market orders use `estimate_fill` for average price; limit orders execute at `order.price`.

---

## Analytics Functions (`polyalpha.orderbook.analytics`)

Pure functions operating on `OrderBookSnapshot`:

| Function | Returns |
|----------|---------|
| `cumulative_depth(levels, side)` | `list[dict]` with cumulative size and notional per level |
| `estimate_fill(book, side, size)` | `FillEstimate` — walk book to estimate fill |
| `estimate_market_buy_usdc(book, usdc_amount)` | `FillEstimate` — shares received for USDC spend |
| `liquidity_at_price(book, price, side, tolerance=None)` | `float` — total size near price |
| `support_resistance_levels(book, levels=5)` | `{"support": [...], "resistance": [...]}` |
| `volatility_from_spread(book)` | `float` — spread / mid_price |
| `book_summary(book)` | `dict` — compact summary of key metrics |

```python
from polyalpha.orderbook import estimate_fill, BookSide

fill = estimate_fill(snapshot, BookSide.BUY, 100.0)
print(f"Avg price: {fill.average_price:.4f}, Slippage: {fill.slippage:.4f}")
```

---

## Quick Reference

```
polyalpha.orderbook
├── Enums: BookSide, OrderStatus, OrderType
├── Dataclasses: BookLevel, Order, Trade, FillEstimate,
│               OrderBookSnapshot, MarketOrderBook, Position, Portfolio
├── ClobBookClient — REST CLOB API
├── OrderBookFeed — live book (REST + WebSocket)
├── OrderBookManager — in-memory book state
├── SimulatedOrderBookManager — local matching engine
├── Strategy (ABC), ImbalanceStrategy, SpreadStrategy, MomentumStrategy
├── RiskManager — pre-trade validation
├── BacktestEngine — historical replay
└── analytics — cumulative_depth, estimate_fill, estimate_market_buy_usdc,
               liquidity_at_price, support_resistance_levels,
               volatility_from_spread, book_summary
```
