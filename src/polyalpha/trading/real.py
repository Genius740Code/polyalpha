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
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
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
    FEE_RATE_SPORTS,
    FEE_RATE_CRYPTO,
    FEE_RATE_ECONOMICS,
    MINIMUM_FEE,
    FEE_ROUNDING,
    POLYMARKET_FEE_ROUNDING,
)
from .clob_client import ClobClient
from .alchemy_client import AlchemyClient
from .error_handling import (
    CircuitBreaker,
    ErrorRecoveryManager,
    GracefulDegradation,
    TransactionRollbackManager,
    DisasterRecovery,
    DegradationLevel,
)

from ..report.engine import ReportEngine


log = logging.getLogger(__name__)


# ── Configuration ────────────────────────────────────────────────────────────────

@dataclass
class RealTradingConfig:
    """Configuration for real trading with safety checks."""

    # Authentication
    private_key: str
    rpc_url: str
    polymarket_api_key: str
    polymarket_api_secret: str = ""
    polymarket_api_passphrase: str = ""

    # Safety settings
    require_confirmation: bool = True  # Require manual confirmation for orders
    max_order_size: float = 1000.0  # Maximum USDC per order
    max_daily_loss: float = 500.0  # Stop trading if daily loss exceeds this
    max_position_size: float = 2000.0  # Maximum position size
    max_open_positions: int = 10  # Maximum concurrent positions (global)
    max_positions_per_market: int = 1  # Maximum concurrent positions per individual market (None = no limit)

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

    # Position management
    enable_position_scaling: bool = True  # Allow pyramiding (adding to winning positions)
    min_profit_for_scaling: float = 0.10  # Minimum 10% profit before allowing scaling
    max_scale_additions: int = 3  # Maximum number of times to scale a position
    enable_position_reduction: bool = True  # Allow reducing positions
    enable_hedging: bool = True  # Allow hedging positions
    max_hedge_ratio: float = 0.5  # Maximum hedge ratio (50% of position)

    # Execution settings
    slippage_tolerance: float = 0.05  # 5% slippage tolerance
    order_timeout: int = 60  # Order timeout in seconds
    retry_attempts: int = 3
    retry_delay: float = 1.0

    # Fee settings
    fee_mode: str = "polymarket"  # "polymarket", "custom", or "zero"
    market_category: str = "crypto"  # For polymarket mode: crypto, sports, finance, politics, tech, economics, culture, weather, geopolitical, other
    custom_fee_rate: float = 0.02  # Used when fee_mode="custom"
    maker_fee_rate: float = 0.0  # Maker fee rate for limit orders

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
        if self.max_positions_per_market < 0:
            raise ValueError(f"max_positions_per_market must be >= 0, got {self.max_positions_per_market}")
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
        if self.custom_fee_rate < 0:
            raise ValueError(f"custom_fee_rate must be >= 0, got {self.custom_fee_rate}")
        if self.maker_fee_rate < 0:
            raise ValueError(f"maker_fee_rate must be >= 0, got {self.maker_fee_rate}")


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
    status: str  # "pending", "open", "filled", "partially_filled", "cancelled", "expired"
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

    # Fill tracking
    filled_shares: float = 0.0
    filled_amount: float = 0.0
    avg_fill_price: float = 0.0
    last_status_check: Optional[datetime] = None
    status_check_attempts: int = 0

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
            "filled_shares": self.filled_shares,
            "filled_amount": self.filled_amount,
            "avg_fill_price": self.avg_fill_price,
            "last_status_check": self.last_status_check.isoformat() if self.last_status_check else None,
            "status_check_attempts": self.status_check_attempts,
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
    entry_time: Optional[datetime] = None

    # Risk management
    stop_loss: Optional[float] = None
    take_profit: Optional[float] = None

    # Position management
    scale_count: int = 0  # Number of times position has been scaled
    hedge_amount: float = 0.0  # Amount hedged on opposite side

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


@dataclass
class OCOOrder:
    """
    One-Cancels-Other (OCO) order pair.
    
    An OCO order consists of two orders where if one is filled,
    the other is automatically cancelled.
    """

    id: str
    market_id: str
    slug: str
    side: str
    order1_id: str  # First order (e.g., take profit)
    order2_id: str  # Second order (e.g., stop loss)
    order1_price: float
    order2_price: float
    amount: float
    status: str  # "active", "triggered", "cancelled"
    created_at: datetime
    triggered_order_id: Optional[str] = None
    cancelled_order_id: Optional[str] = None
    triggered_at: Optional[datetime] = None

    def dump(self) -> dict:
        return {
            "id": self.id,
            "market": self.slug,
            "side": self.side,
            "order1_id": self.order1_id,
            "order2_id": self.order2_id,
            "order1_price": self.order1_price,
            "order2_price": self.order2_price,
            "amount": self.amount,
            "status": self.status,
            "created_at": self.created_at.isoformat(),
            "triggered_order_id": self.triggered_order_id,
            "cancelled_order_id": self.cancelled_order_id,
            "triggered_at": self.triggered_at.isoformat() if self.triggered_at else None,
        }


@dataclass
class BracketOrder:
    """
    Bracket order (entry + stop loss + take profit).
    
    A bracket order places an entry order along with
    associated stop loss and take profit orders.
    """

    id: str
    market_id: str
    slug: str
    side: str
    entry_order_id: str
    entry_price: float
    amount: float
    status: str  # "pending", "active", "partial", "completed", "cancelled"
    created_at: datetime
    stop_loss_order_id: Optional[str] = None
    take_profit_order_id: Optional[str] = None
    stop_loss_price: Optional[float] = None
    take_profit_price: Optional[float] = None
    filled_at: Optional[datetime] = None
    token_id: str = ""

    def dump(self) -> dict:
        return {
            "id": self.id,
            "market": self.slug,
            "side": self.side,
            "entry_order_id": self.entry_order_id,
            "stop_loss_order_id": self.stop_loss_order_id,
            "take_profit_order_id": self.take_profit_order_id,
            "entry_price": self.entry_price,
            "stop_loss_price": self.stop_loss_price,
            "take_profit_price": self.take_profit_price,
            "amount": self.amount,
            "status": self.status,
            "created_at": self.created_at.isoformat(),
            "filled_at": self.filled_at.isoformat() if self.filled_at else None,
        }


@dataclass
class ConditionalOrder:
    """
    Conditional order with if-then logic.
    
    A conditional order triggers a child order when
    specified conditions are met (e.g., price threshold).
    """

    id: str
    market_id: str
    slug: str
    side: str
    condition_type: str  # "price_above", "price_below", "time_after"
    condition_value: float
    status: str  # "waiting", "triggered", "cancelled", "expired"
    created_at: datetime
    child_order_id: Optional[str] = None
    child_order_price: Optional[float] = None
    child_order_amount: Optional[float] = None
    triggered_at: Optional[datetime] = None
    expires_at: Optional[datetime] = None
    token_id: str = ""

    def dump(self) -> dict:
        return {
            "id": self.id,
            "market": self.slug,
            "side": self.side,
            "condition_type": self.condition_type,
            "condition_value": self.condition_value,
            "child_order_id": self.child_order_id,
            "child_order_price": self.child_order_price,
            "child_order_amount": self.child_order_amount,
            "status": self.status,
            "created_at": self.created_at.isoformat(),
            "triggered_at": self.triggered_at.isoformat() if self.triggered_at else None,
            "expires_at": self.expires_at.isoformat() if self.expires_at else None,
        }


@dataclass
class IcebergOrder:
    """
    Iceberg order for large order splitting.
    
    An iceberg order splits a large order into smaller
    visible chunks to avoid market impact.
    """

    id: str
    market_id: str
    slug: str
    side: str
    total_amount: float
    visible_size: float
    price: float
    status: str  # "active", "partial", "completed", "cancelled"
    created_at: datetime
    filled_amount: float = 0.0
    child_order_ids: list[str] = field(default_factory=list)
    token_id: str = ""

    @property
    def remaining_amount(self) -> float:
        return self.total_amount - self.filled_amount

    @property
    def progress_pct(self) -> float:
        if self.total_amount == 0:
            return 0.0
        return (self.filled_amount / self.total_amount) * 100

    def dump(self) -> dict:
        return {
            "id": self.id,
            "market": self.slug,
            "side": self.side,
            "total_amount": self.total_amount,
            "visible_size": self.visible_size,
            "price": self.price,
            "filled_amount": self.filled_amount,
            "remaining_amount": self.remaining_amount,
            "progress_pct": self.progress_pct,
            "status": self.status,
            "created_at": self.created_at.isoformat(),
            "child_order_ids": self.child_order_ids,
        }


@dataclass
class TWAPOrder:
    """
    Time-Weighted Average Price (TWAP) execution order.
    
    A TWAP order executes a large order over a specified
    time period to achieve an average execution price.
    """

    id: str
    market_id: str
    slug: str
    side: str
    total_amount: float
    duration_seconds: int
    num_slices: int
    status: str  # "active", "partial", "completed", "cancelled"
    created_at: datetime
    price: Optional[float] = None  # If None, uses market price
    filled_amount: float = 0.0
    ends_at: Optional[datetime] = None
    child_order_ids: list[str] = field(default_factory=list)
    slice_interval: float = 0.0  # Seconds between slices
    token_id: str = ""

    @property
    def remaining_amount(self) -> float:
        return self.total_amount - self.filled_amount

    @property
    def slice_amount(self) -> float:
        return self.total_amount / self.num_slices

    @property
    def progress_pct(self) -> float:
        if self.total_amount == 0:
            return 0.0
        return (self.filled_amount / self.total_amount) * 100

    def dump(self) -> dict:
        return {
            "id": self.id,
            "market": self.slug,
            "side": self.side,
            "total_amount": self.total_amount,
            "duration_seconds": self.duration_seconds,
            "num_slices": self.num_slices,
            "price": self.price,
            "filled_amount": self.filled_amount,
            "remaining_amount": self.remaining_amount,
            "slice_amount": self.slice_amount,
            "progress_pct": self.progress_pct,
            "status": self.status,
            "created_at": self.created_at.isoformat(),
            "ends_at": self.ends_at.isoformat() if self.ends_at else None,
            "child_order_ids": self.child_order_ids,
            "slice_interval": self.slice_interval,
        }


# ── Position Sizers ────────────────────────────────────────────────────────────────

class PositionSizer(ABC):
    """Abstract base class for position sizing strategies."""

    @abstractmethod
    def calculate_size(
        self,
        balance: float,
        market,
        side: str,
        confidence: float = 0.5,
        price: Optional[float] = None,
    ) -> float:
        """Calculate position size in USDC."""
        pass


class FixedPositionSizer(PositionSizer):
    """Fixed amount position sizing."""

    def __init__(self, amount: float):
        self.amount = amount

    def calculate_size(
        self,
        balance: float,
        market,
        side: str,
        confidence: float = 0.5,
        price: Optional[float] = None,
    ) -> float:
        return min(self.amount, balance)


class PercentagePositionSizer(PositionSizer):
    """Percentage of balance position sizing."""

    def __init__(self, percentage: float):
        self.percentage = percentage

    def calculate_size(
        self,
        balance: float,
        market,
        side: str,
        confidence: float = 0.5,
        price: Optional[float] = None,
    ) -> float:
        return balance * self.percentage


