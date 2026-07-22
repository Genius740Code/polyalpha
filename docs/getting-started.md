# Getting Started

Install PolyAlpha, set up your environment, and run your first script.

## Prerequisites

- Python 3.10 or higher
- git

## Installation

Clone the repository and install from source (PolyAlpha is not on PyPI):

```bash
git clone https://github.com/your-org/polyalpha.git
cd polyalpha
python3 -m venv venv
source venv/bin/activate
pip install -r requirements.txt
```

## Environment Configuration

Copy the template and edit:

```bash
cp .env.example .env
```

All environment variables are optional. By default, the SDK gives you a paper trading account with a 100 USDC balance and WARNING-level logging.

To change the starting balance, edit your `.env`:

```ini
POLYALPHA_BALANCE=500.0
```

For full config options, see **configuration.md**. For the complete variable reference, open `.env.example`.

## Hello, PolyAlpha

Discover a market and check its price:

```python
import polyalpha

client = polyalpha.Client()
market = client.markets.latest("BTC")
print(f"{market.slug}: UP={market.up_price}, DOWN={market.down_price}")
```

Save as `hello.py` and run:

```bash
python hello.py
```

## Example Flow: Discover, Stream, Trade

### 1. Discover a Market

```python
import polyalpha

client = polyalpha.Client()
market = client.markets.latest("BTC", "5m")
print(f"Trading: {market.question}")
```

### 2. Stream Price Updates

```python
from time import sleep

stream = client.stream(market)
stream.on("price", lambda price: print(f"Price: {price}"))
stream.start(background=True)
sleep(10)
stream.stop()
```

The stream delivers real-time price events. Also available: `trade`, `book`, `close`, `error`, and `connect`.

### 3. Place a Paper Trade

```python
order = client.paper.buy(market, side="UP", amount=10.0, stop_loss_pct=0.05)
print(f"Order {order.id}: {order.shares} shares at ${order.price}")

print(f"Balance: ${client.paper.balance}")
client.paper.show_positions()
```

### Complete Script

```python
from time import sleep
import polyalpha

client = polyalpha.Client(balance=100.0)
market = client.markets.latest("BTC", "5m")

print(f"Market: {market.question}")
print(f"UP: {market.up_price}, DOWN: {market.down_price}")

stream = client.stream(market)
stream.on("price", lambda price: print(f"Price: {price}"))
stream.start(background=True)

order = client.paper.buy(market, side="UP", amount=10.0)
print(f"Bought {order.shares} shares at ${order.price}")

sleep(30)
stream.stop()
print(f"Final balance: ${client.paper.balance}")
client.close()
```

## Using the Context Manager

The Client supports context manager protocol for automatic cleanup:

```python
with polyalpha.Client(balance=500.0) as client:
    market = client.markets.latest("BTC")
    client.paper.buy(market, side="UP", amount=5.0)
    # remaining balance = 495.0
# client.close() called automatically
```

## Exploring More

- Check P&amp;L: `client.paper.summary()`
- All markets: `client.markets.available()`
- Market by slug: `client.markets.get("btc-updown-5m-1751234700")`
- Search: `client.markets.search("ETH 15m")`

## Next Steps

| If you want to... | Read this |
|---|---|
| Understand the full client API | client.md |
| Learn about markets | markets.md |
| Stream real-time data | streaming.md |
| Paper and real trading | trading.md |
| All config options | configuration.md |
| Declarative bot framework | bot.md |
| Example scripts walkthrough | examples-guide.md |
