"""
Report metrics tests — run with: pytest tests/unit/report/test_metrics.py
"""

import math
import uuid
from datetime import datetime, timedelta, timezone

import pytest

from polyalpha.report.metrics import (
    compute_metrics,
    compute_rolling_sharpe,
    compute_underwater_curve,
    _sharpe,
    _sortino,
    _max_drawdown,
    _profit_factor,
    _expectancy,
    _calmar,
    _omega,
    _kurtosis,
    _var,
    _cvar,
    _kelly,
    _max_consecutive,
    _pnl_concentration,
    _deflated_sharpe,
    _annualisation_factor,
    _build_equity_array,
)
from polyalpha.report.presets import DEFAULT_METRICS, OPTIONAL_METRICS


@pytest.fixture
def make_trade():
    """Helper to create a TradeRecord."""
    def _make_trade(
        pnl: float,
        entry_price: float = 0.70,
        holding_secs: float = 300.0,
        side: str = "UP",
        outcome: str | None = None,
        fill_type: str = "market",
        entry_time: datetime | None = None,
        amount_in: float = 10.0,
    ):
        if outcome is None:
            outcome = "WON" if pnl > 0 else "LOST"
        if entry_time is None:
            entry_time = datetime(2025, 1, 1, 0, 0, 0, tzinfo=timezone.utc)
        exit_time = entry_time + timedelta(seconds=holding_secs)
        exit_price = 1.0 if outcome == "WON" else 0.0
        pnl_pct = (pnl / amount_in) * 100 if amount_in else 0.0
        from polyalpha.report.records import TradeRecord
        return TradeRecord(
            trade_id=str(uuid.uuid4()),
            market_slug="btc-updown-5m-0001",
            market_id="mkt_001",
            side=side,
            entry_price=entry_price,
            exit_price=exit_price,
            shares=amount_in / entry_price if entry_price else 0.0,
            amount_in=amount_in,
            fee=0.0,
            pnl=pnl,
            pnl_pct=pnl_pct,
            entry_time=entry_time,
            exit_time=exit_time,
            holding_secs=holding_secs,
            outcome=outcome,
            fill_type=fill_type,
            slippage=0.0,
            order_count=1,
        )
    return _make_trade


@pytest.fixture
def make_trades_sequence():
    """Create a sequence of trades with timestamps 1 day apart."""
    def _make_trades_sequence(pnls: list[float], base: datetime | None = None):
        if base is None:
            base = datetime(2025, 1, 1, tzinfo=timezone.utc)
        trades = []
        for i, p in enumerate(pnls):
            t = make_trade()(pnl=p, entry_time=base + timedelta(days=i), amount_in=10.0)
            trades.append(t)
        return trades
    return _make_trades_sequence


