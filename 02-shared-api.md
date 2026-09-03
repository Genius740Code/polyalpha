# Plan 02 — Shared Chainlink History API: one recorder → N strats

> Status: **✅ IMPLEMENTED** — `src/polyalpha/history/registry.py`, `view.py`; `BotHub` `src/polyalpha/bot_hub.py:12`/`src/polyalpha/bot_hub.py:820`, `Globals` `src/polyalpha/globals.py:51`, `Client` `src/polyalpha/client.py:74`, `docs/history.md`, `examples/chainlink_history_shared.py`.
> Companion: `01-warmup-strat.md` (single strat warmup gate). This plan adds the **shared layer**: one WS + one SQLite recorder serving many concurrent strats (BotHub / multi-Bot / external API).  
> Code refs `file:line` at time of writing.

---

## 1. Problem

`01` solves “my EMA needs `N` closes” for one `Bot`. Real usage is `BotHub` with 20 strats on same asset/TF (`src/polyalpha/bot_hub.py:1341` `BotHub`) or multiple `Bot.run_async()` collocated. Today each `Bot`/`BotHub` opens its own `ChainlinkStreamer` (`src/polyalpha/bot.py:575`, `src/polyalpha/bot_hub.py:1438`) and its own `TimeWindow(120)` (`src/polyalpha/windows.py:22`). Issues:

* N WS connections to `wss://ws-live-data.polymarket.com` (`src/polyalpha/analysis/streaming.py:82`) — rate/ham, duplicated ticks.
* N×120 s in-mem windows — still no 50-day history for any of them.
* If each strat owned its own recorder DB, N DBs or lock contention; if one per process, they stomp.
* External callers (notebooks, HTTP API, `DataFeed`) can’t share the same warm history.

Need a **singleton shared recorder + read API**: one writer (WS → SQLite candles), many readers (`ctx.chainlink_history` in each `StrategyContext`, plus `client.chainlink_history` for ad-hoc queries).

---

## 2. Goal

One recorder, one WS, one SQLite file, N strats read concurrently:

* `hub = BotHub("BTC","5m", chainlink_history=shared_recorder_or_config)` — all `hub.strategy` see same `50×1d`/`20×1h` history
* `client.chainlink_history.candles("BTC","1d",50)` — standalone API outside any bot
* No N×WS: `Globals`-style sharing (`src/polyalpha/globals.py:360` `Globals.price_feed / Globals.defaults`) but for history
* Thread-safe, cross-process safe (SQLite WAL), survives restarts

---

## 3. Non-goals

* Not the single-strat warmup gate (that’s `01` — this reuses it).
* No new WebSocket protocol — still `crypto_prices_chainlink` topic (`src/polyalpha/analysis/streaming.py:462`).
* No cross-asset aggregation v1 (one recorder per asset; multi-asset is N recorders or `Map[asset -> Recorder]`).

---

## 4. Proposed API

### 4a. Shared recorder singleton (recommended)

```python
import polyalpha
from polyalpha.history import ChainlinkRecorder, ChainlinkHistoryConfig

# One writer for the whole process — owns WS + SQLite
shared = ChainlinkRecorder(
    db_path="~/.polyalpha/chainlink.db",
    timeframes=("1m","1h","1d"),
    retention={"1m": 30*86400, "1h": 90*86400, "1d": 400*86400},
)
shared.start("BTC", background=True)  # one WS only

# All hub strats share it (no extra WS, no extra DB)
hub = polyalpha.BotHub("BTC", "5m",
    chainlink_history=shared)  # pass instance → shared, not copied

@hub.strategy("ema50_daily")
def ema50(ctx):
    # ctx.chainlink_history is the SAME object as `shared` (plus per-strat view)
    if not ctx.chainlink_history.is_ready("1d", 50):
        return
    if ctx.chainlink_history.close("1d") > ctx.chainlink_history.ema("BTC","1d",50):
        ctx.buy("UP", 20)

@hub.strategy("rsi_hourly")
def rsi_h(ctx):
    rsi = ctx.chainlink_history.rsi("BTC","1h",14)
    ...

hub.run()  # hub reuses shared WS; recorder outlives hub
```

### 4b. Config-based sharing (let hub own it, but still single)

