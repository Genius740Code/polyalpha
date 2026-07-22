# Trading

PolyAlpha supports two trading modes: **paper trading** (simulated, no real money) and **real trading** (live execution via Polymarket CLOB).

---

## Paper Trading

Accessible via `client.paper`. All state is held in memory — no API keys needed.

```python
client = polyalpha.Client(balance=100.0)
```

### Balance

```python
client.paper.balance         # Current USDC balance
client.paper.set_balance(500.0)  # Reset balance
```

### Market Orders

**`buy(market, side, amount, stop_loss_pct=None, take_profit_pct=None) -> PaperOrder`**

Execute a simulated market buy — fills immediately at the current price.

```python
order = client.paper.buy(market, side="UP", amount=10.0)
order = client.paper.buy(market, side="DOWN", amount=25.0, stop_loss_pct=0.05)
```

- `side` — `"UP"` or `"DOWN"`
- `amount` — USDC amount to spend
- `stop_loss_pct` — optional stop-loss as decimal (e.g. 0.05 = 5%)
- `take_profit_pct` — optional take-profit as decimal

### Limit Orders

**`limit(market, side, price, amount) -> PaperOrder`**

Place a limit order that fills when the streamed price reaches your price.

```python
order = client.paper.limit(market, side="UP", price=0.55, amount=10.0)
```

Requires an attached stream to auto-fill:

```python
stream = client.stream(market)
client.paper.attach_stream(stream, market)
stream.start(background=True)
```

Cancel an open limit order:

```python
client.paper.cancel(order.id)
```

### Selling Positions

**`sell_position(market, side, amount=None) -> PaperOrder`**

Sell or reduce a position.

```python
client.paper.sell_position(market, side="UP")
client.paper.sell_position(market, side="UP", amount=5.0)  # partial sell
```

### Advanced Order Types

**`buy_with_tp_sl(market, side, amount, stop_loss=..., take_profit=..., trail_sl=..., trail_tp=...) -> PaperOrder`**

Market buy with stop-loss and take-profit prices or percentages.

```python
order = client.paper.buy_with_tp_sl(
    market, side="UP", amount=10.0,
    stop_loss=0.45, take_profit=0.65,
)
```

**`oco_order(market, side, amount, stop_loss, take_profit) -> tuple[PaperOrder, PaperOrder]`

One-Cancels-Other order — places a main order and a counter-side order.

```python
main, oco = client.paper.oco_order(market, side="UP", amount=10.0, stop_loss=0.40, take_profit=0.70)
```

### Position Management

**`positions() -> list[PaperPosition]`** — live unresolved positions

**`all_positions() -> list[PaperPosition]`** — all positions including resolved

**`show_positions(show_all=False, verbose=True)`** — display formatted table

**`resolve(market, outcome)`** — resolve all positions for a market

```python
client.paper.resolve(market, outcome="UP")
```

**`set_stop_loss(market, side, stop_price)`**

**`set_take_profit(market, side, profit_price)`**

**`set_trailing_stop(market, side, trail_distance)`**

**`set_trailing_sl(order_id, trail_distance)`** — trailing stop-loss on a filled order

**`set_trailing_tp(order_id, trail_distance)`** — trailing take-profit on a filled order

### Order Queries

```python
client.paper.open()          # Open (pending) limit orders
client.paper.orders()        # All orders
client.paper.summary()       # Formatted P&L summary
client.paper.fee_summary()   # Detailed fee and rebate summary
client.paper.get_rebate_stats() -> dict
client.paper.position_history() -> dict
client.paper.pre_trade_checks(market, side, amount) -> dict
```

### Risk Management

Available via `PaperConfig` (see **configuration.md**):

- Daily loss limit (`max_daily_loss`)
- Max trades per day (`max_trades_per_day`)
- Max order size (`max_order_size`)
- Max position size (`max_position_size`)
- Max open positions (`max_open_positions`)
- Max risk per trade (`max_risk_per_trade`)

```python
client.paper.get_risk_summary() -> dict
client.paper.reset_daily_limits()
```

### Stream Integration

Wire a stream so positions auto-update and limit orders auto-fill:

```python
stream = client.stream(market)
client.paper.attach_stream(stream, market)
stream.start(background=True)
```

### Database Persistence

```python
client.paper.enable_database("./trades.db")
client.paper.database       # TradeDatabase instance or None
client.paper.disable_database()
```

### Auto-Redeem

```python
client.paper.auto_redeem                  # AutoRedeemEngine instance
client.paper.set_auto_redeem_config(config)
```

### Reports

```python
client.paper.report                      # ReportEngine for analytics
client.paper.portfolio_analytics         # Portfolio analytics
client.paper.reporting                   # Comprehensive reporting
```

### Multi-Wallet

```python
from polyalpha.trading.wallet import WalletManager, PaperWallet
manager = WalletManager()
manager.add_wallet(PaperWallet("wallet1", balance=100.0))
client.paper.enable_multi_wallet(manager)
client.paper.disable_multi_wallet()
```

### PaperConfig Presets

