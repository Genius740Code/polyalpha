"""
P&L Tracker — performance monitoring and reporting utility.

The Tracker provides comprehensive P&L tracking, statistics, and
reporting for trading activities. It can be used standalone or
integrated with bots like Sniper.

Features:
- Real-time P&L tracking
- Win rate and performance statistics
- Detailed trade history
- Export capabilities (JSON, CSV)
- Formatted summary tables

Usage
-----
    from polyalpha.bots import Tracker

    tracker = Tracker(client)
    tracker.summary()
    tracker.export_json("trades.json")
"""

from __future__ import annotations

import csv
import json
import logging
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Optional

log = logging.getLogger(__name__)


# ── Trade Record ─────────────────────────────────────────────────────────────

@dataclass
class TradeRecord:
    """Record of a single trade."""
    market_slug: str
    side: str
    entry_price: float
    exit_price: Optional[float]
    amount: float
    shares: float
    fee: float
    outcome: Optional[str]  # "WON" | "LOST" | None
    pnl: float
    timestamp: datetime

    def to_dict(self) -> dict:
        """Convert to dictionary for serialization."""
        return {
            "market_slug": self.market_slug,
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


# ── Tracker ───────────────────────────────────────────────────────────────────

class Tracker:
    """
    P&L tracking and reporting utility.

    The Tracker aggregates trading data from the paper engine and
    provides comprehensive statistics and reporting.

    Parameters
    ----------
    client : polyalpha.Client
        The polyalpha client instance.

    Example
    -------
    >>> tracker = Tracker(client)
    >>> tracker.summary()
    >>> tracker.export_json("trades.json")
    """

    def __init__(self, client):
        """Initialize the Tracker."""
        self.client = client
        self._trades: list[TradeRecord] = []
        self._log = logging.getLogger(__name__)

    # ── Data Collection ─────────────────────────────────────────────────────────

    def sync(self) -> None:
        """
        Sync tracker with current paper engine state.

        This method pulls all completed trades from the paper engine
        and updates the tracker's internal state.
        """
        all_positions = self.client.paper.all_positions()
        all_orders = self.client.paper.orders()

        # Build order lookup
        orders_by_id = {o.id: o for o in all_orders}

        # Process resolved positions
        for pos in all_positions:
            if not pos.resolved:
                continue

            # Skip if already tracked
            if any(t.market_slug == pos.slug and t.side == pos.side
                   for t in self._trades):
                continue

            # Find associated orders
            total_amount = 0.0
            total_fee = 0.0
            entry_price = 0.0

            for order_id in pos.order_ids:
                order = orders_by_id.get(order_id)
                if order:
                    total_amount += order.amount
                    total_fee += order.fee
                    if order.status == "filled":
                        entry_price = order.price

            # Create trade record
            trade = TradeRecord(
                market_slug=pos.slug,
                side=pos.side,
                entry_price=entry_price,
                exit_price=None,
                amount=total_amount,
                shares=pos.shares,
                fee=total_fee,
                outcome=pos.outcome,
                pnl=pos.pnl,
                timestamp=datetime.now(timezone.utc),
            )

            self._trades.append(trade)

        self._log.info("Synced: %d trades tracked", len(self._trades))

    # ── Statistics ───────────────────────────────────────────────────────────

    @property
    def total_trades(self) -> int:
        """Total number of tracked trades."""
        return len(self._trades)

    @property
    def wins(self) -> int:
        """Number of winning trades."""
        return sum(1 for t in self._trades if t.outcome == "WON")

    @property
    def losses(self) -> int:
        """Number of losing trades."""
        return sum(1 for t in self._trades if t.outcome == "LOST")

    @property
    def win_rate(self) -> float:
        """Win rate as percentage (0-100)."""
        if self.total_trades == 0:
            return 0.0
        return (self.wins / self.total_trades) * 100

    @property
    def total_pnl(self) -> float:
        """Total P&L across all trades."""
        return sum(t.pnl for t in self._trades)

    @property
    def total_fees(self) -> float:
        """Total fees paid across all trades."""
        return sum(t.fee for t in self._trades)

    @property
    def avg_entry_price(self) -> float:
        """Average	entry price across all trades."""
        if not self._trades:
            return 0.0
        return sum(t.entry_price for t in self._trades) / len(self._trades)

    @property
    def avg_pnl_per_trade(self) -> float:
        """Average P&L per trade."""
        if self.total_trades == 0:
            return 0.0
        return self.total_pnl / self.total_trades

    # ── Reporting ─────────────────────────────────────────────────────────────

    def summary(self) -> None:
        """Print a formatted P&L summary to stdout."""
        self.sync()

        W = 70
        div = "─" * W

        print(div)
        print("  POLYALPHA — P&L TRACKER SUMMARY")
        print(div)
        print(f"  {'Total trades':<25} {self.total_trades:>10}")
        print(f"  {'Wins':<25} {self.wins:>10}")
        print(f"  {'Losses':<25} {self.losses:>10}")
        print(f"  {'Win rate':<25} {self.win_rate:>9.1f}%")
        print(div)
        print(f"  {'Total P&L':<25} ${self.total_pnl:>+10.2f}")
        print(f"  {'Avg P&L per trade':<25} ${self.avg_pnl_per_trade:>+10.2f}")
        print(f"  {'Total fees':<25} ${self.total_fees:>10.2f}")
        print(f"  {'Avg entry price':<25} {self.avg_entry_price:>10.4f}")
        print(div)

        if self._trades:
            print(f"\n  {'MARKET':<30} {'SIDE':<5} {'RESULT':<6} {'P&L':>9}")
            print(f"  {'─'*30} {'─'*5} {'─'*6} {'─'*9}")
            for trade in self._trades:
                label = self._slug_label(trade.market_slug)
                result = trade.outcome if trade.outcome else "PENDING"
                print(f"  {label:<30} {trade.side:<5} {result:<6} ${trade.pnl:>+8.2f}")
        else:
            print("\n  No trades tracked yet.")

        print(div)

    def trades(self) -> list[TradeRecord]:
        """Return all tracked trades."""
        return self._trades.copy()

    # ── Export ───────────────────────────────────────────────────────────────

    def export_json(self, filepath: str) -> None:
        """
        Export trades to JSON file.

        Parameters
        ----------
        filepath : str
            Path to output JSON file.
        """
        self.sync()
        data = {
            "summary": {
                "total_trades": self.total_trades,
                "wins": self.wins,
                "losses": self.losses,
                "win_rate": self.win_rate,
                "total_pnl": self.total_pnl,
                "total_fees": self.total_fees,
                "avg_entry_price": self.avg_entry_price,
                "avg_pnl_per_trade": self.avg_pnl_per_trade,
            },
            "trades": [t.to_dict() for t in self._trades],
        }

        with open(filepath, "w") as f:
            json.dump(data, f, indent=2)

        self._log.info("Exported %d trades to %s", len(self._trades), filepath)

    def export_csv(self, filepath: str) -> None:
        """
        Export trades to CSV file.

        Parameters
        ----------
        filepath : str
            Path to output CSV file.
        """
        self.sync()

        if not self._trades:
            self._log.warning("No trades to export")
            return

        with open(filepath, "w", newline="") as f:
            writer = csv.writer(f)
            writer.writerow([
                "market_slug", "side", "entry_price", "exit_price",
                "amount", "shares", "fee", "outcome", "pnl", "timestamp"
            ])

            for trade in self._trades:
                writer.writerow([
                    trade.market_slug,
                    trade.side,
                    trade.entry_price,
                    trade.exit_price,
                    trade.amount,
                    trade.shares,
                    trade.fee,
                    trade.outcome,
                    trade.pnl,
                    trade.timestamp.isoformat(),
                ])

        self._log.info("Exported %d trades to %s", len(self._trades), filepath)

    # ── Helpers ─────────────────────────────────────────────────────────────

    def _slug_label(self, slug: str) -> str:
        """Shorten a slug for display."""
        parts = slug.split("-")
        try:
            return f"{parts[0].upper()} {parts[2]}"
        except IndexError:
            return slug[:20]
