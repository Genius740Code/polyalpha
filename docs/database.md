# Database

The `polyalpha.database` module provides a SQLite-backed persistent store for trades, orders, and positions, with support for encryption, authentication, authorization, and field-level data masking.

---

## Module Overview

| File | Purpose |
|------|---------|
| `database.py` | `TradeDatabase` — main DB class, dataclasses, migrations |
| `security.py` | `DatabaseEncryption`, `AuthenticationManager`, `AuthorizationManager`, `DataMasker` |

All public symbols accessible via `polyalpha.database`.

---

## TradeDatabase

The main class for all database operations. Uses connection pooling (up to 5 connections), LRU caching with TTL, prepared statement caching, WAL mode, and automatic background optimization.

```python
from polyalpha.database import TradeDatabase

db = TradeDatabase("trades.db", enable_wal=True, enable_cache=True)

# Context manager
with TradeDatabase("trades.db") as db:
    db.save_trade(...)
```

### Constructor

| Param | Type | Default | Description |
|-------|------|---------|-------------|
| `db_path` | `str \| Path` | required | Path to SQLite database file |
| `enable_wal` | `bool` | `True` | Enable Write-Ahead Log mode |
| `enable_cache` | `bool` | `True` | Enable in-memory query cache |

---

### Buy / Sell / Portfolio (recommended)

| Method | Description |
|--------|-------------|
| `buy_trade(market_slug, market_id, side, price, amount, shares=None, fee=0.0, market_session=None, user_id=None, timestamp=None) -> int` | Record a buy. Auto-calculates `shares = amount / price`, defaults `fee=0`, `pnl=0`, `outcome=None`, `status="open"`, `timestamp=now` |
| `sell_trade(trade_id, exit_price, pnl=None, outcome=None) -> bool` | Record a sell/exit. Auto-calculates `pnl = (exit_price - entry_price) × shares`, sets `outcome="WON"/"LOST"` and `status="closed"` |
| `get_portfolio() -> dict` | Returns all trades with summary stats (`total_trades`, `closed_trades`, `open_trades`, `wins`, `losses`, `win_rate`, `total_invested`, `total_pnl`, best/worst trade) |
| `portfolio()` | Prints formatted table of all trades + summary |

```python
# Record a buy
tid = db.buy_trade(
    market_slug="btc-up-2025-07-30",
    market_id="0x1234",
    side="UP",
    price=0.85,
    amount=20.0,
)

# Record a sell (auto-calculates PnL)
db.sell_trade(trade_id=tid, exit_price=0.92)

# View everything
db.portfolio()
```

Output of `portfolio()`:

```
────────────────────────────────────────────────────────────────
  POLYALPHA — TRADE PORTFOLIO
────────────────────────────────────────────────────────────────
  ID   MARKET      SIDE  ENTRY    EXIT   AMOUNT     P&L RESULT
  ──── ─────────── ───── ─────── ─────── ─────── ──────── ──────
  2    eth-down... DOWN  0.4500      —    15.00   +0.00   OPEN
  1    btc-up-...  UP    0.8500 0.9200   20.00  $+1.65   WON
────────────────────────────────────────────────────────────────
  SUMMARY
────────────────────────────────────────────────────────────────
  Total trades           2
  Closed trades          1
  Open trades            1
  Wins                   1
  Losses                 0
  Win rate               100.0%
  Total invested         $   35.00
  Total P&L              $   +1.65
────────────────────────────────────────────────────────────────
```

### Legacy Trade CRUD (deprecated — use `buy_trade`/`sell_trade` instead)

| Method | Description |
|--------|-------------|
| `save_trade(...) -> int` | ⚠️ Deprecated. Insert a new trade record. Use `buy_trade()` instead. |
| `save_trades_bulk(trades, check_duplicates=True) -> list[int]` | Bulk insert multiple trades |
| `update_trade_status(order_id, status, filled_shares=0.0, filled_amount=0.0, avg_fill_price=0.0, filled_at=None) -> bool` | Update trade status after fill |
| `delete_trade(trade_id) -> bool` | Delete a trade by ID |
| `clear_all_trades()` | Delete all trades |
| `is_duplicate_trade(market_id, side, timestamp, tolerance_seconds=1) -> bool` | Check for duplicate trades |

