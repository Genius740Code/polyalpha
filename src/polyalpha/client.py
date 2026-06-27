from .market import Market


class MarketClient:

    def latest(
        self,
        asset: str,
        timeframe: str = "5m"
    ):
        """
        Get the newest Polymarket market.

        Example:
            client.markets.latest("BTC", "5m")
        """

        # TODO:
        # Replace this with real Polymarket API call

        return Market(
            id="example-id",
            question=f"Will {asset} move in the next {timeframe}?",
            description="Crypto prediction market",
            slug="example-market",

            active=True,
            closed=False,
            archived=False,

            start_time="2026-01-01T00:00:00Z",
            end_time="2026-01-01T00:05:00Z",

            volume=10000.5,
            liquidity=5000.2,

            outcomes=[
                "YES",
                "NO"
            ],

            prices=[
                0.55,
                0.45
            ],

            tokens=[
                "yes-token",
                "no-token"
            ],

            raw_data={}
        )


class Client:

    def __init__(self):
        self.markets = MarketClient()