# PolyAlpha Audit Report

Generated: 2026-07-23 (updated 2026-07-24)

---

## Test Suite Results

**1715 passed, 0 failed, 61 deselected**

All 8 previously failing tests now pass after DB bug fixes. All fixes verified with full test suite.

---

## Example Runtime Errors

| Example | Error | Root Cause |
|---------|-------|------------|
| `examples/risk_management.py` | `"Market object missing required attribute: question"` | `MockMarket` (line 52-57) lacks `question`, `up_price`, `down_price` [FIXED] |
| `examples/advanced_orders.py` | `"Order amount $250.00 exceeds max position size $200.00"` | Example tries `buy_with_tp_sl` $250 with default `max_position_size=$200` |
| `examples/fee_rebates.py` | Crash on `limit()` | Risk validation prevents order; `MockMarket` in loop uses `i` from outer scope (works but fragile) |
| `examples/analysis.py` | No visible output | Data feed runs but requires Binance/Chainlink — silent if unavailable |
| `examples/bot_simple.py` | Hangs | Waits for stream to attach — no timeout, no network |

---

## Critical Bugs

### 1. `:memory:` SQLite connection pool [FIXED]

**File:** `src/polyalpha/database/connection.py:37-40`

`_get_connection()` now returns a single shared `self._conn` for `:memory:`, avoiding independent connections.

### 2. TP/SL triggers crash in paper trading [FIXED]

**File:** `src/polyalpha/trading/paper_engine.py:1114-1124`

Mock market object now includes `question`, `up_price`, `down_price` so `validate_market()` passes and TP/SL triggers correctly close positions.

### 3. `_save_exit_to_db` accesses missing RealPosition attributes [FIXED]

**File:** `src/polyalpha/trading/real_engine.py:2583-2620`

Now retrieves order-level metadata (`sizing_strategy`, `confidence`, `kelly_fraction`, `fee`) from `first_order` via `position.order_ids`. Uses valid `RealPosition` attributes (`avg_price`, `cost_basis`, `shares`, `pnl` property).

### 4. `_execute_exit_order` assigns to read-only property [FIXED]

**File:** `src/polyalpha/trading/real_engine.py:2565-2570`

`position.pnl` assignment removed. Uses local `pnl` variable and valid `position.current_value` assignment.

### 5. `scale_position` passes argument to parameter-less method [FIXED]

**File:** `src/polyalpha/trading/real_engine.py:1847`

`_resolve_config_and_risk()` takes no args, and `scale_position` correctly calls it with no argument.

### 6. `place_twap_order` references undefined variable [FIXED]

**File:** `src/polyalpha/trading/real_engine.py:3664`

`slice_amount` removed from constructor call. Uses valid `slice_interval` parameter of `TWAPOrder`. Uses `datetime.timedelta` correctly.

### 7. `PreparedStatementManager` is broken [FIXED]

**File:** `src/polyalpha/database/features.py:29-42`

Now caches query strings (not cursors) and executes fresh each time.

### 8. Auto-generated API key never returned [FIXED]

**File:** `src/polyalpha/database/features.py:203-207`

`SecurityManager.add_user()` and `TradeDatabase.add_user()` now return the raw generated API key.

### 9. Connection leak on backup/restore [FIXED]

**File:** `src/polyalpha/database/export.py:118-139`

`finally` blocks now call `_initialize_db()` instead of leaking `_get_connection()`.

### 10. `save_trades_bulk` drops `order_id` and `status` [FIXED]

**File:** `src/polyalpha/database/repository.py:240-258`

Bulk INSERT now includes `order_id` and `status` columns, matching `save_trade()`.

### 11. Bare `except:` catches SystemExit/KeyboardInterrupt [ALREADY FIXED]

**File:** `src/polyalpha/database/connection.py:71`

Already uses `except Exception:`.

### 12. Duplicate `set_trailing_stop` block [FIXED]

**File:** `src/polyalpha/trading/real_engine.py:1649-1665`

Duplicate block removed. Only one code block remains.

---

## High-Severity Issues

### TP/SL ignores multi-wallet mode [FIXED]

**File:** `src/polyalpha/trading/paper_engine.py:798-844`

`set_stop_loss_pct()` and `set_take_profit_pct()` now use `_find_position_across_wallets()` which searches all wallet positions. Also use `wallet._orders` instead of `self._orders` for consistency.

### `refresh_balance` calls `get_allowance()` without required arg [FIXED]

**File:** `src/polyalpha/trading/wallet.py:363`

Now passes `AlchemyClient.CTF_ADDRESS` as the spender address.

### ADX: Equal +DM/-DM not zeroed [FIXED]

**File:** `src/polyalpha/analysis/_native_ta.py:47-48`

Changed `<`/`>` to `<=`/`>=`. When `+DM == -DM`, both are now correctly zeroed per Wilder's DMI specification.

