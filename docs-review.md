# PolyAlpha Documentation Review

Date: 2026-08-04
Scope: `README.md`, all 28 files in `docs/`, plus root-level `strats.md` and `TOD`.
Method: Full read of the docs plus cross-check of every documented API claim against the source in `src/polyalpha/`.

---

## Verdict

**Good — recent, readable, well-organized, ~90% accurate.** Not perfect: a handful of real
inaccuracies (including broken copy-paste examples), one doc with duplicated/overlapping
sections, and two stray files at the repo root that do not belong in a docs set.

- **Up to date:** Yes. Docs were last committed 2026-08-03 22:04, *after* the latest source
  commit (2026-08-03 20:05). Recent features (liquidation tracker, CVD aggTrade feed,
  `sweep()`, `favourite()`, advanced time windows, `buy_once_per_market`) are covered.
- **Easy to read:** Mostly yes. Consistent structure (tables, code examples, quick-start),
  strong README entry point. Problems: duplicated sections in `docs/bot.md`, no `docs/` index,
  two stray files at the repo root.
- **Accurate:** ~90%. Issues below are grouped by severity and were verified against code
  (`file:line` citations given).

---

## Severity 1 — Broken examples / documented APIs that do not exist

These are copy-paste traps: following the docs raises an exception or calls a method that
doesn't exist.

### 1. `docs/streaming.md:132` — broken example
```python
stream = client.stream(market, price_threshold=0.0005)
```
`Client.stream()` only accepts `(market, retries=None)` (`src/polyalpha/client.py:223`).
This raises `TypeError`. `price_threshold` exists only on the `Stream` constructor.

Also two wrong defaults in the same file:
- `streaming.md:20` says `price_threshold` default `0.0001`; code default is `0.0`
  (`core/constants.py:180`).
- `streaming.md:18` says `retries` default `10`; true for direct `Stream(...)` but
  `client.stream()` uses the client's retry count (default **3**) when omitted.

### 2. `README.md:512–513` — Database example is wrong
```python
db.get_statistics(start_date="2026-01-01", end_date="2026-07-22")   # takes no args
db.get_trades(market_slug="btc-updown-*")                            # method does not exist
```
`get_statistics()` takes no arguments (`database/database.py:377`). There is no `get_trades`
anywhere in the SDK. The correct query API is `load_trades(filters={...})`,
`load_trades_by_market(slug)`, or `stream_trades()`.

### 3. `docs/migration-guide.md:35–36, 43–44, 51` — wrong "new" API names
| Line | Claimed | Reality |
|------|---------|---------|
| :35 | `client.paper.order(id)` | Does not exist (`PaperEngine` has `orders()`, `open()` only) |
| :36 | `client.paper.position(id)` | Does not exist (`PaperEngine` has `positions()` only) |
| :43 | `client.paper.open(market)` | `open()` takes **no** argument and returns open limit orders |
| :44 | `client.paper.attach_stream(stream)` | Requires `market`: `attach_stream(stream, market)` (`paper_engine.py:1142`) |
| :51 | `Position .slug()` → `.market_slug` | Backwards. `PaperPosition` has a `slug` field; the `Market` field was renamed `market_slug` → `slug` |

Also `:49` claims `auto_redeem()` was removed; it still exists as a property returning the
`AutoRedeemEngine` (`paper_engine.py:131`).

### 4. `docs/bot.md:293–333` — 7 documented `ctx.cl` methods do not exist
The "Chainlink Calculations (`ctx.cl`)" section documents `change_abs`, `trend`, `direction`,
`volatility`, `high`, `low`, `range`. `ctx.cl` is a `TimeWindow` (`bot.py:147`,
`bot_hub.py:828`) which exposes only `value`, `age_s`, `change_pct`, `get_value_at`
(`windows.py`). These calls raise `AttributeError`.

### 5. `docs/bot.md:359, 382` — `ctx.binance.avg_volume(period)` does not exist
`BinanceAccessor` (`bot_hub.py`) has `change_pct`, `change_abs`, `trend`, `direction`,
`volatility`, `vol_ratio`, `volume_trend`, `volume_surge` — but **no** `avg_volume`.

### 6. `docs/bot.md:931` — `stats` shape is wrong
Documented `stats` includes a `"variants"` key. The real `BotHub.stats` returns only
`{"ticks": ..., "strategies": ...}` (`bot_hub.py:1548-1565`).

### 7. `docs/database.md:99–100` — `update_trade` / `get_trade` do not exist publicly
`TradeDatabase` exposes `update_trade_status` and `delete_trade`, but the generic
`update_trade(trade_id, **fields)` and `get_trade(trade_id)` are only on the internal
`TradeRepository` (`database/repository.py:690, 679`), not the public `TradeDatabase` wrapper.

---

## Severity 2 — Wrong defaults / descriptions / counts

