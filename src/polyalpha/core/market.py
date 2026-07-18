from __future__ import annotations

import json
from dataclasses import asdict, dataclass, field
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from polyalpha.markets import MarketClient


@dataclass
class Market:
    """
    A single Polymarket Up/Down event with both token legs resolved.

    Attributes
    ----------
    id          : Condition / event ID from the Gamma API.
    question    : Human-readable market question.
    description : Full event description.
    slug        : Deterministic event slug, e.g. "btc-updown-5m-1751234700".
    active      : True while the market is still accepting orders.
    closed      : True once the window has closed (result pending or settled).
    archived    : True when the event is fully settled and archived.
    start_time  : ISO-8601 window open time.
    end_time    : ISO-8601 window close time.
    volume      : Total USDC traded.
    liquidity   : Available USDC liquidity.
    outcomes    : Always ["UP", "DOWN"].
    prices      : [up_price, down_price] — mid of best bid/ask.
    tokens      : [up_token_id, down_token_id] — CLOB token IDs.
    raw         : Original API response (excluded from dump/json).
    """

    # ── Identity ───────────────────────────────────────────────────────────────
    id:          str
    question:    str
    description: str
    slug:        str

    # ── State ──────────────────────────────────────────────────────────────────
    active:   bool
    closed:   bool
    archived: bool

    # ── Timing ─────────────────────────────────────────────────────────────────
    start_time: str
    end_time:   str

    # ── Size ───────────────────────────────────────────────────────────────────
    volume:    float
    liquidity: float

    # ── Market data ────────────────────────────────────────────────────────────
    outcomes: list[str]
    prices:   list[float]
    tokens:   list[str]

    raw: dict = field(default_factory=dict, repr=False)

    # ── Computed properties ────────────────────────────────────────────────────

    @property
    def url(self) -> str:
        return f"https://polymarket.com/event/{self.slug}"

    @property
    def up_price(self) -> float:
        return self.prices[0] if self.prices else 0.0

    @property
    def down_price(self) -> float:
        return self.prices[1] if len(self.prices) > 1 else 0.0

    @property
    def up_token(self) -> str:
        return self.tokens[0] if self.tokens else ""

    @property
    def down_token(self) -> str:
        return self.tokens[1] if len(self.tokens) > 1 else ""

    # ── Serialisation ──────────────────────────────────────────────────────────

    def dump(self) -> dict:
        """Return the market as a plain dict (raw API response excluded)."""
        d = asdict(self)
        d.pop("raw", None)
        d["url"] = self.url
        return d

    def json(self, indent: int = 2) -> str:
        """Return a pretty JSON string of the market."""
        return json.dumps(self.dump(), indent=indent)

    # ── Refresh ─────────────────────────────────────────────────────────────────

    def refresh(self, client: MarketClient) -> "Market":
        """
        Re-fetch this market from the Gamma API.

        Returns a new Market instance with updated prices, closed status,
        volume, and liquidity. The original instance remains unchanged.

        Parameters
        ----------
        client : MarketClient - The client instance to use for re-fetching.

        Raises
        ------
        MarketNotFound  if the market no longer exists.
        MarketClosed    if the market has closed since last fetch.

        Example
        -------
        >>> market = client.markets.latest("BTC", "5m")
        >>> updated = market.refresh(client)
        """
        return client.get(self.slug)

    # ── Display ────────────────────────────────────────────────────────────────

    def show(self):
        """Print a formatted summary of the market to stdout."""
        W = 62
        print("─" * W)
        print(f"  {self.question}")
        print("─" * W)
        rows = [
            ("slug",      self.slug),
            ("id",        self.id),
            ("active",    self.active),
            ("closed",    self.closed),
            ("end_time",  self.end_time),
            ("volume",    f"${self.volume:,.2f}"),
            ("liquidity", f"${self.liquidity:,.2f}"),
            ("UP price",  f"{self.up_price:.4f}"),
            ("DOWN price",f"{self.down_price:.4f}"),
            ("UP token",  self.up_token or "(none)"),
            ("DOWN token",self.down_token or "(none)"),
            ("url",       self.url),
        ]
        for label, value in rows:
            print(f"  {label:<12} {value}")
        print("─" * W)
