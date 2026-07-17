# Paper Trading

`client.paper` is a `PaperEngine` that simulates Polymarket orders locally. No wallet, private key, or real money is involved. It tracks positions, applies configurable fees, and computes P&L against live market prices.

---

## Quick start

```python
client = polyalpha.Client(balance=500.0)

market = client.markets.latest("BTC", "5m")

# Buy $25 on the UP side
order = client.paper.buy(market, side="UP", amount=25.0)
print(order)

# See your positions and total P&L
client.paper.summary()
```

---

## Configuration

Paper trading supports advanced configuration for realistic simulation:

```python
from polyalpha.trading.paper import PaperConfig

# Create a custom configuration
config = PaperConfig(
    fee_mode="polymarket",  # "polymarket", "custom", or "zero"
    market_category="crypto",  # For polymarket mode
    custom_fee_rate=0.02,  # 2% for custom mode
    execution_delay_ms=2000,  # 2 second execution delay
    slippage_pct=0.05,  # 5% slippage
    fill_probability=0.8,  # 80% fill probability for limit orders
    enable_rebates=True,  # Enable fee rebate tracking
    rebate_tiers={  # Volume-based rebate tiers
        0: 0.00,    # $0 - $1000: 0% rebate
        1000: 0.10,  # $1000 - $5000: 10% rebate
        5000: 0.15,  # $5000 - $10000: 15% rebate
        10000: 0.20, # $10000+: 20% rebate
    },
    maker_rebate_pct=0.25,  # Additional 25% rebate for maker orders
)

# Use with client
client = polyalpha.Client(balance=500.0, paper_config=config)
```

---

## Configuration from Environment Variables

You can load paper trading configuration from environment variables for easy configuration without code changes:

```python
import polyalpha
from polyalpha.core.env import load_env_file

# Load from .env file
load_env_file()

# Create client with config from environment
client = polyalpha.Client(balance=500.0, paper_config_from_env=True)
```

### Available Environment Variables

**Fee Configuration:**
- `POLYALPHA_PAPER_FEE_MODE`: Fee mode ("polymarket", "custom", "zero", default: "custom")
- `POLYALPHA_PAPER_MARKET_CATEGORY`: Market category for polymarket fees (default: "crypto")
- `POLYALPHA_PAPER_CUSTOM_FEE_RATE`: Custom fee rate (default: 0.02)
- `POLYALPHA_PAPER_MAKER_FEE_RATE`: Maker fee rate (default: 0.0)

**Fee Rebate Configuration:**
- `POLYALPHA_PAPER_ENABLE_REBATES`: Enable fee rebates (bool, default: True)
- `POLYALPHA_PAPER_MAKER_REBATE_PCT`: Maker rebate percentage (default: 0.25)

**Execution Simulation:**
- `POLYALPHA_PAPER_EXECUTION_DELAY_MS`: Execution delay in milliseconds (default: 0)
- `POLYALPHA_PAPER_DELAY_RANDOMNESS`: Delay randomness 0-1 (default: 0.0)
- `POLYALPHA_PAPER_SLIPPAGE_PCT`: Slippage percentage (default: 0.0)
- `POLYALPHA_PAPER_SLIPPAGE_RANDOMNESS`: Slippage randomness 0-1 (default: 0.0)
- `POLYALPHA_PAPER_MAX_SLIPPAGE_NO_FILL`: Max slippage before no fill 0-1 (default: 0.10)
- `POLYALPHA_PAPER_FILL_PROBABILITY`: Fill probability 0-1 (default: 1.0)
- `POLYALPHA_PAPER_CHECK_MODE`: Condition check mode (default: "continuous")

