"""
Advanced order types — TP/SL, trailing stop, OCO.

Usage:
    python examples/advanced_orders.py
"""
import polyalpha

client = polyalpha.Client(balance=300, paper_mode="realistic")
market = client.markets.latest("BTC", "5m")

order = client.paper.buy_with_tp_sl(
    market,
    side="UP",
    amount=25,
    stop_loss_pct=3.0,
    take_profit_pct=5.0,
)
print(f"Bracket order (TP/SL): {order}")

oco_buy, oco_sell = client.paper.oco_order(
    market,
    side="UP",
    amount=20,
    stop_loss=0.80,
    take_profit=0.95,
)
print(f"OCO buy: {oco_buy}")
print(f"OCO sell: {oco_sell}")

trail_order = client.paper.buy(market, side="UP", amount=15)
client.paper.set_trailing_stop(market, side="UP", trail_distance=0.03)
print(f"Trailing stop set on: {trail_order}")

print(f"\nOpen orders: {len(client.paper.open())}")
client.paper.summary()