@pytest.mark.unit
class TestMetricHelpers:
    """Test metric helper functions."""

    def test_ann_factor_single_trade(self, make_trade):
        """Test annualisation factor for single trade."""
        trades = [make_trade(1.0)]
        f = _annualisation_factor(trades)
        assert f == pytest.approx(math.sqrt(252), rel=0.01)

    def test_ann_factor_many_trades(self, make_trade):
        """Test annualisation factor for many trades."""
        base = datetime(2025, 1, 1, tzinfo=timezone.utc)
        trades = [make_trade(1.0, entry_time=base + timedelta(days=i)) for i in range(365)]
        f = _annualisation_factor(trades)
        assert math.isfinite(f) and f > 0

    def test_equity_array_length(self, make_trades_sequence):
        """Test equity array length."""
        trades = make_trades_sequence([1, -1, 2])
        eq = _build_equity_array(trades, 100.0)
        assert len(eq) == 4

    def test_equity_array_correct(self, make_trades_sequence):
        """Test equity array correctness."""
        trades = make_trades_sequence([10, -5, 3])
        eq = _build_equity_array(trades, 100.0)
        assert eq[0] == 100.0
        assert eq[1] == pytest.approx(110.0)
        assert eq[2] == pytest.approx(105.0)
        assert eq[3] == pytest.approx(108.0)

    def test_sharpe_nan_single_return(self):
        """Test Sharpe returns NaN for single return."""
        assert math.isnan(_sharpe([0.1], 1.0))

    def test_sharpe_nan_zero_std(self):
        """Test Sharpe returns NaN for zero std dev."""
        assert math.isnan(_sharpe([0.1, 0.1, 0.1], 1.0))

    def test_sharpe_positive_for_positive_mean(self):
        """Test Sharpe is positive for positive mean."""
        returns = [0.05, 0.03, 0.07, 0.04, 0.06]
        s = _sharpe(returns, 1.0)
        assert s > 0

    def test_sharpe_negative_for_negative_mean(self):
        """Test Sharpe is negative for negative mean."""
        returns = [-0.05, -0.03, -0.07]
        s = _sharpe(returns, 1.0)
        assert s < 0

    def test_sharpe_annualised_scales_with_factor(self):
        """Test Sharpe annualisation scales with factor."""
        returns = [0.1, -0.05, 0.08, 0.03]
        s1 = _sharpe(returns, 1.0)
        s2 = _sharpe(returns, 2.0)
        assert pytest.approx(s2, rel=0.001) == s1 * 2.0

    def test_sortino_inf_no_losses(self):
        """Test Sortino is infinite with no losses."""
        returns = [0.1, 0.2, 0.3]
        s = _sortino(returns, 1.0)
        assert math.isinf(s) and s > 0

    def test_sortino_nan_single_return(self):
        """Test Sortino returns NaN for single return."""
        assert math.isnan(_sortino([0.1], 1.0))

    def test_sortino_positive_for_positive_mean(self):
        """Test Sortino is positive for positive mean."""
        returns = [0.1, -0.02, 0.05, 0.08, -0.01]
        s = _sortino(returns, 1.0)
        assert s > 0

    def test_sortino_ge_sharpe_always(self):
        """Test Sortino >= Sharpe when there are losses."""
        returns = [0.1, -0.02, 0.05, 0.08, -0.01, 0.04]
        s = _sharpe(returns, 1.0)
        so = _sortino(returns, 1.0)
        if math.isfinite(so) and math.isfinite(s):
            assert so >= s

    def test_max_drawdown_zero_for_monotone_up(self):
        """Test max drawdown is zero for monotonic up."""
        eq = [100, 110, 120, 130]
        dd_pct, dd_usd = _max_drawdown(eq)
        assert dd_pct == 0.0
        assert dd_usd == 0.0

    def test_max_drawdown_correct(self):
        """Test max drawdown calculation."""
        eq = [100, 120, 90]
        dd_pct, dd_usd = _max_drawdown(eq)
        assert dd_pct == pytest.approx(-25.0, abs=0.001)
        assert dd_usd == pytest.approx(-30.0, abs=0.001)

    def test_max_drawdown_picks_largest(self):
        """Test max drawdown picks largest drawdown."""
        eq = [100, 110, 99, 120, 90]
        dd_pct, _ = _max_drawdown(eq)
        assert dd_pct == pytest.approx(-25.0, abs=0.001)

    def test_max_drawdown_single_point(self):
        """Test max drawdown for single point."""
        dd_pct, dd_usd = _max_drawdown([100])
        assert dd_pct == 0.0

    def test_profit_factor_basic(self):
        """Test profit factor basic calculation."""
        pnls = [10, -5, 8, -4]
        pf = _profit_factor(pnls)
        assert pf == pytest.approx(18.0 / 9.0, abs=0.0001)

    def test_profit_factor_no_losses_is_inf(self):
        """Test profit factor is infinite with no losses."""
        assert math.isinf(_profit_factor([10, 20, 30]))

    def test_profit_factor_all_losses_is_nan(self):
        """Test profit factor is NaN with all losses."""
        pf = _profit_factor([-5, -10])
        assert math.isnan(pf)

    def test_expectancy_positive_edge(self, make_trades_sequence):
        """Test expectancy with positive edge."""
        trades = make_trades_sequence([10, 10, -5])
        wins = [t for t in trades if t.pnl > 0]
        losses = [t for t in trades if t.pnl < 0]
        returns = [t.pnl_pct / 100 for t in trades]
        e = _expectancy(returns, wins, losses, len(trades))
        assert e > 0

    def test_expectancy_negative_edge(self, make_trades_sequence):
        """Test expectancy with negative edge."""
        trades = make_trades_sequence([2, -10, -10])
        wins = [t for t in trades if t.pnl > 0]
        losses = [t for t in trades if t.pnl < 0]
        returns = [t.pnl_pct / 100 for t in trades]
        e = _expectancy(returns, wins, losses, len(trades))
        assert e < 0

    def test_omega_positive_mean(self):
        """Test Omega ratio with positive mean."""
        returns = [0.1, 0.05, -0.02, 0.08]
        w = _omega(returns)
        assert w > 1.0

    def test_omega_no_losses_is_inf(self):
        """Test Omega is infinite with no losses."""
        returns = [0.1, 0.2, 0.3]
        w = _omega(returns)
        assert math.isinf(w)

    def test_kelly_positive_edge(self, make_trade):
        """Test Kelly criterion with positive edge."""
        wins = [make_trade(10.0, amount_in=10.0) for _ in range(7)]
        losses = [make_trade(-4.0, amount_in=10.0) for _ in range(3)]
        k = _kelly(wins, losses, 10)
        assert 0 < k <= 1.0

    def test_kelly_no_wins_returns_nan(self, make_trade):
        """Test Kelly returns NaN with no wins."""
        losses = [make_trade(-5.0, amount_in=10.0)]
        k = _kelly([], losses, 1)
        assert math.isnan(k)

    def test_kelly_clamped(self, make_trade):
        """Test Kelly is clamped to 1.0."""
        wins = [make_trade(100.0, amount_in=10.0)]
        losses = [make_trade(-0.001, amount_in=10.0)]
        k = _kelly(wins, losses, 2)
        assert k <= 1.0

    def test_var_95_less_than_var_99(self):
        """Test 95% VaR is less than 99% VaR."""
        returns = [-0.1, -0.05, -0.02, 0.01, 0.03, 0.05] * 5
        var95 = _var(returns, 0.05)
        var99 = _var(returns, 0.01)
        assert var99 >= var95

    def test_var_positive_loss_figure(self):
        """Test VaR returns positive loss figure."""
        returns = [-0.10, -0.05, 0.01, 0.02, 0.03]
        v = _var(returns, 0.05)
        assert v >= 0

    def test_cvar_ge_var(self):
        """Test CVaR >= VaR."""
        returns = [-0.15, -0.10, -0.05, 0.01, 0.03, 0.07] * 3
        v95 = _var(returns, 0.05)
        c95 = _cvar(returns, 0.05)
        assert c95 >= v95

    def test_max_consec_wins(self, make_trades_sequence):
        """Test max consecutive wins."""
        trades = make_trades_sequence([1, 1, 1, -1, 1, 1])
        assert _max_consecutive(trades, win=True) == 3

    def test_max_consec_losses(self, make_trades_sequence):
        """Test max consecutive losses."""
        trades = make_trades_sequence([1, -1, -1, -1, 1, -1])
        assert _max_consecutive(trades, win=False) == 3

    def test_max_consec_all_wins(self, make_trades_sequence):
        """Test max consecutive with all wins."""
        trades = make_trades_sequence([1, 2, 3])
        assert _max_consecutive(trades, win=True) == 3
        assert _max_consecutive(trades, win=False) == 0

    def test_kurtosis_normal_approx_zero(self):
        """Test kurtosis is approximately zero for normal distribution."""
        import random as _rand
        rng = _rand.Random(0)
        returns = [rng.gauss(0, 1) for _ in range(10000)]
        k = _kurtosis(returns)
        assert abs(k) < 0.3

    def test_kurtosis_nan_small_sample(self):
        """Test kurtosis returns NaN for small sample."""
        assert math.isnan(_kurtosis([0.1, 0.2, 0.3]))

    def test_pnl_concentration_top1_from_2(self):
        """Test P&L concentration for top 1 of 2."""
        pnls = [100.0, 10.0]
        c = _pnl_concentration(pnls, n=1)
        assert c == pytest.approx(100.0 / 110.0, abs=0.0001)

    def test_pnl_concentration_all_losses_nan(self):
        """Test P&L concentration returns NaN for all losses."""
        assert math.isnan(_pnl_concentration([-5, -10]))

    def test_deflated_sharpe_between_0_and_1(self):
        """Test deflated Sharpe is between 0 and 1."""
        returns = [0.05, -0.02, 0.03, 0.07, 0.01, -0.01, 0.04] * 5
        dsr = _deflated_sharpe(returns, 1.0)
        if math.isfinite(dsr):
            assert 0 <= dsr <= 1

    def test_deflated_sharpe_nan_small_sample(self):
        """Test deflated Sharpe returns NaN for small sample."""
        assert math.isnan(_deflated_sharpe([0.1, 0.2], 1.0))


