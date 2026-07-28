# Codebase Audit Findings

## CRITICAL (Could cause bad trades or lost funds)

### 1. Race condition in sniper bot state management IMPLEMENTED
- **File**: `src/polyalpha/bots/sniper.py:881-929`
- **What's wrong**: State is checked with lock (line 881-883), but price check and order placement (lines 885-929) happen outside the lock. Between checking state and placing order, another thread could change state.
- **Why it matters**: Could place orders when bot should be disarmed, causing unintended trades during state transitions.
- **Suggested fix**: Extend the state lock to cover the entire price check and order placement logic, or use a reentrant lock pattern.

### 2. Balance updates not atomic in paper engine
- **File**: `src/polyalpha/trading/paper_engine.py:1193,1223,716,951,538,553`
- **What's wrong**: Balance modifications (`wallet.balance -= amount`, `wallet.balance += amount`) have no locking. In BotHub with multiple strategies sharing data, concurrent balance checks/updates could race.
- **Why it matters**: Could cause overspending, negative balances, or lost funds in paper trading simulation.
- **Suggested fix**: Add `threading.Lock` around all balance read-modify-write operations in PaperEngine.

### 3. Position shares modification not atomic
- **File**: `src/polyalpha/trading/paper_engine.py:729`
- **What's wrong**: `position.shares -= sell_shares` is not atomic. Concurrent sells on same position could lead to negative shares or corrupted state.
- **Why it matters**: Could corrupt position tracking, causing incorrect P&L calculations and position management failures.
- **Suggested fix**: Add locking around position modifications in `_upsert_position` and sell operations.

### 4. OrderBookFeed patches stream methods without cleanup
- **File**: `src/polyalpha/orderbook/feed.py:142-159`
- **What's wrong**: Patches `stream._dispatch` and `stream._on_open` but never restores original methods. If multiple feeds attach to same stream, patches overwrite each other.
- **Why it matters**: Could cause event handlers to be lost or called incorrectly, leading to missed price updates or corrupted order book state.
- **Suggested fix**: Store original methods and restore them in `close()` method, or use a proper event registration pattern instead of monkey-patching.

### 5. Sniper resolution uses stale prices after stream closes
- **File**: `src/polyalpha/bots/sniper.py:1075-1081`
- **What's wrong**: Resolution uses `getattr(self._stream, 'up', None)` after stream closes. Stream may have been closed for some time, prices could be stale or reset to initial values.
- **Why it matters**: Could resolve positions with incorrect prices, leading to wrong P&L calculations and incorrect trade records.
- **Suggested fix**: Cache final prices before stream closes, or fetch final prices from REST API for resolution.

## HIGH (Could cause stuck positions or wrong signals)

### 6. Paper engine position avg_price calculation precision loss
- **File**: `src/polyalpha/trading/paper_engine.py:1300-1302`
- **What's wrong**: VWAP calculation `round((pos.shares * pos.avg_price + shares * price) / total, PRICE_ROUNDING)` could accumulate rounding errors across many partial fills.
- **Why it matters**: Over time, avg_price drift could cause incorrect P&L calculations, especially for high-frequency strategies.
- **Suggested fix**: Track total cost basis and total shares separately, compute avg_price as `total_cost / total_shares` only when needed for display.

### 7. Stream price updates not thread-safe
- **File**: `src/polyalpha/stream.py:127-128`
- **What's wrong**: `self.up` and `self.down` are updated from WebSocket callback thread without locks. Reading threads may see partially updated values (though Python's GIL makes this less likely, it's still unsafe).
- **Why it matters**: Could cause strategies to read inconsistent or NaN prices, leading to incorrect trading decisions.
- **Suggested fix**: Add `threading.Lock` around price updates, or use atomic types for price storage.

### 8. Chainlink cache lock not used for timestamp check
- **File**: `src/polyalpha/core/chainlink_cache.py:43-47`
- **What's wrong**: Lock protects dict access but doesn't check timestamp staleness. Could return very old prices if stream stopped updating.
- **Why it matters**: Strategies using stale spot prices could make incorrect trading decisions based on outdated market data.
- **Suggested fix**: Add timestamp staleness check inside the lock, return None if price is too old.

### 9. Data feed WebSocket lock initialized conditionally
- **File**: `src/polyalpha/analysis/data_feed.py:227-233`
- **What's wrong**: `self._ws_lock` is set to `None` if threading import fails, but code may still try to use it later without checking.
- **Why it matters**: Could cause AttributeError in environments without threading, or race conditions if lock is None.
- **Suggested fix**: Either fail hard if threading unavailable, or provide a no-op lock implementation.

