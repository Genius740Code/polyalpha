"""
Real-time Chainlink price streaming from Polymarket WebSocket.

Provides a simple interface to stream live crypto prices from Polymarket's
Chainlink data feed via WebSocket.

Usage
-----
    from polyalpha.analysis import ChainlinkStreamer

    streamer = ChainlinkStreamer()

    @streamer.on("price")
    def on_price(symbol: str, price: float, timestamp: datetime):
        print(f"{symbol}: ${price:.2f}")

    streamer.start("BTC")
"""

from __future__ import annotations

import asyncio
import json
import logging
import random
import threading
import time
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Callable, Optional

from ..core.constants import (
    CL_WS_RECV_TIMEOUT,
    CL_WS_MAX_RETRIES,
    CL_WS_BASE_DELAY,
    CL_WS_BACKOFF_FACTOR,
    CL_WS_JITTER,
    WS_PING_INTERVAL,
)

log = logging.getLogger(__name__)


@dataclass
class ChainlinkStreamerConfig:
    """
    Configuration for Chainlink price streamer.

    Parameters
    ----------
    ws_url : str
        Polymarket WebSocket URL for live data.
    symbol_map : dict
        Mapping of asset symbols to WebSocket symbols.
    timeout : int
        WebSocket connection timeout in seconds.
    reconnect_delay : float
        Deprecated, use base_delay instead.
    recv_timeout : int
        Per-message receive timeout in seconds.
    max_retries : int
        Maximum reconnection attempts before giving up.
    base_delay : float
        Base backoff delay in seconds for reconnection.
    backoff_factor : float
        Exponential backoff multiplier.
    jitter : float
        Jitter factor for randomizing reconnect delay.
    stale_threshold : float
        Seconds without a price update before warning.
    """
    ws_url: str = "wss://ws-live-data.polymarket.com"
    symbol_map: dict = field(default_factory=lambda: {
        "BTC": "btc/usd",
        "ETH": "eth/usd",
        "SOL": "sol/usd",
        "XRP": "xrp/usd",
        "DOGE": "doge/usd",
    })
    timeout: int = 30
    reconnect_delay: float = 5.0
    recv_timeout: int = CL_WS_RECV_TIMEOUT
    max_retries: int = CL_WS_MAX_RETRIES
    base_delay: float = CL_WS_BASE_DELAY
    backoff_factor: float = CL_WS_BACKOFF_FACTOR
    jitter: float = CL_WS_JITTER
    stale_threshold: float = 30.0