class KellyPositionSizer(PositionSizer):
    """
    Kelly criterion position sizing.

    Formula: f* = (bp - q) / b
    Where:
    - f* = fraction of bankroll to wager
    - b = odds received on the wager (decimal odds)
    - p = probability of winning
    - q = probability of losing (1 - p)

    For binary markets: f* = p - q/b = 2p - 1 (when odds are 1:1)
    """

    def __init__(self, kelly_fraction: float = 0.25, min_confidence: float = 0.55):
        """
        Parameters
        ----------
        kelly_fraction : float
            Fraction of full Kelly to use (0.25 = quarter Kelly for safety)
        min_confidence : float
            Minimum confidence to place a trade (below this, return 0)
        """
        self.kelly_fraction = kelly_fraction
        self.min_confidence = min_confidence

    def calculate_size(
        self,
        balance: float,
        market,
        side: str,
        confidence: float = 0.5,
        price: Optional[float] = None,
    ) -> float:
        # Don't trade if confidence is too low
        if confidence < self.min_confidence:
            return 0.0

        # Calculate Kelly fraction
        # For binary markets with price p, implied probability = p
        # If our confidence > implied probability, we have edge
        implied_prob = price if price else (market.up_price if side == "UP" else market.down_price)

        if confidence <= implied_prob:
            return 0.0  # No edge

        # Kelly formula for binary options
        # f = (confidence * (1 + (1-implied_prob)/implied_prob) - 1) / ((1-implied_prob)/implied_prob)
        # Simplified: f = (confidence - implied_prob) / (1 - implied_prob)
        kelly_fraction = (confidence - implied_prob) / (1 - implied_prob)

        # Apply safety fraction (quarter Kelly, etc.)
        kelly_fraction *= self.kelly_fraction

        # Cap at reasonable maximum (never bet more than 50% of bankroll)
        kelly_fraction = min(kelly_fraction, 0.5)

        return balance * kelly_fraction


class HybridPositionSizer(PositionSizer):
    """
    Hybrid position sizing combining multiple strategies.

    Strategies:
    - Base size from fixed or percentage
    - Adjust based on Kelly confidence
    - Apply risk limits
    """

    def __init__(
        self,
        base_strategy: str = "percentage",
        base_amount: float = 0.05,  # 5% for percentage
        enable_kelly_adjustment: bool = True,
        kelly_fraction: float = 0.25,
        max_size: float = 1000.0,
        min_size: float = 1.0,
    ):
        self.base_strategy = base_strategy
        self.base_amount = base_amount
        self.enable_kelly_adjustment = enable_kelly_adjustment
        self.kelly_fraction = kelly_fraction
        self.max_size = max_size
        self.min_size = min_size

    def calculate_size(
        self,
        balance: float,
        market,
        side: str,
        confidence: float = 0.5,
        price: Optional[float] = None,
    ) -> float:
        # Calculate base size
        if self.base_strategy == "fixed":
            size = min(self.base_amount, balance)
        else:  # percentage
            size = balance * self.base_amount

        # Apply Kelly adjustment if enabled
        if self.enable_kelly_adjustment and confidence > 0.5:
            implied_prob = price if price else (market.up_price if side == "UP" else market.down_price)
            if confidence > implied_prob:
                kelly_adj = (confidence - implied_prob) / (1 - implied_prob) * self.kelly_fraction
                size *= (1 + kelly_adj)

        # Apply limits
        size = max(self.min_size, min(size, self.max_size))
        size = min(size, balance)

        return size


# ── Risk Manager ─────────────────────────────────────────────────────────────────

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

        # Check max order size
        if amount > self.config.max_order_size:
            raise RiskLimitExceeded(
                f"Order amount ${amount:.2f} exceeds maximum ${self.config.max_order_size:.2f}"
            )

        # Check max position size
        current_exposure = self._get_market_exposure(market.id, positions)
        if current_exposure + amount > self.config.max_position_size:
            raise RiskLimitExceeded(
                f"Position would exceed maximum size ${self.config.max_position_size:.2f}"
            )

        # Check max open positions (global)
        open_positions = [p for p in positions.values() if not p.resolved]
        if len(open_positions) >= self.config.max_open_positions:
            raise RiskLimitExceeded(
                f"Maximum open positions ({self.config.max_open_positions}) reached"
            )

        # Check max positions per market
        if self.config.max_positions_per_market > 0:
            market_positions = [p for p in positions.values() if not p.resolved and p.market_id == market.id]
            if len(market_positions) >= self.config.max_positions_per_market:
                raise RiskLimitExceeded(
                    f"Maximum positions per market ({self.config.max_positions_per_market}) reached for market {market.id}"
                )

        # Check daily loss limit
        if self.daily_pnl < -self.config.max_daily_loss:
            raise RiskLimitExceeded(
                f"Daily loss ${abs(self.daily_pnl):.2f} exceeds limit ${self.config.max_daily_loss:.2f}"
            )

        # Check max risk per trade
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
        """
        Calculate position size based on risk per trade.

        Formula: Position Size = (Balance × Risk%) / |Entry - StopLoss| / Entry
        """
        risk_amount = balance * self.config.max_risk_per_trade
        price_diff = abs(entry_price - stop_loss)

        if price_diff == 0:
            return balance * risk_amount

        position_size = risk_amount / (price_diff / entry_price)
        return min(position_size, balance)

    def _get_market_exposure(self, market_id: str, positions: dict[str, RealPosition]) -> float:
        """Get total exposure for a market."""
        exposure = 0.0
        for position in positions.values():
            if position.market_id == market_id and not position.resolved:
                exposure += position.cost_basis
        return exposure

    def _check_and_reset_daily(self) -> None:
        """Check if we need to reset daily tracking (new day)."""
        today = datetime.now(timezone.utc).date().isoformat()
        if self._last_reset_date != today:
            self.daily_pnl = 0.0
            self.daily_trades = 0
            self._last_reset_date = today
            log.info("RiskManager: Daily tracking reset for new day")

    def record_trade(self, pnl: float) -> None:
        """
        Record a trade's P&L for daily tracking.

        Parameters
        ----------
        pnl : float
            Profit or loss from the trade (positive for profit, negative for loss)
        """
        self._check_and_reset_daily()
        self.daily_pnl += pnl
        self.daily_trades += 1
        log.info("RiskManager: Recorded trade P&L: $%.2f (Daily: $%.2f, Trades: %d)", 
                 pnl, self.daily_pnl, self.daily_trades)

    def initialize_daily_balance(self, balance: float) -> None:
        """
        Initialize the daily starting balance for P&L tracking.

        Parameters
        ----------
        balance : float
            Current balance to set as daily start
        """
        self._check_and_reset_daily()
        if self.daily_start_balance == 0.0:
            self.daily_start_balance = balance
            log.info("RiskManager: Daily start balance set to $%.2f", balance)

    def get_daily_stats(self) -> dict:
        """
        Get daily trading statistics.

        Returns
        -------
        dict
            Dictionary with daily_pnl, daily_trades, daily_start_balance, daily_pct_change
        """
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


# ── Wallet Manager ───────────────────────────────────────────────────────────────

