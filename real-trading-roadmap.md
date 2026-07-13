# Real Trading with Cash Roadmap

This document outlines the plan for adding real trading with cash to the polyalpha SDK, including advanced position sizing strategies (fixed amount, percentage-based, Kelly criterion), risk management, and full wallet integration.

## Current State

### Existing Paper Trading Features
- **PaperEngine**: Simulated trading with virtual balance
- **Order Types**: Market orders, limit orders with advanced conditions
- **Fee Simulation**: Multiple fee modes (Polymarket, custom, zero)
- **Fee Rebates**: Volume-based rebate tiers with maker bonuses
- **Execution Realism**: Slippage, execution delays, fill probability
- **Advanced Orders**: Stop loss, take profit, trailing stops, OCO orders
- **Time Windows**: Restrict order execution to specific time periods
- **Database Integration**: Automatic trade persistence to SQLite
- **Position Tracking**: Real-time P&L calculation and position aggregation
- **Streaming Integration**: Auto-fill limit orders via WebSocket streams

### Gaps for Real Trading
- No real wallet integration or balance management
- No actual order execution via Polymarket CLOB API
- No position sizing strategies beyond fixed amounts
- No real risk management with actual funds
- No safety checks or confirmation dialogs for real money
- No transaction signing or authentication
- No real-time balance updates from blockchain

---

## Phase 1: Architecture & Core Infrastructure

### 1.1 RealTradingEngine Class Design ✅

```python
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
    """
    
    def __init__(
        self,
        private_key: str,
        rpc_url: str,
        polymarket_api_key: str,
        config: RealTradingConfig | None = None,
        db_path: str | None = None,
    ):
        # Wallet setup
        self._wallet: Web3.Wallet = ...
        self._usdc_contract: Contract = ...
        
        # Balance tracking
        self._balance: float = 0.0
        self._allowance: float = 0.0
        
        # Order management
        self._orders: dict[str, RealOrder] = {}
        self._positions: dict[str, RealPosition] = {}
        
        # Position sizing
        self._position_sizer: PositionSizer = ...
        
        # Risk management
        self._risk_manager: RiskManager = ...
        
        # CLOB client
        self._clob_client: ClobClient = ...
        
        # Database
        self._db: TradeDatabase | None = None
```

### 1.2 Configuration System ✅

```python
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
```

### 1.3 Wallet Integration ✅

**Features:**
- Connect to Polygon network via Web3.py
- Load USDC contract and check balance
- Manage CLOB token allowances
- Real-time balance updates
- Transaction signing and broadcasting

**API:**
```python
class WalletManager:
    def get_balance(self) -> float:
        """Get current USDC balance."""
        
    def get_allowance(self) -> float:
        """Get CLOB allowance for trading."""
        
    def approve_clob(self, amount: float) -> str:
        """Approve CLOB contract to spend USDC."""
        
    def refresh_balance(self) -> None:
        """Refresh balance from blockchain."""
        
    def wait_for_transaction(self, tx_hash: str) -> dict:
        """Wait for transaction confirmation."""
```

---

## Phase 2: Position Sizing Strategies

### 2.1 Position Sizer Interface ✅

```python
class PositionSizer(ABC):
    """Abstract base class for position sizing strategies."""
    
    @abstractmethod
    def calculate_size(
        self,
        balance: float,
        market: Market,
        side: str,
        confidence: float = 0.5,
        price: float | None = None,
    ) -> float:
        """Calculate position size in USDC."""
        pass

class FixedPositionSizer(PositionSizer):
    """Fixed amount position sizing."""
    
    def __init__(self, amount: float):
        self.amount = amount
        
    def calculate_size(self, balance: float, market: Market, side: str, 
                       confidence: float = 0.5, price: float | None = None) -> float:
        return min(self.amount, balance)

class PercentagePositionSizer(PositionSizer):
    """Percentage of balance position sizing."""
    
    def __init__(self, percentage: float):
        self.percentage = percentage
        
    def calculate_size(self, balance: float, market: Market, side: str,
                       confidence: float = 0.5, price: float | None = None) -> float:
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
        
    def calculate_size(self, balance: float, market: Market, side: str,
                       confidence: float = 0.5, price: float | None = None) -> float:
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
        
    def calculate_size(self, balance: float, market: Market, side: str,
                       confidence: float = 0.5, price: float | None = None) -> float:
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
```

