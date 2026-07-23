"""
Paper trading engine — simulated orders, positions, and P&L.

All state is held in memory.  No real money, no signing, no API keys needed.

Usage
-----
    client = polyalpha.Client(balance=100.0)

    # Market fill — executes immediately at the current price
    order = client.paper.buy(market, side="UP", amount=10.0)

    # Limit order — queued until the live price crosses the threshold
    order = client.paper.limit(market, side="UP", price=0.92, amount=10.0)

    # Wire a stream so limits auto-fill on price events
    stream = client.stream(market)
    client.paper.attach_stream(stream, market)
    stream.start(background=True)

    # Cancel / inspect
    client.paper.cancel(order.id)
    client.paper.open()         # pending limit orders
    client.paper.positions()    # live positions
    client.paper.summary()      # P&L table
"""

from __future__ import annotations

import logging
from datetime import datetime, timezone
from typing import TYPE_CHECKING, Optional

if TYPE_CHECKING:
    from ..report.engine import ReportEngine
    from ..database.database import TradeDatabase
    from .auto_redeem import AutoRedeemEngine, AutoRedeemConfig
    from .wallet import PaperWallet

from ..core import (
    InsufficientBalance,
    OrderNotFound,
    PositionNotFound,
    SUMMARY_DIV_WIDTH,
    FALLBACK_PRICE,
    PRICE_STALENESS_THRESHOLD,
    PRICE_ROUNDING,
    SHARE_ROUNDING,
)

from .paper_config import PaperConfig
from .paper_types import PaperOrder, PaperPosition, new_id, now, validate_market, validate_side, validate_positive, validate_price
from .paper_risk import RiskManager
from .paper_fees import PaperFeeManager

log = logging.getLogger(__name__)


