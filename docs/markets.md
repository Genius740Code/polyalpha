# Markets

Access through `client.markets` — do not instantiate `MarketClient` directly.

```python
market = client.markets.latest("BTC", "5m")
```

## MarketClient Methods

### `latest(asset, timeframe="5m") -> Market`

Return the active market for an asset/timeframe pair. Uses deterministic slug generation — no API search needed.

```python
market = client.markets.latest("SOL", "15m")
```

**Parameters:**
- `asset` — `"BTC"`, `"ETH"`, `"SOL"`, `"XRP"`, `"DOGE"`, `"HYPE"`, `"BNB"`
- `timeframe` — `"5m"`, `"15m"`, `"1h"`, `"4h"`, `"24h"`

**Raises:** `ValueError` if asset or timeframe is unrecognised. `MarketNotFound` if no active market exists.

### `latest_tweet(subject, window="7d") -> Market`

Return the active tweet market for a subject and window.

```python
market = client.markets.latest_tweet("elon-musk", "7d")
```

**Parameters:**
- `subject` — `"elon-musk"`, `"white-house"`, `"zelensky"`
- `window` — `"3d"`, `"7d"`, `"1mo"`

### `get(slug) -> Market`

Fetch a market by its exact event slug.

```python
market = client.markets.get("btc-updown-5m-1751234700")
```

### `search(query, limit=10) -> list[Market]`

Search open markets by keyword.

```python
markets = client.markets.search("ETH 15m", limit=5)
```

**Parameters:**
- `query` — search string (max 200 characters)
- `limit` — results limit (1–100, default 10)

### `available(timeframe="5m") -> list[Market]`

Return active markets for all known assets at a given timeframe.

```python
for m in client.markets.available("5m"):
    print(m.slug, m.up_price)
```

## Market Dataclass

A `Market` represents a single Polymarket Up/Down event.

### Fields

| Field | Type | Description |
|-------|------|-------------|
| `id` | `str` | Condition / event ID from the Gamma API |
| `question` | `str` | Human-readable market question |
| `description` | `str` | Full event description |
| `slug` | `str` | Deterministic event slug, e.g. `"btc-updown-5m-1751234700"` |
| `active` | `bool` | True while the market is still accepting orders |
| `closed` | `bool` | True once the window has closed |
| `archived` | `bool` | True when the event is fully settled |
| `start_time` | `str` | ISO-8601 window open time |
| `end_time` | `str` | ISO-8601 window close time |
| `volume` | `float` | Total USDC traded |
| `liquidity` | `float` | Available USDC liquidity |
| `outcomes` | `list[str]` | Always `["UP", "DOWN"]` |
| `prices` | `list[float]` | `[up_price, down_price]` |
| `tokens` | `list[str]` | `[up_token_id, down_token_id]` |

### Properties

| Property | Returns | Description |
|----------|---------|-------------|
| `market.url` | `str` | Polymarket event URL |
| `market.up_price` | `float` | Current UP token price |
| `market.down_price` | `float` | Current DOWN token price |
| `market.up_token` | `str` | UP CLOB token ID |
| `market.down_token` | `str` | DOWN CLOB token ID |

### Methods

**`market.dump() -> dict`**

Return the market as a plain dict (raw API response excluded).

```python
d = market.dump()
```

**`market.json(indent=2) -> str`**

Return a pretty JSON string.

```python
print(market.json())
```

**`market.refresh(client) -> Market`**

Re-fetch from the Gamma API. Returns a new `Market` with updated prices, status, volume, and liquidity.

```python
updated = market.refresh(client)
```

**`market.show()`**

Print a formatted summary to stdout.

```python
market.show()
# ──────────────────────────────────────────────────────────────
#   Will BTC be above $X at 2:35 PM ET?
# ──────────────────────────────────────────────────────────────
#   slug         btc-updown-5m-1751234700
#   id           0x...
#   active       True
#   ...
```

## Slug Format

Standard Up/Down slugs follow the pattern:

```
{asset}-updown-{timeframe}-{unix_end_ts}
```

For example: `btc-updown-5m-1751234700`

The timestamp is the **end** of the prediction window. `MarketClient.latest()` probes the current window plus the next two to always find an active market.

For 1h and 24h timeframes the slug uses a human-readable format:

- 1h: `bitcoin-up-or-down-month-day-year-hourpm-et`
- 24h: `what-price-will-bitcoin-hit-on-month-day`
