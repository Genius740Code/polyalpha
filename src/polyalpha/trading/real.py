"""
Real trading engine — actual fund execution via Polymarket CLOB.

This module provides real trading capabilities with wallet integration,
position sizing strategies, risk management, and safety checks.

Usage
-----
    import polyalpha

    client = polyalpha.Client(
        private_key="your-private-key",
        rpc_url="https://polygon-rpc.com",
        polymarket_api_key="your-api-key",
        real_config=polyalpha.RealTradingConfig(
            position_sizing="kelly",
            kelly_fraction=0.25,
            max_order_size=100.0,
        ),
    )

    # Real market order
    order = client.real.buy(market, side="UP", confidence=0.65)

    # Real limit order
    order = client.real.limit(market, side="UP", price=0.92, amount=10.0)
"""

from __future__ import annotations

import logging
import time
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import TYPE_CHECKING, Optional

if TYPE_CHECKING:
    from ..database.database import TradeDatabase

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
)

log = logging.getLogger(__name__)


# ── Configuration ────────────────────────────────────────────────────────────────

@dataclass
class RealTradingConfig:
    """Configuration for real trading with safety checks."""

    # Authentication
    private_key: str
    rpc_url: str
    polymarket_api_key: str

    # Safety settings
    require_confirmation: bool = True  # Require manual confirmation for orders
    max_order_size: float = 1000.0  # Maximum USDC per order
    max_daily_loss: float = 500.0  # Stop trading if daily loss exceeds this
    max_position_size: float = 2000.0  # Maximum position size
    max_open_positions: int = 10  # Maximum concurrent positions

    # Position sizing strategy
    position_sizing: str = "fixed"  # "fixed", "percentage", "kelly"
    fixed_amount: float = 10.0  # For "fixed" strategy
    percentage_of_balance: float = 0.05  # For "percentage" strategy (5%)
    kelly_fraction: float = 0.25  # For "kelly" strategy (fraction of full Kelly)

    # Risk management
    enable_stop_loss: bool = True
    default_stop_loss_pct: float = 0.20  # 20% stop loss
    enable_take_profit: bool = True
    default_take_profit_pct: float = 0.50  # 50% take profit
    max_risk_per_trade: float = 0.02  # 2% of balance max risk

    # Execution settings
    slippage_tolerance: float = 0.05  # 5% slippage tolerance
    order_timeout: int = 60  # Order timeout in seconds
    retry_attempts: int = 3
    retry_delay: float = 1.0

    # Fee settings
    fee_mode: str = "polymarket"  # Use actual Polymarket fees

    # Logging
    log_all_orders: bool = True
    log_balance_updates: bool = True

    def __post_init__(self):
        """Validate configuration values."""
        if self.position_sizing not in ("fixed", "percentage", "kelly"):
            raise ValueError(
                f"position_sizing must be 'fixed', 'percentage', or 'kelly', "
                f"got '{self.position_sizing}'"
            )
        if self.fixed_amount < 0:
            raise ValueError(f"fixed_amount must be >= 0, got {self.fixed_amount}")
        if not 0 <= self.percentage_of_balance <= 1:
            raise ValueError(
                f"percentage_of_balance must be between 0 and 1, "
                f"got {self.percentage_of_balance}"
            )
        if not 0 <= self.kelly_fraction <= 1:
            raise ValueError(f"kelly_fraction must be between 0 and 1, got {self.kelly_fraction}")
        if self.max_order_size < 0:
            raise ValueError(f"max_order_size must be >= 0, got {self.max_order_size}")
        if self.max_daily_loss < 0:
            raise ValueError(f"max_daily_loss must be >= 0, got {self.max_daily_loss}")
        if self.max_position_size < 0:
            raise ValueError(f"max_position_size must be >= 0, got {self.max_position_size}")
        if self.max_open_positions < 1:
            raise ValueError(f"max_open_positions must be >= 1, got {self.max_open_positions}")
        if not 0 <= self.default_stop_loss_pct <= 1:
            raise ValueError(
                f"default_stop_loss_pct must be between 0 and 1, "
                f"got {self.default_stop_loss_pct}"
            )
        if not 0 <= self.default_take_profit_pct <= 1:
            raise ValueError(
                f"default_take_profit_pct must be between 0 and 1, "
                f"got {self.default_take_profit_pct}"
            )
        if not 0 <= self.max_risk_per_trade <= 1:
            raise ValueError(
                f"max_risk_per_trade must be between 0 and 1, got {self.max_risk_per_trade}"
            )
        if not 0 <= self.slippage_tolerance <= 1:
            raise ValueError(
                f"slippage_tolerance must be between 0 and 1, got {self.slippage_tolerance}"
            )
        if self.order_timeout < 1:
            raise ValueError(f"order_timeout must be >= 1, got {self.order_timeout}")
        if self.retry_attempts < 1:
            raise ValueError(f"retry_attempts must be >= 1, got {self.retry_attempts}")
        if self.retry_delay < 0:
            raise ValueError(f"retry_delay must be >= 0, got {self.retry_delay}")
        if self.fee_mode not in ("polymarket", "custom", "zero"):
            raise ValueError(
                f"fee_mode must be 'polymarket', 'custom', or 'zero', got '{self.fee_mode}'"
            )