```python
hub = polyalpha.BotHub("BTC", "5m",
    chainlink_history=ChainlinkHistoryConfig(
        timeframes=("1m","1h","1d"),
        warmup={"1d": 50, "1h": 20},
        db_path="~/.polyalpha/chainlink.db",
        block="wait",          # hub waits once, then all strats start together
        shared=True,           # hint: reuse if globals exists
    ))
# hub internally does: recorder = ChainlinkRecorder.from_config(...); recorder.start()
```

If `Globals` is used, even more explicit:

```python
from polyalpha import Globals
from polyalpha.history import ChainlinkHistoryConfig

g = Globals.defaults(asset="BTC", price_feed=True)  # existing shared feeds
g.chainlink_history = ChainlinkRecorder(
    db_path="~/.polyalpha/chainlink.db",
    timeframes=("1m","1h","1d"))
g.chainlink_history.start("BTC", background=True)

hub = polyalpha.BotHub("BTC","5m", globals=g)  # hub reuses g.price_feed AND g.chainlink_history
client = polyalpha.Client(chainlink_history=g.chainlink_history)  # same DB via API
```

### 4c. Standalone / notebook / HTTP API

```python
import polyalpha

client = polyalpha.Client(chainlink_history="~/.polyalpha/chainlink.db")
# or
from polyalpha.history import ChainlinkRecorder
rec = ChainlinkRecorder(db_path="~/.polyalpha/chainlink.db", read_only=True)

df = client.chainlink_history.candles("BTC", "1d", 50)
#        open    high     low   close  count  start_ts
#  ...   67200   68100   66800   67850     4321  1717977600
print(client.chainlink_history.ema("BTC","1d",50))
print(client.chainlink_history.status())  # {"1m": 432/432, "1h": 20/20, "1d": 50/50}
# no WS needed for reads — pure SQLite
```

### 4d. Per-strat view on top of shared store

`ctx.chainlink_history` is a thin view:

```python
ctx.chainlink_history.candles("1d", 50)  # delegates to shared Store
ctx.chainlink_history.ema("BTC","1d",50)
ctx.chainlink_history.is_ready("1d",50)
ctx.chainlink_history.progress("1d",50)  # 0.0–1.0
ctx.chainlink_history.status()           # {"1d": 50/50, ...}
ctx.name  # strat name available for logging
```

Hub-level helpers:

```python
hub.chainlink_history  # same shared recorder
hub.on_warmup(lambda s: print(f"hub warmup {s}"))
hub.wait_until_ready({"1d": 50}, timeout=600)
```

---

## 5. Architecture

```
                   wss://ws-live-data.polymarket.com  (one connection)
                               │
                    ChainlinkStreamer (streaming.py:100)
                               │  on("price") → _record_price (streaming.py:354)
                               ▼
                   ChainlinkRecorder (SINGLETON, owns CandleBuilder + Store)
                       │  ingest(ts, price) → current[(asset,tf)] → on bucket close → Store.insert
                       │  SQLite WAL  ~/.polyalpha/chainlink.db  (candles, meta)
                       │
          ┌─────────────┼─────────────────┬──────────────────┐
          │             │                 │                  │
   BotHub.StrategyContext  StrategyContext  Client.chainlink_history  notebook / API
   ctx.chainlink_history    ctx2...         client.chainlink_history   ChainlinkRecorder(read_only=True)
   (bot_hub.py:882        (same Store)     (client.py)               (direct)
    cl view)                              query only
          │             │                 │
          └──── all call Store.get_candles → DataFrame → IndicatorCalculator.ema ─┘
```

Sharing invariants:

* **One writer per (db_path, asset).** `ChainlinkRecorder` takes a file lock (`Store` `busy_timeout=5000`, `PRAGMA journal_mode=WAL`). Second writer to same `db_path+asset` either (a) reuses existing singleton if in-process (registry `dict[(db_path,asset) -> Recorder]`), or (b) returns `ReadOnlyStore` if cross-process.
* **Readers never block writer.** `get_candles` is `SELECT ... LIMIT n` with `read_uncommitted=False`; WAL allows concurrent reads.
* **In-process singleton registry** `src/polyalpha/history/registry.py` (tiny): `get_or_create(db_path, asset, config)` — ensures `BotHub` + `Client` in same process share one `ChainlinkStreamer` and one `Store` handle (mirrors `Globals` pattern `src/polyalpha/globals.py:360`).

---

