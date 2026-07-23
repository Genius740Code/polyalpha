# PolyAlpha Audit Report

Generated: 2026-07-23

---

## Test Suite Results

**1715 passed, 0 failed, 61 deselected**

All 8 previously failing tests now pass after DB bug fixes.

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

### 3. `_save_exit_to_db` accesses missing RealPosition attributes

**File:** `src/polyalpha/trading/real_engine.py:2583-2620`

Accesses `position.entry_price`, `position.amount`, `position.fee`, `position.sizing_strategy`, `position.confidence`, `position.kelly_fraction` — none of these exist on `RealPosition` (they're on `RealOrder`). Every call raises `AttributeError`.

### 4. `_execute_exit_order` assigns to read-only property

**File:** `src/polyalpha/trading/real_engine.py:2565-2570`

```python
position.pnl = exit_value - position.amount
```
`position.pnl` is a `@property` with no setter (`real_orders.py:131`). Assignment raises `AttributeError: can't set attribute`. Also `position.amount` doesn't exist on `RealPosition`.

### 5. `scale_position` passes argument to parameter-less method

**File:** `src/polyalpha/trading/real_engine.py:1847`

```python
config = self._resolve_config_and_risk(wallet)
```
`_resolve_config_and_risk()` has signature `def _resolve_config_and_risk(self)` — takes no args. Raises `TypeError`.

### 6. `place_twap_order` references undefined variable

**File:** `src/polyalpha/trading/real_engine.py:3664`

```python
twap_order = TWAPOrder(
    ...
    slice_amount=slice_amount,  # NameError: never defined
)
```
`slice_amount` is not computed anywhere, and it's not a valid `__init__` parameter for `TWAPOrder` (it uses `slice_interval`).

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

### 12. Duplicate `set_trailing_stop` block

**File:** `src/polyalpha/trading/real_engine.py:1649-1665`

Lines 1649-1656 and 1659-1665 are identical code. The second block is unreachable — first block already set the attributes.

---

## High-Severity Issues

### TP/SL ignores multi-wallet mode [FIXED]

**File:** `src/polyalpha/trading/paper_engine.py:798-844`

`set_stop_loss_pct()` and `set_take_profit_pct()` now use `_find_position_across_wallets()` which searches all wallet positions. Also use `wallet._orders` instead of `self._orders` for consistency.

### `refresh_balance` calls `get_allowance()` without required arg [FIXED]

**File:** `src/polyalpha/trading/wallet.py:363`

Now passes `AlchemyClient.CTF_ADDRESS` as the spender address.

### ADX: Equal +DM/-DM not zeroed

**File:** `src/polyalpha/analysis/_native_ta.py:47-48`

```python
plus_dm[plus_dm < minus_dm] = 0
minus_dm[minus_dm < plus_dm] = 0
```
When `+DM == -DM`, neither condition is true, so both remain non-zero. Wilder's DMI specifies both should be zero.

### Bollinger Bands column naming mismatch with pandas-ta

**Files:** `src/polyalpha/analysis/_native_ta.py:97-99`, `src/polyalpha/analysis/indicators.py:396-398`

Native code produces `BBL_20_2.0_2.0` but pandas-ta produces `BBL_20_2.0_0` (third param is `ddof`, not `std`). When pandas-ta IS installed, the wrapper crashes with `KeyError`.

### Chainlink data: volume set to zero

**File:** `src/polyalpha/analysis/data_feed.py:605`

```python
df["volume"] = 0
```
All volume-based indicators (`obv`, `volume_sma`, `volume_roc`) produce garbage when source is Chainlink.

### WebSocket scraping: target_duration calculation is wrong

**File:** `src/polyalpha/analysis/data_feed.py:739`

For 500 candles at 5m: 500 × 300 = 150,000s ≈ 41.7h. With 2s interval between fetches, `future.result(timeout=30)` on line 701 times out immediately.

### HTTP 429 retried without backoff

**File:** `src/polyalpha/ai/client.py:326-328`

Rate limit responses trigger immediate retry with no delay — guaranteed to hit another 429.

### Polymarket fee formula duplicated

**Files:** `src/polyalpha/trading/paper_fees.py:61-85`, `src/polyalpha/trading/real_engine.py:2776-2820`

Identical fee calculation logic in two places. DRY violation.

### No `check_same_thread=False` on SQLite connections [ALREADY FIXED]

**File:** `src/polyalpha/database/connection.py:52`

Already set `check_same_thread=False` in `_create_connection()`.

### Migration rollback impossible [FIXED]

**File:** `src/polyalpha/database/connection.py:167-181`

Replaced `executescript()` with individual `cursor.execute()` calls, keeping all statements in the same outer transaction.

### Encryption wired but never applied

**File:** `src/polyalpha/database/features.py:182-193`, `repository.py`

`enable_encryption()` sets up the infrastructure, but `encrypt_dict()`/`decrypt_dict()` are never called in any `save_*` or `load_*` method.

---

## Medium-Severity Issues

| Issue | File | Description |
|-------|------|-------------|
| Dead code: `real.py` | `trading/real.py` | Zero imports reference this file (only commented-out line in `real_config.py:524`) |
| Dead code: `_check_tp_sl()` | `paper_engine.py:1026-1032` | [FIXED] — removed, logic lives in `_check_limits_for_wallet` → `_check_tp_sl_for_wallet` |
| Dead code: `RiskManager` methods | `paper_risk.py:121-135` | `check_stop_loss()`/`check_take_profit()` never called from paper engine |
| Correlation ID lock bypass | `monitoring.py:182,199` | `operation_context()` reads/writes `_current_correlation_id` directly, ignoring `_correlation_lock` |
| Missing validation (4 signals) | `signals.py:722,753,858,916` | `price_above_by`, `price_below_by`, `price_up`, `price_up_by_percent` don't validate non-negative params |
| `stop()` doesn't join thread | `streaming.py:159-163` | Background thread not joined — can outlive the Streamer object |
| Dead `except` handler | `ai/client.py:335-337` | Sibling `except` can't catch exceptions from sibling's `except` handler |
| Autoredeem lies | `auto_redeem.py:414-419` | Fallback path increments `redeemed_count` without actually redeeming |
| Mixed list/dict config shape | `indicators.py:556-563` | `calculate_all()` accepts lists for SMA/EMA but dicts for MACD/BB — no validation |
| Price adjustment on empty data | `data_feed.py:496-503` | `index[-1]` on empty DataFrame raises `IndexError` |
| OAUTH2 enum never handled | `features.py:212-235` | `set_auth_method("oauth2")` makes auth always return False |
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
1. Fix `:memory:` database handling — use `file::memory:?cache=shared` URI or single-connection mode
2. Fix TP/SL mock market object — add `question`, `up_price`, `down_price` [FIXED]
3. Fix `_save_exit_to_db` and `_execute_exit_order` in real_engine
4. Fix `scale_position` parameter passing
5. Fix `place_twap_order` undefined variable
6. Fix PreparedStatementManager
7. Return auto-generated API key to caller
8. Fix connection leak on backup/restore
9. Fix `save_trades_bulk` missing columns
10. Replace bare `except:` in connection.py
11. Add `import asyncio` to test_streaming.py
12. Fix `refresh_balance` → `get_allowance` argument

### Medium Priority
1. Fix ADX equal +DM/-DM bug
2. Fix Bollinger Bands column naming
3. Add backoff for HTTP 429 in AI client
4. Add `check_same_thread=False` to SQLite connections
5. Fix migration rollback (executescript COMMIT issue)
6. Wire encryption into data layer or remove dead code
7. Remove duplicate `set_trailing_stop` block
8. Fix OAUTH2 auth or remove enum value

### Low Priority / Technical Debt
1. Split `paper_engine.py` (1312 lines → smaller files)
2. Eliminate dual single/multi-wallet state
3. Deduplicate fee calculation (paper_fees.py / real_engine.py)
4. Unify three retry frameworks into one
5. Add cache to remaining indicators (macd, adx, bb, etc.)
6. Remove dead code (`real.py`, `_check_tp_sl()`, etc.)
7. Fix `stream_trades_by_asset` manual connection management
8. Add `__del__` to `TradeDatabase`
9. Fix `TIMEFRAME_MAP` deprecated `"1T"` → `"1min"`
10. Replace `O(n)` `pop(0)` with `collections.deque`
