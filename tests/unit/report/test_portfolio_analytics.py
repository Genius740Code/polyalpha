"""
Portfolio analytics tests — run with: pytest tests/unit/report/test_portfolio_analytics.py
"""

import uuid
from datetime import datetime, timedelta, timezone

import pytest

from polyalpha.report.portfolio_analytics import (
    PerformanceMetrics,
    PortfolioAnalytics,
    PortfolioPnL,
    TimeBasedPerformance,
    TradeHistorySummary,
)
from polyalpha.trading.paper import PaperEngine, PaperOrder, PaperPosition


# ── Fixtures ──────────────────────────────────────────────────────────────────

@pytest.fixture
def engine_with_trades():
    """Build a PaperEngine with synthetic resolved positions."""
    engine = PaperEngine(balance=1000.0)
    base = datetime(2025, 1, 1, tzinfo=timezone.utc)

    for i, (pnl, outcome) in enumerate([
        (5.0, "WON"), (-3.0, "LOST"), (8.0, "WON"),
        (-2.0, "LOST"), (4.0, "WON"),
    ]):
        market_id = f"mkt_{i:04d}"
        slug = f"btc-updown-5m-{i:04d}"
        side = "UP"
        entry_price = 0.70
        amount_in = 10.0
        shares = (amount_in * 0.98) / entry_price

        entry_time = base + timedelta(hours=i)
        exit_time = entry_time + timedelta(minutes=30)

        order_id = str(uuid.uuid4())
        order = PaperOrder(
            id=order_id,
            market_id=market_id,
            slug=slug,
            side=side,
            price=entry_price,
            amount=amount_in,
            shares=shares,
            fee=amount_in * 0.02,
            status="filled",
            is_limit=False,
            filled_at=exit_time,
        )
        engine._orders[order_id] = order
        engine._balance += pnl

        engine._positions[f"{market_id}:{side}"] = PaperPosition(
            market_id=market_id,
            slug=slug,
            question=f"Will BTC rise? #{i}",
            side=side,
            shares=shares,
            avg_price=entry_price,
            current_price=1.0 if outcome == "WON" else 0.0,
            resolved=True,
            outcome=outcome,
            order_ids=[order_id],
        )

    return engine


@pytest.fixture
def empty_engine():
    """Build a PaperEngine with no trades."""
    return PaperEngine(balance=1000.0)


# ── Dataclass dump tests ──────────────────────────────────────────────────────

@pytest.mark.unit
class TestPortfolioPnL:
    """Test PortfolioPnL dataclass."""

    def test_dump_returns_dict(self):
        pnl = PortfolioPnL(
            total_pnl=100.0, total_pnl_pct=10.0,
            realized_pnl=80.0, unrealized_pnl=20.0,
            total_invested=500.0, total_fees=25.0, net_fees=20.0,
            current_balance=1100.0, initial_balance=1000.0,
            peak_balance=1200.0, max_drawdown=-50.0, max_drawdown_pct=-5.0,
        )
        d = pnl.dump()
        assert d["total_pnl"] == 100.0
        assert d["total_pnl_pct"] == 10.0
        assert d["realized_pnl"] == 80.0
        assert d["initial_balance"] == 1000.0
        assert d["max_drawdown"] == -50.0


@pytest.mark.unit
class TestTimeBasedPerformance:
    """Test TimeBasedPerformance dataclass."""

    def test_dump_returns_dict(self):
        tp = TimeBasedPerformance(
            period="daily",
            periods={"2025-01-01": 10.0, "2025-01-02": -5.0},
            best_period=("2025-01-01", 10.0),
            worst_period=("2025-01-02", -5.0),
            avg_performance=2.5,
            win_rate=0.5,
        )
        d = tp.dump()
        assert d["period"] == "daily"
        assert d["best_period"]["label"] == "2025-01-01"
        assert d["best_period"]["value"] == 10.0
        assert d["win_rate"] == 0.5

    def test_dump_empty_periods(self):
        tp = TimeBasedPerformance(
            period="daily", periods={},
            best_period=("", 0.0), worst_period=("", 0.0),
            avg_performance=0.0, win_rate=0.0,
        )
        d = tp.dump()
        assert d["periods"] == {}
        assert d["avg_performance"] == 0.0


