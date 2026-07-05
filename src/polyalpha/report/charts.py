"""
charts.py — Plotly chart builders for the paper trading analytics dashboard.

All functions return a Plotly Figure object (or None if there is insufficient
data to render the chart).  The HTML report serialises each figure with
``fig.to_json()`` and inlines it into the dashboard.

Design notes
------------
* Dark theme applied globally via ``DARK_LAYOUT``.
* Colors: wins are #00d4a0 (teal-green), losses are #ff4d6d (coral-red),
  neutral is #7b8cde (periwinkle).  Matches the dashboard CSS palette.
* All functions are pure and side-effect-free — no file I/O.
* Charts degrade gracefully: returns ``None`` when there are < 2 data points.
"""

from __future__ import annotations

import math
from datetime import datetime
from typing import Optional

from .records import TradeRecord, build_equity_curve
from .metrics import (
    compute_rolling_sharpe,
    compute_underwater_curve,
    compute_pnl_by_hour,
    compute_pnl_by_weekday,
    compute_monthly_returns,
    compute_entry_calibration,
    _build_equity_array,
)

# ── Color palette ─────────────────────────────────────────────────────────────

_WIN_COLOR    = "#00d4a0"
_LOSS_COLOR   = "#ff4d6d"
_NEUTRAL_COLOR = "#7b8cde"
_BG_COLOR     = "#0d0f1a"
_SURFACE_COLOR = "#161929"
_GRID_COLOR   = "#232740"
_TEXT_COLOR   = "#c8cde8"
_PEAK_COLOR   = "#7b8cde"
_FILL_COLOR   = "rgba(255,77,109,0.15)"

# ── Shared layout base ────────────────────────────────────────────────────────

def _base_layout(title: str, xaxis_title: str = "", yaxis_title: str = "") -> dict:
    return dict(
        title=dict(
            text=title,
            font=dict(size=14, color=_TEXT_COLOR, family="Inter, system-ui, sans-serif"),
            x=0.0,
            xanchor="left",
        ),
        paper_bgcolor=_SURFACE_COLOR,
        plot_bgcolor=_BG_COLOR,
        font=dict(color=_TEXT_COLOR, family="Inter, system-ui, sans-serif", size=12),
        xaxis=dict(
            title=xaxis_title,
            gridcolor=_GRID_COLOR,
            showgrid=True,
            zeroline=False,
            color=_TEXT_COLOR,
            tickfont=dict(size=10),
        ),
        yaxis=dict(
            title=yaxis_title,
            gridcolor=_GRID_COLOR,
            showgrid=True,
            zeroline=True,
            zerolinecolor=_GRID_COLOR,
            zerolinewidth=1,
            color=_TEXT_COLOR,
            tickfont=dict(size=10),
        ),
        margin=dict(l=50, r=20, t=45, b=40),
        hovermode="x unified",
        legend=dict(
            bgcolor="rgba(0,0,0,0)",
            bordercolor=_GRID_COLOR,
            borderwidth=1,
            font=dict(size=11),
        ),
    )


def _try_import_plotly():
    """Lazy import of plotly — raises ImportError with install hint if absent."""
    try:
        import plotly.graph_objects as go
        return go
    except ImportError:
        raise ImportError(
            "plotly is required for chart generation. "
            "Install it with: pip install polyalpha[report]"
        )


# ── Chart builders ─────────────────────────────────────────────────────────────

