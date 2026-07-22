"""
Sniper bot — minimal example (~10 lines).

Demonstrates the flagship "very little code" promise.

Usage
-----
    python examples/sniper_minimal.py
"""

import sys, os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))
import polyalpha

sniper = polyalpha.Sniper(
    polyalpha.Client(balance=100.0),
    asset="BTC", timeframe="5m", side="UP",
    entry_price=0.92, exit_price=0.88, amount=20,
)
sniper.run()
