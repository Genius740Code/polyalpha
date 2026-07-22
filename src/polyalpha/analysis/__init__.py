"""
Technical analysis module for polyalpha.

This module provides comprehensive technical analysis capabilities including:
- Data feed management (Binance, Chainlink, custom sources)
- Technical indicator calculations (using pandas-ta)
- Signal generation for trading strategies
- Integration with Sniper and paper trading

Data Sources
------------
- Binance: Default external data source (free API)
- Chainlink: Oracle data (matches Polymarket)
- Custom: User-provided data sources
- WebSocket: Cache from existing Stream (fallback)

Supported Indicators
--------------------
- Trend: SMA, EMA, MACD, ADX
- Momentum: RSI, Stochastic, Williams %R, CCI
- Volatility: Bollinger Bands, ATR, Keltner Channels
- Volume: OBV, Volume SMA, Volume ROC
- Price Change: Absolute and percentage price change detection

Usage
-----
    from polyalpha.analysis import DataFeed, IndicatorCalculator, SignalGenerator

    # Fetch data
    feed = DataFeed(DataFeedConfig(source="binance", timeframe="5m"))
    data = feed.fetch("BTC")

    # Calculate indicators
    indicators = IndicatorCalculator(data)
    rsi = indicators.rsi(14)
    bb = indicators.bollinger_bands(20, 2.0)

    # Generate signals
    signals = SignalGenerator(indicators)
    if signals.rsi_above(40) and signals.price_above_sma(20):
        print("BUY signal")
    
    # Price change signals
    if signals.price_change_above(30):  # Only buy if BTC changed by at least $30
        print("Price change threshold met")
    if signals.price_up():  # Only buy if price is up from last candle
        print("Price is up")
    if signals.price_above_by(30):  # Only buy if price is up by at least $30
        print("Price is up by threshold")

IMPORTANT NOTICE
-----------------
Polymarket uses Chainlink oracles for price feeds. When using external
data sources (Binance, custom APIs), price discrepancies may occur.
For best accuracy, use Chainlink data when available.
"""

from .data_feed import DataFeed, DataFeedConfig
from .delta import DeltaCalculator
from .indicators import IndicatorCalculator
from .signals import SignalGenerator
from .streaming import ChainlinkStreamer, ChainlinkStreamerConfig

__all__ = [
    "DataFeed",
    "DataFeedConfig",
    "DeltaCalculator",
    "IndicatorCalculator",
    "SignalGenerator",
    "ChainlinkStreamer",
    "ChainlinkStreamerConfig",
]
