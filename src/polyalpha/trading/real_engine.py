"""Real trading engine — actual fund execution via Polymarket CLOB.

Refactored: large blocks extracted to real_fills.py, real_position_sync.py,
real_risk_controls.py, real_advanced.py, real_helpers.py and staleness.py.
This file remains the facade and preserves backward-compatible imports.
"""

from __future__ import annotations

import logging
import threading
import time
from datetime import datetime, timezone
from typing import TYPE_CHECKING, Optional

if TYPE_CHECKING:
    from ..database.database import TradeDatabase
    from .auto_redeem import AutoRedeemEngine, AutoRedeemConfig

from ..core import (
    InsufficientBalance,
    InsufficientAllowance,
    OrderNotFound,
    PositionNotFound,
    RiskLimitExceeded,
    OrderCancelled,
    NetworkError,
    TransientError,
    OrderRejected,
    OrderTimeout,
    CircuitBreakerOpenError,
    ManualInterventionRequiredError,
    TransactionRollbackError,
    BackupError,
    GasEstimationError,
    TransactionRebroadcastError,
    PRICE_STALENESS_THRESHOLD,
    FALLBACK_PRICE,
    MAX_ORDER_PRICE,
    FEE_ROUNDING,
    calculate_polymarket_fee,
    fee_rate_for_category,
)
from .clob_client import ClobClient
from .alchemy_client import AlchemyClient
from .wallet import RealWallet, RealTradingWalletManager, WalletSelectionStrategy
from .error_handling import (
    CircuitBreaker,
    ErrorRecoveryManager,
    GracefulDegradation,
    TransactionRollbackManager,
    DisasterRecovery,
    DegradationLevel,
)
from .real_config import RealTradingConfig
from .real_orders import RealOrder, RealPosition, OCOOrder, BracketOrder, ConditionalOrder, IcebergOrder, TWAPOrder
from .real_position_sizing import (
    PositionSizer,
    FixedPositionSizer,
    PercentagePositionSizer,
    KellyPositionSizer,
    HybridPositionSizer,
)
from .real_risk import RiskManager
from .real_wallet import WalletManager
from ..report.engine import ReportEngine
from .real_fills import RealFillsMixin
from .real_position_sync import RealPositionSyncMixin
from .real_risk_controls import RealRiskControlsMixin
from .real_advanced import RealAdvancedMixin


log = logging.getLogger(__name__)