## 6. Data flow vs `01`

Same candle model as `01` §6 (same `candles` table, same `Store`), but now:

* `Store` is the shared truth. `CandleBuilder` lives only in the writer `Recorder`. Readers have no builder, only `Store` query.
* Warmup gate is global: `hub` waits until `Store.count(tf) >= need[tf]` once before fanning first tick to any `StrategyContext`. Individual strats can still check `ctx.chainlink_history.is_ready`.
* `BotHub` integration (vs `Bot` in `01`):

```
BotHub.__init__(chainlink_history=shared_or_config, globals=g)
  → if isinstance(chainlink_history, ChainlinkRecorder): self._chainlink_history = chainlink_history (shared, do not own)
  → elif isinstance(chainlink_history, ChainlinkHistoryConfig): self._chainlink_history = Registry.get_or_create(config.db_path, asset, config) (own if new)
  → elif globals and hasattr(globals, "chainlink_history"): self._chainlink_history = globals.chainlink_history
  → else: no history
BotHub._discover() (bot_hub.py:1818) → assert asset matches recorder asset
BotHub._stream_prices() (bot_hub.py:1860) → before fan-out: if warmup and not ready → fire hub "warmup" event, optionally block
StrategyContext (bot_hub.py:789) gets chainlink_history view: StrategyContext(..., chainlink_history_view=View(shared_store, strat_name))
BotHub._cleanup() (bot_hub.py:2084) → only stop recorder if hub owns it (shared registry refcount → stop when last owner drops)
```

`View` is a 30-line wrapper exposing same `candles/close/ema/sma/rsi/is_ready/status` but capturing `strat_name` for logging.

---

## 7. File map

Create (extends `01` files):

```
src/polyalpha/history/__init__.py        # + exports Registry, View
src/polyalpha/history/candle.py          # (from 01)
src/polyalpha/history/store.py           # + ReadOnlyStore, registry helpers, concurrent tests
src/polyalpha/history/recorder.py        # + singleton guard, attach_streamer(), read_only flag
src/polyalpha/history/registry.py        # NEW: _REGISTRY: dict[tuple, Recorder], get_or_create(), release()
src/polyalpha/history/view.py            # NEW: ChainlinkHistoryView(store, asset, strat_name) — reader facade
src/polyalpha/history/config.py          # + shared: bool flag
```

Modify:

* `src/polyalpha/__init__.py:147` — export `ChainlinkRecorder`, `ChainlinkHistoryConfig`, `ChainlinkHistoryView`
* `src/polyalpha/client.py:269` — `Client(chainlink_history: str|Path|Config|Recorder|bool)` → `self.chainlink_history: ChainlinkHistoryView|Recorder|None` (read-only unless `Client` is writer)
* `src/polyalpha/globals.py:360` — add `chainlink_history: ChainlinkRecorder|None` to `Globals`, handle `start()/stop()` like `price_feed`
* `src/polyalpha/bot.py:503` + `src/polyalpha/bot_hub.py:1341` — accept `chainlink_history`, create or reuse via registry, inject into `TickContext`/`StrategyContext` as `chainlink_history` property (alongside existing `chainlink:336`/`cl:369`/`cl:882`)
* `src/polyalpha/bot_hub.py:789` — `StrategyContext` new arg `chainlink_history: View|None`, property `chainlink_history`, keep `chainlink`/`cl` unchanged for compat

No change to `src/polyalpha/windows.py` or `src/polyalpha/analysis/streaming.py` except optional `recorder.attach(streamer)` convenience.

---

## 8. API surface (unified with `01`)

All readers share same surface; `View` and `Recorder` implement same protocol:

```python
class ChainlinkHistoryProto(Protocol):
    def candles(self, asset: str, timeframe: str, limit: int) -> pd.DataFrame: ...
    def close(self, timeframe: str, asset: str = "BTC") -> float | None: ...
    def ema(self, asset: str, timeframe: str, period: int) -> float | None: ...
    def sma(self, asset: str, timeframe: str, period: int) -> float | None: ...
    def rsi(self, asset: str, timeframe: str, period: int) -> float | None: ...
    def macd(self, asset: str, timeframe: str, fast=12, slow=26, signal=9) -> dict | None: ...
    def bollinger_bands(self, asset: str, timeframe: str, period=20, std=2.0) -> dict | None: ...
    def count(self, timeframe: str, asset: str = "BTC") -> int: ...
    def is_ready(self, timeframe: str, need: int, asset: str = "BTC") -> bool: ...
    def progress(self, timeframe: str, need: int) -> float: ...  # 0.0-1.0
    def status(self, need: dict[str,int] | None = None) -> dict[str, str]: ...  # {"1d": "50/50 ✅"}
    def age_s(self, timeframe: str) -> float: ...
    def is_fresh(self, timeframe: str, max_age_s: float) -> bool: ...
```

