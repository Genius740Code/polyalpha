"""
SQLite database for paper trading trade persistence.

This module provides a simple, efficient SQLite-based database for storing
and retrieving paper trading trades. It supports:
- Saving individual trades
- Loading trades by various filters
- Statistics calculation
- Easy export to other formats
"""

from __future__ import annotations

import csv
import json
import logging
import sqlite3
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional, List, Dict, Any, Callable
from functools import lru_cache
import hashlib
from threading import Lock

log = logging.getLogger(__name__)


@dataclass
class TradeRecord:
    """Record of a single trade from the database."""
    id: int
    market_slug: str
    market_id: str
    side: str
    entry_price: float
    exit_price: Optional[float]
    amount: float
    shares: float
    fee: float
    outcome: Optional[str]  # "WON" | "LOST" | "CLOSED" | None
    pnl: float
    timestamp: datetime
    market_session: Optional[str] = None  # "london" | "new_york" | "asia" | "sydney" | None
    
    def to_dict(self) -> dict:
        """Convert to dictionary for serialization."""
        return {
            "id": self.id,
            "market_slug": self.market_slug,
            "market_id": self.market_id,
            "side": self.side,
            "entry_price": self.entry_price,
            "exit_price": self.exit_price,
            "amount": self.amount,
            "shares": self.shares,
            "fee": self.fee,
            "outcome": self.outcome,
            "pnl": self.pnl,
            "timestamp": self.timestamp.isoformat(),
            "market_session": self.market_session,
        }


@dataclass
class TradeStatistics:
    """Statistics summary for all trades."""
    total_trades: int
    wins: int
    losses: int
    win_rate: float
    total_pnl: float
    total_fees: float
    avg_entry_price: float
    avg_pnl_per_trade: float


