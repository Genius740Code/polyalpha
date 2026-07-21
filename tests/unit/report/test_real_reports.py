"""
Real reports tests — run with: pytest tests/unit/report/test_real_reports.py
"""

import json
import uuid
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest

from polyalpha.report.real_reports import export_audit_trail, export_tax_report, generate_risk_exposure
from polyalpha.trading.paper import PaperEngine, PaperOrder, PaperPosition


# ── Helpers ───────────────────────────────────────────────────────────────────

def _make_engine_with_resolved(pnls, initial_balance=1000.0):
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

        pos = PaperPosition(
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
        engine._positions[f"{market_id}:{side}"] = pos

    return engine


def _make_engine_with_open_positions():
    """Build a PaperEngine with open positions (no stop loss)."""
    engine = PaperEngine(balance=1000.0)
    engine._positions["mkt_01:UP"] = PaperPosition(
        market_id="mkt_01", slug="btc-1", question="q1", side="UP",
        shares=10.0, avg_price=0.7, current_price=0.75,
        resolved=False, outcome=None, order_ids=[],
    )
    engine._positions["mkt_02:DOWN"] = PaperPosition(
        market_id="mkt_02", slug="btc-2", question="q2", side="DOWN",
        shares=20.0, avg_price=0.6, current_price=0.55,
        resolved=False, outcome=None, order_ids=[],
    )
    return engine


# ── generate_risk_exposure tests ──────────────────────────────────────────────

@pytest.mark.unit
class TestGenerateRiskExposure:
    """Test generate_risk_exposure."""

    def test_no_positions(self):
        """Test with no positions."""
        engine = PaperEngine(balance=1000.0)
        result = generate_risk_exposure(engine)
        assert "RISK EXPOSURE REPORT" in result
        assert "Available Balance" in result
        assert "No open positions" in result

    def test_with_open_positions(self):
        """Test with open positions."""
        engine = _make_engine_with_open_positions()
        result = generate_risk_exposure(engine)
        assert "RISK EXPOSURE REPORT" in result
        assert "Available Balance" in result
        assert "Total Deployed" in result
        assert "Max Loss Exposure" in result
        assert "Concentration by Market" in result

    def test_position_with_stop_loss(self):
        """Test with a position that has a stop loss."""
        engine = PaperEngine(balance=1000.0)
        engine._positions["mkt_01:UP"] = PaperPosition(
            market_id="mkt_01", slug="btc-1", question="q1", side="UP",
            shares=10.0, avg_price=0.7, current_price=0.75,
            resolved=False, outcome=None, order_ids=[],
            stop_loss=0.65,
        )
        result = generate_risk_exposure(engine)
        assert "RISK EXPOSURE REPORT" in result

    def test_returns_string(self):
        """Test returns a string."""
        engine = PaperEngine(balance=500.0)
        result = generate_risk_exposure(engine)
        assert isinstance(result, str)


# ── export_tax_report tests ───────────────────────────────────────────────────

@pytest.mark.unit
class TestExportTaxReport:
    """Test export_tax_report."""

    def test_writes_csv_file(self, tmp_path):
        """Test writes a CSV file."""
        engine = _make_engine_with_resolved([5.0, -3.0])
        out = tmp_path / "tax_report.csv"
        result = export_tax_report(engine, str(out))
        assert Path(result).exists()
        assert Path(result).suffix == ".csv"

    def test_csv_has_headers(self, tmp_path):
        """Test CSV has correct headers."""
        engine = _make_engine_with_resolved([5.0])
        out = tmp_path / "tax.csv"
        export_tax_report(engine, str(out))
        content = Path(out).read_text(encoding="utf-8")
        assert "TradeID" in content
        assert "RealizedGain" in content
        assert "CostBasis" in content

    def test_csv_has_totals(self, tmp_path):
        """Test CSV has totals row."""
        engine = _make_engine_with_resolved([5.0, -3.0])
        out = tmp_path / "tax.csv"
        export_tax_report(engine, str(out))
        content = Path(out).read_text(encoding="utf-8")
        assert "TOTALS" in content

    def test_empty_engine_writes_csv(self, tmp_path):
        """Test empty engine writes CSV with headers."""
        engine = PaperEngine(balance=1000.0)
        out = tmp_path / "tax.csv"
        export_tax_report(engine, str(out))
        content = Path(out).read_text(encoding="utf-8")
        assert "TradeID" in content

    def test_returns_path_string(self, tmp_path):
        """Test returns the output path as string."""
        engine = _make_engine_with_resolved([5.0])
        out = tmp_path / "tax.csv"
        result = export_tax_report(engine, str(out))
        assert isinstance(result, str)
        assert result == str(Path(out).resolve())

    def test_csv_data_correct(self, tmp_path):
        """Test CSV data is correct."""
        engine = _make_engine_with_resolved([10.0])
        out = tmp_path / "tax.csv"
        export_tax_report(engine, str(out))
        content = Path(out).read_text(encoding="utf-8")
        assert "WON" in content or "UP" in content

    def test_loss_trade_csv(self, tmp_path):
        """Test losing trade appears in CSV."""
        engine = _make_engine_with_resolved([-5.0])
        out = tmp_path / "tax.csv"
        export_tax_report(engine, str(out))
        content = Path(out).read_text(encoding="utf-8")
        assert "LOST" in content or "UP" in content


# ── export_audit_trail tests ──────────────────────────────────────────────────

@pytest.mark.unit
class TestExportAuditTrail:
    """Test export_audit_trail."""

    def test_writes_json_file(self, tmp_path):
        """Test writes a JSON file."""
        engine = _make_engine_with_resolved([5.0, -2.0])
        out = tmp_path / "audit.json"
        result = export_audit_trail(engine, str(out))
        assert Path(result).exists()
        assert Path(result).suffix == ".json"

    def test_json_has_expected_keys(self, tmp_path):
        """Test JSON has expected structure."""
        engine = _make_engine_with_resolved([5.0])
        out = tmp_path / "audit.json"
        export_audit_trail(engine, str(out))
        with open(out) as f:
            data = json.load(f)
        assert "generated_at" in data
        assert "engine_type" in data
        assert "positions" in data
        assert "orders" in data

    def test_positions_in_audit(self, tmp_path):
        """Test positions appear in audit trail."""
        engine = _make_engine_with_resolved([5.0, -3.0])
        out = tmp_path / "audit.json"
        export_audit_trail(engine, str(out))
        with open(out) as f:
            data = json.load(f)
        assert len(data["positions"]) > 0

    def test_orders_in_audit(self, tmp_path):
        """Test orders appear in audit trail."""
        engine = _make_engine_with_resolved([5.0])
        out = tmp_path / "audit.json"
        export_audit_trail(engine, str(out))
        with open(out) as f:
            data = json.load(f)
        assert len(data["orders"]) > 0

    def test_empty_engine(self, tmp_path):
        """Test empty engine exports valid JSON."""
        engine = PaperEngine(balance=1000.0)
        out = tmp_path / "audit.json"
        export_audit_trail(engine, str(out))
        with open(out) as f:
            data = json.load(f)
        assert data["positions"] == []
        assert data["orders"] == []

    def test_returns_path_string(self, tmp_path):
        """Test returns the output path as string."""
        engine = _make_engine_with_resolved([5.0])
        out = tmp_path / "audit.json"
        result = export_audit_trail(engine, str(out))
        assert isinstance(result, str)

    def test_engine_type_correct(self, tmp_path):
        """Test engine_type is correct."""
        engine = _make_engine_with_resolved([5.0])
        out = tmp_path / "audit.json"
        export_audit_trail(engine, str(out))
        with open(out) as f:
            data = json.load(f)
        assert data["engine_type"] == "PaperEngine"

    def test_position_fields(self, tmp_path):
        """Test position fields are present."""
        engine = _make_engine_with_resolved([5.0])
        out = tmp_path / "audit.json"
        export_audit_trail(engine, str(out))
        with open(out) as f:
            data = json.load(f)
        pos = data["positions"][0]
        assert "id" in pos
        assert "market" in pos
        assert "side" in pos
        assert "shares" in pos
        assert "resolved" in pos
        assert pos["resolved"] is True

    def test_order_fields(self, tmp_path):
        """Test order fields are present."""
        engine = _make_engine_with_resolved([5.0])
        out = tmp_path / "audit.json"
        export_audit_trail(engine, str(out))
        with open(out) as f:
            data = json.load(f)
        order = data["orders"][0]
        assert "id" in order
        assert "market" in order
        assert "side" in order
        assert "price" in order
        assert "status" in order
        assert "created_at" in order