def chart_equity_curve(
    trades: list[TradeRecord],
    initial_balance: float,
):
    """
    Equity curve with drawdown shading overlay.

    - Solid line: running equity
    - Dotted line: running peak (high-water mark)
    - Red fill: area between equity and peak (drawdown region)
    """
    go = _try_import_plotly()

    if len(trades) < 1:
        return None

    timestamps, equity = build_equity_curve(trades, initial_balance)

    # Running peak
    peaks = []
    peak = initial_balance
    for eq in equity:
        peak = max(peak, eq)
        peaks.append(peak)

    # Format timestamps as ISO strings for plotly
    ts_str = [t.isoformat() for t in timestamps]

    fig = go.Figure()

    # Drawdown fill: area between equity and peak
    fig.add_trace(go.Scatter(
        x=ts_str + ts_str[::-1],
        y=peaks + equity[::-1],
        fill="toself",
        fillcolor=_FILL_COLOR,
        line=dict(width=0),
        showlegend=False,
        hoverinfo="skip",
        name="Drawdown",
    ))

    # Peak line (dotted)
    fig.add_trace(go.Scatter(
        x=ts_str,
        y=peaks,
        mode="lines",
        name="Peak",
        line=dict(color=_PEAK_COLOR, width=1.5, dash="dot"),
        hovertemplate="%{y:.2f}<extra>Peak</extra>",
    ))

    # Equity line
    fig.add_trace(go.Scatter(
        x=ts_str,
        y=equity,
        mode="lines",
        name="Equity",
        line=dict(color=_WIN_COLOR, width=2.5),
        hovertemplate="%{y:.2f}<extra>Equity</extra>",
    ))

    # Zero line if applicable
    fig.add_hline(
        y=initial_balance,
        line_dash="dot",
        line_color="rgba(255,255,255,0.15)",
        line_width=1,
    )

    fig.update_layout(
        **_base_layout("Equity Curve", xaxis_title="Date", yaxis_title="Portfolio Value ($)"),
        showlegend=True,
    )

    return fig


def chart_underwater_dd(
    trades: list[TradeRecord],
    initial_balance: float,
):
    """
    Standalone underwater drawdown plot.

    Shows % drawdown from the running peak — always <= 0.
    """
    go = _try_import_plotly()

    if len(trades) < 2:
        return None

    timestamps, dd_values = compute_underwater_curve(trades, initial_balance)
    ts_str = [t.isoformat() for t in timestamps]

    fig = go.Figure()

    fig.add_trace(go.Scatter(
        x=ts_str,
        y=dd_values,
        mode="lines",
        fill="tozeroy",
        fillcolor=_FILL_COLOR,
        line=dict(color=_LOSS_COLOR, width=2),
        name="Drawdown %",
        hovertemplate="%{y:.2f}%<extra>Drawdown</extra>",
    ))

    layout = _base_layout("Underwater Drawdown", xaxis_title="Date", yaxis_title="Drawdown (%)")
    layout["yaxis"]["ticksuffix"] = "%"
    fig.update_layout(**layout)

    return fig


def chart_pnl_per_trade(trades: list[TradeRecord]):
    """
    Bar chart of PnL per trade.  Wins green, losses red.
    """
    go = _try_import_plotly()

    if not trades:
        return None

    pnls   = [t.pnl for t in trades]
    labels = [t.market_slug[:20] + f" ({t.side[0]})" for t in trades]
    colors = [_WIN_COLOR if p > 0 else _LOSS_COLOR for p in pnls]

    fig = go.Figure()

    fig.add_trace(go.Bar(
        x=list(range(1, len(trades) + 1)),
        y=pnls,
        marker_color=colors,
        name="PnL",
        customdata=labels,
        hovertemplate="Trade %{x}: %{customdata}<br>PnL: $%{y:.4f}<extra></extra>",
    ))

    fig.add_hline(y=0, line_color="rgba(255,255,255,0.2)", line_width=1)

    layout = _base_layout("PnL per Trade", xaxis_title="Trade #", yaxis_title="PnL ($)")
    layout["xaxis"]["tickmode"] = "linear"
    fig.update_layout(**layout)

    return fig


