"""
Minimal Sniper — ~10 lines to show how little code is needed.

Usage:
    python examples/sniper_minimal.py
"""
import polyalpha
from polyalpha.bots import Sniper

client = polyalpha.Client(balance=100)
sniper = Sniper(client=client, asset="BTC", timeframe="5m", side="UP", amount=10.0)
sniper.run()