### 2.2 Usage Examples ✅

```python
# Fixed amount sizing
client.real.set_position_sizer(FixedPositionSizer(amount=10.0))
order = client.real.buy(market, side="UP")  # Always $10

# Percentage sizing
client.real.set_position_sizer(PercentagePositionSizer(percentage=0.05))  # 5%
order = client.real.buy(market, side="UP")  # 5% of current balance

# Kelly criterion
client.real.set_position_sizer(KellyPositionSizer(kelly_fraction=0.25))
order = client.real.buy(market, side="UP", confidence=0.65)  # Size based on edge

# Hybrid sizing
client.real.set_position_sizer(HybridPositionSizer(
    base_strategy="percentage",
    base_amount=0.05,
    enable_kelly_adjustment=True,
    kelly_fraction=0.25,
))
order = client.real.buy(market, side="UP", confidence=0.70)
```

---

## Phase 3: Real Order Execution

### 3.1 CLOB API Integration ✅

```python
class ClobClient:
    """Client for Polymarket CLOB API."""
    
    def __init__(self, api_key: str, private_key: str, rpc_url: str):
        self.api_key = api_key
        self.private_key = private_key
        self.rpc_url = rpc_url
        self.base_url = "https://clob.polymarket.com"
        
    def place_order(
        self,
        token_id: str,
        side: str,
        price: float,
        size: float,
        order_type: str = "limit",
    ) -> dict:
        """Place an order on the CLOB."""
        
    def cancel_order(self, order_id: str) -> dict:
        """Cancel an order."""
        
    def get_order_status(self, order_id: str) -> dict:
        """Get order status."""
        
    def get_orderbook(self, token_id: str) -> dict:
        """Get current orderbook."""
        
    def get_balance(self) -> dict:
        """Get account balance."""
```

### 3.2 Real Order Dataclass ✅

```python
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
```

### 3.3 Real Position Dataclass ✅

```python
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
```

### 3.4 Order Execution Flow ✅

```python
def buy(
    self,
    market: Market,
    side: str,
    amount: float | None = None,
    confidence: float = 0.5,
    price: float | None = None,
    stop_loss: float | None = None,
    take_profit: float | None = None,
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
    # 1. Calculate position size
    if amount is None:
        amount = self._position_sizer.calculate_size(
            self._balance, market, side, confidence, price
        )
    
    # 2. Validate against risk limits
    self._risk_manager.validate_order(amount, self._balance, market)
    
    # 3. Check balance
    if amount > self._balance:
        raise InsufficientBalance(
            f"Order amount ${amount:.2f} exceeds balance ${self._balance:.2f}"
        )
    
    # 4. Get price
    if price is None:
        price = market.up_price if side == "UP" else market.down_price
    
    # 5. Calculate shares and fee
    shares, fee = self._calculate_shares_and_fee(amount, price)
    
    # 6. Require confirmation if enabled
    if confirm and self._config.require_confirmation:
        self._require_confirmation(market, side, amount, price, shares, fee)
    
    # 7. Place order on CLOB
    order_response = self._clob_client.place_order(
        token_id=market.token_id,
        side=side.lower(),
        price=price,
        size=shares,
        order_type="market" if price is None else "limit",
    )
    
    # 8. Create order object
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
    
    # 9. Update balance
    self._balance -= (amount + fee)
    
    # 10. Store order
    self._orders[order.id] = order
    
    # 11. Update position
    self._update_position(market, side, order)
    
    # 12. Save to database
    if self._db:
        self._save_order_to_db(order)
    
    return order
```

---

## Phase 4: Risk Management ✅

### 4.1 Risk Manager

ITS AN ADD ON TO PAPER TRADING

