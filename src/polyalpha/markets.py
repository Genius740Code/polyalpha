"""
Market discovery via the Polymarket Gamma API.

Slug format:  {asset}-updown-{timeframe}-{unix_end_ts}
              e.g.  btc-updown-5m-1751234700

The timestamp is the END of the prediction window
(window_start + interval_seconds).  We probe the current window plus
the next two so we always catch a market even if the clock is mid-window.
"""

from __future__ import annotations

import asyncio
import json as _json
import logging
import time
from threading import Lock
from typing import Any

import httpx

from .core import (
    ASSETS,
    TWEET_SUBJECTS,
    GAMMA_API,
    TIMEFRAME_SECONDS,
    HTTP_MAX_CONNECTIONS,
    HTTP_MAX_KEEPALIVE_CONNECTIONS,
    HTTP_KEEPALIVE_EXPIRY,
    HTTP_RETRY_DELAY_MULTIPLIER,
    MARKET_CANDIDATE_COUNT,
    DEFAULT_RATE_LIMIT_MAX_REQUESTS,
    DEFAULT_RATE_LIMIT_PERIOD,
    MAX_QUERY_LENGTH,
    MAX_SEARCH_LIMIT,
    MIN_SEARCH_LIMIT,
    DEFAULT_SEARCH_LIMIT,
    PRICE_ROUNDING,
    FALLBACK_PRICE,
    Market,
    MarketClosed,
    MarketNotFound,
    build_slug,
    build_tweet_slug,
)

log = logging.getLogger(__name__)


# ── Helpers ────────────────────────────────────────────────────────────────────

def _jloads(value: Any, default: Any) -> Any:
    """JSON-decode *value* if it is a string, otherwise return it as-is."""
    if isinstance(value, str):
        try:
            return _json.loads(value)
        except Exception:
            return default
    return value if value is not None else default


