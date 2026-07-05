"""
examples/report.py — Demonstrates the polyalpha paper trading analytics dashboard.

Generates 60 synthetic trades (no live Polymarket connection needed) then
renders the full HTML report and prints a terminal summary.

Run:
    python examples/report.py
    python examples/report.py --preset full
    python examples/report.py --no-browser --out my_report.html
"""

from __future__ import annotations

import argparse
import math
import random
import sys
import uuid
from datetime import datetime, timedelta, timezone
from pathlib import Path

# Resolve src layout
sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

import polyalpha
from polyalpha.trading.paper import PaperEngine, PaperOrder, PaperPosition


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _build_synthetic_engine(n_trades: int = 60, seed: int = 42) -> PaperEngine:
    """
    Build a PaperEngine with synthetic resolved trades (no live connection).

    Strategy: random binary outcome, entry prices drawn from U(0.50, 0.95),
    win probability ≈ entry_price (well-calibrated), holding times 1–300 min.
    """
    rng = random.Random(seed)
    engine = PaperEngine(balance=1000.0)

    base_time = datetime(2025, 1, 1, 0, 0, 0, tzinfo=timezone.utc)
    t = base_time

    assets = ["BTC", "ETH", "SOL", "XRP", "DOGE"]
    timeframes = ["5m", "15m", "1h"]

    for i in range(n_trades):
        # Pick a fake market
        asset     = rng.choice(assets)
        timeframe = rng.choice(timeframes)
        market_id = f"mkt_{uuid.uuid4().hex[:8]}"
        slug      = f"{asset.lower()}-updown-{timeframe}-{i:04d}"
        question  = f"Will {asset} be higher in {timeframe}?"
        side      = rng.choice(["UP", "DOWN"])

        entry_price = round(rng.uniform(0.50, 0.95), 4)
        amount_in   = round(rng.uniform(5.0, 50.0), 2)
        fee_rate    = 0.02
        fee         = round(amount_in * fee_rate, 6)
        shares      = round((amount_in - fee) / entry_price, 6)

        holding_min  = rng.randint(1, 300)
        entry_time   = t + timedelta(minutes=rng.randint(0, 5))
        exit_time    = entry_time + timedelta(minutes=holding_min)
        t            = exit_time + timedelta(minutes=rng.randint(1, 30))

        # Win probability calibrated to entry price
        win = rng.random() < entry_price
        outcome = "WON" if win else "LOST"

        # Build fake order
        order_id = str(uuid.uuid4())
        order = PaperOrder(
            id        = order_id,
            market_id = market_id,
            slug      = slug,
            side      = side,
            price     = entry_price,
            amount    = amount_in,
            shares    = shares,
            fee       = fee,
            status    = "filled",
            is_limit  = rng.random() > 0.6,
            filled_at = entry_time,
        )
        engine._orders[order_id] = order

        # Build fake position (resolved)
        exit_price = 1.0 if win else 0.0
        proceeds   = shares if win else 0.0
        cost_basis = shares * entry_price
        pnl        = proceeds - cost_basis

        # Adjust balance
        engine._balance += pnl

        pos = PaperPosition(
            market_id     = market_id,
            slug          = slug,
            question      = question,
            side          = side,
            shares        = shares,
            avg_price     = entry_price,
            current_price = exit_price,
            resolved      = True,
            outcome       = outcome,
            order_ids     = [order_id],
        )
        # Stamp exit time via a second order for holding time calculation
        exit_order_id = str(uuid.uuid4())
        exit_order = PaperOrder(
            id        = exit_order_id,
            market_id = market_id,
            slug      = slug,
            side      = side,
            price     = exit_price,
            amount    = proceeds,
            shares    = shares,
            fee       = 0.0,
            status    = "filled",
            is_limit  = False,
            filled_at = exit_time,
        )
        engine._orders[exit_order_id] = exit_order
        pos.order_ids.append(exit_order_id)

        key = f"{market_id}:{side}"
        engine._positions[key] = pos

    print(f"  Synthetic engine: {n_trades} trades, balance=${engine._balance:.2f}")
    return engine


def main() -> None:
    parser = argparse.ArgumentParser(description="polyalpha paper trading analytics demo")
    parser.add_argument("--preset",     default="default", help="Preset name (default/full/quick)")
    parser.add_argument("--n-trades",   type=int, default=60,  help="Number of synthetic trades")
    parser.add_argument("--no-browser", action="store_true",    help="Don't open browser")
    parser.add_argument("--out",        default=None,          help="Output HTML file path")
    args = parser.parse_args()

    print("\n=== polyalpha — Analytics Demo ===\n")
    engine = _build_synthetic_engine(n_trades=args.n_trades)

    report = engine.report

    # ── Terminal summary ──────────────────────────────────────────────────────
    print("\n--- Terminal Summary ---\n")
    report.show(preset=args.preset, show_trades=True)

    # ── HTML dashboard ────────────────────────────────────────────────────────
    open_browser = not args.no_browser
    out_path = args.out

    print("\n--- Generating HTML dashboard ---")
    try:
        path = report.html(
            preset       = args.preset,
            path         = out_path,
            open_browser = open_browser,
        )
        print(f"  Report saved: {path}")
        if open_browser:
            print("  Browser opened.")
    except ImportError as e:
        print(f"  [SKIP] HTML dashboard requires plotly: {e}")
        print("  Install with: pip install polyalpha[report]")

    # ── Preset demo ───────────────────────────────────────────────────────────
    print("\n--- Preset demo ---")
    saved = report.save_preset(
        name        = "demo_scalp",
        metrics     = ["net_pnl", "win_rate", "total_trades", "sharpe", "max_drawdown", "kelly"],
        charts      = ["equity_curve", "pnl_per_trade"],
        description = "Demo scalp preset created by examples/report.py",
    )
    print(f"  Saved preset: {saved.name}")
    print(f"  Available presets: {report.list_presets()}")

    # Clean up
    report.delete_preset("demo_scalp")
    print("  Deleted demo preset.")

    print("\nDone.\n")


if __name__ == "__main__":
    main()
