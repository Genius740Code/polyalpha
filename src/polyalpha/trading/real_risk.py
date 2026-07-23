"""Risk management for real trading."""

from __future__ import annotations

import logging
from datetime import datetime, timezone
from typing import TYPE_CHECKING, Optional

if TYPE_CHECKING:
    from .real_config import RealTradingConfig
    from .real_orders import RealPosition

from ..core import RiskLimitExceeded

log = logging.getLogger(__name__)


class RiskManager:
    """Risk management for real trading."""

    def __init__(self, config: RealTradingConfig):
        self.config = config
        self.daily_pnl: float = 0.0
        self.daily_trades: int = 0
        self.daily_start_balance: float = 0.0
        self._last_reset_date: Optional[str] = None

    def validate_order(
        self,
        amount: float,
        balance: float,
        market,
        positions: dict[str, RealPosition],
    ) -> None:
        """Validate order against risk limits."""

        if amount > self.config.max_order_size:
            raise RiskLimitExceeded(
                f"Order amount ${amount:.2f} exceeds maximum ${self.config.max_order_size:.2f}"
            )

        current_exposure = self._get_market_exposure(market.id, positions)
        if current_exposure + amount > self.config.max_position_size:
            raise RiskLimitExceeded(
                f"Position would exceed maximum size ${self.config.max_position_size:.2f}"
            )

        open_positions = [p for p in positions.values() if not p.resolved]
        if len(open_positions) >= self.config.max_open_positions:
            raise RiskLimitExceeded(
                f"Maximum open positions ({self.config.max_open_positions}) reached"
            )

        if self.config.max_positions_per_market > 0:
            market_positions = [p for p in positions.values() if not p.resolved and p.market_id == market.id]
            if len(market_positions) >= self.config.max_positions_per_market:
                raise RiskLimitExceeded(
                    f"Maximum positions per market ({self.config.max_positions_per_market}) reached for market {market.id}"
                )

        if self.daily_pnl < -self.config.max_daily_loss:
            raise RiskLimitExceeded(
                f"Daily loss ${abs(self.daily_pnl):.2f} exceeds limit ${self.config.max_daily_loss:.2f}"
            )

        max_risk = balance * self.config.max_risk_per_trade
        if amount > max_risk:
            raise RiskLimitExceeded(
                f"Order amount ${amount:.2f} exceeds max risk ${max_risk:.2f} "
                f"({self.config.max_risk_per_trade:.1%})"
            )

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

    def _get_market_exposure(self, market_id: str, positions: dict[str, RealPosition]) -> float:
        exposure = 0.0
        for position in positions.values():
            if position.market_id == market_id and not position.resolved:
                exposure += position.cost_basis
        return exposure

    def _check_and_reset_daily(self) -> None:
        today = datetime.now(timezone.utc).date().isoformat()
        if self._last_reset_date != today:
            self.daily_pnl = 0.0
            self.daily_trades = 0
            self._last_reset_date = today
            log.info("RiskManager: Daily tracking reset for new day")

    def record_trade(self, pnl: float) -> None:
        self._check_and_reset_daily()
        self.daily_pnl += pnl
        self.daily_trades += 1
        log.debug("RiskManager: Recorded trade P&L: $%.2f (Daily: $%.2f, Trades: %d)",
                  pnl, self.daily_pnl, self.daily_trades)

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
