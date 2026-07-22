"""
portfolio_analytics.py — Portfolio-level analytics and P&L tracking.

This module provides comprehensive portfolio analytics that go beyond individual
trade analysis, offering portfolio-level insights, time-based performance analysis,
and integrated P&L tracking.

Usage
-----
    client = polyalpha.Client(balance=1000.0)
    
    # ... paper trade ...
    
    # Get portfolio analytics
    analytics = client.paper.portfolio_analytics
    
    # Portfolio-level P&L
    print(analytics.get_portfolio_pnl())
    
    # Time-based performance
    print(analytics.get_daily_performance())
    print(analytics.get_weekly_performance())
    print(analytics.get_monthly_performance())
    
    # Performance metrics
    print(analytics.get_performance_metrics())
    
    # Trade history analytics
    print(analytics.get_trade_history_summary())
"""

from __future__ import annotations

import logging
from collections import defaultdict
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from typing import TYPE_CHECKING, Optional, Union

from .metrics import (
    compute_metrics,
    compute_monthly_returns,
    compute_pnl_by_hour,
    compute_pnl_by_weekday,
)
from .records import TradeRecord, extract_trades, build_equity_curve

if TYPE_CHECKING:
    from ..trading.paper_engine import PaperEngine
    from ..trading.real import RealTradingEngine

log = logging.getLogger(__name__)


# ── Dataclasses ────────────────────────────────────────────────────────────────

@dataclass
class PortfolioPnL:
    """Portfolio-level P&L tracking."""
    
    total_pnl: float
    total_pnl_pct: float
    realized_pnl: float
    unrealized_pnl: float
    total_invested: float
    total_fees: float
    net_fees: float
    current_balance: float
    initial_balance: float
    peak_balance: float
    max_drawdown: float
    max_drawdown_pct: float
    
    def dump(self) -> dict:
        return {
            "total_pnl": round(self.total_pnl, 4),
            "total_pnl_pct": round(self.total_pnl_pct, 4),
            "realized_pnl": round(self.realized_pnl, 4),
            "unrealized_pnl": round(self.unrealized_pnl, 4),
            "total_invested": round(self.total_invested, 4),
            "total_fees": round(self.total_fees, 4),
            "net_fees": round(self.net_fees, 4),
            "current_balance": round(self.current_balance, 4),
            "initial_balance": round(self.initial_balance, 4),
            "peak_balance": round(self.peak_balance, 4),
            "max_drawdown": round(self.max_drawdown, 4),
            "max_drawdown_pct": round(self.max_drawdown_pct, 4),
        }


@dataclass
class TimeBasedPerformance:
    """Time-based performance analysis."""
    
    period: str  # "daily", "weekly", "monthly"
    periods: dict[str, float]  # period_label -> return/pnl
    best_period: tuple[str, float]
    worst_period: tuple[str, float]
    avg_performance: float
    win_rate: float  # percentage of periods with positive returns
    
    def dump(self) -> dict:
        return {
            "period": self.period,
            "periods": {k: round(v, 4) for k, v in self.periods.items()},
            "best_period": {"label": self.best_period[0], "value": round(self.best_period[1], 4)},
            "worst_period": {"label": self.worst_period[0], "value": round(self.worst_period[1], 4)},
            "avg_performance": round(self.avg_performance, 4),
            "win_rate": round(self.win_rate, 4),
        }


@dataclass
class TradeHistorySummary:
    """Trade history analytics summary."""
    
    total_trades: int
    winning_trades: int
    losing_trades: int
    win_rate: float
    profit_factor: float
    avg_win: float
    avg_loss: float
    largest_win: float
    largest_loss: float
    avg_holding_time: float  # in seconds
    total_holding_time: float  # in seconds
    
    def dump(self) -> dict:
        return {
            "total_trades": self.total_trades,
            "winning_trades": self.winning_trades,
            "losing_trades": self.losing_trades,
            "win_rate": round(self.win_rate, 4),
            "profit_factor": round(self.profit_factor, 4),
            "avg_win": round(self.avg_win, 4),
            "avg_loss": round(self.avg_loss, 4),
            "largest_win": round(self.largest_win, 4),
            "largest_loss": round(self.largest_loss, 4),
            "avg_holding_time": round(self.avg_holding_time, 2),
            "total_holding_time": round(self.total_holding_time, 2),
        }


