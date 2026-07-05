"""
tests/test_report.py — Unit tests for the polyalpha report module.

Tests cover:
  - TradeRecord extraction from PaperEngine
  - All default and optional metrics (correctness, edge cases, NaN guards)
  - Preset save / load / list / delete round-trips
  - Rolling metrics and helper functions
  - Equity curve and underwater curve construction

Run:
    pytest tests/test_report.py -v
"""

from __future__ import annotations

import math
import statistics
import uuid
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest

from polyalpha.trading.paper import PaperEngine, PaperOrder, PaperPosition
from polyalpha.report.records import TradeRecord, extract_trades, build_equity_curve
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
from polyalpha.report.presets import (
    ReportPreset,
    list_presets,
    load_preset,
    save_preset,
    delete_preset,
    DEFAULT_METRICS,
    DEFAULT_CHARTS,
    ALL_METRICS,
    ALL_CHARTS,
)


# ── Fixtures ──────────────────────────────────────────────────────────────────

def _make_trade(
    pnl: float,
    entry_price: float = 0.70,
    holding_secs: float = 300.0,
    side: str = "UP",
    outcome: str | None = None,
    fill_type: str = "market",
    entry_time: datetime | None = None,
    amount_in: float = 10.0,
) -> TradeRecord:
    """Helper to create a TradeRecord with minimal boilerplate."""
    if outcome is None:
        outcome = "WON" if pnl > 0 else "LOST"
    if entry_time is None:
        entry_time = datetime(2025, 1, 1, 0, 0, 0, tzinfo=timezone.utc)
    exit_time = entry_time + timedelta(seconds=holding_secs)
    exit_price = 1.0 if outcome == "WON" else 0.0
    pnl_pct = (pnl / amount_in) * 100 if amount_in else 0.0
    return TradeRecord(
        trade_id      = str(uuid.uuid4()),
        market_slug   = "btc-updown-5m-0001",
        market_id     = "mkt_001",
        side          = side,
        entry_price   = entry_price,
        exit_price    = exit_price,
        shares        = amount_in / entry_price if entry_price else 0.0,
        amount_in     = amount_in,
        fee           = 0.0,
        pnl           = pnl,
        pnl_pct       = pnl_pct,
        entry_time    = entry_time,
        exit_time     = exit_time,
        holding_secs  = holding_secs,
        outcome       = outcome,
        fill_type     = fill_type,
        slippage      = 0.0,
        order_count   = 1,
    )


def _make_trades_sequence(pnls: list[float], base: datetime | None = None) -> list[TradeRecord]:
    """Create a sequence of trades with timestamps 1 day apart."""
    if base is None:
        base = datetime(2025, 1, 1, tzinfo=timezone.utc)
    trades = []
    for i, p in enumerate(pnls):
        t = _make_trade(
            pnl        = p,
            entry_time = base + timedelta(days=i),
            amount_in  = 10.0,
        )
        trades.append(t)
    return trades


def _make_engine_with_resolved(pnls: list[float], initial_balance: float = 1000.0) -> PaperEngine:
    """Build a PaperEngine with synthetic resolved positions."""
    engine = PaperEngine(balance=initial_balance)
    base = datetime(2025, 1, 1, tzinfo=timezone.utc)

    for i, pnl in enumerate(pnls):
        market_id = f"mkt_{i:04d}"
        slug      = f"btc-updown-5m-{i:04d}"
        side      = "UP"
        entry_price = 0.70
        amount_in   = 10.0
        shares      = (amount_in * 0.98) / entry_price  # 2% fee

        entry_time = base + timedelta(hours=i)
        exit_time  = entry_time + timedelta(minutes=30)

        order_id = str(uuid.uuid4())
        order = PaperOrder(
            id        = order_id,
            market_id = market_id,
            slug      = slug,
            side      = side,
            price     = entry_price,
            amount    = amount_in,
            shares    = shares,
            fee       = amount_in * 0.02,
            status    = "filled",
            is_limit  = False,
            filled_at = entry_time,
        )
        engine._orders[order_id] = order

        outcome = "WON" if pnl > 0 else "LOST"
        engine._balance += pnl

        pos = PaperPosition(
            market_id     = market_id,
            slug          = slug,
            question      = f"Will BTC rise? #{i}",
            side          = side,
            shares        = shares,
            avg_price     = entry_price,
            current_price = 1.0 if outcome == "WON" else 0.0,
            resolved      = True,
            outcome       = outcome,
            order_ids     = [order_id],
        )
        engine._positions[f"{market_id}:{side}"] = pos

    return engine