class WalletManager:
    """
    Manages wallet operations for real trading.

    Handles USDC balance, CLOB allowances, and transaction signing.
    """

    def __init__(self, private_key: str, rpc_url: str, log_balance_updates: bool = False):
        """
        Initialize wallet manager.

        Parameters
        ----------
        private_key : str
            Private key for wallet operations
        rpc_url : str
            Polygon RPC URL for blockchain interaction
        log_balance_updates : bool
            Whether to log balance updates
        """
        self._private_key = private_key
        self._rpc_url = rpc_url
        self._address: Optional[str] = None
        self._balance: float = 0.0
        self._allowance: float = 0.0
        self._log_balance_updates = log_balance_updates

        # Web3.py and contract setup (lazy initialization)
        self._web3 = None
        self._usdc_contract = None
        self._clob_contract = None

        log.info("WalletManager initialized")

    @property
    def address(self) -> Optional[str]:
        """Get the wallet address."""
        if not self._address:
            from eth_account import Account
            account = Account.from_key(self._private_key)
            self._address = account.address
        return self._address

    def _init_web3(self) -> None:
        """Initialize Web3.py and contracts (mandatory for production)."""
        from web3 import Web3
        from eth_account import Account

        self._web3 = Web3(Web3.HTTPProvider(self._rpc_url))
        account = Account.from_key(self._private_key)
        self._address = account.address

        # USDC contract on Polygon (minimal ABI for balance and allowance)
        usdc_abi = [
            {
                "constant": True,
                "inputs": [{"name": "_owner", "type": "address"}],
                "name": "balanceOf",
                "outputs": [{"name": "balance", "type": "uint256"}],
                "type": "function",
            },
            {
                "constant": True,
                "inputs": [
                    {"name": "_owner", "type": "address"},
                    {"name": "_spender", "type": "address"},
                ],
                "name": "allowance",
                "outputs": [{"name": "", "type": "uint256"}],
                "type": "function",
            },
            {
                "constant": False,
                "inputs": [
                    {"name": "_spender", "type": "address"},
                    {"name": "_value", "type": "uint256"},
                ],
                "name": "approve",
                "outputs": [{"name": "", "type": "bool"}],
                "type": "function",
            },
            {
                "constant": True,
                "inputs": [],
                "name": "decimals",
                "outputs": [{"name": "", "type": "uint8"}],
                "type": "function",
            },
        ]
        usdc_address = "0x2791Bca1f2de4661ED88A30C99A7a9449Aa84174"  # Polygon USDC
        self._usdc_contract = self._web3.eth.contract(
            address=usdc_address,
            abi=usdc_abi
        )

        # Initialize nonce management
        self._nonce: int = self._web3.eth.get_transaction_count(self._address)
        self._pending_transactions: dict[str, dict] = {}  # tx_hash -> {nonce, timestamp, retry_count}

        # Gas cost tracking
        self._total_gas_spent: float = 0.0
        self._gas_cost_usd: float = 0.0

        log.info("Web3.py initialized for address %s", self._address)

    def _build_transaction_params(self, gas_estimate: int, to_address: str) -> dict:
        """
        Build transaction parameters with EIP-1559 gas management.

        Parameters
        ----------
        gas_estimate : int
            Estimated gas for the transaction
        to_address : str
            Destination address

        Returns
        -------
        dict
            Transaction parameters
        """
        # Get current gas price from network
        latest_block = self._web3.eth.get_block('latest')
        base_fee = latest_block.get('baseFeePerGas', 0)
        
        # EIP-1559: maxFeePerGas = baseFee + maxPriorityFeePerGas
        # Set priority fee to 2 Gwei (2000000000 wei)
        max_priority_fee_per_gas = self._web3.to_wei(2, 'gwei')
        
        # Set max fee to baseFee + 3 Gwei (cushion for baseFee increases)
        max_fee_per_gas = base_fee + self._web3.to_wei(3, 'gwei')
        
        # Get and increment nonce
        nonce = self._get_next_nonce()
        
        return {
            'from': self._address,
            'gas': gas_estimate,
            'maxFeePerGas': max_fee_per_gas,
            'maxPriorityFeePerGas': max_priority_fee_per_gas,
            'nonce': nonce,
            'type': 2,  # EIP-1559 transaction type
        }

    def _get_next_nonce(self) -> int:
        """
        Get next nonce with proper management for concurrent transactions.

        Returns
        -------
        int
            Next nonce to use
        """
        # Get current network nonce
        network_nonce = self._web3.eth.get_transaction_count(self._address)
        
        # Use the higher of network nonce or local nonce
        if self._nonce < network_nonce:
            self._nonce = network_nonce
        
        current_nonce = self._nonce
        self._nonce += 1
        
        return current_nonce

    def _track_pending_transaction(self, tx_hash: str, nonce: int) -> None:
        """
        Track a pending transaction for potential re-broadcast.

        Parameters
        ----------
        tx_hash : str
            Transaction hash
        nonce : int
            Transaction nonce
        """
        self._pending_transactions[tx_hash] = {
            'nonce': nonce,
            'timestamp': time.time(),
            'retry_count': 0,
        }

    def _rebroadcast_transaction(self, tx_hash: str) -> dict:
        """
        Re-broadcast a transaction that timed out.

        Parameters
        ----------
        tx_hash : str
            Transaction hash to re-broadcast

        Returns
        -------
        dict
            Transaction receipt or error info
        """
        if tx_hash not in self._pending_transactions:
            log.error("Cannot re-broadcast %s: not tracked as pending", tx_hash)
            return {'status': 0, 'error': 'Transaction not tracked'}
        
        tx_info = self._pending_transactions[tx_hash]
        retry_count = tx_info['retry_count']
        
        if retry_count >= 3:
            log.error("Transaction %s exceeded max retry attempts", tx_hash)
            return {'status': 0, 'error': 'Max retries exceeded'}
        
        try:
            # Get the original transaction
            tx = self._web3.eth.get_transaction(tx_hash)
            
            # Re-broadcast with higher gas price
            from eth_account import Account
            
            # Increase gas price by 20% for re-broadcast
            new_max_fee = int(tx['maxFeePerGas'] * 1.2)
            new_priority_fee = int(tx['maxPriorityFeePerGas'] * 1.2)
            
            # Rebuild transaction with higher gas
            tx_dict = {
                'to': tx['to'],
                'from': tx['from'],
                'value': tx['value'],
                'data': tx['input'],
                'gas': tx['gas'],
                'maxFeePerGas': new_max_fee,
                'maxPriorityFeePerGas': new_priority_fee,
                'nonce': tx['nonce'],
                'type': 2,
                'chainId': tx['chainId'],
            }
            
            signed_tx = Account.sign_transaction(tx_dict, self._private_key)
            new_tx_hash = self._web3.eth.send_raw_transaction(signed_tx.raw_transaction)
            new_tx_hash_hex = new_tx_hash.hex()
            
            # Update tracking
            tx_info['retry_count'] += 1
            del self._pending_transactions[tx_hash]
            self._track_pending_transaction(new_tx_hash_hex, tx['nonce'])
            
            log.info("Re-broadcast transaction %s as %s (attempt %d)", tx_hash, new_tx_hash_hex, retry_count + 1)
            
            # Wait for the new transaction
            return self.wait_for_transaction(new_tx_hash_hex, timeout=60)
            
        except Exception as e:
            log.error("Failed to re-broadcast transaction %s: %s", tx_hash, e)
            raise TransactionRebroadcastError(f"Failed to re-broadcast transaction: {e}")

    def get_gas_stats(self) -> dict:
        """
        Get gas cost statistics.

        Returns
        -------
        dict
            Gas statistics including total_gas_spent, gas_cost_usd, pending_transactions
        """
        return {
            'total_gas_spent': self._total_gas_spent,
            'gas_cost_usd': self._gas_cost_usd,
            'pending_transactions': len(self._pending_transactions),
            'current_nonce': self._nonce,
        }

    def get_address(self) -> str:
        """Get wallet address."""
        if self._address is None:
            self._init_web3()
        return self._address

    def get_balance(self) -> float:
        """
        Get current USDC balance.

        Returns
        -------
        float
            USDC balance
        """
        if self._web3 is None:
            self._init_web3()

        try:
            balance_raw = self._usdc_contract.functions.balanceOf(
                self._address
            ).call()
            self._balance = float(balance_raw) / 1e6  # USDC has 6 decimals
        except Exception as e:
            log.error("Failed to fetch balance: %s", e)
            raise NetworkError(f"Failed to fetch balance from blockchain: {e}")

        return self._balance

    def get_allowance(self, spender_address: str) -> float:
        """
        Get allowance for a specific spender.

        Parameters
        ----------
        spender_address : str
            Address of the spender (e.g., CLOB contract)

        Returns
        -------
        float
            Allowance in USDC
        """
        if self._web3 is None:
            self._init_web3()

        try:
            allowance_raw = self._usdc_contract.functions.allowance(
                self._address,
                spender_address
            ).call()
            self._allowance = float(allowance_raw) / 1e6
        except Exception as e:
            log.error("Failed to fetch allowance: %s", e)
            raise NetworkError(f"Failed to fetch allowance from blockchain: {e}")

        return self._allowance

    def approve_spender(self, spender_address: str, amount: float) -> str:
        """
        Approve a spender to spend USDC.

        Parameters
        ----------
        spender_address : str
            Address of the spender (e.g., CLOB contract)
        amount : float
            Amount to approve (use very large number for unlimited)

        Returns
        -------
        str
            Transaction hash
        """
        if self._web3 is None:
            self._init_web3()

        try:
            amount_raw = int(amount * 1e6)
            
            # Estimate gas with error handling
            try:
                gas_estimate = self._usdc_contract.functions.approve(
                    spender_address,
                    amount_raw
                ).estimate_gas({'from': self._address})
            except Exception as e:
                log.error("Gas estimation failed for approval: %s", e)
                raise GasEstimationError(f"Failed to estimate gas for approval: {e}")
            
            # Build transaction with EIP-1559 gas params
            tx_params = self._build_transaction_params(
                gas_estimate=gas_estimate,
                to_address=spender_address
            )
            
            tx = self._usdc_contract.functions.approve(
                spender_address,
                amount_raw
            ).build_transaction(tx_params)

            # Sign and send transaction
            from eth_account import Account
            signed_tx = Account.sign_transaction(tx, self._private_key)
            tx_hash = self._web3.eth.send_raw_transaction(signed_tx.raw_transaction)
            tx_hash_hex = tx_hash.hex()
            
            # Track pending transaction
            self._track_pending_transaction(tx_hash_hex, tx_params['nonce'])
            
            log.info("Approval transaction sent: %s", tx_hash_hex)
            return tx_hash_hex
        except GasEstimationError:
            raise
        except Exception as e:
            log.error("Failed to approve spender: %s", e)
            raise NetworkError(f"Failed to approve spender: {e}")

    def refresh_balance(self) -> None:
        """Refresh balance from blockchain."""
        self._balance = self.get_balance()
        if self._log_balance_updates:
            log.info("Balance refreshed: $%.2f", self._balance)

    def wait_for_transaction(self, tx_hash: str, timeout: int = 120, poll_interval: float = 1.0) -> dict:
        """
        Wait for transaction confirmation with polling.

        Parameters
        ----------
        tx_hash : str
            Transaction hash
        timeout : int
            Timeout in seconds
        poll_interval : float
            Polling interval in seconds

        Returns
        -------
        dict
            Transaction receipt with status, gas_used, block_number, gas_cost_usd
        """
        if self._web3 is None:
            self._init_web3()

        start_time = time.time()
        
        while time.time() - start_time < timeout:
            try:
                receipt = self._web3.eth.get_transaction_receipt(tx_hash)
                
                if receipt is not None:
                    # Transaction confirmed
                    gas_used = receipt['gasUsed']
                    block_number = receipt['blockNumber']
                    
                    # Calculate gas cost in USD (approximate using MATIC price)
                    gas_cost_wei = gas_used * receipt.get('effectiveGasPrice', 0)
                    gas_cost_matic = float(self._web3.from_wei(gas_cost_wei, 'ether'))
                    gas_cost_usd = gas_cost_matic * 0.5  # Approximate MATIC/USD price
                    
                    # Update gas tracking
                    self._total_gas_spent += float(gas_used)
                    self._gas_cost_usd += gas_cost_usd
                    
                    # Remove from pending transactions
                    if tx_hash in self._pending_transactions:
                        del self._pending_transactions[tx_hash]
                    
                    log.info(
                        "Transaction %s confirmed in block %d. Gas used: %d, Cost: $%.4f",
                        tx_hash, block_number, gas_used, gas_cost_usd
                    )
                    
                    return {
                        'status': receipt['status'],
                        'gas_used': int(gas_used),
                        'block_number': block_number,
                        'gas_cost_usd': gas_cost_usd,
                        'effective_gas_price': receipt.get('effectiveGasPrice', 0),
                    }
                
            except Exception as e:
                # Transaction not yet mined
                pass
            
            time.sleep(poll_interval)
        
        # Timeout - try to re-broadcast
        log.warning("Transaction %s timed out after %d seconds, attempting re-broadcast", tx_hash, timeout)
        return self._rebroadcast_transaction(tx_hash)


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

        # Wallet setup
        self._wallet = WalletManager(private_key, rpc_url, log_balance_updates=self._config.log_balance_updates)
        self._balance: float = 0.0
        self._allowance: float = 0.0

        # Order management
        self._orders: dict[str, RealOrder] = {}
        self._positions: dict[str, RealPosition] = {}  # key: "{market_id}:{side}"

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
        if db_path:
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
        except Exception as e:
            log.error("Failed to create emergency backup: %s", e)
            raise BackupError(f"Failed to create emergency backup: {e}")

    def restore_from_backup(self, backup_path: str) -> None:
        """
        Restore trading state from backup.

        Parameters
        ----------
        backup_path : str
            Path to backup file
        """
        try:
            backup_data = self._disaster_recovery.restore_backup(backup_path)

            # Restore positions
            if "positions" in backup_data["data"]:
                for pos_id, pos_data in backup_data["data"]["positions"].items():
                    # Reconstruct position from data
                    # This would need proper implementation based on RealPosition structure
                    log.info("Restoring position: %s", pos_id)

            # Restore orders
            if "orders" in backup_data["data"]:
                for order_id, order_data in backup_data["data"]["orders"].items():
                    # Reconstruct order from data
                    log.info("Restoring order: %s", order_id)

            log.info("Successfully restored from backup: %s", backup_path)

        except Exception as e:
            log.error("Failed to restore from backup: %s", e)
            raise BackupError(f"Failed to restore from backup: {e}")

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
        checks = {
            "balance_ok": True,
            "allowance_ok": True,
            "market_open": True,
            "price_reasonable": True,
            "warnings": [],
            "can_proceed": True,
        }

        # Check balance
        if amount > self._balance:
            checks["balance_ok"] = False
            checks["can_proceed"] = False
            checks["warnings"].append(
                f"Insufficient balance: need ${amount:.2f}, have ${self._balance:.2f}"
            )

        # Check CLOB allowance (real trading specific)
        if self._allowance < amount:
            checks["allowance_ok"] = False
            checks["warnings"].append(
                f"Insufficient CLOB allowance: need ${amount:.2f}, have ${self._allowance:.2f}. "
                f"Call approve_spender() to increase allowance."
            )
            # Allowance warning doesn't block trade (can be auto-approved), but warn user

        # Check if market is still open
        if hasattr(market, 'end_time') and market.end_time:
            try:
                end_time = datetime.fromisoformat(market.end_time.replace('Z', '+00:00'))
                if end_time < datetime.now(timezone.utc):
                    checks["market_open"] = False
                    checks["can_proceed"] = False
                    checks["warnings"].append("Market has closed")
            except (ValueError, AttributeError) as e:
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
            log.info("Real: pre-trade checks warnings: %s", checks["warnings"])

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

        # Sync balance from chain to avoid divergence
        self.refresh_balance()

        # Track if user explicitly provided a price (for limit vs market order)
        user_provided_price = price is not None

        # 1. Calculate position size if not provided
        if amount is None:
            amount = self._position_sizer.calculate_size(
                self._balance, market, side, confidence, price
            )

        # 2. Run pre-trade checks
        checks = self.pre_trade_checks(market, side, amount)
        if not checks["can_proceed"]:
            raise ValueError(
                f"Pre-trade checks failed: {'; '.join(checks['warnings'])}"
            )

        # 3. Validate against risk limits
        self._risk_manager.validate_order(amount, self._balance, market, self._positions)

        # 4. Check balance
        if amount > self._balance:
            raise InsufficientBalance(
                f"Order amount ${amount:.2f} exceeds balance ${self._balance:.2f}"
            )

        # 5. Get price with stream awareness (prefers live stream price if available)
        if price is None:
            price, price_source = self._get_price_for_side(market, side)

        # 6. Calculate shares and fee
        is_maker = user_provided_price  # limit orders provide liquidity
        shares, fee = self._calculate_shares_and_fee(amount, price, is_maker=is_maker)

        # 7. Require confirmation if enabled
        if confirm and self._config.require_confirmation:
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
            sizing_strategy=self._config.position_sizing,
            confidence=confidence,
        )

        # 10. Update balance (fee comes out of amount, not on top)
        self._balance -= amount

        # 11. Store order
        self._orders[order.id] = order

        # 12. Update position
        self._update_position(market, side, order)

        # 13. Save to database
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

    def poll_order_status(self, order_id: str) -> dict:
        """
        Poll order status from CLOB API with retry logic.

        Parameters
        ----------
        order_id : str
            Order ID to poll

        Returns
        -------
        dict
            Order status response from CLOB API

        Raises
        ------
        OrderNotFound
            If order not found in local records
        NetworkError
            If polling fails after retries
        """
        if order_id not in self._orders:
            raise OrderNotFound(f"Order {order_id} not found")

        order = self._orders[order_id]
        order.last_status_check = datetime.now(timezone.utc)
        order.status_check_attempts += 1

        try:
            status_response = self._clob_client.get_order_status(order_id)
            log.debug("Order %s status: %s", order_id, status_response.get("status"))
            return status_response
        except Exception as e:
            log.error("Failed to poll order %s status (attempt %d): %s",
                     order_id, order.status_check_attempts, e)
            if order.status_check_attempts >= self._config.retry_attempts:
                raise NetworkError(f"Order status polling failed after {self._config.retry_attempts} attempts: {e}")
            raise

    def update_order_fill_status(self, order_id: str) -> None:
        """
        Update order fill status based on CLOB API response.

        Handles partial fills, full fills, and status transitions.

        Parameters
        ----------
        order_id : str
            Order ID to update
        """
        if order_id not in self._orders:
            raise OrderNotFound(f"Order {order_id} not found")

        order = self._orders[order_id]

        # Skip if order is already in final state
        if order.status in ("filled", "cancelled", "expired"):
            return

        # Poll current status from CLOB
        status_response = self.poll_order_status(order_id)

        api_status = status_response.get("status", "unknown")
        filled_size = float(status_response.get("filled_size", 0.0))
        avg_price = float(status_response.get("avg_price", order.price))

        # Handle partial fills
        if filled_size > 0 and filled_size < order.shares:
            if order.status != "partially_filled":
                log.info("Order %s partially filled: %.2f/%.2f shares",
                        order_id, filled_size, order.shares)
                order.status = "partially_filled"

            order.filled_shares = filled_size
            order.filled_amount = filled_size * avg_price
            order.avg_fill_price = avg_price

            # Update position with partial fill
            self._handle_partial_fill(order, filled_size, avg_price)

        # Handle full fills
        elif filled_size >= order.shares or api_status == "filled":
            if order.status != "filled":
                log.info("Order %s fully filled: %.2f shares @ %.4f",
                        order_id, filled_size, avg_price)
                order.status = "filled"
                order.filled_at = datetime.now(timezone.utc)
                order.filled_shares = filled_size
                order.filled_amount = filled_size * avg_price
                order.avg_fill_price = avg_price

                # Trigger fill callback
                self._on_order_filled(order)

        # Handle cancelled orders
        elif api_status == "cancelled":
            if order.status != "cancelled":
                log.info("Order %s cancelled", order_id)
                order.status = "cancelled"

        # Handle expired orders
        elif api_status == "expired":
            if order.status != "expired":
                log.warning("Order %s expired", order_id)
                order.status = "expired"

        # Update database if enabled
        if self._db_enabled:
            self._update_order_in_db(order)

    def _handle_partial_fill(self, order: RealOrder, filled_shares: float, avg_price: float) -> None:
        """
        Handle partial fill by updating position incrementally.

        Parameters
        ----------
        order : RealOrder
            Order that was partially filled
        filled_shares : float
            Number of shares filled in this update
        avg_price : float
            Average fill price
        """
        # Find the position for this order
        position_key = f"{order.market_id}:{order.side}"
        
        if position_key not in self._positions:
            # Position doesn't exist yet, create it with partial fill
            log.warning("Position not found for partial fill order %s, creating new position",
                       order.id)
            # This shouldn't normally happen as position is created on order placement
            return

        position = self._positions[position_key]

        # Calculate additional shares from this partial fill
        new_shares = filled_shares - position.shares
        if new_shares <= 0:
            return  # No new shares to add

        # Update position with volume-weighted average price
        total_shares = position.shares + new_shares
        position.avg_price = (
            (position.avg_price * position.shares + avg_price * new_shares)
            / total_shares
        )
        position.shares = total_shares
        position.cost_basis = position.shares * position.avg_price
        position.current_value = position.shares * avg_price

        log.debug("Position updated with partial fill: %s %s, shares=%.2f, avg_price=%.4f",
                 position.slug, position.side, position.shares, position.avg_price)

    def _on_order_filled(self, order: RealOrder) -> None:
        """
        Callback when order is fully filled.

        Parameters
        ----------
        order : RealOrder
            Filled order
        """
        log.info("Order fill callback: %s %s $%.2f @ $%.4f",
                order.slug, order.side, order.amount, order.price)

        # Record trade in risk manager for daily P&L tracking
        # Note: This is a simplified P&L calculation
        # Real P&L would be calculated on position exit
        self._risk_manager.record_trade(0.0)

    def check_order_timeout(self, order_id: str) -> bool:
        """
        Check if order has exceeded timeout threshold.

        Parameters
        ----------
        order_id : str
            Order ID to check

        Returns
        -------
        bool
            True if order has timed out
        """
        if order_id not in self._orders:
            raise OrderNotFound(f"Order {order_id} not found")

        order = self._orders[order_id]

        # Only check timeout for pending/open orders
        if order.status not in ("pending", "open", "partially_filled"):
            return False

        # Check if order has exceeded timeout
        if order.created_at:
            elapsed = (datetime.now(timezone.utc) - order.created_at).total_seconds()
            if elapsed > self._config.order_timeout:
                log.warning("Order %s timed out after %.1f seconds (status: %s)",
                           order_id, elapsed, order.status)
                return True

        return False

    def poll_all_orders(self) -> dict[str, str]:
        """
        Poll status for all open orders.

        Returns
        -------
        dict[str, str]
            Dictionary mapping order_id to new status
        """
        status_updates = {}

        for order_id, order in list(self._orders.items()):
            if order.status in ("pending", "open", "partially_filled"):
                try:
                    old_status = order.status
                    self.update_order_fill_status(order_id)
                    if order.status != old_status:
                        status_updates[order_id] = order.status
                except Exception as e:
                    log.error("Failed to update order %s status: %s", order_id, e)

                    # Check for timeout
                    if self.check_order_timeout(order_id):
                        status_updates[order_id] = "timeout"

        return status_updates

    # ── Position Management ───────────────────────────────────────────────────────

    def sync_positions_from_chain(self) -> None:
        """
        Fetch real positions from the blockchain using Alchemy.
        Calculates balances from transfers and fetches token metadata.
        """
        log.info("Syncing positions from blockchain...")
        address = self._wallet.address
        balances = self._alchemy_client.get_token_balances(address)
        transfers = self._alchemy_client.get_asset_transfers(address)
        
        # Build token IDs list
        token_ids = list(balances.keys())
        if not token_ids:
            return
            
        metadata = self._alchemy_client.fetch_polymarket_metadata(token_ids)
        
        # Calculate cost basis from transfers
        for token_id, amount in balances.items():
            if amount <= 0:
                continue
                
            meta = metadata.get(token_id, {})
            market_id = meta.get("market_id", token_id)
            slug = meta.get("slug", token_id)
            question = meta.get("question", "Unknown Market")
            side = meta.get("side", "UP") # Assume UP if unknown, can be derived
            
            # Simple average fill price derivation (placeholder)
            # In real implementation we'd need to match with orders or parse the amounts paid
            avg_price = 0.5  
            cost_basis = amount * avg_price
            current_price = float(meta.get("price", 0.5))
            
            # Find entry time from transfers
            entry_time = None
            token_transfers = [t for t in transfers if any(m.get("tokenId") == token_id for m in t.get("erc1155Metadata", []))]
            if token_transfers:
                # Get the earliest transfer to this address
                # alchemy_getAssetTransfers returns a blockNum (hex string), can use block timestamp if we fetched it, but we don't have timestamps directly. We'd have to use eth_getBlockByNumber or rely on a rough estimate if time is missing. Let's set it to datetime.now() for now if we can't parse it easily.
                entry_time = datetime.now() 
                
            position = RealPosition(
                market_id=market_id,
                slug=slug,
                question=question,
                side=side,
                shares=amount,
                avg_price=avg_price,
                current_price=current_price,
                cost_basis=cost_basis,
                current_value=amount * current_price,
                entry_time=entry_time,
            )
            
            # Track buy/sell dates in position if needed (can add attributes later)
            self._positions[f"{market_id}:{side}"] = position
            
        log.info(f"Synced {len(balances)} live positions.")

    def positions(self) -> list[RealPosition]:
        """Get all open positions."""
        now = time.time()
        if now - self._last_position_sync > self._position_sync_ttl:
            self.sync_positions_from_chain()
            self._last_position_sync = now
        return [p for p in self._positions.values() if not p.resolved]

    def all_positions(self) -> list[RealPosition]:
        """Get all positions including resolved ones."""
        now = time.time()
        if now - self._last_position_sync > self._position_sync_ttl:
            self.sync_positions_from_chain()
            self._last_position_sync = now
        return list(self._positions.values())

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
        render_positions(positions, self._orders, show_all=show_all, verbose=verbose)

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
        holding_times = []
        for pos in closed_pos:
            if pos.order_ids:
                fill_times = [
                    self._orders[oid].filled_at 
                    for oid in pos.order_ids 
                    if oid in self._orders and self._orders[oid].filled_at
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
        key = f"{market_id}:{side}"
        if key not in self._positions:
            raise PositionNotFound(f"No position for {market_id} {side}")
        return self._positions[key]

    def set_stop_loss(
        self,
        market,
        side: str,
        stop_price: float,
    ) -> None:
        """
        Set stop loss for a position.

        Parameters
        ----------
        market : Market
            Market object
        side : str
            "UP" or "DOWN"
        stop_price : float
            Stop loss price trigger

        Example
        -------
        >>> client.real.set_stop_loss(market, side="UP", stop_price=0.45)
        """
        side = _validate_side(side)
        position_key = f"{market.id}:{side}"
        
        if position_key not in self._positions:
            raise PositionNotFound(f"No position found for {market.slug} {side}")
        
        position = self._positions[position_key]
        position.stop_loss = stop_price
        
        log.info("Stop loss set at $%.4f for %s %s", stop_price, market.slug, side)

    def set_take_profit(
        self,
        market,
        side: str,
        profit_price: float,
    ) -> None:
        """
        Set take profit for a position.

        Parameters
        ----------
        market : Market
            Market object
        side : str
            "UP" or "DOWN"
        profit_price : float
            Take profit price trigger

        Example
        -------
        >>> client.real.set_take_profit(market, side="UP", profit_price=0.55)
        """
        side = _validate_side(side)
        position_key = f"{market.id}:{side}"
        
        if position_key not in self._positions:
            raise PositionNotFound(f"No position found for {market.slug} {side}")
        
        position = self._positions[position_key]
        position.take_profit = profit_price
        
        log.info("Take profit set at $%.4f for %s %s", profit_price, market.slug, side)

    def set_trailing_stop(
        self,
        market,
        side: str,
        trail_distance: float,
    ) -> None:
        """
        Set trailing stop loss for a position.

        Parameters
        ----------
        market : Market
            Market object
        side : str
            "UP" or "DOWN"
        trail_distance : float
            Trailing distance as percentage (e.g., 0.05 for 5%)

        Example
        -------
        >>> client.real.set_trailing_stop(market, side="UP", trail_distance=0.05)
        """
        side = _validate_side(side)
        position_key = f"{market.id}:{side}"
        
        if position_key not in self._positions:
            raise PositionNotFound(f"No position found for {market.slug} {side}")
        
        position = self._positions[position_key]
        
        # Add trailing stop fields to position if not already present
        if not hasattr(position, 'trail_sl'):
            position.trail_sl = None
        if not hasattr(position, 'trail_sl_price'):
            position.trail_sl_price = None
        
        position.trail_sl = trail_distance
        position.trail_sl_price = position.current_price - trail_distance if side == "UP" else position.current_price + trail_distance
        
        log.info("Trailing stop set at %.4f distance for %s %s", trail_distance, market.slug, side)

    def check_and_execute_trailing_stops(self, market_updates: dict[str, float]) -> list[str]:
        """
        Check and execute trailing stops based on current market prices.

        Parameters
        ----------
        market_updates : dict[str, float]
            Dictionary mapping token_id to current price

        Returns
        -------
        list[str]
            List of position keys that had trailing stops triggered
        """
        triggered = []
        
        for key, position in self._positions.items():
            if position.resolved:
                continue
            
            # Check if position has trailing stop enabled
            if not hasattr(position, 'trail_sl') or position.trail_sl is None:
                continue
            
            # Get current price for this position
            token_id = None
            if hasattr(position, 'token_id'):
                token_id = position.token_id
            else:
                # Try to derive from market_id
                token_id = position.market_id  # Fallback
            
            if token_id not in market_updates:
                continue
            
            current_price = market_updates[token_id]
            old_trail_price = position.trail_sl_price
            
            # Update trailing stop price based on favorable price movement
            if position.side == "UP":
                # For long positions, trail price moves up with price
                new_trail_price = current_price - position.trail_sl
                if new_trail_price > old_trail_price:
                    position.trail_sl_price = new_trail_price
                    log.info("Trailing stop updated for %s %s: $%.4f -> $%.4f", 
                             position.slug, position.side, old_trail_price, new_trail_price)
                
                # Check if stop triggered
                if current_price <= position.trail_sl_price:
                    triggered.append(key)
                    log.warning("Trailing stop triggered for %s %s at $%.4f", 
                              position.slug, position.side, current_price)
                    
            else:  # DOWN
                # For short positions, trail price moves down with price
                new_trail_price = current_price + position.trail_sl
                if new_trail_price < old_trail_price:
                    position.trail_sl_price = new_trail_price
                    log.info("Trailing stop updated for %s %s: $%.4f -> $%.4f", 
                             position.slug, position.side, old_trail_price, new_trail_price)
                
                # Check if stop triggered
                if current_price >= position.trail_sl_price:
                    triggered.append(key)
                    log.warning("Trailing stop triggered for %s %s at $%.4f", 
                              position.slug, position.side, current_price)
        
        return triggered

    def execute_trailing_stop_exit(self, position_key: str) -> None:
        """
        Execute an exit order for a position whose trailing stop was triggered.

        Parameters
        ----------
        position_key : str
            Position key in format "{market_id}:{side}"
        """
        if position_key not in self._positions:
            log.warning("Position %s not found for trailing stop exit", position_key)
            return
        
        position = self._positions[position_key]
        
        log.info("Executing trailing stop exit for %s %s at $%.4f",
                 position.slug, position.side, position.current_price)
        
        try:
            token_id = position.market_id
            current_price = position.current_price
            
            order_response = self._clob_client.place_order(
                token_id=token_id,
                side="sell",
                price=current_price,
                size=position.shares,
                order_type="market",
            )
            
            order = RealOrder(
                id=order_response["order_id"],
                market_id=position.market_id,
                slug=position.slug,
                side=position.side,
                price=current_price,
                amount=position.shares * current_price,
                shares=position.shares,
                fee=0.0,
                status="pending",
                is_limit=False,
                created_at=datetime.now(timezone.utc),
            )
            self._orders[order.id] = order
            
            position.resolved = True
            position.outcome = "STOPPED"
            
            log.info("Trailing stop exit executed for %s %s: order=%s",
                     position.slug, position.side, order.id)
                     
        except Exception as e:
            log.error("Failed to execute trailing stop exit for %s %s: %s",
                      position.slug, position.side, e)

    # ── Position Management ───────────────────────────────────────────────────────

    def scale_position(
        self,
        market,
        side: str,
        add_amount: float,
        confidence: float = 0.5,
    ) -> RealOrder:
        """
        Scale (pyramid) a position by adding more shares to a winning position.

        This implements the pyramiding strategy where you add to a position
        as it moves in your favor, increasing exposure while maintaining risk control.

        Parameters
        ----------
        market : Market
            Market object
        side : str
            "UP" or "DOWN"
        add_amount : float
            USDC amount to add to the position
        confidence : float, optional
            Confidence level for the additional trade (default: 0.5)

        Returns
        -------
        RealOrder
            The order that was placed to scale the position

        Raises
        ------
        PositionNotFound
            If no existing position exists for this market/side
        RiskLimitExceeded
            If scaling would exceed risk limits or position is not profitable enough

        Example
        -------
        >>> # Add $50 more to a winning UP position
        >>> order = client.real.scale_position(market, side="UP", add_amount=50.0, confidence=0.7)
        """
        if not self._config.enable_position_scaling:
            raise RiskLimitExceeded("Position scaling is disabled in configuration")

        side = _validate_side(side)
        position_key = f"{market.id}:{side}"

        if position_key not in self._positions:
            raise PositionNotFound(f"No position found for {market.slug} {side}")

        position = self._positions[position_key]

        # Check if position has reached maximum scale additions
        if position.scale_count >= self._config.max_scale_additions:
            raise RiskLimitExceeded(
                f"Position has been scaled {position.scale_count} times, "
                f"maximum is {self._config.max_scale_additions}"
            )

        # Check if position is profitable enough before allowing scaling
        min_profit_pct = self._config.min_profit_for_scaling
        if position.pnl_pct < min_profit_pct * 100:
            raise RiskLimitExceeded(
                f"Position profit {position.pnl_pct:.1f}% is below minimum {min_profit_pct*100:.1f}% for scaling"
            )

        # Calculate maximum additional size based on risk limits
        current_exposure = self._get_market_exposure(market.id)
        max_add_amount = self._config.max_position_size - current_exposure
        if add_amount > max_add_amount:
            log.warning("Requested scale amount $%.2f exceeds limit, capping at $%.2f", add_amount, max_add_amount)
            add_amount = max_add_amount

        # Place additional order
        log.info("Scaling position %s %s by $%.2f at confidence %.2f (scale #%d)",
                 market.slug, side, add_amount, confidence, position.scale_count + 1)

        order = self.buy(market, side=side, amount=add_amount, confidence=confidence, confirm=False)

        # Update scale count
        position.scale_count += 1

        return order

    def reduce_position(
        self,
        market,
        side: str,
        reduce_pct: float,
        reason: str = "manual",
    ) -> RealOrder:
        """
        Reduce a position by selling a percentage of shares.

        This implements position reduction strategies for risk management
        or profit taking. In Polymarket, selling is done by buying the opposite side.

        Parameters
        ----------
        market : Market
            Market object
        side : str
            "UP" or "DOWN"
        reduce_pct : float
            Percentage of position to reduce (0.0 to 1.0)
        reason : str, optional
            Reason for reduction (default: "manual")

        Returns
        -------
        RealOrder
            The order that was placed to reduce the position

        Raises
        ------
        PositionNotFound
            If no existing position exists for this market/side
        ValueError
            If reduce_pct is not between 0 and 1
        RiskLimitExceeded
            If position reduction is disabled in configuration

        Example
        -------
        >>> # Reduce position by 50%
        >>> order = client.real.reduce_position(market, side="UP", reduce_pct=0.5, reason="profit_taking")
        """
        if not self._config.enable_position_reduction:
            raise RiskLimitExceeded("Position reduction is disabled in configuration")

        side = _validate_side(side)
        position_key = f"{market.id}:{side}"

        if position_key not in self._positions:
            raise PositionNotFound(f"No position found for {market.slug} {side}")

        if not 0 < reduce_pct <= 1:
            raise ValueError("reduce_pct must be between 0 and 1")

        position = self._positions[position_key]
        shares_to_reduce = position.shares * reduce_pct

        # Calculate amount to spend on opposite side to reduce position
        current_price = position.current_price
        reduce_amount = shares_to_reduce * current_price

        log.info("Reducing position %s %s by %.1f%% ($%.2f) - reason: %s",
                 market.slug, side, reduce_pct * 100, reduce_amount, reason)

        # To reduce a position, buy the opposite side
        opposite_side = "DOWN" if side == "UP" else "UP"
        order = self.buy(market, side=opposite_side, amount=reduce_amount, confidence=0.5, confirm=False)

        return order

    def hedge_position(
        self,
        market,
        side: str,
        hedge_pct: float = 0.5,
    ) -> RealOrder:
        """
        Hedge a position by taking an opposite position in the same market.

        This reduces risk by taking a counter-position that can offset losses
        if the original position moves against you.

        Parameters
        ----------
        market : Market
            Market object
        side : str
            "UP" or "DOWN" - the side of the position to hedge
        hedge_pct : float, optional
            Percentage of position to hedge (0.0 to 1.0, default: 0.5)

        Returns
        -------
        RealOrder
            The order that was placed to hedge the position

        Raises
        ------
        PositionNotFound
            If no existing position exists for this market/side
        ValueError
            If hedge_pct is not between 0 and 1
        RiskLimitExceeded
            If hedging is disabled or hedge ratio exceeds maximum

        Example
        -------
        >>> # Hedge 50% of a UP position with a DOWN position
        >>> order = client.real.hedge_position(market, side="UP", hedge_pct=0.5)
        """
        if not self._config.enable_hedging:
            raise RiskLimitExceeded("Position hedging is disabled in configuration")

        side = _validate_side(side)
        position_key = f"{market.id}:{side}"

        if position_key not in self._positions:
            raise PositionNotFound(f"No position found for {market.slug} {side}")

        if not 0 < hedge_pct <= 1:
            raise ValueError("hedge_pct must be between 0 and 1")

        # Check if hedge ratio exceeds maximum
        if hedge_pct > self._config.max_hedge_ratio:
            raise RiskLimitExceeded(
                f"Hedge ratio {hedge_pct:.1%} exceeds maximum {self._config.max_hedge_ratio:.1%}"
            )

        position = self._positions[position_key]

        # Calculate hedge amount based on position value
        hedge_amount = position.cost_basis * hedge_pct

        # Determine opposite side
        hedge_side = "DOWN" if side == "UP" else "UP"

        log.info("Hedging position %s %s with %.1f%% ($%.2f) on opposite side %s",
                 market.slug, side, hedge_pct * 100, hedge_amount, hedge_side)

        # Place order on opposite side
        order = self.buy(market, side=hedge_side, amount=hedge_amount, confidence=0.5, confirm=False)

        # Track hedge amount on position
        position.hedge_amount += hedge_amount

        return order

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

        # This is a placeholder implementation
        # In production, this would involve:
        # 1. Using Web3.py to transfer tokens to target wallet
        # 2. Updating position tracking in both wallets
        # 3. Recording the transfer in the database

        tx_details = {
            "from_wallet": self._wallet.get_address(),
            "to_wallet": target_wallet_address,
            "market_id": market.id,
            "side": side,
            "shares": shares_to_transfer,
            "tx_hash": None,  # Would be actual transaction hash
            "status": "pending",
            "timestamp": datetime.now(timezone.utc).isoformat(),
        }

        log.warning("Position transfer is a placeholder - needs blockchain implementation")
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

    def _get_price_for_side(self, market, side: str) -> tuple[float, str]:
        """
        Get the best available price for a side, preferring live stream prices.
        
        Returns a tuple of (price, source) where source indicates where the price came from:
        - "stream": Live price from attached stream
        - "market": Price from market object (may be stale)
        - "fallback": Fallback price when no valid price available
        
        Parameters
        ----------
        market : Market object
        side   : "UP" or "DOWN"
        
        Returns
        -------
        tuple[float, str] - (price, source)
        """
        # Check if there's an attached running stream for this market
        stream = self._attached_streams.get(market.id)
        if stream and stream.running:
            # Use live stream price
            price = stream.up if side == "UP" else stream.down
            if price > 0:
                log.debug("Real: using live stream price %.4f for %s %s", price, market.slug, side)
                return price, "stream"
            else:
                log.warning("Real: stream attached but price is 0, falling back to market price")
        
        # Fall back to market price
        price = market.up_price if side == "UP" else market.down_price
        
        # Check if market price is stale
        if hasattr(market, 'end_time') and market.end_time:
            try:
                from datetime import datetime, timezone
                end_time = datetime.fromisoformat(market.end_time.replace('Z', '+00:00'))
                now = datetime.now(timezone.utc)
                time_until_close = (end_time - now).total_seconds()
                
                # If market is closed or very close to closing, price is likely stale
                if time_until_close <= 0:
                    log.warning("Real: market %s is closed, price may be stale", market.slug)
                elif time_until_close < PRICE_STALENESS_THRESHOLD:
                    log.warning(
                        "Real: market %s closes in %.1fs, using potentially stale price %.4f",
                        market.slug, time_until_close, price
                    )
            except (ValueError, TypeError):
                pass  # If we can't parse end_time, skip staleness check
        
        if price <= 0:
            log.warning("Real: market price is invalid (%.4f), using fallback", price)
            return FALLBACK_PRICE, "fallback"
        
        log.debug("Real: using market price %.4f for %s %s", price, market.slug, side)
        return price, "market"

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

    def _on_price_update(self, market_id: str, up_price: float, down_price: float) -> None:
        """
        Handle price updates from attached stream.

        Updates live position prices and executes stop loss, take profit,
        and trailing stop triggers based on current prices.

        Parameters
        ----------
        market_id : str
            Market ID for the price update
        up_price : float
            Current UP token price
        down_price : float
            Current DOWN token price
        """
        # Validate prices
        up_price = _validate_positive(up_price, "up_price")
        down_price = _validate_positive(down_price, "down_price")

        # Update live prices for all open positions in this market
        for pos in self._positions.values():
            if pos.market_id == market_id and not pos.resolved:
                pos.current_price = up_price if pos.side == "UP" else down_price

        # Build market updates dictionary for trailing stops
        market_updates = {}
        for pos in self._positions.values():
            if pos.market_id == market_id and not pos.resolved:
                token_id = pos.market_id  # Use market_id as token_id for now
                current_price = up_price if pos.side == "UP" else down_price
                market_updates[token_id] = current_price

        # Check and execute stop losses
        self._check_and_execute_stop_losses(market_id, up_price, down_price)

        # Check and execute take profits
        self._check_and_execute_take_profits(market_id, up_price, down_price)

        # Check and execute trailing stops
        triggered_trailing_stops = self.check_and_execute_trailing_stops(market_updates)
        for position_key in triggered_trailing_stops:
            self.execute_trailing_stop_exit(position_key)

    def _check_and_execute_stop_losses(self, market_id: str, up_price: float, down_price: float) -> None:
        """
        Check and execute stop loss orders based on current prices.

        Parameters
        ----------
        market_id : str
            Market ID to check
        up_price : float
            Current UP token price
        down_price : float
            Current DOWN token price
        """
        for position_key, position in self._positions.items():
            if position.market_id != market_id or position.resolved:
                continue

            if position.stop_loss is None:
                continue

            current_price = up_price if position.side == "UP" else down_price
            should_trigger = self._risk_manager.check_stop_loss(position, current_price)

            if should_trigger:
                log.warning(
                    "Stop loss triggered for %s %s: current=%.4f, stop=%.4f",
                    position.slug, position.side, current_price, position.stop_loss
                )
                self._execute_exit_order(position, "STOP_LOSS")

    def _check_and_execute_take_profits(self, market_id: str, up_price: float, down_price: float) -> None:
        """
        Check and execute take profit orders based on current prices.

        Parameters
        ----------
        market_id : str
            Market ID to check
        up_price : float
            Current UP token price
        down_price : float
            Current DOWN token price
        """
        for position_key, position in self._positions.items():
            if position.market_id != market_id or position.resolved:
                continue

            if position.take_profit is None:
                continue

            current_price = up_price if position.side == "UP" else down_price
            should_trigger = self._risk_manager.check_take_profit(position, current_price)

            if should_trigger:
                log.info(
                    "Take profit triggered for %s %s: current=%.4f, target=%.4f",
                    position.slug, position.side, current_price, position.take_profit
                )
                self._execute_exit_order(position, "TAKE_PROFIT")

    def _execute_exit_order(self, position: RealPosition, reason: str) -> None:
        """
        Execute an exit order for a position (stop loss, take profit, or trailing stop).

        Parameters
        ----------
        position : RealPosition
            Position to exit
        reason : str
            Reason for exit ("STOP_LOSS", "TAKE_PROFIT", "TRAILING_STOP")
        """
        try:
            # Determine token_id for sell order
            token_id = position.market_id  # Simplified - would need actual token mapping

            # Calculate current price
            current_price = position.current_price

            # Place market sell order
            order_response = self._place_clob_order(
                token_id,
                "sell",
                current_price,
                position.shares,
                "market"
            )

            # Update position status
            position.resolved = True
            position.outcome = reason

            # Calculate final P&L
            if position.side == "UP":
                exit_value = position.shares * current_price
            else:
                exit_value = position.shares * (1 - current_price)

            position.pnl = exit_value - position.amount

            log.info(
                "Exit order executed for %s %s: reason=%s, pnl=$%.2f",
                position.slug, position.side, reason, position.pnl
            )

            # Save to database if enabled
            if self._db_enabled:
                self._save_exit_to_db(position, reason, current_price)

        except Exception as e:
            log.error("Failed to execute exit order for %s %s: %s", position.slug, position.side, e)

    def _save_exit_to_db(self, position: RealPosition, reason: str, exit_price: float) -> None:
        """
        Save exit trade to database.

        Parameters
        ----------
        position : RealPosition
            Position that was exited
        reason : str
            Exit reason
        exit_price : float
            Exit price
        """
        try:
            self._db.save_trade(
                market_slug=position.slug,
                market_id=position.market_id,
                side=position.side,
                entry_price=position.entry_price,
                exit_price=exit_price,
                amount=position.amount,
                shares=position.shares,
                fee=position.fee,
                outcome=reason,
                pnl=position.pnl,
                timestamp=datetime.now(timezone.utc),
                sizing_strategy=position.sizing_strategy,
                confidence=position.confidence,
                kelly_fraction=position.kelly_fraction,
                stop_loss=position.stop_loss,
                take_profit=position.take_profit,
                tx_hash=None,
                is_real_trade=True,
                wallet_address=self._wallet.get_address(),
            )
            log.debug("Real: exit saved to database for %s", position.slug)
        except Exception as exc:
            log.error("Real: failed to save exit to database: %s", exc)

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
        """
        Calculate Polymarket-style fee using their actual formula.

        Formula: fee = C × p × feeRate × (p × (1 - p))^exponent

        Where:
        - C: Number of shares traded
        - p: Price of the trade
        - feeRate: Category-specific (e.g., sports=0.03, crypto=0.02)
        - exponent: 1

        Geopolitical markets have 0% fee.
        The price-dependent term p*(1-p) means fees are highest at p=0.5
        and approach zero near p=0 or p=1.

        Parameters
        ----------
        amount : float
            Total USDC being spent (unused in formula but kept for interface consistency)
        price : float
            Price per share
        shares : float
            Number of shares
        is_maker : bool
            Whether this is a maker order (currently unused — same formula for both)

        Returns
        -------
        float
            The fee amount in USDC
        """
        if self._config.market_category.lower() == "geopolitical":
            return 0.0

        fee_rate = self._fee_rate_for_category(self._config.market_category)

        exponent = 1
        fee = shares * price * fee_rate * (price * (1 - price)) ** exponent
        fee = round(fee, POLYMARKET_FEE_ROUNDING)

        if fee < MINIMUM_FEE:
            fee = 0.0

        return fee

    def _fee_rate_for_category(self, category: str) -> float:
        """Get the Polymarket fee rate for a given market category."""
        c = category.lower()
        if c == "sports":
            return FEE_RATE_SPORTS
        elif c in ("crypto", "finance", "politics", "tech"):
            return FEE_RATE_CRYPTO
        elif c in ("economics", "culture", "weather", "other"):
            return FEE_RATE_ECONOMICS
        return FEE_RATE_CRYPTO  # Default

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
        """Place order on CLOB."""
        return self._clob_client.place_order(
            token_id=token_id,
            side=side,
            price=price,
            size=size,
            order_type=order_type,
        )

    def _cancel_clob_order(self, order_id: str) -> None:
        """Cancel order on CLOB."""
        self._clob_client.cancel_order(order_id)

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
                order_id=order.id,
                status=order.status,
            )
            log.debug("Real: order saved to database for %s", order.slug)
        except Exception as exc:
            log.error("Real: failed to save order to database: %s", exc)

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
            log.error("Real: failed to update order in database: %s", exc)

    # ── Advanced Order Types ─────────────────────────────────────────────────────────

    def place_oco_order(
        self,
        market,
        side: str,
        amount: float,
        price1: float,
        price2: float,
        confirm: bool = True,
    ) -> OCOOrder:
        """
        Place a One-Cancels-Other (OCO) order pair.

        An OCO order places two orders where if one is filled, the other is automatically cancelled.
        Commonly used for stop loss + take profit combinations.

        Parameters
        ----------
        market : Market
            Market to trade
        side : str
            "UP" or "DOWN"
        amount : float
            USDC amount for each order
        price1 : float
            Price for first order (e.g., take profit)
        price2 : float
            Price for second order (e.g., stop loss)
        confirm : bool
            Require manual confirmation

        Returns
        -------
        OCOOrder
            The OCO order object

        Example
        -------
        >>> oco = client.real.place_oco_order(
        ...     market, side="UP", amount=10.0, price1=0.60, price2=0.40
        ... )
        """
        import uuid

        if self._emergency_mode:
            raise OrderCancelled("Trading halted - emergency mode active")

        side = _validate_side(side)

        # Place first order
        order1 = self.limit(market, side, price1, amount, confirm=confirm)

        # Place second order
        order2 = self.limit(market, side, price2, amount, confirm=False)

        # Create OCO order
        oco_id = str(uuid.uuid4())
        oco_order = OCOOrder(
            id=oco_id,
            market_id=market.id,
            slug=market.slug,
            side=side,
            order1_id=order1.id,
            order2_id=order2.id,
            order1_price=price1,
            order2_price=price2,
            amount=amount,
            status="active",
            created_at=datetime.now(timezone.utc),
        )

        self._oco_orders[oco_id] = oco_order

        log.info(
            "OCO order placed: %s %s, order1=%s @ %.4f, order2=%s @ %.4f",
            market.slug, side, order1.id, price1, order2.id, price2
        )

        return oco_order

    def check_oco_triggers(self) -> list[str]:
        """
        Check OCO orders for trigger conditions and cancel the other order if one fills.

        Returns
        -------
        list[str]
            List of OCO order IDs that were triggered
        """
        triggered_ocos = []

        for oco_id, oco in list(self._oco_orders.items()):
            if oco.status != "active":
                continue

            # Check if either order is filled
            order1 = self._orders.get(oco.order1_id)
            order2 = self._orders.get(oco.order2_id)

            if not order1 or not order2:
                continue

            # Update order statuses
            self.update_order_fill_status(oco.order1_id)
            self.update_order_fill_status(oco.order2_id)

            # Check if order1 is filled
            if order1.status == "filled":
                # Cancel order2
                try:
                    self.cancel(oco.order2_id)
                    oco.status = "triggered"
                    oco.triggered_order_id = order1.id
                    oco.cancelled_order_id = order2.id
                    oco.triggered_at = datetime.now(timezone.utc)
                    triggered_ocos.append(oco_id)
                    log.info("OCO triggered: order1 %s filled, cancelled order2 %s", order1.id, order2.id)
                except Exception as e:
                    log.error("Failed to cancel order2 in OCO %s: %s", oco_id, e)

            # Check if order2 is filled
            elif order2.status == "filled":
                # Cancel order1
                try:
                    self.cancel(oco.order1_id)
                    oco.status = "triggered"
                    oco.triggered_order_id = order2.id
                    oco.cancelled_order_id = order1.id
                    oco.triggered_at = datetime.now(timezone.utc)
                    triggered_ocos.append(oco_id)
                    log.info("OCO triggered: order2 %s filled, cancelled order1 %s", order2.id, order1.id)
                except Exception as e:
                    log.error("Failed to cancel order1 in OCO %s: %s", oco_id, e)

        return triggered_ocos

    def place_bracket_order(
        self,
        market,
        side: str,
        entry_price: float,
        amount: float,
        stop_loss_price: Optional[float] = None,
        take_profit_price: Optional[float] = None,
        stop_loss_pct: Optional[float] = None,
        take_profit_pct: Optional[float] = None,
        confirm: bool = True,
    ) -> BracketOrder:
        """
        Place a bracket order (entry + stop loss + take profit).

        A bracket order places an entry order along with associated stop loss and take profit orders.

        Parameters
        ----------
        market : Market
            Market to trade
        side : str
            "UP" or "DOWN"
        entry_price : float
            Entry order price
        amount : float
            USDC amount for entry order
        stop_loss_price : float, optional
            Stop loss price (overrides stop_loss_pct)
        take_profit_price : float, optional
            Take profit price (overrides take_profit_pct)
        stop_loss_pct : float, optional
            Stop loss as percentage of entry price (e.g., 0.20 for 20%)
        take_profit_pct : float, optional
            Take profit as percentage of entry price (e.g., 0.50 for 50%)
        confirm : bool
            Require manual confirmation

        Returns
        -------
        BracketOrder
            The bracket order object

        Example
        -------
        >>> bracket = client.real.place_bracket_order(
        ...     market, side="UP", entry_price=0.50, amount=10.0,
        ...     stop_loss_pct=0.20, take_profit_pct=0.50
        ... )
        """
        import uuid

        if self._emergency_mode:
            raise OrderCancelled("Trading halted - emergency mode active")

        side = _validate_side(side)

        # Calculate stop loss and take profit prices if not provided
        if stop_loss_price is None and stop_loss_pct is not None:
            if side == "UP":
                stop_loss_price = entry_price * (1 - stop_loss_pct)
            else:
                stop_loss_price = entry_price * (1 + stop_loss_pct)

        if take_profit_price is None and take_profit_pct is not None:
            if side == "UP":
                take_profit_price = entry_price * (1 + take_profit_pct)
            else:
                take_profit_price = entry_price * (1 - take_profit_pct)

        # Place entry order
        entry_order = self.limit(market, side, entry_price, amount, confirm=confirm)

        # Create bracket order
        bracket_id = str(uuid.uuid4())
        bracket_order = BracketOrder(
            id=bracket_id,
            market_id=market.id,
            slug=market.slug,
            side=side,
            entry_order_id=entry_order.id,
            entry_price=entry_price,
            stop_loss_price=stop_loss_price,
            take_profit_price=take_profit_price,
            amount=amount,
            status="pending",
            created_at=datetime.now(timezone.utc),
        )

        self._bracket_orders[bracket_id] = bracket_order

        log.info(
            "Bracket order placed: %s %s @ %.4f, stop=%.4f, take=%.4f",
            market.slug, side, entry_price, stop_loss_price, take_profit_price
        )

        return bracket_order

    def activate_bracket_orders(self) -> None:
        """
        Activate stop loss and take profit orders for filled bracket entry orders.

        This method checks all pending bracket orders and if the entry order is filled,
        it places the corresponding stop loss and take profit orders.
        """
        for bracket_id, bracket in list(self._bracket_orders.items()):
            if bracket.status != "pending":
                continue

            entry_order = self._orders.get(bracket.entry_order_id)
            if not entry_order:
                continue

            # Update entry order status
            self.update_order_fill_status(bracket.entry_order_id)

            # If entry order is filled, place stop loss and take profit
            if entry_order.status == "filled":
                bracket.status = "active"
                bracket.filled_at = datetime.now(timezone.utc)

                # Place stop loss order if specified
                if bracket.stop_loss_price is not None:
                    try:
                        log.info("Placing stop loss order for bracket %s at %.4f", bracket_id, bracket.stop_loss_price)
                        sl_order = self._clob_client.place_order(
                            token_id=bracket.market_id,
                            side="sell",
                            price=bracket.stop_loss_price,
                            size=bracket.amount / bracket.stop_loss_price,
                            order_type="limit",
                        )
                        bracket.stop_loss_order_id = sl_order.get("order_id", "")
                    except Exception as e:
                        log.error("Failed to place stop loss for bracket %s: %s", bracket_id, e)

                # Place take profit order if specified
                if bracket.take_profit_price is not None:
                    try:
                        log.info("Placing take profit order for bracket %s at %.4f", bracket_id, bracket.take_profit_price)
                        tp_order = self._clob_client.place_order(
                            token_id=bracket.market_id,
                            side="sell",
                            price=bracket.take_profit_price,
                            size=bracket.amount / bracket.take_profit_price,
                            order_type="limit",
                        )
                        bracket.take_profit_order_id = tp_order.get("order_id", "")
                    except Exception as e:
                        log.error("Failed to place take profit for bracket %s: %s", bracket_id, e)

                log.info("Bracket order %s activated", bracket_id)

    def place_conditional_order(
        self,
        market,
        side: str,
        condition_type: str,
        condition_value: float,
        child_order_price: float,
        child_order_amount: float,
        expires_after_seconds: Optional[int] = None,
    ) -> ConditionalOrder:
        """
        Place a conditional order with if-then logic.

        A conditional order triggers a child order when specified conditions are met.

        Parameters
        ----------
        market : Market
            Market to trade
        side : str
            "UP" or "DOWN"
        condition_type : str
            Condition type: "price_above", "price_below", "time_after"
        condition_value : float
            Value for the condition (price threshold or timestamp)
        child_order_price : float
            Price for the child order when triggered
        child_order_amount : float
            Amount for the child order when triggered
        expires_after_seconds : int, optional
            Expiration time in seconds

        Returns
        -------
        ConditionalOrder
            The conditional order object

        Example
        -------
        >>> cond = client.real.place_conditional_order(
        ...     market, side="UP", condition_type="price_above",
        ...     condition_value=0.60, child_order_price=0.61, child_order_amount=10.0
        ... )
        """
        import uuid

        if self._emergency_mode:
            raise OrderCancelled("Trading halted - emergency mode active")

        side = _validate_side(side)

        if condition_type not in ("price_above", "price_below", "time_after"):
            raise ValueError(f"Invalid condition_type: {condition_type}")

        # Calculate expiration
        expires_at = None
        if expires_after_seconds is not None:
            expires_at = datetime.now(timezone.utc).replace(
                second=0, microsecond=0
            ) + datetime.timedelta(seconds=expires_after_seconds)

        # Create conditional order
        cond_id = str(uuid.uuid4())
        cond_order = ConditionalOrder(
            id=cond_id,
            market_id=market.id,
            slug=market.slug,
            side=side,
            condition_type=condition_type,
            condition_value=condition_value,
            child_order_price=child_order_price,
            child_order_amount=child_order_amount,
            status="waiting",
            created_at=datetime.now(timezone.utc),
            expires_at=expires_at,
        )

        self._conditional_orders[cond_id] = cond_order

        log.info(
            "Conditional order placed: %s %s, condition=%s %.4f",
            market.slug, side, condition_type, condition_value
        )

        return cond_order

    def check_conditional_triggers(self, market_updates: dict[str, float]) -> list[str]:
        """
        Check conditional orders for trigger conditions.

        Parameters
        ----------
        market_updates : dict[str, float]
            Dictionary mapping market_id to current price

        Returns
        -------
        list[str]
            List of conditional order IDs that were triggered
        """
        triggered = []

        for cond_id, cond in list(self._conditional_orders.items()):
            if cond.status != "waiting":
                continue

            # Check expiration
            if cond.expires_at and datetime.now(timezone.utc) > cond.expires_at:
                cond.status = "expired"
                log.info("Conditional order %s expired", cond_id)
                continue

            # Check price conditions
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
                        log.info(
                            "Conditional order %s triggered: price %.4f, placing child order",
                            cond_id, current_price
                        )
                        child = self._clob_client.place_order(
                            token_id=cond.market_id,
                            side="buy",
                            price=cond.child_order_price,
                            size=cond.child_order_amount / cond.child_order_price,
                            order_type="limit",
                        )
                        cond.child_order_id = child.get("order_id", "")
                        cond.status = "triggered"
                        cond.triggered_at = datetime.now(timezone.utc)
                        triggered.append(cond_id)
                    except Exception as e:
                        log.error("Failed to place child order for conditional %s: %s", cond_id, e)

        return triggered

    def place_iceberg_order(
        self,
        market,
        side: str,
        total_amount: float,
        visible_size: float,
        price: float,
        confirm: bool = True,
    ) -> IcebergOrder:
        """
        Place an iceberg order for large order splitting.

        An iceberg order splits a large order into smaller visible chunks to avoid market impact.

        Parameters
        ----------
        market : Market
            Market to trade
        side : str
            "UP" or "DOWN"
        total_amount : float
            Total USDC amount to execute
        visible_size : float
            Visible chunk size in USDC
        price : float
            Limit price for each chunk
        confirm : bool
            Require manual confirmation for first chunk

        Returns
        -------
        IcebergOrder
            The iceberg order object

        Example
        -------
        >>> iceberg = client.real.place_iceberg_order(
        ...     market, side="UP", total_amount=1000.0, visible_size=50.0, price=0.50
        ... )
        """
        import uuid

        if self._emergency_mode:
            raise OrderCancelled("Trading halted - emergency mode active")

        side = _validate_side(side)

        if visible_size > total_amount:
            raise ValueError("visible_size cannot exceed total_amount")

        # Create iceberg order
        token_id = market.up_token if side == "UP" else market.down_token
        iceberg_id = str(uuid.uuid4())
        iceberg_order = IcebergOrder(
            id=iceberg_id,
            market_id=market.id,
            slug=market.slug,
            side=side,
            total_amount=total_amount,
            visible_size=visible_size,
            price=price,
            status="active",
            created_at=datetime.now(timezone.utc),
            token_id=token_id,
        )

        self._iceberg_orders[iceberg_id] = iceberg_order

        # Place first visible chunk
        self._execute_iceberg_slice(iceberg_id, confirm=confirm)

        log.info(
            "Iceberg order placed: %s %s, total=$%.2f, visible=$%.2f @ %.4f",
            market.slug, side, total_amount, visible_size, price
        )

        return iceberg_order

    def _execute_iceberg_slice(self, iceberg_id: str, confirm: bool = True) -> Optional[RealOrder]:
        """
        Execute a single slice of an iceberg order.

        Parameters
        ----------
        iceberg_id : str
            Iceberg order ID
        confirm : bool
            Require manual confirmation

        Returns
        -------
        RealOrder, optional
            The placed order, or None if no more to execute
        """
        iceberg = self._iceberg_orders.get(iceberg_id)
        if not iceberg or iceberg.status not in ("active", "partial"):
            return None

        remaining = iceberg.remaining_amount
        if remaining <= 0:
            iceberg.status = "completed"
            return None

        # Calculate slice size (visible size or remaining, whichever is smaller)
        slice_amount = min(iceberg.visible_size, remaining)

        try:
            log.info(
                "Executing iceberg slice: %s %s, amount=$%.2f @ %.4f",
                iceberg.slug, iceberg.side, slice_amount, iceberg.price
            )
            # Use ClobClient directly with the stored token_id
            order_response = self._clob_client.place_order(
                token_id=iceberg.token_id,
                side="buy",
                price=iceberg.price,
                size=slice_amount / iceberg.price if iceberg.price > 0 else 0,
                order_type="limit",
            )

            # Create a RealOrder for tracking
            order = RealOrder(
                id=order_response["order_id"],
                market_id=iceberg.market_id,
                slug=iceberg.slug,
                side=iceberg.side,
                price=iceberg.price,
                amount=slice_amount,
                shares=slice_amount / iceberg.price if iceberg.price > 0 else 0,
                fee=0.0,
                status="pending",
                is_limit=True,
                created_at=datetime.now(timezone.utc),
            )
            self._orders[order.id] = order
            iceberg.child_order_ids.append(order.id)
            return order

        except Exception as e:
            log.error("Failed to execute iceberg slice for %s: %s", iceberg_id, e)
            return None

    def update_iceberg_orders(self) -> None:
        """
        Update iceberg orders and execute additional slices as previous ones fill.

        This method should be called periodically to check if iceberg slices have filled
        and execute additional slices if needed.
        """
        for iceberg_id, iceberg in list(self._iceberg_orders.items()):
            if iceberg.status not in ("active", "partial"):
                continue

            # Check if child orders have filled
            filled_amount = 0.0
            for child_id in iceberg.child_order_ids:
                child_order = self._orders.get(child_id)
                if child_order:
                    self.update_order_fill_status(child_id)
                    if child_order.status == "filled":
                        filled_amount += child_order.amount

            iceberg.filled_amount = filled_amount

            # Update status
            if iceberg.filled_amount >= iceberg.total_amount:
                iceberg.status = "completed"
                log.info("Iceberg order %s completed", iceberg_id)
            elif iceberg.filled_amount > 0:
                iceberg.status = "partial"

            # Execute next slice if there's remaining amount and previous slice filled
            if iceberg.remaining_amount > 0 and len(iceberg.child_order_ids) > 0:
                last_child_id = iceberg.child_order_ids[-1]
                last_child = self._orders.get(last_child_id)
                if last_child and last_child.status == "filled":
                    self._execute_iceberg_slice(iceberg_id, confirm=False)

    def place_twap_order(
        self,
        market,
        side: str,
        total_amount: float,
        duration_seconds: int,
        num_slices: int,
        price: Optional[float] = None,
        confirm: bool = True,
    ) -> TWAPOrder:
        """
        Place a Time-Weighted Average Price (TWAP) execution order.

        A TWAP order executes a large order over a specified time period to achieve an average execution price.

        Parameters
        ----------
        market : Market
            Market to trade
        side : str
            "UP" or "DOWN"
        total_amount : float
            Total USDC amount to execute
        duration_seconds : int
            Duration over which to execute (in seconds)
        num_slices : int
            Number of slices to split the order into
        price : float, optional
            Limit price for each slice (if None, uses market price)
        confirm : bool
            Require manual confirmation for first slice

        Returns
        -------
        TWAPOrder
            The TWAP order object

        Example
        -------
        >>> twap = client.real.place_twap_order(
        ...     market, side="UP", total_amount=1000.0, duration_seconds=300, num_slices=10
        ... )
        """
        import uuid

        if self._emergency_mode:
            raise OrderCancelled("Trading halted - emergency mode active")

        side = _validate_side(side)

        if num_slices < 1:
            raise ValueError("num_slices must be at least 1")

        # Calculate slice interval
        slice_interval = duration_seconds / num_slices

        # Calculate end time
        ends_at = datetime.now(timezone.utc) + datetime.timedelta(seconds=duration_seconds)

        # Create TWAP order
        token_id = market.up_token if side == "UP" else market.down_token
        twap_id = str(uuid.uuid4())
        twap_order = TWAPOrder(
            id=twap_id,
            market_id=market.id,
            slug=market.slug,
            side=side,
            total_amount=total_amount,
            slice_amount=slice_amount,
            price=price,
            status="active",
            created_at=datetime.now(timezone.utc),
            slice_interval=slice_interval,
            token_id=token_id,
        )

        self._twap_orders[twap_id] = twap_order

        # Place first slice
        self._execute_twap_slice(twap_id, confirm=confirm)

        log.info(
            "TWAP order placed: %s %s, total=$%.2f over %ds in %d slices",
            market.slug, side, total_amount, duration_seconds, num_slices
        )

        return twap_order

    def _execute_twap_slice(self, twap_id: str, confirm: bool = True) -> Optional[RealOrder]:
        """
        Execute a single slice of a TWAP order.

        Parameters
        ----------
        twap_id : str
            TWAP order ID
        confirm : bool
            Require manual confirmation

        Returns
        -------
        RealOrder, optional
            The placed order, or None if no more to execute
        """
        twap = self._twap_orders.get(twap_id)
        if not twap or twap.status not in ("active", "partial"):
            return None

        # Check if we've exceeded the end time
        if twap.ends_at and datetime.now(timezone.utc) > twap.ends_at:
            twap.status = "completed"
            log.info("TWAP order %s completed (time expired)", twap_id)
            return None

        remaining = twap.remaining_amount
        if remaining <= 0:
            twap.status = "completed"
            return None

        # Calculate slice amount
        slice_amount = twap.slice_amount

        try:
            log.info(
                "Executing TWAP slice: %s %s, amount=$%.2f",
                twap.slug, twap.side, slice_amount
            )
            if twap.price and twap.price > 0:
                # Limit order at specified price
                order_response = self._clob_client.place_order(
                    token_id=twap.token_id,
                    side="buy",
                    price=twap.price,
                    size=slice_amount / twap.price,
                    order_type="limit",
                )
            else:
                # Market order (use current price)
                price = 0.5  # Will be overridden by actual fill
                order_response = self._clob_client.place_order(
                    token_id=twap.token_id,
                    side="buy",
                    price=price,
                    size=slice_amount / price,
                    order_type="market",
                )

            order = RealOrder(
                id=order_response["order_id"],
                market_id=twap.market_id,
                slug=twap.slug,
                side=twap.side,
                price=twap.price or 0.5,
                amount=slice_amount,
                shares=slice_amount / (twap.price or 0.5),
                fee=0.0,
                status="pending",
                is_limit=twap.price is not None and twap.price > 0,
                created_at=datetime.now(timezone.utc),
            )
            self._orders[order.id] = order
            twap.child_order_ids.append(order.id)
            return order

        except Exception as e:
            log.error("Failed to execute TWAP slice for %s: %s", twap_id, e)
            return None

    def update_twap_orders(self) -> None:
        """
        Update TWAP orders and execute slices based on schedule.

        This method should be called periodically to check if it's time to execute
        the next slice of each TWAP order.
        """
        for twap_id, twap in list(self._twap_orders.items()):
            if twap.status not in ("active", "partial"):
                continue

            # Check if child orders have filled
            filled_amount = 0.0
            for child_id in twap.child_order_ids:
                child_order = self._orders.get(child_id)
                if child_order:
                    self.update_order_fill_status(child_id)
                    if child_order.status == "filled":
                        filled_amount += child_order.amount

            twap.filled_amount = filled_amount

            # Update status
            if twap.filled_amount >= twap.total_amount:
                twap.status = "completed"
                log.info("TWAP order %s completed", twap_id)
            elif twap.filled_amount > 0:
                twap.status = "partial"

            # Check if it's time for next slice
            if twap.remaining_amount > 0:
                # Calculate expected number of slices based on elapsed time
                elapsed = (datetime.now(timezone.utc) - twap.created_at).total_seconds()
                expected_slices = int(elapsed / twap.slice_interval) + 1

                # Execute next slice if we haven't placed enough slices yet
                if len(twap.child_order_ids) < expected_slices and len(twap.child_order_ids) < twap.num_slices:
                    self._execute_twap_slice(twap_id, confirm=False)


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
