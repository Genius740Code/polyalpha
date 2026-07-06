# Paper Trading

`client.paper` is a `PaperEngine` that simulates Polymarket orders locally. No wallet, private key, or real money is involved. It tracks positions, applies configurable fees, and computes P&L against live market prices.

---

## Quick start

```python
client = polyalpha.Client(balance=500.0)

market = client.markets.latest("BTC", "5m")

# Buy $25 on the UP side
order = client.paper.buy(market, side="UP", amount=25.0)
print(order)

# See your positions and total P&L
client.paper.summary()
```

---

## Configuration

Paper trading supports advanced configuration for realistic simulation:

```python
from polyalpha.trading.paper import PaperConfig

# Create a custom configuration
config = PaperConfig(
    fee_mode="polymarket",  # "polymarket", "custom", or "zero"
    market_category="crypto",  # For polymarket mode
    custom_fee_rate=0.02,  # 2% for custom mode
    execution_delay_ms=2000,  # 2 second execution delay
    slippage_pct=0.05,  # 5% slippage
    fill_probability=0.8,  # 80% fill probability for limit orders
)

# Use with client
client = polyalpha.Client(balance=500.0, paper_config=config)
```

---

## Placing orders

### Buy

```python
order = client.paper.buy(market, side="UP", amount=25.0)
order = client.paper.buy(market, side="DOWN", amount=10.0)
```

| Parameter | Type | Description |
|---|---|---|
| `market` | `Market` | The market returned by `client.markets.latest()` |
| `side` | `str` | `"UP"` or `"DOWN"` (case-insensitive) |
| `amount` | `float` | USDC to spend |

**What happens:**

1. A 2% taker fee is deducted from `amount`
2. The remaining USDC is converted to shares at the current mid-price
3. Your balance decreases by `amount`
4. A `PaperOrder` is created and returned
5. A `PaperPosition` is opened (or added to an existing one for that market+side)

**Raises** `InsufficientBalance` if your balance is too low.

### Sell

```python
order = client.paper.sell(market, side="UP", shares=50.0)
```

| Parameter | Type | Description |
|---|---|---|
| `market` | `Market` | The market to sell in |
| `side` | `str` | `"UP"` or `"DOWN"` |
| `shares` | `float` | Number of shares to sell |

Sells at the current mid-price minus the 2% fee. Your balance increases by the proceeds. Raises `InsufficientBalance` if you don't hold enough shares.

---

## The PaperOrder object

`client.paper.buy()` and `client.paper.sell()` both return a `PaperOrder`.

| Attribute | Type | Description |
|---|---|---|
| `order.id` | `str` | Unique UUID for this order |
| `order.market_slug` | `str` | Slug of the market |
| `order.side` | `str` | `"UP"` or `"DOWN"` |
| `order.direction` | `str` | `"BUY"` or `"SELL"` |
| `order.amount_usdc` | `float` | USDC spent (buy) or received (sell) |
| `order.shares` | `float` | Shares filled |
| `order.fill_price` | `float` | Price at which the order was filled |
| `order.fee` | `float` | Fee charged in USDC |
| `order.timestamp` | `str` | ISO-8601 fill time |

---

## The PaperPosition object

Each open position is tracked as a `PaperPosition`.

| Attribute | Type | Description |
|---|---|---|
| `position.market_slug` | `str` | Slug of the market |
| `position.side` | `str` | `"UP"` or `"DOWN"` |
| `position.shares` | `float` | Current share balance |
| `position.avg_cost` | `float` | Average cost basis per share |
| `position.total_cost` | `float` | Total USDC invested |
| `position.realized_pnl` | `float` | P&L locked in from sells |

To compute unrealized P&L, pass the current price:

```python
position = client.paper.positions[0]
unrealized = position.unrealized_pnl(current_price=market.up_price)
```

---

## Inspecting your state

### Balance

```python
print(client.paper.balance)  # float — current USDC balance
```

