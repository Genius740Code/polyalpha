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

import logging
import sqlite3
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional, List, Dict, Any

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
    
    def __init__(self, db_path: str | Path):
        """
        Initialize the database.
        
        Parameters
        ----------
        db_path : str or Path
            Path to the SQLite database file.
        """
        self.db_path = Path(db_path)
        self._conn: Optional[sqlite3.Connection] = None
        self._initialize_db()
    
    def _get_connection(self) -> sqlite3.Connection:
        """Get or create database connection."""
        if self._conn is None:
            self._conn = sqlite3.connect(self.db_path)
            self._conn.row_factory = sqlite3.Row
        return self._conn
    
    def _initialize_db(self) -> None:
        """Create database schema if it doesn't exist."""
        conn = self._get_connection()
        cursor = conn.cursor()
        
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
        
        conn.commit()
        log.info("Database initialized at %s", self.db_path)
    
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
        
        Returns
        -------
        int
            The ID of the inserted trade.
        """
        conn = self._get_connection()
        cursor = conn.cursor()
        
        timestamp_str = timestamp.isoformat()
        
        cursor.execute("""
            INSERT INTO trades (
                market_slug, market_id, side, entry_price, exit_price,
                amount, shares, fee, outcome, pnl, timestamp
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """, (
            market_slug, market_id, side, entry_price, exit_price,
            amount, shares, fee, outcome, pnl, timestamp_str
        ))
        
        conn.commit()
        trade_id = cursor.lastrowid
        log.debug("Trade saved: ID=%d, market=%s, side=%s, pnl=%.2f",
                  trade_id, market_slug, side, pnl)
        return trade_id
    
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
                   amount, shares, fee, outcome, pnl, timestamp
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
                   amount, shares, fee, outcome, pnl, timestamp
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
                   amount, shares, fee, outcome, pnl, timestamp
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
                   amount, shares, fee, outcome, pnl, timestamp
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
                   amount, shares, fee, outcome, pnl, timestamp
            FROM trades
            WHERE outcome = ?
            ORDER BY timestamp DESC
        """, (outcome.upper(),))
        
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
                   amount, shares, fee, outcome, pnl, timestamp
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
        conn = self._get_connection()
        cursor = conn.cursor()
        
        # Build query with filters
        query = """
            SELECT id, market_slug, market_id, side, entry_price, exit_price,
                   amount, shares, fee, outcome, pnl, timestamp
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
            log.debug("Trade deleted: ID=%d", trade_id)
        return deleted
    
    def clear_all_trades(self) -> None:
        """Delete all trades from the database."""
        conn = self._get_connection()
        cursor = conn.cursor()
        
        cursor.execute("DELETE FROM trades")
        conn.commit()
        
        log.info("All trades cleared from database")
    
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
        )
