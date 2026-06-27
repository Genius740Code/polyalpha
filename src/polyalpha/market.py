from dataclasses import dataclass, field, asdict
import json


@dataclass
class Market:

    id: str
    question: str
    description: str
    slug: str

    active: bool
    closed: bool
    archived: bool

    start_time: str
    end_time: str

    volume: float
    liquidity: float

    outcomes: list
    prices: list
    tokens: list

    raw: dict = field(default_factory=dict, repr=False)


    @property
    def url(self) -> str:
        return "https://polymarket.com/event/" + self.slug

    @property
    def yes_price(self) -> float:
        return self.prices[0] if self.prices else 0.0

    @property
    def no_price(self) -> float:
        return self.prices[1] if len(self.prices) > 1 else 0.0

    @property
    def yes_token(self) -> str:
        return self.tokens[0] if self.tokens else ""

    @property
    def no_token(self) -> str:
        return self.tokens[1] if len(self.tokens) > 1 else ""


    def dump(self) -> dict:
        """Return market as dictionary (excludes raw)."""
        d = asdict(self)
        d.pop("raw", None)
        d["url"] = self.url
        return d


    def json(self) -> str:
        """Return JSON representation."""
        return json.dumps(self.dump(), indent=4)


    def show(self):
        """Print all market information."""
        print("=" * 60)
        print("POLYALPHA MARKET")
        print("=" * 60)
        for key, value in self.dump().items():
            print(f"{key:<15}: {value}")


    def help(self):
        print("""
Market

Attributes
----------
id              condition ID
question        market question string
description
slug            e.g. btc-updown-5m-1751234000
active / closed / archived
start_time / end_time
volume / liquidity
outcomes        ["YES", "NO"]
prices          [yes_price, no_price]
tokens          [yes_token_id, no_token_id]
raw             raw API response dict

Computed
--------
url             polymarket.com link
yes_price / no_price
yes_token / no_token

Methods
-------
show()          print all fields
dump()          dict (excludes raw)
json()          JSON string
help()
        """)