def chart_win_loss_dist(trades: list[TradeRecord]):
    """
    Histogram showing distribution of win and loss PnL amounts.
    """
    go = _try_import_plotly()

    wins   = [t.pnl for t in trades if t.pnl > 0]
    losses = [t.pnl for t in trades if t.pnl < 0]

    if not wins and not losses:
        return None

    fig = go.Figure()

    if wins:
        fig.add_trace(go.Histogram(
            x=wins,
            name="Wins",
            marker_color=_WIN_COLOR,
            opacity=0.75,
            nbinsx=min(30, max(5, len(wins) // 2)),
            hovertemplate="PnL: %{x:.4f}<br>Count: %{y}<extra>Wins</extra>",
        ))

    if losses:
        fig.add_trace(go.Histogram(
            x=losses,
            name="Losses",
            marker_color=_LOSS_COLOR,
            opacity=0.75,
            nbinsx=min(30, max(5, len(losses) // 2)),
            hovertemplate="PnL: %{x:.4f}<br>Count: %{y}<extra>Losses</extra>",
        ))

    layout = _base_layout("Win / Loss Distribution", xaxis_title="PnL ($)", yaxis_title="Count")
    layout["barmode"] = "overlay"
    fig.update_layout(**layout)

    return fig


def chart_rolling_sharpe(
    trades: list[TradeRecord],
    window_30d: bool = True,
    window_90d: bool = True,
    risk_free_rate: float = 0.0,
):
    """
    Rolling Sharpe ratio line chart (30d and/or 90d windows).
    """
    go = _try_import_plotly()

    if len(trades) < 3:
        return None

    fig = go.Figure()
    has_data = False

    if window_30d:
        ts30, sr30 = compute_rolling_sharpe(trades, 30, risk_free_rate)
        if ts30:
            fig.add_trace(go.Scatter(
                x=[t.isoformat() for t in ts30],
                y=sr30,
                mode="lines",
                name="30d Sharpe",
                line=dict(color=_WIN_COLOR, width=2),
                hovertemplate="%{y:.2f}<extra>30d Sharpe</extra>",
            ))
            has_data = True

    if window_90d:
        ts90, sr90 = compute_rolling_sharpe(trades, 90, risk_free_rate)
        if ts90:
            fig.add_trace(go.Scatter(
                x=[t.isoformat() for t in ts90],
                y=sr90,
                mode="lines",
                name="90d Sharpe",
                line=dict(color=_NEUTRAL_COLOR, width=2, dash="dash"),
                hovertemplate="%{y:.2f}<extra>90d Sharpe</extra>",
            ))
            has_data = True

    if not has_data:
        return None

    fig.add_hline(y=0, line_color="rgba(255,255,255,0.2)", line_width=1)

    fig.update_layout(
        **_base_layout("Rolling Sharpe Ratio", xaxis_title="Date", yaxis_title="Sharpe"),
        showlegend=True,
    )

    return fig


def chart_pnl_heatmap(trades: list[TradeRecord]):
    """
    PnL by hour-of-day × day-of-week heatmap.

    Rows = days of week (Mon–Sun), columns = hours (0–23 UTC).
    """
    go = _try_import_plotly()

    if len(trades) < 5:
        return None

    # Build 7×24 matrix
    day_names = ["Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun"]
    matrix = [[0.0] * 24 for _ in range(7)]

    for t in trades:
        dow  = t.entry_time.weekday()
        hour = t.entry_time.hour
        matrix[dow][hour] += t.pnl

    fig = go.Figure(data=go.Heatmap(
        z=matrix,
        x=list(range(24)),
        y=day_names,
        colorscale=[
            [0.0,  _LOSS_COLOR],
            [0.5,  _SURFACE_COLOR],
            [1.0,  _WIN_COLOR],
        ],
        zmid=0,
        hoverongaps=False,
        hovertemplate="Hour %{x}:00 UTC | %{y}<br>PnL: $%{z:.4f}<extra></extra>",
        colorbar=dict(
            title="PnL ($)",
            titlefont=dict(color=_TEXT_COLOR),
            tickfont=dict(color=_TEXT_COLOR),
            bgcolor=_SURFACE_COLOR,
        ),
    ))

    layout = _base_layout("PnL by Hour × Weekday", xaxis_title="Hour (UTC)", yaxis_title="")
    layout["xaxis"]["dtick"] = 2
    layout["hovermode"] = "closest"
    fig.update_layout(**layout)

    return fig


def chart_return_dist(trades: list[TradeRecord]):
    """
    Return distribution histogram with a normal overlay.
    """
    go = _try_import_plotly()
    import math as _math

    if len(trades) < 5:
        return None

    import statistics as _stats

    returns_pct = [t.pnl_pct for t in trades]
    mean_r = _stats.mean(returns_pct)
    std_r  = _stats.stdev(returns_pct) if len(returns_pct) >= 2 else 1.0

    # Normal overlay
    r_min = min(returns_pct)
    r_max = max(returns_pct)
    step  = (r_max - r_min) / 200 if r_max > r_min else 0.1
    xs    = [r_min + i * step for i in range(201)]

    def normal_pdf(x: float) -> float:
        if std_r == 0:
            return 0.0
        z = (x - mean_r) / std_r
        return (1 / (std_r * _math.sqrt(2 * _math.pi))) * _math.exp(-0.5 * z * z)

    ys_normal = [normal_pdf(x) for x in xs]

    # Scale to match histogram height: n_trades * bin_width
    n = len(returns_pct)
    bin_width = (r_max - r_min) / max(1, min(30, n // 2))
    scale = n * bin_width

    fig = go.Figure()

    fig.add_trace(go.Histogram(
        x=returns_pct,
        name="Returns",
        marker_color=_NEUTRAL_COLOR,
        opacity=0.8,
        nbinsx=min(30, max(5, n // 2)),
        hovertemplate="Return: %{x:.2f}%<br>Count: %{y}<extra></extra>",
    ))

    fig.add_trace(go.Scatter(
        x=xs,
        y=[y * scale for y in ys_normal],
        mode="lines",
        name="Normal",
        line=dict(color=_WIN_COLOR, width=2, dash="dot"),
        hovertemplate="Normal: %{y:.2f}<extra></extra>",
    ))

    layout = _base_layout("Return Distribution", xaxis_title="Return (%)", yaxis_title="Count")
    layout["xaxis"]["ticksuffix"] = "%"
    layout["barmode"] = "overlay"
    fig.update_layout(**layout)

    return fig


def chart_duration_hist(trades: list[TradeRecord]):
    """
    Trade holding-duration histogram (seconds → human-readable bins).
    """
    go = _try_import_plotly()

    if len(trades) < 3:
        return None

    durations_min = [t.holding_secs / 60.0 for t in trades]

    fig = go.Figure()

    fig.add_trace(go.Histogram(
        x=durations_min,
        name="Duration",
        marker_color=_NEUTRAL_COLOR,
        opacity=0.85,
        nbinsx=min(30, max(5, len(durations_min) // 2)),
        hovertemplate="Duration: %{x:.1f}m<br>Count: %{y}<extra></extra>",
    ))

    fig.update_layout(
        **_base_layout("Trade Duration", xaxis_title="Holding Time (minutes)", yaxis_title="Count"),
    )

    return fig


def chart_monthly_returns(
    trades: list[TradeRecord],
    initial_balance: float,
):
    """
    Monthly returns calendar heatmap (squares coloured by month return %).
    """
    go = _try_import_plotly()

    if len(trades) < 2:
        return None

    monthly = compute_monthly_returns(trades, initial_balance)
    if not monthly:
        return None

    # Parse keys into year/month
    years  = sorted({k[:4] for k in monthly.keys()})
    months = ["Jan", "Feb", "Mar", "Apr", "May", "Jun",
              "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"]

    # Build matrix: rows=months, cols=years
    matrix = [[None] * len(years) for _ in range(12)]
    for label, ret in monthly.items():
        y, m = label.split("-")
        col = years.index(y)
        row = int(m) - 1
        matrix[row][col] = ret

    # Replace None with NaN for plotly
    matrix_clean = [
        [v if v is not None else float("nan") for v in row]
        for row in matrix
    ]

    fig = go.Figure(data=go.Heatmap(
        z=matrix_clean,
        x=years,
        y=months,
        colorscale=[
            [0.0,  _LOSS_COLOR],
            [0.5,  _SURFACE_COLOR],
            [1.0,  _WIN_COLOR],
        ],
        zmid=0,
        hoverongaps=False,
        hovertemplate="%{y} %{x}<br>Return: %{z:.2f}%<extra></extra>",
        colorbar=dict(
            title="Return (%)",
            titlefont=dict(color=_TEXT_COLOR),
            tickfont=dict(color=_TEXT_COLOR),
            ticksuffix="%",
            bgcolor=_SURFACE_COLOR,
        ),
    ))

    layout = _base_layout("Monthly Returns", xaxis_title="Year", yaxis_title="")
    layout["hovermode"] = "closest"
    fig.update_layout(**layout)

    return fig


def chart_entry_calibration(trades: list[TradeRecord]):
    """
    Entry price vs win-rate calibration curve.

    X = entry price bucket midpoint, Y = empirical win rate.
    A well-calibrated strategy should approximate the diagonal.
    """
    go = _try_import_plotly()

    if len(trades) < 10:
        return None

    calibration = compute_entry_calibration(trades, n_buckets=10)
    if not calibration:
        return None

    xs = sorted(calibration.keys())
    ys = [calibration[x] for x in xs]

    fig = go.Figure()

    # Perfect calibration diagonal
    fig.add_trace(go.Scatter(
        x=[0, 1],
        y=[0, 1],
        mode="lines",
        name="Perfect calibration",
        line=dict(color="rgba(255,255,255,0.2)", width=1, dash="dot"),
        hoverinfo="skip",
    ))

    # Actual calibration
    fig.add_trace(go.Scatter(
        x=xs,
        y=ys,
        mode="lines+markers",
        name="Actual win rate",
        line=dict(color=_NEUTRAL_COLOR, width=2),
        marker=dict(color=_NEUTRAL_COLOR, size=8),
        hovertemplate="Entry: %{x:.2f}<br>Win rate: %{y:.1%}<extra></extra>",
    ))

    layout = _base_layout(
        "Entry Price Calibration",
        xaxis_title="Entry Price",
        yaxis_title="Empirical Win Rate",
    )
    layout["yaxis"]["tickformat"] = ".0%"
    layout["xaxis"]["range"] = [0, 1]
    layout["yaxis"]["range"] = [0, 1]
    fig.update_layout(**layout)

    return fig


def chart_pnl_tte_bucket(trades: list[TradeRecord]):
    """
    PnL by time-to-expiry bucket (inferred from holding time as a proxy).
    Buckets: <1m, 1–5m, 5–15m, 15–60m, >60m.
    """
    go = _try_import_plotly()

    if len(trades) < 3:
        return None

    buckets = ["<1m", "1–5m", "5–15m", "15–60m", ">60m"]
    bucket_pnl = {b: 0.0 for b in buckets}
    bucket_count = {b: 0 for b in buckets}

    for t in trades:
        secs = t.holding_secs
        if secs < 60:
            b = "<1m"
        elif secs < 300:
            b = "1–5m"
        elif secs < 900:
            b = "5–15m"
        elif secs < 3600:
            b = "15–60m"
        else:
            b = ">60m"
        bucket_pnl[b]   += t.pnl
        bucket_count[b] += 1

    # Filter empty buckets
    xs     = [b for b in buckets if bucket_count[b] > 0]
    ys_pnl = [bucket_pnl[b] for b in xs]
    colors = [_WIN_COLOR if p > 0 else _LOSS_COLOR for p in ys_pnl]

    fig = go.Figure()

    fig.add_trace(go.Bar(
        x=xs,
        y=ys_pnl,
        marker_color=colors,
        name="PnL",
        hovertemplate="%{x}<br>PnL: $%{y:.4f}<extra></extra>",
    ))

    fig.add_hline(y=0, line_color="rgba(255,255,255,0.2)", line_width=1)

    fig.update_layout(
        **_base_layout("PnL by Holding Time Bucket", xaxis_title="Holding Time", yaxis_title="Total PnL ($)"),
    )

    return fig


# ── Chart dispatcher ──────────────────────────────────────────────────────────

def build_charts(
    chart_keys: list[str],
    trades: list[TradeRecord],
    initial_balance: float,
    risk_free_rate: float = 0.0,
) -> dict[str, Optional[object]]:
    """
    Build all requested charts and return a dict of {key: figure|None}.

    Parameters
    ----------
    chart_keys : list[str]
        Chart keys from presets.ALL_CHARTS.
    trades : list[TradeRecord]
    initial_balance : float
    risk_free_rate : float

    Returns
    -------
    dict[str, Optional[Figure]]
    """
    result: dict[str, Optional[object]] = {}

    dispatch = {
        "equity_curve":    lambda: chart_equity_curve(trades, initial_balance),
        "underwater_dd":   lambda: chart_underwater_dd(trades, initial_balance),
        "pnl_per_trade":   lambda: chart_pnl_per_trade(trades),
        "win_loss_dist":   lambda: chart_win_loss_dist(trades),
        "rolling_sharpe":  lambda: chart_rolling_sharpe(trades, risk_free_rate=risk_free_rate),
        "pnl_hour_heatmap":lambda: chart_pnl_heatmap(trades),
        "return_dist":     lambda: chart_return_dist(trades),
        "duration_hist":   lambda: chart_duration_hist(trades),
        "monthly_returns": lambda: chart_monthly_returns(trades, initial_balance),
        "entry_calibration":lambda: chart_entry_calibration(trades),
        "pnl_tte_bucket":  lambda: chart_pnl_tte_bucket(trades),
        # corr_matrix requires multi-strategy data — not available from single engine
        "corr_matrix":     lambda: None,
    }

    for key in chart_keys:
        fn = dispatch.get(key)
        if fn is not None:
            try:
                result[key] = fn()
            except Exception:
                result[key] = None
        else:
            result[key] = None

    return result
