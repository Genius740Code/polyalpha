from __future__ import annotations

import sqlite3
import logging
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional
from threading import Lock, Thread, Event
from contextlib import contextmanager
from queue import Queue, Empty

log = logging.getLogger(__name__)


class DatabaseConnection:
    def __init__(self, db_path: str | Path, enable_wal: bool = True):
        self.db_path = Path(db_path)
        self._enable_wal = enable_wal

        self._conn: Optional[sqlite3.Connection] = None

        self._connection_pool: Queue[sqlite3.Connection] = Queue(maxsize=5)
        self._pool_lock = Lock()
        self._max_pool_size = 5
        self._pool_created = 0

        self._last_optimization: Optional[datetime] = None

        self._optimization_thread: Optional[Thread] = None
        self._optimization_stop_event = Event()
        self._optimization_interval = 3600

    def _get_connection(self) -> sqlite3.Connection:
        try:
            return self._connection_pool.get_nowait()
        except Empty:
            with self._pool_lock:
                if self._pool_created < self._max_pool_size:
                    conn = self._create_connection()
                    self._pool_created += 1
                    return conn
            return self._create_connection()

    def _create_connection(self) -> sqlite3.Connection:
        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row
        if self._enable_wal:
            conn.execute("PRAGMA journal_mode=WAL")
            conn.execute("PRAGMA synchronous=NORMAL")
        conn.execute("PRAGMA busy_timeout=5000")
        conn.execute("PRAGMA temp_store=MEMORY")
        conn.execute("PRAGMA mmap_size=268435456")
        conn.execute("PRAGMA page_size=4096")
        conn.execute("PRAGMA cache_size=-64000")
        conn.execute("PRAGMA locking_mode=NORMAL")
        conn.execute("PRAGMA foreign_keys=OFF")
        return conn

    def _return_connection(self, conn: sqlite3.Connection) -> None:
        try:
            self._connection_pool.put_nowait(conn)
        except:
            conn.close()

    @contextmanager
    def _connection_ctx(self) -> sqlite3.Connection:
        conn = self._get_connection()
        try:
            yield conn
        finally:
            self._return_connection(conn)

    def _initialize_db(self) -> None:
        with self._connection_ctx() as conn:
            cursor = conn.cursor()
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS schema_version (
                    version INTEGER PRIMARY KEY,
                    applied_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
                )
            """)
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS users (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    username TEXT UNIQUE NOT NULL,
                    password_hash TEXT NOT NULL,
                    created_at TEXT DEFAULT CURRENT_TIMESTAMP,
                    is_active INTEGER DEFAULT 1
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
                    created_at TEXT DEFAULT CURRENT_TIMESTAMP,
                    order_id TEXT,
                    status TEXT DEFAULT 'pending',
                    filled_shares REAL DEFAULT 0.0,
                    filled_amount REAL DEFAULT 0.0,
                    avg_fill_price REAL DEFAULT 0.0,
                    filled_at TEXT,
                    user_id INTEGER REFERENCES users(id)
                )
            """)
            cursor.execute("CREATE INDEX IF NOT EXISTS idx_market_slug ON trades(market_slug)")
            cursor.execute("CREATE INDEX IF NOT EXISTS idx_market_id ON trades(market_id)")
            cursor.execute("CREATE INDEX IF NOT EXISTS idx_side ON trades(side)")
            cursor.execute("CREATE INDEX IF NOT EXISTS idx_outcome ON trades(outcome)")
            cursor.execute("CREATE INDEX IF NOT EXISTS idx_timestamp ON trades(timestamp)")
            cursor.execute("CREATE INDEX IF NOT EXISTS idx_duplicate_check ON trades(market_id, side, timestamp)")
            cursor.execute("CREATE INDEX IF NOT EXISTS idx_market_session ON trades(market_session)")
            cursor.execute("CREATE INDEX IF NOT EXISTS idx_user_id ON trades(user_id)")

            cursor.execute("""
                CREATE TABLE IF NOT EXISTS trade_statistics_mv (
                    asset TEXT PRIMARY KEY,
                    total_trades INTEGER,
                    wins INTEGER,
                    losses INTEGER,
                    win_rate REAL,
                    total_pnl REAL,
                    avg_pnl REAL,
                    last_updated TEXT
                )
            """)
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS daily_summary_mv (
                    date TEXT PRIMARY KEY,
                    total_trades INTEGER,
                    total_pnl REAL,
                    total_fees REAL,
                    win_rate REAL,
                    last_updated TEXT
                )
            """)
            cursor.execute("INSERT OR IGNORE INTO schema_version (version) VALUES (1)")
            conn.commit()
        log.info("Database initialized at %s", self.db_path)

    def get_schema_version(self) -> int:
        with self._connection_ctx() as conn:
            cursor = conn.cursor()
            cursor.execute("SELECT MAX(version) FROM schema_version")
            result = cursor.fetchone()
            return result[0] if result[0] is not None else 0

    def _apply_migration(self, version: int, migration_sql: str) -> None:
        with self._connection_ctx() as conn:
            cursor = conn.cursor()
            current_version = self.get_schema_version()
            if current_version >= version:
                return
            log.info("Applying migration %d", version)
            try:
                cursor.executescript(migration_sql)
                cursor.execute("INSERT INTO schema_version (version) VALUES (?)", (version,))
                conn.commit()
                log.info("Migration %d applied successfully", version)
            except Exception as e:
                conn.rollback()
                log.warning("Migration %d skipped: %s", version, e)

    def run_migrations(self) -> None:
        current_version = self.get_schema_version()
        log.info("Current schema version: %d", current_version)
        migrations = {
            2: """
            ALTER TABLE trades ADD COLUMN order_id TEXT;
            ALTER TABLE trades ADD COLUMN status TEXT DEFAULT 'pending';
            ALTER TABLE trades ADD COLUMN filled_shares REAL DEFAULT 0.0;
            ALTER TABLE trades ADD COLUMN filled_amount REAL DEFAULT 0.0;
            ALTER TABLE trades ADD COLUMN avg_fill_price REAL DEFAULT 0.0;
            ALTER TABLE trades ADD COLUMN filled_at TEXT;
            """,
            3: """
            CREATE TABLE IF NOT EXISTS users (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                username TEXT UNIQUE NOT NULL,
                password_hash TEXT NOT NULL,
                created_at TEXT DEFAULT CURRENT_TIMESTAMP,
                is_active INTEGER DEFAULT 1
            );
            ALTER TABLE trades ADD COLUMN user_id INTEGER REFERENCES users(id);
            CREATE INDEX IF NOT EXISTS idx_user_id ON trades(user_id);
            """,
        }
        for version, migration_sql in sorted(migrations.items()):
            if version > current_version:
                self._apply_migration(version, migration_sql)

    def close(self) -> None:
        if self._optimization_thread is not None:
            self._optimization_stop_event.set()
            self._optimization_thread.join(timeout=5)
            self._optimization_thread = None
        while not self._connection_pool.empty():
            try:
                conn = self._connection_pool.get_nowait()
                conn.close()
            except Empty:
                break
        if self._conn is not None:
            self._conn.close()
            self._conn = None
        with self._pool_lock:
            self._pool_created = 0
        log.debug("Database connection closed")
