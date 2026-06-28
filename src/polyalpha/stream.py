"""
WebSocket streaming for Polymarket CLOB price feed.

Protocol:
  - Subscribe:  {"type": "market", "assets_ids": [up_token_id, down_token_id],
                 "custom_feature_enabled": true}
  - PING/PONG:  Client must send text "PING" every 10 s — server replies "PONG".
                Server also sends "PING"; reply immediately with "PONG".
                Miss the 10 s window → server drops the connection.
  - event_type: "book" | "price_change" | "last_trade_price" | "best_bid_ask"
                "new_market" | "market_resolved" | "tick_size_change"

Usage:
    stream = client.stream(market)

    @stream.on("price")
    def on_price(up: float, down: float):
        print(f"UP={up:.4f}  DOWN={down:.4f}")

    @stream.on("close")
    def on_close():
        print("Market resolved")

    stream.start()                  # blocking
    stream.start(background=True)   # daemon thread
    stream.stop()
"""

import json
import threading
import time
import logging
from collections import defaultdict
from typing import Callable

try:
    import websocket  # websocket-client
    _HAS_WS = True
except ImportError:
    _HAS_WS = False

from .constants import CLOB_WS
from .errors import StreamDisconnected

log = logging.getLogger(__name__)

EVENTS        = {"price", "book", "trade", "close", "error", "connect"}
PING_INTERVAL = 10   # seconds — must send text PING at least every 10 s


