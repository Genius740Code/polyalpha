"""Advanced order types — OCO, Bracket, Conditional, Iceberg, TWAP — extracted from RealTradingEngine."""

from __future__ import annotations

import logging
import uuid
from datetime import datetime, timedelta, timezone
from typing import Optional

from ..core import OrderCancelled

log = logging.getLogger(__name__)


class RealAdvancedMixin:
    """Mixin for advanced order types."""

    _emergency_mode: bool
    _orders: dict
    _oco_orders: dict
    _bracket_orders: dict
    _conditional_orders: dict
    _iceberg_orders: dict
    _twap_orders: dict
    _clob_client: object
    _resolve_clob: callable  # type: ignore

    def place_oco_order(self, market, side: str, amount: float, price1: float, price2: float, confirm: bool = True):
        from .real_orders import OCOOrder
        from .real_helpers import validate_side
        if self._emergency_mode:
            raise OrderCancelled("Trading halted - emergency mode active")
        side = validate_side(side)
        order1 = self.limit(market, side, price1, amount, confirm=confirm)  # type: ignore
        order2 = self.limit(market, side, price2, amount, confirm=False)  # type: ignore
        oco_id = str(uuid.uuid4())
        oco_order = OCOOrder(id=oco_id, market_id=market.id, slug=market.slug, side=side, order1_id=order1.id, order2_id=order2.id, order1_price=price1, order2_price=price2, amount=amount, status="active", created_at=datetime.now(timezone.utc))
        self._oco_orders[oco_id] = oco_order
        log.info("OCO order placed: %s %s, order1=%s @ %.4f, order2=%s @ %.4f", market.slug, side, order1.id, price1, order2.id, price2)
        return oco_order

    def check_oco_triggers(self) -> list[str]:
        triggered_ocos: list[str] = []
        for oco_id, oco in list(self._oco_orders.items()):
            if getattr(oco, "status", None) != "active":
                continue
            order1 = self._orders.get(oco.order1_id)
            order2 = self._orders.get(oco.order2_id)
            if not order1 or not order2:
                continue
            self.update_order_fill_status(oco.order1_id)  # type: ignore
            self.update_order_fill_status(oco.order2_id)  # type: ignore
            if order1.status == "filled":
                try:
                    self.cancel(oco.order2_id)  # type: ignore
                    oco.status = "triggered"
                    oco.triggered_order_id = order1.id
                    oco.cancelled_order_id = order2.id
                    oco.triggered_at = datetime.now(timezone.utc)
                    triggered_ocos.append(oco_id)
                    log.info("OCO triggered: order1 %s filled, cancelled order2 %s", order1.id, order2.id)
                except Exception:
                    log.exception("Failed to cancel order2 in OCO %s", oco_id)
            elif order2.status == "filled":
                try:
                    self.cancel(oco.order1_id)  # type: ignore
                    oco.status = "triggered"
                    oco.triggered_order_id = order2.id
                    oco.cancelled_order_id = order1.id
                    oco.triggered_at = datetime.now(timezone.utc)
                    triggered_ocos.append(oco_id)
                    log.info("OCO triggered: order2 %s filled, cancelled order1 %s", order2.id, order1.id)
                except Exception:
                    log.exception("Failed to cancel order1 in OCO %s", oco_id)
        return triggered_ocos

    def place_bracket_order(self, market, side: str, entry_price: float, amount: float, stop_loss_price: Optional[float] = None, take_profit_price: Optional[float] = None, stop_loss_pct: Optional[float] = None, take_profit_pct: Optional[float] = None, confirm: bool = True):
        from .real_orders import BracketOrder
        from .real_helpers import validate_side
        if self._emergency_mode:
            raise OrderCancelled("Trading halted - emergency mode active")
        side = validate_side(side)
        if stop_loss_price is None and stop_loss_pct is not None:
            stop_loss_price = entry_price * (1 - stop_loss_pct) if side == "UP" else entry_price * (1 + stop_loss_pct)
        if take_profit_price is None and take_profit_pct is not None:
            take_profit_price = entry_price * (1 + take_profit_pct) if side == "UP" else entry_price * (1 - take_profit_pct)
        entry_order = self.limit(market, side, entry_price, amount, confirm=confirm)  # type: ignore
        bracket_id = str(uuid.uuid4())
        bracket_order = BracketOrder(id=bracket_id, market_id=market.id, slug=market.slug, side=side, entry_order_id=entry_order.id, entry_price=entry_price, stop_loss_price=stop_loss_price, take_profit_price=take_profit_price, amount=amount, status="pending", created_at=datetime.now(timezone.utc))
        self._bracket_orders[bracket_id] = bracket_order
        log.info("Bracket order placed: %s %s @ %.4f, stop=%.4f, take=%.4f", market.slug, side, entry_price, stop_loss_price or 0, take_profit_price or 0)
        return bracket_order

    def activate_bracket_orders(self) -> None:
        for bracket_id, bracket in list(self._bracket_orders.items()):
            if bracket.status != "pending":
                continue
            entry_order = self._orders.get(bracket.entry_order_id)
            if not entry_order:
                continue
            self.update_order_fill_status(bracket.entry_order_id)  # type: ignore
            if entry_order.status == "filled":
                bracket.status = "active"
                bracket.filled_at = datetime.now(timezone.utc)
                # Resolve token_id: prefer clobTokenIds from market, fallback to market.id
                token_id = self._resolve_token_id(bracket.market_id, bracket.side)  # type: ignore
                if bracket.stop_loss_price is not None:
                    try:
                        log.info("Placing stop loss order for bracket %s at %.4f", bracket_id, bracket.stop_loss_price)
                        sl_order = self._clob_client.place_order(token_id=token_id, side="sell", price=bracket.stop_loss_price, size=bracket.amount / bracket.stop_loss_price if bracket.stop_loss_price else 0, order_type="limit")  # type: ignore
                        bracket.stop_loss_order_id = sl_order.get("order_id", "")
                    except Exception:
                        log.exception("Failed to place stop loss for bracket %s", bracket_id)
                if bracket.take_profit_price is not None:
                    try:
                        log.info("Placing take profit order for bracket %s at %.4f", bracket_id, bracket.take_profit_price)
                        tp_order = self._clob_client.place_order(token_id=token_id, side="sell", price=bracket.take_profit_price, size=bracket.amount / bracket.take_profit_price if bracket.take_profit_price else 0, order_type="limit")  # type: ignore
                        bracket.take_profit_order_id = tp_order.get("order_id", "")
                    except Exception:
                        log.exception("Failed to place take profit for bracket %s", bracket_id)
                log.info("Bracket order %s activated", bracket_id)

    def place_conditional_order(self, market, side: str, condition_type: str, condition_value: float, child_order_price: float, child_order_amount: float, expires_after_seconds: Optional[int] = None):
        from .real_orders import ConditionalOrder
        from .real_helpers import validate_side
        if self._emergency_mode:
            raise OrderCancelled("Trading halted - emergency mode active")
        side = validate_side(side)
        if condition_type not in ("price_above", "price_below", "time_after"):
            raise ValueError(f"Invalid condition_type: {condition_type}")
        expires_at = None
        if expires_after_seconds is not None:
            expires_at = datetime.now(timezone.utc) + timedelta(seconds=expires_after_seconds)
        cond_id = str(uuid.uuid4())
        cond_order = ConditionalOrder(id=cond_id, market_id=market.id, slug=market.slug, side=side, condition_type=condition_type, condition_value=condition_value, child_order_price=child_order_price, child_order_amount=child_order_amount, status="waiting", created_at=datetime.now(timezone.utc), expires_at=expires_at)
        self._conditional_orders[cond_id] = cond_order
        log.info("Conditional order placed: %s %s, condition=%s %.4f", market.slug, side, condition_type, condition_value)
        return cond_order

    def check_conditional_triggers(self, market_updates: dict[str, float]) -> list[str]:
        triggered: list[str] = []
        for cond_id, cond in list(self._conditional_orders.items()):
            if cond.status != "waiting":
                continue
            if cond.expires_at and datetime.now(timezone.utc) > cond.expires_at:
                cond.status = "expired"
                log.info("Conditional order %s expired", cond_id)
                continue
            if cond.condition_type in ("price_above", "price_below"):
                current_price = market_updates.get(cond.market_id)
                if current_price is None:
                    continue
                should_trigger = False
                if cond.condition_type == "price_above" and current_price > cond.condition_value:
                    should_trigger = True
                elif cond.condition_type == "price_below" and current_price < cond.condition_value:
                    should_trigger = True
                if should_trigger:
                    try:
                        log.info("Conditional order %s triggered: price %.4f, placing child order", cond_id, current_price)
                        token_id = self._resolve_token_id(cond.market_id, cond.side)  # type: ignore
                        child = self._clob_client.place_order(token_id=token_id, side="buy", price=cond.child_order_price, size=cond.child_order_amount / cond.child_order_price if cond.child_order_price else 0, order_type="limit")  # type: ignore
                        cond.child_order_id = child.get("order_id", "")
                        cond.status = "triggered"
                        cond.triggered_at = datetime.now(timezone.utc)
                        triggered.append(cond_id)
                    except Exception:
                        log.exception("Failed to place child order for conditional %s", cond_id)
        return triggered

    def place_iceberg_order(self, market, side: str, total_amount: float, visible_size: float, price: float, confirm: bool = True):
        from .real_orders import IcebergOrder
        from .real_helpers import validate_side
        if self._emergency_mode:
            raise OrderCancelled("Trading halted - emergency mode active")
        side = validate_side(side)
        if visible_size > total_amount:
            raise ValueError("visible_size cannot exceed total_amount")
        token_id = self._resolve_token_id(market, side)  # type: ignore
        iceberg_id = str(uuid.uuid4())
        iceberg_order = IcebergOrder(id=iceberg_id, market_id=market.id, slug=market.slug, side=side, total_amount=total_amount, visible_size=visible_size, price=price, status="active", created_at=datetime.now(timezone.utc), token_id=token_id)
        self._iceberg_orders[iceberg_id] = iceberg_order
        self._execute_iceberg_slice(iceberg_id, confirm=confirm)
        log.info("Iceberg order placed: %s %s, total=$%.2f, visible=$%.2f @ %.4f", market.slug, side, total_amount, visible_size, price)
        return iceberg_order

    def _execute_iceberg_slice(self, iceberg_id: str, confirm: bool = True):
        from datetime import datetime, timezone
        from .real_orders import RealOrder
        iceberg = self._iceberg_orders.get(iceberg_id)
        if not iceberg or iceberg.status not in ("active", "partial"):
            return None
        remaining = float(getattr(iceberg, "remaining_amount", 0) or 0)
        if remaining <= 0:
            iceberg.status = "completed"
            return None
        slice_amount = min(iceberg.visible_size, remaining)
        try:
            log.info("Executing iceberg slice: %s %s, amount=$%.2f @ %.4f", iceberg.slug, iceberg.side, slice_amount, iceberg.price)
            order_response = self._clob_client.place_order(token_id=iceberg.token_id, side="buy", price=iceberg.price, size=slice_amount / iceberg.price if iceberg.price > 0 else 0, order_type="limit")  # type: ignore
            order = RealOrder(id=order_response["order_id"], market_id=iceberg.market_id, slug=iceberg.slug, side=iceberg.side, price=iceberg.price, amount=slice_amount, shares=slice_amount / iceberg.price if iceberg.price > 0 else 0, fee=0.0, status="pending", is_limit=True, created_at=datetime.now(timezone.utc))
            self._orders[order.id] = order
            iceberg.child_order_ids.append(order.id)
            return order
        except Exception:
            log.exception("Failed to execute iceberg slice for %s", iceberg_id)
            return None

    def update_iceberg_orders(self) -> None:
        for iceberg_id, iceberg in list(self._iceberg_orders.items()):
            if iceberg.status not in ("active", "partial"):
                continue
            filled_amount = 0.0
            for child_id in list(getattr(iceberg, "child_order_ids", [])):
                child_order = self._orders.get(child_id)
                if child_order:
                    self.update_order_fill_status(child_id)  # type: ignore
                    if child_order.status == "filled":
                        filled_amount += float(getattr(child_order, "amount", 0) or 0)
            iceberg.filled_amount = filled_amount
            if iceberg.filled_amount >= iceberg.total_amount:
                iceberg.status = "completed"
                log.info("Iceberg order %s completed", iceberg_id)
            elif iceberg.filled_amount > 0:
                iceberg.status = "partial"
            if float(getattr(iceberg, "remaining_amount", 0) or 0) > 0 and len(iceberg.child_order_ids) > 0:
                last_child_id = iceberg.child_order_ids[-1]
                last_child = self._orders.get(last_child_id)
                if last_child and last_child.status == "filled":
                    self._execute_iceberg_slice(iceberg_id, confirm=False)

    def place_twap_order(self, market, side: str, total_amount: float, duration_seconds: int, num_slices: int, price: Optional[float] = None, confirm: bool = True):
        from .real_orders import TWAPOrder
        from .real_helpers import validate_side
        if self._emergency_mode:
            raise OrderCancelled("Trading halted - emergency mode active")
        side = validate_side(side)
        if num_slices < 1:
            raise ValueError("num_slices must be at least 1")
        slice_interval = duration_seconds / num_slices
        ends_at = datetime.now(timezone.utc) + timedelta(seconds=duration_seconds)
        token_id = self._resolve_token_id(market, side)  # type: ignore
        twap_id = str(uuid.uuid4())
        twap_order = TWAPOrder(id=twap_id, market_id=market.id, slug=market.slug, side=side, total_amount=total_amount, duration_seconds=duration_seconds, num_slices=num_slices, price=price, status="active", created_at=datetime.now(timezone.utc), ends_at=ends_at, slice_interval=slice_interval, token_id=token_id)
        self._twap_orders[twap_id] = twap_order
        self._execute_twap_slice(twap_id, confirm=confirm)
        log.info("TWAP order placed: %s %s, total=$%.2f over %ds in %d slices", market.slug, side, total_amount, duration_seconds, num_slices)
        return twap_order

    def _execute_twap_slice(self, twap_id: str, confirm: bool = True):
        from datetime import datetime, timezone
        from .real_orders import RealOrder
        from .staleness import get_price_for_side
        twap = self._twap_orders.get(twap_id)
        if not twap or twap.status not in ("active", "partial"):
            return None
        if twap.ends_at and datetime.now(timezone.utc) > twap.ends_at:
            twap.status = "completed"
            log.info("TWAP order %s completed (time expired)", twap_id)
            return None
        remaining = float(getattr(twap, "remaining_amount", 0) or 0)
        if remaining <= 0:
            twap.status = "completed"
            return None
        slice_amount = float(getattr(twap, "slice_amount", remaining / max(twap.num_slices, 1)) or 0)
        # If market-aware: try live price, else fallback
        price = twap.price
        is_market = price is None or price <= 0
        try:
            log.info("Executing TWAP slice: %s %s, amount=$%.2f", twap.slug, twap.side, slice_amount)
            if not is_market and price and price > 0:
                order_response = self._clob_client.place_order(token_id=twap.token_id, side="buy", price=price, size=slice_amount / price, order_type="limit")  # type: ignore
                fill_price = price
            else:
                # Resolve live price via staleness helper if market known
                # We don't have market object; use fallback 0.5 if no stream
                # Better: use attached stream price if available for this token/market
                # Try to find attached stream that matches this TWAP's token/market
                live_price = None
                # Best-effort: iterate attached streams for price
                for stream in getattr(self, "_attached_streams", {}).values():
                    if getattr(stream, "running", False):
                        # Use up/down based on side
                        p = getattr(stream, "up", None) if twap.side == "UP" else getattr(stream, "down", None)
                        if p and p > 0:
                            live_price = p
                            break
                fill_price = live_price if live_price and live_price > 0 else 0.5
                order_response = self._clob_client.place_order(token_id=twap.token_id, side="buy", price=fill_price, size=slice_amount / fill_price if fill_price else 0, order_type="market" if is_market else "limit")  # type: ignore
            order = RealOrder(id=order_response["order_id"], market_id=twap.market_id, slug=twap.slug, side=twap.side, price=fill_price or 0.5, amount=slice_amount, shares=slice_amount / (fill_price or 0.5) if fill_price else 0, fee=0.0, status="pending", is_limit=not is_market, created_at=datetime.now(timezone.utc))
            self._orders[order.id] = order
            twap.child_order_ids.append(order.id)
            return order
        except Exception:
            log.exception("Failed to execute TWAP slice for %s", twap_id)
            return None

    def update_twap_orders(self) -> None:
        for twap_id, twap in list(self._twap_orders.items()):
            if twap.status not in ("active", "partial"):
                continue
            filled_amount = 0.0
            for child_id in list(getattr(twap, "child_order_ids", [])):
                child_order = self._orders.get(child_id)
                if child_order:
                    self.update_order_fill_status(child_id)  # type: ignore
                    if child_order.status == "filled":
                        filled_amount += float(getattr(child_order, "amount", 0) or 0)
            twap.filled_amount = filled_amount
            if twap.filled_amount >= twap.total_amount:
                twap.status = "completed"
                log.info("TWAP order %s completed", twap_id)
            elif twap.filled_amount > 0:
                twap.status = "partial"
            if float(getattr(twap, "remaining_amount", 0) or 0) > 0:
                elapsed = (datetime.now(timezone.utc) - twap.created_at).total_seconds()
                expected_slices = int(elapsed / float(getattr(twap, "slice_interval", 1) or 1)) + 1
                if len(twap.child_order_ids) < expected_slices and len(twap.child_order_ids) < twap.num_slices:
                    self._execute_twap_slice(twap_id, confirm=False)

    def _resolve_token_id(self, market_or_id, side: str) -> str:
        """Resolve token_id from market object or market_id string."""
        # If market_or_id is a market object with clobTokenIds/up_token/down_token
        if hasattr(market_or_id, "clobTokenIds") and getattr(market_or_id, "clobTokenIds", None):
            raw = str(getattr(market_or_id, "clobTokenIds"))
            if raw:
                parts = [p.strip() for p in raw.split(",")]
                if len(parts) >= 2:
                    return parts[0] if side == "UP" else parts[1]
                return parts[0]
        if hasattr(market_or_id, "up_token"):
            return market_or_id.up_token if side == "UP" else market_or_id.down_token  # type: ignore
        # fallback: assume market_or_id is already token_id/market_id
        return str(market_or_id)