# ── extract_trades ────────────────────────────────────────────────────────────

class TestExtractTrades:
    def test_empty_engine(self):
        engine = PaperEngine(balance=100.0)
        assert extract_trades(engine) == []

    def test_open_positions_excluded(self):
        engine = PaperEngine(balance=100.0)
        # Add an unresolved position
        engine._positions["mkt_01:UP"] = PaperPosition(
            market_id="mkt_01", slug="btc-1", question="q", side="UP",
            shares=10.0, avg_price=0.7, current_price=0.72,
            resolved=False, outcome=None, order_ids=[],
        )
        assert extract_trades(engine) == []

    def test_resolved_positions_extracted(self):
        engine = _make_engine_with_resolved([3.0, -2.0, 5.0])
        trades = extract_trades(engine)
        assert len(trades) == 3

    def test_sorted_chronologically(self):
        engine = _make_engine_with_resolved([1.0, -1.0, 2.0])
        trades = extract_trades(engine)
        times = [t.entry_time for t in trades]
        assert times == sorted(times)

    def test_pnl_sign_correct(self):
        engine = _make_engine_with_resolved([5.0, -3.0])
        trades = extract_trades(engine)
        wins  = [t for t in trades if t.outcome == "WON"]
        losses = [t for t in trades if t.outcome == "LOST"]
        assert all(t.pnl > 0 for t in wins)
        assert all(t.pnl < 0 for t in losses)

    def test_trade_id_unique(self):
        engine = _make_engine_with_resolved([1.0, 1.0, -1.0])
        trades = extract_trades(engine)
        ids = [t.trade_id for t in trades]
        assert len(ids) == len(set(ids))


# ── build_equity_curve ────────────────────────────────────────────────────────

class TestBuildEquityCurve:
    def test_empty_trades(self):
        trades = []
        ts, eq = build_equity_curve(trades, 100.0)
        assert len(ts) == 1
        assert eq[0] == 100.0

    def test_single_win(self):
        trades = [_make_trade(10.0, amount_in=10.0)]
        ts, eq = build_equity_curve(trades, 100.0)
        assert eq[0] == 100.0
        assert eq[-1] == pytest.approx(110.0, abs=1e-6)

    def test_single_loss(self):
        trades = [_make_trade(-5.0, amount_in=10.0)]
        ts, eq = build_equity_curve(trades, 100.0)
        assert eq[-1] == pytest.approx(95.0, abs=1e-6)

    def test_length_correct(self):
        trades = _make_trades_sequence([1, -1, 2, -2, 3])
        ts, eq = build_equity_curve(trades, 100.0)
        assert len(ts) == len(trades) + 1
        assert len(eq) == len(trades) + 1

    def test_monotone_wins(self):
        trades = _make_trades_sequence([10, 10, 10])
        _, eq = build_equity_curve(trades, 100.0)
        for i in range(len(eq) - 1):
            assert eq[i + 1] > eq[i]


# ── Metric helpers ─────────────────────────────────────────────────────────────

