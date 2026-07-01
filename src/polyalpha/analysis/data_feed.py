"""
Data feed management for technical analysis.

Supports multiple data sources:
- Binance: Free API with extensive historical data
- Chainlink: Oracle data (matches Polymarket)
- Custom: User-provided data sources
- WebSocket: Cache from existing Stream

Usage
-----
    from polyalpha.analysis import DataFeed, DataFeedConfig

    config = DataFeedConfig(source="binance", timeframe="5m")
    feed = DataFeed(config)
    data = feed.fetch("BTC")
"""

from __future__ import annotations

import logging
import os
import time
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Optional, Callable

import pandas as pd
import requests

from ..core.constants import (
    DEFAULT_CACHE_MAX_TICKS,
    API_REQUEST_TIMEOUT,
    CACHE_EXPIRY_SECONDS,
)

log = logging.getLogger(__name__)


# ── Constants ───────────────────────────────────────────────────────────────────

TIMEFRAME_MAP = {
    "1m": "1T",
    "5m": "5T",
    "15m": "15T",
    "1h": "1H",
    "4h": "4H",
    "1d": "1D",
}

BINANCE_INTERVAL_MAP = {
    "1m": "1m",
    "5m": "5m",
    "15m": "15m",
    "1h": "1h",
    "4h": "4h",
    "1d": "1d",
}

# ── Configuration ─────────────────────────────────────────────────────────────

@dataclass
class DataFeedConfig:
    """
    Data feed configuration.

    Parameters
    ----------
    source : str
        Data source: "binance" | "chainlink" | "custom" | "websocket"
    asset_map : dict
        Mapping of Polymarket assets to data source symbols.
    timeframe : str
        Timeframe: "1m" | "5m" | "15m" | "1h" | "4h" | "1d"
    lookback_periods : int
        Number of candles to fetch.
    custom_url : str, optional
        Custom API URL (if source="custom").
    custom_api_key : str, optional
        Custom API key (if source="custom").
    use_cache : bool
        Whether to cache fetched data.
    cache_dir : str, optional
        Directory for cache files.
    """

    source: str = "binance"
    asset_map: dict = field(default_factory=lambda: {
        "BTC": "BTCUSDT",
        "ETH": "ETHUSDT",
        "SOL": "SOLUSDT",
        "XRP": "XRPUSDT",
        "DOGE": "DOGEUSDT",
    })
    timeframe: str = "5m"
    lookback_periods: int = 500
    custom_url: Optional[str] = None
    custom_api_key: Optional[str] = None
    use_cache: bool = True
    cache_dir: Optional[str] = None

    # Binance specific
    binance_api_url: str = "https://api.binance.com/api/v3/klines"

    def __post_init__(self):
        """Validate configuration."""
        valid_sources = ["binance", "chainlink", "custom", "websocket"]
        if self.source not in valid_sources:
            raise ValueError(
                f"Invalid source '{self.source}'. Must be one of: {valid_sources}"
            )

        valid_timeframes = ["1m", "5m", "15m", "1h", "4h", "1d"]
        if self.timeframe not in valid_timeframes:
            raise ValueError(
                f"Invalid timeframe '{self.timeframe}'. Must be one of: {valid_timeframes}"
            )

        if self.lookback_periods <= 0:
            raise ValueError("lookback_periods must be positive")

        if self.source == "custom" and not self.custom_url:
            raise ValueError("custom_url required when source='custom'")

        # Set default cache directory
        if self.use_cache and not self.cache_dir:
            self.cache_dir = os.path.join(os.path.expanduser("~"), ".polyalpha", "cache")


# ── Data Feed ────────────────────────────────────────────────────────────────

