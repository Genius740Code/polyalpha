"""
terminal.py — Rich terminal renderer for the paper trading analytics report.

Renders metric cards and trade tables to stdout using only the stdlib
``textwrap`` and ANSI escape codes — no external dependencies required for
basic output.  If ``rich`` is installed, a much prettier version is shown.
"""

from __future__ import annotations

import math
import textwrap
from datetime import datetime
from typing import Any, Optional

from .records import TradeRecord

# ── ANSI helpers (stdlib fallback) ───────────────────────────────────────────

_RESET  = "\033[0m"
_BOLD   = "\033[1m"
_DIM    = "\033[2m"
_GREEN  = "\033[38;5;43m"
_RED    = "\033[38;5;204m"
_BLUE   = "\033[38;5;111m"
_YELLOW = "\033[38;5;221m"
_GREY   = "\033[38;5;245m"
_CYAN   = "\033[38;5;117m"
_WHITE  = "\033[38;5;255m"


def _color(text: str, code: str) -> str:
    return f"{code}{text}{_RESET}"


def _fmt_float(v: Any, decimals: int = 4, suffix: str = "") -> str:
    if v is None:
        return _color("—", _GREY)
    if isinstance(v, float):
        if math.isnan(v):
            return _color("n/a", _GREY)
        if math.isinf(v):
            return _color("∞", _YELLOW) if v > 0 else _color("-∞", _RED)
        return f"{v:.{decimals}f}{suffix}"
    return str(v)


def _fmt_pnl(v: float) -> str:
    if math.isnan(v) or v is None:
        return _color("n/a", _GREY)
    col = _GREEN if v > 0 else (_RED if v < 0 else _GREY)
    sign = "+" if v > 0 else ""
    return _color(f"{sign}${v:.4f}", col)


def _fmt_pct(v: float) -> str:
    if math.isnan(v) or v is None:
        return _color("n/a", _GREY)
    col = _GREEN if v > 0 else (_RED if v < 0 else _GREY)
    sign = "+" if v > 0 else ""
    return _color(f"{sign}{v:.2f}%", col)


def _divider(width: int = 70, char: str = "─") -> str:
    return _color(char * width, _GREY)


# ── Metric formatters ─────────────────────────────────────────────────────────

_METRIC_LABELS: dict[str, str] = {
    "net_pnl":           "Net PnL",
    "win_rate":          "Win Rate",
    "total_trades":      "Total Trades",
    "sharpe":            "Sharpe Ratio",
    "sortino":           "Sortino Ratio",
    "max_drawdown":      "Max Drawdown",
    "profit_factor":     "Profit Factor",
    "avg_win_loss":      "Avg Win / Avg Loss",
    "expectancy":        "Expectancy (per trade)",
    "median_holding":    "Median Holding Time",
    "best_trade":        "Best Trade",
    "worst_trade":       "Worst Trade",
    "mean_holding":      "Mean Holding Time",
    "calmar":            "Calmar Ratio",
    "omega":             "Omega Ratio",
    "skew":              "Skewness",
    "kurtosis":          "Excess Kurtosis",
    "var_95":            "VaR (95%)",
    "var_99":            "VaR (99%)",
    "cvar_95":           "CVaR (95%)",
    "cvar_99":           "CVaR (99%)",
    "max_consec_wins":   "Max Consecutive Wins",
    "max_consec_losses": "Max Consecutive Losses",
    "kelly":             "Kelly Fraction",
    "rolling_sharpe_30d":"Rolling Sharpe (30d)",
    "rolling_sharpe_90d":"Rolling Sharpe (90d)",
    "fill_rate":         "Fill Rate (limit %)",
    "avg_slippage":      "Avg Slippage",
    "pnl_concentration": "PnL Concentration (top 10)",
    "deflated_sharpe":   "Deflated Sharpe (prob.)",
    "avg_position_size": "Avg Position Size",
    "turnover":          "Turnover (× capital)",
}