### All orders

```python
orders = client.paper.orders  # list[PaperOrder]
for o in orders:
    print(o.id, o.side, o.shares, o.fill_price)
```

### All positions

```python
positions = client.paper.positions  # list[PaperPosition]
for p in positions:
    print(p.market_slug, p.side, p.shares, p.avg_cost)
```

### Print a summary

```python
client.paper.summary()
```

Prints balance, all open positions with live P&L, and a total P&L line.

---

## Fees

Paper trading supports three fee modes:

### 1. Polymarket Mode (Realistic)
Uses Polymarket's actual fee structure based on market category:

```python
config = PaperConfig(
    fee_mode="polymarket",
    market_category="crypto",  # crypto, sports, geopolitical, etc.
)
```

**Fee structure:**
- **Geopolitical markets**: 0% fee
- **Sports markets**: Peak 0.75% at 50/50 price
- **Crypto/Finance/Politics/Tech**: Peak 1.80% at 50/50 price
- **Formula**: `fee = C × p × feeRate × (p × (1 − p))^exponent`
- Fees are symmetric around p = 0.50 and decrease at extremes
- Rounded to 4 decimal places

### 2. Custom Mode
Use a fixed fee rate:

```python
config = PaperConfig(
    fee_mode="custom",
    custom_fee_rate=0.02,  # 2% fee
)
```

### 3. Zero Mode
No fees at all:

```python
config = PaperConfig(
    fee_mode="zero",
)
```

**Default behavior:** If no config is provided, uses custom mode with 2% fee.

**Buy example** — spending $100 with 2% fee:
- Fee: $100 × 0.02 = $2.00
- Net USDC invested: $98.00
- Shares at fill price 0.55: $98 / 0.55 ≈ 178.18 shares

---

## Execution Delay

Simulate realistic execution latency:

```python
config = PaperConfig(
    execution_delay_ms=2000,  # 2 second delay
    delay_randomness=0.2,  # ±20% randomness
)
```

This means when you place an order, it will execute after 2 seconds (±20% random variation) at whatever the price is at that time. This simulates:
- Network latency
- Order routing time
- Exchange processing time

**Note:** If you buy at 0.90 and the price moves to 0.91 during the delay, you'll fill at 0.91.

---

## Slippage

Simulate price impact and partial fills:

```python
config = PaperConfig(
    slippage_pct=0.05,  # 5% slippage
    slippage_randomness=0.1,  # ±10% randomness
    max_slippage_no_fill=0.10,  # Don't fill if price moves >10%
)
```

**How it works:**
- If slippage is 5% and you buy UP at 0.90, you might fill at 0.945 (worse price)
- If the price moves beyond `max_slippage_no_fill`, the order won't fill
- Slippage is direction-aware: UP orders get higher prices, DOWN orders get lower prices

---

## Fill Probability

Limit orders don't always fill in real trading. Simulate this:

```python
config = PaperConfig(
    fill_probability=0.7,  # 70% chance limit orders fill
)
```

When a limit order is triggered, there's a 70% chance it fills. If it doesn't fill, the order is cancelled and balance is refunded.

---

## Complete Configuration Example

```python
from polyalpha.trading.paper import PaperConfig

# Realistic Polymarket simulation
config = PaperConfig(
    fee_mode="polymarket",
    market_category="crypto",
    execution_delay_ms=2000,
    delay_randomness=0.2,
    slippage_pct=0.03,
    slippage_randomness=0.1,
    max_slippage_no_fill=0.10,
    fill_probability=0.8,
)

client = polyalpha.Client(balance=1000.0, paper_config=config)
```

---

## Practical patterns

### Flat dollar-cost average

```python
market = client.markets.latest("BTC", "5m")
stream = client.stream(market)
tick = 0

@stream.on("price")
def on_price(up, down):
    global tick
    tick += 1
    if tick % 10 == 0:  # every 10 ticks
        client.paper.buy(market, side="UP", amount=5.0)
        client.paper.summary()

stream.start()
```

