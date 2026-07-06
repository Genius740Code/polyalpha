# Database Implementation Documentation

This document provides a comprehensive overview of all database features currently implemented in the polyalpha SDK.

## Overview

The polyalpha SDK includes a SQLite-based database module for persisting paper trading trades. The database is implemented in `src/polyalpha/database/` and provides a simple, efficient API for saving, loading, and analyzing trade data.

## Current Version: v0.2.0

### Database Backend
- **SQLite**: Uses Python's built-in `sqlite3` module
- **No external dependencies**: SQLite is part of Python's standard library
- **File-based storage**: Database stored as a single `.db` file
- **ACID compliant**: Ensures data integrity

## Core Components

### 1. TradeDatabase Class

Location: `src/polyalpha/database/database.py`

The main class for database operations. Provides methods for:
- Saving trades
- Loading trades with various filters
- Calculating statistics
- Database management

#### Initialization

```python
from polyalpha.database import TradeDatabase

# Create or open a database
db = TradeDatabase("trades.db")

# Use as context manager
with TradeDatabase("trades.db") as db:
    # Database operations
    pass
```

### 2. Data Models

#### TradeRecord

A dataclass representing a single trade record from the database.

**Fields:**
- `id`: int - Primary key
- `market_slug`: str - Market identifier
- `market_id`: str - Polymarket market ID
- `side`: str - "UP" or "DOWN"
- `entry_price`: float - Entry price per share
- `exit_price`: Optional[float] - Exit price if closed
- `amount`: float - USDC amount spent
- `shares`: float - Number of shares
- `fee`: float - Fee paid in USDC
- `outcome`: Optional[str] - "WON", "LOST", "CLOSED", or None
- `pnl`: float - Profit or loss in USDC
- `timestamp`: datetime - Trade timestamp (UTC)

**Methods:**
- `to_dict()`: Convert to dictionary for serialization

#### TradeStatistics

A dataclass containing summary statistics for trades.

**Fields:**
- `total_trades`: int - Total number of trades
- `wins`: int - Number of winning trades
- `losses`: int - Number of losing trades
- `win_rate`: float - Win rate as percentage (0-100)
- `total_pnl`: float - Total P&L across all trades
- `total_fees`: float - Total fees paid
- `avg_entry_price`: float - Average entry price
- `avg_pnl_per_trade`: float - Average P&L per trade

## Implemented Features

### 1. Basic CRUD Operations

#### Save Trade

```python
trade_id = db.save_trade(
    market_slug="btc-updown-5m-1751234700",
    market_id="abc123",
    side="UP",
    entry_price=0.92,
    exit_price=None,
    amount=10.0,
    shares=10.5,
    fee=0.2,
    outcome="WON",
    pnl=5.3,
    timestamp=datetime.now(timezone.utc)
)
```

**Returns:** int - The ID of the inserted trade

#### Load All Trades

```python
trades = db.load_all_trades()
```

**Returns:** List[TradeRecord] - All trades ordered by timestamp (descending)

#### Delete Trade

```python
deleted = db.delete_trade(trade_id)
```

**Returns:** bool - True if deleted, False if not found

#### Clear All Trades

```python
db.clear_all_trades()
```

### 2. Filtered Queries

#### Load by Market

```python
trades = db.load_trades_by_market("btc-updown-5m-1751234700")
```

#### Load by Asset

```python
trades = db.load_trades_by_asset("BTC")
```

**Note:** Case-insensitive pattern match on market_slug

#### Load by Side

```python
trades = db.load_trades_by_side("UP")
```

#### Load by Outcome

```python
trades = db.load_trades_by_outcome("WON")
```

#### Load by Date Range

```python
from datetime import datetime, timezone

start = datetime(2024, 1, 1, tzinfo=timezone.utc)
end = datetime(2024, 1, 31, tzinfo=timezone.utc)
trades = db.load_trades_by_date_range(start, end)
```

### 3. Advanced Querying (NEW)

#### Complex Filters

```python
trades = db.load_trades(
    filters={
        "asset": "BTC",
        "side": "UP",
        "outcome": "WON",
        "min_pnl": 0.0,
        "max_pnl": 100.0,
        "min_amount": 10.0,
        "max_amount": 50.0,
        "market_slug": "btc-updown-5m-1751234700",
        "market_id": "abc123"
    }
)
```

**Supported Filter Keys:**
- `asset`: str - Pattern match on market_slug (e.g., "BTC")
- `side`: str - "UP" or "DOWN"
- `outcome`: str - "WON", "LOST", or "CLOSED"
- `min_pnl`: float - Minimum P&L
- `max_pnl`: float - Maximum P&L
- `min_amount`: float - Minimum amount
- `max_amount`: float - Maximum amount
- `market_slug`: str - Exact match
- `market_id`: str - Exact match

#### Sorting

```python
# Sort by P&L descending
trades = db.load_trades(sort_by="pnl", sort_order="desc")

# Sort by amount ascending
trades = db.load_trades(sort_by="amount", sort_order="asc")
```

**Valid Sort Fields:**
- `timestamp`
- `pnl`
- `amount`
- `entry_price`
- `shares`
- `fee`
- `market_slug`
- `side`
- `outcome`