def _format_metric_value(key: str, val: Any) -> str:
    """Format a metric value as a human-readable string."""
    if val is None:
        return _color("—", _GREY)

    if key == "net_pnl":
        usd = val.get("usd", float("nan"))
        pct = val.get("pct", float("nan"))
        return f"{_fmt_pnl(usd)}  ({_fmt_pct(pct)})"

    if key == "win_rate":
        return _fmt_pct(val * 100) if not math.isnan(val) else _color("n/a", _GREY)

    if key == "total_trades":
        return _color(str(val), _WHITE)

    if key in ("sharpe", "sortino", "calmar", "omega", "kelly",
               "rolling_sharpe_30d", "rolling_sharpe_90d",
               "skew", "kurtosis"):
        return _fmt_float(val, decimals=4)

    if key == "max_drawdown":
        pct = val.get("pct", float("nan"))
        usd = val.get("usd", float("nan"))
        p = f"{pct:.2f}%" if not math.isnan(pct) else "n/a"
        u = f"${usd:.4f}" if not math.isnan(usd) else "n/a"
        col = _RED if not math.isnan(pct) and pct < 0 else _GREY
        return _color(f"{p}  ({u})", col)

    if key == "profit_factor":
        return _fmt_float(val, decimals=4)

    if key == "avg_win_loss":
        aw = val.get("avg_win",  float("nan"))
        al = val.get("avg_loss", float("nan"))
        return f"{_fmt_pnl(aw)}  /  {_fmt_pnl(al)}"

    if key == "expectancy":
        return _fmt_pct(val * 100)

    if key in ("median_holding", "mean_holding"):
        if math.isnan(val):
            return _color("n/a", _GREY)
        return _color(_format_duration(val), _CYAN)

    if key in ("best_trade", "worst_trade"):
        pnl   = val.get("pnl",    float("nan"))
        pct   = val.get("pct",    float("nan"))
        mkt   = val.get("market", "")
        p     = _fmt_pnl(pnl)
        pp    = _fmt_pct(pct)
        mk    = _color(mkt[:25], _GREY)
        return f"{p}  ({pp})  {mk}"

    if key in ("var_95", "var_99", "cvar_95", "cvar_99"):
        return _fmt_pct(val * 100)

    if key in ("max_consec_wins", "max_consec_losses"):
        return _color(str(val), _WHITE)

    if key == "fill_rate":
        return _fmt_pct(val * 100)

    if key == "avg_slippage":
        return _fmt_float(val, decimals=6, suffix=" USDC/share")

    if key == "pnl_concentration":
        return _fmt_pct(val * 100)

    if key == "deflated_sharpe":
        return _fmt_pct(val * 100)

    if key == "avg_position_size":
        return f"${_fmt_float(val, decimals=2)}"

    if key == "turnover":
        return f"{_fmt_float(val, decimals=2)}×"

    return _fmt_float(val)


def _format_duration(secs: float) -> str:
    """Format seconds into a human-readable duration."""
    if math.isnan(secs) or secs < 0:
        return "n/a"
    secs = int(secs)
    if secs < 60:
        return f"{secs}s"
    if secs < 3600:
        m, s = divmod(secs, 60)
        return f"{m}m {s}s"
    if secs < 86400:
        h, rem = divmod(secs, 3600)
        m = rem // 60
        return f"{h}h {m}m"
    d, rem = divmod(secs, 86400)
    h = rem // 3600
    return f"{d}d {h}h"


def _format_datetime(dt: Optional[datetime]) -> str:
    """Format datetime for display."""
    if dt is None:
        return _color("—", _GREY)
    return dt.strftime("%Y-%m-%d %H:%M:%S")


# ── Position render function ─────────────────────────────────────────────────────

