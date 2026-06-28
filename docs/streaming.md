# Streaming

`client.stream(market)` returns a `Stream` object that connects to the Polymarket CLOB WebSocket and delivers real-time price updates. It auto-reconnects on drops and sends keepalive pings automatically.

---

## Quick start

```python
market = client.markets.latest("BTC", "5m")
stream = client.stream(market)

@stream.on("price")
def on_price(up: float, down: float):
    print(f"UP={up:.4f}  DOWN={down:.4f}")

stream.start()  # blocks until the market closes or stream.stop() is called
```

---

## Creating a stream

```python
stream = client.stream(market)
stream = client.stream(market, retries=5)  # override reconnect budget
```

The stream does not connect until you call `.start()`. Register all your handlers first.

---

## Registering event handlers

Use `@stream.on("event_name")` as a decorator, or `stream.add_handler("event_name", fn)` without one.

```python
# Decorator style
@stream.on("price")
def handler(up, down): ...

# Functional style (useful when building handlers dynamically)
stream.add_handler("price", lambda up, down: print(up, down))
```

Multiple handlers for the same event are all called in registration order. Exceptions raised in a handler are logged and swallowed so they don't crash the stream.

---

## Events

### `price` — up and down prices updated

```python
@stream.on("price")
def on_price(up: float, down: float):
    print(f"UP={up:.4f}  DOWN={down:.4f}")
```

Emitted whenever the mid-price changes for either the UP or DOWN token. Both values are always provided together. This is the most commonly used event.

`up` and `down` are also readable as attributes at any time without registering a handler:

```python
print(stream.up, stream.down)
```

---

### `book` — full order-book snapshot

```python
@stream.on("book")
def on_book(data: dict):
    bids = data.get("bids", [])
    asks = data.get("asks", [])
    print(f"Best bid: {bids[0]['price'] if bids else 'none'}")
```

Received once on connect per token as the CLOB sends the initial state. `data` is the raw dict from the WebSocket.

---

### `trade` — last matched trade

```python
@stream.on("trade")
def on_trade(data: dict):
    print(f"Trade at {data.get('price')} for token {data.get('asset_id')}")
```

Emitted when a `last_trade_price` message arrives. `data` is the raw dict.

---

### `connect` — successful connection (including reconnects)

```python
@stream.on("connect")
def on_connect():
    print("Connected!")
```

Fires once each time a WebSocket connection is established, including after automatic reconnects.

---

### `close` — market resolved

```python
@stream.on("close")
def on_close():
    print("Market resolved — stream done")
```

Emitted when the server sends a `market_resolved` message. After this the stream stops cleanly; no reconnect is attempted.

---

### `error` — unrecoverable failure

```python
@stream.on("error")
def on_error(exc: Exception):
    print(f"Stream failed: {exc}")
```

Emitted when the retry budget is exhausted or an unexpected exception occurs. The stream will not reconnect after this.

---

## Starting the stream

### Blocking mode (default)

```python
stream.start()
```

Blocks the calling thread until the stream stops (market resolved, `stream.stop()` called, or error).

### Background mode

```python
stream.start(background=True)
# your code continues here

# ... later
stream.stop()
```

Runs in a daemon thread. The program exits if the main thread ends, which also kills background streams.

```python
# Check if the background stream is alive
if stream.running:
    print("Stream is active")
```

---

## Stopping the stream

```python
stream.stop()
```

Sets the stop flag and closes the WebSocket cleanly. If the stream is in background mode, the thread exits within one ping interval (≤10 s).

---

## Reconnection behaviour

The stream reconnects automatically on WebSocket drops. Each failure adds a delay:

```
delay = retry_delay × attempt_number
```

Default values (from `constants.py`):

| Constant | Default | Description |
|---|---|---|
| `WS_MAX_RETRIES` | 10 | Give up after this many consecutive failures |
| `WS_RETRY_DELAY` | 3.0 s | Base delay multiplied by attempt number |
| `WS_PING_INTERVAL` | 10 s | How often the client sends a text `PING` |

Override retries for a single stream:

```python
stream = client.stream(market, retries=20)
```

---

## Protocol details

The SDK implements Polymarket's text-based keepalive protocol internally — you don't need to handle this yourself:

- On connect, subscribes with `{"type": "market", "assets_ids": [...], "custom_feature_enabled": true}`
- Sends text `"PING"` every 10 seconds
- Responds to server-sent `"PING"` with `"PONG"` immediately
- Missing the ping window causes a silent server-side disconnect, which triggers an automatic reconnect

---

## Practical patterns

### Background stream with a trading loop

```python
import time
import polyalpha

client = polyalpha.Client()
market = client.markets.latest("BTC", "5m")
stream = client.stream(market)

prices = []

@stream.on("price")
def on_price(up, down):
    prices.append(up)

@stream.on("close")
def on_close():
    print("Market closed, stopping")

stream.start(background=True)

while stream.running:
    if len(prices) >= 10:
        avg = sum(prices[-10:]) / 10
        print(f"10-tick average UP price: {avg:.4f}")
    time.sleep(2)
```

### Trigger a paper order on a price threshold

```python
market = client.markets.latest("ETH", "5m")
stream = client.stream(market)
ordered = False

@stream.on("price")
def on_price(up, down):
    global ordered
    if not ordered and up > 0.65:
        order = client.paper.buy(market, side="UP", amount=25.0)
        print("Placed order:", order)
        ordered = True

stream.start()
```

### Multiple markets in parallel

```python
import polyalpha

client = polyalpha.Client()
streams = []

for asset in ["BTC", "ETH", "SOL"]:
    market = client.markets.latest(asset, "5m")
    s = client.stream(market)

    @s.on("price")
    def on_price(up, down, asset=asset):
        print(f"{asset}  UP={up:.4f}  DOWN={down:.4f}")

    s.start(background=True)
    streams.append(s)

# Wait for all to finish
import time
while any(s.running for s in streams):
    time.sleep(1)
```
