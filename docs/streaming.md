# Streaming

Real-time price streaming via the Polymarket CLOB WebSocket.

```python
stream = client.stream(market)
```

## Stream Constructor

| Parameter | Type | Default | Description |
|-----------|------|---------|-------------|
| `market` | `Market` | — | The market to subscribe to |
| `retries` | `int` | `10` | Maximum reconnect attempts |
| `retry_delay` | `float` | `3.0` | Base back-off delay in seconds |
| `price_threshold` | `float` | `0.0001` | Minimum price change to emit a `price` event |
| `enable_circuit_breaker` | `bool` | `True` | Enable circuit breaker for cascading failure protection |

## Events

| Event | Callback Signature | Description |
|-------|-------------------|-------------|
| `"price"` | `(up: float, down: float)` | Emitted on any mid-price change exceeding `price_threshold` |
| `"book"` | `(data: dict)` | Raw order-book snapshot |
| `"trade"` | `(data: dict)` | Last matched trade |
| `"close"` | `()` | Market resolved — stream closes cleanly |
| `"error"` | `(exc: Exception)` | Unrecoverable error |
| `"connect"` | `()` | Fired on every successful connect |

## Registering Handlers

**Decorator syntax:**
```python
@stream.on("price")
def on_price(up, down):
    if up > 0.6:
        print(f"UP is strong at {up:.4f}")
```

**`add_handler()` method:**
```python
def on_close():
    print("Market resolved")

stream.add_handler("close", on_close)
```

## Starting the Stream

### Blocking (sync)

```python
stream.start()
# blocks until the stream stops (market resolved or error)
```

### Background thread

```python
stream.start(background=True)
# returns immediately, runs in a daemon thread
```

Stop it later:

```python
stream.stop()
```

### Async

```python
await stream.run_async()
```

Requires `pip install websockets` (the async variant uses the `websockets` library instead of `websocket-client`).

## Stream Properties

| Property | Type | Description |
|----------|------|-------------|
| `stream.up` | `float` | Latest UP price (always readable, no callback needed) |
| `stream.down` | `float` | Latest DOWN price |
| `stream.running` | `bool` | True while the background thread is alive |
| `stream.connection_quality` | `float` | 0.0 to 1.0 (1.0 = excellent) |
| `stream.circuit_breaker_state` | `str \| None` | Circuit breaker state, or `None` if disabled |

## Reconnection Logic

The stream auto-reconnects on unexpected disconnects:

1. **Exponential backoff** — delay = `retry_delay * 2^(attempt-1)` plus ±20% random jitter
2. **Max retries** — defaults to 10 attempts; emits `error` and stops after exhausting the budget
3. **High-retry warning** — logged when >50% of retry budget is consumed
4. **Stale data check** — warns if no price update for 30 seconds

## Keepalive Protocol

- Client sends text `"PING"` every 10 seconds
- Server replies with `"PONG"`
- Server may also send `"PING"` — reply is `"PONG"`
- Missing the window causes a silent server-side disconnect

The keepalive runs automatically in a daemon thread (sync) or asyncio task (async).

## Rate Limiting

Incoming messages are rate-limited with a token bucket (default 100 messages per second) to prevent flood-driven memory growth.

## Circuit Breaker

When enabled (default), the circuit breaker opens after 5 consecutive failures and blocks reconnection attempts for 60 seconds. It attempts recovery with 2 consecutive successes before fully closing.

## Price Threshold

A `price` event is only emitted when the price change exceeds `price_threshold` (default 0.0001). This reduces noise when the market is flat. The `up` and `down` properties always reflect the latest tick regardless of the threshold.

## Example: Full Stream Lifecycle

```python
import polyalpha
import time

polyalpha.load_env_file()
client = polyalpha.Client(balance=100.0)

market = client.markets.latest("BTC", "5m")
stream = client.stream(market, price_threshold=0.0005)

@stream.on("price")
def on_price(up, down):
    print(f"[{time.strftime('%H:%M:%S')}] UP={up:.4f}  DOWN={down:.4f}")

@stream.on("connect")
def on_connect():
    print("Connected!")

@stream.on("close")
def on_close():
    print("Market resolved")

@stream.on("error")
def on_error(exc):
    print(f"Stream error: {exc}")

stream.start(background=True)
time.sleep(30)
stream.stop()
client.close()
```
