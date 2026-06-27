"""
Phase 2 example — real-time price streaming.
"""
import polyalpha

client = polyalpha.Client(log_level="INFO")

# 1. Get the current BTC 5m market
market = client.markets.latest("BTC", "5m")
market.show()

# 2. Create a stream
stream = client.stream(market)

# 3. Register handlers
@stream.on("connect")
def on_connect():
    print(f"Connected — watching {market.slug}")

@stream.on("price")
def on_price(yes: float, no: float):
    print(f"  YES={yes:.3f}  NO={no:.3f}")

@stream.on("trade")
def on_trade(data: dict):
    print(f"  TRADE: {data}")

@stream.on("close")
def on_close():
    print("Market resolved.")

@stream.on("error")
def on_error(exc: Exception):
    print(f"Error: {exc}")

# 4a. Blocking
stream.start()

# 4b. Background (comment out 4a and uncomment this)
# stream.start(background=True)
# import time; time.sleep(300)
# stream.stop()