class ChainlinkStreamer:
    """
    Stream live Chainlink prices from Polymarket WebSocket.

    Events
    ------
    ``price``    (symbol: str, price: float, timestamp: datetime) — price update
    ``error``    (exc: Exception) — connection or parsing error
    ``connect``  () — successful connection
    ``disconnect`` () — connection lost

    Example
    -------
    >>> streamer = ChainlinkStreamer()
    >>> @streamer.on("price")
    ... def on_price(symbol, price, timestamp):
    ...     print(f"{symbol}: ${price:.2f}")
    >>> streamer.start("BTC")
    """

    def __init__(self, config: Optional[ChainlinkStreamerConfig] = None):
        """Initialize streamer."""
        self.config = config or ChainlinkStreamerConfig()
        self._callbacks: dict[str, list[Callable]] = {
            "price": [],
            "error": [],
            "connect": [],
            "disconnect": [],
        }
        self._running = False
        self._task: Optional[asyncio.Task] = None
        self._loop: Optional[asyncio.AbstractEventLoop] = None
        self._thread: Optional[threading.Thread] = None

        self._last_price_time: float = 0.0
        self._stale_warned: bool = False
        self._last_pong_time: float = 0.0

        # Latest price accessible without callbacks
        self.last_price: Optional[float] = None
        self.last_update: Optional[datetime] = None
        self.last_symbol: Optional[str] = None

    def on(self, event: str) -> Callable:
        """
        Register a callback for an event.

        Parameters
        ----------
        event : str
            Event name: "price", "error", "connect", "disconnect"

        Returns
        -------
        Callable
            Decorator function

        Example
        -------
        >>> @streamer.on("price")
        ... def handler(symbol, price, timestamp):
        ...     print(price)
        """
        if event not in self._callbacks:
            raise ValueError(f"Invalid event: {event}. Valid: {list(self._callbacks.keys())}")

        def decorator(func: Callable) -> Callable:
            self._callbacks[event].append(func)
            return func

        return decorator

    def start(self, symbol: str, background: bool = False) -> None:
        """
        Start streaming prices for a symbol.

        Parameters
        ----------
        symbol : str
            Asset symbol (e.g., "BTC", "ETH").
        background : bool
            If True, runs in background thread. If False, blocks until stopped.

        Raises
        ------
        ValueError
            If symbol not in symbol_map.
        """
        symbol = symbol.upper()
        if symbol not in self.config.symbol_map:
            raise ValueError(
                f"Symbol '{symbol}' not in symbol_map. "
                f"Supported: {list(self.config.symbol_map.keys())}"
            )

        self._running = True

        if background:
            self._thread = threading.Thread(
                target=self._run_in_thread,
                args=(symbol,),
                daemon=True
            )
            self._thread.start()
            log.info(f"Started background stream for {symbol}")
        else:
            self._run_sync(symbol)

    def stop(self) -> None:
        """Stop streaming."""
        self._running = False
        if self._task and not self._task.done():
            self._task.cancel()
        if self._thread and self._thread.is_alive():
            self._thread.join(timeout=5)
        log.info("Streamer stopped")

    def _run_in_thread(self, symbol: str) -> None:
        """Run async loop in background thread."""
        self._run_sync(symbol)

    def _run_sync(self, symbol: str) -> None:
        """Run async streaming in sync context."""
        try:
            asyncio.run(self._stream(symbol))
        except KeyboardInterrupt:
            log.info("Stopped by user")
        except Exception as exc:
            self._emit("error", exc)
            raise

    async def _stream(self, symbol: str) -> None:
        """Async streaming implementation with exponential backoff reconnect."""
        try:
            import websockets
        except ImportError:
            raise ImportError(
                "websockets library not installed. "
                "Install with: pip install websockets>=12.0"
            )

        ws_symbol = self.config.symbol_map[symbol]
        consecutive_failures = 0

        while self._running:
            try:
                await self._connect_and_stream(ws_symbol, symbol)
                # Clean exit — reset failures
                consecutive_failures = 0
            except asyncio.TimeoutError:
                if not self._running:
                    break
                consecutive_failures += 1
                self._emit("disconnect")
                log.warning("ChainlinkStreamer: recv timeout")
            except Exception as exc:
                consecutive_failures += 1
                if self._running:
                    self._emit("error", exc)
                    self._emit("disconnect")
                    log.error(f"Connection error: {exc}")

            if not self._running:
                break

            # 1.3: max retries check
            if consecutive_failures > self.config.max_retries:
                log.error(
                    "ChainlinkStreamer: max retries (%d) exceeded — giving up",
                    self.config.max_retries,
                )
                if self._running:
                    self._emit(
                        "error",
                        ConnectionError(
                            f"Max retries ({self.config.max_retries}) exceeded"
                        ),
                    )
                self._running = False
                break

            # 1.2: exponential backoff with jitter
            base = self.config.base_delay * (
                self.config.backoff_factor ** (consecutive_failures - 1)
            )
            jitter = base * self.config.jitter * random.random()
            delay = base + jitter

            log.warning(
                "ChainlinkStreamer: reconnecting in %.1fs (attempt %d/%d)",
                delay,
                consecutive_failures,
                self.config.max_retries,
            )
            await asyncio.sleep(delay)

    async def _connect_and_stream(self, ws_symbol: str, symbol: str) -> None:
        """Connect to WebSocket and stream prices."""
        import websockets

        log.info(f"Connecting to {self.config.ws_url}...")

        async with websockets.connect(
            self.config.ws_url,
            additional_headers={
                "User-Agent": "Mozilla/5.0",
                "Origin": "https://polymarket.com"
            },
            open_timeout=10,
            ping_interval=WS_PING_INTERVAL,
            ping_timeout=5,
        ) as ws:
            # Subscribe to crypto prices
            await ws.send(json.dumps({
                "action": "subscribe",
                "subscriptions": [{
                    "topic": "crypto_prices_chainlink",
                    "type": "update"
                }]
            }))

            log.info(f"Subscribed to crypto_prices_chainlink for {symbol}")
            self._last_price_time = time.time()
            self._emit("connect")

            # 1.4: concurrent ping keepalive
            ping_task = asyncio.create_task(
                self._ping_loop(ws)
            )

            try:
                # 1.6: use recv_timeout for per-message timeout
                while self._running:
                    try:
                        raw = await asyncio.wait_for(
                            ws.recv(),
                            timeout=self.config.recv_timeout,
                        )
                    except asyncio.TimeoutError:
                        log.warning("ChainlinkStreamer: recv timeout — reconnecting")
                        raise  # 1.1: propagate to _stream reconnect loop

                    # 1.4: handle text-level PING/PONG
                    if raw == "PING":
                        await self._send_pong(ws)
                        continue
                    if raw == "PONG":
                        self._last_pong_time = time.time()
                        continue

                    try:
                        msg = json.loads(raw)
                    except json.JSONDecodeError:
                        continue

                    payload = msg.get("payload", {})
                    if payload.get("symbol") == ws_symbol:
                        self._last_price_time = time.time()  # 1.5: track price time
                        # 1.5: reset stale warning on fresh data
                        self._stale_warned = False
                        timestamp = datetime.fromtimestamp(
                            payload["timestamp"] / 1000,
                            tz=timezone.utc
                        )
                        price = float(payload["value"])
                        self.last_price = price
                        self.last_update = timestamp
                        self.last_symbol = symbol
                        self._emit("price", symbol, price, timestamp)

                    # 1.5: check stale data on every message
                    self._check_stale_data()
            finally:
                ping_task.cancel()
                await asyncio.gather(ping_task, return_exceptions=True)

    async def _ping_loop(self, ws) -> None:
        """Send text PING periodically and check for stale data."""
        while self._running:
            await asyncio.sleep(WS_PING_INTERVAL)
            if not self._running:
                break
            try:
                await ws.send("PING")
                log.debug("ChainlinkStreamer: -> PING")
                self._check_stale_data()
            except Exception:
                break

    async def _send_pong(self, ws) -> None:
        """Send a PONG response to the server."""
        try:
            await ws.send("PONG")
            log.debug("ChainlinkStreamer: <- PING -> PONG")
        except Exception:
            pass

    def _check_stale_data(self) -> None:
        """Log a warning if no price update for stale_threshold seconds."""
        if self._last_price_time == 0:
            return
        elapsed = time.time() - self._last_price_time
        if elapsed > self.config.stale_threshold and not self._stale_warned:
            log.warning(
                "ChainlinkStreamer: no price update for %.0fs — data may be stale",
                elapsed,
            )
            self._stale_warned = True
        elif elapsed <= self.config.stale_threshold:
            self._stale_warned = False

    def _emit(self, event: str, *args) -> None:
        """Emit event to all registered callbacks."""
        for callback in self._callbacks[event]:
            try:
                callback(*args)
            except Exception as exc:
                log.error(f"Callback error for {event}: {exc}")
