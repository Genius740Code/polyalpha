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

from ..core import (
    InsufficientBalance,
    OrderNotFound,
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
        self._balance:   float                       = float(balance)
        self._orders:    dict[str, PaperOrder]       = {}
        self._positions: dict[str, PaperPosition]    = {}   # key: "{market_id}:{side}"
        self._config:    PaperConfig                  = config or PaperConfig()
        # Lazy-initialised in the report property to avoid circular imports
        self._report: Optional["ReportEngine"] = None
        # Optional database for trade persistence
        self._db: Optional["TradeDatabase"] = None
        self._db_enabled: bool = False
        if db_path:
            self.enable_database(db_path)

    @property
    def report(self) -> "ReportEngine":
        """Analytics and reporting engine. Access via ``client.paper.report``."""
        if self._report is None:
            from ..report.engine import ReportEngine
            self._report = ReportEngine(self)
        return self._report

    # ── Balance ────────────────────────────────────────────────────────────────

    @property
    def balance(self) -> float:
        """Current paper USDC balance."""
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
        try:
            from ..database.database import TradeDatabase
            self._db = TradeDatabase(db_path)
            self._db_enabled = True
            log.info("Paper: database enabled at %s", db_path)
        except ImportError:
            log.error("Paper: database module not available. Install required dependencies.")
            self._db_enabled = False

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

    def _calculate_fee(self, amount: float, price: float, shares: float, is_maker: bool = False) -> float:
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
        float
            Fee amount in USDC
        """
        if self._config.fee_mode == "zero":
            return 0.0
        elif self._config.fee_mode == "custom":
            fee_rate = self._config.maker_fee_rate if is_maker else self._config.custom_fee_rate
            return round(amount * fee_rate, FEE_ROUNDING)
        elif self._config.fee_mode == "polymarket":
            return self._polymarket_fee(amount, price, shares, is_maker)
        else:
            # Fallback to default taker fee
            return round(amount * TAKER_FEE_RATE, FEE_ROUNDING)

    def _polymarket_fee(self, amount: float, price: float, shares: float, is_maker: bool = False) -> float:
        """
        Calculate Polymarket-style fee based on their formula.
        
        Formula: fee = C × p × feeRate × (p × (1 − p))^exponent
        
        Where:
        - C: Number of shares traded
        - p: Price of the trade
        - feeRate: Category-specific (e.g., sports=0.03, crypto=0.02)
        - exponent: 1
        
        Geopolitical markets have 0% fee.
        """
        # Geopolitical markets are fee-free
        if self._config.market_category.lower() == "geopolitical":
            return 0.0
        
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
        
        # For maker orders, apply maker fee rate (typically lower)
        if is_maker:
            fee = fee * MAKER_REBATE_PCT  # 25% maker rebate
        
        return fee

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
        side   = _validate_side(side)
        amount = _validate_positive(float(amount), "amount")

        price = market.up_price if side == "UP" else market.down_price
        if price <= 0:
            price = FALLBACK_PRICE  # safe fallback before first WS price arrives

        # Check time window if set
        if time_window_start is not None or time_window_end is not None:
            now = datetime.now(timezone.utc)
            if time_window_start is not None and now < time_window_start:
                raise ValueError(f"Cannot buy: current time {now} is before time window start {time_window_start}")
            if time_window_end is not None and now > time_window_end:
                raise ValueError(f"Cannot buy: current time {now} is after time window end {time_window_end}")

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
            self._orders[order_id] = order
            return order

        order = self._fill(market, side, actual_price, amount, is_limit=False)
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
        side   = _validate_side(side)
        price  = _validate_positive(float(price),  "price")
        amount = _validate_positive(float(amount), "amount")

        if amount > self._balance:
            raise InsufficientBalance(
                f"Order amount ${amount:.2f} exceeds balance ${self._balance:.2f}"
            )

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
        self._orders[order_id] = order
        self._balance -= amount  # reserve
        log.info(
            "Paper: limit %s @ %.3f $%.2f reserved — balance $%.2f",
            side, price, amount, self._balance,
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

        # Validate TP/SL prices
        if stop_loss is not None:
            stop_loss = _validate_positive(float(stop_loss), "stop_loss")
        if take_profit is not None:
            take_profit = _validate_positive(float(take_profit), "take_profit")
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
        side = _validate_side(side)
        key = f"{market.id}:{side}"

        if key not in self._positions:
            raise ValueError(f"No position found for {market.slug} {side}")

        position = self._positions[key]
        current_price = position.current_price

        if current_price <= 0:
            current_price = FALLBACK_PRICE

        # Determine amount to sell
        if amount is None:
            # Sell full position
            sell_shares = position.shares
            sell_amount = sell_shares * current_price
        else:
            amount = _validate_positive(float(amount), "amount")
            sell_shares = amount / current_price
            sell_amount = amount

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
        fee = self._calculate_fee(sell_amount, actual_price, sell_shares, is_maker=False)
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
        side = _validate_side(side)
        amount = _validate_positive(float(amount), "amount")
        stop_loss = _validate_positive(float(stop_loss), "stop_loss")
        take_profit = _validate_positive(float(take_profit), "take_profit")

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
        return [o for o in self._orders.values() if o.status == "open"]

    def orders(self) -> list[PaperOrder]:
        """Return all orders (open, filled, and cancelled)."""
        return list(self._orders.values())

    def positions(self) -> list[PaperPosition]:
        """Return all live (unresolved) positions."""
        return [p for p in self._positions.values() if not p.resolved]

    def all_positions(self) -> list[PaperPosition]:
        """Return all positions including resolved ones."""
        return list(self._positions.values())

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
        outcome = outcome.upper()
        if outcome not in ("UP", "DOWN"):
            raise ValueError(f"outcome must be 'UP' or 'DOWN', got '{outcome}'")

        for pos in self._positions.values():
            if pos.market_id == market.id and not pos.resolved:
                pos.resolved = True
                pos.outcome  = "WON" if pos.side == outcome else "LOST"
                payout = pos.shares if pos.outcome == "WON" else 0.0
                self._balance += payout
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

        Example
        -------
        >>> stream = client.stream(market)
        >>> client.paper.attach_stream(stream, market)
        >>> stream.start(background=True)
        """
        @stream.on("price")
        def _on_price(up: float, down: float) -> None:
            self.check_limits(market.id, up, down)

        @stream.on("close")
        def _on_close() -> None:
            log.info(
                "Paper: stream closed for %s — call paper.resolve(market, outcome)",
                market.slug,
            )

        log.info("Paper: stream attached for %s", market.slug)

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
    ) -> PaperOrder:
        """Execute a simulated fill and update the position book."""
        if amount > self._balance:
            raise InsufficientBalance(
                f"Order amount ${amount:.2f} exceeds balance ${self._balance:.2f}"
            )

        # Calculate shares first (needed for fee calculation)
        net = amount  # Will subtract fee after calculation
        shares = round(net / price, SHARE_ROUNDING) if price > 0 else 0.0

        # Calculate fee using new method
        fee = self._calculate_fee(amount, price, shares, is_maker=is_limit)
        net = amount - fee
        shares = round(net / price, SHARE_ROUNDING) if price > 0 else 0.0

        self._balance -= amount

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
        )
        self._orders[order.id] = order

        self._upsert_position(market.id, market.slug, market.question, side, shares, price, order.id)
        log.info(
            "Paper: filled %s %.4f shares @ %.3f  fee=$%.4f  balance=$%.2f",
            side, shares, price, fee, self._balance,
        )
        return order

    def _fill_limit(self, order: PaperOrder, current_price: float) -> None:
        """Fill a pending limit order at *current_price* (balance already reserved)."""
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

        # Calculate fee using new method
        shares = round(order.amount / actual_price, SHARE_ROUNDING) if actual_price > 0 else 0.0
        fee = self._calculate_fee(order.amount, actual_price, shares, is_maker=True)
        net = order.amount - fee
        shares = round(net / actual_price, SHARE_ROUNDING) if actual_price > 0 else 0.0

        order.price     = actual_price
        order.shares    = shares
        order.fee       = fee
        order.status    = "filled"
        order.filled_at = _now()

        # Resolve the question string from any existing position in this market
        question = next(
            (p.question for p in self._positions.values() if p.market_id == order.market_id),
            "",
        )
        self._upsert_position(
            order.market_id, order.slug, question, order.side, shares, actual_price, order.id,
        )
        log.info(
            "Paper: limit filled %s %.4f shares @ %.3f  fee=$%.4f",
            order.side, shares, actual_price, fee,
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
    ) -> None:
        """Merge *shares* into an existing position or create a new one."""
        key = f"{market_id}:{side}"
        if key in self._positions:
            pos         = self._positions[key]
            total       = pos.shares + shares
            pos.avg_price = round(
                (pos.shares * pos.avg_price + shares * price) / total, PRICE_ROUNDING
            )
            pos.shares  = total
            pos.order_ids.append(order_id)
        else:
            self._positions[key] = PaperPosition(
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

def _validate_side(side: str) -> str:
    s = side.strip().upper()
    if s not in ("UP", "DOWN"):
        raise ValueError(f"side must be 'UP' or 'DOWN', got '{side!r}'")
    return s


def _validate_positive(value: float, name: str) -> float:
    if value <= 0:
        raise ValueError(f"{name} must be > 0, got {value}")
    return value


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
