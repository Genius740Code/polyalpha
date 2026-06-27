import time
import logging
import httpx

from .market import Market
from .stream import Stream
from .errors import MarketNotFound, MarketClosed
from .constants import GAMMA_API, SLUG_PATTERNS

log = logging.getLogger(__name__)


class MarketClient:

    def __init__(self, timeout: int = 10, retries: int = 3):
        self._timeout = timeout
        self._retries = retries

    # ------------------------------------------------------------------
    # Public
    # ------------------------------------------------------------------

    def latest(self, asset: str, timeframe: str = "5m") -> Market:
        """
        Get the newest active market for an asset/timeframe pair.

        Example:
            client.markets.latest("BTC", "5m")
        """
        asset = asset.upper()
        params = {
            "tag_slug": f"{asset.lower()}-up-down",
            "active": "true",
            "closed": "false",
            "limit": 20,
            "order": "end_date_min",
            "ascending": "true",
        }
        data = self._get("/markets", params=params)
        markets = data if isinstance(data, list) else data.get("markets", [])

        # Filter to the right timeframe by slug pattern prefix
        prefix = SLUG_PATTERNS.get(asset, {}).get(timeframe)
        if prefix:
            slug_prefix = prefix.split("{")[0]  # e.g. "btc-updown-5m-"
            markets = [m for m in markets if m.get("slug", "").startswith(slug_prefix)]

        if not markets:
            raise MarketNotFound(f"No active {asset} {timeframe} market found")

        # Pick the one expiring soonest (already sorted ascending by end_date_min)
        return self._parse(markets[0])

    def get(self, slug: str) -> Market:
        """
        Get a market by exact slug.

        Example:
            client.markets.get("btc-updown-5m-1751234000")
        """
        data = self._get("/markets", params={"slug": slug})
        markets = data if isinstance(data, list) else data.get("markets", [])

        if not markets:
            raise MarketNotFound(f"Market not found: {slug}")

        return self._parse(markets[0])

    def search(self, query: str, limit: int = 10) -> list[Market]:
        """
        Search open markets by keyword.

        Example:
            client.markets.search("ETH 5m")
        """
        data = self._get("/markets", params={
            "search": query,
            "active": "true",
            "closed": "false",
            "limit": limit,
        })
        markets = data if isinstance(data, list) else data.get("markets", [])
        return [self._parse(m) for m in markets]

    # ------------------------------------------------------------------
    # Internal
    # ------------------------------------------------------------------

    def _get(self, path: str, params: dict = None) -> dict | list:
        url = GAMMA_API + path
        last_exc = None

        for attempt in range(1, self._retries + 1):
            try:
                resp = httpx.get(url, params=params, timeout=self._timeout)
                resp.raise_for_status()
                return resp.json()
            except httpx.HTTPStatusError as exc:
                log.warning(f"HTTP {exc.response.status_code} on attempt {attempt}")
                last_exc = exc
                if exc.response.status_code < 500:
                    break  # don't retry 4xx
            except httpx.RequestError as exc:
                log.warning(f"Request error on attempt {attempt}: {exc}")
                last_exc = exc
            time.sleep(1.0 * attempt)

        raise last_exc

    @staticmethod
    def _parse(data: dict) -> Market:
        outcomes = data.get("outcomes", ["YES", "NO"])
        if isinstance(outcomes, str):
            import json as _json
            try:
                outcomes = _json.loads(outcomes)
            except Exception:
                outcomes = ["YES", "NO"]

        tokens_raw = data.get("tokens", []) or data.get("clobTokenIds", [])
        if isinstance(tokens_raw, str):
            import json as _json
            try:
                tokens_raw = _json.loads(tokens_raw)
            except Exception:
                tokens_raw = []

        # prices may come as outcomePrices or token-level
        prices_raw = data.get("outcomePrices", [])
        if isinstance(prices_raw, str):
            import json as _json
            try:
                prices_raw = _json.loads(prices_raw)
            except Exception:
                prices_raw = []
        prices = [float(p) for p in prices_raw] if prices_raw else []

        return Market(
            id           = data.get("conditionId") or data.get("id", ""),
            question     = data.get("question", ""),
            description  = data.get("description", ""),
            slug         = data.get("slug", ""),
            active       = bool(data.get("active", False)),
            closed       = bool(data.get("closed", False)),
            archived     = bool(data.get("archived", False)),
            start_time   = data.get("startDate") or data.get("start_date", ""),
            end_time     = data.get("endDate") or data.get("end_date", ""),
            volume       = float(data.get("volume", 0) or 0),
            liquidity    = float(data.get("liquidity", 0) or 0),
            outcomes     = outcomes,
            prices       = prices,
            tokens       = tokens_raw,
            raw          = data,
        )


class Client:

    def __init__(
        self,
        balance: float    = 100.0,
        timeout: int      = 10,
        retries: int      = 3,
        log_level: str    = "WARNING",
    ):
        logging.basicConfig(level=getattr(logging, log_level.upper(), logging.WARNING))

        self.markets = MarketClient(timeout=timeout, retries=retries)
        self._balance = balance
        self._timeout = timeout
        self._retries = retries

    def stream(self, market: Market, retries: int = None) -> Stream:
        """
        Create a WebSocket stream for a market.

        Example:
            stream = client.stream(market)

            @stream.on("price")
            def on_price(yes, no):
                print(yes, no)

            stream.start()
        """
        return Stream(
            market  = market,
            retries = retries if retries is not None else self._retries,
        )
