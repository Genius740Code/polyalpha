# Paper Trading

`client.paper` is a `PaperEngine` that simulates Polymarket orders locally. No wallet, private key, or real money is involved. It tracks positions, applies a 2% taker fee, and computes P&L against live market prices.

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

The simulated taker fee is 2% on every fill.

```python
from polyalpha import TAKER_FEE_RATE
print(TAKER_FEE_RATE)  # 0.02
```

**Buy example** — spending $100:
- Fee: $100 × 0.02 = $2.00
- Net USDC invested: $98.00
- Shares at fill price 0.55: $98 / 0.55 ≈ 178.18 shares

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
