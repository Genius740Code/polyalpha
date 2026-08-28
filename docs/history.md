# Chainlink History — configurable candle store

> **Status: ✅ IMPLEMENTED** — `src/polyalpha/history/` (`candle.py`, `store.py`, `recorder.py`, `config.py`, `registry.py`, `view.py`) wired to `Bot` (`src/polyalpha/bot.py:84`), `BotHub` (`src/polyalpha/bot_hub.py:12`), `Client` (`src/polyalpha/client.py:74`), `Globals` (`src/polyalpha/globals.py:51`).
> User chooses exactly how much to keep — e.g. `{"1m":10, "1h":50, "1s":20}` — unused timeframes are **deleted automatically**.  
> Storage is **SQLite WAL, `WITHOUT ROWID`, one file at `~/.polyalpha/chainlink.db`** — best for incremental 1-s tick → candle with concurrent readers.

## Why this format?

| Alternative | Problem for live ticks |
|---|---|
| **Parquet / CSV** | Rewrite whole file per flush, no concurrent reads, no ACID |
| **DuckDB / Influx** | Extra dependency / server, heavier for 1-s writes |
| **SQLite WAL (chosen)** | Single file, crash-safe, WAL concurrent reads while writing, `PRAGMA synchronous=NORMAL` + `busy_timeout=5000`, `WITHOUT ROWID` on PK `(asset, timeframe, start_ts)` → ~2× faster lookups, ~4 KB per page. For `10×1m + 50×1h + 20×1s` the DB is **one 4 KB page** — pruned to exactly `keep_n` rows per TF, older rows deleted on each candle close and unused TFs deleted on start. |

Schema (`src/polyalpha/history/store.py:38`):

```sql
CREATE TABLE candles(
  asset TEXT, timeframe TEXT, start_ts INTEGER,
  open REAL, high REAL, low REAL, close REAL, count INTEGER,
  PRIMARY KEY (asset, timeframe, start_ts)
) WITHOUT ROWID;
```

- `start_ts = floor(ts / tf_secs) * tf_secs` (`HISTORY_TIMEFRAME_SECONDS` in `src/polyalpha/history/candle.py:10`: `1s,5s,15s,30s,1m,5m,15m,1h,4h,1d,1w`, alias `24h→1d`)
- `count` = ticks in bucket (data-quality: filter `count < 0.8*expected` if you care about gaps)
- `PRAGMA journal_mode=WAL` → readers (`BotHub` fan-out, `Client` notebooks) never block writer.

## User API — choose your keep

```python
import polyalpha
from polyalpha.history import ChainlinkHistoryConfig

# Example: 10 closed 1-min, 50 1-hour, 20 1-sec candles — nothing else kept
cfg = ChainlinkHistoryConfig(warmup={"1m":10, "1h":50, "1s":20})
# shorthand on Bot / BotHub / Globals / Client:
bot = polyalpha.Bot("BTC", "5m", chainlink_history={"1m":10, "1h":50, "1s":20})
hub = polyalpha.BotHub("BTC", "5m", chainlink_history={"1m":10, "1h":50, "1s":20})
client = polyalpha.Client(chainlink_history={"1m":10, "1h":50, "1s":20})
g = polyalpha.Globals.defaults("BTC", chainlink_history={"1m":10, "1h":50, "1s":20})
```

- `warmup` is **both** the blocking gate and the retention `keep`. If you want to keep more than you wait for, set `keep` separately:

```python
cfg = ChainlinkHistoryConfig(warmup={"1m":10}, keep={"1m":100, "1h":50})
```

- `timeframes` is inferred from `warmup|keep` keys; you can also set it explicitly.
- `block="wait"` (default) → strat not called until warm; `"skip"` → strat is called but `is_ready()` is False; `"call_with_flag"` → always called with flag. Warmup progress via `@bot.on_warmup` / `@hub.on_warmup` / `Globals.start()`.

### Pruning — delete unused

