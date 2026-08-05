# polyalpha code review findings

Logic errors, placeholders, and unfinished code grouped by theme so you can fix one group at a time.

- **Risk:** 🔴 CRITICAL (lose money / permanently broken) · 🟠 HIGH (core flow silently broken) · 🟡 MEDIUM (wrong math / state) · 🟢 LOW (sloppy / misleading)
- Everything below was verified directly, not just from an agent scan.
- ✅ items at the end were checked and cleared — not bugs.

---

## hgroup1 — Technical indicator & calculation correctness

> These feed trading decisions. Wrong math here = wrong signals = wrong trades.

| # | Risk | Loc | Issue |
|---|------|-----|-------|
| 1 | 🔴 | `analysis/_native_ta.py:25` | **RSI returns `NaN` in the strongest trends.** `rs = avg_gain / avg_loss.replace(0, np.nan)` — when a series is all-up (or flat) `avg_loss==0` → `NaN` → RSI `NaN` instead of ~100 / ~50. All `rsi_above()`/`rsi_below()` then return `False` in exactly the strongest moves. Also `ewm()` defaults to `adjust=True`, which is **not Wilder's RSI** (needs `adjust=False`). |
| 2 | 🔴 | `analysis/indicators.py:313` | **PSAR always crashes when pandas_ta is installed** (`pandas-ta` is a declared dependency). `ta.psar(..., af=af, af_max=af_max)` — the library kwarg is `max_af`, not `af_max`. Every call raises `TypeError`→`RuntimeError`; `psar_uptrend/downtrend` always raise, `evaluate()` swallows to `False`. Only the native fallback path works. |
| 3 | 🔴 | `analysis/signals/ichimoku.py:203-252` | **Both Chikou signals are tautological, always `False`.** `chikou_span = close.shift(-kijun)` so its last non-NaN value equals the current close → `ichimoku_chikou_above_price` computes `close[-1] > close[-1]`. Should compare against the close 26 bars ago. Dead signal. |
| 4 | 🟡 | `analysis/_native_ta.py:44-60` | **ADX uses SMA everywhere instead of Wilder RMA** (rolling `.mean()` for ATR, +DI/−DI, and ADX). Standard ADX uses Wilder smoothing; values differ materially. |
| 5 | 🟡 | `calculations/base_accessor.py:140` | **`change_abs` is wrong math.** Returns `current * change_pct` instead of `current - oldest`. ~1% error on a 1% move, ~10% on a 10% move. Feeds `price_change_since()`/`rate_of_change()`. |
| 6 | 🟡 | `calculations/base_accessor.py:162,185,206,227,236,245,254` | **Lookback assumes a full window** (`int(len(data)*seconds/max_age)`). Right after streamer start the window is short, so `trend(60)/volatility(60)` analyze only a few seconds of data. |
| 7 | 🟡 | `calculations/market_calculations.py:129-131` | **`rate_of_change` divides by point-count, not time** (`total_time = period * time_interval` with `time_interval` never passed → "per second" is actually per-data-point). |
| 8 | 🟡 | `analysis/signals/vwap.py:229-231` | **`0.0` instead of `None`.** With scraping/Chainlink sources volume is `NaN` → VWAP `NaN` → `composite.summary()` reports `vwap_distance_pct: 0.0`, which reads as "price exactly at VWAP" not "no data". |
| 9 | 🟢 | `data_feed.py:464` | **Binance `quote_volume`/`trades` columns dropped.** `get_quote_volume()`/`get_trade_count()` always `None` — advertised features dead. |
| 10 | 🟢 | `data_feed.py:756,776` | **Scraping loop counts ticks, not candles** (`len(ticks) < lookback_periods`). Stops at ~500 ticks (~90s) instead of 500 candles → `.dropna()` often leaves empty frame → "No data fetched" and configured lookback is never reached. |
| 11 | 🟢 | `volume_calculations.py:236-242` | **`relative_volume` ignores `period`** — percentile computed over all history, not the last `period` points. |

---

## hgroup2 — Paper trading engine

> Paper fill / P&L / balance / advanced-order math. These corrupt simulated results.