class PaperEngine:
    """
    Paper trading engine.  Access via ``client.paper``.

    All order-book and position state is held in memory for the session.

    Parameters
    ----------
    balance : float
        Starting USDC balance (default: 100.0)
    config : PaperConfig, optional
        Configuration for fees, delays, slippage, and fill probability
    db_path : str, optional
        Path to SQLite database file for trade persistence.
    """

    def __init__(self, balance: float = 100.0, config: Optional[PaperConfig] = None, db_path: Optional[str] = None):
        self._config: PaperConfig = config or PaperConfig()
        self._report: Optional[ReportEngine] = None
        self._db: Optional[TradeDatabase] = None
        self._db_enabled: bool = False
        if db_path:
            self.enable_database(db_path)

        # Multi-wallet support
        self._wallet_manager: Optional[object] = None
        self._use_multi_wallet: bool = False

        # Single-wallet state
        self._balance: float = float(balance)
        self._orders: dict[str, PaperOrder] = {}
        self._positions: dict[str, PaperPosition] = {}

        # Risk management
        self._risk_manager: RiskManager = RiskManager(self._config, self._balance)

        # Fee management
        self._fee_manager: PaperFeeManager = PaperFeeManager(self._config)

        # Auto-redeem engine (lazy-initialized)
        self._auto_redeem: Optional[AutoRedeemEngine] = None

        # Portfolio analytics engine (lazy-initialized)
        self._portfolio_analytics: Optional[object] = None

        # Reporting engine (lazy-initialized)
        self._reporting: Optional[object] = None

        # Stream tracking for price-aware trading
        self._attached_streams: dict[str, object] = {}

    @property
    def report(self) -> ReportEngine:
        """Analytics and reporting engine. Access via ``client.paper.report``."""
        if self._report is None:
            from ..report.engine import ReportEngine
            self._report = ReportEngine(self)
        return self._report

    @property
    def auto_redeem(self) -> AutoRedeemEngine:
        """Auto-redeem engine for automatic position redemption."""
        if self._auto_redeem is None:
            from .auto_redeem import AutoRedeemEngine, AutoRedeemConfig
            self._auto_redeem = AutoRedeemEngine(self, AutoRedeemConfig())
        return self._auto_redeem

    @property
    def portfolio_analytics(self) -> object:
        """Portfolio analytics engine. Access via ``client.paper.portfolio_analytics``."""
        if self._portfolio_analytics is None:
            from ..report.portfolio_analytics import PortfolioAnalytics
            self._portfolio_analytics = PortfolioAnalytics(self)
        return self._portfolio_analytics

    @property
    def reporting(self) -> object:
        """Comprehensive reporting engine. Access via ``client.paper.reporting``."""
        if self._reporting is None:
            from ..report.reporting import ReportingEngine
            self._reporting = ReportingEngine(self)
        return self._reporting

    def set_auto_redeem_config(self, config: AutoRedeemConfig) -> None:
        """Set a custom auto-redeem configuration."""
        from .auto_redeem import AutoRedeemEngine
        self._auto_redeem = AutoRedeemEngine(self, config)

    # ── Multi-Wallet Support ─────────────────────────────────────────────────────

    def enable_multi_wallet(self, wallet_manager) -> None:
        """Enable multi-wallet mode with a custom wallet manager."""
        from .wallet import WalletManager
        if not isinstance(wallet_manager, WalletManager):
            raise TypeError("wallet_manager must be a WalletManager instance")
        if not wallet_manager.wallets:
            raise ValueError("wallet_manager must have at least one wallet")

        self._wallet_manager = wallet_manager
        self._use_multi_wallet = True
        log.info("PaperEngine: multi-wallet mode enabled with %d wallets", len(wallet_manager.wallets))

    def disable_multi_wallet(self) -> None:
        """Disable multi-wallet mode and return to single-wallet mode."""
        self._wallet_manager = None
        self._use_multi_wallet = False
        log.info("PaperEngine: returned to single-wallet mode")

    @property
    def wallets(self) -> Optional[object]:
        """Get the wallet manager if multi-wallet mode is enabled."""
        return self._wallet_manager

    @property
    def is_multi_wallet(self) -> bool:
        """Check if multi-wallet mode is enabled."""
        return self._use_multi_wallet

    def _find_order_across_wallets(self, order_id: str):
        """Find an order across all wallets. Returns (order, wallet) tuple or raises OrderNotFound."""
        if self._use_multi_wallet and self._wallet_manager:
            for wallet in self._wallet_manager.get_all_wallets():
                order = wallet._orders.get(order_id)
                if order is not None:
                    return order, wallet
        else:
            order = self._orders.get(order_id)
            if order is not None:
                return order, self._get_active_wallet()
        raise OrderNotFound(f"No order found: {order_id}")

    def _find_position_across_wallets(self, market_id: str, side: str):
        """Find a position across all wallets. Returns (position, wallet) tuple or raises PositionNotFound."""
        key = f"{market_id}:{side}"
        if self._use_multi_wallet and self._wallet_manager:
            for wallet in self._wallet_manager.get_all_wallets():
                pos = wallet._positions.get(key)
                if pos is not None:
                    return pos, wallet
        else:
            pos = self._positions.get(key)
            if pos is not None:
                return pos, self._get_active_wallet()
        raise PositionNotFound(f"Position {key} not found")

    def _get_all_orders_across_wallets(self) -> list[PaperOrder]:
        """Get all orders from all wallets."""
        if self._use_multi_wallet and self._wallet_manager:
            all_orders = []
            for wallet in self._wallet_manager.get_all_wallets():
                all_orders.extend(wallet._orders.values())
            return all_orders
        return list(self._orders.values())

    def _get_active_wallet(self):
        """Get the active wallet for trading operations."""
        if not self._use_multi_wallet:
            from .wallet import PaperWallet
            virtual_wallet = PaperWallet(wallet_id="default", balance=self._balance, config=self._config)
            virtual_wallet._orders = self._orders
            virtual_wallet._positions = self._positions
            virtual_wallet._risk_manager = self._risk_manager
            return virtual_wallet
        else:
            return self._wallet_manager.select_wallet()

    # ── Balance ────────────────────────────────────────────────────────────────

    @property
    def balance(self) -> float:
        """Current paper USDC balance."""
        if self._use_multi_wallet and self._wallet_manager:
            return self._wallet_manager.get_aggregated_summary()["total_balance"]
        return self._balance

    @property
    def config(self) -> PaperConfig:
        """Current paper trading configuration."""
        return self._config

    def set_balance(self, amount: float, wallet_id: str | None = None) -> None:
        """Reset the paper balance to *amount*."""
        if amount < 0:
            raise ValueError("Balance cannot be negative")
        if self._use_multi_wallet and self._wallet_manager:
            if wallet_id:
                wallet = self._wallet_manager.get_wallet(wallet_id)
                wallet.set_balance(float(amount))
            else:
                per_wallet = float(amount) / len(self._wallet_manager.wallets)
                for w in self._wallet_manager.get_all_wallets():
                    w.set_balance(per_wallet)
            log.debug("Paper: multi-wallet balance set to $%.2f", amount)
        else:
            self._balance = float(amount)
            log.debug("Paper: balance set to $%.2f", amount)

    def set_config(self, config: PaperConfig) -> None:
        """Update the paper trading configuration."""
        self._config = config
        self._fee_manager.config = config
        log.info("Paper: configuration updated")

    # ── Risk Management ───────────────────────────────────────────────────────────

    def get_risk_summary(self) -> dict:
        """Get current risk management summary."""
        if self._use_multi_wallet and self._wallet_manager:
            summaries = [w.risk_manager.get_summary() for w in self._wallet_manager.get_all_wallets()]
            return {
                "daily_pnl": sum(s.get("daily_pnl", 0.0) for s in summaries),
                "daily_trades": sum(s.get("daily_trades", 0) for s in summaries),
                "remaining_loss_limit": min(s.get("remaining_loss_limit", float('inf')) for s in summaries),
                "remaining_trades": min(s.get("remaining_trades", float('inf')) for s in summaries),
                "daily_loss_limit": summaries[0].get("daily_loss_limit", 0.0) if summaries else 0.0,
                "max_trades_per_day": summaries[0].get("max_trades_per_day", 0) if summaries else 0,
            }
        return self._risk_manager.get_summary()

    def reset_daily_limits(self) -> None:
        """Manually reset daily risk limits."""
        if self._use_multi_wallet and self._wallet_manager:
            for wallet in self._wallet_manager.get_all_wallets():
                wallet.risk_manager.reset_daily_limits()
        else:
            self._risk_manager.reset_daily_limits()

    # ── Pre-Trade Checks ─────────────────────────────────────────────────────────

    def pre_trade_checks(self, market, side: str, amount: float, balance: float | None = None) -> dict:
        """Run comprehensive pre-trade checks before order execution."""
        checks = {
            "balance_ok": True,
            "market_open": True,
            "price_reasonable": True,
            "warnings": [],
            "can_proceed": True,
        }

        available_balance = balance if balance is not None else self._balance
        if amount > available_balance:
            checks["balance_ok"] = False
            checks["can_proceed"] = False
            checks["warnings"].append(
                f"Insufficient balance: need ${amount:.2f}, have ${available_balance:.2f}"
            )

        if hasattr(market, 'end_time') and market.end_time:
            try:
                end_time = datetime.fromisoformat(market.end_time.replace('Z', '+00:00'))
                if end_time < datetime.now(timezone.utc):
                    checks["market_open"] = False
                    checks["can_proceed"] = False
                    checks["warnings"].append("Market has closed")
            except (ValueError, AttributeError) as e:
                log.debug("Paper: could not parse market end_time: %s", e)

        price = market.up_price if side == "UP" else market.down_price
        if price < 0.01 or price > 0.99:
            checks["price_reasonable"] = False
            checks["warnings"].append(f"Unusual price: ${price:.4f}")

        if price < 0.02 or price > 0.98:
            checks["warnings"].append(
                f"Price near boundary (${price:.4f}) - low liquidity risk"
            )

        if checks["warnings"]:
            log.debug("Paper: pre-trade checks warnings: %s", checks["warnings"])

        return checks

    # ── Database Integration ─────────────────────────────────────────────────────

    def enable_database(self, db_path: str) -> None:
        """Enable database persistence for trades."""
        if not db_path or not isinstance(db_path, str):
            raise ValueError("db_path must be a non-empty string")
        try:
            from ..database.database import TradeDatabase
            self._db = TradeDatabase(db_path)
            self._db_enabled = True
            log.info("Paper: database enabled at %s", db_path)
        except ImportError:
            log.error("Paper: database module not available.")
            self._db_enabled = False
        except Exception as e:
            log.error("Paper: failed to enable database: %s", e)
            self._db_enabled = False
            raise

    def disable_database(self) -> None:
        """Disable database persistence and close connection."""
        if self._db:
            self._db.close()
            self._db = None
        self._db_enabled = False
        log.info("Paper: database disabled")

    @property
    def database(self) -> Optional[TradeDatabase]:
        """Get the database instance if enabled, None otherwise."""
        return self._db if self._db_enabled else None

    def _save_trade_to_db(self, position: PaperPosition) -> None:
        """Save a resolved position as a trade to the database."""
        if not self._db_enabled or self._db is None:
            return
        try:
            total_amount = 0.0
            total_shares = position.shares
            total_fee = 0.0
            entry_price = position.avg_price

            all_orders_map = {o.id: o for o in self._get_all_orders_across_wallets()}
            for order_id in position.order_ids:
                order = all_orders_map.get(order_id)
                if order:
                    total_amount += order.amount
                    total_fee += order.fee
                    if order.status == "filled":
                        entry_price = order.price

            self._db.save_trade(
                market_slug=position.slug,
                market_id=position.market_id,
                side=position.side,
                entry_price=entry_price,
                exit_price=None,
                amount=total_amount,
                shares=total_shares,
                fee=total_fee,
                outcome=position.outcome,
                pnl=position.pnl,
                timestamp=datetime.now(timezone.utc),
            )
            log.debug("Paper: trade saved to database for %s %s", position.slug, position.side)
        except Exception as exc:
            log.error("Paper: failed to save trade to database: %s", exc)

    # ── Price helpers ──────────────────────────────────────────────────────────

    def _get_price_for_side(self, market, side: str) -> tuple[float, str]:
        """Get the best available price for a side, preferring live stream prices."""
        stream = self._attached_streams.get(market.id)
        if stream and stream.running:
            price = stream.up if side == "UP" else stream.down
            if price > 0:
                log.debug("Paper: using live stream price %.4f for %s %s", price, market.slug, side)
                return price, "stream"
            else:
                log.warning("Paper: stream attached but price is 0, falling back to market price")

        price = market.up_price if side == "UP" else market.down_price

        if hasattr(market, 'end_time') and market.end_time:
            try:
                end_time = datetime.fromisoformat(market.end_time.replace('Z', '+00:00'))
                now_dt = datetime.now(timezone.utc)
                time_until_close = (end_time - now_dt).total_seconds()

                if time_until_close <= 0:
                    log.warning("Paper: market %s is closed, price may be stale", market.slug)
                elif time_until_close < PRICE_STALENESS_THRESHOLD:
                    log.warning(
                        "Paper: market %s closes in %.1fs, using potentially stale price %.4f",
                        market.slug, time_until_close, price,
                    )
            except (ValueError, TypeError):
                pass

        if price <= 0:
            log.warning("Paper: market price is invalid (%.4f), using fallback", price)
            return FALLBACK_PRICE, "fallback"

        log.debug("Paper: using market price %.4f for %s %s", price, market.slug, side)
        return price, "market"

    # ── Orders ─────────────────────────────────────────────────────────────────

    def buy(
        self, market, side: str, amount: float,
        stop_loss_pct: float | None = None,
        take_profit_pct: float | None = None,
        time_window_start: Optional[datetime] = None,
        time_window_end: Optional[datetime] = None,
    ) -> PaperOrder:
        """Simulated market buy — fills immediately at the current market price."""
        if stop_loss_pct is not None or take_profit_pct is not None:
            return self.buy_with_tp_sl(
                market, side=side, amount=amount,
                stop_loss_pct=stop_loss_pct,
                take_profit_pct=take_profit_pct,
                time_window_start=time_window_start,
                time_window_end=time_window_end,
            )

        validate_market(market)
        side = validate_side(side)
        amount = validate_positive(float(amount), "amount")

        wallet = self._get_active_wallet()
        price, price_source = self._get_price_for_side(market, side)

        if time_window_start is not None or time_window_end is not None:
            now_dt = datetime.now(timezone.utc)
            if time_window_start is not None and now_dt < time_window_start:
                raise ValueError(f"Cannot buy: current time {now_dt} is before time window start {time_window_start}")
            if time_window_end is not None and now_dt > time_window_end:
                raise ValueError(f"Cannot buy: current time {now_dt} is after time window end {time_window_end}")

        checks = self.pre_trade_checks(market, side, amount, balance=wallet.balance)
        if not checks["can_proceed"]:
            raise ValueError(f"Pre-trade checks failed: {'; '.join(checks['warnings'])}")

        wallet.risk_manager.validate_order(amount, wallet.balance, market.id, wallet._positions)

        self._fee_manager.apply_execution_delay()

        actual_price, filled = self._fee_manager.apply_slippage(price, side)
        if not filled:
            log.debug("Paper: market order not filled due to slippage threshold")
            order_id = new_id()
            order = PaperOrder(
                id=order_id, market_id=market.id, slug=market.slug, side=side,
                price=price, amount=0.0, shares=0.0, fee=0.0, status="cancelled",
                is_limit=False, filled_at=now(),
                time_window_start=time_window_start, time_window_end=time_window_end,
            )
            wallet._orders[order_id] = order
            return order

        order = self._fill(market, side, actual_price, amount, is_limit=False, wallet=wallet)
        order.time_window_start = time_window_start
        order.time_window_end = time_window_end
        return order

    def limit(
        self, market, side: str, price: float, amount: float,
        time_window_start: Optional[datetime] = None,
        time_window_end: Optional[datetime] = None,
    ) -> PaperOrder:
        """Simulated limit order — fills when the streamed price crosses *price*."""
        validate_market(market)
        side = validate_side(side)
        price = validate_price(float(price), "price")
        amount = validate_positive(float(amount), "amount")

        wallet = self._get_active_wallet()

        if amount > wallet.balance:
            raise InsufficientBalance(
                f"Order amount ${amount:.2f} exceeds balance ${wallet.balance:.2f}"
            )

        checks = self.pre_trade_checks(market, side, amount, balance=wallet.balance)
        if not checks["can_proceed"]:
            raise ValueError(f"Pre-trade checks failed: {'; '.join(checks['warnings'])}")

        wallet.risk_manager.validate_order(amount, wallet.balance, market.id, wallet._positions)

        order_id = new_id()
        order = PaperOrder(
            id=order_id, market_id=market.id, slug=market.slug, side=side,
            price=price, amount=amount, shares=0.0, fee=0.0, status="open",
            is_limit=True,
            time_window_start=time_window_start, time_window_end=time_window_end,
        )
        wallet._orders[order_id] = order
        wallet.balance -= amount
        if not self._use_multi_wallet:
            self._balance = wallet.balance
        log.debug("Paper: limit %s @ %.3f $%.2f reserved — balance $%.2f", side, price, amount, wallet.balance)
        return order

    def cancel(self, order_id: str) -> PaperOrder:
        """Cancel an open limit order and refund the reserved balance."""
        if self._use_multi_wallet and self._wallet_manager:
            for wallet in self._wallet_manager.get_all_wallets():
                order = wallet._orders.get(order_id)
                if order is not None:
                    if order.status != "open":
                        raise ValueError(f"Cannot cancel order with status='{order.status}' (must be 'open')")
                    order.status = "cancelled"
                    wallet.balance += order.amount
                    log.info("Paper: cancelled order %s in wallet %s — $%.2f refunded, balance $%.2f",
                             order_id[:8], wallet.wallet_id, order.amount, wallet.balance)
                    return order
            raise OrderNotFound(f"No order found: {order_id}")

        order = self._orders.get(order_id)
        if order is None:
            raise OrderNotFound(f"No order found: {order_id}")
        if order.status != "open":
            raise ValueError(f"Cannot cancel order with status='{order.status}' (must be 'open')")

        order.status = "cancelled"
        self._balance += order.amount
        log.info("Paper: cancelled order %s — $%.2f refunded, balance $%.2f", order_id[:8], order.amount, self._balance)
        return order

    def buy_with_tp_sl(
        self, market, side: str, amount: float,
        stop_loss: float | None = None, take_profit: float | None = None,
        stop_loss_pct: float | None = None, take_profit_pct: float | None = None,
        trail_sl: float | None = None, trail_tp: float | None = None,
        time_window_start: Optional[datetime] = None,
        time_window_end: Optional[datetime] = None,
    ) -> PaperOrder:
        """Market buy with optional stop-loss and take-profit."""
        validate_market(market)
        side = validate_side(side)
        amount = validate_positive(float(amount), "amount")

        wallet = self._get_active_wallet()
        price, price_source = self._get_price_for_side(market, side)

        if time_window_start is not None or time_window_end is not None:
            now_dt = datetime.now(timezone.utc)
            if time_window_start is not None and now_dt < time_window_start:
                raise ValueError(f"Cannot buy: current time {now_dt} is before time window start {time_window_start}")
            if time_window_end is not None and now_dt > time_window_end:
                raise ValueError(f"Cannot buy: current time {now_dt} is after time window end {time_window_end}")

        checks = self.pre_trade_checks(market, side, amount, balance=wallet.balance)
        if not checks["can_proceed"]:
            raise ValueError(f"Pre-trade checks failed: {'; '.join(checks['warnings'])}")

        wallet.risk_manager.validate_order(amount, wallet.balance, market.id, wallet._positions)

        if stop_loss is not None:
            stop_loss = validate_price(float(stop_loss), "stop_loss")
        if take_profit is not None:
            take_profit = validate_price(float(take_profit), "take_profit")
        if stop_loss_pct is not None:
            stop_loss_pct = validate_positive(float(stop_loss_pct), "stop_loss_pct")
        if take_profit_pct is not None:
            take_profit_pct = validate_positive(float(take_profit_pct), "take_profit_pct")
        if trail_sl is not None:
            trail_sl = validate_positive(float(trail_sl), "trail_sl")
        if trail_tp is not None:
            trail_tp = validate_positive(float(trail_tp), "trail_tp")

        self._fee_manager.apply_execution_delay()
        actual_price, filled = self._fee_manager.apply_slippage(price, side)
        if not filled:
            log.debug("Paper: market order not filled due to slippage threshold")
            order_id = new_id()
            order = PaperOrder(
                id=order_id, market_id=market.id, slug=market.slug, side=side,
                price=price, amount=0.0, shares=0.0, fee=0.0, status="cancelled",
                is_limit=False, filled_at=now(),
            )
            wallet._orders[order_id] = order
            return order

        order = self._fill(market, side, actual_price, amount, is_limit=False, wallet=wallet)

        if stop_loss_pct is not None and stop_loss is None:
            if side == "UP":
                stop_loss = round(actual_price * (1 - stop_loss_pct), PRICE_ROUNDING)
            else:
                stop_loss = round(actual_price * (1 + stop_loss_pct), PRICE_ROUNDING)
        if take_profit_pct is not None and take_profit is None:
            if side == "UP":
                take_profit = round(actual_price * (1 + take_profit_pct), PRICE_ROUNDING)
            else:
                take_profit = round(actual_price * (1 - take_profit_pct), PRICE_ROUNDING)

        order.stop_loss = stop_loss
        order.take_profit = take_profit
        order.stop_loss_pct = stop_loss_pct
        order.take_profit_pct = take_profit_pct
        order.trail_sl = trail_sl
        order.trail_tp = trail_tp
        order.time_window_start = time_window_start
        order.time_window_end = time_window_end

        if trail_sl is not None:
            order.trail_sl_price = actual_price * (1 - trail_sl) if side == "UP" else actual_price * (1 + trail_sl)
        if trail_tp is not None:
            order.trail_tp_price = actual_price * (1 + trail_tp) if side == "UP" else actual_price * (1 - trail_tp)

        log.info(
            "Paper: buy_with_tp_sl %s @ %.3f SL=%.3f TP=%.3f SL_pct=%.3f TP_pct=%.3f trail_SL=%.3f trail_TP=%.3f",
            side, actual_price, stop_loss or 0, take_profit or 0,
            stop_loss_pct or 0, take_profit_pct or 0, trail_sl or 0, trail_tp or 0,
        )
        return order

    def sell_position(
        self, market, side: str, amount: float | None = None, wallet=None,
    ) -> PaperOrder:
        """Sell/close a position (simulated sell for prediction markets)."""
        validate_market(market)
        side = validate_side(side)
        if wallet is None:
            wallet = self._get_active_wallet()
        key = f"{market.id}:{side}"

        if key not in wallet._positions:
            raise ValueError(f"No position found for {market.slug} {side}")

        position = wallet._positions[key]
        current_price = position.current_price

        if current_price <= 0:
            current_price = FALLBACK_PRICE

        if position.shares <= 0:
            raise ValueError(f"Position has no shares to sell: {position.shares}")

        if amount is None:
            sell_shares = position.shares
            sell_amount = sell_shares * current_price
        else:
            amount = validate_positive(float(amount), "amount")
            sell_shares = amount / current_price
            sell_amount = amount
            if sell_shares > position.shares:
                raise ValueError(f"Cannot sell {sell_shares:.4f} shares, only {position.shares:.4f} available")

        self._fee_manager.apply_execution_delay()
        actual_price, filled = self._fee_manager.apply_slippage(current_price, side)
        if not filled:
            log.debug("Paper: sell order not filled due to slippage threshold")
            order_id = new_id()
            order = PaperOrder(
                id=order_id, market_id=market.id, slug=market.slug, side=side,
                price=current_price, amount=0.0, shares=0.0, fee=0.0,
                status="cancelled", is_limit=False, filled_at=now(),
            )
            wallet._orders[order_id] = order
            return order

        fee, rebate_amount, rebate_rate, fee_type = self._fee_manager.calculate_fee(
            sell_amount, actual_price, sell_shares, is_maker=False
        )
        net_amount = sell_amount - fee

        if self._config.fee_mode == "polymarket":
            sell_shares = round(net_amount / actual_price, SHARE_ROUNDING) if actual_price > 0 else 0.0
            fee, rebate_amount, rebate_rate, fee_type = self._fee_manager.calculate_fee(
                net_amount, actual_price, sell_shares, is_maker=False
            )
            net_amount = sell_amount - fee

        wallet.balance += net_amount
        if not self._use_multi_wallet:
            self._balance = wallet.balance

        order_id = new_id()
        order = PaperOrder(
            id=order_id, market_id=market.id, slug=market.slug, side=side,
            price=actual_price, amount=sell_amount, shares=sell_shares, fee=fee,
            status="filled", is_limit=False, filled_at=now(),
        )
        wallet._orders[order_id] = order

        closed_cost_basis = position.cost_basis
        position.shares -= sell_shares
        if position.shares <= 0.001:
            position.shares = 0
            position.resolved = True
            position.outcome = "CLOSED"
            pnl = net_amount - closed_cost_basis
            wallet.risk_manager.record_trade(pnl)
            log.info("Paper: closed position %s %s — proceeds $%.2f, balance $%.2f",
                     market.slug, side, net_amount, wallet.balance)
            self._save_trade_to_db(position)
        else:
            log.info("Paper: reduced position %s %s by %.2f shares — proceeds $%.2f",
                     market.slug, side, sell_shares, net_amount)

        return order

    def set_trailing_sl(self, order_id: str, trail_distance: float) -> PaperOrder:
        """Set or update trailing stop-loss on an existing order."""
        trail_distance = validate_positive(float(trail_distance), "trail_distance")
        order, _ = self._find_order_across_wallets(order_id)
        if order.status != "filled":
            raise ValueError(f"Can only set trailing SL on filled orders, got status='{order.status}'")

        order.trail_sl = trail_distance
        order.trail_sl_price = order.price * (1 - trail_distance) if order.side == "UP" else order.price * (1 + trail_distance)

        log.info("Paper: set trailing SL %.2f%% on order %s @ %.3f",
                 trail_distance * 100, order_id[:8], order.trail_sl_price)
        return order

    def set_trailing_tp(self, order_id: str, trail_distance: float) -> PaperOrder:
        """Set or update trailing take-profit on an existing order."""
        trail_distance = validate_positive(float(trail_distance), "trail_distance")
        order, _ = self._find_order_across_wallets(order_id)
        if order.status != "filled":
            raise ValueError(f"Can only set trailing TP on filled orders, got status='{order.status}'")

        order.trail_tp = trail_distance
        order.trail_tp_price = order.price * (1 + trail_distance) if order.side == "UP" else order.price * (1 - trail_distance)

        log.info("Paper: set trailing TP %.2f%% on order %s @ %.3f",
                 trail_distance * 100, order_id[:8], order.trail_tp_price)
        return order

    def set_stop_loss(self, market, side: str, stop_price: float) -> None:
        """Set stop loss for a position."""
        validate_market(market)
        side = validate_side(side)
        stop_price = validate_price(float(stop_price), "stop_price")
        pos, _ = self._find_position_across_wallets(market.id, side)
        pos.stop_loss = stop_price
        log.info("Stop loss set at $%.4f for %s %s", stop_price, market.slug, side)

    def set_take_profit(self, market, side: str, profit_price: float) -> None:
        """Set take profit for a position."""
        validate_market(market)
        side = validate_side(side)
        profit_price = validate_price(float(profit_price), "profit_price")
        pos, _ = self._find_position_across_wallets(market.id, side)
        pos.take_profit = profit_price
        log.info("Take profit set at $%.4f for %s %s", profit_price, market.slug, side)

    def set_trailing_stop(self, market, side: str, trail_distance: float) -> None:
        """Set trailing stop loss for a position."""
        validate_market(market)
        side = validate_side(side)
        trail_distance = validate_positive(float(trail_distance), "trail_distance")
        position, _ = self._find_position_across_wallets(market.id, side)

        if not hasattr(position, 'trail_sl'):
            position.trail_sl = None
        if not hasattr(position, 'trail_sl_price'):
            position.trail_sl_price = None

        position.trail_sl = trail_distance
        position.trail_sl_price = position.current_price - trail_distance if side == "UP" else position.current_price + trail_distance

        log.info("Trailing stop set at %.4f distance for %s %s", trail_distance, market.slug, side)

    def set_stop_loss_pct(self, market, side: str, sl_pct: float) -> None:
        """Set stop loss for a position as a percentage of the entry price."""
        validate_market(market)
        side = validate_side(side)
        sl_pct = validate_positive(float(sl_pct), "sl_pct")

        position, wallet = self._find_position_across_wallets(market.id, side)
        position.stop_loss_pct = sl_pct
        if side == "UP":
            position.stop_loss = round(position.avg_price * (1 - sl_pct), PRICE_ROUNDING)
        else:
            position.stop_loss = round(position.avg_price * (1 + sl_pct), PRICE_ROUNDING)

        for oid in position.order_ids:
            order = wallet._orders.get(oid)
            if order:
                order.stop_loss_pct = sl_pct
                order.stop_loss = position.stop_loss

        log.info("Stop loss set at %.2f%% ($%.4f) for %s %s",
                 sl_pct * 100, position.stop_loss, market.slug, side)

    def set_take_profit_pct(self, market, side: str, tp_pct: float) -> None:
        """Set take profit for a position as a percentage of the entry price."""
        validate_market(market)
        side = validate_side(side)
        tp_pct = validate_positive(float(tp_pct), "tp_pct")

        position, wallet = self._find_position_across_wallets(market.id, side)
        position.take_profit_pct = tp_pct
        if side == "UP":
            position.take_profit = round(position.avg_price * (1 + tp_pct), PRICE_ROUNDING)
        else:
            position.take_profit = round(position.avg_price * (1 - tp_pct), PRICE_ROUNDING)

        for oid in position.order_ids:
            order = wallet._orders.get(oid)
            if order:
                order.take_profit_pct = tp_pct
                order.take_profit = position.take_profit

        log.info("Take profit set at %.2f%% ($%.4f) for %s %s",
                 tp_pct * 100, position.take_profit, market.slug, side)

    def oco_order(
        self, market, side: str, amount: float,
        stop_loss: float, take_profit: float,
    ) -> tuple[PaperOrder, PaperOrder]:
        """One-Cancels-Other (OCO) order."""
        validate_market(market)
        side = validate_side(side)
        amount = validate_positive(float(amount), "amount")
        stop_loss = validate_price(float(stop_loss), "stop_loss")
        take_profit = validate_price(float(take_profit), "take_profit")

        main_order = self.buy_with_tp_sl(
            market, side=side, amount=amount,
            stop_loss=stop_loss, take_profit=take_profit,
        )

        oco_id = new_id()
        oco_order = PaperOrder(
            id=oco_id, market_id=main_order.market_id, slug=main_order.slug,
            side="DOWN" if side == "UP" else "UP",
            price=main_order.price, amount=main_order.amount, shares=main_order.shares,
            fee=main_order.fee, status="filled", is_limit=False,
            filled_at=main_order.filled_at,
            stop_loss=main_order.stop_loss, take_profit=main_order.take_profit,
        )
        main_order.oco_order_id = oco_id
        oco_order.oco_order_id = main_order.id
        _, oco_wallet = self._find_order_across_wallets(main_order.id)
        oco_wallet._orders[oco_id] = oco_order

        log.info("Paper: OCO orders created %s / %s SL=%.3f TP=%.3f",
                 main_order.id[:8], oco_id[:8], stop_loss, take_profit)

        return main_order, oco_order

    # ── Queries ────────────────────────────────────────────────────────────────

    def open(self) -> list[PaperOrder]:
        """Return all open (pending) limit orders."""
        if self._use_multi_wallet and self._wallet_manager:
            all_orders = []
            for wallet in self._wallet_manager.get_all_wallets():
                all_orders.extend([o for o in wallet._orders.values() if o.status == "open"])
            return all_orders
        return [o for o in self._orders.values() if o.status == "open"]

    def orders(self) -> list[PaperOrder]:
        """Return all orders (open, filled, and cancelled)."""
        if self._use_multi_wallet and self._wallet_manager:
            all_orders = []
            for wallet in self._wallet_manager.get_all_wallets():
                all_orders.extend(list(wallet._orders.values()))
            return all_orders
        return list(self._orders.values())

    def positions(self) -> list[PaperPosition]:
        """Return all live (unresolved) positions."""
        if self._use_multi_wallet and self._wallet_manager:
            all_positions = []
            for wallet in self._wallet_manager.get_all_wallets():
                all_positions.extend([p for p in wallet._positions.values() if not p.resolved])
            return all_positions
        return [p for p in self._positions.values() if not p.resolved]

    def all_positions(self) -> list[PaperPosition]:
        """Return all positions including resolved ones."""
        if self._use_multi_wallet and self._wallet_manager:
            all_positions = []
            for wallet in self._wallet_manager.get_all_wallets():
                all_positions.extend(list(wallet._positions.values()))
            return all_positions
        return list(self._positions.values())

    def show_positions(self, show_all: bool = False, verbose: bool = True) -> None:
        """Display positions with entry/exit information and ROI."""
        from .paper_reporting import show_positions as _show_positions
        _show_positions(self, show_all=show_all, verbose=verbose)

    def position_history(self) -> dict:
        """Get position history summary statistics."""
        from .paper_reporting import get_position_history as _get_position_history
        return _get_position_history(self)

    # ── Resolution ─────────────────────────────────────────────────────────────

    def resolve(self, market, outcome: str) -> None:
        """Mark all positions for *market* as resolved."""
        validate_market(market)
        outcome = outcome.upper()
        if outcome not in ("UP", "DOWN"):
            raise ValueError(f"outcome must be 'UP' or 'DOWN', got '{outcome}'")

        if self._use_multi_wallet and self._wallet_manager:
            for wallet in self._wallet_manager.get_all_wallets():
                for pos in wallet._positions.values():
                    if pos.market_id == market.id and not pos.resolved:
                        pos.resolved = True
                        pos.outcome = "WON" if pos.side == outcome else "LOST"
                        payout = pos.shares if pos.outcome == "WON" else 0.0
                        wallet.balance += payout
                        wallet.risk_manager.record_trade(pos.pnl)
                        log.info("Paper: resolved %s in wallet %s  -> %s  payout=$%.2f  balance=$%.2f",
                                 pos.slug, wallet.wallet_id, pos.outcome, payout, wallet.balance)
                        self._save_trade_to_db(pos)
        else:
            for pos in self._positions.values():
                if pos.market_id == market.id and not pos.resolved:
                    pos.resolved = True
                    pos.outcome = "WON" if pos.side == outcome else "LOST"
                    payout = pos.shares if pos.outcome == "WON" else 0.0
                    self._balance += payout
                    self._risk_manager.record_trade(pos.pnl)
                    log.info("Paper: resolved %s -> %s  payout=$%.2f  balance=$%.2f",
                             pos.slug, pos.outcome, payout, self._balance)
                    self._save_trade_to_db(pos)

    # ── Stream integration ─────────────────────────────────────────────────────

    def check_limits(self, market_id: str, up_price: float, down_price: float) -> None:
        """Update live position prices and fill any triggered limit orders."""
        up_price = validate_price(float(up_price), "up_price")
        down_price = validate_price(float(down_price), "down_price")

        if self._use_multi_wallet and self._wallet_manager:
            for wallet in self._wallet_manager.get_all_wallets():
                self._check_limits_for_wallet(wallet, market_id, up_price, down_price)
        else:
            self._check_limits_for_wallet(self._get_active_wallet(), market_id, up_price, down_price)

    def _check_limits_for_wallet(self, wallet, market_id: str, up_price: float, down_price: float) -> None:
        """Check limits for a single wallet."""
        for pos in wallet._positions.values():
            if pos.market_id == market_id and not pos.resolved:
                pos.current_price = up_price if pos.side == "UP" else down_price

        for order in list(wallet._orders.values()):
            if order.status != "open" or order.market_id != market_id:
                continue
            order.check_count += 1

            if not self._should_check_order(order):
                log.debug("Paper: limit order %s skipped - check count %d exceeds check_mode %s",
                          order.id[:8], order.check_count, self._config.check_mode)
                continue

            current = up_price if order.side == "UP" else down_price
            if current >= order.price:
                if self._is_within_time_window(order):
                    self._fill_limit(order, current, wallet=wallet)
                else:
                    log.debug("Paper: limit order %s not filled - outside time window", order.id[:8])

        self._check_tp_sl_for_wallet(wallet, market_id, up_price, down_price)

    def _is_within_time_window(self, order: PaperOrder) -> bool:
        """Check if current time is within the order's time window."""
        if order.time_window_start is None and order.time_window_end is None:
            return True
        now_dt = datetime.now(timezone.utc)
        if order.time_window_start is not None and now_dt < order.time_window_start:
            return False
        if order.time_window_end is not None and now_dt > order.time_window_end:
            return False
        return True

    def _should_check_order(self, order: PaperOrder) -> bool:
        """Check if an order should be checked based on check_mode configuration."""
        check_mode = self._config.check_mode
        if check_mode == "continuous":
            return True
        if check_mode == "once":
            return order.check_count <= 1
        if isinstance(check_mode, int):
            return order.check_count <= check_mode
        return True

    def _check_tp_sl_for_wallet(self, wallet, market_id: str, up_price: float, down_price: float) -> None:
        """Check and trigger TP/SL orders for a single wallet."""
        for order in list(wallet._orders.values()):
            if order.status != "filled" or order.market_id != market_id:
                continue
            if (order.stop_loss is None and order.take_profit is None
                    and order.stop_loss_pct is None and order.take_profit_pct is None
                    and order.trail_sl is None and order.trail_tp is None):
                continue
            if order.tp_sl_triggered_by is not None:
                continue

            current_price = up_price if order.side == "UP" else down_price
            triggered = None

            if order.trail_sl is not None:
                new_trail_sl = current_price * (1 - order.trail_sl) if order.side == "UP" else current_price * (1 + order.trail_sl)
                if order.side == "UP":
                    if new_trail_sl > (order.trail_sl_price or 0):
                        order.trail_sl_price = new_trail_sl
                        log.debug("Paper: trailing SL moved up to %.3f for order %s", new_trail_sl, order.id[:8])
                else:
                    if new_trail_sl < (order.trail_sl_price or float('inf')):
                        order.trail_sl_price = new_trail_sl
                        log.debug("Paper: trailing SL moved down to %.3f for order %s", new_trail_sl, order.id[:8])

            if order.trail_tp is not None:
                new_trail_tp = current_price * (1 + order.trail_tp) if order.side == "UP" else current_price * (1 - order.trail_tp)
                if order.side == "UP":
                    if new_trail_tp > (order.trail_tp_price or 0):
                        order.trail_tp_price = new_trail_tp
                        log.debug("Paper: trailing TP moved up to %.3f for order %s", new_trail_tp, order.id[:8])
                else:
                    if new_trail_tp < (order.trail_tp_price or float('inf')):
                        order.trail_tp_price = new_trail_tp
                        log.debug("Paper: trailing TP moved down to %.3f for order %s", new_trail_tp, order.id[:8])

            if order.stop_loss_pct is not None and order.stop_loss is None:
                if order.side == "UP":
                    order.stop_loss = round(order.price * (1 - order.stop_loss_pct), PRICE_ROUNDING)
                else:
                    order.stop_loss = round(order.price * (1 + order.stop_loss_pct), PRICE_ROUNDING)
            if order.take_profit_pct is not None and order.take_profit is None:
                if order.side == "UP":
                    order.take_profit = round(order.price * (1 + order.take_profit_pct), PRICE_ROUNDING)
                else:
                    order.take_profit = round(order.price * (1 - order.take_profit_pct), PRICE_ROUNDING)

            sl_trigger = order.stop_loss if order.stop_loss is not None else order.trail_sl_price
            if sl_trigger is not None:
                if order.side == "UP" and current_price <= sl_trigger:
                    triggered = "sl"
                elif order.side == "DOWN" and current_price >= sl_trigger:
                    triggered = "sl"

            tp_trigger = order.take_profit if order.take_profit is not None else order.trail_tp_price
            if tp_trigger is not None and triggered is None:
                if order.side == "UP" and current_price >= tp_trigger:
                    triggered = "tp"
                elif order.side == "DOWN" and current_price <= tp_trigger:
                    triggered = "tp"

            if triggered:
                order.tp_sl_triggered_by = triggered
                log.debug("Paper: %s triggered for order %s @ %.3f (trigger: %.3f)",
                          "STOP-LOSS" if triggered == "sl" else "TAKE-PROFIT",
                          order.id[:8], current_price, sl_trigger if triggered == "sl" else tp_trigger)

                if order.oco_order_id and order.oco_order_id != order.id:
                    try:
                        oco_order, _ = self._find_order_across_wallets(order.oco_order_id)
                        if oco_order and oco_order.status == "filled":
                            oco_order.stop_loss = None
                            oco_order.take_profit = None
                            oco_order.trail_sl = None
                            oco_order.trail_tp = None
                            log.info("Paper: cancelled OCO linked order %s", order.oco_order_id[:8])
                    except OrderNotFound:
                        pass

                try:
                    self.sell_position(
                        type('obj', (object,), {
                            'id': order.market_id,
                            'slug': order.slug,
                            'question': order.slug,
                            'up_price': up_price,
                            'down_price': down_price,
                        })(),
                        side=order.side,
                        wallet=wallet,
                    )
                except ValueError as e:
                    log.warning("Paper: failed to sell position on %s trigger: %s", triggered, e)

    def attach_stream(self, stream, market) -> None:
        """Wire *stream* so positions auto-update and limits auto-fill."""
        validate_market(market)
        self._attached_streams[market.id] = stream

        @stream.on("price")
        def _on_price(up: float, down: float) -> None:
            self.check_limits(market.id, up, down)

        @stream.on("close")
        def _on_close() -> None:
            log.info("Paper: stream closed for %s — call paper.resolve(market, outcome)", market.slug)
            self._attached_streams.pop(market.id, None)

        log.info("Paper: stream attached for %s", market.slug)

    # ── Fee Rebate Reporting ─────────────────────────────────────────────────────

    def fee_summary(self) -> None:
        """Print a detailed fee and rebate summary."""
        from .paper_reporting import print_fee_summary as _print_fee_summary
        _print_fee_summary(self)

    def get_rebate_stats(self) -> dict:
        """Get rebate statistics as a dictionary."""
        from .paper_reporting import get_rebate_stats as _get_rebate_stats
        return _get_rebate_stats(self)

    # ── Reporting ──────────────────────────────────────────────────────────────

    def summary(self) -> None:
        """Print a formatted P&L summary to stdout."""
        from .paper_reporting import print_summary as _print_summary
        _print_summary(self)

    # ── Internal ───────────────────────────────────────────────────────────────

    def _fill(
        self, market, side: str, price: float, amount: float,
        is_limit: bool, wallet=None,
    ) -> PaperOrder:
        """Execute a simulated fill and update the position book."""
        if wallet is None:
            wallet = self._get_active_wallet()

        if amount > wallet.balance:
            raise InsufficientBalance(
                f"Order amount ${amount:.2f} exceeds balance ${wallet.balance:.2f}"
            )

        if price <= 0:
            raise ValueError(f"Price must be positive, got {price}")

        shares = round(amount / price, SHARE_ROUNDING) if price > 0 else 0.0
        if shares <= 0:
            raise ValueError(
                f"Calculated shares is zero or negative (amount=${amount:.2f}, price=${price:.4f})"
            )

        fee, rebate_amount, rebate_rate, fee_type = self._fee_manager.calculate_fee(
            amount, price, shares, is_maker=is_limit,
        )
        net = amount - fee + rebate_amount
        shares = round(net / price, SHARE_ROUNDING) if price > 0 else 0.0

        if self._config.fee_mode == "polymarket":
            fee, rebate_amount, rebate_rate, fee_type = self._fee_manager.calculate_fee(
                net, price, shares, is_maker=is_limit,
            )

        wallet.balance -= amount
        if not self._use_multi_wallet:
            self._balance = wallet.balance

        self._fee_manager.track_fee_and_rebate(fee, rebate_amount, fee_type, amount)

        order = PaperOrder(
            id=new_id(), market_id=market.id, slug=market.slug, side=side,
            price=price, amount=amount, shares=shares, fee=fee, status="filled",
            is_limit=is_limit, filled_at=now(),
            fee_type=fee_type, rebate_amount=rebate_amount, rebate_rate=rebate_rate,
        )
        wallet._orders[order.id] = order

        self._upsert_position(market.id, market.slug, market.question, side, shares, price, order.id, wallet=wallet)
        log.debug("Paper: filled %s %.4f shares @ %.3f  fee=$%.4f  rebate=$%.4f  balance=$%.2f",
                  side, shares, price, fee, rebate_amount, wallet.balance)
        return order

    def _fill_limit(self, order: PaperOrder, current_price: float, wallet=None) -> None:
        """Fill a pending limit order at *current_price* (balance already reserved)."""
        if wallet is None:
            try:
                _, wallet = self._find_order_across_wallets(order.id)
            except OrderNotFound:
                log.error("Paper: order %s not found in any wallet, cannot fill", order.id[:8])
                order.status = "cancelled"
                return

        def _refund(w, order):
            w.balance += order.amount
            if not self._use_multi_wallet:
                self._balance = w.balance

        if current_price <= 0:
            log.warning("Paper: invalid current price %.4f for limit order %s, cancelling", current_price, order.id[:8])
            order.status = "cancelled"
            _refund(wallet, order)
            return

        if not self._fee_manager.check_fill_probability():
            log.debug("Paper: limit order %s not filled due to fill probability %.2f",
                      order.id[:8], self._config.fill_probability)
            order.status = "cancelled"
            _refund(wallet, order)
            return

        actual_price, filled = self._fee_manager.apply_slippage(current_price, order.side)
        if not filled:
            log.debug("Paper: limit order %s not filled due to slippage threshold", order.id[:8])
            order.status = "cancelled"
            _refund(wallet, order)
            return

        shares = round(order.amount / actual_price, SHARE_ROUNDING) if actual_price > 0 else 0.0
        if shares <= 0:
            log.warning("Paper: calculated shares is zero for limit order %s (amount=$%.2f, price=$%.4f), cancelling",
                        order.id[:8], order.amount, actual_price)
            order.status = "cancelled"
            _refund(wallet, order)
            return

        fee, rebate_amount, rebate_rate, fee_type = self._fee_manager.calculate_fee(
            order.amount, actual_price, shares, is_maker=True,
        )
        net = order.amount - fee + rebate_amount
        shares = round(net / actual_price, SHARE_ROUNDING) if actual_price > 0 else 0.0

        if self._config.fee_mode == "polymarket":
            fee, rebate_amount, rebate_rate, fee_type = self._fee_manager.calculate_fee(
                net, actual_price, shares, is_maker=True,
            )

        self._fee_manager.track_fee_and_rebate(fee, rebate_amount, fee_type, order.amount)

        order.price = actual_price
        order.shares = shares
        order.fee = fee
        order.status = "filled"
        order.filled_at = now()
        order.fee_type = fee_type
        order.rebate_amount = rebate_amount
        order.rebate_rate = rebate_rate

        question = next(
            (p.question for p in wallet._positions.values() if p.market_id == order.market_id),
            "",
        )
        self._upsert_position(
            order.market_id, order.slug, question, order.side, shares, actual_price, order.id, wallet=wallet,
        )
        log.debug("Paper: limit filled %s %.4f shares @ %.3f  fee=$%.4f  rebate=$%.4f",
                  order.side, shares, actual_price, fee, rebate_amount)

    def _upsert_position(
        self, market_id: str, slug: str, question: str, side: str,
        shares: float, price: float, order_id: str,
        wallet=None,
    ) -> None:
        """Merge *shares* into an existing position or create a new one."""
        if wallet is None:
            wallet = self._get_active_wallet()

        key = f"{market_id}:{side}"
        if key in wallet._positions:
            pos = wallet._positions[key]
            total = pos.shares + shares
            pos.avg_price = round(
                (pos.shares * pos.avg_price + shares * price) / total, PRICE_ROUNDING,
            )
            pos.shares = total
            pos.order_ids.append(order_id)
        else:
            wallet._positions[key] = PaperPosition(
                market_id=market_id, slug=slug, question=question, side=side,
                shares=shares, avg_price=price, current_price=price, order_ids=[order_id],
            )
