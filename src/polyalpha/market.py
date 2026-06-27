from dataclasses import dataclass, asdict
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

    raw_data: dict


    @property
    def url(self):
        return (
            "https://polymarket.com/event/"
            + self.slug
        )


    @property
    def raw(self):
        return self.raw_data


    def dump(self):
        """
        Return market as dictionary
        """

        return asdict(self)


    def json(self):
        """
        Return JSON representation
        """

        return json.dumps(
            self.dump(),
            indent=4
        )


    def print(self):
        """
        Print all market information
        """

        print("=" * 60)
        print("POLYALPHA MARKET")
        print("=" * 60)

        for key, value in self.dump().items():
            print(
                f"{key:<15}: {value}"
            )

        print(
            f"{'url':<15}: {self.url}"
        )


    def help(self):

        print("""
Market

Attributes
----------

id
question
description
slug

active
closed
archived

start_time
end_time

volume
liquidity

outcomes
prices
tokens

url
raw


Methods
-------

print()
dump()
json()
help()

        """)