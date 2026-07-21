"""
Reporting engine tests — run with: pytest tests/unit/report/test_reporting.py
"""

import json
import uuid
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest

from polyalpha.report.records import TradeRecord
from polyalpha.report.reporting import (
    AuditEntry,
    ExecutionQualityMetrics,
    ReportingEngine,
    RiskMetrics,
    TaxReportEntry,
)
from polyalpha.trading.paper import PaperEngine, PaperOrder, PaperPosition


# ── Helpers ───────────────────────────────────────────────────────────────────

def _make_trade(pnl, amount_in=10.0, outcome=None):
    """Helper to create a TradeRecord."""
    if outcome is None:
        outcome = "WON" if pnl > 0 else "LOST"
    entry_time = datetime(2025, 1, 1, tzinfo=timezone.utc)
    exit_time = entry_time + timedelta(seconds=300)
    exit_price = 1.0 if outcome == "WON" else 0.0
    pnl_pct = (pnl / amount_in) * 100 if amount_in else 0.0
    return TradeRecord(
        trade_id=str(uuid.uuid4()),
        market_slug="btc-updown-5m-0001",
        market_id="mkt_001",
        side="UP",
        entry_price=0.70,
        exit_price=exit_price,
        shares=amount_in / 0.70,
        amount_in=amount_in,
        fee=0.0,
        pnl=pnl,
        pnl_pct=pnl_pct,
        entry_time=entry_time,
        exit_time=exit_time,
        holding_secs=300.0,
        outcome=outcome,
        fill_type="market",
        slippage=0.0,
        order_count=1,
    )


def _make_engine_with_trades(pnls, initial_balance=1000.0):
    """Build a PaperEngine with synthetic resolved positions."""
    engine = PaperEngine(balance=initial_balance)
    base = datetime(2025, 1, 1, tzinfo=timezone.utc)

    for i, pnl in enumerate(pnls):
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
            filled_at=entry_time,
        )
        engine._orders[order_id] = order

        outcome = "WON" if pnl > 0 else "LOST"
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


def _make_engine_with_open_positions():
    """Build a PaperEngine with open positions."""
    engine = PaperEngine(balance=500.0)
    engine._positions["mkt_01:UP"] = PaperPosition(
        market_id="mkt_01", slug="btc-1", question="q1", side="UP",
        shares=10.0, avg_price=0.7, current_price=0.75,
        resolved=False, outcome=None, order_ids=[],
        stop_loss=0.60,
    )
    return engine


def _make_engine_with_orders():
    """Build a PaperEngine with various order types."""
    engine = PaperEngine(balance=1000.0)
    base = datetime(2025, 1, 1, tzinfo=timezone.utc)

    # A filled market order
    ord_market = PaperOrder(
        id="ord_market", market_id="mkt_00", slug="btc-1", side="UP",
        price=0.70, amount=10.0, shares=14.0, fee=0.2,
        status="filled", is_limit=False,
        filled_at=base + timedelta(minutes=1),
    )
    ord_market.created_at = base
    engine._orders["ord_market"] = ord_market

    # A filled limit order
    ord_limit = PaperOrder(
        id="ord_limit", market_id="mkt_00", slug="btc-1", side="DOWN",
        price=0.30, amount=10.0, shares=32.0, fee=0.2,
        status="filled", is_limit=True,
        filled_at=base + timedelta(minutes=5),
    )
    ord_limit.created_at = base
    engine._orders["ord_limit"] = ord_limit

    # An open (pending) limit order
    ord_open = PaperOrder(
        id="ord_open", market_id="mkt_00", slug="btc-1", side="UP",
        price=0.65, amount=5.0, shares=7.5, fee=0.1,
        status="open", is_limit=True,
        filled_at=None,
    )
    ord_open.created_at = base
    engine._orders["ord_open"] = ord_open

    return engine


# ── Dataclass dump tests ──────────────────────────────────────────────────────

