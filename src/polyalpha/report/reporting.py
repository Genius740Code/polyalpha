"""
reporting.py — Comprehensive reporting system for portfolio analytics.

This module provides production-ready reporting functionality including:
- Portfolio summary reports
- Trade execution quality reports
- Risk exposure reports
- Tax reporting (cost basis, realized gains)
- Audit trail for compliance

Usage
-----
    client = polyalpha.Client(balance=1000.0)
    
    # ... paper trade ...
    
    # Generate reports
    client.paper.reporting.portfolio_summary("portfolio_summary.html")
    client.paper.reporting.execution_quality("execution_quality.html")
    client.paper.reporting.risk_exposure("risk_exposure.html")
    client.paper.reporting.tax_report("tax_report.csv")
    client.paper.reporting.audit_trail("audit_trail.json")
"""

from __future__ import annotations

import csv
import json
import logging
from collections import defaultdict
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import TYPE_CHECKING, Optional, Union

from .portfolio_analytics import (
    PortfolioAnalytics,
    PortfolioPnL,
    TradeHistorySummary,
    PerformanceMetrics,
    TimeBasedPerformance,
)
from .records import TradeRecord, extract_trades

if TYPE_CHECKING:
    from ..trading.paper_engine import PaperEngine
    from ..trading.real import RealTradingEngine

log = logging.getLogger(__name__)


# ── Dataclasses ────────────────────────────────────────────────────────────────

@dataclass
class ExecutionQualityMetrics:
    """Trade execution quality metrics."""
    
    avg_fill_time: float  # Average time to fill orders (seconds)
    fill_rate: float  # Percentage of orders that filled
    slippage_avg: float  # Average slippage
    slippage_max: float  # Maximum slippage
    price_improvement: float  # Average price improvement
    limit_order_success_rate: float  # Success rate of limit orders
    market_order_count: int
    limit_order_count: int
    total_orders: int
    
    def dump(self) -> dict:
        return {
            "avg_fill_time": round(self.avg_fill_time, 2),
            "fill_rate": round(self.fill_rate, 4),
            "slippage_avg": round(self.slippage_avg, 6),
            "slippage_max": round(self.slippage_max, 6),
            "price_improvement": round(self.price_improvement, 6),
            "limit_order_success_rate": round(self.limit_order_success_rate, 4),
            "market_order_count": self.market_order_count,
            "limit_order_count": self.limit_order_count,
            "total_orders": self.total_orders,
        }


@dataclass
class RiskMetrics:
    """Risk exposure metrics."""
    
    total_exposure: float
    max_loss_exposure: float
    concentration_risk: dict[str, float]  # market -> exposure percentage
    leverage_ratio: float
    var_95: float  # Value at Risk at 95% confidence
    var_99: float  # Value at Risk at 99% confidence
    beta_exposure: float  # Market beta exposure
    
    def dump(self) -> dict:
        return {
            "total_exposure": round(self.total_exposure, 4),
            "max_loss_exposure": round(self.max_loss_exposure, 4),
            "concentration_risk": {k: round(v, 4) for k, v in self.concentration_risk.items()},
            "leverage_ratio": round(self.leverage_ratio, 4),
            "var_95": round(self.var_95, 4),
            "var_99": round(self.var_99, 4),
            "beta_exposure": round(self.beta_exposure, 4),
        }


@dataclass
class TaxReportEntry:
    """Single entry in tax report."""
    
    trade_id: str
    market: str
    side: str
    acquired: datetime
    sold: datetime
    proceeds: float
    cost_basis: float
    realized_gain: float
    gain_percent: float
    holding_period_days: int
    short_term: bool  # True if held < 1 year
    
    def dump(self) -> dict:
        return {
            "trade_id": self.trade_id,
            "market": self.market,
            "side": self.side,
            "acquired": self.acquired.isoformat(),
            "sold": self.sold.isoformat(),
            "proceeds": round(self.proceeds, 6),
            "cost_basis": round(self.cost_basis, 6),
            "realized_gain": round(self.realized_gain, 6),
            "gain_percent": round(self.gain_percent, 2),
            "holding_period_days": self.holding_period_days,
            "short_term": self.short_term,
        }


@dataclass
class AuditEntry:
    """Single entry in audit trail."""
    
    timestamp: datetime
    event_type: str  # "order_created", "order_filled", "position_opened", "position_closed", etc.
    details: dict
    
    def dump(self) -> dict:
        return {
            "timestamp": self.timestamp.isoformat(),
            "event_type": self.event_type,
            "details": self.details,
        }


# ── Reporting Engine ───────────────────────────────────────────────────────────