**Risk Management:**
- `POLYALPHA_PAPER_ENABLE_RISK_MANAGEMENT`: Enable risk checks (bool, default: True)
- `POLYALPHA_PAPER_MAX_DAILY_LOSS`: Maximum daily loss (default: 500.0)
- `POLYALPHA_PAPER_MAX_TRADES_PER_DAY`: Maximum trades per day (default: 100)
- `POLYALPHA_PAPER_MAX_ORDER_SIZE`: Maximum order size (default: 1000.0)
- `POLYALPHA_PAPER_MAX_POSITION_SIZE`: Maximum position size (default: 2000.0)
- `POLYALPHA_PAPER_MAX_OPEN_POSITIONS`: Maximum open positions (default: 10)
- `POLYALPHA_PAPER_MAX_RISK_PER_TRADE`: Maximum risk per trade 0-1 (default: 0.02)

### Example .env File

```bash
# Paper Trading Configuration
POLYALPHA_PAPER_FEE_MODE=polymarket
POLYALPHA_PAPER_MARKET_CATEGORY=crypto
POLYALPHA_PAPER_EXECUTION_DELAY_MS=2000
POLYALPHA_PAPER_SLIPPAGE_PCT=0.03
POLYALPHA_PAPER_FILL_PROBABILITY=0.85
POLYALPHA_PAPER_ENABLE_REBATES=true
POLYALPHA_PAPER_ENABLE_RISK_MANAGEMENT=true
POLYALPHA_PAPER_MAX_DAILY_LOSS=500.0
POLYALPHA_PAPER_MAX_RISK_PER_TRADE=0.02
```

---

## Configuration Presets

Paper trading includes pre-configured presets for common trading strategies:

```python
from polyalpha.trading.paper_config import get_paper_config_from_preset, list_presets

# List available presets
print(list_presets())
# Output: ['CONSERVATIVE', 'REALISTIC', 'AGGRESSIVE', 'ZERO_FEE', 'HIGH_LATENCY', 'LIQUIDITY_PROVIDER', 'SCALPER', 'TEST']

# Use a preset
config = get_paper_config_from_preset("REALISTIC")
client = polyalpha.Client(balance=1000.0, paper_config=config)
```

### Available Presets

- **CONSERVATIVE**: Low risk, low slippage, realistic fees. Good for testing strategies safely.
- **REALISTIC**: Balanced configuration matching typical Polymarket conditions.
- **AGGRESSIVE**: Higher risk tolerance, higher slippage, more trades allowed.
- **ZERO_FEE**: No fees for testing strategy logic without cost impact.
- **HIGH_LATENCY**: Simulates slow execution with high delays and slippage.
- **LIQUIDITY_PROVIDER**: Maker-focused configuration with enhanced rebates.
- **SCALPER**: Fast execution, low slippage, high trade frequency for scalping strategies.
- **TEST**: No restrictions, no fees, unlimited trades for testing and development.

### Preset Details

**CONSERVATIVE:**
- Fees: Polymarket realistic
- Execution delay: 500ms ±10%
- Slippage: 1% ±5%
- Max daily loss: $100
- Max trades per day: 20
- Max risk per trade: 1%

**REALISTIC:**
- Fees: Polymarket realistic
- Execution delay: 2000ms ±20%
- Slippage: 3% ±10%
- Max daily loss: $500
- Max trades per day: 100
- Max risk per trade: 2%

**AGGRESSIVE:**
- Fees: Custom 2%
- Execution delay: 100ms ±30%
- Slippage: 5% ±20%
- Max daily loss: $1000
- Max trades per day: 200
- Max risk per trade: 5%

**ZERO_FEE:**
- Fees: None
- Execution delay: 0ms
- Slippage: 0%
- Fill probability: 100%
- Risk management: Enabled

**HIGH_LATENCY:**
- Fees: Custom 2%
- Execution delay: 5000ms ±50%
- Slippage: 8% ±30%
- Max daily loss: $500
- Max trades per day: 50

**LIQUIDITY_PROVIDER:**
- Fees: Custom 1%
- Enhanced rebates: 35% maker bonus
- Execution delay: 1000ms ±15%
- Slippage: 2% ±5%
- Max trades per day: 150

