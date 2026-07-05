"""
html_template.py — Self-contained HTML dashboard generator.

Produces a single .html file with all Plotly charts and metric data inlined.
No server required, no external CDN calls (Plotly JS is fetched once from CDN
but the chart data is 100% local).

The dashboard features a modern, professional trading interface inspired by
platforms like Kraken, TradingView, and Jesse AI. It includes:
  - Clean dark theme with professional color palette
  - Responsive grid layout with metric cards
  - Interactive charts with Plotly
  - Tabbed interface: Overview | Charts | Trades
  - Google Fonts (Inter + JetBrains Mono) for professional typography

Design inspiration
------------------
Inspired by Jesse AI (MIT licensed) and modern trading platforms like Kraken
and TradingView, featuring:
  - Deep dark backgrounds (#0d1117, #161b22)
  - Professional accent colors (emerald green for wins, rose for losses)
  - Clean typography with proper hierarchy
  - Subtle borders and shadows for depth
  - Responsive design for all screen sizes

Performance notes
-----------------
* Chart JSON serialisation uses plotly's built-in to_json() which is fast.
* The HTML string uses f-strings (not Jinja2) to keep dependencies minimal.
* Large trade tables are virtualised via a simple JS slice to cap DOM nodes.
"""

from __future__ import annotations

import json
import math
from datetime import datetime, timezone
from typing import Any, Optional

from .records import TradeRecord
from .terminal import _METRIC_LABELS, _format_duration, _fmt_float

# ── Colour tokens (inspired by Kraken/TradingView/Jesse) ────────────────────────

_WIN_HEX    = "#10b981"    # Emerald 500
_LOSS_HEX   = "#f43f5e"    # Rose 500
_NEUTRAL_HEX = "#6366f1"   # Indigo 500
_BLUE_HEX   = "#3b82f6"    # Blue 500


def _safe_float(v: Any) -> str:
    """Format a float safely for HTML, handling NaN/Inf."""
    if v is None:
        return "—"
    if isinstance(v, float):
        if math.isnan(v):
            return "n/a"
        if math.isinf(v):
            return "∞" if v > 0 else "-∞"
        return f"{v:.4f}"
    return str(v)