Built-in presets: `CONSERVATIVE`, `REALISTIC`, `AGGRESSIVE`, `ZERO_FEE`, `HIGH_LATENCY`, `LIQUIDITY_PROVIDER`, `SCALPER`, `TEST`

```python
from polyalpha.trading.paper_config import get_paper_config_from_preset, list_presets
config = get_paper_config_from_preset("REALISTIC")
client = polyalpha.Client(paper_config=config)
```

---

## Real Trading

Accessible via `client.real` when credentials are provided.

```python
client = polyalpha.Client(
    private_key="0x...",
    rpc_url="https://polygon-rpc.com",
    polymarket_api_key="...",
)
```

### RealTradingConfig

| Field | Type | Default | Description |
|-------|------|---------|-------------|
| `private_key` | `str` | — | Wallet private key |
| `rpc_url` | `str` | — | Polygon RPC URL |
| `polymarket_api_key` | `str` | — | Polymarket API key |
| `require_confirmation` | `bool` | `True` | Require manual confirmation |
| `position_sizing` | `str` | `"fixed"` | `"fixed"`, `"percentage"`, or `"kelly"` |
| `fixed_amount` | `float` | `10.0` | Order size for fixed strategy |
| `percentage_of_balance` | `float` | `0.05` | For percentage strategy |
| `kelly_fraction` | `float` | `0.25` | Kelly criterion fraction |
| `max_order_size` | `float` | `1000.0` | Maximum USDC per order |
| `max_daily_loss` | `float` | `500.0` | Daily loss limit |
| `max_open_positions` | `int` | `10` | Maximum concurrent positions |
| `slippage_tolerance` | `float` | `0.05` | 5% slippage tolerance |
| `order_timeout` | `int` | `60` | Order timeout in seconds |

### Methods

```python
client.real.buy(market, side="UP", confidence=0.65)
client.real.limit(market, side="UP", price=0.55, amount=10.0)
client.real.sell(market, side="UP")
client.real.cancel(order_id)
client.real.balance                    # Current USDC balance
client.real.refresh_balance()          # Refresh from chain
client.real.open()                     # Open orders
client.real.orders()                   # All orders
client.real.positions()                # Live positions
client.real.summary()                  # Position summary
```

### Auto-Redeem

```python
client.real.auto_redeem
client.real.set_auto_redeem_config(config)
```

### Position Sizing

```python
from polyalpha.trading.real import FixedPositionSizer, PercentagePositionSizer, KellyPositionSizer
client.real.set_position_sizer(KellyPositionSizer(kelly_fraction=0.25))
```

### Error Handling

```python
client.real.get_error_handling_status() -> dict
client.real.clob_circuit_breaker
client.real.wallet_circuit_breaker
client.real.error_recovery
client.real.trigger_degradation(level, reason)
client.real.trigger_recovery(level, reason)
client.real.emergency_mode
```

---

## Auto-Redeem Engine

Available on both `client.paper.auto_redeem` and `client.real.auto_redeem`.

### AutoRedeemConfig

| Field | Type | Default | Description |
|-------|------|---------|-------------|
| `enabled` | `bool` | `True` | Enable auto-redeem |
| `trigger_on_time` | `bool` | `True` | Time-based triggers |
| `trigger_on_count` | `bool` | `True` | Count-based triggers |
| `time_interval` | `str` | `"1d"` | `"1h"`, `"1d"`, `"1w"` |
| `min_markets` | `int` | `10` | Min markets before redeem |
| `max_markets` | `int` | `100` | Max markets before forced redeem |
| `min_value_usd` | `float` | `100.0` | Min value before redeem |
| `require_confirmation` | `bool` | `False` | Require user confirmation |
| `dry_run` | `bool` | `False` | Simulate without executing |
| `only_winning` | `bool` | `False` | Only redeem winning positions |

---

## PaperOrder Fields

| Field | Type | Description |
|-------|------|-------------|
| `id` | `str` | Unique order ID |
| `market_id` | `str` | Market condition ID |
| `slug` | `str` | Market slug |
| `side` | `str` | `"UP"` or `"DOWN"` |
| `price` | `float` | Fill price |
| `amount` | `float` | USDC amount |
| `shares` | `float` | Shares received |
| `fee` | `float` | Fee paid |
| `status` | `str` | `"open"`, `"filled"`, `"cancelled"` |
| `is_limit` | `bool` | True if limit order |
| `filled_at` | `datetime` | Fill timestamp |
| `stop_loss` | `float \| None` | Stop-loss price |
| `take_profit` | `float \| None` | Take-profit price |

## PaperPosition Fields

| Field | Type | Description |
|-------|------|-------------|
| `market_id` | `str` | Market condition ID |
| `slug` | `str` | Market slug |
| `side` | `str` | `"UP"` or `"DOWN"` |
| `shares` | `float` | Shares held |
| `avg_price` | `float` | Average entry price |
| `current_price` | `float` | Current price |
| `pnl` | `float` | Unrealized P&L |
| `resolved` | `bool` | True if resolved |
| `outcome` | `str \| None` | `"WON"`, `"LOST"`, `"CLOSED"` |
