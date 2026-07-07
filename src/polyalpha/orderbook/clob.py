"""
REST client for Polymarket CLOB order book endpoints.

Public endpoints — no authentication required.
"""

from __future__ import annotations

import logging
import time
from threading import Lock
from typing import Any

import httpx

from ..core.constants import (
    CLOB_API,
    HTTP_KEEPALIVE_EXPIRY,
    HTTP_MAX_CONNECTIONS,
    HTTP_MAX_KEEPALIVE_CONNECTIONS,
    HTTP_RETRY_DELAY_MULTIPLIER,
)
from ..core.errors import OrderBookError, OrderBookNotFound
from ..markets import RateLimiter
from .models import OrderBookSnapshot

log = logging.getLogger(__name__)


class ClobBookClient:
    """
    Fetch order books, prices, spreads, and midpoints from the Polymarket CLOB API.

    Parameters
    ----------
    timeout     : HTTP timeout in seconds.
    retries     : Retries on 5xx responses.
    rate_limit  : Max requests per second (None = unlimited).
    cache_ttl   : Seconds to cache book snapshots (0 = disabled).
    """

    def __init__(
        self,
        timeout: int = 10,
        retries: int = 3,
        rate_limit: int | None = None,
        cache_ttl: float = 2.0,
    ):
        self._timeout = timeout
        self._retries = retries
        self._cache_ttl = cache_ttl
        self._cache: dict[str, tuple[float, OrderBookSnapshot]] = {}
        self._cache_lock = Lock()
        self._rate_limiter = (
            RateLimiter(max_requests=rate_limit, period_seconds=1.0)
            if rate_limit
            else None
        )
        self._client = httpx.Client(
            timeout=timeout,
            limits=httpx.Limits(
                max_connections=HTTP_MAX_CONNECTIONS,
                max_keepalive_connections=HTTP_MAX_KEEPALIVE_CONNECTIONS,
                keepalive_expiry=HTTP_KEEPALIVE_EXPIRY,
            ),
        )

    def close(self) -> None:
        self._client.close()

    def __enter__(self) -> ClobBookClient:
        return self

    def __exit__(self, *args: Any) -> None:
        self.close()

    def _acquire(self) -> None:
        if self._rate_limiter:
            self._rate_limiter.acquire()

    def _request(
        self,
        method: str,
        path: str,
        *,
        params: dict[str, Any] | None = None,
        json: Any | None = None,
    ) -> Any:
        url = f"{CLOB_API}{path}"
        last_exc: Exception | None = None

        for attempt in range(1, self._retries + 1):
            self._acquire()
            try:
                response = self._client.request(method, url, params=params, json=json)
                if response.status_code == 404:
                    raise OrderBookNotFound(f"No order book at {path}")
                if response.status_code >= 500:
                    raise OrderBookError(f"CLOB server error {response.status_code}")
                response.raise_for_status()
                return response.json()
            except OrderBookNotFound:
                raise
            except Exception as exc:
                last_exc = exc
                if attempt < self._retries:
                    time.sleep(HTTP_RETRY_DELAY_MULTIPLIER * attempt)
                    continue
                break

        raise OrderBookError(f"CLOB request failed: {last_exc}") from last_exc

    def _get_cached(self, token_id: str) -> OrderBookSnapshot | None:
        if self._cache_ttl <= 0:
            return None
        with self._cache_lock:
            entry = self._cache.get(token_id)
            if entry and (time.time() - entry[0]) < self._cache_ttl:
                return entry[1]
        return None

    def _set_cached(self, token_id: str, snapshot: OrderBookSnapshot) -> None:
        if self._cache_ttl <= 0:
            return
        with self._cache_lock:
            self._cache[token_id] = (time.time(), snapshot)

    def get_book(self, token_id: str, *, use_cache: bool = True) -> OrderBookSnapshot:
        """Fetch full order book for a token."""
        if use_cache:
            cached = self._get_cached(token_id)
            if cached:
                return cached

        data = self._request("GET", "/book", params={"token_id": token_id})
        snapshot = OrderBookSnapshot.from_clob_response(data)
        self._set_cached(token_id, snapshot)
        return snapshot

    def get_books(self, token_ids: list[str]) -> dict[str, OrderBookSnapshot]:
        """Batch fetch up to 500 token order books."""
        if not token_ids:
            return {}

        payload = [{"token_id": token_id} for token_id in token_ids]
        data = self._request("POST", "/books", json=payload)
        books: dict[str, OrderBookSnapshot] = {}
        for item in data if isinstance(data, list) else []:
            snapshot = OrderBookSnapshot.from_clob_response(item)
            books[snapshot.token_id] = snapshot
            self._set_cached(snapshot.token_id, snapshot)
        return books

    def get_price(self, token_id: str, side: str = "BUY") -> float:
        """Best price for buying (BUY=ask) or selling (SELL=bid)."""
        data = self._request("GET", "/price", params={"token_id": token_id, "side": side.upper()})
        return float(data.get("price", 0))

    def get_midpoint(self, token_id: str) -> float:
        data = self._request("GET", "/midpoint", params={"token_id": token_id})
        return float(data.get("mid", 0))

    def get_spread(self, token_id: str) -> float:
        data = self._request("POST", "/spreads", json=[{"token_id": token_id}])
        if isinstance(data, dict):
            entry = data.get(token_id) or next(iter(data.values()), {})
            if isinstance(entry, dict):
                return float(entry.get("spread", 0))
            return float(entry)
        return 0.0

    def get_last_trade_price(self, token_id: str) -> dict[str, Any]:
        data = self._request("GET", "/last-trade-price", params={"token_id": token_id})
        return data if isinstance(data, dict) else {}

    def clear_cache(self) -> None:
        with self._cache_lock:
            self._cache.clear()