### Momentum entry

```python
prices = []

@stream.on("price")
def on_price(up, down):
    prices.append(up)
    if len(prices) < 5:
        return
    if prices[-1] > prices[-5]:  # price rising
        client.paper.buy(market, side="UP", amount=20.0)

stream.start()
```

### Close a position on resolve

```python
@stream.on("close")
def on_close():
    for pos in client.paper.positions:
        if pos.shares > 0:
            client.paper.sell(market, side=pos.side, shares=pos.shares)
    client.paper.summary()

stream.start()
```

### Track P&L live

```python
@stream.on("price")
def on_price(up, down):
    for pos in client.paper.positions:
        price = up if pos.side == "UP" else down
        pnl = pos.unrealized_pnl(price)
        print(f"{pos.side} {pos.shares:.2f} shares  unrealized={pnl:+.4f}")
```

---

## Starting fresh

If you want to reset the paper engine during a session:

```python
client.paper.reset()  # clears orders, positions, restores original balance
```

---

## Time Window Execution

Control when orders are allowed to execute using time windows. This is useful for strategies that only want to trade during specific periods, such as the final minute before market close.

### Basic Usage

```python
from datetime import datetime, timezone, timedelta

client = polyalpha.Client(balance=500.0)
market = client.markets.latest("BTC", "5m")

# Parse market end time
end_time = datetime.fromisoformat(market.end_time)

# Only allow execution within 1 minute of market close
order = client.paper.buy(
    market, 
    side="UP", 
    amount=25.0,
    time_window_start=end_time - timedelta(minutes=1),
    time_window_end=end_time
)
```

### Time Window with Limit Orders

```python
# Place a limit order that only fills within the time window
order = client.paper.limit(
    market,
    side="UP",
    price=0.92,
    amount=25.0,
    time_window_start=end_time - timedelta(minutes=1),
    time_window_end=end_time
)

# Attach stream - order will only fill if price crosses threshold
# AND current time is within the window
stream = client.stream(market)
client.paper.attach_stream(stream, market)
stream.start(background=True)
```

### Time Window with TP/SL

```python
# Buy with stop-loss/take-profit, but only within time window
order = client.paper.buy_with_tp_sl(
    market,
    side="UP",
    amount=100.0,
    stop_loss=0.45,
    take_profit=0.55,
    time_window_start=end_time - timedelta(minutes=1),
    time_window_end=end_time
)
```

### Time Window Parameters

| Parameter | Type | Description |
|---|---|---|
| `time_window_start` | `datetime` (UTC) | Earliest time order can execute |
| `time_window_end` | `datetime` (UTC) | Latest time order can execute |

**Behavior:**
- **Market orders**: If current time is outside the window, the order is rejected with a `ValueError`
- **Limit orders**: The order is placed but will only fill when both price crosses threshold AND time is within window
- **No window set**: Orders execute normally without time restrictions

### Example: BTC 5-Minute Strategy

```python
# Strategy: Only trade BTC 5-minute markets in the final 30 seconds
market = client.markets.latest("BTC", "5m")
end_time = datetime.fromisoformat(market.end_time)

# Place limit order that only fills in last 30 seconds
order = client.paper.limit(
    market,
    side="UP",
    price=0.90,
    amount=50.0,
    time_window_start=end_time - timedelta(seconds=30),
    time_window_end=end_time
)

stream = client.stream(market)
client.paper.attach_stream(stream, market)
stream.start(background=True)
```

### Checking Time Windows

The time window is automatically checked on every price update when a stream is attached. You can also manually check:

```python
# Manually check if an order is within its time window
from polyalpha.trading.paper import PaperEngine
engine = client.paper

# This is called automatically by check_limits()
if engine._is_within_time_window(order):
    print("Order can execute now")
else:
    print("Order outside time window")
```