@pytest.mark.unit
class TestExecutionQualityMetrics:
    """Test ExecutionQualityMetrics dataclass."""

    def test_dump_returns_dict(self):
        eq = ExecutionQualityMetrics(
            avg_fill_time=1.5, fill_rate=0.85,
            slippage_avg=0.001, slippage_max=0.005,
            price_improvement=0.0,
            limit_order_success_rate=0.75,
            market_order_count=10, limit_order_count=5, total_orders=15,
        )
        d = eq.dump()
        assert d["avg_fill_time"] == 1.5
        assert d["fill_rate"] == 0.85
        assert d["market_order_count"] == 10
        assert d["total_orders"] == 15


@pytest.mark.unit
class TestRiskMetrics:
    """Test RiskMetrics dataclass."""

    def test_dump_returns_dict(self):
        rm = RiskMetrics(
            total_exposure=1500.0, max_loss_exposure=500.0,
            concentration_risk={"mkt_01": 0.6, "mkt_02": 0.4},
            leverage_ratio=0.5, var_95=100.0, var_99=200.0, beta_exposure=1.0,
        )
        d = rm.dump()
        assert d["total_exposure"] == 1500.0
        assert d["concentration_risk"]["mkt_01"] == 0.6
        assert d["leverage_ratio"] == 0.5

    def test_dump_empty_concentration(self):
        rm = RiskMetrics(
            total_exposure=0.0, max_loss_exposure=0.0,
            concentration_risk={},
            leverage_ratio=0.0, var_95=0.0, var_99=0.0, beta_exposure=0.0,
        )
        d = rm.dump()
        assert d["concentration_risk"] == {}


@pytest.mark.unit
class TestTaxReportEntry:
    """Test TaxReportEntry dataclass."""

    def test_dump_returns_dict(self):
        entry = TaxReportEntry(
            trade_id="t1", market="btc-1", side="UP",
            acquired=datetime(2025, 1, 1, tzinfo=timezone.utc),
            sold=datetime(2025, 6, 1, tzinfo=timezone.utc),
            proceeds=15.0, cost_basis=10.0, realized_gain=5.0,
            gain_percent=50.0, holding_period_days=151, short_term=True,
        )
        d = entry.dump()
        assert d["trade_id"] == "t1"
        assert d["realized_gain"] == 5.0
        assert d["short_term"] is True
        assert d["holding_period_days"] == 151

    def test_long_term(self):
        entry = TaxReportEntry(
            trade_id="t2", market="btc-2", side="DOWN",
            acquired=datetime(2024, 1, 1, tzinfo=timezone.utc),
            sold=datetime(2025, 6, 1, tzinfo=timezone.utc),
            proceeds=0.0, cost_basis=10.0, realized_gain=-10.0,
            gain_percent=-100.0, holding_period_days=517, short_term=False,
        )
        d = entry.dump()
        assert d["short_term"] is False
        assert d["realized_gain"] == -10.0


@pytest.mark.unit
class TestAuditEntry:
    """Test AuditEntry dataclass."""

    def test_dump_returns_dict(self):
        entry = AuditEntry(
            timestamp=datetime(2025, 1, 1, 12, 0, tzinfo=timezone.utc),
            event_type="order_created",
            details={"order_id": "ord_1", "side": "UP"},
        )
        d = entry.dump()
        assert "2025-01-01" in d["timestamp"]
        assert d["event_type"] == "order_created"
        assert d["details"]["order_id"] == "ord_1"


# ── ReportingEngine init tests ────────────────────────────────────────────────

@pytest.mark.unit
class TestReportingEngineInit:
    """Test ReportingEngine initialization."""

    def test_init(self):
        """Test initialization creates internal PortfolioAnalytics."""
        engine = PaperEngine(balance=100.0)
        re = ReportingEngine(engine)
        assert re._engine is engine
        assert re._portfolio_analytics is not None

    def test_init_with_trades(self):
        """Test initialization with engine containing trades."""
        engine = _make_engine_with_trades([5.0, -3.0])
        re = ReportingEngine(engine)
        assert re._portfolio_analytics is not None


# ── portfolio_summary tests ───────────────────────────────────────────────────

