"""
engine.py — ReportEngine: the main entry point for analytics.

Attached to PaperEngine as ``engine.report``.

Usage
-----
    client = polyalpha.Client(balance=1000.0)

    # ... paper trade ...

    # Terminal summary (rich if installed, plain ANSI fallback)
    client.paper.report.show()

    # Interactive HTML dashboard (opens browser)
    client.paper.report.html(open_browser=True)

    # Save to file with a specific preset
    client.paper.report.html(preset="full", path="report.html")

    # Save PNG via matplotlib (requires matplotlib)
    client.paper.report.save_png("report.png")

    # Preset management
    client.paper.report.save_preset(
        name="scalp",
        metrics=["net_pnl", "win_rate", "sharpe"],
        charts=["equity_curve", "pnl_per_trade"],
    )
    print(client.paper.report.list_presets())
"""

from __future__ import annotations

import logging
import os
import tempfile
import webbrowser
from datetime import datetime, timezone
from pathlib import Path
from typing import TYPE_CHECKING, Optional, Union

from .charts import build_charts
from .html_template import generate_html
from .metrics import compute_metrics
from .presets import (
    ReportPreset,
    delete_preset,
    list_presets,
    load_preset,
    save_preset,
)
from .records import TradeRecord, extract_trades
from .terminal import render_terminal

if TYPE_CHECKING:
    from ..trading.paper_engine import PaperEngine
    from ..trading.real_engine import RealTradingEngine

log = logging.getLogger(__name__)


