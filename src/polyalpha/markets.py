"""
Market discovery via the Polymarket Gamma API.

Slug format:  {asset}-updown-{timeframe}-{unix_end_ts}
              e.g.  btc-updown-5m-1751234700

The timestamp is the END of the prediction window
(window_start + interval_seconds).  We probe the current window plus
the next two so we always catch a market even if the clock is mid-window.
"""

from __future__ import annotations

import json as _json
import logging
import time
from typing import Any

import httpx

from .core import (
    ASSETS,
    GAMMA_API,
    TIMEFRAME_SECONDS,
    Market,
    MarketClosed,
    MarketNotFound,
    build_slug,
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


def _candidate_ends(timeframe: str, count: int = 3) -> list[int]:
    """Return [current, next, next+1] window-end timestamps to probe."""
    interval = TIMEFRAME_SECONDS[timeframe]
    current  = _current_window_end(timeframe)
    return [current + i * interval for i in range(count)]


# ── MarketClient ───────────────────────────────────────────────────────────────

class MarketClient:
    """
    Discover and fetch Polymarket Up/Down markets via the Gamma API.

    Access through ``client.markets`` — do not instantiate directly.
    """

    def __init__(self, timeout: int = 10, retries: int = 3):
        self._timeout = timeout
        self._retries = retries

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

    def get(self, slug: str) -> Market:
        """
        Fetch a market by its exact event slug.

        Example
        -------
        >>> market = client.markets.get("btc-updown-5m-1751234700")
        """
        return self._fetch_by_slug(slug)

    def search(self, query: str, limit: int = 10) -> list[Market]:
        """
        Search open markets by keyword.

        Example
        -------
        >>> markets = client.markets.search("ETH 15m")
        """
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
                return round((float(bid) + float(ask)) / 2, 6)
            return 0.5

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
                response = httpx.get(url, params=params, timeout=self._timeout)
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
                time.sleep(1.0 * attempt)

        raise last_exc  # type: ignore[misc]