**SCALPER:**
- Fees: Custom 2%
- Execution delay: 50ms ±10%
- Slippage: 2% ±5%
- Max trades per day: 500
- Max risk per trade: 0.5%

**TEST:**
- Fees: None
- Execution delay: 0ms
- Slippage: 0%
- Risk management: Disabled
- Unlimited trades and positions

---

## Fee Rebate System

The paper trading engine includes a comprehensive fee rebate system that tracks and rewards trading volume. Rebates reduce your effective trading costs based on your cumulative trading volume and order type.

### How Rebates Work

1. **Volume-Based Tiers**: As your total trading volume increases, you qualify for higher rebate percentages
2. **Maker Bonus**: Limit orders (maker orders) receive an additional rebate percentage on top of volume tiers
3. **Automatic Tracking**: All fees and rebates are tracked automatically and displayed in summaries

### Configuration

```python
from polyalpha.trading.paper import PaperConfig

config = PaperConfig(
    enable_rebates=True,  # Enable/disable rebate tracking
    rebate_tiers={
        0: 0.00,    # $0 - $1000: 0% rebate
        1000: 0.10,  # $1000 - $5000: 10% rebate
        5000: 0.15,  # $5000 - $10000: 15% rebate
        10000: 0.20, # $10000+: 20% rebate
    },
    maker_rebate_pct=0.25,  # Additional 25% for maker orders
)
```

### Viewing Rebate Statistics

```python
# Get detailed fee and rebate summary
client.paper.fee_summary()

# Get rebate statistics as a dictionary
stats = client.paper.get_rebate_stats()
print(f"Total volume: ${stats['total_volume']:.2f}")
print(f"Total fees paid: ${stats['total_fees_paid']:.4f}")
print(f"Total rebates earned: ${stats['total_rebates_earned']:.4f}")
print(f"Net fees: ${stats['net_fees']:.4f}")
print(f"Effective fee rate: {stats['effective_fee_rate']:.2%}")
print(f"Current rebate tier: {stats['current_rebate_rate']:.1%}")
```

### Order-Level Rebate Information

Each order tracks its individual rebate:

```python
order = client.paper.buy(market, side="UP", amount=25.0)
print(f"Fee type: {order.fee_type}")  # "taker" or "maker"
print(f"Rebate amount: ${order.rebate_amount:.4f}")
print(f"Rebate rate: {order.rebate_rate:.1%}")
print(f"Net fee: ${order.fee - order.rebate_amount:.4f}")
```

### Example Output

```
──────────────────────────────────────────────────────────────────
  POLYALPHA — FEE & REBATE SUMMARY
──────────────────────────────────────────────────────────────────
  Total volume              $   1250.00
  Total fees paid           $      25.0000
  Total rebates earned      $       2.5000
  Net fees (after rebates)  $      22.5000
  Effective fee rate       1.80%
──────────────────────────────────────────────────────────────────
  Taker fees                $      15.0000
  Taker rebates             $       1.5000
  Maker fees                $      10.0000
  Maker rebates             $       1.0000
──────────────────────────────────────────────────────────────────
  Current volume rebate tier: 10.0%
  Volume thresholds:
      $     0+:  0.0%
      $  1000+: 10.0% ← current
      $  5000+: 15.0%
      $ 10000+: 20.0%
──────────────────────────────────────────────────────────────────
```

### Benefits

- **Cost Reduction**: High-volume traders can significantly reduce their effective fee rates
- **Maker Incentive**: Limit orders provide liquidity and earn additional rebates
- **Transparency**: Full visibility into fee breakdown and rebate calculations
- **Configurability**: Customize rebate tiers to match your trading strategy

---

## Placing orders

### Buy

```python
order = client.paper.buy(market, side="UP", amount=25.0)
order = client.paper.buy(market, side="DOWN", amount=10.0)
```

