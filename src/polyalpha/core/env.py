"""
Environment variable loading utilities for polyalpha.

This module provides functions to load configuration from environment variables
and .env files.
"""

from __future__ import annotations

import os
from pathlib import Path
from typing import Any

try:
    from dotenv import load_dotenv
    DOTENV_AVAILABLE = True
except ImportError:
    DOTENV_AVAILABLE = False


def load_env_file(env_path: str | Path | None = None) -> bool:
    """
    Load environment variables from a .env file.
    
    Parameters
    ----------
    env_path : str | Path | None
        Path to .env file. If None, searches for .env in current directory
        and parent directories.
    
    Returns
    -------
    bool
        True if .env was loaded successfully, False otherwise.
    """
    if not DOTENV_AVAILABLE:
        return False
    
    if env_path is None:
        env_path = Path.cwd()
    
    return load_dotenv(env_path, override=True)


def get_env_config() -> dict[str, Any]:
    """
    Load all polyalpha configuration from environment variables.
    
    Returns
    -------
    dict[str, Any]
        Dictionary containing all configuration values from environment.
    
    Notes
    -----
    This function loads the following environment variables:
    - POLYALPHA_BALANCE: Paper trading balance (float, default: 100.0)
    - POLYALPHA_LOG_LEVEL: Logging level (str, default: "WARNING")
    - POLYALPHA_LOG_FILE: Optional file path for log persistence (str)
    - POLYALPHA_LOG_FORMAT: Log format, "text" or "json" (str, default: "text")
    - POLYALPHA_RATE_LIMIT: API rate limit (int or None)
    - POLYALPHA_TIMEOUT: HTTP timeout (int, default: 10)
    - POLYALPHA_RETRIES: HTTP retries (int, default: 3)
    - POLYALPHA_PRIVATE_KEY: Wallet private key (str)
    - POLYALPHA_RPC_URL: Polygon RPC URL (str, default: "https://polygon-rpc.com")
    - POLYALPHA_POLYMARKET_API_KEY: Polymarket API key (str)
    - POLYALPHA_OPENROUTER_API_KEY: OpenRouter API key (str)
    - POLYALPHA_DB_PATH: Database path (str)
    """
    def _get(name: str, default: Any = None, var_type: type = str) -> Any:
        """Helper to get env var with type conversion."""
        env_name = f"POLYALPHA_{name}"
        value = os.environ.get(env_name)
        if value is None:
            return default
        if var_type == bool:
            return value.lower() in ("true", "1", "yes", "on")
        if var_type == int:
            return int(value)
        if var_type == float:
            return float(value)
        return value
    
    return {
        "balance": _get("BALANCE", default=100.0, var_type=float),
        "log_level": _get("LOG_LEVEL", default="WARNING", var_type=str),
        "log_file": _get("LOG_FILE", var_type=str),
        "log_format": _get("LOG_FORMAT", default="text", var_type=str),
        "rate_limit": _get("RATE_LIMIT", var_type=int),
        "timeout": _get("TIMEOUT", default=10, var_type=int),
        "retries": _get("RETRIES", default=3, var_type=int),
        "private_key": _get("PRIVATE_KEY", var_type=str),
        "rpc_url": _get("RPC_URL", default="https://polygon-rpc.com", var_type=str),
        "polymarket_api_key": _get("POLYMARKET_API_KEY", var_type=str),
        "polymarket_api_secret": _get("POLYMARKET_API_SECRET", var_type=str),
        "polymarket_api_passphrase": _get("POLYMARKET_API_PASSPHRASE", var_type=str),
        "openrouter_api_key": _get("OPENROUTER_API_KEY", var_type=str),
        "db_path": _get("DB_PATH", var_type=str),
    }