def _current_window_end(timeframe: str) -> int:
    """Return the Unix timestamp of the END of the window that contains now."""
    interval    = TIMEFRAME_SECONDS[timeframe]
    now         = int(time.time())
    window_start = (now // interval) * interval
    return window_start + interval


def _candidate_ends(timeframe: str, count: int = MARKET_CANDIDATE_COUNT) -> list[int]:
    """Return [current, next, next+1] window-end timestamps to probe."""
    interval = TIMEFRAME_SECONDS[timeframe]
    current  = _current_window_end(timeframe)
    return [current + i * interval for i in range(count)]


class RateLimiter:
    """Token bucket rate limiter for API requests."""

    def __init__(self, max_requests: int, period_seconds: float = 1.0):
        """
        Initialize rate limiter.

        Parameters
        ----------
        max_requests    : Maximum number of requests allowed per period.
        period_seconds  : Time window in seconds (default 1.0).
        """
        self.max_requests = max_requests
        self.period = period_seconds
        self.tokens = float(max_requests)
        self.last_update = time.time()
        self._lock = Lock()

    def acquire(self) -> None:
        """Block until a token is available."""
        wait_time = 0.0
        with self._lock:
            now = time.time()
            elapsed = now - self.last_update
            
            # Refill tokens based on elapsed time
            self.tokens = min(
                float(self.max_requests),
                self.tokens + elapsed * (self.max_requests / self.period)
            )
            self.last_update = now
            
            if self.tokens < 1:
                # Queue request by allowing tokens to go negative, compute wait
                wait_time = (1 - self.tokens) * (self.period / self.max_requests)
                self.tokens -= 1
            else:
                self.tokens -= 1
                
        if wait_time > 0:
            time.sleep(wait_time)

    async def acquire_async(self) -> None:
        """Async version - wait until a token is available."""
        wait_time = 0.0
        with self._lock:
            now = time.time()
            elapsed = now - self.last_update
            
            # Refill tokens based on elapsed time
            self.tokens = min(
                float(self.max_requests),
                self.tokens + elapsed * (self.max_requests / self.period)
            )
            self.last_update = now
            
            if self.tokens < 1:
                # Queue request by allowing tokens to go negative, compute wait
                wait_time = (1 - self.tokens) * (self.period / self.max_requests)
                self.tokens -= 1
            else:
                self.tokens -= 1
                
        if wait_time > 0:
            await asyncio.sleep(wait_time)


# ── MarketClient ───────────────────────────────────────────────────────────────

class MarketClient:
    """
    Discover and fetch Polymarket Up/Down markets via the Gamma API.

    Access through ``client.markets`` — do not instantiate directly.

    Parameters
    ----------
    timeout    : HTTP request timeout in seconds (default 10).
    retries    : Number of HTTP retries on 5xx errors (default 3).
    rate_limit : Max API requests per second (default None = unlimited).
                 Uses token-bucket algorithm with 1-second window.
    """

    def __init__(
        self,
        timeout: int = 10,
        retries: int = 3,
        rate_limit: int | None = None,
    ):
        self._timeout = timeout
        self._retries = retries
        self._rate_limiter = RateLimiter(rate_limit) if rate_limit else None
        
        # Configure HTTP client with connection pooling
        limits = httpx.Limits(
            max_keepalive_connections=HTTP_MAX_KEEPALIVE_CONNECTIONS,
            max_connections=HTTP_MAX_CONNECTIONS,
            keepalive_expiry=HTTP_KEEPALIVE_EXPIRY,
        )
        self._client = httpx.Client(
            timeout=timeout,
            limits=limits,
            http2=True,
        )

    # ── Public API ─────────────────────────────────────────────────────────────

    def latest(self, asset: str, timeframe: str = "5m") -> Market:
        """
        Return the active market for an asset/timeframe pair.

        Uses deterministic slug generation — no search needed.

        Parameters
        ----------
        asset     : "BTC" | "ETH" | "SOL" | "XRP" | "DOGE"
        timeframe : "5m" | "15m" | "1h" | "4h" | "24h"

        Raises
        ------
        ValueError       if asset or timeframe is unrecognised.
        MarketNotFound   if no active market exists for that window.

        Example
        -------
        >>> market = client.markets.latest("BTC", "5m")
        """
        asset     = asset.upper()
        timeframe = timeframe.lower()

        if asset not in ASSETS:
            raise ValueError(f"Unknown asset '{asset}'. Supported: {ASSETS}")
        if timeframe not in TIMEFRAME_SECONDS:
            raise ValueError(
                f"Unknown timeframe '{timeframe}'. "
                f"Supported: {list(TIMEFRAME_SECONDS)}"
            )

        candidates = _candidate_ends(timeframe)
        for end_ts in candidates:
            slug = build_slug(asset, timeframe, end_ts)
            log.debug("Trying slug: %s", slug)
            try:
                return self._fetch_by_slug(slug)
            except MarketNotFound:
                log.debug("Not found: %s", slug)
            except MarketClosed:
                log.debug("Closed: %s", slug)

        tried = [build_slug(asset, timeframe, ts) for ts in candidates]
        raise MarketNotFound(
            f"No active {asset} {timeframe} market found. Tried: {tried}"
        )

    def latest_tweet(self, subject: str, window: str = "7d") -> Market:
        """
        Return the active tweet market for a subject and window.
        
        Because tweet markets use rolling date windows, this probes 
        the current date and combinations of offsets.
        
        Parameters
        ----------
        subject : "elon-musk" | "white-house" | "zelensky"
        window  : "3d" | "7d" | "1mo"
        """
        subject = subject.lower()
        if subject not in TWEET_SUBJECTS:
            raise ValueError(f"Unknown subject '{subject}'. Supported: {TWEET_SUBJECTS}")
            
        now_ts = int(time.time())
        tried = []
        
        if window == "1mo":
            slug = build_tweet_slug(subject, now_ts, monthly=True)
            tried.append(slug)
            try:
                return self._fetch_by_slug(slug)
            except (MarketNotFound, MarketClosed):
                pass
        else:
            days = 7 if window == "7d" else 3
            # Probe combinations of start offsets
            # usually markets are active for current days
            for offset_start in range(-days, 1):
                start_ts = now_ts + (offset_start * 86400)
                end_ts = start_ts + (days * 86400)
                
                slug = build_tweet_slug(subject, start_ts, end_ts)
                if slug in tried:
                    continue
                tried.append(slug)
                try:
                    return self._fetch_by_slug(slug)
                except (MarketNotFound, MarketClosed):
                    pass
                    
        raise MarketNotFound(
            f"No active {subject} {window} tweet market found. Tried: {tried}"
        )

    def get(self, slug: str) -> Market:
        """
        Fetch a market by its exact event slug.

        Example
        -------
        >>> market = client.markets.get("btc-updown-5m-1751234700")
        """
        return self._fetch_by_slug(slug)

    def search(self, query: str, limit: int = DEFAULT_SEARCH_LIMIT) -> list[Market]:
        """
        Search open markets by keyword.

        Example
        -------
        >>> markets = client.markets.search("ETH 15m")
        """
        # Sanitize input
        if not isinstance(query, str):
            raise ValueError(f"Query must be a string, got {type(query).__name__}")
        
        query = query.strip()
        if len(query) == 0:
            raise ValueError("Query cannot be empty")
        if len(query) > MAX_QUERY_LENGTH:
            raise ValueError(f"Query too long (max {MAX_QUERY_LENGTH} characters)")
        
        # Sanitize limit
        if not isinstance(limit, int):
            raise ValueError(f"Limit must be an integer, got {type(limit).__name__}")
        if limit < MIN_SEARCH_LIMIT or limit > MAX_SEARCH_LIMIT:
            raise ValueError(f"Limit must be between {MIN_SEARCH_LIMIT} and {MAX_SEARCH_LIMIT}")
        
        data = self._get("/markets", params={
            "search": query,
            "active": "true",
            "closed": "false",
            "limit":  limit,
        })
        rows = data if isinstance(data, list) else data.get("markets", [])
        return [self._parse_market_row(row) for row in rows]

    def available(self, timeframe: str = "5m") -> list[Market]:
        """
        Return active markets for all known assets at a given timeframe.

        Example
        -------
        >>> for m in client.markets.available("5m"):
        ...     print(m.slug, m.up_price)
        """
        markets = []
        for asset in ASSETS:
            try:
                markets.append(self.latest(asset, timeframe))
            except MarketNotFound:
                pass
        return markets

    # ── Internal — slug fetch & event parsing ──────────────────────────────────

    def _fetch_by_slug(self, slug: str) -> Market:
        """Fetch an event by slug via GET /events?slug=… and parse it."""
        try:
            data = self._get("/events", params={"slug": slug})
        except httpx.HTTPStatusError as exc:
            if exc.response.status_code == 404:
                raise MarketNotFound(f"Event not found: {slug}") from exc
            raise

        events = data if isinstance(data, list) else [data]
        events = [e for e in events if e]

        if not events:
            raise MarketNotFound(f"Event not found: {slug}")

        event   = events[0]
        markets = event.get("markets", [])
        if not markets:
            raise MarketNotFound(f"Event has no markets: {slug}")

        return self._parse_event(event, slug)

    def _parse_event(self, event: dict, slug: str) -> Market:
        """
        Parse a Gamma Up/Down event dict into a Market object.

        Each event has ONE sub-market whose ``clobTokenIds`` JSON string
        holds *both* token IDs aligned with the ``outcomes`` array:

            outcomes      = '["Up", "Down"]'
            clobTokenIds  = '["<up_id>", "<down_id>"]'
            outcomePrices = '["0.55", "0.45"]'
        """
        markets    = event.get("markets", [])
        m          = markets[0] if markets else {}

        outcomes   = _jloads(m.get("outcomes",      "[]"), [])
        token_ids  = _jloads(m.get("clobTokenIds",  "[]"), [])
        prices_raw = _jloads(m.get("outcomePrices", "[]"), [])

        log.debug(
            "parse_event slug=%s outcomes=%s n_tokens=%d prices=%s",
            slug, outcomes, len(token_ids), prices_raw,
        )

        # Locate UP / DOWN positions within the outcomes array
        def _find_index(variants: list[str]) -> int | None:
            for i, label in enumerate(outcomes):
                if any(v.lower() in str(label).lower() for v in variants):
                    return i
            return None

        up_idx   = _find_index(["up", "higher", "greater"]) or 0
        down_idx = _find_index(["down", "lower"])
        if down_idx is None:
            down_idx = 1 if len(token_ids) > 1 else 0

        def _token(idx: int) -> str:
            return str(token_ids[idx]) if idx < len(token_ids) else ""

        def _price(idx: int) -> float:
            try:
                if idx < len(prices_raw):
                    return float(prices_raw[idx])
            except (TypeError, ValueError):
                pass
            # Fallback: mid of best bid/ask on the sub-market
            bid = m.get("bestBid")
            ask = m.get("bestAsk")
            if bid and ask:
                return round((float(bid) + float(ask)) / 2, PRICE_ROUNDING)
            return FALLBACK_PRICE

        active = event.get("active", False) or any(
            sub.get("active", False) for sub in markets
        )
        closed = event.get("closed", False) and all(
            sub.get("closed", True) for sub in markets
        )

        if closed and not active:
            raise MarketClosed(f"Market is closed: {slug}")

        return Market(
            id          = str(event.get("id", "")),
            question    = event.get("title") or event.get("question", ""),
            description = event.get("description", ""),
            slug        = slug,
            active      = bool(active),
            closed      = bool(closed),
            archived    = bool(event.get("archived", False)),
            start_time  = event.get("startDate") or event.get("start_date", ""),
            end_time    = event.get("endDate")   or event.get("end_date", ""),
            volume      = float(event.get("volume",    0) or 0),
            liquidity   = float(event.get("liquidity", 0) or 0),
            outcomes    = ["UP", "DOWN"],
            prices      = [_price(up_idx), _price(down_idx)],
            tokens      = [_token(up_idx), _token(down_idx)],
            raw         = event,
        )

    @staticmethod
    def _parse_market_row(data: dict) -> Market:
        """Parse a raw /markets row (used by search())."""
        outcomes   = _jloads(data.get("outcomes"),                    ["YES", "NO"])
        token_ids  = _jloads(data.get("clobTokenIds") or data.get("tokens"), [])
        prices_raw = _jloads(data.get("outcomePrices"), [])
        prices     = [float(p) for p in prices_raw] if prices_raw else []

        return Market(
            id          = data.get("conditionId") or data.get("id", ""),
            question    = data.get("question", ""),
            description = data.get("description", ""),
            slug        = data.get("slug", ""),
            active      = bool(data.get("active",   False)),
            closed      = bool(data.get("closed",   False)),
            archived    = bool(data.get("archived", False)),
            start_time  = data.get("startDate") or data.get("start_date", ""),
            end_time    = data.get("endDate")   or data.get("end_date", ""),
            volume      = float(data.get("volume",    0) or 0),
            liquidity   = float(data.get("liquidity", 0) or 0),
            outcomes    = outcomes,
            prices      = prices,
            tokens      = token_ids,
            raw         = data,
        )

    # ── HTTP ───────────────────────────────────────────────────────────────────

    def _get(self, path: str, params: dict | None = None) -> dict | list:
        """
        GET ``GAMMA_API + path`` with retries and exponential back-off.

        Retries on 5xx and network errors; raises immediately on 4xx.
        """
        url      = GAMMA_API + path
        last_exc: Exception | None = None

        for attempt in range(1, self._retries + 1):
            try:
                # Apply rate limiting if enabled
                if self._rate_limiter:
                    self._rate_limiter.acquire()

                response = self._client.get(url, params=params)
                response.raise_for_status()
                return response.json()

            except httpx.HTTPStatusError as exc:
                log.warning(
                    "HTTP %d on attempt %d/%d: %s",
                    exc.response.status_code, attempt, self._retries, url,
                )
                last_exc = exc
                if exc.response.status_code < 500:
                    break   # 4xx — retrying won't help

            except httpx.RequestError as exc:
                log.warning("Network error on attempt %d/%d: %s", attempt, self._retries, exc)
                last_exc = exc

            if attempt < self._retries:
                time.sleep(HTTP_RETRY_DELAY_MULTIPLIER * attempt)

        raise last_exc  # type: ignore[misc]

    def close(self) -> None:
        """Close the HTTP client and release resources."""
        if hasattr(self, '_client'):
            self._client.close()

    def __enter__(self):
        """Context manager entry."""
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        """Context manager exit - ensures client is closed."""
        self.close()
        return False
