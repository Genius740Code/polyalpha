"""
Sniper + RSI threshold + SMA period — only arm when TA conditions are met.

Usage:
    python examples/sniper_ta.py
"""
import polyalpha
from polyalpha.bots import Sniper, SniperConfig

client = polyalpha.Client(balance=100)

config = SniperConfig(
    asset="BTC",
    timeframe="5m",
    side="UP",
    entry_price=0.92,
    exit_price=0.88,
    amount=20.0,
    use_ta=True,
    ta_rsi_threshold=50.0,
    ta_sma_period=20,
)

sniper = Sniper(client=client, config=config)

@sniper.on("entry")
def on_entry(order):
    print(f"TA-filtered entry: {order}")

@sniper.on("resolve")
def on_resolve(result):
    print(f"P&L: {result.pnl:.2f}")

sniper.run()
