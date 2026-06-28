"""
Paper trading engine — simulated orders, positions, and P&L.

All fills are in-memory. No real money, no signing, no API keys needed.
Taker fee of 2% is applied on fills to simulate real costs.

Usage:
    client = polyalpha.Client(balance=100.0)

    # Market fill at current price
    order = client.paper.buy(market, side="UP", amount=10.0)

    # Limit — fills when price crosses threshold
    order = client.paper.limit(market, side="UP", price=0.92, amount=10.0)

    # Wire a stream so limits auto-fill on price events
    client.paper.attach_stream(stream)

    # Cancel / view
    client.paper.cancel(order.id)
    client.paper.open()
    client.paper.positions()
    client.paper.summary()
"""

import uuid
import logging
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Optional

log = logging.getLogger(__name__)

TAKER_FEE = 0.02   # 2% taker fee applied on each fill


# ── Dataclasses ────────────────────────────────────────────────────────

@dataclass
class PaperOrder:
    id:        str
    market_id: str
    slug:      str
    side:      str          # "UP" or "DOWN"
    price:     float        # fill price (market) or limit threshold
    amount:    float        # USDC in
    shares:    float        # shares received after fee
    fee:       float        # USDC fee paid
    status:    str          # "open" | "filled" | "cancelled"
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
    market_id:     str
    slug:          str
    question:      str
    side:          str          # "UP" or "DOWN"
    shares:        float
    avg_price:     float
    current_price: float        # updated by stream
    resolved:      bool = False
    outcome:       Optional[str] = None   # "WON" | "LOST"
    orders:        list = field(default_factory=list)

    @property
    def cost_basis(self) -> float:
        return self.shares * self.avg_price

    @property
    def current_value(self) -> float:
        if self.resolved:
            return self.shares if self.outcome == "WON" else 0.0
        return self.shares * self.current_price

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
            "market":        self.slug,
            "question":      self.question,
            "side":          self.side,
            "shares":        round(self.shares, 4),
            "avg_price":     round(self.avg_price, 4),
            "current_price": round(self.current_price, 4),
            "cost_basis":    round(self.cost_basis, 4),
            "current_value": round(self.current_value, 4),
            "pnl":           round(self.pnl, 4),
            "pnl_pct":       round(self.pnl_pct, 2),
            "resolved":      self.resolved,
            "outcome":       self.outcome,
        }


# ── Engine ─────────────────────────────────────────────────────────────

