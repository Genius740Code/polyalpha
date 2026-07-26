"""
Cross-asset pair-sum scanner via OrderBookFeed.

Usage:
    python examples/pairsum_arb.py
"""
import polyalpha

client = polyalpha.Client()
markets = {
    "BTC": client.markets.latest("BTC", "15m"),
    "ETH": client.markets.latest("ETH", "15m"),
    "SOL": client.markets.latest("SOL", "15m"),
}

feeds = {name: client.orderbook(m) for name, m in markets.items()}

FAIR_SUM = 1.0
THRESHOLD_PCT = 1.0

for name, feed in feeds.items():
    feed.refresh()
    book = feed.book
    spread = (book.best_ask - book.best_bid) / book.mid_price * 100
    print(f"{name}: bid={book.best_bid:.4f} ask={book.best_ask:.4f} spread={spread:.2f}%")

btc_eth_sum = feeds["BTC"].book.mid_price + feeds["ETH"].book.mid_price
deviation = abs(btc_eth_sum - FAIR_SUM) / FAIR_SUM * 100

if deviation > THRESHOLD_PCT:
    print(f"\nARB SIGNAL: BTC+ETH sum={btc_eth_sum:.4f} deviates {deviation:.2f}% from fair value")
else:
    print(f"\nBTC+ETH sum={btc_eth_sum:.4f} within threshold ({deviation:.2f}%)")

for feed in feeds.values():
    feed.close()
