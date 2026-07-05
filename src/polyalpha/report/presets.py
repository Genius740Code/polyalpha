"""
presets.py — ReportPreset dataclass, built-in presets, and user preset registry.

Presets are stored as JSON files in ~/.polyalpha/presets/.
Two built-in presets ("default" and "full") are shipped with the library and are
always available even without the directory existing.

Metric keys
-----------
Default:  net_pnl, win_rate, total_trades, sharpe, sortino, max_drawdown,
          profit_factor, avg_win_loss, expectancy, median_holding,
          best_trade, worst_trade

Optional: mean_holding, calmar, omega, skew, kurtosis, var_95, var_99,
          cvar_95, cvar_99, max_consec_wins, max_consec_losses, kelly,
          rolling_sharpe_30d, rolling_sharpe_90d, fill_rate,
          avg_slippage, pnl_concentration, deflated_sharpe,
          avg_position_size, turnover

Chart keys
----------
Default:  equity_curve, underwater_dd, pnl_per_trade, win_loss_dist

Optional: rolling_sharpe, pnl_hour_heatmap, pnl_tte_bucket, return_dist,
          duration_hist, monthly_returns, corr_matrix, entry_calibration
"""

from __future__ import annotations

import json
import logging
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Optional

log = logging.getLogger(__name__)

# ── Storage location ──────────────────────────────────────────────────────────

_PRESET_DIR = Path.home() / ".polyalpha" / "presets"

# ── Canonical key lists ────────────────────────────────────────────────────────

DEFAULT_METRICS: list[str] = [
    "net_pnl",
    "win_rate",
    "total_trades",
    "sharpe",
    "sortino",
    "max_drawdown",
    "profit_factor",
    "avg_win_loss",
    "expectancy",
    "median_holding",
    "best_trade",
    "worst_trade",
]

DEFAULT_CHARTS: list[str] = [
    "equity_curve",
    "underwater_dd",
    "pnl_per_trade",
    "win_loss_dist",
]

OPTIONAL_METRICS: list[str] = [
    "mean_holding",
    "calmar",
    "omega",
    "skew",
    "kurtosis",
    "var_95",
    "var_99",
    "cvar_95",
    "cvar_99",
    "max_consec_wins",
    "max_consec_losses",
    "kelly",
    "rolling_sharpe_30d",
    "rolling_sharpe_90d",
    "fill_rate",
    "avg_slippage",
    "pnl_concentration",
    "deflated_sharpe",
    "avg_position_size",
    "turnover",
]

OPTIONAL_CHARTS: list[str] = [
    "rolling_sharpe",
    "pnl_hour_heatmap",
    "pnl_tte_bucket",
    "return_dist",
    "duration_hist",
    "monthly_returns",
    "corr_matrix",
    "entry_calibration",
]

ALL_METRICS: list[str] = DEFAULT_METRICS + OPTIONAL_METRICS
ALL_CHARTS:  list[str] = DEFAULT_CHARTS  + OPTIONAL_CHARTS

# ── Dataclass ─────────────────────────────────────────────────────────────────

@dataclass
class ReportPreset:
    """
    A named collection of metrics and charts to include in a report.

    Parameters
    ----------
    name : str
        Unique identifier for this preset.
    metrics : list[str]
        Metric keys to compute and display.
    charts : list[str]
        Chart keys to render.
    description : str
        Optional human-readable description.
    """

    name:        str
    metrics:     list[str]       = field(default_factory=lambda: list(DEFAULT_METRICS))
    charts:      list[str]       = field(default_factory=lambda: list(DEFAULT_CHARTS))
    description: str             = ""

    def __post_init__(self) -> None:
        # Validate metric and chart keys
        unknown_m = [m for m in self.metrics if m not in ALL_METRICS]
        if unknown_m:
            raise ValueError(
                f"Unknown metric keys: {unknown_m}. "
                f"Valid keys: {ALL_METRICS}"
            )
        unknown_c = [c for c in self.charts if c not in ALL_CHARTS]
        if unknown_c:
            raise ValueError(
                f"Unknown chart keys: {unknown_c}. "
                f"Valid keys: {ALL_CHARTS}"
            )

    def to_dict(self) -> dict:
        return asdict(self)

    @classmethod
    def from_dict(cls, d: dict) -> "ReportPreset":
        return cls(
            name        = d["name"],
            metrics     = d.get("metrics", list(DEFAULT_METRICS)),
            charts      = d.get("charts",  list(DEFAULT_CHARTS)),
            description = d.get("description", ""),
        )