def render_positions(positions: list, orders: dict, show_all: bool = False, verbose: bool = True) -> None:
    """
    Render positions with entry/exit information and ROI.

    Parameters
    ----------
    positions : list
        List of PaperPosition objects to display
    orders : dict
        Dictionary of orders keyed by order ID
    show_all : bool
        Whether to show all positions or just live ones
    verbose : bool
        Whether to show detailed information including entry/exit times
    """
    if not positions:
        print(_color("No positions to display", _GREY))
        return

    W = 90
    print()
    print(_divider(W))
    title = "All Positions" if show_all else "Live Positions"
    print(_color(f"  {title}", _BOLD + _WHITE))
    print(_divider(W))

    # Separate live and closed positions
    live_positions = [p for p in positions if not p.resolved]
    closed_positions = [p for p in positions if p.resolved]

    # Show live positions first
    if live_positions:
        print(_color("  LIVE POSITIONS", _BOLD + _GREEN))
        print()
        
        if verbose:
            header = (
                f"  {'Market':<22} {'Side':<5} {'Entry Time':<19} {'Entry':>6} "
                f"{'Current':>8} {'ROI':>8} {'Shares':>8}"
            )
            print(_color(header, _DIM))
            print(_color("  " + "─" * 78, _GREY))

            for pos in live_positions:
                # Get entry time from orders
                entry_time = None
                if pos.order_ids:
                    fill_times = [
                        orders[oid].filled_at 
                        for oid in pos.order_ids 
                        if oid in orders and orders[oid].filled_at
                    ]
                    if fill_times:
                        entry_time = min(fill_times)

                side_col = _GREEN if pos.side == "UP" else _BLUE
                roi_col = _GREEN if pos.pnl_pct > 0 else (_RED if pos.pnl_pct < 0 else _GREY)
                
                row = (
                    f"  {pos.slug[:20]:<22} "
                    f"{_color(pos.side, side_col):<5} "
                    f"{_format_datetime(entry_time):<19} "
                    f"{pos.avg_price:>6.4f} "
                    f"{pos.current_price:>8.4f} "
                    f"{_color(f'{pos.pnl_pct:+.2f}%', roi_col):>8} "
                    f"{pos.shares:>8.2f}"
                )
                print(row)
        else:
            header = (
                f"  {'Market':<22} {'Side':<5} {'Entry':>6} "
                f"{'Current':>8} {'ROI':>8} {'Status':<8}"
            )
            print(_color(header, _DIM))
            print(_color("  " + "─" * 65, _GREY))

            for pos in live_positions:
                side_col = _GREEN if pos.side == "UP" else _BLUE
                roi_col = _GREEN if pos.pnl_pct > 0 else (_RED if pos.pnl_pct < 0 else _GREY)
                
                row = (
                    f"  {pos.slug[:20]:<22} "
                    f"{_color(pos.side, side_col):<5} "
                    f"{pos.avg_price:>6.4f} "
                    f"{pos.current_price:>8.4f} "
                    f"{_color(f'{pos.pnl_pct:+.2f}%', roi_col):>8} "
                    f"{'OPEN':<8}"
                )
                print(row)
        
        print()

    # Show closed positions if show_all
    if show_all and closed_positions:
        print(_color("  CLOSED POSITIONS", _BOLD + _YELLOW))
        print()
        
        if verbose:
            header = (
                f"  {'Market':<22} {'Side':<5} {'Entry Time':<19} {'Exit Time':<19} "
                f"{'Entry':>6} {'Exit':>6} {'ROI':>8} {'Outcome':<8}"
            )
            print(_color(header, _DIM))
            print(_color("  " + "─" * 95, _GREY))

            for pos in closed_positions:
                # Get entry and exit times from orders
                entry_time = None
                exit_time = None
                if pos.order_ids:
                    fill_times = [
                        orders[oid].filled_at 
                        for oid in pos.order_ids 
                        if oid in orders and orders[oid].filled_at
                    ]
                    if fill_times:
                        entry_time = min(fill_times)
                        exit_time = max(fill_times)

                side_col = _GREEN if pos.side == "UP" else _BLUE
                roi_col = _GREEN if pos.pnl_pct > 0 else (_RED if pos.pnl_pct < 0 else _GREY)
                out_col = _GREEN if pos.outcome == "WON" else _RED
                
                exit_price = 1.0 if pos.outcome == "WON" else 0.0
                
                row = (
                    f"  {pos.slug[:20]:<22} "
                    f"{_color(pos.side, side_col):<5} "
                    f"{_format_datetime(entry_time):<19} "
                    f"{_format_datetime(exit_time):<19} "
                    f"{pos.avg_price:>6.4f} "
                    f"{exit_price:>6.4f} "
                    f"{_color(f'{pos.pnl_pct:+.2f}%', roi_col):>8} "
                    f"{_color(pos.outcome, out_col):<8}"
                )
                print(row)
        else:
            header = (
                f"  {'Market':<22} {'Side':<5} {'Entry':>6} "
                f"{'Exit':>6} {'ROI':>8} {'Outcome':<8}"
            )
            print(_color(header, _DIM))
            print(_color("  " + "─" * 60, _GREY))

            for pos in closed_positions:
                side_col = _GREEN if pos.side == "UP" else _BLUE
                roi_col = _GREEN if pos.pnl_pct > 0 else (_RED if pos.pnl_pct < 0 else _GREY)
                out_col = _GREEN if pos.outcome == "WON" else _RED
                
                exit_price = 1.0 if pos.outcome == "WON" else 0.0
                
                row = (
                    f"  {pos.slug[:20]:<22} "
                    f"{_color(pos.side, side_col):<5} "
                    f"{pos.avg_price:>6.4f} "
                    f"{exit_price:>6.4f} "
                    f"{_color(f'{pos.pnl_pct:+.2f}%', roi_col):>8} "
                    f"{_color(pos.outcome, out_col):<8}"
                )
                print(row)
        
        print()

    print(_divider(W))
    print()