@pytest.mark.unit
class TestComputeMetrics:
    """Test compute_metrics function."""

    def test_empty_trades_all_none(self):
        """Test all metrics are None for empty trades."""
        m = compute_metrics([], 100.0, DEFAULT_METRICS)
        assert all(v is None for v in m.values())

    def test_all_default_metrics_present(self, make_trades_sequence):
        """Test all default metrics are present."""
        trades = make_trades_sequence([5, -3, 8, -2, 4])
        m = compute_metrics(trades, 100.0, DEFAULT_METRICS)
        for k in DEFAULT_METRICS:
            assert k in m

    def test_all_optional_metrics_computable(self, make_trades_sequence):
        """Test all optional metrics are computable."""
        trades = make_trades_sequence([5, -3, 8, -2, 4, 6, -1, 2, 3, -4])
        m = compute_metrics(trades, 100.0, OPTIONAL_METRICS)
        assert set(m.keys()) == set(OPTIONAL_METRICS)

    def test_net_pnl_correct(self, make_trades_sequence):
        """Test net P&L is correct."""
        pnls = [10.0, -5.0, 8.0]
        trades = make_trades_sequence(pnls, base=datetime(2025, 1, 1, tzinfo=timezone.utc))
        m = compute_metrics(trades, 100.0, ["net_pnl"])
        assert m["net_pnl"]["usd"] == pytest.approx(sum(pnls), abs=1e-6)

    def test_win_rate_correct(self, make_trades_sequence):
        """Test win rate is correct."""
        trades = make_trades_sequence([1, 1, -1, 1])
        m = compute_metrics(trades, 100.0, ["win_rate"])
        assert m["win_rate"] == pytest.approx(0.75, abs=1e-6)

    def test_total_trades_correct(self, make_trades_sequence):
        """Test total trades is correct."""
        trades = make_trades_sequence([1, -1, 1])
        m = compute_metrics(trades, 100.0, ["total_trades"])
        assert m["total_trades"] == 3

    def test_best_worst_trade(self, make_trades_sequence):
        """Test best and worst trade."""
        trades = make_trades_sequence([10, -5, 2])
        m = compute_metrics(trades, 100.0, ["best_trade", "worst_trade"])
        assert m["best_trade"]["pnl"] == pytest.approx(10.0, abs=1e-6)
        assert m["worst_trade"]["pnl"] == pytest.approx(-5.0, abs=1e-6)

    def test_median_holding(self, make_trade):
        """Test median holding time."""
        base = datetime(2025, 1, 1, tzinfo=timezone.utc)
        t1 = make_trade(1.0, holding_secs=60, entry_time=base)
        t2 = make_trade(1.0, holding_secs=120, entry_time=base + timedelta(hours=1))
        t3 = make_trade(1.0, holding_secs=300, entry_time=base + timedelta(hours=2))
        m = compute_metrics([t1, t2, t3], 100.0, ["median_holding"])
        assert m["median_holding"] == pytest.approx(120.0, abs=0.1)