| Where | Claim | Reality |
|-------|-------|---------|
| `README.md:436`, `analysis.md:29` | Default data source is `"binance"` | Default is `"scraping"` (`data_feed.py:119`); valid sources are binance/chainlink/custom/websocket/scraping — `"coingecko"` is not a source |
| `README.md:3, 411` | "20+ TA indicators" | Exactly **19** public indicator methods (`analysis/indicators.py`) |
| `api-reference.md:188` | IndicatorCalculator "28 indicators" | 19 (count includes `__init__`, properties, helpers) |
| `api-reference.md:205` | OpenRouterClient "12 methods" | 6 public methods (`ai/client.py`) |
| `api-reference.md:40` | Stream "6 events" | 8 events — `price_reset` and `price_anomaly` are undocumented (`stream.py:77`) |
| `api-reference.md:107` | `BookTrade` in `orderbook/models.py` | The class is `Trade`; the `BookTrade` alias is defined in `__init__.py:176` |
| `api-reference.md:241+` | "Complete Export List" | Omits `CircuitBreakerOpenError`, `ManualInterventionRequiredError`, `TransactionRollbackError`, `BackupError`, `ConfigurationError`, `AuthenticationError`, `RateLimitExceeded`, `GasEstimationError`, `TransactionRebroadcastError` — all listed in `errors.md` |
| `conditions.md:295–339, 505–508` | Param named `candles` | Code uses `candles_back` (`conditions.py:1012+`); keyword calls per docs fail (positional works) |
| `bot.md:424–427` | `price_change(candles=1)`, `price_up(candles=1)`, `price_above_by(amount=50)` | Code uses `candles_back` and `min_change` (`bot_hub.py:379–406`); `analysis.md:536` documents the correct names |
| `bots.md:131` | `post_window_timeout` default `30` | Code default is `10` (`constants.py:83`) |
| `bot.md:288` | `ctx.chainlink.last_update` is `float \| None` | It is `datetime \| None` (`analysis/streaming.py:130`) |
| `bot.md:357` | `volume_trend` returns `INCREASING/DECREASING/STABLE` | Lowercase `increasing/decreasing/stable` (`bot_hub.py:541–566`) |
| `troubleshooting.md:30` | Backoff "starting at 1s" | Base `retry_delay` default is `3.0` (`stream.py` constructor) |

---

## Severity 3 — Structure / readability

1. **`docs/bot.md` has duplicated/overlapping sections** (evidence of layered edits):
   - Two different `ctx.cl` sections: "Chainlink Calculations" (lines 293–333, contains the
     non-existent methods) and "Chainlink Price Window" (lines 429–460, correct).
   - Two overlapping `ctx.binance` sections (lines 335–387 and 388–427).
   - Orphaned table row at line 460: `| price_above_by(min_change) | bool |` dangles under
     the wrong table (duplicate of line 427).
   - `ctx.cl` is used throughout but omitted from the TickContext property table.
2. **No `docs/` index page.** Getting-started points to individual files; there is no single
   overview of the 28 doc files.
3. **Stray root files:**
   - `strats.md` (17 KB) — a strategy/example catalog that duplicates the README examples
     index and `docs/strategies.md`, and references a different repo URL
     (`github.com/Genius740Code/polyalpha`) than the placeholder in the README.
   - `TOD` — a scratch todo file with loose notes; not documentation.
4. **Placeholder repo URL:** `README.md:6` and `docs/getting-started.md:15` use
   `https://github.com/your-org/polyalpha.git`. Should be the real URL.
5. **Minor documentation gaps:** `price_reset` / `price_anomaly` stream events undocumented;
   `client.check()` and `client.time_sync` undocumented (`client.py:173`); `Bot.onresolve`
   and `Bot.on_price_anomaly` undocumented (`bot.py:596, 611`); `SniperConfig.max_price`
   undocumented (`sniper.py:398`).

---

## Verified accurate (no action needed)

- `docs/client.md`, `docs/errors.md` — all constructor params, attributes, methods, and 19
  core + 7 AI error classes match the code.
- `docs/calculations.md` — all `MarketCalculations` / `VolumeCalculations` /
  `ChainlinkAccessor` methods and signatures.
- `docs/trading.md` — all `PaperEngine` / `RealTradingEngine` / `AutoRedeemConfig` methods;
  all `PaperOrder` / `PaperPosition` fields (the P&L fields are computed properties, as noted).
- `docs/orderbook.md`, `docs/ai.md`, `docs/reporting.md`, `docs/wallet.md`,
  `docs/telegram-notifications.md`, `docs/configuration.md`, `docs/logging.md`,
  `docs/security.md`, `docs/testing.md`, `docs/contributing.md`, `docs/strategies.md`,
  `docs/examples-guide.md` — cross-checks found no discrepancies.
- `README.md` preset tables (8 paper presets + real-trading presets) match
  `trading/paper_config.py` / `trading/real_config.py` exactly.
- No broken relative links between docs; all `examples/*.py` files referenced in the README
  exist.

---

## Recommended fix list (prioritized)

1. **Fix broken examples / wrong APIs** (Severity 1): `streaming.md`, `README.md` (database
   section), `migration-guide.md`, `bot.md` (`ctx.cl`, `avg_volume`, `stats`), `database.md`.
2. **Dedupe `docs/bot.md`** — collapse the two `ctx.cl` and two `ctx.binance` sections; remove
   the orphaned table row; add `ctx.cl` to the property table.
3. **Correct defaults / counts / param names** (Severity 2): `analysis.md`, `README.md`
   (indicator count), `api-reference.md`, `conditions.md`, `bots.md`, `troubleshooting.md`.
4. **Decide slug-timestamp semantics** — `docs/markets.md` says the slug timestamp is the
   window *end*; `markets.py` module docstring says window *start*, and `build_slug`'s
   parameter is named `window_end_ts` while callers pass window-start timestamps. Align docs
   and code.
5. **Housekeeping:** remove `strats.md` and `TOD` from the repo root (or move `strats.md`
   content into `docs/`); add a small `docs/README.md` index; fix the placeholder repo URL;
   document the two new stream events.