@pytest.mark.unit
class TestPortfolioSummary:
    """Test portfolio_summary."""

    def test_json_format(self, tmp_path):
        """Test JSON output format."""
        engine = _make_engine_with_trades([5.0, -3.0])
        re = ReportingEngine(engine)
        out = tmp_path / "summary.json"
        re.portfolio_summary(str(out), format="json")
        with open(out) as f:
            data = json.load(f)
        assert "portfolio_pnl" in data
        assert "trade_summary" in data
        assert "generated_at" in data

    def test_csv_format(self, tmp_path):
        """Test CSV output format."""
        engine = _make_engine_with_trades([5.0, -3.0])
        re = ReportingEngine(engine)
        out = tmp_path / "summary.csv"
        re.portfolio_summary(str(out), format="csv")
        content = Path(out).read_text(encoding="utf-8")
        assert "Portfolio P&L" in content
        assert "Total P&L" in content

    def test_html_format(self, tmp_path):
        """Test HTML output format."""
        engine = _make_engine_with_trades([5.0, -3.0])
        re = ReportingEngine(engine)
        out = tmp_path / "summary.html"
        re.portfolio_summary(str(out), format="html")
        content = Path(out).read_text(encoding="utf-8")
        assert "Portfolio Summary Report" in content
        assert "<!DOCTYPE html>" in content

    def test_html_without_charts(self, tmp_path):
        """Test HTML without charts."""
        engine = _make_engine_with_trades([5.0])
        re = ReportingEngine(engine)
        out = tmp_path / "summary.html"
        re.portfolio_summary(str(out), format="html", include_charts=False)
        assert out.exists()

    def test_returns_path_string(self, tmp_path):
        """Test returns absolute path to file."""
        engine = _make_engine_with_trades([5.0])
        re = ReportingEngine(engine)
        out = tmp_path / "summary.json"
        result = re.portfolio_summary(str(out), format="json")
        assert isinstance(result, str)
        assert Path(result).exists()

    def test_unsupported_format_raises(self, tmp_path):
        """Test unsupported format raises ValueError."""
        engine = _make_engine_with_trades([5.0])
        re = ReportingEngine(engine)
        out = tmp_path / "summary.txt"
        with pytest.raises(ValueError, match="Unsupported format"):
            re.portfolio_summary(str(out), format="pdf")

    def test_empty_engine_json(self, tmp_path):
        """Test JSON with empty engine."""
        engine = PaperEngine(balance=100.0)
        re = ReportingEngine(engine)
        out = tmp_path / "summary.json"
        re.portfolio_summary(str(out), format="json")
        with open(out) as f:
            data = json.load(f)
        assert data["portfolio_pnl"]["total_pnl"] == 0.0


# ── execution_quality tests ───────────────────────────────────────────────────

@pytest.mark.unit
class TestExecutionQuality:
    """Test execution_quality."""

    def test_json_format(self, tmp_path):
        """Test JSON output format."""
        engine = _make_engine_with_orders()
        re = ReportingEngine(engine)
        out = tmp_path / "exec.json"
        re.execution_quality(str(out), format="json")
        with open(out) as f:
            data = json.load(f)
        assert "execution_quality" in data
        assert data["execution_quality"]["total_orders"] > 0

    def test_csv_format(self, tmp_path):
        """Test CSV output format."""
        engine = _make_engine_with_orders()
        re = ReportingEngine(engine)
        out = tmp_path / "exec.csv"
        re.execution_quality(str(out), format="csv")
        content = Path(out).read_text(encoding="utf-8")
        assert "Average Fill Time" in content

    def test_html_format(self, tmp_path):
        """Test HTML output format."""
        engine = _make_engine_with_orders()
        re = ReportingEngine(engine)
        out = tmp_path / "exec.html"
        re.execution_quality(str(out), format="html")
        content = Path(out).read_text(encoding="utf-8")
        assert "Execution Quality Report" in content

    def test_empty_engine(self, tmp_path):
        """Test with empty engine."""
        engine = PaperEngine(balance=100.0)
        re = ReportingEngine(engine)
        out = tmp_path / "exec.json"
        re.execution_quality(str(out), format="json")
        with open(out) as f:
            data = json.load(f)
        assert data["execution_quality"]["total_orders"] == 0

    def test_unsupported_format_raises(self, tmp_path):
        """Test unsupported format raises ValueError."""
        engine = PaperEngine(balance=100.0)
        re = ReportingEngine(engine)
        out = tmp_path / "exec.txt"
        with pytest.raises(ValueError, match="Unsupported format"):
            re.execution_quality(str(out), format="xml")

    def test_returns_path_string(self, tmp_path):
        """Test returns path string."""
        engine = _make_engine_with_orders()
        re = ReportingEngine(engine)
        out = tmp_path / "exec.json"
        result = re.execution_quality(str(out), format="json")
        assert isinstance(result, str)
        assert Path(result).exists()


