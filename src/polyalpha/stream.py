"""
Real-time price streaming via the Polymarket CLOB WebSocket.

WebSocket endpoint: wss://ws-subscriptions-clob.polymarket.com/ws/market

Protocol
--------
Subscribe (sent once on connect):
    {"type": "market", "assets_ids": [token_id, ...], "custom_feature_enabled": true}

Keepalive:
    • Client must send text "PING" at least every 10 s.
    • Server replies with text "PONG".
    • Server may also send "PING" — reply immediately with "PONG".
    • Missing the window causes a silent server-side disconnect.

Event types received:
    book             — full order-book snapshot
    price_change     — best bid/ask changed for one or more assets
    best_bid_ask     — single asset bid/ask update
    last_trade_price — last matched trade for an asset
    market_resolved  — market settled; stream closes cleanly
    new_market       — (ignored)
    tick_size_change — (ignored)

Usage
-----
    stream = client.stream(market)

    @stream.on("price")
    def on_price(up: float, down: float):
        print(f"UP={up:.4f}  DOWN={down:.4f}")

    @stream.on("close")
    def on_close():
        print("Market resolved")

    stream.start()                  # blocking
    stream.start(background=True)   # daemon thread; call stream.stop() to exit
"""

from __future__ import annotations

import asyncio
import json
import logging
import random
import threading
import time
from collections import defaultdict
from typing import Any, Callable

from .utils.logging_utils import mask_transaction_hash

from .core import (
    WS_MAX_RETRIES,
    WS_PING_INTERVAL,
    WS_RETRY_DELAY,
    WS_BACKOFF_FACTOR,
    WS_JITTER,
    CLOB_WS,
    DEFAULT_RATE_LIMIT_MAX_REQUESTS,
    DEFAULT_RATE_LIMIT_PERIOD,
    DEFAULT_PRICE_THRESHOLD,
    PRICE_ROUNDING,
    FALLBACK_PRICE,
    Market,
    StreamDisconnected,
    CircuitBreakerOpenError,
)
from .markets import RateLimiter
from .trading.error_handling import CircuitBreaker

log = logging.getLogger(__name__)

# Event names exposed to callers
EVENTS = frozenset({"price", "book", "trade", "close", "error", "connect", "price_reset", "price_anomaly"})