```python
class RiskManager:
    """Risk management for real trading."""
    
    def __init__(self, config: RealTradingConfig):
        self.config = config
        self.daily_pnl: float = 0.0
        self.daily_trades: int = 0
        self.daily_start_balance: float = 0.0
        
    def validate_order(
        self,
        amount: float,
        balance: float,
        market: Market,
    ) -> None:
        """Validate order against risk limits."""
        
        # Check max order size
        if amount > self.config.max_order_size:
            raise ValueError(
                f"Order amount ${amount:.2f} exceeds maximum ${self.config.max_order_size:.2f}"
            )
        
        # Check max position size
        current_exposure = self._get_market_exposure(market.id)
        if current_exposure + amount > self.config.max_position_size:
            raise ValueError(
                f"Position would exceed maximum size ${self.config.max_position_size:.2f}"
            )
        
        # Check max open positions
        if len(self._get_open_positions()) >= self.config.max_open_positions:
            raise ValueError(
                f"Maximum open positions ({self.config.max_open_positions}) reached"
            )
        
        # Check daily loss limit
        if self.daily_pnl < -self.config.max_daily_loss:
            raise ValueError(
                f"Daily loss ${abs(self.daily_pnl):.2f} exceeds limit ${self.config.max_daily_loss:.2f}"
            )
        
        # Check max risk per trade
        max_risk = balance * self.config.max_risk_per_trade
        if amount > max_risk:
            raise ValueError(
                f"Order amount ${amount:.2f} exceeds max risk ${max_risk:.2f} ({self.config.max_risk_per_trade:.1%})"
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
```

### 4.2 Stop Loss & Take Profit

```python
def set_stop_loss(
    self,
    market: Market,
    side: str,
    stop_price: float,
) -> None:
    """Set stop loss for a position."""
    
    position_key = f"{market.id}:{side}"
    if position_key not in self._positions:
        raise PositionNotFound(f"No position found for {market.slug} {side}")
    
    position = self._positions[position_key]
    position.stop_loss = stop_price
    
    log.info(f"Stop loss set at ${stop_price:.4f} for {market.slug} {side}")

def set_take_profit(
    self,
    market: Market,
    side: str,
    profit_price: float,
) -> None:
    """Set take profit for a position."""
    
    position_key = f"{market.id}:{side}"
    if position_key not in self._positions:
        raise PositionNotFound(f"No position found for {market.slug} {side}")
    
    position = self._positions[position_key]
    position.take_profit = profit_price
    
    log.info(f"Take profit set at ${profit_price:.4f} for {market.slug} {side}")

def set_trailing_stop(
    self,
    market: Market,
    side: str,
    trail_distance: float,
) -> None:
    """Set trailing stop loss."""
    
    position_key = f"{market.id}:{side}"
    if position_key not in self._positions:
        raise PositionNotFound(f"No position found for {market.slug} {side}")
    
    position = self._positions[position_key]
    position.trail_sl = trail_distance
    position.trail_sl_price = position.current_price - trail_distance if side == "UP" else position.current_price + trail_distance
    
    log.info(f"Trailing stop set at {trail_distance:.4f} distance for {market.slug} {side}")
```

---

## Phase 5: Safety Features

### 5.1 Confirmation Dialogs

```python
def _require_confirmation(
    self,
    market: Market,
    side: str,
    amount: float,
    price: float,
    shares: float,
    fee: float,
) -> None:
    """Require user confirmation before executing order."""
    
    print("\n" + "="*60)
    print("ORDER CONFIRMATION REQUIRED")
    print("="*60)
    print(f"Market:    {market.question}")
    print(f"Side:      {side}")
    print(f"Amount:    ${amount:.2f}")
    print(f"Price:     ${price:.4f}")
    print(f"Shares:    {shares:.4f}")
    print(f"Fee:       ${fee:.4f}")
    print(f"Total:     ${amount + fee:.2f}")
    print(f"Balance:   ${self._balance:.2f}")
    print("="*60)
    
    response = input("\nConfirm this order? (yes/no): ").strip().lower()
    
    if response not in ("yes", "y"):
        raise OrderCancelled("Order cancelled by user")
    
    print("Order confirmed.\n")
```

### 5.2 Pre-Trade Checks

