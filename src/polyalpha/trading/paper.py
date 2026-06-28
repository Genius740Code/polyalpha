"""
Paper trading engine — simulated orders, positions, and P&L.

All state is held in memory.  No real money, no signing, no API keys needed.
A 2% taker fee is applied on each fill to simulate real costs.

Usage
-----
    client = polyalpha.Client(balance=100.0)

    # Market fill — executes immediately at the current price
    order = client.paper.buy(market, side="UP", amount=10.0)

    # Limit order — queued until the live price crosses the threshold
    order = client.paper.limit(market, side="UP", price=0.92, amount=10.0)

    # Wire a stream so limits auto-fill on price events
    stream = client.stream(market)
    client.paper.attach_stream(stream, market)
    stream.start(background=True)

    # Cancel / inspect
    client.paper.cancel(order.id)
    client.paper.open()         # pending limit orders
    client.paper.positions()    # live positions
    client.paper.summary()      # P&L table
"""

from __future__ import annotations

import logging
import uuid
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Optional

from ..core import InsufficientBalance, OrderNotFound, TAKER_FEE_RATE

log = logging.getLogger(__name__)


# ── Dataclasses ────────────────────────────────────────────────────────────────

@dataclass
class PaperOrder:
    """A single simulated order (market or limit)."""

    id:        str
    market_id: str
    slug:      str
    side:      str           # "UP" | "DOWN"
    price:     float         # fill price, or limit threshold if pending
    amount:    float         # USDC spent (or reserved)
    shares:    float         # shares received after fee
    fee:       float         # USDC fee paid
    status:    str           # "open" | "filled" | "cancelled"
    is_limit:  bool
    filled_at: Optional[datetime] = None

    def dump(self) -> dict:
        return {
            "id":        self.id,
            "market":    self.slug,
            "side":      self.side,
            "price":     self.price,
            "amount":    self.amount,
            "shares":    self.shares,
            "fee":       self.fee,
            "status":    self.status,
            "is_limit":  self.is_limit,
            "filled_at": self.filled_at.isoformat() if self.filled_at else None,
        }


@dataclass
class PaperPosition:
    """
    An aggregated position for one side of one market.

    Multiple fills on the same market+side are merged into a single position
    using a volume-weighted average price.
    """

    market_id:     str
    slug:          str
    question:      str
    side:          str           # "UP" | "DOWN"
    shares:        float
    avg_price:     float
    current_price: float         # updated live from the attached stream
    resolved:      bool                = False
    outcome:       Optional[str]       = None   # "WON" | "LOST"
    order_ids:     list[str]           = field(default_factory=list)

    # ── Computed ───────────────────────────────────────────────────────────────

    @property
    def cost_basis(self) -> float:
        return round(self.shares * self.avg_price, 6)

    @property
    def current_value(self) -> float:
        """Shares × 1.0 if won, 0.0 if lost, else shares × live price."""
        if self.resolved:
            return round(self.shares, 6) if self.outcome == "WON" else 0.0
        return round(self.shares * self.current_price, 6)

    @property
    def pnl(self) -> float:
        return round(self.current_value - self.cost_basis, 6)

    @property
    def pnl_pct(self) -> float:
        if self.cost_basis == 0:
            return 0.0
        return round((self.pnl / self.cost_basis) * 100, 2)

    def dump(self) -> dict:
        return {
            "market":        self.slug,
            "question":      self.question,
            "side":          self.side,
            "shares":        round(self.shares,        4),
            "avg_price":     round(self.avg_price,     4),
            "current_price": round(self.current_price, 4),
            "cost_basis":    round(self.cost_basis,    4),
            "current_value": round(self.current_value, 4),
            "pnl":           round(self.pnl,           4),
            "pnl_pct":       round(self.pnl_pct,       2),
            "resolved":      self.resolved,
            "outcome":       self.outcome,
        }


# ── Engine ─────────────────────────────────────────────────────────────────────