| # | Risk | Loc | Issue |
|---|------|-----|-------|
| 12 | 🟡 | `paper_engine.py:726-731` | **Polymarket-mode sells recompute shares at post-slippage price** (`sell_shares = round(net_amount/actual_price)`). A full-position close can leave a partial residual (or a negative residual); `closed_cost_basis` (`:746`) is then mispriced. |
| 13 | 🟡 | `paper_engine.py:698-704` | **Selling "by amount" ignores slippage on proceeds.** `sell_amount`/`net_amount` use the pre-slippage `amount`; slippage never reduces credits. Consistent only in polymarket mode is inconsistent. |
| 14 | 🟡 | `paper_engine.py:870-903` | **OCO is not a real one-cancels-other.** Second leg is stored `filled` with side-inverted SL/TP on a non-existent position (`_check_tp_sl_for_wallet` then tries `sell_position` on it); the actual cancel is a swallowed `OrderNotFound` `pass` (`:1115-1125`). Can trigger sell logic on an unrelated real position if one exists. |
| 15 | 🟡 | `paper_engine.py:1084-1093` vs `826-868` | **SL/TP% computed from `order.price` in the tick loop but from `position.avg_price` in `set_stop_loss_pct`/`set_take_profit_pct`** — inconsistent trigger prices for the same value. |
| 16 | 🟡 | `paper_engine.py:1062-1082` | **Trailing SL/TP init state splits between** `buy_with_tp_sl` (sets `trail_sl_price` relative to current) vs `set_trailing_sl` (relative to `order.price`); re-trailing thresholds diverge depending on entry method. |
| 17 | 🟢 | `paper_risk.py:81` | **`daily_trades` increment happens in `validate_order`, even for orders never filled** (rejected/no-fill) → `max_trades_per_day` burned by failed orders. |
| 18 | 🟢 | `paper_engine.py` `_orders` dict | **Mutable `_orders` read/written from the stream thread** (`_fill_limit`, `_check_limits_for_wallet`) while user threads call `cancel`/`limit`/`positions` with no lock (race window only). |

---

## hgroup3 — Bot lifecycle & resolution

> Multi-cycle automation; whatever is broken here loops every market.

| # | Risk | Loc | Issue |
|---|------|-----|-------|
| 19 | 🟠 | `bot.py:925-951` | **Bot never resolves paper positions** — realised P&L is always `$0`. `_resolve()` iterates `paper.positions()` which returns **only unresolved** positions (`paper_engine.py:932`), then checks `if pos.resolved:` (never True). Nothing calls `paper.resolve()`. So no WIN/LOSS, no payout credit, `onresolve` never fires, `_trade_count` never increments. |
| 20 | 🟡 | `bot_hub.py:1827,1890` | **All indicators built from the UP leg only.** `ctx.rsi/sma/ema/macd/bbands` and `ctx.indicators.*` reflect only `up`; `down` is never recorded. Any DOWN-based signal is computed from UP data. |
| 21 | 🟡 | `bot_hub.py:963-967,988,995` | **`buy_once` guard is inconsistent.** `ctx.buy()` returns `None` after the first buy per market/name (blocks both legs all window), while `ctx.limit()` and `ctx.close_position()` bypass the guard entirely. |
| 22 | 🟡 | `bot_hub.py:1959-1968` / `1976-1986` | **`_rollover` resets `_candle_id` but not `_candle_start_time`/`_candle_open_price`** → spurious `candle_close` on first tick of next market, `_candle_id` reused across markets. |
| 23 | 🟡 | `bot_hub.py:1366-1397`, `chainlink_cache.py:34-45` | **Double Chainlink connection.** `BotHub` constructs `ChainlinkPriceCache` (which opens its own socket) **and** a separate `ChainlinkStreamer`/`_chainlink`, even when the caller supplies a shared `globals.price_feed`. Defeats "one data connection" + doubles oracle sockets. |

---

## hgroup4 — Streaming & discovery & time-sync

> Connectivity and market discovery. If these degrade, the bot silently goes deaf or discovers nothing.

