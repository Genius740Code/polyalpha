# Strategy Framework

Declarative strategies with minimal boilerplate — write just the `signal()`
method (usually **< 30 lines**); the framework handles CL window, cooldown,
volume filter, price zone, logging, stats, and lifecycle hooks.

```python
from polyalpha.strategy import Strategy, Signal, StrategySuite

class M41(Strategy):
    name = "M41"
    cl_window_s = 30
    cl_threshold_pct = 0.08
    fav_max = 0.60

    def signal(self, ctx):
        change = ctx.cl.change_pct(self.cl_window_s)
        if change is not None:
            if change > self.cl_threshold_pct and ctx.price.up < self.fav_max:
                return Signal("UP")
            if change < -self.cl_threshold_pct and ctx.price.down < self.fav_max:
                return Signal("DOWN")
        return None

suite = StrategySuite("BTC", "5m", balance=500)
suite.add(M41())
suite.run()
```

The suite also accepts declarative (parameter-only) strategies:

```python
from polyalpha.strategy import ConfigurableStrategy

suite.add(ConfigurableStrategy.from_config(
    "B1", side="UP", cl_threshold_pct=0.12,
    fav_min=0.50, fav_max=0.75,
))
```

---

## Strategy

`Strategy` is an abstract base class. Override `signal()`; everything else is
optional.

### Class parameters (override in subclass)

| Field | Default | Description |
|-------|---------|-------------|
| `name` | `""` | Human-readable name (defaults to class name on registration) |
| `cl_window_s` | `60` | CL price-change window (seconds) |
| `cl_threshold_pct` | `0.12` | CL change threshold (%) |
| `fav_min` | `0.0` | Minimum favourite token price |
| `fav_max` | `1.0` | Maximum favourite token price |
| `vol_multiplier` | `0.0` | Min volume ratio (0 = disabled) |
| `order_size_pct` | `20` | Order size as % of balance |
| `cooldown_s` | `300` | Min seconds between trades |
| `side` | `None` | Fixed side (None = auto per signal) |

### Methods

- `signal(ctx)` — **required.** Return a `Signal(side)` to trade, or `None`
  to skip the tick. `ctx` is a `StrategyContext` with `ctx.cl`, `ctx.price`,
  `ctx.balance`, `ctx.buy(side, amount)`, `ctx.binance`, etc.
- `on_start()` — called once when the strategy starts.
- `on_entry(side, price)` — called after a position is entered.
- `on_resolve(pos)` — called when a position resolves (win or loss).
- `on_stop()` — called when the strategy stops.
- `check_cooldown()` — `True` if enough time has passed since the last trade.
- `check_volume(ctx)` — `True` if `ctx.binance.vol_ratio() >= vol_multiplier`.
- `check_price_zone(ctx, side)` — `True` if `fav_min <= price <= fav_max`.
- `should_skip(ctx)` — composite guard hook.

### Signals

- `Signal(side)` — tells the framework to trade at the configured order size.
- `SignalResult(side, amount_pct=None, limit_price=None)` — full result with
  optional overrides for order size / limit price.

---

## StrategySuite

Runs N strategies on one shared WebSocket stream. Each strategy gets its own
isolated `PaperEngine` (independent balance / positions / P&L), but all
strategies share ONE market discovery call and ONE stream. A crash in one
strategy does not stop the others.

```python
suite = StrategySuite(
    asset="BTC",              # required: BTC, ETH, SOL, XRP, DOGE, HYPE, BNB
    timeframe="5m",           # required: 5m, 15m, 1h, 4h, 24h
    balance=100.0,            # default starting paper balance per strategy
    mode="simple",            # "simple", "realistic", or "custom"
    buy_once_per_market=True, # buy only once per market, per strategy
    **kwargs,                 # forwarded to BotHub (and Client)
)
```

### API

| Method | Description |
|--------|-------------|
| `add(strategy, balance=None)` | Register a strategy (returns it). Duplicate names raise `ValueError`. |
| `run()` | Start all strategies (blocking) until `stop()`. Raises `RuntimeError` if empty. |
| `run_async()` | Async variant. |
| `stop()` | Signal all strategies to stop gracefully. |
| `stats` | Per-strategy running statistics (dict with a `"strategies"` key). |
| `strategies` | Read-only `{name: strategy}` view. |

See `examples/strategy_framework.py` for a runnable example combining custom
and parameter-only strategies.
