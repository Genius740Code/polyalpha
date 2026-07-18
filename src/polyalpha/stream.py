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

import json
import logging
import random
import threading
import time
from collections import defaultdict
from typing import Callable

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
)
from .markets import RateLimiter
from .trading.error_handling import CircuitBreaker

log = logging.getLogger(__name__)

# Event names exposed to callers
EVENTS = frozenset({"price", "book", "trade", "close", "error", "connect"})


class Stream:
    """
    Real-time price stream for a Polymarket Up/Down market.

    Subscribes to both UP and DOWN token IDs via the CLOB market channel,
    auto-reconnects on drops, and keeps the server alive with text PINGs.

    Events
    ------
    ``price``    (up: float, down: float)   — emitted on any mid-price change
    ``book``     (data: dict)               — raw order-book snapshot
    ``trade``    (data: dict)               — last matched trade
    ``close``    ()                         — market resolved / clean close
    ``error``    (exc: Exception)           — unrecoverable error
    ``connect``  ()                         — fired on every successful connect
    """

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
        self._thread:      threading.Thread | None = None
        self._stop:        threading.Event         = threading.Event()

        # Latest prices — always readable without a callback
        self.up:   float = market.up_price
        self.down: float = market.down_price

        # Track last emitted prices to avoid unnecessary events
        self._last_emitted_up:   float = self.up
        self._last_emitted_down: float = self.down

        # Rate limiter for WebSocket message processing (prevent message floods)
        self._message_rate_limiter = RateLimiter(
            max_requests=DEFAULT_RATE_LIMIT_MAX_REQUESTS,
            period_seconds=DEFAULT_RATE_LIMIT_PERIOD
        )

        # Mid-price per token ID (populated from WS events)
        self._token_prices: dict[str, float] = {}

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

    def stop(self) -> None:
        """Signal the stream to stop and close the WebSocket cleanly."""
        self._stop.set()
        if self._ws:
            try:
                self._ws.close()  # type: ignore[union-attr]
            except Exception:
                pass

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
        consecutive_failures = 0

        while not self._stop.is_set():
            # Check circuit breaker before attempting connection
            if self._circuit_breaker and self._circuit_breaker.is_open:
                log.warning("Stream: circuit breaker is open, blocking connection attempt")
                time.sleep(5)  # Wait before checking again
                continue

            try:
                if self._circuit_breaker:
                    self._circuit_breaker.call(self._connect)
                else:
                    self._connect()
                # _connect() returns only on a clean stop or market_resolved
                return

            except StreamDisconnected as exc:
                consecutive_failures += 1
                if consecutive_failures > self.retries:
                    log.error("Stream: max retries (%d) exceeded — giving up", self.retries)
                    self._emit("error", exc)
                    return

                # Calculate exponential backoff with jitter
                base_delay = self.retry_delay * (WS_BACKOFF_FACTOR ** (consecutive_failures - 1))
                jitter_amount = base_delay * WS_JITTER * (random.random() * 2 - 1)
                delay = max(0, base_delay + jitter_amount)
                
                log.warning(
                    "Stream: disconnected (attempt %d/%d) — retrying in %.1fs (with jitter)",
                    consecutive_failures, self.retries, delay,
                )
                time.sleep(delay)

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
        self._ws = ws

        # Disable the library's binary WebSocket ping — we use text PING/PONG
        ws.run_forever(ping_interval=None, ping_timeout=None)

        if not self._stop.is_set():
            raise StreamDisconnected("WebSocket closed unexpectedly")

    def _on_open(self, ws, token_ids: list[str]) -> None:
        log.info("Stream: connected — subscribing to %d token(s)", len(token_ids))

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
        """Send text 'PING' every WS_PING_INTERVAL seconds."""
        while not self._stop.is_set():
            time.sleep(WS_PING_INTERVAL)
            if self._stop.is_set():
                break
            try:
                self._last_ping_time = time.time()
                self._ping_count += 1
                ws.send("PING")
                log.debug("Stream: → PING")
            except Exception:
                break   # socket gone; _on_ws_close will trigger reconnect

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

    def _mid(self, bid: Any, ask: Any) -> float | None:
        """Return bid/ask mid-price, or None if either is absent/zero."""
        try:
            b, a = float(bid), float(ask)
            if b > 0 and a > 0:
                return round((b + a) / 2, PRICE_ROUNDING)
        except (TypeError, ValueError):
            pass
        return None

    def _set_token_price(self, token_id: str, price: float) -> None:
        if token_id and price > 0:
            self._token_prices[token_id] = price

    def _handle_price_change(self, msg: dict) -> None:
        for pc in msg.get("price_changes", []):
            asset_id = pc.get("asset_id", "")
            mid = self._mid(pc.get("best_bid"), pc.get("best_ask"))
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
        mid = self._mid(msg.get("best_bid"), msg.get("best_ask"))
        if mid is not None:
            self._set_token_price(asset_id, mid)
        self._publish_prices()

    def _handle_book(self, msg: dict) -> None:
        asset_id = msg.get("asset_id", "")
        try:
            bids = msg.get("bids", [])
            asks = msg.get("asks", [])
            if bids and asks:
                mid = self._mid(bids[0]["price"], asks[0]["price"])
                if mid is not None:
                    self._set_token_price(asset_id, mid)
        except (KeyError, IndexError):
            pass
        self._publish_prices()

    def _handle_last_trade(self, msg: dict) -> None:
        asset_id = msg.get("asset_id", "")
        try:
            price = float(msg.get("price", 0))
            self._set_token_price(asset_id, price)
        except (TypeError, ValueError):
            pass
        self._publish_prices()

    def _publish_prices(self) -> None:
        """Map per-token prices → (up, down) and emit a 'price' event."""
        tokens = self.market.tokens
        if not tokens:
            return

        up_id   = tokens[0] if tokens else None
        down_id = tokens[1] if len(tokens) > 1 else None
        changed = False

        # Degenerate case: both tokens share the same ID — derive complement
        if up_id and down_id and up_id == down_id:
            if up_id in self._token_prices:
                self.up   = self._token_prices[up_id]
                self.down = round(1.0 - self.up, PRICE_ROUNDING)
                changed   = True
        else:
            if up_id and up_id in self._token_prices:
                self.up  = self._token_prices[up_id]
                changed  = True
            if down_id and down_id in self._token_prices:
                self.down = self._token_prices[down_id]
                changed   = True

        if changed:
            # Only emit if price change exceeds threshold
            if (abs(self.up - self._last_emitted_up) >= self._price_threshold or
                abs(self.down - self._last_emitted_down) >= self._price_threshold):
                self._emit("price", self.up, self.down)
                self._last_emitted_up = self.up
                self._last_emitted_down = self.down

    # ── Event emission ─────────────────────────────────────────────────────────

    def _emit(self, event: str, *args) -> None:
        for fn in self._handlers.get(event, []):
            try:
                fn(*args)
            except Exception as exc:
                log.exception("Stream: handler '%s' raised: %s", event, exc)


# Type hint alias used inside _publish_prices
from typing import Any
