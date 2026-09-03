"""Risk management for real trading.

Refactored to inherit BaseRiskManager for shared daily/limits logic; retains
real-specific stop-loss/take-profit and position-sizing helpers.
"""

from __future__ import annotations

import logging
from datetime import datetime, timezone
from typing import TYPE_CHECKING, Optional

if TYPE_CHECKING:
    from .real_config import RealTradingConfig
    from .real_orders import RealPosition

from ..core import RiskLimitExceeded
from .base_risk import BaseRiskManager

log = logging.getLogger(__name__)


class RiskManager(BaseRiskManager):
    """Risk management for real trading — unified with BaseRiskManager."""

    def __init__(self, config: RealTradingConfig):
        super().__init__(config)
        self.daily_start_balance: float = 0.0
        self._last_reset_date: Optional[str] = None

    def validate_order(
        self,
        amount: float,
        balance: float,
        market,
        positions: dict[str, RealPosition],
    ) -> None:
        """Validate order against risk limits (delegates to BaseRiskManager)."""
        super()._check_limits(amount, market, positions)
        # keep daily loss check message compatibility (Base already checks)
        # extra: ensure daily reset
        self._check_and_reset_daily()

    def check_stop_loss(self, position: RealPosition, current_price: float) -> bool:
        """Check if stop loss should be triggered."""
        if position.stop_loss is None:
            return False

        if position.side == "UP":
            return current_price <= position.stop_loss
        else:
            return current_price >= position.stop_loss

    def check_take_profit(self, position: RealPosition, current_price: float) -> bool:
        """Check if take profit should be triggered."""
        if position.take_profit is None:
            return False

        if position.side == "UP":
            return current_price >= position.take_profit
        else:
            return current_price <= position.take_profit

    def calculate_position_size_with_risk(
        self,
        balance: float,
        entry_price: float,
        stop_loss: float,
        side: str,
    ) -> float:
        risk_amount = balance * self.config.max_risk_per_trade
        price_diff = abs(entry_price - stop_loss)

        if price_diff == 0:
            return balance * risk_amount

        position_size = risk_amount / (price_diff / entry_price)
        return min(position_size, balance)

    # _get_market_exposure, _check_and_reset_daily, record_trade inherited from BaseRiskManager
    # keep record_trade override for log prefix compat if needed
    def record_trade(self, pnl: float) -> None:  # type: ignore[override]
        super().record_trade(pnl)

    def initialize_daily_balance(self, balance: float) -> None:
        self._check_and_reset_daily()
        if self.daily_start_balance == 0.0:
            self.daily_start_balance = balance
            log.info("RiskManager: Daily start balance set to $%.2f", balance)

    def get_daily_stats(self) -> dict:
        self._check_and_reset_daily()
        pct_change = 0.0
        if self.daily_start_balance > 0:
            pct_change = (self.daily_pnl / self.daily_start_balance) * 100

        return {
            "daily_pnl": self.daily_pnl,
            "daily_trades": self.daily_trades,
            "daily_start_balance": self.daily_start_balance,
            "daily_pct_change": pct_change,
            "daily_loss_limit": self.config.max_daily_loss,
            "daily_loss_remaining": self.config.max_daily_loss + self.daily_pnl if self.daily_pnl < 0 else self.config.max_daily_loss,
        }
