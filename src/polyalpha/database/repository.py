from __future__ import annotations

import hashlib
import json
import logging
import time
from datetime import datetime, timezone
from typing import Optional, List, Dict, Any, Callable
from threading import Lock
from concurrent.futures import ThreadPoolExecutor, as_completed

from .models import TradeRecord, TradeStatistics, row_to_trade_record

log = logging.getLogger(__name__)


class QueryCache:
    def __init__(self):
        self._cache_enabled = True
        self._query_cache: Dict[str, List[TradeRecord]] = {}
        self._cache_max_size = 100
        self._cache_ttl: Dict[str, float] = {}
        self._default_cache_ttl = 300.0
        self._cache_hits = 0
        self._cache_misses = 0

    def _generate_cache_key(
        self,
        filters: Optional[Dict[str, Any]] = None,
        sort_by: str = "timestamp",
        sort_order: str = "desc",
        limit: Optional[int] = None,
        offset: int = 0,
    ) -> str:
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
        self._query_cache.clear()
        self._cache_ttl.clear()

    def _is_cache_entry_valid(self, cache_key: str) -> bool:
        if cache_key not in self._cache_ttl:
            return False
        entry_time = self._cache_ttl[cache_key]
        current_time = time.time()
        return (current_time - entry_time) < self._default_cache_ttl

    def get_cached(self, cache_key: str) -> Optional[List[TradeRecord]]:
        if cache_key in self._query_cache and self._is_cache_entry_valid(cache_key):
            self._cache_hits += 1
            return self._query_cache[cache_key]
        self._cache_misses += 1
        return None

    def set_cached(self, cache_key: str, trades: List[TradeRecord]) -> None:
        if len(self._query_cache) >= self._cache_max_size:
            oldest_key = next(iter(self._query_cache))
            self._query_cache.pop(oldest_key)
            self._cache_ttl.pop(oldest_key, None)
        self._query_cache[cache_key] = trades
        self._cache_ttl[cache_key] = time.time()

    def clear(self) -> None:
        self._invalidate_cache()

    def enable(self) -> None:
        self._cache_enabled = True

    def disable(self) -> None:
        self._cache_enabled = False
        self._invalidate_cache()

    @property
    def enabled(self) -> bool:
        return self._cache_enabled

    @property
    def size(self) -> int:
        return len(self._query_cache)

    @property
    def hit_rate(self) -> float:
        total = self._cache_hits + self._cache_misses
        return (self._cache_hits / total) if total > 0 else 0.0

    def clean_expired(self) -> None:
        current_time = time.time()
        expired_keys = [k for k, t in self._cache_ttl.items()
                        if (current_time - t) >= self._default_cache_ttl]
        for key in expired_keys:
            self._query_cache.pop(key, None)
            self._cache_ttl.pop(key, None)
        if expired_keys:
            log.debug("Cleaned %d expired cache entries", len(expired_keys))

    @property
    def hits(self) -> int:
        return self._cache_hits

    @property
    def misses(self) -> int:
        return self._cache_misses