def _metric_html(key: str, val: Any) -> str:
    """Render a single metric as an HTML value string with colour."""
    if val is None:
        return '<span class="na">—</span>'

    def colored(txt: str, cls: str = "") -> str:
        return f'<span class="{cls}">{txt}</span>' if cls else txt

    if key == "net_pnl":
        usd = val.get("usd", float("nan"))
        pct = val.get("pct", float("nan"))
        cls = "win" if not math.isnan(usd) and usd > 0 else "loss" if not math.isnan(usd) and usd < 0 else ""
        u = f"+${usd:.4f}" if usd > 0 else f"${usd:.4f}"
        p = f"+{pct:.2f}%" if pct > 0 else f"{pct:.2f}%"
        return f'<span class="{cls}">{u}</span> <span class="sub">({p})</span>'

    if key == "win_rate":
        pct = val * 100
        cls = "win" if pct >= 50 else "loss"
        return f'<span class="{cls}">{pct:.2f}%</span>'

    if key == "total_trades":
        return f'<span class="neutral">{val}</span>'

    if key == "max_drawdown":
        pct = val.get("pct", float("nan"))
        usd = val.get("usd", float("nan"))
        pp = f"{pct:.2f}%" if not math.isnan(pct) else "n/a"
        uu = f"${usd:.4f}" if not math.isnan(usd) else "n/a"
        return f'<span class="loss">{pp}</span> <span class="sub">({uu})</span>'

    if key == "avg_win_loss":
        aw = val.get("avg_win",  float("nan"))
        al = val.get("avg_loss", float("nan"))
        aw_s = f"+${aw:.4f}" if not math.isnan(aw) else "n/a"
        al_s = f"${al:.4f}"  if not math.isnan(al) else "n/a"
        return f'<span class="win">{aw_s}</span> <span class="sub">/</span> <span class="loss">{al_s}</span>'

    if key in ("best_trade", "worst_trade"):
        pnl = val.get("pnl", float("nan"))
        pct = val.get("pct", float("nan"))
        mkt = val.get("market", "")
        cls = "win" if key == "best_trade" else "loss"
        p = f"+${pnl:.4f}" if pnl > 0 else f"${pnl:.4f}"
        pp = f"+{pct:.2f}%" if pct > 0 else f"{pct:.2f}%"
        return f'<span class="{cls}">{p} ({pp})</span> <span class="sub mkt">{mkt[:20]}</span>'

    if key in ("median_holding", "mean_holding"):
        if math.isnan(val):
            return '<span class="na">n/a</span>'
        return f'<span class="neutral">{_format_duration(val)}</span>'

    if key == "profit_factor":
        cls = "win" if isinstance(val, float) and not math.isnan(val) and val > 1 else "loss"
        return f'<span class="{cls}">{_safe_float(val)}</span>'

    if key == "expectancy":
        cls = "win" if isinstance(val, float) and not math.isnan(val) and val > 0 else "loss"
        pct = val * 100 if not (isinstance(val, float) and math.isnan(val)) else float("nan")
        return f'<span class="{cls}">{_safe_float(pct)}%</span>'

    if key in ("sharpe", "sortino", "calmar", "omega"):
        cls = "win" if isinstance(val, float) and not math.isnan(val) and val > 0 else "loss"
        return f'<span class="{cls}">{_safe_float(val)}</span>'

    if key == "kelly":
        cls = "win" if isinstance(val, float) and not math.isnan(val) and val > 0 else "neutral"
        return f'<span class="{cls}">{_safe_float(val)}</span>'

    if key in ("var_95", "var_99", "cvar_95", "cvar_99"):
        pct = val * 100 if isinstance(val, float) and not math.isnan(val) else float("nan")
        return f'<span class="loss">{_safe_float(pct)}%</span>'

    if key == "pnl_concentration":
        pct = val * 100 if isinstance(val, float) and not math.isnan(val) else float("nan")
        return f'<span class="neutral">{_safe_float(pct)}%</span>'

    if key == "deflated_sharpe":
        pct = val * 100 if isinstance(val, float) and not math.isnan(val) else float("nan")
        cls = "win" if isinstance(val, float) and not math.isnan(val) and val > 0.95 else "neutral"
        return f'<span class="{cls}">{_safe_float(pct)}%</span>'

    if key == "fill_rate":
        pct = val * 100 if isinstance(val, float) and not math.isnan(val) else float("nan")
        return f'<span class="neutral">{_safe_float(pct)}%</span>'

    if key == "avg_position_size":
        return f'<span class="neutral">${_safe_float(val)}</span>'

    if key == "turnover":
        return f'<span class="neutral">{_safe_float(val)}×</span>'

    if key in ("max_consec_wins",):
        return f'<span class="win">{val}</span>'

    if key in ("max_consec_losses",):
        return f'<span class="loss">{val}</span>'

    return f'<span class="neutral">{_safe_float(val)}</span>'


def _trade_rows_html(trades: list[TradeRecord], max_rows: int = 200) -> str:
    rows = []
    for i, t in enumerate(trades[-max_rows:], 1):
        side_cls   = "win" if t.side == "UP" else "blue"
        out_cls    = "win" if t.outcome == "WON" else ("loss" if t.outcome == "LOST" else "warn")
        pnl_cls    = "win" if t.pnl > 0 else ("loss" if t.pnl < 0 else "")
        sign       = "+" if t.pnl > 0 else ""
        pnl_str    = f"{sign}${t.pnl:.4f}"
        holding    = _format_duration(t.holding_secs)
        entry_dt   = t.entry_time.strftime("%m-%d %H:%M")
        rows.append(
            f"<tr>"
            f"<td class='dim'>{i}</td>"
            f"<td>{t.market_slug[:22]}</td>"
            f"<td class='{side_cls}'>{t.side}</td>"
            f"<td class='{out_cls}'>{t.outcome}</td>"
            f"<td class='mono'>{t.entry_price:.4f}</td>"
            f"<td class='mono'>{t.exit_price:.4f}</td>"
            f"<td class='mono {pnl_cls}'>{pnl_str}</td>"
            f"<td class='dim'>{holding}</td>"
            f"<td class='dim'>{entry_dt}</td>"
            f"</tr>"
        )
    return "\n".join(rows)