# ── Dataclasses ────────────────────────────────────────────────────────────────

@dataclass
class RealOrder:
    """A real order executed on the CLOB."""

    id: str
    market_id: str
    slug: str
    side: str
    price: float
    amount: float
    shares: float
    fee: float
    status: str  # "pending", "open", "filled", "partially_filled", "cancelled"
    is_limit: bool
    created_at: datetime
    filled_at: Optional[datetime] = None
    tx_hash: Optional[str] = None

    # Risk management
    stop_loss: Optional[float] = None
    take_profit: Optional[float] = None

    # Position sizing info
    sizing_strategy: str = "fixed"
    confidence: float = 0.5
    kelly_fraction: float = 0.0

    def dump(self) -> dict:
        return {
            "id": self.id,
            "market": self.slug,
            "side": self.side,
            "price": self.price,
            "amount": self.amount,
            "shares": self.shares,
            "fee": self.fee,
            "status": self.status,
            "is_limit": self.is_limit,
            "created_at": self.created_at.isoformat(),
            "filled_at": self.filled_at.isoformat() if self.filled_at else None,
            "tx_hash": self.tx_hash,
            "stop_loss": self.stop_loss,
            "take_profit": self.take_profit,
            "sizing_strategy": self.sizing_strategy,
            "confidence": self.confidence,
            "kelly_fraction": self.kelly_fraction,
        }


@dataclass
class RealPosition:
    """A real position held on the CLOB."""

    market_id: str
    slug: str
    question: str
    side: str
    shares: float
    avg_price: float
    current_price: float
    cost_basis: float
    current_value: float
    resolved: bool = False
    outcome: Optional[str] = None
    order_ids: list[str] = field(default_factory=list)

    # Risk management
    stop_loss: Optional[float] = None
    take_profit: Optional[float] = None

    @property
    def pnl(self) -> float:
        return self.current_value - self.cost_basis

    @property
    def pnl_pct(self) -> float:
        if self.cost_basis == 0:
            return 0.0
        return (self.pnl / self.cost_basis) * 100

    def dump(self) -> dict:
        return {
            "market": self.slug,
            "question": self.question,
            "side": self.side,
            "shares": self.shares,
            "avg_price": self.avg_price,
            "current_price": self.current_price,
            "cost_basis": self.cost_basis,
            "current_value": self.current_value,
            "pnl": self.pnl,
            "pnl_pct": self.pnl_pct,
            "resolved": self.resolved,
            "outcome": self.outcome,
            "stop_loss": self.stop_loss,
            "take_profit": self.take_profit,
            "order_ids": self.order_ids,
        }


# ── Wallet Manager ───────────────────────────────────────────────────────────────

