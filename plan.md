# Strategy Abstraction Plan — PolyAlpha

> **Status:** Phases 1–4 implemented. Phases 5–7 planned.

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

## Implemented

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

### 3. `ctx.binance.vol_ratio` + `change_pct` —  (`bot_hub.py`)

```python
ctx.binance.vol_ratio(10)   # current vol / avg of last 10 candles
ctx.binance.change_pct(3)   # price change % over N candles
```

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

### 5. `TimeWindow` — Reusable Rolling Window —  (`windows.py`)

Generic, thread-safe, prunes old entries. Works with any data source:

```python
from polyalpha import TimeWindow

w = TimeWindow(max_age=120)
w.update(price)          # from any source
w.value                  # latest
w.change_pct(30)         # % change over 30 s
w.age_s                  # seconds since last update
```

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
| P1 | Add `Strategy` base class, `Signal`, `SignalResult` |  |
| P2 | Add `ctx.cl.change_pct(30/60/90)` helpers | ✅ Done |
| P3 | Add `ctx.binance.vol_ratio`, `ctx.binance.change_pct` |  |
| P4 | Add `StrategySuite` with shared stream |  |
| P5 | Add `from_config()` for parameter-only strats |   |
| P6 | Port M41, M42, B1/B21 to new base | 📋 Planned |
| P7 | Remove example boilerplate (argparse, logging, tg, etc.) | 📋 Planned |

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
