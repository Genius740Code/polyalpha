# Troubleshooting

Common issues, causes, and solutions when using polyalpha.

---

## WebSocket Disconnects

**Symptom:** `StreamDisconnected` raised or the stream stops receiving price updates.

**Causes:**
- Network interruption
- Market expires (resolution)
- Rate limiting from Polymarket WebSocket
- Stale data detection (no price update for 30 seconds)

**Solutions:**
```python
# Increase retry budget
stream = client.stream(market, retries=10)

# Enable circuit breaker for auto-recovery
stream = client.stream(market, enable_circuit_breaker=True)

# Check connection quality
if stream.connection_quality < 0.5:
    print("Poor connection quality")
```

The stream automatically reconnects with exponential backoff (starting at 1s, doubling, with jitter). If retries are exhausted, `StreamDisconnected` is raised.

---

## Rate Limiting

**Symptom:** HTTP 429 responses, `RateLimitExceeded` errors, or orders failing to place.

**Causes:**
- Too many requests per second to the Gamma API or CLOB endpoints
- Excessive market discovery calls in a loop

**Solutions:**
```python
# Limit to 5 requests/second globally
client = Client(rate_limit=5)

# Use caching on order book client
clob = ClobBookClient(cache_ttl=2.0)  # Cache snapshots for 2s

# Avoid calling market discovery in tight loops
# Instead, cache the market object and reuse it
```

---

## Market Not Found

**Symptom:** `MarketNotFound` raised.

**Causes:**
- Asset slug doesn't exist (e.g. `"XRP"` instead of `"XRP"`)
- Timeframe not available for the asset
- Market has expired
- Wrong market slug format

**Solutions:**
```python
# Check available markets
available = client.markets.available("BTC")
for m in available:
    print(m.slug, m.active, m.close_time)

# Search with partial slug
results = client.markets.search("BTC")

# Use latest() which finds the current active market
market = client.markets.latest("BTC", "5m")

# Check if market is still active
if market.active:
    print("Market is tradable")
else:
    print("Market has closed")
```

---

## Insufficient Balance

**Symptom:** `InsufficientBalance` raised when placing an order.

**Causes:**
- Paper balance too low for the requested amount + fees
- Multiple open positions consuming the balance

**Solutions:**
```python
# Check current balance
print(f"Balance: ${client.paper.balance:.2f}")

# Check open positions
for pos in client.paper.positions():
    print(f"  {pos.market_slug}: {pos.side} @ {pos.entry_price}")

# Create client with higher balance
client = Client(balance=5000.0)
```

---

## Order Book Not Available

**Symptom:** `OrderBookNotFound` raised, or `feed.up` / `feed.down` returns `None`.

**Causes:**
- Token ID is incorrect
- Market is too new and has no order book data
- CLOB API is temporarily unavailable

**Solutions:**
```python
# Check if book data is available
feed = client.orderbook(market)
book = feed.refresh()

if feed.up is None:
    print("No UP book data — market may be too new")

if feed.down is None:
    print("No DOWN book data")

# Use last trade price as fallback
snapshot = book_up or book_down
if snapshot:
    print(f"Mid price: {snapshot.mid_price}")
```

---

## Authentication Failures

**Symptom:** `AuthenticationError` or 401/403 responses from real trading API.

**Causes:**
- Invalid or expired Polymarket API credentials
- Missing private key or RPC URL
- Wrong network (not Polygon)

**Solutions:**
```python
# Verify all required credentials are set
config = RealTradingConfig(
    private_key="0x...",
    rpc_url="https://polygon-rpc.com",
    polymarket_api_key="...",
)

# Use environment variables
client = Client(
    private_key="0x...",
    rpc_url="https://polygon-rpc.com",
    polymarket_api_key="...",
)

# Check if real trading was enabled
if client.real is None:
    print("Real trading not enabled — check credentials")
```

---

## Slow Database Queries

**Symptom:** Trade database operations taking longer than expected.

**Causes:**
- Large number of trades without indexes
- WAL mode disabled
- Cache disabled

**Solutions:**
```python
# Enable WAL mode and cache
db = TradeDatabase("trades.db", enable_wal=True, enable_cache=True)

# Run maintenance
db.optimize_database()
db.analyze_indexes()

# Start background optimization
db.start_background_optimization(interval_seconds=3600)

# Use pagination for large result sets
trades = db.load_trades(limit=100, offset=0)
```

---

## Fee Calculation Discrepancies

**Symptom:** Actual fees don't match expected fees.

**Causes:**
- Wrong fee mode configured (polymarket vs custom vs zero)
- Market category mismatch for polymarket fee mode
- Fee rebates not accounted for

**Solutions:**
```python
# Use explicit fee configuration
config = PaperConfig(
    fee_mode="custom",        # "polymarket", "custom", or "zero"
    custom_fee_rate=0.02,     # 2%
    enable_rebates=True,
    maker_rebate_pct=0.25,    # 25% rebate for maker orders
)

client = Client(paper_config=config)
```

---

## Memory Leaks in Long-Running Bots

**Symptom:** Memory usage grows over time during extended bot runs.

**Causes:**
- Price history deque accumulating without bound
- Stream handlers not cleaned up between cycles
- Market objects held in closures

**Solutions:**
```python
# Bot auto-manages its price history (maxlen=200)
# No action needed for TickContext — it caps at 200 entries

# For custom implementations, ensure cleanup:
stream.stop()
feed.close()

# Use bot's built-in cycle management
bot = Bot("BTC", "5m", balance=1000.0)
bot.run()  # Automatic cleanup between cycles
```

---

## Correlation ID Not Set

**Symptom:** Log entries missing correlation IDs, making debugging hard.

**Solution:**
```python
from polyalpha.utils.logging_utils import set_correlation_id

set_correlation_id("my-session-1")
# All subsequent logs from this thread/async context will include [cid=...]
```

---

## Common Error Codes

| Error | Likely Cause |
|-------|-------------|
| `MarketNotFound` | Wrong slug or expired market |
| `MarketClosed` | Market resolved |
| `StreamDisconnected` | Network issue or market expired |
| `InsufficientBalance` | Not enough USDC in paper account |
| `OrderBookError` | CLOB API unavailable |
| `RateLimitExceeded` | Too many requests |
| `ConfigurationError` | Invalid env vars or config values |
| `AuthenticationError` | Bad API key or credentials |
