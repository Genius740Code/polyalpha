"""Reporting and display functions for paper trading."""

from __future__ import annotations

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from .paper_engine import PaperEngine

from ..core import SUMMARY_DIV_WIDTH


def print_summary(engine: PaperEngine) -> None:
    """Print a formatted P&L summary to stdout."""
    all_orders = engine.orders()
    all_positions = engine.all_positions()

    filled = [o for o in all_orders if o.status == "filled"]
    open_pos = [p for p in all_positions if not p.resolved]
    resolved = [p for p in all_positions if p.resolved]

    total_invested = sum(o.amount for o in filled)
    total_fees = sum(o.fee for o in filled)
    total_rebates = sum(o.rebate_amount for o in filled)
    wins = [p for p in resolved if p.outcome == "WON"]
    losses = [p for p in resolved if p.outcome == "LOST"]
    realised_pnl = sum(p.pnl for p in resolved)
    unrealised_pnl = sum(p.pnl for p in open_pos)

    div = "─" * SUMMARY_DIV_WIDTH
    print(div)
    print("  POLYALPHA — PAPER TRADING SUMMARY")
    print(div)
    current_balance = engine.balance
    print(f"  {'Balance':<22} ${current_balance:>10.2f}")
    print(f"  {'Total invested':<22} ${total_invested:>10.2f}")
    print(f"  {'Total fees paid':<22} ${total_fees:>10.4f}")
    print(f"  {'Total rebates earned':<22} ${total_rebates:>10.4f}")
    print(f"  {'Net fees (after rebates)':<22} ${total_fees - total_rebates:>10.4f}")
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
        from .paper_types import slug_label
        for p in resolved:
            label = slug_label(p.slug)
            result = "WON" if p.outcome == "WON" else "LOST"
            print(f"  {label:<30} {p.side:<5} {result:<6} ${p.pnl:>+8.2f}")

    if open_pos:
        print(div)
        print(f"  Open positions ({len(open_pos)})\n")
        print(f"  {'MARKET':<30} {'SIDE':<5} {'AVG':>6} {'NOW':>6} {'P&L':>9}")
        print(f"  {'─'*30} {'─'*5} {'─'*6} {'─'*6} {'─'*9}")
        from .paper_types import slug_label
        for p in open_pos:
            label = slug_label(p.slug)
            print(
                f"  {label:<30} {p.side:<5} "
                f"{p.avg_price:>6.3f} {p.current_price:>6.3f} ${p.pnl:>+8.2f}"
            )

    if not resolved and not open_pos:
        print(f"\n  No trades yet.")

    print(div)


def print_fee_summary(engine: PaperEngine) -> None:
    """Print a detailed fee and rebate summary."""
    fm = engine._fee_manager
    div = "─" * SUMMARY_DIV_WIDTH
    print(div)
    print("  POLYALPHA — FEE & REBATE SUMMARY")
    print(div)
    print(f"  {'Total volume':<22} ${fm.total_volume:>10.2f}")
    print(f"  {'Total fees paid':<22} ${fm.total_fees_paid:>10.4f}")
    print(f"  {'Total rebates earned':<22} ${fm.total_rebates_earned:>10.4f}")
    print(f"  {'Net fees (after rebates)':<22} ${fm.total_fees_paid - fm.total_rebates_earned:>10.4f}")
    print(f"  {'Effective fee rate':<22} {(fm.total_fees_paid - fm.total_rebates_earned) / fm.total_volume * 100 if fm.total_volume > 0 else 0:.2f}%")
    print(div)
    print(f"  {'Taker fees':<22} ${fm.taker_fees:>10.4f}")
    print(f"  {'Taker rebates':<22} ${fm.taker_rebates:>10.4f}")
    print(f"  {'Maker fees':<22} ${fm.maker_fees:>10.4f}")
    print(f"  {'Maker rebates':<22} ${fm.maker_rebates:>10.4f}")
    print(div)

    current_rate = fm._get_volume_rebate_rate()
    print(f"  Current volume rebate tier: {current_rate * 100:.1f}%")
    if fm.config.rebate_tiers:
        print(f"  Volume thresholds:")
        thresholds = sorted(fm.config.rebate_tiers.items())
        for threshold, rate in thresholds:
            marker = " ← current" if rate == current_rate else ""
            print(f"    ${threshold:>8.0f}+: {rate * 100:>5.1f}%{marker}")
    print(div)


def get_rebate_stats(engine: PaperEngine) -> dict:
    """Get rebate statistics as a dictionary."""
    fm = engine._fee_manager
    return {
        "total_volume": fm.total_volume,
        "total_fees_paid": fm.total_fees_paid,
        "total_rebates_earned": fm.total_rebates_earned,
        "net_fees": fm.total_fees_paid - fm.total_rebates_earned,
        "effective_fee_rate": (fm.total_fees_paid - fm.total_rebates_earned) / fm.total_volume if fm.total_volume > 0 else 0,
        "taker_fees": fm.taker_fees,
        "taker_rebates": fm.taker_rebates,
        "maker_fees": fm.maker_fees,
        "maker_rebates": fm.maker_rebates,
        "current_rebate_rate": fm._get_volume_rebate_rate(),
    }


def get_position_history(engine: PaperEngine) -> dict:
    """Get position history summary statistics."""
    all_pos = engine.all_positions()
    open_pos = [p for p in all_pos if not p.resolved]
    closed_pos = [p for p in all_pos if p.resolved]

    wins = [p for p in closed_pos if p.outcome == "WON"]
    losses = [p for p in closed_pos if p.outcome == "LOST"]

    all_orders_map = {o.id: o for o in engine._get_all_orders_across_wallets()}
    holding_times = []
    for pos in closed_pos:
        if pos.order_ids:
            fill_times = [
                all_orders_map[oid].filled_at
                for oid in pos.order_ids
                if oid in all_orders_map and all_orders_map[oid].filled_at
            ]
            if fill_times:
                holding_time = (max(fill_times) - min(fill_times)).total_seconds()
                holding_times.append(holding_time)

    avg_holding = sum(holding_times) / len(holding_times) if holding_times else 0.0

    best_pos = max(closed_pos, key=lambda p: p.pnl) if closed_pos else None
    worst_pos = min(closed_pos, key=lambda p: p.pnl) if closed_pos else None

    return {
        "total_positions": len(all_pos),
        "total_closed": len(closed_pos),
        "total_open": len(open_pos),
        "wins": len(wins),
        "losses": len(losses),
        "win_rate": (len(wins) / len(closed_pos) * 100) if closed_pos else 0.0,
        "avg_holding_time": avg_holding,
        "best_position": {
            "market": best_pos.slug if best_pos else None,
            "pnl": best_pos.pnl if best_pos else 0.0,
            "pnl_pct": best_pos.pnl_pct if best_pos else 0.0,
        } if best_pos else None,
        "worst_position": {
            "market": worst_pos.slug if worst_pos else None,
            "pnl": worst_pos.pnl if worst_pos else 0.0,
            "pnl_pct": worst_pos.pnl_pct if worst_pos else 0.0,
        } if worst_pos else None,
    }


def show_positions(engine: PaperEngine, show_all: bool = False, verbose: bool = True) -> None:
    """Display positions with entry/exit information and ROI."""
    from ..report.terminal import render_positions

    positions = engine.all_positions() if show_all else engine.positions()
    all_orders = engine._get_all_orders_across_wallets()
    orders_dict = {o.id: o for o in all_orders}
    render_positions(positions, orders_dict, show_all=show_all, verbose=verbose)