| Parameter | Type | Description |
|---|---|---|
| `market` | `Market` | The market returned by `client.markets.latest()` |
| `side` | `str` | `"UP"` or `"DOWN"` (case-insensitive) |
| `amount` | `float` | USDC to spend |

**What happens:**

1. A 2% taker fee is deducted from `amount`
2. The remaining USDC is converted to shares at the current mid-price
3. Your balance decreases by `amount`
4. A `PaperOrder` is created and returned
5. A `PaperPosition` is opened (or added to an existing one for that market+side)

**Raises** `InsufficientBalance` if your balance is too low.

### Sell

```python
order = client.paper.sell(market, side="UP", shares=50.0)
```

| Parameter | Type | Description |
|---|---|---|
| `market` | `Market` | The market to sell in |
| `side` | `str` | `"UP"` or `"DOWN"` |
| `shares` | `float` | Number of shares to sell |

Sells at the current mid-price minus the 2% fee. Your balance increases by the proceeds. Raises `InsufficientBalance` if you don't hold enough shares.

---

## The PaperOrder object

`client.paper.buy()` and `client.paper.sell()` both return a `PaperOrder`.

| Attribute | Type | Description |
|---|---|---|
| `order.id` | `str` | Unique UUID for this order |
| `order.market_slug` | `str` | Slug of the market |
| `order.side` | `str` | `"UP"` or `"DOWN"` |
| `order.direction` | `str` | `"BUY"` or `"SELL"` |
| `order.amount_usdc` | `float` | USDC spent (buy) or received (sell) |
| `order.shares` | `float` | Shares filled |
| `order.fill_price` | `float` | Price at which the order was filled |
| `order.fee` | `float` | Fee charged in USDC |
| `order.timestamp` | `str` | ISO-8601 fill time |

---

## The PaperPosition object

Each open position is tracked as a `PaperPosition`.

| Attribute | Type | Description |
|---|---|---|
| `position.market_slug` | `str` | Slug of the market |
| `position.side` | `str` | `"UP"` or `"DOWN"` |
| `position.shares` | `float` | Current share balance |
| `position.avg_cost` | `float` | Average cost basis per share |
| `position.total_cost` | `float` | Total USDC invested |
| `position.realized_pnl` | `float` | P&L locked in from sells |

To compute unrealized P&L, pass the current price:

```python
position = client.paper.positions[0]
unrealized = position.unrealized_pnl(current_price=market.up_price)
```

---

## Inspecting your state

### Balance

```python
print(client.paper.balance)  # float — current USDC balance
```

### All orders

```python
orders = client.paper.orders  # list[PaperOrder]
for o in orders:
    print(o.id, o.side, o.shares, o.fill_price)
```

### All positions

```python
positions = client.paper.positions  # list[PaperPosition]
for p in positions:
    print(p.market_slug, p.side, p.shares, p.avg_cost)
```

### Print a summary

```python
client.paper.summary()
```

Prints balance, all open positions with live P&L, and a total P&L line.

---

## Fees

Paper trading supports three fee modes:

### 1. Polymarket Mode (Realistic)
Uses Polymarket's actual fee structure based on market category:

```python
config = PaperConfig(
    fee_mode="polymarket",
    market_category="crypto",  # crypto, sports, geopolitical, etc.
)
```

**Fee structure:**
- **Geopolitical markets**: 0% fee
- **Sports markets**: Peak 0.75% at 50/50 price
- **Crypto/Finance/Politics/Tech**: Peak 1.80% at 50/50 price
- **Formula**: `fee = C × p × feeRate × (p × (1 − p))^exponent`
- Fees are symmetric around p = 0.50 and decrease at extremes
- Rounded to 4 decimal places

### 2. Custom Mode
Use a fixed fee rate:

```python
config = PaperConfig(
    fee_mode="custom",
    custom_fee_rate=0.02,  # 2% fee
)
```

### 3. Zero Mode
No fees at all:

```python
config = PaperConfig(
    fee_mode="zero",
)
```

**Default behavior:** If no config is provided, uses custom mode with 2% fee.

