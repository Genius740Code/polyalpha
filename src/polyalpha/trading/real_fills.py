"""Fill handling extracted from RealTradingEngine."""

from __future__ import annotations

import logging
import threading
from datetime import datetime, timezone
from typing import TYPE_CHECKING

from ..core import NetworkError, OrderNotFound

if TYPE_CHECKING:
    from .real_orders import RealOrder

log = logging.getLogger(__name__)


class RealFillsMixin:
    """Mixin for order polling and partial-fill correction."""

    _orders: dict
    _positions: dict
    _position_lock: threading.RLock
    _resolve_clob: callable  # type: ignore
    _resolve_config: callable  # type: ignore
    _find_order_across_wallets: callable  # type: ignore
    _get_all_orders_across_wallets: callable  # type: ignore
    _resolve_positions: callable  # type: ignore
    _db_enabled: bool
    _db: object

    def poll_order_status(self, order_id: str) -> dict:
        order, _ = self._find_order_across_wallets(order_id)
        if order is None:
            raise OrderNotFound(f"Order {order_id} not found")
        order.last_status_check = datetime.now(timezone.utc)
        order.status_check_attempts += 1
        clob = self._resolve_clob()
        config = self._resolve_config()
        try:
            status_response = clob.get_order_status(order_id)
            log.debug("Order %s status: %s", order_id, status_response.get("status"))
            return status_response
        except Exception as e:
            log.exception("Failed to poll order %s status (attempt %d)", order_id, order.status_check_attempts)
            if order.status_check_attempts >= getattr(config, "retry_attempts", 3):
                raise NetworkError(f"Order status polling failed after {config.retry_attempts} attempts: {e}")
            raise

    def update_order_fill_status(self, order_id: str) -> None:
        order, _ = self._find_order_across_wallets(order_id)
        if order is None:
            raise OrderNotFound(f"Order {order_id} not found")
        if order.status in ("filled", "cancelled", "expired"):
            return
        status_response = self.poll_order_status(order_id)
        api_status = status_response.get("status", "unknown")
        filled_size = float(status_response.get("filled_size", 0.0))
        avg_price = float(status_response.get("avg_price", order.price))

        if filled_size > 0 and filled_size < order.shares:
            if order.status != "partially_filled":
                log.debug("Order %s partially filled: %.2f/%.2f shares", order_id, filled_size, order.shares)
                order.status = "partially_filled"
            prev_filled = float(getattr(order, "filled_shares", 0) or 0)
            incremental = filled_size - prev_filled
            if incremental <= 0:
                return
            order.filled_shares = filled_size
            order.filled_amount = filled_size * avg_price
            order.avg_fill_price = avg_price
            self._handle_partial_fill(order, incremental, avg_price)
        elif filled_size >= order.shares or api_status == "filled":
            if order.status != "filled":
                log.info("Order %s fully filled: %.2f shares @ %.4f", order_id, filled_size, avg_price)
                order.status = "filled"
                order.filled_at = datetime.now(timezone.utc)
                order.filled_shares = filled_size
                order.filled_amount = filled_size * avg_price
                order.avg_fill_price = avg_price
                self._on_order_filled(order)
        elif api_status == "cancelled":
            if order.status != "cancelled":
                log.info("Order %s cancelled", order_id)
                order.status = "cancelled"
        elif api_status == "expired":
            if order.status != "expired":
                log.warning("Order %s expired", order_id)
                order.status = "expired"

        if self._db_enabled:
            self._update_order_in_db(order)

    def _handle_partial_fill(self, order: "RealOrder", incremental_shares: float, avg_price: float) -> None:
        positions = self._resolve_positions()
        position_key = f"{order.market_id}:{order.side}"
        with self._position_lock:
            if position_key not in positions:
                from .real_orders import RealPosition
                position = RealPosition(
                    market_id=order.market_id,
                    slug=order.slug,
                    question=getattr(order, "slug", ""),
                    side=order.side,
                    shares=0,
                    avg_price=0,
                    current_price=0,
                    cost_basis=0,
                    current_value=0,
                    order_ids=[order.id],
                )
                positions[position_key] = position
            else:
                position = positions[position_key]

            if position.shares >= order.shares:
                position.shares -= order.shares
                position.cost_basis = max(0.0, position.cost_basis - order.shares * order.price)

            position.shares += incremental_shares
            position.cost_basis += incremental_shares * avg_price
            if position.shares > 0:
                position.avg_price = position.cost_basis / position.shares
            position.current_value = position.shares * order.price
            log.debug("Position updated with partial fill: %s %s, shares=%.2f, avg_price=%.4f",
                      position.slug, position.side, position.shares, position.avg_price)

    def _on_order_filled(self, order: "RealOrder") -> None:
        log.debug("Order fill callback: %s %s $%.2f @ $%.4f (avg_fill: $%.4f)",
                  order.slug, order.side, order.amount, order.price, getattr(order, "avg_fill_price", 0))
        if getattr(order, "avg_fill_price", 0) and order.avg_fill_price > 0:
            self._correct_position_from_fill(order)
        risk_manager = self._resolve_risk_manager()  # type: ignore
        risk_manager.record_trade(0.0)

    def _correct_position_from_fill(self, order: "RealOrder") -> None:
        positions = self._resolve_positions()
        key = f"{order.market_id}:{order.side}"
        with self._position_lock:
            position = positions.get(key)
            if position is None:
                return
            actual_shares = max(float(getattr(order, "filled_shares", 0) or 0), 0.0)
            if actual_shares <= 0:
                actual_shares = order.shares
            fill_price = float(getattr(order, "avg_fill_price", 0) or 0)
            if position.shares >= order.shares:
                position.shares -= order.shares
                position.cost_basis = max(0.0, position.cost_basis - order.shares * order.price)
            position.shares += actual_shares
            position.cost_basis += actual_shares * fill_price
            if position.shares > 0:
                position.avg_price = position.cost_basis / position.shares
            position.current_value = position.shares * order.price

    def check_order_timeout(self, order_id: str) -> bool:
        order, _ = self._find_order_across_wallets(order_id)
        if order is None:
            raise OrderNotFound(f"Order {order_id} not found")
        config = self._resolve_config()
        if order.status not in ("pending", "open", "partially_filled"):
            return False
        if order.created_at:
            elapsed = (datetime.now(timezone.utc) - order.created_at).total_seconds()
            if elapsed > getattr(config, "order_timeout", 60):
                log.warning("Order %s timed out after %.1f seconds (status: %s)", order_id, elapsed, order.status)
                return True
        return False

    def poll_all_orders(self) -> dict[str, str]:
        status_updates: dict[str, str] = {}
        orders = self._get_all_orders_across_wallets()
        for order_id, order in list(orders.items()):
            if order.status in ("pending", "open", "partially_filled"):
                try:
                    old_status = order.status
                    self.update_order_fill_status(order_id)
                    if order.status != old_status:
                        status_updates[order_id] = order.status
                except Exception:
                    log.exception("Failed to update order %s status", order_id)
                    if self.check_order_timeout(order_id):
                        status_updates[order_id] = "timeout"
        return status_updates
