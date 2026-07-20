"""
Terminal rendering tests — run with: pytest tests/unit/report/test_terminal.py
"""

from datetime import datetime, timedelta, timezone

import pytest

from polyalpha.report.terminal import (
    _color,
    _fmt_float,
    _fmt_pnl,
    _fmt_pct,
    _divider,
    _format_duration,
    _format_datetime,
    _format_metric_value,
    render_positions,
    _render_ansi,
    render_terminal,
)
from polyalpha.report.records import TradeRecord
from polyalpha.trading.paper import PaperPosition, PaperOrder


@pytest.mark.unit
class TestANSIHelpers:
    """Test ANSI color helpers."""

    def test_color_wraps_text(self):
        """Test that _color wraps text with ANSI codes."""
        result = _color("test", "\033[31m")
        assert result.startswith("\033[31m")
        assert result.endswith("\033[0m")
        assert "test" in result

    def test_fmt_float_with_none(self):
        """Test formatting None returns dash."""
        result = _fmt_float(None)
        assert "—" in result

    def test_fmt_float_with_nan(self):
        """Test formatting NaN returns n/a."""
        import math
        result = _fmt_float(float("nan"))
        assert "n/a" in result

    def test_fmt_float_with_inf(self):
        """Test formatting infinity returns infinity symbol."""
        result = _fmt_float(float("inf"))
        assert "∞" in result

    def test_fmt_float_with_negative_inf(self):
        """Test formatting negative infinity returns negative infinity."""
        result = _fmt_float(float("-inf"))
        assert "-∞" in result

    def test_fmt_float_normal(self):
        """Test normal float formatting."""
        result = _fmt_float(3.14159, decimals=2)
        assert "3.14" in result

    def test_fmt_float_with_suffix(self):
        """Test float formatting with suffix."""
        result = _fmt_float(100.0, decimals=0, suffix=" USDC")
        assert "100" in result
        assert "USDC" in result

    def test_fmt_pnl_positive(self):
        """Test positive PnL formatting."""
        result = _fmt_pnl(10.5)
        assert "+" in result
        assert "$" in result
        assert "10.5" in result

    def test_fmt_pnl_negative(self):
        """Test negative PnL formatting."""
        result = _fmt_pnl(-5.25)
        assert "-" in result
        assert "$" in result
        assert "5.25" in result

    def test_fmt_pnl_zero(self):
        """Test zero PnL formatting."""
        result = _fmt_pnl(0.0)
        assert "$0.0000" in result

    def test_fmt_pct_positive(self):
        """Test positive percentage formatting."""
        result = _fmt_pct(15.5)
        assert "+" in result
        assert "15.50%" in result

    def test_fmt_pct_negative(self):
        """Test negative percentage formatting."""
        result = _fmt_pct(-8.25)
        assert "-" in result
        assert "8.25%" in result

    def test_divider_default(self):
        """Test default divider."""
        result = _divider()
        assert len(result) == 70 + len("\033[0m") + len("\033[38;5;245m")

    def test_divider_custom_width(self):
        """Test custom width divider."""
        result = _divider(width=50)
        assert "─" * 50 in result


@pytest.mark.unit
class TestFormatters:
    """Test value formatters."""

    def test_format_duration_seconds(self):
        """Test duration formatting for seconds."""
        result = _format_duration(45.0)
        assert "45s" in result

    def test_format_duration_minutes(self):
        """Test duration formatting for minutes."""
        result = _format_duration(125.0)
        assert "2m" in result
        assert "5s" in result

    def test_format_duration_hours(self):
        """Test duration formatting for hours."""
        result = _format_duration(3661.0)
        assert "1h" in result
        assert "1m" in result

    def test_format_duration_days(self):
        """Test duration formatting for days."""
        result = _format_duration(90000.0)
        assert "1d" in result
        assert "1h" in result

    def test_format_duration_nan(self):
        """Test duration formatting with NaN."""
        import math
        result = _format_duration(float("nan"))
        assert "n/a" in result

    def test_format_datetime_valid(self):
        """Test datetime formatting."""
        dt = datetime(2025, 1, 15, 10, 30, 45, tzinfo=timezone.utc)
        result = _format_datetime(dt)
        assert "2025-01-15" in result
        assert "10:30:45" in result

    def test_format_datetime_none(self):
        """Test datetime formatting with None."""
        result = _format_datetime(None)
        assert "—" in result


@pytest.mark.unit
class TestMetricFormatting:
    """Test metric value formatting."""

    def test_format_net_pnl(self):
        """Test net_pnl metric formatting."""
        val = {"usd": 100.5, "pct": 10.25}
        result = _format_metric_value("net_pnl", val)
        assert "$" in result
        assert "%" in result

    def test_format_win_rate(self):
        """Test win_rate metric formatting."""
        result = _format_metric_value("win_rate", 0.65)
        assert "%" in result
        assert "65" in result

    def test_format_total_trades(self):
        """Test total_trades metric formatting."""
        result = _format_metric_value("total_trades", 150)
        assert "150" in result

    def test_format_sharpe(self):
        """Test sharpe ratio formatting."""
        result = _format_metric_value("sharpe", 1.5)
        assert "1.5" in result

    def test_format_max_drawdown(self):
        """Test max_drawdown formatting."""
        val = {"pct": -15.5, "usd": -100.0}
        result = _format_metric_value("max_drawdown", val)
        assert "%" in result
        assert "$" in result

    def test_format_profit_factor(self):
        """Test profit_factor formatting."""
        result = _format_metric_value("profit_factor", 2.5)
        assert "2.5" in result

    def test_format_avg_win_loss(self):
        """Test avg_win_loss formatting."""
        val = {"avg_win": 10.0, "avg_loss": -5.0}
        result = _format_metric_value("avg_win_loss", val)
        assert "$" in result

    def test_format_median_holding(self):
        """Test median_holding formatting."""
        result = _format_metric_value("median_holding", 3600.0)
        assert "h" in result or "m" in result

    def test_format_best_trade(self):
        """Test best_trade formatting."""
        val = {"pnl": 50.0, "pct": 25.0, "market": "btc-updown"}
        result = _format_metric_value("best_trade", val)
        assert "$" in result
        assert "%" in result

    def test_format_unknown_metric(self):
        """Test unknown metric falls back to default."""
        result = _format_metric_value("unknown_metric", 42.0)
        assert "42" in result


