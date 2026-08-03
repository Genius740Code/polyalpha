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
    up = book.up
    down = book.down
    if up is None or up.best_bid <= 0:
        print(f"{name}: book unavailable")
        continue
    spread = (up.best_ask - up.best_bid) / up.best_bid * 100
    print(f"{name}: bid={up.best_bid:.4f} ask={up.best_ask:.4f} spread={spread:.2f}% "
          f"(DOWN mid={down.mid_price if down else 0.0:.4f})")

btc_eth_sum = feeds["BTC"].book.up_mid + feeds["ETH"].book.up_mid
deviation = abs(btc_eth_sum - FAIR_SUM) / FAIR_SUM * 100

if deviation > THRESHOLD_PCT:
    print(f"\nARB SIGNAL: BTC+ETH sum={btc_eth_sum:.4f} deviates {deviation:.2f}% from fair value")
else:
    print(f"\nBTC+ETH sum={btc_eth_sum:.4f} within threshold ({deviation:.2f}%)")

for feed in feeds.values():
    feed.close()
