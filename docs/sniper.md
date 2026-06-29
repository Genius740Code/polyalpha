# Sniper Bot

The `Sniper` bot automates trading by executing limit orders only during a specified time window before market resolution. It monitors prices and automatically transitions to the next market after resolution, enabling continuous automated trading.

---

## Quick start

```python
import polyalpha
from polyalpha.bots import Sniper, SniperConfig

client = polyalpha.Client(balance=500.0)

# Configure the sniper bot
config = SniperConfig(
    asset="BTC",
    timeframe="5m",
    side="UP",
    entry_price=0.92,
    exit_price=0.88,
    window_seconds=35,
    amount=20.0,
)

sniper = Sniper(client, config)

# Run the sniper bot (blocks until stopped)
sniper.run()
```

---

## Configuration

The `SniperConfig` dataclass defines all behavior for the bot.

| Parameter | Type | Default | Description |
|---|---|---|---|
| `asset` | `str` | `"BTC"` | Asset to trade (e.g. `"BTC"`, `"ETH"`) |
| `timeframe` | `str` | `"5m"` | Timeframe (e.g. `"5m"`, `"1h"`) |
| `side` | `str` | `"UP"` | Market side to trade (`"UP"` or `"DOWN"`) |
| `entry_price` | `float` | `0.92` | Price at which to place limit order |
| `exit_price` | `float` | `None` | Price at which to exit/cancel order (must be < entry_price) |
| `window_seconds` | `int` | `35` | Trading window in seconds before market close |
| `amount` | `float` | `20.0` | Trade size in USDC |
| `max_position_size` | `float` | `None` | Maximum concurrent position exposure |
| `max_consecutive_losses` | `int` | `3` | Stop after this many consecutive losses |
| `max_trades` | `int` | `None` | Stop after this many total trades |

---

## Technical Analysis Integration

The Sniper can conditionally execute trades based on technical indicators.

```python
config = SniperConfig(
    asset="BTC",
    timeframe="5m",
    side="UP",
    entry_price=0.92,
    amount=20.0,
    window_seconds=30,
    # TA configuration
    use_ta=True,
    ta_data_source="binance",
    ta_rsi_threshold=60,
    ta_sma_period=20
)
```

If TA is enabled, the entry order is only placed if:
1. Current price reaches `entry_price`.
2. The TA conditions are met (e.g., RSI > 60 and Price > SMA(20)).

---

## Event Handlers

The `Sniper` is event-driven. You can attach custom logic using the `@sniper.on()` decorator.

```python
@sniper.on("market_found")
def on_market(market):
    print(f"Discovered market: {market.slug}")

@sniper.on("entry")
def on_entry(order):
    print(f"Filled entry order! Shares: {order.shares}")

@sniper.on("resolve")
def on_resolve(outcome, pnl):
    print(f"Resolved {outcome}: ${pnl:.2f}")

@sniper.on("rollover")
def on_rollover(market):
    print("Moving to the next market cycle.")
```

Supported events:
- `market_found`: New market discovered
- `window_enter`: Entering the trading window
- `entry`: Order filled
- `exit`: Order cancelled (e.g. exit threshold triggered)
- `resolve`: Market resolved (outcome: `'WON'` | `'LOST'`)
- `rollover`: Transitioning to next market
- `error`: Unrecoverable error occurred
- `stop`: Bot stopped

---

## Lifecycle and State

The bot moves through a state machine during its execution cycle:

`IDLE` → `DISCOVERING` → `WAITING` → `ARMED` → `FILLED` → `RESOLVING` → `ROLLOVER` → `IDLE`

You can inspect the current state using `sniper.state`.

---

## Statistics & Performance

Track the bot's performance via `sniper.stats`.

```python
stats = sniper.stats

print(f"Total trades: {stats.total_trades}")
print(f"Win rate: {stats.win_rate:.1f}%")
print(f"Total P&L: ${stats.total_pnl:.2f}")
print(f"Current consecutive losses: {stats.consecutive_losses}")

# Inspect individual trades
for trade in stats.trades:
    print(trade.market_slug, trade.outcome, trade.pnl)
```

---

## Stopping the bot

To gracefully shut down a running bot from an event handler or another thread:

```python
sniper.stop(reason="target_profit_reached")
```
