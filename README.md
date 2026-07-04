# polyalpha

Python SDK for Polymarket — market discovery, real-time price streaming, and paper trading.

```bash
pip install polyalpha
```

---

## Quick start

```python
import polyalpha

client = polyalpha.Client()

# Fetch the active BTC 5-minute market
market = client.markets.latest("BTC", "5m")
market.show()
```

---

## Market discovery

```python
client = polyalpha.Client()

# Latest market for any asset / timeframe
market = client.markets.latest("BTC",  "5m")
market = client.markets.latest("ETH",  "15m")
market = client.markets.latest("SOL",  "1h")

# Direct slug lookup
market = client.markets.get("btc-updown-5m-1751234700")

# Latest tweet market (e.g. Elon Musk, White House, Zelensky)
market = client.markets.latest_tweet("elon-musk", "7d")

# Keyword search
markets = client.markets.search("ETH 15m")   # → list[Market]

# All active markets at a timeframe
markets = client.markets.available("5m")     # → list[Market]
```

**Supported assets:** BTC, ETH, SOL, XRP, DOGE, HYPE, BNB
**Supported timeframes:** 5m, 15m, 1h, 4h, 24h

### Market object

```python
market.id           # Gamma condition / event ID
market.slug         # "btc-updown-5m-1751234700"
market.question     # "Will BTC be higher in 5 minutes?"
market.end_time     # ISO-8601 window close time
market.volume       # float (USDC)
market.liquidity    # float (USDC)
market.up_price     # float — current UP mid-price
market.down_price   # float — current DOWN mid-price
market.up_token     # CLOB token ID for the UP leg
market.down_token   # CLOB token ID for the DOWN leg
market.url          # https://polymarket.com/event/…
market.active       # bool
market.closed       # bool

market.show()       # print formatted summary
market.dump()       # → dict  (raw excluded)
market.json()       # → JSON string
```

---

## Price streaming

```python
stream = client.stream(market)

@stream.on("price")
def on_price(up: float, down: float):
    print(f"UP={up:.4f}  DOWN={down:.4f}")

@stream.on("book")
def on_book(data: dict):
    print(data["bids"][0], data["asks"][0])

@stream.on("trade")
def on_trade(data: dict):
    print(data["price"], data["size"])

@stream.on("close")
def on_close():
    print("Market resolved")

@stream.on("error")
def on_error(exc: Exception):
    print(f"Error: {exc}")

@stream.on("connect")
def on_connect():
    print("Connected")

stream.start()                  # blocking
stream.start(background=True)   # daemon thread
stream.stop()                   # clean shutdown
```

The stream auto-reconnects on drops using exponential back-off.
A text `PING` keepalive is sent every 10 seconds to prevent silent server-side disconnects.

Latest prices are always available without a handler:

```python
print(stream.up, stream.down)
```

---

## Paper trading

```python
client = polyalpha.Client(balance=500.0)

# Market fill — executes immediately at the current price
order = client.paper.buy(market, side="UP", amount=10.0)

# Limit order — queued until the streamed price crosses the threshold
order = client.paper.limit(market, side="UP", price=0.92, amount=25.0)

# Cancel a pending limit and refund the reserved balance
client.paper.cancel(order.id)

# Inspect
client.paper.open()             # → list[PaperOrder]  (pending limits)
client.paper.orders()           # → list[PaperOrder]  (all orders)
client.paper.positions()        # → list[PaperPosition]  (live)
client.paper.all_positions()    # → list[PaperPosition]  (all, incl. resolved)
client.paper.balance            # float

# Wire a stream for auto-fill and live P&L updates
stream = client.stream(market)
client.paper.attach_stream(stream, market)
stream.start(background=True)

# Resolve after market settles
client.paper.resolve(market, outcome="UP")

# Print P&L table
client.paper.summary()
```

### Advanced order management

The paper trading engine supports advanced order types for professional risk management:

**Stop-loss & Take-profit:**

```python
# Buy with stop-loss and/or take-profit
order = client.paper.buy_with_tp_sl(
    market, 
    side="UP", 
    amount=100.0,
    stop_loss=0.45,      # Auto-sell if price drops to 0.45
    take_profit=0.55,    # Auto-sell if price rises to 0.55
)

# Set trailing stop-loss (moves with favorable price movement)
order = client.paper.buy_with_tp_sl(
    market, 
    side="UP", 
    amount=100.0,
    trail_sl=0.05,       # 5% trailing stop-loss
)

# Set trailing take-profit (allows more profit potential)
order = client.paper.buy_with_tp_sl(
    market, 
    side="UP", 
    amount=100.0,
    trail_tp=0.10,       # 10% trailing take-profit
)

# Add trailing SL to existing order
order = client.paper.buy(market, side="UP", amount=100.0)
client.paper.set_trailing_sl(order.id, 0.05)
client.paper.set_trailing_tp(order.id, 0.10)
```

