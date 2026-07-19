"""
Report presets tests — run with: pytest tests/unit/report/test_presets.py
"""

from pathlib import Path

import pytest

from polyalpha.trading.paper import PaperEngine
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


@pytest.mark.unit
class TestPresets:
    """Test preset system."""

    def test_load_default(self):
        """Test loading default preset."""
        p = load_preset("default")
        assert p.name == "default"
        assert set(p.metrics) == set(DEFAULT_METRICS)

    def test_load_full(self):
        """Test loading full preset."""
        p = load_preset("full")
        assert "calmar" in p.metrics
        assert "monthly_returns" in p.charts

    def test_load_quick(self):
        """Test loading quick preset."""
        p = load_preset("quick")
        assert "net_pnl" in p.metrics
        assert len(p.metrics) < len(DEFAULT_METRICS)

    def test_load_unknown_raises(self):
        """Test loading unknown preset raises error."""
        with pytest.raises(FileNotFoundError):
            load_preset("__nonexistent_preset__")

    def test_list_presets_includes_builtins(self):
        """Test list presets includes built-in presets."""
        names = list_presets()
        assert "default" in names
        assert "full" in names
        assert "quick" in names

    def test_save_load_delete_roundtrip(self, tmp_path, monkeypatch):
        """Test save, load, delete roundtrip."""
        import polyalpha.report.presets as pmod
        monkeypatch.setattr(pmod, "_PRESET_DIR", tmp_path)

        preset = ReportPreset(
            name="my_test",
            metrics=["net_pnl", "win_rate"],
            charts=["equity_curve"],
            description="test preset",
        )
        path = save_preset(preset)
        assert path.exists()

        loaded = load_preset("my_test")
        assert loaded.name == "my_test"
        assert loaded.metrics == ["net_pnl", "win_rate"]
        assert loaded.charts == ["equity_curve"]

        delete_preset("my_test")
        assert not path.exists()

    def test_save_reserved_name_raises(self, tmp_path, monkeypatch):
        """Test saving reserved name raises error."""
        import polyalpha.report.presets as pmod
        monkeypatch.setattr(pmod, "_PRESET_DIR", tmp_path)

        preset = ReportPreset(name="default", metrics=["net_pnl"], charts=["equity_curve"])
        with pytest.raises(ValueError, match="reserved"):
            save_preset(preset)

    def test_invalid_metric_key_raises(self):
        """Test invalid metric key raises error."""
        with pytest.raises(ValueError, match="Unknown metric"):
            ReportPreset(name="bad", metrics=["__fake_metric__"], charts=[])

    def test_invalid_chart_key_raises(self):
        """Test invalid chart key raises error."""
        with pytest.raises(ValueError, match="Unknown chart"):
            ReportPreset(name="bad", metrics=[], charts=["__fake_chart__"])


@pytest.mark.unit
class TestReportEngine:
    """Test ReportEngine integration."""

    def _make_engine_with_resolved(self, pnls, initial_balance=1000.0):
        """Build a PaperEngine with synthetic resolved positions."""
        import uuid
        from datetime import datetime, timedelta, timezone
        from polyalpha.trading.paper import PaperOrder, PaperPosition

        engine = PaperEngine(balance=initial_balance)
        base = datetime(2025, 1, 1, tzinfo=timezone.utc)

        for i, pnl in enumerate(pnls):
            market_id = f"mkt_{i:04d}"
            slug = f"btc-updown-5m-{i:04d}"
            side = "UP"
            entry_price = 0.70
            amount_in = 10.0
            shares = (amount_in * 0.98) / entry_price  # 2% fee

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

    def test_report_attached_to_engine(self):
        """Test report is attached to engine."""
        engine = PaperEngine(balance=100.0)
        assert engine.report is not None

    def test_trades_empty(self):
        """Test trades are empty for new engine."""
        engine = PaperEngine(balance=100.0)
        assert engine.report.trades() == []

    def test_compute_returns_dict(self):
        """Test compute returns dict."""
        engine = self._make_engine_with_resolved([5.0, -2.0, 3.0])
        m = engine.report.compute(preset="default")
        assert isinstance(m, dict)
        assert "net_pnl" in m

    def test_initial_balance_reconstruction(self):
        """Test initial balance reconstruction."""
        engine = self._make_engine_with_resolved([10.0, -5.0])
        trades = engine.report.trades()
        net = sum(t.pnl for t in trades)
        ib = engine.report._initial_balance(trades)
        assert ib == pytest.approx(engine._balance - net, abs=1e-6)

    def test_html_requires_plotly(self, monkeypatch, tmp_path):
        """Test html() raises ImportError when plotly absent."""
        import builtins
        real_import = builtins.__import__

        def mock_import(name, *args, **kwargs):
            if name == "plotly" or name.startswith("plotly."):
                raise ImportError("No module named 'plotly'")
            return real_import(name, *args, **kwargs)

        engine = self._make_engine_with_resolved([5.0, -2.0])
        out = tmp_path / "report.html"

        monkeypatch.setattr(builtins, "__import__", mock_import)
        with pytest.raises(ImportError, match="plotly"):
            engine.report.html(
                preset="quick",
                path=str(out),
                open_browser=False,
            )

    def test_save_and_list_preset(self, tmp_path, monkeypatch):
        """Test save and list preset through engine."""
        import polyalpha.report.presets as pmod
        monkeypatch.setattr(pmod, "_PRESET_DIR", tmp_path)

        engine = PaperEngine(balance=100.0)
        p = engine.report.save_preset(
            name="engine_test",
            metrics=["net_pnl", "win_rate"],
            charts=["equity_curve"],
        )
        assert p.name == "engine_test"
        assert "engine_test" in engine.report.list_presets()
        engine.report.delete_preset("engine_test")
        assert "engine_test" not in engine.report.list_presets()
