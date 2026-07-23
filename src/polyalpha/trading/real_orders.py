"""Real order/position dataclasses for Polymarket CLOB trading."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Optional


@dataclass
class RealOrder:
    """A real order executed on the CLOB."""

    id: str
    market_id: str
    slug: str
    side: str
    price: float
    amount: float
    shares: float
    fee: float
    status: str  # "pending", "open", "filled", "partially_filled", "cancelled", "expired"
    is_limit: bool
    created_at: datetime
    filled_at: Optional[datetime] = None
    tx_hash: Optional[str] = None

    # Risk management
    stop_loss: Optional[float] = None
    take_profit: Optional[float] = None

    # Position sizing info
    sizing_strategy: str = "fixed"
    confidence: float = 0.5
    kelly_fraction: float = 0.0

    # Fill tracking
    filled_shares: float = 0.0
    filled_amount: float = 0.0
    avg_fill_price: float = 0.0
    last_status_check: Optional[datetime] = None
    status_check_attempts: int = 0

    def dump(self) -> dict:
        return {
            "id": self.id,
            "market_id": self.market_id,
            "market": self.slug,
            "side": self.side,
            "price": self.price,
            "amount": self.amount,
            "shares": self.shares,
            "fee": self.fee,
            "status": self.status,
            "is_limit": self.is_limit,
            "created_at": self.created_at.isoformat(),
            "filled_at": self.filled_at.isoformat() if self.filled_at else None,
            "tx_hash": self.tx_hash,
            "stop_loss": self.stop_loss,
            "take_profit": self.take_profit,
            "sizing_strategy": self.sizing_strategy,
            "confidence": self.confidence,
            "kelly_fraction": self.kelly_fraction,
            "filled_shares": self.filled_shares,
            "filled_amount": self.filled_amount,
            "avg_fill_price": self.avg_fill_price,
            "last_status_check": self.last_status_check.isoformat() if self.last_status_check else None,
            "status_check_attempts": self.status_check_attempts,
        }

    @staticmethod
    def from_dump(data: dict) -> "RealOrder":
        created_at = datetime.fromisoformat(data["created_at"]) if data.get("created_at") else _now()
        filled_at = datetime.fromisoformat(data["filled_at"]) if data.get("filled_at") else None
        last_sc = datetime.fromisoformat(data["last_status_check"]) if data.get("last_status_check") else None

        return RealOrder(
            id=data.get("id", ""),
            market_id=data.get("market_id", ""),
            slug=data.get("market", ""),
            side=data.get("side", "UP"),
            price=float(data.get("price", 0)),
            amount=float(data.get("amount", 0)),
            shares=float(data.get("shares", 0)),
            fee=float(data.get("fee", 0)),
            status=data.get("status", "pending"),
            is_limit=bool(data.get("is_limit", False)),
            created_at=created_at,
            filled_at=filled_at,
            tx_hash=data.get("tx_hash"),
            stop_loss=float(data["stop_loss"]) if data.get("stop_loss") is not None else None,
            take_profit=float(data["take_profit"]) if data.get("take_profit") is not None else None,
            sizing_strategy=data.get("sizing_strategy", "fixed"),
            confidence=float(data.get("confidence", 0.5)),
            kelly_fraction=float(data.get("kelly_fraction", 0)),
            filled_shares=float(data.get("filled_shares", 0)),
            filled_amount=float(data.get("filled_amount", 0)),
            avg_fill_price=float(data.get("avg_fill_price", 0)),
            last_status_check=last_sc,
            status_check_attempts=int(data.get("status_check_attempts", 0)),
        )


@dataclass
class RealPosition:
    """A real position held on the CLOB."""

    market_id: str
    slug: str
    question: str
    side: str
    shares: float
    avg_price: float
    current_price: float
    cost_basis: float
    current_value: float
    resolved: bool = False
    outcome: Optional[str] = None
    order_ids: list[str] = field(default_factory=list)
    entry_time: Optional[datetime] = None

    # Risk management
    stop_loss: Optional[float] = None
    take_profit: Optional[float] = None

    # Position management
    scale_count: int = 0
    hedge_amount: float = 0.0

    @property
    def pnl(self) -> float:
        return self.current_value - self.cost_basis

    @property
    def pnl_pct(self) -> float:
        if self.cost_basis == 0:
            return 0.0
        return (self.pnl / self.cost_basis) * 100

    def dump(self) -> dict:
        return {
            "market_id": self.market_id,
            "market": self.slug,
            "question": self.question,
            "side": self.side,
            "shares": self.shares,
            "avg_price": self.avg_price,
            "current_price": self.current_price,
            "cost_basis": self.cost_basis,
            "current_value": self.current_value,
            "pnl": self.pnl,
            "pnl_pct": self.pnl_pct,
            "resolved": self.resolved,
            "outcome": self.outcome,
            "stop_loss": self.stop_loss,
            "take_profit": self.take_profit,
            "order_ids": self.order_ids,
            "entry_time": self.entry_time.isoformat() if self.entry_time else None,
            "scale_count": self.scale_count,
            "hedge_amount": self.hedge_amount,
        }

    @staticmethod
    def from_dump(data: dict) -> "RealPosition":
        entry_time = None
        if data.get("entry_time"):
            try:
                entry_time = datetime.fromisoformat(data["entry_time"])
            except (ValueError, TypeError):
                entry_time = None

        return RealPosition(
            market_id=data.get("market_id", data.get("market", "")),
            slug=data.get("market", ""),
            question=data.get("question", ""),
            side=data.get("side", "UP"),
            shares=float(data.get("shares", 0)),
            avg_price=float(data.get("avg_price", 0)),
            current_price=float(data.get("current_price", 0)),
            cost_basis=float(data.get("cost_basis", 0)),
            current_value=float(data.get("current_value", 0)),
            resolved=bool(data.get("resolved", False)),
            outcome=data.get("outcome"),
            order_ids=list(data.get("order_ids", [])),
            entry_time=entry_time,
            stop_loss=float(data["stop_loss"]) if data.get("stop_loss") is not None else None,
            take_profit=float(data["take_profit"]) if data.get("take_profit") is not None else None,
            scale_count=int(data.get("scale_count", 0)),
            hedge_amount=float(data.get("hedge_amount", 0)),
        )


@dataclass
class OCOOrder:
    """One-Cancels-Other (OCO) order pair."""

    id: str
    market_id: str
    slug: str
    side: str
    order1_id: str
    order2_id: str
    order1_price: float
    order2_price: float
    amount: float
    status: str  # "active", "triggered", "cancelled"
    created_at: datetime
    triggered_order_id: Optional[str] = None
    cancelled_order_id: Optional[str] = None
    triggered_at: Optional[datetime] = None

    def dump(self) -> dict:
        return {
            "id": self.id,
            "market": self.slug,
            "side": self.side,
            "order1_id": self.order1_id,
            "order2_id": self.order2_id,
            "order1_price": self.order1_price,
            "order2_price": self.order2_price,
            "amount": self.amount,
            "status": self.status,
            "created_at": self.created_at.isoformat(),
            "triggered_order_id": self.triggered_order_id,
            "cancelled_order_id": self.cancelled_order_id,
            "triggered_at": self.triggered_at.isoformat() if self.triggered_at else None,
        }


@dataclass
class BracketOrder:
    """Bracket order (entry + stop loss + take profit)."""

    id: str
    market_id: str
    slug: str
    side: str
    entry_order_id: str
    entry_price: float
    amount: float
    status: str  # "pending", "active", "partial", "completed", "cancelled"
    created_at: datetime
    stop_loss_order_id: Optional[str] = None
    take_profit_order_id: Optional[str] = None
    stop_loss_price: Optional[float] = None
    take_profit_price: Optional[float] = None
    filled_at: Optional[datetime] = None
    token_id: str = ""

    def dump(self) -> dict:
        return {
            "id": self.id,
            "market": self.slug,
            "side": self.side,
            "entry_order_id": self.entry_order_id,
            "stop_loss_order_id": self.stop_loss_order_id,
            "take_profit_order_id": self.take_profit_order_id,
            "entry_price": self.entry_price,
            "stop_loss_price": self.stop_loss_price,
            "take_profit_price": self.take_profit_price,
            "amount": self.amount,
            "status": self.status,
            "created_at": self.created_at.isoformat(),
            "filled_at": self.filled_at.isoformat() if self.filled_at else None,
        }


@dataclass
class ConditionalOrder:
    """Conditional order with if-then logic."""

    id: str
    market_id: str
    slug: str
    side: str
    condition_type: str  # "price_above", "price_below", "time_after"
    condition_value: float
    status: str  # "waiting", "triggered", "cancelled", "expired"
    created_at: datetime
    child_order_id: Optional[str] = None
    child_order_price: Optional[float] = None
    child_order_amount: Optional[float] = None
    triggered_at: Optional[datetime] = None
    expires_at: Optional[datetime] = None
    token_id: str = ""

    def dump(self) -> dict:
        return {
            "id": self.id,
            "market": self.slug,
            "side": self.side,
            "condition_type": self.condition_type,
            "condition_value": self.condition_value,
            "child_order_id": self.child_order_id,
            "child_order_price": self.child_order_price,
            "child_order_amount": self.child_order_amount,
            "status": self.status,
            "created_at": self.created_at.isoformat(),
            "triggered_at": self.triggered_at.isoformat() if self.triggered_at else None,
            "expires_at": self.expires_at.isoformat() if self.expires_at else None,
        }


@dataclass
class IcebergOrder:
    """Iceberg order for large order splitting."""

    id: str
    market_id: str
    slug: str
    side: str
    total_amount: float
    visible_size: float
    price: float
    status: str  # "active", "partial", "completed", "cancelled"
    created_at: datetime
    filled_amount: float = 0.0
    child_order_ids: list[str] = field(default_factory=list)
    token_id: str = ""

    @property
    def remaining_amount(self) -> float:
        return self.total_amount - self.filled_amount

    @property
    def progress_pct(self) -> float:
        if self.total_amount == 0:
            return 0.0
        return (self.filled_amount / self.total_amount) * 100

    def dump(self) -> dict:
        return {
            "id": self.id,
            "market": self.slug,
            "side": self.side,
            "total_amount": self.total_amount,
            "visible_size": self.visible_size,
            "price": self.price,
            "filled_amount": self.filled_amount,
            "remaining_amount": self.remaining_amount,
            "progress_pct": self.progress_pct,
            "status": self.status,
            "created_at": self.created_at.isoformat(),
            "child_order_ids": self.child_order_ids,
        }


@dataclass
class TWAPOrder:
    """Time-Weighted Average Price (TWAP) execution order."""

    id: str
    market_id: str
    slug: str
    side: str
    total_amount: float
    duration_seconds: int
    num_slices: int
    status: str  # "active", "partial", "completed", "cancelled"
    created_at: datetime
    price: Optional[float] = None
    filled_amount: float = 0.0
    ends_at: Optional[datetime] = None
    child_order_ids: list[str] = field(default_factory=list)
    slice_interval: float = 0.0
    token_id: str = ""

    @property
    def remaining_amount(self) -> float:
        return self.total_amount - self.filled_amount

    @property
    def slice_amount(self) -> float:
        return self.total_amount / self.num_slices

    @property
    def progress_pct(self) -> float:
        if self.total_amount == 0:
            return 0.0
        return (self.filled_amount / self.total_amount) * 100

    def dump(self) -> dict:
        return {
            "id": self.id,
            "market": self.slug,
            "side": self.side,
            "total_amount": self.total_amount,
            "duration_seconds": self.duration_seconds,
            "num_slices": self.num_slices,
            "price": self.price,
            "filled_amount": self.filled_amount,
            "remaining_amount": self.remaining_amount,
            "slice_amount": self.slice_amount,
            "progress_pct": self.progress_pct,
            "status": self.status,
            "created_at": self.created_at.isoformat(),
            "ends_at": self.ends_at.isoformat() if self.ends_at else None,
            "child_order_ids": self.child_order_ids,
            "slice_interval": self.slice_interval,
        }


# ── Helpers ─────────────────────────────────────────────────────────────────────


def _validate_side(side: str) -> str:
    """Validate and normalize side."""
    side = side.upper()
    if side not in ("UP", "DOWN"):
        raise ValueError(f"side must be 'UP' or 'DOWN', got '{side}'")
    return side


def _validate_positive(value: float, name: str) -> float:
    """Validate that value is positive."""
    if value <= 0:
        raise ValueError(f"{name} must be positive, got {value}")
    return value


def _now() -> datetime:
    """Get current UTC datetime."""
    return datetime.now(timezone.utc)
