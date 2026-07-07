# Database Support Roadmap

This document outlines the current state and future plans for database support in the polyalpha SDK.

## Current Implementation (v0.2.0)

### Features
- **SQLite Backend**: Full SQLite support using Python's standard library
- **Automatic Trade Saving**: Trades are automatically saved when positions are resolved
- **Manual Trade Saving**: Direct API for saving trades programmatically
- **Query Methods**: Filter trades by market, asset, side, outcome, and date range
- **Statistics**: Calculate win rate, P&L, fees, and other metrics
- **Dynamic Enable/Disable**: Enable or disable database persistence at runtime

### Current API

```python
from polyalpha.database import TradeDatabase

# Initialize database
db = TradeDatabase("trades.db")

# Save trades
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
all_trades = db.load_all_trades()
market_trades = db.load_trades_by_market("btc-updown-5m-1751234700")
asset_trades = db.load_trades_by_asset("BTC")
side_trades = db.load_trades_by_side("UP")
outcome_trades = db.load_trades_by_outcome("WON")
date_trades = db.load_trades_by_date_range(start, end)

# Statistics
stats = db.get_statistics()

# Management
db.delete_trade(trade_id)
db.clear_all_trades()
db.close()
```

### Integration with Paper Trading

```python
# Enable via Client
client = polyalpha.Client(balance=500.0, db_path="trades.db")

# Or enable later
client.paper.enable_database("trades.db")

# Access database
db = client.paper.database

# Disable
client.paper.disable_database()
```

---

## Future Enhancements

### Phase 1: Enhanced SQLite Features

#### 1.1 Advanced Querying
- **Complex Filters**: Combine multiple filter criteria
- **Sorting**: Sort trades by any field (date, P&L, etc.)
- **Pagination**: Load trades in chunks for large datasets
- **Aggregation**: Group trades by asset, timeframe, etc.

```python
# Proposed API
trades = db.load_trades(
    filters={
        "asset": "BTC",
        "side": "UP",
        "outcome": "WON",
        "min_pnl": 0.0,
        "max_pnl": 100.0
    },
    sort_by="pnl",
    sort_order="desc",
    limit=100,
    offset=0
)

# Aggregation
by_asset = db.aggregate_trades(group_by="asset")
by_timeframe = db.aggregate_trades(group_by="timeframe")
```

#### 1.2 Export Formats ✅ (COMPLETED)
- **CSV Export**: Built-in CSV export functionality
- **JSON Export**: Enhanced JSON with metadata
- **Parquet Export**: For data science workflows
- **Excel Export**: For business users

```python
# Implemented API
db.export_csv("trades.csv")
db.export_json("trades.json")
db.export_parquet("trades.parquet")
db.export_excel("trades.xlsx")

# With filters
db.export_csv("btc_trades.csv", filters={"asset": "BTC"})
db.export_json("won_trades.json", filters={"outcome": "WON"})
```

**Implementation Notes:**
- CSV and JSON use only Python standard library (no dependencies)
- Parquet requires `pyarrow` (optional dependency)
- Excel requires `openpyxl` (optional dependency)
- All export methods support the same filter criteria as `load_trades()`
- JSON export includes metadata (export timestamp, total trades, database path)

#### 1.3 Data Validation
- **Schema Validation**: Ensure data integrity
- **Duplicate Detection**: Prevent duplicate trade entries
- **Data Migration**: Versioned schema migrations

#### 1.4 Performance Optimization
- **Connection Pooling**: Reuse database connections
- **Bulk Operations**: Batch insert/update operations
- **Query Caching**: Cache frequently accessed data
- **Index Optimization**: Automatic index management

---

### Phase 2: Multi-Database Support

#### 2.1 PostgreSQL Support
- **Driver**: Use `psycopg2` or `asyncpg`
- **Connection String**: Standard PostgreSQL connection strings
- **Schema**: Auto-create tables and indexes
- **Features**: Full-text search, JSONB support

```python
# Proposed API
from polyalpha.database import PostgreSQLDatabase

db = PostgreSQLDatabase(
    host="localhost",
    port=5432,
    database="polyalpha",
    user="postgres",
    password="secret"
)

# Or via connection string
db = PostgreSQLDatabase("postgresql://user:pass@localhost:5432/polyalpha")
```

#### 2.2 MySQL Support
- **Driver**: Use `mysql-connector-python` or `PyMySQL`
- **Connection String**: Standard MySQL connection strings
- **Schema**: Auto-create tables and indexes

```python
# Proposed API
from polyalpha.database import MySQLDatabase

db = MySQLDatabase(
    host="localhost",
    port=3306,
    database="polyalpha",
    user="root",
    password="secret"
)
```

#### 2.3 MongoDB Support
- **Driver**: Use `pymongo`
- **Schema**: Flexible document schema
- **Features**: Aggregation pipeline, indexing

```python
# Proposed API
from polyalpha.database import MongoDBDatabase

db = MongoDBDatabase(
    host="localhost",
    port=27017,
    database="polyalpha"
)
```