# ── _calculate_execution_quality tests ────────────────────────────────────────

@pytest.mark.unit
class TestCalculateExecutionQuality:
    """Test _calculate_execution_quality."""

    def test_no_orders_returns_defaults(self):
        """Test no orders returns default metrics."""
        engine = PaperEngine(balance=100.0)
        re = ReportingEngine(engine)
        m = re._calculate_execution_quality()
        assert m.total_orders == 0
        assert m.fill_rate == 0.0

    def test_with_orders(self):
        """Test with mixed order types."""
        engine = _make_engine_with_orders()
        re = ReportingEngine(engine)
        m = re._calculate_execution_quality()
        assert m.total_orders == 3
        assert m.limit_order_count == 2
        assert m.market_order_count == 1
        assert m.fill_rate > 0

    def test_fill_times_calculated(self):
        """Test fill times are calculated."""
        engine = _make_engine_with_orders()
        re = ReportingEngine(engine)
        m = re._calculate_execution_quality()
        assert m.avg_fill_time > 0

    def test_limit_order_success_rate(self):
        """Test limit order success rate."""
        engine = _make_engine_with_orders()
        re = ReportingEngine(engine)
        m = re._calculate_execution_quality()
        assert m.limit_order_success_rate == 0.5  # 1 of 2 limit orders filled


# ── risk_exposure tests ───────────────────────────────────────────────────────

@pytest.mark.unit
class TestRiskExposure:
    """Test risk_exposure."""

    def test_json_format(self, tmp_path):
        """Test JSON output format."""
        engine = _make_engine_with_open_positions()
        re = ReportingEngine(engine)
        out = tmp_path / "risk.json"
        re.risk_exposure(str(out), format="json")
        with open(out) as f:
            data = json.load(f)
        assert "risk_exposure" in data

    def test_csv_format(self, tmp_path):
        """Test CSV output format."""
        engine = _make_engine_with_open_positions()
        re = ReportingEngine(engine)
        out = tmp_path / "risk.csv"
        re.risk_exposure(str(out), format="csv")
        content = Path(out).read_text(encoding="utf-8")
        assert "Total Exposure" in content

    def test_html_format(self, tmp_path):
        """Test HTML output format."""
        engine = _make_engine_with_open_positions()
        re = ReportingEngine(engine)
        out = tmp_path / "risk.html"
        re.risk_exposure(str(out), format="html")
        content = Path(out).read_text(encoding="utf-8")
        assert "Risk Exposure Report" in content

    def test_empty_engine(self, tmp_path):
        """Test with empty engine."""
        engine = PaperEngine(balance=100.0)
        re = ReportingEngine(engine)
        out = tmp_path / "risk.json"
        re.risk_exposure(str(out), format="json")
        with open(out) as f:
            data = json.load(f)
        assert data["risk_exposure"]["total_exposure"] == 100.0
        assert data["risk_exposure"]["concentration_risk"] == {}

    def test_unsupported_format_raises(self, tmp_path):
        """Test unsupported format."""
        engine = PaperEngine(balance=100.0)
        re = ReportingEngine(engine)
        out = tmp_path / "risk.txt"
        with pytest.raises(ValueError, match="Unsupported format"):
            re.risk_exposure(str(out), format="xml")


# ── _calculate_risk_metrics tests ─────────────────────────────────────────────

