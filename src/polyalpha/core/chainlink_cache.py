from __future__ import annotations

import logging
import threading
from datetime import datetime
from typing import Optional

log = logging.getLogger(__name__)


class ChainlinkPriceCache:
    """
    Runs a background :class:`ChainlinkStreamer` and caches the latest
    oracle price so every strategy reads from one connection instead of
    opening N WebSockets.

    Usage
    -----
        cache = ChainlinkPriceCache("BTC")
        price = cache.get_price("BTC")
        cache.stop()
    """

    def __init__(self, symbol: str = "BTC"):
        self._prices: dict[str, tuple[float, float]] = {}
        self._lock = threading.Lock()
        self._streamer: Optional[object] = None
        self._start(symbol)

    def _start(self, symbol: str) -> None:
        from ..analysis.streaming import ChainlinkStreamer

        self._streamer = ChainlinkStreamer()

        @self._streamer.on("price")
        def on_price(sym: str, price: float, timestamp: datetime) -> None:
            with self._lock:
                self._prices[sym] = (price, timestamp.timestamp())

        self._streamer.start(symbol, background=True)
        log.info("ChainlinkPriceCache started for %s", symbol)

    def get_price(self, symbol: str) -> Optional[float]:
        """Return the latest spot price for *symbol*, or *None* if not yet received."""
        with self._lock:
            entry = self._prices.get(symbol)
            return entry[0] if entry else None

    def stop(self) -> None:
        if self._streamer:
            try:
                self._streamer.stop()
            except Exception:
                pass
            self._streamer = None
            log.info("ChainlinkPriceCache stopped")
