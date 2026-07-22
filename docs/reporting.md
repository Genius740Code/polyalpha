# Reporting

The `polyalpha.report` module provides comprehensive trade analytics, performance metrics, interactive HTML dashboards, terminal rendering, and portfolio analytics for both paper and real trading.

---

## Module Overview

| File | Purpose |
|------|---------|
| `engine.py` | `ReportEngine` — main analytics entry point |
| `presets.py` | `ReportPreset` — configurable metric/chart presets |
| `metrics.py` | 32 performance metrics computations |
| `charts.py` | 12 Plotly chart builders (dark theme) |
| `terminal.py` | ANSI/rich terminal renderer |
| `html_template.py` | Self-contained HTML dashboard generator |
| `records.py` | `TradeRecord` dataclass + `extract_trades()` |
| `portfolio_analytics.py` | `PortfolioAnalytics` engine |
| `reporting.py` | `ReportingEngine` — comprehensive reports |
| `real_reports.py` | Standalone real-trading report functions |

Public API: `ReportEngine`, `ReportPreset`, `list_presets`, `load_preset`, `save_preset`

---

## ReportEngine

Main analytics entry point. Attached as `client.paper.report` when using the Client.

```python
from polyalpha.report import ReportEngine
from polyalpha.trading.paper_engine import PaperEngine

engine = PaperEngine(balance=1000.0)
report = ReportEngine(engine)

# Terminal output
report.show()

# Interactive HTML dashboard
path = report.html()

# Raw metrics dict
metrics = report.compute()
```

### Constructor

| Param | Type | Default | Description |
|-------|------|---------|-------------|
| `engine` | `PaperEngine \| RealTradingEngine` | required | Trading engine to analyze |
| `risk_free_rate` | `float` | `0.0` | Risk-free rate for Sharpe/Sortino |

### Methods

| Method | Description |
|--------|-------------|
| `trades() -> list[TradeRecord]` | All resolved trades chronologically |
| `show(preset="default", show_trades=True)` | Print report to terminal |
| `html(preset="default", path=None, open_browser=True) -> str` | Generate HTML dashboard, returns file path |
| `save_png(path, preset="default", width=1400, height=900) -> str` | Export equity curve + underwater DD as PNG |
| `compute(preset="default") -> dict` | Return raw metrics dictionary |
| `save_preset(name, metrics=None, charts=None, description="") -> ReportPreset` | Save custom preset |
| `load_preset(name) -> ReportPreset` | Load preset by name |
| `list_presets() -> list[str]` | List available presets |
| `delete_preset(name)` | Delete a user preset |
| `risk_exposure() -> str` | Risk exposure report text |
| `tax_report(path) -> str` | Export tax report CSV |
| `audit_trail(path) -> str` | Export audit trail JSON |

---

## Presets (`ReportPreset`)

Configurable sets of metrics and charts.

### Built-in Presets

| Preset | Metrics | Charts |
|--------|---------|--------|
| `default` | 12 core metrics | 4 core charts |
| `full` | All 32 metrics | All 12 charts |
| `quick` | 5 metrics (net_pnl, win_rate, total_trades, sharpe, max_drawdown) | 2 charts (equity_curve, pnl_per_trade) |

### Functions

| Function | Description |
|----------|-------------|
| `list_presets() -> list[str]` | List all preset names |
| `load_preset(name) -> ReportPreset` | Load preset |
| `save_preset(preset) -> Path` | Save custom preset to `~/.polyalpha/presets/` |
| `delete_preset(name)` | Delete user preset |

---

## Metrics (32 total)

### Default Metrics (12)

| Key | Description |
|-----|-------------|
| `net_pnl` | Total P&L in USDC |
| `win_rate` | Win rate (0-100%) |
| `total_trades` | Trade count |
| `sharpe` | Annualized Sharpe ratio |
| `sortino` | Annualized Sortino ratio (MAR=0) |
| `max_drawdown` | Peak-to-trough drawdown (%) |
| `profit_factor` | Gross profit / \|gross loss\| |
| `avg_win_loss` | Average win / average loss ratio |
| `expectancy` | Expected return per trade |
| `median_holding` | Median holding time |
| `best_trade` | Best single trade P&L |
| `worst_trade` | Worst single trade P&L |

### Optional Metrics (20)

`mean_holding`, `calmar`, `omega`, `skew`, `kurtosis`, `var_95`, `var_99`, `cvar_95`, `cvar_99`, `max_consec_wins`, `max_consec_losses`, `kelly`, `rolling_sharpe_30d`, `rolling_sharpe_90d`, `fill_rate`, `avg_slippage`, `pnl_concentration`, `deflated_sharpe`, `avg_position_size`, `turnover`

```python
from polyalpha.report.metrics import compute_metrics

metrics = compute_metrics(trades, initial_balance=1000.0, metric_keys=["sharpe", "sortino", "max_drawdown"])
```

---

## Charts (12 total)

### Default Charts (4)

