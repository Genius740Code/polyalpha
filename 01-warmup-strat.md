# Plan 01 — Warmup Strat: collect Chainlink until enough candles, then trade

> Status: **✅ IMPLEMENTED** — `src/polyalpha/history/candle.py`, `store.py`, `recorder.py`, `config.py`; `Bot` wiring `src/polyalpha/bot.py:84`/`src/polyalpha/bot.py:138`; `docs/history.md`; `examples/chainlink_history_warmup.py`; `tests/unit/history/test_history.py`.
> Code refs use `file:line` from `src/polyalpha` at time of writing.  
> Companion: `02-shared-api.md` (one recorder → N strats via single WS).

---

## 1. Problem

EMA-50 on daily (`src/polyalpha/analysis/indicators.py:138` `ema(50)`) and any look-back > `CL_WS_WINDOW_SECONDS=120` (`src/polyalpha/core/constants.py:71`) returns `None` because live state is:

* `ChainlinkStreamer.window` → `ChainlinkAccessor(TimeWindow max_age=120)` (`src/polyalpha/analysis/streaming.py:354`)
* `Bot.TickContext._price_history deque(maxlen=200)` (`src/polyalpha/bot.py:143`) + `BotHub._price_history` (`src/polyalpha/bot_hub.py:1394`)
* `Bot.TickContext.cl` falls back to `_cl_window TimeWindow(120)` (`src/polyalpha/bot.py:392`)

All are in-memory, pruned after 120 s. No disk persistence → `ema(50)` on `1d` can never be warm. Users restart and lose everything. Need a **code-driven warmup gate**: “I need `10×1m` (or `50×1d`) before my strategy runs”.

---

## 2. Goal

Single strat file that:

1. Starts recording Chainlink at ~1 s from `wss://ws-live-data.polymarket.com` (`src/polyalpha/analysis/streaming.py:82`)
2. Compresses ticks → OHLC candles per timeframe (`1s → 1m → 5m → 1h → 1d`)
3. Blocks strategy logic until `N` closed candles exist (e.g. `need = {"1m": 10}` or `{"1d": 50, "1h": 20}`)
4. Then trades with real `ema/sma/rsi` computed over the stored candles
5. Persists across restarts (SQLite) so 2nd run is instantly warm

Zero extra Infra: one DB file, one WS, thread-safe.

---

## 3. Non-goals

* Not the shared-hub API (see `02-shared-api.md`). This plan is **one recorder owned by one `Bot` run**.
* No volume backfill, no Binance fallback by default (opt-in `bootstrap=True` only).
* No cross-asset aggregation yet (one asset per recorder, default `BTC`).

---

## 4. Proposed API (code you’d write)

### 4a. Declarative warmup on `Bot` / `BotHub` (recommended)

```python
import polyalpha
from polyalpha.history import ChainlinkHistoryConfig

# 10 closed 1-min candles before strat fires; persist to ~/.polyalpha/chainlink.db
bot = polyalpha.Bot("BTC", "5m", balance=500,
    chainlink_history=ChainlinkHistoryConfig(
        timeframes=("1m",),      # which TFs to build
        warmup={"1m": 10},       # block until 10 closed 1m candles
        db_path="~/.polyalpha/chainlink.db",
        block="wait",            # "wait" | "skip" | "call_with_flag"
    ))

@bot.on_tick
def strat(ctx):
    # ctx.chainlink_history is guaranteed warm here when block="wait"
    ema10 = ctx.chainlink_history.ema("BTC", "1m", 10)
    if ctx.chainlink_history.close("1m") > ema10:
        ctx.buy("UP", 20)

bot.run()
```

Same for `BotHub`:

```python
hub = polyalpha.BotHub("BTC", "5m",
    chainlink_history=ChainlinkHistoryConfig(warmup={"1m": 10}))
@hub.strategy("ema10")
def ema10(ctx):
    if not ctx.chainlink_history.is_ready("1m", 10):
        return  # when block="skip" — manual guard
    ...
```

### 4b. Imperative warmup (explicit control)

```python
from polyalpha.history import ChainlinkRecorder

rec = ChainlinkRecorder(db_path="~/.polyalpha/chainlink.db",
                        timeframes=("1m","1h","1d"))
rec.start("BTC", background=True)

# wait up to 5 min for 50 daily closes (returns False on timeout)
if not rec.wait_until_ready({"1d": 50, "1h": 20}, timeout=300):
    print(f"warmup {rec.status()}")  # {"1m": 7/10, "1d": 12/50}
    rec.stop(); raise SystemExit

# now strat is safe
@bot.on_tick
def strat(ctx):
    ema50 = rec.ema("BTC", "1d", 50)  # or ctx.chainlink_history.ema(...)
```