class Stream:
    """
    Real-time price stream for a Polymarket Up/Down market.

    Subscribes to both UP and DOWN token IDs via the CLOB market channel,
    auto-reconnects on drops, and keeps the server alive with text PINGs.

    Events
    ------
    ``price``        (up: float, down: float)   — emitted on any mid-price change
    ``book``         (data: dict)               — raw order-book snapshot
    ``trade``        (data: dict)               — last matched trade
    ``close``        ()                         — market resolved / clean close
    ``error``        (exc: Exception)           — unrecoverable error
    ``connect``      ()                         — fired on every successful connect
    ``price_reset``  (up: float, down: float)   — emitted when prices reset due to validation failure or reconnect
    ``price_anomaly`` (type: str, ...)          — emitted when price anomaly detected
    """

    STALE_DATA_SECONDS = 30.0

    def __init__(
        self,
        market:      Market,
        retries:     int   = WS_MAX_RETRIES,
        retry_delay: float = WS_RETRY_DELAY,
        price_threshold: float = DEFAULT_PRICE_THRESHOLD,
        enable_circuit_breaker: bool = True,
    ):
        try:
            import websocket as _ws_module  # websocket-client
            self._ws_module = _ws_module
        except ImportError:
            raise ImportError(
                "websocket-client is required for streaming.\n"
                "Install: pip install websocket-client"
            ) from None

        self.market      = market
        self.retries     = retries
        self.retry_delay = retry_delay
        self._price_threshold = price_threshold
        self._enable_circuit_breaker = enable_circuit_breaker

        self._handlers: dict[str, list[Callable]] = defaultdict(list)
        self._ws:          object | None           = None
        self._ws_lock:     threading.Lock          = threading.Lock()
        self._thread:      threading.Thread | None = None
        self._stop:        threading.Event         = threading.Event()
        self._price_lock:  threading.Lock          = threading.Lock()

        # Latest prices — always readable without a callback
        self.up:   float = market.up_price
        self.down: float = market.down_price

        # Track last emitted prices to avoid unnecessary events
        self._last_emitted_up:   float = self.up
        self._last_emitted_down: float = self.down

        # Initialize last valid prices with market prices (not 0)
        self._last_valid_up: float = self.up
        self._last_valid_down: float = self.down

        # Create a mapping from token_id to "UP"/"DOWN" for reliable price mapping
        self._token_to_side: dict[str, str] = {}
        if market.up_token:
            self._token_to_side[market.up_token] = "UP"
        if market.down_token:
            self._token_to_side[market.down_token] = "DOWN"
        
        log.debug(
            "Stream: token_to_side mapping created: UP=%s, DOWN=%s",
            market.up_token[:12] if market.up_token else "(none)",
            market.down_token[:12] if market.down_token else "(none)"
        )

        # Rate limiter for WebSocket message processing (prevent message floods)
        self._message_rate_limiter = RateLimiter(
            max_requests=DEFAULT_RATE_LIMIT_MAX_REQUESTS,
            period_seconds=DEFAULT_RATE_LIMIT_PERIOD
        )

        # Mid-price per token ID (populated from WS events)
        self._token_prices: dict[str, float] = {}
        # Last trade price per token ID (for spread fallback)
        self._last_trade_prices: dict[str, float] = {}

        # Circuit breaker to prevent cascading failures
        if self._enable_circuit_breaker:
            self._circuit_breaker = CircuitBreaker(
                name=f"ws-{market.slug}",
                failure_threshold=5,
                recovery_timeout=60,
                success_threshold=2,
                expected_exception=(StreamDisconnected,)
            )
        else:
            self._circuit_breaker = None

        # Connection quality monitoring
        self._last_ping_time: float = 0
        self._last_pong_time: float = 0
        self._ping_count: int = 0
        self._pong_count: int = 0
        self._connection_quality: float = 1.0  # 0.0 to 1.0

        # Missing-pong tracking
        self._pong_warned: bool = False

        # Stale data tracking
        self._last_price_time: float = time.time()
        self._stale_warned: bool = False

        # Consecutive failure tracking for reconnection backoff
        self._consecutive_failures: int = 0

        # Async stop signal
        self._async_stop: asyncio.Event | None = None

        # Price validation and anomaly detection
        self._last_valid_up: float = self.up if self.up > 0 else 0.5  # Initialize with market price or neutral
        self._last_valid_down: float = self.down if self.down > 0 else 0.5
        self._price_anomaly_count: int = 0
        self._max_price_anomaly_threshold: float = 0.05  # 5% difference threshold
        self._max_price_jump_threshold: float = 0.20  # 20% jump threshold
        self._price_anomaly_mode: bool = False

    # ── Public API ─────────────────────────────────────────────────────────────

    def on(self, event: str) -> Callable:
        """
        Decorator — register a handler for a named event.

        Example
        -------
        >>> @stream.on("price")
        ... def handler(up, down): ...
        """
        if event not in EVENTS:
            raise ValueError(f"Unknown event '{event}'. Valid: {sorted(EVENTS)}")

        def decorator(fn: Callable) -> Callable:
            self._handlers[event].append(fn)
            return fn

        return decorator

    def add_handler(self, event: str, fn: Callable) -> None:
        """Register *fn* as a handler for *event* without decorator syntax."""
        if event not in EVENTS:
            raise ValueError(f"Unknown event '{event}'. Valid: {sorted(EVENTS)}")
        self._handlers[event].append(fn)

    def start(self, background: bool = False) -> None:
        """
        Start the WebSocket stream.

        Parameters
        ----------
        background : if True, runs in a daemon thread and returns immediately.
                     If False (default), blocks until the stream stops.
        """
        self._stop.clear()

        if background:
            self._thread = threading.Thread(
                target  = self._run_with_retry,
                daemon  = True,
                name    = f"polyalpha-stream-{self.market.slug}",
            )
            self._thread.start()
        else:
            self._run_with_retry()

    async def run_async(self) -> None:
        """
        Start the stream asynchronously.

        Uses the ``websockets`` library instead of ``websocket-client``.
        Returns when the stream stops (market resolved or stop() called).

        Example
        -------
        >>> stream = client.stream(market)
        >>> @stream.on("price")
        ... def on_price(up, down):
        ...     print(f"UP={up:.4f}  DOWN={down:.4f}")
        >>> await stream.run_async()
        """
        self._stop.clear()
        self._async_stop = asyncio.Event()

        self._consecutive_failures = 0
        high_retry_warned = False

        while not self._is_stopped():
            try:
                if self._circuit_breaker:
                    await self._circuit_breaker.acall(self._connect_async)
                else:
                    await self._connect_async()
                return

            except CircuitBreakerOpenError:
                recovery = getattr(self._circuit_breaker, 'recovery_timeout', 60) if self._circuit_breaker else 60
                log.warning("Stream: circuit breaker is open, blocking connection attempt")
                await asyncio.sleep(recovery)
                continue

            except StreamDisconnected as exc:
                self._consecutive_failures += 1
                if self._consecutive_failures > self.retries:
                    log.error("Stream: max retries (%d) exceeded — giving up", self.retries)
                    self._emit("error", exc)
                    return

                if self._consecutive_failures > self.retries // 2 and not high_retry_warned:
                    log.warning(
                        "Stream: high retry rate (%d/%d) — network may be unreliable",
                        self._consecutive_failures, self.retries,
                    )
                    high_retry_warned = True

                base_delay = self.retry_delay * (WS_BACKOFF_FACTOR ** (self._consecutive_failures - 1))
                delay = base_delay + base_delay * WS_JITTER * random.random()

                log.warning(
                    "Stream: disconnected (attempt %d/%d) — retrying in %.1fs",
                    self._consecutive_failures, self.retries, delay,
                )
                await asyncio.sleep(delay)

            except Exception as exc:
                log.exception("Stream: unexpected error: %s", exc)
                self._emit("error", exc)
                return
        else:
            self._async_stop = None

    def stop(self) -> None:
        """Signal the stream to stop and close the WebSocket cleanly."""
        self._stop.set()
        if self._async_stop:
            self._async_stop.set()
        with self._ws_lock:
            ws = self._ws
            self._ws = None
        if ws:
            try:
                ws.close()  # type: ignore[union-attr]
            except Exception:
                log.debug("Error closing WebSocket connection", exc_info=True)

    @property
    def running(self) -> bool:
        """True while the background thread is alive."""
        return self._thread is not None and self._thread.is_alive()

    @property
    def connection_quality(self) -> float:
        """Current connection quality (0.0 to 1.0, where 1.0 is excellent)."""
        return self._connection_quality

    @property
    def circuit_breaker_state(self) -> str | None:
        """Current circuit breaker state, or None if disabled."""
        if self._circuit_breaker:
            return self._circuit_breaker.state.value
        return None

    # ── Retry loop ─────────────────────────────────────────────────────────────

    def _run_with_retry(self) -> None:
        """Connect, reconnect on drops, give up after ``self.retries`` failures."""
        self._consecutive_failures = 0
        high_retry_warned = False

        while not self._stop.is_set():
            try:
                if self._circuit_breaker:
                    self._circuit_breaker.call(self._connect)
                else:
                    self._connect()
                # _connect() returns only on a clean stop or market_resolved
                return

            except StreamDisconnected as exc:
                self._consecutive_failures += 1
                if self._consecutive_failures > self.retries:
                    log.error("Stream: max retries (%d) exceeded — giving up", self.retries)
                    self._emit("error", exc)
                    return

                # Warn if retries are getting high (>50% of budget used)
                if self._consecutive_failures > self.retries // 2 and not high_retry_warned:
                    log.warning(
                        "Stream: high retry rate (%d/%d) — network may be unreliable",
                        self._consecutive_failures, self.retries,
                    )
                    high_retry_warned = True

                # Calculate exponential backoff with positive-only jitter
                base_delay = self.retry_delay * (WS_BACKOFF_FACTOR ** (self._consecutive_failures - 1))
                delay = base_delay + base_delay * WS_JITTER * random.random()
                
                log.warning(
                    "Stream: disconnected (attempt %d/%d) — retrying in %.1fs (with jitter)",
                    self._consecutive_failures, self.retries, delay,
                )
                time.sleep(delay)

            except CircuitBreakerOpenError:
                recovery = getattr(self._circuit_breaker, 'recovery_timeout', 60) if self._circuit_breaker else 60
                log.warning("Stream: circuit breaker is open, blocking connection attempt")
                time.sleep(recovery)
                continue

            except Exception as exc:
                log.exception("Stream: unexpected error: %s", exc)
                self._emit("error", exc)
                return

    # ── WebSocket lifecycle ────────────────────────────────────────────────────

    def _connect(self) -> None:
        """Open the WebSocket and block until it closes."""
        token_ids = [t for t in self.market.tokens if t]
        if not token_ids:
            raise StreamDisconnected("Market has no token IDs to subscribe to")

        ws = self._ws_module.WebSocketApp(
            CLOB_WS,
            on_open    = lambda ws:          self._on_open(ws, token_ids),
            on_message = lambda ws, raw:     self._on_message(ws, raw),
            on_error   = lambda ws, exc:     self._on_ws_error(ws, exc),
            on_close   = lambda ws, c, m:   self._on_ws_close(ws, c, m),
        )
        with self._ws_lock:
            self._ws = ws

        # Disable the library's binary WebSocket ping — we use text PING/PONG
        ws.run_forever(ping_interval=None, ping_timeout=None)

        if not self._is_stopped():
            raise StreamDisconnected("WebSocket closed unexpectedly")

    def _is_stopped(self) -> bool:
        """Check if the stream has been signalled to stop (works for sync and async)."""
        if self._stop.is_set():
            return True
        if self._async_stop and self._async_stop.is_set():
            return True
        return False

    async def _connect_async(self) -> None:
        """Open the WebSocket asynchronously and process messages until close."""
        import websockets

        token_ids = [t for t in self.market.tokens if t]
        if not token_ids:
            raise StreamDisconnected("Market has no token IDs to subscribe to")

        async with websockets.connect(CLOB_WS) as ws:
            self._consecutive_failures = 0
            # Clear stale price state on reconnect
            self._token_prices.clear()
            self._last_trade_prices.clear()
            # Reset last price time to avoid immediate stale data detection after reconnect
            self._last_price_time = time.time()
            self._emit("price_reset")
            self._emit("connect")

            await ws.send(json.dumps({
                "type": "market",
                "assets_ids": token_ids,
                "custom_feature_enabled": True,
            }))

            ping_task = asyncio.create_task(self._ping_loop_async(ws))

            try:
                async for raw in ws:
                    if self._is_stopped():
                        break
                    await self._message_rate_limiter.acquire_async()
                    self._on_message_async(ws, raw)
            except websockets.ConnectionClosed:
                pass
            finally:
                ping_task.cancel()
                try:
                    await ping_task
                except asyncio.CancelledError:
                    pass

    async def _send_pong(self, ws) -> None:
        """Send a PONG response to the server."""
        try:
            await ws.send("PONG")
        except Exception:
            log.debug("Failed to send PONG", exc_info=True)

    async def _ping_loop_async(self, ws) -> None:
        """Send text 'PING' at intervals and check for stale data."""
        while not self._is_stopped():
            await asyncio.sleep(WS_PING_INTERVAL)
            if self._is_stopped():
                break
            try:
                self._last_ping_time = time.time()
                self._ping_count += 1
                await ws.send("PING")
                log.debug("Stream: → PING")
                if self._check_stale_data() or self._check_missing_pong():
                    break
            except Exception:
                break

    def _on_message_async(self, ws, raw: str) -> None:
        """Handle a raw WebSocket message in the async path (no rate limiting for WS)."""
        if raw == "PING":
            try:
                asyncio.ensure_future(self._send_pong(ws))
                log.debug("Stream: ← PING → PONG")
            except Exception:
                pass
            return

        if raw == "PONG":
            self._last_pong_time = time.time()
            self._pong_count += 1
            self._pong_warned = False
            if self._last_ping_time > 0:
                rtt = self._last_pong_time - self._last_ping_time
                if rtt < 1.0:
                    self._connection_quality = min(1.0, self._connection_quality * 0.9 + 0.1)
                elif rtt < 3.0:
                    self._connection_quality = max(0.5, self._connection_quality * 0.95)
                else:
                    self._connection_quality = max(0.0, self._connection_quality * 0.8 - 0.1)
            return

        if raw in ("[]", ""):
            return

        try:
            msg = json.loads(raw)
        except (json.JSONDecodeError, TypeError):
            log.debug("Stream: non-JSON frame: %r", raw[:80])
            return

        if isinstance(msg, list):
            for item in msg:
                if isinstance(item, dict):
                    self._dispatch(item)
        elif isinstance(msg, dict):
            self._dispatch(msg)

    def _on_open(self, ws, token_ids: list[str]) -> None:
        self._consecutive_failures = 0
        # Clear stale price state on reconnect
        if self._token_prices:
            log.info("Stream: reconnected — clearing stale price state")
        self._token_prices.clear()
        self._last_trade_prices.clear()
        # Reset last price time to avoid immediate stale data detection after reconnect
        self._last_price_time = time.time()
        self._emit("price_reset")
        log.info("Stream: connected — subscribing to %d token(s)", len([mask_transaction_hash(t) for t in token_ids]))

        ws.send(json.dumps({
            "type":                  "market",
            "assets_ids":            token_ids,
            "custom_feature_enabled": True,
        }))

        # Start the keepalive ping thread
        ping_thread = threading.Thread(
            target = self._ping_loop,
            args   = (ws,),
            daemon = True,
            name   = "polyalpha-ping",
        )
        ping_thread.start()

        self._emit("connect")

    def _ping_loop(self, ws) -> None:
        """Send text 'PING' every WS_PING_INTERVAL seconds and check for stale data."""
        while not self._stop.is_set():
            time.sleep(WS_PING_INTERVAL)
            if self._stop.is_set():
                break
            try:
                self._last_ping_time = time.time()
                self._ping_count += 1
                ws.send("PING")
                log.debug("Stream: → PING")
                if self._check_stale_data() or self._check_missing_pong():
                    break
            except Exception:
                break   # socket gone; _on_ws_close / force_reconnect will trigger reconnect

    def _on_message(self, ws, raw: str) -> None:
        # Server-sent PING — reply immediately (no rate limit for control messages)
        if raw == "PING":
            try:
                ws.send("PONG")
                log.debug("Stream: ← PING → PONG")
            except Exception:
                pass
            return

        # Track PONG responses for connection quality
        if raw == "PONG":
            self._last_pong_time = time.time()
            self._pong_count += 1
            self._pong_warned = False
            # Calculate round-trip time
            if self._last_ping_time > 0:
                rtt = self._last_pong_time - self._last_ping_time
                # Update connection quality (exponential moving average)
                if rtt < 1.0:  # Good: < 1 second
                    self._connection_quality = min(1.0, self._connection_quality * 0.9 + 0.1)
                elif rtt < 3.0:  # Acceptable: < 3 seconds
                    self._connection_quality = max(0.5, self._connection_quality * 0.95)
                else:  # Poor: >= 3 seconds
                    self._connection_quality = max(0.0, self._connection_quality * 0.8 - 0.1)
            return

        # Ignore empty frames
        if raw in ("[]", ""):
            return

        # Apply rate limiting to message processing
        self._message_rate_limiter.acquire()

        try:
            msg = json.loads(raw)
        except (json.JSONDecodeError, TypeError):
            log.debug("Stream: non-JSON frame: %r", raw[:80])
            return

        if isinstance(msg, list):
            for item in msg:
                if isinstance(item, dict):
                    self._dispatch(item)
        elif isinstance(msg, dict):
            self._dispatch(msg)

    def _on_ws_error(self, ws, exc: Exception) -> None:
        log.warning("Stream: WS error: %s", exc)
        # Don't emit here — the retry loop handles it

    def _on_ws_close(self, ws, code: int | None, message: str | None) -> None:
        if code and code != 1000:
            log.warning("Stream: closed abnormally (code=%s) — initiating reconnect", code)
        else:
            log.info("Stream: closed (code=%s)", code)

    # ── Message dispatch ───────────────────────────────────────────────────────

    def _dispatch(self, msg: dict) -> None:
        event_type = msg.get("event_type", "")

        if event_type == "price_change":
            self._handle_price_change(msg)

        elif event_type == "best_bid_ask":
            self._handle_best_bid_ask(msg)

        elif event_type == "book":
            self._handle_book(msg)
            self._emit("book", msg)

        elif event_type == "last_trade_price":
            self._handle_last_trade(msg)
            self._emit("trade", msg)

        elif event_type == "market_resolved":
            log.info("Stream: market resolved")
            self._emit("close")
            self.stop()

        else:
            log.debug("Stream: unhandled event_type=%r", event_type)

    # ── Price extraction ───────────────────────────────────────────────────────

    def _mid(self, bid: Any, ask: Any, last_trade_price: float = 0.0, token_id: str = "") -> float | None:
        """
        Return bid/ask mid-price with Polymarket spread rule.
        If spread > $0.10, fallback to last_trade_price.
        """
        try:
            b, a = float(bid), float(ask)
            if b > 0 and a > 0:
                spread = a - b
                if spread <= 0.10:
                    computed = round((b + a) / 2, PRICE_ROUNDING)
                    log.debug(
                        "Price calc: token=%s bid=%.6f ask=%.6f spread=%.6f last_trade=%.6f -> midpoint=%.6f",
                        token_id[:12] if token_id else "", b, a, spread, last_trade_price, computed
                    )
                    return computed
                # Spread too wide - fallback to last trade price
                if last_trade_price > 0:
                    computed = round(float(last_trade_price), PRICE_ROUNDING)
                    log.warning(
                        "Price calc (spread fallback): token=%s bid=%.6f ask=%.6f spread=%.6f last_trade=%.6f -> fallback=%.6f",
                        token_id[:12] if token_id else "", b, a, spread, last_trade_price, computed
                    )
                    return computed
                else:
                    log.warning(
                        "Price calc (spread too wide, no fallback): token=%s bid=%.6f ask=%.6f spread=%.6f - returning None",
                        token_id[:12] if token_id else "", b, a, spread
                    )
        except (TypeError, ValueError) as exc:
            log.debug("Price calc (invalid bid/ask): token=%s bid=%r ask=%r - %s", token_id[:12] if token_id else "", bid, ask, exc)
        return None

    def _set_token_price(self, token_id: str, price: float) -> None:
        if token_id and price > 0:
            with self._price_lock:
                self._token_prices[token_id] = price

    def _handle_price_change(self, msg: dict) -> None:
        for pc in msg.get("price_changes", []):
            asset_id = pc.get("asset_id", "")
            last_trade = self._last_trade_prices.get(asset_id, 0.0)
            mid = self._mid(pc.get("best_bid"), pc.get("best_ask"), last_trade, asset_id)
            if mid is not None:
                self._set_token_price(asset_id, mid)
            elif pc.get("price"):
                try:
                    self._set_token_price(asset_id, float(pc["price"]))
                except (TypeError, ValueError):
                    pass
        self._publish_prices()

    def _handle_best_bid_ask(self, msg: dict) -> None:
        asset_id = msg.get("asset_id", "")
        last_trade = self._last_trade_prices.get(asset_id, 0.0)
        mid = self._mid(msg.get("best_bid"), msg.get("best_ask"), last_trade, asset_id)
        if mid is not None:
            self._set_token_price(asset_id, mid)
        self._publish_prices()

    def _handle_book(self, msg: dict) -> None:
        asset_id = msg.get("asset_id", "")
        try:
            bids = msg.get("bids", [])
            asks = msg.get("asks", [])
            # Track last_trade_price from book snapshot
            if msg.get("last_trade_price"):
                self._last_trade_prices[asset_id] = float(msg["last_trade_price"])
            if bids and asks:
                last_trade = self._last_trade_prices.get(asset_id, 0.0)
                mid = self._mid(bids[0]["price"], asks[0]["price"], last_trade, asset_id)
                if mid is not None:
                    self._set_token_price(asset_id, mid)
        except (KeyError, IndexError):
            pass
        self._publish_prices()

    def _handle_last_trade(self, msg: dict) -> None:
        asset_id = msg.get("asset_id", "")
        try:
            price = float(msg.get("price", 0))
            # Track last trade price for spread fallback
            self._last_trade_prices[asset_id] = price
            self._set_token_price(asset_id, price)
        except (TypeError, ValueError):
            pass
        self._publish_prices()

    def _check_missing_pong(self) -> bool:
        """Force reconnect if no PONG received within 3x WS_PING_TIMEOUT."""
        if self._last_ping_time <= 0:
            return False
        elapsed = time.time() - self._last_ping_time
        if elapsed > WS_PING_TIMEOUT and not self._pong_warned:
            log.warning(
                "Stream: no PONG for %.1fs (market %s) — server may be unresponsive",
                elapsed, self.market.slug,
            )
            self._pong_warned = True
        elif elapsed <= WS_PING_TIMEOUT:
            self._pong_warned = False

        if elapsed > WS_PING_TIMEOUT * 3:
            log.warning(
                "Stream: no PONG for %.1fs (market %s) — forcing reconnect",
                elapsed, self.market.slug,
            )
            self._force_reconnect()
            return True
        return False

    def _check_stale_data(self) -> bool:
        """Force reconnect if no price update for 3x STALE_DATA_SECONDS."""
        elapsed = time.time() - self._last_price_time
        if elapsed > self.STALE_DATA_SECONDS and not self._stale_warned:
            log.warning(
                "Stream: no price update for %.0fs (market %s) — data may be stale",
                elapsed, self.market.slug,
            )
            self._stale_warned = True
        elif elapsed <= self.STALE_DATA_SECONDS:
            self._stale_warned = False

        if elapsed > self.STALE_DATA_SECONDS * 3:
            log.warning(
                "Stream: no price update for %.0fs (market %s) — forcing reconnect",
                elapsed, self.market.slug,
            )
            self._force_reconnect()
            return True
        return False

    def _force_reconnect(self) -> None:
        """Close the current WebSocket so the retry loop reconnects."""
        with self._ws_lock:
            ws = self._ws
            self._ws = None
        if ws:
            try:
                ws.close()
            except Exception:
                pass

    def _validate_prices(self) -> bool:
        """
        Validate price consistency and detect anomalies.
        Returns True if prices are valid, False otherwise.
        """
        # Check for basic price sanity
        if not (0 <= self.up <= 1) or not (0 <= self.down <= 1):
            log.error("Price out of bounds: UP=%.4f DOWN=%.4f", self.up, self.down)
            return False

        # Check for price consistency (UP + DOWN should be close to 1.0)
        price_sum = self.up + self.down
        if abs(price_sum - 1.0) > 0.15:  # Allow 15% deviation for market inefficiency
            log.warning(
                "Price sum anomaly: UP+DOWN=%.4f (expected ~1.0). UP=%.4f DOWN=%.4f",
                price_sum, self.up, self.down
            )
            self._price_anomaly_count += 1
            if self._price_anomaly_count >= 3:
                self._price_anomaly_mode = True
                log.error("Entered price anomaly mode due to consistent price sum issues")
            return False
        else:
            # Reset anomaly count gradually when prices are consistent
            if self._price_anomaly_count > 0:
                self._price_anomaly_count = max(0, self._price_anomaly_count - 1)
                if self._price_anomaly_count == 0 and self._price_anomaly_mode:
                    self._price_anomaly_mode = False
                    log.info("Exited price anomaly mode - prices are now consistent")

        # Check for extreme price jumps (possible token mapping swap)
        if self._last_valid_up > 0 and self._last_valid_down > 0:
            up_jump = abs(self.up - self._last_valid_up) / self._last_valid_up if self._last_valid_up > 0 else 0
            down_jump = abs(self.down - self._last_valid_down) / self._last_valid_down if self._last_valid_down > 0 else 0
            
            if up_jump > self._max_price_jump_threshold or down_jump > self._max_price_jump_threshold:
                log.error(
                    "Extreme price jump detected: UP jump=%.2f%% DOWN jump=%.2f%%. Current: UP=%.4f DOWN=%.4f, Last: UP=%.4f DOWN=%.4f",
                    up_jump * 100, down_jump * 100, self.up, self.down, self._last_valid_up, self._last_valid_down
                )
                self._price_anomaly_count += 1
                self._emit("price_anomaly", "extreme_jump", up_jump, down_jump, self.up, self.down)
                return False

        # Check for logical consistency (UP + DOWN should be close to 1.0 for binary markets)
        # In binary markets, UP and DOWN represent probabilities that should sum to ~1.0
        # Neither should consistently dominate the other; that depends on the actual probability
        # Skip this check as it's not valid for binary markets where probabilities can vary

        # Prices passed validation - update last valid prices
        self._last_valid_up = self.up
        self._last_valid_down = self.down
        # Don't reset anomaly count immediately - use gradual recovery above
        if self._price_anomaly_count == 0:
            self._price_anomaly_mode = False
        
        return True

    def _publish_prices(self) -> None:
        """Map per-token prices → (up, down) and emit a 'price' event."""
        # Use token_to_side mapping for reliable price assignment
        if not self._token_to_side:
            log.warning("Stream: No token_to_side mapping available - cannot map prices")
            return
        changed = False

        with self._price_lock:
            # Map token prices to UP/DOWN using the token_to_side mapping
            for token_id, price in self._token_prices.items():
                side = self._token_to_side.get(token_id)
                if side == "UP":
                    if self.up != price:
                        log.debug("Stream: UP price updated: %.6f -> %.6f (token=%s)", self.up, price, token_id[:12])
                        self.up = price
                        changed = True
                elif side == "DOWN":
                    if self.down != price:
                        log.debug("Stream: DOWN price updated: %.6f -> %.6f (token=%s)", self.down, price, token_id[:12])
                        self.down = price
                        changed = True
                else:
                    log.debug("Stream: Token %s not found in token_to_side mapping", token_id[:12])
            
            # Degenerate case: if both tokens share the same ID, derive complement
            # This should not happen in normal operation but handle it gracefully
            up_id = self.market.up_token
            down_id = self.market.down_token
            if up_id and down_id and up_id == down_id:
                if up_id in self._token_prices:
                    log.warning("Stream: Both tokens have same ID %s - this may indicate a configuration error", up_id[:12])
                    self.up = self._token_prices[up_id]
                    self.down = round(1.0 - self.up, PRICE_ROUNDING)
                    changed = True

            if changed:
                # Validate prices before updating
                if self._validate_prices():
                    self._last_price_time = time.time()
                    # Only emit if price change exceeds threshold
                    # For binary markets, use AND logic since both prices move together
                    # This prevents redundant emissions when only one price appears to change
                    up_change = abs(self.up - self._last_emitted_up)
                    down_change = abs(self.down - self._last_emitted_down)
                    
                    # Use OR logic but ensure prices are consistent (sum ≈ 1.0)
                    if (up_change > self._price_threshold or down_change > self._price_threshold):
                        # Additional check: for binary markets, both should move together
                        # If one changed significantly but the other didn't, it might be noise
                        price_sum = self.up + self.down
                        if abs(price_sum - 1.0) < 0.15:  # Only emit if prices are still consistent
                            self._emit("price", self.up, self.down)
                            self._last_emitted_up = self.up
                            self._last_emitted_down = self.down
                else:
                    # Price validation failed - use last valid prices
                    log.warning(
                        "Price validation failed - using last valid prices. Current: UP=%.4f DOWN=%.4f, Last valid: UP=%.4f DOWN=%.4f",
                        self.up, self.down, self._last_valid_up, self._last_valid_down
                    )
                    self.up = self._last_valid_up
                    self.down = self._last_valid_down
                    # Update timestamp to prevent stale data detection from triggering
                    self._last_price_time = time.time()
                    
                    # Emit price reset event to signal anomaly
                    self._emit("price_reset", self.up, self.down)

    # ── Event emission ─────────────────────────────────────────────────────────

    def _emit(self, event: str, *args) -> None:
        for fn in self._handlers.get(event, []):
            try:
                fn(*args)
            except Exception as exc:
                log.exception("Stream: handler '%s' raised: %s", event, exc)



