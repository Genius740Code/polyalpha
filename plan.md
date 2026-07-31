# Strategy Abstraction Plan — PolyAlpha

> **Status:** Phases 1–5 implemented. Phases 6–8 planned.

Every strategy example (~200 lines each) is ~80% boilerplate:

| Boilerplate | Lines |
|-------------|-------|
| argparse + db resolve | 20 |
| logging setup | 10 |
| Telegram wrapper | 10 |
| stats dict + keyboard handler + summary | 30 |
| CL price window (deque + loop) | 15 |
| cooldown tracking | 8 |
| bot.run() try/except | 15 |
| **Total wasted** | **~110** |
| Actual strategy logic | ~30 |

## Goal

New strategies in **< 30 lines** — just the signal logic, nothing else.

---

## 

### 1. `Strategy` Base Class —  (`strategy/base.py`)

```python
class Strategy(ABC):
    name: str
    cl_window_s: int       = 60
    cl_threshold_pct: float = 0.12
    fav_min: float          = 0.0
    fav_max: float          = 1.0
    vol_multiplier: float   = 0.0     # 0 = disabled
    order_size_pct: float   = 20
    cooldown_s: int         = 300
    side: str | None        = None    # "UP" / "DOWN" / None = auto

    def signal(self, ctx) -> Signal | None:
        raise NotImplementedError
```

`StrategySuite` accepts any `Strategy` instance and handles: CL window, cooldown,
volume check, price zone, logging, stats, Telegram, keyboard interrupt.

```python
class M41(Strategy):
    name = "M41"
    cl_window_s = 30
    cl_threshold_pct = 0.08
    fav_max = 0.60

    def signal(self, ctx):
        if ctx.cl.change_pct(30) > 0.08 and ctx.price.up < 0.60:
            return Signal("UP")
        if ctx.cl.change_pct(30) < -0.08 and ctx.price.down < 0.60:
            return Signal("DOWN")
```

### 2. `TickContext.cl` Window Helpers — ✅ (`windows.py`, `bot.py`, `bot_hub.py`)

Eliminates manual deque + loop in every strategy:

```python
ctx.cl.value             # latest CL price
ctx.cl.change_pct(30)    # % change over last 30 s
ctx.cl.change_pct(60)    # % change over last 60 s
ctx.cl.change_pct(90)    # % change over last 90 s
ctx.cl.age_s             # seconds since last update
```

Also available on `StrategyContext` inside a `BotHub` / `StrategySuite`.

**Implementation Details:**
- Created `TimeWindow` class in `src/polyalpha/windows.py` with thread-safe rolling window
- Added `ctx.cl` property to `TickContext` in `bot.py` with Chainlink callback integration
- Added `ctx.cl` property to `StrategyContext` in `bot_hub.py` with shared CL window
- Added comprehensive unit tests in `tests/unit/core/test_windows.py`
- Updated documentation in `docs/bot.md` and `README.md`

### 3. `Calculations Library` — ✅ (`calculations/`)

Unified calculation library for all data sources with modular, reusable functions:

```python
from polyalpha.calculations import MarketCalculations, VolumeCalculations

# Universal price calculations (all sources)
MarketCalculations.change_pct(data, period=1)     # % change over N periods
MarketCalculations.change_abs(data, period=1)     # absolute price change
MarketCalculations.rate_of_change(data, period=1) # speed of change per second
MarketCalculations.trend(data, period=1)          # UP/DOWN/NEUTRAL
MarketCalculations.direction(data, period=1)       # "up"/"down"/"flat"
MarketCalculations.volatility(data, period=10)     # price volatility
MarketCalculations.high(data, period=10)          # highest price
MarketCalculations.low(data, period=10)           # lowest price
MarketCalculations.range(data, period=10)         # price range

# Volume calculations (Binance/Coinbase only)
VolumeCalculations.vol_ratio(data, period=10)      # current / avg volume
VolumeCalculations.volume_trend(data, period=5)    # INCREASING/DECREASING/STABLE
VolumeCalculations.volume_surge(data, multiplier=2.0) # detect volume spikes
VolumeCalculations.avg_volume(data, period=10)    # average volume
VolumeCalculations.volume_momentum(data, period=5) # volume % change
VolumeCalculations.relative_volume(data, percentile=0.75) # percentile-based
```

