"""
Paper trading engine — simulated orders, positions, and P&L.

All state is held in memory.  No real money, no signing, no API keys needed.
A 2% taker fee is applied on each fill to simulate real costs.

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
import random
import time
import uuid
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import TYPE_CHECKING, Optional

if TYPE_CHECKING:
    from ..report.engine import ReportEngine
    from ..database.database import TradeDatabase
    from .auto_redeem import AutoRedeemEngine, AutoRedeemConfig

from ..core import (
    InsufficientBalance,
    OrderNotFound,
    PositionNotFound,
    TAKER_FEE_RATE,
    FEE_RATE_SPORTS,
    FEE_RATE_CRYPTO,
    FEE_RATE_ECONOMICS,
    MAKER_REBATE_PCT,
    MINIMUM_FEE,
    SUMMARY_DIV_WIDTH,
    FALLBACK_PRICE,
    PRICE_ROUNDING,
    FEE_ROUNDING,
    POLYMARKET_FEE_ROUNDING,
    SHARE_ROUNDING,
    DISPLAY_ROUNDING_SHARES,
    DISPLAY_ROUNDING_PRICES,
    DISPLAY_ROUNDING_PNL,
    DISPLAY_ROUNDING_PNL_PCT,
)

log = logging.getLogger(__name__)


# ── Configuration ────────────────────────────────────────────────────────────────

@dataclass
class PaperConfig:
    """Configuration for paper trading realism options."""
    # Fee configuration
    fee_mode: str = "custom"  # "polymarket", "custom", or "zero"
    custom_fee_rate: float = 0.02  # Used when fee_mode="custom"
    market_category: str = "crypto"  # For polymarket mode: "crypto", "sports", "geopolitical", etc.
    maker_fee_rate: float = 0.0  # Separate maker fee (optional)
    
    # Fee rebate configuration
    enable_rebates: bool = True  # Enable fee rebate tracking
    rebate_tiers: dict = field(default_factory=lambda: {
        0: 0.00,    # $0 - $1000: 0% rebate
        1000: 0.10,  # $1000 - $5000: 10% rebate
        5000: 0.15,  # $5000 - $10000: 15% rebate
        10000: 0.20, # $10000 - $50000: 20% rebate
        50000: 0.25, # $50000+: 25% rebate
    })  # Volume-based rebate tiers (volume_threshold: rebate_rate)
    maker_rebate_pct: float = 0.25  # Additional rebate for maker orders (on top of tier)
    
    # Execution delay
    execution_delay_ms: int = 0  # Delay in milliseconds (0 = no delay)
    delay_randomness: float = 0.0  # Random variation as percentage (0-1)
    
    # Slippage
    slippage_pct: float = 0.0  # Slippage percentage (e.g., 0.05 for 5%)
    slippage_randomness: float = 0.0  # Random variation as percentage (0-1)
    max_slippage_no_fill: float = 0.10  # If price moves beyond this, order doesn't fill
    
    # Fill probability
    fill_probability: float = 1.0  # Default 100% fill
    
    # Condition check mode for limit orders
    check_mode: str | int = "continuous"  # "continuous", "once", or int for N times
    
    # Risk management settings
    enable_risk_management: bool = True  # Enable risk management checks
    max_daily_loss: float = 500.0  # Stop trading if daily loss exceeds this (USDC)
    max_trades_per_day: int = 100  # Maximum number of trades per day
    max_order_size: float = 1000.0  # Maximum USDC per order
    max_position_size: float = 2000.0  # Maximum position size per market (USDC)
    max_open_positions: int = 10  # Maximum concurrent positions (global)
    max_positions_per_market: int = 1  # Maximum concurrent positions per individual market (None = no limit)
    max_risk_per_trade: float = 0.02  # Maximum risk per trade as percentage of balance (2%)
    
    def __post_init__(self):
        """Validate configuration values."""
        if self.fee_mode not in ("polymarket", "custom", "zero"):
            raise ValueError(f"fee_mode must be 'polymarket', 'custom', or 'zero', got '{self.fee_mode}'")
        if self.custom_fee_rate < 0:
            raise ValueError(f"custom_fee_rate must be >= 0, got {self.custom_fee_rate}")
        if self.maker_fee_rate < 0:
            raise ValueError(f"maker_fee_rate must be >= 0, got {self.maker_fee_rate}")
        if self.execution_delay_ms < 0:
            raise ValueError(f"execution_delay_ms must be >= 0, got {self.execution_delay_ms}")
        if not 0 <= self.delay_randomness <= 1:
            raise ValueError(f"delay_randomness must be between 0 and 1, got {self.delay_randomness}")
        if self.slippage_pct < 0:
            raise ValueError(f"slippage_pct must be >= 0, got {self.slippage_pct}")
        if not 0 <= self.slippage_randomness <= 1:
            raise ValueError(f"slippage_randomness must be between 0 and 1, got {self.slippage_randomness}")
        if not 0 <= self.max_slippage_no_fill <= 1:
            raise ValueError(f"max_slippage_no_fill must be between 0 and 1, got {self.max_slippage_no_fill}")
        if not 0 <= self.fill_probability <= 1:
            raise ValueError(f"fill_probability must be between 0 and 1, got {self.fill_probability}")
        # Validate check_mode
        if isinstance(self.check_mode, str) and self.check_mode not in ("continuous", "once"):
            raise ValueError(f"check_mode must be 'continuous', 'once', or a positive integer, got '{self.check_mode}'")
        if isinstance(self.check_mode, int) and self.check_mode < 1:
            raise ValueError(f"check_mode as integer must be >= 1, got {self.check_mode}")
        # Validate rebate configuration
        if not 0 <= self.maker_rebate_pct <= 1:
            raise ValueError(f"maker_rebate_pct must be between 0 and 1, got {self.maker_rebate_pct}")
        # Validate rebate tiers are sorted and have valid values
        if self.rebate_tiers:
            thresholds = sorted(self.rebate_tiers.keys())
            rates = [self.rebate_tiers[t] for t in thresholds]
            if any(not 0 <= r <= 1 for r in rates):
                raise ValueError(f"Rebate rates must be between 0 and 1")
        # Validate risk management settings
        if self.max_daily_loss < 0:
            raise ValueError(f"max_daily_loss must be >= 0, got {self.max_daily_loss}")
        if self.max_trades_per_day < 0:
            raise ValueError(f"max_trades_per_day must be >= 0, got {self.max_trades_per_day}")
        if self.max_order_size < 0:
            raise ValueError(f"max_order_size must be >= 0, got {self.max_order_size}")
        if self.max_position_size < 0:
            raise ValueError(f"max_position_size must be >= 0, got {self.max_position_size}")
        if self.max_open_positions < 0:
            raise ValueError(f"max_open_positions must be >= 0, got {self.max_open_positions}")
        if self.max_positions_per_market < 0:
            raise ValueError(f"max_positions_per_market must be >= 0, got {self.max_positions_per_market}")
        if not 0 <= self.max_risk_per_trade <= 1:
            raise ValueError(f"max_risk_per_trade must be between 0 and 1, got {self.max_risk_per_trade}")


# ── Risk Manager ────────────────────────────────────────────────────────────────

class RiskManager:
    """Risk management for paper trading."""
    
    def __init__(self, config: PaperConfig, initial_balance: float):
        self.config = config
        self.daily_pnl: float = 0.0
        self.daily_trades: int = 0
        self.daily_start_balance: float = initial_balance
        self.daily_start_date: datetime = datetime.now(timezone.utc).date()
        
    def _check_day_reset(self) -> None:
        """Check if we've crossed into a new day and reset counters if so."""
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
        """Validate order against risk limits."""
        if not self.config.enable_risk_management:
            return
        
        self._check_day_reset()
        
        # Check max order size
        if amount > self.config.max_order_size:
            raise ValueError(
                f"Order amount ${amount:.2f} exceeds maximum ${self.config.max_order_size:.2f}"
            )
        
        # Check max position size
        current_exposure = self._get_market_exposure(market_id, positions)
        if current_exposure + amount > self.config.max_position_size:
            raise ValueError(
                f"Position would exceed maximum size ${self.config.max_position_size:.2f} "
                f"(current: ${current_exposure:.2f}, adding: ${amount:.2f})"
            )
        
        # Check max open positions (global)
        open_positions = [p for p in positions.values() if not p.resolved]
        if len(open_positions) >= self.config.max_open_positions:
            raise ValueError(
                f"Maximum open positions ({self.config.max_open_positions}) reached"
            )
        
        # Check max positions per market
        if self.config.max_positions_per_market > 0:
            market_positions = [p for p in positions.values() if not p.resolved and p.market_id == market_id]
            if len(market_positions) >= self.config.max_positions_per_market:
                raise ValueError(
                    f"Maximum positions per market ({self.config.max_positions_per_market}) reached for market {market_id}"
                )
        
        # Check daily loss limit
        if self.daily_pnl < -self.config.max_daily_loss:
            raise ValueError(
                f"Daily loss ${abs(self.daily_pnl):.2f} exceeds limit ${self.config.max_daily_loss:.2f}"
            )
        
        # Check max trades per day
        if self.daily_trades >= self.config.max_trades_per_day:
            raise ValueError(
                f"Maximum daily trades ({self.config.max_trades_per_day}) reached"
            )
        
        # Check max risk per trade
        max_risk = balance * self.config.max_risk_per_trade
        if amount > max_risk:
            raise ValueError(
                f"Order amount ${amount:.2f} exceeds max risk ${max_risk:.2f} "
                f"({self.config.max_risk_per_trade:.1%} of balance)"
            )
        
        # Increment trade count on order entry (not exit)
        self.daily_trades += 1
    
    def _get_market_exposure(self, market_id: str, positions: dict) -> float:
        """Get current exposure for a specific market."""
        exposure = 0.0
        for key, pos in positions.items():
            if pos.market_id == market_id and not pos.resolved:
                exposure += pos.cost_basis
        return exposure
    
    def record_trade(self, pnl: float) -> None:
        """Record a completed trade and update daily P&L."""
        self._check_day_reset()
        self.daily_pnl += pnl
        log.debug(
            "RiskManager: Trade recorded - daily_pnl=$%.2f",
            self.daily_pnl
        )
    
    def get_summary(self) -> dict:
        """Get current risk management summary."""
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
        """Manually reset daily limits (useful for testing)."""
        self.daily_pnl = 0.0
        self.daily_trades = 0
        self.daily_start_date = datetime.now(timezone.utc).date()
        log.info("RiskManager: Daily limits manually reset")
    
    def check_stop_loss(self, position: "PaperPosition", current_price: float) -> bool:
        """
        Check if stop loss should be triggered.
        
        Parameters
        ----------
        position : PaperPosition
            The position to check
        current_price : float
            Current market price
        
        Returns
        -------
        bool
            True if stop loss should be triggered
        """
        if position.stop_loss is None:
            return False
        
        if position.side == "UP":
            return current_price <= position.stop_loss
        else:
            return current_price >= position.stop_loss
    
    def check_take_profit(self, position: "PaperPosition", current_price: float) -> bool:
        """
        Check if take profit should be triggered.
        
        Parameters
        ----------
        position : PaperPosition
            The position to check
        current_price : float
            Current market price
        
        Returns
        -------
        bool
            True if take profit should be triggered
        """
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
        
        Parameters
        ----------
        balance : float
            Current account balance
        entry_price : float
            Entry price for the trade
        stop_loss : float
            Stop loss price
        side : str
            "UP" or "DOWN"
        
        Returns
        -------
        float
            Recommended position size in USDC
        """
        risk_amount = balance * self.config.max_risk_per_trade
        price_diff = abs(entry_price - stop_loss)
        
        if price_diff == 0:
            # If no price difference, can't calculate based on risk
            # Return the risk amount as a safe default
            return min(risk_amount, balance)
        
        position_size = risk_amount / (price_diff / entry_price)
        return min(position_size, balance)


# ── Dataclasses ────────────────────────────────────────────────────────────────

@dataclass
class PaperOrder:
    """A single simulated order (market or limit)."""

    id:        str
    market_id: str
    slug:      str
    side:      str           # "UP" | "DOWN"
    price:     float         # fill price, or limit threshold if pending
    amount:    float         # USDC spent (or reserved)
    shares:    float         # shares received after fee
    fee:       float         # USDC fee paid
    status:    str           # "open" | "filled" | "cancelled"
    is_limit:  bool
    filled_at: Optional[datetime] = None
    
    # Fee rebate tracking
    fee_type: str = "taker"  # "taker" or "maker"
    rebate_amount: float = 0.0  # USDC rebate earned on this order
    rebate_rate: float = 0.0  # Rebate rate applied (as decimal)
    
    # Advanced order management
    stop_loss: Optional[float] = None           # SL price trigger
    take_profit: Optional[float] = None         # TP price trigger
    trail_sl: Optional[float] = None            # Trailing SL distance
    trail_tp: Optional[float] = None            # Trailing TP distance
    trail_sl_price: Optional[float] = None       # Current trailing SL price
    trail_tp_price: Optional[float] = None       # Current trailing TP price
    oco_order_id: Optional[str] = None           # OCO linked order ID
    tp_sl_triggered_by: Optional[str] = None     # Which order triggered this: "tp" | "sl" | None
    
    # Time window for order execution
    time_window_start: Optional[datetime] = None  # Start of time window for execution
    time_window_end: Optional[datetime] = None    # End of time window for execution
    
    # Condition check tracking
    check_count: int = 0  # Number of times this order has been checked

    def dump(self) -> dict:
        return {
            "id":        self.id,
            "market":    self.slug,
            "side":      self.side,
            "price":     self.price,
            "amount":    self.amount,
            "shares":    self.shares,
            "fee":       self.fee,
            "status":    self.status,
            "is_limit":  self.is_limit,
            "filled_at": self.filled_at.isoformat() if self.filled_at else None,
            "fee_type":  self.fee_type,
            "rebate_amount": self.rebate_amount,
            "rebate_rate": self.rebate_rate,
            "stop_loss": self.stop_loss,
            "take_profit": self.take_profit,
            "trail_sl": self.trail_sl,
            "trail_tp": self.trail_tp,
            "trail_sl_price": self.trail_sl_price,
            "trail_tp_price": self.trail_tp_price,
            "oco_order_id": self.oco_order_id,
            "tp_sl_triggered_by": self.tp_sl_triggered_by,
            "time_window_start": self.time_window_start.isoformat() if self.time_window_start else None,
            "time_window_end": self.time_window_end.isoformat() if self.time_window_end else None,
            "check_count": self.check_count,
        }


@dataclass
class PaperPosition:
    """
    An aggregated position for one side of one market.

    Multiple fills on the same market+side are merged into a single position
    using a volume-weighted average price.
    """

    market_id:     str
    slug:          str
    question:      str
    side:          str           # "UP" | "DOWN"
    shares:        float
    avg_price:     float
    current_price: float         # updated live from the attached stream
    resolved:      bool                = False
    outcome:       Optional[str]       = None   # "WON" | "LOST"
    order_ids:     list[str]           = field(default_factory=list)
    
    # Risk management
    stop_loss:     Optional[float]      = None
    take_profit:   Optional[float]      = None

    # ── Computed ───────────────────────────────────────────────────────────────

    @property
    def cost_basis(self) -> float:
        return round(self.shares * self.avg_price, PRICE_ROUNDING)

    @property
    def current_value(self) -> float:
        """Shares × 1.0 if won, 0.0 if lost, else shares × live price."""
        if self.resolved:
            return round(self.shares, PRICE_ROUNDING) if self.outcome == "WON" else 0.0
        return round(self.shares * self.current_price, PRICE_ROUNDING)

    @property
    def pnl(self) -> float:
        return round(self.current_value - self.cost_basis, PRICE_ROUNDING)

    @property
    def pnl_pct(self) -> float:
        if self.cost_basis == 0:
            return 0.0
        return round((self.pnl / self.cost_basis) * 100, DISPLAY_ROUNDING_PNL_PCT)

    def dump(self) -> dict:
        return {
            "market":        self.slug,
            "question":      self.question,
            "side":          self.side,
            "shares":        round(self.shares,        DISPLAY_ROUNDING_SHARES),
            "avg_price":     round(self.avg_price,     DISPLAY_ROUNDING_PRICES),
            "current_price": round(self.current_price, DISPLAY_ROUNDING_PRICES),
            "cost_basis":    round(self.cost_basis,    DISPLAY_ROUNDING_PRICES),
            "current_value": round(self.current_value, DISPLAY_ROUNDING_PRICES),
            "pnl":           round(self.pnl,           DISPLAY_ROUNDING_PNL),
            "pnl_pct":       round(self.pnl_pct,       DISPLAY_ROUNDING_PNL_PCT),
            "resolved":      self.resolved,
            "outcome":       self.outcome,
            "stop_loss":     self.stop_loss,
            "take_profit":   self.take_profit,
        }


# ── Engine ─────────────────────────────────────────────────────────────────────

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
        Path to SQLite database file for trade persistence. If provided,
        trades will be automatically saved when positions are resolved.
    """

    def __init__(self, balance: float = 100.0, config: Optional[PaperConfig] = None, db_path: Optional[str] = None):
        self._config:    PaperConfig                  = config or PaperConfig()
        # Lazy-initialised in the report property to avoid circular imports
        self._report: Optional["ReportEngine"] = None
        # Optional database for trade persistence
        self._db: Optional["TradeDatabase"] = None
        self._db_enabled: bool = False
        if db_path:
            self.enable_database(db_path)
        
        # Multi-wallet support
        self._wallet_manager: Optional["WalletManager"] = None
        self._use_multi_wallet: bool = False
        
        # Initialize single-wallet mode for backward compatibility
        self._balance:   float                       = float(balance)
        self._orders:    dict[str, PaperOrder]       = {}
        self._positions: dict[str, PaperPosition]    = {}   # key: "{market_id}:{side}"
        # Risk management
        self._risk_manager: RiskManager = RiskManager(self._config, self._balance)
        # Fee rebate tracking
        self._total_fees_paid: float = 0.0
        self._total_rebates_earned: float = 0.0
        self._total_volume: float = 0.0  # Total trading volume
        self._taker_fees: float = 0.0
        self._maker_fees: float = 0.0
        self._taker_rebates: float = 0.0
        self._maker_rebates: float = 0.0
        
        # Auto-redeem engine (lazy-initialized)
        self._auto_redeem: Optional[AutoRedeemEngine] = None
        
        # Portfolio analytics engine (lazy-initialized)
        self._portfolio_analytics: Optional["PortfolioAnalytics"] = None
        
        # Reporting engine (lazy-initialized)
        self._reporting: Optional["ReportingEngine"] = None
        
        # Stream tracking for price-aware trading
        self._attached_streams: dict[str, "Stream"] = {}  # market_id -> Stream

    @property
    def report(self) -> "ReportEngine":
        """Analytics and reporting engine. Access via ``client.paper.report``."""
        if self._report is None:
            from ..report.engine import ReportEngine
            self._report = ReportEngine(self)
        return self._report

    @property
    def auto_redeem(self) -> "AutoRedeemEngine":
        """Auto-redeem engine for automatic position redemption. Access via ``client.paper.auto_redeem``."""
        if self._auto_redeem is None:
            from .auto_redeem import AutoRedeemEngine, AutoRedeemConfig
            self._auto_redeem = AutoRedeemEngine(self, AutoRedeemConfig())
        return self._auto_redeem

    @property
    def portfolio_analytics(self) -> "PortfolioAnalytics":
        """Portfolio analytics engine. Access via ``client.paper.portfolio_analytics``."""
        if self._portfolio_analytics is None:
            from ..report.portfolio_analytics import PortfolioAnalytics
            self._portfolio_analytics = PortfolioAnalytics(self)
        return self._portfolio_analytics

    @property
    def reporting(self) -> "ReportingEngine":
        """Comprehensive reporting engine. Access via ``client.paper.reporting``."""
        if self._reporting is None:
            from ..report.reporting import ReportingEngine
            self._reporting = ReportingEngine(self)
        return self._reporting

    def set_auto_redeem_config(self, config: "AutoRedeemConfig") -> None:
        """Set a custom auto-redeem configuration."""
        from .auto_redeem import AutoRedeemEngine
        self._auto_redeem = AutoRedeemEngine(self, config)

    # ── Multi-Wallet Support ─────────────────────────────────────────────────────

    def enable_multi_wallet(self, wallet_manager: "WalletManager") -> None:
        """
        Enable multi-wallet mode with a custom wallet manager.
        
        Parameters
        ----------
        wallet_manager : WalletManager
            Pre-configured wallet manager with multiple wallets.
        
        Example
        -------
        >>> from polyalpha.trading.wallet import WalletManager, PaperWallet
        >>> wm = WalletManager()
        >>> wm.add_wallet(PaperWallet("wallet1", balance=100.0))
        >>> wm.add_wallet(PaperWallet("wallet2", balance=200.0))
        >>> client.paper.enable_multi_wallet(wm)
        """
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
    def wallets(self) -> Optional["WalletManager"]:
        """
        Get the wallet manager if multi-wallet mode is enabled.
        
        Returns None if in single-wallet mode.
        
        Example
        -------
        >>> if client.paper.wallets:
        ...     summary = client.paper.wallets.get_aggregated_summary()
        ...     print(f"Total balance: ${summary['total_balance']}")
        """
        return self._wallet_manager

    @property
    def is_multi_wallet(self) -> bool:
        """Check if multi-wallet mode is enabled."""
        return self._use_multi_wallet

    def _get_active_wallet(self) -> "PaperWallet":
        """
        Get the active wallet for trading operations.
        
        In single-wallet mode, returns a virtual wallet wrapping the engine's state.
        In multi-wallet mode, uses the wallet manager's selection strategy.
        """
        if not self._use_multi_wallet:
            # Return a virtual wallet for backward compatibility
            from .wallet import PaperWallet
            # Create a virtual wallet that wraps the engine's state
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

    def set_balance(self, amount: float) -> None:
        """Reset the paper balance to *amount*."""
        if amount < 0:
            raise ValueError("Balance cannot be negative")
        self._balance = float(amount)
        log.info("Paper: balance set to $%.2f", amount)

    def set_config(self, config: PaperConfig) -> None:
        """Update the paper trading configuration."""
        self._config = config
        log.info("Paper: configuration updated")

    # ── Risk Management ───────────────────────────────────────────────────────────

    def get_risk_summary(self) -> dict:
        """
        Get current risk management summary.

        Returns
        -------
        dict
            Dictionary with daily P&L, trade count, and remaining limits.

        Example
        -------
        >>> summary = client.paper.get_risk_summary()
        >>> print(f"Daily P&L: ${summary['daily_pnl']:.2f}")
        >>> print(f"Trades today: {summary['daily_trades']}")
        >>> print(f"Remaining loss limit: ${summary['remaining_loss_limit']:.2f}")
        """
        return self._risk_manager.get_summary()

    def reset_daily_limits(self) -> None:
        """
        Manually reset daily risk limits.

        This is useful for testing or when you want to start fresh without
        waiting for the calendar day to change.

        Example
        -------
        >>> client.paper.reset_daily_limits()
        """
        self._risk_manager.reset_daily_limits()

    # ── Pre-Trade Checks ─────────────────────────────────────────────────────────

    def pre_trade_checks(self, market, side: str, amount: float) -> dict:
        """
        Run comprehensive pre-trade checks before order execution.

        This method validates various conditions before allowing a trade to proceed,
        helping prevent errors and risky trades.

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
            - market_open: bool - Whether market is still open
            - price_reasonable: bool - Whether price is within reasonable range
            - warnings: list[str] - List of warning messages
            - can_proceed: bool - Whether trade can proceed (all critical checks pass)

        Example
        -------
        >>> checks = client.paper.pre_trade_checks(market, side="UP", amount=10.0)
        >>> if not checks["can_proceed"]:
        ...     for warning in checks["warnings"]:
        ...         print(f"Warning: {warning}")
        ... else:
        ...     order = client.paper.buy(market, side="UP", amount=10.0)
        """
        checks = {
            "balance_ok": True,
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

        # Check if market is still open
        if hasattr(market, 'end_time') and market.end_time:
            try:
                end_time = datetime.fromisoformat(market.end_time.replace('Z', '+00:00'))
                if end_time < datetime.now(timezone.utc):
                    checks["market_open"] = False
                    checks["can_proceed"] = False
                    checks["warnings"].append("Market has closed")
            except (ValueError, AttributeError) as e:
                log.debug("Paper: could not parse market end_time: %s", e)

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
            log.info("Paper: pre-trade checks warnings: %s", checks["warnings"])

        return checks

    # ── Database Integration ─────────────────────────────────────────────────────

    def enable_database(self, db_path: str) -> None:
        """
        Enable database persistence for trades.
        
        Parameters
        ----------
        db_path : str
            Path to SQLite database file. Will be created if it doesn't exist.
        
        Example
        -------
        >>> client.paper.enable_database("trades.db")
        """
        if not db_path or not isinstance(db_path, str):
            raise ValueError("db_path must be a non-empty string")
        
        try:
            from ..database.database import TradeDatabase
            self._db = TradeDatabase(db_path)
            self._db_enabled = True
            log.info("Paper: database enabled at %s", db_path)
        except ImportError:
            log.error("Paper: database module not available. Install required dependencies.")
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
    def database(self) -> Optional["TradeDatabase"]:
        """Get the database instance if enabled, None otherwise."""
        return self._db if self._db_enabled else None

    def _save_trade_to_db(self, position: PaperPosition) -> None:
        """
        Save a resolved position as a trade to the database.
        
        This is called automatically when a position is resolved if database is enabled.
        """
        if not self._db_enabled or self._db is None:
            return

        try:
            # Calculate total amount, shares, and fee from orders
            total_amount = 0.0
            total_shares = position.shares
            total_fee = 0.0
            entry_price = position.avg_price

            for order_id in position.order_ids:
                order = self._orders.get(order_id)
                if order:
                    total_amount += order.amount
                    total_fee += order.fee
                    if order.status == "filled":
                        entry_price = order.price

            # Save to database
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

    # ── Fee Calculation ───────────────────────────────────────────────────────────

    def _calculate_fee(self, amount: float, price: float, shares: float, is_maker: bool = False) -> tuple[float, float, float, str]:
        """
        Calculate fee based on configuration mode.
        
        Parameters
        ----------
        amount : float
            USDC amount being traded
        price : float
            Price per share
        shares : float
            Number of shares
        is_maker : bool
            Whether this is a maker order (limit order that provides liquidity)
        
        Returns
        -------
        tuple[float, float, float, str]
            (fee_amount, rebate_amount, rebate_rate, fee_type)
        """
        if self._config.fee_mode == "zero":
            return 0.0, 0.0, 0.0, "taker"
        elif self._config.fee_mode == "custom":
            fee_rate = self._config.maker_fee_rate if is_maker else self._config.custom_fee_rate
            fee = round(amount * fee_rate, FEE_ROUNDING)
            fee_type = "maker" if is_maker else "taker"
            rebate_amount, rebate_rate = self._calculate_rebate(fee, fee_type)
            return fee, rebate_amount, rebate_rate, fee_type
        elif self._config.fee_mode == "polymarket":
            return self._polymarket_fee(amount, price, shares, is_maker)
        else:
            # Fallback to default taker fee
            fee = round(amount * TAKER_FEE_RATE, FEE_ROUNDING)
            rebate_amount, rebate_rate = self._calculate_rebate(fee, "taker")
            return fee, rebate_amount, rebate_rate, "taker"

    def _polymarket_fee(self, amount: float, price: float, shares: float, is_maker: bool = False) -> tuple[float, float, float, str]:
        """
        Calculate Polymarket-style fee based on their formula.
        
        Formula: fee = C × p × feeRate × (p × (1 − p))^exponent
        
        Where:
        - C: Number of shares traded
        - p: Price of the trade
        - feeRate: Category-specific (e.g., sports=0.03, crypto=0.02)
        - exponent: 1
        
        Geopolitical markets have 0% fee.
        
        Returns
        -------
        tuple[float, float, float, str]
            (fee_amount, rebate_amount, rebate_rate, fee_type)
        """
        # Geopolitical markets are fee-free
        if self._config.market_category.lower() == "geopolitical":
            return 0.0, 0.0, 0.0, "taker"
        
        # Determine fee rate based on market category
        category = self._config.market_category.lower()
        if category == "sports":
            fee_rate = FEE_RATE_SPORTS
        elif category in ("crypto", "finance", "politics", "tech"):
            fee_rate = FEE_RATE_CRYPTO
        elif category in ("economics", "culture", "weather", "other"):
            fee_rate = FEE_RATE_ECONOMICS
        else:
            fee_rate = FEE_RATE_CRYPTO  # Default to crypto rate
        
        # Apply Polymarket formula
        exponent = 1
        fee = shares * price * fee_rate * (price * (1 - price)) ** exponent
        
        # Round to 4 decimal places (Polymarket precision)
        fee = round(fee, POLYMARKET_FEE_ROUNDING)
        
        # Minimum fee is 0.0001, anything smaller rounds to zero
        if fee < MINIMUM_FEE:
            fee = 0.0
        
        fee_type = "maker" if is_maker else "taker"
        
        # For maker orders, apply maker fee rate (typically lower)
        if is_maker:
            fee = fee * MAKER_REBATE_PCT  # 25% maker rebate
        
        # Calculate additional rebate if enabled
        rebate_amount, rebate_rate = self._calculate_rebate(fee, fee_type)
        
        return fee, rebate_amount, rebate_rate, fee_type

    def _calculate_rebate(self, fee: float, fee_type: str) -> tuple[float, float]:
        """
        Calculate rebate amount based on fee and rebate configuration.
        
        Parameters
        ----------
        fee : float
            Fee amount before rebate
        fee_type : str
            "taker" or "maker"
        
        Returns
        -------
        tuple[float, float]
            (rebate_amount, rebate_rate)
        """
        if not self._config.enable_rebates or fee == 0:
            return 0.0, 0.0
        
        # Start with volume-based rebate
        rebate_rate = self._get_volume_rebate_rate()
        
        # Add additional maker rebate if applicable
        if fee_type == "maker":
            rebate_rate += self._config.maker_rebate_pct
        
        # Cap rebate at 100%
        rebate_rate = min(rebate_rate, 1.0)
        
        # Calculate rebate amount
        rebate_amount = round(fee * rebate_rate, FEE_ROUNDING)
        
        return rebate_amount, rebate_rate

    def _get_volume_rebate_rate(self) -> float:
        """
        Get volume-based rebate rate based on current trading volume.
        
        Returns
        -------
        float
            Rebate rate as decimal (e.g., 0.15 for 15%)
        """
        if not self._config.rebate_tiers:
            return 0.0
        
        # Sort thresholds in descending order
        thresholds = sorted(self._config.rebate_tiers.keys(), reverse=True)
        
        # Find the highest threshold we've exceeded
        for threshold in thresholds:
            if self._total_volume >= threshold:
                return self._config.rebate_tiers[threshold]
        
        return 0.0  # Below lowest threshold

    def _track_fee_and_rebate(self, fee: float, rebate: float, fee_type: str, amount: float) -> None:
        """
        Track fee and rebate statistics.
        
        Parameters
        ----------
        fee : float
            Fee amount paid
        rebate : float
            Rebate amount earned
        fee_type : str
            "taker" or "maker"
        amount : float
            Trade amount (for volume tracking)
        """
        self._total_fees_paid += fee
        self._total_rebates_earned += rebate
        self._total_volume += amount
        
        if fee_type == "taker":
            self._taker_fees += fee
            self._taker_rebates += rebate
        else:
            self._maker_fees += fee
            self._maker_rebates += rebate
        
        log.debug(
            "Paper: fee tracked - total_fees=$%.4f, total_rebates=$%.4f, total_volume=$%.2f",
            self._total_fees_paid, self._total_rebates_earned, self._total_volume
        )

    # ── Slippage Calculation ───────────────────────────────────────────────────────

    def _apply_slippage(self, target_price: float, side: str) -> tuple[float, bool]:
        """
        Apply slippage to target price and determine if order should fill.
        
        Parameters
        ----------
        target_price : float
        The intended execution price
        side : str
        "UP" or "DOWN"
        
        Returns
        -------
        tuple[float, bool]
        (actual_price, filled) - actual price after slippage and whether order fills
        """
        if self._config.slippage_pct == 0:
            return target_price, True
        
        # Calculate base slippage
        slippage = target_price * self._config.slippage_pct
        
        # Add randomness if configured
        if self._config.slippage_randomness > 0:
            random_factor = random.uniform(
                1 - self._config.slippage_randomness,
                1 + self._config.slippage_randomness
            )
            slippage = slippage * random_factor
        
        # Apply slippage based on side (worse price for trader)
        if side == "UP":
            actual_price = target_price + slippage  # Higher price for buyer
        else:
            actual_price = target_price - slippage  # Lower price for buyer
        
        # Check if price moved too much (no fill)
        price_change_pct = abs(actual_price - target_price) / target_price
        if price_change_pct > self._config.max_slippage_no_fill:
            log.info(
                "Paper: slippage %.2f%% exceeds max %.2f%% - order not filled",
                price_change_pct * 100,
                self._config.max_slippage_no_fill * 100
            )
            return target_price, False
        
        return actual_price, True

    # ── Execution Delay ───────────────────────────────────────────────────────────

    def _apply_execution_delay(self) -> None:
        """
        Apply execution delay if configured.
        """
        if self._config.execution_delay_ms == 0:
            return
        
        delay_ms = self._config.execution_delay_ms
        
        # Add randomness if configured
        if self._config.delay_randomness > 0:
            random_factor = random.uniform(
                1 - self._config.delay_randomness,
                1 + self._config.delay_randomness
            )
            delay_ms = int(delay_ms * random_factor)
        
        delay_seconds = delay_ms / 1000.0
        log.debug("Paper: applying execution delay of %.0fms", delay_ms)
        time.sleep(delay_seconds)

    # ── Fill Probability ───────────────────────────────────────────────────────────

    def _check_fill_probability(self) -> bool:
        """
        Check if order should fill based on fill probability.
        
        Returns
        -------
        bool
            True if order should fill, False otherwise
        """
        if self._config.fill_probability >= 1.0:
            return True
        
        return random.random() < self._config.fill_probability

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
                log.debug("Paper: using live stream price %.4f for %s %s", price, market.slug, side)
                return price, "stream"
            else:
                log.warning("Paper: stream attached but price is 0, falling back to market price")
        
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
                    log.warning("Paper: market %s is closed, price may be stale", market.slug)
                elif time_until_close < PRICE_STALENESS_THRESHOLD:
                    log.warning(
                        "Paper: market %s closes in %.1fs, using potentially stale price %.4f",
                        market.slug, time_until_close, price
                    )
            except (ValueError, TypeError):
                pass  # If we can't parse end_time, skip staleness check
        
        if price <= 0:
            log.warning("Paper: market price is invalid (%.4f), using fallback", price)
            return FALLBACK_PRICE, "fallback"
        
        log.debug("Paper: using market price %.4f for %s %s", price, market.slug, side)
        return price, "market"

    # ── Orders ─────────────────────────────────────────────────────────────────

    def buy(self, market, side: str, amount: float, time_window_start: Optional[datetime] = None, time_window_end: Optional[datetime] = None) -> PaperOrder:
        """
        Simulated market buy — fills immediately at the current market price.

        Parameters
        ----------
        market : Market object
        side   : "UP" or "DOWN"
        amount : USDC to spend
        time_window_start : datetime, optional
            Only allow execution after this time (UTC)
        time_window_end : datetime, optional
            Only allow execution before this time (UTC)

        Returns
        -------
        PaperOrder with ``status="filled"``

        Example
        -------
        >>> order = client.paper.buy(market, side="UP", amount=10.0)
        >>> # Only buy within 1 minute of market close
        >>> from datetime import datetime, timezone, timedelta
        >>> end_time = datetime.fromisoformat(market.end_time)
        >>> order = client.paper.buy(market, side="UP", amount=10.0,
        ...     time_window_start=end_time - timedelta(minutes=1),
        ...     time_window_end=end_time)
        """
        _validate_market(market)
        side   = _validate_side(side)
        amount = _validate_positive(float(amount), "amount")

        # Get active wallet
        wallet = self._get_active_wallet()

        # Get price with stream awareness (prefers live stream price if available)
        price, price_source = self._get_price_for_side(market, side)

        # Check time window if set
        if time_window_start is not None or time_window_end is not None:
            now = datetime.now(timezone.utc)
            if time_window_start is not None and now < time_window_start:
                raise ValueError(f"Cannot buy: current time {now} is before time window start {time_window_start}")
            if time_window_end is not None and now > time_window_end:
                raise ValueError(f"Cannot buy: current time {now} is after time window end {time_window_end}")

        # Run pre-trade checks
        checks = self.pre_trade_checks(market, side, amount)
        if not checks["can_proceed"]:
            raise ValueError(
                f"Pre-trade checks failed: {'; '.join(checks['warnings'])}"
            )

        # Validate against risk limits
        wallet.risk_manager.validate_order(amount, wallet.balance, market.id, wallet._positions)

        # Apply execution delay if configured
        self._apply_execution_delay()

        # Apply slippage if configured
        actual_price, filled = self._apply_slippage(price, side)
        if not filled:
            log.info("Paper: market order not filled due to slippage threshold")
            # Create a cancelled order
            order_id = _new_id()
            order = PaperOrder(
                id        = order_id,
                market_id = market.id,
                slug      = market.slug,
                side      = side,
                price     = price,
                amount    = 0.0,
                shares    = 0.0,
                fee       = 0.0,
                status    = "cancelled",
                is_limit  = False,
                filled_at = _now(),
                time_window_start=time_window_start,
                time_window_end=time_window_end,
            )
            wallet._orders[order_id] = order
            return order

        order = self._fill(market, side, actual_price, amount, is_limit=False, wallet=wallet)
        order.time_window_start = time_window_start
        order.time_window_end = time_window_end
        return order

    def limit(self, market, side: str, price: float, amount: float, time_window_start: Optional[datetime] = None, time_window_end: Optional[datetime] = None) -> PaperOrder:
        """
        Simulated limit order — fills when the streamed price crosses *price*.

        Requires ``attach_stream()`` to have been called, otherwise call
        ``check_limits(up, down)`` manually after each price update.

        Parameters
        ----------
        market : Market object
        side   : "UP" or "DOWN"
        price  : trigger price — fills when token price >= this value
        amount : USDC to spend
        time_window_start : datetime, optional
            Only allow execution after this time (UTC)
        time_window_end : datetime, optional
            Only allow execution before this time (UTC)

        Returns
        -------
        PaperOrder with ``status="open"``

        Example
        -------
        >>> order = client.paper.limit(market, side="UP", price=0.92, amount=25.0)
        >>> # Only fill within 1 minute of market close
        >>> from datetime import datetime, timezone, timedelta
        >>> end_time = datetime.fromisoformat(market.end_time)
        >>> order = client.paper.limit(market, side="UP", price=0.92, amount=25.0,
        ...     time_window_start=end_time - timedelta(minutes=1),
        ...     time_window_end=end_time)
        """
        _validate_market(market)
        side   = _validate_side(side)
        price  = _validate_price(float(price), "price")
        amount = _validate_positive(float(amount), "amount")

        # Get active wallet
        wallet = self._get_active_wallet()

        if amount > wallet.balance:
            raise InsufficientBalance(
                f"Order amount ${amount:.2f} exceeds balance ${wallet.balance:.2f}"
            )

        # Run pre-trade checks
        checks = self.pre_trade_checks(market, side, amount)
        if not checks["can_proceed"]:
            raise ValueError(
                f"Pre-trade checks failed: {'; '.join(checks['warnings'])}"
            )

        # Validate against risk limits
        wallet.risk_manager.validate_order(amount, wallet.balance, market.id, wallet._positions)

        order_id = _new_id()
        order = PaperOrder(
            id        = order_id,
            market_id = market.id,
            slug      = market.slug,
            side      = side,
            price     = price,
            amount    = amount,
            shares    = 0.0,
            fee       = 0.0,
            status    = "open",
            is_limit  = True,
            time_window_start=time_window_start,
            time_window_end=time_window_end,
        )
        wallet._orders[order_id] = order
        wallet.balance -= amount  # reserve
        log.info(
            "Paper: limit %s @ %.3f $%.2f reserved — balance $%.2f",
            side, price, amount, wallet.balance,
        )
        return order

    def cancel(self, order_id: str) -> PaperOrder:
        """
        Cancel an open limit order and refund the reserved balance.

        Raises
        ------
        OrderNotFound  if the ID is unknown.
        ValueError     if the order is already filled or cancelled.

        Example
        -------
        >>> client.paper.cancel(order.id)
        """
        # Find the order across all wallets if in multi-wallet mode
        if self._use_multi_wallet and self._wallet_manager:
            for wallet in self._wallet_manager.get_all_wallets():
                order = wallet._orders.get(order_id)
                if order is not None:
                    if order.status != "open":
                        raise ValueError(
                            f"Cannot cancel order with status='{order.status}' (must be 'open')"
                        )
                    order.status = "cancelled"
                    wallet.balance += order.amount  # refund
                    log.info(
                        "Paper: cancelled order %s in wallet %s — $%.2f refunded, balance $%.2f",
                        order_id[:8], wallet.wallet_id, order.amount, wallet.balance,
                    )
                    return order
            raise OrderNotFound(f"No order found: {order_id}")
        
        # Single wallet mode
        order = self._orders.get(order_id)
        if order is None:
            raise OrderNotFound(f"No order found: {order_id}")
        if order.status != "open":
            raise ValueError(
                f"Cannot cancel order with status='{order.status}' (must be 'open')"
            )

        order.status  = "cancelled"
        self._balance += order.amount   # refund
        log.info(
            "Paper: cancelled order %s — $%.2f refunded, balance $%.2f",
            order_id[:8], order.amount, self._balance,
        )
        return order

    def buy_with_tp_sl(
        self,
        market,
        side: str,
        amount: float,
        stop_loss: float | None = None,
        take_profit: float | None = None,
        trail_sl: float | None = None,
        trail_tp: float | None = None,
        time_window_start: Optional[datetime] = None,
        time_window_end: Optional[datetime] = None,
    ) -> PaperOrder:
        """
        Market buy with optional stop-loss and take-profit.

        Parameters
        ----------
        market : Market object
        side   : "UP" or "DOWN"
        amount : USDC to spend
        stop_loss : SL price trigger (optional)
        take_profit : TP price trigger (optional)
        trail_sl : Trailing SL distance as percentage (e.g., 0.05 for 5%)
        trail_tp : Trailing TP distance as percentage (e.g., 0.10 for 10%)
        time_window_start : datetime, optional
            Only allow execution after this time (UTC)
        time_window_end : datetime, optional
            Only allow execution before this time (UTC)

        Returns
        -------
        PaperOrder with TP/SL set

        Example
        -------
        >>> order = client.paper.buy_with_tp_sl(
        ...     market, side="UP", amount=10.0,
        ...     stop_loss=0.45, take_profit=0.55
        ... )
        >>> # Only buy within 1 minute of market close
        >>> from datetime import datetime, timezone, timedelta
        >>> end_time = datetime.fromisoformat(market.end_time)
        >>> order = client.paper.buy_with_tp_sl(
        ...     market, side="UP", amount=10.0,
        ...     stop_loss=0.45, take_profit=0.55,
        ...     time_window_start=end_time - timedelta(minutes=1),
        ...     time_window_end=end_time
        ... )
        """
        _validate_market(market)
        side = _validate_side(side)
        amount = _validate_positive(float(amount), "amount")

        price = market.up_price if side == "UP" else market.down_price
        if price <= 0:
            price = FALLBACK_PRICE

        # Check time window if set
        if time_window_start is not None or time_window_end is not None:
            now = datetime.now(timezone.utc)
            if time_window_start is not None and now < time_window_start:
                raise ValueError(f"Cannot buy: current time {now} is before time window start {time_window_start}")
            if time_window_end is not None and now > time_window_end:
                raise ValueError(f"Cannot buy: current time {now} is after time window end {time_window_end}")

        # Validate against risk limits
        self._risk_manager.validate_order(amount, self._balance, market.id, self._positions)

        # Validate TP/SL prices
        if stop_loss is not None:
            stop_loss = _validate_price(float(stop_loss), "stop_loss")
        if take_profit is not None:
            take_profit = _validate_price(float(take_profit), "take_profit")
        if trail_sl is not None:
            trail_sl = _validate_positive(float(trail_sl), "trail_sl")
        if trail_tp is not None:
            trail_tp = _validate_positive(float(trail_tp), "trail_tp")

        # Apply execution delay and slippage
        self._apply_execution_delay()
        actual_price, filled = self._apply_slippage(price, side)
        if not filled:
            log.info("Paper: market order not filled due to slippage threshold")
            order_id = _new_id()
            order = PaperOrder(
                id=order_id,
                market_id=market.id,
                slug=market.slug,
                side=side,
                price=price,
                amount=0.0,
                shares=0.0,
                fee=0.0,
                status="cancelled",
                is_limit=False,
                filled_at=_now(),
            )
            self._orders[order_id] = order
            return order

        # Execute the fill
        order = self._fill(market, side, actual_price, amount, is_limit=False)

        # Set TP/SL on the order
        order.stop_loss = stop_loss
        order.take_profit = take_profit
        order.trail_sl = trail_sl
        order.trail_tp = trail_tp
        order.time_window_start = time_window_start
        order.time_window_end = time_window_end

        # Initialize trailing prices
        if trail_sl is not None:
            order.trail_sl_price = actual_price * (1 - trail_sl) if side == "UP" else actual_price * (1 + trail_sl)
        if trail_tp is not None:
            order.trail_tp_price = actual_price * (1 + trail_tp) if side == "UP" else actual_price * (1 - trail_tp)

        log.info(
            "Paper: buy_with_tp_sl %s @ %.3f SL=%.3f TP=%.3f trail_SL=%.3f trail_TP=%.3f",
            side, actual_price, stop_loss or 0, take_profit or 0, trail_sl or 0, trail_tp or 0,
        )
        return order

    def sell_position(self, market, side: str, amount: float | None = None) -> PaperOrder:
        """
        Sell/close a position (simulated sell for prediction markets).

        Parameters
        ----------
        market : Market object
        side   : "UP" or "DOWN" - which position to close
        amount : USDC to sell (optional, defaults to full position)

        Returns
        -------
        PaperOrder representing the sell

        Example
        -------
        >>> order = client.paper.sell_position(market, side="UP")
        """
        _validate_market(market)
        side = _validate_side(side)
        key = f"{market.id}:{side}"

        if key not in self._positions:
            raise ValueError(f"No position found for {market.slug} {side}")

        position = self._positions[key]
        current_price = position.current_price

        if current_price <= 0:
            current_price = FALLBACK_PRICE

        # Validate position has shares to sell
        if position.shares <= 0:
            raise ValueError(f"Position has no shares to sell: {position.shares}")

        # Determine amount to sell
        if amount is None:
            # Sell full position
            sell_shares = position.shares
            sell_amount = sell_shares * current_price
        else:
            amount = _validate_positive(float(amount), "amount")
            sell_shares = amount / current_price
            sell_amount = amount
            
            # Validate not selling more than available
            if sell_shares > position.shares:
                raise ValueError(
                    f"Cannot sell {sell_shares:.4f} shares, only {position.shares:.4f} available"
                )

        # Apply execution delay and slippage
        self._apply_execution_delay()
        actual_price, filled = self._apply_slippage(current_price, side)
        if not filled:
            log.info("Paper: sell order not filled due to slippage threshold")
            order_id = _new_id()
            order = PaperOrder(
                id=order_id,
                market_id=market.id,
                slug=market.slug,
                side=side,
                price=current_price,
                amount=0.0,
                shares=0.0,
                fee=0.0,
                status="cancelled",
                is_limit=False,
                filled_at=_now(),
            )
            self._orders[order_id] = order
            return order

        # Calculate fee (selling also has fee)
        fee, rebate_amount, rebate_rate, fee_type = self._calculate_fee(sell_amount, actual_price, sell_shares, is_maker=False)
        net_amount = sell_amount - fee

        # Update balance (add proceeds)
        self._balance += net_amount

        # Create sell order
        order_id = _new_id()
        order = PaperOrder(
            id=order_id,
            market_id=market.id,
            slug=market.slug,
            side=side,
            price=actual_price,
            amount=sell_amount,
            shares=sell_shares,
            fee=fee,
            status="filled",
            is_limit=False,
            filled_at=_now(),
        )
        self._orders[order_id] = order

        # Reduce or close position
        position.shares -= sell_shares
        if position.shares <= 0.001:  # Close if negligible
            position.shares = 0
            position.resolved = True
            position.outcome = "CLOSED"
            # Calculate P&L for the closed position
            pnl = net_amount - position.cost_basis
            # Record P&L with risk manager
            self._risk_manager.record_trade(pnl)
            log.info(
                "Paper: closed position %s %s — proceeds $%.2f, balance $%.2f",
                market.slug, side, net_amount, self._balance,
            )
            # Save trade to database if enabled
            self._save_trade_to_db(position)
        else:
            log.info(
                "Paper: reduced position %s %s by %.2f shares — proceeds $%.2f",
                market.slug, side, sell_shares, net_amount,
            )

        return order

    def set_trailing_sl(self, order_id: str, trail_distance: float) -> PaperOrder:
        """
        Set or update trailing stop-loss on an existing order.

        Parameters
        ----------
        order_id : Order ID to modify
        trail_distance : Trailing distance as percentage (e.g., 0.05 for 5%)

        Returns
        -------
        Updated PaperOrder

        Example
        -------
        >>> order = client.paper.set_trailing_sl(order.id, 0.05)
        """
        trail_distance = _validate_positive(float(trail_distance), "trail_distance")

        order = self._orders.get(order_id)
        if order is None:
            raise OrderNotFound(f"No order found: {order_id}")
        if order.status != "filled":
            raise ValueError(f"Can only set trailing SL on filled orders, got status='{order.status}'")

        order.trail_sl = trail_distance
        # Initialize trailing SL price
        order.trail_sl_price = order.price * (1 - trail_distance) if order.side == "UP" else order.price * (1 + trail_distance)

        log.info(
            "Paper: set trailing SL %.2f%% on order %s @ %.3f",
            trail_distance * 100, order_id[:8], order.trail_sl_price,
        )
        return order

    def set_trailing_tp(self, order_id: str, trail_distance: float) -> PaperOrder:
        """
        Set or update trailing take-profit on an existing order.

        Parameters
        ----------
        order_id : Order ID to modify
        trail_distance : Trailing distance as percentage (e.g., 0.10 for 10%)

        Returns
        -------
        Updated PaperOrder

        Example
        -------
        >>> order = client.paper.set_trailing_tp(order.id, 0.10)
        """
        trail_distance = _validate_positive(float(trail_distance), "trail_distance")

        order = self._orders.get(order_id)
        if order is None:
            raise OrderNotFound(f"No order found: {order_id}")
        if order.status != "filled":
            raise ValueError(f"Can only set trailing TP on filled orders, got status='{order.status}'")

        order.trail_tp = trail_distance
        # Initialize trailing TP price
        order.trail_tp_price = order.price * (1 + trail_distance) if order.side == "UP" else order.price * (1 - trail_distance)

        log.info(
            "Paper: set trailing TP %.2f%% on order %s @ %.3f",
            trail_distance * 100, order_id[:8], order.trail_tp_price,
        )
        return order

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
        >>> client.paper.set_stop_loss(market, side="UP", stop_price=0.45)
        """
        _validate_market(market)
        side = _validate_side(side)
        stop_price = _validate_price(float(stop_price), "stop_price")
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
        >>> client.paper.set_take_profit(market, side="UP", profit_price=0.55)
        """
        _validate_market(market)
        side = _validate_side(side)
        profit_price = _validate_price(float(profit_price), "profit_price")
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
        >>> client.paper.set_trailing_stop(market, side="UP", trail_distance=0.05)
        """
        _validate_market(market)
        side = _validate_side(side)
        trail_distance = _validate_positive(float(trail_distance), "trail_distance")
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

    def oco_order(
       self,
        market,
        side: str,
        amount: float,
        stop_loss: float,
        take_profit: float,
    ) -> tuple[PaperOrder, PaperOrder]:
        """
        One-Cancels-Other (OCO) order - place SL and TP where one cancels the other.

        Creates a main order and automatically sets up SL and TP as OCO-linked.
        When either SL or TP is triggered, the other is automatically cancelled.

        Parameters
        ----------
        market : Market object
        side   : "UP" or "DOWN"
        amount : USDC to spend
        stop_loss : SL price trigger
        take_profit : TP price trigger

        Returns
        -------
        tuple of (main_order, oco_order) - main order and the OCO-linked SL/TP order

        Example
        -------
        >>> main_order, oco_order = client.paper.oco_order(
        ...     market, side="UP", amount=10.0,
        ...     stop_loss=0.45, take_profit=0.55
        ... )
        """
        _validate_market(market)
        side = _validate_side(side)
        amount = _validate_positive(float(amount), "amount")
        stop_loss = _validate_price(float(stop_loss), "stop_loss")
        take_profit = _validate_price(float(take_profit), "take_profit")

        # Create main order with TP/SL
        main_order = self.buy_with_tp_sl(
            market, side=side, amount=amount,
            stop_loss=stop_loss, take_profit=take_profit,
        )

        # Link them as OCO
        main_order.oco_order_id = main_order.id  # Self-linked for tracking

        log.info(
            "Paper: OCO order created %s SL=%.3f TP=%.3f",
            main_order.id[:8], stop_loss, take_profit,
        )

        return main_order, main_order

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
        >>> client.paper.show_positions()  # Show live positions
        >>> client.paper.show_positions(show_all=True)  # Show all positions
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

    # ── Resolution ─────────────────────────────────────────────────────────────

    def resolve(self, market, outcome: str) -> None:
        """
        Mark all positions for *market* as resolved.

        Parameters
        ----------
        market  : Market object
        outcome : "UP" or "DOWN" — whichever outcome won

        Example
        -------
        >>> client.paper.resolve(market, outcome="UP")
        """
        _validate_market(market)
        outcome = outcome.upper()
        if outcome not in ("UP", "DOWN"):
            raise ValueError(f"outcome must be 'UP' or 'DOWN', got '{outcome}'")

        # Get positions from all wallets if in multi-wallet mode
        if self._use_multi_wallet and self._wallet_manager:
            for wallet in self._wallet_manager.get_all_wallets():
                for pos in wallet._positions.values():
                    if pos.market_id == market.id and not pos.resolved:
                        pos.resolved = True
                        pos.outcome  = "WON" if pos.side == outcome else "LOST"
                        payout = pos.shares if pos.outcome == "WON" else 0.0
                        wallet.balance += payout
                        # Record P&L with risk manager
                        wallet.risk_manager.record_trade(pos.pnl)
                        log.info(
                            "Paper: resolved %s in wallet %s → %s  payout=$%.2f  balance=$%.2f",
                            pos.slug, wallet.wallet_id, pos.outcome, payout, wallet.balance,
                        )
                        # Save trade to database if enabled
                        self._save_trade_to_db(pos)
        else:
            # Single wallet mode
            for pos in self._positions.values():
                if pos.market_id == market.id and not pos.resolved:
                    pos.resolved = True
                    pos.outcome  = "WON" if pos.side == outcome else "LOST"
                    payout = pos.shares if pos.outcome == "WON" else 0.0
                    self._balance += payout
                    # Record P&L with risk manager
                    self._risk_manager.record_trade(pos.pnl)
                    log.info(
                        "Paper: resolved %s → %s  payout=$%.2f  balance=$%.2f",
                        pos.slug, pos.outcome, payout, self._balance,
                    )
                    # Save trade to database if enabled
                    self._save_trade_to_db(pos)

    # ── Stream integration ─────────────────────────────────────────────────────

    def check_limits(self, market_id: str, up_price: float, down_price: float) -> None:
        """
        Update live position prices and fill any triggered limit orders.
        Also checks and triggers TP/SL orders and updates trailing stops.

        Called automatically when a stream is attached via ``attach_stream()``.
        Can also be called manually when running without a stream.
        
        Respects check_mode configuration:
        - "continuous": Check continuously (default)
        - "once": Only check conditions once
        - int N: Check conditions N times maximum
        """
        # Validate prices
        up_price = _validate_price(float(up_price), "up_price")
        down_price = _validate_price(float(down_price), "down_price")
        
        # Update live prices for all open positions in this market
        for pos in self._positions.values():
            if pos.market_id == market_id and not pos.resolved:
                pos.current_price = up_price if pos.side == "UP" else down_price

        # Check and fill pending limit orders
        for order in list(self._orders.values()):
            if order.status != "open" or order.market_id != market_id:
                continue
            
            # Increment check count
            order.check_count += 1
            
            # Check if we should skip based on check_mode
            if not self._should_check_order(order):
                log.debug(
                    "Paper: limit order %s skipped - check count %d exceeds check_mode %s",
                    order.id[:8], order.check_count, self._config.check_mode
                )
                continue
            
            current = up_price if order.side == "UP" else down_price
            if current >= order.price:
                # Check time window before filling
                if self._is_within_time_window(order):
                    self._fill_limit(order, current)
                else:
                    log.debug(
                        "Paper: limit order %s not filled - outside time window",
                        order.id[:8]
                    )

        # Check TP/SL on filled orders
        self._check_tp_sl(market_id, up_price, down_price)

    def _is_within_time_window(self, order: PaperOrder) -> bool:
        """
        Check if current time is within the order's time window.
        
        Parameters
        ----------
        order : PaperOrder
            The order to check
            
        Returns
        -------
        bool
            True if current time is within time window or no window is set
        """
        if order.time_window_start is None and order.time_window_end is None:
            return True  # No time window restriction
        
        now = datetime.now(timezone.utc)
        
        if order.time_window_start is not None and now < order.time_window_start:
            return False  # Before window start
        
        if order.time_window_end is not None and now > order.time_window_end:
            return False  # After window end
        
        return True

    def _should_check_order(self, order: PaperOrder) -> bool:
        """
        Check if an order should be checked based on check_mode configuration.
        
        Parameters
        ----------
        order : PaperOrder
            The order to check
            
        Returns
        -------
        bool
            True if order should be checked, False if check limit exceeded
        """
        check_mode = self._config.check_mode
        
        # Continuous mode - always check
        if check_mode == "continuous":
            return True
        
        # Once mode - only check on first attempt
        if check_mode == "once":
            return order.check_count <= 1
        
        # Integer mode - check up to N times
        if isinstance(check_mode, int):
            return order.check_count <= check_mode
        
        # Default to continuous for safety
        return True

    def _check_tp_sl(self, market_id: str, up_price: float, down_price: float) -> None:
        """
        Check and trigger TP/SL orders, update trailing stops.
        
        This method is called by check_limits on every price update.
        """
        for order in list(self._orders.values()):
            # Only check filled orders with TP/SL set
            if order.status != "filled" or order.market_id != market_id:
                continue
            
            if order.stop_loss is None and order.take_profit is None and order.trail_sl is None and order.trail_tp is None:
                continue
            
            # Skip if already triggered
            if order.tp_sl_triggered_by is not None:
                continue
            
            current_price = up_price if order.side == "UP" else down_price
            triggered = None
            
            # Update trailing stop-loss
            if order.trail_sl is not None:
                new_trail_sl = current_price * (1 - order.trail_sl) if order.side == "UP" else current_price * (1 + order.trail_sl)
                # Only move SL up (for UP) or down (for DOWN) - never against the trader
                if order.side == "UP":
                    if new_trail_sl > (order.trail_sl_price or 0):
                        order.trail_sl_price = new_trail_sl
                        log.debug("Paper: trailing SL moved up to %.3f for order %s", new_trail_sl, order.id[:8])
                else:  # DOWN
                    if new_trail_sl < (order.trail_sl_price or float('inf')):
                        order.trail_sl_price = new_trail_sl
                        log.debug("Paper: trailing SL moved down to %.3f for order %s", new_trail_sl, order.id[:8])
            
            # Update trailing take-profit
            if order.trail_tp is not None:
                new_trail_tp = current_price * (1 + order.trail_tp) if order.side == "UP" else current_price * (1 - order.trail_tp)
                # Move TP in direction of trade to allow more profit potential
                if order.side == "UP":
                    if new_trail_tp > (order.trail_tp_price or 0):
                        order.trail_tp_price = new_trail_tp
                        log.debug("Paper: trailing TP moved up to %.3f for order %s", new_trail_tp, order.id[:8])
                else:  # DOWN
                    if new_trail_tp < (order.trail_tp_price or float('inf')):
                        order.trail_tp_price = new_trail_tp
                        log.debug("Paper: trailing TP moved down to %.3f for order %s", new_trail_tp, order.id[:8])
            
            # Check stop-loss trigger
            sl_trigger = order.stop_loss if order.stop_loss is not None else order.trail_sl_price
            if sl_trigger is not None:
                if order.side == "UP" and current_price <= sl_trigger:
                    triggered = "sl"
                elif order.side == "DOWN" and current_price >= sl_trigger:
                    triggered = "sl"
            
            # Check take-profit trigger
            tp_trigger = order.take_profit if order.take_profit is not None else order.trail_tp_price
            if tp_trigger is not None and triggered is None:
                if order.side == "UP" and current_price >= tp_trigger:
                    triggered = "tp"
                elif order.side == "DOWN" and current_price <= tp_trigger:
                    triggered = "tp"
            
            # Execute triggered order
            if triggered:
                order.tp_sl_triggered_by = triggered
                log.info(
                    "Paper: %s triggered for order %s @ %.3f (trigger: %.3f)",
                    "STOP-LOSS" if triggered == "sl" else "TAKE-PROFIT",
                    order.id[:8], current_price, sl_trigger if triggered == "sl" else tp_trigger,
                )
                
                # Cancel OCO linked order if exists
                if order.oco_order_id and order.oco_order_id != order.id:
                    oco_order = self._orders.get(order.oco_order_id)
                    if oco_order and oco_order.status == "filled":
                        oco_order.stop_loss = None
                        oco_order.take_profit = None
                        oco_order.trail_sl = None
                        oco_order.trail_tp = None
                        log.info("Paper: cancelled OCO linked order %s", order.oco_order_id[:8])
                
                # Execute sell to close position
                try:
                    self.sell_position(
                        type('obj', (object,), {
                            'id': order.market_id,
                            'slug': order.slug,
                        })(),
                        side=order.side,
                    )
                except ValueError as e:
                    log.warning("Paper: failed to sell position on %s trigger: %s", triggered, e)

    def attach_stream(self, stream, market) -> None:
        """
        Wire *stream* so positions auto-update and limits auto-fill.

        Also enables price-aware trading: buy() will automatically use live
        streamed prices when a stream is attached and running.

        Example
        -------
        >>> stream = client.stream(market)
        >>> client.paper.attach_stream(stream, market)
        >>> stream.start(background=True)
        """
        _validate_market(market)
        
        # Store stream reference for price-aware trading
        self._attached_streams[market.id] = stream
        
        @stream.on("price")
        def _on_price(up: float, down: float) -> None:
            self.check_limits(market.id, up, down)

        @stream.on("close")
        def _on_close() -> None:
            log.info(
                "Paper: stream closed for %s — call paper.resolve(market, outcome)",
                market.slug,
            )
            # Remove stream reference when closed
            self._attached_streams.pop(market.id, None)

        log.info("Paper: stream attached for %s", market.slug)

    # ── Fee Rebate Reporting ─────────────────────────────────────────────────────

    def fee_summary(self) -> None:
        """Print a detailed fee and rebate summary."""
        div = "─" * SUMMARY_DIV_WIDTH
        print(div)
        print("  POLYALPHA — FEE & REBATE SUMMARY")
        print(div)
        print(f"  {'Total volume':<22} ${self._total_volume:>10.2f}")
        print(f"  {'Total fees paid':<22} ${self._total_fees_paid:>10.4f}")
        print(f"  {'Total rebates earned':<22} ${self._total_rebates_earned:>10.4f}")
        print(f"  {'Net fees (after rebates)':<22} ${self._total_fees_paid - self._total_rebates_earned:>10.4f}")
        print(f"  {'Effective fee rate':<22} {(self._total_fees_paid - self._total_rebates_earned) / self._total_volume * 100 if self._total_volume > 0 else 0:.2f}%")
        print(div)
        print(f"  {'Taker fees':<22} ${self._taker_fees:>10.4f}")
        print(f"  {'Taker rebates':<22} ${self._taker_rebates:>10.4f}")
        print(f"  {'Maker fees':<22} ${self._maker_fees:>10.4f}")
        print(f"  {'Maker rebates':<22} ${self._maker_rebates:>10.4f}")
        print(div)
        
        # Show current rebate tier
        current_rate = self._get_volume_rebate_rate()
        print(f"  Current volume rebate tier: {current_rate * 100:.1f}%")
        if self._config.rebate_tiers:
            print(f"  Volume thresholds:")
            thresholds = sorted(self._config.rebate_tiers.items())
            for threshold, rate in thresholds:
                marker = " ← current" if rate == current_rate else ""
                print(f"    ${threshold:>8.0f}+: {rate * 100:>5.1f}%{marker}")
        print(div)

    def get_rebate_stats(self) -> dict:
        """
        Get rebate statistics as a dictionary.
        
        Returns
        -------
        dict
            Dictionary containing all rebate statistics
        """
        return {
            "total_volume": self._total_volume,
            "total_fees_paid": self._total_fees_paid,
            "total_rebates_earned": self._total_rebates_earned,
            "net_fees": self._total_fees_paid - self._total_rebates_earned,
            "effective_fee_rate": (self._total_fees_paid - self._total_rebates_earned) / self._total_volume if self._total_volume > 0 else 0,
            "taker_fees": self._taker_fees,
            "taker_rebates": self._taker_rebates,
            "maker_fees": self._maker_fees,
            "maker_rebates": self._maker_rebates,
            "current_rebate_rate": self._get_volume_rebate_rate(),
        }

    # ── Reporting ──────────────────────────────────────────────────────────────

    def summary(self) -> None:
        """Print a formatted P&L summary to stdout."""
        all_orders    = self.orders()
        all_positions = self.all_positions()

        filled    = [o for o in all_orders    if o.status == "filled"]
        open_pos  = [p for p in all_positions if not p.resolved]
        resolved  = [p for p in all_positions if p.resolved]

        total_invested = sum(o.amount for o in filled)
        total_fees     = sum(o.fee    for o in filled)
        total_rebates   = sum(o.rebate_amount for o in filled)
        wins           = [p for p in resolved if p.outcome == "WON"]
        losses         = [p for p in resolved if p.outcome == "LOST"]
        realised_pnl   = sum(p.pnl for p in resolved)
        unrealised_pnl = sum(p.pnl for p in open_pos)

        div = "─" * SUMMARY_DIV_WIDTH
        print(div)
        print("  POLYALPHA — PAPER TRADING SUMMARY")
        print(div)
        print(f"  {'Balance':<22} ${self._balance:>10.2f}")
        print(f"  {'Total invested':<22} ${total_invested:>10.2f}")
        print(f"  {'Total fees paid':<22} ${total_fees:>10.4f}")
        print(f"  {'Total rebates earned':<22} ${total_rebates:>10.4f}")
        print(f"  {'Net fees (after rebates)':<22} ${total_fees - total_rebates:>10.4f}")
        print(f"  {'Unrealised P&L':<22} ${unrealised_pnl:>+10.2f}")
        print(f"  {'Realised P&L':<22} ${realised_pnl:>+10.2f}")

        if resolved:
            win_rate = len(wins) / len(resolved) * 100
            print(div)
            print(
                f"  Resolved: {len(resolved)} trades  "
                f"({len(wins)}W / {len(losses)}L  {win_rate:.0f}% win rate)"
            )
            print(f"\n  {'MARKET':<30} {'SIDE':<5} {'RESULT':<6} {'P&L':>9}")
            print(f"  {'─'*30} {'─'*5} {'─'*6} {'─'*9}")
            for p in resolved:
                label  = _slug_label(p.slug)
                result = "WON" if p.outcome == "WON" else "LOST"
                print(f"  {label:<30} {p.side:<5} {result:<6} ${p.pnl:>+8.2f}")

        if open_pos:
            print(div)
            print(f"  Open positions ({len(open_pos)})\n")
            print(f"  {'MARKET':<30} {'SIDE':<5} {'AVG':>6} {'NOW':>6} {'P&L':>9}")
            print(f"  {'─'*30} {'─'*5} {'─'*6} {'─'*6} {'─'*9}")
            for p in open_pos:
                label = _slug_label(p.slug)
                print(
                    f"  {label:<30} {p.side:<5} "
                    f"{p.avg_price:>6.3f} {p.current_price:>6.3f} ${p.pnl:>+8.2f}"
                )

        if not resolved and not open_pos:
            print(f"\n  No trades yet.")

        print(div)

    # ── Internal ───────────────────────────────────────────────────────────────

    def _fill(
        self,
        market,
        side:     str,
        price:    float,
        amount:   float,
        is_limit: bool,
        wallet: Optional[PaperWallet] = None,
    ) -> PaperOrder:
        """Execute a simulated fill and update the position book."""
        if wallet is None:
            wallet = self._get_active_wallet()
            
        if amount > wallet.balance:
            raise InsufficientBalance(
                f"Order amount ${amount:.2f} exceeds balance ${wallet.balance:.2f}"
            )

        # Validate price is positive
        if price <= 0:
            raise ValueError(f"Price must be positive, got {price}")

        # Calculate shares first (needed for fee calculation)
        net = amount  # Will subtract fee after calculation
        shares = round(net / price, SHARE_ROUNDING) if price > 0 else 0.0
        
        # Validate shares calculation resulted in positive amount
        if shares <= 0:
            raise ValueError(
                f"Calculated shares is zero or negative (amount=${amount:.2f}, price=${price:.4f})"
            )

        # Calculate fee and rebate
        fee, rebate_amount, rebate_rate, fee_type = self._calculate_fee(amount, price, shares, is_maker=is_limit)
        net = amount - fee + rebate_amount  # Net cost after fee and rebate
        shares = round(net / price, SHARE_ROUNDING) if price > 0 else 0.0

        wallet.balance -= amount
        
        # Track fee and rebate statistics
        self._track_fee_and_rebate(fee, rebate_amount, fee_type, amount)

        order = PaperOrder(
            id        = _new_id(),
            market_id = market.id,
            slug      = market.slug,
            side      = side,
            price     = price,
            amount    = amount,
            shares    = shares,
            fee       = fee,
            status    = "filled",
            is_limit  = is_limit,
            filled_at = _now(),
            fee_type  = fee_type,
            rebate_amount = rebate_amount,
            rebate_rate = rebate_rate,
        )
        wallet._orders[order.id] = order

        self._upsert_position(market.id, market.slug, market.question, side, shares, price, order.id, wallet=wallet)
        log.info(
            "Paper: filled %s %.4f shares @ %.3f  fee=$%.4f  rebate=$%.4f  balance=$%.2f",
            side, shares, price, fee, rebate_amount, wallet.balance,
        )
        return order

    def _fill_limit(self, order: PaperOrder, current_price: float) -> None:
        """Fill a pending limit order at *current_price* (balance already reserved)."""
        # Validate current price
        if current_price <= 0:
            log.warning("Paper: invalid current price %.4f for limit order %s, cancelling", current_price, order.id[:8])
            order.status = "cancelled"
            self._balance += order.amount  # refund
            return
        
        # Check fill probability
        if not self._check_fill_probability():
            log.info(
                "Paper: limit order %s not filled due to fill probability %.2f",
                order.id[:8], self._config.fill_probability
            )
            order.status = "cancelled"
            self._balance += order.amount  # refund
            return

        # Apply slippage to limit order fill
        actual_price, filled = self._apply_slippage(current_price, order.side)
        if not filled:
            log.info(
                "Paper: limit order %s not filled due to slippage threshold",
                order.id[:8]
            )
            order.status = "cancelled"
            self._balance += order.amount  # refund
            return

        # Calculate fee and rebate
        shares = round(order.amount / actual_price, SHARE_ROUNDING) if actual_price > 0 else 0.0
        
        # Validate shares calculation
        if shares <= 0:
            log.warning(
                "Paper: calculated shares is zero for limit order %s (amount=$%.2f, price=$%.4f), cancelling",
                order.id[:8], order.amount, actual_price
            )
            order.status = "cancelled"
            self._balance += order.amount  # refund
            return
        
        fee, rebate_amount, rebate_rate, fee_type = self._calculate_fee(order.amount, actual_price, shares, is_maker=True)
        net = order.amount - fee + rebate_amount
        shares = round(net / actual_price, SHARE_ROUNDING) if actual_price > 0 else 0.0
        
        # Track fee and rebate statistics
        self._track_fee_and_rebate(fee, rebate_amount, fee_type, order.amount)

        order.price     = actual_price
        order.shares    = shares
        order.fee       = fee
        order.status    = "filled"
        order.filled_at = _now()
        order.fee_type  = fee_type
        order.rebate_amount = rebate_amount
        order.rebate_rate = rebate_rate

        # Resolve the question string from any existing position in this market
        question = next(
            (p.question for p in self._positions.values() if p.market_id == order.market_id),
            "",
        )
        self._upsert_position(
            order.market_id, order.slug, question, order.side, shares, actual_price, order.id,
        )
        log.info(
            "Paper: limit filled %s %.4f shares @ %.3f  fee=$%.4f  rebate=$%.4f",
            order.side, shares, actual_price, fee, rebate_amount,
        )

    def _upsert_position(
        self,
        market_id: str,
        slug:      str,
        question:  str,
        side:      str,
        shares:    float,
        price:     float,
        order_id:  str,
        wallet: Optional[PaperWallet] = None,
    ) -> None:
        """Merge *shares* into an existing position or create a new one."""
        if wallet is None:
            wallet = self._get_active_wallet()
            
        key = f"{market_id}:{side}"
        if key in wallet._positions:
            pos         = wallet._positions[key]
            total       = pos.shares + shares
            pos.avg_price = round(
                (pos.shares * pos.avg_price + shares * price) / total, PRICE_ROUNDING
            )
            pos.shares  = total
            pos.order_ids.append(order_id)
        else:
            wallet._positions[key] = PaperPosition(
                market_id     = market_id,
                slug          = slug,
                question      = question,
                side          = side,
                shares        = shares,
                avg_price     = price,
                current_price = price,
                order_ids     = [order_id],
            )


# ── Helpers ────────────────────────────────────────────────────────────────────

def _validate_market(market) -> None:
    """Validate that market object has required attributes."""
    required_attrs = ['id', 'slug', 'question', 'up_price', 'down_price']
    for attr in required_attrs:
        if not hasattr(market, attr):
            raise ValueError(f"Market object missing required attribute: {attr}")
    
    # Validate price attributes are numeric
    if not isinstance(market.up_price, (int, float)):
        raise ValueError(f"Market up_price must be numeric, got {type(market.up_price)}")
    if not isinstance(market.down_price, (int, float)):
        raise ValueError(f"Market down_price must be numeric, got {type(market.down_price)}")
    
    # Validate prices are not NaN or infinity
    import math
    if math.isnan(market.up_price) or math.isinf(market.up_price):
        raise ValueError(f"Market up_price is invalid: {market.up_price}")
    if math.isnan(market.down_price) or math.isinf(market.down_price):
        raise ValueError(f"Market down_price is invalid: {market.down_price}")

def _validate_side(side: str) -> str:
    s = side.strip().upper()
    if s not in ("UP", "DOWN"):
        raise ValueError(f"side must be 'UP' or 'DOWN', got '{side!r}'")
    return s


def _validate_positive(value: float, name: str) -> float:
    if value <= 0:
        raise ValueError(f"{name} must be > 0, got {value}")
    return value


def _validate_price(price: float, name: str = "price") -> float:
    """Validate that price is within valid range for prediction markets (0-1)."""
    if not isinstance(price, (int, float)):
        raise ValueError(f"{name} must be numeric, got {type(price)}")
    
    import math
    if math.isnan(price) or math.isinf(price):
        raise ValueError(f"{name} is invalid: {price}")
    
    if price < 0 or price > 1:
        raise ValueError(f"{name} must be between 0 and 1, got {price}")
    
    return price


def _new_id() -> str:
    return str(uuid.uuid4())


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _slug_label(slug: str) -> str:
    """Shorten a slug for display.  btc-updown-5m-1234 → BTC 5m"""
    parts = slug.split("-")
    try:
        return f"{parts[0].upper()} {parts[2]}"
    except IndexError:
        return slug[:20]
