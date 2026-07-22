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
import logging.config
import os

from .utils.logging_utils import (
    DEFAULT_LOG_FORMAT,
    DEFAULT_DATE_FORMAT,
)

_log = logging.getLogger("polyalpha")
_log.setLevel(logging.INFO)
_log.propagate = False


class _LevelFilter(logging.Filter):
    """Allow records below a threshold level through."""
    def __init__(self, max_level: int):
        super().__init__()
        self.max_level = max_level
    def filter(self, record: logging.LogRecord) -> bool:
        return record.levelno < self.max_level


def _setup_logging() -> None:
    """Configure polyalpha logging via dictConfig."""
    if _log.handlers:
        return
    fmt = os.environ.get("POLYALPHA_LOG_FORMAT", "text")
    log_file = os.environ.get("POLYALPHA_LOG_FILE")

    if fmt == "json":
        formatter_cls = "polyalpha.utils.logging_utils.JSONFormatter"
        formatter_kwargs = {"redact_file_paths": False}
    else:
        formatter_cls = "polyalpha.utils.logging_utils.SensitiveDataFormatter"
        formatter_kwargs = {
            "fmt": DEFAULT_LOG_FORMAT,
            "datefmt": DEFAULT_DATE_FORMAT,
            "redact_file_paths": False,
        }

    config: dict = {
        "version": 1,
        "disable_existing_loggers": False,
        "formatters": {
            "default": {
                "()": formatter_cls,
                **formatter_kwargs,
            },
        },
        "filters": {
            "stdout_filter": {
                "()": "polyalpha._LevelFilter",
                "max_level": logging.WARNING,
            },
        },
        "handlers": {
            "stdout": {
                "class": "logging.StreamHandler",
                "level": logging.INFO,
                "formatter": "default",
                "filters": ["stdout_filter"],
                "stream": "ext://sys.stdout",
            },
            "stderr": {
                "class": "logging.StreamHandler",
                "level": logging.WARNING,
                "formatter": "default",
                "stream": "ext://sys.stderr",
            },
        },
        "loggers": {
            "polyalpha": {
                "level": logging.INFO,
                "handlers": ["stdout", "stderr"],
                "propagate": False,
            },
        },
    }

    if log_file:
        config["handlers"]["file"] = {
            "class": "logging.handlers.RotatingFileHandler",
            "level": logging.DEBUG,
            "formatter": "default",
            "filename": log_file,
            "maxBytes": 10 * 1024 * 1024,
            "backupCount": 3,
            "encoding": "utf-8",
        }
        config["loggers"]["polyalpha"]["handlers"].append("file")

    try:
        logging.config.dictConfig(config)
    except Exception as exc:
        _log.warning("Failed to configure logging: %s", exc)


_setup_logging()


_setup_logging()

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
from . import conditions
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
    # Conditions
    "conditions",
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