### 10. Sniper exit threshold check uses wrong comparison
- **File**: `src/polyalpha/bots/sniper.py:891-893`
- **What's wrong**: Exit threshold check `current_price <= self.config.exit_price` for UP side. If price drops below exit, it cancels. But for DOWN side, logic should be inverted (should exit when price goes up).
- **Why it matters**: DOWN-side exit threshold would never trigger correctly, could hold losing positions too long.
- **Suggested fix**: Add side-specific logic: `if side == "UP" and current_price <= exit_price` or `if side == "DOWN" and current_price >= exit_price`.

## MEDIUM (Error handling or edge cases)

### 11. Broad exception catching hides errors
- **File**: Multiple files (204 matches across codebase)
- **What's wrong**: Many `except Exception as exc:` blocks catch all exceptions without specific handling, making debugging difficult.
- **Why it matters**: Silent failures or generic error messages make it hard to diagnose issues in production.
- **Suggested fix**: Catch specific exceptions where possible, or at least log full stack traces.

### 12. Backtest equity calculation uses current mid-price for all positions
- **File**: `src/polyalpha/orderbook/backtest.py:104-107`
- **What's wrong**: `_update_equity` uses single mid-price for all positions: `position_value = sum(pos * mid for pos in self.positions.values())`. This assumes all positions have same price, which is incorrect for multi-asset strategies.
- **Why it matters**: Equity curve will be wrong for strategies trading multiple markets, leading to incorrect performance metrics.
- **Suggested fix**: Track position entry prices and calculate position value per symbol using appropriate prices.

### 13. Paper engine sell position P&L calculation timing
- **File**: `src/polyalpha/trading/paper_engine.py:728-738`
- **What's wrong**: P&L is calculated as `net_amount - closed_cost_basis` but `closed_cost_basis` is captured before shares are reduced. For partial closes, this is incorrect.
- **Why it matters**: Partial position closes will have incorrect P&L, skewing performance metrics.
- **Suggested fix**: Calculate cost basis proportionally: `closed_cost_basis = position.cost_basis * (sell_shares / position.shares)`.

### 14. Stream reconnection clears price state without notification
- **File**: `src/polyalpha/stream.py:401-403, 494-496`
- **What's wrong**: On reconnect, `_token_prices.clear()` and `_last_trade_prices.clear()` are called but no event is emitted to notify handlers of state reset.
- **Why it matters**: Strategies may continue using stale cached prices after reconnection, leading to incorrect decisions.
- **Suggested fix**: Emit a "reconnect" event or "price_reset" event after clearing state.

### 15. Indicator cache not invalidated on data update
- **File**: `src/polyalpha/analysis/indicators.py:59-74`
- **What's wrong**: Cache is keyed by indicator parameters but not by data version. If underlying data changes, cached indicators remain stale.
- **Why it matters**: Real-time strategies using indicators could compute values on stale data, leading to wrong signals.
- **Suggested fix**: Add data version/timestamp to cache key, or provide explicit cache invalidation when data updates.

## LOW (Style or minor issues)

### 16. Magic number for position close threshold
- **File**: `src/polyalpha/trading/paper_engine.py:730`
- **What's wrong**: `if position.shares <= 0.001` uses magic number 0.001 without constant or config.
- **Why it matters**: Makes code harder to maintain and threshold unclear.
- **Suggested fix**: Define `MIN_SHARE_THRESHOLD` constant or add to PaperConfig.

### 17. Duplicate fee calculation in polymarket mode
- **File**: `src/polyalpha/trading/paper_engine.py:1188-1191, 1261-1264`
- **What's wrong**: Fee is calculated twice when `fee_mode == "polymarket"` - once on original amount, once on net amount. This appears intentional but is confusing.
- **Why it matters**: Could lead to incorrect fee calculations if logic is misunderstood during maintenance.
- **Suggested fix**: Add comment explaining why double calculation is needed for polymarket fee structure.

### 18. Sniper order placement price validation range
- **File**: `src/polyalpha/bots/sniper.py:976-982`
- **What's wrong**: Validates price in range `(0, 1.0]` but prediction markets can have edge cases where prices briefly exceed 1.0 due to data errors.
- **Why it matters**: Could skip valid trades during data anomalies, or fail to catch actual invalid prices.
- **Suggested fix**: Add configurable price validation range with warning for prices outside normal bounds rather than hard rejection.

---

**Summary**: 18 issues found - 5 critical, 5 high, 7 medium, 4 low. Priority focus should be on the race conditions in balance/position updates and the state management issues in the sniper bot, as these could directly cause financial losses or incorrect trading behavior.