class TestMetricHelpers:

    # ── _annualisation_factor ─────────────────────────────────────────────────
    def test_ann_factor_single_trade(self):
        trades = [_make_trade(1.0)]
        f = _annualisation_factor(trades)
        assert f == pytest.approx(math.sqrt(252), rel=0.01)

    def test_ann_factor_many_trades(self):
        # 365 trades over 1 year → sqrt(365)
        base = datetime(2025, 1, 1, tzinfo=timezone.utc)
        trades = [_make_trade(1.0, entry_time=base + timedelta(days=i)) for i in range(365)]
        f = _annualisation_factor(trades)
        assert math.isfinite(f) and f > 0

    # ── _build_equity_array ───────────────────────────────────────────────────
    def test_equity_array_length(self):
        trades = _make_trades_sequence([1, -1, 2])
        eq = _build_equity_array(trades, 100.0)
        assert len(eq) == 4

    def test_equity_array_correct(self):
        trades = _make_trades_sequence([10, -5, 3])
        eq = _build_equity_array(trades, 100.0)
        assert eq[0] == 100.0
        assert eq[1] == pytest.approx(110.0)
        assert eq[2] == pytest.approx(105.0)
        assert eq[3] == pytest.approx(108.0)

    # ── _sharpe ───────────────────────────────────────────────────────────────
    def test_sharpe_nan_single_return(self):
        assert math.isnan(_sharpe([0.1], 1.0))

    def test_sharpe_nan_zero_std(self):
        assert math.isnan(_sharpe([0.1, 0.1, 0.1], 1.0))

    def test_sharpe_positive_for_positive_mean(self):
        returns = [0.05, 0.03, 0.07, 0.04, 0.06]
        s = _sharpe(returns, 1.0)
        assert s > 0

    def test_sharpe_negative_for_negative_mean(self):
        returns = [-0.05, -0.03, -0.07]
        s = _sharpe(returns, 1.0)
        assert s < 0

    def test_sharpe_annualised_scales_with_factor(self):
        returns = [0.1, -0.05, 0.08, 0.03]
        s1 = _sharpe(returns, 1.0)
        s2 = _sharpe(returns, 2.0)
        assert pytest.approx(s2, rel=0.001) == s1 * 2.0

    # ── _sortino ──────────────────────────────────────────────────────────────
    def test_sortino_inf_no_losses(self):
        returns = [0.1, 0.2, 0.3]
        s = _sortino(returns, 1.0)
        assert math.isinf(s) and s > 0

    def test_sortino_nan_single_return(self):
        assert math.isnan(_sortino([0.1], 1.0))

    def test_sortino_positive_for_positive_mean(self):
        returns = [0.1, -0.02, 0.05, 0.08, -0.01]
        s = _sortino(returns, 1.0)
        assert s > 0

    def test_sortino_ge_sharpe_always(self):
        """Sortino >= Sharpe when there are losses (downside dev <= total std)."""
        returns = [0.1, -0.02, 0.05, 0.08, -0.01, 0.04]
        s  = _sharpe(returns, 1.0)
        so = _sortino(returns, 1.0)
        # Both finite
        if math.isfinite(so) and math.isfinite(s):
            assert so >= s

    # ── _max_drawdown ─────────────────────────────────────────────────────────
    def test_max_drawdown_zero_for_monotone_up(self):
        eq = [100, 110, 120, 130]
        dd_pct, dd_usd = _max_drawdown(eq)
        assert dd_pct == 0.0
        assert dd_usd == 0.0

    def test_max_drawdown_correct(self):
        # Rises to 120, falls to 90 → DD = -25%
        eq = [100, 120, 90]
        dd_pct, dd_usd = _max_drawdown(eq)
        assert dd_pct == pytest.approx(-25.0, abs=0.001)
        assert dd_usd == pytest.approx(-30.0, abs=0.001)

    def test_max_drawdown_picks_largest(self):
        # Two drawdowns: -10% then -25%; should pick -25%
        eq = [100, 110, 99, 120, 90]
        dd_pct, _ = _max_drawdown(eq)
        assert dd_pct == pytest.approx(-25.0, abs=0.001)

    def test_max_drawdown_single_point(self):
        dd_pct, dd_usd = _max_drawdown([100])
        assert dd_pct == 0.0

    # ── _profit_factor ────────────────────────────────────────────────────────
    def test_profit_factor_basic(self):
        pnls = [10, -5, 8, -4]
        pf = _profit_factor(pnls)
        assert pf == pytest.approx(18.0 / 9.0, abs=0.0001)

    def test_profit_factor_no_losses_is_inf(self):
        assert math.isinf(_profit_factor([10, 20, 30]))

    def test_profit_factor_all_losses_is_nan(self):
        # No wins → gross_profit=0, gross_loss>0, returns nan
        pf = _profit_factor([-5, -10])
        assert math.isnan(pf)

    # ── _expectancy ───────────────────────────────────────────────────────────
    def test_expectancy_positive_edge(self):
        trades = _make_trades_sequence([10, 10, -5])
        wins   = [t for t in trades if t.pnl > 0]
        losses = [t for t in trades if t.pnl < 0]
        returns = [t.pnl_pct / 100 for t in trades]
        e = _expectancy(returns, wins, losses, len(trades))
        assert e > 0

    def test_expectancy_negative_edge(self):
        trades = _make_trades_sequence([2, -10, -10])
        wins   = [t for t in trades if t.pnl > 0]
        losses = [t for t in trades if t.pnl < 0]
        returns = [t.pnl_pct / 100 for t in trades]
        e = _expectancy(returns, wins, losses, len(trades))
        assert e < 0

    # ── _omega ────────────────────────────────────────────────────────────────
    def test_omega_positive_mean(self):
        returns = [0.1, 0.05, -0.02, 0.08]
        w = _omega(returns)
        assert w > 1.0

    def test_omega_no_losses_is_inf(self):
        returns = [0.1, 0.2, 0.3]
        w = _omega(returns)
        assert math.isinf(w)

    # ── _kelly ────────────────────────────────────────────────────────────────
    def test_kelly_positive_edge(self):
        wins   = [_make_trade(10.0, amount_in=10.0) for _ in range(7)]
        losses = [_make_trade(-4.0, amount_in=10.0) for _ in range(3)]
        k = _kelly(wins, losses, 10)
        assert 0 < k <= 1.0

    def test_kelly_no_wins_returns_nan(self):
        losses = [_make_trade(-5.0, amount_in=10.0)]
        k = _kelly([], losses, 1)
        assert math.isnan(k)

    def test_kelly_clamped(self):
        wins   = [_make_trade(100.0, amount_in=10.0)]
        losses = [_make_trade(-0.001, amount_in=10.0)]
        k = _kelly(wins, losses, 2)
        assert k <= 1.0

    # ── _var ─────────────────────────────────────────────────────────────────
    def test_var_95_less_than_var_99(self):
        returns = [-0.1, -0.05, -0.02, 0.01, 0.03, 0.05] * 5
        var95 = _var(returns, 0.05)
        var99 = _var(returns, 0.01)
        # 99% VaR (worse tail) should be >= 95% VaR
        assert var99 >= var95

    def test_var_positive_loss_figure(self):
        returns = [-0.10, -0.05, 0.01, 0.02, 0.03]
        v = _var(returns, 0.05)
        assert v >= 0

    # ── _cvar ────────────────────────────────────────────────────────────────
    def test_cvar_ge_var(self):
        returns = [-0.15, -0.10, -0.05, 0.01, 0.03, 0.07] * 3
        v95 = _var(returns, 0.05)
        c95 = _cvar(returns, 0.05)
        assert c95 >= v95

    # ── _max_consecutive ─────────────────────────────────────────────────────
    def test_max_consec_wins(self):
        trades = _make_trades_sequence([1, 1, 1, -1, 1, 1])
        assert _max_consecutive(trades, win=True) == 3

    def test_max_consec_losses(self):
        trades = _make_trades_sequence([1, -1, -1, -1, 1, -1])
        assert _max_consecutive(trades, win=False) == 3

    def test_max_consec_all_wins(self):
        trades = _make_trades_sequence([1, 2, 3])
        assert _max_consecutive(trades, win=True) == 3
        assert _max_consecutive(trades, win=False) == 0

    # ── _kurtosis ────────────────────────────────────────────────────────────
    def test_kurtosis_normal_approx_zero(self):
        # For a truly normal sample the excess kurtosis ≈ 0
        import random as _rand
        rng = _rand.Random(0)
        returns = [rng.gauss(0, 1) for _ in range(10000)]
        k = _kurtosis(returns)
        assert abs(k) < 0.3  # should be close to 0

    def test_kurtosis_nan_small_sample(self):
        assert math.isnan(_kurtosis([0.1, 0.2, 0.3]))  # n < 4

    # ── _pnl_concentration ────────────────────────────────────────────────────
    def test_pnl_concentration_top1_from_2(self):
        pnls = [100.0, 10.0]
        c = _pnl_concentration(pnls, n=1)
        assert c == pytest.approx(100.0 / 110.0, abs=0.0001)

    def test_pnl_concentration_all_losses_nan(self):
        assert math.isnan(_pnl_concentration([-5, -10]))

    # ── _deflated_sharpe ──────────────────────────────────────────────────────
    def test_deflated_sharpe_between_0_and_1(self):
        returns = [0.05, -0.02, 0.03, 0.07, 0.01, -0.01, 0.04] * 5
        dsr = _deflated_sharpe(returns, 1.0)
        if math.isfinite(dsr):
            assert 0 <= dsr <= 1

    def test_deflated_sharpe_nan_small_sample(self):
        assert math.isnan(_deflated_sharpe([0.1, 0.2], 1.0))


