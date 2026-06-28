# Markets

`client.markets` is a `MarketClient` that finds and fetches Polymarket Up/Down events via the Gamma API. It handles slug generation, window probing, and API retries automatically.

---

## Finding the current market

```python
market = client.markets.latest("BTC", "5m")
```

This is the most common call. It generates the deterministic slug for the current time window, probes the current window and the next two (in case the clock is right at a boundary), and returns the first active `Market` it finds.

**Parameters**

| Parameter | Type | Default | Description |
|---|---|---|---|
| `asset` | `str` | — | `"BTC"`, `"ETH"`, `"SOL"`, `"XRP"`, or `"DOGE"` (case-insensitive) |
| `timeframe` | `str` | `"5m"` | `"5m"`, `"15m"`, `"1h"`, `"4h"`, or `"24h"` |

**Raises**

- `ValueError` — if the asset or timeframe is not in the supported list
- `MarketNotFound` — if no active market exists for that window

```python
# All five assets at the 15-minute timeframe
for m in client.markets.available("15m"):
    print(m.slug, m.up_price, m.down_price)
```

---

## Fetching by slug

```python
market = client.markets.get("btc-updown-5m-1751234700")
```

Use this when you already have the exact slug — for example, if you persisted it from a previous run. Raises `MarketNotFound` if the event doesn't exist.

**Slug format:** `{asset}-updown-{timeframe}-{unix_end_ts}`

You can also build a slug yourself:

```python
from polyalpha import build_slug
slug = build_slug("BTC", "5m", 1751234700)
# → "btc-updown-5m-1751234700"
```

---

## Searching by keyword

```python
markets = client.markets.search("ETH 15m", limit=5)
for m in markets:
    print(m.question, m.up_price)
```

Searches open markets using the Gamma API's full-text search. Returns a list of `Market` objects (may be empty). Useful for exploratory browsing; for production use `latest()` instead.

---

## All active markets at a timeframe

```python
markets = client.markets.available("1h")
```

Calls `latest()` for every supported asset and collects the results. Assets with no active market at that timeframe are silently skipped.

---

## The Market object

Every method above returns a `Market` dataclass.

### Identity fields

| Field | Type | Description |
|---|---|---|
| `market.id` | `str` | Condition/event ID from the Gamma API |
| `market.question` | `str` | Human-readable market question |
| `market.description` | `str` | Full event description |
| `market.slug` | `str` | Deterministic event slug |

### State fields

| Field | Type | Description |
|---|---|---|
| `market.active` | `bool` | True while the market accepts orders |
| `market.closed` | `bool` | True once the window has closed |
| `market.archived` | `bool` | True when fully settled and archived |

### Timing fields

| Field | Type | Description |
|---|---|---|
| `market.start_time` | `str` | ISO-8601 window open time |
| `market.end_time` | `str` | ISO-8601 window close time |

### Size fields

| Field | Type | Description |
|---|---|---|
| `market.volume` | `float` | Total USDC traded |
| `market.liquidity` | `float` | Available USDC liquidity |

### Price and token fields

| Field | Type | Description |
|---|---|---|
| `market.outcomes` | `list[str]` | Always `["UP", "DOWN"]` |
| `market.prices` | `list[float]` | `[up_price, down_price]` — mid of best bid/ask |
| `market.tokens` | `list[str]` | `[up_token_id, down_token_id]` — CLOB token IDs |

### Computed properties

```python
market.up_price    # float — prices[0]
market.down_price  # float — prices[1]
market.up_token    # str   — tokens[0]
market.down_token  # str   — tokens[1]
market.url         # str   — "https://polymarket.com/event/{slug}"

# Legacy aliases (for compatibility with older code)
market.yes_price   # same as up_price
market.no_price    # same as down_price
market.yes_token   # same as up_token
market.no_token    # same as down_token
```

### Displaying a market

```python
market.show()
```

Prints a formatted summary to stdout:

```
──────────────────────────────────────────────────────────────
  Will BTC be higher in 5 minutes?
──────────────────────────────────────────────────────────────
  slug         btc-updown-5m-1751234700
  id           123456
  active       True
  closed       False
  end_time     2024-06-28T12:05:00Z
  volume       $12,450.00
  liquidity    $3,200.00
  UP price     0.5500
  DOWN price   0.4500
  UP token     abc123...
  DOWN token   def456...
  url          https://polymarket.com/event/btc-updown-5m-1751234700
──────────────────────────────────────────────────────────────
```

### Serializing a market

```python
d    = market.dump()   # dict — excludes raw API response
json = market.json()   # pretty JSON string (indent=2)
json = market.json(indent=4)
```

---

## Practical patterns

### Poll for the next market

Markets open on exact window boundaries. If `latest()` raises `MarketNotFound`, wait a few seconds and retry:

```python
import time
import polyalpha
from polyalpha import MarketNotFound

client = polyalpha.Client()

while True:
    try:
        market = client.markets.latest("BTC", "5m")
        break
    except MarketNotFound:
        time.sleep(5)
```

### React to price direction

```python
market = client.markets.latest("ETH", "15m")

if market.up_price > 0.6:
    print("Market strongly favours UP — up_price:", market.up_price)
elif market.down_price > 0.6:
    print("Market strongly favours DOWN — down_price:", market.down_price)
else:
    print("Market is near 50/50")
```

### Scan all assets

```python
for m in client.markets.available("5m"):
    spread = abs(m.up_price - m.down_price)
    print(f"{m.slug:40s}  spread={spread:.4f}")
```
