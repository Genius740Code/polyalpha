"""
Full Sniper — time-window, entry/exit thresholds, event callbacks.

Usage:
    python examples/sniper.py
"""
import polyalpha
from polyalpha.bots import Sniper

client = polyalpha.Client(balance=100)

sniper = Sniper(
    client=client,
    asset="BTC",
    timeframe="5m",
    side="UP",
    entry_price=0.92,
    exit_price=0.88,
    window_seconds=35,
    amount=20.0,
)

@sniper.on("market_found")
def on_market_found(market):
    print(f"Market found: {market}")

@sniper.on("entry")
def on_entry(order):
    print(f"Entry filled: {order}")

@sniper.on("exit")
def on_exit(reason):
    print(f"Position exited: {reason}")

@sniper.on("resolve")
def on_resolve(outcome, pnl):
    print(f"Resolved: {outcome} P&L=${pnl:.2f}")

@sniper.on("rollover")
def on_rollover(market):
    print(f"Position rolled over to next window: {market}")

@sniper.on("error")
def on_error(err):
    print(f"Error: {err}")

@sniper.on("stop")
def on_stop(reason):
    print(f"Stopped: {reason}")

sniper.run()
