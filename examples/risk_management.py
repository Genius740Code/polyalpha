"""
Risk management — position size cap, daily loss limit, pre-trade checks.

Demonstrates the orderbook RiskManager against a simulated portfolio.

Usage:
    python examples/risk_management.py
"""
import asyncio

from polyalpha.orderbook import (
    BookSide,
    Order,
    OrderStatus,
    OrderType,
    Portfolio,
    Position,
    RiskManager,
)

risk = RiskManager(
    max_order_size=25.0,
    max_position_size=30.0,
    max_daily_loss=0.05,
)

portfolio = Portfolio(
    user_id="demo",
    positions={},
    cash_balance=200.0,
    total_value=200.0,
)

trades = [
    ("UP", 25),
    ("UP", 40),
    ("DOWN", 20),
    ("DOWN", 10),
    ("UP", 15),
]


async def main():
    for i, (side, amount) in enumerate(trades):
        order = Order(
            id=f"order-{i}",
            user_id="demo",
            side=BookSide.BUY if side == "UP" else BookSide.SELL,
            order_type=OrderType.MARKET,
            price=0.50,
            quantity=amount,
            status=OrderStatus.FILLED,
        )

        valid, reason = await risk.validate_order(order, portfolio)

        if not valid:
            print(f"REJECT ({side}, {amount}): {reason}")
            continue

        # Simulate a fill: track the position and accrue daily P&L.
        symbol = order.side.value
        current = portfolio.positions.get(symbol, Position(symbol=symbol, quantity=0.0, average_price=0.50))
        current.quantity += amount if order.side == BookSide.BUY else -amount
        portfolio.positions[symbol] = current
        risk.update_daily_pnl(2.5 if side == "UP" else -1.5)
        print(f"EXECUTED ({side}, {amount}): validated")

    print(f"\nDaily P&L: ${risk.daily_pnl:.2f} | trades: {risk.daily_trades}")
    risk.reset_daily_limits()
    print(f"Limits reset — daily P&L: ${risk.daily_pnl:.2f}")


if __name__ == "__main__":
    asyncio.run(main())