> **Note:** The generic `update_trade(trade_id, **fields)` and `get_trade(trade_id)` helpers are
> internal to the `TradeRepository` and are not exposed on the public `TradeDatabase` wrapper.
> To adjust a trade, use `update_trade_status()` or delete and re-insert via `buy_trade()`.

### Querying

| Method | Description |
|--------|-------------|
| `load_all_trades() -> list[TradeRecord]` | All trades, newest first |
| `load_trades_by_market(market_slug) -> list[TradeRecord]` | Filter by market slug |
| `load_trades_by_asset(asset) -> list[TradeRecord]` | Case-insensitive pattern match on slug |
| `load_trades_by_side(side) -> list[TradeRecord]` | Filter by UP/DOWN |
| `load_trades_by_outcome(outcome) -> list[TradeRecord]` | Filter by WON/LOST |
| `load_trades_by_market_session(session) -> list[TradeRecord]` | Filter by trading session |
| `load_trades_by_date_range(start, end) -> list[TradeRecord]` | Filter by datetime range |
| `load_trades(filters=None, sort_by="timestamp", sort_order="desc", limit=None, offset=0) -> list[TradeRecord]` | Advanced querying |

**`load_trades` filter keys:** `asset`, `side`, `outcome`, `min_pnl`, `max_pnl`, `min_amount`, `max_amount`, `market_slug`, `market_id`

| Method | Description |
|--------|-------------|
| `aggregate_trades(group_by="asset", filters=None) -> dict` | Group by asset/side/outcome/market_slug |
| `get_statistics() -> TradeStatistics` | Overall trade statistics |
| `stream_trades(filters=None, batch_size=100) -> Generator` | Memory-efficient streaming |
| `stream_trades_by_asset(asset, batch_size=100) -> Generator` | Streaming by asset |

### Export & Backup

| Method | Description |
|--------|-------------|
| `export_csv(filepath, filters=None)` | Export to CSV |
| `export_json(filepath, filters=None)` | Export to JSON with metadata |
| `export_parquet(filepath, filters=None)` | Export to Parquet (requires `pyarrow`) |
| `export_excel(filepath, filters=None)` | Export to Excel (requires `openpyxl`) |
| `backup(backup_path)` | Local file copy backup |
| `restore(backup_path, overwrite=False)` | Restore from backup |
| `backup_to_s3(s3_uri, ...)` | Backup to AWS S3 (requires `boto3`) |
| `backup_to_gcs(gcs_uri, ...)` | Backup to Google Cloud Storage (requires `google-cloud-storage`) |

### Events & Streaming

| Method | Description |
|--------|-------------|
| `on_trade_saved(callback) -> callback` | Decorator to register hook on trade save |
| `on_trade_updated(callback) -> callback` | Decorator on trade update |
| `on_trade_deleted(callback) -> callback` | Decorator on trade delete |
| `remove_trade_saved_hook(callback)` | Remove hook |
| `remove_trade_updated_hook(callback)` | Remove hook |
| `remove_trade_deleted_hook(callback)` | Remove hook |
| `enable_streaming()` | Enable change tracking |
| `disable_streaming()` | Disable change tracking |
| `is_streaming_enabled() -> bool` | Check streaming status |
| `get_recent_changes(limit=100) -> list[dict]` | Recent change log |

### Database Management

