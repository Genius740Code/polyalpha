"""
Simple script to print Chainlink BTC price from Polymarket WebSocket every second.

This example uses polyalpha's ChainlinkStreamer for easy connection to
Polymarket's Chainlink data feed.

Usage:
    python examples/chainlink_btc_stream.py
"""

import asyncio
from datetime import datetime
from polyalpha.analysis import ChainlinkStreamer

# Create streamer
streamer = ChainlinkStreamer()

# Register price callback
@streamer.on("price")
def on_price(symbol: str, price: float, timestamp: datetime):
    """Print price update with timestamp."""
    print(f"[{timestamp.strftime('%Y-%m-%d %H:%M:%S UTC')}] {symbol}: ${price:.2f}")

# Register error callback
@streamer.on("error")
def on_error(exc: Exception):
    """Handle connection errors."""
    print(f"Error: {exc}")

# Register connect callback
@streamer.on("connect")
def on_connect():
    """Handle successful connection."""
    print("Connected to Polymarket WebSocket")

# Register disconnect callback
@streamer.on("disconnect")
def on_disconnect():
    """Handle disconnection."""
    print("Disconnected from WebSocket")

if __name__ == "__main__":
    try:
        # Start streaming BTC prices (blocking)
        streamer.start("BTC")
    except KeyboardInterrupt:
        print("\nStopped by user")
        streamer.stop()