class PaperEngine:
    """
    Paper trading engine.  Access via ``client.paper``.

    All order-book and position state is held in memory for the session.
    """

    def __init__(self, balance: float = 100.0):
        self._balance:   float                       = float(balance)
        self._orders:    dict[str, PaperOrder]       = {}
        self._positions: dict[str, PaperPosition]    = {}   # key: "{market_id}:{side}"

    # ── Balance ────────────────────────────────────────────────────────────────

    @property
    def balance(self) -> float:
        """Current paper USDC balance."""
        return self._balance

    def set_balance(self, amount: float) -> None:
        """Reset the paper balance to *amount*."""
        if amount < 0:
            raise ValueError("Balance cannot be negative")
        self._balance = float(amount)
        log.info("Paper: balance set to $%.2f", amount)

    # ── Orders ─────────────────────────────────────────────────────────────────

    def buy(self, market, side: str, amount: float) -> PaperOrder:
        """
        Simulated market buy — fills immediately at the current market price.

        Parameters
        ----------
        market : Market object
        side   : "UP" or "DOWN"
        amount : USDC to spend

        Returns
        -------
        PaperOrder with ``status="filled"``

        Example
        -------
        >>> order = client.paper.buy(market, side="UP", amount=10.0)
        """
        side   = _validate_side(side)
        amount = _validate_positive(float(amount), "amount")

        price = market.up_price if side == "UP" else market.down_price
        if price <= 0:
            price = 0.5  # safe fallback before first WS price arrives

        return self._fill(market, side, price, amount, is_limit=False)

    def limit(self, market, side: str, price: float, amount: float) -> PaperOrder:
        """
        Simulated limit order — fills when the streamed price crosses *price*.

        Requires ``attach_stream()`` to have been called, otherwise call
        ``check_limits(up, down)`` manually after each price update.

        Parameters
        ----------
        market : Market object
        side   : "UP" or "DOWN"
        price  : trigger price — fills when token price >= this value
        amount : USDC to spend

        Returns
        -------
        PaperOrder with ``status="open"``

        Example
        -------
        >>> order = client.paper.limit(market, side="UP", price=0.92, amount=25.0)
        """
        side   = _validate_side(side)
        price  = _validate_positive(float(price),  "price")
        amount = _validate_positive(float(amount), "amount")

        if amount > self._balance:
            raise InsufficientBalance(
                f"Order amount ${amount:.2f} exceeds balance ${self._balance:.2f}"
            )

        order_id = _new_id()
        order = PaperOrder(
            id        = order_id,
            market_id = market.id,
            slug      = market.slug,
            side      = side,
            price     = price,
            amount    = amount,
            shares    = 0.0,
            fee       = 0.0,
            status    = "open",
            is_limit  = True,
        )
        self._orders[order_id] = order
        self._balance -= amount  # reserve
        log.info(
            "Paper: limit %s @ %.3f $%.2f reserved — balance $%.2f",
            side, price, amount, self._balance,
        )
        return order

    def cancel(self, order_id: str) -> PaperOrder:
        """
        Cancel an open limit order and refund the reserved balance.

        Raises
        ------
        OrderNotFound  if the ID is unknown.
        ValueError     if the order is already filled or cancelled.

        Example
        -------
        >>> client.paper.cancel(order.id)
        """
        order = self._orders.get(order_id)
        if order is None:
            raise OrderNotFound(f"No order found: {order_id}")
        if order.status != "open":
            raise ValueError(
                f"Cannot cancel order with status='{order.status}' (must be 'open')"
            )

        order.status  = "cancelled"
        self._balance += order.amount   # refund
        log.info(
            "Paper: cancelled order %s — $%.2f refunded, balance $%.2f",
            order_id[:8], order.amount, self._balance,
        )
        return order

    # ── Queries ────────────────────────────────────────────────────────────────

    def open(self) -> list[PaperOrder]:
        """Return all open (pending) limit orders."""
        return [o for o in self._orders.values() if o.status == "open"]

    def orders(self) -> list[PaperOrder]:
        """Return all orders (open, filled, and cancelled)."""
        return list(self._orders.values())

    def positions(self) -> list[PaperPosition]:
        """Return all live (unresolved) positions."""
        return [p for p in self._positions.values() if not p.resolved]

    def all_positions(self) -> list[PaperPosition]:
        """Return all positions including resolved ones."""
        return list(self._positions.values())

    # ── Resolution ─────────────────────────────────────────────────────────────

    def resolve(self, market, outcome: str) -> None:
        """
        Mark all positions for *market* as resolved.

        Parameters
        ----------
        market  : Market object
        outcome : "UP" or "DOWN" — whichever outcome won

        Example
        -------
        >>> client.paper.resolve(market, outcome="UP")
        """
        outcome = outcome.upper()
        if outcome not in ("UP", "DOWN"):
            raise ValueError(f"outcome must be 'UP' or 'DOWN', got '{outcome}'")

        for pos in self._positions.values():
            if pos.market_id == market.id and not pos.resolved:
                pos.resolved = True
                pos.outcome  = "WON" if pos.side == outcome else "LOST"
                payout = pos.shares if pos.outcome == "WON" else 0.0
                self._balance += payout
                log.info(
                    "Paper: resolved %s → %s  payout=$%.2f  balance=$%.2f",
                    pos.slug, pos.outcome, payout, self._balance,
                )

    # ── Stream integration ─────────────────────────────────────────────────────

    def check_limits(self, market_id: str, up_price: float, down_price: float) -> None:
        """
        Update live position prices and fill any triggered limit orders.

        Called automatically when a stream is attached via ``attach_stream()``.
        Can also be called manually when running without a stream.
        """
        # Update live prices for all open positions in this market
        for pos in self._positions.values():
            if pos.market_id == market_id and not pos.resolved:
                pos.current_price = up_price if pos.side == "UP" else down_price

        # Check and fill pending limit orders
        for order in list(self._orders.values()):
            if order.status != "open" or order.market_id != market_id:
                continue
            current = up_price if order.side == "UP" else down_price
            if current >= order.price:
                self._fill_limit(order, current)

    def attach_stream(self, stream, market) -> None:
        """
        Wire *stream* so positions auto-update and limits auto-fill.

        Example
        -------
        >>> stream = client.stream(market)
        >>> client.paper.attach_stream(stream, market)
        >>> stream.start(background=True)
        """
        @stream.on("price")
        def _on_price(up: float, down: float) -> None:
            self.check_limits(market.id, up, down)

        @stream.on("close")
        def _on_close() -> None:
            log.info(
                "Paper: stream closed for %s — call paper.resolve(market, outcome)",
                market.slug,
            )

        log.info("Paper: stream attached for %s", market.slug)

    # ── Reporting ──────────────────────────────────────────────────────────────

    def summary(self) -> None:
        """Print a formatted P&L summary to stdout."""
        all_orders    = self.orders()
        all_positions = self.all_positions()

        filled    = [o for o in all_orders    if o.status == "filled"]
        open_pos  = [p for p in all_positions if not p.resolved]
        resolved  = [p for p in all_positions if p.resolved]

        total_invested = sum(o.amount for o in filled)
        total_fees     = sum(o.fee    for o in filled)
        wins           = [p for p in resolved if p.outcome == "WON"]
        losses         = [p for p in resolved if p.outcome == "LOST"]
        realised_pnl   = sum(p.pnl for p in resolved)
        unrealised_pnl = sum(p.pnl for p in open_pos)

        W = 64
        div = "─" * W
        print(div)
        print("  POLYALPHA — PAPER TRADING SUMMARY")
        print(div)
        print(f"  {'Balance':<22} ${self._balance:>10.2f}")
        print(f"  {'Total invested':<22} ${total_invested:>10.2f}")
        print(f"  {'Total fees paid':<22} ${total_fees:>10.4f}")
        print(f"  {'Unrealised P&L':<22} ${unrealised_pnl:>+10.2f}")
        print(f"  {'Realised P&L':<22} ${realised_pnl:>+10.2f}")

        if resolved:
            win_rate = len(wins) / len(resolved) * 100
            print(div)
            print(
                f"  Resolved: {len(resolved)} trades  "
                f"({len(wins)}W / {len(losses)}L  {win_rate:.0f}% win rate)"
            )
            print(f"\n  {'MARKET':<30} {'SIDE':<5} {'RESULT':<6} {'P&L':>9}")
            print(f"  {'─'*30} {'─'*5} {'─'*6} {'─'*9}")
            for p in resolved:
                label  = _slug_label(p.slug)
                result = "WON" if p.outcome == "WON" else "LOST"
                print(f"  {label:<30} {p.side:<5} {result:<6} ${p.pnl:>+8.2f}")

        if open_pos:
            print(div)
            print(f"  Open positions ({len(open_pos)})\n")
            print(f"  {'MARKET':<30} {'SIDE':<5} {'AVG':>6} {'NOW':>6} {'P&L':>9}")
            print(f"  {'─'*30} {'─'*5} {'─'*6} {'─'*6} {'─'*9}")
            for p in open_pos:
                label = _slug_label(p.slug)
                print(
                    f"  {label:<30} {p.side:<5} "
                    f"{p.avg_price:>6.3f} {p.current_price:>6.3f} ${p.pnl:>+8.2f}"
                )

        if not resolved and not open_pos:
            print(f"\n  No trades yet.")

        print(div)

    # ── Internal ───────────────────────────────────────────────────────────────

    def _fill(
        self,
        market,
        side:     str,
        price:    float,
        amount:   float,
        is_limit: bool,
    ) -> PaperOrder:
        """Execute a simulated fill and update the position book."""
        if amount > self._balance:
            raise InsufficientBalance(
                f"Order amount ${amount:.2f} exceeds balance ${self._balance:.2f}"
            )

        fee    = round(amount * TAKER_FEE_RATE, 6)
        net    = amount - fee
        shares = round(net / price, 6) if price > 0 else 0.0

        self._balance -= amount

        order = PaperOrder(
            id        = _new_id(),
            market_id = market.id,
            slug      = market.slug,
            side      = side,
            price     = price,
            amount    = amount,
            shares    = shares,
            fee       = fee,
            status    = "filled",
            is_limit  = is_limit,
            filled_at = _now(),
        )
        self._orders[order.id] = order

        self._upsert_position(market.id, market.slug, market.question, side, shares, price, order.id)
        log.info(
            "Paper: filled %s %.4f shares @ %.3f  fee=$%.4f  balance=$%.2f",
            side, shares, price, fee, self._balance,
        )
        return order

    def _fill_limit(self, order: PaperOrder, current_price: float) -> None:
        """Fill a pending limit order at *current_price* (balance already reserved)."""
        fee    = round(order.amount * TAKER_FEE_RATE, 6)
        net    = order.amount - fee
        shares = round(net / current_price, 6) if current_price > 0 else 0.0

        order.price     = current_price
        order.shares    = shares
        order.fee       = fee
        order.status    = "filled"
        order.filled_at = _now()

        # Resolve the question string from any existing position in this market
        question = next(
            (p.question for p in self._positions.values() if p.market_id == order.market_id),
            "",
        )
        self._upsert_position(
            order.market_id, order.slug, question, order.side, shares, current_price, order.id,
        )
        log.info(
            "Paper: limit filled %s %.4f shares @ %.3f  fee=$%.4f",
            order.side, shares, current_price, fee,
        )

    def _upsert_position(
        self,
        market_id: str,
        slug:      str,
        question:  str,
        side:      str,
        shares:    float,
        price:     float,
        order_id:  str,
    ) -> None:
        """Merge *shares* into an existing position or create a new one."""
        key = f"{market_id}:{side}"
        if key in self._positions:
            pos         = self._positions[key]
            total       = pos.shares + shares
            pos.avg_price = round(
                (pos.shares * pos.avg_price + shares * price) / total, 6
            )
            pos.shares  = total
            pos.order_ids.append(order_id)
        else:
            self._positions[key] = PaperPosition(
                market_id     = market_id,
                slug          = slug,
                question      = question,
                side          = side,
                shares        = shares,
                avg_price     = price,
                current_price = price,
                order_ids     = [order_id],
            )


# ── Helpers ────────────────────────────────────────────────────────────────────

def _validate_side(side: str) -> str:
    s = side.strip().upper()
    if s not in ("UP", "DOWN"):
        raise ValueError(f"side must be 'UP' or 'DOWN', got '{side!r}'")
    return s


def _validate_positive(value: float, name: str) -> float:
    if value <= 0:
        raise ValueError(f"{name} must be > 0, got {value}")
    return value


def _new_id() -> str:
    return str(uuid.uuid4())


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _slug_label(slug: str) -> str:
    """Shorten a slug for display.  btc-updown-5m-1234 → BTC 5m"""
    parts = slug.split("-")
    try:
        return f"{parts[0].upper()} {parts[2]}"
    except IndexError:
        return slug[:20]
