# Polyalpha Strategy Implementation Improvements — Plan

## Overview

Six feature improvements to eliminate custom wrappers (SharedStreamManager), reduce boilerplate, and add cross-variant comparison. Each is scoped by file and dependency order (later items may depend on earlier ones).

---

## Priority 1: Native Chainlink Price Feed in BotHub

**Files:** `src/polyalpha/stream.py`, `src/polyalpha/analysis/streaming.py`, `src/polyalpha/bot_hub.py`

**Goal:** Expose Chainlink spot price, candle open price, and seconds-in-candle directly on `StrategyContext` so users don't need a custom `SharedStreamManager`.

### Implementation Plan

**1a. — Chainlink price cache layer** (`stream.py` or new `src/polyalpha/core/chainlink_cache.py`)

Currently `ChainlinkStreamer` (in `analysis/streaming.py`) connects to `wss://ws-live-data.polymarket.com` and emits `price(symbol, price, timestamp)` via callbacks. BotHub's `Stream` connects to the CLOB WS at `wss://ws-subscriptions-clob.polymarket.com/ws/market` — two different WebSocket endpoints.

| Step | What | Why |
|------|------|-----|
| 1a.1 | Create `ChainlinkPriceCache` — a lightweight singleton that runs one `ChainlinkStreamer` in the background and stores `{symbol: (price, timestamp)}` | Avoids one WS connection per strategy; reuses the existing `ChainlinkStreamer` |
| 1a.2 | Add `BotHub(chainlink=True)` param; on init, starts `ChainlinkPriceCache` if enabled | Configurable — no overhead if user doesn't need it |
| 1a.3 | Expose `ctx.spot_price` and `ctx.candle_open` on `StrategyContext` | Read from cache; `candle_open` = price at first tick after timeframe boundary |

**1b. — Candle tracking** (`bot_hub.py`)

| Step | What | Why |
|------|------|-----|
| 1b.1 | Track `_candle_start_time` and `_candle_open_price` in BotHub | Derived from first tick after `time.time() % TIMEFRAME_SECONDS[timeframe]` resets |
| 1b.2 | Add `ctx.seconds_in` property | `time.time() - _candle_start_time` |

**Dependency:** `ChainlinkStreamer` already exists and works. No structural changes to the stream module needed.

---

## Priority 2: Multi-Variant Strategy Framework (highest impact)

**Files:** `src/polyalpha/bot_hub.py`, new `src/polyalpha/variant.py`

**Goal:** `@hub.variant()` decorator with isolated P&L, auto-database, and `hub.compare_variants()`.

### Implementation Plan

**2a. — `Variant` dataclass and registry** (new `variant.py` or inline in `bot_hub.py`)

| Step | What |
|------|------|
| 2a.1 | Add `Variant` dataclass extending `_RegisteredStrategy` with `id: str`, `params: dict`, `created_at`, `run_count` |
| 2a.2 | Add `hub.variant(name, balance=100, params={})` decorator — same as `.strategy()` but also stores metadata for comparison |
| 2a.3 | Each variant gets its own database namespace via `TradeDatabase(namespace=name)` (lazy) — avoids cross-contamination |

**2b. — Comparison engine** (`src/polyalpha/report/comparison.py`)

| Step | What |
|------|------|
| 2b.1 | `hub.compare_variants()` iterates all variants, extracts P&L, win rate, trade count, Sharpe from each variant's `PaperEngine` |
| 2b.2 | Returns `ComparisonReport` — dataclass with `results: list[VariantResult]` sorted by P&L |
| 2b.3 | `print()` variant of `ComparisonReport` renders a Rich table (name, balance, P&L, win%, Sharpe) |
| 2b.4 | Expose as top-level `polyalpha.ComparisonReport` |

**2c. — Persist variant runs** (`report/comparison.py`)

| Step | What |
|------|------|
| 2c.1 | Save comparison snapshots to `~/.polyalpha/variants/{hub_asset}_{hub_tf}_{timestamp}.json` |
| 2c.2 | `hub.list_runs()` shows past comparison runs |
| 2c.3 | `hub.load_run(timestamp)` restores a previous comparison for re-analysis |

**Dependency:** Requires Priority 1 (Chainlink) only if spot_price/candle_open are used in comparison metrics.

---

## Priority 3: Candle-Aware Trading Controls

**Files:** `src/polyalpha/bot_hub.py`, `src/polyalpha/bot.py`

**Goal:** Add `ctx.buy_once_per_candle()`, `ctx.buy_in_window()`, and auto-track candle IDs.

### Implementation Plan

| Step | What | Where |
|------|------|-------|
| 3a.1 | Track `_candle_id` on BotHub/StrategyContext — increments each time `seconds_in` resets past 0 | `bot_hub.py:_stream_prices` |
| 3a.2 | `StrategyContext._bought_this_candle: dict[int, set[str]]` — maps candle_id → {sides bought} | `bot_hub.py:StrategyContext` |
| 3a.3 | `ctx.buy_once_per_candle(side, amount)` — checks `_bought_this_candle[candle_id]`, skips if already bought | `StrategyContext` |
| 3a.4 | `ctx.buy_in_window(side, amount, min_seconds, max_seconds)` — reads `ctx.seconds_in`, only buys within window | `StrategyContext` |
| 3a.5 | Backport `buy_once_per_candle` to `Bot.TickContext` for single-bot users | `bot.py:TickContext` |

