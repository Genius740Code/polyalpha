# Plan — Chainlink History for TA (EMA-50 etc.)

> **Status: ✅ IMPLEMENTED** — `src/polyalpha/history/` (candle/store/recorder/config + registry/view), `Bot`/`BotHub`/`Client`/`Globals` wiring, `docs/history.md`, examples + tests.
> Two features, two docs. Read in order.

* **01 — Warmup strat** (`plans/01-warmup-strat.md`): run a strat that *collects 1 s Chainlink, compresses to candles, and blocks until `N` closes* (e.g. `10×1m`, `50×1d`) before trading. Single `Bot`, owns its recorder + SQLite, honest warmup, `block="wait"|"skip"` gate, `ctx.chainlink_history.ema("1d",50)`.

* **02 — Shared API / N strats** (`plans/02-shared-api.md`): one recorder, one WS, one DB → N `BotHub` strats + `Client`/notebook readers. Singleton `Registry`, `Globals.chainlink_history`, `ChainlinkHistoryView` per strat, WAL-concurrent SQLite, union warmup.

Both share same core:

* **Package:** `src/polyalpha/history/` — `candle.py` / `store.py` / `recorder.py` / `config.py` (01) + `registry.py` / `view.py` (02)
* **Data:** `candles(asset,tf,start_ts, o/h/l/c, count)` in `~/.polyalpha/chainlink.db` (WAL), built by flooring `ts` to `TIMEFRAME_SECONDS` (`src/polyalpha/core/constants.py:22`) on each Chainlink tick from `wss://ws-live-data.polymarket.com` (`src/polyalpha/analysis/streaming.py:82`). Indicators via `IndicatorCalculator` (`src/polyalpha/analysis/indicators.py:43`) / `_native_ta` (`src/polyalpha/analysis/_native_ta.py`).
* **Integration:** `Client` / `Bot` (`src/polyalpha/bot.py:503`) / `BotHub` (`src/polyalpha/bot_hub/hub.py:1341`) accept `chainlink_history=ChainlinkHistoryConfig|ChainlinkRecorder`; expose `ctx.chainlink_history` alongside existing `ctx.chainlink` (`src/polyalpha/bot.py:336`) / `ctx.cl` (`src/polyalpha/bot.py:369`); persist across restarts.

Start with `01` MVP (single strat warmup), then `02` (shared layer) is additive.