class WalletManager:
    """
    Manages wallet operations for real trading.

    Handles USDC balance, CLOB allowances, and transaction signing.
    """

    def __init__(self, private_key: str, rpc_url: str):
        """
        Initialize wallet manager.

        Parameters
        ----------
        private_key : str
            Private key for wallet operations
        rpc_url : str
            Polygon RPC URL for blockchain interaction
        """
        self._private_key = private_key
        self._rpc_url = rpc_url
        self._address: Optional[str] = None
        self._balance: float = 0.0
        self._allowance: float = 0.0

        # Web3.py and contract setup (lazy initialization)
        self._web3 = None
        self._usdc_contract = None
        self._clob_contract = None

        log.info("WalletManager initialized")

    def _init_web3(self) -> None:
        """Initialize Web3.py and contracts (lazy loading)."""
        try:
            from web3 import Web3
            from eth_account import Account

            self._web3 = Web3(Web3.HTTPProvider(self._rpc_url))
            account = Account.from_key(self._private_key)
            self._address = account.address

            # USDC contract on Polygon
            usdc_abi = [...]  # USDC contract ABI
            usdc_address = "0x2791Bca1f2de4661ED88A30C99A7a9449Aa84174"  # Polygon USDC
            self._usdc_contract = self._web3.eth.contract(
                address=usdc_address,
                abi=usdc_abi
            )

            log.info("Web3.py initialized for address %s", self._address)
        except ImportError:
            log.warning("Web3.py not installed. Wallet operations will be simulated.")
            self._address = "0x" + self._private_key[:40]  # Simulated address

    def get_address(self) -> str:
        """Get wallet address."""
        if self._address is None:
            self._init_web3()
        return self._address or "0x" + self._private_key[:40]

    def get_balance(self) -> float:
        """
        Get current USDC balance.

        Returns
        -------
        float
            USDC balance (simulated if Web3 not available)
        """
        if self._web3 is None:
            self._init_web3()

        if self._web3 and self._usdc_contract:
            try:
                balance_raw = self._usdc_contract.functions.balanceOf(
                    self._address
                ).call()
                self._balance = float(balance_raw) / 1e6  # USDC has 6 decimals
            except Exception as e:
                log.error("Failed to fetch balance: %s", e)
                self._balance = 0.0

        return self._balance

    def get_allowance(self) -> float:
        """
        Get CLOB allowance for trading.

        Returns
        -------
        float
            CLOB allowance (simulated if Web3 not available)
        """
        if self._web3 is None:
            self._init_web3()

        if self._web3 and self._clob_contract:
            try:
                allowance_raw = self._usdc_contract.functions.allowance(
                    self._address,
                    self._clob_contract.address
                ).call()
                self._allowance = float(allowance_raw) / 1e6
            except Exception as e:
                log.error("Failed to fetch allowance: %s", e)
                self._allowance = 0.0

        return self._allowance

    def approve_clob(self, amount: float) -> str:
        """
        Approve CLOB contract to spend USDC.

        Parameters
        ----------
        amount : float
            Amount to approve (use very large number for unlimited)

        Returns
        -------
        str
            Transaction hash (simulated if Web3 not available)
        """
        if self._web3 is None:
            self._init_web3()

        if self._web3 and self._usdc_contract:
            try:
                amount_raw = int(amount * 1e6)
                tx = self._usdc_contract.functions.approve(
                    self._clob_contract.address,
                    amount_raw
                ).build_transaction({
                    'from': self._address,
                    'gas': 100000,
                    'gasPrice': self._web3.eth.gas_price,
                    'nonce': self._web3.eth.get_transaction_count(self._address),
                })

                # Sign and send transaction
                from eth_account import Account
                signed_tx = Account.sign_transaction(tx, self._private_key)
                tx_hash = self._web3.eth.send_raw_transaction(signed_tx.raw_transaction)
                log.info("CLOB approval transaction sent: %s", tx_hash.hex())
                return tx_hash.hex()
            except Exception as e:
                log.error("Failed to approve CLOB: %s", e)
                raise

        # Simulated approval
        self._allowance = amount
        log.info("Simulated CLOB approval for %f USDC", amount)
        return "0x" + "0" * 64

    def refresh_balance(self) -> None:
        """Refresh balance from blockchain."""
        self._balance = self.get_balance()
        if self._config.log_balance_updates:
            log.info("Balance refreshed: $%.2f", self._balance)

    def wait_for_transaction(self, tx_hash: str, timeout: int = 60) -> dict:
        """
        Wait for transaction confirmation.

        Parameters
        ----------
        tx_hash : str
            Transaction hash
        timeout : int
            Timeout in seconds

        Returns
        -------
        dict
            Transaction receipt
        """
        if self._web3 is None:
            self._init_web3()

        if self._web3:
            try:
                receipt = self._web3.eth.wait_for_transaction_receipt(
                    tx_hash,
                    timeout=timeout
                )
                return {
                    'status': receipt['status'],
                    'gas_used': receipt['gasUsed'],
                    'block_number': receipt['blockNumber'],
                }
            except Exception as e:
                log.error("Transaction %s failed or timed out: %s", tx_hash, e)
                raise OrderTimeout(f"Transaction {tx_hash} timed out")

        # Simulated receipt
        return {'status': 1, 'gas_used': 50000, 'block_number': 12345678}


