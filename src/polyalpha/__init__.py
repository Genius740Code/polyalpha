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
from .trading import PaperEngine
from .trading.paper import PaperConfig
from .report import ReportPreset
from .bots import Sniper, Tracker
from .analysis import DataFeed, DataFeedConfig, IndicatorCalculator, SignalGenerator
from .database import TradeDatabase
from .orderbook import (
    BacktestEngine,
    BookLevel,
    BookSide,
    ClobBookClient,
    FillEstimate,
    ImbalanceStrategy,
    MarketOrderBook,
    MomentumStrategy,
    OrderBookFeed,
    OrderBookManager,
    OrderBookSnapshot,
    RiskManager,
    SpreadStrategy,
    Strategy,
    Trade as BookTrade,
    estimate_fill,
    book_summary,
)
from .core.errors import (
    InsufficientBalance,
    MarketClosed,
    MarketNotFound,
    OrderNotFound,
    OrderBookError,
    OrderBookNotFound,
    PolyalphaError,
    StreamDisconnected,
)
from .ai import (
    OpenRouterClient,
    AIError,
    AIAuthenticationError,
    AIModelNotFoundError,
    AIQuotaExceededError,
    AIResponseError,
    AITimeoutError,
    AIConnectionError,
    MarketAnalysis,
    TradingSignal,
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
    "PaperConfig",
    "ReportPreset",
    # Database
    "TradeDatabase",
    # Order book
    "ClobBookClient",
    "OrderBookFeed",
    "OrderBookManager",
    "OrderBookSnapshot",
    "MarketOrderBook",
    "BookLevel",
    "BookSide",
    "FillEstimate",
    "BookTrade",
    "Strategy",
    "ImbalanceStrategy",
    "SpreadStrategy",
    "MomentumStrategy",
    "BacktestEngine",
    "RiskManager",
    "estimate_fill",
    "book_summary",
    # Bots
    "Sniper",
    "Tracker",
    # Analysis
    "DataFeed",
    "DataFeedConfig",
    "IndicatorCalculator",
    "SignalGenerator",
    # AI
    "OpenRouterClient",
    "MarketAnalysis",
    "TradingSignal",
    # Errors
    "PolyalphaError",
    "MarketNotFound",
    "MarketClosed",
    "StreamDisconnected",
    "InsufficientBalance",
    "OrderNotFound",
    "OrderBookError",
    "OrderBookNotFound",
    "AIError",
    "AIAuthenticationError",
    "AIModelNotFoundError",
    "AIQuotaExceededError",
    "AIResponseError",
    "AITimeoutError",
    "AIConnectionError",
]
