"""
Technical analysis module for polyalpha.

This module provides comprehensive technical analysis capabilities including:
- Data feed management (Binance, Chainlink, custom sources)
- Technical indicator calculations (using ta-lib)
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

IMPORTANT NOTICE
-----------------
Polymarket uses Chainlink oracles for price feeds. When using external
data sources (Binance, custom APIs), price discrepancies may occur.
For best accuracy, use Chainlink data when available.
"""

from .data_feed import DataFeed, DataFeedConfig
from .indicators import IndicatorCalculator
from .signals import SignalGenerator

__all__ = [
    "DataFeed",
    "DataFeedConfig",
    "IndicatorCalculator",
    "SignalGenerator",
]