**Buy example** — spending $100 with 2% fee:
- Fee: $100 × 0.02 = $2.00
- Net USDC invested: $98.00
- Shares at fill price 0.55: $98 / 0.55 ≈ 178.18 shares

---

## Execution Delay

Simulate realistic execution latency:

```python
config = PaperConfig(
    execution_delay_ms=2000,  # 2 second delay
    delay_randomness=0.2,  # ±20% randomness
)
```

This means when you place an order, it will execute after 2 seconds (±20% random variation) at whatever the price is at that time. This simulates:
- Network latency
- Order routing time
- Exchange processing time

**Note:** If you buy at 0.90 and the price moves to 0.91 during the delay, you'll fill at 0.91.

---

## Slippage

Simulate price impact and partial fills:

```python
config = PaperConfig(
    slippage_pct=0.05,  # 5% slippage
    slippage_randomness=0.1,  # ±10% randomness
    max_slippage_no_fill=0.10,  # Don't fill if price moves >10%
)
```

**How it works:**
- If slippage is 5% and you buy UP at 0.90, you might fill at 0.945 (worse price)
- If the price moves beyond `max_slippage_no_fill`, the order won't fill
- Slippage is direction-aware: UP orders get higher prices, DOWN orders get lower prices

---

## Fill Probability

Limit orders don't always fill in real trading. Simulate this:

```python
config = PaperConfig(
    fill_probability=0.7,  # 70% chance limit orders fill
)
```

When a limit order is triggered, there's a 70% chance it fills. If it doesn't fill, the order is cancelled and balance is refunded.

---

## Condition Check Mode

Control how many times limit orders check their conditions before giving up:

```python
config = PaperConfig(
    check_mode="continuous",  # Check continuously (default)
    # check_mode="once",      # Only check once
    # check_mode=5,           # Check exactly 5 times
)
```

**Modes:**
- **"continuous"** (default): Orders check conditions on every price update until filled or cancelled
- **"once"**: Orders only check conditions once - if not met, they're skipped on subsequent updates
- **int N**: Orders check conditions up to N times, then stop checking

**Use cases:**
- **"once"**: For one-time entry signals (e.g., "if BTC > $15k at market open, buy once")
- **N times**: For limited retry attempts (e.g., "check 3 times for price to cross threshold")
- **"continuous"**: For standard limit orders that wait indefinitely

### Example: Check Once

```python
# Only check if BTC price is above $15k once
config = PaperConfig(check_mode="once")

client = polyalpha.Client(balance=500.0, paper_config=config)
market = client.markets.latest("BTC", "5m")

# This order will only check its condition once
order = client.paper.limit(market, side="UP", price=0.92, amount=25.0)

stream = client.stream(market)
client.paper.attach_stream(stream, market)
stream.start(background=True)
# If price doesn't cross 0.92 on the first check, order won't fill even if it crosses later
```

### Example: Check N Times

```python
# Check conditions exactly 5 times
config = PaperConfig(check_mode=5)

client = polyalpha.Client(balance=500.0, paper_config=config)

order = client.paper.limit(market, side="UP", price=0.92, amount=25.0)
# Order will check up to 5 times, then stop checking even if still open
```

### Check Count Tracking

Each order tracks how many times it has been checked:

```python
order = client.paper.limit(market, side="UP", price=0.92, amount=25.0)
print(order.check_count)  # 0 initially

# After stream runs and checks conditions
print(order.check_count)  # Increments with each check
```

---

## Complete Configuration Example

```python
from polyalpha.trading.paper import PaperConfig

# Realistic Polymarket simulation
config = PaperConfig(
    fee_mode="polymarket",
    market_category="crypto",
    execution_delay_ms=2000,
    delay_randomness=0.2,
    slippage_pct=0.03,
    slippage_randomness=0.1,
    max_slippage_no_fill=0.10,
    fill_probability=0.8,
)

client = polyalpha.Client(balance=1000.0, paper_config=config)
```