def get_paper_config_from_env() -> dict[str, Any]:
    """
    Load paper trading configuration from environment variables.
    
    Returns
    -------
    dict[str, Any]
        Dictionary containing paper trading configuration values from environment.
    
    Notes
    -----
    This function loads the following paper trading environment variables:
    
    Fee Configuration:
    - POLYALPHA_PAPER_FEE_MODE: Fee mode ("polymarket", "custom", "zero", default: "custom")
    - POLYALPHA_PAPER_MARKET_CATEGORY: Market category for polymarket fees (default: "crypto")
    - POLYALPHA_PAPER_CUSTOM_FEE_RATE: Custom fee rate (default: 0.02)
    - POLYALPHA_PAPER_MAKER_FEE_RATE: Maker fee rate (default: 0.0)
    
    Fee Rebate Configuration:
    - POLYALPHA_PAPER_ENABLE_REBATES: Enable fee rebates (bool, default: True)
    - POLYALPHA_PAPER_MAKER_REBATE_PCT: Maker rebate percentage (default: 0.25)
    
    Execution Simulation:
    - POLYALPHA_PAPER_EXECUTION_DELAY_MS: Execution delay in milliseconds (default: 0)
    - POLYALPHA_PAPER_DELAY_RANDOMNESS: Delay randomness 0-1 (default: 0.0)
    - POLYALPHA_PAPER_SLIPPAGE_PCT: Slippage percentage (default: 0.0)
    - POLYALPHA_PAPER_SLIPPAGE_RANDOMNESS: Slippage randomness 0-1 (default: 0.0)
    - POLYALPHA_PAPER_MAX_SLIPPAGE_NO_FILL: Max slippage before no fill 0-1 (default: 0.10)
    - POLYALPHA_PAPER_FILL_PROBABILITY: Fill probability 0-1 (default: 1.0)
    - POLYALPHA_PAPER_CHECK_MODE: Condition check mode (default: "continuous")
    
    Risk Management:
    - POLYALPHA_PAPER_ENABLE_RISK_MANAGEMENT: Enable risk checks (bool, default: True)
    - POLYALPHA_PAPER_MAX_DAILY_LOSS: Maximum daily loss (default: 500.0)
    - POLYALPHA_PAPER_MAX_TRADES_PER_DAY: Maximum trades per day (default: 100)
    - POLYALPHA_PAPER_MAX_ORDER_SIZE: Maximum order size (default: 1000.0)
    - POLYALPHA_PAPER_MAX_POSITION_SIZE: Maximum position size (default: 2000.0)
    - POLYALPHA_PAPER_MAX_OPEN_POSITIONS: Maximum open positions (default: 10)
    - POLYALPHA_PAPER_MAX_RISK_PER_TRADE: Maximum risk per trade 0-1 (default: 0.02)
    """
    def _get(name: str, default: Any = None, var_type: type = str) -> Any:
        """Helper to get env var with type conversion."""
        env_name = f"POLYALPHA_PAPER_{name}"
        value = os.environ.get(env_name)
        if value is None:
            return default
        if var_type == bool:
            return value.lower() in ("true", "1", "yes", "on")
        if var_type == int:
            return int(value)
        if var_type == float:
            return float(value)
        return value
    
    # Parse check_mode - could be string or integer
    check_mode = _get("CHECK_MODE", default="continuous", var_type=str)
    if check_mode not in ("continuous", "once"):
        try:
            check_mode = int(check_mode)
        except ValueError:
            check_mode = "continuous"
    
    return {
        "fee_mode": _get("FEE_MODE", default="custom", var_type=str),
        "market_category": _get("MARKET_CATEGORY", default="crypto", var_type=str),
        "custom_fee_rate": _get("CUSTOM_FEE_RATE", default=0.02, var_type=float),
        "maker_fee_rate": _get("MAKER_FEE_RATE", default=0.0, var_type=float),
        "enable_rebates": _get("ENABLE_REBATES", default=True, var_type=bool),
        "maker_rebate_pct": _get("MAKER_REBATE_PCT", default=0.25, var_type=float),
        "execution_delay_ms": _get("EXECUTION_DELAY_MS", default=0, var_type=int),
        "delay_randomness": _get("DELAY_RANDOMNESS", default=0.0, var_type=float),
        "slippage_pct": _get("SLIPPAGE_PCT", default=0.0, var_type=float),
        "slippage_randomness": _get("SLIPPAGE_RANDOMNESS", default=0.0, var_type=float),
        "max_slippage_no_fill": _get("MAX_SLIPPAGE_NO_FILL", default=0.10, var_type=float),
        "fill_probability": _get("FILL_PROBABILITY", default=1.0, var_type=float),
        "check_mode": check_mode,
        "enable_risk_management": _get("ENABLE_RISK_MANAGEMENT", default=True, var_type=bool),
        "max_daily_loss": _get("MAX_DAILY_LOSS", default=500.0, var_type=float),
        "max_trades_per_day": _get("MAX_TRADES_PER_DAY", default=100, var_type=int),
        "max_order_size": _get("MAX_ORDER_SIZE", default=1000.0, var_type=float),
        "max_position_size": _get("MAX_POSITION_SIZE", default=2000.0, var_type=float),
        "max_open_positions": _get("MAX_OPEN_POSITIONS", default=10, var_type=int),
        "max_risk_per_trade": _get("MAX_RISK_PER_TRADE", default=0.02, var_type=float),
    }
