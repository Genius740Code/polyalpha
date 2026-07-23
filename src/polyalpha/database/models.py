from __future__ import annotations

import sqlite3
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Optional, List, Dict, Any, Callable, Set


@dataclass
class DBUser:
    id: int
    username: str
    password_hash: str
    created_at: str
    is_active: bool = True

    def to_dict(self) -> dict:
        return {
            "id": self.id,
            "username": self.username,
            "created_at": self.created_at,
            "is_active": self.is_active,
        }


@dataclass
class TradeRecord:
    id: int
    market_slug: str
    market_id: str
    side: str
    entry_price: float
    exit_price: Optional[float]
    amount: float
    shares: float
    fee: float
    outcome: Optional[str]
    pnl: float
    timestamp: datetime
    market_session: Optional[str] = None
    user_id: Optional[int] = None

    def to_dict(self) -> dict:
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
            "user_id": self.user_id,
        }


@dataclass
class TradeStatistics:
    total_trades: int
    wins: int
    losses: int
    win_rate: float
    total_pnl: float
    total_fees: float
    avg_entry_price: float
    avg_pnl_per_trade: float


@dataclass
class DatabaseMetrics:
    total_trades: int
    database_size_bytes: int
    cache_hit_rate: float
    cache_size: int
    query_count: int
    slow_query_count: int
    avg_query_time_ms: float
    connection_pool_size: int
    wal_enabled: bool
    last_optimization: Optional[datetime]

    def to_dict(self) -> Dict[str, Any]:
        return {
            "total_trades": self.total_trades,
            "database_size_bytes": self.database_size_bytes,
            "database_size_mb": round(self.database_size_bytes / (1024 * 1024), 2),
            "cache_hit_rate": round(self.cache_hit_rate * 100, 2),
            "cache_size": self.cache_size,
            "query_count": self.query_count,
            "slow_query_count": self.slow_query_count,
            "avg_query_time_ms": round(self.avg_query_time_ms, 2),
            "connection_pool_size": self.connection_pool_size,
            "wal_enabled": self.wal_enabled,
            "last_optimization": self.last_optimization.isoformat() if self.last_optimization else None,
        }


@dataclass
class LogEntry:
    correlation_id: str
    timestamp: datetime
    level: str
    message: str
    operation: Optional[str]
    duration_ms: Optional[float]
    metadata: Dict[str, Any]

    def to_dict(self) -> Dict[str, Any]:
        return {
            "correlation_id": self.correlation_id,
            "timestamp": self.timestamp.isoformat(),
            "level": self.level,
            "message": self.message,
            "operation": self.operation,
            "duration_ms": self.duration_ms,
            "metadata": self.metadata,
        }


@dataclass
class AlertRule:
    name: str
    metric: str
    threshold: float
    comparison: str
    enabled: bool
    callback: Optional[Callable[[str, float, float], None]]
    last_triggered: Optional[datetime]
    trigger_count: int


def row_to_trade_record(row: sqlite3.Row) -> TradeRecord:
    timestamp = datetime.fromisoformat(row["timestamp"])
    if timestamp.tzinfo is None:
        timestamp = timestamp.replace(tzinfo=timezone.utc)
    try:
        market_session = row["market_session"]
    except (KeyError, IndexError):
        market_session = None
    try:
        user_id = row["user_id"]
    except (KeyError, IndexError):
        user_id = None
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
        user_id=user_id,
    )
