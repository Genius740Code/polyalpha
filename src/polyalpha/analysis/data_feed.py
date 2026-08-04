"""
Data feed management for technical analysis.

Supports multiple data sources:
- Binance: Free API with extensive historical data
- Chainlink: Oracle data (matches Polymarket)
- Scraping: Polymarket WebSocket with configurable delay (default source)
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

import asyncio
import json
import logging
import os
import threading
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
    SCRAPE_RECV_TIMEOUT,
    SCRAPE_RETRY_ATTEMPTS,
)

log = logging.getLogger(__name__)


# ── Constants ───────────────────────────────────────────────────────────────────

TIMEFRAME_MAP = {
    "1m": "1min",
    "5m": "5min",
    "15m": "15min",
    "1h": "1h",
    "4h": "4h",
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
        Data source: "binance" | "chainlink" | "scraping" | "custom" | "websocket"
        Binance provides full OHLCV data including volume, quote volume, and trade count.
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
    chainlink_rpc_url : str, optional
        Ethereum RPC endpoint for Chainlink oracle access (if source="chainlink").
        Example: "https://eth.llamarpc.com" or "https://mainnet.infura.io/v3/YOUR_KEY"
    chainlink_contracts : dict
        Mapping of assets to Chainlink oracle contract addresses.
    scraping_ws_url : str
        WebSocket URL for scraping data source (default: "wss://ws-live-data.polymarket.com").
    scraping_delay : float
        Delay in seconds between price collections for scraping (default: 2.0).
    scraping_symbol_map : dict
        Mapping of assets to WebSocket symbols for scraping.
    scraping_timeout : int
        WebSocket timeout in seconds for scraping (default: 90).
    
    Volume Support
    --------------
    When using source="binance", the following volume data is available:
    - volume: Base asset trading volume
    - quote_volume: Quote asset (USDT) trading volume
    - trades: Number of trades in the candle
    - taker_buy_base_volume: Taker buy base asset volume
    - taker_buy_quote_volume: Taker buy quote asset volume
    
    Use DataFeed methods: get_volume(), get_avg_volume(), get_volume_ratio(),
    get_quote_volume(), get_trade_count()
    """

    source: str = "scraping"
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

    # Chainlink specific
    chainlink_rpc_url: Optional[str] = None  # e.g., "https://eth.llamarpc.com" or "https://mainnet.infura.io/v3/YOUR_KEY"
    chainlink_contracts: dict = field(default_factory=lambda: {
        "BTC": "0xF4030086522a5bEEa4988F8cA5B36dbC97BeE88c",  # BTC/USD
        "ETH": "0x5f4eC3Df9cbd43714FE2740f5E3616155c5b8419",  # ETH/USD
        "SOL": "0xD6aF7A0d92771C8c846814E3c8724a6642519e92",  # SOL/USD
        "XRP": "0x97E9361F7B119D89350Ae73995bC1f8A6C78F9F2",  # XRP/USD
        "DOGE": "0x8FbbF1933BFE539e4e6C4518A533941AF5B4C918",  # DOGE/USD
    })

    # Scraping specific
    scraping_ws_url: str = "wss://ws-live-data.polymarket.com"
    scraping_delay: float = 2.0  # Deprecated, use adaptive per-timeframe delay instead
    scraping_symbol_map: dict = field(default_factory=lambda: {
        "BTC": "btc/usd",
        "ETH": "eth/usd",
        "SOL": "sol/usd",
        "XRP": "xrp/usd",
        "DOGE": "doge/usd",
    })
    scraping_timeout: int = 90  # WebSocket session duration in seconds
    scraping_recv_timeout: int = SCRAPE_RECV_TIMEOUT  # Per-message recv timeout
    scraping_retry_attempts: int = SCRAPE_RETRY_ATTEMPTS  # Retries before Binance fallback

    def __post_init__(self):
        """Validate configuration."""
        valid_sources = ["binance", "chainlink", "custom", "websocket", "scraping"]
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

    Volume Support (Binance)
    ------------------------
    When using source="binance", the following volume methods are available:
    - get_volume(asset): Current candle volume
    - get_avg_volume(asset, period=20): Average volume over N periods
    - get_volume_ratio(asset, period=20): Current volume / average volume
    - get_quote_volume(asset): Quote asset (USDT) volume
    - get_trade_count(asset): Number of trades in current candle

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
    >>> volume = feed.get_volume("BTC")
    >>> volume_ratio = feed.get_volume_ratio("BTC", 20)
    """

    def __init__(self, config: DataFeedConfig):
        """Initialize data feed."""
        self.config = config
        self._data: Optional[pd.DataFrame] = None
        self._current_asset: Optional[str] = None
        self._log = logging.getLogger(__name__)

        # WebSocket cache
        self._ws_cache: list[dict] = []
        self._ws_lock = threading.Lock()

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
        elif self.config.source == "scraping":
            data = self._fetch_scraping(asset)
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

        with self._ws_lock:
            self._ws_cache.append(tick)
            # Keep last N ticks
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

        This implementation fetches current prices from Chainlink oracles
        and historical OHLCV data from CoinGecko API for technical analysis.
        """
        try:
            from web3 import Web3
        except ImportError:
            self._log.warning(
                "web3.py not installed. Install with: pip install web3>=6.0.0. "
                "Falling back to Binance."
            )
            return self._fetch_binance(asset)

        if not self.config.chainlink_rpc_url:
            self._log.warning(
                "chainlink_rpc_url not configured. "
                "Set chainlink_rpc_url in DataFeedConfig. "
                "Falling back to Binance."
            )
            return self._fetch_binance(asset)

        if asset not in self.config.chainlink_contracts:
            self._log.warning(
                f"Asset '{asset}' not in chainlink_contracts. "
                f"Supported: {list(self.config.chainlink_contracts.keys())}. "
                "Falling back to Binance."
            )
            return self._fetch_binance(asset)

        try:
            # Fetch current price from Chainlink oracle
            current_price = self._fetch_chainlink_price(asset)
            self._log.info(f"Current Chainlink price for {asset}: ${current_price:.2f}")

            # Fetch historical OHLCV data from CoinGecko
            historical_data = self._fetch_coingecko_historical(asset)

            if historical_data is None or historical_data.empty:
                self._log.warning("Failed to fetch historical data from CoinGecko. Falling back to Binance.")
                return self._fetch_binance(asset)

            # Adjust the latest close price to match Chainlink current price
            historical_data.loc[historical_data.index[-1], 'close'] = current_price
            # Recalculate high/low if needed
            historical_data.loc[historical_data.index[-1], 'high'] = max(
                historical_data.loc[historical_data.index[-1], 'high'], current_price
            )
            historical_data.loc[historical_data.index[-1], 'low'] = min(
                historical_data.loc[historical_data.index[-1], 'low'], current_price
            )

            return historical_data

        except Exception as exc:
            self._log.error(f"Chainlink data fetch error: {exc}")
            self._log.warning("Falling back to Binance.")
            return self._fetch_binance(asset)

    def _fetch_chainlink_price(self, asset: str) -> float:
        """Fetch current price from Chainlink oracle."""
        from web3 import Web3

        contract_address = self.config.chainlink_contracts[asset]
        rpc_url = self.config.chainlink_rpc_url

        w3 = Web3(Web3.HTTPProvider(rpc_url))

        if not w3.is_connected():
            raise ConnectionError("Failed to connect to RPC endpoint")

        # Chainlink Price Feed ABI (minimal)
        abi = [
            {
                "inputs": [],
                "name": "latestRoundData",
                "outputs": [
                    {"name": "roundId", "type": "uint80"},
                    {"name": "answer", "type": "int256"},
                    {"name": "startedAt", "type": "uint256"},
                    {"name": "updatedAt", "type": "uint256"},
                    {"name": "answeredInRound", "type": "uint80"},
                ],
                "stateMutability": "view",
                "type": "function",
            },
            {
                "inputs": [],
                "name": "decimals",
                "outputs": [{"name": "", "type": "uint8"}],
                "stateMutability": "view",
                "type": "function",
            },
        ]

        contract = w3.eth.contract(address=Web3.to_checksum_address(contract_address), abi=abi)

        # Get decimals
        decimals = contract.functions.decimals().call()

        # Get latest price
        latest_data = contract.functions.latestRoundData().call()
        price = latest_data[1] / (10 ** decimals)

        return float(price)

    def _fetch_coingecko_historical(self, asset: str) -> Optional[pd.DataFrame]:
        """Fetch historical OHLCV data from CoinGecko API."""
        # Map asset to CoinGecko IDs
        coingecko_ids = {
            "BTC": "bitcoin",
            "ETH": "ethereum",
            "SOL": "solana",
            "XRP": "ripple",
            "DOGE": "dogecoin",
        }

        if asset not in coingecko_ids:
            self._log.warning(f"Asset '{asset}' not supported by CoinGecko fallback")
            return None

        coin_id = coingecko_ids[asset]

        # Map timeframe to CoinGecko days
        timeframe_days = {
            "1m": 1,
            "5m": 1,
            "15m": 1,
            "1h": 1,
            "4h": 2,
            "1d": max(30, self.config.lookback_periods),
        }

        days = timeframe_days.get(self.config.timeframe, 30)

        url = f"https://api.coingecko.com/api/v3/coins/{coin_id}/ohlc"
        params = {
            "vs_currency": "usd",
            "days": days,
        }

        try:
            response = requests.get(url, params=params, timeout=API_REQUEST_TIMEOUT)
            response.raise_for_status()
            data = response.json()
        except Exception as exc:
            self._log.error(f"CoinGecko API error: {exc}")
            return None

        # CoinGecko returns [timestamp, open, high, low, close]
        df = pd.DataFrame(data, columns=["timestamp", "open", "high", "low", "close"])
        df["timestamp"] = pd.to_datetime(df["timestamp"], unit="ms")
        df["volume"] = float("nan")  # CoinGecko OHLC doesn't include volume

        # Resample to target timeframe if needed
        if self.config.timeframe in ["1m", "5m", "15m", "1h", "4h"]:
            df = self._resample_coingecko_data(df)

        # Limit to lookback_periods
        df = df.tail(self.config.lookback_periods).copy()

        return self._normalize_ohlcv(df)

    def _resample_coingecko_data(self, df: pd.DataFrame) -> pd.DataFrame:
        """Resample CoinGecko data to target timeframe."""
        df = df.copy()
        df.set_index("timestamp", inplace=True)

        rule = TIMEFRAME_MAP[self.config.timeframe]
        resampled = df.resample(rule).agg({
            "open": "first",
            "high": "max",
            "low": "min",
            "close": "last",
            "volume": "sum",
        }).dropna()

        resampled.reset_index(inplace=True)
        return resampled

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

    def _fetch_scraping(self, asset: str) -> pd.DataFrame:
        """
        Fetch data from Polymarket WebSocket with scraping.

        Connects to Polymarket WebSocket, subscribes to crypto prices,
        and collects price ticks with configurable delay.
        Retries on failure before falling back to Binance.
        """
        try:
            import websockets
        except ImportError:
            self._log.warning(
                "websockets not installed. Install with: pip install websockets>=12.0. "
                "Falling back to Binance."
            )
            return self._fetch_binance(asset)

        if asset not in self.config.scraping_symbol_map:
            self._log.warning(
                f"Asset '{asset}' not in scraping_symbol_map. "
                f"Supported: {list(self.config.scraping_symbol_map.keys())}. "
                "Falling back to Binance."
            )
            return self._fetch_binance(asset)

        # Run async WebSocket connection (safe for sync or async callers)
        try:
            loop = asyncio.get_running_loop()
        except RuntimeError:
            loop = None

        # 2.1: retry before falling back to Binance
        last_error = None
        for attempt in range(1, self.config.scraping_retry_attempts + 1):
            try:
                if loop and loop.is_running():
                    future = asyncio.run_coroutine_threadsafe(self._fetch_scraping_async(asset), loop)
                    data = future.result(timeout=30)
                else:
                    data = asyncio.run(self._fetch_scraping_async(asset))
                return data
            except Exception as exc:
                last_error = exc
                self._log.warning(
                    "Scraping attempt %d/%d failed: %s",
                    attempt, self.config.scraping_retry_attempts, exc,
                )
                if attempt < self.config.scraping_retry_attempts:
                    time.sleep(1.0)

        self._log.error(
            "All %d scraping attempts failed: %s",
            self.config.scraping_retry_attempts, last_error,
        )
        self._log.warning("Falling back to Binance.")
        return self._fetch_binance(asset)

    async def _fetch_scraping_async(self, asset: str) -> pd.DataFrame:
        """Async implementation of scraping WebSocket data fetch."""
        try:
            import websockets
        except ImportError:
            raise ImportError("websockets library not installed")

        symbol = self.config.scraping_symbol_map[asset]
        ticks = []
        start_time = time.time()
        target_duration = self.config.scraping_timeout

        # 2.4: inner retry loop — reconnect on WS drop within session
        while time.time() - start_time < target_duration and len(ticks) < self.config.lookback_periods:
            try:
                async with websockets.connect(
                    self.config.scraping_ws_url,
                    additional_headers={
                        "User-Agent": "Mozilla/5.0",
                        "Origin": "https://polymarket.com"
                    },
                    open_timeout=10,
                ) as ws:
                    # Subscribe to crypto prices
                    await ws.send(json.dumps({
                        "action": "subscribe",
                        "subscriptions": [{
                            "topic": "crypto_prices_chainlink",
                            "type": "update"
                        }]
                    }))

                    # 2.2: use recv_timeout for per-message, session_duration for overall
                    while time.time() - start_time < target_duration and len(ticks) < self.config.lookback_periods:
                        try:
                            raw = await asyncio.wait_for(
                                ws.recv(),
                                timeout=self.config.scraping_recv_timeout,
                            )
                        except asyncio.TimeoutError:
                            # 2.2: recv timed out — still within session, keep waiting
                            continue

                        # Handle text-level PING/PONG (same as ChainlinkStreamer)
                        if raw == "PING":
                            await ws.send("PONG")
                            continue
                        if raw == "PONG":
                            continue

                        try:
                            msg = json.loads(raw)
                        except json.JSONDecodeError:
                            continue

                        payload = msg.get("payload", {})
                        if payload.get("symbol") == symbol:
                            timestamp = datetime.fromtimestamp(
                                payload["timestamp"] / 1000,
                                tz=timezone.utc
                            )
                            price = float(payload["value"])
                            ticks.append({"timestamp": timestamp, "price": price})

                            # 2.3: adaptive delay per timeframe instead of fixed 2s
                            await asyncio.sleep(self._get_scraping_delay())

            except Exception as exc:
                remaining = target_duration - (time.time() - start_time)
                if remaining <= 0 or len(ticks) >= self.config.lookback_periods:
                    break
                self._log.warning(
                    "Scraping: WS disconnected — retrying (%.0fs remaining): %s", remaining, exc,
                )
                await asyncio.sleep(1.0)

        if not ticks:
            raise ValueError(f"No price data collected for {asset}")

        self._log.info(
            "Scraping: collected %d ticks for %s in %.0fs",
            len(ticks), asset, time.time() - start_time,
        )

        # Convert to DataFrame and aggregate into OHLCV
        df = pd.DataFrame(ticks)
        df.set_index("timestamp", inplace=True)

        # Resample to target timeframe
        rule = TIMEFRAME_MAP[self.config.timeframe]
        resampled = df.resample(rule).agg({
            "price": ["first", "max", "min", "last"]
        }).dropna()

        resampled.columns = ["open", "high", "low", "close"]
        resampled["volume"] = float("nan")  # No volume data from WebSocket
        resampled.reset_index(inplace=True)

        return self._normalize_ohlcv(resampled)

    def _get_scraping_delay(self) -> float:
        """Get adaptive per-tick delay based on timeframe."""
        delays = {
            "1m": 0.2,
            "5m": 0.2,
            "15m": 0.3,
            "1h": 0.5,
            "4h": 0.5,
            "1d": 0.5,
        }
        return delays.get(self.config.timeframe, 0.3)

    def _get_timeframe_seconds(self) -> int:
        """Get timeframe duration in seconds."""
        timeframe_seconds = {
            "1m": 60,
            "5m": 300,
            "15m": 900,
            "1h": 3600,
            "4h": 14400,
            "1d": 86400,
        }
        return timeframe_seconds.get(self.config.timeframe, 300)

    def _fetch_websocket_cache(self, asset: str) -> pd.DataFrame:
        """
        Build OHLCV data from WebSocket cache.

        This is a fallback method when no external data source is available.
        It aggregates price ticks into candles.
        """
        if not self._ws_cache:
            raise ValueError("No WebSocket cache data available")

        with self._ws_lock:
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
        resampled["volume"] = float("nan")  # No volume data from price ticks
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

    # ── Volume Methods (Binance-specific) ────────────────────────────────────────

    def get_volume(self, asset: str) -> Optional[float]:
        """
        Get current volume for asset from latest candle.

        Parameters
        ----------
        asset : str
            Asset symbol (e.g., "BTC", "ETH").

        Returns
        -------
        float or None
            Current volume or None if data unavailable.
        """
        if self._data is None or self._current_asset != asset:
            try:
                self.fetch(asset)
            except Exception:
                return None

        if self._data is None or len(self._data) == 0:
            return None

        return float(self._data.iloc[-1]['volume'])

    def get_avg_volume(self, asset: str, period: int = 20) -> Optional[float]:
        """
        Get average volume over N periods for asset.

        Parameters
        ----------
        asset : str
            Asset symbol (e.g., "BTC", "ETH").
        period : int
            Number of periods to average (default: 20).

        Returns
        -------
        float or None
            Average volume or None if data unavailable.
        """
        if self._data is None or self._current_asset != asset:
            try:
                self.fetch(asset)
            except Exception:
                return None

        if self._data is None or len(self._data) < period:
            return None

        return float(self._data.tail(period)['volume'].mean())

    def get_volume_ratio(self, asset: str, period: int = 20) -> Optional[float]:
        """
        Get current volume divided by average volume over N periods.

        Useful for detecting volume spikes (ratio > 1.5 indicates high volume).

        Parameters
        ----------
        asset : str
            Asset symbol (e.g., "BTC", "ETH").
        period : int
            Number of periods for average (default: 20).

        Returns
        -------
        float or None
            Volume ratio or None if data unavailable.
        """
        current_vol = self.get_volume(asset)
        avg_vol = self.get_avg_volume(asset, period)

        if current_vol is None or avg_vol is None or avg_vol == 0:
            return None

        return current_vol / avg_vol

    def get_quote_volume(self, asset: str) -> Optional[float]:
        """
        Get current quote volume (USDT value) for asset from Binance.

        Parameters
        ----------
        asset : str
            Asset symbol (e.g., "BTC", "ETH").

        Returns
        -------
        float or None
            Quote volume or None if data unavailable.
        """
        if self._data is None or self._current_asset != asset:
            try:
                self.fetch(asset)
            except Exception:
                return None

        if self._data is None or len(self._data) == 0:
            return None

        # Check if quote_volume column exists (Binance data)
        if 'quote_volume' in self._data.columns:
            return float(self._data.iloc[-1]['quote_volume'])

        return None

    def get_trade_count(self, asset: str) -> Optional[int]:
        """
        Get number of trades in current candle from Binance.

        Parameters
        ----------
        asset : str
            Asset symbol (e.g., "BTC", "ETH").

        Returns
        -------
        int or None
            Trade count or None if data unavailable.
        """
        if self._data is None or self._current_asset != asset:
            try:
                self.fetch(asset)
            except Exception:
                return None

        if self._data is None or len(self._data) == 0:
            return None

        # Check if trades column exists (Binance data)
        if 'trades' in self._data.columns:
            return int(self._data.iloc[-1]['trades'])

        return None