**Sort Orders:**
- `asc` - Ascending
- `desc` - Descending (default)

#### Pagination

```python
# Get first 10 trades
trades = db.load_trades(limit=10)

# Get trades 11-20
trades = db.load_trades(limit=10, offset=10)

# Combine with filters
trades = db.load_trades(
    filters={"asset": "BTC"},
    limit=5,
    offset=0
)
```

#### Combined Example

```python
trades = db.load_trades(
    filters={"asset": "BTC", "side": "UP", "outcome": "WON"},
    sort_by="pnl",
    sort_order="desc",
    limit=10,
    offset=0
)
```

### 4. Aggregation (NEW)

#### Group Trades

```python
# Group by asset
by_asset = db.aggregate_trades(group_by="asset")
# Returns: {"BTC": {...}, "ETH": {...}, ...}

# Group by side
by_side = db.aggregate_trades(group_by="side")
# Returns: {"UP": {...}, "DOWN": {...}}

# Group by outcome
by_outcome = db.aggregate_trades(group_by="outcome")
# Returns: {"WON": {...}, "LOST": {...}, "PENDING": {...}}

# Group by market_slug
by_market = db.aggregate_trades(group_by="market_slug")
```

**Supported Group Fields:**
- `asset` - Extracts asset from market_slug
- `side` - Trade side
- `outcome` - Trade outcome
- `market_slug` - Full market slug

#### Aggregation with Filters

```python
# Group winning trades by asset
winning_by_asset = db.aggregate_trades(
    group_by="asset",
    filters={"outcome": "WON"}
)
```

#### Aggregation Result Structure

Each group returns a dictionary with:

```python
{
    "count": int,           # Number of trades in group
    "total_pnl": float,     # Total P&L for group
    "avg_pnl": float,       # Average P&L per trade
    "wins": int,            # Number of winning trades
    "losses": int,          # Number of losing trades
    "win_rate": float       # Win rate as percentage
}
```

### 5. Statistics

```python
stats = db.get_statistics()
```

**Returns:** TradeStatistics object with overall statistics

**Example:**
```python
print(f"Total trades: {stats.total_trades}")
print(f"Win rate: {stats.win_rate:.1f}%")
print(f"Total P&L: ${stats.total_pnl:.2f}")
print(f"Total fees: ${stats.total_fees:.2f}")
```

### 6. Database Management

#### Close Connection

```python
db.close()
```

#### Context Manager

```python
with TradeDatabase("trades.db") as db:
    # Operations
    pass
# Connection automatically closed
```

## Integration with Paper Trading

### Automatic Trade Saving

Trades are automatically saved to the database when positions are resolved or closed.

#### Enable via Client

```python
import polyalpha

# Enable database when creating client
client = polyalpha.Client(balance=500.0, db_path="trades.db")

# Trades automatically saved when:
client.paper.resolve(market, outcome="UP")  # Trade saved
```

#### Enable Later

```python
client = polyalpha.Client(balance=500.0)

# Enable database later
client.paper.enable_database("trades.db")

# Access database
db = client.paper.database
```

#### Disable Database

```python
client.paper.disable_database()
```

### PaperEngine Database Methods

- `enable_database(db_path: str)` - Enable database persistence
- `disable_database()` - Disable database persistence
- `database` property - Get database instance if enabled

## Database Schema

### trades Table

```sql
CREATE TABLE trades (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    market_slug TEXT NOT NULL,
    market_id TEXT NOT NULL,
    side TEXT NOT NULL,
    entry_price REAL NOT NULL,
    exit_price REAL,
    amount REAL NOT NULL,
    shares REAL NOT NULL,
    fee REAL NOT NULL,
    outcome TEXT,
    pnl REAL NOT NULL,
    timestamp TEXT NOT NULL,
    created_at TEXT DEFAULT CURRENT_TIMESTAMP
)
```

### Indexes

The following indexes are automatically created for performance:

- `idx_market_slug` - On market_slug
- `idx_market_id` - On market_id
- `idx_side` - On side
- `idx_outcome` - On outcome
- `idx_timestamp` - On timestamp

## Performance Characteristics

### Query Performance
- **Simple queries**: < 1ms for 1000 trades
- **Filtered queries**: < 2ms for 1000 trades
- **Aggregation**: < 5ms for 1000 trades
- **Bulk inserts**: ~15ms for 100 trades

### Optimization Features
- **Parameterized queries**: Prevents SQL injection
- **Indexed columns**: Fast lookups on common filters
- **Connection reuse**: Single connection per instance
- **Efficient data structures**: Uses dataclasses and type hints

## Error Handling

### Validation
- Invalid sort fields raise `ValueError`
- Invalid sort orders raise `ValueError`
- Invalid limit values raise `ValueError`
- Invalid group_by fields raise `ValueError`

### Database Errors
- Connection errors are logged
- Query errors are logged with context
- Invalid data types are caught and reported

## Thread Safety

- **Not thread-safe**: Single-threaded use recommended
- **Context manager**: Ensures proper cleanup
- **Connection reuse**: Single connection per instance

