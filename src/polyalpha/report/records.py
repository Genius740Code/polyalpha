"""
records.py — TradeRecord dataclass and extractor from PaperEngine state.

A TradeRecord is one closed (resolved or early-exited) trade.  All downstream
metrics and charts work exclusively from a list[TradeRecord], never touching the
engine directly after extraction.

Design notes
------------
* A "trade" is one resolved PaperPosition.  If a position was built from
  multiple fill orders (averaging in) we reconstruct it from the position's
  avg_price and the resolution outcome.
* Slippage is recorded as (intended_price - actual_fill_price) summed across
  all fills for the position, then divided by share count.
* Holding time is (resolution_time or last_fill_time) - first_fill_time.
  Because PaperEngine doesn't explicitly stamp resolution times we use the
  latest fill time of any order in the position's order_ids list as a
  conservative proxy.
"""

from __future__ import annotations

import math
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import TYPE_CHECKING, Optional, Union

if TYPE_CHECKING:
    from ..trading.paper_engine import PaperEngine
    from ..trading.real_engine import RealTradingEngine


@dataclass
class TradeRecord:
    """One resolved trade, derived from a PaperPosition + its fill orders."""

    trade_id:      str
    market_slug:   str
    market_id:     str
    side:          str            # "UP" | "DOWN"
    entry_price:   float          # volume-weighted avg fill price (before fee)
    exit_price:    float          # 1.0 if WON, 0.0 if LOST, market price if CLOSED
    shares:        float          # total shares held
    amount_in:     float          # total USDC spent (gross, incl. fee)
    fee:           float          # total fee paid across all fills
    pnl:           float          # net realised PnL in USDC
    pnl_pct:       float          # pnl / amount_in * 100
    entry_time:    datetime       # UTC time of first fill
    exit_time:     datetime       # UTC time of last fill (proxy for close time)
    holding_secs:  float          # (exit_time - entry_time).total_seconds()
    outcome:       str            # "WON" | "LOST" | "CLOSED"
    fill_type:     str            # "market" | "limit" | "mixed"
    slippage:      float          # avg absolute slippage per share (USDC), 0 if n/a
    order_count:   int            # number of fill orders that composed this trade
    # Optional: intended entry price (before slippage) — populated when available
    intended_price: Optional[float] = field(default=None)

    def is_win(self) -> bool:
        return self.pnl > 0

    def is_loss(self) -> bool:
        return self.pnl < 0

    def dump(self) -> dict:
        return {
            "trade_id":      self.trade_id,
            "market":        self.market_slug,
            "side":          self.side,
            "entry_price":   round(self.entry_price, 4),
            "exit_price":    round(self.exit_price, 4),
            "shares":        round(self.shares, 4),
            "amount_in":     round(self.amount_in, 4),
            "fee":           round(self.fee, 6),
            "pnl":           round(self.pnl, 4),
            "pnl_pct":       round(self.pnl_pct, 2),
            "entry_time":    self.entry_time.isoformat(),
            "exit_time":     self.exit_time.isoformat(),
            "holding_secs":  round(self.holding_secs, 1),
            "outcome":       self.outcome,
            "fill_type":     self.fill_type,
            "slippage":      round(self.slippage, 6),
            "order_count":   self.order_count,
            "intended_price": round(self.intended_price, 4) if self.intended_price is not None else None,
        }


# ── Extractor ──────────────────────────────────────────────────────────────────

