"""
Calculations library for market data analysis.

Provides modular calculation functions organized by data type:
- Market calculations: price changes, trends, volatility
- Volume calculations: volume ratios, trends, surge detection
- Base accessor: source-aware calculation methods for Chainlink, Binance, Coinbase

Usage
-----
    from polyalpha.calculations import MarketCalculations, VolumeCalculations
    from polyalpha.calculations import BaseAccessor
"""

from .market_calculations import MarketCalculations
from .volume_calculations import VolumeCalculations
from .base_accessor import BaseAccessor
from .chainlink_accessor import ChainlinkAccessor
from .binance_accessor import BinanceAccessor

__all__ = [
    "MarketCalculations",
    "VolumeCalculations", 
    "BaseAccessor",
    "ChainlinkAccessor",
    "BinanceAccessor",
]