class TradeDatabase:
    """
    SQLite database for paper trading trade persistence.
    
    This class provides a simple interface for saving and loading
    paper trading trades to a SQLite database file.
    
    Parameters
    ----------
    db_path : str or Path
        Path to the SQLite database file. Will be created if it doesn't exist.
    
    Example
    -------
    >>> db = TradeDatabase("trades.db")
    >>> db.save_trade(
    ...     market_slug="btc-updown-5m-1751234700",
    ...     market_id="abc123",
    ...     side="UP",
    ...     entry_price=0.92,
    ...     exit_price=None,
    ...     amount=10.0,
    ...     shares=10.5,
    ...     fee=0.2,
    ...     outcome="WON",
    ...     pnl=5.3,
    ...     timestamp=datetime.now(timezone.utc)
    ... )
    >>> trades = db.load_all_trades()
    """
    
    def __init__(self, db_path: str | Path, enable_wal: bool = True, enable_cache: bool = True):
        """
        Initialize the database.
        
        Parameters
        ----------
        db_path : str or Path
            Path to the SQLite database file.
        enable_wal : bool, optional
            Enable WAL (Write-Ahead Logging) mode for better concurrency (default: True).
        enable_cache : bool, optional
            Enable query result caching (default: True).
        """
        self.db_path = Path(db_path)
        self._conn: Optional[sqlite3.Connection] = None
        self._enable_wal = enable_wal
        self._cache_enabled = enable_cache
        self._query_cache: Dict[str, List[TradeRecord]] = {}
        self._cache_max_size = 100
        
        # Event hooks for real-time synchronization
        self._trade_saved_hooks: List[Callable[[TradeRecord], None]] = []
        self._trade_updated_hooks: List[Callable[[int, Dict[str, Any]], None]] = []
        self._trade_deleted_hooks: List[Callable[[int], None]] = []
        self._hooks_lock = Lock()
        
        # Streaming state
        self._streaming_enabled = False
        
        self._initialize_db()
    
    def _get_connection(self) -> sqlite3.Connection:
        """Get or create database connection."""
        if self._conn is None:
            self._conn = sqlite3.connect(self.db_path)
            self._conn.row_factory = sqlite3.Row
            
            # Enable WAL mode for better concurrency
            if self._enable_wal:
                self._conn.execute("PRAGMA journal_mode=WAL")
                self._conn.execute("PRAGMA synchronous=NORMAL")
            
            # Set performance optimizations
            self._conn.execute("PRAGMA busy_timeout=5000")  # 5 second timeout
            self._conn.execute("PRAGMA temp_store=MEMORY")  # Store temp tables in memory
            self._conn.execute("PRAGMA mmap_size=268435456")  # 256MB memory-mapped I/O
            
        return self._conn
    
    def _initialize_db(self) -> None:
        """Create database schema if it doesn't exist."""
        conn = self._get_connection()
        cursor = conn.cursor()
        
        # Create schema version table for migrations
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS schema_version (
                version INTEGER PRIMARY KEY,
                applied_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
            )
        """)
        
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS trades (
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
                market_session TEXT,
                created_at TEXT DEFAULT CURRENT_TIMESTAMP
            )
        """)
        
        # Create indexes for common queries
        cursor.execute("""
            CREATE INDEX IF NOT EXISTS idx_market_slug 
            ON trades(market_slug)
        """)
        cursor.execute("""
            CREATE INDEX IF NOT EXISTS idx_market_id 
            ON trades(market_id)
        """)
        cursor.execute("""
            CREATE INDEX IF NOT EXISTS idx_side 
            ON trades(side)
        """)
        cursor.execute("""
            CREATE INDEX IF NOT EXISTS idx_outcome 
            ON trades(outcome)
        """)
        cursor.execute("""
            CREATE INDEX IF NOT EXISTS idx_timestamp 
            ON trades(timestamp)
        """)
        
        # Create composite index for duplicate detection
        cursor.execute("""
            CREATE INDEX IF NOT EXISTS idx_duplicate_check 
            ON trades(market_id, side, timestamp)
        """)
        
        # Create index for market session
        cursor.execute("""
            CREATE INDEX IF NOT EXISTS idx_market_session 
            ON trades(market_session)
        """)
        
        # Initialize schema version if not exists
        cursor.execute("INSERT OR IGNORE INTO schema_version (version) VALUES (1)")
        
        conn.commit()
        log.info("Database initialized at %s", self.db_path)
    
    def _validate_trade_data(
        self,
        market_slug: str,
        market_id: str,
        side: str,
        entry_price: float,
        exit_price: Optional[float],
        amount: float,
        shares: float,
        fee: float,
        outcome: Optional[str],
        pnl: float,
        timestamp: datetime,
        market_session: Optional[str] = None,
    ) -> None:
        """
        Validate trade data before saving.
        
        Raises
        ------
        ValueError
            If any validation fails.
        """
        # Validate required string fields
        if not market_slug or not isinstance(market_slug, str):
            raise ValueError("market_slug must be a non-empty string")
        if not market_id or not isinstance(market_id, str):
            raise ValueError("market_id must be a non-empty string")
        
        # Validate side
        if side not in ("UP", "DOWN"):
            raise ValueError(f"side must be 'UP' or 'DOWN', got '{side}'")
        
        # Validate numeric fields
        if entry_price < 0:
            raise ValueError(f"entry_price must be non-negative, got {entry_price}")
        if exit_price is not None and exit_price < 0:
            raise ValueError(f"exit_price must be non-negative, got {exit_price}")
        if amount < 0:
            raise ValueError(f"amount must be non-negative, got {amount}")
        if shares < 0:
            raise ValueError(f"shares must be non-negative, got {shares}")
        if fee < 0:
            raise ValueError(f"fee must be non-negative, got {fee}")
        
        # Validate outcome
        valid_outcomes = {"WON", "LOST", "CLOSED", None}
        if outcome not in valid_outcomes:
            raise ValueError(f"outcome must be one of {valid_outcomes}, got '{outcome}'")
        
        # Validate timestamp
        if not isinstance(timestamp, datetime):
            raise ValueError(f"timestamp must be a datetime object, got {type(timestamp)}")
        if timestamp.tzinfo is None:
            raise ValueError("timestamp must be timezone-aware")
        
        # Validate market_session if provided
        if market_session is not None:
            valid_sessions = {"london", "new_york", "asia", "sydney"}
            if market_session not in valid_sessions:
                raise ValueError(f"market_session must be one of {valid_sessions}, got '{market_session}'")
    
    def save_trade(
        self,
        market_slug: str,
        market_id: str,
        side: str,
        entry_price: float,
        exit_price: Optional[float],
        amount: float,
        shares: float,
        fee: float,
        outcome: Optional[str],
        pnl: float,
        timestamp: datetime,
        market_session: Optional[str] = None,
        check_duplicates: bool = True,
    ) -> int:
        """
        Save a trade to the database.
        
        Parameters
        ----------
        market_slug : str
            Market slug identifier.
        market_id : str
            Market ID from Polymarket.
        side : str
            "UP" or "DOWN".
        entry_price : float
            Entry price per share.
        exit_price : float or None
            Exit price if position was closed.
        amount : float
            USDC amount spent.
        shares : float
            Number of shares received.
        fee : float
            Fee paid in USDC.
        outcome : str or None
            "WON", "LOST", "CLOSED", or None if pending.
        pnl : float
            Profit or loss in USDC.
        timestamp : datetime
            Trade timestamp (UTC).
        market_session : str or None, optional
            Market session name (e.g., "london", "new_york", "asia", "sydney").
        check_duplicates : bool, optional
            Whether to check for duplicate trades (default: True).
        
        Returns
        -------
        int
            The ID of the inserted trade.
        
        Raises
        ------
        ValueError
            If validation fails or duplicate detected.
        """
        # Validate data
        self._validate_trade_data(
            market_slug, market_id, side, entry_price, exit_price,
            amount, shares, fee, outcome, pnl, timestamp, market_session
        )
        
        # Check for duplicates if enabled
        if check_duplicates:
            if self.is_duplicate_trade(market_id, side, timestamp):
                raise ValueError(
                    f"Duplicate trade detected: market_id={market_id}, "
                    f"side={side}, timestamp={timestamp.isoformat()}"
                )
        
        conn = self._get_connection()
        cursor = conn.cursor()
        
        timestamp_str = timestamp.isoformat()
        
        cursor.execute("""
            INSERT INTO trades (
                market_slug, market_id, side, entry_price, exit_price,
                amount, shares, fee, outcome, pnl, timestamp, market_session
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """, (
            market_slug, market_id, side, entry_price, exit_price,
            amount, shares, fee, outcome, pnl, timestamp_str, market_session
        ))
        
        conn.commit()
        trade_id = cursor.lastrowid
        
        # Invalidate cache on write
        self._invalidate_cache()
        
        # Trigger trade_saved hooks if streaming is enabled
        if self._streaming_enabled:
            trade_record = self._row_to_trade_record(cursor.execute(
                "SELECT * FROM trades WHERE id = ?", (trade_id,)
            ).fetchone())
            self._trigger_trade_saved_hooks(trade_record)
        
        log.debug("Trade saved: ID=%d, market=%s, side=%s, pnl=%.2f",
                  trade_id, market_slug, side, pnl)
        return trade_id
    
    def save_trades_bulk(
        self,
        trades: List[Dict[str, Any]],
        check_duplicates: bool = True,
    ) -> List[int]:
        """
        Save multiple trades in a single transaction for better performance.
        
        Parameters
        ----------
        trades : list of dict
            List of trade dictionaries with keys: market_slug, market_id, side,
            entry_price, exit_price, amount, shares, fee, outcome, pnl, timestamp, market_session.
        check_duplicates : bool, optional
            Whether to check for duplicate trades (default: True).
        
        Returns
        -------
        list of int
            List of inserted trade IDs.
        
        Raises
        ------
        ValueError
            If validation fails or duplicate detected.
        """
        if not trades:
            return []
        
        conn = self._get_connection()
        cursor = conn.cursor()
        
        # Validate all trades first
        for trade in trades:
            self._validate_trade_data(
                market_slug=trade["market_slug"],
                market_id=trade["market_id"],
                side=trade["side"],
                entry_price=trade["entry_price"],
                exit_price=trade.get("exit_price"),
                amount=trade["amount"],
                shares=trade["shares"],
                fee=trade["fee"],
                outcome=trade.get("outcome"),
                pnl=trade["pnl"],
                timestamp=trade["timestamp"],
                market_session=trade.get("market_session"),
            )
        
        # Check for duplicates if enabled
        if check_duplicates:
            for trade in trades:
                if self.is_duplicate_trade(
                    trade["market_id"],
                    trade["side"],
                    trade["timestamp"]
                ):
                    raise ValueError(
                        f"Duplicate trade detected: market_id={trade['market_id']}, "
                        f"side={trade['side']}, timestamp={trade['timestamp'].isoformat()}"
                    )
        
        # Prepare data for bulk insert
        trade_data = []
        for trade in trades:
            trade_data.append((
                trade["market_slug"],
                trade["market_id"],
                trade["side"],
                trade["entry_price"],
                trade.get("exit_price"),
                trade["amount"],
                trade["shares"],
                trade["fee"],
                trade.get("outcome"),
                trade["pnl"],
                trade["timestamp"].isoformat(),
                trade.get("market_session"),
            ))
        
        # Begin transaction
        cursor.execute("BEGIN TRANSACTION")
        
        try:
            # Bulk insert
            cursor.executemany("""
                INSERT INTO trades (
                    market_slug, market_id, side, entry_price, exit_price,
                    amount, shares, fee, outcome, pnl, timestamp, market_session
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """, trade_data)
            
            conn.commit()
            
            # Get the inserted IDs by querying the last inserted rows
            # Get the last row ID
            last_id = cursor.lastrowid
            first_id = last_id - len(trades) + 1
            
            # Generate the list of IDs
            trade_ids = list(range(first_id, last_id + 1))
            
            # Invalidate cache on write
            self._invalidate_cache()
            
            log.info("Bulk saved %d trades", len(trades))
            return trade_ids
            
        except Exception as e:
            conn.rollback()
            log.error("Bulk insert failed: %s", e)
            raise
    
    def is_duplicate_trade(
        self,
        market_id: str,
        side: str,
        timestamp: datetime,
        tolerance_seconds: int = 1,
    ) -> bool:
        """
        Check if a trade already exists in the database.
        
        A trade is considered a duplicate if it has the same market_id, side,
        and timestamp (within a tolerance window).
        
        Parameters
        ----------
        market_id : str
            Market ID to check.
        side : str
            Side to check ("UP" or "DOWN").
        timestamp : datetime
            Timestamp to check.
        tolerance_seconds : int, optional
            Time tolerance in seconds for timestamp matching (default: 1).
        
        Returns
        -------
        bool
            True if a duplicate exists, False otherwise.
        """
        conn = self._get_connection()
        cursor = conn.cursor()
        
        timestamp_str = timestamp.isoformat()
        
        # Check for exact match first
        cursor.execute("""
            SELECT COUNT(*) FROM trades
            WHERE market_id = ? AND side = ? AND timestamp = ?
        """, (market_id, side.upper(), timestamp_str))
        
        count = cursor.fetchone()[0]
        if count > 0:
            return True
        
        # If no exact match, check within tolerance window
        # This handles cases where timestamps might differ slightly
        cursor.execute("""
            SELECT COUNT(*) FROM trades
            WHERE market_id = ? AND side = ?
        """, (market_id, side.upper()))
        
        rows = cursor.fetchall()
        for row in rows:
            # Parse stored timestamps and check tolerance
            cursor.execute("""
                SELECT timestamp FROM trades
                WHERE market_id = ? AND side = ?
            """, (market_id, side.upper()))
            
            for ts_row in cursor.fetchall():
                stored_ts = datetime.fromisoformat(ts_row[0])
                if stored_ts.tzinfo is None:
                    stored_ts = stored_ts.replace(tzinfo=timezone.utc)
                
                time_diff = abs((timestamp - stored_ts).total_seconds())
                if time_diff <= tolerance_seconds:
                    return True
        
        return False
    
    def get_schema_version(self) -> int:
        """
        Get the current schema version.
        
        Returns
        -------
        int
            The current schema version.
        """
        conn = self._get_connection()
        cursor = conn.cursor()
        
        cursor.execute("SELECT MAX(version) FROM schema_version")
        result = cursor.fetchone()
        return result[0] if result[0] is not None else 0
    
    def _apply_migration(self, version: int, migration_sql: str) -> None:
        """
        Apply a migration to the database.
        
        Parameters
        ----------
        version : int
            The migration version number.
        migration_sql : str
            SQL statements to execute for the migration.
        """
        conn = self._get_connection()
        cursor = conn.cursor()
        
        current_version = self.get_schema_version()
        
        if current_version >= version:
            log.debug("Migration %d already applied (current version: %d)", version, current_version)
            return
        
        log.info("Applying migration %d", version)
        
        try:
            # Execute migration SQL
            cursor.executescript(migration_sql)
            
            # Update schema version
            cursor.execute(
                "INSERT INTO schema_version (version) VALUES (?)",
                (version,)
            )
            
            conn.commit()
            log.info("Migration %d applied successfully", version)
        except Exception as e:
            conn.rollback()
            log.error("Migration %d failed: %s", version, e)
            raise
    
    def run_migrations(self) -> None:
        """
        Run all pending migrations.
        
        This method checks the current schema version and applies any
        pending migrations in order.
        """
        current_version = self.get_schema_version()
        log.info("Current schema version: %d", current_version)
        
        # Define migrations
        migrations = {
            # Future migrations can be added here
            # Example:
            # 2: """
            # ALTER TABLE trades ADD COLUMN notes TEXT;
            # """,
        }
        
        # Apply migrations in order
        for version, migration_sql in sorted(migrations.items()):
            if version > current_version:
                self._apply_migration(version, migration_sql)
    
    def _generate_cache_key(
        self,
        filters: Optional[Dict[str, Any]] = None,
        sort_by: str = "timestamp",
        sort_order: str = "desc",
        limit: Optional[int] = None,
        offset: int = 0,
    ) -> str:
        """Generate a cache key for query parameters."""
        key_data = {
            "filters": filters,
            "sort_by": sort_by,
            "sort_order": sort_order,
            "limit": limit,
            "offset": offset,
        }
        key_str = json.dumps(key_data, sort_keys=True)
        return hashlib.md5(key_str.encode()).hexdigest()
    
    def _invalidate_cache(self) -> None:
        """Invalidate the query cache."""
        self._query_cache.clear()
        log.debug("Query cache invalidated")
    
    def enable_cache(self) -> None:
        """Enable query result caching."""
        self._cache_enabled = True
        log.debug("Query cache enabled")
    
    def disable_cache(self) -> None:
        """Disable query result caching and clear existing cache."""
        self._cache_enabled = False
        self._invalidate_cache()
        log.debug("Query cache disabled")
    
    def clear_cache(self) -> None:
        """Clear the query cache."""
        self._invalidate_cache()
    
    def analyze_indexes(self) -> None:
        """
        Analyze database indexes to optimize query planning.
        
        This runs SQLite's ANALYZE command to update statistics
        that help the query planner choose optimal execution plans.
        """
        conn = self._get_connection()
        cursor = conn.cursor()
        
        cursor.execute("ANALYZE")
        conn.commit()
        
        log.info("Database indexes analyzed")
    
    def optimize_database(self) -> None:
        """
        Optimize the database for better performance.
        
        This runs SQLite's OPTIMIZE command which can:
        - Rebuild the database file
        - Update statistics
        - Defragment the database
        """
        conn = self._get_connection()
        cursor = conn.cursor()
        
        cursor.execute("PRAGMA optimize")
        conn.commit()
        
        log.info("Database optimized")
    
    def get_index_info(self) -> Dict[str, Dict[str, Any]]:
        """
        Get information about database indexes.
        
        Returns
        -------
        dict
            Dictionary with index names as keys and index details as values.
        """
        conn = self._get_connection()
        cursor = conn.cursor()
        
        cursor.execute("""
            SELECT name, tbl_name, sql 
            FROM sqlite_master 
            WHERE type='index' AND name NOT LIKE 'sqlite_%'
        """)
        
        indexes = {}
        for row in cursor.fetchall():
            indexes[row["name"]] = {
                "table": row["tbl_name"],
                "sql": row["sql"],
            }
        
        return indexes
    
    def rebuild_index(self, index_name: str) -> None:
        """
        Rebuild a specific index to optimize performance.
        
        Parameters
        ----------
        index_name : str
            Name of the index to rebuild.
        
        Raises
        ------
        ValueError
            If the index doesn't exist.
        """
        conn = self._get_connection()
        cursor = conn.cursor()
        
        # Check if index exists
        cursor.execute("""
            SELECT name FROM sqlite_master 
            WHERE type='index' AND name=?
        """, (index_name,))
        
        if not cursor.fetchone():
            raise ValueError(f"Index '{index_name}' does not exist")
        
        # Rebuild by dropping and recreating
        cursor.execute(f"DROP INDEX IF EXISTS {index_name}")
        
        # Recreate based on the index type
        if index_name == "idx_market_slug":
            cursor.execute("CREATE INDEX idx_market_slug ON trades(market_slug)")
        elif index_name == "idx_market_id":
            cursor.execute("CREATE INDEX idx_market_id ON trades(market_id)")
        elif index_name == "idx_side":
            cursor.execute("CREATE INDEX idx_side ON trades(side)")
        elif index_name == "idx_outcome":
            cursor.execute("CREATE INDEX idx_outcome ON trades(outcome)")
        elif index_name == "idx_timestamp":
            cursor.execute("CREATE INDEX idx_timestamp ON trades(timestamp)")
        elif index_name == "idx_duplicate_check":
            cursor.execute("CREATE INDEX idx_duplicate_check ON trades(market_id, side, timestamp)")
        
        conn.commit()
        log.info("Index '%s' rebuilt", index_name)
    
    def load_all_trades(self) -> List[TradeRecord]:
        """
        Load all trades from the database.
        
        Returns
        -------
        List[TradeRecord]
            All trades in the database.
        """
        conn = self._get_connection()
        cursor = conn.cursor()
        
        cursor.execute("""
            SELECT id, market_slug, market_id, side, entry_price, exit_price,
                   amount, shares, fee, outcome, pnl, timestamp, market_session
            FROM trades
            ORDER BY timestamp DESC
        """)
        
        trades = []
        for row in cursor.fetchall():
            trades.append(self._row_to_trade_record(row))
        
        log.debug("Loaded %d trades from database", len(trades))
        return trades
    
    def load_trades_by_market(self, market_slug: str) -> List[TradeRecord]:
        """
        Load trades for a specific market slug.
        
        Parameters
        ----------
        market_slug : str
            Market slug to filter by.
        
        Returns
        -------
        List[TradeRecord]
            Trades for the specified market.
        """
        conn = self._get_connection()
        cursor = conn.cursor()
        
        cursor.execute("""
            SELECT id, market_slug, market_id, side, entry_price, exit_price,
                   amount, shares, fee, outcome, pnl, timestamp, market_session
            FROM trades
            WHERE market_slug = ?
            ORDER BY timestamp DESC
        """, (market_slug,))
        
        trades = []
        for row in cursor.fetchall():
            trades.append(self._row_to_trade_record(row))
        
        return trades
    
    def load_trades_by_asset(self, asset: str) -> List[TradeRecord]:
        """
        Load trades for a specific asset (e.g., "BTC", "ETH").
        
        Parameters
        ----------
        asset : str
            Asset symbol to filter by (case-insensitive).
        
        Returns
        -------
        List[TradeRecord]
            Trades for the specified asset.
        """
        conn = self._get_connection()
        cursor = conn.cursor()
        
        # Match market_slug starting with asset (case-insensitive)
        pattern = f"{asset.lower()}%"
        cursor.execute("""
            SELECT id, market_slug, market_id, side, entry_price, exit_price,
                   amount, shares, fee, outcome, pnl, timestamp, market_session
            FROM trades
            WHERE LOWER(market_slug) LIKE ?
            ORDER BY timestamp DESC
        """, (pattern,))
        
        trades = []
        for row in cursor.fetchall():
            trades.append(self._row_to_trade_record(row))
        
        return trades
    
    def load_trades_by_side(self, side: str) -> List[TradeRecord]:
        """
        Load trades for a specific side.
        
        Parameters
        ----------
        side : str
            "UP" or "DOWN".
        
        Returns
        -------
        List[TradeRecord]
            Trades for the specified side.
        """
        conn = self._get_connection()
        cursor = conn.cursor()
        
        cursor.execute("""
            SELECT id, market_slug, market_id, side, entry_price, exit_price,
                   amount, shares, fee, outcome, pnl, timestamp, market_session
            FROM trades
            WHERE side = ?
            ORDER BY timestamp DESC
        """, (side.upper(),))
        
        trades = []
        for row in cursor.fetchall():
            trades.append(self._row_to_trade_record(row))
        
        return trades
    
    def load_trades_by_outcome(self, outcome: str) -> List[TradeRecord]:
        """
        Load trades with a specific outcome.
        
        Parameters
        ----------
        outcome : str
            "WON", "LOST", or "CLOSED".
        
        Returns
        -------
        List[TradeRecord]
            Trades with the specified outcome.
        """
        conn = self._get_connection()
        cursor = conn.cursor()
        
        cursor.execute("""
            SELECT id, market_slug, market_id, side, entry_price, exit_price,
                   amount, shares, fee, outcome, pnl, timestamp, market_session
            FROM trades
            WHERE outcome = ?
            ORDER BY timestamp DESC
        """, (outcome.upper(),))
        
        trades = []
        for row in cursor.fetchall():
            trades.append(self._row_to_trade_record(row))
        
        return trades
    
    def load_trades_by_market_session(self, market_session: str) -> List[TradeRecord]:
        """
        Load trades for a specific market session.
        
        Parameters
        ----------
        market_session : str
            Market session name ("london", "new_york", "asia", "sydney").
        
        Returns
        -------
        List[TradeRecord]
            Trades for the specified market session.
        """
        conn = self._get_connection()
        cursor = conn.cursor()
        
        cursor.execute("""
            SELECT id, market_slug, market_id, side, entry_price, exit_price,
                   amount, shares, fee, outcome, pnl, timestamp, market_session
            FROM trades
            WHERE market_session = ?
            ORDER BY timestamp DESC
        """, (market_session,))
        
        trades = []
        for row in cursor.fetchall():
            trades.append(self._row_to_trade_record(row))
        
        return trades
    
    def load_trades_by_date_range(
        self,
        start_date: datetime,
        end_date: datetime
    ) -> List[TradeRecord]:
        """
        Load trades within a date range.
        
        Parameters
        ----------
        start_date : datetime
            Start of date range (inclusive).
        end_date : datetime
            End of date range (inclusive).
        
        Returns
        -------
        List[TradeRecord]
            Trades within the specified date range.
        """
        conn = self._get_connection()
        cursor = conn.cursor()
        
        cursor.execute("""
            SELECT id, market_slug, market_id, side, entry_price, exit_price,
                   amount, shares, fee, outcome, pnl, timestamp, market_session
            FROM trades
            WHERE timestamp >= ? AND timestamp <= ?
            ORDER BY timestamp DESC
        """, (start_date.isoformat(), end_date.isoformat()))
        
        trades = []
        for row in cursor.fetchall():
            trades.append(self._row_to_trade_record(row))
        
        return trades
    
    def load_trades(
        self,
        filters: Optional[Dict[str, Any]] = None,
        sort_by: str = "timestamp",
        sort_order: str = "desc",
        limit: Optional[int] = None,
        offset: int = 0,
    ) -> List[TradeRecord]:
        """
        Load trades with advanced filtering, sorting, and pagination.
        
        Parameters
        ----------
        filters : dict, optional
            Dictionary of filter criteria. Supported keys:
            - asset: str (e.g., "BTC")
            - side: str ("UP" or "DOWN")
            - outcome: str ("WON", "LOST", "CLOSED")
            - min_pnl: float (minimum P&L)
            - max_pnl: float (maximum P&L)
            - min_amount: float (minimum amount)
            - max_amount: float (maximum amount)
            - market_slug: str (exact match)
            - market_id: str (exact match)
        sort_by : str, optional
            Field to sort by (default: "timestamp").
            Options: "timestamp", "pnl", "amount", "entry_price", "shares", "fee"
        sort_order : str, optional
            Sort order: "asc" or "desc" (default: "desc").
        limit : int, optional
            Maximum number of trades to return (default: None = no limit).
        offset : int, optional
            Number of trades to skip (default: 0).
        
        Returns
        -------
        List[TradeRecord]
            Filtered and sorted trades.
        
        Example
        -------
        >>> trades = db.load_trades(
        ...     filters={"asset": "BTC", "side": "UP", "outcome": "WON"},
        ...     sort_by="pnl",
        ...     sort_order="desc",
        ...     limit=10
        ... )
        """
        # Check cache if enabled
        if self._cache_enabled:
            cache_key = self._generate_cache_key(filters, sort_by, sort_order, limit, offset)
            if cache_key in self._query_cache:
                log.debug("Cache hit for key: %s", cache_key)
                return self._query_cache[cache_key]
        
        conn = self._get_connection()
        cursor = conn.cursor()
        
        # Build query with filters
        query = """
            SELECT id, market_slug, market_id, side, entry_price, exit_price,
                   amount, shares, fee, outcome, pnl, timestamp, market_session
            FROM trades
        """
        
        params = []
        where_clauses = []
        
        if filters:
            # Asset filter (pattern match on market_slug)
            if "asset" in filters:
                pattern = f"{filters['asset'].lower()}%"
                where_clauses.append("LOWER(market_slug) LIKE ?")
                params.append(pattern)
            
            # Side filter
            if "side" in filters:
                where_clauses.append("side = ?")
                params.append(filters["side"].upper())
            
            # Outcome filter
            if "outcome" in filters:
                where_clauses.append("outcome = ?")
                params.append(filters["outcome"].upper())
            
            # P&L range filters
            if "min_pnl" in filters:
                where_clauses.append("pnl >= ?")
                params.append(float(filters["min_pnl"]))
            
            if "max_pnl" in filters:
                where_clauses.append("pnl <= ?")
                params.append(float(filters["max_pnl"]))
            
            # Amount range filters
            if "min_amount" in filters:
                where_clauses.append("amount >= ?")
                params.append(float(filters["min_amount"]))
            
            if "max_amount" in filters:
                where_clauses.append("amount <= ?")
                params.append(float(filters["max_amount"]))
            
            # Exact market_slug filter
            if "market_slug" in filters:
                where_clauses.append("market_slug = ?")
                params.append(filters["market_slug"])
            
            # Exact market_id filter
            if "market_id" in filters:
                where_clauses.append("market_id = ?")
                params.append(filters["market_id"])
        
        # Add WHERE clause if filters exist
        if where_clauses:
            query += " WHERE " + " AND ".join(where_clauses)
        
        # Validate sort_by field
        valid_sort_fields = {
            "timestamp", "pnl", "amount", "entry_price", "shares", "fee",
            "market_slug", "side", "outcome"
        }
        if sort_by not in valid_sort_fields:
            raise ValueError(
                f"Invalid sort_by field '{sort_by}'. "
                f"Valid options: {sorted(valid_sort_fields)}"
            )
        
        # Validate sort_order
        sort_order = sort_order.lower()
        if sort_order not in ("asc", "desc"):
            raise ValueError(f"sort_order must be 'asc' or 'desc', got '{sort_order}'")
        
        # Add ORDER BY clause
        query += f" ORDER BY {sort_by} {sort_order.upper()}"
        
        # Add LIMIT and OFFSET for pagination
        if limit is not None:
            if limit <= 0:
                raise ValueError(f"limit must be positive, got {limit}")
            query += " LIMIT ?"
            params.append(int(limit))
        
        if offset > 0:
            query += " OFFSET ?"
            params.append(int(offset))
        
        # Execute query
        cursor.execute(query, params)
        
        # Convert rows to TradeRecord objects
        trades = []
        for row in cursor.fetchall():
            trades.append(self._row_to_trade_record(row))
        
        log.debug(
            "Loaded %d trades with filters=%s, sort_by=%s, limit=%s, offset=%d",
            len(trades), filters, sort_by, limit, offset
        )
        
        # Store in cache if enabled
        if self._cache_enabled:
            cache_key = self._generate_cache_key(filters, sort_by, sort_order, limit, offset)
            # Implement LRU eviction if cache is full
            if len(self._query_cache) >= self._cache_max_size:
                # Remove oldest entry (first in dict)
                self._query_cache.pop(next(iter(self._query_cache)))
            self._query_cache[cache_key] = trades
            log.debug("Cached %d trades with key: %s", len(trades), cache_key)
        
        return trades
    
    def aggregate_trades(
        self,
        group_by: str = "asset",
        filters: Optional[Dict[str, Any]] = None,
    ) -> Dict[str, Dict[str, Any]]:
        """
        Aggregate trades by a specified field.
        
        Parameters
        ----------
        group_by : str
            Field to group by. Options: "asset", "side", "outcome", "market_slug".
        filters : dict, optional
            Same filter criteria as load_trades().
        
        Returns
        -------
        dict
            Dictionary with group keys as keys and statistics as values.
            Each value contains: count, total_pnl, avg_pnl, wins, losses, win_rate.
        
        Example
        -------
        >>> by_asset = db.aggregate_trades(group_by="asset")
        >>> print(by_asset["BTC"])
        >>> {'count': 10, 'total_pnl': 50.0, 'avg_pnl': 5.0, 'wins': 6, 'losses': 4, 'win_rate': 60.0}
        """
        # Validate group_by field
        valid_group_fields = {"asset", "side", "outcome", "market_slug"}
        if group_by not in valid_group_fields:
            raise ValueError(
                f"Invalid group_by field '{group_by}'. "
                f"Valid options: {sorted(valid_group_fields)}"
            )
        
        # Load trades with filters
        trades = self.load_trades(filters=filters)
        
        # Group trades
        groups: Dict[str, List[TradeRecord]] = {}
        
        for trade in trades:
            if group_by == "asset":
                # Extract asset from market_slug (first part before dash)
                key = trade.market_slug.split("-")[0].upper()
            elif group_by == "side":
                key = trade.side
            elif group_by == "outcome":
                key = trade.outcome or "PENDING"
            elif group_by == "market_slug":
                key = trade.market_slug
            else:
                key = str(getattr(trade, group_by, "unknown"))
            
            if key not in groups:
                groups[key] = []
            groups[key].append(trade)
        
        # Calculate statistics for each group
        results = {}
        for key, group_trades in groups.items():
            count = len(group_trades)
            total_pnl = sum(t.pnl for t in group_trades)
            avg_pnl = total_pnl / count if count > 0 else 0.0
            wins = sum(1 for t in group_trades if t.outcome == "WON")
            losses = sum(1 for t in group_trades if t.outcome == "LOST")
            win_rate = (wins / count * 100) if count > 0 else 0.0
            
            results[key] = {
                "count": count,
                "total_pnl": total_pnl,
                "avg_pnl": avg_pnl,
                "wins": wins,
                "losses": losses,
                "win_rate": win_rate,
            }
        
        log.debug("Aggregated %d trades by %s into %d groups", len(trades), group_by, len(results))
        return results
    
    def get_statistics(self) -> TradeStatistics:
        """
        Calculate statistics for all trades in the database.
        
        Returns
        -------
        TradeStatistics
            Summary statistics.
        """
        trades = self.load_all_trades()
        
        total_trades = len(trades)
        wins = sum(1 for t in trades if t.outcome == "WON")
        losses = sum(1 for t in trades if t.outcome == "LOST")
        win_rate = (wins / total_trades * 100) if total_trades > 0 else 0.0
        total_pnl = sum(t.pnl for t in trades)
        total_fees = sum(t.fee for t in trades)
        avg_entry_price = (sum(t.entry_price for t in trades) / total_trades) if total_trades > 0 else 0.0
        avg_pnl_per_trade = (total_pnl / total_trades) if total_trades > 0 else 0.0
        
        return TradeStatistics(
            total_trades=total_trades,
            wins=wins,
            losses=losses,
            win_rate=win_rate,
            total_pnl=total_pnl,
            total_fees=total_fees,
            avg_entry_price=avg_entry_price,
            avg_pnl_per_trade=avg_pnl_per_trade,
        )
    
    def export_csv(self, filepath: str | Path, filters: Optional[Dict[str, Any]] = None) -> None:
        """
        Export trades to CSV format.
        
        Parameters
        ----------
        filepath : str or Path
            Path to the output CSV file.
        filters : dict, optional
            Filter criteria to apply before export (same as load_trades()).
        
        Example
        -------
        >>> db.export_csv("trades.csv")
        >>> db.export_csv("btc_trades.csv", filters={"asset": "BTC"})
        """
        filepath = Path(filepath)
        trades = self.load_trades(filters=filters)
        
        if not trades:
            log.warning("No trades to export to CSV")
            return
        
        # Define CSV columns
        fieldnames = [
            "id", "market_slug", "market_id", "side", "entry_price",
            "exit_price", "amount", "shares", "fee", "outcome", "pnl", "timestamp"
        ]
        
        with filepath.open("w", newline="", encoding="utf-8") as f:
            writer = csv.DictWriter(f, fieldnames=fieldnames)
            writer.writeheader()
            
            for trade in trades:
                row = {
                    "id": trade.id,
                    "market_slug": trade.market_slug,
                    "market_id": trade.market_id,
                    "side": trade.side,
                    "entry_price": trade.entry_price,
                    "exit_price": trade.exit_price,
                    "amount": trade.amount,
                    "shares": trade.shares,
                    "fee": trade.fee,
                    "outcome": trade.outcome,
                    "pnl": trade.pnl,
                    "timestamp": trade.timestamp.isoformat(),
                }
                writer.writerow(row)
        
        log.info("Exported %d trades to CSV: %s", len(trades), filepath)
    
    def export_json(self, filepath: str | Path, filters: Optional[Dict[str, Any]] = None) -> None:
        """
        Export trades to JSON format with metadata.
        
        Parameters
        ----------
        filepath : str or Path
            Path to the output JSON file.
        filters : dict, optional
            Filter criteria to apply before export (same as load_trades()).
        
        Example
        -------
        >>> db.export_json("trades.json")
        >>> db.export_json("won_trades.json", filters={"outcome": "WON"})
        """
        filepath = Path(filepath)
        trades = self.load_trades(filters=filters)
        
        if not trades:
            log.warning("No trades to export to JSON")
            return
        
        # Create export with metadata
        export_data = {
            "metadata": {
                "export_timestamp": datetime.now(timezone.utc).isoformat(),
                "total_trades": len(trades),
                "database_path": str(self.db_path),
            },
            "trades": [trade.to_dict() for trade in trades]
        }
        
        with filepath.open("w", encoding="utf-8") as f:
            json.dump(export_data, f, indent=2, ensure_ascii=False)
        
        log.info("Exported %d trades to JSON: %s", len(trades), filepath)
    
    def export_parquet(self, filepath: str | Path, filters: Optional[Dict[str, Any]] = None) -> None:
        """
        Export trades to Parquet format for data science workflows.
        
        This method requires the 'pyarrow' library to be installed.
        
        Parameters
        ----------
        filepath : str or Path
            Path to the output Parquet file.
        filters : dict, optional
            Filter criteria to apply before export (same as load_trades()).
        
        Raises
        ------
        ImportError
            If pyarrow is not installed.
        
        Example
        -------
        >>> db.export_parquet("trades.parquet")
        >>> db.export_parquet("btc_trades.parquet", filters={"asset": "BTC"})
        """
        try:
            import pyarrow as pa
            import pyarrow.parquet as pq
        except ImportError as e:
            raise ImportError(
                "pyarrow is required for Parquet export. "
                "Install it with: pip install pyarrow"
            ) from e
        
        filepath = Path(filepath)
        trades = self.load_trades(filters=filters)
        
        if not trades:
            log.warning("No trades to export to Parquet")
            return
        
        # Convert trades to list of dictionaries
        data = [trade.to_dict() for trade in trades]
        
        # Create PyArrow table
        table = pa.Table.from_pylist(data)
        
        # Write to Parquet
        pq.write_table(table, filepath)
        
        log.info("Exported %d trades to Parquet: %s", len(trades), filepath)
    
    def export_excel(self, filepath: str | Path, filters: Optional[Dict[str, Any]] = None) -> None:
        """
        Export trades to Excel format for business users.
        
        This method requires the 'openpyxl' library to be installed.
        
        Parameters
        ----------
        filepath : str or Path
            Path to the output Excel file (.xlsx).
        filters : dict, optional
            Filter criteria to apply before export (same as load_trades()).
        
        Raises
        ------
        ImportError
            If openpyxl is not installed.
        
        Example
        -------
        >>> db.export_excel("trades.xlsx")
        >>> db.export_excel("btc_trades.xlsx", filters={"asset": "BTC"})
        """
        try:
            from openpyxl import Workbook
        except ImportError as e:
            raise ImportError(
                "openpyxl is required for Excel export. "
                "Install it with: pip install openpyxl"
            ) from e
        
        filepath = Path(filepath)
        trades = self.load_trades(filters=filters)
        
        if not trades:
            log.warning("No trades to export to Excel")
            return
        
        # Create workbook
        wb = Workbook()
        ws = wb.active
        ws.title = "Trades"
        
        # Define headers
        headers = [
            "ID", "Market Slug", "Market ID", "Side", "Entry Price",
            "Exit Price", "Amount", "Shares", "Fee", "Outcome", "P&L", "Timestamp"
        ]
        
        # Write headers
        for col_num, header in enumerate(headers, 1):
            ws.cell(row=1, column=col_num, value=header)
        
        # Write trade data
        for row_num, trade in enumerate(trades, 2):
            ws.cell(row=row_num, column=1, value=trade.id)
            ws.cell(row=row_num, column=2, value=trade.market_slug)
            ws.cell(row=row_num, column=3, value=trade.market_id)
            ws.cell(row=row_num, column=4, value=trade.side)
            ws.cell(row=row_num, column=5, value=trade.entry_price)
            ws.cell(row=row_num, column=6, value=trade.exit_price)
            ws.cell(row=row_num, column=7, value=trade.amount)
            ws.cell(row=row_num, column=8, value=trade.shares)
            ws.cell(row=row_num, column=9, value=trade.fee)
            ws.cell(row=row_num, column=10, value=trade.outcome)
            ws.cell(row=row_num, column=11, value=trade.pnl)
            ws.cell(row=row_num, column=12, value=trade.timestamp.isoformat())
        
        # Save workbook
        wb.save(filepath)
        
        log.info("Exported %d trades to Excel: %s", len(trades), filepath)
    
    def delete_trade(self, trade_id: int) -> bool:
        """
        Delete a trade by ID.
        
        Parameters
        ----------
        trade_id : int
            ID of the trade to delete.
        
        Returns
        -------
        bool
            True if trade was deleted, False if not found.
        """
        conn = self._get_connection()
        cursor = conn.cursor()
        
        cursor.execute("DELETE FROM trades WHERE id = ?", (trade_id,))
        conn.commit()
        
        deleted = cursor.rowcount > 0
        if deleted:
            # Invalidate cache on write
            self._invalidate_cache()
            
            # Trigger trade_deleted hooks if streaming is enabled
            if self._streaming_enabled:
                self._trigger_trade_deleted_hooks(trade_id)
            
            log.debug("Trade deleted: ID=%d", trade_id)
        return deleted
    
    def clear_all_trades(self) -> None:
        """Delete all trades from the database."""
        conn = self._get_connection()
        cursor = conn.cursor()
        
        cursor.execute("DELETE FROM trades")
        conn.commit()
        
        # Invalidate cache on write
        self._invalidate_cache()
        
        log.info("All trades cleared from database")
    
    # Event Hooks for Real-time Synchronization
    
    def on_trade_saved(self, callback: Callable[[TradeRecord], None]) -> Callable[[TradeRecord], None]:
        """
        Register a callback to be called when a trade is saved.
        
        Parameters
        ----------
        callback : Callable[[TradeRecord], None]
            Function that takes a TradeRecord as argument.
        
        Returns
        -------
        Callable[[TradeRecord], None]
            The same callback function (allows decorator usage).
        
        Example
        -------
        >>> @db.on_trade_saved
        >>> def handle_trade_saved(trade: TradeRecord):
        ...     print(f"Trade saved: {trade.market_slug}")
        """
        with self._hooks_lock:
            self._trade_saved_hooks.append(callback)
        log.debug("Registered trade_saved callback: %s", callback.__name__)
        return callback
    
    def on_trade_updated(self, callback: Callable[[int, Dict[str, Any]], None]) -> Callable[[int, Dict[str, Any]], None]:
        """
        Register a callback to be called when a trade is updated.
        
        Parameters
        ----------
        callback : Callable[[int, Dict[str, Any]], None]
            Function that takes trade_id and changes dict as arguments.
        
        Returns
        -------
        Callable[[int, Dict[str, Any]], None]
            The same callback function (allows decorator usage).
        
        Example
        -------
        >>> @db.on_trade_updated
        >>> def handle_trade_updated(trade_id: int, changes: Dict[str, Any]):
        ...     print(f"Trade {trade_id} updated: {changes}")
        """
        with self._hooks_lock:
            self._trade_updated_hooks.append(callback)
        log.debug("Registered trade_updated callback: %s", callback.__name__)
        return callback
    
    def on_trade_deleted(self, callback: Callable[[int], None]) -> Callable[[int], None]:
        """
        Register a callback to be called when a trade is deleted.
        
        Parameters
        ----------
        callback : Callable[[int], None]
            Function that takes trade_id as argument.
        
        Returns
        -------
        Callable[[int], None]
            The same callback function (allows decorator usage).
        
        Example
        -------
        >>> @db.on_trade_deleted
        >>> def handle_trade_deleted(trade_id: int):
        ...     print(f"Trade {trade_id} deleted")
        """
        with self._hooks_lock:
            self._trade_deleted_hooks.append(callback)
        log.debug("Registered trade_deleted callback: %s", callback.__name__)
        return callback
    
    def remove_trade_saved_hook(self, callback: Callable[[TradeRecord], None]) -> None:
        """
        Remove a registered trade_saved callback.
        
        Parameters
        ----------
        callback : Callable[[TradeRecord], None]
            The callback function to remove.
        """
        with self._hooks_lock:
            if callback in self._trade_saved_hooks:
                self._trade_saved_hooks.remove(callback)
                log.debug("Removed trade_saved callback: %s", callback.__name__)
    
    def remove_trade_updated_hook(self, callback: Callable[[int, Dict[str, Any]], None]) -> None:
        """
        Remove a registered trade_updated callback.
        
        Parameters
        ----------
        callback : Callable[[int, Dict[str, Any]], None]
            The callback function to remove.
        """
        with self._hooks_lock:
            if callback in self._trade_updated_hooks:
                self._trade_updated_hooks.remove(callback)
                log.debug("Removed trade_updated callback: %s", callback.__name__)
    
    def remove_trade_deleted_hook(self, callback: Callable[[int], None]) -> None:
        """
        Remove a registered trade_deleted callback.
        
        Parameters
        ----------
        callback : Callable[[int], None]
            The callback function to remove.
        """
        with self._hooks_lock:
            if callback in self._trade_deleted_hooks:
                self._trade_deleted_hooks.remove(callback)
                log.debug("Removed trade_deleted callback: %s", callback.__name__)
    
    def _trigger_trade_saved_hooks(self, trade: TradeRecord) -> None:
        """
        Trigger all registered trade_saved callbacks.
        
        Parameters
        ----------
        trade : TradeRecord
            The trade that was saved.
        """
        with self._hooks_lock:
            for callback in self._trade_saved_hooks:
                try:
                    callback(trade)
                except Exception as e:
                    log.error("Error in trade_saved callback %s: %s", callback.__name__, e)
    
    def _trigger_trade_updated_hooks(self, trade_id: int, changes: Dict[str, Any]) -> None:
        """
        Trigger all registered trade_updated callbacks.
        
        Parameters
        ----------
        trade_id : int
            The ID of the trade that was updated.
        changes : Dict[str, Any]
            Dictionary of changed fields.
        """
        with self._hooks_lock:
            for callback in self._trade_updated_hooks:
                try:
                    callback(trade_id, changes)
                except Exception as e:
                    log.error("Error in trade_updated callback %s: %s", callback.__name__, e)
    
    def _trigger_trade_deleted_hooks(self, trade_id: int) -> None:
        """
        Trigger all registered trade_deleted callbacks.
        
        Parameters
        ----------
        trade_id : int
            The ID of the trade that was deleted.
        """
        with self._hooks_lock:
            for callback in self._trade_deleted_hooks:
                try:
                    callback(trade_id)
                except Exception as e:
                    log.error("Error in trade_deleted callback %s: %s", callback.__name__, e)
    
    # Streaming Control
    
    def enable_streaming(self) -> None:
        """
        Enable real-time streaming of database events.
        
        When enabled, registered event hooks will be triggered
        on trade save, update, and delete operations.
        """
        self._streaming_enabled = True
        log.info("Real-time streaming enabled")
    
    def disable_streaming(self) -> None:
        """
        Disable real-time streaming of database events.
        
        When disabled, event hooks will not be triggered.
        """
        self._streaming_enabled = False
        log.info("Real-time streaming disabled")
    
    def is_streaming_enabled(self) -> bool:
        """
        Check if streaming is currently enabled.
        
        Returns
        -------
        bool
            True if streaming is enabled, False otherwise.
        """
        return self._streaming_enabled
    
    # Change Data Capture
    
    def get_recent_changes(self, limit: int = 100) -> List[Dict[str, Any]]:
        """
        Get recent database changes from the change log.
        
        This method queries the trades table ordered by created_at
        to simulate change tracking. For production use, consider
        implementing a dedicated change log table.
        
        Parameters
        ----------
        limit : int, optional
            Maximum number of changes to return (default: 100).
        
        Returns
        -------
        List[Dict[str, Any]]
            List of recent changes with metadata.
        """
        conn = self._get_connection()
        cursor = conn.cursor()
        
        cursor.execute("""
            SELECT id, market_slug, market_id, side, outcome, pnl, 
                   timestamp, created_at
            FROM trades
            ORDER BY created_at DESC
            LIMIT ?
        """, (limit,))
        
        changes = []
        for row in cursor.fetchall():
            changes.append({
                "id": row["id"],
                "market_slug": row["market_slug"],
                "market_id": row["market_id"],
                "side": row["side"],
                "outcome": row["outcome"],
                "pnl": row["pnl"],
                "timestamp": row["timestamp"],
                "created_at": row["created_at"],
                "operation": "INSERT"  # Simulated operation type
            })
        
        log.debug("Retrieved %d recent changes", len(changes))
        return changes
    
    def close(self) -> None:
        """Close the database connection."""
        if self._conn is not None:
            self._conn.close()
            self._conn = None
            log.debug("Database connection closed")
    
    def __enter__(self):
        """Context manager entry."""
        return self
    
    def __exit__(self, exc_type, exc_val, exc_tb):
        """Context manager exit."""
        self.close()
        return False
    
    def _row_to_trade_record(self, row: sqlite3.Row) -> TradeRecord:
        """Convert a database row to a TradeRecord."""
        timestamp = datetime.fromisoformat(row["timestamp"])
        if timestamp.tzinfo is None:
            timestamp = timestamp.replace(tzinfo=timezone.utc)
        
        # Handle market_session - may not exist in older databases
        # sqlite3.Row doesn't have .get(), so we need to check key existence
        try:
            market_session = row["market_session"]
        except (KeyError, IndexError):
            market_session = None
        
        return TradeRecord(
            id=row["id"],
            market_slug=row["market_slug"],
            market_id=row["market_id"],
            side=row["side"],
            entry_price=row["entry_price"],
            exit_price=row["exit_price"],
            amount=row["amount"],
            shares=row["shares"],
            fee=row["fee"],
            outcome=row["outcome"],
            pnl=row["pnl"],
            timestamp=timestamp,
            market_session=market_session,
        )