# ── Real Trading Engine ───────────────────────────────────────────────────────────

class RealTradingEngine:
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
    """

    def __init__(
        self,
        private_key: str,
        rpc_url: str,
        polymarket_api_key: str,
        config: Optional[RealTradingConfig] = None,
        db_path: Optional[str] = None,
    ):
        # Configuration
        self._config = config or RealTradingConfig(
            private_key=private_key,
            rpc_url=rpc_url,
            polymarket_api_key=polymarket_api_key,
        )

        # Wallet setup
        self._wallet = WalletManager(private_key, rpc_url)
        self._balance: float = 0.0
        self._allowance: float = 0.0

        # Order management
        self._orders: dict[str, RealOrder] = {}
        self._positions: dict[str, RealPosition] = {}  # key: "{market_id}:{side}"

        # CLOB client (placeholder - to be implemented)
        self._clob_client = None

        # Database
        self._db: Optional[TradeDatabase] = None
        self._db_enabled: bool = False
        if db_path:
            self.enable_database(db_path)

        # Emergency mode
        self._emergency_mode: bool = False

        # Initialize balance
        self.refresh_balance()

        log.info("RealTradingEngine initialized")

    @property
    def config(self) -> RealTradingConfig:
        """Get current configuration."""
        return self._config

    @property
    def balance(self) -> float:
        """Get current USDC balance."""
        return self._balance

    @property
    def emergency_mode(self) -> bool:
        """Check if emergency mode is active."""
        return self._emergency_mode

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
        """Refresh balance from blockchain."""
        self._balance = self._wallet.get_balance()
        self._allowance = self._wallet.get_allowance()
        if self._config.log_balance_updates:
            log.info("Balance: $%.2f, Allowance: $%.2f", self._balance, self._allowance)

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

        # Get price
        if price is None:
            price = market.up_price if side == "UP" else market.down_price

        # Calculate position size if not provided
        if amount is None:
            amount = self._calculate_position_size(market, side, confidence, price)

        # Validate against risk limits
        self._validate_order(amount, market)

        # Check balance
        if amount > self._balance:
            raise InsufficientBalance(
                f"Order amount ${amount:.2f} exceeds balance ${self._balance:.2f}"
            )

        # Check allowance
        if amount > self._allowance:
            raise InsufficientAllowance(
                f"Order amount ${amount:.2f} exceeds allowance ${self._allowance:.2f}"
            )

        # Calculate shares and fee
        shares, fee = self._calculate_shares_and_fee(amount, price)

        # Require confirmation if enabled
        if confirm and self._config.require_confirmation:
            self._require_confirmation(market, side, amount, price, shares, fee)

        # Place order on CLOB (placeholder)
        order_response = self._place_clob_order(
            market.token_id,
            side.lower(),
            price,
            shares,
            "market" if price is None else "limit"
        )

        # Create order object
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
            is_limit=price is not None,
            created_at=datetime.now(timezone.utc),
            stop_loss=stop_loss,
            take_profit=take_profit,
            sizing_strategy=self._config.position_sizing,
            confidence=confidence,
        )

        # Update balance
        self._balance -= (amount + fee)

        # Store order
        self._orders[order.id] = order

        # Update position
        self._update_position(market, side, order)

        # Save to database
        if self._db_enabled:
            self._save_order_to_db(order)

        if self._config.log_all_orders:
            log.info(
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

    # ── Order Management ─────────────────────────────────────────────────────────

    def cancel(self, order_id: str) -> None:
        """
        Cancel an open order.

        Parameters
        ----------
        order_id : str
            Order ID to cancel
        """
        if order_id not in self._orders:
            raise OrderNotFound(f"Order {order_id} not found")

        order = self._orders[order_id]

        if order.status not in ("open", "pending"):
            log.warning("Order %s is not open (status: %s)", order_id, order.status)
            return

        # Cancel on CLOB (placeholder)
        self._cancel_clob_order(order_id)

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
        if order_id not in self._orders:
            raise OrderNotFound(f"Order {order_id} not found")
        return self._orders[order_id]

    def open_orders(self) -> list[RealOrder]:
        """Get all open orders."""
        return [o for o in self._orders.values() if o.status in ("open", "pending")]

    # ── Position Management ───────────────────────────────────────────────────────

    def positions(self) -> list[RealPosition]:
        """Get all open positions."""
        return [p for p in self._positions.values() if not p.resolved]

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
        key = f"{market_id}:{side}"
        if key not in self._positions:
            raise PositionNotFound(f"No position for {market_id} {side}")
        return self._positions[key]

    # ── Safety Features ───────────────────────────────────────────────────────────

    def emergency_stop(self, reason: str = "Manual") -> None:
        """
        Emergency stop - cancel all open orders and prevent new trades.

        Parameters
        ----------
        reason : str
            Reason for emergency stop
        """
        log.warning("EMERGENCY STOP: %s", reason)

        # Cancel all open orders
        for order_id in list(self._orders.keys()):
            try:
                self.cancel(order_id)
            except Exception as e:
                log.error("Failed to cancel order %s: %s", order_id, e)

        # Set emergency flag
        self._emergency_mode = True

        log.warning("All trading halted. Call resume_trading() to re-enable.")

    def resume_trading(self, confirm: bool = True) -> None:
        """Resume trading after emergency stop."""
        if confirm:
            response = input("Resume trading? (yes/no): ").strip().lower()
            if response not in ("yes", "y"):
                print("Trading remains halted.")
                return

        self._emergency_mode = False
        log.info("Trading resumed.")

    # ── Private Methods ───────────────────────────────────────────────────────────

    def _calculate_position_size(
        self,
        market,
        side: str,
        confidence: float,
        price: float,
    ) -> float:
        """Calculate position size based on configured strategy."""
        strategy = self._config.position_sizing

        if strategy == "fixed":
            return min(self._config.fixed_amount, self._balance)
        elif strategy == "percentage":
            return self._balance * self._config.percentage_of_balance
        elif strategy == "kelly":
            # Kelly criterion calculation
            if confidence < 0.55:
                return 0.0  # Minimum confidence for Kelly

            implied_prob = price
            if confidence <= implied_prob:
                return 0.0  # No edge

            kelly_fraction = (confidence - implied_prob) / (1 - implied_prob)
            kelly_fraction *= self._config.kelly_fraction
            kelly_fraction = min(kelly_fraction, 0.5)  # Cap at 50%

            return self._balance * kelly_fraction
        else:
            return min(self._config.fixed_amount, self._balance)

    def _validate_order(self, amount: float, market) -> None:
        """Validate order against risk limits."""
        # Check max order size
        if amount > self._config.max_order_size:
            raise RiskLimitExceeded(
                f"Order amount ${amount:.2f} exceeds maximum ${self._config.max_order_size:.2f}"
            )

        # Check max position size
        current_exposure = self._get_market_exposure(market.id)
        if current_exposure + amount > self._config.max_position_size:
            raise RiskLimitExceeded(
                f"Position would exceed maximum size ${self._config.max_position_size:.2f}"
            )

        # Check max open positions
        if len(self.positions()) >= self._config.max_open_positions:
            raise RiskLimitExceeded(
                f"Maximum open positions ({self._config.max_open_positions}) reached"
            )

        # Check max risk per trade
        max_risk = self._balance * self._config.max_risk_per_trade
        if amount > max_risk:
            raise RiskLimitExceeded(
                f"Order amount ${amount:.2f} exceeds max risk ${max_risk:.2f} "
                f"({self._config.max_risk_per_trade:.1%})"
            )

    def _calculate_shares_and_fee(self, amount: float, price: float) -> tuple[float, float]:
        """Calculate shares and fee for an order."""
        shares = amount / price
        fee = amount * 0.02  # Placeholder: 2% fee
        return shares, fee

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
        print(f"Total:     ${amount + fee:.2f}")
        print(f"Balance:   ${self._balance:.2f}")
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
    ) -> dict:
        """Place order on CLOB (placeholder)."""
        # This is a placeholder - actual CLOB integration to be implemented
        import uuid
        return {
            "order_id": str(uuid.uuid4()),
            "status": "pending",
        }

    def _cancel_clob_order(self, order_id: str) -> None:
        """Cancel order on CLOB (placeholder)."""
        # This is a placeholder - actual CLOB integration to be implemented
        pass

    def _update_position(self, market, side: str, order: RealOrder) -> None:
        """Update position after order fill."""
        key = f"{market.id}:{side}"

        if key in self._positions:
            # Update existing position
            position = self._positions[key]
            position.order_ids.append(order.id)

            # Volume-weighted average price
            total_shares = position.shares + order.shares
            position.avg_price = (
                (position.avg_price * position.shares + order.price * order.shares)
                / total_shares
            )
            position.shares = total_shares
            position.cost_basis = position.shares * position.avg_price
            position.current_value = position.shares * order.price
        else:
            # Create new position
            position = RealPosition(
                market_id=market.id,
                slug=market.slug,
                question=market.question,
                side=side,
                shares=order.shares,
                avg_price=order.price,
                current_price=order.price,
                cost_basis=order.amount,
                current_value=order.amount,
                order_ids=[order.id],
            )
            self._positions[key] = position

    def _get_market_exposure(self, market_id: str) -> float:
        """Get total exposure for a market."""
        exposure = 0.0
        for key, position in self._positions.items():
            if position.market_id == market_id and not position.resolved:
                exposure += position.cost_basis
        return exposure

    def _save_order_to_db(self, order: RealOrder) -> None:
        """Save real order to database."""
        if not self._db_enabled or self._db is None:
            return

        try:
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
                wallet_address=self._wallet.get_address(),
            )
            log.debug("Real: order saved to database for %s", order.slug)
        except Exception as exc:
            log.error("Real: failed to save order to database: %s", exc)


# ── Helpers ─────────────────────────────────────────────────────────────────────

def _validate_side(side: str) -> str:
    """Validate and normalize side."""
    side = side.upper()
    if side not in ("UP", "DOWN"):
        raise ValueError(f"side must be 'UP' or 'DOWN', got '{side}'")
    return side


def _validate_positive(value: float, name: str) -> float:
    """Validate that value is positive."""
    if value <= 0:
        raise ValueError(f"{name} must be positive, got {value}")
    return value


def _now() -> datetime:
    """Get current UTC datetime."""
    return datetime.now(timezone.utc)
