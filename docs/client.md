# Client

The `Client` is the single entry point for all SDK features.

```python
import polyalpha
client = polyalpha.Client()
```

## Constructor Parameters

| Parameter | Type | Default | Description |
|-----------|------|---------|-------------|
| `balance` | `float` | `100.0` | Starting paper USDC balance |
| `timeout` | `int` | `10` | HTTP request timeout in seconds |
| `retries` | `int` | `3` | Number of HTTP retries on 5xx errors |
| `log_level` | `str` | `"WARNING"` | Logging level: `"DEBUG"`, `"INFO"`, `"WARNING"`, `"ERROR"` |
| `rate_limit` | `int \| None` | `None` | Max API requests per second (`None` = unlimited) |
| `paper_config` | `PaperConfig \| None` | `None` | Paper trading configuration for fees, slippage, risk |
| `paper_config_from_env` | `bool` | `False` | Load paper config from `POLYALPHA_PAPER_*` env vars |
| `db_path` | `str \| None` | `None` | Path to SQLite database for trade persistence |
| `openrouter_api_key` | `str \| None` | `None` | OpenRouter API key for AI features |
| `private_key` | `str \| None` | `None` | Private key for real trading wallet |
| `rpc_url` | `str \| None` | `None` | Polygon RPC URL for real trading |
| `polymarket_api_key` | `str \| None` | `None` | Polymarket API key for CLOB access |
| `real_config` | `RealTradingConfig \| None` | `None` | Real trading configuration |

## Attributes

| Attribute | Type | Description |
|-----------|------|-------------|
| `client.markets` | `MarketClient` | Discover and fetch markets |
| `client.paper` | `PaperEngine` | Simulated paper trading (orders, positions, P&L) |
| `client.ai` | `OpenRouterClient \| None` | AI-powered analysis (if API key provided) |
| `client.real` | `RealTradingEngine \| None` | Real trading with actual funds (if credentials provided) |

## Methods

### `client.stream(market, retries=None) -> Stream`

Create a real-time WebSocket price stream.

```python
stream = client.stream(market)
stream.start(background=True)
```

- `market` — a `Market` object from `client.markets.latest()`
- `retries` — override the default reconnect budget

### `client.orderbook(market) -> OrderBookFeed`

Create a live order book feed.

```python
feed = client.orderbook(market)
feed.refresh()
```

### `client.close()`

Clean up HTTP connections and resources.

```python
client.close()
```

## Context Manager

```python
with polyalpha.Client(balance=500.0) as client:
    market = client.markets.latest("BTC", "5m")
    client.paper.buy(market, side="UP", amount=10.0)
# client.close() called automatically
```

## Env Loading

Call `polyalpha.load_env_file()` before constructing the Client to load variables from `.env`:

```python
import polyalpha
polyalpha.load_env_file()
config = polyalpha.get_env_config()
client = polyalpha.Client(
    balance=config["balance"],
    log_level=config["log_level"],
    rate_limit=config["rate_limit"],
)
```

## Examples

**Minimal** — paper trade only:
```python
client = polyalpha.Client(balance=100.0)
```

**With AI** — add OpenRouter for market analysis:
```python
client = polyalpha.Client(
    balance=100.0,
    openrouter_api_key="sk-or-...",
)
```

**Full** — paper + AI + real trading + database:
```python
client = polyalpha.Client(
    balance=500.0,
    log_level="INFO",
    rate_limit=10,
    openrouter_api_key="sk-or-...",
    private_key="0x...",
    rpc_url="https://polygon-rpc.com",
    polymarket_api_key="...",
    db_path="./trades.db",
    paper_config_from_env=True,
)
```