class Stream:
    """
    Real-time price stream for a Polymarket Up/Down market.

    Subscribes to both UP and DOWN token IDs via the CLOB market channel.

    Events
    ------
    price     (up: float, down: float)
    book      (data: dict)   raw order-book snapshot
    trade     (data: dict)   last matched trade
    close     ()             market resolved / WS closed cleanly
    error     (exc: Exception)
    connect   ()             fired on every successful (re)connect
    """

    def __init__(self, market, retries: int = 5, retry_delay: float = 3.0):
        if not _HAS_WS:
            raise ImportError(
                "websocket-client is required for streaming.\n"
                "Install: pip install websocket-client"
            )

        self.market      = market
        self.retries     = retries
        self.retry_delay = retry_delay

        self._handlers: dict[str, list[Callable]] = defaultdict(list)
        self._ws          = None
        self._ping_thread = None
        self._thread      = None
        self._stop_flag   = threading.Event()

        # Latest prices — readable at any time without a handler
        self.up:   float = market.yes_price
        self.down: float = market.no_price

        # Per-token mid prices, keyed by token_id string
        self._prices: dict[str, float] = {}

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def on(self, event: str):
        """
        Decorator to register an event handler.

            @stream.on("price")
            def handler(up, down): ...
        """
        if event not in EVENTS:
            raise ValueError(f"Unknown event '{event}'. Valid: {EVENTS}")
        def decorator(fn: Callable):
            self._handlers[event].append(fn)
            return fn
        return decorator

    def add_handler(self, event: str, fn: Callable):
        """Register a handler without using the decorator syntax."""
        if event not in EVENTS:
            raise ValueError(f"Unknown event '{event}'. Valid: {EVENTS}")
        self._handlers[event].append(fn)

    def start(self, background: bool = False):
        """
        Start the stream.

        Args:
            background: if True, runs in a daemon thread and returns
                        immediately. If False, blocks until stopped.
        """
        self._stop_flag.clear()
        if background:
            self._thread = threading.Thread(
                target=self._run_with_retry,
                daemon=True,
                name=f"polyalpha-stream-{self.market.slug}",
            )
            self._thread.start()
        else:
            self._run_with_retry()

    def stop(self):
        """Signal the stream to stop and close the WebSocket."""
        self._stop_flag.set()
        if self._ws:
            try:
                self._ws.close()
            except Exception:
                pass

    @property
    def running(self) -> bool:
        return self._thread is not None and self._thread.is_alive()

    # ------------------------------------------------------------------
    # Internal
    # ------------------------------------------------------------------

    def _run_with_retry(self):
        attempts = 0
        while not self._stop_flag.is_set():
            try:
                self._connect()
                attempts = 0  # reset counter on clean connect
            except StreamDisconnected as exc:
                attempts += 1
                if attempts > self.retries:
                    log.error("Stream: max retries exceeded")
                    self._emit("error", exc)
                    break
                delay = self.retry_delay * attempts
                log.warning(
                    f"Stream: disconnected, retry {attempts}/{self.retries} "
                    f"in {delay:.1f}s"
                )
                time.sleep(delay)
            except Exception as exc:
                log.exception(f"Stream: unexpected error: {exc}")
                self._emit("error", exc)
                break

    def _connect(self):
        # Subscribe to both UP and DOWN token IDs
        token_ids = [t for t in self.market.tokens if t]
        if not token_ids:
            raise StreamDisconnected("Market has no token IDs to subscribe to")

        ws = websocket.WebSocketApp(
            CLOB_WS,
            on_open    = lambda ws: self._on_open(ws, token_ids),
            on_message = self._on_message,
            on_error   = self._on_ws_error,
            on_close   = self._on_ws_close,
        )
        self._ws = ws

        # Disable the built-in binary WebSocket ping — we send text PING ourselves
        ws.run_forever(ping_interval=None, ping_timeout=None)

        if not self._stop_flag.is_set():
            raise StreamDisconnected("WebSocket closed unexpectedly")

    def _on_open(self, ws, token_ids: list[str]):
        log.info(f"Stream: connected, subscribing to {len(token_ids)} token(s)")

        sub = json.dumps({
            "type": "market",
            "assets_ids": token_ids,
            "custom_feature_enabled": True,
        })
        ws.send(sub)

        # Kick off client-side PING thread
        ping = threading.Thread(
            target=self._ping_loop,
            args=(ws,),
            daemon=True,
            name="polyalpha-ping",
        )
        ping.start()
        self._ping_thread = ping

        self._emit("connect")

    def _ping_loop(self, ws):
        """Send text 'PING' every 10 s to keep the server from dropping us."""
        while not self._stop_flag.is_set():
            time.sleep(PING_INTERVAL)
            if self._stop_flag.is_set():
                break
            try:
                ws.send("PING")
                log.debug("Stream: sent PING")
            except Exception:
                break  # connection gone; _on_ws_close will trigger retry

    def _on_message(self, ws, raw: str):
        # Server sends "PING" too — reply immediately
        if raw == "PING":
            try:
                ws.send("PONG")
                log.debug("Stream: replied PONG")
            except Exception:
                pass
            return

        if raw in ("PONG", "[]", ""):
            return

        try:
            msg = json.loads(raw)
        except (json.JSONDecodeError, TypeError):
            log.debug(f"Stream: non-JSON: {repr(raw[:80])}")
            return

        if isinstance(msg, list):
            for item in msg:
                if isinstance(item, dict):
                    self._dispatch(item)
        elif isinstance(msg, dict):
            self._dispatch(msg)

    def _dispatch(self, msg: dict):
        event_type = msg.get("event_type", "")

        if event_type == "price_change":
            self._handle_price_change(msg)

        elif event_type == "best_bid_ask":
            self._handle_best_bid_ask(msg)

        elif event_type == "book":
            self._emit("book", msg)
            self._handle_book_price(msg)

        elif event_type == "last_trade_price":
            self._handle_last_trade(msg)
            self._emit("trade", msg)

        elif event_type == "market_resolved":
            log.info("Stream: market resolved")
            self._emit("close")
            self.stop()

        else:
            log.debug(f"Stream: {event_type}: {str(msg)[:100]}")

    # ------------------------------------------------------------------
    # Price extraction helpers
    # ------------------------------------------------------------------

    def _handle_price_change(self, msg: dict):
        for pc in msg.get("price_changes", []):
            asset_id = pc.get("asset_id", "")
            try:
                bid = pc.get("best_bid")
                ask = pc.get("best_ask")
                if bid and ask and float(bid) > 0 and float(ask) > 0:
                    self._prices[asset_id] = round(
                        (float(bid) + float(ask)) / 2, 6
                    )
                elif pc.get("price"):
                    self._prices[asset_id] = float(pc["price"])
            except (TypeError, ValueError):
                pass
        self._update_and_emit()

    def _handle_best_bid_ask(self, msg: dict):
        asset_id = msg.get("asset_id", "")
        try:
            bid = msg.get("best_bid")
            ask = msg.get("best_ask")
            if bid and ask and float(bid) > 0 and float(ask) > 0:
                self._prices[asset_id] = round(
                    (float(bid) + float(ask)) / 2, 6
                )
        except (TypeError, ValueError):
            pass
        self._update_and_emit()

    def _handle_book_price(self, msg: dict):
        asset_id = msg.get("asset_id", "")
        try:
            bids = msg.get("bids", [])
            asks = msg.get("asks", [])
            if bids and asks:
                mid = round(
                    (float(bids[0]["price"]) + float(asks[0]["price"])) / 2, 6
                )
                self._prices[asset_id] = mid
        except (TypeError, ValueError, KeyError, IndexError):
            pass
        self._update_and_emit()

    def _handle_last_trade(self, msg: dict):
        asset_id = msg.get("asset_id", "")
        try:
            price = float(msg.get("price", 0))
            if price > 0:
                self._prices[asset_id] = price
        except (TypeError, ValueError):
            pass
        self._update_and_emit()

    def _update_and_emit(self):
        """Map per-token prices → (up, down) and emit 'price' event."""
        tokens = self.market.tokens
        if not tokens:
            return

        up_id   = tokens[0] if len(tokens) > 0 else None
        down_id = tokens[1] if len(tokens) > 1 else None

        changed = False

        if up_id and down_id and up_id == down_id:
            # Degenerate case: both tokens identical — derive down from complement
            if up_id in self._prices:
                p         = self._prices[up_id]
                self.up   = p
                self.down = round(1.0 - p, 6)
                changed   = True
        else:
            if up_id and up_id in self._prices:
                self.up = self._prices[up_id]
                changed = True
            if down_id and down_id in self._prices:
                self.down = self._prices[down_id]
                changed   = True

        if changed:
            self._emit("price", self.up, self.down)

    # ------------------------------------------------------------------
    # WebSocket callbacks
    # ------------------------------------------------------------------

    def _on_ws_error(self, ws, exc):
        log.warning(f"Stream: WS error: {exc}")
        # Don't emit here — the retry loop in _run_with_retry handles reconnect

    def _on_ws_close(self, ws, code, msg):
        log.info(f"Stream: closed (code={code})")

    def _emit(self, event: str, *args):
        for fn in self._handlers.get(event, []):
            try:
                fn(*args)
            except Exception as exc:
                log.exception(f"Stream: handler '{event}' raised: {exc}")