# ── compute_metrics ───────────────────────────────────────────────────────────

class TestComputeMetrics:
    def test_empty_trades_all_none(self):
        m = compute_metrics([], 100.0, DEFAULT_METRICS)
        assert all(v is None for v in m.values())

    def test_all_default_metrics_present(self):
        trades = _make_trades_sequence([5, -3, 8, -2, 4])
        m = compute_metrics(trades, 100.0, DEFAULT_METRICS)
        for k in DEFAULT_METRICS:
            assert k in m

    def test_all_optional_metrics_computable(self):
        from polyalpha.report.presets import OPTIONAL_METRICS
        trades = _make_trades_sequence([5, -3, 8, -2, 4, 6, -1, 2, 3, -4])
        m = compute_metrics(trades, 100.0, OPTIONAL_METRICS)
        # No key should raise — may return None or float
        assert set(m.keys()) == set(OPTIONAL_METRICS)

    def test_net_pnl_correct(self):
        pnls = [10.0, -5.0, 8.0]
        trades = _make_trades_sequence(pnls, base=datetime(2025, 1, 1, tzinfo=timezone.utc))
        m = compute_metrics(trades, 100.0, ["net_pnl"])
        assert m["net_pnl"]["usd"] == pytest.approx(sum(pnls), abs=1e-6)

    def test_win_rate_correct(self):
        trades = _make_trades_sequence([1, 1, -1, 1])  # 3W 1L → 75%
        m = compute_metrics(trades, 100.0, ["win_rate"])
        assert m["win_rate"] == pytest.approx(0.75, abs=1e-6)

    def test_total_trades_correct(self):
        trades = _make_trades_sequence([1, -1, 1])
        m = compute_metrics(trades, 100.0, ["total_trades"])
        assert m["total_trades"] == 3

    def test_best_worst_trade(self):
        trades = _make_trades_sequence([10, -5, 2])
        m = compute_metrics(trades, 100.0, ["best_trade", "worst_trade"])
        assert m["best_trade"]["pnl"] == pytest.approx(10.0, abs=1e-6)
        assert m["worst_trade"]["pnl"] == pytest.approx(-5.0, abs=1e-6)

    def test_median_holding(self):
        base = datetime(2025, 1, 1, tzinfo=timezone.utc)
        t1 = _make_trade(1.0, holding_secs=60,  entry_time=base)
        t2 = _make_trade(1.0, holding_secs=120, entry_time=base + timedelta(hours=1))
        t3 = _make_trade(1.0, holding_secs=300, entry_time=base + timedelta(hours=2))
        m = compute_metrics([t1, t2, t3], 100.0, ["median_holding"])
        assert m["median_holding"] == pytest.approx(120.0, abs=0.1)


