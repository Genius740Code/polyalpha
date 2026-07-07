# Order Book

The order book module provides real-time access to Polymarket Central Limit Order Book (CLOB) data, along with tools for strategy development and backtesting.

## Overview

The `orderbook` module in `polyalpha` allows you to:
- Fetch full order book snapshots for any market via REST
- Maintain a live order book using WebSocket streams
- Calculate spread, mid price, order book imbalance, and depth
- Run simulated backtests on historical order book data
- Build and test automated trading strategies (Market Making, Momentum, Arbitrage)

## Usage

You can access the order book feed directly from the client:

```python
import asyncio
from polyalpha import Client

async def main():
    client = Client()
    market = client.markets.latest("BTC", "5m")
    
    # Initialize the feed
    feed = client.orderbook(market)
    
    # Fetch initial REST snapshot
    book = feed.refresh()
    print(f"UP token best bid: {book.up.best_bid}, best ask: {book.up.best_ask}")
    
    # Attach WebSocket for live updates
    stream = client.stream(market)
    feed.attach_stream(stream)
    
    @feed.on("update")
    def on_update(updated_book):
        print(f"Live Mid Prices -> UP: {updated_book.up_mid:.3f} | DOWN: {updated_book.down_mid:.3f}")
        
    stream.start(background=True)
    await asyncio.sleep(60)
    stream.stop()

if __name__ == "__main__":
    asyncio.run(main())
```

## Strategy Development

The module provides base classes and implementations for trading strategies, such as `SpreadStrategy`, `ImbalanceStrategy`, and `MomentumStrategy`.
You can subclass `Strategy` to implement your own logic based on order book changes and execute them within the `BacktestEngine`.

For more details, see the complete `polyalpha.orderbook` documentation in `api-reference.md`.