@pytest.mark.unit
class TestCalculateRiskMetrics:
    """Test _calculate_risk_metrics."""

    def test_no_positions(self):
        """Test with no positions."""
        engine = PaperEngine(balance=1000.0)
        re = ReportingEngine(engine)
        rm = re._calculate_risk_metrics()
        assert rm.total_exposure == 1000.0
        assert rm.max_loss_exposure == 0.0
        assert rm.concentration_risk == {}
        assert rm.leverage_ratio == 0.0

    def test_with_open_positions(self):
        """Test with open positions."""
        engine = _make_engine_with_open_positions()
        re = ReportingEngine(engine)
        rm = re._calculate_risk_metrics()
        assert rm.total_exposure > 500.0
        assert rm.max_loss_exposure > 0
        assert len(rm.concentration_risk) > 0

    def test_position_without_stop_loss(self):
        """Test that position without SL contributes full cost basis."""
        engine = PaperEngine(balance=1000.0)
        engine._positions["mkt_01:UP"] = PaperPosition(
            market_id="mkt_01", slug="btc-1", question="q", side="UP",
            shares=10.0, avg_price=0.7, current_price=0.75,
            resolved=False, outcome=None, order_ids=[],
        )
        re = ReportingEngine(engine)
        rm = re._calculate_risk_metrics()
        cost_basis = 10.0 * 0.7  # shares * avg_price
        assert rm.max_loss_exposure == pytest.approx(cost_basis, abs=0.01)
        assert rm.leverage_ratio > 0


# ── tax_report tests ──────────────────────────────────────────────────────────

@pytest.mark.unit
class TestTaxReport:
    """Test tax_report."""

    def test_csv_format(self, tmp_path):
        """Test CSV output format."""
        engine = _make_engine_with_trades([5.0, -3.0, 8.0])
        re = ReportingEngine(engine)
        out = tmp_path / "tax.csv"
        re.tax_report(str(out), format="csv")
        content = Path(out).read_text(encoding="utf-8")
        assert "TradeID" in content
        assert "RealizedGain" in content
        assert "TOTALS" in content

    def test_json_format(self, tmp_path):
        """Test JSON output format."""
        engine = _make_engine_with_trades([5.0, -3.0])
        re = ReportingEngine(engine)
        out = tmp_path / "tax.json"
        re.tax_report(str(out), format="json")
        with open(out) as f:
            data = json.load(f)
        assert "tax_entries" in data
        assert "summary" in data
        assert data["summary"]["total_trades"] > 0

    def test_unsupported_format_raises(self, tmp_path):
        """Test unsupported format."""
        engine = PaperEngine(balance=100.0)
        re = ReportingEngine(engine)
        out = tmp_path / "tax.txt"
        with pytest.raises(ValueError, match="Unsupported format"):
            re.tax_report(str(out), format="html")

    def test_empty_engine(self, tmp_path):
        """Test with empty engine."""
        engine = PaperEngine(balance=100.0)
        re = ReportingEngine(engine)
        out = tmp_path / "tax.csv"
        re.tax_report(str(out), format="csv")
        content = Path(out).read_text(encoding="utf-8")
        assert "TradeID" in content

    def test_json_summary(self, tmp_path):
        """Test JSON summary fields."""
        engine = _make_engine_with_trades([10.0, -5.0])
        re = ReportingEngine(engine)
        out = tmp_path / "tax.json"
        re.tax_report(str(out), format="json")
        with open(out) as f:
            data = json.load(f)
        summary = data["summary"]
        assert "total_proceeds" in summary
        assert "total_cost_basis" in summary
        assert "total_realized_gains" in summary
        assert "short_term_trades" in summary
        assert "long_term_trades" in summary

    def test_returns_path_string(self, tmp_path):
        """Test returns path string."""
        engine = _make_engine_with_trades([5.0])
        re = ReportingEngine(engine)
        out = tmp_path / "tax.csv"
        result = re.tax_report(str(out), format="csv")
        assert isinstance(result, str)
        assert Path(result).exists()


# ── _calculate_tax_entries tests ──────────────────────────────────────────────

