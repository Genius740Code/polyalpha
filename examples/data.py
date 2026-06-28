"""
Basic data example.

Run from the project root:
    python examples/data.py
"""

import sys, os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))

import polyalpha

client = polyalpha.Client()

btc = client.markets.latest("BTC", "5m")

btc.show()

print(btc.volume)
print(btc.prices)
print(btc.url)
print(btc.yes_price)
print(btc.no_price)
print(btc.yes_token)
print(btc.no_token)