---

## Practical patterns

### Flat dollar-cost average

```python
market = client.markets.latest("BTC", "5m")
stream = client.stream(market)
tick = 0

@stream.on("price")
def on_price(up, down):
    global tick
    tick += 1
    if tick % 10 == 0:  # every 10 ticks
        client.paper.buy(market, side="UP", amount=5.0)
        client.paper.summary()

stream.start()
```

### Momentum entry

```python
prices = []

@stream.on("price")
def on_price(up, down):
    prices.append(up)
    if len(prices) < 5:
        return
    if prices[-1] > prices[-5]:  # price rising
        client.paper.buy(market, side="UP", amount=20.0)

stream.start()
```

### Close a position on resolve

```python
@stream.on("close")
def on_close():
    for pos in client.paper.positions:
        if pos.shares > 0:
            client.paper.sell(market, side=pos.side, shares=pos.shares)
    client.paper.summary()

stream.start()
```

### Track P&L live

```python
@stream.on("price")
def on_price(up, down):
    for pos in client.paper.positions:
        price = up if pos.side == "UP" else down
        pnl = pos.unrealized_pnl(price)
        print(f"{pos.side} {pos.shares:.2f} shares  unrealized={pnl:+.4f}")
```

---

## Starting fresh

If you want to reset the paper engine during a session:

```python
client.paper.reset()  # clears orders, positions, restores original balance
```

---

## Risk Management

Paper trading includes built-in risk management features to help you simulate realistic trading constraints and protect your paper trading account from excessive losses.

### Configuration

Risk management is configured through `PaperConfig`:

```python
from polyalpha.trading.paper import PaperConfig

config = PaperConfig(
    enable_risk_management=True,  # Enable/disable risk checks
    max_daily_loss=500.0,         # Stop trading if daily loss exceeds $500
    max_trades_per_day=100,       # Maximum 100 trades per day
    max_order_size=1000.0,        # Maximum $1000 per order
    max_position_size=2000.0,     # Maximum $2000 position per market
    max_open_positions=10,        # Maximum 10 concurrent positions
    max_risk_per_trade=0.02,      # Maximum 2% of balance per trade
)

client = polyalpha.Client(balance=1000.0, paper_config=config)
```

### Risk Limits

The following risk limits are enforced:

- **Max Daily Loss**: Stops trading when cumulative daily P&L drops below this threshold
- **Max Trades Per Day**: Limits the number of orders you can place per calendar day
- **Max Order Size**: Prevents placing orders larger than this amount
- **Max Position Size**: Limits total exposure to a single market
- **Max Open Positions**: Limits the number of concurrent open positions
- **Max Risk Per Trade**: Limits each order to a percentage of your current balance

### Monitoring Risk

Get a summary of your current risk status:

```python
summary = client.paper.get_risk_summary()
print(f"Daily P&L: ${summary['daily_pnl']:.2f}")
print(f"Trades today: {summary['daily_trades']}")
print(f"Remaining loss limit: ${summary['remaining_loss_limit']:.2f}")
print(f"Remaining trades: {summary['remaining_trades']}")
```

### Example: Daily Loss Limit

```python
config = PaperConfig(max_daily_loss=50.0, max_risk_per_trade=0.50)
client = polyalpha.Client(balance=100.0, paper_config=config)

# Make a losing trade
client.paper.buy(market, side="UP", amount=30.0)
client.paper.resolve(market, outcome="DOWN")  # Loss

# Next trade will be blocked due to loss limit
try:
    client.paper.buy(market, side="UP", amount=10.0)
except ValueError as e:
    print(f"Trade blocked: {e}")  # "Daily loss $30.00 exceeds limit $50.00"
```

### Example: Trade Count Limit