class TradeRepository:
    def __init__(self, conn_manager, query_cache: QueryCache, on_cache_invalidate: Callable[[], None]):
        self._conn = conn_manager
        self._cache = query_cache
        self._on_cache_invalidate = on_cache_invalidate

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
        if not market_slug or not isinstance(market_slug, str):
            raise ValueError("market_slug must be a non-empty string")
        if not market_id or not isinstance(market_id, str):
            raise ValueError("market_id must be a non-empty string")
        if side not in ("UP", "DOWN"):
            raise ValueError(f"side must be 'UP' or 'DOWN', got '{side}'")
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
        valid_outcomes = {"WON", "LOST", "CLOSED", None}
        if outcome not in valid_outcomes:
            raise ValueError(f"outcome must be one of {valid_outcomes}, got '{outcome}'")
        if not isinstance(timestamp, datetime):
            raise ValueError("timestamp must be a datetime object")
        if timestamp.tzinfo is None:
            raise ValueError("timestamp must be timezone-aware")

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
        order_id: Optional[str] = None,
        status: str = "pending",
        user_id: Optional[int] = None,
    ) -> int:
        self._validate_trade_data(
            market_slug, market_id, side, entry_price, exit_price,
            amount, shares, fee, outcome, pnl, timestamp, market_session
        )
        if check_duplicates:
            if self.is_duplicate_trade(market_id, side, timestamp):
                raise ValueError(
                    f"Duplicate trade detected: market_id={market_id}, "
                    f"side={side}, timestamp={timestamp.isoformat()}"
                )
        with self._conn._connection_ctx() as conn:
            cursor = conn.cursor()
            timestamp_str = timestamp.isoformat()
            cursor.execute("""
                INSERT INTO trades (
                    market_slug, market_id, side, entry_price, exit_price,
                    amount, shares, fee, outcome, pnl, timestamp, market_session,
                    order_id, status, user_id
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """, (
                market_slug, market_id, side, entry_price, exit_price,
                amount, shares, fee, outcome, pnl, timestamp_str, market_session,
                order_id, status, user_id
            ))
            conn.commit()
            trade_id = cursor.lastrowid
            self._on_cache_invalidate()
        log.debug("Trade saved: ID=%d, market=%s, side=%s, pnl=%.2f",
                  trade_id, market_slug, side, pnl)
        return trade_id

    def save_trades_bulk(
        self,
        trades: List[Dict[str, Any]],
        check_duplicates: bool = True,
        user_id: Optional[int] = None,
    ) -> List[int]:
        if not trades:
            return []
        with self._conn._connection_ctx() as conn:
            cursor = conn.cursor()
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
            if check_duplicates:
                seen: set[tuple[str, str, str]] = set()
                for trade in trades:
                    key = (trade["market_id"], trade["side"], trade["timestamp"].isoformat())
                    if key in seen:
                        raise ValueError(
                            f"Duplicate trade in batch: market_id={trade['market_id']}, "
                            f"side={trade['side']}, timestamp={trade['timestamp'].isoformat()}"
                        )
                    seen.add(key)
                    if self.is_duplicate_trade(trade["market_id"], trade["side"], trade["timestamp"]):
                        raise ValueError(
                            f"Duplicate trade detected: market_id={trade['market_id']}, "
                            f"side={trade['side']}, timestamp={trade['timestamp'].isoformat()}"
                        )
            trade_data = []
            for trade in trades:
                trade_data.append((
                    trade["market_slug"], trade["market_id"], trade["side"],
                    trade["entry_price"], trade.get("exit_price"),
                    trade["amount"], trade["shares"], trade["fee"],
                    trade.get("outcome"), trade["pnl"],
                    trade["timestamp"].isoformat(), trade.get("market_session"),
                    trade.get("order_id"), trade.get("status", "pending"),
                    user_id,
                ))
            cursor.execute("BEGIN TRANSACTION")
            try:
                cursor.executemany("""
                    INSERT INTO trades (
                        market_slug, market_id, side, entry_price, exit_price,
                        amount, shares, fee, outcome, pnl, timestamp, market_session,
                        order_id, status, user_id
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """, trade_data)
                conn.commit()
                cursor.execute("SELECT id FROM (SELECT id FROM trades ORDER BY id DESC LIMIT ?) ORDER BY id", (len(trades),))
                trade_ids = [row[0] for row in cursor.fetchall()]
                self._on_cache_invalidate()
                log.info("Bulk saved %d trades", len(trades))
                return trade_ids
            except Exception as e:
                conn.rollback()
                log.error("Bulk insert failed: %s", e)
                raise

    def update_trade_status(
        self,
        order_id: str,
        status: str,
        filled_shares: float = 0.0,
        filled_amount: float = 0.0,
        avg_fill_price: float = 0.0,
        filled_at: Optional[datetime] = None,
    ) -> bool:
        with self._conn._connection_ctx() as conn:
            cursor = conn.cursor()
            filled_at_str = filled_at.isoformat() if filled_at else None
            try:
                cursor.execute("""
                    UPDATE trades
                    SET status = ?, filled_shares = ?, filled_amount = ?,
                        avg_fill_price = ?, filled_at = ?
                    WHERE order_id = ?
                """, (status, filled_shares, filled_amount, avg_fill_price, filled_at_str, order_id))
                conn.commit()
                if cursor.rowcount > 0:
                    log.debug("Trade status updated: order_id=%s, status=%s", order_id, status)
                    self._on_cache_invalidate()
                    return True
                log.warning("No trade found with order_id=%s", order_id)
                return False
            except Exception as e:
                conn.rollback()
                log.error("Failed to update trade status: %s", e)
                return False

    def is_duplicate_trade(
        self,
        market_id: str,
        side: str,
        timestamp: datetime,
        tolerance_seconds: int = 1,
    ) -> bool:
        with self._conn._connection_ctx() as conn:
            cursor = conn.cursor()
            timestamp_str = timestamp.isoformat()
            cursor.execute("SELECT COUNT(*) FROM trades WHERE market_id = ? AND side = ? AND timestamp = ?",
                           (market_id, side.upper(), timestamp_str))
            count = cursor.fetchone()[0]
            if count > 0:
                return True
            cursor.execute("SELECT timestamp FROM trades WHERE market_id = ? AND side = ?",
                           (market_id, side.upper()))
            for ts_row in cursor.fetchall():
                stored_ts = datetime.fromisoformat(ts_row[0])
                if stored_ts.tzinfo is None:
                    stored_ts = stored_ts.replace(tzinfo=timezone.utc)
                if abs((timestamp - stored_ts).total_seconds()) <= tolerance_seconds:
                    return True
            return False

    def delete_trade(self, trade_id: int, streaming_enabled: bool = False, on_delete=None) -> bool:
        with self._conn._connection_ctx() as conn:
            cursor = conn.cursor()
            cursor.execute("DELETE FROM trades WHERE id = ?", (trade_id,))
            conn.commit()
            deleted = cursor.rowcount > 0
            if deleted:
                self._on_cache_invalidate()
                if streaming_enabled and on_delete:
                    on_delete(trade_id)
                log.debug("Trade deleted: ID=%d", trade_id)
            return deleted

    def clear_all_trades(self) -> None:
        with self._conn._connection_ctx() as conn:
            cursor = conn.cursor()
            cursor.execute("DELETE FROM trades")
            conn.commit()
            self._on_cache_invalidate()
            log.info("All trades cleared from database")

    def load_all_trades(self) -> List[TradeRecord]:
        with self._conn._connection_ctx() as conn:
            cursor = conn.cursor()
            cursor.execute("""
                SELECT id, market_slug, market_id, side, entry_price, exit_price,
                       amount, shares, fee, outcome, pnl, timestamp, market_session, user_id
                FROM trades ORDER BY timestamp DESC
            """)
            trades = [row_to_trade_record(row) for row in cursor.fetchall()]
            log.debug("Loaded %d trades from database", len(trades))
            return trades

    def load_trades_by_market(self, market_slug: str) -> List[TradeRecord]:
        with self._conn._connection_ctx() as conn:
            cursor = conn.cursor()
            cursor.execute("""
                SELECT id, market_slug, market_id, side, entry_price, exit_price,
                       amount, shares, fee, outcome, pnl, timestamp, market_session, user_id
                FROM trades WHERE market_slug = ? ORDER BY timestamp DESC
            """, (market_slug,))
            return [row_to_trade_record(row) for row in cursor.fetchall()]

    def load_trades_by_asset(self, asset: str) -> List[TradeRecord]:
        with self._conn._connection_ctx() as conn:
            cursor = conn.cursor()
            pattern = f"{asset.lower()}%"
            cursor.execute("""
                SELECT id, market_slug, market_id, side, entry_price, exit_price,
                       amount, shares, fee, outcome, pnl, timestamp, market_session, user_id
                FROM trades WHERE LOWER(market_slug) LIKE ? ORDER BY timestamp DESC
            """, (pattern,))
            return [row_to_trade_record(row) for row in cursor.fetchall()]

    def load_trades_by_side(self, side: str) -> List[TradeRecord]:
        with self._conn._connection_ctx() as conn:
            cursor = conn.cursor()
            cursor.execute("""
                SELECT id, market_slug, market_id, side, entry_price, exit_price,
                       amount, shares, fee, outcome, pnl, timestamp, market_session, user_id
                FROM trades WHERE side = ? ORDER BY timestamp DESC
            """, (side.upper(),))
            return [row_to_trade_record(row) for row in cursor.fetchall()]

    def load_trades_by_outcome(self, outcome: str) -> List[TradeRecord]:
        with self._conn._connection_ctx() as conn:
            cursor = conn.cursor()
            cursor.execute("""
                SELECT id, market_slug, market_id, side, entry_price, exit_price,
                       amount, shares, fee, outcome, pnl, timestamp, market_session, user_id
                FROM trades WHERE outcome = ? ORDER BY timestamp DESC
            """, (outcome.upper(),))
            return [row_to_trade_record(row) for row in cursor.fetchall()]

    def load_trades_by_market_session(self, market_session: str) -> List[TradeRecord]:
        with self._conn._connection_ctx() as conn:
            cursor = conn.cursor()
            cursor.execute("""
                SELECT id, market_slug, market_id, side, entry_price, exit_price,
                       amount, shares, fee, outcome, pnl, timestamp, market_session, user_id
                FROM trades WHERE market_session = ? ORDER BY timestamp DESC
            """, (market_session,))
            return [row_to_trade_record(row) for row in cursor.fetchall()]

    def load_trades_by_date_range(self, start_date: datetime, end_date: datetime) -> List[TradeRecord]:
        with self._conn._connection_ctx() as conn:
            cursor = conn.cursor()
            cursor.execute("""
                SELECT id, market_slug, market_id, side, entry_price, exit_price,
                       amount, shares, fee, outcome, pnl, timestamp, market_session, user_id
                FROM trades WHERE timestamp >= ? AND timestamp <= ? ORDER BY timestamp DESC
            """, (start_date.isoformat(), end_date.isoformat()))
            return [row_to_trade_record(row) for row in cursor.fetchall()]

    def load_trades(
        self,
        filters: Optional[Dict[str, Any]] = None,
        sort_by: str = "timestamp",
        sort_order: str = "desc",
        limit: Optional[int] = None,
        offset: int = 0,
    ) -> List[TradeRecord]:
        if self._cache.enabled:
            cache_key = self._cache._generate_cache_key(filters, sort_by, sort_order, limit, offset)
            cached = self._cache.get_cached(cache_key)
            if cached is not None:
                return cached

        with self._conn._connection_ctx() as conn:
            cursor = conn.cursor()
            query = """
                SELECT id, market_slug, market_id, side, entry_price, exit_price,
                       amount, shares, fee, outcome, pnl, timestamp, market_session, user_id
                FROM trades
            """
            params = []
            where_clauses = []

            if filters:
                if "asset" in filters:
                    pattern = f"{filters['asset'].lower()}%"
                    where_clauses.append("LOWER(market_slug) LIKE ?")
                    params.append(pattern)
                if "side" in filters:
                    where_clauses.append("side = ?")
                    params.append(filters["side"].upper())
                if "outcome" in filters:
                    where_clauses.append("outcome = ?")
                    params.append(filters["outcome"].upper())
                if "min_pnl" in filters:
                    where_clauses.append("pnl >= ?")
                    params.append(float(filters["min_pnl"]))
                if "max_pnl" in filters:
                    where_clauses.append("pnl <= ?")
                    params.append(float(filters["max_pnl"]))
                if "min_amount" in filters:
                    where_clauses.append("amount >= ?")
                    params.append(float(filters["min_amount"]))
                if "max_amount" in filters:
                    where_clauses.append("amount <= ?")
                    params.append(float(filters["max_amount"]))
                if "market_slug" in filters:
                    where_clauses.append("market_slug = ?")
                    params.append(filters["market_slug"])
                if "market_id" in filters:
                    where_clauses.append("market_id = ?")
                    params.append(filters["market_id"])
                if "user_id" in filters:
                    user_id_val = filters["user_id"]
                    if user_id_val is not None:
                        where_clauses.append("user_id = ?")
                        params.append(int(user_id_val))
                    else:
                        where_clauses.append("user_id IS NULL")

            if where_clauses:
                query += " WHERE " + " AND ".join(where_clauses)

            valid_sort_fields = {"timestamp", "pnl", "amount", "entry_price", "shares", "fee",
                                 "market_slug", "side", "outcome"}
            if sort_by not in valid_sort_fields:
                raise ValueError(f"Invalid sort_by field '{sort_by}'. Valid options: {sorted(valid_sort_fields)}")

            sort_order = sort_order.lower()
            if sort_order not in ("asc", "desc"):
                raise ValueError(f"sort_order must be 'asc' or 'desc', got '{sort_order}'")

            sort_field_map = {
                "timestamp": "timestamp", "pnl": "pnl", "amount": "amount",
                "entry_price": "entry_price", "shares": "shares", "fee": "fee",
                "market_slug": "market_slug", "side": "side", "outcome": "outcome"
            }
            safe_sort_by = sort_field_map.get(sort_by)
            if not safe_sort_by:
                raise ValueError(f"Invalid sort_by field '{sort_by}'. Valid options: {sorted(valid_sort_fields)}")
            query += f" ORDER BY {safe_sort_by} {sort_order.upper()}"

            if limit is not None:
                if limit <= 0:
                    raise ValueError(f"limit must be positive, got {limit}")
                query += " LIMIT ?"
                params.append(int(limit))
            if offset > 0:
                query += " OFFSET ?"
                params.append(int(offset))

            cursor.execute(query, params)
            trades = [row_to_trade_record(row) for row in cursor.fetchall()]

            if self._cache.enabled:
                cache_key = self._cache._generate_cache_key(filters, sort_by, sort_order, limit, offset)
                self._cache.set_cached(cache_key, trades)

            return trades

    def aggregate_trades(
        self,
        group_by: str = "asset",
        filters: Optional[Dict[str, Any]] = None,
    ) -> Dict[str, Dict[str, Any]]:
        valid_group_fields = {"asset", "side", "outcome", "market_slug"}
        if group_by not in valid_group_fields:
            raise ValueError(f"Invalid group_by field '{group_by}'. Valid options: {sorted(valid_group_fields)}")
        trades = self.load_trades(filters=filters)
        groups: Dict[str, List[TradeRecord]] = {}
        for trade in trades:
            if group_by == "asset":
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
        results = {}
        for key, group_trades in groups.items():
            count = len(group_trades)
            total_pnl = sum(t.pnl for t in group_trades)
            avg_pnl = total_pnl / count if count > 0 else 0.0
            wins = sum(1 for t in group_trades if t.outcome == "WON")
            losses = sum(1 for t in group_trades if t.outcome == "LOST")
            win_rate = (wins / count * 100) if count > 0 else 0.0
            results[key] = {"count": count, "total_pnl": total_pnl, "avg_pnl": avg_pnl,
                            "wins": wins, "losses": losses, "win_rate": win_rate}
        return results

    def get_statistics(self) -> TradeStatistics:
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
            total_trades=total_trades, wins=wins, losses=losses,
            win_rate=win_rate, total_pnl=total_pnl, total_fees=total_fees,
            avg_entry_price=avg_entry_price, avg_pnl_per_trade=avg_pnl_per_trade,
        )

    def stream_trades(self, filters=None, batch_size=100):
        offset = 0
        while True:
            batch = self.load_trades(filters=filters, limit=batch_size, offset=offset)
            if not batch:
                break
            yield batch
            offset += batch_size

    def stream_trades_by_asset(self, asset: str, batch_size: int = 100):
        offset = 0
        conn = self._conn._get_connection()
        try:
            while True:
                cursor = conn.cursor()
                pattern = f"{asset.lower()}%"
                cursor.execute("""
                    SELECT id, market_slug, market_id, side, entry_price, exit_price,
                           amount, shares, fee, outcome, pnl, timestamp, market_session, user_id
                    FROM trades WHERE LOWER(market_slug) LIKE ?
                    ORDER BY timestamp DESC LIMIT ? OFFSET ?
                """, (pattern, batch_size, offset))
                batch = [row_to_trade_record(row) for row in cursor.fetchall()]
                if not batch:
                    break
                yield batch
                offset += batch_size
        finally:
            self._conn._return_connection(conn)

    def get_user_statistics(self, user_id: int) -> TradeStatistics:
        trades = self.load_trades(filters={"user_id": str(user_id)})
        total_trades = len(trades)
        wins = sum(1 for t in trades if t.outcome == "WON")
        losses = sum(1 for t in trades if t.outcome == "LOST")
        win_rate = (wins / total_trades * 100) if total_trades > 0 else 0.0
        total_pnl = sum(t.pnl for t in trades)
        total_fees = sum(t.fee for t in trades)
        avg_entry_price = (sum(t.entry_price for t in trades) / total_trades) if total_trades > 0 else 0.0
        avg_pnl_per_trade = (total_pnl / total_trades) if total_trades > 0 else 0.0
        return TradeStatistics(
            total_trades=total_trades, wins=wins, losses=losses,
            win_rate=win_rate, total_pnl=total_pnl, total_fees=total_fees,
            avg_entry_price=avg_entry_price, avg_pnl_per_trade=avg_pnl_per_trade,
        )

    def refresh_materialized_views(self) -> None:
        with self._conn._connection_ctx() as conn:
            cursor = conn.cursor()
            cursor.execute("DELETE FROM trade_statistics_mv")
            cursor.execute("""
                INSERT INTO trade_statistics_mv (asset, total_trades, wins, losses, win_rate, total_pnl, avg_pnl, last_updated)
                SELECT SUBSTR(market_slug, 1, INSTR(market_slug, '-') - 1) as asset,
                       COUNT(*) as total_trades,
                       SUM(CASE WHEN outcome = 'WON' THEN 1 ELSE 0 END) as wins,
                       SUM(CASE WHEN outcome = 'LOST' THEN 1 ELSE 0 END) as losses,
                       CAST(SUM(CASE WHEN outcome = 'WON' THEN 1 ELSE 0 END) * 100.0 / COUNT(*) AS REAL) as win_rate,
                       SUM(pnl) as total_pnl, AVG(pnl) as avg_pnl,
                       datetime('now') as last_updated
                FROM trades GROUP BY asset
            """)
            cursor.execute("DELETE FROM daily_summary_mv")
            cursor.execute("""
                INSERT INTO daily_summary_mv (date, total_trades, total_pnl, total_fees, win_rate, last_updated)
                SELECT DATE(timestamp) as date, COUNT(*) as total_trades,
                       SUM(pnl) as total_pnl, SUM(fee) as total_fees,
                       CAST(SUM(CASE WHEN outcome = 'WON' THEN 1 ELSE 0 END) * 100.0 / COUNT(*) AS REAL) as win_rate,
                       datetime('now') as last_updated
                FROM trades GROUP BY DATE(timestamp)
            """)
            conn.commit()
            log.info("Materialized views refreshed")

    def get_trade_statistics_from_mv(self) -> Dict[str, Dict[str, Any]]:
        with self._conn._connection_ctx() as conn:
            cursor = conn.cursor()
            cursor.execute("SELECT * FROM trade_statistics_mv")
            stats = {}
            for row in cursor.fetchall():
                stats[row['asset']] = {
                    'total_trades': row['total_trades'], 'wins': row['wins'],
                    'losses': row['losses'], 'win_rate': row['win_rate'],
                    'total_pnl': row['total_pnl'], 'avg_pnl': row['avg_pnl'],
                    'last_updated': row['last_updated']
                }
            return stats

    def get_daily_summary_from_mv(self) -> Dict[str, Dict[str, Any]]:
        with self._conn._connection_ctx() as conn:
            cursor = conn.cursor()
            cursor.execute("SELECT * FROM daily_summary_mv ORDER BY date DESC")
            summary = {}
            for row in cursor.fetchall():
                summary[row['date']] = {
                    'total_trades': row['total_trades'], 'total_pnl': row['total_pnl'],
                    'total_fees': row['total_fees'], 'win_rate': row['win_rate'],
                    'last_updated': row['last_updated']
                }
            return summary

    def execute_parallel_queries(
        self,
        queries: List[str],
        params_list: Optional[List[tuple]] = None,
        max_workers: int = 4,
    ) -> List[List]:
        if params_list is None:
            params_list = [() for _ in queries]
        if len(queries) != len(params_list):
            raise ValueError("Number of queries must match number of params lists")
        results = [None] * len(queries)

        def execute_query(index: int, query: str, params: tuple) -> None:
            with self._conn._connection_ctx() as conn:
                cursor = conn.cursor()
                cursor.execute(query, params)
                results[index] = cursor.fetchall()

        with ThreadPoolExecutor(max_workers=max_workers) as executor:
            futures = [executor.submit(execute_query, i, q, p)
                       for i, (q, p) in enumerate(zip(queries, params_list))]
            for future in as_completed(futures):
                try:
                    future.result()
                except Exception as e:
                    log.error("Parallel query failed: %s", e)
        return results

    def get_parallel_statistics_by_assets(self, assets: List[str], max_workers: int = 4) -> Dict[str, Dict[str, Any]]:
        queries = []
        params_list = []
        for asset in assets:
            pattern = f"{asset.lower()}%"
            queries.append("""
                SELECT COUNT(*) as total_trades,
                       SUM(CASE WHEN outcome = 'WON' THEN 1 ELSE 0 END) as wins,
                       SUM(CASE WHEN outcome = 'LOST' THEN 1 ELSE 0 END) as losses,
                       SUM(pnl) as total_pnl, AVG(pnl) as avg_pnl, SUM(fee) as total_fees
                FROM trades WHERE LOWER(market_slug) LIKE ?
            """)
            params_list.append((pattern,))
        results = self.execute_parallel_queries(queries, params_list, max_workers)
        stats = {}
        for asset, rows in zip(assets, results):
            if rows and rows[0]:
                row = rows[0]
                total = row['total_trades']
                wins = row['wins'] or 0
                losses = row['losses'] or 0
                total_pnl = row['total_pnl'] or 0
                avg_pnl = row['avg_pnl'] or 0
                total_fees = row['total_fees'] or 0
                win_rate = (wins / total * 100) if total > 0 else 0
                stats[asset] = {'total_trades': total, 'wins': wins, 'losses': losses,
                                'win_rate': win_rate, 'total_pnl': total_pnl,
                                'avg_pnl': avg_pnl, 'total_fees': total_fees}
            else:
                stats[asset] = {'total_trades': 0, 'wins': 0, 'losses': 0, 'win_rate': 0,
                                'total_pnl': 0, 'avg_pnl': 0, 'total_fees': 0}
        return stats
