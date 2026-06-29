"""
polyalpha — Python SDK for Polymarket.

Quick start
-----------
    import polyalpha

    client = polyalpha.Client()

    # Discover the current BTC 5-minute market
    market = client.markets.latest("BTC", "5m")
    market.show()

    # Stream live prices
    stream = client.stream(market)

    @stream.on("price")
    def on_price(up, down):
        print(f"UP={up:.4f}  DOWN={down:.4f}")

    stream.start()

    # Paper trade
    order = client.paper.buy(market, side="UP", amount=10.0)
    client.paper.summary()
"""

from .client import Client
from .core import Market
from .stream import Stream
from .trading import PaperEngine, PaperOrder, PaperPosition
from .bots import Sniper, Tracker
from .core.errors import (
    InsufficientBalance,
    MarketClosed,
    MarketNotFound,
    OrderNotFound,
    PolyalphaError,
    StreamDisconnected,
)

__version__ = "0.2.0"

__all__ = [
    # Main entry point
    "Client",
    # Data objects
    "Market",
    "Stream",
    # Paper trading
    "PaperEngine",
    "PaperOrder",
    "PaperPosition",
    # Bots
    "Sniper",
    "Tracker",
    # Errors
    "PolyalphaError",
    "MarketNotFound",
    "MarketClosed",
    "StreamDisconnected",
    "InsufficientBalance",
    "OrderNotFound",
]