```python
config = PaperConfig(max_trades_per_day=3, max_risk_per_trade=0.20)
client = polyalpha.Client(balance=100.0, paper_config=config)

# First 3 trades succeed
for _ in range(3):
    client.paper.buy(market, side="UP", amount=10.0)

# 4th trade is blocked
try:
    client.paper.buy(market, side="UP", amount=10.0)
except ValueError as e:
    print(f"Trade blocked: {e}")  # "Maximum daily trades (3) reached"
```

### Resetting Daily Limits

Manually reset daily limits (useful for testing):

```python
client.paper.reset_daily_limits()
```

Daily limits also automatically reset at midnight UTC.

### Disabling Risk Management

If you want to disable all risk checks:

```python
config = PaperConfig(enable_risk_management=False)
client = polyalpha.Client(balance=100.0, paper_config=config)

# Orders will succeed regardless of limits
client.paper.buy(market, side="UP", amount=5000.0)  # No error
```

### Default Values

If no configuration is provided, these defaults are used:

- `enable_risk_management`: True
- `max_daily_loss`: $500.0
- `max_trades_per_day`: 100
- `max_order_size`: $1000.0
- `max_position_size`: $2000.0
- `max_open_positions`: 10
- `max_risk_per_trade`: 2% (0.02)

---

## Time Window Execution

Control when orders are allowed to execute using time windows. This is useful for strategies that only want to trade during specific periods, such as the final minute before market close.

### Basic Usage

```python
from datetime import datetime, timezone, timedelta

client = polyalpha.Client(balance=500.0)
market = client.markets.latest("BTC", "5m")

# Parse market end time
end_time = datetime.fromisoformat(market.end_time)

# Only allow execution within 1 minute of market close
order = client.paper.buy(
    market, 
    side="UP", 
    amount=25.0,
    time_window_start=end_time - timedelta(minutes=1),
    time_window_end=end_time
)
```

### Time Window with Limit Orders

```python
# Place a limit order that only fills within the time window
order = client.paper.limit(
    market,
    side="UP",
    price=0.92,
    amount=25.0,
    time_window_start=end_time - timedelta(minutes=1),
    time_window_end=end_time
)

# Attach stream - order will only fill if price crosses threshold
# AND current time is within the window
stream = client.stream(market)
client.paper.attach_stream(stream, market)
stream.start(background=True)
```

### Time Window with TP/SL

```python
# Buy with stop-loss/take-profit, but only within time window
order = client.paper.buy_with_tp_sl(
    market,
    side="UP",
    amount=100.0,
    stop_loss=0.45,
    take_profit=0.55,
    time_window_start=end_time - timedelta(minutes=1),
    time_window_end=end_time
)
```

### Time Window Parameters

| Parameter | Type | Description |
|---|---|---|
| `time_window_start` | `datetime` (UTC) | Earliest time order can execute |
| `time_window_end` | `datetime` (UTC) | Latest time order can execute |

**Behavior:**
- **Market orders**: If current time is outside the window, the order is rejected with a `ValueError`
- **Limit orders**: The order is placed but will only fill when both price crosses threshold AND time is within window
- **No window set**: Orders execute normally without time restrictions

### Example: BTC 5-Minute Strategy

```python
# Strategy: Only trade BTC 5-minute markets in the final 30 seconds
market = client.markets.latest("BTC", "5m")
end_time = datetime.fromisoformat(market.end_time)

# Place limit order that only fills in last 30 seconds
order = client.paper.limit(
    market,
    side="UP",
    price=0.90,
    amount=50.0,
    time_window_start=end_time - timedelta(seconds=30),
    time_window_end=end_time
)

stream = client.stream(market)
client.paper.attach_stream(stream, market)
stream.start(background=True)
```

### Checking Time Windows

The time window is automatically checked on every price update when a stream is attached. You can also manually check:

```python
# Manually check if an order is within its time window
from polyalpha.trading.paper import PaperEngine
engine = client.paper

# This is called automatically by check_limits()
if engine._is_within_time_window(order):
    print("Order can execute now")
else:
    print("Order outside time window")
```
