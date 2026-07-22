# Getting Started

## Installation

PolyAlpha is not yet on PyPI. Install directly from the repository:

```bash
git clone https://github.com/Genius740Code/polyalpha.git
cd polyalpha
python -m venv venv
source venv/bin/activate   # Linux/Mac
# venv\Scripts\activate    # Windows
pip install -e .
```

Install optional dependencies for analysis and reporting features:

```bash
pip install -e ".[analysis, report]"
# Or install everything (including dev tools):
pip install -e ".[all]"
```

## Environment Setup

Copy the example env file and customize:

```bash
cp .env.example .env
```

At minimum, set your paper trading balance:

```
POLYALPHA_BALANCE=100.0
POLYALPHA_LOG_LEVEL=INFO
```

Call `load_env_file()` before creating your Client to load `.env` automatically:

```python
import polyalpha

polyalpha.load_env_file()          # loads .env from current directory
client = polyalpha.Client()
```

Or pass the path explicitly:

```python
polyalpha.load_env_file("/path/to/.env")
```

## Your First Script

```python
import polyalpha

polyalpha.load_env_file()
client = polyalpha.Client(balance=500.0, log_level="INFO")

# 1. Discover a market
market = client.markets.latest("BTC", "5m")
print(f"Market: {market.question}")
print(f"UP: {market.up_price:.4f}  DOWN: {market.down_price:.4f}")

# 2. Place a paper trade
order = client.paper.buy(market, side="UP", amount=10.0)
print(f"Order filled: {order.id[:8]} @ {order.price:.4f}")

# 3. Stream live prices
stream = client.stream(market)

@stream.on("price")
def on_price(up, down):
    print(f"UP={up:.4f}  DOWN={down:.4f}")

@stream.on("close")
def on_close():
    print("Market resolved — stream closed")

stream.start(background=True)

# 4. Check summary
import time
time.sleep(5)
client.paper.summary()

# 5. Clean up
client.close()
```

Run it:

```bash
python first_script.py
```

## Next Steps

- Read **client.md** for all `Client` constructor options and attributes
- Read **markets.md** for market discovery (`latest`, `search`, `get`, `available`)
- Read **streaming.md** for WebSocket events, handlers, and reconnection
- Read **trading.md** for paper trading commands and real trading setup
- Read **configuration.md** for all environment variables and config classes
