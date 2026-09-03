"""Risk controls — trailing stops, SL/TP, emergency — extracted from RealTradingEngine."""

from __future__ import annotations

import logging
from datetime import datetime, timezone

from ..core import PositionNotFound, RiskLimitExceeded

log = logging.getLogger(__name__)


class RealRiskControlsMixin:
    """Mixin for stop-loss / take-profit / trailing / emergency."""

    _positions: dict
    _orders: dict
    _resolve_positions: callable  # type: ignore
    _get_all_positions_across_wallets: callable  # type: ignore
    _find_position_across_wallets: callable  # type: ignore
    _find_position_by_key_across_wallets: callable  # type: ignore
    _resolve_risk_manager: callable  # type: ignore
    _resolve_config_and_risk: callable  # type: ignore
    _get_all_orders_across_wallets: callable  # type: ignore
    _resolve_balance: callable  # type: ignore
    _db_enabled: bool
    _wallet: object
    _clob_client: object
    _real_wallet_manager: object
    _use_multi_wallet: bool
    _emergency_mode: bool
    _orders: dict  # type: ignore
    _config: object

    def set_stop_loss(self, market, side: str, stop_price: float) -> None:
        from .real_helpers import validate_side
        side = validate_side(side)
        position, _ = self._find_position_across_wallets(market.id, side)
        if position is None:
            raise PositionNotFound(f"No position found for {market.slug} {side}")
        position.stop_loss = stop_price
        log.info("Stop loss set at $%.4f for %s %s", stop_price, market.slug, side)

    def set_take_profit(self, market, side: str, profit_price: float) -> None:
        from .real_helpers import validate_side
        side = validate_side(side)
        position, _ = self._find_position_across_wallets(market.id, side)
        if position is None:
            raise PositionNotFound(f"No position found for {market.slug} {side}")
        position.take_profit = profit_price
        log.info("Take profit set at $%.4f for %s %s", profit_price, market.slug, side)

    def set_trailing_stop(self, market, side: str, trail_distance: float) -> None:
        from .real_helpers import validate_side
        side = validate_side(side)
        position, _ = self._find_position_across_wallets(market.id, side)
        if position is None:
            raise PositionNotFound(f"No position found for {market.slug} {side}")
        if not hasattr(position, "trail_sl"):
            position.trail_sl = None
        if not hasattr(position, "trail_sl_price"):
            position.trail_sl_price = None
        position.trail_sl = trail_distance
        position.trail_sl_price = position.current_price - trail_distance if side == "UP" else position.current_price + trail_distance
        log.info("Trailing stop set at %.4f distance for %s %s", trail_distance, market.slug, side)

    def check_and_execute_trailing_stops(self, market_updates: dict[str, float]) -> list[str]:
        triggered: list[str] = []
        positions = self._get_all_positions_across_wallets()
        for key, position in positions.items():
            if getattr(position, "resolved", False):
                continue
            if not hasattr(position, "trail_sl") or position.trail_sl is None:
                continue
            token_id = getattr(position, "token_id", None) or position.market_id
            if token_id not in market_updates:
                continue
            current_price = market_updates[token_id]
            old_trail_price = getattr(position, "trail_sl_price", None)
            if old_trail_price is None:
                continue
            if position.side == "UP":
                new_trail_price = current_price - position.trail_sl
                if new_trail_price > old_trail_price:
                    position.trail_sl_price = new_trail_price
                    log.debug("Trailing stop updated for %s %s: $%.4f -> $%.4f", position.slug, position.side, old_trail_price, new_trail_price)
                if current_price <= position.trail_sl_price:
                    triggered.append(key)
                    log.warning("Trailing stop triggered for %s %s at $%.4f", position.slug, position.side, current_price)
            else:
                new_trail_price = current_price + position.trail_sl
                if new_trail_price < old_trail_price:
                    position.trail_sl_price = new_trail_price
                    log.debug("Trailing stop updated for %s %s: $%.4f -> $%.4f", position.slug, position.side, old_trail_price, new_trail_price)
                if current_price >= position.trail_sl_price:
                    triggered.append(key)
                    log.warning("Trailing stop triggered for %s %s at $%.4f", position.slug, position.side, current_price)
        return triggered

    def _find_position_by_key_across_wallets(self, position_key: str):
        if not self._use_multi_wallet or not self._real_wallet_manager:
            if position_key in self._positions:
                return self._positions[position_key], None
            return None, None
        for wallet in self._real_wallet_manager.get_all_wallets():  # type: ignore
            if position_key in wallet.positions:
                return wallet.positions[position_key], wallet
        return None, None

    def execute_trailing_stop_exit(self, position_key: str) -> None:
        position, wallet = self._find_position_by_key_across_wallets(position_key)
        if position is None:
            log.warning("Position %s not found for trailing stop exit", position_key)
            return
        log.info("Executing trailing stop exit for %s %s at $%.4f", position.slug, position.side, position.current_price)
        try:
            clob = wallet.clob_client if wallet is not None else self._clob_client
            orders = wallet.orders if wallet is not None else self._orders
            token_id = position.market_id
            current_price = position.current_price
            from datetime import datetime, timezone
            from .real_orders import RealOrder
            order_response = clob.place_order(token_id=token_id, side="sell", price=current_price, size=position.shares, order_type="market")
            order = RealOrder(id=order_response["order_id"], market_id=position.market_id, slug=position.slug, side=position.side, price=current_price, amount=position.shares * current_price, shares=position.shares, fee=0.0, status="pending", is_limit=False, created_at=datetime.now(timezone.utc))
            orders[order.id] = order
            position.resolved = True
            position.outcome = "STOPPED"
            log.info("Trailing stop exit executed for %s %s: order=%s", position.slug, position.side, order.id)
        except Exception:
            log.exception("Failed to execute trailing stop exit for %s %s", position.slug, position.side)

    def scale_position(self, market, side: str, add_amount: float, confidence: float = 0.5):
        from .real_helpers import validate_side
        side = validate_side(side)
        position, _ = self._find_position_across_wallets(market.id, side)
        if position is None:
            raise PositionNotFound(f"No position found for {market.slug} {side}")
        config, _ = self._resolve_config_and_risk()
        if not getattr(config, "enable_position_scaling", True):
            raise RiskLimitExceeded("Position scaling is disabled in configuration")
        if getattr(position, "scale_count", 0) >= getattr(config, "max_scale_additions", 3):
            raise RiskLimitExceeded(f"Position has been scaled {position.scale_count} times, maximum is {config.max_scale_additions}")
        min_profit_pct = getattr(config, "min_profit_for_scaling", 0.1)
        if float(getattr(position, "pnl_pct", 0) or 0) < min_profit_pct * 100:
            raise RiskLimitExceeded(f"Position profit {position.pnl_pct:.1f}% is below minimum {min_profit_pct*100:.1f}% for scaling")
        current_exposure = self._get_market_exposure(market.id)  # type: ignore
        max_add_amount = getattr(config, "max_position_size", float("inf")) - current_exposure
        if add_amount > max_add_amount:
            log.warning("Requested scale amount $%.2f exceeds limit, capping at $%.2f", add_amount, max_add_amount)
            add_amount = max(0, max_add_amount)
        log.info("Scaling position %s %s by $%.2f at confidence %.2f (scale #%d)", market.slug, side, add_amount, confidence, int(getattr(position, "scale_count", 0)) + 1)
        order = self.buy(market, side=side, amount=add_amount, confidence=confidence, confirm=False)  # type: ignore
        position.scale_count = int(getattr(position, "scale_count", 0)) + 1
        return order

    def reduce_position(self, market, side: str, reduce_pct: float, reason: str = "manual"):
        from .real_helpers import validate_side
        side = validate_side(side)
        position, _ = self._find_position_across_wallets(market.id, side)
        if position is None:
            raise PositionNotFound(f"No position found for {market.slug} {side}")
        config, _ = self._resolve_config_and_risk()
        if not getattr(config, "enable_position_reduction", True):
            raise RiskLimitExceeded("Position reduction is disabled in configuration")
        if not 0 < reduce_pct <= 1:
            raise ValueError("reduce_pct must be between 0 and 1")
        shares_to_reduce = position.shares * reduce_pct
        current_price = float(getattr(position, "current_price", 0) or 0)
        reduce_amount = shares_to_reduce * current_price
        log.info("Reducing position %s %s by %.1f%% ($%.2f) - reason: %s", market.slug, side, reduce_pct * 100, reduce_amount, reason)
        opposite_side = "DOWN" if side == "UP" else "UP"
        order = self.buy(market, side=opposite_side, amount=reduce_amount, confidence=0.5, confirm=False)  # type: ignore
        return order

    def hedge_position(self, market, side: str, hedge_pct: float = 0.5):
        from .real_helpers import validate_side
        side = validate_side(side)
        position, _ = self._find_position_across_wallets(market.id, side)
        if position is None:
            raise PositionNotFound(f"No position found for {market.slug} {side}")
        config, _ = self._resolve_config_and_risk()
        if not getattr(config, "enable_hedging", True):
            raise RiskLimitExceeded("Position hedging is disabled in configuration")
        if not 0 < hedge_pct <= 1:
            raise ValueError("hedge_pct must be between 0 and 1")
        if hedge_pct > getattr(config, "max_hedge_ratio", 1.0):
            raise RiskLimitExceeded(f"Hedge ratio {hedge_pct:.1%} exceeds maximum {config.max_hedge_ratio:.1%}")
        hedge_amount = position.cost_basis * hedge_pct
        hedge_side = "DOWN" if side == "UP" else "UP"
        log.info("Hedging position %s %s with %.1f%% ($%.2f) on opposite side %s", market.slug, side, hedge_pct * 100, hedge_amount, hedge_side)
        order = self.buy(market, side=hedge_side, amount=hedge_amount, confidence=0.5, confirm=False)  # type: ignore
        position.hedge_amount = float(getattr(position, "hedge_amount", 0) or 0) + hedge_amount
        return order

    def _on_price_update(self, market_id: str, up_price: float, down_price: float) -> None:
        from .real_helpers import validate_positive
        up_price = validate_positive(up_price, "up_price")
        down_price = validate_positive(down_price, "down_price")
        # Update live prices
        for pos in getattr(self, "_positions", {}).values():
            if getattr(pos, "market_id", None) == market_id and not getattr(pos, "resolved", False):
                pos.current_price = up_price if pos.side == "UP" else down_price
        if self._use_multi_wallet and self._real_wallet_manager:
            for w in self._real_wallet_manager.get_all_wallets():  # type: ignore
                for pos in w.positions.values():
                    if getattr(pos, "market_id", None) == market_id and not getattr(pos, "resolved", False):
                        pos.current_price = up_price if pos.side == "UP" else down_price
        market_updates: dict[str, float] = {}
        for pos in self._get_all_positions_across_wallets().values():
            if getattr(pos, "market_id", None) == market_id and not getattr(pos, "resolved", False):
                token_id = getattr(pos, "token_id", None) or pos.market_id
                current_price = up_price if pos.side == "UP" else down_price
                market_updates[token_id] = current_price
        self._check_and_execute_stop_losses(market_id, up_price, down_price)
        self._check_and_execute_take_profits(market_id, up_price, down_price)
        triggered_trailing_stops = self.check_and_execute_trailing_stops(market_updates)
        for position_key in triggered_trailing_stops:
            self.execute_trailing_stop_exit(position_key)

    def _check_stop_losses_for_wallet(self, positions, risk_manager, market_id: str, up_price: float, down_price: float, wallet=None) -> list[tuple]:
        triggered = []
        for position in positions.values():
            if getattr(position, "market_id", None) != market_id or getattr(position, "resolved", False):
                continue
            if getattr(position, "stop_loss", None) is None:
                continue
            current_price = up_price if position.side == "UP" else down_price
            if risk_manager.check_stop_loss(position, current_price):
                triggered.append((position, wallet))
        return triggered

    def _check_take_profits_for_wallet(self, positions, risk_manager, market_id: str, up_price: float, down_price: float, wallet=None) -> list[tuple]:
        triggered = []
        for position in positions.values():
            if getattr(position, "market_id", None) != market_id or getattr(position, "resolved", False):
                continue
            if getattr(position, "take_profit", None) is None:
                continue
            current_price = up_price if position.side == "UP" else down_price
            if risk_manager.check_take_profit(position, current_price):
                triggered.append((position, wallet))
        return triggered

    def _check_and_execute_stop_losses(self, market_id: str, up_price: float, down_price: float) -> None:
        all_triggered = []
        if self._use_multi_wallet and self._real_wallet_manager:
            for w in self._real_wallet_manager.get_all_wallets():  # type: ignore
                rm = w.risk_manager if w.risk_manager is not None else self._resolve_risk_manager()
                all_triggered.extend(self._check_stop_losses_for_wallet(w.positions, rm, market_id, up_price, down_price, w))
        else:
            all_triggered.extend(self._check_stop_losses_for_wallet(self._positions, self._resolve_risk_manager(), market_id, up_price, down_price))
        for position, wallet in all_triggered:
            log.warning("Stop loss triggered for %s %s", position.slug, position.side)
            self._execute_exit_order(position, "STOP_LOSS", wallet=wallet)

    def _check_and_execute_take_profits(self, market_id: str, up_price: float, down_price: float) -> None:
        all_triggered = []
        if self._use_multi_wallet and self._real_wallet_manager:
            for w in self._real_wallet_manager.get_all_wallets():  # type: ignore
                rm = w.risk_manager if w.risk_manager is not None else self._resolve_risk_manager()
                all_triggered.extend(self._check_take_profits_for_wallet(w.positions, rm, market_id, up_price, down_price, w))
        else:
            all_triggered.extend(self._check_take_profits_for_wallet(self._positions, self._resolve_risk_manager(), market_id, up_price, down_price))
        for position, wallet in all_triggered:
            log.info("Take profit triggered for %s %s", position.slug, position.side)
            self._execute_exit_order(position, "TAKE_PROFIT", wallet=wallet)

    def _execute_exit_order(self, position, reason: str, wallet=None) -> None:
        try:
            token_id = getattr(position, "market_id", "")
            # Resolve correct token_id from market if available via position metadata
            # Fallback: use market_id as token_id for Polymarket conditional tokens
            current_price = float(getattr(position, "current_price", 0) or 0)
            clob = wallet.clob_client if wallet is not None else self._clob_client  # type: ignore
            # Prefer clobTokenIds if available from position metadata
            order_response = clob.place_order(token_id=token_id, side="sell", price=current_price, size=position.shares, order_type="market")
            _ = order_response
            position.resolved = True
            position.outcome = reason
            if position.side == "UP":
                exit_value = position.shares * current_price
            else:
                exit_value = position.shares * (1 - current_price)
            pnl = exit_value - position.cost_basis
            position.current_value = exit_value
            log.info("Exit order executed for %s %s: reason=%s, pnl=$%.2f", position.slug, position.side, reason, pnl)
            if self._db_enabled:
                self._save_exit_to_db(position, reason, current_price)  # type: ignore
        except Exception:
            log.exception("Failed to execute exit order for %s %s", getattr(position, "slug", "?"), getattr(position, "side", "?"))

    def _save_exit_to_db(self, position, reason: str, exit_price: float) -> None:
        try:
            sizing_strategy = "unknown"
            confidence = 0.5
            kelly_fraction = 0.0
            fee = 0.0
            if getattr(position, "order_ids", None):
                first_order = self._orders.get(position.order_ids[0])  # type: ignore
                if first_order:
                    sizing_strategy = getattr(first_order, "sizing_strategy", "unknown")
                    confidence = getattr(first_order, "confidence", 0.5)
                    kelly_fraction = getattr(first_order, "kelly_fraction", 0.0)
                    fee = getattr(first_order, "fee", 0.0)
            self._db.save_trade(  # type: ignore
                market_slug=position.slug,
                market_id=position.market_id,
                side=position.side,
                entry_price=position.avg_price,
                exit_price=exit_price,
                amount=position.cost_basis,
                shares=position.shares,
                fee=fee,
                outcome=reason,
                pnl=float(getattr(position, "pnl", 0) or 0),
                timestamp=datetime.now(timezone.utc),
                sizing_strategy=sizing_strategy,
                confidence=confidence,
                kelly_fraction=kelly_fraction,
                stop_loss=getattr(position, "stop_loss", None),
                take_profit=getattr(position, "take_profit", None),
                tx_hash=None,
                is_real_trade=True,
                wallet_address=self._wallet.get_address(),  # type: ignore
            )
            log.debug("Real: exit saved to database for %s", position.slug)
        except Exception:
            log.exception("Real: failed to save exit to database")

    def emergency_stop(self, reason: str = "Manual") -> None:
        log.warning("EMERGENCY STOP: %s", reason)
        for order_id in list(self._orders.keys()):
            try:
                self.cancel(order_id)  # type: ignore
            except Exception:
                log.exception("Failed to cancel order %s", order_id)
        self._emergency_mode = True
        log.warning("All trading halted. Call resume_trading() to re-enable.")

    def resume_trading(self, confirm: bool = True) -> None:
        if confirm:
            try:
                response = input("Resume trading? (yes/no): ").strip().lower()
            except EOFError:
                response = "no"
            if response not in ("yes", "y"):
                log.info("Trading remains halted.")
                return
        self._emergency_mode = False
        log.info("Trading resumed.")
