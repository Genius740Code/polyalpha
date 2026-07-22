"""Risk management for paper trading."""

from __future__ import annotations

import logging
from datetime import datetime, timezone
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from .paper_config import PaperConfig
    from .paper_types import PaperPosition

log = logging.getLogger(__name__)


class RiskManager:
    """Risk management for paper trading."""

    def __init__(self, config: PaperConfig, initial_balance: float):
        self.config = config
        self.daily_pnl: float = 0.0
        self.daily_trades: int = 0
        self.daily_start_balance: float = initial_balance
        self.daily_start_date: datetime = datetime.now(timezone.utc).date()

    def _check_day_reset(self) -> None:
        current_date = datetime.now(timezone.utc).date()
        if current_date != self.daily_start_date:
            log.info("RiskManager: New day detected, resetting daily limits")
            self.daily_pnl = 0.0
            self.daily_trades = 0
            self.daily_start_date = current_date

    def validate_order(
        self,
        amount: float,
        balance: float,
        market_id: str,
        positions: dict,
    ) -> None:
        if not self.config.enable_risk_management:
            return

        self._check_day_reset()

        if amount > self.config.max_order_size:
            raise ValueError(
                f"Order amount ${amount:.2f} exceeds maximum ${self.config.max_order_size:.2f}"
            )

        current_exposure = self._get_market_exposure(market_id, positions)
        if current_exposure + amount > self.config.max_position_size:
            raise ValueError(
                f"Position would exceed maximum size ${self.config.max_position_size:.2f} "
                f"(current: ${current_exposure:.2f}, adding: ${amount:.2f})"
            )

        open_positions = [p for p in positions.values() if not p.resolved]
        if len(open_positions) >= self.config.max_open_positions:
            raise ValueError(
                f"Maximum open positions ({self.config.max_open_positions}) reached"
            )

        if self.config.max_positions_per_market > 0:
            market_positions = [p for p in positions.values() if not p.resolved and p.market_id == market_id]
            if len(market_positions) >= self.config.max_positions_per_market:
                raise ValueError(
                    f"Maximum positions per market ({self.config.max_positions_per_market}) reached for market {market_id}"
                )

        if self.daily_pnl < -self.config.max_daily_loss:
            raise ValueError(
                f"Daily loss ${abs(self.daily_pnl):.2f} exceeds limit ${self.config.max_daily_loss:.2f}"
            )

        if self.daily_trades >= self.config.max_trades_per_day:
            raise ValueError(
                f"Maximum daily trades ({self.config.max_trades_per_day}) reached"
            )

        max_risk = balance * self.config.max_risk_per_trade
        if amount > max_risk:
            raise ValueError(
                f"Order amount ${amount:.2f} exceeds max risk ${max_risk:.2f} "
                f"({self.config.max_risk_per_trade:.1%} of balance)"
            )

        self.daily_trades += 1

    def _get_market_exposure(self, market_id: str, positions: dict) -> float:
        exposure = 0.0
        for pos in positions.values():
            if pos.market_id == market_id and not pos.resolved:
                exposure += pos.cost_basis
        return exposure

    def record_trade(self, pnl: float) -> None:
        self._check_day_reset()
        self.daily_pnl += pnl
        log.debug("RiskManager: Trade recorded - daily_pnl=$%.2f", self.daily_pnl)

    def get_summary(self) -> dict:
        self._check_day_reset()
        return {
            "daily_pnl": self.daily_pnl,
            "daily_trades": self.daily_trades,
            "daily_start_balance": self.daily_start_balance,
            "daily_date": self.daily_start_date.isoformat(),
            "max_daily_loss": self.config.max_daily_loss,
            "max_trades_per_day": self.config.max_trades_per_day,
            "remaining_loss_limit": max(0, self.config.max_daily_loss + self.daily_pnl),
            "remaining_trades": max(0, self.config.max_trades_per_day - self.daily_trades),
        }

    def reset_daily_limits(self) -> None:
        self.daily_pnl = 0.0
        self.daily_trades = 0
        self.daily_start_date = datetime.now(timezone.utc).date()
        log.info("RiskManager: Daily limits manually reset")

    def check_stop_loss(self, position: PaperPosition, current_price: float) -> bool:
        if position.stop_loss is None:
            return False
        if position.side == "UP":
            return current_price <= position.stop_loss
        else:
            return current_price >= position.stop_loss

    def check_take_profit(self, position: PaperPosition, current_price: float) -> bool:
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
            return min(risk_amount, balance)

        position_size = risk_amount / (price_diff / entry_price)
        return min(position_size, balance)
