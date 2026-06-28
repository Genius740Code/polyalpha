"""
polyalpha client — market discovery via deterministic slug generation.

Slug format: {asset}-updown-{timeframe}-{unix_end_ts}
The timestamp is the END of the window (window_start + interval_seconds).

Examples
--------
  btc-updown-5m-1751234700     # BTC 5m window ending at 1751234700
  eth-updown-15m-1751234700    # ETH 15m window ending at 1751234700
  sol-updown-1h-1751234000     # SOL 1h window
"""

import time
import logging
import httpx

from .market import Market
from .stream import Stream
from .paper import PaperEngine
from .errors import MarketNotFound, MarketClosed
from .constants import (
    GAMMA_API,
    TIMEFRAME_SECONDS,
    ASSETS,
    build_slug,
    slug_prefix,
)

log = logging.getLogger(__name__)


def _current_window_end(timeframe: str) -> int:
    """
    Return the Unix timestamp of the END of the current window.

    Polymarket slugs use the window end time.
    e.g. for 5m: floor(now / 300) * 300 + 300
    """
    interval = TIMEFRAME_SECONDS[timeframe]
    now = int(time.time())
    window_start = (now // interval) * interval
    return window_start + interval


def _candidate_window_ends(timeframe: str, count: int = 3) -> list[int]:
    """
    Return [current, next, next+1] window end timestamps.
    We try a few because a market might open slightly late or
    we might be at the very edge of a boundary.
    """
    interval = TIMEFRAME_SECONDS[timeframe]
    current = _current_window_end(timeframe)
    return [current + (i * interval) for i in range(count)]


class MarketClient:

    def __init__(self, timeout: int = 10, retries: int = 3):
        self._timeout = timeout
        self._retries = retries

    # ------------------------------------------------------------------
    # Public
    # ------------------------------------------------------------------

    def latest(self, asset: str, timeframe: str = "5m") -> Market:
        """
        Get the active market for an asset/timeframe using deterministic
        slug generation. Tries current window and up to 2 upcoming windows.

        Args:
            asset:     "BTC", "ETH", "SOL", "XRP", "DOGE"
            timeframe: "5m", "15m", "1h", "4h", "24h"

        Example:
            market = client.markets.latest("BTC", "5m")
            market = client.markets.latest("ETH", "15m")
        """
        asset = asset.upper()
        if asset not in ASSETS:
            raise ValueError(f"Unknown asset '{asset}'. Supported: {ASSETS}")
        if timeframe not in TIMEFRAME_SECONDS:
            raise ValueError(
                f"Unknown timeframe '{timeframe}'. "
                f"Supported: {list(TIMEFRAME_SECONDS)}"
            )

        candidates = _candidate_window_ends(timeframe)
        last_exc = None

        for end_ts in candidates:
            slug = build_slug(asset, timeframe, end_ts)
            log.debug(f"Trying slug: {slug}")
            try:
                return self._fetch_by_event_slug(slug)
            except MarketNotFound as exc:
                log.debug(f"Not found: {slug}")
                last_exc = exc
            except MarketClosed:
                log.debug(f"Closed: {slug}")
                continue

        raise MarketNotFound(
            f"No active {asset} {timeframe} market found. "
            f"Tried slugs: {[build_slug(asset, timeframe, ts) for ts in candidates]}"
        )

    def get(self, slug: str) -> Market:
        """
        Get a market by exact event slug.

        Example:
            market = client.markets.get("btc-updown-5m-1751234700")
        """
        return self._fetch_by_event_slug(slug)

    def search(self, query: str, limit: int = 10) -> list[Market]:
        """
        Search open markets by keyword via Gamma /markets endpoint.

        Example:
            markets = client.markets.search("ETH 15m")
        """
        data = self._get("/markets", params={
            "search": query,
            "active": "true",
            "closed": "false",
            "limit": limit,
        })
        rows = data if isinstance(data, list) else data.get("markets", [])
        return [self._parse_market(m) for m in rows]

    def available(self, timeframe: str = "5m") -> list[Market]:
        """
        Return currently active markets for all known assets
        at a given timeframe.

        Example:
            markets = client.markets.available("15m")
            for m in markets:
                print(m.slug, m.yes_price)
        """
        results = []
        for asset in ASSETS:
            try:
                m = self.latest(asset, timeframe)
                results.append(m)
            except MarketNotFound:
                pass
        return results

    # ------------------------------------------------------------------
    # Internal
    # ------------------------------------------------------------------

    def _fetch_by_event_slug(self, slug: str) -> Market:
        """
        Fetch via /events/slug/{slug}.
        404 → MarketNotFound (caller handles retry with next window).
        """
        try:
            data = self._get(f"/events/slug/{slug}")
        except httpx.HTTPStatusError as exc:
            if exc.response.status_code == 404:
                raise MarketNotFound(f"Event not found: {slug}") from exc
            raise

        if not data:
            raise MarketNotFound(f"Event not found: {slug}")

        markets = data.get("markets", [])
        if not markets:
            raise MarketNotFound(f"Event has no markets: {slug}")

        return self._parse_event(data, slug)

    def _parse_event(self, event: dict, slug: str) -> Market:
        """
        Parse a Gamma Up/Down event into a Market object.

        Each sub-market has a clobTokenIds field — a JSON-string list of
        [yes_token, no_token] for that sub-market. For Up/Down events:
          - Up sub-market:   clobTokenIds[0] = UP token
          - Down sub-market: clobTokenIds[0] = DOWN token
        We extract one token per sub-market and store as [up_token, down_token].
        """
        import json as _j

        markets = event.get("markets", [])

        # Sort into up/down by question text
        up_market   = next(
            (m for m in markets
             if any(w in m.get("question","").lower() for w in ("up", "higher", "greater"))),
            None
        )
        down_market = next(
            (m for m in markets
             if any(w in m.get("question","").lower() for w in ("down", "lower"))),
            None
        )

        # Fallback: index order
        if not up_market and markets:
            up_market = markets[0]
        if not down_market and len(markets) > 1:
            down_market = markets[1]

        def _price(m):
            if not m:
                return 0.5
            # outcomePrices is a JSON-string like "[\"0.505\", \"0.495\"]"
            raw = m.get("outcomePrices", "[]")
            if isinstance(raw, str):
                try:
                    raw = _j.loads(raw)
                except Exception:
                    raw = []
            if raw:
                try:
                    return float(raw[0])
                except Exception:
                    pass
            bid = m.get("bestBid")
            ask = m.get("bestAsk")
            if bid and ask:
                return round((float(bid) + float(ask)) / 2, 6)
            return 0.5

        def _token(m):
            """
            clobTokenIds is a JSON-string list like
            "[\"12345...\", \"67890...\"]"
            For Up/Down sub-markets the first entry is the outcome token.
            """
            if not m:
                return ""
            raw = m.get("clobTokenIds") or m.get("tokens", "[]")
            if isinstance(raw, str):
                try:
                    raw = _j.loads(raw)
                except Exception:
                    raw = []
            if isinstance(raw, list) and raw:
                return str(raw[0])
            return m.get("conditionId") or ""

        up_price   = _price(up_market)
        down_price = _price(down_market)
        up_token   = _token(up_market)
        down_token = _token(down_market)

        active = event.get("active", False) or any(
            m.get("active", False) for m in markets
        )
        closed = event.get("closed", False) and all(
            m.get("closed", True) for m in markets
        )

        if closed and not active:
            raise MarketClosed(f"Market is closed: {slug}")

        return Market(
            id          = event.get("id", ""),
            question    = event.get("title") or event.get("question", ""),
            description = event.get("description", ""),
            slug        = slug,
            active      = bool(active),
            closed      = bool(closed),
            archived    = bool(event.get("archived", False)),
            start_time  = event.get("startDate") or event.get("start_date", ""),
            end_time    = event.get("endDate")   or event.get("end_date", ""),
            volume      = float(event.get("volume", 0) or 0),
            liquidity   = float(event.get("liquidity", 0) or 0),
            outcomes    = ["UP", "DOWN"],
            prices      = [up_price, down_price],
            tokens      = [up_token, down_token],
            raw         = event,
        )

    @staticmethod
    def _parse_market(data: dict) -> Market:
        """Parse a raw /markets row (used by search())."""
        import json as _j

        def _loads(val, default):
            if isinstance(val, str):
                try:
                    return _j.loads(val)
                except Exception:
                    return default
            return val if val is not None else default

        outcomes = _loads(data.get("outcomes"), ["YES", "NO"])
        tokens   = _loads(data.get("clobTokenIds") or data.get("tokens"), [])
        prices_r = _loads(data.get("outcomePrices"), [])
        prices   = [float(p) for p in prices_r] if prices_r else []

        return Market(
            id          = data.get("conditionId") or data.get("id", ""),
            question    = data.get("question", ""),
            description = data.get("description", ""),
            slug        = data.get("slug", ""),
            active      = bool(data.get("active", False)),
            closed      = bool(data.get("closed", False)),
            archived    = bool(data.get("archived", False)),
            start_time  = data.get("startDate") or data.get("start_date", ""),
            end_time    = data.get("endDate")   or data.get("end_date", ""),
            volume      = float(data.get("volume", 0) or 0),
            liquidity   = float(data.get("liquidity", 0) or 0),
            outcomes    = outcomes,
            prices      = prices,
            tokens      = tokens,
            raw         = data,
        )

    def _get(self, path: str, params: dict = None) -> dict | list:
        url = GAMMA_API + path
        last_exc = None

        for attempt in range(1, self._retries + 1):
            try:
                resp = httpx.get(url, params=params, timeout=self._timeout)
                resp.raise_for_status()
                return resp.json()
            except httpx.HTTPStatusError as exc:
                log.warning(f"HTTP {exc.response.status_code} on attempt {attempt}: {url}")
                last_exc = exc
                if exc.response.status_code < 500:
                    break
            except httpx.RequestError as exc:
                log.warning(f"Request error on attempt {attempt}: {exc}")
                last_exc = exc
            time.sleep(1.0 * attempt)

        raise last_exc


class Client:

    def __init__(
        self,
        balance: float = 100.0,
        timeout: int   = 10,
        retries: int   = 3,
        log_level: str = "WARNING",
    ):
        logging.basicConfig(
            level=getattr(logging, log_level.upper(), logging.WARNING),
            format="%(levelname)s:%(name)s:%(message)s",
        )
        self.markets  = MarketClient(timeout=timeout, retries=retries)
        self.paper    = PaperEngine(balance=balance)
        self._balance = balance
        self._timeout = timeout
        self._retries = retries

    def stream(self, market: Market, retries: int = None) -> Stream:
        """
        Create a WebSocket price stream for a market.

        Example:
            stream = client.stream(market)

            @stream.on("price")
            def on_price(up, down):
                print(up, down)

            stream.start()
        """
        return Stream(
            market  = market,
            retries = retries if retries is not None else self._retries,
        )