`block` modes:
* `wait` (default) — hub buffers ticks, strat not called until warm. `on_tick` fires with `ctx.chainlink_history.warming = True` if you also register `@bot.on_warmup`.
* `skip` — strat is called every tick but `is_ready()` is False until warm; strat must guard.
* `call_with_flag` — strat always called with `ctx.chainlink_history.is_ready` flag, useful for logging warmup progress.

### 4c. Read-only helpers on `ctx.chainlink_history`

```python
ctx.chainlink_history.is_ready("1m", 10) -> bool
ctx.chainlink_history.count("1m") -> int            # closed candles
ctx.chainlink_history.progress("1m", 10) -> 0.0-1.0
ctx.chainlink_history.status() -> {"1m": 7/10, "1d": 3/50}
ctx.chainlink_history.candles("1m", 10) -> DataFrame  # open/high/low/close/count/start_ts
ctx.chainlink_history.close("1m") -> float | None     # last close
ctx.chainlink_history.ema("BTC","1m",10) -> float | None  # None if not warm
ctx.chainlink_history.sma / rsi / macd / bollinger_bands  # same
ctx.chainlink_history.age_s("1m") -> float
```

All indicator helpers delegate to `IndicatorCalculator(DataFrame)` (`src/polyalpha/analysis/indicators.py:43`) → `_native_ta.ema` (`src/polyalpha/analysis/_native_ta.py:13`).

---

## 5. Architecture

```
ChainlinkStreamer (existing, 120s window)  ─┐
                                           ├─► ChainlinkRecorder.ingest(ts, price)
Bot/BotHub tick loop (bot.py:782,           │     ├─ current[(asset,tf)] drift → finalize candle
             bot_hub.py:1790)  ─────────────┘     ├─ SQLite candles(asset,tf,start_ts, o/h/l/c, count)
                                                  └─ query → DataFrame → IndicatorCalculator → ema()
                                                        ▲
ctx.chainlink_history (new property on         ───────────┘
  TickContext bot.py:369 / StrategyContext bot_hub.py:882
  alongside ctx.cl / ctx.chainlink)
```

New package: `src/polyalpha/history/` (see §7).

Lifecycle (per `Bot` run):

```
Bot.__init__(chainlink_history=Config) → Recorder(db_path, tfs) → reuse or start ChainlinkStreamer
Bot._discover() (bot.py:809) → ensure recorder asset matches bot.asset (error if mismatch)
Bot._stream_prices() on_price (bot.py:826) → recorder.ingest(up? no — Chainlink BTC spot, not Polymarket)
                                         → warmup gate: if not ready → fire on_warmup, skip strat
                                         → else call strat(ctx)
Bot._cleanup() (bot.py:1018) → recorder.flush() + stop streamer it owns (not shared)
```

Important: ingredient is **Chainlink BTC spot** (`crypto_prices_chainlink` topic, `src/polyalpha/analysis/streaming.py:462`), not `Stream.up` (Polymarket CLOB mid). Recorder ingests Chainlink ticks, not `on_price up/down`.

---

## 6. Data & compression

**Candle schema** (SQLite, WAL):

```sql
CREATE TABLE candles(
  asset TEXT, timeframe TEXT, start_ts INTEGER,
  open REAL, high REAL, low REAL, close REAL, count INTEGER,
  PRIMARY KEY (asset, timeframe, start_ts)
) WITHOUT ROWID;
CREATE INDEX idx_candles ON candles(asset, timeframe, start_ts);
CREATE TABLE meta(k TEXT PRIMARY KEY, v TEXT); -- schema_version, created_at
```

* `start_ts = floor(ts / tf_secs) * tf_secs` (`TIMEFRAME_SECONDS` `src/polyalpha/core/constants.py:22`). Use UTC for `1d` (document ET caveat from `build_slug:96` but keep UTC for TA).
* In-mem `current: dict[(asset,tf) -> Candle]` — on each ingest, update `high/low/close/count`; when `bucket != current.start_ts`, finalize previous → `INSERT OR REPLACE` (batch).
* Tick arrival ~1 s; candle close fires exactly on wall-clock boundary; `count` = ticks in bucket (useful for data-quality gate: `count < 0.8*expected → mark incomplete`).
* **Retention** (`Config.retention: dict[tf -> secs]`): default `{"1m": 30d, "1h": 90d, "1d": 400d}` (covers `EMA 200` daily). Background `DELETE WHERE start_ts < now - retention[tf]` every hour. `1s` raw not persisted by default (only in-mem ring + optional `ticks` table with 24 h TTL if `persist_raw=True`).
* **“1 s then compresses”** realized as: in-mem 1 s ring (`deque` like `TimeWindow:53` but unbounded only for current bucket), then on bucket close compress to `1m` etc. No 4.3 M row table for `1s` retained 50 d.

