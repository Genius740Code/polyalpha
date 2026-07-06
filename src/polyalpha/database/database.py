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
from typing import Optional, List

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
