# Getting Started with polyalpha

`polyalpha` is a Python SDK for Polymarket's Up/Down prediction markets. It lets you discover live markets, stream real-time prices via WebSocket, and simulate paper trades — all through a single `Client` object.

---

## Installation

```bash
pip install polyalpha
```

For live price streaming, also install the WebSocket client:

```bash
pip install polyalpha websocket-client
```

---

## Your first script

```python
import polyalpha

# Create a client with a $500 paper balance
client = polyalpha.Client(balance=500.0)

# Find the current BTC 5-minute market
market = client.markets.latest("BTC", "5m")
market.show()  # prints a summary table

# Stream live prices
stream = client.stream(market)

@stream.on("price")
def on_price(up: float, down: float):
    print(f"UP={up:.4f}  DOWN={down:.4f}")

stream.start()  # blocks until the market closes
```

---

## The Client

`polyalpha.Client` is the single entry point for everything.

```python
from polyalpha.trading.paper import PaperConfig

# Optional: configure paper trading with risk management
config = PaperConfig(
    max_daily_loss=500.0,         # Stop trading if daily loss exceeds $500
    max_trades_per_day=100,       # Maximum 100 trades per day
    max_order_size=1000.0,        # Maximum $1000 per order
    max_position_size=2000.0,     # Maximum $2000 position per market
    max_open_positions=10,        # Maximum 10 concurrent positions
    max_risk_per_trade=0.02,      # Maximum 2% of balance per trade
)

client = polyalpha.Client(
    balance=100.0,     # starting paper USDC balance (default 100)
    paper_config=config,  # optional paper trading configuration
    timeout=10,        # HTTP timeout in seconds (default 10)
    retries=3,         # retries on 5xx errors (default 3)
    log_level="INFO",  # "DEBUG" | "INFO" | "WARNING" | "ERROR"
)
```

| Attribute | Type | Description |
|---|---|---|
| `client.markets` | `MarketClient` | Discover and fetch markets |
| `client.paper` | `PaperEngine` | Place and track paper trades |

```python
# Method on Client
stream = client.stream(market)          # create a WebSocket stream
stream = client.stream(market, retries=5)  # override reconnect budget
```

---

## Key concepts

**Market** — a single Polymarket Up/Down event covering one asset over one time window (5 minutes, 1 hour, etc.). Each market has two sides: `UP` and `DOWN`. Their prices always sum to approximately 1.0 USDC.

**Token** — each side of a market is backed by a CLOB token ID. The stream subscribes using these IDs.

**Slug** — a deterministic string that identifies every market, e.g. `btc-updown-5m-1751234700`. The number is the Unix timestamp of the window's end time.

**Paper trading** — all orders are simulated locally. No wallet or private key is needed.

---

## Supported assets and timeframes

```python
polyalpha.ASSETS      # ["BTC", "ETH", "SOL", "XRP", "DOGE"]

polyalpha.TIMEFRAME_SECONDS  # {"5m": 300, "15m": 900, "1h": 3600, "4h": 14400, "24h": 86400}
```

---

## Logging

Pass `log_level` to the `Client` constructor to control verbosity. The SDK uses Python's standard `logging` module under the namespace `polyalpha.*`.

```python
client = polyalpha.Client(log_level="DEBUG")  # very verbose — good for debugging streams
client = polyalpha.Client(log_level="INFO")   # connection events and warnings
client = polyalpha.Client(log_level="WARNING")  # default — only problems
```

---

## Error handling

All SDK exceptions inherit from `polyalpha.PolyalphaError`. See [api-reference.md](./api-reference.md) for the full list.

```python
import polyalpha
from polyalpha import MarketNotFound, MarketClosed

client = polyalpha.Client()

try:
    market = client.markets.latest("BTC", "5m")
except MarketNotFound:
    print("No active market right now — try again in a moment")
except MarketClosed:
    print("That window just closed")
```

---

## Next steps

- [markets.md](./markets.md) — finding and inspecting markets
- [streaming.md](./streaming.md) — live WebSocket price feeds
- [paper-trading.md](./paper-trading.md) — simulating orders and tracking P&L
- [sniper.md](./sniper.md) — automated trading bot
- [market-analysis.md](./market-analysis.md) — technical analysis and signals
- [api-reference.md](./api-reference.md) — complete class and method reference

## Weather bot configuration

For weather trading bots, pre-configured city templates are available:

```python
from polyalpha.bots import CITIES, print_config, list_configs

# List available cities
print(list_configs())

# Use a configuration
config = CITIES["Seoul"]

# Print for copy-paste
print_config("Seoul")
```

See the README for the full list of available cities and configuration fields.