On every `Recorder.start()` and on each candle close:

1. `DELETE WHERE timeframe NOT IN (keep_keys)` → removes `1d` rows if you now only keep `1m`
2. `DELETE WHERE start_ts NOT IN (latest keep_n)` per `(asset, timeframe)` → keeps **exactly** the N you asked for (`src/polyalpha/history/store.py:226`)

Restart with a smaller `keep` instantly trims the file; no unbounded growth.

## ctx API

Inside `on_tick` / `hub.strategy`:

```python
@bot.on_tick
def strat(ctx):
    # ctx.chainlink_history is a ChainlinkHistoryView over the shared DB
    if not ctx.chainlink_history.is_ready("1m", 10):
        return
    # flexible signatures: both work
    ema10 = ctx.chainlink_history.ema("1m", 10)
    ema10b = ctx.chainlink_history.ema("BTC", "1m", 10)
    sma = ctx.chainlink_history.sma("1m", 20)
    rsi = ctx.chainlink_history.rsi("1m", 14)
    macd = ctx.chainlink_history.macd("1m", 12, 26, 9)
    bb = ctx.chainlink_history.bollinger_bands("1m", 20, 2.0)

    df = ctx.chainlink_history.candles("1m", 10)  # DataFrame open/high/low/close/count/timestamp
    close = ctx.chainlink_history.close("1m")
    status = ctx.chainlink_history.status({"1m":10, "1h":50})  # {"1m":"10/10 ✅", "1h":"23/50"}
```

`None` is returned until warm — same semantics as `ctx.indicators.rsi(14)` (`src/polyalpha/bot.py:450`) and `ChainlinkStreamer.window` (`src/polyalpha/analysis/streaming.py:354`).

## Shared mode — one WS → N strats

```python
from polyalpha.history import ChainlinkRecorder
shared = ChainlinkRecorder(db_path="~/.polyalpha/chainlink.db",
                           timeframes=("1m","1h","1s"),
                           warmup={"1m":10, "1h":50, "1s":20})
shared.start("BTC", background=True)  # one wss://ws-live-data.polymarket.com

hub = polyalpha.BotHub("BTC", "5m", chainlink_history=shared)
client = polyalpha.Client(chainlink_history=shared)  # read-only, WAL concurrent
```

`Registry` (`src/polyalpha/history/registry.py:20`) ensures one recorder per `(db_path, asset)` in-process; `Globals.chainlink_history` (`src/polyalpha/globals.py:360`) reuses it.

## Persistence & env

- Default DB `~/.polyalpha/chainlink.db` (WAL, survives restarts → second run is instantly warm)
- `Store` `PRAGMA busy_timeout=5000, cache_size=-64000, synchronous=NORMAL`
- Env: `POLYALPHA_CHAINLINK_HISTORY=1 POLYALPHA_CHAINLINK_DB=... POLYALPHA_CHAINLINK_WARMUP=1m:10,1d:50 POLYALPHA_CHAINLINK_KEEP=1m:100`
- Indicators via `IndicatorCalculator` (`src/polyalpha/analysis/indicators.py:43`) / `_native_ta` (`src/polyalpha/analysis/_native_ta.py:13`)

## Examples

- `examples/chainlink_history_warmup.py` — single `Bot`, custom `--keep 1m:10,1h:50,1s:20`, warmup gate, client read
- `examples/chainlink_history_shared.py` — one `ChainlinkRecorder` → `BotHub` 2 strats + `Client` (WAL concurrent)

## Caveats

- Honest wall-time wait: `10×1m ≈10 min`, `50×1d ≈50 days`. For demos use `bootstrap=True` (DataFeed Binance fallback) — off by default.
- `1d` uses UTC midnight (ET caveat in `src/polyalpha/core/constants.py:104` `build_slug`).
- `persist_raw` (`1s` ticks) defaults `False` — kept only in-mem current bucket → candle; enable only to store raw ticks (bloats).