class ReportEngine:
    """
    Analytics and reporting engine for PaperEngine.

    Accessed via ``client.paper.report``.

    Parameters
    ----------
    engine : Union[PaperEngine, RealTradingEngine]
        The trading engine (paper or real) to report on.
    risk_free_rate : float
        Annual risk-free rate used for Sharpe / Sortino (default 0.0).
    """

    def __init__(self, engine: Union["PaperEngine", "RealTradingEngine"], risk_free_rate: float = 0.0) -> None:
        self._engine          = engine
        self._risk_free_rate  = risk_free_rate

    # ── Core extraction ───────────────────────────────────────────────────────

    def trades(self) -> list[TradeRecord]:
        """
        Return all resolved trades extracted from the attached trading engine.

        Returns
        -------
        list[TradeRecord]  sorted chronologically.
        """
        return extract_trades(self._engine)

    # ── Terminal output ───────────────────────────────────────────────────────

    def show(
        self,
        preset: str = "default",
        show_trades: bool = True,
    ) -> None:
        """
        Print the analytics report to stdout.

        Uses ``rich`` if installed, falls back to plain ANSI colour codes.

        Parameters
        ----------
        preset : str
            Preset name to use (default "default").
        show_trades : bool
            Whether to also print the per-trade table.
        """
        _preset  = load_preset(preset)
        _trades  = self.trades()
        _metrics = compute_metrics(
            trades          = _trades,
            initial_balance = self._initial_balance(_trades),
            metric_keys     = _preset.metrics,
            risk_free_rate  = self._risk_free_rate,
        )
        render_terminal(
            metrics         = _metrics,
            trades          = _trades,
            initial_balance = self._initial_balance(_trades),
            preset_name     = preset,
            show_trades     = show_trades,
        )

    # ── HTML dashboard ────────────────────────────────────────────────────────

    def html(
        self,
        preset: str = "default",
        path: Optional[str] = None,
        open_browser: bool = True,
    ) -> str:
        """
        Generate and optionally open an interactive HTML dashboard.

        Parameters
        ----------
        preset : str
            Preset name to use.
        path : str, optional
            File path to save the HTML to.  If None and open_browser=True,
            a temporary file is used.
        open_browser : bool
            Whether to open the file in the default web browser.

        Returns
        -------
        str  Absolute path to the saved HTML file.

        Raises
        ------
        ImportError  if plotly is not installed.
        """
        _preset  = load_preset(preset)
        _trades  = self.trades()
        _ib      = self._initial_balance(_trades)

        _metrics = compute_metrics(
            trades          = _trades,
            initial_balance = _ib,
            metric_keys     = _preset.metrics,
            risk_free_rate  = self._risk_free_rate,
        )

        _charts = build_charts(
            chart_keys      = _preset.charts,
            trades          = _trades,
            initial_balance = _ib,
            risk_free_rate  = self._risk_free_rate,
        )

        html_content = generate_html(
            metrics         = _metrics,
            trades          = _trades,
            charts          = _charts,
            chart_keys      = _preset.charts,
            initial_balance = _ib,
            preset_name     = preset,
            generated_at    = datetime.now(timezone.utc),
        )

        # Determine output path
        if path is not None:
            out_path = Path(path).resolve()
        elif open_browser:
            # Use a temp file in the system temp dir
            fd, tmp = tempfile.mkstemp(suffix=".html", prefix="polyalpha_report_")
            os.close(fd)
            out_path = Path(tmp)
        else:
            raise ValueError("Either 'path' must be specified or 'open_browser' must be True.")

        out_path.write_text(html_content, encoding="utf-8")
        log.info("Report written to %s", out_path)

        if open_browser:
            webbrowser.open(out_path.as_uri())
            log.info("Opening browser at %s", out_path.as_uri())

        return str(out_path)

    # ── PNG export ────────────────────────────────────────────────────────────

    def save_png(
        self,
        path: str,
        preset: str = "default",
        width: int = 1400,
        height: int = 900,
    ) -> str:
        """
        Export the equity curve and drawdown charts as a PNG image.

        Requires ``kaleido`` (``pip install kaleido``) for Plotly static export.

        Parameters
        ----------
        path : str
            Output PNG file path.
        preset : str
        width : int
        height : int

        Returns
        -------
        str  Absolute path to the saved PNG.
        """
        try:
            import plotly.io as pio
        except ImportError:
            raise ImportError(
                "plotly is required for PNG export. "
                "Install with: pip install polyalpha[report]"
            )

        _preset  = load_preset(preset)
        _trades  = self.trades()
        _ib      = self._initial_balance(_trades)

        _charts = build_charts(
            chart_keys      = ["equity_curve", "underwater_dd"],
            trades          = _trades,
            initial_balance = _ib,
            risk_free_rate  = self._risk_free_rate,
        )

        eq_fig = _charts.get("equity_curve")
        if eq_fig is None:
            raise ValueError("No equity curve data available (no resolved trades).")

        out_path = Path(path).resolve()
        pio.write_image(eq_fig, str(out_path), format="png", width=width, height=height)
        log.info("PNG saved to %s", out_path)
        return str(out_path)

    # ── Raw metrics dict ──────────────────────────────────────────────────────

    def compute(
        self,
        preset: str = "default",
    ) -> dict:
        """
        Return the raw metrics dictionary for programmatic use.

        Parameters
        ----------
        preset : str

        Returns
        -------
        dict[str, Any]
        """
        _preset = load_preset(preset)
        _trades = self.trades()
        _ib     = self._initial_balance(_trades)
        return compute_metrics(
            trades          = _trades,
            initial_balance = _ib,
            metric_keys     = _preset.metrics,
            risk_free_rate  = self._risk_free_rate,
        )

    # ── Preset management ─────────────────────────────────────────────────────

    def save_preset(
        self,
        name: str,
        metrics: Optional[list[str]] = None,
        charts:  Optional[list[str]] = None,
        description: str = "",
    ) -> "ReportPreset":
        """
        Create and save a user preset.

        Parameters
        ----------
        name : str
            Preset name (must not be "default", "full", or "quick").
        metrics : list[str], optional
            Metric keys to include.  Defaults to the default preset's metrics.
        charts : list[str], optional
            Chart keys to include.  Defaults to the default preset's charts.
        description : str

        Returns
        -------
        ReportPreset

        Raises
        ------
        ValueError  if name is reserved or keys are invalid.
        """
        from .presets import DEFAULT_METRICS, DEFAULT_CHARTS

        preset = ReportPreset(
            name        = name,
            metrics     = metrics if metrics is not None else list(DEFAULT_METRICS),
            charts      = charts  if charts  is not None else list(DEFAULT_CHARTS),
            description = description,
        )
        path = save_preset(preset)
        log.info("Preset '%s' saved to %s", name, path)
        return preset

    def load_preset(self, name: str) -> "ReportPreset":
        """Load a preset by name."""
        return load_preset(name)

    def list_presets(self) -> list[str]:
        """
        List all available preset names (built-in + user).

        Returns
        -------
        list[str]
        """
        return list_presets()

    def delete_preset(self, name: str) -> None:
        """
        Delete a user preset.

        Parameters
        ----------
        name : str

        Raises
        ------
        ValueError       if attempting to delete a built-in preset.
        FileNotFoundError if not found.
        """
        delete_preset(name)

    # ── Real Trading / Special Reports ────────────────────────────────────────

    def risk_exposure(self) -> str:
        """
        Return the Risk Exposure report as a string.
        """
        from .real_reports import generate_risk_exposure
        return generate_risk_exposure(self._engine)

    def tax_report(self, path: str) -> str:
        """
        Export Tax Report to the given CSV path.
        """
        from .real_reports import export_tax_report
        return export_tax_report(self._engine, path)

    def audit_trail(self, path: str) -> str:
        """
        Export Audit Trail to the given JSON path.
        """
        from .real_reports import export_audit_trail
        return export_audit_trail(self._engine, path)

    # ── Internal helpers ──────────────────────────────────────────────────────

    def _initial_balance(self, trades: list[TradeRecord]) -> float:
        """
        Reconstruct the initial balance from current balance + net PnL of all trades.
        """
        net_pnl = sum(t.pnl for t in trades)
        return self._engine._balance - net_pnl
