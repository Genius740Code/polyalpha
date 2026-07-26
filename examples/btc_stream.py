import sys, os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))
import polyalpha

client = polyalpha.Client(log_level="INFO")

market = client.markets.latest("BTC", "5m")
print(f"Market: {market.question}")
print(f"Active: {market.active}  Closed: {market.closed}")
print(f"UP={market.up_price:.4f}  DOWN={market.down_price:.4f}")

stream = client.stream(market)

@stream.on("price")
def on_price(up, down):
    print(f"UP={up:.4f}  DOWN={down:.4f}")

@stream.on("close")
def on_close():
    print("\nMarket closed.")

stream.start()
