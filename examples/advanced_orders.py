"""
Advanced order types — TP/SL, trailing stop, OCO.

Usage:
    python examples/advanced_orders.py
"""
import polyalpha
from polyalpha.trading.paper_config import get_paper_config_from_preset

client = polyalpha.Client(balance=300, paper_config=get_paper_config_from_preset("REALISTIC"))

# Use a distinct market per order type — the default config allows only one
# position per market, so stacking bracket + OCO + trailing on one market fails.
btc_market = client.markets.latest("BTC", "5m")
eth_market = client.markets.latest("ETH", "5m")
sol_market = client.markets.latest("SOL", "5m")

order = client.paper.buy_with_tp_sl(
    btc_market,
    side="UP",
    amount=25,
    stop_loss_pct=0.03,
    take_profit_pct=0.05,
)
print(f"Bracket order (TP/SL): {order}")

oco_buy, oco_sell = client.paper.oco_order(
    eth_market,
    side="UP",
    amount=20,
    stop_loss=0.80,
    take_profit=0.95,
)
print(f"OCO buy: {oco_buy}")
print(f"OCO sell: {oco_sell}")

trail_order = client.paper.buy(sol_market, side="UP", amount=15)
client.paper.set_trailing_stop(sol_market, side="UP", trail_distance=0.03)
print(f"Trailing stop set on: {trail_order}")

print(f"\nOpen orders: {len(client.paper.open())}")
client.paper.summary()