@pytest.mark.unit
class TestCalculateTaxEntries:
    """Test _calculate_tax_entries."""

    def test_empty_trades(self):
        """Test empty trades returns empty list."""
        engine = PaperEngine(balance=100.0)
        re = ReportingEngine(engine)
        entries = re._calculate_tax_entries([])
        assert entries == []

    def test_with_trades(self):
        """Test with trade records."""
        trades = [_make_trade(10.0), _make_trade(-5.0)]
        engine = PaperEngine(balance=100.0)
        re = ReportingEngine(engine)
        entries = re._calculate_tax_entries(trades)
        assert len(entries) == 2

    def test_entry_fields(self):
        """Test entry field values."""
        trades = [_make_trade(10.0)]
        engine = PaperEngine(balance=100.0)
        re = ReportingEngine(engine)
        entries = re._calculate_tax_entries(trades)
        entry = entries[0]
        assert entry.trade_id is not None
        assert entry.market != ""
        assert entry.side == "UP"
        assert entry.short_term is True
        assert isinstance(entry.dump(), dict)

    def test_holding_period(self):
        """Test holding period calculation."""
        trades = [_make_trade(10.0)]
        engine = PaperEngine(balance=100.0)
        re = ReportingEngine(engine)
        entries = re._calculate_tax_entries(trades)
        assert entries[0].holding_period_days == 0  # Same day

    def test_lost_outcome_proceeds_zero(self):
        """Test LOST outcome has zero proceeds."""
        trade = _make_trade(-10.0, outcome="LOST")
        engine = PaperEngine(balance=100.0)
        re = ReportingEngine(engine)
        entries = re._calculate_tax_entries([trade])
        assert entries[0].proceeds == 0.0
        assert entries[0].realized_gain < 0


# ── audit_trail tests ─────────────────────────────────────────────────────────

@pytest.mark.unit
class TestAuditTrail:
    """Test audit_trail."""

    def test_json_format(self, tmp_path):
        """Test JSON output format."""
        engine = _make_engine_with_orders()
        re = ReportingEngine(engine)
        out = tmp_path / "audit.json"
        re.audit_trail(str(out), format="json")
        with open(out) as f:
            data = json.load(f)
        assert "audit_entries" in data
        assert "engine_type" in data
        assert len(data["audit_entries"]) > 0

    def test_csv_format(self, tmp_path):
        """Test CSV output format."""
        engine = _make_engine_with_orders()
        re = ReportingEngine(engine)
        out = tmp_path / "audit.csv"
        re.audit_trail(str(out), format="csv")
        content = Path(out).read_text(encoding="utf-8")
        assert "Timestamp" in content
        assert "EventType" in content

    def test_unsupported_format_raises(self, tmp_path):
        """Test unsupported format."""
        engine = PaperEngine(balance=100.0)
        re = ReportingEngine(engine)
        out = tmp_path / "audit.txt"
        with pytest.raises(ValueError, match="Unsupported format"):
            re.audit_trail(str(out), format="xml")

    def test_empty_engine(self, tmp_path):
        """Test with empty engine."""
        engine = PaperEngine(balance=100.0)
        re = ReportingEngine(engine)
        out = tmp_path / "audit.json"
        re.audit_trail(str(out), format="json")
        with open(out) as f:
            data = json.load(f)
        assert data["audit_entries"] == []
        assert data["engine_type"] == "PaperEngine"

    def test_returns_path_string(self, tmp_path):
        """Test returns path string."""
        engine = _make_engine_with_orders()
        re = ReportingEngine(engine)
        out = tmp_path / "audit.json"
        result = re.audit_trail(str(out), format="json")
        assert isinstance(result, str)
        assert Path(result).exists()


# ── _generate_audit_entries tests ─────────────────────────────────────────────

