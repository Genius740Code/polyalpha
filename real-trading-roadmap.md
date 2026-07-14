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