#### 2.4 Cloud Database Support
- **Amazon RDS**: PostgreSQL, MySQL, MariaDB
- **Google Cloud SQL**: PostgreSQL, MySQL
- **Azure Database**: PostgreSQL, MySQL
- **Supabase**: PostgreSQL with real-time features

```python
# Proposed API
from polyalpha.database import CloudDatabase

# Supabase
db = CloudDatabase.supabase(
    project_url="https://xxx.supabase.co",
    api_key="your-key"
)

# AWS RDS
db = CloudDatabase.rds(
    region="us-east-1",
    instance_id="polyalpha-db",
    database="trades"
)
```

#### 2.5 Unified Database Interface
- **Abstract Base Class**: Common interface for all databases
- **Factory Pattern**: Create database instances from configuration
- **Connection Management**: Automatic connection pooling and retry
- **Failover**: Automatic failover to backup databases

```python
# Proposed API
from polyalpha.database import DatabaseFactory

# Create from configuration
config = {
    "type": "postgresql",
    "host": "localhost",
    "port": 5432,
    "database": "polyalpha",
    "user": "postgres",
    "password": "secret"
}
db = DatabaseFactory.create(config)

# Or from environment variables
db = DatabaseFactory.from_env()

# Or from connection string
db = DatabaseFactory.from_url("postgresql://user:pass@localhost:5432/polyalpha")
```

---

### Phase 3: Advanced Features

#### 3.1 Real-time Synchronization
- **Change Data Capture**: Track database changes
- **Webhooks**: Notify external systems on trade updates
- **Streaming**: Real-time trade streaming
- **Replication**: Multi-database replication

```python
# Proposed API
db.enable_streaming()

@db.on_trade_saved
def on_trade(trade):
    print(f"Trade saved: {trade.market_slug}")

@db.on_trade_updated
def on_trade_updated(trade_id, changes):
    print(f"Trade {trade_id} updated: {changes}")
```

#### 3.2 Backup and Restore
- **Automatic Backups**: Scheduled database backups
- **Export/Import**: Full database export and import
- **Point-in-Time Recovery**: Restore to specific timestamps
- **Cloud Storage**: Backup to S3, GCS, Azure Blob

```python
# Proposed API
db.backup("backup_2024_01_01.db")
db.restore("backup_2024_01_01.db")

# Cloud backup
db.backup_to_s3("s3://bucket/backups/trades.db")
db.backup_to_gcs("gs://bucket/backups/trades.db")
```

#### 3.3 Data Analysis Tools
- **Pandas Integration**: Direct DataFrame conversion
- **Time Series Analysis**: Built-in time series functions
- **Performance Metrics**: Advanced performance analytics
- **Visualization**: Built-in charting

```python
# Proposed API
df = db.to_dataframe()

# Time series analysis
daily_pnl = db.get_daily_pnl()
cumulative_returns = db.get_cumulative_returns()
drawdown_analysis = db.get_drawdown_analysis()

# Visualization
db.plot_pnl_over_time()
db.plot_win_rate_by_asset()
db.plot_trade_distribution()
```

#### 3.4 Machine Learning Integration
- **Feature Engineering**: Automatic feature extraction
- **Model Training**: Train ML models on trade data
- **Prediction**: Predict trade outcomes
- **Backtesting**: Historical backtesting framework

```python
# Proposed API
features = db.extract_features()
model = db.train_model(features)
predictions = db.predict(model)
backtest_results = db.backtest(strategy, start_date, end_date)
```

---

### Phase 4: Enterprise Features

#### 4.1 Multi-Tenancy
- **Tenant Isolation**: Separate databases per tenant
- **User Management**: Per-user access control
- **Audit Logging**: Track all database operations
- **Compliance**: GDPR, SOC2 compliance features

```python
# Proposed API
db.set_tenant("tenant_id")
db.set_user("user_id")

# Audit logs
logs = db.get_audit_logs(user_id="user_id", start_date, end_date)
```

#### 4.2 Security
- **Encryption**: At-rest and in-transit encryption
- **Authentication**: Multiple auth methods (API keys, OAuth, JWT)
- **Authorization**: Role-based access control
- **Data Masking**: Sensitive data masking

```python
# Proposed API
db.enable_encryption(key="encryption_key")
db.set_auth_method("oauth2")
db.add_role("analyst", permissions=["read"])
db.add_role("trader", permissions=["read", "write"])
```

#### 4.3 Monitoring and Observability
- **Metrics**: Database performance metrics
- **Logging**: Structured logging with correlation IDs
- **Tracing**: Distributed tracing support
- **Alerting**: Custom alert rules

```python
# Proposed API
metrics = db.get_metrics()
logs = db.get_logs(level="ERROR", start_date, end_date)
db.set_alert("slow_query", threshold_ms=1000)
```

#### 4.4 Scalability
- **Sharding**: Horizontal scaling via sharding
- **Read Replicas**: Read-only replica support
- **Caching Layer**: Redis/Memcached integration
- **Load Balancing**: Automatic load balancing