Implementation: `SELECT open,high,low,close,count,start_ts FROM candles WHERE asset=? AND timeframe=? ORDER BY start_ts DESC LIMIT ?` → reverse → `DataFrame` → `IndicatorCalculator(df).ema(...)` (`src/polyalpha/analysis/indicators.py:138`) → `float|None` if `len < period` (same `None` semantics as `IndicatorAccessor.ema` `src/polyalpha/bot_hub.py:228`).

Convenience `need` dict for multi-TF: `is_ready_map({"1d":50,"1h":20}) -> bool`, `status(need)` → `{"1d":"12/50","1h":"20/20"}`.

---

## 9. Concurrency & persistence

* **SQLite WAL** `PRAGMA journal_mode=WAL; synchronous=NORMAL; busy_timeout=5000` (same as `src/polyalpha/database/connection.py`). Writer does `INSERT OR REPLACE` batch every candle close (e.g. 1×/min for `1m`), not per-tick. Readers do `SELECT` never blocking.
* **In-process sharing:** `Registry` refcount. `get_or_create(db_path, asset, config)` — if exists, return same `Recorder` (same `ChainlinkStreamer` via `streaming.py:180` `on("price")` fan-out). Prevents N WS.
* **Cross-process:** OS file lock not needed v1; SQLite WAL handles it. Second process opening same `db_path` as writer will get `SQLITE_BUSY` on `INSERT`; catch and downgrade to `ReadOnlyStore` with `log.warning("db busy — opening read-only, start writer in this process or use separate db")`.
* **Hub fan-out safety:** `BotHub._stream_prices` `on_price` (`src/polyalpha/bot_hub.py:1872`) already fans to N `StrategyContext` with try/except isolation — add warmup check before fan-out so one strat’s `is_ready=False` doesn’t affect others.
* **Cleanup ownership:** `Registry.release(recorder)` decrements refcount; only last owner calls `recorder.stop()` (flush + stop `ChainlinkStreamer`). Mirrors `Globals.stop()` pattern.

---

## 10. Configuration (extends `01` §10)

```python
@dataclass
class ChainlinkHistoryConfig:
    timeframes: tuple[str, ...] = ("1m","1h","1d")
    warmup: dict[str,int] = field(default_factory=dict)  # hub waits for this
    db_path: str = "~/.polyalpha/chainlink.db"
    block: Literal["wait","skip","call_with_flag"] = "wait"
    block_timeout: float = 600.0
    retention: dict[str,int] | None = None
    persist_raw: bool = False
    bootstrap: bool = False
    shared: bool = True  # NEW: try to reuse registry/Globals singleton
    read_only: bool = False  # for Client/notebook readers
```

`BotHub("BTC","5m", chainlink_history=ChainlinkHistoryConfig(warmup={"1d":50}, shared=True))` → registry lookup.  
`Client(chainlink_history=True)` → `ChainlinkRecorder(read_only=True, db_path=...)` (no WS).  
`Globals` addition:

```python
@dataclass
class Globals:
    price_feed: ChainlinkStreamer | None = None  # existing
    chainlink_history: ChainlinkRecorder | None = None  # NEW
    # start() also starts chainlink_history if present
    # stop() also stops it
```

Env same as `01` plus `POLYALPHA_CHAINLINK_SHARED=1`.

---

## 11. Edge cases

* Mixed TF needs: strat A needs `50×1d`, strat B needs `10×1m` — hub waits for `max` of all `warmup` dicts if `block="wait"` is union (`{"1d":50,"1m":10}`), then both start together. If `block="skip"`, each strat self-guards.
* Asset mismatch: `hub asset="BTC"` + `recorder asset="ETH"` → `ValueError` at `BotHub.__init__` / `_discover`.
* Lag: if WS stalls (`ChainlinkStreamer._check_stale_data` `src/polyalpha/analysis/streaming.py:544` >30 s), next candle’s `count` drops → readers can filter `df[df.count >= 0.8*expected]` if they care.
* Hot reload: hub `strategy` added at runtime gets same `chainlink_history` view immediately (already warm).
* Notebook + hub same DB: notebook opens `read_only=True` → no lock fight.