**Dependency:** Priority 1b (candle tracking) is required.

---

## Priority 4: First-Class Indicator Access via `ctx.indicators`

**Files:** `src/polyalpha/bot_hub.py`, `src/polyalpha/analysis/_native_ta.py`

**Goal:** Replace `ctx.rsi`, `ctx.sma_20` properties with `ctx.indicators.rsi(14)`, `ctx.indicators.macd(12,26,9)`, `ctx.indicators.bollinger_bands(20, 2)`.

### Implementation Plan

| Step | What |
|------|------|
| 4a.1 | Create `IndicatorAccessor` class on `StrategyContext` — wraps the shared `_price_history` deque |
| 4a.2 | `indicators.rsi(period=14)` — calls `_rsi(series, period)`; cache results for current tick |
| 4a.3 | `indicators.macd(fast=12, slow=26, signal=9)` — returns `MACDResult(macd, signal, histogram)` namedtuple |
| 4a.4 | `indicators.bollinger_bands(period=20, std=2)` — returns `BBResult(upper, mid, lower)` namedtuple |
| 4a.5 | `indicators.sma(period)`, `indicators.ema(period)` — parameterized versions of existing fixed-period props |
| 4a.6 | Add per-tick result cache on `IndicatorAccessor` — cleared on `_invalidate_series_cache()` to avoid recomputation within one tick |
| 4a.7 | Add `_native_ta.py:bollinger_bands()` function — pure numpy implementation (no pandas-ta dependency for real-time use) |
| 4a.8 | Backport `ctx.indicators` to `Bot.TickContext` for single-bot users |

**Dependency:** None standalone, but integrates with Priority 1 (shares price history).

---

## Priority 5: Built-in Per-Strategy File Logging

**Files:** `src/polyalpha/bot_hub.py`, `src/polyalpha/bot.py`, `src/polyalpha/utils/logging_utils.py`

**Goal:** `BotHub(asset="BTC", timeframe="5m", log_dir="./logs")` auto-creates rotating file handlers per strategy.

### Implementation Plan

| Step | What |
|------|------|
| 5a.1 | Add `BotHub.__init__(log_dir=None)` param — stores path |
| 5a.2 | In `_discover()` (or strategy registration), create `RotatingFileHandler(log_dir/{name}.log, maxBytes=5MB, backupCount=3)` and attach to each strategy's logger |
| 5a.3 | Each strategy gets `logging.getLogger(f"polyalpha.BotHub.{name}")` — separate logger instance per variant |
| 5a.4 | Add `Bot(log_dir=None)` param for single-bot users |
| 5a.5 | Optionally add a `setup_strategy_logger(name, log_dir)` helper to `logging_utils.py` |

**Dependency:** None.

---

## Priority 6: Strategy Comparison Dashboard

**Files:** `src/polyalpha/report/comparison.py`, `src/polyalpha/report/presets.py`, `src/polyalpha/report/metrics.py`

**Goal:** `hub.run_comparison(duration_hours=24)` runs all variants for N hours, then outputs a P&L table, win rates, and Sharpe ratios.

### Implementation Plan

| Step | What |
|------|------|
| 6a.1 | `hub.run_comparison(duration_hours)` — runs `hub.run()` with a timer, stops after N hours |
| 6a.2 | Extract per-variant `PaperEngine.all_positions()` → `TradeRecord[]` via `extract_trades()` |
| 6a.3 | Compute per-variant metrics: win rate, total P&L, Sharpe (from `metrics.py:compute_metrics`), max drawdown |
| 6a.4 | Render Rich table: | Rank | Variant | Trades | Win% | P&L | Sharpe | DD | Balance | |
| 6a.5 | Render equity curves as an overlay chart via Plotly (if `[report]` extras installed) |
| 6a.6 | Save comparison HTML to `comparison_{timestamp}.html` — self-contained with embedded charts |
| 6a.7 | Expose `hub.comparison_summary()` — returns `ComparisonReport` dataclass (no HTML dependency) |

**Dependency:** Priority 2 (variants must exist to compare). Reuses `report/metrics.py`.

---

## Execution Order

```
Phase 1 (core enablers):   #5 Logging  →  #1 Chainlink + Candle
Phase 2 (framework):       #4 Indicators  →  #2 Variant framework
Phase 3 (quality of life): #3 Candle guards  →  #6 Dashboard
```

Each phase can be shipped and released independently.

---

## Files Changed Summary

| File | Changes |
|------|---------|
| `src/polyalpha/bot_hub.py` | Chainlink cache, candle tracking, variant decorator, candle guards, IndicatorAccessor, per-strategy logging, run_comparison |
| `src/polyalpha/bot.py` | Backport candle guards, IndicatorAccessor, log_dir |
| `src/polyalpha/stream.py` | Optional: expose candle boundary signal |
| `src/polyalpha/analysis/_native_ta.py` | Add `bollinger_bands()` function |
| `src/polyalpha/analysis/streaming.py` | No changes (reused by ChainlinkPriceCache) |
| `src/polyalpha/core/chainlink_cache.py` | **New** — singleton background ChainlinkStreamer |
| `src/polyalpha/report/comparison.py` | **New** — variant comparison engine, Rich table, HTML dashboard |
| `src/polyalpha/utils/logging_utils.py` | `setup_strategy_logger()` helper |
| `src/polyalpha/__init__.py` | Export new public API symbols |