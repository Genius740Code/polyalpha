"""
PaperEngine basics — buy, sell, limit, attach_stream, summary.

Usage:
    python examples/paper.py
"""
import time

import polyalpha

client = polyalpha.Client(balance=200, paper_mode="realistic")
market = client.markets.latest("BTC", "5m")
print(f"Trading: {market}")

order1 = client.paper.buy(market, side="UP", amount=20)
print(f"Market buy: {order1}")

order2 = client.paper.limit(market, side="DOWN", price=0.10, amount=10)
print(f"Limit order: {order2}")

stream = client.stream(market)
client.paper.attach_stream(stream, market)

stream.start(background=True)

time.sleep(5)

positions = client.paper.positions()
print(f"\nOpen positions ({len(positions)}):")
for p in positions:
    print(f"  {p.side} size={p.size:.2f} entry={p.entry_price:.4f}")

if positions:
    closed = client.paper.sell_position(market, positions[0].side, amount=positions[0].size)
    print(f"\nClosed: {closed}")

print(f"\nBalance: {client.paper.balance:.2f}")
client.paper.summary()