@pytest.mark.unit
class TestTradeHistorySummary:
    """Test TradeHistorySummary dataclass."""

    def test_dump_returns_dict(self):
        th = TradeHistorySummary(
            total_trades=10, winning_trades=6, losing_trades=4,
            win_rate=0.6, profit_factor=2.5,
            avg_win=15.0, avg_loss=-8.0,
            largest_win=30.0, largest_loss=-12.0,
            avg_holding_time=3600.0, total_holding_time=36000.0,
        )
        d = th.dump()
        assert d["total_trades"] == 10
        assert d["win_rate"] == 0.6
        assert d["profit_factor"] == 2.5
        assert d["avg_holding_time"] == 3600.0


@pytest.mark.unit
class TestPerformanceMetrics:
    """Test PerformanceMetrics dataclass."""

    def test_dump_returns_dict(self):
        pm = PerformanceMetrics(
            sharpe_ratio=1.5, sortino_ratio=2.0, calmar_ratio=1.2,
            omega_ratio=1.8, max_drawdown=-100.0, max_drawdown_pct=-10.0,
            expectancy=0.05, kelly_fraction=0.25,
            skew=0.1, kurtosis=-0.5,
            var_95=0.02, var_99=0.05, cvar_95=0.03, cvar_99=0.06,
        )
        d = pm.dump()
        assert d["sharpe_ratio"] == 1.5
        assert d["sortino_ratio"] == 2.0
        assert d["expectancy"] == 0.05
        assert d["var_95"] == 0.02


# ── PortfolioAnalytics tests ─────────────────────────────────────────────────

@pytest.mark.unit
class TestPortfolioAnalyticsInit:
    """Test PortfolioAnalytics initialization."""

    def test_init_creates_analytics(self, empty_engine):
        """Test initialization with empty engine."""
        pa = PortfolioAnalytics(empty_engine)
        assert pa._engine is empty_engine
        assert pa._trades_cache is None

    def test_trades_property_empty(self, empty_engine):
        """Test trades property returns empty list."""
        pa = PortfolioAnalytics(empty_engine)
        assert pa.trades == []

    def test_trades_property_cached(self, engine_with_trades):
        """Test trades property caches results."""
        pa = PortfolioAnalytics(engine_with_trades)
        t1 = pa.trades
        t2 = pa.trades
        assert t1 is t2  # Same cached object

    def test_cache_refresh(self, engine_with_trades):
        """Test cache refreshes after TTL."""
        pa = PortfolioAnalytics(engine_with_trades)
        pa._cache_ttl_seconds = 0
        t1 = pa.trades
        t2 = pa.trades
        assert t1 is not t2


@pytest.mark.unit
class TestPortfolioPnLMethod:
    """Test get_portfolio_pnl."""

    def test_empty_engine(self, empty_engine):
        """Test P&L with no trades."""
        pa = PortfolioAnalytics(empty_engine)
        pnl = pa.get_portfolio_pnl()
        assert pnl.total_pnl == 0.0
        assert pnl.realized_pnl == 0.0
        assert pnl.unrealized_pnl == 0.0
        assert pnl.current_balance == 1000.0
        assert pnl.initial_balance == 1000.0

    def test_with_trades(self, engine_with_trades):
        """Test P&L with resolved trades."""
        pa = PortfolioAnalytics(engine_with_trades)
        pnl = pa.get_portfolio_pnl()
        # 3 wins @ +4.2 each + 2 losses @ -9.8 each = 12.6 - 19.6 = -7.0
        assert pnl.realized_pnl == pytest.approx(-7.0, abs=0.1)
        assert pnl.total_invested > 0
        assert isinstance(pnl.dump(), dict)

    def test_with_open_positions(self, empty_engine):
        """Test P&L with an open (unresolved) position."""
        empty_engine._positions["mkt_01:UP"] = PaperPosition(
            market_id="mkt_01", slug="btc-1", question="q", side="UP",
            shares=10.0, avg_price=0.7, current_price=0.8,
            resolved=False, outcome=None, order_ids=[],
        )
        pa = PortfolioAnalytics(empty_engine)
        pnl = pa.get_portfolio_pnl()
        assert pnl.unrealized_pnl != 0.0