class DataFeed:
    """
    Fetch and manage price data for technical analysis.

    Supports multiple data sources and provides caching, resampling,
    and real-time update capabilities.

    Parameters
    ----------
    config : DataFeedConfig
        Data feed configuration.

    Example
    -------
    >>> config = DataFeedConfig(source="binance", timeframe="5m")
    >>> feed = DataFeed(config)
    >>> data = feed.fetch("BTC")
    >>> print(data.head())
    """

    def __init__(self, config: DataFeedConfig):
        """Initialize data feed."""
        self.config = config
        self._data: Optional[pd.DataFrame] = None
        self._current_asset: Optional[str] = None
        self._log = logging.getLogger(__name__)

        # WebSocket cache
        self._ws_cache: list[dict] = []
        self._ws_lock = None

        try:
            import threading
            self._ws_lock = threading.Lock()
        except ImportError:
            pass

        # Create cache directory if needed
        if self.config.use_cache and self.config.cache_dir:
            os.makedirs(self.config.cache_dir, exist_ok=True)

    # ── Public API ─────────────────────────────────────────────────────────────

    def fetch(self, asset: str) -> pd.DataFrame:
        """
        Fetch historical data for asset.

        Parameters
        ----------
        asset : str
            Asset symbol (e.g., "BTC", "ETH").

        Returns
        -------
        pd.DataFrame
            DataFrame with columns: timestamp, open, high, low, close, volume.

        Raises
        ------
        ValueError
            If asset is not in asset_map.
        Exception
            If data fetch fails.
        """
        asset = asset.upper()
        if asset not in self.config.asset_map:
            raise ValueError(
                f"Asset '{asset}' not in asset_map. "
                f"Supported: {list(self.config.asset_map.keys())}"
            )

        self._current_asset = asset

        # Try cache first
        if self.config.use_cache:
            cached = self._load_from_cache(asset)
            if cached is not None:
                self._log.info("Loaded %d candles from cache for %s", len(cached), asset)
                self._data = cached
                return cached

        # Fetch from source
        if self.config.source == "binance":
            data = self._fetch_binance(asset)
        elif self.config.source == "chainlink":
            data = self._fetch_chainlink(asset)
        elif self.config.source == "custom":
            data = self._fetch_custom(asset)
        elif self.config.source == "websocket":
            data = self._fetch_websocket_cache(asset)
        else:
            raise ValueError(f"Unsupported source: {self.config.source}")

        # Validate data
        if data is None or len(data) == 0:
            raise Exception(f"No data fetched for {asset}")

        # Save to cache
        if self.config.use_cache:
            self._save_to_cache(asset, data)

        self._data = data
        self._log.info("Fetched %d candles for %s from %s", len(data), asset, self.config.source)
        return data

    def update(self, price: float, timestamp: Optional[datetime] = None) -> None:
        """
        Add real-time price tick (for WebSocket cache).

        Parameters
        ----------
        price : float
            Current price.
        timestamp : datetime, optional
            Timestamp of price (default: now).
        """
        if timestamp is None:
            timestamp = datetime.now(timezone.utc)

        tick = {
            "timestamp": timestamp,
            "price": price,
        }

        if self._ws_lock:
            with self._ws_lock:
                self._ws_cache.append(tick)
                # Keep last N ticks
                if len(self._ws_cache) > DEFAULT_CACHE_MAX_TICKS:
                    self._ws_cache.pop(0)
        else:
            self._ws_cache.append(tick)
            if len(self._ws_cache) > DEFAULT_CACHE_MAX_TICKS:
                self._ws_cache.pop(0)

    def resample(self, timeframe: str) -> pd.DataFrame:
        """
        Resample data to different timeframe.

        Parameters
        ----------
        timeframe : str
            Target timeframe: "1m" | "5m" | "15m" | "1h" | "4h" | "1d".

        Returns
        -------
        pd.DataFrame
            Resampled data.
        """
        if self._data is None:
            raise ValueError("No data available. Call fetch() first.")

        if timeframe not in TIMEFRAME_MAP:
            raise ValueError(f"Invalid timeframe: {timeframe}")

        rule = TIMEFRAME_MAP[timeframe]
        data = self._data.copy()
        data.set_index("timestamp", inplace=True)

        resampled = data.resample(rule).agg({
            "open": "first",
            "high": "max",
            "low": "min",
            "close": "last",
            "volume": "sum",
        }).dropna()

        resampled.reset_index(inplace=True)
        return resampled

    def get_latest(self, n: int = 1) -> pd.DataFrame:
        """
        Get latest n candles.

        Parameters
        ----------
        n : int
            Number of candles to return.

        Returns
        -------
        pd.DataFrame
            Latest n candles.
        """
        if self._data is None:
            raise ValueError("No data available. Call fetch() first.")

        return self._data.tail(n).copy()

    def to_csv(self, filepath: str) -> None:
        """
        Export data to CSV.

        Parameters
        ----------
        filepath : str
            Path to output CSV file.
        """
        if self._data is None:
            raise ValueError("No data available. Call fetch() first.")

        self._data.to_csv(filepath, index=False)
        self._log.info("Exported data to %s", filepath)

    def from_csv(self, filepath: str) -> pd.DataFrame:
        """
        Import data from CSV.

        Parameters
        ----------
        filepath : str
            Path to input CSV file.

        Returns
        -------
        pd.DataFrame
            Imported data.
        """
        self._data = pd.read_csv(filepath)
        self._data["timestamp"] = pd.to_datetime(self._data["timestamp"])
        self._log.info("Imported data from %s", filepath)
        return self._data

    # ── Data Source Implementations ───────────────────────────────────────────

    def _normalize_ohlcv(self, df: pd.DataFrame) -> pd.DataFrame:
        """
        Normalize DataFrame to standard OHLCV format.

        Ensures timestamp is datetime and price/volume columns are float.
        """
        df["timestamp"] = pd.to_datetime(df["timestamp"])
        df["open"] = df["open"].astype(float)
        df["high"] = df["high"].astype(float)
        df["low"] = df["low"].astype(float)
        df["close"] = df["close"].astype(float)
        df["volume"] = df["volume"].astype(float)
        return df

    def _fetch_binance(self, asset: str) -> pd.DataFrame:
        """Fetch data from Binance API."""
        symbol = self.config.asset_map[asset]

        interval = BINANCE_INTERVAL_MAP[self.config.timeframe]

        params = {
            "symbol": symbol,
            "interval": interval,
            "limit": self.config.lookback_periods,
        }

        try:
            response = requests.get(
                self.config.binance_api_url,
                params=params,
                timeout=API_REQUEST_TIMEOUT
            )
            response.raise_for_status()
            data = response.json()
        except Exception as exc:
            self._log.error("Binance API error: %s", exc)
            raise

        # Parse response
        df = pd.DataFrame(data, columns=[
            "timestamp", "open", "high", "low", "close", "volume",
            "close_time", "quote_volume", "trades", "taker_buy_base",
            "taker_buy_quote", "ignore"
        ])

        # Convert timestamp from milliseconds
        df["timestamp"] = pd.to_datetime(df["timestamp"], unit="ms")

        # Select and normalize columns
        df = df[["timestamp", "open", "high", "low", "close", "volume"]]
        df = self._normalize_ohlcv(df)

        return df

    def _fetch_chainlink(self, asset: str) -> pd.DataFrame:
        """
        Fetch data from Chainlink oracles.

        Note: This is a placeholder implementation. Chainlink data
        access requires additional setup (web3.py, RPC endpoints, etc.).
        For now, this falls back to Binance with a warning.
        """
        self._log.warning(
            "Chainlink data source not fully implemented. "
            "Falling back to Binance. "
            "Note: Polymarket uses Chainlink oracles for price feeds. "
            "Using Binance data may have price discrepancies."
        )
        return self._fetch_binance(asset)

    def _fetch_custom(self, asset: str) -> pd.DataFrame:
        """Fetch data from custom API."""
        if not self.config.custom_url:
            raise ValueError("custom_url required for custom source")

        headers = {}
        if self.config.custom_api_key:
            headers["Authorization"] = f"Bearer {self.config.custom_api_key}"

        try:
            response = requests.get(
                self.config.custom_url,
                headers=headers,
                timeout=API_REQUEST_TIMEOUT,
                verify=True  # Explicit SSL verification
            )
            response.raise_for_status()
            data = response.json()
        except Exception as exc:
            self._log.error("Custom API error: %s", exc)
            raise

        # Try to parse as standard OHLCV format
        if isinstance(data, list):
            df = pd.DataFrame(data, columns=["timestamp", "open", "high", "low", "close", "volume"])
        elif isinstance(data, dict) and "data" in data:
            df = pd.DataFrame(data["data"])
        else:
            raise ValueError("Unexpected custom API response format")

        # Normalize types
        df = self._normalize_ohlcv(df)

        return df

    def _fetch_websocket_cache(self, asset: str) -> pd.DataFrame:
        """
        Build OHLCV data from WebSocket cache.

        This is a fallback method when no external data source is available.
        It aggregates price ticks into candles.
        """
        if not self._ws_cache:
            raise ValueError("No WebSocket cache data available")

        if self._ws_lock:
            with self._ws_lock:
                ticks = self._ws_cache.copy()
        else:
            ticks = self._ws_cache.copy()

        # Convert to DataFrame
        df = pd.DataFrame(ticks)
        df["timestamp"] = pd.to_datetime(df["timestamp"])
        df.set_index("timestamp", inplace=True)

        # Resample to target timeframe
        rule = TIMEFRAME_MAP[self.config.timeframe]

        resampled = df.resample(rule).agg({
            "price": ["first", "max", "min", "last"]
        }).dropna()

        resampled.columns = ["open", "high", "low", "close"]
        resampled["volume"] = 0  # No volume data from price ticks
        resampled.reset_index(inplace=True)

        return resampled

    # ── Cache Management ─────────────────────────────────────────────────────

    def _get_cache_path(self, asset: str) -> str:
        """Get cache file path for asset."""
        filename = f"{self.config.source}_{asset}_{self.config.timeframe}.csv"
        return os.path.join(self.config.cache_dir, filename)

    def _load_from_cache(self, asset: str) -> Optional[pd.DataFrame]:
        """Load data from cache if available and recent."""
        if not self.config.use_cache or not self.config.cache_dir:
            return None

        cache_path = self._get_cache_path(asset)

        if not os.path.exists(cache_path):
            return None

        # Check if cache is recent
        cache_age = time.time() - os.path.getmtime(cache_path)
        if cache_age > CACHE_EXPIRY_SECONDS:
            self._log.debug("Cache expired for %s", asset)
            return None

        try:
            df = pd.read_csv(cache_path)
            df["timestamp"] = pd.to_datetime(df["timestamp"])
            return df
        except Exception as exc:
            self._log.warning("Failed to load cache: %s", exc)
            return None

    def _save_to_cache(self, asset: str, data: pd.DataFrame) -> None:
        """Save data to cache."""
        if not self.config.use_cache or not self.config.cache_dir:
            return

        cache_path = self._get_cache_path(asset)

        try:
            data.to_csv(cache_path, index=False)
            self._log.debug("Saved cache for %s", asset)
        except Exception as exc:
            self._log.warning("Failed to save cache: %s", exc)