class PaperEngine:
    """
    Paper trading engine attached to a Client.
    Access via client.paper.
    """

    def __init__(self, balance: float = 100.0):
        self._balance:   float = balance
        self._orders:    dict[str, PaperOrder]   = {}
        self._positions: dict[str, PaperPosition] = {}  # keyed by market_id+side
        self._streams    = []

    # ------------------------------------------------------------------
    # Balance
    # ------------------------------------------------------------------

    @property
    def balance(self) -> float:
        """Current USDC paper balance."""
        return self._balance

    def set_balance(self, amount: float):
        """Reset the paper balance."""
        self._balance = float(amount)
        log.info(f"Paper: balance set to ${amount:.2f}")

    # ------------------------------------------------------------------
    # Orders
    # ------------------------------------------------------------------

    def buy(self, market, side: str, amount: float) -> PaperOrder:
        """
        Simulated market buy — fills immediately at current market price.

        Args:
            market: Market object
            side:   "UP" or "DOWN"
            amount: USDC to spend

        Returns:
            PaperOrder (status="filled")

        Example:
            order = client.paper.buy(market, side="UP", amount=10.0)
        """
        side = _validate_side(side)
        amount = float(amount)
        _check_positive(amount, "amount")

        price = market.yes_price if side == "UP" else market.no_price
        if price <= 0:
            price = 0.5  # fallback if price not loaded yet

        return self._fill(market, side, price, amount, is_limit=False)

    def limit(self, market, side: str, price: float, amount: float) -> PaperOrder:
        """
        Simulated limit order — queued until stream price crosses threshold.
        Requires attach_stream() to have been called, otherwise call
        check_limits(current_price) manually.

        Args:
            market: Market object
            side:   "UP" or "DOWN"
            price:  trigger price (fills when market price >= this for UP,
                    or <= this for DOWN... actually both sides fill when the
                    token price >= limit price since each token is independent)
            amount: USDC to spend

        Returns:
            PaperOrder (status="open")

        Example:
            order = client.paper.limit(market, side="UP", price=0.92, amount=25.0)
        """
        side   = _validate_side(side)
        price  = float(price)
        amount = float(amount)
        _check_positive(price,  "price")
        _check_positive(amount, "amount")

        from .errors import InsufficientBalance
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
        # Reserve balance
        self._balance -= amount
        log.info(f"Paper: limit order {order_id[:8]} {side} @ {price:.3f} ${amount:.2f} — balance ${self._balance:.2f}")
        return order

    def cancel(self, order_id: str) -> PaperOrder:
        """
        Cancel an open limit order and refund the reserved balance.

        Example:
            client.paper.cancel(order.id)
        """
        from .errors import OrderNotFound
        order = self._orders.get(order_id)
        if not order:
            raise OrderNotFound(f"No order with id: {order_id}")
        if order.status != "open":
            raise ValueError(f"Order {order_id[:8]} is already {order.status}")

        order.status  = "cancelled"
        self._balance += order.amount   # refund reserved amount
        log.info(f"Paper: cancelled order {order_id[:8]}, refunded ${order.amount:.2f}")
        return order

    def cancel_all(self) -> list[PaperOrder]:
        """Cancel all open limit orders."""
        cancelled = []
        for order in list(self._orders.values()):
            if order.status == "open":
                cancelled.append(self.cancel(order.id))
        return cancelled

    def open(self) -> list[PaperOrder]:
        """Return all open limit orders."""
        return [o for o in self._orders.values() if o.status == "open"]

    def orders(self) -> list[PaperOrder]:
        """Return all orders (open, filled, cancelled)."""
        return list(self._orders.values())

    # ------------------------------------------------------------------
    # Positions
    # ------------------------------------------------------------------

    def positions(self) -> list[PaperPosition]:
        """Return all open (unresolved) positions."""
        return [p for p in self._positions.values() if not p.resolved]

    def all_positions(self) -> list[PaperPosition]:
        """Return all positions including resolved ones."""
        return list(self._positions.values())

    def resolve(self, market, outcome: str):
        """
        Manually resolve positions for a market.
        Normally called automatically when stream emits 'close'.

        Args:
            market:  Market object
            outcome: "UP" or "DOWN" (the winning side)

        Example:
            client.paper.resolve(market, outcome="UP")
        """
        outcome = _validate_side(outcome)
        resolved_count = 0

        for key, pos in self._positions.items():
            if pos.market_id == market.id and not pos.resolved:
                pos.resolved = True
                pos.outcome  = "WON" if pos.side == outcome else "LOST"
                if pos.outcome == "WON":
                    self._balance += pos.shares  # $1 per winning share
                resolved_count += 1
                log.info(
                    f"Paper: resolved {pos.side} → {pos.outcome}  "
                    f"pnl={pos.pnl:+.2f}"
                )

        if resolved_count == 0:
            log.debug(f"Paper: no open positions to resolve for {market.slug}")

    # ------------------------------------------------------------------
    # Price updates (called by stream integration)
    # ------------------------------------------------------------------

    def update_price(self, market_id: str, up_price: float, down_price: float):
        """
        Update current prices on open positions and check pending limits.
        Called automatically when a stream is attached.
        """
        for key, pos in self._positions.items():
            if pos.market_id == market_id and not pos.resolved:
                pos.current_price = up_price if pos.side == "UP" else down_price

        # Check pending limit orders for this market
        for order in list(self._orders.values()):
            if order.status != "open" or order.market_id != market_id:
                continue
            current = up_price if order.side == "UP" else down_price
            if current >= order.price:
                self._fill_limit(order, current)

    def attach_stream(self, stream, market):
        """
        Wire a Stream so positions auto-update and limits auto-fill.

        Example:
            stream = client.stream(market)
            client.paper.attach_stream(stream, market)
            stream.start(background=True)
        """
        @stream.on("price")
        def _on_price(up: float, down: float):
            self.update_price(market.id, up, down)

        @stream.on("close")
        def _on_close():
            # Try to resolve — outcome unknown from WS alone,
            # caller should call client.paper.resolve(market, outcome)
            log.info(f"Paper: stream closed for {market.slug} — call paper.resolve() with outcome")

        self._streams.append(stream)
        log.info(f"Paper: attached stream for {market.slug}")

    # ------------------------------------------------------------------
    # Reporting
    # ------------------------------------------------------------------

    def summary(self):
        """Print a P&L summary table."""
        positions = self.all_positions()
        orders    = self.orders()

        filled   = [o for o in orders if o.status == "filled"]
        open_pos = [p for p in positions if not p.resolved]
        resolved = [p for p in positions if p.resolved]

        total_in  = sum(o.amount for o in filled)
        total_fee = sum(o.fee    for o in filled)
        wins      = [p for p in resolved if p.outcome == "WON"]
        losses    = [p for p in resolved if p.outcome == "LOST"]
        net_pnl   = sum(p.pnl for p in resolved)
        unrealised= sum(p.pnl for p in open_pos)

        W = 64
        print("=" * W)
        print("POLYALPHA PAPER TRADING SUMMARY")
        print("=" * W)
        print(f"{'Balance':<20} ${self._balance:>10.2f}")
        print(f"{'Total invested':<20} ${total_in:>10.2f}")
        print(f"{'Total fees paid':<20} ${total_fee:>10.2f}")
        print(f"{'Unrealised P&L':<20} ${unrealised:>+10.2f}")
        print(f"{'Realised P&L':<20} ${net_pnl:>+10.2f}")
        print()

        if resolved:
            win_rate = len(wins) / len(resolved) * 100
            print(f"{'Resolved trades':<20} {len(resolved)}")
            print(f"{'Win rate':<20} {win_rate:.0f}%  ({len(wins)}W / {len(losses)}L)")
            print()
            print(f"  {'MARKET':<35} {'SIDE':<5} {'RESULT':<6} {'P&L':>8}")
            print(f"  {'-'*35} {'-'*5} {'-'*6} {'-'*8}")
            for p in resolved:
                label = m_label(p.slug)
                result = "WON" if p.outcome == "WON" else "LOST"
                print(f"  {label:<35} {p.side:<5} {result:<6} ${p.pnl:>+7.2f}")

        if open_pos:
            print()
            print(f"  Open positions ({len(open_pos)})")
            for p in open_pos:
                print(f"  {m_label(p.slug):<35} {p.side:<5} @ {p.avg_price:.3f}  now={p.current_price:.3f}  pnl=${p.pnl:>+.2f}")

        if not resolved and not open_pos:
            print("  No trades yet.")

        print("=" * W)

    # ------------------------------------------------------------------
    # Internal
    # ------------------------------------------------------------------

    def _fill(self, market, side: str, price: float, amount: float, is_limit: bool) -> PaperOrder:
        """Execute a simulated fill."""
        from .errors import InsufficientBalance

        if amount > self._balance:
            raise InsufficientBalance(
                f"Order amount ${amount:.2f} exceeds balance ${self._balance:.2f}"
            )

        fee    = round(amount * TAKER_FEE, 6)
        net    = amount - fee
        shares = round(net / price, 6) if price > 0 else 0.0

        self._balance -= amount

        order_id = _new_id()
        order = PaperOrder(
            id        = order_id,
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
        self._orders[order_id] = order

        # Update or create position
        pos_key = f"{market.id}:{side}"
        if pos_key in self._positions:
            pos = self._positions[pos_key]
            total_shares = pos.shares + shares
            pos.avg_price = round(
                (pos.shares * pos.avg_price + shares * price) / total_shares, 6
            )
            pos.shares = total_shares
            pos.orders.append(order_id)
        else:
            self._positions[pos_key] = PaperPosition(
                market_id     = market.id,
                slug          = market.slug,
                question      = market.question,
                side          = side,
                shares        = shares,
                avg_price     = price,
                current_price = price,
                orders        = [order_id],
            )

        log.info(
            f"Paper: filled {side} {shares:.4f} shares @ {price:.3f}  "
            f"fee=${fee:.4f}  balance=${self._balance:.2f}"
        )
        return order

    def _fill_limit(self, order: PaperOrder, current_price: float):
        """Fill a pending limit order at current_price."""
        # Balance was already reserved at limit() time
        fee    = round(order.amount * TAKER_FEE, 6)
        net    = order.amount - fee
        shares = round(net / current_price, 6) if current_price > 0 else 0.0

        order.price     = current_price
        order.shares    = shares
        order.fee       = fee
        order.status    = "filled"
        order.filled_at = _now()

        # Find the market from any existing position or use stub
        pos_key = None
        for key, pos in self._positions.items():
            if pos.market_id == order.market_id and pos.side == order.side:
                pos_key = key
                break

        if pos_key:
            pos = self._positions[pos_key]
            total = pos.shares + shares
            pos.avg_price = round(
                (pos.shares * pos.avg_price + shares * current_price) / total, 6
            )
            pos.shares = total
            pos.orders.append(order.id)
        else:
            self._positions[f"{order.market_id}:{order.side}"] = PaperPosition(
                market_id     = order.market_id,
                slug          = order.slug,
                question      = "",
                side          = order.side,
                shares        = shares,
                avg_price     = current_price,
                current_price = current_price,
                orders        = [order.id],
            )

        log.info(
            f"Paper: limit filled {order.side} {shares:.4f} shares @ {current_price:.3f}  "
            f"fee=${fee:.4f}"
        )


# ── Helpers ────────────────────────────────────────────────────────────

def _validate_side(side: str) -> str:
    s = side.upper()
    if s not in ("UP", "DOWN"):
        raise ValueError(f"side must be 'UP' or 'DOWN', got '{side}'")
    return s

def _check_positive(val: float, name: str):
    if val <= 0:
        raise ValueError(f"{name} must be > 0, got {val}")

def _new_id() -> str:
    return str(uuid.uuid4())

def _now() -> datetime:
    return datetime.now(timezone.utc)

def m_label(slug: str) -> str:
    """Shorten slug for display: btc-updown-5m-1234 → BTC 5m"""
    parts = slug.split("-")
    try:
        asset = parts[0].upper()
        tf    = parts[2]
        return f"{asset} {tf}"
    except IndexError:
        return slug[:20]