# polyalpha — Feature Plan

Python SDK for Polymarket. Designed to make bot development fast.

> **Scope:** Paper trading only. Live order execution (CLOB signing, wallet, real fills) is out of scope for now and planned for a future release.

---

## Goals

- One-liner to get the latest BTC 5m market
- Real-time price streaming via WebSocket
- Simulate orders in memory with realistic fill logic
- Track P&L across sessions
- Clean, typed, bot-friendly API

---

## Package Structure

```
polyalpha/
├── __init__.py
├── client.py          # Main Client entry point
├── market.py          # Market dataclass
├── stream.py          # WebSocket price streaming
├── paper.py           # Paper trading engine (orders, positions, P&L)
├── errors.py          # Typed exceptions
└── constants.py       # Endpoints, slugs, known assets
```

> `order.py` and `wallet.py` are deferred — they require L2 signing and live CLOB access. Planned for a future live-trading release.

---

## Feature Roadmap

### Phase 1 — Data (current)

**`client.markets.latest(asset, timeframe)`**

Resolves the active market slug from Polymarket's Gamma API, handles the unix-timestamp slug pattern, returns a `Market` object.

```python
client = polyalpha.Client()
market = client.markets.latest("BTC", "5m")

market.id           # condition ID
market.slug         # btc-updown-5m-1234567890
market.question     # "Will BTC be higher in 5 minutes?"
market.end_time     # ISO timestamp
market.volume       # float
market.liquidity    # float
market.prices       # [0.55, 0.45]  → [YES, NO]
market.outcomes     # ["YES", "NO"]
market.tokens       # [yes_token_id, no_token_id]
market.url          # https://polymarket.com/event/...
market.active       # bool
market.closed       # bool
```

**`client.markets.search(query)`**

Fuzzy search across open markets.

```python
markets = client.markets.search("ETH 5m")
# returns list[Market]
```

**`client.markets.get(slug)`**

Direct lookup by slug.

```python
market = client.markets.get("btc-updown-5m-1751234000")
```

---

### Phase 2 — Streaming

**`stream.py`** — wraps `wss://ws-subscriptions-clob.polymarket.com/ws/market`

```python
stream = client.stream(market)

@stream.on("price")
def on_price(yes: float, no: float):
    print(f"YES={yes:.2f}  NO={no:.2f}")

@stream.on("close")
def on_close():
    print("Market closed")

stream.start()              # blocking
stream.start(background=True)
```

Events emitted:

| Event | Payload |
|-------|---------|
| `price` | `(yes: float, no: float)` |
| `book` | raw order book dict |
| `trade` | last trade dict |
| `close` | none |
| `error` | exception |

---

### Phase 3 — Paper Trading

**`paper.py`** — simulated order engine, no signing, no real money

All order calls go through `client.paper`. Fills are simulated at the current streamed price. Taker fee (2%) is applied to simulate real costs. Positions and P&L are tracked in memory for the session.

```python
client = polyalpha.Client()

# Buy YES — fills immediately at current price
order = client.paper.buy(
    market=market,
    side="YES",
    amount=10.0,        # USDC
)

# Limit order — fills when price crosses threshold
order = client.paper.limit(
    market=market,
    side="YES",
    price=0.92,
    amount=25.0,
)

# Cancel a pending limit
client.paper.cancel(order.id)

# View open orders
client.paper.open()

# View all positions
client.paper.positions()
```

**`PaperOrder` object:**

```python
order.id
order.side          # "YES" / "NO"
order.price         # fill price (or limit price if pending)
order.amount        # USDC in
order.shares        # shares received after fee
order.fee           # USDC fee paid (2% taker sim)
order.status        # "open" / "filled" / "cancelled"
order.filled_at     # datetime or None
```

**`PaperPosition` object:**

```python
pos.market          # Market
pos.side            # "YES" / "NO"
pos.shares          # float
pos.avg_price       # float
pos.current_price   # float (live from stream)
pos.pnl             # float  (unrealised until resolved)
pos.pnl_pct         # float
pos.resolved        # bool
pos.outcome         # "WON" / "LOST" / None
```

**Balance tracking:**

```python
client.paper.balance        # starting USDC remaining
client.paper.set_balance(100.0)   # reset/set starting bankroll
```

---

### Phase 4 — Bot Utilities

**Sniper** — enter when price crosses threshold in final window, auto-loops to next market:

```python
from polyalpha.bots import Sniper

sniper = Sniper(
    client=client,
    asset="BTC",
    timeframe="5m",
    side="YES",
    entry_price=0.92,       # enter at >= 0.92
    exit_price=0.88,        # eject (cancel limit) at <= 0.88
    window_seconds=35,      # only fire in final 35s
    amount=20.0,
)

sniper.run()    # blocking loop, auto-finds next market after resolution
```

**P&L Tracker:**

```python
from polyalpha.bots import Tracker

tracker = Tracker(client)
tracker.summary()

# ┌─────────────┬───────┬──────────┬──────────┐
# │ market      │ side  │ result   │ pnl      │
# ├─────────────┼───────┼──────────┼──────────┤
# │ BTC 5m      │ YES   │ WON      │ +$4.20   │
# │ BTC 5m      │ YES   │ LOST     │ -$10.00  │
# └─────────────┴───────┴──────────┴──────────┘
# Net: -$5.80  |  Win rate: 50%  |  Trades: 2
```

---

## Error Handling

All errors are typed:

```python
from polyalpha.errors import (
    MarketNotFound,
    MarketClosed,
    InsufficientBalance,    # paper balance check
    OrderNotFound,
    StreamDisconnected,
)
```

> `AuthError` and `OrderRejected` are deferred to the live trading release.

---

## Config

```python
client = polyalpha.Client(
    balance=100.0,      # starting paper balance (default: 100 USDC)
    timeout=10,         # HTTP timeout seconds
    retries=3,          # auto-retry on 5xx
    log_level="INFO",   # logging verbosity
)
```

No API key or private key needed — paper only.

---

## Dependencies

```
httpx          # HTTP client
websockets     # WS streaming
```

> `eth_account` removed — not needed until live trading.

---

## Deferred to Live Trading Release

These are fully designed but intentionally out of scope until paper mode is solid:

| Feature | Reason deferred |
|---------|----------------|
| `order.py` — real CLOB buys/sells | requires L2 ECDSA signing |
| `wallet.py` — balance, on-chain positions | requires Polygon RPC + private key |
| `AuthError`, `OrderRejected` exceptions | only relevant for live fills |
| `eth_account` dependency | only needed for signing |
| `POLYMARKET_KEY` env var | no key needed for paper |

---

## Known Issues in Current Code

| Issue | Fix |
|-------|-----|
| `raw_data` field name leaks into `dump()` output as `raw_data` not `raw` | rename field to `raw` or override `dump()` to alias |
| `print()` shadows Python builtin | rename to `show()` or `display()` |
| No real API call in `MarketClient.latest()` | implement Gamma API fetch with slug resolution |
| Token IDs are placeholder strings | pull real condition IDs from Gamma response |
| No error handling anywhere | add typed exceptions + HTTP retry |