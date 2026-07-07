import asyncio
import os
from polyalpha import Client, MarketNotFound

async def main():
    client = Client()
    print("Fetching active market...")
    try:
        market = client.markets.latest("BTC", "5m")
        print(f"Market: {market.question}")
    except MarketNotFound:
        print("No active BTC 5m market found right now.")
        return

    # Create the order book feed
    feed = client.orderbook(market)
    
    # 1. Fetch the initial REST snapshot
    print("\nFetching initial order book snapshot...")
    book = feed.refresh()
    
    print(f"UP Token  | Best Bid: {book.up.best_bid:.3f} | Best Ask: {book.up.best_ask:.3f} | Spread: {book.up.spread:.3f}")
    print(f"DOWN Token| Best Bid: {book.down.best_bid:.3f} | Best Ask: {book.down.best_ask:.3f} | Spread: {book.down.spread:.3f}")

    # 2. Attach WebSocket stream for real-time updates
    print("\nAttaching WebSocket stream for live updates...")
    stream = client.stream(market)
    feed.attach_stream(stream)
    
    # Add an event handler for order book updates
    @feed.on("update")
    def on_update(updated_book):
        print(f"\rLive Mid Prices -> UP: {updated_book.up_mid:.3f} | DOWN: {updated_book.down_mid:.3f}", end="")

    print("Listening to live stream for 10 seconds...")
    stream.start(background=True)
    
    await asyncio.sleep(10)
    print("\n\nStopping stream.")
    stream.stop()
    client.close()

if __name__ == "__main__":
    asyncio.run(main())
