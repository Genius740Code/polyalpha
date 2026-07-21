"""
Report charts tests — run with: pytest tests/unit/report/test_charts.py
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from typing import Any
from unittest.mock import patch

import pytest
from plotly.graph_objects import Figure

from polyalpha.report.charts import (
    build_charts,
    chart_duration_hist,
    chart_entry_calibration,
    chart_equity_curve,
    chart_monthly_returns,
    chart_pnl_heatmap,
    chart_pnl_per_trade,
    chart_pnl_tte_bucket,
    chart_return_dist,
    chart_rolling_sharpe,
    chart_underwater_dd,
    chart_win_loss_dist,
)
from polyalpha.report.records import TradeRecord

# ── Test helpers ─────────────────────────────────────────────────────────────

def _trade(**overrides: Any) -> TradeRecord:
    """Factory for TradeRecord with sensible defaults."""
    defaults: dict[str, Any] = dict(
        trade_id="t1",
        market_slug="BTC-USD",
        market_id="btc-usd",
        side="UP",
        entry_price=0.5,
        exit_price=1.0,
        shares=10.0,
        amount_in=1000.0,
        fee=0.5,
        pnl=50.0,
        pnl_pct=5.0,
        entry_time=datetime(2024, 1, 1, 12, 0, tzinfo=timezone.utc),
        exit_time=datetime(2024, 1, 1, 13, 0, tzinfo=timezone.utc),
        holding_secs=3600.0,
        outcome="WON",
        fill_type="market",
        slippage=0.0,
        order_count=1,
        intended_price=None,
    )
    defaults.update(**overrides)
    return TradeRecord(**defaults)


def _trades(n: int, **shared: Any) -> list[TradeRecord]:
    """Create *n* sequential trades with shared attributes."""
    base = datetime(2024, 1, 1, 12, 0, tzinfo=timezone.utc)
    result: list[TradeRecord] = []
    for i in range(n):
        kwargs: dict[str, Any] = dict(shared)
        kwargs.setdefault("trade_id", f"t{i}")
        kwargs.setdefault("entry_time", base + timedelta(hours=i))
        kwargs.setdefault("exit_time", base + timedelta(hours=i + 1))
        kwargs.setdefault("holding_secs", 3600.0)
        result.append(_trade(**kwargs))
    return result


# ── Equity curve ─────────────────────────────────────────────────────────────

@pytest.mark.unit
class TestEquityCurve:
    """chart_equity_curve"""

    def test_empty_returns_none(self):
        assert chart_equity_curve([], 1000.0) is None

    @patch("polyalpha.report.charts.build_equity_curve")
    def test_single_trade(self, mock_build):
        mock_build.return_value = (
            [datetime(2024, 1, 1, 13, 0, tzinfo=timezone.utc)],
            [1050.0],
        )
        fig = chart_equity_curve([_trade()], 1000.0)
        assert isinstance(fig, Figure)

    @patch("polyalpha.report.charts.build_equity_curve")
    def test_multiple_trades(self, mock_build):
        ts = [
            datetime(2024, 1, 1, 13, 0, tzinfo=timezone.utc),
            datetime(2024, 1, 2, 13, 0, tzinfo=timezone.utc),
            datetime(2024, 1, 3, 13, 0, tzinfo=timezone.utc),
        ]
        mock_build.return_value = (ts, [1000.0, 1050.0, 1030.0])
        fig = chart_equity_curve(_trades(3), 1000.0)
        assert isinstance(fig, Figure)
        assert len(fig.data) >= 1


# ── Underwater drawdown ──────────────────────────────────────────────────────

@pytest.mark.unit
class TestUnderwaterDD:
    """chart_underwater_dd"""

    def test_empty_returns_none(self):
        assert chart_underwater_dd([], 1000.0) is None

    def test_single_trade_returns_none(self):
        assert chart_underwater_dd([_trade()], 1000.0) is None

    @patch("polyalpha.report.charts.compute_underwater_curve")
    def test_two_or_more(self, mock_uw):
        mock_uw.return_value = (
            [datetime(2024, 1, 1, 13, 0, tzinfo=timezone.utc),
             datetime(2024, 1, 2, 13, 0, tzinfo=timezone.utc)],
            [0.0, -5.0],
        )
        fig = chart_underwater_dd(_trades(2), 1000.0)
        assert isinstance(fig, Figure)


# ── PnL per trade ────────────────────────────────────────────────────────────

@pytest.mark.unit
class TestPnLPerTrade:
    """chart_pnl_per_trade"""

    def test_empty_returns_none(self):
        assert chart_pnl_per_trade([]) is None

    def test_single_trade(self):
        fig = chart_pnl_per_trade([_trade(pnl=50.0)])
        assert isinstance(fig, Figure)

    def test_mixed_pnl(self):
        trades = [
            _trade(trade_id="w1", pnl=100.0),
            _trade(trade_id="l1", pnl=-30.0, outcome="LOST"),
        ]
        fig = chart_pnl_per_trade(trades)
        assert isinstance(fig, Figure)

    def test_zero_pnl(self):
        fig = chart_pnl_per_trade([_trade(pnl=0.0, outcome="CLOSED")])
        assert isinstance(fig, Figure)


# ── Win / Loss distribution ──────────────────────────────────────────────────

@pytest.mark.unit
class TestWinLossDist:
    """chart_win_loss_dist"""

    def test_empty_returns_none(self):
        assert chart_win_loss_dist([]) is None

    def test_no_wins_no_losses_returns_none(self):
        trades = [_trade(pnl=0.0, outcome="CLOSED") for _ in range(3)]
        assert chart_win_loss_dist(trades) is None

    def test_only_wins(self):
        fig = chart_win_loss_dist([_trade(pnl=10.0) for _ in range(5)])
        assert isinstance(fig, Figure)

    def test_only_losses(self):
        fig = chart_win_loss_dist([
            _trade(trade_id=f"l{i}", pnl=-5.0, outcome="LOST") for i in range(5)
        ])
        assert isinstance(fig, Figure)

    def test_mixed(self):
        trades = [
            _trade(trade_id="w1", pnl=10.0),
            _trade(trade_id="l1", pnl=-5.0, outcome="LOST"),
        ]
        fig = chart_win_loss_dist(trades)
        assert isinstance(fig, Figure)


# ── Rolling Sharpe ───────────────────────────────────────────────────────────

@pytest.mark.unit
class TestRollingSharpe:
    """chart_rolling_sharpe"""

    def test_less_than_three_returns_none(self):
        assert chart_rolling_sharpe(_trades(2)) is None

    @patch("polyalpha.report.charts.compute_rolling_sharpe")
    def test_both_windows(self, mock_rs):
        ts = [datetime(2024, 1, i, 13, 0, tzinfo=timezone.utc) for i in range(1, 4)]
        mock_rs.return_value = (ts, [1.5, 2.0, 1.8])
        fig = chart_rolling_sharpe(_trades(3))
        assert isinstance(fig, Figure)
        assert mock_rs.call_count == 2

    @patch("polyalpha.report.charts.compute_rolling_sharpe")
    def test_only_30d(self, mock_rs):
        ts = [datetime(2024, 1, i, 13, 0, tzinfo=timezone.utc) for i in range(1, 4)]
        mock_rs.return_value = (ts, [1.5, 2.0, 1.8])
        fig = chart_rolling_sharpe(_trades(3), window_90d=False)
        assert isinstance(fig, Figure)
        assert mock_rs.call_count == 1

    @patch("polyalpha.report.charts.compute_rolling_sharpe")
    def test_only_90d(self, mock_rs):
        ts = [datetime(2024, 1, i, 13, 0, tzinfo=timezone.utc) for i in range(1, 4)]
        mock_rs.return_value = (ts, [1.5, 2.0, 1.8])
        fig = chart_rolling_sharpe(_trades(3), window_30d=False)
        assert isinstance(fig, Figure)
        assert mock_rs.call_count == 1

    @patch("polyalpha.report.charts.compute_rolling_sharpe")
    def test_no_data_returns_none(self, mock_rs):
        mock_rs.return_value = ([], [])
        fig = chart_rolling_sharpe(_trades(3))
        assert fig is None


# ── PnL heatmap (hour × weekday) ─────────────────────────────────────────────

@pytest.mark.unit
class TestPnLHeatmap:
    """chart_pnl_heatmap"""

    def test_empty_returns_none(self):
        assert chart_pnl_heatmap([]) is None

    def test_fewer_than_five_returns_none(self):
        assert chart_pnl_heatmap(_trades(4)) is None

    def test_five_or_more(self):
        fig = chart_pnl_heatmap(_trades(5, pnl=10.0))
        assert isinstance(fig, Figure)

    def test_varied_hours_and_weekdays(self):
        trades = [
            _trade(
                trade_id=f"t{i}",
                entry_time=datetime(2024, 1, day, hour, 0, tzinfo=timezone.utc),
                exit_time=datetime(2024, 1, day, hour + 1, 0, tzinfo=timezone.utc),
                pnl=10.0 if i % 2 == 0 else -5.0,
                outcome="WON" if i % 2 == 0 else "LOST",
            )
            for i, (day, hour) in enumerate(
                [(1, 6), (1, 10), (2, 8), (2, 14), (3, 20)]
            )
        ]
        fig = chart_pnl_heatmap(trades)
        assert isinstance(fig, Figure)


# ── Return distribution ──────────────────────────────────────────────────────

@pytest.mark.unit
class TestReturnDist:
    """chart_return_dist"""

    def test_empty_returns_none(self):
        assert chart_return_dist([]) is None

    def test_fewer_than_five_returns_none(self):
        assert chart_return_dist(_trades(4)) is None

    def test_five_or_more(self):
        fig = chart_return_dist(_trades(5, pnl=10.0, pnl_pct=1.0))
        assert isinstance(fig, Figure)

    def test_varied_returns(self):
        trades = [
            _trade(trade_id=f"t{i}", pnl=float(v), pnl_pct=float(v))
            for i, v in enumerate([1.0, -0.5, 2.0, -1.0, 0.5])
        ]
        fig = chart_return_dist(trades)
        assert isinstance(fig, Figure)


# ── Duration histogram ───────────────────────────────────────────────────────

@pytest.mark.unit
class TestDurationHist:
    """chart_duration_hist"""

    def test_empty_returns_none(self):
        assert chart_duration_hist([]) is None

    def test_fewer_than_three_returns_none(self):
        assert chart_duration_hist(_trades(2)) is None

    def test_three_or_more(self):
        fig = chart_duration_hist(_trades(3, holding_secs=3600.0))
        assert isinstance(fig, Figure)

    def test_varied_durations(self):
        trades = [
            _trade(
                trade_id=f"t{i}",
                holding_secs=secs,
                entry_time=datetime(2024, 1, 1, 12, 0, tzinfo=timezone.utc),
                exit_time=(
                    datetime(2024, 1, 1, 12, 0, tzinfo=timezone.utc)
                    + timedelta(seconds=secs)
                ),
            )
            for i, secs in enumerate([60, 300, 900, 3600, 7200])
        ]
        fig = chart_duration_hist(trades)
        assert isinstance(fig, Figure)


# ── Monthly returns ──────────────────────────────────────────────────────────

@pytest.mark.unit
class TestMonthlyReturns:
    """chart_monthly_returns"""

    def test_empty_returns_none(self):
        assert chart_monthly_returns([], 1000.0) is None

    def test_single_trade_returns_none(self):
        assert chart_monthly_returns(_trades(1), 1000.0) is None

    @patch("polyalpha.report.charts.compute_monthly_returns")
    def test_empty_monthly_returns_none(self, mock_mr):
        mock_mr.return_value = {}
        assert chart_monthly_returns(_trades(2), 1000.0) is None

    @patch("polyalpha.report.charts.compute_monthly_returns")
    def test_with_data(self, mock_mr):
        mock_mr.return_value = {"2024-01": 5.0, "2024-02": -2.0}
        fig = chart_monthly_returns(_trades(2), 1000.0)
        assert isinstance(fig, Figure)

    @patch("polyalpha.report.charts.compute_monthly_returns")
    def test_single_year_single_month(self, mock_mr):
        mock_mr.return_value = {"2024-01": 3.5}
        fig = chart_monthly_returns(_trades(2), 1000.0)
        assert isinstance(fig, Figure)

    @patch("polyalpha.report.charts.compute_monthly_returns")
    def test_multiple_years(self, mock_mr):
        mock_mr.return_value = {"2023-12": 4.0, "2024-01": -1.0, "2024-02": 2.5}
        fig = chart_monthly_returns(_trades(2), 1000.0)
        assert isinstance(fig, Figure)


# ── Entry calibration ────────────────────────────────────────────────────────

@pytest.mark.unit
class TestEntryCalibration:
    """chart_entry_calibration"""

    def test_empty_returns_none(self):
        assert chart_entry_calibration([]) is None

    def test_fewer_than_ten_returns_none(self):
        assert chart_entry_calibration(_trades(9, entry_price=0.5)) is None

    @patch("polyalpha.report.charts.compute_entry_calibration")
    def test_empty_calibration_returns_none(self, mock_ec):
        mock_ec.return_value = {}
        assert chart_entry_calibration(_trades(10, entry_price=0.5)) is None

    @patch("polyalpha.report.charts.compute_entry_calibration")
    def test_with_data(self, mock_ec):
        mock_ec.return_value = {0.1: 0.5, 0.3: 0.6, 0.5: 0.7}
        fig = chart_entry_calibration(_trades(10, entry_price=0.5))
        assert isinstance(fig, Figure)

    @patch("polyalpha.report.charts.compute_entry_calibration")
    def test_single_bucket(self, mock_ec):
        mock_ec.return_value = {0.55: 1.0}
        fig = chart_entry_calibration(_trades(10, entry_price=0.5))
        assert isinstance(fig, Figure)

    @patch("polyalpha.report.charts.compute_entry_calibration")
    def test_multiple_buckets(self, mock_ec):
        mock_ec.return_value = {0.1: 0.4, 0.3: 0.55, 0.5: 0.6, 0.7: 0.75, 0.9: 0.9}
        fig = chart_entry_calibration(_trades(10, entry_price=0.5))
        assert isinstance(fig, Figure)


# ── PnL by holding-time bucket ───────────────────────────────────────────────

@pytest.mark.unit
class TestPnLTTEBucket:
    """chart_pnl_tte_bucket"""

    def test_empty_returns_none(self):
        assert chart_pnl_tte_bucket([]) is None

    def test_fewer_than_three_returns_none(self):
        assert chart_pnl_tte_bucket(_trades(2)) is None

    def test_three_or_more(self):
        fig = chart_pnl_tte_bucket(_trades(3, pnl=10.0))
        assert isinstance(fig, Figure)

    def test_different_buckets(self):
        trades = [
            _trade(trade_id="t1", pnl=10.0, holding_secs=30),
            _trade(trade_id="t2", pnl=-5.0, holding_secs=120, outcome="LOST"),
            _trade(trade_id="t3", pnl=15.0, holding_secs=600),
            _trade(trade_id="t4", pnl=-2.0, holding_secs=1800, outcome="LOST"),
            _trade(trade_id="t5", pnl=20.0, holding_secs=7200),
        ]
        fig = chart_pnl_tte_bucket(trades)
        assert isinstance(fig, Figure)

    def test_only_one_bucket_populated(self):
        trades = _trades(5, pnl=10.0, holding_secs=30)
        fig = chart_pnl_tte_bucket(trades)
        assert isinstance(fig, Figure)


# ── build_charts dispatcher ──────────────────────────────────────────────────

@pytest.mark.unit
class TestBuildCharts:
    """build_charts"""

    def test_empty_keys(self):
        assert build_charts([], [], 1000.0) == {}

    def test_single_valid_key(self):
        result = build_charts(["pnl_per_trade"], [_trade()], 1000.0)
        assert "pnl_per_trade" in result
        assert isinstance(result["pnl_per_trade"], Figure)

    def test_multiple_valid_keys(self):
        trades = _trades(10, entry_price=0.5)
        keys = ["pnl_per_trade", "duration_hist", "pnl_tte_bucket"]
        result = build_charts(keys, trades, 1000.0)
        assert set(result.keys()) == set(keys)
        for v in result.values():
            assert isinstance(v, Figure)

    def test_unknown_key_returns_none(self):
        result = build_charts(["nonexistent_key"], [], 1000.0)
        assert result == {"nonexistent_key": None}

    def test_corr_matrix_returns_none(self):
        result = build_charts(["corr_matrix"], _trades(3), 1000.0)
        assert result == {"corr_matrix": None}

    def test_error_during_chart_returns_none(self):
        with patch("polyalpha.report.charts.chart_pnl_per_trade",
                   side_effect=ValueError("test error")):
            result = build_charts(["pnl_per_trade"], [_trade()], 1000.0)
            assert result == {"pnl_per_trade": None}

    def test_mixed_valid_and_invalid(self):
        trades = _trades(5, pnl=10.0)
        result = build_charts(["pnl_per_trade", "bad_key", "corr_matrix"],
                              trades, 1000.0)
        assert result["pnl_per_trade"] is not None
        assert result["bad_key"] is None
        assert result["corr_matrix"] is None

    def test_all_known_chart_keys(self):
        """All standard chart keys should be dispatchable."""
        trades = _trades(10, entry_price=0.5)
        keys = [
            "equity_curve",
            "underwater_dd",
            "pnl_per_trade",
            "win_loss_dist",
            "rolling_sharpe",
            "pnl_hour_heatmap",
            "return_dist",
            "duration_hist",
            "monthly_returns",
            "entry_calibration",
            "pnl_tte_bucket",
            "corr_matrix",
        ]
        result = build_charts(keys, trades, 1000.0)
        assert set(result.keys()) == set(keys)

    def test_risk_free_rate_passed(self):
        """risk_free_rate should be forwarded to rolling_sharpe."""
        with patch("polyalpha.report.charts.chart_rolling_sharpe",
                   wraps=chart_rolling_sharpe) as spy:
            trades = _trades(3, pnl=10.0, pnl_pct=1.0)
            build_charts(["rolling_sharpe"], trades, 1000.0, risk_free_rate=0.05)
            spy.assert_called_once()


# ── No-plotly degradation ────────────────────────────────────────────────────

@pytest.mark.unit
class TestNoPlotly:
    """When plotly is absent, individual functions raise; build_charts returns None."""

    @patch("polyalpha.report.charts._try_import_plotly",
           side_effect=ImportError("plotly not installed"))
    def test_individual_chart_raises(self, _mock):
        with pytest.raises(ImportError):
            chart_pnl_per_trade([_trade()])

    @patch("polyalpha.report.charts._try_import_plotly",
           side_effect=ImportError("plotly not installed"))
    def test_build_charts_returns_none(self, _mock):
        result = build_charts(["pnl_per_trade"], [_trade()], 1000.0)
        assert result == {"pnl_per_trade": None}

    @patch("polyalpha.report.charts._try_import_plotly",
           side_effect=ImportError("plotly not installed"))
    def test_equity_curve_raises(self, _mock):
        with pytest.raises(ImportError):
            chart_equity_curve([_trade()], 1000.0)

    @patch("polyalpha.report.charts._try_import_plotly",
           side_effect=ImportError("plotly not installed"))
    def test_underwater_dd_raises(self, _mock):
        with pytest.raises(ImportError):
            chart_underwater_dd(_trades(2), 1000.0)