| Method | Description |
|--------|-------------|
| `enable_cache()` / `disable_cache()` | Toggle query cache |
| `clear_cache()` | Clear cached results |
| `execute_parallel_queries(queries, params_list=None, max_workers=4) -> list[list]` | Run queries in parallel |
| `get_parallel_statistics_by_assets(assets, max_workers=4) -> dict` | Parallel stats per asset |
| `analyze_indexes()` | Run ANALYZE |
| `optimize_database()` | PRAGMA optimize, rebuild indexes |
| `get_index_info() -> dict` | Index metadata |
| `rebuild_index(index_name)` | Rebuild specific index |
| `run_migrations()` | Apply pending schema migrations |
| `refresh_materialized_views()` | Refresh `trade_statistics_mv` and `daily_summary_mv` |
| `get_schema_version() -> int` | Current schema version |
| `start_background_optimization(interval_seconds=3600)` | Start daemon optimization thread |
| `stop_background_optimization()` | Stop optimization thread |

### Observability

| Method | Description |
|--------|-------------|
| `get_metrics() -> DatabaseMetrics` | Cache hit rate, query counts, size, pool info |
| `get_logs(level=None, start_date=None, end_date=None, operation=None, limit=100) -> list[LogEntry]` | Query audit log |
| `set_alert(name, metric, threshold, comparison="gt", callback=None)` | Define alert rule |
| `remove_alert(name)` | Remove alert rule |
| `get_alerts() -> dict` | List all alert rules |
| `check_alerts()` | Evaluate all alert thresholds |
| `set_correlation_id(id)` / `clear_correlation_id()` | Correlation tracing |
| `operation_context(operation_name) -> Generator` | Context manager for operation tracking |

### Context Manager

```python
with TradeDatabase("trades.db") as db:
    db.save_trade(...)
# Connection automatically cleaned up
```

---

## Security (`polyalpha.database.security`)

### Encryption (`DatabaseEncryption`)

Fernet symmetric encryption with PBKDF2 key derivation.

```python
from polyalpha.database import DatabaseEncryption

key = DatabaseEncryption.generate_key()
enc = DatabaseEncryption(key=key)
encrypted = enc.encrypt("sensitive data")
decrypted = enc.decrypt(encrypted)
```

| Method | Description |
|--------|-------------|
| `generate_key() -> bytes` | Generate a new random key |
| `key_from_password(password, salt=None) -> bytes` | Derive key from password |
| `key_and_salt_from_password(password) -> tuple[bytes, bytes]` | Key + salt from password |
| `encrypt(data) -> bytes` | Encrypt a string |
| `decrypt(encrypted_data) -> str` | Decrypt bytes |
| `encrypt_dict(data, fields) -> dict` | Encrypt specific dict fields |
| `decrypt_dict(data, fields) -> dict` | Decrypt specific dict fields |
| `enable()` / `disable()` / `is_enabled()` | Toggle encryption |

### Authentication (`AuthenticationManager`)

| `AuthMethod` | Values |
|---|---|
| `NONE`, `API_KEY`, `JWT`, `OAUTH2` | |

| Method | Description |
|--------|-------------|
| `set_method(method)` | Set auth method |
| `get_method() -> AuthMethod` | Get current method |
| `add_user(user_id, username, roles, api_key=None, jwt_secret=None)` | Register user |
| `remove_user(user_id)` | Remove user |
| `generate_api_key() -> str` | Generate new API key (`pk_` prefix) |
| `validate_api_key(api_key) -> str \| None` | Validate and return user ID |
| `generate_jwt_token(user_id, payload=None) -> str` | Generate JWT (HS256) |
| `validate_jwt_token(token, user_id) -> bool` | Validate JWT |

### Authorization (`AuthorizationManager`)

Role-based access control with 4 default roles:

| Role | Permissions |
|------|-------------|
| `admin` | read, write, delete, export, import, backup, restore, manage_users, manage_roles |
| `trader` | read, write, export |
| `analyst` | read, export |
| `viewer` | read |

| Method | Description |
|--------|-------------|
| `add_role(role)`, `remove_role(name)` | Manage roles |
| `check_permission(roles, permission) -> bool` | Check permission |
| `get_all_roles() -> dict` | List all roles |

### Data Masking (`DataMasker`)

Field-level masking for sensitive data.

