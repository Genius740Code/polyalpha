# Codebase Audit Findings

Grouped by theme so similar fixes can be batched together.

---

## Group 1: Thread Safety / Race Conditions

Missing or insufficient locking around shared state.

### 1. Sniper bot state management race CRITICAL — IMPLEMENTED
- **File**: `src/polyalpha/bots/sniper.py:881-929`
- **What's wrong**: State checked under lock (881-883), but price check & order placement (885-929) outside it.
- **Why it matters**: Could place orders when bot should be disarmed.
- **Fix**: Extend state lock to cover entire price check + order placement, or use reentrant lock.

### 2. Balance updates not atomic in paper engine CRITICAL — IMPLEMENTED
- **File**: `src/polyalpha/trading/paper_engine.py`
- **What's wrong**: Balance modify (`wallet.balance +=`/`-=`) have no locking.
- **Why it matters**: Overspending, negative balances in paper trading.
- **Fix**: Added `_balance_lock` around all balance read-modify-write.

### 3. Position shares modification not atomic CRITICAL — IMPLEMENTED
- **File**: `src/polyalpha/trading/paper_engine.py`, `src/polyalpha/trading/real_engine.py`
- **What's wrong**: `position.shares -= sell_shares` not atomic. Concurrent sells corrupt state.
- **Why it matters**: Wrong P&L, position tracking failures.
- **Fix**: Added `_position_lock` in both engines, wrapped all share modifications.

### 7. Stream price updates not thread-safe HIGH — IMPLEMENTED
- **File**: `src/polyalpha/stream.py:127-128`
- **What's wrong**: `self.up` / `self.down` updated from WS callback without lock.
- **Why it matters**: Strategies may read inconsistent/NaN prices.
- **Fix**: Add `threading.Lock` around price updates, or use atomic types.

### 9. Data feed WebSocket lock initialized conditionally HIGH — IMPLEMENTED
- **File**: `src/polyalpha/analysis/data_feed.py:227-233`
- **What's wrong**: `_ws_lock` set to `None` if threading import fails, usage unchecked.
- **Why it matters**: AttributeError or race condition if lock is None.
- **Fix**: Fail hard if threading unavailable, or use no-op lock.

---

## Group 2: Monkey-patching Without Restoration

### 4. OrderBookFeed patches stream methods without cleanup CRITICAL — IMPLEMENTED
- **File**: `src/polyalpha/orderbook/feed.py:142-159`
- **What's wrong**: Patches `stream._dispatch`/`_on_open`, never restores. Multiple feeds overwrite each other.
- **Why it matters**: Lost handlers, corrupted order book state.
- **Fix**: Store originals, restore in `close()`, or switch to event registration.

---

## Group 3: Stale / Uncached Data

Using outdated data after state changes.

### 5. Sniper resolution uses stale prices after stream closes CRITICAL — IMPLEMENTED
- **File**: `src/polyalpha/bots/sniper.py:1075-1081`
- **What's wrong**: `getattr(self._stream, 'up', None)` after close — prices may be stale/reset.
- **Why it matters**: Wrong P&L on position resolution.
- **Fix**: Cache final prices before close, or fetch from REST API.

### 8. Chainlink cache lock not used for timestamp check HIGH — IMPLEMENTED
- **File**: `src/polyalpha/core/chainlink_cache.py:43-47`
- **What's wrong**: Lock protects dict access but doesn't check staleness.
- **Why it matters**: Strategies use stale spot prices.
- **Fix**: Add timestamp staleness check inside lock, return None if too old.

### 14. Stream reconnection clears price state without notification MEDIUM — IMPLEMENTED
- **File**: `src/polyalpha/stream.py:401-403, 494-496`
- **What's wrong**: `_token_prices.clear()` / `_last_trade_prices.clear()` on reconnect, no event emitted.
- **Why it matters**: Strategies use stale cached prices after reconnect.
- **Fix**: Emit "reconnect" or "price_reset" event after clearing.

### 15. Indicator cache not invalidated on data update MEDIUM — IMPLEMENTED
- **File**: `src/polyalpha/analysis/indicators.py:59-74`
- **What's wrong**: Cache keyed by params only, not data version.
- **Why it matters**: Real-time strategies compute on stale data.
- **Fix**: Add data version/timestamp to cache key, or provide explicit invalidation.

---

## Group 4: Calculation / Logic Bugs — IMPLEMENTED

### 6. Paper engine avg_price precision loss HIGH — IMPLEMENTED
- **File**: `src/polyalpha/trading/paper_engine.py:1300-1302`
- **What's wrong**: VWAP `round((shares * avg + shares * price) / total, ...)` accumulates rounding errors.
- **Why it matters**: Incorrect P&L for high-frequency strategies.
- **Fix**: Added `total_cost` field to `PaperPosition`; `cost_basis` now reads `total_cost` directly; `avg_price` computed as `total_cost / shares` without intermediate rounding.