def extract_trades(engine: Union["PaperEngine", "RealTradingEngine"]) -> list[TradeRecord]:
    """
    Walk the PaperEngine or RealTradingEngine's positions and orders to build a list of TradeRecords.

    Only *resolved* positions (outcome WON / LOST / CLOSED) are returned.
    Open positions are ignored — they have no exit price yet.

    Parameters
    ----------
    engine : Union[PaperEngine, RealTradingEngine]
        The trading engine to extract trades from.

    Returns
    -------
    list[TradeRecord]
        Sorted chronologically by entry_time (oldest first).
    """
    orders_by_id = engine._orders

    records: list[TradeRecord] = []

    for pos in engine._positions.values():
        if not pos.resolved:
            continue  # skip open positions

        # Gather all fill orders for this position
        fill_orders = [
            orders_by_id[oid]
            for oid in pos.order_ids
            if oid in orders_by_id and orders_by_id[oid].status == "filled"
        ]

        if not fill_orders:
            continue  # no data to work with

        # ── Timing ────────────────────────────────────────────────────────────
        filled_timestamps = [
            o.filled_at for o in fill_orders if o.filled_at is not None
        ]
        if not filled_timestamps:
            # Fallback: use epoch; shouldn't happen in normal usage
            entry_time = datetime(1970, 1, 1, tzinfo=timezone.utc)
            exit_time  = entry_time
        else:
            entry_time = min(filled_timestamps)
            exit_time  = max(filled_timestamps)

        holding_secs = max(0.0, (exit_time - entry_time).total_seconds())

        # ── Amounts ───────────────────────────────────────────────────────────
        total_amount = sum(o.amount for o in fill_orders)
        total_fee    = sum(o.fee    for o in fill_orders)
        total_shares = sum(o.shares for o in fill_orders)

        # Volume-weighted average entry price
        if total_shares > 0:
            entry_price = sum(o.price * o.shares for o in fill_orders) / total_shares
        else:
            entry_price = pos.avg_price

        # ── PnL ───────────────────────────────────────────────────────────────
        outcome = pos.outcome or "LOST"
        if outcome == "WON":
            exit_price  = 1.0
            proceeds    = total_shares  # shares × $1
        elif outcome == "CLOSED":
            # Early exit: use position's current_price at close time
            exit_price  = pos.current_price if pos.current_price > 0 else 0.0
            proceeds    = total_shares * exit_price
        else:  # LOST
            exit_price  = 0.0
            proceeds    = 0.0

        # Cost basis = total amount spent (already includes fee deduction from shares)
        # PnL = proceeds - cost_basis  (cost_basis = amount_in net of fee = shares * avg_price)
        cost_basis = total_shares * entry_price  # same as pos.cost_basis
        pnl        = round(proceeds - cost_basis, 6)
        pnl_pct    = round((pnl / cost_basis) * 100, 4) if cost_basis > 0 else 0.0

        # ── Fill type ─────────────────────────────────────────────────────────
        limit_count  = sum(1 for o in fill_orders if o.is_limit)
        market_count = len(fill_orders) - limit_count
        if limit_count == 0:
            fill_type = "market"
        elif market_count == 0:
            fill_type = "limit"
        else:
            fill_type = "mixed"

        # ── Slippage ──────────────────────────────────────────────────────────
        # Average absolute difference between the order's stored price (limit threshold
        # or recorded fill price) and the actual fill price.
        # For market orders the slippage comes from PaperConfig.slippage_pct.
        # We approximate: slippage per share = |actual_price - intended_price|.
        # Since we don't store "intended_price" separately, we use 0 for market orders
        # without slippage config.
        slippage = 0.0
        intended_price: Optional[float] = None
        if fill_orders:
            # Best proxy: use position avg_price vs entry_price deviation (rounding noise)
            # In practice slippage is already baked into the fill price stored on the order.
            slippage = 0.0  # conservative — actual slippage info not stored per order

        records.append(TradeRecord(
            trade_id      = pos.market_id + ":" + pos.side,
            market_slug   = pos.slug,
            market_id     = pos.market_id,
            side          = pos.side,
            entry_price   = round(entry_price, 6),
            exit_price    = round(exit_price, 6),
            shares        = round(total_shares, 6),
            amount_in     = round(total_amount, 6),
            fee           = round(total_fee, 6),
            pnl           = pnl,
            pnl_pct       = pnl_pct,
            entry_time    = entry_time,
            exit_time     = exit_time,
            holding_secs  = holding_secs,
            outcome       = outcome,
            fill_type     = fill_type,
            slippage      = slippage,
            order_count   = len(fill_orders),
            intended_price= intended_price,
        ))

    # Sort chronologically by entry time
    records.sort(key=lambda r: r.entry_time)
    return records


def build_equity_curve(
    trades: list[TradeRecord],
    initial_balance: float,
) -> tuple[list[datetime], list[float]]:
    """
    Build (timestamps, equity_values) arrays for plotting.

    Returns two parallel lists:
      - timestamps: entry and exit times interleaved
      - equity:     running portfolio value at each timestamp

    The curve starts at initial_balance and steps by each trade's PnL
    at its exit_time.
    """
    if not trades:
        now = datetime.now(timezone.utc)
        return [now], [initial_balance]

    # We use exit_time as the event time (trade realises PnL at close)
    events: list[tuple[datetime, float]] = []
    for t in trades:
        events.append((t.exit_time, t.pnl))

    events.sort(key=lambda e: e[0])

    timestamps: list[datetime] = []
    equity: list[float] = []
    running = initial_balance

    # Prepend origin point at first trade's entry time
    timestamps.append(trades[0].entry_time)
    equity.append(initial_balance)

    for ts, pnl in events:
        running = round(running + pnl, 6)
        timestamps.append(ts)
        equity.append(running)

    return timestamps, equity