class ReportingEngine:
    """
    Comprehensive reporting engine for trading analytics.
    
    Provides production-ready reporting functionality for portfolio analysis,
    execution quality, risk management, tax compliance, and audit trails.
    
    Accessed via ``client.paper.reporting``.
    
    Parameters
    ----------
    engine : Union[PaperEngine, RealTradingEngine]
        The trading engine to generate reports for.
    """
    
    def __init__(self, engine: Union["PaperEngine", "RealTradingEngine"]) -> None:
        self._engine = engine
        self._portfolio_analytics = PortfolioAnalytics(engine)
    
    # ── Portfolio Summary Reports ───────────────────────────────────────────────
    
    def portfolio_summary(
        self,
        path: str,
        format: str = "html",
        include_charts: bool = True,
    ) -> str:
        """
        Generate a comprehensive portfolio summary report.
        
        Parameters
        ----------
        path : str
            Output file path.
        format : str
            Output format: "html", "json", or "csv" (default: "html").
        include_charts : bool
            Whether to include charts in HTML output (default: True).
        
        Returns
        -------
        str
            Absolute path to the generated report file.
        """
        out_path = Path(path).resolve()
        
        # Gather all analytics data
        portfolio_pnl = self._portfolio_analytics.get_portfolio_pnl()
        trade_summary = self._portfolio_analytics.get_trade_history_summary()
        perf_metrics = self._portfolio_analytics.get_performance_metrics()
        daily_perf = self._portfolio_analytics.get_daily_performance()
        weekly_perf = self._portfolio_analytics.get_weekly_performance()
        monthly_perf = self._portfolio_analytics.get_monthly_performance()
        
        if format == "json":
            data = {
                "generated_at": datetime.now(timezone.utc).isoformat(),
                "portfolio_pnl": portfolio_pnl.dump(),
                "trade_summary": trade_summary.dump(),
                "performance_metrics": perf_metrics.dump(),
                "daily_performance": daily_perf.dump(),
                "weekly_performance": weekly_perf.dump(),
                "monthly_performance": monthly_perf.dump(),
            }
            with open(out_path, "w", encoding="utf-8") as f:
                json.dump(data, f, indent=2)
        
        elif format == "csv":
            with open(out_path, "w", newline="", encoding="utf-8") as f:
                writer = csv.writer(f)
                writer.writerow(["Metric", "Value"])
                
                # Portfolio P&L
                writer.writerow(["Portfolio P&L", ""])
                writer.writerow(["Total P&L", f"${portfolio_pnl.total_pnl:.2f}"])
                writer.writerow(["Total P&L %", f"{portfolio_pnl.total_pnl_pct:.2f}%"])
                writer.writerow(["Realized P&L", f"${portfolio_pnl.realized_pnl:.2f}"])
                writer.writerow(["Unrealized P&L", f"${portfolio_pnl.unrealized_pnl:.2f}"])
                writer.writerow(["Current Balance", f"${portfolio_pnl.current_balance:.2f}"])
                writer.writerow(["Peak Balance", f"${portfolio_pnl.peak_balance:.2f}"])
                writer.writerow(["Max Drawdown", f"${portfolio_pnl.max_drawdown:.2f}"])
                writer.writerow(["Max Drawdown %", f"{portfolio_pnl.max_drawdown_pct:.2f}%"])
                writer.writerow([])
                
                # Trade Summary
                writer.writerow(["Trade Summary", ""])
                writer.writerow(["Total Trades", trade_summary.total_trades])
                writer.writerow(["Winning Trades", trade_summary.winning_trades])
                writer.writerow(["Losing Trades", trade_summary.losing_trades])
                writer.writerow(["Win Rate", f"{trade_summary.win_rate:.2%}"])
                writer.writerow(["Profit Factor", f"{trade_summary.profit_factor:.2f}"])
                writer.writerow(["Avg Win", f"${trade_summary.avg_win:.2f}"])
                writer.writerow(["Avg Loss", f"${trade_summary.avg_loss:.2f}"])
                writer.writerow([])
                
                # Performance Metrics
                writer.writerow(["Performance Metrics", ""])
                writer.writerow(["Sharpe Ratio", f"{perf_metrics.sharpe_ratio:.4f}"])
                writer.writerow(["Sortino Ratio", f"{perf_metrics.sortino_ratio:.4f}"])
                writer.writerow(["Calmar Ratio", f"{perf_metrics.calmar_ratio:.4f}"])
                writer.writerow(["Omega Ratio", f"{perf_metrics.omega_ratio:.4f}"])
                writer.writerow(["Expectancy", f"{perf_metrics.expectancy:.6f}"])
                writer.writerow(["Kelly Fraction", f"{perf_metrics.kelly_fraction:.4f}"])
        
        elif format == "html":
            html_content = self._generate_portfolio_summary_html(
                portfolio_pnl, trade_summary, perf_metrics,
                daily_perf, weekly_perf, monthly_perf, include_charts
            )
            out_path.write_text(html_content, encoding="utf-8")
        
        else:
            raise ValueError(f"Unsupported format: {format}")
        
        log.info("Portfolio summary report generated at %s", out_path)
        return str(out_path)
    
    def _generate_portfolio_summary_html(
        self,
        portfolio_pnl: PortfolioPnL,
        trade_summary: TradeHistorySummary,
        perf_metrics: PerformanceMetrics,
        daily_perf: TimeBasedPerformance,
        weekly_perf: TimeBasedPerformance,
        monthly_perf: TimeBasedPerformance,
        include_charts: bool,
    ) -> str:
        """Generate HTML portfolio summary report."""
        
        html = f"""
<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>Portfolio Summary Report</title>
    <style>
        body {{ font-family: Arial, sans-serif; margin: 40px; background-color: #f5f5f5; }}
        .container {{ max-width: 1200px; margin: 0 auto; background: white; padding: 30px; border-radius: 8px; box-shadow: 0 2px 10px rgba(0,0,0,0.1); }}
        h1 {{ color: #333; border-bottom: 3px solid #007bff; padding-bottom: 10px; }}
        h2 {{ color: #555; margin-top: 30px; border-bottom: 1px solid #ddd; padding-bottom: 5px; }}
        .metric-grid {{ display: grid; grid-template-columns: repeat(auto-fit, minmax(250px, 1fr)); gap: 20px; margin: 20px 0; }}
        .metric-card {{ background: #f8f9fa; padding: 20px; border-radius: 6px; border-left: 4px solid #007bff; }}
        .metric-label {{ font-size: 12px; color: #666; text-transform: uppercase; letter-spacing: 0.5px; }}
        .metric-value {{ font-size: 24px; font-weight: bold; color: #333; margin-top: 5px; }}
        .positive {{ color: #28a745; }}
        .negative {{ color: #dc3545; }}
        .table {{ width: 100%; border-collapse: collapse; margin: 20px 0; }}
        .table th, .table td {{ padding: 12px; text-align: left; border-bottom: 1px solid #ddd; }}
        .table th {{ background-color: #007bff; color: white; }}
        .table tr:hover {{ background-color: #f5f5f5; }}
        .timestamp {{ color: #999; font-size: 12px; margin-top: 30px; }}
    </style>
</head>
<body>
    <div class="container">
        <h1>Portfolio Summary Report</h1>
        
        <h2>Portfolio P&L</h2>
        <div class="metric-grid">
            <div class="metric-card">
                <div class="metric-label">Total P&L</div>
                <div class="metric-value {'positive' if portfolio_pnl.total_pnl >= 0 else 'negative'}">${portfolio_pnl.total_pnl:.2f}</div>
                <div class="metric-label">{portfolio_pnl.total_pnl_pct:.2f}%</div>
            </div>
            <div class="metric-card">
                <div class="metric-label">Realized P&L</div>
                <div class="metric-value {'positive' if portfolio_pnl.realized_pnl >= 0 else 'negative'}">${portfolio_pnl.realized_pnl:.2f}</div>
            </div>
            <div class="metric-card">
                <div class="metric-label">Unrealized P&L</div>
                <div class="metric-value {'positive' if portfolio_pnl.unrealized_pnl >= 0 else 'negative'}">${portfolio_pnl.unrealized_pnl:.2f}</div>
            </div>
            <div class="metric-card">
                <div class="metric-label">Current Balance</div>
                <div class="metric-value">${portfolio_pnl.current_balance:.2f}</div>
            </div>
            <div class="metric-card">
                <div class="metric-label">Peak Balance</div>
                <div class="metric-value">${portfolio_pnl.peak_balance:.2f}</div>
            </div>
            <div class="metric-card">
                <div class="metric-label">Max Drawdown</div>
                <div class="metric-value negative">${portfolio_pnl.max_drawdown:.2f}</div>
                <div class="metric-label">{portfolio_pnl.max_drawdown_pct:.2f}%</div>
            </div>
        </div>
        
        <h2>Trade History</h2>
        <div class="metric-grid">
            <div class="metric-card">
                <div class="metric-label">Total Trades</div>
                <div class="metric-value">{trade_summary.total_trades}</div>
            </div>
            <div class="metric-card">
                <div class="metric-label">Win Rate</div>
                <div class="metric-value">{trade_summary.win_rate:.2%}</div>
            </div>
            <div class="metric-card">
                <div class="metric-label">Profit Factor</div>
                <div class="metric-value">{trade_summary.profit_factor:.2f}</div>
            </div>
            <div class="metric-card">
                <div class="metric-label">Avg Win</div>
                <div class="metric-value positive">${trade_summary.avg_win:.2f}</div>
            </div>
            <div class="metric-card">
                <div class="metric-label">Avg Loss</div>
                <div class="metric-value negative">${trade_summary.avg_loss:.2f}</div>
            </div>
            <div class="metric-card">
                <div class="metric-label">Avg Holding Time</div>
                <div class="metric-value">{trade_summary.avg_holding_time:.1f}s</div>
            </div>
        </div>
        
        <h2>Performance Metrics</h2>
        <div class="metric-grid">
            <div class="metric-card">
                <div class="metric-label">Sharpe Ratio</div>
                <div class="metric-value">{perf_metrics.sharpe_ratio:.4f}</div>
            </div>
            <div class="metric-card">
                <div class="metric-label">Sortino Ratio</div>
                <div class="metric-value">{perf_metrics.sortino_ratio:.4f}</div>
            </div>
            <div class="metric-card">
                <div class="metric-label">Calmar Ratio</div>
                <div class="metric-value">{perf_metrics.calmar_ratio:.4f}</div>
            </div>
            <div class="metric-card">
                <div class="metric-label">Omega Ratio</div>
                <div class="metric-value">{perf_metrics.omega_ratio:.4f}</div>
            </div>
            <div class="metric-card">
                <div class="metric-label">Expectancy</div>
                <div class="metric-value">{perf_metrics.expectancy:.6f}</div>
            </div>
            <div class="metric-card">
                <div class="metric-label">Kelly Fraction</div>
                <div class="metric-value">{perf_metrics.kelly_fraction:.4f}</div>
            </div>
        </div>
        
        <h2>Time-based Performance</h2>
        <table class="table">
            <tr>
                <th>Period</th>
                <th>Best</th>
                <th>Worst</th>
                <th>Average</th>
                <th>Win Rate</th>
            </tr>
            <tr>
                <td>Daily</td>
                <td>{daily_perf.best_period[0]} (${daily_perf.best_period[1]:.2f})</td>
                <td>{daily_perf.worst_period[0]} (${daily_perf.worst_period[1]:.2f})</td>
                <td>${daily_perf.avg_performance:.2f}</td>
                <td>{daily_perf.win_rate:.2%}</td>
            </tr>
            <tr>
                <td>Weekly</td>
                <td>{weekly_perf.best_period[0]} (${weekly_perf.best_period[1]:.2f})</td>
                <td>{weekly_perf.worst_period[0]} (${weekly_perf.worst_period[1]:.2f})</td>
                <td>${weekly_perf.avg_performance:.2f}</td>
                <td>{weekly_perf.win_rate:.2%}</td>
            </tr>
            <tr>
                <td>Monthly</td>
                <td>{monthly_perf.best_period[0]} (${monthly_perf.best_period[1]:.2f})</td>
                <td>{monthly_perf.worst_period[0]} (${monthly_perf.worst_period[1]:.2f})</td>
                <td>${monthly_perf.avg_performance:.2f}</td>
                <td>{monthly_perf.win_rate:.2%}</td>
            </tr>
        </table>
        
        <div class="timestamp">
            Generated: {datetime.now(timezone.utc).strftime('%Y-%m-%d %H:%M:%S UTC')}
        </div>
    </div>
</body>
</html>
"""
        return html
    
    # ── Trade Execution Quality Reports ───────────────────────────────────────────
    
    def execution_quality(
        self,
        path: str,
        format: str = "html",
    ) -> str:
        """
        Generate trade execution quality report.
        
        Parameters
        ----------
        path : str
            Output file path.
        format : str
            Output format: "html", "json", or "csv" (default: "html").
        
        Returns
        -------
        str
            Absolute path to the generated report file.
        """
        out_path = Path(path).resolve()
        
        # Calculate execution quality metrics
        metrics = self._calculate_execution_quality()
        
        if format == "json":
            data = {
                "generated_at": datetime.now(timezone.utc).isoformat(),
                "execution_quality": metrics.dump(),
            }
            with open(out_path, "w", encoding="utf-8") as f:
                json.dump(data, f, indent=2)
        
        elif format == "csv":
            with open(out_path, "w", newline="", encoding="utf-8") as f:
                writer = csv.writer(f)
                writer.writerow(["Metric", "Value"])
                writer.writerow(["Average Fill Time (s)", f"{metrics.avg_fill_time:.2f}"])
                writer.writerow(["Fill Rate", f"{metrics.fill_rate:.2%}"])
                writer.writerow(["Average Slippage", f"{metrics.slippage_avg:.6f}"])
                writer.writerow(["Maximum Slippage", f"{metrics.slippage_max:.6f}"])
                writer.writerow(["Price Improvement", f"{metrics.price_improvement:.6f}"])
                writer.writerow(["Limit Order Success Rate", f"{metrics.limit_order_success_rate:.2%}"])
                writer.writerow(["Market Orders", metrics.market_order_count])
                writer.writerow(["Limit Orders", metrics.limit_order_count])
                writer.writerow(["Total Orders", metrics.total_orders])
        
        elif format == "html":
            html_content = self._generate_execution_quality_html(metrics)
            out_path.write_text(html_content, encoding="utf-8")
        
        else:
            raise ValueError(f"Unsupported format: {format}")
        
        log.info("Execution quality report generated at %s", out_path)
        return str(out_path)
    
    def _calculate_execution_quality(self) -> ExecutionQualityMetrics:
        """Calculate execution quality metrics from order history."""
        orders = self._engine._orders
        
        if not orders:
            return ExecutionQualityMetrics(
                avg_fill_time=0.0,
                fill_rate=0.0,
                slippage_avg=0.0,
                slippage_max=0.0,
                price_improvement=0.0,
                limit_order_success_rate=0.0,
                market_order_count=0,
                limit_order_count=0,
                total_orders=0,
            )
        
        filled_orders = [o for o in orders.values() if o.status == "filled"]
        limit_orders = [o for o in orders.values() if getattr(o, "is_limit", False)]
        filled_limit_orders = [o for o in limit_orders if o.status == "filled"]
        
        # Calculate fill time
        fill_times = []
        for o in filled_orders:
            if o.filled_at and hasattr(o, 'created_at') and o.created_at:
                fill_time = (o.filled_at - o.created_at).total_seconds()
                fill_times.append(fill_time)
        
        avg_fill_time = sum(fill_times) / len(fill_times) if fill_times else 0.0
        
        # Calculate fill rate
        fill_rate = len(filled_orders) / len(orders) if orders else 0.0
        
        # Calculate slippage (using stored slippage if available)
        slippages = [getattr(o, 'slippage', 0.0) for o in filled_orders]
        slippage_avg = sum(slippages) / len(slippages) if slippages else 0.0
        slippage_max = max(slippages) if slippages else 0.0
        
        # Calculate price improvement (simplified)
        price_improvement = 0.0  # Would need intended price vs actual price
        
        # Limit order success rate
        limit_order_success_rate = len(filled_limit_orders) / len(limit_orders) if limit_orders else 0.0
        
        return ExecutionQualityMetrics(
            avg_fill_time=avg_fill_time,
            fill_rate=fill_rate,
            slippage_avg=slippage_avg,
            slippage_max=slippage_max,
            price_improvement=price_improvement,
            limit_order_success_rate=limit_order_success_rate,
            market_order_count=len([o for o in orders.values() if not getattr(o, "is_limit", False)]),
            limit_order_count=len(limit_orders),
            total_orders=len(orders),
        )
    
    def _generate_execution_quality_html(self, metrics: ExecutionQualityMetrics) -> str:
        """Generate HTML execution quality report."""
        
        html = f"""
<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>Execution Quality Report</title>
    <style>
        body {{ font-family: Arial, sans-serif; margin: 40px; background-color: #f5f5f5; }}
        .container {{ max-width: 1000px; margin: 0 auto; background: white; padding: 30px; border-radius: 8px; box-shadow: 0 2px 10px rgba(0,0,0,0.1); }}
        h1 {{ color: #333; border-bottom: 3px solid #007bff; padding-bottom: 10px; }}
        h2 {{ color: #555; margin-top: 30px; border-bottom: 1px solid #ddd; padding-bottom: 5px; }}
        .metric-grid {{ display: grid; grid-template-columns: repeat(auto-fit, minmax(250px, 1fr)); gap: 20px; margin: 20px 0; }}
        .metric-card {{ background: #f8f9fa; padding: 20px; border-radius: 6px; border-left: 4px solid #007bff; }}
        .metric-label {{ font-size: 12px; color: #666; text-transform: uppercase; letter-spacing: 0.5px; }}
        .metric-value {{ font-size: 24px; font-weight: bold; color: #333; margin-top: 5px; }}
        .good {{ color: #28a745; }}
        .warning {{ color: #ffc107; }}
        .bad {{ color: #dc3545; }}
        .timestamp {{ color: #999; font-size: 12px; margin-top: 30px; }}
    </style>
</head>
<body>
    <div class="container">
        <h1>Execution Quality Report</h1>
        
        <h2>Order Execution Metrics</h2>
        <div class="metric-grid">
            <div class="metric-card">
                <div class="metric-label">Total Orders</div>
                <div class="metric-value">{metrics.total_orders}</div>
            </div>
            <div class="metric-card">
                <div class="metric-label">Market Orders</div>
                <div class="metric-value">{metrics.market_order_count}</div>
            </div>
            <div class="metric-card">
                <div class="metric-label">Limit Orders</div>
                <div class="metric-value">{metrics.limit_order_count}</div>
            </div>
            <div class="metric-card">
                <div class="metric-label">Fill Rate</div>
                <div class="metric-value {'good' if metrics.fill_rate >= 0.95 else 'warning' if metrics.fill_rate >= 0.9 else 'bad'}">{metrics.fill_rate:.2%}</div>
            </div>
        </div>
        
        <h2>Execution Speed</h2>
        <div class="metric-grid">
            <div class="metric-card">
                <div class="metric-label">Average Fill Time</div>
                <div class="metric-value">{metrics.avg_fill_time:.2f}s</div>
            </div>
        </div>
        
        <h2>Price Quality</h2>
        <div class="metric-grid">
            <div class="metric-card">
                <div class="metric-label">Average Slippage</div>
                <div class="metric-value {'good' if metrics.slippage_avg <= 0.001 else 'warning' if metrics.slippage_avg <= 0.005 else 'bad'}">{metrics.slippage_avg:.6f}</div>
            </div>
            <div class="metric-card">
                <div class="metric-label">Maximum Slippage</div>
                <div class="metric-value">{metrics.slippage_max:.6f}</div>
            </div>
            <div class="metric-card">
                <div class="metric-label">Price Improvement</div>
                <div class="metric-value">{metrics.price_improvement:.6f}</div>
            </div>
            <div class="metric-card">
                <div class="metric-label">Limit Order Success Rate</div>
                <div class="metric-value {'good' if metrics.limit_order_success_rate >= 0.8 else 'warning'}">{metrics.limit_order_success_rate:.2%}</div>
            </div>
        </div>
        
        <div class="timestamp">
            Generated: {datetime.now(timezone.utc).strftime('%Y-%m-%d %H:%M:%S UTC')}
        </div>
    </div>
</body>
</html>
"""
        return html
    
    # ── Risk Exposure Reports ─────────────────────────────────────────────────────
    
    def risk_exposure(
        self,
        path: str,
        format: str = "html",
    ) -> str:
        """
        Generate risk exposure report.
        
        Parameters
        ----------
        path : str
            Output file path.
        format : str
            Output format: "html", "json", or "csv" (default: "html").
        
        Returns
        -------
        str
            Absolute path to the generated report file.
        """
        out_path = Path(path).resolve()
        
        # Calculate risk metrics
        metrics = self._calculate_risk_metrics()
        
        if format == "json":
            data = {
                "generated_at": datetime.now(timezone.utc).isoformat(),
                "risk_exposure": metrics.dump(),
            }
            with open(out_path, "w", encoding="utf-8") as f:
                json.dump(data, f, indent=2)
        
        elif format == "csv":
            with open(out_path, "w", newline="", encoding="utf-8") as f:
                writer = csv.writer(f)
                writer.writerow(["Metric", "Value"])
                writer.writerow(["Total Exposure", f"${metrics.total_exposure:.2f}"])
                writer.writerow(["Max Loss Exposure", f"${metrics.max_loss_exposure:.2f}"])
                writer.writerow(["Leverage Ratio", f"{metrics.leverage_ratio:.2f}"])
                writer.writerow(["VaR (95%)", f"${metrics.var_95:.2f}"])
                writer.writerow(["VaR (99%)", f"${metrics.var_99:.2f}"])
                writer.writerow(["Beta Exposure", f"{metrics.beta_exposure:.2f}"])
                writer.writerow([])
                writer.writerow(["Market Concentration", ""])
                for market, pct in metrics.concentration_risk.items():
                    writer.writerow([market, f"{pct:.2%}"])
        
        elif format == "html":
            html_content = self._generate_risk_exposure_html(metrics)
            out_path.write_text(html_content, encoding="utf-8")
        
        else:
            raise ValueError(f"Unsupported format: {format}")
        
        log.info("Risk exposure report generated at %s", out_path)
        return str(out_path)
    
    def _calculate_risk_metrics(self) -> RiskMetrics:
        """Calculate risk exposure metrics."""
        positions = [p for p in self._engine._positions.values() if not getattr(p, "resolved", False)]
        balance = getattr(self._engine, "_balance", 0.0)
        
        total_deployed = sum(getattr(p, "cost_basis", 0.0) for p in positions)
        total_exposure = balance + total_deployed
        
        # Calculate max loss exposure
        max_loss_exposure = 0.0
        market_exposure = defaultdict(float)
        
        for p in positions:
            cost_basis = getattr(p, "cost_basis", 0.0)
            market_id = getattr(p, "market_id", "unknown")
            market_exposure[market_id] += cost_basis
            
            stop_loss = getattr(p, "stop_loss", None)
            shares = getattr(p, "shares", 0.0)
            
            if stop_loss is not None:
                guaranteed_return = shares * stop_loss
                loss = cost_basis - guaranteed_return
                max_loss_exposure += loss
            else:
                max_loss_exposure += cost_basis
        
        # Calculate concentration risk
        concentration_risk = {}
        if total_deployed > 0:
            for market, exposure in market_exposure.items():
                concentration_risk[market] = exposure / total_deployed
        
        # Calculate leverage ratio
        leverage_ratio = total_deployed / balance if balance > 0 else 0.0
        
        # Calculate VaR (simplified - using historical simulation)
        trades = extract_trades(self._engine)
        if trades:
            returns = [t.pnl for t in trades]
            returns.sort()
            var_95 = abs(returns[int(len(returns) * 0.05)]) if len(returns) > 0 else 0.0
            var_99 = abs(returns[int(len(returns) * 0.01)]) if len(returns) > 0 else 0.0
        else:
            var_95 = 0.0
            var_99 = 0.0
        
        # Beta exposure (simplified - would need market data)
        beta_exposure = 1.0  # Placeholder
        
        return RiskMetrics(
            total_exposure=total_exposure,
            max_loss_exposure=max_loss_exposure,
            concentration_risk=concentration_risk,
            leverage_ratio=leverage_ratio,
            var_95=var_95,
            var_99=var_99,
            beta_exposure=beta_exposure,
        )
    
    def _generate_risk_exposure_html(self, metrics: RiskMetrics) -> str:
        """Generate HTML risk exposure report."""
        
        concentration_rows = ""
        for market, pct in sorted(metrics.concentration_risk.items(), key=lambda x: x[1], reverse=True):
            concentration_rows += f"""
            <tr>
                <td>{market}</td>
                <td>{pct:.2%}</td>
                <td class="{'warning' if pct > 0.3 else 'good'}">{'High' if pct > 0.3 else 'Normal'}</td>
            </tr>
"""
        
        html = f"""
<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>Risk Exposure Report</title>
    <style>
        body {{ font-family: Arial, sans-serif; margin: 40px; background-color: #f5f5f5; }}
        .container {{ max-width: 1000px; margin: 0 auto; background: white; padding: 30px; border-radius: 8px; box-shadow: 0 2px 10px rgba(0,0,0,0.1); }}
        h1 {{ color: #333; border-bottom: 3px solid #dc3545; padding-bottom: 10px; }}
        h2 {{ color: #555; margin-top: 30px; border-bottom: 1px solid #ddd; padding-bottom: 5px; }}
        .metric-grid {{ display: grid; grid-template-columns: repeat(auto-fit, minmax(250px, 1fr)); gap: 20px; margin: 20px 0; }}
        .metric-card {{ background: #f8f9fa; padding: 20px; border-radius: 6px; border-left: 4px solid #dc3545; }}
        .metric-label {{ font-size: 12px; color: #666; text-transform: uppercase; letter-spacing: 0.5px; }}
        .metric-value {{ font-size: 24px; font-weight: bold; color: #333; margin-top: 5px; }}
        .good {{ color: #28a745; }}
        .warning {{ color: #ffc107; }}
        .bad {{ color: #dc3545; }}
        .table {{ width: 100%; border-collapse: collapse; margin: 20px 0; }}
        .table th, .table td {{ padding: 12px; text-align: left; border-bottom: 1px solid #ddd; }}
        .table th {{ background-color: #dc3545; color: white; }}
        .table tr:hover {{ background-color: #f5f5f5; }}
        .timestamp {{ color: #999; font-size: 12px; margin-top: 30px; }}
    </style>
</head>
<body>
    <div class="container">
        <h1>Risk Exposure Report</h1>
        
        <h2>Overall Risk Metrics</h2>
        <div class="metric-grid">
            <div class="metric-card">
                <div class="metric-label">Total Exposure</div>
                <div class="metric-value">${metrics.total_exposure:.2f}</div>
            </div>
            <div class="metric-card">
                <div class="metric-label">Max Loss Exposure</div>
                <div class="metric-value bad">${metrics.max_loss_exposure:.2f}</div>
            </div>
            <div class="metric-card">
                <div class="metric-label">Leverage Ratio</div>
                <div class="metric-value {'good' if metrics.leverage_ratio <= 1.0 else 'warning' if metrics.leverage_ratio <= 2.0 else 'bad'}">{metrics.leverage_ratio:.2f}x</div>
            </div>
            <div class="metric-card">
                <div class="metric-label">VaR (95%)</div>
                <div class="metric-value">${metrics.var_95:.2f}</div>
            </div>
            <div class="metric-card">
                <div class="metric-label">VaR (99%)</div>
                <div class="metric-value">${metrics.var_99:.2f}</div>
            </div>
            <div class="metric-card">
                <div class="metric-label">Beta Exposure</div>
                <div class="metric-value">{metrics.beta_exposure:.2f}</div>
            </div>
        </div>
        
        <h2>Market Concentration</h2>
        <table class="table">
            <tr>
                <th>Market</th>
                <th>Exposure %</th>
                <th>Risk Level</th>
            </tr>
            {concentration_rows if concentration_rows else '<tr><td colspan="3">No open positions</td></tr>'}
        </table>
        
        <div class="timestamp">
            Generated: {datetime.now(timezone.utc).strftime('%Y-%m-%d %H:%M:%S UTC')}
        </div>
    </div>
</body>
</html>
"""
        return html
    
    # ── Tax Reporting ─────────────────────────────────────────────────────────────
    
    def tax_report(
        self,
        path: str,
        format: str = "csv",
    ) -> str:
        """
        Generate tax report with cost basis and realized gains.
        
        Parameters
        ----------
        path : str
            Output file path.
        format : str
            Output format: "csv" or "json" (default: "csv").
        
        Returns
        -------
        str
            Absolute path to the generated report file.
        """
        out_path = Path(path).resolve()
        
        trades = extract_trades(self._engine)
        tax_entries = self._calculate_tax_entries(trades)
        
        if format == "json":
            data = {
                "generated_at": datetime.now(timezone.utc).isoformat(),
                "tax_entries": [entry.dump() for entry in tax_entries],
                "summary": {
                    "total_trades": len(tax_entries),
                    "total_proceeds": sum(e.proceeds for e in tax_entries),
                    "total_cost_basis": sum(e.cost_basis for e in tax_entries),
                    "total_realized_gains": sum(e.realized_gain for e in tax_entries),
                    "short_term_trades": sum(1 for e in tax_entries if e.short_term),
                    "long_term_trades": sum(1 for e in tax_entries if not e.short_term),
                }
            }
            with open(out_path, "w", encoding="utf-8") as f:
                json.dump(data, f, indent=2)
        
        elif format == "csv":
            with open(out_path, "w", newline="", encoding="utf-8") as f:
                writer = csv.writer(f)
                writer.writerow([
                    "TradeID", "Market", "Side", "Acquired", "Sold",
                    "Proceeds", "CostBasis", "RealizedGain", "GainPercent",
                    "HoldingPeriodDays", "ShortTerm"
                ])
                
                for entry in tax_entries:
                    writer.writerow([
                        entry.trade_id,
                        entry.market,
                        entry.side,
                        entry.acquired.isoformat(),
                        entry.sold.isoformat(),
                        f"{entry.proceeds:.6f}",
                        f"{entry.cost_basis:.6f}",
                        f"{entry.realized_gain:.6f}",
                        f"{entry.gain_percent:.2f}",
                        entry.holding_period_days,
                        "Yes" if entry.short_term else "No",
                    ])
                
                # Add summary row
                writer.writerow([])
                writer.writerow([
                    "TOTALS", "", "", "", "",
                    f"{sum(e.proceeds for e in tax_entries):.6f}",
                    f"{sum(e.cost_basis for e in tax_entries):.6f}",
                    f"{sum(e.realized_gain for e in tax_entries):.6f}",
                    "", "", ""
                ])
        
        else:
            raise ValueError(f"Unsupported format: {format}")
        
        log.info("Tax report generated at %s", out_path)
        return str(out_path)
    
    def _calculate_tax_entries(self, trades: list[TradeRecord]) -> list[TaxReportEntry]:
        """Calculate tax report entries from trades."""
        entries = []
        
        for t in trades:
            proceeds = (t.exit_price * t.shares) if t.outcome != "LOST" else 0.0
            cost_basis = t.amount_in
            realized_gain = proceeds - cost_basis
            gain_percent = t.pnl_pct
            
            holding_period = (t.exit_time - t.entry_time).days
            short_term = holding_period < 365
            
            entry = TaxReportEntry(
                trade_id=t.trade_id,
                market=t.market_slug,
                side=t.side,
                acquired=t.entry_time,
                sold=t.exit_time,
                proceeds=proceeds,
                cost_basis=cost_basis,
                realized_gain=realized_gain,
                gain_percent=gain_percent,
                holding_period_days=holding_period,
                short_term=short_term,
            )
            entries.append(entry)
        
        return entries
    
    # ── Audit Trail ─────────────────────────────────────────────────────────────
    
    def audit_trail(
        self,
        path: str,
        format: str = "json",
    ) -> str:
        """
        Generate audit trail for compliance.
        
        Parameters
        ----------
        path : str
            Output file path.
        format : str
            Output format: "json" or "csv" (default: "json").
        
        Returns
        -------
        str
            Absolute path to the generated audit trail file.
        """
        out_path = Path(path).resolve()
        
        audit_entries = self._generate_audit_entries()
        
        if format == "json":
            data = {
                "generated_at": datetime.now(timezone.utc).isoformat(),
                "engine_type": self._engine.__class__.__name__,
                "audit_entries": [entry.dump() for entry in audit_entries],
            }
            with open(out_path, "w", encoding="utf-8") as f:
                json.dump(data, f, indent=2)
        
        elif format == "csv":
            with open(out_path, "w", newline="", encoding="utf-8") as f:
                writer = csv.writer(f)
                writer.writerow([
                    "Timestamp", "EventType", "Details"
                ])
                
                for entry in audit_entries:
                    writer.writerow([
                        entry.timestamp.isoformat(),
                        entry.event_type,
                        json.dumps(entry.details),
                    ])
        
        else:
            raise ValueError(f"Unsupported format: {format}")
        
        log.info("Audit trail generated at %s", out_path)
        return str(out_path)
    
    def _generate_audit_entries(self) -> list[AuditEntry]:
        """Generate audit entries from order and position history."""
        entries = []
        
        # Add order events
        for oid, order in self._engine._orders.items():
            # Order creation
            if hasattr(order, 'created_at') and order.created_at:
                entries.append(AuditEntry(
                    timestamp=order.created_at,
                    event_type="order_created",
                    details={
                        "order_id": oid,
                        "market": getattr(order, "slug", ""),
                        "side": getattr(order, "side", ""),
                        "price": getattr(order, "price", 0.0),
                        "amount": getattr(order, "amount", 0.0),
                        "is_limit": getattr(order, "is_limit", False),
                    }
                ))
            
            # Order fill
            if order.status == "filled" and order.filled_at:
                entries.append(AuditEntry(
                    timestamp=order.filled_at,
                    event_type="order_filled",
                    details={
                        "order_id": oid,
                        "market": getattr(order, "slug", ""),
                        "side": getattr(order, "side", ""),
                        "fill_price": getattr(order, "price", 0.0),
                        "shares": getattr(order, "shares", 0.0),
                        "fee": getattr(order, "fee", 0.0),
                    }
                ))
        
        # Add position events
        for pid, pos in self._engine._positions.items():
            # Position opened (first order)
            if pos.order_ids:
                first_order = self._engine._orders.get(pos.order_ids[0])
                if first_order and first_order.filled_at:
                    entries.append(AuditEntry(
                        timestamp=first_order.filled_at,
                        event_type="position_opened",
                        details={
                            "position_id": pid,
                            "market": getattr(pos, "slug", ""),
                            "side": getattr(pos, "side", ""),
                            "shares": getattr(pos, "shares", 0.0),
                            "avg_price": getattr(pos, "avg_price", 0.0),
                        }
                    ))
            
            # Position closed/resolved
            if pos.resolved:
                # Use the last order's fill time as close time
                last_order = self._engine._orders.get(pos.order_ids[-1]) if pos.order_ids else None
                close_time = last_order.filled_at if last_order and last_order.filled_at else datetime.now(timezone.utc)
                
                entries.append(AuditEntry(
                    timestamp=close_time,
                    event_type="position_closed",
                    details={
                        "position_id": pid,
                        "market": getattr(pos, "slug", ""),
                        "side": getattr(pos, "side", ""),
                        "outcome": getattr(pos, "outcome", ""),
                        "pnl": getattr(pos, "pnl", 0.0),
                    }
                ))
        
        # Sort by timestamp
        entries.sort(key=lambda e: e.timestamp)
        
        return entries