---

## 7. File map (to create)

```
src/polyalpha/history/__init__.py        # exports ChainlinkRecorder, ChainlinkHistoryConfig, Candle
src/polyalpha/history/candle.py          # @dataclass Candle + floor helper
src/polyalpha/history/store.py           # Store(db_path) — init, insert, get_candles(limit), count, prune, export
src/polyalpha/history/recorder.py        # Recorder — ingest, CandleBuilder, wait_until_ready, is_ready, status, e/s/rsi helpers
src/polyalpha/history/config.py          # ChainlinkHistoryConfig dataclass (or inline in recorder.py)
```

Modify:

* `src/polyalpha/__init__.py:147` — export `ChainlinkRecorder`, `ChainlinkHistoryConfig`
* `src/polyalpha/client.py:269` — `Client(chainlink_history=...)` passthrough
* `src/polyalpha/bot.py:503` `Bot.__init__` — accept `chainlink_history: bool|ChainlinkHistoryConfig|ChainlinkRecorder`, create `self._chainlink_history`, expose `TickContext.chainlink_history` property next to `chainlink:336` / `cl:369`
* `src/polyalpha/bot_hub.py:1341` `BotHub.__init__` — same, plus shared `self._shared_chainlink_history`
* `src/polyalpha/windows.py` — untouched (keep 120 s helper separate)

No change to `ChainlinkStreamer` except optional `recorder.attach(streamer)` helper.

---

## 8. Warmup gate — exact behavior

* `warmup: dict[tf -> int]` e.g. `{"1m": 10}` means need 10 **closed** candles (not including currently forming). `count()` queries `SELECT COUNT(*) WHERE asset=? AND timeframe=?`.
* `is_ready(tf, n)` → `count(tf) >= n` AND last candle `start_ts + tf_secs < now - 2s` (guard half-formed latest).
* `wait_until_ready(need, timeout)` — polling `count` every 1 s, with `progress` logging via `log.info` (respect `POLYALPHA_LOG_LEVEL`). Returns `True` if warm before timeout, else `False`. Used when `block="wait"` at start of `_stream_prices`.
* `Bot._stream_prices` gate pseudocode:

```python
if self._chainlink_history and self._chainlink_history.config.block == "wait":
    need = self._chainlink_history.config.warmup
    if not self._chainlink_history.wait_until_ready_async(need, tick_source=self._stream):
        # emit on_warmup forever until ready
        while not self._chainlink_history.is_ready(...):
            self._chainlink_history.emit_warmup(status())
            sleep(1)
```

* Indicators return `None` until warm (matches `IndicatorAccessor.ema:228` / `Bot.TickContext.ema_12:450` semantics), so strat can also `if ema is None: return`.

---

## 9. Persistence details

* DB path default `~/.polyalpha/chainlink.db` (separate from `trades.db` `src/polyalpha/database/database.py` to avoid coupling; like `DataFeed` cache `~/.polyalpha/cache` `src/polyalpha/analysis/data_feed.py`).
* `Store` handles `PRAGMA journal_mode=WAL`, `busy_timeout=5000`, `connection` pooling (copy pattern from `src/polyalpha/database/connection.py`).
* `flush()` on candle close + `atexit` + `Bot._cleanup` / `BotHub._cleanup` (`src/polyalpha/bot.py:1018`, `src/polyalpha/bot_hub.py:2084`).
* Bootstrap: if `len(df) < need` on first run, behavior is `wait` (block 10 min for 10×1m ≈ 10 min). Optional `bootstrap=True` → fetch past candles via `DataFeed(source="binance")` (`src/polyalpha/analysis/data_feed.py:1090`) or `DataFeed(source="chainlink")` CoinGecko fallback, insert as synthetic candles marked `count=-1`. Off by default (honest warmup).

---

## 10. Configuration

```python
@dataclass
class ChainlinkHistoryConfig:
    timeframes: tuple[str, ...] = ("1m", "1h", "1d")
    warmup: dict[str, int] = field(default_factory=dict)  # e.g. {"1m": 10}
    db_path: str = "~/.polyalpha/chainlink.db"
    block: Literal["wait","skip","call_with_flag"] = "wait"
    block_timeout: float = 600.0
    retention: dict[str, int] | None = None  # tf -> secs, None = defaults above
    persist_raw: bool = False
    bootstrap: bool = False
    warmup_emit_interval: float = 5.0  # seconds between on_warmup callbacks
```