```python
from polyalpha.database import DataMasker

masker = DataMasker()
masked = masker.mask_record({"api_key": "sk-abc123", "market_id": "0xabcd..."})
```

Default rules mask `market_id`, `api_key`, `secret`, `password`.

| Method | Description |
|--------|-------------|
| `add_rule(rule)` | Add masking rule |
| `remove_rule(field_name)` | Remove rule |
| `mask_field(field_name, value) -> str \| None` | Mask single value |
| `mask_record(record) -> dict` | Mask all matching fields |
| `enable()` / `disable()` / `is_enabled()` | Toggle masking |

---

## Dataclasses

### `TradeRecord`

| Field | Type | Description |
|-------|------|-------------|
| `id` | `int` | Primary key |
| `market_slug` | `str` | Market identifier |
| `market_id` | `str` | Polymarket market ID |
| `side` | `str` | "UP" or "DOWN" |
| `entry_price` | `float` | Entry price per share |
| `exit_price` | `Optional[float]` | Exit price if closed |
| `amount` | `float` | USDC amount |
| `shares` | `float` | Number of shares |
| `fee` | `float` | Fee in USDC |
| `outcome` | `Optional[str]` | "WON", "LOST", "CLOSED" |
| `pnl` | `float` | Profit/loss in USDC |
| `timestamp` | `datetime` | Trade timestamp (UTC) |
| `market_session` | `Optional[str]` | Session (london/new_york/asia/sydney) |

Method: `to_dict() -> dict`

### `TradeStatistics`

`total_trades`, `wins`, `losses`, `win_rate`, `total_pnl`, `total_fees`, `avg_entry_price`, `avg_pnl_per_trade`

### `DatabaseMetrics`

`total_trades`, `database_size_bytes`, `cache_hit_rate`, `cache_size`, `query_count`, `slow_query_count`, `avg_query_time_ms`, `connection_pool_size`, `wal_enabled`, `last_optimization`

### `LogEntry`

`correlation_id`, `timestamp`, `level`, `message`, `operation`, `duration_ms`, `metadata`

### `AlertRule`

`name`, `metric`, `threshold`, `comparison` ("gt"/"lt"/"eq"/"gte"/"lte"), `enabled`, `callback`, `last_triggered`, `trigger_count`

---

## Schema

```sql
CREATE TABLE trades (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    market_slug     TEXT NOT NULL,
    market_id       TEXT NOT NULL,
    side            TEXT NOT NULL,
    entry_price     REAL NOT NULL,
    exit_price      REAL,
    amount          REAL NOT NULL,
    shares          REAL NOT NULL,
    fee             REAL NOT NULL,
    outcome         TEXT,
    pnl             REAL NOT NULL,
    timestamp       TEXT NOT NULL,
    market_session  TEXT,
    created_at      TEXT DEFAULT CURRENT_TIMESTAMP,
    order_id        TEXT,
    status          TEXT DEFAULT 'pending',
    filled_shares   REAL DEFAULT 0.0,
    filled_amount   REAL DEFAULT 0.0,
    avg_fill_price  REAL DEFAULT 0.0,
    filled_at       TEXT,
    user_id         INTEGER REFERENCES users(id)
);
```

Indexes: `idx_market_slug`, `idx_market_id`, `idx_side`, `idx_outcome`, `idx_timestamp`, `idx_market_session`, `idx_duplicate_check`, `idx_user_id`

Materialized views: `trade_statistics_mv` (per-asset), `daily_summary_mv` (per-date)

---

## Integration with Client

```python
import polyalpha

# Enable database on client construction
client = polyalpha.Client(balance=1000.0, db_path="trades.db")

# Access database directly via client.db
client.db.buy_trade(
    market_slug="btc-up-2025-07-30",
    market_id="0x1234",
    side="UP",
    price=0.85,
    amount=20.0,
)
client.db.sell_trade(trade_id=1, exit_price=0.92)
client.db.portfolio()

# Stats
stats = client.db.get_statistics()
```