@pytest.mark.unit
class TestRenderPositions:
    """Test position rendering."""

    def _make_position(self, resolved=False, outcome=None, pnl_pct=0.0):
        """Helper to create a test position."""
        return PaperPosition(
            market_id="mkt_001",
            slug="btc-updown-5m-0001",
            question="Will BTC rise?",
            side="UP",
            shares=10.0,
            avg_price=0.70,
            current_price=0.72,
            resolved=resolved,
            outcome=outcome,
            order_ids=["order_1"],
            pnl_pct=pnl_pct,
        )

    def _make_order(self):
        """Helper to create a test order."""
        return PaperOrder(
            id="order_1",
            market_id="mkt_001",
            slug="btc-updown-5m-0001",
            side="UP",
            price=0.70,
            amount=10.0,
            shares=14.0,
            fee=0.2,
            status="filled",
            is_limit=False,
            filled_at=datetime(2025, 1, 1, 10, 0, 0, tzinfo=timezone.utc),
        )

    def test_render_empty_positions(self, capsys):
        """Test rendering empty positions list."""
        render_positions([], {}, show_all=False, verbose=True)
        captured = capsys.readouterr()
        assert "No positions" in captured.out

    def test_render_live_positions(self, capsys):
        """Test rendering live positions."""
        positions = [self._make_position(resolved=False)]
        orders = {"order_1": self._make_order()}
        render_positions(positions, orders, show_all=False, verbose=True)
        captured = capsys.readouterr()
        assert "LIVE POSITIONS" in captured.out

    def test_render_closed_positions(self, capsys):
        """Test rendering closed positions."""
        positions = [self._make_position(resolved=True, outcome="WON", pnl_pct=10.0)]
        orders = {"order_1": self._make_order()}
        render_positions(positions, orders, show_all=True, verbose=True)
        captured = capsys.readouterr()
        assert "CLOSED POSITIONS" in captured.out

    def test_render_compact_mode(self, capsys):
        """Test compact rendering mode."""
        positions = [self._make_position(resolved=False)]
        orders = {"order_1": self._make_order()}
        render_positions(positions, orders, show_all=False, verbose=False)
        captured = capsys.readouterr()
        assert "Entry Time" not in captured.out


@pytest.mark.unit
class TestRenderTerminal:
    """Test terminal report rendering."""

    def _make_trade(self, pnl=10.0):
        """Helper to create a test trade."""
        entry_time = datetime(2025, 1, 1, 10, 0, 0, tzinfo=timezone.utc)
        exit_time = entry_time + timedelta(minutes=30)
        return TradeRecord(
            trade_id="mkt_001:UP",
            market_slug="btc-updown-5m-0001",
            market_id="mkt_001",
            side="UP",
            entry_price=0.70,
            exit_price=1.0,
            shares=14.0,
            amount_in=10.0,
            fee=0.2,
            pnl=pnl,
            pnl_pct=(pnl / 10.0) * 100,
            entry_time=entry_time,
            exit_time=exit_time,
            holding_secs=1800.0,
            outcome="WON" if pnl > 0 else "LOST",
            fill_type="market",
            slippage=0.0,
            order_count=1,
        )

    def test_render_ansi_basic(self, capsys):
        """Test basic ANSI rendering."""
        metrics = {
            "net_pnl": {"usd": 100.0, "pct": 10.0},
            "win_rate": 0.65,
            "total_trades": 10,
        }
        trades = [self._make_trade(10.0)]
        _render_ansi(metrics, trades, 100.0, "default", show_trades=True)
        captured = capsys.readouterr()
        assert "POLYALPHA" in captured.out
        assert "Net PnL" in captured.out

    def test_render_ansi_no_trades(self, capsys):
        """Test ANSI rendering without trades."""
        metrics = {"net_pnl": {"usd": 0.0, "pct": 0.0}}
        trades = []
        _render_ansi(metrics, trades, 100.0, "default", show_trades=True)
        captured = capsys.readouterr()
        assert "POLYALPHA" in captured.out

    def test_render_terminal_fallback_to_ansi(self, capsys):
        """Test render_terminal falls back to ANSI when rich unavailable."""
        metrics = {"net_pnl": {"usd": 100.0, "pct": 10.0}}
        trades = [self._make_trade(10.0)]
        render_terminal(metrics, trades, 100.0, "default", show_trades=False)
        captured = capsys.readouterr()
        assert "POLYALPHA" in captured.out

    def test_render_terminal_with_trades(self, capsys):
        """Test render_terminal with trades."""
        metrics = {"net_pnl": {"usd": 100.0, "pct": 10.0}}
        trades = [self._make_trade(10.0), self._make_trade(-5.0)]
        render_terminal(metrics, trades, 100.0, "default", show_trades=True)
        captured = capsys.readouterr()
        assert "Recent Trades" in captured.out