@pytest.mark.unit
class TestDailyPerformance:
    """Test get_daily_performance."""

    def test_empty_returns_defaults(self, empty_engine):
        """Test daily performance with no trades."""
        pa = PortfolioAnalytics(empty_engine)
        dp = pa.get_daily_performance()
        assert dp.period == "daily"
        assert dp.periods == {}
        assert dp.win_rate == 0.0

    def test_with_trades(self, engine_with_trades):
        """Test daily performance with trades."""
        pa = PortfolioAnalytics(engine_with_trades)
        dp = pa.get_daily_performance()
        assert dp.period == "daily"
        assert len(dp.periods) > 0
        assert dp.best_period[0] != ""
        assert dp.worst_period[0] != ""
        assert isinstance(dp.dump(), dict)


@pytest.mark.unit
class TestWeeklyPerformance:
    """Test get_weekly_performance."""

    def test_empty_returns_defaults(self, empty_engine):
        """Test weekly performance with no trades."""
        pa = PortfolioAnalytics(empty_engine)
        wp = pa.get_weekly_performance()
        assert wp.period == "weekly"
        assert wp.periods == {}
        assert wp.win_rate == 0.0

    def test_with_trades(self, engine_with_trades):
        """Test weekly performance with trades."""
        pa = PortfolioAnalytics(engine_with_trades)
        wp = pa.get_weekly_performance()
        assert wp.period == "weekly"
        assert len(wp.periods) > 0


@pytest.mark.unit
class TestMonthlyPerformance:
    """Test get_monthly_performance."""

    def test_empty_returns_defaults(self, empty_engine):
        """Test monthly performance with no trades."""
        pa = PortfolioAnalytics(empty_engine)
        mp = pa.get_monthly_performance()
        assert mp.period == "monthly"
        assert mp.periods == {}

    def test_with_trades(self, engine_with_trades):
        """Test monthly performance with trades."""
        pa = PortfolioAnalytics(engine_with_trades)
        mp = pa.get_monthly_performance()
        assert mp.period == "monthly"


@pytest.mark.unit
class TestHourlyAndWeekdayPerformance:
    """Test hourly and weekday performance."""

    def test_hourly_empty(self, empty_engine):
        pa = PortfolioAnalytics(empty_engine)
        result = pa.get_hourly_performance()
        assert result == {}

    def test_hourly_with_trades(self, engine_with_trades):
        pa = PortfolioAnalytics(engine_with_trades)
        result = pa.get_hourly_performance()
        assert isinstance(result, dict)

    def test_weekday_empty(self, empty_engine):
        pa = PortfolioAnalytics(empty_engine)
        result = pa.get_weekday_performance()
        assert result == {}

    def test_weekday_with_trades(self, engine_with_trades):
        pa = PortfolioAnalytics(engine_with_trades)
        result = pa.get_weekday_performance()
        assert isinstance(result, dict)


@pytest.mark.unit
class TestPerformanceMetricsMethod:
    """Test get_performance_metrics."""

    def test_empty_returns_nan_defaults(self, empty_engine):
        """Test performance metrics with no trades."""
        import math
        pa = PortfolioAnalytics(empty_engine)
        pm = pa.get_performance_metrics()
        assert math.isnan(pm.sharpe_ratio)
        assert pm.max_drawdown == 0.0

    def test_with_trades(self, engine_with_trades):
        """Test performance metrics with trades."""
        pa = PortfolioAnalytics(engine_with_trades)
        pm = pa.get_performance_metrics()
        assert isinstance(pm.dump(), dict)

    def test_dump_rounds_values(self, engine_with_trades):
        """Test dump rounds values."""
        pa = PortfolioAnalytics(engine_with_trades)
        pm = pa.get_performance_metrics()
        d = pm.dump()
        for key, val in d.items():
            assert val is None or isinstance(val, (int, float))