# ── Main render function ───────────────────────────────────────────────────────

def render_terminal(
    metrics: dict[str, Any],
    trades: list[TradeRecord],
    initial_balance: float,
    preset_name: str = "default",
    show_trades: bool = True,
) -> None:
    """
    Print the analytics report to stdout.

    Tries to use ``rich`` for a prettier output; falls back to plain ANSI.

    Parameters
    ----------
    metrics : dict
        Output of compute_metrics().
    trades : list[TradeRecord]
    initial_balance : float
    preset_name : str
    show_trades : bool
        Whether to print the per-trade table at the bottom.
    """
    try:
        _render_rich(metrics, trades, initial_balance, preset_name, show_trades)
    except ImportError:
        _render_ansi(metrics, trades, initial_balance, preset_name, show_trades)


def _render_ansi(
    metrics: dict[str, Any],
    trades: list[TradeRecord],
    initial_balance: float,
    preset_name: str,
    show_trades: bool,
) -> None:
    """Plain ANSI fallback renderer."""
    W = 72

    print()
    print(_divider(W))
    print(_color(f"  POLYALPHA  ·  Paper Trading Analytics", _BOLD + _WHITE))
    print(_color(f"  Preset: {preset_name}   ·   Initial balance: ${initial_balance:.2f}", _DIM))
    print(_divider(W))

    # ── Metric cards ─────────────────────────────────────────────────────────
    label_w = 28
    for key, val in metrics.items():
        label = _METRIC_LABELS.get(key, key)
        value = _format_metric_value(key, val)
        print(f"  {_color(label + ':', _GREY):<{label_w + 10}} {value}")

    print(_divider(W))

    # ── Trade table ──────────────────────────────────────────────────────────
    if show_trades and trades:
        n_show = min(len(trades), 50)
        print(_color(f"  Recent Trades (last {n_show})", _BOLD + _WHITE))
        print()

        cols = ["#", "Market", "Side", "Outcome", "Entry", "Exit", "PnL", "Holding"]
        header = (
            f"  {'#':<5} {'Market':<22} {'Side':<5} {'Outcome':<7} "
            f"{'Entry':>6} {'Exit':>6} {'PnL':>10} {'Holding':>9}"
        )
        print(_color(header, _DIM))
        print(_color("  " + "─" * 68, _GREY))

        for i, t in enumerate(trades[-n_show:], 1):
            side_col = _GREEN if t.side == "UP" else _BLUE
            out_col  = _GREEN if t.outcome == "WON" else (_RED if t.outcome == "LOST" else _YELLOW)
            row = (
                f"  {i:<5} "
                f"{t.market_slug[:20]:<22} "
                f"{_color(t.side, side_col):<14} "
                f"{_color(t.outcome, out_col):<16} "
                f"{t.entry_price:>6.3f} "
                f"{t.exit_price:>6.3f} "
                f"{_fmt_pnl(t.pnl):>22} "
                f"{_color(_format_duration(t.holding_secs), _CYAN):>21}"
            )
            print(row)

    print(_divider(W))
    print()