# ── Preset system ─────────────────────────────────────────────────────────────

class TestPresets:
    def test_load_default(self):
        p = load_preset("default")
        assert p.name == "default"
        assert set(p.metrics) == set(DEFAULT_METRICS)

    def test_load_full(self):
        p = load_preset("full")
        assert "calmar" in p.metrics
        assert "monthly_returns" in p.charts

    def test_load_quick(self):
        p = load_preset("quick")
        assert "net_pnl" in p.metrics
        assert len(p.metrics) < len(DEFAULT_METRICS)

    def test_load_unknown_raises(self):
        with pytest.raises(FileNotFoundError):
            load_preset("__nonexistent_preset__")

    def test_list_presets_includes_builtins(self):
        names = list_presets()
        assert "default" in names
        assert "full" in names
        assert "quick" in names

    def test_save_load_delete_roundtrip(self, tmp_path, monkeypatch):
        # Redirect preset dir to tmp_path
        import polyalpha.report.presets as pmod
        monkeypatch.setattr(pmod, "_PRESET_DIR", tmp_path)

        preset = ReportPreset(
            name    = "my_test",
            metrics = ["net_pnl", "win_rate"],
            charts  = ["equity_curve"],
            description = "test preset",
        )
        path = save_preset(preset)
        assert path.exists()

        loaded = load_preset("my_test")
        assert loaded.name == "my_test"
        assert loaded.metrics == ["net_pnl", "win_rate"]
        assert loaded.charts  == ["equity_curve"]

        delete_preset("my_test")
        assert not path.exists()

    def test_save_reserved_name_raises(self, tmp_path, monkeypatch):
        import polyalpha.report.presets as pmod
        monkeypatch.setattr(pmod, "_PRESET_DIR", tmp_path)

        preset = ReportPreset(name="default", metrics=["net_pnl"], charts=["equity_curve"])
        with pytest.raises(ValueError, match="reserved"):
            save_preset(preset)

    def test_invalid_metric_key_raises(self):
        with pytest.raises(ValueError, match="Unknown metric"):
            ReportPreset(name="bad", metrics=["__fake_metric__"], charts=[])

    def test_invalid_chart_key_raises(self):
        with pytest.raises(ValueError, match="Unknown chart"):
            ReportPreset(name="bad", metrics=[], charts=["__fake_chart__"])