@dataclass
class PerformanceMetrics:
    """Comprehensive performance metrics."""
    
    sharpe_ratio: float
    sortino_ratio: float
    calmar_ratio: float
    omega_ratio: float
    max_drawdown: float
    max_drawdown_pct: float
    expectancy: float
    kelly_fraction: float
    skew: float
    kurtosis: float
    var_95: float
    var_99: float
    cvar_95: float
    cvar_99: float
    
    def dump(self) -> dict:
        return {
            "sharpe_ratio": round(self.sharpe_ratio, 4),
            "sortino_ratio": round(self.sortino_ratio, 4),
            "calmar_ratio": round(self.calmar_ratio, 4),
            "omega_ratio": round(self.omega_ratio, 4),
            "max_drawdown": round(self.max_drawdown, 4),
            "max_drawdown_pct": round(self.max_drawdown_pct, 4),
            "expectancy": round(self.expectancy, 6),
            "kelly_fraction": round(self.kelly_fraction, 4),
            "skew": round(self.skew, 4),
            "kurtosis": round(self.kurtosis, 4),
            "var_95": round(self.var_95, 6),
            "var_99": round(self.var_99, 6),
            "cvar_95": round(self.cvar_95, 6),
            "cvar_99": round(self.cvar_99, 6),
        }


# ── Portfolio Analytics Engine ───────────────────────────────────────────────────