```python
def pre_trade_checks(self, market: Market, side: str, amount: float) -> dict:
    """
    Run comprehensive pre-trade checks.
    
    Returns
    -------
    dict with check results and warnings
    """
    checks = {
        "balance_ok": True,
        "allowance_ok": True,
        "market_open": True,
        "price_reasonable": True,
        "warnings": [],
    }
    
    # Check balance
    if amount > self._balance:
        checks["balance_ok"] = False
        checks["warnings"].append(f"Insufficient balance: need ${amount:.2f}, have ${self._balance:.2f}")
    
    # Check CLOB allowance
    allowance = self._wallet.get_allowance()
    if allowance < amount:
        checks["allowance_ok"] = False
        checks["warnings"].append(f"Insufficient CLOB allowance: need ${amount:.2f}, have ${allowance:.2f}")
    
    # Check if market is still open
    if hasattr(market, 'end_time'):
        end_time = datetime.fromisoformat(market.end_time)
        if end_time < datetime.now(timezone.utc):
            checks["market_open"] = False
            checks["warnings"].append("Market has closed")
    
    # Check if price is reasonable
    price = market.up_price if side == "UP" else market.down_price
    if price < 0.01 or price > 0.99:
        checks["warnings"].append(f"Unusual price: ${price:.4f}")
    
    return checks
```

### 5.3 Emergency Stop

```python
def emergency_stop(self, reason: str = "Manual") -> None:
    """
    Emergency stop - cancel all open orders and prevent new trades.
    
    This is a safety mechanism to quickly halt all trading activity.
    """
    log.warning(f"EMERGENCY STOP: {reason}")
    
    # Cancel all open orders
    for order_id, order in self._orders.items():
        if order.status in ("open", "pending"):
            try:
                self._clob_client.cancel_order(order_id)
                order.status = "cancelled"
                log.info(f"Cancelled order {order_id}")
            except Exception as e:
                log.error(f"Failed to cancel order {order_id}: {e}")
    
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
```

---

## Phase 6: Database Integration

### 6.1 Extended Trade Schema

```python
# Add to existing trade database schema
ALTER TABLE trades ADD COLUMN sizing_strategy TEXT;
ALTER TABLE trades ADD COLUMN confidence REAL;
ALTER TABLE trades ADD COLUMN kelly_fraction REAL;
ALTER TABLE trades ADD COLUMN stop_loss REAL;
ALTER TABLE trades ADD COLUMN take_profit REAL;
ALTER TABLE trades ADD COLUMN tx_hash TEXT;
ALTER TABLE trades ADD COLUMN is_real_trade INTEGER DEFAULT 0;
ALTER TABLE trades ADD COLUMN wallet_address TEXT;
```

### 6.2 Real Trade Persistence

```python
def _save_order_to_db(self, order: RealOrder) -> None:
    """Save real order to database."""
    if not self._db:
        return
    
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
        # New fields
        sizing_strategy=order.sizing_strategy,
        confidence=order.confidence,
        kelly_fraction=order.kelly_fraction,
        stop_loss=order.stop_loss,
        take_profit=order.take_profit,
        tx_hash=order.tx_hash,
        is_real_trade=True,
        wallet_address=self._wallet.address,
    )
```

---

## Phase 7: Error Handling & Retry Logic

### 7.1 Retry Decorator

```python
def retry_on_error(max_attempts: int = 3, delay: float = 1.0):
    """Decorator for retrying failed operations."""
    def decorator(func):
        @functools.wraps(func)
        def wrapper(*args, **kwargs):
            last_error = None
            for attempt in range(max_attempts):
                try:
                    return func(*args, **kwargs)
                except (TransientError, NetworkError, TimeoutError) as e:
                    last_error = e
                    if attempt < max_attempts - 1:
                        log.warning(f"Attempt {attempt + 1} failed: {e}. Retrying in {delay}s...")
                        time.sleep(delay * (2 ** attempt))  # Exponential backoff
                    else:
                        log.error(f"All {max_attempts} attempts failed")
                        raise
                except Exception as e:
                    # Don't retry on non-transient errors
                    log.error(f"Non-retryable error: {e}")
                    raise
            raise last_error
        return wrapper
    return decorator
```

### 7.2 Error Classes