def _chart_script(chart_key: str, fig_json: str, div_id: str) -> str:
    return f"""
    (function() {{
        var figData = {fig_json};
        var layout  = figData.layout || {{}};
        var data    = figData.data   || [];
        Plotly.newPlot('{div_id}', data, layout, {{
            responsive: true,
            displayModeBar: true,
            modeBarButtonsToRemove: ['sendDataToCloud','autoScale2d','resetScale2d'],
            displaylogo: false,
            scrollZoom: true,
        }});
    }})();
"""


def _chart_section_html(
    charts: dict[str, Optional[object]],
    chart_keys: list[str],
) -> str:
    """Generate HTML + init script for all chart divs."""
    divs   = []
    scripts = []

    chart_titles = {
        "equity_curve":     "Equity Curve",
        "underwater_dd":    "Underwater Drawdown",
        "pnl_per_trade":    "PnL per Trade",
        "win_loss_dist":    "Win / Loss Distribution",
        "rolling_sharpe":   "Rolling Sharpe Ratio",
        "pnl_hour_heatmap": "PnL Heatmap (Hour × Day)",
        "pnl_tte_bucket":   "PnL by Holding Time",
        "return_dist":      "Return Distribution",
        "duration_hist":    "Trade Duration",
        "monthly_returns":  "Monthly Returns",
        "corr_matrix":      "Correlation Matrix",
        "entry_calibration":"Entry Calibration",
    }

    for key in chart_keys:
        fig = charts.get(key)
        if fig is None:
            divs.append(
                f'<div class="chart-card chart-empty">'
                f'<div class="chart-title">{chart_titles.get(key, key)}</div>'
                f'<div class="chart-placeholder">Insufficient data</div>'
                f'</div>'
            )
            continue

        div_id = f"chart_{key}"
        title  = chart_titles.get(key, key)

        divs.append(
            f'<div class="chart-card">'
            f'<div class="chart-title">{title}</div>'
            f'<div id="{div_id}" class="chart-div"></div>'
            f'</div>'
        )

        try:
            fig_json = fig.to_json()
            scripts.append(_chart_script(key, fig_json, div_id))
        except Exception:
            pass

    charts_html = "\n".join(divs)
    init_script = "\n".join(scripts)
    return charts_html, init_script