@pytest.mark.unit
class TestTradeHistorySummaryMethod:
    """Test get_trade_history_summary."""

    def test_empty_returns_defaults(self, empty_engine):
        """Test trade history summary with no trades."""
        pa = PortfolioAnalytics(empty_engine)
        th = pa.get_trade_history_summary()
        assert th.total_trades == 0
        assert th.win_rate == 0.0
        assert th.profit_factor == 0.0

    def test_with_trades(self, engine_with_trades):
        """Test trade history summary with trades."""
        pa = PortfolioAnalytics(engine_with_trades)
        th = pa.get_trade_history_summary()
        assert th.total_trades == 5
        assert th.winning_trades == 3
        assert th.losing_trades == 2
        assert th.win_rate == pytest.approx(0.6, abs=0.01)
        assert th.total_holding_time >= 0
        assert isinstance(th.dump(), dict)

    def test_profit_factor_inf_all_wins(self, empty_engine):
        """Test profit factor is infinite with all winning trades."""
        engine = PaperEngine(balance=100.0)
        base = datetime(2025, 1, 1, tzinfo=timezone.utc)
        order_id = str(uuid.uuid4())
        engine._orders[order_id] = PaperOrder(
            id=order_id, market_id="mkt_00", slug="btc-1", side="UP",
            price=0.7, amount=10.0, shares=14.0, fee=0.2,
            status="filled", is_limit=False, filled_at=base,
        )
        engine._positions["mkt_00:UP"] = PaperPosition(
            market_id="mkt_00", slug="btc-1", question="q", side="UP",
            shares=14.0, avg_price=0.7, current_price=1.0,
            resolved=True, outcome="WON", order_ids=[order_id],
        )
        engine._balance = 110.0

        pa = PortfolioAnalytics(engine)
        th = pa.get_trade_history_summary()
        assert th.profit_factor == float('inf')
        assert th.winning_trades == 1
        assert th.losing_trades == 0

    def test_all_losses_profit_factor_zero(self, empty_engine):
        """Test profit factor is 0 with all losing trades."""
        engine = PaperEngine(balance=90.0)
        base = datetime(2025, 1, 1, tzinfo=timezone.utc)
        order_id = str(uuid.uuid4())
        engine._orders[order_id] = PaperOrder(
            id=order_id, market_id="mkt_00", slug="btc-1", side="UP",
            price=0.7, amount=10.0, shares=14.0, fee=0.2,
            status="filled", is_limit=False, filled_at=base,
        )
        engine._positions["mkt_00:UP"] = PaperPosition(
            market_id="mkt_00", slug="btc-1", question="q", side="UP",
            shares=14.0, avg_price=0.7, current_price=0.0,
            resolved=True, outcome="LOST", order_ids=[order_id],
        )
        pa = PortfolioAnalytics(engine)
        th = pa.get_trade_history_summary()
        assert th.profit_factor == 0.0


@pytest.mark.unit
class TestGenerateSummaryReport:
    """Test generate_summary_report."""

    def test_empty_engine_returns_string(self, empty_engine):
        """Test summary report with no trades."""
        pa = PortfolioAnalytics(empty_engine)
        report = pa.generate_summary_report()
        assert isinstance(report, str)
        assert "PORTFOLIO ANALYTICS SUMMARY" in report

    def test_with_trades_returns_string(self, engine_with_trades):
        """Test summary report with trades."""
        pa = PortfolioAnalytics(engine_with_trades)
        report = pa.generate_summary_report()
        assert isinstance(report, str)
        assert "Total P&L" in report
        assert "Trade History" in report
        assert "Performance Metrics" in report

    def test_print_summary(self, engine_with_trades, capsys):
        """Test print_summary prints to stdout."""
        pa = PortfolioAnalytics(engine_with_trades)
        pa.print_summary()
        captured = capsys.readouterr()
        assert "PORTFOLIO ANALYTICS SUMMARY" in captured.out


@pytest.mark.unit
class TestNetFeesWithRebates:
    """Test net fees with rebates."""

    def test_rebates_deducted(self, empty_engine):
        """Test net fees deducts rebates."""
        empty_engine._fee_manager.total_rebates_earned = 5.0
        empty_engine._balance = 1000.0
        pa = PortfolioAnalytics(empty_engine)
        pnl = pa.get_portfolio_pnl()
        assert pnl.net_fees == -5.0  # 0 fees - 5 rebates

    def test_no_rebates_net_equals_total(self, empty_engine):
        """Test net fees equals total fees when no rebates."""
        pa = PortfolioAnalytics(empty_engine)
        pnl = pa.get_portfolio_pnl()
        assert pnl.net_fees == pnl.total_fees