| # | Risk | Loc | Issue |
|---|------|-----|-------|
| 24 | 🟠 | `stream.py:275-281` | **Async API never reconnects.** `run_async()` → `_connect_async()` swallows `ConnectionClosed` (`:466-467`) and returns normally → `run_async()` hits `return` at `:281`. The retry loop is unreachable → `hub.run_async()`/`stream.run_async()` die permanently on any network blip. |
| 25 | 🟡 | `stream.py:499-505` | **PONG handler creates an orphaned task** (`asyncio.ensure_future(self._send_pong(ws))`, never awaited) → "Task exception was never retrieved" on failures; `except Exception: pass` there catches nothing real. |
| 26 | 🟡 | `stream.py:781-800` | **Stale-data reconnect fires on healthy-but-flat markets.** `_last_price_time` only advances when prices change, so a stable market (no events) is force-reconnected every ~90s. |
| 27 | 🟠 | `markets.py:67,235` | **Time-sync is ornamental.** Slug generation uses `int(time.time())`, never `TimeSync.now()`. NTP drift-correction is never consumed → drifted clock still probes wrong slugs → spurious `MarketNotFound`. |
| 28 | 🟡 | `markets.py:241-244` | **The `1mo` slug probe tries a single offset** (vs `range(-days,1)` for 3d/7d) → frequently falls through to `MarketNotFound` |
| 29 | 🟡 | `chainlink_cache.py:47-57` | **Staleness measured from the oracle's reported timestamp, `max_age=60s`.** If updates arrive slower than 60s, `get_price` flaps valid↔`None`; `ctx.spot_price` (`bot_hub.py:842-847`) silently returns `None` on every flap. |
| 30 | 🟢 | `core/time_sync.py:72` | **`struct.unpack("!12I", ...)` raises `struct.error` on >48-byte NTP packets**, and `sync()` only catches `(socket.timeout, OSError)` → a malformed packet defeats the whole multi-server failover. |

---

## hgroup5 — Reporting & records

> Misleading output metrics.

| # | Risk | Loc | Issue |
|---|------|-----|-------|
| 31 | 🟢 | `report/records.py:185-190` | **`slippage` hardcoded `0.0`.** `avg_slippage` (`metrics.py:183`) and the HTML/terminal report are always 0. Comment admits the info isn't stored. |
| 32 | 🟢 | `report/charts.py:116,192,224,…` (`return None`) | Verify chart builders return `None` to mean "chart unavailable" and that callers guard it. (Likely graceful — confirm before changing.) |

---

## hgroup6 — Orderbook, database, wallet, errors

> Data integrity & persistence.

| # | Risk | Loc | Issue |
|---|------|-----|-------|
| 33 | 🟡 | `orderbook/models.py:37` | **Malformed ISO timestamp silently becomes "now"** — `pass` in the `except ValueError`, then returns `datetime.now(timezone.utc)`. Wrong value, no error. |
| 34 | 🟢 | `database/features.py:243` | **OAUTH2 auth raises `NotImplementedError`.** Reachable via `set_auth_method("oauth2")` + `authenticate()`, but has **no current callers** (latent — gate it or finish it). |
| 35 | 🟢 | `database/repository.py:269` | **Bulk-insert id recovery assumes single-writer** (`ORDER BY id DESC LIMIT len`). Under concurrent inserts the returned ids won't match the inserted rows. |
| 36 | ✅ | `wallet_security.py:449` (`_list_known_wallets`) | DOC says "placeholder — in production, maintain a registry" but it returns the in-memory registry. **Clear / fine.** |

---

## ✅ Checked and cleared (not bugs)

- `pass` / `return None` in `error_handling.py` (exception classes, `:332,620`), `clob_client.py` (`:116,121`), `real_engine.py` (`:3597,3602,3641,3787-3798,3847` — iceberg/TWAP completion + credential validation), `transaction_signer.py` (`:469-524` — graceful `None` + `TransactionNotFound: pass`), `wallet_manager.py:371`, `real_position_sizing.py:22` (abstract method), `conditions.py:35` & `strategy/base.py:129` (abstract contracts), `retry.py:15` (docstring example), `globals.py:27` & `liquidations.py:22` (docstring).
- Simulation/mock responses in `clob_client.py` (`_simulate_response`, fake HMAC) only activate via explicit `simulate=True`. **Safe** — just never enable it against the real API in prod.
- `markets.py` parse fallbacks (`:244,260,323,404,480`) and `sniper.py` `return None`/`pass` are legitimate.
- `analysis/indicators.py:920/925` `get_latest_value` returning `None` — all callers check.

---

## Suggested fix order

1. **hgroup1** — wrong indicators (RSI, PSAR, Chikou) change signal decisions → fix first.
2. **hgroup3 #19** (Bot resolution) — core paper loop shows $0 P&L forever.
3. **hgroup4 #24** (async reconnect) + **#27** (time-sync wiring).
4. **hgroup2** paper engine fill math.
5. Rest are medium/low cleanups.