# ── ReportEngine integration ──────────────────────────────────────────────────

class TestReportEngine:
    def test_report_attached_to_engine(self):
        engine = PaperEngine(balance=100.0)
        assert engine.report is not None

    def test_trades_empty(self):
        engine = PaperEngine(balance=100.0)
        assert engine.report.trades() == []

    def test_compute_returns_dict(self):
        engine = _make_engine_with_resolved([5.0, -2.0, 3.0])
        m = engine.report.compute(preset="default")
        assert isinstance(m, dict)
        assert "net_pnl" in m

    def test_initial_balance_reconstruction(self):
        engine = _make_engine_with_resolved([10.0, -5.0])
        # Initial balance = current_balance - net_pnl
        trades = engine.report.trades()
        net = sum(t.pnl for t in trades)
        ib = engine.report._initial_balance(trades)
        assert ib == pytest.approx(engine._balance - net, abs=1e-6)

    def test_html_requires_plotly(self, monkeypatch, tmp_path):
        """html() should raise ImportError with a helpful message when plotly absent."""
        import builtins
        real_import = builtins.__import__

        def mock_import(name, *args, **kwargs):
            if name == "plotly" or name.startswith("plotly."):
                raise ImportError("No module named 'plotly'")
            return real_import(name, *args, **kwargs)

        engine = _make_engine_with_resolved([5.0, -2.0])
        out = tmp_path / "report.html"

        monkeypatch.setattr(builtins, "__import__", mock_import)
        with pytest.raises(ImportError, match="plotly"):
            engine.report.html(
                preset       = "quick",
                path         = str(out),
                open_browser = False,
            )

    def test_save_and_list_preset(self, tmp_path, monkeypatch):
        import polyalpha.report.presets as pmod
        monkeypatch.setattr(pmod, "_PRESET_DIR", tmp_path)

        engine = PaperEngine(balance=100.0)
        p = engine.report.save_preset(
            name    = "engine_test",
            metrics = ["net_pnl", "win_rate"],
            charts  = ["equity_curve"],
        )
        assert p.name == "engine_test"
        assert "engine_test" in engine.report.list_presets()
        engine.report.delete_preset("engine_test")
        assert "engine_test" not in engine.report.list_presets()


# ── Rolling / curve helpers ───────────────────────────────────────────────────

class TestRollingAndCurves:
    def test_rolling_sharpe_empty(self):
        ts, vals = compute_rolling_sharpe([], 30)
        assert ts == []
        assert vals == []

    def test_rolling_sharpe_returns_finite(self):
        trades = _make_trades_sequence([5, -3, 4, -2, 6, -1, 3, -4, 5, 2])
        ts, vals = compute_rolling_sharpe(trades, 30)
        assert all(math.isfinite(v) for v in vals)

    def test_underwater_curve_len_matches_trades(self):
        trades = _make_trades_sequence([5, -10, 3])
        ts, dd = compute_underwater_curve(trades, 100.0)
        assert len(ts) == len(trades)
        assert len(dd) == len(trades)

    def test_underwater_curve_non_positive(self):
        trades = _make_trades_sequence([5, -10, 3, -5, 2])
        _, dd = compute_underwater_curve(trades, 100.0)
        assert all(v <= 0 for v in dd)

    def test_underwater_curve_zero_at_new_high(self):
        """After a new all-time high the drawdown should be 0."""
        # All wins → equity always at all-time high
        trades = _make_trades_sequence([10, 10, 10])
        _, dd = compute_underwater_curve(trades, 100.0)
        assert all(v == 0.0 for v in dd)
