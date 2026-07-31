"""
Signal generation for trading strategies.

Provides a clean interface for generating trading signals from technical
indicators. Supports simple conditions, composite signals, and custom logic.

Usage
-----
    from polyalpha.analysis import SignalGenerator

    signals = SignalGenerator(indicators)
    if signals.rsi_above(40) and signals.price_above_sma(20):
        print("BUY signal")
"""

from .composite import SignalGenerator

__all__ = ["SignalGenerator"]