def _render_rich(
    metrics: dict[str, Any],
    trades: list[TradeRecord],
    initial_balance: float,
    preset_name: str,
    show_trades: bool,
) -> None:
    """Rich-library renderer (imported lazily)."""
    from rich.console import Console
    from rich.table import Table
    from rich import box
    from rich.panel import Panel
    from rich.columns import Columns
    from rich.text import Text

    console = Console()

    # ── Header ───────────────────────────────────────────────────────────────
    console.print()
    console.rule(
        f"[bold white]POLYALPHA[/] · [dim]Paper Trading Analytics[/]  "
        f"[dim]preset:[/] [cyan]{preset_name}[/]  "
        f"[dim]balance:[/] [white]${initial_balance:.2f}[/]",
        style="dim blue",
    )

    # ── Metrics table ─────────────────────────────────────────────────────────
    mtable = Table(
        box=box.SIMPLE,
        show_header=True,
        header_style="bold dim",
        padding=(0, 2),
    )
    mtable.add_column("Metric", style="dim", min_width=28)
    mtable.add_column("Value", min_width=30)

    for key, val in metrics.items():
        label = _METRIC_LABELS.get(key, key)
        value = _format_metric_value(key, val)
        # Strip ANSI for rich
        mtable.add_row(label, value)

    console.print(mtable)

    # ── Trade table ───────────────────────────────────────────────────────────
    if show_trades and trades:
        n_show = min(len(trades), 50)
        ttable = Table(
            title=f"Recent Trades (last {n_show})",
            box=box.SIMPLE,
            show_header=True,
            header_style="bold dim",
            padding=(0, 1),
        )
        ttable.add_column("#",       style="dim", width=4)
        ttable.add_column("Market",  min_width=22)
        ttable.add_column("Side",    width=5)
        ttable.add_column("Result",  width=7)
        ttable.add_column("Entry",   justify="right", width=7)
        ttable.add_column("Exit",    justify="right", width=7)
        ttable.add_column("PnL",     justify="right", min_width=12)
        ttable.add_column("Holding", justify="right", width=9)

        for i, t in enumerate(trades[-n_show:], 1):
            side_style = "green" if t.side == "UP" else "blue"
            out_style  = "green" if t.outcome == "WON" else ("red" if t.outcome == "LOST" else "yellow")
            pnl_style  = "green" if t.pnl > 0 else ("red" if t.pnl < 0 else "dim")
            sign = "+" if t.pnl > 0 else ""
            ttable.add_row(
                str(i),
                t.market_slug[:22],
                Text(t.side, style=side_style),
                Text(t.outcome, style=out_style),
                f"{t.entry_price:.3f}",
                f"{t.exit_price:.3f}",
                Text(f"{sign}${t.pnl:.4f}", style=pnl_style),
                _format_duration(t.holding_secs),
            )

        console.print(ttable)

    console.rule(style="dim blue")
    console.print()
