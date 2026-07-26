# BotHub Pain Points (from paper_6_strategies.py)

Discovered while building a paper-trading script running 6 strategies across 5-min BTC markets.

---

### ~~1. No event/hook system on BotHub~~ ✅ Fixed

```
# Now exists:
@hub.on("tick")
def ticker(up, down): ...

@hub.every(30)
def periodic(up, down): ...

hub.on("candle_open", handler)
hub.on("start", handler)
hub.on("stop", handler)
hub.on("error", handler)
hub.add_handler("stop", handler)
```

Added in `bot_hub.py`:
- `hub.on(event)` — decorator/imperative for events: `"start"`, `"tick"`, `"candle_open"`, `"candle_close"`, `"stop"`, `"error"`
- `hub.every(seconds)` — decorator/imperative for periodic timers (receives latest up/down)
- `hub.add_handler(event, fn)` — imperative form
- Events fire at correct lifecycle points: start, tick, candle boundary, strategy error, cleanup
- Updated docs (`docs/bot.md`) and example (`examples/paper_6_strategies.py`)

---

### ~~2. OrderBookFeed API is opaque~~ ✅ Fixed

```python
# Now works:
ctx.orderbook.up.bids       # tuple[BookLevel] — UP bids
ctx.orderbook.down.asks     # tuple[BookLevel] — DOWN asks
ctx.orderbook.up.spread     # float — UP bid-ask spread
ctx.orderbook.refresh()     # force REST refresh
```

Added in `bot_hub.py`:
- `OrderBookAccessor` class wrapping `OrderBookFeed` with clean, documented API
- `ctx.orderbook` property on `StrategyContext` — lazy-init, auto-attaches to the shared WebSocket stream
- Auto-fetches an initial REST snapshot on first access so data is available immediately
- `BotHub._discover()` passes the shared `ClobBookClient` to each strategy context (no second `Client()` needed)
- Updated docs and example (`examples/paper_6_strategies.py`)

---

### 3. Strategy errors silently swallowed

Strategy 8 crashed every tick with `AttributeError`. The BotHub caught it internally but produced zero visible output — no per-strategy error log, no traceback in the terminal. Strategy ran "silently broken" and the user had no idea.

```python
# From _stream_prices — catch swallows everything:
try:
    s.fn(s.ctx)
except Exception as exc:
    ...  # no visible output
```

**Ask:** Log strategy errors at `ERROR` level with traceback by default, or expose an `on_error` hook.

---

### 4. No periodic timer / scheduled callback

Can't schedule 30-second, 1-minute, or candle-level callbacks. Everything is tick-driven. If BTC sits at the same price for 2 minutes, strategies still fire on every mid-price jitter but there's no way to run maintenance logic (cancel stale orders, log status) on a schedule.

**Ask:** `hub.every(seconds=30, fn=my_ticker)` or `hub.on("candle", fn)`.

---

### 5. Strategy vs variant API blurred

```python
hub.strategy("name", balance=100)    # decorator
hub.add_strategy("name", fn, 100)    # imperative
hub.variant("name", balance=100)     # decorator
hub.add_variant("name", fn, 100)     # imperative
hub.compare_variants()               # only for variants?
```

When to use `strategy` vs `variant`? How does that affect `compare_variants()` output? Unclear.

**Ask:** Either merge them or document the distinction clearly with examples.

---

### 6. Indicator availability unclear

```
INFO polyalpha.analysis.indicators pandas-ta not installed; using native TA implementations
```

Which indicators are available natively? Same signatures as pandas-ta? What's missing? Had to guess RSI and SMA would work — they did, but with zero confidence.

**Ask:** Print available native indicators on startup, or expose `ctx.indicators.available()`.



API Documentation & Consistency
StrategyContext Missing Attributes:

Document available attributes clearly (no tick_count, atr as expected)
Add tick_count or similar for tracking strategy execution history
Add built-in ATR/ATR-based volatility to context
Add time_to_close for time-based strategies
BotHub Internal API:

_RegisteredStrategy should expose stats property publicly
Better documentation for accessing strategy results post-run
Consistent naming between Bot and BotHub contexts
Paper Trading Configuration
Automatic Config Application:

Apply paper config to all BotHub strategies automatically via hub-level setting
Strategy-specific config overrides
Config validation before run
External Data Integration
Built-in Data Fetching:

Integrate external price feeds (BTC, ETH) directly into StrategyContext
Add order book depth data to context
Social sentiment hooks (Twitter/Reddit) as optional context attributes
Caching mechanism for external API calls
Strategy Lifecycle & Hooks
Enhanced Lifecycle Events:

on_initialize() - called once before first tick
on_market_rollover() - called when market closes/rolls over
on_error() - per-strategy error handling with recovery
on_shutdown() - cleanup on stop
Cross-Strategy Features
Strategy Communication:

Shared state store between strategies in same hub
Event bus for inter-strategy signaling
Coordination primitives (locks, semaphores)
Performance & Analytics
Built-in Metrics:

Per-strategy real-time P&L tracking accessible via context
Strategy comparison utilities built into BotHub
Export functionality (JSON/CSV) for all strategies
Performance dashboard/summary generation
Backtesting Integration
Historical Mode:

Run strategies against historical data
Replay mode for testing strategies
Parameter optimization framework
Risk Management
Global Risk Controls:

Hub-level risk limits (total exposure, max drawdown)
Automatic position sizing based on Kelly Criterion
Circuit breakers for extreme market conditions
Developer Experience
Better Debugging:

Strategy-level logging configuration
Step-through debugging mode
Strategy validation before deployment
Dry-run mode with execution preview
Type Safety:

Full type hints for StrategyContext
Strategy function signature validation
Config schema validation
Current Workarounds Needed
The script required workarounds for:

Manual paper config application per strategy
Custom performance tracker (library may have this undocumented)
External data fetching (no built-in integration)
Time-to-close calculation (not in context)
Strategy stats access (private API)
These improvements would make building multi-strategy systems significantly easier and more robust.