```python
class TradingError(Exception):
    """Base class for trading errors."""
    pass

class InsufficientBalance(TradingError):
    """Insufficient balance for trade."""
    pass

class InsufficientAllowance(TradingError):
    """Insufficient CLOB allowance."""
    pass

class OrderRejected(TradingError):
    """Order rejected by CLOB."""
    pass

class OrderTimeout(TradingError):
    """Order timed out."""
    pass

class NetworkError(TradingError):
    """Network connectivity error."""
    pass

class TransientError(TradingError):
    """Transient error that can be retried."""
    pass

class PositionNotFound(TradingError):
    """Position not found."""
    pass

class RiskLimitExceeded(TradingError):
    """Risk management limit exceeded."""
    pass
```

---

## Phase 8: Client Integration

### 8.1 Updated Client Class

```python
class Client:
    def __init__(
        self,
        balance: float = 100.0,
        timeout: int = 10,
        retries: int = 3,
        log_level: str = "WARNING",
        rate_limit: int | None = None,
        paper_config: PaperConfig | None = None,
        db_path: str | None = None,
        openrouter_api_key: str | None = None,
        # Real trading parameters
        private_key: str | None = None,
        rpc_url: str | None = None,
        polymarket_api_key: str | None = None,
        real_config: RealTradingConfig | None = None,
    ):
        # ... existing initialization ...
        
        self.markets = MarketClient(timeout=timeout, retries=retries, rate_limit=rate_limit)
        self.paper = PaperEngine(balance=balance, config=paper_config, db_path=db_path)
        self.ai = OpenRouterClient(api_key=openrouter_api_key) if openrouter_api_key else None
        self._clob = ClobBookClient(timeout=timeout, retries=retries, rate_limit=rate_limit)
        
        # Real trading (optional)
        self.real: RealTradingEngine | None = None
        if private_key and rpc_url and polymarket_api_key:
            self.real = RealTradingEngine(
                private_key=private_key,
                rpc_url=rpc_url,
                polymarket_api_key=polymarket_api_key,
                config=real_config,
                db_path=db_path,
            )
```

### 8.2 Usage Example

```python
import polyalpha

# Paper trading (existing)
client = polyalpha.Client(balance=100.0)
order = client.paper.buy(market, side="UP", amount=10.0)

# Real trading (new)
client = polyalpha.Client(
    private_key="your-private-key",
    rpc_url="https://polygon-rpc.com",
    polymarket_api_key="your-api-key",
    real_config=polyalpha.RealTradingConfig(
        position_sizing="kelly",
        kelly_fraction=0.25,
        max_order_size=100.0,
        require_confirmation=True,
    ),
)

# Refresh balance
client.real.refresh_balance()
print(f"Balance: ${client.real.balance:.2f}")

# Approve CLOB (first time only)
client.real.approve_clob(amount=1000.0)

# Trade with Kelly sizing
order = client.real.buy(
    market,
    side="UP",
    confidence=0.65,  # 65% confidence
    stop_loss=0.85,   # Stop at $0.85
    take_profit=0.95, # Take profit at $0.95
)

# Check positions
positions = client.real.positions()
for pos in positions:
    print(f"{pos.slug} {pos.side}: ${pos.pnl:+.2f} ({pos.pnl_pct:+.1f}%)")

# Emergency stop if needed
client.real.emergency_stop("Manual intervention")
```

---

## Phase 9: Auto-Redeem System

### 9.1 AutoRedeemConfig

```python
@dataclass
class AutoRedeemConfig:
    """Configuration for automatic token redemption."""
    
    # Enable/disable
    enabled: bool = True
    
    # Trigger modes
    trigger_on_time: bool = True
    trigger_on_count: bool = True
    trigger_on_value: bool = False
    
    # Time-based triggers
    time_interval: str = "1d"        # "1h", "6h", "1d", "1w"
    redeem_at_time: str | None = None # Specific time "14:00" UTC
    
    # Count-based triggers
    min_markets: int = 10            # Redeem after N resolved markets
    max_markets: int = 100           # Force redeem after N (safety)
    
    # Value-based triggers
    min_value_usd: float = 100.0     # Redeem when value >= $100
    max_value_usd: float = 10000.0  # Force redeem at $10k (safety)
    
    # Safety settings
    require_confirmation: bool = False  # Confirm before redeeming
    max_gas_price: float = 50.0     # Max gas price in Gwei
    dry_run: bool = False           # Simulate without executing
    
    # Filtering
    only_winning: bool = False      # Only redeem winning positions
    min_age_hours: int = 1          # Wait N hours after resolution
```

