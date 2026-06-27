"""
WebSocket streaming for Polymarket CLOB price feed.

Usage:
    stream = client.stream(market)

    @stream.on("price")
    def on_price(yes: float, no: float):
        print(f"YES={yes:.2f}  NO={no:.2f}")

    @stream.on("close")
    def on_close():
        print("Market resolved")

    stream.start()              # blocking
    stream.start(background=True)
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

EVENTS = {"price", "book", "trade", "close", "error", "connect"}


class Stream:
    """
    Real-time price stream for a single Polymarket market.

    Events
    ------
    price       (yes: float, no: float)
    book        (data: dict)   raw order book snapshot
    trade       (data: dict)   last matched trade
    close       ()             market resolved / WS closed cleanly
    error       (exc: Exception)
    connect     ()             fired on successful (re)connect
    """

    def __init__(self, market, retries: int = 5, retry_delay: float = 2.0):
        if not _HAS_WS:
            raise ImportError(
                "websocket-client is required for streaming. "
                "Install it with: pip install websocket-client"
            )

        self.market     = market
        self.retries    = retries
        self.retry_delay = retry_delay

        self._handlers: dict[str, list[Callable]] = defaultdict(list)
        self._ws        = None
        self._thread    = None
        self._stop_flag = threading.Event()

        # Latest prices — readable at any time
        self.yes: float = market.yes_price
        self.no: float  = market.no_price

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def on(self, event: str):
        """
        Decorator to register an event handler.

            @stream.on("price")
            def handler(yes, no): ...
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
                name=f"polyalpha-stream-{self.market.slug}"
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
                attempts = 0  # reset on clean connect
            except StreamDisconnected as exc:
                attempts += 1
                if attempts > self.retries:
                    log.error("Stream: max retries exceeded")
                    self._emit("error", exc)
                    break
                delay = self.retry_delay * attempts
                log.warning(f"Stream: disconnected, retry {attempts}/{self.retries} in {delay:.1f}s")
                time.sleep(delay)
            except Exception as exc:
                self._emit("error", exc)
                break

    def _connect(self):
        asset_id = self.market.yes_token

        ws = websocket.WebSocketApp(
            CLOB_WS,
            on_open    = lambda ws: self._on_open(ws, asset_id),
            on_message = self._on_message,
            on_error   = self._on_ws_error,
            on_close   = self._on_ws_close,
        )
        self._ws = ws

        # run_forever blocks; returns when socket closes
        ws.run_forever(ping_interval=20, ping_timeout=10)

        if not self._stop_flag.is_set():
            raise StreamDisconnected("WebSocket closed unexpectedly")

    def _on_open(self, ws, asset_id: str):
        log.info(f"Stream: connected — subscribing to {asset_id}")
        sub = json.dumps({
            "type": "subscribe",
            "markets": [asset_id],
        })
        ws.send(sub)
        self._emit("connect")

    def _on_message(self, ws, raw: str):
        try:
            msg = json.loads(raw)
        except json.JSONDecodeError:
            log.debug(f"Stream: non-JSON message: {raw!r}")
            return

        msg_type = msg.get("type", "")

        if msg_type == "last_trade_price":
            self._handle_price(msg)

        elif msg_type == "book":
            self._emit("book", msg)
            # also derive best price from book if available
            self._handle_book_price(msg)

        elif msg_type == "trade":
            self._emit("trade", msg)

        elif msg_type in ("market_ready", "market_closed"):
            if msg_type == "market_closed":
                log.info("Stream: market closed")
                self._emit("close")
                self.stop()

        else:
            log.debug(f"Stream: unhandled message type '{msg_type}'")

    def _handle_price(self, msg: dict):
        """Parse last_trade_price message and emit price event."""
        try:
            price = float(msg.get("price", 0))
            self.yes = price
            self.no  = round(1.0 - price, 6)
            self._emit("price", self.yes, self.no)
        except (TypeError, ValueError) as exc:
            log.debug(f"Stream: price parse error: {exc}")

    def _handle_book_price(self, msg: dict):
        """Derive mid price from best bid/ask in book snapshot."""
        try:
            bids = msg.get("bids", [])
            asks = msg.get("asks", [])
            if bids and asks:
                best_bid = float(bids[0]["price"])
                best_ask = float(asks[0]["price"])
                mid = round((best_bid + best_ask) / 2, 6)
                self.yes = mid
                self.no  = round(1.0 - mid, 6)
                self._emit("price", self.yes, self.no)
        except (TypeError, ValueError, KeyError) as exc:
            log.debug(f"Stream: book price parse error: {exc}")

    def _on_ws_error(self, ws, exc):
        log.warning(f"Stream: WebSocket error: {exc}")
        self._emit("error", exc)

    def _on_ws_close(self, ws, code, msg):
        log.info(f"Stream: closed (code={code})")

    def _emit(self, event: str, *args):
        for fn in self._handlers.get(event, []):
            try:
                fn(*args)
            except Exception as exc:
                log.exception(f"Stream: handler for '{event}' raised: {exc}")
