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
        "rate_limit": _get("RATE_LIMIT", var_type=int),
        "timeout": _get("TIMEOUT", default=10, var_type=int),
        "retries": _get("RETRIES", default=3, var_type=int),
        "private_key": _get("PRIVATE_KEY", var_type=str),
        "rpc_url": _get("RPC_URL", default="https://polygon-rpc.com", var_type=str),
        "polymarket_api_key": _get("POLYMARKET_API_KEY", var_type=str),
        "openrouter_api_key": _get("OPENROUTER_API_KEY", var_type=str),
        "db_path": _get("DB_PATH", var_type=str),
    }