### 9.2 AutoRedeemEngine

```python
class AutoRedeemEngine:
    """
    Automatic redemption engine for resolved Polymarket positions.
    
    Features:
    - Monitors positions for resolution status
    - Executes redemption based on configured triggers
    - Supports paper and real trading modes
    - Provides detailed logging and history
    """
    
    def __init__(
        self,
        trading_engine: PaperEngine | RealTradingEngine,
        config: AutoRedeemConfig,
    ):
        self._trading = trading_engine
        self._config = config
        self._redeem_history: list[RedeemRecord] = []
        self._resolved_queue: set[str] = set()
        
    def check_positions(self) -> list[RedeemablePosition]:
        """Scan positions and return those ready for redemption."""
        
    def redeem(self, positions: list[RedeemablePosition] | None = None) -> RedeemResult:
        """Execute redemption for specified positions."""
        
    def start_scheduler(self) -> None:
        """Start background scheduler for time-based triggers."""
        
    def stop_scheduler(self) -> None:
        """Stop background scheduler."""
        
    def get_redeem_history(self) -> list[RedeemRecord]:
        """Get history of redemption operations."""
        
    def get_pending_count(self) -> int:
        """Get count of positions awaiting redemption."""
```

### 9.3 Data Structures

```python
@dataclass
class RedeemablePosition:
    """A position that is ready for redemption."""
    market_id: str
    slug: str
    side: str
    shares: float
    outcome: str  # "WON" or "LOST"
    value_usd: float
    resolved_at: datetime
    token_id: str

@dataclass
class RedeemRecord:
    """Record of a redemption operation."""
    timestamp: datetime
    positions_count: int
    total_value_usd: float
    trigger_reason: str  # "time", "count", "value", "manual"
    success: bool
    tx_hash: str | None = None
    error: str | None = None

@dataclass
class RedeemResult:
    """Result of a redemption operation."""
    success: bool
    redeemed_count: int
    total_value_usd: float
    failed_count: int
    errors: list[str]
    tx_hash: str | None = None
```

### 9.4 Integration

```python
# Paper trading
client.paper.set_auto_redeem_config(AutoRedeemConfig(
    time_interval="1d",
    min_value_usd=100.0,
))
client.paper.auto_redeem.start_scheduler()

# Real trading
client.real.set_auto_redeem_config(AutoRedeemConfig(
    time_interval="6h",
    min_markets=5,
    require_confirmation=True,
))
client.real.auto_redeem.start_scheduler()
```

### 9.5 Usage Examples

```python
# Simple daily auto-redeem
config = AutoRedeemConfig(
    time_interval="1d",
    min_value_usd=100.0,
)

# Multi-trigger configuration
config = AutoRedeemConfig(
    trigger_on_time=True,
    trigger_on_count=True,
    trigger_on_value=True,
    time_interval="6h",
    min_markets=5,
    max_markets=20,
    min_value_usd=50.0,
    max_value_usd=500.0,
)

# Manual check and redeem
positions = client.paper.auto_redeem.check_positions()
result = client.paper.auto_redeem.redeem(positions)

# View history
history = client.paper.auto_redeem.get_redeem_history()
```

---

## Implementation Priority

### Phase 1 (Week 1-2): Core Infrastructure
1. RealTradingEngine class design
2. Wallet integration (Web3.py, USDC contract)
3. CLOB API client
4. Basic configuration system
5. Safety checks and confirmations

### Phase 2 (Week 3): Position Sizing
1. PositionSizer interface
2. FixedPositionSizer
3. PercentagePositionSizer
4. KellyPositionSizer
5. HybridPositionSizer
6. Integration with buy/sell methods

### Phase 3 (Week 4): Order Execution
1. Real order dataclass
2. Real position dataclass
3. Order execution flow
4. Transaction signing
5. Balance updates
6. Error handling

### Phase 4 (Week 5): Risk Management
1. RiskManager class
2. Stop loss implementation
3. Take profit implementation
4. Trailing stops
5. Position limits
6. Daily loss limits

### Phase 5 (Week 6): Safety Features
1. Confirmation dialogs
2. Pre-trade checks
3. Emergency stop
4. Transaction logging
5. Balance monitoring