**One-Cancels-Other (OCO) orders:**

```python
# Place SL and TP where one cancels the other
main_order, oco_order = client.paper.oco_order(
    market, 
    side="UP", 
    amount=100.0,
    stop_loss=0.45,
    take_profit=0.55,
)
# When SL triggers, TP is automatically cancelled (and vice versa)
```

**Selling/closing positions:**

```python
# Sell full position
sell_order = client.paper.sell_position(market, side="UP")

# Sell partial position
sell_order = client.paper.sell_position(market, side="UP", amount=50.0)
```

**Automatic TP/SL triggering:**

When a stream is attached, TP/SL orders are automatically checked on every price update:

```python
stream = client.stream(market)
client.paper.attach_stream(stream, market)
stream.start(background=True)
# TP/SL will trigger automatically when price crosses thresholds
```

### PaperOrder

```python
order.id          # UUID string
order.side        # "UP" | "DOWN"
order.price       # fill price (or limit threshold if still open)
order.amount      # USDC spent
order.shares      # shares received after 2% taker fee
order.fee         # USDC fee paid
order.status      # "open" | "filled" | "cancelled"
order.is_limit    # bool
order.filled_at   # datetime (UTC) or None

# Advanced order fields
order.stop_loss          # SL price trigger (optional)
order.take_profit        # TP price trigger (optional)
order.trail_sl           # Trailing SL distance as percentage (optional)
order.trail_tp           # Trailing TP distance as percentage (optional)
order.trail_sl_price     # Current trailing SL price (optional)
order.trail_tp_price     # Current trailing TP price (optional)
order.oco_order_id       # OCO linked order ID (optional)
order.tp_sl_triggered_by # Which order triggered: "tp" | "sl" | None

order.dump()      # → dict
```

### PaperPosition

```python
pos.side           # "UP" | "DOWN"
pos.shares         # float
pos.avg_price      # volume-weighted average entry price
pos.current_price  # live price (updated from stream)
pos.cost_basis     # shares × avg_price
pos.current_value  # shares × current_price (or 0/shares if resolved)
pos.pnl            # current_value − cost_basis
pos.pnl_pct        # pnl / cost_basis × 100
pos.resolved       # bool
pos.outcome        # "WON" | "LOST" | None
pos.dump()         # → dict
```

---

## Configuration

```python
client = polyalpha.Client(
    balance   = 100.0,      # paper USDC balance
    timeout   = 10,         # HTTP timeout (seconds)
    retries   = 3,          # retries on 5xx errors
    log_level = "WARNING",  # "DEBUG" | "INFO" | "WARNING" | "ERROR"
    rate_limit = None,      # max API requests per second (default: unlimited)
)
```

**Rate limiting:** Optional token-bucket rate limiter to prevent API abuse. Set to an integer (e.g., `10` for 10 requests/second) or `None` for unlimited.

---

## Error handling

```python
from polyalpha import (
    MarketNotFound,       # no active market for that slug / asset+timeframe
    MarketClosed,         # market exists but window has closed
    StreamDisconnected,   # WS dropped and retry budget exhausted
    InsufficientBalance,  # paper balance too low
    OrderNotFound,        # cancel/lookup of unknown order ID
)

try:
    market = client.markets.latest("BTC", "5m")
except polyalpha.MarketNotFound as exc:
    print(f"Not found: {exc}")
```

---

## Examples

```bash
python examples/market.py --asset BTC --timeframe 5m
python examples/market.py --rate-limit 10
python examples/stream.py --asset ETH --timeframe 15m --log DEBUG
python examples/paper.py  --side UP   --amount 25 --limit 0.92
python examples/advanced_orders.py  # Demonstrates TP/SL, trailing stops, OCO orders
```

---

## Project layout

```
src/polyalpha/
├── __init__.py          Public API surface
├── client.py            Client — main entry point
├── markets.py           MarketClient — Gamma API + slug resolution
├── stream.py            Stream — WebSocket price feed
├── core/
│   ├── __init__.py
│   ├── constants.py     Endpoints, timeframes, assets, tuning knobs
│   ├── errors.py        Typed exceptions
│   └── market.py        Market dataclass
└── trading/
    ├── __init__.py
    └── paper.py         PaperEngine, PaperOrder, PaperPosition
examples/
├── market.py
├── stream.py
└── paper.py
```