# ── Built-in presets ──────────────────────────────────────────────────────────

_DEFAULT_PRESET = ReportPreset(
    name        = "default",
    metrics     = list(DEFAULT_METRICS),
    charts      = list(DEFAULT_CHARTS),
    description = "Standard performance metrics and core charts.",
)

_FULL_PRESET = ReportPreset(
    name        = "full",
    metrics     = list(ALL_METRICS),
    charts      = list(ALL_CHARTS),
    description = "All available metrics and charts — maximum detail.",
)

_QUICK_PRESET = ReportPreset(
    name        = "quick",
    metrics     = ["net_pnl", "win_rate", "total_trades", "sharpe", "max_drawdown"],
    charts      = ["equity_curve", "pnl_per_trade"],
    description = "Minimal preset for a fast overview.",
)

_BUILTIN_PRESETS: dict[str, ReportPreset] = {
    "default": _DEFAULT_PRESET,
    "full":    _FULL_PRESET,
    "quick":   _QUICK_PRESET,
}


# ── Registry functions ─────────────────────────────────────────────────────────

def _preset_path(name: str) -> Path:
    return _PRESET_DIR / f"{name}.json"


def list_presets() -> list[str]:
    """
    Return sorted list of all available preset names (built-in + user).

    Returns
    -------
    list[str]
    """
    names = set(_BUILTIN_PRESETS.keys())
    if _PRESET_DIR.exists():
        for p in _PRESET_DIR.glob("*.json"):
            names.add(p.stem)
    return sorted(names)


def load_preset(name: str) -> ReportPreset:
    """
    Load a preset by name.

    Built-in presets ("default", "full", "quick") are always available.
    User presets are loaded from ~/.polyalpha/presets/<name>.json.

    Parameters
    ----------
    name : str

    Returns
    -------
    ReportPreset

    Raises
    ------
    FileNotFoundError  if the preset does not exist.
    """
    if name in _BUILTIN_PRESETS:
        return _BUILTIN_PRESETS[name]

    path = _preset_path(name)
    if not path.exists():
        available = list_presets()
        raise FileNotFoundError(
            f"Preset '{name}' not found. Available: {available}"
        )

    with path.open("r", encoding="utf-8") as f:
        data = json.load(f)

    preset = ReportPreset.from_dict(data)
    log.debug("Loaded preset '%s' from %s", name, path)
    return preset


def save_preset(preset: ReportPreset) -> Path:
    """
    Save a user preset to ~/.polyalpha/presets/<name>.json.

    Parameters
    ----------
    preset : ReportPreset

    Returns
    -------
    Path  path the preset was written to.

    Raises
    ------
    ValueError  if attempting to overwrite a built-in preset name.
    """
    if preset.name in ("default", "full", "quick"):
        raise ValueError(
            f"'{preset.name}' is a reserved built-in preset name. "
            "Choose a different name."
        )

    _PRESET_DIR.mkdir(parents=True, exist_ok=True)
    path = _preset_path(preset.name)

    with path.open("w", encoding="utf-8") as f:
        json.dump(preset.to_dict(), f, indent=2)

    log.info("Saved preset '%s' → %s", preset.name, path)
    return path


def delete_preset(name: str) -> None:
    """
    Delete a user preset.

    Parameters
    ----------
    name : str

    Raises
    ------
    ValueError       if attempting to delete a built-in preset.
    FileNotFoundError if the preset does not exist.
    """
    if name in _BUILTIN_PRESETS:
        raise ValueError(f"Cannot delete built-in preset '{name}'.")

    path = _preset_path(name)
    if not path.exists():
        raise FileNotFoundError(f"Preset '{name}' not found at {path}.")

    path.unlink()
    log.info("Deleted preset '%s'", name)
