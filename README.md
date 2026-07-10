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

# Keyword search
markets = client.markets.search("ETH 15m")   # → list[Market]

# All active markets at a timeframe
markets = client.markets.available("5m")     # → list[Market]
```

**Supported assets:** BTC, ETH, SOL, XRP, DOGE  
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

## Auto-Redeem

Automatically redeem resolved positions based on configurable triggers (time intervals, market count, or value thresholds).

```python
import polyalpha
from polyalpha import AutoRedeemConfig

client = polyalpha.Client(balance=1000.0)

# Simple daily auto-redeem
config = AutoRedeemConfig(
    time_interval="1d",  # Redeem daily
    min_value_usd=100.0,  # Only when value >= $100
)

client.paper.set_auto_redeem_config(config)
client.paper.auto_redeem.start_scheduler()
```

### Configuration Options

```python
AutoRedeemConfig(
    # Trigger modes
    trigger_on_time=True,   # Enable time-based triggers
    trigger_on_count=True,  # Enable count-based triggers
    trigger_on_value=False, # Enable value-based triggers
    
    # Time-based
    time_interval="1d",    # "1h", "6h", "1d", "1w"
    redeem_at_time=None,   # Specific time "14:00" UTC
    
    # Count-based
    min_markets=10,         # Redeem after N markets
    max_markets=100,        # Force redeem at N (safety)
    
    # Value-based
    min_value_usd=100.0,    # Redeem when value >= $100
    max_value_usd=10000.0, # Force redeem at $10k (safety)
    
    # Safety
    require_confirmation=False,  # Confirm before redeeming
    dry_run=False,               # Simulate without executing
    only_winning=False,          # Only redeem winning positions
    min_age_hours=1,             # Wait N hours after resolution
)
```

### Manual Redemption

```python
# Check for redeemable positions
positions = client.paper.auto_redeem.check_positions()
print(f"Found {len(positions)} positions to redeem")

# Manually redeem
result = client.paper.auto_redeem.redeem(positions)
print(f"Redeemed {result.redeemed_count} positions")

# View history
history = client.paper.auto_redeem.get_redeem_history()
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
python examples/auto_redeem.py
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