---

## 12. Testing

* Reuse `01` unit tests + new:
  * `tests/unit/history/test_registry.py` — same `db_path+asset` returns same object, refcount, second `db_path` returns different recorder, cross-process simulation (two `Store` handles same file → reader sees writer’s commits).
  * `tests/unit/history/test_view.py` — `View` delegates to `Store`, `ema` matches direct `IndicatorCalculator`, `is_ready`/`status` multi-TF.
  * `tests/unit/bots/test_shared_history.py` — mock `HubFeed` (`src/polyalpha/bots/hub_feed.py`) + shared `Recorder` with synthetic ticks: hub with 3 strats shares one recorder (assert `Recorder.ingest` called once per tick, not N×), strat A goes live after `10×1m` while strat B with `skip` logs warmup.
  * `tests/unit/history/test_concurrency.py` — 10 threads `get_candles` while writer `ingest`-loops; no `SQLITE_BUSY` leak, WAL verified.
  * Manual: `examples/chainlink_history_shared.py` (hub 3 strats + standalone client read).

---

## 13. Docs & examples

* `docs/history.md` — single doc for both plans: § Warmup (01) + § Shared (02) with hub diagram, `Registry`/`Globals` pattern, “one writer, N readers” rule, `read_only` note.
* Update `docs/bot.md` — add `BotHub(chainlink_history=...)` + `ctx.chainlink_history` alongside `ctx.cl` (`src/polyalpha/bot.py:369`) / `ctx.chainlink` (`src/polyalpha/bot.py:336`).
* Update `docs/architecture.md` — add `history` box to component diagram, point to `src/polyalpha/history/`.
* `examples/chainlink_history_shared.py`:

```python
import polyalpha
from polyalpha.history import ChainlinkRecorder

shared = ChainlinkRecorder(db_path="~/.polyalpha/chainlink.db",
                           timeframes=("1m","1h","1d"))
shared.start("BTC", background=True)

hub = polyalpha.BotHub("BTC", "5m", chainlink_history=shared)

@hub.strategy("daily_ema")
def daily(ctx):
    ema = ctx.chainlink_history.ema("BTC","1d",50)
    if ema and ctx.chainlink_history.close("1d") > ema:
        ctx.buy("UP", 10)

@hub.strategy("hourly_rsi")
def hourly(ctx):
    if ctx.chainlink_history.rsi("BTC","1h",14) and ctx.chainlink_history.rsi("BTC","1h",14) < 30:
        ctx.buy("DOWN", 10)

# standalone read while hub runs
client = polyalpha.Client(chainlink_history=shared)
print(client.chainlink_history.status({"1d":50,"1h":20}))

hub.run()
```

* Also `examples/chainlink_history_api.py` — pure API read-only demo (no bot).

---

## 14. Rollout (after `01` MVP)

1. **Registry + View** — `registry.py` + `view.py`, make `Store` WAL-concurrent, add `read_only` flag.
2. **Hub/Globals/Client wiring** — `BotHub` + `Globals` + `Client` accept `ChainlinkRecorder|Config`, inject `StrategyContext.chainlink_history` (`src/polyalpha/bot_hub.py:789`), hub-level `warmup` union + `Registry` singleton.
3. **Polish** — hub `on_warmup` event, `status(progress)` pretty table (reuse `comparison.py` style), `export` for history, docs, shared example, concurrency tests.

No breaking change: `01`’s single-bot API still works; `02` is additive (pass same recorder to N consumers).

---

## 15. Open choices (defaults proposed)

* Should hub `block="wait"` wait for union of all strats’ `warmup` dicts (all start together) or per-strat staggered start? Proposed: union wait once, then all start.
* `Globals.chainlink_history` owned by `Globals.start()/stop()` like `price_feed` — or should `BotHub` own it? Proposed: both — if `globals` provides it, hub reuses; otherwise hub owns via registry.
* Cross-process writer conflict UX: silent downgrade to read-only + warning, or raise? Proposed: warning + read-only.