### Phase 6 (Week 7): Database Integration
1. Extended trade schema
2. Real trade persistence
3. Wallet address tracking
3. Transaction hash tracking
4. Position sizing metadata

### Phase 7 (Week 8): Error Handling
1. Retry logic
2. Error classes
3. Network error handling
4. Timeout handling
5. Graceful degradation

### Phase 8 (Week 9): Client Integration
1. Updated Client class
2. Unified API
3. Documentation
4. Examples
5. Testing

---

## Dependencies

### New Dependencies
- **web3**: For blockchain interaction
- **eth-account**: For transaction signing
- **requests**: For CLOB API calls (already likely present)

### Optional Dependencies
- **python-dotenv**: For environment variable management
- **keyring**: For secure key storage

---

## Security Considerations

1. **Private Key Security**
   - Never hardcode private keys
   - Use environment variables or secure storage
   - Consider hardware wallet integration

2. **Transaction Safety**
   - Always require confirmation for large orders
   - Implement maximum order size limits
   - Add emergency stop functionality

3. **API Key Security**
   - Store API keys securely
   - Rotate keys regularly
   - Use different keys for development/production

4. **Network Security**
   - Use HTTPS for all API calls
   - Validate RPC URLs
   - Consider using VPN for trading

5. **Audit Trail**
   - Log all transactions
   - Save all trades to database
   - Implement trade reconciliation

---

## Testing Strategy

### Unit Tests
- Test position sizing calculations
- Test risk management validation
- Test fee calculations
- Test error handling

### Integration Tests
- Test wallet connection (testnet)
- CLOB API integration (testnet)
- Transaction signing (testnet)
- Order execution (testnet)

### Paper Trading Tests
- Test real trading features in paper mode first
- Validate position sizing strategies
- Test risk management

### Manual Testing
- Small test trades on mainnet
- Verify balance updates
- Test emergency stop
- Validate database records

---

## Documentation

### User Documentation
- Getting started with real trading
- Wallet setup guide
- API key management
- Position sizing strategies
- Risk management best practices
- Safety features guide

### API Documentation
- RealTradingEngine API reference
- PositionSizer API reference
- RiskManager API reference
- Configuration options

### Examples
- Basic real trading example
- Kelly criterion example
- Risk management example
- Emergency procedures example

---

## Open Questions

1. **Should we support testnet trading first?**
   - Pros: Safer for testing, no real money at risk
   - Cons: Additional complexity, testnet may not mirror mainnet exactly

2. **Should we implement hardware wallet support?**
   - Pros: Enhanced security
   - Cons: Additional complexity, user experience impact

3. **Should we support multiple wallets?**
   - Pros: Portfolio segregation, risk management
   - Cons: Additional complexity

4. **Should we implement automatic position sizing based on market conditions?**
   - Pros: Adaptive risk management
   - Cons: More complex, harder to validate

5. **Should we add social trading/copy trading features?**
   - Pros: Community features
   - Cons: Privacy concerns, additional complexity

---

## Timeline Estimates

- **Phase 1 (Core Infrastructure)**: 2 weeks
- **Phase 2 (Position Sizing)**: 1 week
- **Phase 3 (Order Execution)**: 1 week
- **Phase 4 (Risk Management)**: 1 week
- **Phase 5 (Safety Features)**: 1 week
- **Phase 6 (Database Integration)**: 1 week
- **Phase 7 (Error Handling)**: 1 week
- **Phase 8 (Client Integration)**: 1 week
- **Testing & Documentation**: 2 weeks

**Total**: ~11 weeks

---

## Contributing

When contributing real trading features:

1. **Security First**: All changes must be security-focused
2. **Test Thoroughly**: Test on testnet before mainnet
3. **Document**: Update all documentation
4. **Safety Checks**: Add safety checks for all money operations
5. **Error Handling**: Handle all error cases gracefully
6. **Logging**: Log all money operations
7. **Review**: All real trading code requires additional review

---

## Changelog

### v0.3.0 (Planned)
- Real trading with cash
- Position sizing strategies (fixed, percentage, Kelly)
- Risk management (stop loss, take profit, position limits)
- Wallet integration
- CLOB API integration
- Safety features and confirmations
- Extended database schema for real trades