| Key | Description |
|-----|-------------|
| `equity_curve` | Equity over time with peak/peak drawdown shading |
| `underwater_dd` | Drawdown from peak (always ≤ 0) |
| `pnl_per_trade` | PnL bar chart (green wins, red losses) |
| `win_loss_dist` | Overlay histogram of win/loss amounts |

### Optional Charts (8)

| Key | Description |
|-----|-------------|
| `rolling_sharpe` | 30-day and 90-day rolling Sharpe |
| `pnl_hour_heatmap` | PnL by hour-of-day × day-of-week |
| `pnl_tte_bucket` | PnL by holding time bucket |
| `return_dist` | Return distribution with normal overlay |
| `duration_hist` | Holding duration histogram (minutes) |
| `monthly_returns` | Monthly returns calendar heatmap |
| `entry_calibration` | Win rate vs entry price calibration curve |
| `corr_matrix` | Correlation matrix (returns `None`) |

```python
from polyalpha.report.charts import build_charts

figures = build_charts(
    chart_keys=["equity_curve", "underwater_dd", "rolling_sharpe"],
    trades=trades,
    initial_balance=1000.0
)
```

All charts use Plotly with a consistent dark theme (dark background `#0d0f1a`, surface `#161929`, grid `#232740`, text `#c8cde8`).

---

## Terminal Rendering

`render_terminal(metrics, trades, initial_balance, preset_name="default", show_trades=True)`

Renders a formatted report table to stdout. Uses `rich` if installed, falls back to ANSI color codes.

Features: metric cards with color-coded values, trade table (last 50 max), horizontal dividers, PnL formatting with +/- coloring.

`render_positions(positions, orders, show_all=False, verbose=True)` renders live/closed positions with entry/exit/ROI info.

---

## HTML Dashboard

`generate_html(metrics, trades, charts, chart_keys, initial_balance, preset_name, generated_at=None) -> str`

Self-contained single-file HTML dashboard featuring:
- Google Fonts (Inter + JetBrains Mono)
- Plotly.js v2.35.2 for interactive charts
- Dark theme with GitHub-inspired styling
- Sidebar with brand, report metadata, balance strip
- Tabbed layout (Dashboard / Trades)
- Charts grid with wide equity curve
- Trade table with 9 columns
- Tab switching + Plotly resize JavaScript

---

## PortfolioAnalytics

```python
from polyalpha.report.portfolio_analytics import PortfolioAnalytics

pa = PortfolioAnalytics(engine)
```

| Method | Returns |
|--------|---------|
| `get_portfolio_pnl() -> PortfolioPnL` | Realized/unrealized P&L, fees, drawdown |
| `get_daily_performance() -> TimeBasedPerformance` | Daily P&L breakdown |
| `get_weekly_performance() -> TimeBasedPerformance` | Weekly P&L (ISO week) |
| `get_monthly_performance() -> TimeBasedPerformance` | Monthly returns |
| `get_hourly_performance() -> dict[int, float]` | PnL by hour of day (0-23) |
| `get_weekday_performance() -> dict[int, float]` | PnL by weekday (0=Mon) |
| `get_performance_metrics() -> PerformanceMetrics` | 13 advanced metrics |
| `get_trade_history_summary() -> TradeHistorySummary` | Win rate, profit factor, holding times |
| `generate_summary_report() -> str` | Text report |
| `print_summary()` | Print to stdout |

### Dataclasses

- `PortfolioPnL`: total_pnl, realized_pnl, unrealized_pnl, total_fees, current_balance, max_drawdown, etc.
- `TimeBasedPerformance`: period_label, per-period dicts, best/worst period, avg, win_rate
- `TradeHistorySummary`: total_trades, winning_trades, losing_trades, win_rate, profit_factor, avg_win, avg_loss, avg_holding_time
- `PerformanceMetrics`: sharpe, sortino, calmar, omega, max_drawdown, expectancy, kelly, skew, kurtosis, var_95, var_99, cvar_95, cvar_99

---

## ReportingEngine

```python
from polyalpha.report.reporting import ReportingEngine

re = ReportingEngine(engine)
```

| Method | Description |
|--------|-------------|
| `portfolio_summary(path, format="html", include_charts=True) -> str` | Generate summary report (HTML/JSON/CSV) |
| `execution_quality(path, format="html") -> str` | Fill rate, slippage, limit order success |
| `risk_exposure(path, format="html") -> str` | Total exposure, VaR, concentration, leverage |
| `tax_report(path, format="csv") -> str` | Cost basis, realized gains, holding periods |
| `audit_trail(path, format="json") -> str` | Chronological order/position event log |

Additional dataclasses: `ExecutionQualityMetrics`, `RiskMetrics`, `TaxReportEntry`, `AuditEntry`

---

## Quick Reference

```
polyalpha.report
├── ReportEngine — show() / html() / compute() / save_png()
├── ReportPreset — default / full / quick presets
├── PortfolioAnalytics — per-period breakdowns, advanced metrics
├── ReportingEngine — portfolio / execution / risk / tax / audit
├── metrics (32): sharpe, sortino, calmar, omega, kelly, var, cvar, ...
└── charts (12): equity_curve, underwater_dd, rolling_sharpe, heatmap, ...
```
