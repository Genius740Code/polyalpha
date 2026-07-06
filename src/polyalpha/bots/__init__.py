"""
Bot utilities for automated trading strategies.

This module provides high-level trading bots that build on top of the
paper trading engine. All bots are designed to work with both paper
and live trading (future release).

Current bots:
- Sniper: Time-window entry bot with threshold-based execution
- Tracker: P&L tracking and reporting utility

Configuration:
- weather_config: Pre-configured city templates for weather bots
"""

from .sniper import Sniper
from .tracker import Tracker
from .weather_config import CITIES, get_config, list_configs, print_config

__all__ = ["Sniper", "Tracker", "CITIES", "get_config", "list_configs", "print_config"]