**Implementation Details:**
- Created `src/polyalpha/calculations/` folder with modular calculation functions
- `market_calculations.py` - universal price calculations for all data sources
- `volume_calculations.py` - volume-specific calculations for Binance/Coinbase
- `base_accessor.py` - base class integrating TimeWindow with calculation methods
- `chainlink_accessor.py` - Chainlink-specific accessor with price calculations only
- Updated `BinanceAccessor` in `bot_hub.py` to use calculation library with fallback support
- All calculations are source-aware (Chainlink has no volume, Binance has both)
- Added comprehensive unit tests (121 tests, all passing)

### 4. `StrategySuite` — Run N Strategies on One Stream —  (`strategy/suite.py`)

```python
suite = StrategySuite("BTC", "5m", balance=500)
suite.add(M41())
suite.run()
```

- One WebSocket stream, N strategies
- Each strategy gets its own PaperEngine (isolated balance/P&L)
- Per-strategy stats table at end
- No duplicate CL windows — shared across strategies via `TimeWindow`
- Extensible: add any data source by subclassing or adding to context

### 5. `TimeWindow` + `BaseAccessor` — Reusable Infrastructure — ✅ (`windows.py`, `calculations/`)

**TimeWindow**: Generic, thread-safe rolling window with automatic pruning:

```python
from polyalpha import TimeWindow

w = TimeWindow(max_age=120)
w.update(price)          # from any source
w.value                  # latest
w.change_pct(30)         # % change over 30 s
w.age_s                  # seconds since last update
```

**BaseAccessor**: Source-aware calculation methods using TimeWindow:

```python
from polyalpha.calculations import BaseAccessor, ChainlinkAccessor

# Chainlink accessor (price calculations only)
cl_accessor = ChainlinkAccessor(window)
cl_accessor.change_pct(30)    # % change over 30 seconds
cl_accessor.trend(60)         # trend direction
cl_accessor.volatility(120)   # price volatility

# Future: Coinbase accessor (price + volume calculations)
# cb_accessor = CoinbaseAccessor(window)
# cb_accessor.vol_ratio(10)   # volume calculations available
```

**Implementation Details:**
- `TimeWindow` provides thread-safe rolling window infrastructure
- `BaseAccessor` integrates TimeWindow with calculation library
- Each data source has specific accessor (Chainlink, Binance, future Coinbase)
- Accessors automatically adapt to available data (price-only vs price+volume)
- All calculation methods are consistent across data sources

### 6. `ConfigurableStrategy` — Parameter-Only Strategies —  (`strategy/base.py`)

```python
s = ConfigurableStrategy.from_config(
    "B1", side="UP", cl_threshold_pct=0.12,
    fav_min=0.50, fav_max=0.75,
)
suite.add(s)
```

Auto-generates signal from CL threshold + price zone.

---

## Migration Path

| Phase | What | Status |
|-------|------|--------|
| P1 | Add `Strategy` base class, `Signal`, `SignalResult` | ✅ Done |
| P2 | Add `ctx.cl.change_pct(30/60/90)` helpers | ✅ Done |
| P3 | Add calculations library with market & volume calculations | ✅ Done |
| P4 | Add `StrategySuite` with shared stream | ✅ Done |
| P5 | Add `from_config()` for parameter-only strats | ✅ Done |
| P6 | Port M41, M42, B1/B21 to new base | 📋 Planned |
| P7 | Remove example boilerplate (argparse, logging, tg, etc.) | 📋 Planned |
| P8 | Add Coinbase accessor with price + volume calculations | 📋 Future |

---

## Architecture

```
StrategySuite
  └── BotHub (1 WebSocket, 1 discovery)
        ├── StrategyContext #1  ← PaperEngine #1  ← Strategy.signal()
        ├── StrategyContext #2  ← PaperEngine #2  ← Strategy.signal()
        ├── ...                ← ...
        └── Shared:
              ├── TimeWindow (CL prices)     ← ctx.cl
              ├── BinanceAccessor            ← ctx.binance
              ├── ChainlinkStreamer          ← ctx.chainlink
              ├── IndicatorAccessor          ← ctx.indicators
              └── OrderBookAccessor          ← ctx.orderbook
```
