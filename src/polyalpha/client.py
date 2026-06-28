"""
polyalpha client — market discovery via deterministic slug generation.

Slug format: {asset}-updown-{timeframe}-{unix_end_ts}

The timestamp is the END of the window (window_start + interval_seconds).
The event has ONE market. That market's clobTokenIds JSON string contains
BOTH tokens: [up_token, down_token], aligned with the outcomes array.
"""

import time
import json as _json
import logging
import httpx

from .market import Market
from .stream import Stream
from .paper import PaperEngine
from .errors import MarketNotFound, MarketClosed
from .constants import GAMMA_API, TIMEFRAME_SECONDS, ASSETS, build_slug

log = logging.getLogger(__name__)


def _jloads(val, default):
    """JSON-decode a value if it's a string, else return as-is."""
    if isinstance(val, str):
        try:
            return _json.loads(val)
        except Exception:
            return default
    return val if val is not None else default


def _current_window_end(timeframe: str) -> int:
    """Return the Unix timestamp of the END of the current window."""
    interval = TIMEFRAME_SECONDS[timeframe]
    now = int(time.time())
    window_start = (now // interval) * interval
    return window_start + interval


def _candidate_window_ends(timeframe: str, count: int = 3) -> list[int]:
    """Return [current, next, next+1] window end timestamps to try."""
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
        Get the active market for an asset/timeframe pair.
        Uses deterministic slug generation — no search needed.

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
                return self._fetch_by_slug(slug)
            except MarketNotFound as exc:
                log.debug(f"Not found: {slug}")
                last_exc = exc
            except MarketClosed:
                log.debug(f"Closed: {slug}")
                continue

        raise MarketNotFound(
            f"No active {asset} {timeframe} market found. "
            f"Tried: {[build_slug(asset, timeframe, ts) for ts in candidates]}"
        )

    def get(self, slug: str) -> Market:
        """
        Get a market by exact event slug.

        Example:
            market = client.markets.get("btc-updown-5m-1751234700")
        """
        return self._fetch_by_slug(slug)

    def search(self, query: str, limit: int = 10) -> list[Market]:
        """
        Search open markets by keyword.

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
        return [self._parse_market_row(m) for m in rows]

    def available(self, timeframe: str = "5m") -> list[Market]:
        """
        Return currently active markets for all known assets at a timeframe.

        Example:
            for m in client.markets.available("5m"):
                print(m.slug, m.yes_price)
        """
        results = []
        for asset in ASSETS:
            try:
                results.append(self.latest(asset, timeframe))
            except MarketNotFound:
                pass
        return results

    # ------------------------------------------------------------------
    # Internal
    # ------------------------------------------------------------------

    def _fetch_by_slug(self, slug: str) -> Market:
        """
        Fetch event via /events?slug={slug} (list endpoint, returns array).
        404 or empty → MarketNotFound.
        """
        try:
            data = self._get("/events", params={"slug": slug})
        except httpx.HTTPStatusError as exc:
            if exc.response.status_code == 404:
                raise MarketNotFound(f"Event not found: {slug}") from exc
            raise

        # /events returns a list
        events = data if isinstance(data, list) else [data]
        events = [e for e in events if e]  # strip nulls

        if not events:
            raise MarketNotFound(f"Event not found: {slug}")

        event = events[0]
        markets = event.get("markets", [])
        if not markets:
            raise MarketNotFound(f"Event has no markets: {slug}")

        return self._parse_event(event, slug)

    def _parse_event(self, event: dict, slug: str) -> Market:
        """
        Parse a Gamma Up/Down event into a Market object.

        The event has ONE market. Its clobTokenIds JSON string holds
        BOTH token IDs aligned with the outcomes array:
            outcomes      = '["Up", "Down"]'
            clobTokenIds  = '["<up_token_id>", "<down_token_id>"]'
            outcomePrices = '["0.505", "0.495"]'
        """
        markets = event.get("markets", [])
        m = markets[0] if markets else {}

        outcomes   = _jloads(m.get("outcomes",      "[]"), [])
        token_ids  = _jloads(m.get("clobTokenIds",  "[]"), [])
        prices_raw = _jloads(m.get("outcomePrices", "[]"), [])

        log.debug(f"parse_event slug={slug} outcomes={outcomes} "
                  f"n_tokens={len(token_ids)} prices={prices_raw}")

        # Find Up / Down index in outcomes list
        def _find_idx(variants):
            for i, label in enumerate(outcomes):
                if any(v.lower() in str(label).lower() for v in variants):
                    return i
            return None

        up_idx   = _find_idx(["up", "higher", "greater"]) 
        down_idx = _find_idx(["down", "lower"])

        # Fallback order
        if up_idx is None:
            up_idx = 0
        if down_idx is None:
            down_idx = 1 if len(token_ids) > 1 else 0

        def _tok(idx: int) -> str:
            return str(token_ids[idx]) if idx < len(token_ids) else ""

        def _price(idx: int) -> float:
            if idx < len(prices_raw):
                try:
                    return float(prices_raw[idx])
                except (TypeError, ValueError):
                    pass
            # Fallback: mid from best bid/ask on the sub-market
            bid = m.get("bestBid")
            ask = m.get("bestAsk")
            if bid and ask:
                return round((float(bid) + float(ask)) / 2, 6)
            return 0.5

        up_token   = _tok(up_idx)
        down_token = _tok(down_idx)
        up_price   = _price(up_idx)
        down_price = _price(down_idx)

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
    def _parse_market_row(data: dict) -> Market:
        """Parse a raw /markets row (used by search())."""
        outcomes   = _jloads(data.get("outcomes"),      ["YES", "NO"])
        token_ids  = _jloads(data.get("clobTokenIds") or data.get("tokens"), [])
        prices_raw = _jloads(data.get("outcomePrices"), [])
        prices     = [float(p) for p in prices_raw] if prices_raw else []

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
            tokens      = token_ids,
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
                log.warning(
                    f"HTTP {exc.response.status_code} on attempt {attempt}: {url}"
                )
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