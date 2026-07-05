"""
polyalpha.report — Paper trading analytics and reporting.

Usage
-----
    client = polyalpha.Client(balance=1000.0)

    # ... place and resolve paper trades ...

    # Terminal summary (rich tables)
    client.paper.report.show()

    # Full interactive HTML dashboard
    client.paper.report.html(open_browser=True)

    # Save with a specific preset
    client.paper.report.html(preset="full", path="report.html")

    # Preset management
    client.paper.report.save_preset(
        name="scalp",
        metrics=["net_pnl", "win_rate", "sharpe"],
        charts=["equity_curve", "pnl_per_trade"],
    )
    client.paper.report.list_presets()
"""

from .engine import ReportEngine
from .presets import ReportPreset, list_presets, load_preset, save_preset

__all__ = [
    "ReportEngine",
    "ReportPreset",
    "list_presets",
    "load_preset",
    "save_preset",
]