Env mirrors:

```
POLYALPHA_CHAINLINK_HISTORY=1
POLYALPHA_CHAINLINK_DB=~/.polyalpha/chainlink.db
POLYALPHA_CHAINLINK_TFS=1m,1h,1d
POLYALPHA_CHAINLINK_WARMUP=1m:10,1d:50
```

Read in `src/polyalpha/core/env.py` like `paper_config_from_env`.

---

## 11. Edge cases

* Asset mismatch: `Bot("ETH")` + recorder `BTC` → raise `ValueError` at init.
* Clock skew: reuse `TimeSync` (`src/polyalpha/core/time_sync.py`) for `start_ts` floor if available, else `time.time()`.
* WS gap: if `ChainlinkStreamer._check_stale_data` (`src/polyalpha/analysis/streaming.py:544`) warns >30 s, mark next candle incomplete (store but flag `incomplete=True` — optional column, v1 can just store `count` and let caller filter `count < threshold`).
* Restart: `count()` immediately reflects prior run → `is_ready` true → strat fires on first tick.
* `1d` boundary: UTC midnight vs ET midnight (MDR slug uses ET `src/polyalpha/core/constants.py:104`). Document as UTC; conversion helper `to_et_day()` if needed later.

---

## 12. Testing

* `tests/unit/history/test_candle.py` — floor, OHLC, multi-tf, boundary.
* `tests/unit/history/test_store.py` — CRUD, `get_candles(limit)`, retention prune, WAL, concurrent `ingest` thread safety (like `tests/unit/core/test_windows.py:194` thread_safety).
* `tests/unit/history/test_recorder.py` — inject synthetic 1 s ticks → assert 10×1m flushed, `wait_until_ready({"1m":10})` times out until warm then passes, indicator `ema("1m",10)` matches `IndicatorCalculator`.
* `tests/unit/bots/test_warmup.py` — `Bot` with `HubFeed` (`src/polyalpha/bots/hub_feed.py`) mock + `ChainlinkRecorder` mock → strat not called until warm when `block="wait"`, called with `is_ready=False` when `block="skip"`.
* Manual: `examples/chainlink_history_warmup.py` (single bot), `examples/chainlink_history_warmup_hub.py` (hub variant).

---

## 13. Docs & examples (to add)

* `docs/history.md` (new) — warmup strat pattern, `ChainlinkHistoryConfig` table, `ctx.chainlink_history` API, caveats (warmup time = `need * tf_secs`, e.g. `50×1d ≈ 50 days`).
* Update `docs/bot.md` — warmup section next to “Candle-aware trading guards” (`src/polyalpha/bot.py:287`).
* Update `docs/analysis.md` — note `IndicatorCalculator` now fed by `recorder.candles()`.
* `examples/chainlink_history_warmup.py`:

```python
import polyalpha
from polyalpha.history import ChainlinkHistoryConfig

bot = polyalpha.Bot("BTC", "5m",
    chainlink_history=ChainlinkHistoryConfig(warmup={"1m": 10}, block="wait"))

@bot.on_tick
def s(ctx):
    # guaranteed warm
    if ctx.chainlink_history.close("1m") > ctx.chainlink_history.ema("BTC","1m",10):
        ctx.buy("UP", 10)

@bot.on_warmup  # optional progress hook
def warmup(status): print(f"warming {status}")

bot.run()
```

---

## 14. Rollout

1. **MVP** — `candle.py` + `store.py` + `recorder.py` + `config.py`, `is_ready/wait_until_ready/candles/close/ema`.
2. **Bot single** — wire `Bot` + `TickContext.chainlink_history` + `block="wait"` gate in `Bot._stream_prices`.
3. **Polish** — retention pruner, `on_warmup` event, `bootstrap` flag, docs, example, tests. No BotHub yet (that’s `02`).

---

## 15. Open choices (defaults proposed — confirm or change)

* Warmup takes wall time (`10×1m = 10 min`, `50×1d = 50 days`). Keep honest wait, or enable `bootstrap` synthetic backfill for fast demos?
* `persist_raw` default `False` — keep `1s` only in-mem?
* DB sharing: this plan owns its DB per `Bot`; `02` will share it. OK to default to `~/.polyalpha/chainlink.db` shared file even for this single-bot plan (so later runs share)?