@pytest.mark.unit
class TestRollingAndCurves:
    """Test rolling metrics and curve helpers."""

    def test_rolling_sharpe_empty(self, make_trades_sequence):
        """Test rolling Sharpe with empty trades."""
        ts, vals = compute_rolling_sharpe([], 30)
        assert ts == []
        assert vals == []

    def test_rolling_sharpe_returns_finite(self, make_trades_sequence):
        """Test rolling Sharpe returns finite values."""
        trades = make_trades_sequence([5, -3, 4, -2, 6, -1, 3, -4, 5, 2])
        ts, vals = compute_rolling_sharpe(trades, 30)
        assert all(math.isfinite(v) for v in vals)

    def test_underwater_curve_len_matches_trades(self, make_trades_sequence):
        """Test underwater curve length matches trades."""
        trades = make_trades_sequence([5, -10, 3])
        ts, dd = compute_underwater_curve(trades, 100.0)
        assert len(ts) == len(trades)
        assert len(dd) == len(trades)

    def test_underwater_curve_non_positive(self, make_trades_sequence):
        """Test underwater curve values are non-positive."""
        trades = make_trades_sequence([5, -10, 3, -5, 2])
        _, dd = compute_underwater_curve(trades, 100.0)
        assert all(v <= 0 for v in dd)

    def test_underwater_curve_zero_at_new_high(self, make_trades_sequence):
        """Test underwater curve is zero at new high."""
        trades = make_trades_sequence([10, 10, 10])
        _, dd = compute_underwater_curve(trades, 100.0)
        assert all(v == 0.0 for v in dd)
