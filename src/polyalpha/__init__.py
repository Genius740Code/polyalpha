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

import logging

# Set up sensitive data filtering for all logs using a custom formatter
from .utils.logging_utils import SensitiveDataFormatter

# Get the root logger and configure it with sensitive data formatter
_root_logger = logging.getLogger()
# Remove any existing handlers to avoid duplicates
_root_logger.handlers.clear()

# Create a handler with the sensitive data formatter
_handler = logging.StreamHandler()
_handler.setFormatter(SensitiveDataFormatter(redact_file_paths=False))
_root_logger.addHandler(_handler)

# Set default level if not already configured
if _root_logger.level == logging.WARNING:
    _root_logger.setLevel(logging.INFO)

from .client import Client
from .core import Market
from .core.env import load_env_file, get_env_config
from .stream import Stream
from .bot import Bot
from .trading import PaperEngine, RealTradingEngine
from .trading.paper import PaperConfig
from .trading.real import RealTradingConfig, RealOrder, RealPosition, WalletManager
from .trading.auto_redeem import AutoRedeemConfig
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
    InsufficientAllowance,
    OrderRejected,
    OrderTimeout,
    NetworkError,
    TransientError,
    PositionNotFound,
    RiskLimitExceeded,
    OrderCancelled,
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
    # Bot
    "Bot",
    # Environment
    "load_env_file",
    "get_env_config",
    # Paper trading
    "PaperEngine",
    "PaperConfig",
    "AutoRedeemConfig",
    # Real trading
    "RealTradingEngine",
    "RealTradingConfig",
    "RealOrder",
    "RealPosition",
    "WalletManager",
    # Report
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
    "InsufficientAllowance",
    "OrderNotFound",
    "OrderBookError",
    "OrderBookNotFound",
    "OrderRejected",
    "OrderTimeout",
    "NetworkError",
    "TransientError",
    "PositionNotFound",
    "RiskLimitExceeded",
    "OrderCancelled",
    "AIError",
    "AIAuthenticationError",
    "AIModelNotFoundError",
    "AIQuotaExceededError",
    "AIResponseError",
    "AITimeoutError",
    "AIConnectionError",
]