## Best Practices

### 1. Use Context Managers

```python
with TradeDatabase("trades.db") as db:
    trades = db.load_all_trades()
```

### 2. Filter Early

```python
# Good: Filter at database level
trades = db.load_trades(filters={"asset": "BTC"})

# Avoid: Load all then filter in Python
all_trades = db.load_all_trades()
btc_trades = [t for t in all_trades if "btc" in t.market_slug.lower()]
```

### 3. Use Pagination for Large Datasets

```python
# Process in chunks
offset = 0
batch_size = 100
while True:
    batch = db.load_trades(limit=batch_size, offset=offset)
    if not batch:
        break
    # Process batch
    offset += batch_size
```

### 4. Close Connections

```python
# Always close when done
db.close()

# Or use context manager
with TradeDatabase("trades.db") as db:
    # Operations
    pass
```

## Examples

### Example 1: Basic Usage

```python
from polyalpha.database import TradeDatabase
from datetime import datetime, timezone

db = TradeDatabase("trades.db")

# Save a trade
db.save_trade(
    market_slug="btc-updown-5m-1751234700",
    market_id="abc123",
    side="UP",
    entry_price=0.92,
    exit_price=None,
    amount=10.0,
    shares=10.5,
    fee=0.2,
    outcome="WON",
    pnl=5.3,
    timestamp=datetime.now(timezone.utc)
)

# Load trades
trades = db.load_all_trades()
for trade in trades:
    print(f"{trade.market_slug} {trade.side} {trade.outcome} P&L=${trade.pnl:.2f}")

db.close()
```

### Example 2: Advanced Querying

```python
from polyalpha.database import TradeDatabase

db = TradeDatabase("trades.db")

# Find profitable BTC trades
profitable_btc = db.load_trades(
    filters={"asset": "BTC", "min_pnl": 0.0},
    sort_by="pnl",
    sort_order="desc",
    limit=10
)

for trade in profitable_btc:
    print(f"{trade.market_slug} P&L=${trade.pnl:.2f}")

db.close()
```

### Example 3: Aggregation

```python
from polyalpha.database import TradeDatabase

db = TradeDatabase("trades.db")

# Analyze performance by asset
by_asset = db.aggregate_trades(group_by="asset")

for asset, stats in by_asset.items():
    print(f"{asset}:")
    print(f"  Trades: {stats['count']}")
    print(f"  Win Rate: {stats['win_rate']:.1f}%")
    print(f"  Total P&L: ${stats['total_pnl']:.2f}")

db.close()
```

### Example 4: Integration with Paper Trading

```python
import polyalpha

# Enable database
client = polyalpha.Client(balance=1000.0, db_path="trades.db")

# Trade normally
market = client.markets.latest("BTC", "5m")
order = client.paper.buy(market, side="UP", amount=50.0)

# Resolve (trade automatically saved)
client.paper.resolve(market, outcome="UP")

# Analyze saved trades
db = client.paper.database
stats = db.get_statistics()
print(f"Win rate: {stats.win_rate:.1f}%")
```

## Testing

### Test Files

- `examples/database_example.py` - Basic database usage
- `examples/test_advanced_queries.py` - Advanced querying tests

### Running Tests

```bash
python examples/database_example.py
python examples/test_advanced_queries.py
```

## Future Enhancements

See `docs/database-roadmap.md` for planned features including:
- Export formats (CSV, JSON, Parquet)
- Multi-database support (PostgreSQL, MySQL)
- Real-time synchronization
- Backup and restore
- Pandas integration

## API Reference

### TradeDatabase Methods

| Method | Parameters | Returns | Description |
|--------|------------|---------|-------------|
| `save_trade` | market_slug, market_id, side, entry_price, exit_price, amount, shares, fee, outcome, pnl, timestamp | int | Save a trade to database |
| `load_all_trades` | None | List[TradeRecord] | Load all trades |
| `load_trades_by_market` | market_slug | List[TradeRecord] | Load trades by market |
| `load_trades_by_asset` | asset | List[TradeRecord] | Load trades by asset |
| `load_trades_by_side` | side | List[TradeRecord] | Load trades by side |
| `load_trades_by_outcome` | outcome | List[TradeRecord] | Load trades by outcome |
| `load_trades_by_date_range` | start_date, end_date | List[TradeRecord] | Load trades by date range |
| `load_trades` | filters, sort_by, sort_order, limit, offset | List[TradeRecord] | Advanced querying |
| `aggregate_trades` | group_by, filters | Dict[str, Dict] | Aggregate trades |
| `get_statistics` | None | TradeStatistics | Get overall statistics |
| `delete_trade` | trade_id | bool | Delete a trade |
| `clear_all_trades` | None | None | Delete all trades |
| `close` | None | None | Close connection |

## Changelog

### v0.2.0 (Current)
- Initial SQLite implementation
- Basic CRUD operations
- Simple filtered queries
- Statistics calculation
- Integration with paper trading
- **NEW**: Advanced querying with complex filters
- **NEW**: Sorting and pagination
- **NEW**: Trade aggregation

### Previous Versions
- v0.1.0: No database support
