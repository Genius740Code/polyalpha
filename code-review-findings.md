# Polyalpha Code Review — Findings

## 🔴 CRITICAL BUGS

### 1. `src/polyalpha/database/database.py:216` — `sqlite3.Statement` type doesn't exist

```python
self._prepared_statements: Dict[str, sqlite3.Statement] = {}
```

`sqlite3.Statement` is not a type in Python's stdlib. The `.prepare()` method (line 960) also does not exist on `sqlite3.Connection`. Will `AttributeError` at runtime if `_get_prepared_statement` is ever called.

### 2. `src/polyalpha/trading/paper.py:1930` — OCO order returns the same object twice

```python
main_order.oco_order_id = main_order.id  # Self-linked
return main_order, main_order
```

Both return values point to the same order. The `_check_tp_sl` cancel-guard at line 2299 (`if oco_order_id != order.id`) never fires because it's self-linked. One-Cancels-Other is completely non-functional.

### 3. `src/polyalpha/trading/paper.py:1684` — Wrong PnL on partial position sell

```python
pnl = net_amount - position.cost_basis
```

At this point `position.shares` was already reduced (line 1678), but `position.cost_basis` still reflects the original full cost, while `net_amount` only covers the portion being sold. PnL is wildly wrong for partial closes.

### 4. `src/polyalpha/trading/paper.py:971` — Double maker rebate on polymarket fees

Method `_polymarket_fee` applies `MAKER_REBATE_PCT` (25%) to the fee at line 1000, then `_calculate_rebate` at line 1003 applies `maker_rebate_pct` (25%) again. Maker orders get ~43% discount instead of 25%.

### 5. `src/polyalpha/database/database.py:687` — Assumes sequential AUTOINCREMENT IDs

```python
first_id = last_id - len(trades) + 1
```

SQLite does not guarantee gapless `AUTOINCREMENT` sequences, especially with concurrent writes, rollbacks, or partial inserts.

### 6. `src/polyalpha/database/database.py:818-833` — N+1 query in `is_duplicate_trade`

Fetches all matching rows, then iterates each row issuing another `SELECT timestamp` query individually. The first query already has all the data.

### 7. `src/polyalpha/__init__.py:44` — Root logger level guard never triggers

```python
if not _root_logger.level:
```

The root logger always has a default level of `WARNING` (30), so this condition is always `False`. Dead code.

---

## 🟡 LOGIC / SEMANTIC ISSUES

### 8. `src/polyalpha/markets.py:393` — UP index defaults to 0 even when not found

```python
up_idx = _find_index(["up", "higher", "greater"]) or 0
```

If `_find_index` returns `None` (no match), `None or 0` silently maps to the first outcome, which may not be UP.

### 9. `src/polyalpha/trading/paper.py:1523` — `buy_with_tp_sl` bypasses multi-wallet

Uses `self._risk_manager`, `self._balance`, `self._positions` directly instead of `_get_active_wallet()`. Multi-wallet mode is silently ignored.

### 10. `src/polyalpha/trading/paper.py:1272` — Pre-trade checks use wrong balance in multi-wallet

`pre_trade_checks` reads `self._balance` internally, but the caller has already resolved an active wallet with a potentially different balance.

### 11. `src/polyalpha/trading/real.py:1821` — Local balance not synchronized with chain

```python
self._balance -= (amount + fee)
```

This Python variable has no connection to the real USDC balance on Polygon. Divergence is guaranteed after any on-chain activity outside this client.

### 12. `src/polyalpha/trading/real.py:2347-2352` — `positions()` calls full chain sync every time

Every read of `positions()` or `all_positions()` triggers `sync_positions_from_chain()` (RPC + Alchemy API calls). Extremely slow and costly.

### 13. `src/polyalpha/stream.py:260` — Jitter can cancel backoff

```python
delay = max(0, base_delay + jitter_amount)
```

Jitter range is ±20% of `base_delay`. For small values the jitter can nearly cancel the delay entirely.

### 14. `src/polyalpha/trading/auto_redeem.py:323-324` — Manual trigger fires with no positions

```python
if count > 0:
    return True, "manual"
```

If only `trigger_on_time` is enabled but `redeem()` is called explicitly with empty positions, it still returns `should_redeem=True`.

---

## 🔵 DESIGN / MAINTAINABILITY ISSUES

### 15. No async support despite httpx with `http2=True`

All I/O is synchronous. `RateLimiter.acquire_async` is defined but never called anywhere in the codebase.

### 16. `src/polyalpha/trading/error_handling.py:520` — `import random` inside a hot retry loop

Should be a module-level import. Currently re-imported on every backoff retry.

### 17. Two separate CLOB client classes with overlapping concerns

- `src/polyalpha/orderbook/clob.py: ClobBookClient` — REST snapshot fetcher
- `src/polyalpha/trading/clob_client.py: ClobClient` — order placement and signing

Different interfaces, overlapping responsibilities.

### 18. `src/polyalpha/markets.py:508` — Unnecessary `hasattr` guard

```python
if hasattr(self, '_client'):
```

`_client` is unconditionally set in `__init__` on the same code path. Defensive pattern with no actual defensive value.

### 19. Database connection pooling leaks connections

`_get_connection` takes from the pool, but `_return_connection` is not called consistently. Many query methods (`load_trades`, `save_trade`, etc.) never return connections, causing pool exhaustion.

### 20. `src/polyalpha/trading/paper.py:2503-2505` — Fee tracked before share recalculation

`_track_fee_and_rebate` is called with the original `amount`, then `shares` is recomputed from `net = amount - fee + rebate`. The shares used for the position differ from what was tracked in fees.

---

## Summary

| Severity | Count |
|----------|-------|
| 🔴 Critical | 7 |
| 🟡 Logic | 7 |
| 🔵 Design | 6 |
| **Total** | **20** |