@pytest.mark.unit
class TestGenerateAuditEntries:
    """Test _generate_audit_entries."""

    def test_empty_engine(self):
        """Test empty engine returns empty list."""
        engine = PaperEngine(balance=100.0)
        re = ReportingEngine(engine)
        entries = re._generate_audit_entries()
        assert entries == []

    def test_order_created_events(self):
        """Test order creation events."""
        engine = _make_engine_with_orders()
        re = ReportingEngine(engine)
        entries = re._generate_audit_entries()
        order_created = [e for e in entries if e.event_type == "order_created"]
        assert len(order_created) > 0

    def test_order_filled_events(self):
        """Test order filled events."""
        engine = _make_engine_with_orders()
        re = ReportingEngine(engine)
        entries = re._generate_audit_entries()
        order_filled = [e for e in entries if e.event_type == "order_filled"]
        assert len(order_filled) > 0

    def test_position_opened_events(self):
        """Test position opened events."""
        engine = _make_engine_with_trades([5.0])
        re = ReportingEngine(engine)
        entries = re._generate_audit_entries()
        position_open = [e for e in entries if e.event_type == "position_opened"]
        assert len(position_open) > 0

    def test_position_closed_events(self):
        """Test position closed events."""
        engine = _make_engine_with_trades([5.0])
        re = ReportingEngine(engine)
        entries = re._generate_audit_entries()
        position_closed = [e for e in entries if e.event_type == "position_closed"]
        assert len(position_closed) > 0

    def test_entries_sorted_by_timestamp(self):
        """Test entries are sorted by timestamp."""
        engine = _make_engine_with_trades([5.0, -3.0])
        re = ReportingEngine(engine)
        entries = re._generate_audit_entries()
        timestamps = [e.timestamp for e in entries]
        assert timestamps == sorted(timestamps)

    def test_audit_entry_dump(self):
        """Test audit entry dump works."""
        engine = _make_engine_with_trades([5.0])
        re = ReportingEngine(engine)
        entries = re._generate_audit_entries()
        assert all(isinstance(e.dump(), dict) for e in entries)


@pytest.mark.unit
class TestHTMLGeneration:
    """Test HTML generation methods."""

    def test_portfolio_summary_html(self):
        """Test portfolio summary HTML generation."""
        from polyalpha.report.portfolio_analytics import (
            PortfolioPnL, TradeHistorySummary, PerformanceMetrics, TimeBasedPerformance,
        )
        engine = PaperEngine(balance=100.0)
        re = ReportingEngine(engine)
        pnl = PortfolioPnL(100.0, 10.0, 80.0, 20.0, 500.0, 25.0, 20.0, 1100.0, 1000.0, 1200.0, -50.0, -5.0)
        ts = TradeHistorySummary(10, 6, 4, 0.6, 2.5, 15.0, -8.0, 30.0, -12.0, 3600.0, 36000.0)
        pm = PerformanceMetrics(1.5, 2.0, 1.2, 1.8, -100.0, -10.0, 0.05, 0.25, 0.1, -0.5, 0.02, 0.05, 0.03, 0.06)
        dp = TimeBasedPerformance("daily", {"2025-01-01": 10.0}, ("2025-01-01", 10.0), ("", 0.0), 10.0, 1.0)
        wp = TimeBasedPerformance("weekly", {"2025-W01": 15.0}, ("2025-W01", 15.0), ("", 0.0), 15.0, 1.0)
        mp = TimeBasedPerformance("monthly", {"2025-01": 25.0}, ("2025-01", 25.0), ("", 0.0), 25.0, 1.0)
        html = re._generate_portfolio_summary_html(pnl, ts, pm, dp, wp, mp, include_charts=True)
        assert "Portfolio Summary Report" in html
        assert "1100.00" in html  # current balance

    def test_execution_quality_html(self):
        """Test execution quality HTML generation."""
        engine = PaperEngine(balance=100.0)
        re = ReportingEngine(engine)
        eq = ExecutionQualityMetrics(1.5, 0.85, 0.001, 0.005, 0.0, 0.75, 10, 5, 15)
        html = re._generate_execution_quality_html(eq)
        assert "Execution Quality Report" in html
        assert "15" in html  # total orders

    def test_risk_exposure_html(self):
        """Test risk exposure HTML generation."""
        engine = PaperEngine(balance=100.0)
        re = ReportingEngine(engine)
        rm = RiskMetrics(1500.0, 500.0, {"mkt_01": 0.6, "mkt_02": 0.4}, 0.5, 100.0, 200.0, 1.0)
        html = re._generate_risk_exposure_html(rm)
        assert "Risk Exposure Report" in html
        assert "Market Concentration" in html
        assert "mkt_01" in html

    def test_risk_exposure_html_empty_concentration(self):
        """Test risk exposure HTML with no positions."""
        engine = PaperEngine(balance=100.0)
        re = ReportingEngine(engine)
        rm = RiskMetrics(100.0, 0.0, {}, 0.0, 0.0, 0.0, 0.0)
        html = re._generate_risk_exposure_html(rm)
        assert "No open positions" in html