```python
# Proposed API
db.enable_sharding(shard_key="asset")
db.add_read_replica("replica1")
db.enable_cache(redis_url="redis://localhost:6379")
```

---

## Implementation Priority

### High Priority (Next Release)
1. Advanced Querying (complex filters, sorting, pagination)
2. Export Formats (CSV, JSON, Parquet)
3. Data Validation and Migration
4. Performance Optimization (bulk operations, caching)

### Medium Priority (Following Releases)
1. PostgreSQL Support
2. MySQL Support
3. Backup and Restore
4. Pandas Integration

### Low Priority (Future Releases)
1. MongoDB Support
2. Cloud Database Support
3. Real-time Synchronization
4. Machine Learning Integration
5. Enterprise Features

---

## Dependencies

### Current Dependencies
- **None**: SQLite is in Python's standard library

### Future Dependencies
- **PostgreSQL**: `psycopg2-binary` or `asyncpg`
- **MySQL**: `mysql-connector-python` or `PyMySQL`
- **MongoDB**: `pymongo`
- **Cloud**: Supabase SDK, AWS SDK, Google Cloud SDK
- **Data Analysis**: `pandas`, `numpy` (already optional)
- **Visualization**: `matplotlib`, `plotly` (optional)
- **Caching**: `redis` (optional)

---

## Configuration

### Current Configuration
```python
# Simple file path
db_path = "trades.db"
```

### Future Configuration
```python
# Database configuration object
config = {
    "type": "postgresql",
    "host": "localhost",
    "port": 5432,
    "database": "polyalpha",
    "user": "postgres",
    "password": "secret",
    "pool_size": 10,
    "max_overflow": 20,
    "pool_timeout": 30,
    "pool_recycle": 3600,
    "echo": False,
    "future": True
}

# Environment variables
DATABASE_URL="postgresql://user:pass@localhost:5432/polyalpha"
DATABASE_POOL_SIZE=10
DATABASE_MAX_OVERFLOW=20
```

---

## Migration Guide

### From In-Memory to Database
```python
# Before (in-memory only)
client = polyalpha.Client(balance=500.0)

# After (with database)
client = polyalpha.Client(balance=500.0, db_path="trades.db")
```

### From SQLite to PostgreSQL
```python
# Before (SQLite)
client = polyalpha.Client(balance=500.0, db_path="trades.db")

# After (PostgreSQL)
config = {
    "type": "postgresql",
    "host": "localhost",
    "port": 5432,
    "database": "polyalpha",
    "user": "postgres",
    "password": "secret"
}
client = polyalpha.Client(balance=500.0, db_config=config)
```

### Data Migration
```python
# Export from SQLite
sqlite_db = TradeDatabase("trades.db")
trades = sqlite_db.load_all_trades()

# Import to PostgreSQL
postgres_db = PostgreSQLDatabase(config)
for trade in trades:
    postgres_db.save_trade(**trade.to_dict())
```

---

## Testing Strategy

### Unit Tests
- Test database operations with in-memory databases
- Test query methods with sample data
- Test error handling and edge cases

### Integration Tests
- Test with real PostgreSQL/MySQL instances
- Test connection pooling and retry logic
- Test migration scripts

### Performance Tests
- Benchmark bulk insert operations
- Test query performance with large datasets
- Test connection pooling under load

---

## Documentation

### User Documentation
- Getting started guide
- API reference
- Configuration guide
- Migration guide
- Best practices

### Developer Documentation
- Architecture overview
- Database schema
- Contribution guide
- Testing guide

### Examples
- Basic usage examples
- Advanced query examples
- Export/import examples
- Integration examples

---

## Open Questions

1. **Should we support async database operations?**
   - Pros: Better performance for I/O-bound operations
   - Cons: Increased complexity, breaking changes

2. **Should we use an ORM (SQLAlchemy, Django ORM)?**
   - Pros: Type safety, relationship management
   - Cons: Additional dependency, learning curve

3. **Should we support time-series databases (TimescaleDB, InfluxDB)?**
   - Pros: Optimized for time-series data
   - Cons: Additional complexity, limited use case

4. **Should we support graph databases (Neo4j)?**
   - Pros: Complex relationship queries
   - Cons: Limited use case for trading data

5. **Should we implement a query builder DSL?**
   - Pros: Type-safe queries, better IDE support
   - Cons: Additional complexity, learning curve

---

## Timeline Estimates

- **Phase 1 (Enhanced SQLite)**: 2-3 weeks
- **Phase 2 (Multi-Database)**: 4-6 weeks
- **Phase 3 (Advanced Features)**: 6-8 weeks
- **Phase 4 (Enterprise Features)**: 8-12 weeks

---

## Contributing

Contributions are welcome! Please see the main CONTRIBUTING.md file for guidelines.

When contributing database-related features:
1. Update this roadmap
2. Add tests for new functionality
3. Update documentation
4. Add examples
5. Consider backward compatibility

---

## Changelog

### v0.2.0 (Current)
- Initial SQLite implementation
- Basic CRUD operations
- Query methods
- Statistics calculation
- Integration with paper trading

### Future Releases
- See Implementation Priority section above