### Bollinger Bands column naming mismatch with pandas-ta [FIXED]

**Files:** `src/polyalpha/analysis/_native_ta.py:97-99`, `src/polyalpha/analysis/indicators.py:396-398`

Both native code and pandas-ta wrapper now use suffix `_0` (matching pandas-ta's `ddof=0` default). `KeyError` eliminated.

### Chainlink data: volume set to zero [FIXED]

**File:** `src/polyalpha/analysis/data_feed.py:605`

Changed from `df["volume"] = 0` to `df["volume"] = float("nan")`. Volume-based indicators (`obv`, `volume_sma`, `volume_roc`) now receive NaN instead of zero for chainlink/coingecko sources. Same fix applied to WebSocket scraping and Binance price-tick paths.

### WebSocket scraping: target_duration calculation [FIXED]

**File:** `src/polyalpha/analysis/data_feed.py:739`

Replaced the unrealistic `lookback_periods * timeframe_seconds` duration with `scraping_timeout`. The loop already breaks early when enough ticks are collected.

### HTTP 429 retried without backoff [FIXED]

**File:** `src/polyalpha/ai/client.py:326-328`

Exponential backoff added: `time.sleep(2 ** attempt)` after 429 and all retryable errors. Also removed the dead `except (AIAuthenticationError, AIModelNotFoundError)` handler.

### Polymarket fee formula duplicated [FIXED]

**Files:** `src/polyalpha/trading/paper_fees.py:61-85`, `src/polyalpha/trading/real_engine.py:2776-2820`

Extracted shared `calculate_polymarket_fee()` and `fee_rate_for_category()` into `polyalpha.core`. Both `PaperFeeManager` and `RealTradingEngine` delegate to these shared functions.

### No `check_same_thread=False` on SQLite connections [ALREADY FIXED]

**File:** `src/polyalpha/database/connection.py:52`

Already set `check_same_thread=False` in `_create_connection()`.

### Migration rollback impossible [FIXED]

**File:** `src/polyalpha/database/connection.py:167-181`

Replaced `executescript()` with individual `cursor.execute()` calls, keeping all statements in the same outer transaction.

### Encryption wired but never applied [FIXED]

**File:** `src/polyalpha/database/features.py:182-193`, `database.py`

Added `encrypt_dict()`/`decrypt_dict()` passthroughs on `SecurityManager`. Wired encryption into `TradeDatabase.save_trade()`, `save_trades_bulk()`, and all `load_*` methods via `_decrypt_trades()`.

---

## Medium-Severity Issues

| Issue | File | Description |
|-------|------|-------------|
| Dead code: `real.py` | `trading/real.py` | Zero imports reference this file (only commented-out line in `real_config.py:524`) |
| Dead code: `_check_tp_sl()` | `paper_engine.py:1026-1032` | [FIXED] — removed, logic lives in `_check_limits_for_wallet` → `_check_tp_sl_for_wallet` |
| Dead code: `RiskManager` methods | `paper_risk.py:121-135` | `check_stop_loss()`/`check_take_profit()` never called from paper engine |
| Correlation ID lock bypass [FIXED] | `monitoring.py:182,199` | `operation_context()` now uses `_correlation_lock` for save/restore |
| Missing validation (4 signals) [FIXED] | `signals.py:722,753,858,916` | Added non-negative validation for `min_change` and `min_percent` params |
| `stop()` doesn't join thread [FIXED] | `streaming.py:159-163` | `stop()` now calls `self._thread.join(timeout=5)` |
| Dead `except` handler [FIXED] | `ai/client.py:335-337` | Removed unreachable `except (AIAuthenticationError, AIModelNotFoundError)` block |
| Autoredeem lies [FIXED] | `auto_redeem.py:414-419` | Fallback path now increments `failed_count` and logs error instead of lying |
| Mixed list/dict config shape | `indicators.py:556-563` | `calculate_all()` accepts lists for SMA/EMA but dicts for MACD/BB — no validation |
| Price adjustment on empty data [FIXED] | `data_feed.py:496-503` | Now uses `historical_data.empty` check before accessing `index[-1]` |
| OAUTH2 enum never handled [FIXED] | `features.py:212-235` | `set_auth_method("oauth2")` now raises `NotImplementedError` with clear message |
| `save_trades_bulk` no intra-batch dedup [FIXED] | `repository.py:233-239` | Now tracks a `seen` set across the batch |
| Pool shared across threads unsafely [ALREADY FIXED] | `repository.py:685-689` | `check_same_thread=False` already set in `_create_connection()` |
| Migration race condition [FIXED] | `connection.py:183-209` | Uses `INSERT OR IGNORE` for schema version |

---

## Design Issues

### Dual single/multi-wallet state machine

**File:** `src/polyalpha/trading/paper_engine.py`

Every method checks `if self._use_multi_wallet and self._wallet_manager:` before operating. Two parallel state tracks (`self._balance/_orders/_positions` vs `wallet._balance/_orders/_positions`) make every method fragile. Should always use a WalletManager with a single default wallet.

### `_get_active_wallet()` creates throwaway PaperWallet on every call

**File:** `src/polyalpha/trading/paper_engine.py:213-223`

Each call constructs a new `PaperWallet` (logs, creates RiskManager, etc.) then immediately replaces the RiskManager. Generates log spam and wasted allocations.

### `PaperEngine` too large (1312 lines)

**File:** `src/polyalpha/trading/paper_engine.py`

Compare to `real_engine.py` which is split into `real_engine.py` + `real_orders.py` + `real_config.py` + `real_risk.py` + `real_wallet.py`. Paper engine has `paper_fees.py`, `paper_config.py`, `paper_risk.py`, `paper_types.py` but the main engine file is still enormous.

### Three retry frameworks

**Files:** `retry.py`, `error_handling.py`, `clob_client.py:388-456`

`retry_on_error`/`retry_with_jitter`, `ErrorRecoveryManager.execute_with_recovery`, and inline retry loops in CLOB client — three separate implementations.

### Migration runs on every `TradeDatabase.__init__`

**File:** `src/polyalpha/database/database.py:44-45`

Wastes I/O re-checking tables and re-querying schema_version on every construction.

### `PaperPosition` vs `RealPosition` have diverging attributes

**Files:** `paper_types.py:90-157`, `real_orders.py:104-190`

Different attribute sets prevent writing generic position-handling code without type-checking.

### `validate_market` too strict for sell operations

**File:** `src/polyalpha/trading/paper_types.py:183-196`

Requires `question`, `up_price`, `down_price` even when only `id` and `slug` are needed (e.g., TP/SL exits). Should be split into granular validators.

---

## Dead Code

| File | Lines | Description |
|------|-------|-------------|
| `trading/real.py` | Entire file | Legacy re-export shim — zero imports reference it |
| `paper_engine.py` | 1026-1032 | `_check_tp_sl()` — no callers |
| `paper_risk.py` | 121-135 | `check_stop_loss()`, `check_take_profit()` — never called from paper engine |
| `connection.py` | 20, 213-215 | `DatabaseConnection._conn` — always `None`, never assigned |
| `ai/client.py` | 335-337 | `except (AIAuthenticationError, AIModelNotFoundError)` — unreachable |
| `features.py` | 182-193 | Encryption infrastructure — fully wired but never called in data layer |

---

## Improvement Opportunities

### High Priority
1. Fix `:memory:` database handling — use `file::memory:?cache=shared` URI or single-connection mode [FIXED]
2. Fix TP/SL mock market object — add `question`, `up_price`, `down_price` [FIXED]
3. Fix `_save_exit_to_db` and `_execute_exit_order` in real_engine [FIXED]
4. Fix `scale_position` parameter passing [FIXED]
5. Fix `place_twap_order` undefined variable [FIXED]
6. Fix PreparedStatementManager [FIXED]
7. Return auto-generated API key to caller [FIXED]
8. Fix connection leak on backup/restore [FIXED]
9. Fix `save_trades_bulk` missing columns [FIXED]
10. Replace bare `except:` in connection.py [FIXED]
11. Add `import asyncio` to test_streaming.py [FIXED]
12. Fix `refresh_balance` → `get_allowance` argument [FIXED]

### Medium Priority
1. Fix ADX equal +DM/-DM bug [FIXED]
2. Fix Bollinger Bands column naming [FIXED]
3. Add backoff for HTTP 429 in AI client [FIXED]
4. Add `check_same_thread=False` to SQLite connections [FIXED]
5. Fix migration rollback (executescript COMMIT issue) [FIXED]
6. Wire encryption into data layer or remove dead code [FIXED]
7. Remove duplicate `set_trailing_stop` block [FIXED]
8. Fix OAUTH2 auth or remove enum value [FIXED]

### Low Priority / Technical Debt
1. Split `paper_engine.py` (1312 lines → smaller files)
2. Eliminate dual single/multi-wallet state
3. Deduplicate fee calculation (paper_fees.py / real_engine.py) [FIXED]
4. Unify three retry frameworks into one
5. Add cache to remaining indicators (macd, adx, bb, etc.)
6. Remove dead code (`real.py`, `_check_tp_sl()`, etc.)
7. Fix `stream_trades_by_asset` manual connection management [FIXED]
8. Add `__del__` to `TradeDatabase`
9. Fix `TIMEFRAME_MAP` deprecated `"1T"` → `"1min"` [FIXED]
10. Replace `O(n)` `pop(0)` with `collections.deque`
