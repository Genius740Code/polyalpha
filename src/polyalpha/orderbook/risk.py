"""
Risk management for order book strategies.
"""

from __future__ import annotations

from .models import BookSide, Order, Portfolio


class RiskManager:
    """Pre-trade risk checks for strategy orders."""

    def __init__(
        self,
        max_position_size: float = 1000.0,
        max_daily_loss: float = 0.05,
        max_order_size: float = 100.0,
    ):
        self.max_position_size = max_position_size
        self.max_daily_loss = max_daily_loss
        self.max_order_size = max_order_size
        self.daily_pnl = 0.0
        self.daily_trades = 0
        self.positions: dict[str, float] = {}

    async def validate_order(self, order: Order, portfolio: Portfolio) -> tuple[bool, str]:
        if order.quantity > self.max_order_size:
            return False, f"Order size exceeds maximum of {self.max_order_size}"

        symbol = order.side.value
        current = self.positions.get(symbol, 0.0)
        delta = order.quantity if order.side == BookSide.BUY else -order.quantity
        new_position = current + delta

        if abs(new_position) > self.max_position_size:
            return False, f"Position would exceed maximum of {self.max_position_size}"

        if self.daily_pnl < -self.max_daily_loss * portfolio.total_value:
            return False, f"Daily loss limit exceeded: {self.daily_pnl}"

        required = order.quantity * order.price
        if order.side == BookSide.BUY and portfolio.cash_balance < required:
            return False, f"Insufficient balance: {portfolio.cash_balance} < {required}"

        return True, "Order validated"

    async def check_position_limit(self, symbol: str, quantity: float) -> bool:
        current = self.positions.get(symbol, 0.0)
        return abs(current + quantity) <= self.max_position_size

    def update_daily_pnl(self, pnl: float) -> None:
        self.daily_pnl += pnl

    def reset_daily_limits(self) -> None:
        self.daily_pnl = 0.0
        self.daily_trades = 0
