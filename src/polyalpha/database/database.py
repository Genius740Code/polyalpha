from __future__ import annotations

import logging
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional, List, Dict, Any, Callable, Set
from threading import Thread

from .models import (
    TradeRecord, TradeStatistics, DatabaseMetrics, LogEntry, AlertRule, DBUser,
)
from .connection import DatabaseConnection
from .repository import TradeRepository, QueryCache
from .export import DatabaseExporter, DatabaseBackup
from .monitoring import DatabaseMonitor, EventSystem
from .features import UserManager, SecurityManager, IndexManager, PreparedStatementManager

log = logging.getLogger(__name__)


class TradeDatabase:
    def __init__(self, db_path: str | Path, enable_wal: bool = True, enable_cache: bool = True):
        self.db_path = Path(db_path)

        self._conn_mgr = DatabaseConnection(self.db_path, enable_wal)
        self._cache = QueryCache()
        self._events = EventSystem()
        self._monitor = DatabaseMonitor()
        self._security = SecurityManager()
        self._prep_stmts = PreparedStatementManager()
        self._users = UserManager(self._conn_mgr)
        self._indexes = IndexManager(self._conn_mgr)
        self._repo = TradeRepository(self._conn_mgr, self._cache, self._cache._invalidate_cache)
        self._exporter = DatabaseExporter(self)
        self._backup = DatabaseBackup(self)

        if not enable_cache:
            self._cache.disable()

        self._last_optimization = None
        self._optimization_thread = None
        self._optimization_stop_event = self._conn_mgr._optimization_stop_event

        self._conn_mgr._initialize_db()
        self._conn_mgr.run_migrations()

    def _get_connection(self):
        return self._conn_mgr._get_connection()

    def _create_connection(self):
        return self._conn_mgr._create_connection()

    def _return_connection(self, conn):
        return self._conn_mgr._return_connection(conn)

    def _connection_ctx(self):
        return self._conn_mgr._connection_ctx()

    def _initialize_db(self):
        self._conn_mgr._initialize_db()

    def _validate_trade_data(self, *args, **kwargs):
        return self._repo._validate_trade_data(*args, **kwargs)

    def _generate_cache_key(self, *args, **kwargs):
        return self._cache._generate_cache_key(*args, **kwargs)

    def _invalidate_cache(self):
        self._cache._invalidate_cache()

    def _is_cache_entry_valid(self, cache_key):
        return self._cache._is_cache_entry_valid(cache_key)

    def _get_prepared_statement(self, query):
        return self._prep_stmts.get_prepared_statement(query, self._get_connection)

    def clear_prepared_statements(self):
        self._prep_stmts.clear()

    def _track_query(self, operation):
        return self._monitor._track_query(operation)

    def _add_log_entry(self, *args, **kwargs):
        return self._monitor._add_log_entry(*args, **kwargs)

    def set_correlation_id(self, correlation_id: str):
        self._monitor.set_correlation_id(correlation_id)

    def clear_correlation_id(self):
        self._monitor.clear_correlation_id()

    def _get_correlation_id(self):
        return self._monitor._get_correlation_id()

    def operation_context(self, operation_name: str):
        return self._monitor.operation_context(operation_name)

    def _trigger_trade_saved_hooks(self, trade):
        self._events._trigger_trade_saved_hooks(trade)

    def _trigger_trade_updated_hooks(self, trade_id, changes):
        self._events._trigger_trade_updated_hooks(trade_id, changes)

    def _trigger_trade_deleted_hooks(self, trade_id):
        self._events._trigger_trade_deleted_hooks(trade_id)

    def _row_to_trade_record(self, row):
        from .models import row_to_trade_record
        return row_to_trade_record(row)

    def _clean_expired_cache(self):
        self._cache.clean_expired()

    @property
    def _query_cache(self):
        return self._cache._query_cache

    @property
    def _cache_max_size(self):
        return self._cache._cache_max_size

    @_cache_max_size.setter
    def _cache_max_size(self, value):
        self._cache._cache_max_size = value

    @property
    def _trade_updated_hooks(self):
        return self._events._trade_updated_hooks

    @property
    def _cache_enabled(self):
        return self._cache._cache_enabled

    @_cache_enabled.setter
    def _cache_enabled(self, value):
        if value:
            self._cache.enable()
        else:
            self._cache.disable()

    @property
    def _auth_manager(self):
        return self._security.auth_manager

    @property
    def _authz_manager(self):
        return self._security.authz_manager

    @property
    def _data_masker(self):
        return self._security.data_masker

    # --- Public API: Trade CRUD ---

    def save_trade(self, *args, **kwargs):
        kwargs.setdefault("user_id", self._security.current_user_id)
        result = self._repo.save_trade(*args, **kwargs)
        if self._events.streaming_enabled:
            trades = self._repo.load_trades(filters={"id": str(result)})
            if trades:
                self._events._trigger_trade_saved_hooks(trades[0])
        return result

    def save_trades_bulk(self, trades, **kwargs):
        return self._repo.save_trades_bulk(trades, **kwargs)

    def update_trade_status(self, *args, **kwargs):
        return self._repo.update_trade_status(*args, **kwargs)

    def is_duplicate_trade(self, *args, **kwargs):
        return self._repo.is_duplicate_trade(*args, **kwargs)

    def delete_trade(self, trade_id: int) -> bool:
        return self._repo.delete_trade(
            trade_id,
            streaming_enabled=self._events.streaming_enabled,
            on_delete=self._events._trigger_trade_deleted_hooks,
        )

    def clear_all_trades(self):
        self._repo.clear_all_trades()

    # --- Public API: Trade Queries ---

    def load_all_trades(self) -> List[TradeRecord]:
        return self._repo.load_all_trades()

    def load_trades_by_market(self, market_slug: str) -> List[TradeRecord]:
        return self._repo.load_trades_by_market(market_slug)

    def load_trades_by_asset(self, asset: str) -> List[TradeRecord]:
        return self._repo.load_trades_by_asset(asset)

    def load_trades_by_side(self, side: str) -> List[TradeRecord]:
        return self._repo.load_trades_by_side(side)

    def load_trades_by_outcome(self, outcome: str) -> List[TradeRecord]:
        return self._repo.load_trades_by_outcome(outcome)

    def load_trades_by_market_session(self, market_session: str) -> List[TradeRecord]:
        return self._repo.load_trades_by_market_session(market_session)

    def load_trades_by_date_range(self, start_date: datetime, end_date: datetime) -> List[TradeRecord]:
        return self._repo.load_trades_by_date_range(start_date, end_date)

    def load_trades(self, *args, **kwargs) -> List[TradeRecord]:
        self.require_permission("read")
        return self._repo.load_trades(*args, **kwargs)

    def aggregate_trades(self, *args, **kwargs) -> Dict[str, Dict[str, Any]]:
        return self._repo.aggregate_trades(*args, **kwargs)

    def get_statistics(self) -> TradeStatistics:
        return self._repo.get_statistics()

    def get_user_statistics(self, user_id: int) -> TradeStatistics:
        return self._repo.get_user_statistics(user_id)

    def stream_trades(self, *args, **kwargs):
        return self._repo.stream_trades(*args, **kwargs)

    def stream_trades_by_asset(self, asset: str, batch_size: int = 100):
        return self._repo.stream_trades_by_asset(asset, batch_size)

    # --- Public API: User Management ---

    def create_user(self, username: str, password_hash: str) -> int:
        return self._users.create_user(username, password_hash)

    def get_user(self, user_id: int) -> Optional[DBUser]:
        return self._users.get_user(user_id)

    def get_user_by_username(self, username: str) -> Optional[DBUser]:
        return self._users.get_user_by_username(username)

    def get_all_users(self) -> List[DBUser]:
        return self._users.get_all_users()

    def deactivate_user(self, user_id: int) -> bool:
        return self._users.deactivate_user(user_id)

    def delete_user(self, user_id: int, reassign_trades: bool = False) -> bool:
        return self._users.delete_user(user_id, reassign_trades)

    def load_trades_by_user(self, user_id: int) -> List[TradeRecord]:
        return self._repo.load_trades(filters={"user_id": str(user_id)})

    # --- Public API: Export ---

    def export_csv(self, filepath: str | Path, filters: Optional[Dict[str, Any]] = None) -> None:
        self._exporter.export_csv(filepath, filters)

    def export_json(self, filepath: str | Path, filters: Optional[Dict[str, Any]] = None) -> None:
        self._exporter.export_json(filepath, filters)

    def export_parquet(self, filepath: str | Path, filters: Optional[Dict[str, Any]] = None) -> None:
        self._exporter.export_parquet(filepath, filters)

    def export_excel(self, filepath: str | Path, filters: Optional[Dict[str, Any]] = None) -> None:
        self._exporter.export_excel(filepath, filters)

    # --- Public API: Backup and Restore ---

    def backup(self, backup_path: str | Path) -> None:
        self._backup.backup(backup_path)

    def restore(self, backup_path: str | Path, overwrite: bool = False) -> None:
        self._backup.restore(backup_path, overwrite)

    def backup_to_s3(self, *args, **kwargs) -> None:
        self._backup.backup_to_s3(*args, **kwargs)

    def backup_to_gcs(self, *args, **kwargs) -> None:
        self._backup.backup_to_gcs(*args, **kwargs)

    # --- Public API: Cache ---

    def enable_cache(self) -> None:
        self._cache.enable()

    def disable_cache(self) -> None:
        self._cache.disable()

    def clear_cache(self) -> None:
        self._cache.clear()

    # --- Public API: Parallel Queries ---

    def execute_parallel_queries(self, queries, params_list=None, max_workers=4):
        return self._repo.execute_parallel_queries(queries, params_list, max_workers)

    def get_parallel_statistics_by_assets(self, assets, max_workers=4):
        return self._repo.get_parallel_statistics_by_assets(assets, max_workers)

    # --- Public API: Index Management ---

    def analyze_indexes(self) -> None:
        self._indexes.analyze_indexes()

    def optimize_database(self) -> None:
        self._indexes.optimize_database()
        self._last_optimization = datetime.now(timezone.utc)

    def get_index_info(self) -> Dict[str, Dict[str, Any]]:
        return self._indexes.get_index_info()

    def rebuild_index(self, index_name: str) -> None:
        self._indexes.rebuild_index(index_name)

    # --- Public API: Materialized Views ---

    def refresh_materialized_views(self) -> None:
        self._repo.refresh_materialized_views()

    def get_trade_statistics_from_mv(self) -> Dict[str, Dict[str, Any]]:
        return self._repo.get_trade_statistics_from_mv()

    def get_daily_summary_from_mv(self) -> Dict[str, Dict[str, Any]]:
        return self._repo.get_daily_summary_from_mv()

    # --- Public API: Background Optimization ---

    def start_background_optimization(self, interval_seconds: int = 3600) -> None:
        if self._optimization_thread is not None and self._optimization_thread.is_alive():
            log.warning("Background optimization thread already running")
            return
        self._optimization_interval = interval_seconds
        self._optimization_stop_event = self._conn_mgr._optimization_stop_event
        self._optimization_stop_event.clear()

        def optimization_loop():
            while not self._optimization_stop_event.wait(self._optimization_interval):
                try:
                    self._run_background_optimization()
                except Exception as e:
                    log.error("Background optimization failed: %s", e)

        self._optimization_thread = Thread(target=optimization_loop, daemon=True)
        self._optimization_thread.start()
        log.info("Background optimization started (interval: %d seconds)", interval_seconds)

    def stop_background_optimization(self) -> None:
        self._conn_mgr._optimization_stop_event.set()
        if self._optimization_thread is not None:
            self._optimization_thread.join(timeout=5)
            self._optimization_thread = None
            log.info("Background optimization stopped")

    def _run_background_optimization(self) -> None:
        log.info("Running background optimization...")
        self._repo.refresh_materialized_views()
        self._indexes.analyze_indexes()
        self._indexes.optimize_database()
        self._cache.clean_expired()
        log.info("Background optimization completed")

    # --- Public API: Schema Migrations ---

    def get_schema_version(self) -> int:
        return self._conn_mgr.get_schema_version()

    def run_migrations(self) -> None:
        self._conn_mgr.run_migrations()

    # --- Public API: Events / Hooks ---

    def on_trade_saved(self, callback: Callable[[TradeRecord], None]) -> Callable[[TradeRecord], None]:
        return self._events.on_trade_saved(callback)

    def on_trade_updated(self, callback: Callable[[int, Dict[str, Any]], None]) -> Callable[[int, Dict[str, Any]], None]:
        return self._events.on_trade_updated(callback)

    def on_trade_deleted(self, callback: Callable[[int], None]) -> Callable[[int], None]:
        return self._events.on_trade_deleted(callback)

    def remove_trade_saved_hook(self, callback: Callable[[TradeRecord], None]) -> None:
        self._events.remove_trade_saved_hook(callback)

    def remove_trade_updated_hook(self, callback: Callable[[int, Dict[str, Any]], None]) -> None:
        self._events.remove_trade_updated_hook(callback)

    def remove_trade_deleted_hook(self, callback: Callable[[int], None]) -> None:
        self._events.remove_trade_deleted_hook(callback)

    # --- Public API: Streaming ---

    def enable_streaming(self) -> None:
        self._events.enable_streaming()

    def disable_streaming(self) -> None:
        self._events.disable_streaming()

    def is_streaming_enabled(self) -> bool:
        return self._events.streaming_enabled

    # --- Public API: Change Data Capture ---

    def get_recent_changes(self, limit: int = 100) -> List[Dict[str, Any]]:
        with self._conn_mgr._connection_ctx() as conn:
            cursor = conn.cursor()
            cursor.execute("""
                SELECT id, market_slug, market_id, side, outcome, pnl, timestamp, created_at
                FROM trades ORDER BY created_at DESC LIMIT ?
            """, (limit,))
            changes = []
            for row in cursor.fetchall():
                changes.append({
                    "id": row["id"], "market_slug": row["market_slug"],
                    "market_id": row["market_id"], "side": row["side"],
                    "outcome": row["outcome"], "pnl": row["pnl"],
                    "timestamp": row["timestamp"], "created_at": row["created_at"],
                    "operation": "INSERT",
                })
            return changes

    # --- Public API: Metrics & Monitoring ---

    def get_metrics(self) -> DatabaseMetrics:
        with self._conn_mgr._connection_ctx() as conn:
            cursor = conn.cursor()
            cursor.execute("SELECT COUNT(*) FROM trades")
            total_trades = cursor.fetchone()[0]
            cursor.execute("PRAGMA journal_mode")
            wal_mode = cursor.fetchone()[0]
            wal_enabled = wal_mode.upper() == "WAL"
        database_size_bytes = self.db_path.stat().st_size if self.db_path.exists() else 0
        return DatabaseMetrics(
            total_trades=total_trades,
            database_size_bytes=database_size_bytes,
            cache_hit_rate=self._cache.hit_rate,
            cache_size=self._cache.size,
            query_count=self._monitor._query_count,
            slow_query_count=self._monitor._slow_query_count,
            avg_query_time_ms=(sum(self._monitor._query_times) / len(self._monitor._query_times)
                               if self._monitor._query_times else 0.0),
            connection_pool_size=self._conn_mgr._pool_created,
            wal_enabled=wal_enabled,
            last_optimization=self._last_optimization,
        )

    def get_logs(self, *args, **kwargs) -> List[LogEntry]:
        return self._monitor.get_logs(*args, **kwargs)

    def set_alert(self, *args, **kwargs) -> None:
        self._monitor.set_alert(*args, **kwargs)

    def remove_alert(self, name: str) -> None:
        self._monitor.remove_alert(name)

    def get_alerts(self) -> Dict[str, Dict[str, Any]]:
        return self._monitor.get_alerts()

    def check_alerts(self) -> None:
        metrics = self.get_metrics()
        self._monitor.check_alerts(metrics)

    # --- Public API: Security ---

    def enable_encryption(self, key=None, password=None, fields=None):
        self._security.enable_encryption(key, password, fields)

    def disable_encryption(self):
        self._security.disable_encryption()

    def is_encryption_enabled(self) -> bool:
        return self._security.is_encryption_enabled()

    def set_auth_method(self, method: str) -> None:
        self._security.set_auth_method(method)

    def get_auth_method(self) -> str:
        return self._security.get_auth_method()

    def add_user(self, user_id: str, username: str, roles: List[str],
                 api_key=None, jwt_secret=None) -> None:
        self._security.add_user(user_id, username, roles, api_key, jwt_secret)

    def remove_user(self, user_id: str) -> None:
        self._security.remove_user(user_id)

    def authenticate(self, credential: str, user_id: Optional[str] = None) -> bool:
        return self._security.authenticate(credential, user_id)

    def get_current_user(self) -> Optional[str]:
        return self._security.get_current_user()

    def get_current_roles(self) -> Set[str]:
        return self._security.get_current_roles()

    def add_role(self, name: str, permissions: List[str], description: Optional[str] = None) -> None:
        self._security.add_role(name, permissions, description)

    def remove_role(self, role_name: str) -> None:
        self._security.remove_role(role_name)

    def check_permission(self, permission: str) -> bool:
        return self._security.check_permission(permission)

    def require_permission(self, permission: str) -> None:
        self._security.require_permission(permission)

    def add_masking_rule(self, *args, **kwargs) -> None:
        self._security.add_masking_rule(*args, **kwargs)

    def remove_masking_rule(self, field_name: str) -> None:
        self._security.remove_masking_rule(field_name)

    def enable_masking(self) -> None:
        self._security.enable_masking()

    def disable_masking(self) -> None:
        self._security.disable_masking()

    def is_masking_enabled(self) -> bool:
        return self._security.is_masking_enabled()

    def mask_trade_record(self, trade: TradeRecord) -> Dict[str, Any]:
        return self._security.mask_trade_record(trade)

    # --- Public API: Lifecycle ---

    def close(self) -> None:
        self.stop_background_optimization()
        self._conn_mgr.close()

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        self.close()
        return False