class RealTradingEngine(RealFillsMixin, RealPositionSyncMixin, RealRiskControlsMixin, RealAdvancedMixin):
    """
    Real trading engine with actual fund execution via Polymarket CLOB.

    Features:
    - Wallet integration (USDC balance on Polygon)
    - Real order execution with signing
    - Position sizing strategies (fixed, percentage, Kelly)
    - Risk management (stop loss, take profit, position limits)
    - Safety checks and confirmations
    - Real-time balance tracking
    - Trade persistence to database

    Parameters
    ----------
    private_key : str
        Private key for wallet operations
    rpc_url : str
        Polygon RPC URL for blockchain interaction
    polymarket_api_key : str
        Polymarket API key for CLOB access
    config : RealTradingConfig, optional
        Configuration for real trading
    db_path : str, optional
        Path to SQLite database for trade persistence
    simulate : bool, optional
        Enable simulation mode for testing (default: False)
    """

    def __init__(
        self,
        private_key: str,
        rpc_url: str,
        polymarket_api_key: str,
        polymarket_api_secret: str = "",
        polymarket_api_passphrase: str = "",
        config: Optional[RealTradingConfig] = None,
        db_path: Optional[str] = None,
        db: Optional[TradeDatabase] = None,
        simulate: bool = False,
    ):
        # Configuration
        self._config = config or RealTradingConfig(
            private_key=private_key,
            rpc_url=rpc_url,
            polymarket_api_key=polymarket_api_key,
            polymarket_api_secret=polymarket_api_secret,
            polymarket_api_passphrase=polymarket_api_passphrase,
        )

        # Validate credentials for real trading
        if not simulate:
            self._validate_credentials(private_key, polymarket_api_key, rpc_url)
        else:
            log.warning("⚠️  SIMULATION MODE ENABLED - No real trades will be executed")
            log.warning("Set simulate=False for production trading")

        self._simulate = simulate
        # Wallet setup (matic price configurable via RealTradingConfig.matic_price_usd)
        self._wallet = WalletManager(
            private_key,
            rpc_url,
            log_balance_updates=self._config.log_balance_updates,
            matic_price_usd=getattr(self._config, "matic_price_usd", 0.5),
        )
        self._balance: float = 0.0
        self._allowance: float = 0.0

        # Order management
        self._orders: dict[str, RealOrder] = {}
        self._positions: dict[str, RealPosition] = {}  # key: "{market_id}:{side}"

        # Position lock for thread-safe position share modifications
        self._position_lock: threading.RLock = threading.RLock()

        # Advanced order types storage
        self._oco_orders: dict[str, OCOOrder] = {}
        self._bracket_orders: dict[str, BracketOrder] = {}
        self._conditional_orders: dict[str, ConditionalOrder] = {}
        self._iceberg_orders: dict[str, IcebergOrder] = {}
        self._twap_orders: dict[str, TWAPOrder] = {}

        # Position sizing
        self._position_sizer: PositionSizer = self._create_position_sizer()

        # Risk management
        self._risk_manager = RiskManager(self._config)

        # CLOB client
        self._clob_client = ClobClient(
            api_key=polymarket_api_key,
            private_key=private_key,
            rpc_url=rpc_url,
            api_secret=polymarket_api_secret or self._config.polymarket_api_secret or None,
            api_passphrase=polymarket_api_passphrase or self._config.polymarket_api_passphrase or None,
            timeout=self._config.order_timeout,
            retry_attempts=self._config.retry_attempts,
            retry_delay=self._config.retry_delay,
            simulate=simulate,
        )

        # Alchemy Client
        self._alchemy_client = AlchemyClient(rpc_url=rpc_url)

        # Database
        self._db: Optional[TradeDatabase] = None
        self._db_enabled: bool = False
        if db:
            self._db = db
            self._db_enabled = True
        elif db_path:
            self.enable_database(db_path)

        # Reporting
        self.report = ReportEngine(self)

        # Emergency mode
        self._emergency_mode: bool = False
        
        # Position sync caching
        self._last_position_sync: float = 0.0
        self._position_sync_ttl: float = 30.0  # seconds before re-syncing from chain
        
        # Stream tracking for price-aware trading
        self._attached_streams: dict[str, "Stream"] = {}  # market_id -> Stream

        # Auto-redeem engine (lazy-initialized)
        self._auto_redeem: Optional[AutoRedeemEngine] = None

        # Error handling components
        self._clob_circuit_breaker = CircuitBreaker(
            name="clob_api",
            failure_threshold=5,
            recovery_timeout=60,
            expected_exception=(NetworkError, OrderTimeout),
        )
        self._wallet_circuit_breaker = CircuitBreaker(
            name="wallet_rpc",
            failure_threshold=3,
            recovery_timeout=120,
            expected_exception=(NetworkError,),
        )
        self._error_recovery = ErrorRecoveryManager()
        self._graceful_degradation = GracefulDegradation()
        self._transaction_rollback = TransactionRollbackManager()
        self._disaster_recovery = DisasterRecovery()

        # Multi-wallet mode
        self._use_multi_wallet: bool = False
        self._real_wallet_manager: Optional[RealTradingWalletManager] = None
        self._active_wallet_id: Optional[str] = None

        # Initialize balance
        self.refresh_balance()

        log.info("RealTradingEngine initialized with comprehensive error handling")

    def _validate_credentials(self, private_key: str, polymarket_api_key: str, rpc_url: str) -> None:
        """
        Validate that real trading credentials are provided and not placeholder values.

        Raises
        ------
        ValueError
            If credentials appear to be placeholder or invalid values
        """
        # Check for common placeholder values
        placeholder_patterns = [
            "your-private-key",
            "your_api_key",
            "placeholder",
            "test-key",
            "example-key",
            "xxx",
            "0000",
        ]

        if not private_key or len(private_key) < 32:
            raise ValueError(
                "Invalid private key: must be at least 32 characters. "
                "Provide a real private key for production trading."
            )

        if any(pattern.lower() in private_key.lower() for pattern in placeholder_patterns):
            raise ValueError(
                f"Invalid private key: appears to be a placeholder value. "
                "Provide a real private key for production trading."
            )

        if not polymarket_api_key or len(polymarket_api_key) < 10:
            raise ValueError(
                "Invalid Polymarket API key: must be at least 10 characters. "
                "Provide a real API key for production trading."
            )

        if any(pattern.lower() in polymarket_api_key.lower() for pattern in placeholder_patterns):
            raise ValueError(
                f"Invalid Polymarket API key: appears to be a placeholder value. "
                "Provide a real API key for production trading."
            )

        if not rpc_url or not rpc_url.startswith(("http://", "https://")):
            raise ValueError(
                f"Invalid RPC URL: must be a valid HTTP/HTTPS URL. Got: {rpc_url}"
            )

        log.info("✓ Credentials validated for real trading")

    @property
    def config(self) -> RealTradingConfig:
        """Get current configuration."""
        return self._config

    @property
    def auto_redeem(self) -> "AutoRedeemEngine":
        """Auto-redeem engine for automatic position redemption. Access via ``client.real.auto_redeem``."""
        if self._auto_redeem is None:
            from .auto_redeem import AutoRedeemEngine, AutoRedeemConfig
            self._auto_redeem = AutoRedeemEngine(self, AutoRedeemConfig())
        return self._auto_redeem

    def set_auto_redeem_config(self, config: "AutoRedeemConfig") -> None:
        """Set a custom auto-redeem configuration."""
        from .auto_redeem import AutoRedeemEngine
        self._auto_redeem = AutoRedeemEngine(self, config)

    def set_position_sizer(self, sizer: PositionSizer) -> None:
        """
        Set a custom position sizer.

        Parameters
        ----------
        sizer : PositionSizer
            Position sizer instance (FixedPositionSizer, PercentagePositionSizer, etc.)
        """
        self._position_sizer = sizer
        log.info("Position sizer updated to %s", type(sizer).__name__)

    @property
    def balance(self) -> float:
        """Get current USDC balance."""
        return self._balance

    @property
    def emergency_mode(self) -> bool:
        """Check if emergency mode is active."""
        return self._emergency_mode

    # ── Error Handling Properties ──────────────────────────────────────────────────

    @property
    def clob_circuit_breaker(self) -> CircuitBreaker:
        """Get CLOB API circuit breaker."""
        return self._clob_circuit_breaker

    @property
    def wallet_circuit_breaker(self) -> CircuitBreaker:
        """Get wallet RPC circuit breaker."""
        return self._wallet_circuit_breaker

    @property
    def error_recovery(self) -> ErrorRecoveryManager:
        """Get error recovery manager."""
        return self._error_recovery

    @property
    def graceful_degradation(self) -> GracefulDegradation:
        """Get graceful degradation manager."""
        return self._graceful_degradation

    @property
    def transaction_rollback(self) -> TransactionRollbackManager:
        """Get transaction rollback manager."""
        return self._transaction_rollback

    @property
    def disaster_recovery(self) -> DisasterRecovery:
        """Get disaster recovery manager."""
        return self._disaster_recovery

    # ── Error Handling Methods ─────────────────────────────────────────────────────

    def get_error_handling_status(self) -> dict:
        """
        Get comprehensive error handling status.

        Returns
        -------
        dict
            Status of all error handling components
        """
        return {
            "clob_circuit_breaker": self._clob_circuit_breaker.metrics,
            "wallet_circuit_breaker": self._wallet_circuit_breaker.metrics,
            "graceful_degradation": self._graceful_degradation.get_degradation_summary(),
            "emergency_mode": self._emergency_mode,
        }

    def trigger_degradation(self, level: DegradationLevel, reason: str) -> None:
        """
        Manually trigger system degradation.

        Parameters
        ----------
        level : DegradationLevel
            Target degradation level
        reason : str
            Reason for degradation
        """
        self._graceful_degradation.degrade(level, reason)
        log.warning("Manual degradation triggered: %s - %s", level.value, reason)

    def trigger_recovery(self, level: DegradationLevel, reason: str) -> None:
        """
        Manually trigger system recovery.

        Parameters
        ----------
        level : DegradationLevel
            Target degradation level
        reason : str
            Reason for recovery
        """
        self._graceful_degradation.recover(level, reason)
        log.info("Manual recovery triggered: %s - %s", level.value, reason)

    def create_emergency_backup(self) -> str:
        """
        Create an emergency backup of current trading state.

        Returns
        -------
        str
            Path to backup file
        """
        try:
            backup_path = self._disaster_recovery.create_emergency_snapshot(
                positions={k: v.dump() for k, v in self._positions.items()},
                orders={k: v.dump() for k, v in self._orders.items()},
                config={
                    "max_order_size": self._config.max_order_size,
                    "max_daily_loss": self._config.max_daily_loss,
                    "max_position_size": self._config.max_position_size,
                },
            )
            log.info("Emergency backup created: %s", backup_path)
            return backup_path
        except Exception:
            log.exception("Failed to create emergency backup")
            raise BackupError("Failed to create emergency backup")

    def restore_from_backup(self, backup_path: str) -> dict:
        """
        Restore trading state from backup.

        Reconstructs in-memory ``RealPosition`` and ``RealOrder`` objects
        from the emergency snapshot data, and re-establishes the
        position/order cross-references (order_ids on positions).

        Parameters
        ----------
        backup_path : str
            Path to backup file (``.json`` or ``.json.gz``).

        Returns
        -------
        dict
            Summary: positions_restored, orders_restored, advanced_orders.

        Raises
        ------
        BackupError
            If the backup data is corrupt or cannot be loaded.
        """
        try:
            backup_data = self._disaster_recovery.restore_backup(backup_path)
            data = backup_data["data"]

            restored_positions = 0
            restored_orders = 0

            # Restore orders first (positions reference order IDs)
            if "orders" in data:
                for order_id, order_data in data["orders"].items():
                    if order_id in self._orders:
                        log.warning("Order %s already exists, overwriting", order_id)
                    self._orders[order_id] = RealOrder.from_dump(order_data)
                    restored_orders += 1
                    log.debug("Restored order: %s (%s %s)",
                              order_id, order_data.get("market"), order_data.get("side"))
                log.info("Restored %d orders from backup", restored_orders)

            # Restore positions
            if "positions" in data:
                for pos_key, pos_data in data["positions"].items():
                    if pos_key in self._positions:
                        log.warning("Position %s already exists, overwriting", pos_key)
                    self._positions[pos_key] = RealPosition.from_dump(pos_data)

                    position = self._positions[pos_key]
                    orphan_ids = [oid for oid in position.order_ids if oid not in self._orders]
                    if orphan_ids:
                        log.warning("Position %s references %d order(s) not in backup: %s",
                                    pos_key, len(orphan_ids), orphan_ids[:5])

                    restored_positions += 1
                    log.debug("Restored position: %s (%s %s, shares=%.2f)",
                              pos_key, pos_data.get("market"), pos_data.get("side"),
                              float(pos_data.get("shares", 0)))
                log.info("Restored %d positions from backup", restored_positions)

            # Rebuild daily tracking from config
            self._risk_manager._check_and_reset_daily()
            if "config" in data:
                cfg = data["config"]
                log.info("Backup config: max_order_size=%.2f, max_daily_loss=%.2f, "
                         "max_position_size=%.2f",
                         float(cfg.get("max_order_size", 0)),
                         float(cfg.get("max_daily_loss", 0)),
                         float(cfg.get("max_position_size", 0)))

            # Refresh balance from chain
            try:
                self.refresh_balance()
            except Exception as exc:
                log.warning("Could not refresh balance after restore: %s", exc)

            log.info("Restore complete: %d positions, %d orders from %s",
                     restored_positions, restored_orders, backup_path)

            return {
                "positions_restored": restored_positions,
                "orders_restored": restored_orders,
                "balance": self._balance,
            }

        except Exception:
            log.exception("Failed to restore from backup")
            raise BackupError("Failed to restore from backup")

    # ── Database Integration ─────────────────────────────────────────────────────

    def enable_database(self, db_path: str) -> None:
        """
        Enable database persistence for trades.

        Parameters
        ----------
        db_path : str
            Path to SQLite database file
        """
        try:
            from ..database.database import TradeDatabase
            self._db = TradeDatabase(db_path)
            self._db_enabled = True
            log.info("Real: database enabled at %s", db_path)
        except ImportError:
            log.error("Real: database module not available")
            self._db_enabled = False

    def disable_database(self) -> None:
        """Disable database persistence."""
        if self._db:
            self._db.close()
            self._db = None
        self._db_enabled = False
        log.info("Real: database disabled")

    # ── Balance Management ───────────────────────────────────────────────────────

    def refresh_balance(self) -> None:
        """Refresh balance from blockchain (no-op in simulate)."""
        if getattr(self, "_simulate", False):
            # In simulate mode keep existing balance; do not hit RPC
            return
        if self._use_multi_wallet and self._real_wallet_manager:
            self._real_wallet_manager.refresh_all_balances()
        else:
            try:
                self._balance = self._wallet.get_balance()
                # get_allowance requires CTF spender address
                from .alchemy_client import AlchemyClient
                spender = getattr(self._wallet, "_ctf_address", AlchemyClient.CTF_ADDRESS)
                try:
                    self._allowance = self._wallet.get_allowance(spender)
                except TypeError:
                    # fallback for mock wallets without param
                    self._allowance = self._wallet.get_allowance()
            except Exception:
                # Defer failure to caller; keep last known balance
                log.debug("refresh_balance failed, keeping cached", exc_info=True)
                return
            if self._config.log_balance_updates:
                log.debug("Balance: $%.2f, Allowance: $%.2f", self._balance, self._allowance)

    # ── Multi-Wallet Support ─────────────────────────────────────────────────────

    @property
    def is_multi_wallet(self) -> bool:
        """Check if multi-wallet mode is enabled."""
        return self._use_multi_wallet

    @property
    def wallets(self) -> Optional[RealTradingWalletManager]:
        """Get the real wallet manager if multi-wallet mode is enabled."""
        return self._real_wallet_manager if self._use_multi_wallet else None

    def enable_multi_wallet(
        self,
        wallet_manager: RealTradingWalletManager,
        wallet_id: Optional[str] = None,
    ) -> None:
        """
        Enable multi-wallet trading mode.

        Parameters
        ----------
        wallet_manager : RealTradingWalletManager
            Wallet manager with configured wallets
        wallet_id : str, optional
            Initially active wallet ID (default: first wallet)
        """
        if not wallet_manager.get_all_wallets():
            raise ValueError("Wallet manager must have at least one wallet")

        self._real_wallet_manager = wallet_manager
        self._use_multi_wallet = True

        if wallet_id:
            self._active_wallet_id = wallet_id
        else:
            first = wallet_manager.get_all_wallets()[0]
            self._active_wallet_id = first.wallet_id

        log.info(
            "RealTradingEngine: multi-wallet mode enabled with %d wallets (active: %s)",
            len(wallet_manager.get_all_wallets()),
            self._active_wallet_id,
        )

    def disable_multi_wallet(self) -> None:
        """Disable multi-wallet mode and return to single-wallet operation."""
        self._use_multi_wallet = False
        self._real_wallet_manager = None
        self._active_wallet_id = None
        log.info("RealTradingEngine: multi-wallet mode disabled")

    def set_active_wallet(self, wallet_id: str) -> None:
        """Set the active wallet by ID. Only valid in multi-wallet mode."""
        if not self._use_multi_wallet or not self._real_wallet_manager:
            raise RuntimeError("Multi-wallet mode is not enabled")
        self._real_wallet_manager.get_wallet(wallet_id)  # validate exists
        self._active_wallet_id = wallet_id
        log.info("RealTradingEngine: active wallet set to %s", wallet_id)

    def _get_active_wallet(self) -> RealWallet:
        """Get the currently active wallet in multi-wallet mode."""
        if not self._use_multi_wallet or not self._real_wallet_manager:
            raise RuntimeError("Multi-wallet mode is not enabled")
        return self._real_wallet_manager.get_wallet(self._active_wallet_id)

    def _resolve_orders(self) -> dict:
        """Get orders dict from active wallet or single-wallet mode."""
        if self._use_multi_wallet:
            return self._get_active_wallet().orders
        return self._orders

    def _resolve_positions(self) -> dict:
        """Get positions dict from active wallet or single-wallet mode."""
        if self._use_multi_wallet:
            return self._get_active_wallet().positions
        return self._positions

    def _resolve_balance(self) -> float:
        """Get balance from active wallet or single-wallet mode."""
        if self._use_multi_wallet:
            return self._get_active_wallet().balance
        return self._balance

    def _set_balance(self, value: float) -> None:
        """Set balance on active wallet or single-wallet mode."""
        if self._use_multi_wallet:
            self._get_active_wallet().balance = value
        else:
            self._balance = value

    def _resolve_allowance(self) -> float:
        """Get allowance from active wallet or single-wallet mode."""
        if self._use_multi_wallet:
            return self._get_active_wallet().allowance
        return self._allowance

    def _set_allowance(self, value: float) -> None:
        """Set allowance on active wallet or single-wallet mode."""
        if self._use_multi_wallet:
            self._get_active_wallet().allowance = value
        else:
            self._allowance = value

    def _resolve_wallet(self):
        """Get WalletManager from active wallet or single-wallet mode."""
        if self._use_multi_wallet:
            return self._get_active_wallet().wallet_manager
        return self._wallet

    def _resolve_clob(self):
        """Get ClobClient from active wallet or single-wallet mode."""
        if self._use_multi_wallet:
            return self._get_active_wallet().clob_client
        return self._clob_client

    def _resolve_config(self):
        """Get config from active wallet or single-wallet mode."""
        if self._use_multi_wallet:
            return self._get_active_wallet().config or self._config
        return self._config

    def _resolve_risk_manager(self):
        """Get risk manager from active wallet or single-wallet mode."""
        if self._use_multi_wallet:
            rm = self._get_active_wallet().risk_manager
            if rm is not None:
                return rm
        return self._risk_manager

    def _resolve_config_and_risk(self):
        """Convenience: return (config, risk_manager) for current wallet."""
        if self._use_multi_wallet:
            wallet = self._get_active_wallet()
            cfg = wallet.config or self._config
            rm = wallet.risk_manager if wallet.risk_manager is not None else self._risk_manager
            return cfg, rm
        return self._config, self._risk_manager

    def _find_order_across_wallets(self, order_id: str):
        """Find an order across all wallets. Returns (order, wallet) or (None, None)."""
        if not self._use_multi_wallet or not self._real_wallet_manager:
            if order_id in self._orders:
                return self._orders[order_id], None
            return None, None
        return self._real_wallet_manager.find_order_across_wallets(order_id)

    def _find_position_across_wallets(self, market_id: str, side: str):
        """Find a position across all wallets. Returns (position, wallet) or (None, None)."""
        if not self._use_multi_wallet or not self._real_wallet_manager:
            key = f"{market_id}:{side}"
            if key in self._positions:
                return self._positions[key], None
            return None, None
        return self._real_wallet_manager.find_position_across_wallets(market_id, side)

    def _get_all_orders_across_wallets(self) -> dict:
        """Get all orders across all wallets."""
        if not self._use_multi_wallet or not self._real_wallet_manager:
            return self._orders
        return self._real_wallet_manager.get_all_orders()

    def _get_all_positions_across_wallets(self) -> dict:
        """Get all positions across all wallets."""
        if not self._use_multi_wallet or not self._real_wallet_manager:
            return self._positions
        return self._real_wallet_manager.get_all_positions()

    # ── Pre-Trade Checks ─────────────────────────────────────────────────────────

    def pre_trade_checks(self, market, side: str, amount: float) -> dict:
        """
        Run comprehensive pre-trade checks before order execution.

        This method validates various conditions before allowing a trade to proceed,
        helping prevent errors and risky trades in real trading.

        Parameters
        ----------
        market : Market object
            Market to trade
        side : str
            "UP" or "DOWN"
        amount : float
            USDC amount to spend

        Returns
        -------
        dict
            Dictionary with check results and warnings:
            - balance_ok: bool - Whether sufficient balance exists
            - allowance_ok: bool - Whether sufficient CLOB allowance exists
            - market_open: bool - Whether market is still open
            - price_reasonable: bool - Whether price is within reasonable range
            - warnings: list[str] - List of warning messages
            - can_proceed: bool - Whether trade can proceed (all critical checks pass)

        Example
        -------
        >>> checks = client.real.pre_trade_checks(market, side="UP", amount=10.0)
        >>> if not checks["can_proceed"]:
        ...     for warning in checks["warnings"]:
        ...         print(f"Warning: {warning}")
        ... else:
        ...     order = client.real.buy(market, side="UP", amount=10.0)
        """
        balance = self._resolve_balance()
        allowance = self._resolve_allowance()

        checks = {
            "balance_ok": True,
            "allowance_ok": True,
            "market_open": True,
            "price_reasonable": True,
            "warnings": [],
            "can_proceed": True,
        }

        # Check balance
        if amount > balance:
            checks["balance_ok"] = False
            checks["can_proceed"] = False
            checks["warnings"].append(
                f"Insufficient balance: need ${amount:.2f}, have ${balance:.2f}"
            )

        # Check CLOB allowance (real trading specific)
        if allowance < amount:
            checks["allowance_ok"] = False
            checks["warnings"].append(
                f"Insufficient CLOB allowance: need ${amount:.2f}, have ${allowance:.2f}. "
                f"Call approve_spender() to increase allowance."
            )
            # Allowance warning doesn't block trade (can be auto-approved), but warn user

        # Check if market is open for trading
        if hasattr(market, 'start_time') and isinstance(getattr(market, 'start_time', None), str) and market.start_time:
            try:
                start_time = datetime.fromisoformat(market.start_time.replace('Z', '+00:00'))
                if start_time > datetime.now(timezone.utc):
                    checks["market_open"] = False
                    checks["can_proceed"] = False
                    checks["warnings"].append("Market has not yet opened")
            except (ValueError, AttributeError, TypeError) as e:
                log.debug("Real: could not parse market start_time: %s", e)

        # Check if market is still open
        if hasattr(market, 'end_time') and isinstance(getattr(market, 'end_time', None), str) and market.end_time:
            try:
                end_time = datetime.fromisoformat(market.end_time.replace('Z', '+00:00'))
                if end_time < datetime.now(timezone.utc):
                    checks["market_open"] = False
                    checks["can_proceed"] = False
                    checks["warnings"].append("Market has closed")
            except (ValueError, AttributeError, TypeError) as e:
                log.debug("Real: could not parse market end_time: %s", e)

        # Check if price is reasonable
        price = market.up_price if side == "UP" else market.down_price
        if price < 0.01 or price > 0.99:
            checks["price_reasonable"] = False
            checks["warnings"].append(f"Unusual price: ${price:.4f}")

        # Additional warning if price is very close to boundaries
        if price < 0.02 or price > 0.98:
            checks["warnings"].append(
                f"Price near boundary (${price:.4f}) - low liquidity risk"
            )

        # Log warnings if any
        if checks["warnings"]:
            log.debug("Real: pre-trade checks warnings: %s", checks["warnings"])

        return checks

    # ── Order Execution ─────────────────────────────────────────────────────────

    def buy(
        self,
        market,
        side: str,
        amount: Optional[float] = None,
        confidence: float = 0.5,
        price: Optional[float] = None,
        stop_loss: Optional[float] = None,
        take_profit: Optional[float] = None,
        confirm: bool = True,
    ) -> RealOrder:
        """
        Execute a real buy order on the CLOB.

        Parameters
        ----------
        market : Market
            Market to trade
        side : str
            "UP" or "DOWN"
        amount : float, optional
            USDC amount to spend. If None, uses position sizing strategy.
        confidence : float
            Confidence level (0-1) for position sizing
        price : float, optional
            Limit price. If None, executes at market.
        stop_loss : float, optional
            Stop loss price trigger
        take_profit : float, optional
            Take profit price trigger
        confirm : bool
            Require manual confirmation before executing

        Returns
        -------
        RealOrder
            The executed order
        """
        if self._emergency_mode:
            raise OrderCancelled("Trading halted - emergency mode active")

        side = _validate_side(side)

        # Resolve wallet-aware state
        config, risk_manager = self._resolve_config_and_risk()
        balance = self._resolve_balance()
        positions = self._resolve_positions()
        orders = self._resolve_orders()

        # Sync balance from chain to avoid divergence
        self.refresh_balance()
        balance = self._resolve_balance()

        # Track if user explicitly provided a price (for limit vs market order)
        user_provided_price = price is not None

        # 1. Calculate position size if not provided
        if amount is None:
            amount = self._position_sizer.calculate_size(
                balance, market, side, confidence, price
            )

        # 2. Run pre-trade checks
        checks = self.pre_trade_checks(market, side, amount)
        if not checks["can_proceed"]:
            raise ValueError(
                f"Pre-trade checks failed: {'; '.join(checks['warnings'])}"
            )

        # 3. Validate against risk limits
        risk_manager.validate_order(amount, balance, market, positions)

        # 4. Check balance
        if amount > balance:
            raise InsufficientBalance(
                f"Order amount ${amount:.2f} exceeds balance ${balance:.2f}"
            )

        # 5. Get price with stream awareness (prefers live stream price if available)
        if price is None:
            price, price_source = self._get_price_for_side(market, side)
            # Market orders cross the spread. Buffer the price by the configured
            # slippage tolerance so the marketable limit actually fills, and record
            # the buffered (worst-case) price so cost is never underestimated.
            price = self._apply_buy_slippage(price, config)

        # 6. Calculate shares and fee
        is_maker = user_provided_price  # limit orders provide liquidity
        shares, fee = self._calculate_shares_and_fee(amount, price, is_maker=is_maker)

        # 7. Require confirmation if enabled
        if confirm and config.require_confirmation:
            self._require_confirmation(market, side, amount, price, shares, fee)

        # 8. Place order on CLOB
        token_id = market.up_token if side == "UP" else market.down_token
        order_response = self._place_clob_order(
            token_id,
            "buy",  # Always buying tokens (UP or DOWN)
            price,
            shares,
            "market" if not user_provided_price else "limit"
        )

        # 9. Create order object
        order = RealOrder(
            id=order_response["order_id"],
            market_id=market.id,
            slug=market.slug,
            side=side,
            price=price,
            amount=amount,
            shares=shares,
            fee=fee,
            status="pending",
            is_limit=user_provided_price,
            created_at=datetime.now(timezone.utc),
            stop_loss=stop_loss,
            take_profit=take_profit,
            sizing_strategy=config.position_sizing,
            confidence=confidence,
        )

        # 10. Update balance (fee comes out of amount, not on top)
        self._set_balance(self._resolve_balance() - amount)

        # 11. Store order
        orders[order.id] = order

        # 12. Update position
        self._update_position(market, side, order)

        # 13. Save to database
        if self._db_enabled:
            active_wallet = self._get_active_wallet() if self._use_multi_wallet else None
            self._save_order_to_db(order, wallet=active_wallet)

        if config.log_all_orders:
            log.debug(
                "Order placed: %s %s $%.2f @ $%.4f",
                market.slug, side, amount, price
            )

        return order

    def limit(
        self,
        market,
        side: str,
        price: float,
        amount: Optional[float] = None,
        confidence: float = 0.5,
        stop_loss: Optional[float] = None,
        take_profit: Optional[float] = None,
        confirm: bool = True,
    ) -> RealOrder:
        """
        Execute a real limit order on the CLOB.

        Parameters
        ----------
        market : Market
            Market to trade
        side : str
            "UP" or "DOWN"
        price : float
            Limit price
        amount : float, optional
            USDC amount to spend
        confidence : float
            Confidence level for position sizing
        stop_loss : float, optional
            Stop loss price trigger
        take_profit : float, optional
            Take profit price trigger
        confirm : bool
            Require manual confirmation

        Returns
        -------
        RealOrder
            The placed limit order
        """
        return self.buy(
            market=market,
            side=side,
            amount=amount,
            confidence=confidence,
            price=price,
            stop_loss=stop_loss,
            take_profit=take_profit,
            confirm=confirm,
        )

    def sell(
        self,
        market,
        side: str,
        amount: Optional[float] = None,
        confidence: float = 0.5,
        price: Optional[float] = None,
        confirm: bool = True,
    ) -> RealOrder:
        """
        Execute a real sell order on the CLOB.

        To sell an existing position on Polymarket, you buy the opposite side.
        This method handles the side inversion automatically.

        Parameters
        ----------
        market : Market
            Market to trade
        side : str
            Side of the position being sold ("UP" or "DOWN")
        amount : float, optional
            USDC amount to sell. If None, uses position sizing strategy.
        confidence : float
            Confidence level for position sizing
        price : float, optional
            Limit price. If None, executes at market.
        confirm : bool
            Require manual confirmation before executing

        Returns
        -------
        RealOrder
            The executed sell order
        """
        opposite = "DOWN" if _validate_side(side) == "UP" else "UP"
        return self.buy(
            market=market,
            side=opposite,
            amount=amount,
            confidence=confidence,
            price=price,
            confirm=confirm,
        )

    # ── Order Management ─────────────────────────────────────────────────────────

    def cancel(self, order_id: str) -> None:
        """
        Cancel an open order.

        Parameters
        ----------
        order_id : str
            Order ID to cancel
        """
        order, wallet = self._find_order_across_wallets(order_id)
        if order is None:
            raise OrderNotFound(f"Order {order_id} not found")

        if order.status not in ("open", "pending"):
            log.warning("Order %s is not open (status: %s)", order_id, order.status)
            return

        # Cancel on CLOB
        self._cancel_clob_order(order_id, wallet=wallet)

        order.status = "cancelled"
        log.info("Order %s cancelled", order_id)

    def get_order(self, order_id: str) -> RealOrder:
        """
        Get order by ID.

        Parameters
        ----------
        order_id : str
            Order ID

        Returns
        -------
        RealOrder
            Order object
        """
        order, _ = self._find_order_across_wallets(order_id)
        if order is None:
            raise OrderNotFound(f"Order {order_id} not found")
        return order

    def open_orders(self) -> list[RealOrder]:
        """Get all open orders."""
        orders = self._get_all_orders_across_wallets()
        return [o for o in orders.values() if o.status in ("open", "pending")]

    def _create_position_sizer(self) -> PositionSizer:
        """Create position sizer based on configuration."""
        strategy = self._config.position_sizing

        if strategy == "fixed":
            return FixedPositionSizer(amount=self._config.fixed_amount)
        elif strategy == "percentage":
            return PercentagePositionSizer(percentage=self._config.percentage_of_balance)
        elif strategy == "kelly":
            return KellyPositionSizer(
                kelly_fraction=self._config.kelly_fraction,
                min_confidence=0.55,
            )
        else:
            # Default to fixed
            return FixedPositionSizer(amount=self._config.fixed_amount)

    def _calculate_position_size(
        self,
        market,
        side: str,
        confidence: float,
        price: float,
    ) -> float:
        """Calculate position size using the configured position sizer."""
        return self._position_sizer.calculate_size(
            balance=self._balance,
            market=market,
            side=side,
            confidence=confidence,
            price=price,
        )

    def _validate_order(self, amount: float, market) -> None:
        """Validate order against risk limits using RiskManager."""
        self._risk_manager.validate_order(
            amount=amount,
            balance=self._balance,
            market=market,
            positions=self._positions,
        )

    def _apply_buy_slippage(self, price: float, config) -> float:
        """
        Buffer a market-buy price by the configured slippage tolerance.

        A market buy has to cross the spread; submitting at the exact quoted price
        leaves the signed order non-marketable, so it may never fill. We raise the
        price by ``slippage_tolerance`` (a buy is always adverse in the up direction)
        and cap it just below 1.0, since Polymarket prices live in (0, 1). The
        buffered price is used for both submission and accounting, so recorded cost
        is the worst case and never underestimated.

        Parameters
        ----------
        price : float
            Quoted price per share.
        config : RealTradingConfig
            Resolved config providing ``slippage_tolerance``.

        Returns
        -------
        float
            Slippage-adjusted price, capped at ``MAX_ORDER_PRICE``.
        """
        tolerance = getattr(config, "slippage_tolerance", 0.0)
        if tolerance <= 0 or price <= 0:
            return price
        adjusted = min(price * (1 + tolerance), MAX_ORDER_PRICE)
        if adjusted != price:
            log.debug(
                "Real: applied %.2f%% buy slippage: %.4f -> %.4f",
                tolerance * 100, price, adjusted,
            )
        return adjusted

    def _calculate_shares_and_fee(self, amount: float, price: float, is_maker: bool = False) -> tuple[float, float]:
        """
        Calculate shares and fee for an order using the configured fee mode.

        The fee is deducted from the trade amount (like Polymarket does on-chain),
        so the user receives fewer shares.

        Parameters
        ----------
        amount : float
            Total USDC being spent
        price : float
            Price per share
        is_maker : bool
            Whether this is a maker order (limit order providing liquidity)

        Returns
        -------
        tuple[float, float]
            (shares, fee) where shares = (amount - fee) / price
        """
        if price <= 0:
            return 0.0, 0.0

        # First pass: estimate fee from initial share estimate
        shares_est = amount / price
        fee = self._calculate_fee(amount, price, shares_est, is_maker)

        # Fee comes out of the trade amount
        net_trade = amount - fee
        if net_trade <= 0:
            return 0.0, fee

        shares = net_trade / price

        # Second pass: recalculate fee with actual shares (significant for polymarket formula)
        if self._config.fee_mode == "polymarket":
            fee = self._calculate_fee(amount, price, shares, is_maker)
            net_trade = amount - fee
            if net_trade <= 0:
                return 0.0, fee
            shares = net_trade / price

        return shares, fee

    def _calculate_fee(self, amount: float, price: float, shares: float, is_maker: bool = False) -> float:
        """
        Calculate the fee for an order based on the configured fee mode.

        Parameters
        ----------
        amount : float
            Total USDC being spent
        price : float
            Price per share
        shares : float
            Number of shares being traded
        is_maker : bool
            Whether this is a maker order (limit order providing liquidity)

        Returns
        -------
        float
            The fee amount in USDC
        """
        if self._config.fee_mode == "zero":
            return 0.0
        elif self._config.fee_mode == "custom":
            fee_rate = self._config.maker_fee_rate if is_maker else self._config.custom_fee_rate
            return round(amount * fee_rate, FEE_ROUNDING)
        elif self._config.fee_mode == "polymarket":
            return self._polymarket_fee(amount, price, shares, is_maker)
        return 0.0

    def _polymarket_fee(self, amount: float, price: float, shares: float, is_maker: bool = False) -> float:
        if self._config.market_category.lower() == "geopolitical":
            return 0.0
        fee_rate = fee_rate_for_category(self._config.market_category)
        return calculate_polymarket_fee(shares, price, fee_rate)

    def _require_confirmation(
        self,
        market,
        side: str,
        amount: float,
        price: float,
        shares: float,
        fee: float,
    ) -> None:
        """Require user confirmation before executing order."""
        print("\n" + "=" * 60)
        print("ORDER CONFIRMATION REQUIRED")
        print("=" * 60)
        print(f"Market:    {market.question}")
        print(f"Side:      {side}")
        print(f"Amount:    ${amount:.2f}")
        print(f"Price:     ${price:.4f}")
        print(f"Shares:    {shares:.4f}")
        print(f"Fee:       ${fee:.4f}")
        print(f"Net Trade: ${amount - fee:.2f}")
        print(f"Total:     ${amount:.2f}")
        balance = self._resolve_balance()
        print(f"Balance:   ${balance:.2f}")
        print("=" * 60)

        response = input("\nConfirm this order? (yes/no): ").strip().lower()

        if response not in ("yes", "y"):
            raise OrderCancelled("Order cancelled by user")

        print("Order confirmed.\n")

    def _place_clob_order(
        self,
        token_id: str,
        side: str,
        price: float,
        size: float,
        order_type: str,
        wallet=None,
    ) -> dict:
        """Place order on CLOB."""
        clob = self._resolve_clob() if wallet is None else wallet.clob_client
        return clob.place_order(
            token_id=token_id,
            side=side,
            price=price,
            size=size,
            order_type=order_type,
        )

    def _cancel_clob_order(self, order_id: str, wallet=None) -> None:
        """Cancel order on CLOB."""
        clob = self._resolve_clob() if wallet is None else wallet.clob_client
        clob.cancel_order(order_id)

    def _update_position(self, market, side: str, order: RealOrder, wallet=None) -> None:
        """Update position after order fill."""
        key = f"{market.id}:{side}"
        if wallet is not None and self._use_multi_wallet:
            positions = wallet.positions
        else:
            positions = self._resolve_positions()

        with self._position_lock:
            if key in positions:
                position = positions[key]
                position.order_ids.append(order.id)

                total_shares = position.shares + order.shares
                position.avg_price = (
                    (position.avg_price * position.shares + order.price * order.shares)
                    / total_shares
                )
                position.shares = total_shares
                position.cost_basis = position.shares * position.avg_price
                position.current_value = position.shares * order.price
            else:
                position = RealPosition(
                    market_id=market.id,
                    slug=market.slug,
                    question=market.question,
                    side=side,
                    shares=order.shares,
                    avg_price=order.price,
                    current_price=order.price,
                    cost_basis=order.shares * order.price,
                    current_value=order.shares * order.price,
                    order_ids=[order.id],
                )
                positions[key] = position

    def _get_market_exposure(self, market_id: str) -> float:
        """Get total exposure for a market."""
        exposure = 0.0
        positions = self._get_all_positions_across_wallets()
        for position in positions.values():
            if position.market_id == market_id and not position.resolved:
                exposure += position.cost_basis
        return exposure

    def _save_order_to_db(self, order: RealOrder, wallet=None) -> None:
        """Save real order to database."""
        if not self._db_enabled or self._db is None:
            return

        try:
            wallet_obj = wallet if (wallet is not None and self._use_multi_wallet) else self._resolve_wallet()
            addr = wallet_obj.get_address() if hasattr(wallet_obj, 'get_address') else str(wallet_obj)

            self._db.save_trade(
                market_slug=order.slug,
                market_id=order.market_id,
                side=order.side,
                entry_price=order.price,
                exit_price=None,
                amount=order.amount,
                shares=order.shares,
                fee=order.fee,
                outcome=None,
                pnl=0.0,
                timestamp=order.created_at,
                sizing_strategy=order.sizing_strategy,
                confidence=order.confidence,
                kelly_fraction=order.kelly_fraction,
                stop_loss=order.stop_loss,
                take_profit=order.take_profit,
                tx_hash=order.tx_hash,
                is_real_trade=True,
                wallet_address=addr,
                order_id=order.id,
                status=order.status,
            )
            log.debug("Real: order saved to database for %s", order.slug)
        except Exception as exc:
            log.exception("Real: failed to save order to database")

    def _update_order_in_db(self, order: RealOrder) -> None:
        """Update order status in database after fill status changes."""
        if not self._db_enabled or self._db is None:
            return

        try:
            # Update the trade record with fill information
            self._db.update_trade_status(
                order_id=order.id,
                status=order.status,
                filled_shares=order.filled_shares,
                filled_amount=order.filled_amount,
                avg_fill_price=order.avg_fill_price,
                filled_at=order.filled_at,
            )
            log.debug("Real: order status updated in database for %s: %s", order.slug, order.status)
        except Exception as exc:
            log.exception("Real: failed to update order in database")

    # ── Advanced Order Types ─────────────────────────────────────────────────────────

    def _get_price_for_side(self, market, side: str) -> tuple[float, str]:
        """Get best available price — delegates to staleness helper (single threshold)."""
        from .staleness import get_price_for_side as _helper
        return _helper(market, side, self._attached_streams, log_prefix="Real")

    # ── Real-Time Price Monitoring ───────────────────────────────────────────────

    def attach_stream(self, stream, market) -> None:
        """
        Wire *stream* so positions auto-update and stop loss/take profit triggers execute.

        This method integrates price streams with the RealTradingEngine for automatic
        price updates, stop loss/take profit execution, and trailing stop management.

        Also enables price-aware trading: buy() will automatically use live
        streamed prices when a stream is attached and running.

        Example
        -------
        >>> stream = client.stream(market)
        >>> client.real.attach_stream(stream, market)
        >>> stream.start(background=True)
        """
        # Validate market
        if not hasattr(market, 'id') or not hasattr(market, 'slug'):
            raise ValueError("Invalid market object")

        # Store stream reference for price-aware trading
        self._attached_streams[market.id] = stream

        @stream.on("price")
        def _on_price(up: float, down: float) -> None:
            self._on_price_update(market.id, up, down)

        @stream.on("close")
        def _on_close() -> None:
            log.info(
                "Real: stream closed for %s — market resolved",
                market.slug,
            )
            # Remove stream reference when closed
            self._attached_streams.pop(market.id, None)

        log.info("Real: stream attached for %s", market.slug)

    def show_positions(self, show_all: bool = False, verbose: bool = True) -> None:
        """
        Display positions with entry/exit information and ROI.

        Parameters
        ----------
        show_all : bool
            If True, show all positions including resolved ones. If False, only show live positions.
        verbose : bool
            If True, show detailed information including entry/exit times.

        Example
        -------
        >>> client.real.show_positions()  # Show live positions
        >>> client.real.show_positions(show_all=True)  # Show all positions
        """
        from ..report.terminal import render_positions

        positions = self.all_positions() if show_all else self.positions()
        orders = self._get_all_orders_across_wallets()
        render_positions(positions, orders, show_all=show_all, verbose=verbose)

    def position_history(self) -> dict:
        """
        Get position history summary statistics.

        Returns
        -------
        dict
            Dictionary with position history statistics including:
            - total_positions: Total number of positions opened
            - total_closed: Total number of positions closed
            - total_open: Current number of open positions
            - win_rate: Win rate percentage
            - avg_holding_time: Average holding time in seconds
            - best_position: Best performing position
            - worst_position: Worst performing position
        """
        all_pos = self.all_positions()
        open_pos = [p for p in all_pos if not p.resolved]
        closed_pos = [p for p in all_pos if p.resolved]

        wins = [p for p in closed_pos if p.outcome == "WON"]
        losses = [p for p in closed_pos if p.outcome == "LOST"]

        # Calculate holding times for closed positions
        orders = self._get_all_orders_across_wallets()
        holding_times = []
        for pos in closed_pos:
            if pos.order_ids:
                fill_times = [
                    orders[oid].filled_at 
                    for oid in pos.order_ids 
                    if oid in orders and orders[oid].filled_at
                ]
                if fill_times:
                    holding_time = (max(fill_times) - min(fill_times)).total_seconds()
                    holding_times.append(holding_time)

        avg_holding = sum(holding_times) / len(holding_times) if holding_times else 0.0

        # Find best and worst positions
        best_pos = max(closed_pos, key=lambda p: p.pnl) if closed_pos else None
        worst_pos = min(closed_pos, key=lambda p: p.pnl) if closed_pos else None

        return {
            "total_positions": len(all_pos),
            "total_closed": len(closed_pos),
            "total_open": len(open_pos),
            "wins": len(wins),
            "losses": len(losses),
            "win_rate": (len(wins) / len(closed_pos) * 100) if closed_pos else 0.0,
            "avg_holding_time": avg_holding,
            "best_position": {
                "market": best_pos.slug if best_pos else None,
                "pnl": best_pos.pnl if best_pos else 0.0,
                "pnl_pct": best_pos.pnl_pct if best_pos else 0.0,
            } if best_pos else None,
            "worst_position": {
                "market": worst_pos.slug if worst_pos else None,
                "pnl": worst_pos.pnl if worst_pos else 0.0,
                "pnl_pct": worst_pos.pnl_pct if worst_pos else 0.0,
            } if worst_pos else None,
        }

    def get_position(self, market_id: str, side: str) -> RealPosition:
        """
        Get position for a market and side.

        Parameters
        ----------
        market_id : str
            Market ID
        side : str
            "UP" or "DOWN"

        Returns
        -------
        RealPosition
            Position object
        """
        position, _ = self._find_position_across_wallets(market_id, side)
        if position is None:
            raise PositionNotFound(f"No position for {market_id} {side}")
        return position

    def redeem_position(
        self,
        market_id: str,
        side: str,
    ) -> dict:
        """
        Redeem a resolved position on-chain via the CTF contract.

        Converts winning polymarket position tokens back into USDC
        by calling the Conditional Tokens Framework ``redeem`` method.

        Parameters
        ----------
        market_id : str
            Market/condition ID to redeem.
        side : str
            "UP" or "DOWN" — which side of the market to redeem.

        Returns
        -------
        dict
            ``{"success": bool, "tx_hash": str | None, "error": str | None}``

        Raises
        ------
        PositionNotFound
            If no position exists for the given market/side.
        """
        side = _validate_side(side)
        position_key = f"{market_id}:{side}"

        if position_key not in self._positions:
            raise PositionNotFound(f"No position found for {market_id} {side}")

        position = self._positions[position_key]
        log.info("Redeeming position %s %s (shares=%.4f, resolved=%s)",
                 position.slug, side, position.shares, position.resolved)

        if not position.resolved:
            log.warning("Position %s %s is not yet resolved, checking chain...",
                        position.slug, side)
            try:
                self._alchemy_client.get_token_balances(self._wallet.address)
            except Exception:
                log.warning("Failed to check token balances for redemption", exc_info=True)

        if self._wallet._web3 is None:
            self._wallet._init_web3()

        tx_hash = None
        try:
            from web3 import Web3

            ctf = self._wallet._ctf_contract
            address = Web3.to_checksum_address(self._wallet.address)

            condition_id = Web3.to_bytes(hexstr=market_id) if market_id.startswith("0x") else market_id.encode()
            if len(condition_id) != 32:
                condition_id = Web3.keccak(text=market_id)

            parent_collection_id = "0x" + "0" * 64
            index_set = 0 if side == "DOWN" else 1
            index_sets = [index_set]

            gas_estimate = ctf.functions.redeem(
                condition_id,
                parent_collection_id,
                index_sets,
            ).estimate_gas({'from': address})

            tx_params = self._wallet._build_transaction_params(
                gas_estimate=int(gas_estimate * 1.2),
                to_address=self._wallet._ctf_address,
            )

            tx = ctf.functions.redeem(
                condition_id,
                parent_collection_id,
                index_sets,
            ).build_transaction(tx_params)

            from eth_account import Account
            signed_tx = Account.sign_transaction(tx, self._wallet._private_key)
            tx_hash_raw = self._wallet._web3.eth.send_raw_transaction(signed_tx.raw_transaction)
            tx_hash = tx_hash_raw.hex()

            self._wallet._track_pending_transaction(tx_hash, tx_params['nonce'])
            receipt = self._wallet.wait_for_transaction(tx_hash, timeout=120)

            if receipt['status'] == 1:
                position.resolved = True
                position.outcome = "WON"
                log.info("Position %s %s redeemed on-chain: tx=%s",
                         position.slug, side, tx_hash)

                del self._positions[position_key]

                self.refresh_balance()

                return {"success": True, "tx_hash": tx_hash, "error": None}
            else:
                log.error("Redeem transaction %s failed on-chain", tx_hash)
                return {"success": False, "tx_hash": tx_hash, "error": "On-chain revert"}

        except Exception as e:
            log.exception("Failed to redeem position %s %s", position.slug, side)
            return {"success": False, "tx_hash": tx_hash, "error": str(e)}

    def transfer_position(
        self,
        market,
        side: str,
        target_wallet_address: str,
        transfer_pct: float = 1.0,
    ) -> dict:
        """
        Transfer a position (or portion of it) to another wallet.

        This allows moving positions between wallets for risk management
        or portfolio rebalancing.

        Parameters
        ----------
        market : Market
            Market object
        side : str
            "UP" or "DOWN"
        target_wallet_address : str
            Address of the wallet to transfer to
        transfer_pct : float, optional
            Percentage of position to transfer (0.0 to 1.0, default: 1.0)

        Returns
        -------
        dict
            Transaction details including tx_hash and status

        Raises
        ------
        PositionNotFound
            If no existing position exists for this market/side
        ValueError
            If transfer_pct is not between 0 and 1

        Example
        -------
        >>> # Transfer entire position to another wallet
        >>> tx = client.real.transfer_position(market, side="UP",
        ...                                     target_wallet_address="0x123...")
        """
        side = _validate_side(side)
        position_key = f"{market.id}:{side}"

        if position_key not in self._positions:
            raise PositionNotFound(f"No position found for {market.slug} {side}")

        if not 0 < transfer_pct <= 1:
            raise ValueError("transfer_pct must be between 0 and 1")

        position = self._positions[position_key]
        shares_to_transfer = position.shares * transfer_pct

        log.info("Transferring %.1f%% (%.2f shares) of position %s %s to wallet %s",
                 transfer_pct * 100, shares_to_transfer, market.slug, side, target_wallet_address)

        if self._wallet._web3 is None:
            self._wallet._init_web3()

        from web3 import Web3

        token_id = market.up_token if side == "UP" else market.down_token
        token_id_int = int(token_id, 16) if token_id.startswith("0x") else int(token_id)
        from_address = Web3.to_checksum_address(self._wallet.address)
        to_address = Web3.to_checksum_address(target_wallet_address)
        amount_raw = int(shares_to_transfer * 1_000_000)

        try:
            gas_estimate = self._wallet._ctf_contract.functions.safeTransferFrom(
                from_address,
                to_address,
                token_id_int,
                amount_raw,
                b"",
            ).estimate_gas({'from': from_address})

            tx_params = self._wallet._build_transaction_params(
                gas_estimate=int(gas_estimate * 1.2),
                to_address=self._wallet._ctf_address,
            )

            tx = self._wallet._ctf_contract.functions.safeTransferFrom(
                from_address,
                to_address,
                token_id_int,
                amount_raw,
                b"",
            ).build_transaction(tx_params)

            from eth_account import Account
            signed_tx = Account.sign_transaction(tx, self._wallet._private_key)
            tx_hash_raw = self._wallet._web3.eth.send_raw_transaction(signed_tx.raw_transaction)
            tx_hash = tx_hash_raw.hex()

            self._wallet._track_pending_transaction(tx_hash, tx_params['nonce'])
            receipt = self._wallet.wait_for_transaction(tx_hash, timeout=120)

            if receipt['status'] == 1:
                with self._position_lock:
                    position.shares -= shares_to_transfer
                    position.cost_basis = position.shares * position.avg_price
                    position.current_value = position.shares * position.current_price

                    del self._positions[position_key]

                log.info("Transfer successful: %s %s -> %s (tx=%s)",
                         market.slug, side, target_wallet_address, tx_hash)

                tx_details = {
                    "from_wallet": from_address,
                    "to_wallet": to_address,
                    "market_id": market.id,
                    "side": side,
                    "shares": shares_to_transfer,
                    "tx_hash": tx_hash,
                    "status": "confirmed",
                    "timestamp": datetime.now(timezone.utc).isoformat(),
                }
            else:
                raise RuntimeError("Transfer reverted on-chain")

        except Exception as e:
            log.exception("Failed to transfer position %s %s", market.slug, side)
            tx_details = {
                "from_wallet": from_address,
                "to_wallet": to_address,
                "market_id": market.id,
                "side": side,
                "shares": shares_to_transfer,
                "tx_hash": None,
                "status": "failed",
                "error": str(e),
                "timestamp": datetime.now(timezone.utc).isoformat(),
            }

        return tx_details

    def merge_positions(
        self,
        market,
        side: str,
    ) -> RealPosition:
        """
        Merge multiple positions for the same market and side into a single position.

        This combines fragmented positions into one for easier management.

        Parameters
        ----------
        market : Market
            Market object
        side : str
            "UP" or "DOWN"

        Returns
        -------
        RealPosition
            The merged position

        Raises
        ------
        PositionNotFound
            If no positions exist for this market/side

        Example
        -------
        >>> # Merge all UP positions for a market
        >>> merged = client.real.merge_positions(market, side="UP")
        """
        side = _validate_side(side)
        position_key = f"{market.id}:{side}"

        if position_key not in self._positions:
            raise PositionNotFound(f"No position found for {market.slug} {side}")

        # In the current implementation, positions are already merged by market_id:side
        # This method is provided for future extensibility if the implementation
        # changes to support multiple positions per market/side

        position = self._positions[position_key]

        log.info("Position %s %s already merged (single position per market/side)",
                 market.slug, side)

        return position

    def get_position_exposure(self, market_id: str) -> float:
        """
        Get total exposure for a specific market across all sides.

        Parameters
        ----------
        market_id : str
            Market ID

        Returns
        -------
        float
            Total exposure in USDC

        Example
        -------
        >>> exposure = client.real.get_position_exposure(market.id)
        """
        return self._get_market_exposure(market_id)

    def get_portfolio_exposure(self) -> dict[str, float]:
        """
        Get total exposure across all markets.

        Returns
        -------
        dict[str, float]
            Dictionary mapping market_id to total exposure

        Example
        -------
        >>> exposure = client.real.get_portfolio_exposure()
        """
        exposure = {}
        for position in self.positions():
            if position.market_id not in exposure:
                exposure[position.market_id] = 0.0
            exposure[position.market_id] += position.cost_basis
        return exposure

# ── Helpers (backcompat wrappers)
def _validate_side(side: str) -> str:
    from .real_helpers import validate_side as _vs
    return _vs(side)


def _validate_positive(value: float, name: str) -> float:
    from .real_helpers import validate_positive as _vp
    return _vp(value, name)


def _now():
    from datetime import datetime, timezone
    return datetime.now(timezone.utc)