def generate_html(
    metrics: dict[str, Any],
    trades: list[TradeRecord],
    charts: dict[str, Optional[object]],
    chart_keys: list[str],
    initial_balance: float,
    preset_name: str,
    generated_at: Optional[datetime] = None,
) -> str:
    """
    Render the complete HTML dashboard as a string.

    Parameters
    ----------
    metrics : dict
    trades : list[TradeRecord]
    charts : dict
    chart_keys : list[str]
    initial_balance : float
    preset_name : str
    generated_at : datetime  (UTC)

    Returns
    -------
    str — self-contained HTML document
    """
    if generated_at is None:
        generated_at = datetime.now(timezone.utc)

    ts = generated_at.strftime("%Y-%m-%d %H:%M UTC")
    n  = len(trades)
    balance = metrics.get("net_pnl", {})
    final_balance = initial_balance + (balance.get("usd", 0) if isinstance(balance, dict) else 0)

    # Metric cards HTML
    metric_rows = []
    for key, val in metrics.items():
        label = _METRIC_LABELS.get(key, key)
        value_html = _metric_html(key, val)
        metric_rows.append(
            f'<div class="metric-card">'
            f'<div class="metric-label">{label}</div>'
            f'<div class="metric-value">{value_html}</div>'
            f'</div>'
        )
    metrics_html = "\n".join(metric_rows)

    # Trade table HTML
    trade_rows = _trade_rows_html(trades)

    # Charts
    charts_section, chart_init_script = _chart_section_html(charts, chart_keys)

    # Whether equity curve spans 2 columns
    has_equity = "equity_curve" in chart_keys and charts.get("equity_curve") is not None

    return f"""<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="UTF-8">
  <meta name="viewport" content="width=device-width, initial-scale=1.0">
  <title>polyalpha — Paper Trading Report</title>
  <meta name="description" content="Interactive paper trading analytics dashboard generated by polyalpha.">
  <link rel="preconnect" href="https://fonts.googleapis.com">
  <link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>
  <link href="https://fonts.googleapis.com/css2?family=Inter:wght@400;500;600&family=JetBrains+Mono:wght@400;500&display=swap" rel="stylesheet">
  <script src="https://cdn.plot.ly/plotly-2.35.2.min.js" charset="utf-8"></script>
  <style>
    *, *::before, *::after {{ box-sizing: border-box; margin: 0; padding: 0; }}

    :root {{
      /* GitHub-inspired dark theme with trading platform accents */
      --bg-primary:     #0d1117;
      --bg-secondary:   #161b22;
      --bg-tertiary:    #21262d;
      --border-color:   #30363d;
      --border-hover:   #8b949e;
      
      /* Text colors */
      --text-primary:   #e6edf3;
      --text-secondary: #8b949e;
      --text-muted:     #6e7681;
      
      /* Trading colors */
      --win:            #10b981;
      --loss:           #f43f5e;
      --neutral:        #6366f1;
      --blue:           #3b82f6;
      --warn:           #f59e0b;
      
      /* Spacing & sizing */
      --radius-sm:      6px;
      --radius-md:      8px;
      --radius-lg:      12px;
      --shadow-sm:      0 1px 2px rgba(0,0,0,0.3);
      --shadow-md:      0 4px 6px rgba(0,0,0,0.4);
      
      /* Typography */
      --font-sans:      'Inter', -apple-system, BlinkMacSystemFont, 'Segoe UI', sans-serif;
      --font-mono:      'JetBrains Mono', 'Fira Code', monospace;
    }}

    body {{
      font-family: var(--font-sans);
      background: var(--bg-primary);
      color: var(--text-primary);
      min-height: 100vh;
      font-size: 13px;
      line-height: 1.6;
      -webkit-font-smoothing: antialiased;
      -moz-osx-font-smoothing: grayscale;
    }}

    /* ── Layout ── */
    .app {{ 
      display: flex; 
      height: 100vh; 
      overflow: hidden;
    }}

    .main {{
      flex: 1;
      display: flex;
      flex-direction: column;
      overflow: hidden;
      background: var(--bg-primary);
    }}

    .sidebar {{
      width: 320px;
      min-width: 280px;
      background: var(--bg-secondary);
      border-left: 1px solid var(--border-color);
      display: flex;
      flex-direction: column;
      overflow-y: auto;
      overflow-x: hidden;
    }}

    /* ── Sidebar header ── */
    .sidebar-header {{
      padding: 24px 20px 16px;
      border-bottom: 1px solid var(--border-color);
      background: linear-gradient(180deg, var(--bg-tertiary) 0%, var(--bg-secondary) 100%);
    }}

    .brand {{
      font-size: 20px;
      font-weight: 700;
      color: var(--neutral);
      letter-spacing: -0.02em;
      display: flex;
      align-items: center;
      gap: 8px;
    }}
    .brand span {{ color: var(--text-primary); font-weight: 400; }}

    .report-meta {{
      margin-top: 12px;
      font-size: 11px;
      color: var(--text-muted);
      line-height: 1.8;
      padding: 8px 12px;
      background: var(--bg-tertiary);
      border-radius: var(--radius-sm);
    }}
    .report-meta strong {{ color: var(--text-secondary); }}

    /* ── Stats strip ── */
    .stats-strip {{
      display: grid;
      grid-template-columns: 1fr 1fr;
      gap: 1px;
      background: var(--border-color);
      border-bottom: 1px solid var(--border-color);
    }}
    .stat-cell {{
      background: var(--bg-secondary);
      padding: 14px 16px;
      transition: background 0.15s;
    }}
    .stat-cell:hover {{ background: var(--bg-tertiary); }}
    .stat-label {{ 
      font-size: 10px; 
      color: var(--text-muted); 
      text-transform: uppercase; 
      letter-spacing: 0.08em;
      font-weight: 600;
    }}
    .stat-val   {{ 
      font-size: 16px; 
      font-weight: 700; 
      margin-top: 4px;
      font-family: var(--font-mono);
    }}

    /* ── Metric cards ── */
    .metrics-scroll {{
      flex: 1;
      overflow-y: auto;
      padding: 4px 0;
    }}

    .metric-card {{
      padding: 12px 20px;
      border-bottom: 1px solid var(--border-color);
      transition: all 0.15s ease;
      cursor: default;
    }}
    .metric-card:hover {{ 
      background: var(--bg-tertiary);
      padding-left: 24px;
    }}

    .metric-label {{
      font-size: 10px;
      color: var(--text-muted);
      text-transform: uppercase;
      letter-spacing: 0.06em;
      font-weight: 600;
      margin-bottom: 4px;
    }}
    .metric-value {{
      font-size: 15px;
      font-weight: 500;
      font-family: var(--font-mono);
    }}

    /* ── Tab bar ── */
    .tab-bar {{
      display: flex;
      border-bottom: 1px solid var(--border-color);
      background: var(--bg-secondary);
      padding: 0 8px;
      gap: 2px;
    }}
    .tab {{
      padding: 14px 20px 12px;
      font-size: 13px;
      font-weight: 500;
      color: var(--text-muted);
      cursor: pointer;
      border-bottom: 2px solid transparent;
      transition: all 0.2s ease;
      user-select: none;
      position: relative;
    }}
    .tab:hover {{ 
      color: var(--text-primary);
      background: var(--bg-tertiary);
    }}
    .tab.active {{ 
      color: var(--neutral); 
      border-bottom-color: var(--neutral);
      font-weight: 600;
    }}
    .tab.active::after {{
      content: '';
      position: absolute;
      bottom: -1px;
      left: 0;
      right: 0;
      height: 2px;
      background: var(--neutral);
    }}

    /* ── Content panels ── */
    .panel {{
      display: none;
      flex: 1;
      overflow-y: auto;
      padding: 24px;
    }}
    .panel.active {{ display: block; }}

    /* ── Charts grid ── */
    .charts-grid {{
      display: grid;
      grid-template-columns: repeat(auto-fill, minmax(400px, 1fr));
      gap: 16px;
    }}

    .chart-card {{
      background: var(--bg-secondary);
      border: 1px solid var(--border-color);
      border-radius: var(--radius-md);
      padding: 16px;
      transition: border-color 0.2s ease;
    }}
    .chart-card:hover {{ 
      border-color: var(--border-hover);
    }}
    .chart-card.wide {{ grid-column: 1 / -1; }}

    .chart-title {{
      font-size: 12px;
      font-weight: 600;
      color: var(--text-primary);
      margin-bottom: 12px;
    }}

    .chart-div {{ height: 280px; width: 100%; }}
    .chart-div.tall {{ height: 350px; }}

    .chart-empty {{
      display: flex;
      flex-direction: column;
      align-items: center;
      justify-content: center;
      min-height: 200px;
      background: var(--bg-tertiary);
      border-radius: var(--radius-sm);
    }}
    .chart-placeholder {{
      font-size: 12px;
      color: var(--text-muted);
      margin-top: 12px;
    }}

    /* ── Summary panel ── */
    .summary-grid {{
      display: grid;
      grid-template-columns: repeat(auto-fill, minmax(180px, 1fr));
      gap: 12px;
      margin-bottom: 20px;
    }}
    .summary-card {{
      background: var(--bg-tertiary);
      border: 1px solid var(--border-color);
      border-radius: var(--radius-sm);
      padding: 16px;
    }}
    .summary-card .label {{
      font-size: 10px;
      color: var(--text-muted);
      text-transform: uppercase;
      letter-spacing: 0.06em;
      font-weight: 600;
    }}
    .summary-card .value {{
      font-size: 18px;
      font-weight: 600;
      margin-top: 6px;
      font-family: var(--font-mono);
    }}
    .summary-card .sub {{ 
      font-size: 11px; 
      color: var(--text-secondary); 
      margin-top: 2px;
    }}

    /* ── Trade table ── */
    .table-wrap {{
      overflow-x: auto;
      border-radius: var(--radius-lg);
      border: 1px solid var(--border-color);
      box-shadow: var(--shadow-sm);
    }}

    table {{
      width: 100%;
      border-collapse: collapse;
      font-size: 13px;
    }}

    thead th {{
      background: var(--bg-tertiary);
      color: var(--text-secondary);
      font-size: 11px;
      text-transform: uppercase;
      letter-spacing: 0.06em;
      font-weight: 600;
      padding: 12px 16px;
      text-align: left;
      white-space: nowrap;
      border-bottom: 1px solid var(--border-color);
    }}

    tbody tr {{
      border-bottom: 1px solid var(--border-color);
      transition: background 0.1s;
    }}
    tbody tr:hover {{ background: var(--bg-tertiary); }}
    tbody tr:last-child {{ border-bottom: none; }}
    tbody td {{ padding: 12px 16px; white-space: nowrap; }}

    /* ── Colour utilities ── */
    .win     {{ color: var(--win);     }}
    .loss    {{ color: var(--loss);    }}
    .neutral {{ color: var(--neutral); }}
    .blue    {{ color: var(--blue);    }}
    .warn    {{ color: var(--warn);    }}
    .dim     {{ color: var(--text-muted);}}
    .na      {{ color: var(--text-muted);}}
    .sub     {{ color: var(--text-secondary); font-size: 12px; }}
    .mkt     {{ font-size: 11px; }}
    .mono    {{ font-family: var(--font-mono); font-size: 13px; }}

    /* ── Scrollbars ── */
    ::-webkit-scrollbar {{ width: 8px; height: 8px; }}
    ::-webkit-scrollbar-track {{ background: var(--bg-primary); }}
    ::-webkit-scrollbar-thumb {{ 
      background: var(--border-color); 
      border-radius: 4px;
    }}
    ::-webkit-scrollbar-thumb:hover {{ background: var(--border-hover); }}

    /* ── Responsive ── */
    @media (max-width: 1024px) {{
      .sidebar {{ width: 280px; }}
      .charts-grid {{ grid-template-columns: 1fr; }}
    }}
    
    @media (max-width: 768px) {{
      .sidebar {{ 
        width: 100%; 
        min-width: unset; 
        max-height: 200px; 
        flex-direction: row; 
        flex-wrap: wrap; 
      }}
      .app {{ flex-direction: column; height: auto; }}
      .main {{ height: auto; }}
      .panel {{ padding: 16px; }}
      .charts-grid {{ grid-template-columns: 1fr; }}
      .summary-grid {{ grid-template-columns: 1fr 1fr; }}
    }}
  </style>
</head>
<body>
<div class="app">

  <!-- ── Main panel ── -->
  <main class="main">
    <div class="tab-bar">
      <div class="tab active" id="tab-charts"  onclick="switchTab('charts')">Dashboard</div>
      <div class="tab"        id="tab-trades"  onclick="switchTab('trades')">Trades ({n})</div>
    </div>

    <!-- Charts panel -->
    <div class="panel active" id="panel-charts">
      <div class="charts-grid" id="charts-grid">
        {charts_section}
      </div>
    </div>

    <!-- Trades panel -->
    <div class="panel" id="panel-trades">
      <div class="table-wrap">
        <table id="trades-table">
          <thead>
            <tr>
              <th>#</th>
              <th>Market</th>
              <th>Side</th>
              <th>Result</th>
              <th>Entry</th>
              <th>Exit</th>
              <th>PnL</th>
              <th>Holding</th>
              <th>Date</th>
            </tr>
          </thead>
          <tbody>
            {trade_rows}
          </tbody>
        </table>
      </div>
    </div>
  </main>

  <!-- ── Sidebar ── -->
  <aside class="sidebar">
    <div class="sidebar-header">
      <div class="brand">poly<span>alpha</span></div>
      <div class="report-meta">
        Preset: <strong>{preset_name}</strong><br>
        Generated: {ts}<br>
        Trades: {n}
      </div>
    </div>

    <div class="stats-strip">
      <div class="stat-cell">
        <div class="stat-label">Start</div>
        <div class="stat-val neutral">${initial_balance:,.2f}</div>
      </div>
      <div class="stat-cell">
        <div class="stat-label">End</div>
        <div class="stat-val {'win' if final_balance >= initial_balance else 'loss'}">${final_balance:,.2f}</div>
      </div>
    </div>

    <div class="metrics-scroll">
      {metrics_html}
    </div>
  </aside>
</div>

<script>
  // ── Tab switching ──
  function switchTab(name) {{
    ['charts','trades'].forEach(function(t) {{
      document.getElementById('tab-'   + t).classList.toggle('active', t === name);
      document.getElementById('panel-' + t).classList.toggle('active', t === name);
    }});
    // Trigger resize for Plotly so charts fill their containers
    if (name === 'charts') {{
      setTimeout(function() {{
        var divs = document.querySelectorAll('.chart-div');
        divs.forEach(function(d) {{ Plotly.Plots.resize(d); }});
      }}, 50);
    }}
  }}

  // ── Chart init (runs after page load) ──
  window.addEventListener('load', function() {{
    {chart_init_script}
  }});

  // ── Equity curve gets wide treatment ──
  (function() {{
    var eq = document.getElementById('chart_equity_curve');
    if (eq) {{
      var card = eq.closest('.chart-card');
      if (card) card.classList.add('wide');
      eq.classList.add('tall');
    }}
    var ud = document.getElementById('chart_underwater_dd');
    if (ud) {{
      var card2 = ud.closest('.chart-card');
      if (card2) card2.classList.add('wide');
    }}
  }})();
</script>
</body>
</html>"""


def _summary_cards_html(metrics: dict[str, Any]) -> str:
    """Render the summary panel hero cards for key metrics."""
    hero_keys = [
        ("net_pnl",       "Net PnL"),
        ("win_rate",      "Win Rate"),
        ("total_trades",  "Total Trades"),
        ("sharpe",        "Sharpe Ratio"),
        ("max_drawdown",  "Max Drawdown"),
        ("profit_factor", "Profit Factor"),
    ]
    cards = []
    for key, title in hero_keys:
        val = metrics.get(key)
        if val is None:
            continue
        value_html = _metric_html(key, val)
        cards.append(
            f'<div class="summary-card">'
            f'<div class="label">{title}</div>'
            f'<div class="value">{value_html}</div>'
            f'</div>'
        )
    return "\n".join(cards)
