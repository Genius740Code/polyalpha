"""
Risk management — daily loss limit, position size cap, pre-trade checks.

Usage:
    python examples/risk_management.py
"""
import polyalpha
from polyalpha.orderbook import RiskManager

client = polyalpha.Client(balance=200)
market = client.markets.latest("BTC", "5m")

risk = RiskManager(
    daily_loss_limit=50.0,
    max_position_size=30.0,
    max_positions=3,
)

trades = [
    ("UP", 25),
    ("UP", 40),
    ("DOWN", 20),
    ("DOWN", 10),
    ("UP", 15),
]

for side, amount in trades:
    can_trade, reason = risk.can_trade(client.paper)
    valid_order, order_reason = risk.validate_order(amount)

    if not can_trade:
        print(f"SKIP ({side}, {amount}): {reason}")
    elif not valid_order:
        print(f"REJECT ({side}, {amount}): {order_reason}")
    else:
        order = client.paper.buy(market, side=side, amount=amount)
        print(f"EXECUTED ({side}, {amount}): {order}")
        risk.capture_trade(amount)

print(f"\nRisk stats: {risk.stats()}")
client.paper.summary()