class PortfolioAnalytics:
    """
    Portfolio-level analytics engine.
    
    Provides comprehensive portfolio analytics including P&L tracking,
    time-based performance analysis, and advanced metrics.
    
    Accessed via ``client.paper.portfolio_analytics``.
    
    Parameters
    ----------
    engine : Union[PaperEngine, RealTradingEngine]
        The trading engine to analyze.
    """
    
    def __init__(self, engine: Union["PaperEngine", "RealTradingEngine"]) -> None:
        self._engine = engine
        self._trades_cache: Optional[list[TradeRecord]] = None
        self._cache_timestamp: Optional[datetime] = None
        self._cache_ttl_seconds = 60  # Cache trades for 1 minute
    
    def _refresh_cache(self) -> None:
        """Refresh the trades cache if it's stale."""
        now = datetime.now(timezone.utc)
        if (self._trades_cache is None or 
            self._cache_timestamp is None or 
            (now - self._cache_timestamp).total_seconds() > self._cache_ttl_seconds):
            self._trades_cache = extract_trades(self._engine)
            self._cache_timestamp = now
    
    @property
    def trades(self) -> list[TradeRecord]:
        """Get cached trades, refreshing if stale."""
        self._refresh_cache()
        return self._trades_cache or []
    
    # ── Portfolio-level P&L Tracking ─────────────────────────────────────────────
    
    def get_portfolio_pnl(self) -> PortfolioPnL:
        """
        Get comprehensive portfolio-level P&L tracking.
        
        Returns
        -------
        PortfolioPnL
            Portfolio P&L summary including realized/unrealized P&L,
            fees, drawdown, and balance information.
        """
        trades = self.trades
        positions = self._engine._positions
        
        # Calculate realized P&L from resolved trades
        realized_pnl = sum(t.pnl for t in trades)
        
        # Calculate unrealized P&L from open positions
        unrealized_pnl = sum(p.pnl for p in positions.values() if not p.resolved)
        
        # Total invested and fees
        total_invested = sum(t.amount_in for t in trades)
        total_fees = sum(t.fee for t in trades)
        
        # Get current balance
        current_balance = self._engine._balance
        
        # Calculate initial balance from current balance - net P&L
        total_pnl = realized_pnl + unrealized_pnl
        initial_balance = current_balance - total_pnl
        
        # Calculate peak balance and max drawdown
        timestamps, equity = build_equity_curve(trades, initial_balance)
        peak_balance = max(equity) if equity else current_balance
        max_drawdown = peak_balance - current_balance
        max_drawdown_pct = (max_drawdown / peak_balance * 100) if peak_balance > 0 else 0.0
        
        # Total P&L percentage
        total_pnl_pct = (total_pnl / initial_balance * 100) if initial_balance > 0 else 0.0
        
        # Net fees (after rebates if available)
        net_fees = total_fees
        if hasattr(self._engine, '_fee_manager') and hasattr(self._engine._fee_manager, 'total_rebates_earned'):
            net_fees = total_fees - self._engine._fee_manager.total_rebates_earned
        
        return PortfolioPnL(
            total_pnl=total_pnl,
            total_pnl_pct=total_pnl_pct,
            realized_pnl=realized_pnl,
            unrealized_pnl=unrealized_pnl,
            total_invested=total_invested,
            total_fees=total_fees,
            net_fees=net_fees,
            current_balance=current_balance,
            initial_balance=initial_balance,
            peak_balance=peak_balance,
            max_drawdown=max_drawdown,
            max_drawdown_pct=max_drawdown_pct,
        )
    
    # ── Time-based Performance Analysis ──────────────────────────────────────────
    
    def get_daily_performance(self) -> TimeBasedPerformance:
        """
        Get daily performance analysis.
        
        Returns
        -------
        TimeBasedPerformance
            Daily performance statistics including best/worst days,
            average daily performance, and daily win rate.
        """
        trades = self.trades
        if not trades:
            return TimeBasedPerformance(
                period="daily",
                periods={},
                best_period=("", 0.0),
                worst_period=("", 0.0),
                avg_performance=0.0,
                win_rate=0.0,
            )
        
        # Group P&L by date
        daily_pnl: dict[str, float] = defaultdict(float)
        for t in trades:
            date_str = t.exit_time.strftime("%Y-%m-%d")
            daily_pnl[date_str] += t.pnl
        
        # Calculate statistics
        periods = dict(daily_pnl)
        best_period = max(periods.items(), key=lambda x: x[1]) if periods else ("", 0.0)
        worst_period = min(periods.items(), key=lambda x: x[1]) if periods else ("", 0.0)
        avg_performance = sum(periods.values()) / len(periods) if periods else 0.0
        win_rate = sum(1 for v in periods.values() if v > 0) / len(periods) if periods else 0.0
        
        return TimeBasedPerformance(
            period="daily",
            periods=periods,
            best_period=best_period,
            worst_period=worst_period,
            avg_performance=avg_performance,
            win_rate=win_rate,
        )
    
    def get_weekly_performance(self) -> TimeBasedPerformance:
        """
        Get weekly performance analysis.
        
        Returns
        -------
        TimeBasedPerformance
            Weekly performance statistics.
        """
        trades = self.trades
        if not trades:
            return TimeBasedPerformance(
                period="weekly",
                periods={},
                best_period=("", 0.0),
                worst_period=("", 0.0),
                avg_performance=0.0,
                win_rate=0.0,
            )
        
        # Group P&L by week (ISO week format)
        weekly_pnl: dict[str, float] = defaultdict(float)
        for t in trades:
            year_week = t.exit_time.strftime("%Y-W%W")
            weekly_pnl[year_week] += t.pnl
        
        # Calculate statistics
        periods = dict(weekly_pnl)
        best_period = max(periods.items(), key=lambda x: x[1]) if periods else ("", 0.0)
        worst_period = min(periods.items(), key=lambda x: x[1]) if periods else ("", 0.0)
        avg_performance = sum(periods.values()) / len(periods) if periods else 0.0
        win_rate = sum(1 for v in periods.values() if v > 0) / len(periods) if periods else 0.0
        
        return TimeBasedPerformance(
            period="weekly",
            periods=periods,
            best_period=best_period,
            worst_period=worst_period,
            avg_performance=avg_performance,
            win_rate=win_rate,
        )
    
    def get_monthly_performance(self) -> TimeBasedPerformance:
        """
        Get monthly performance analysis.
        
        Returns
        -------
        TimeBasedPerformance
            Monthly performance statistics.
        """
        trades = self.trades
        if not trades:
            return TimeBasedPerformance(
                period="monthly",
                periods={},
                best_period=("", 0.0),
                worst_period=("", 0.0),
                avg_performance=0.0,
                win_rate=0.0,
            )
        
        # Use existing monthly returns computation
        monthly_returns = compute_monthly_returns(trades, self._engine._balance)
        
        # Convert to P&L instead of percentage
        portfolio_pnl = self.get_portfolio_pnl()
        initial_balance = portfolio_pnl.initial_balance
        
        monthly_pnl: dict[str, float] = {}
        for month, ret_pct in monthly_returns.items():
            # Approximate monthly P&L from return percentage
            monthly_pnl[month] = initial_balance * (ret_pct / 100.0)
        
        # Calculate statistics
        periods = monthly_pnl
        best_period = max(periods.items(), key=lambda x: x[1]) if periods else ("", 0.0)
        worst_period = min(periods.items(), key=lambda x: x[1]) if periods else ("", 0.0)
        avg_performance = sum(periods.values()) / len(periods) if periods else 0.0
        win_rate = sum(1 for v in periods.values() if v > 0) / len(periods) if periods else 0.0
        
        return TimeBasedPerformance(
            period="monthly",
            periods=periods,
            best_period=best_period,
            worst_period=worst_period,
            avg_performance=avg_performance,
            win_rate=win_rate,
        )
    
    def get_hourly_performance(self) -> dict[int, float]:
        """
        Get P&L by hour of day (0-23 UTC).
        
        Returns
        -------
        dict[int, float]
            Hour of day -> total P&L.
        """
        trades = self.trades
        return compute_pnl_by_hour(trades)
    
    def get_weekday_performance(self) -> dict[int, float]:
        """
        Get P&L by day of week (0=Mon, 6=Sun).
        
        Returns
        -------
        dict[int, float]
            Day of week -> total P&L.
        """
        trades = self.trades
        return compute_pnl_by_weekday(trades)
    
    # ── Performance Metrics ────────────────────────────────────────────────────────
    
    def get_performance_metrics(self) -> PerformanceMetrics:
        """
        Get comprehensive performance metrics.
        
        Returns
        -------
        PerformanceMetrics
            Advanced performance metrics including Sharpe, Sortino,
            Calmar, Omega, VaR, CVaR, etc.
        """
        trades = self.trades
        if not trades:
            return PerformanceMetrics(
                sharpe_ratio=float('nan'),
                sortino_ratio=float('nan'),
                calmar_ratio=float('nan'),
                omega_ratio=float('nan'),
                max_drawdown=0.0,
                max_drawdown_pct=0.0,
                expectancy=float('nan'),
                kelly_fraction=float('nan'),
                skew=float('nan'),
                kurtosis=float('nan'),
                var_95=float('nan'),
                var_99=float('nan'),
                cvar_95=float('nan'),
                cvar_99=float('nan'),
            )
        
        portfolio_pnl = self.get_portfolio_pnl()
        initial_balance = portfolio_pnl.initial_balance
        
        # Compute metrics using existing metrics module
        metrics_dict = compute_metrics(
            trades=trades,
            initial_balance=initial_balance,
            metric_keys=[
                "sharpe", "sortino", "calmar", "omega",
                "max_drawdown", "expectancy", "kelly",
                "skew", "kurtosis", "var_95", "var_99", "cvar_95", "cvar_99"
            ],
            risk_free_rate=0.0,
        )
        
        # Extract max drawdown
        max_dd = metrics_dict.get("max_drawdown", {"pct": 0.0, "usd": 0.0})
        max_drawdown_pct = max_dd.get("pct", 0.0) if isinstance(max_dd, dict) else 0.0
        max_drawdown_usd = max_dd.get("usd", 0.0) if isinstance(max_dd, dict) else 0.0
        
        return PerformanceMetrics(
            sharpe_ratio=metrics_dict.get("sharpe", float('nan')),
            sortino_ratio=metrics_dict.get("sortino", float('nan')),
            calmar_ratio=metrics_dict.get("calmar", float('nan')),
            omega_ratio=metrics_dict.get("omega", float('nan')),
            max_drawdown=max_drawdown_usd,
            max_drawdown_pct=max_drawdown_pct,
            expectancy=metrics_dict.get("expectancy", float('nan')),
            kelly_fraction=metrics_dict.get("kelly", float('nan')),
            skew=metrics_dict.get("skew", float('nan')),
            kurtosis=metrics_dict.get("kurtosis", float('nan')),
            var_95=metrics_dict.get("var_95", float('nan')),
            var_99=metrics_dict.get("var_99", float('nan')),
            cvar_95=metrics_dict.get("cvar_95", float('nan')),
            cvar_99=metrics_dict.get("cvar_99", float('nan')),
        )
    
    # ── Trade History Analytics ────────────────────────────────────────────────────
    
    def get_trade_history_summary(self) -> TradeHistorySummary:
        """
        Get trade history analytics summary.
        
        Returns
        -------
        TradeHistorySummary
            Summary of trade history including win rate, profit factor,
            average win/loss, and holding time statistics.
        """
        trades = self.trades
        if not trades:
            return TradeHistorySummary(
                total_trades=0,
                winning_trades=0,
                losing_trades=0,
                win_rate=0.0,
                profit_factor=0.0,
                avg_win=0.0,
                avg_loss=0.0,
                largest_win=0.0,
                largest_loss=0.0,
                avg_holding_time=0.0,
                total_holding_time=0.0,
            )
        
        winning_trades = [t for t in trades if t.pnl > 0]
        losing_trades = [t for t in trades if t.pnl < 0]
        
        total_trades = len(trades)
        win_rate = len(winning_trades) / total_trades if total_trades > 0 else 0.0
        
        # Profit factor
        gross_profit = sum(t.pnl for t in winning_trades)
        gross_loss = abs(sum(t.pnl for t in losing_trades))
        profit_factor = gross_profit / gross_loss if gross_loss > 0 else float('inf')
        
        # Average win/loss
        avg_win = sum(t.pnl for t in winning_trades) / len(winning_trades) if winning_trades else 0.0
        avg_loss = sum(t.pnl for t in losing_trades) / len(losing_trades) if losing_trades else 0.0
        
        # Largest win/loss
        largest_win = max((t.pnl for t in winning_trades), default=0.0)
        largest_loss = min((t.pnl for t in losing_trades), default=0.0)
        
        # Holding time statistics
        holding_times = [t.holding_secs for t in trades]
        avg_holding_time = sum(holding_times) / len(holding_times) if holding_times else 0.0
        total_holding_time = sum(holding_times)
        
        return TradeHistorySummary(
            total_trades=total_trades,
            winning_trades=len(winning_trades),
            losing_trades=len(losing_trades),
            win_rate=win_rate,
            profit_factor=profit_factor,
            avg_win=avg_win,
            avg_loss=avg_loss,
            largest_win=largest_win,
            largest_loss=largest_loss,
            avg_holding_time=avg_holding_time,
            total_holding_time=total_holding_time,
        )
    
    # ── Summary Report ────────────────────────────────────────────────────────────
    
    def generate_summary_report(self) -> str:
        """
        Generate a comprehensive portfolio summary report.
        
        Returns
        -------
        str
            Formatted summary report with all key metrics.
        """
        portfolio_pnl = self.get_portfolio_pnl()
        daily_perf = self.get_daily_performance()
        weekly_perf = self.get_weekly_performance()
        monthly_perf = self.get_monthly_performance()
        trade_summary = self.get_trade_history_summary()
        perf_metrics = self.get_performance_metrics()
        
        lines = [
            "=" * 80,
            "  PORTFOLIO ANALYTICS SUMMARY",
            "=" * 80,
            "",
            "  Portfolio P&L",
            "-" * 40,
            f"  Total P&L:           ${portfolio_pnl.total_pnl:>10.2f} ({portfolio_pnl.total_pnl_pct:>6.2f}%)",
            f"  Realized P&L:        ${portfolio_pnl.realized_pnl:>10.2f}",
            f"  Unrealized P&L:      ${portfolio_pnl.unrealized_pnl:>10.2f}",
            f"  Current Balance:     ${portfolio_pnl.current_balance:>10.2f}",
            f"  Peak Balance:        ${portfolio_pnl.peak_balance:>10.2f}",
            f"  Max Drawdown:        ${portfolio_pnl.max_drawdown:>10.2f} ({portfolio_pnl.max_drawdown_pct:>6.2f}%)",
            f"  Total Fees:          ${portfolio_pnl.total_fees:>10.2f}",
            f"  Net Fees:            ${portfolio_pnl.net_fees:>10.2f}",
            "",
            "  Trade History",
            "-" * 40,
            f"  Total Trades:        {trade_summary.total_trades:>10}",
            f"  Winning Trades:      {trade_summary.winning_trades:>10}",
            f"  Losing Trades:       {trade_summary.losing_trades:>10}",
            f"  Win Rate:            {trade_summary.win_rate:>10.2%}",
            f"  Profit Factor:       {trade_summary.profit_factor:>10.2f}",
            f"  Avg Win:             ${trade_summary.avg_win:>10.2f}",
            f"  Avg Loss:            ${trade_summary.avg_loss:>10.2f}",
            f"  Largest Win:         ${trade_summary.largest_win:>10.2f}",
            f"  Largest Loss:        ${trade_summary.largest_loss:>10.2f}",
            f"  Avg Holding Time:    {trade_summary.avg_holding_time:>10.1f}s",
            "",
            "  Performance Metrics",
            "-" * 40,
            f"  Sharpe Ratio:        {perf_metrics.sharpe_ratio:>10.4f}",
            f"  Sortino Ratio:       {perf_metrics.sortino_ratio:>10.4f}",
            f"  Calmar Ratio:        {perf_metrics.calmar_ratio:>10.4f}",
            f"  Omega Ratio:         {perf_metrics.omega_ratio:>10.4f}",
            f"  Expectancy:         {perf_metrics.expectancy:>10.6f}",
            f"  Kelly Fraction:      {perf_metrics.kelly_fraction:>10.4f}",
            f"  Skew:               {perf_metrics.skew:>10.4f}",
            f"  Kurtosis:           {perf_metrics.kurtosis:>10.4f}",
            f"  VaR (95%):           {perf_metrics.var_95:>10.6f}",
            f"  VaR (99%):           {perf_metrics.var_99:>10.6f}",
            f"  CVaR (95%):          {perf_metrics.cvar_95:>10.6f}",
            f"  CVaR (99%):          {perf_metrics.cvar_99:>10.6f}",
            "",
            "  Time-based Performance",
            "-" * 40,
            f"  Best Day:            {daily_perf.best_period[0]:>12} ${daily_perf.best_period[1]:>8.2f}",
            f"  Worst Day:           {daily_perf.worst_period[0]:>12} ${daily_perf.worst_period[1]:>8.2f}",
            f"  Daily Win Rate:      {daily_perf.win_rate:>10.2%}",
            f"  Best Week:           {weekly_perf.best_period[0]:>12} ${weekly_perf.best_period[1]:>8.2f}",
            f"  Worst Week:          {weekly_perf.worst_period[0]:>12} ${weekly_perf.worst_period[1]:>8.2f}",
            f"  Weekly Win Rate:     {weekly_perf.win_rate:>10.2%}",
            f"  Best Month:          {monthly_perf.best_period[0]:>12} ${monthly_perf.best_period[1]:>8.2f}",
            f"  Worst Month:         {monthly_perf.worst_period[0]:>12} ${monthly_perf.worst_period[1]:>8.2f}",
            f"  Monthly Win Rate:    {monthly_perf.win_rate:>10.2%}",
            "",
            "=" * 80,
        ]
        
        return "\n".join(lines)
    
    def print_summary(self) -> None:
        """Print the portfolio summary report to stdout."""
        print(self.generate_summary_report())
