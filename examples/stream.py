"""
Real-time price stream with UP/DOWN ASCII bar chart.

Usage:
    python examples/stream.py
"""
import polyalpha

client = polyalpha.Client(balance=100)
market = client.markets.latest("BTC", "5m")
print(f"Streaming: {market}\n")

stream = client.stream(market)

@stream.on("price")
def on_price(up, down):
    up_bar = "█" * int(up * 50)
    down_bar = "█" * int(down * 50)
    print(f"UP   {up:.4f} {up_bar}")
    print(f"DOWN {down:.4f} {down_bar}")
    print()

@stream.on("error")
def on_error(err):
    print(f"Stream error: {err}")

@stream.on("close")
def on_close():
    print("Stream closed")

stream.start()
