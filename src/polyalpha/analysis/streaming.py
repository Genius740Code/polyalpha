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
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Callable, Optional

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
        WebSocket timeout in seconds.
    reconnect_delay : float
        Delay in seconds before reconnection attempt.
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
            import threading
            thread = threading.Thread(
                target=self._run_in_thread,
                args=(symbol,),
                daemon=True
            )
            thread.start()
            log.info(f"Started background stream for {symbol}")
        else:
            self._run_sync(symbol)

    def stop(self) -> None:
        """Stop streaming."""
        self._running = False
        if self._task and not self._task.done():
            self._task.cancel()
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
        """Async streaming implementation."""
        try:
            import websockets
        except ImportError:
            raise ImportError(
                "websockets library not installed. "
                "Install with: pip install websockets>=12.0"
            )

        ws_symbol = self.config.symbol_map[symbol]

        while self._running:
            try:
                await self._connect_and_stream(ws_symbol, symbol)
            except Exception as exc:
                if self._running:
                    self._emit("error", exc)
                    self._emit("disconnect")
                    log.error(f"Connection error: {exc}")
                    log.info(f"Reconnecting in {self.config.reconnect_delay}s...")
                    await asyncio.sleep(self.config.reconnect_delay)

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
            self._emit("connect")

            # Stream prices
            while self._running:
                try:
                    raw = await asyncio.wait_for(
                        ws.recv(),
                        timeout=self.config.timeout
                    )
                except asyncio.TimeoutError:
                    log.warning("WebSocket timeout")
                    break

                try:
                    msg = json.loads(raw)
                except json.JSONDecodeError:
                    continue

                payload = msg.get("payload", {})
                if payload.get("symbol") == ws_symbol:
                    timestamp = datetime.fromtimestamp(
                        payload["timestamp"] / 1000,
                        tz=timezone.utc
                    )
                    price = float(payload["value"])
                    self._emit("price", symbol, price, timestamp)

    def _emit(self, event: str, *args) -> None:
        """Emit event to all registered callbacks."""
        for callback in self._callbacks[event]:
            try:
                callback(*args)
            except Exception as exc:
                log.error(f"Callback error for {event}: {exc}")