### 10. Sniper exit threshold wrong comparison for DOWN side HIGH — IMPLEMENTED
- **File**: `src/polyalpha/bots/sniper.py:891-893`
- **What's wrong**: `current_price <= exit_price` for both UP and DOWN. DOWN should exit when price *goes up*.
- **Why it matters**: DOWN exits never trigger; holds losing positions.
- **Fix**: Side-specific: `UP → current_price <= exit_price`, `DOWN → current_price >= exit_price`.

### 12. Backtest equity uses single mid-price for all positions MEDIUM — IMPLEMENTED
- **File**: `src/polyalpha/orderbook/backtest.py:104-107`
- **What's wrong**: `sum(pos * mid for pos in positions)` — assumes all positions have same price.
- **Why it matters**: Wrong equity curve for multi-market strategies.
- **Fix**: Track per-symbol `_last_prices` dict; value each position at its own symbol's price.

### 13. Paper engine partial close P&L uses full cost basis MEDIUM — IMPLEMENTED
- **File**: `src/polyalpha/trading/paper_engine.py:728-738`
- **What's wrong**: `pnl = net_amount - closed_cost_basis` where `closed_cost_basis` is total, not proportional.
- **Why it matters**: Partial closes have wrong P&L.
- **Fix**: `closed_cost_basis = position.cost_basis * (sell_shares / position.shares)`.

---

## Group 5: Error Handling

### 11. Broad exception catching hides errors MEDIUM — IMPLEMENTED
- **File**: 204 matches across codebase
- **What's wrong**: `except Exception as exc:` everywhere, no specific handling.
- **Why it matters**: Silent failures, hard to debug production issues.
- **Fix**: Catch specific exceptions where possible, or log full stack traces.
- **Changes**:
  - `bot.py`: Silent `except Exception: pass` → `log.warning()`/`log.debug(exc_info=True)` in cleanup, rollover, Binance refresh, and indicator compute methods
  - `stream.py`: Silent `except Exception: pass` → `log.debug(exc_info=True)` for WS close and PONG send
  - `clob_client.py`: Narrowed `except Exception` to `except ImportError` for eth_account deps; all API error handlers changed from `log.error(...)` to `log.exception(...)`
  - `real_engine.py`: All 20+ error handlers changed from `log.error("msg: %s", e)` to `log.exception("msg")`
  - `real_wallet.py`: All error handlers changed to `log.exception(...)` with full stack traces
  - `paper_engine.py`: DB save/init error handlers changed to `log.exception()`
  - `retry.py`: Unexpected error handlers changed to `log.exception()`
  - `wallet.py`, `alchemy_client.py`, `auto_redeem.py`: Error handlers changed to `log.exception()`
  - `error_handling.py`: Circuit breaker, retry, rollback, and backup error handlers changed to `log.exception()`
  - `database/`: Migration, query, backup error handlers changed to `log.exception()`
  - `notifications/telegram.py`: Send error handler changed to `log.exception()`
  - `ai/client.py`: Retry error handler changed to `log.exception()`

---

## Group 6: Code Quality / Maintainability

### 16. Magic number for position close threshold LOW
- **File**: `src/polyalpha/trading/paper_engine.py:730`
- **What's wrong**: `if position.shares <= 0.001` — magic number.
- **Fix**: Define `MIN_SHARE_THRESHOLD` constant or add to PaperConfig.

### 17. Duplicate fee calculation in polymarket mode LOW
- **File**: `src/polyalpha/trading/paper_engine.py:1188-1191, 1261-1264`
- **What's wrong**: Fee calculated twice in polymarket mode, no explanation.
- **Fix**: Add comment explaining polymarket fee structure.

### 18. Sniper price validation range too strict LOW
- **File**: `src/polyalpha/bots/sniper.py:976-982`
- **What's wrong**: Rejects `price > 1.0` but edge cases briefly exceed it.
- **Fix**: Configurable range, warn instead of hard reject.

---

## Summary

| Group | Total | IMPLEMENTED | Remaining |
|-------|-------|-------------|-----------|
| 1 — Thread Safety | 5 | 5 | 0 |
| 2 — Monkey-patching | 1 | 1 | 0 |
| 3 — Stale Data | 4 | 4 | 0 |
| 4 — Calculation Bugs | 4 | 4 | 0 |
| 5 — Error Handling | 1 | 1 | 0 |
| 6 — Code Quality | 3 | 0 | 3 |
| **Total** | **18** | **15** | **3** |
