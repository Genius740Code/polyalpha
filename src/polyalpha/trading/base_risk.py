"""Shared risk management base for paper and real engines."""

from __future__ import annotations

import logging
from datetime import datetime, timezone

from ..core import RiskLimitExceeded

log = logging.getLogger(__name__)


class BaseRiskManager:
    """Shared risk checks used by both paper and real engines."""

    def __init__(self, config):
        self.config = config
        self.daily_pnl: float = 0.0
        self.daily_trades: int = 0
        self._last_reset_date: str | None = None

    def _check_and_reset_daily(self) -> None:
        today = datetime.now(timezone.utc).date().isoformat()
        if self._last_reset_date != today:
            self.daily_pnl = 0.0
            self.daily_trades = 0
            self._last_reset_date = today

    def _check_limits(
        self,
        amount: float,
        market,
        positions: dict,
        *,
        market_id: str | None = None,
        enable_risk: bool = True,
    ) -> None:
        if not enable_risk:
            return
        self._check_and_reset_daily()
        mid = market_id or getattr(market, "id", None) or str(market)
        max_order = getattr(self.config, "max_order_size", float("inf"))
        if amount > max_order:
            raise RiskLimitExceeded(f"Order amount ${amount:.2f} exceeds maximum ${max_order:.2f}")

        max_pos = getattr(self.config, "max_position_size", float("inf"))
        exposure = self._get_market_exposure(mid, positions)
        if exposure + amount > max_pos:
            raise RiskLimitExceeded(f"Position would exceed maximum size ${max_pos:.2f}")

        max_open = getattr(self.config, "max_open_positions", float("inf"))
        open_positions = [p for p in positions.values() if not getattr(p, "resolved", False)]
        if len(open_positions) >= max_open:
            raise RiskLimitExceeded(f"Maximum open positions ({max_open}) reached")

        max_per_market = getattr(self.config, "max_positions_per_market", 0)
        if max_per_market and max_per_market > 0:
            market_positions = [p for p in positions.values() if not getattr(p, "resolved", False) and getattr(p, "market_id", None) == mid]
            if len(market_positions) >= max_per_market:
                raise RiskLimitExceeded(f"Maximum positions per market ({max_per_market}) reached for market {mid}")

        max_daily_loss = getattr(self.config, "max_daily_loss", float("inf"))
        if self.daily_pnl < -max_daily_loss:
            raise RiskLimitExceeded(f"Daily loss ${abs(self.daily_pnl):.2f} exceeds limit ${max_daily_loss:.2f}")

    def _get_market_exposure(self, market_id: str, positions: dict) -> float:
        exposure = 0.0
        for p in positions.values():
            if getattr(p, "market_id", None) == market_id and not getattr(p, "resolved", False):
                exposure += float(getattr(p, "cost_basis", 0) or 0)
        return exposure

    def record_trade(self, pnl: float) -> None:
        self._check_and_reset_daily()
        self.daily_pnl += pnl
        self.daily_trades += 1
        log.debug("BaseRisk: Recorded trade P&L: $%.2f (Daily: $%.2f, Trades: %d)", pnl, self.daily_pnl, self.daily_trades)
