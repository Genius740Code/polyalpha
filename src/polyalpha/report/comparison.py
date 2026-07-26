"""
comparison.py — Variant comparison engine for BotHub.

Builds, renders, persists and reloads cross-variant comparison reports.
A *variant* is a registered strategy-like entry on ``BotHub`` that carries
free-form parameter metadata. Each variant runs in its own isolated
``PaperEngine`` so its P&L, win rate, trade count and Sharpe can be
compared against the other variants on the same shared data stream.

Design notes
------------
* Each variant's trades are extracted via ``extract_trades()`` from
  ``records.py`` (the same extractor used by the regular ReportEngine).
* Per-variant metrics are computed via ``compute_metrics()`` from
  ``metrics.py`` so the math is identical between BotHub comparisons and
  single-engine reports.
* Persistence uses plain JSON (no engine coupling) and a stable
  filesystem layout: ``~/.polyalpha/variants/{asset}_{timeframe}_{ts}.json``.
  No external dependencies are required beyond the standard library.
* Rich table rendering is optional — the ``print()`` method imports
  ``rich`` lazily so the rest of the module works even if ``rich`` is
  unavailable.

Public API
----------
- ``VariantResult``      : per-variant row dataclass
- ``ComparisonReport``   : top-level report (sorted list of VariantResult)
- ``build_variant_result(variant)`` : helper that turns a ``Variant`` into a row
- ``list_runs(directory=None)``     : list persisted snapshots
- ``load_run(timestamp, directory=None)`` : reload a snapshot
"""

from __future__ import annotations

import json
import math
import re
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import TYPE_CHECKING, Any, Optional

from .metrics import compute_metrics
from .records import extract_trades

if TYPE_CHECKING:  # pragma: no cover - typing only
    from ..bot_hub import Variant

# ── Default metrics computed per variant for comparison ───────────────────────

DEFAULT_COMPARISON_METRICS: list[str] = [
    "net_pnl",
    "win_rate",
    "total_trades",
    "sharpe",
    "max_drawdown",
]

# ── Filesystem layout for persistence ─────────────────────────────────────────

DEFAULT_VARIANT_DIR = Path.home() / ".polyalpha" / "variants"

# Timestamp format safe for filenames — no colons (cross-platform).
_TIMESTAMP_FMT = "%Y-%m-%dT%H-%M-%S"


# ── VariantResult ─────────────────────────────────────────────────────────────

@dataclass
class VariantResult:
    """One row in a ``ComparisonReport`` — per-variant metrics snapshot.

    All numeric fields are rounded to 4 decimal places for stable
    serialisation. ``pnl`` is in USDC, ``win_rate`` is a fraction in [0,1],
    ``sharpe`` and ``max_drawdown_pct`` are unitless. Fields default to
    ``NaN`` when a variant has not yet produced any resolved trades.
    """

    name: str
    id: str
    balance: float
    pnl: float
    win_rate: float
    trade_count: int
    sharpe: Optional[float]
    max_drawdown_pct: Optional[float]
    params: dict = field(default_factory=dict)
    created_at: str = ""

    def is_nan(self) -> bool:
        """True if the variant produced no resolved trades (all-NaN row)."""
        return math.isnan(self.pnl) and self.trade_count == 0

    def dump(self) -> dict:
        """JSON-serialisable representation."""
        return {
            "name": self.name,
            "id": self.id,
            "balance": round(self.balance, 4),
            "pnl": None if math.isnan(self.pnl) else round(self.pnl, 4),
            "win_rate": None if math.isnan(self.win_rate) else round(self.win_rate, 4),
            "trade_count": self.trade_count,
            "sharpe": None if self.sharpe is None or (isinstance(self.sharpe, float) and math.isnan(self.sharpe)) else round(self.sharpe, 4),
            "max_drawdown_pct": None if self.max_drawdown_pct is None or (
                isinstance(self.max_drawdown_pct, float) and math.isnan(self.max_drawdown_pct)
            ) else round(self.max_drawdown_pct, 4),
            "params": self.params,
            "created_at": self.created_at,
        }


# ── ComparisonReport ──────────────────────────────────────────────────────────

@dataclass
class ComparisonReport:
    """Top-level report: a sorted list of ``VariantResult`` rows.

    A report with zero ``results`` is a valid "no variants registered" or
    "all variants yielded no resolved trades" outcome.

    Attributes
    ----------
    results : list[VariantResult]
        Sorted by P&L descending (NaN last).
    asset : str
        Hub asset (e.g. ``"BTC"``).
    timeframe : str
        Hub timeframe (e.g. ``"5m"``).
    timestamp : datetime
        UTC moment when the report was constructed.
    """

    results: list[VariantResult] = field(default_factory=list)
    asset: str = ""
    timeframe: str = ""
    timestamp: datetime = field(default_factory=lambda: datetime.now(timezone.utc))

    # ── Accessors ──────────────────────────────────────────────────────────

    @property
    def variant_count(self) -> int:
        return len(self.results)

    @property
    def best(self) -> Optional[VariantResult]:
        """Top variant by P&L (None if empty)."""
        return self.results[0] if self.results else None

    @property
    def worst(self) -> Optional[VariantResult]:
        """Bottom variant by P&L (None if empty)."""
        return self.results[-1] if self.results else None

    def get(self, name: str) -> Optional[VariantResult]:
        """Look up a variant by name (None if absent)."""
        for r in self.results:
            if r.name == name:
                return r
        return None

    # ── Rendering ─────────────────────────────────────────────────────────

    def dump(self) -> dict:
        """JSON-serialisable representation (round-trips via ``load_run``)."""
        return {
            "asset": self.asset,
            "timeframe": self.timeframe,
            "timestamp": self.timestamp.strftime(_TIMESTAMP_FMT),
            "variant_count": len(self.results),
            "results": [r.dump() for r in self.results],
        }

    def print(self, console: Any = None) -> None:  # noqa: A003 - public API name
        """
        Render the comparison as a Rich table.

        Parameters
        ----------
        console : rich.console.Console, optional
            Reuse an existing Console. Creates one lazily if omitted. If
            ``rich`` is not installed, falls back to a plain text table
            printed to stdout.
        """
        try:
            from rich.console import Console
            from rich.table import Table
            from rich import box
        except ImportError:
            self._print_plain()
            return

        con = console or Console()
        title = f"Polyalpha · Variant Comparison · {self.asset} {self.timeframe} · {self.timestamp.strftime('%Y-%m-%d %H:%M:%S UTC')}"
        con.rule(f"[bold white]{title}[/]", style="dim blue")

        table = Table(
            box=box.SIMPLE,
            show_header=True,
            header_style="bold dim",
            padding=(0, 2),
        )
        table.add_column("Rank", style="dim", width=4, justify="right")
        table.add_column("Variant", min_width=14)
        table.add_column("Balance", justify="right", min_width=10)
        table.add_column("P&L", justify="right", min_width=10)
        table.add_column("Win%", justify="right", min_width=8)
        table.add_column("Trades", justify="right", width=7)
        table.add_column("Sharpe", justify="right", min_width=8)
        table.add_column("Max DD%", justify="right", min_width=10)
        table.add_column("Params", min_width=18, overflow="fold")

        for i, r in enumerate(self.results, 1):
            pnl_str = f"${r.pnl:+.4f}" if not math.isnan(r.pnl) else "—"
            win_str = f"{r.win_rate * 100:.1f}%" if not math.isnan(r.win_rate) else "—"
            sharpe_str = f"{r.sharpe:.3f}" if (
                r.sharpe is not None and not (isinstance(r.sharpe, float) and math.isnan(r.sharpe))
            ) else "—"
            dd_str = f"{r.max_drawdown_pct:.2f}%" if (
                r.max_drawdown_pct is not None
                and not (isinstance(r.max_drawdown_pct, float) and math.isnan(r.max_drawdown_pct))
            ) else "—"
            pnl_style = "green" if (not math.isnan(r.pnl) and r.pnl > 0) else (
                "red" if (not math.isnan(r.pnl) and r.pnl < 0) else "dim"
            )
            params_str = ", ".join(f"{k}={v}" for k, v in r.params.items()) if r.params else "—"
            table.add_row(
                str(i),
                r.name,
                f"${r.balance:.2f}",
                f"[{pnl_style}]{pnl_str}[/]",
                win_str,
                str(r.trade_count),
                sharpe_str,
                dd_str,
                params_str,
            )

        con.print(table)

    def _print_plain(self) -> None:
        """Fallback text-table renderer (no rich dependency)."""
        if not self.results:
            print(f"Variant comparison ({self.asset} {self.timeframe}): no variants.")
            return

        rows = [
            (i, r.name, f"{r.balance:.2f}", f"{r.pnl:+.4f}",
             f"{r.win_rate * 100:.1f}%" if not math.isnan(r.win_rate) else "—",
             str(r.trade_count),
             f"{r.sharpe:.3f}" if r.sharpe is not None else "—",
             f"{r.max_drawdown_pct:.2f}%" if r.max_drawdown_pct is not None else "—")
            for i, r in enumerate(self.results, 1)
        ]
        headers = ("Rank", "Variant", "Balance", "P&L", "Win%", "Trades", "Sharpe", "MaxDD%")
        cols = list(zip(headers, *rows))
        widths = [max(len(str(c[0])), *(len(str(c[k])) for k in range(1, len(c)))) for c in cols]
        fmt = "  ".join(f"{{:>{w}}}" for w in widths)
        print(f"Polyalpha · Variant Comparison · {self.asset} {self.timeframe}")
        print(fmt.format(*[h for h, _ in cols]))
        print(fmt.format(*["-" * w for w in widths]))
        for r in rows:
            print(fmt.format(*r))

    def __repr__(self) -> str:
        return (
            f"ComparisonReport(asset={self.asset!r}, timeframe={self.timeframe!r}, "
            f"variant_count={len(self.results)})"
        )

    def __str__(self) -> str:
        return repr(self)

    # ── Persistence ─────────────────────────────────────────────────────────

    def save(self, directory: Optional[str] = None) -> Path:
        """
        Persist the comparison snapshot to disk as JSON.

        Parameters
        ----------
        directory : str, optional
            Target directory. Defaults to ``~/.polyalpha/variants``.

        Returns
        -------
        pathlib.Path
            Path the snapshot was written to.

        Raises
        ------
        OSError
            If the directory cannot be created or the file written.
        """
        out_dir = Path(directory) if directory else DEFAULT_VARIANT_DIR
        out_dir.mkdir(parents=True, exist_ok=True)
        ts = self.timestamp.strftime(_TIMESTAMP_FMT)
        fname = f"{self.asset}_{self.timeframe}_{ts}.json"
        path = out_dir / fname
        with path.open("w", encoding="utf-8") as fh:
            json.dump(self.dump(), fh, indent=2, sort_keys=True)
        return path

    # ── Rebuild from snapshot ───────────────────────────────────────────────

    @classmethod
    def from_dict(cls, data: dict) -> ComparisonReport:
        """Reconstruct a ``ComparisonReport`` from a ``dump()`` dict."""
        results = []
        for row in data.get("results", []):
            results.append(
                VariantResult(
                    name=row.get("name", ""),
                    id=row.get("id", row.get("name", "")),
                    balance=float(row.get("balance") or 0.0),
                    pnl=float(row["pnl"]) if row.get("pnl") is not None else float("nan"),
                    win_rate=float(row["win_rate"]) if row.get("win_rate") is not None else float("nan"),
                    trade_count=int(row.get("trade_count", 0)),
                    sharpe=row.get("sharpe"),
                    max_drawdown_pct=row.get("max_drawdown_pct"),
                    params=dict(row.get("params") or {}),
                    created_at=row.get("created_at", ""),
                )
            )
        ts_str = data.get("timestamp")
        ts = datetime.strptime(ts_str, _TIMESTAMP_FMT).replace(tzinfo=timezone.utc) if ts_str else datetime.now(timezone.utc)
        return cls(
            results=results,
            asset=data.get("asset", ""),
            timeframe=data.get("timeframe", ""),
            timestamp=ts,
        )


# ── Free helpers ──────────────────────────────────────────────────────────────

def build_variant_result(variant: Variant) -> VariantResult:
    """
    Extract a ``VariantResult`` (P&L, win rate, trades, Sharpe, max DD) from
    a BotHub strategy's isolated ``PaperEngine``.

    If the strategy's ``PaperEngine`` is ``None`` (not yet discovered) or
    has produced no resolved trades, the returned row carries NaN values
    and a zero trade count so it sorts last by P&L descending.
    """
    paper = variant.paper
    if paper is None:
        return VariantResult(
            name=variant.name,
            id=variant.id,
            balance=variant.balance,
            pnl=float("nan"),
            win_rate=float("nan"),
            trade_count=0,
            sharpe=None,
            max_drawdown_pct=None,
            params=dict(variant.params),
            created_at=variant.created_at.isoformat() if isinstance(variant.created_at, datetime) else str(variant.created_at),
        )

    trades = extract_trades(paper)

    # P&L from all resolved positions.
    pnl = float(sum(t.pnl for t in trades)) if trades else float("nan")

    # Win rate (fraction in [0, 1]).
    if trades:
        wins = sum(1 for t in trades if t.pnl > 0)
        win_rate = wins / len(trades)
    else:
        win_rate = float("nan")

    # Use compute_metrics for sharpe + max_drawdown so the math is
    # identical between BotHub comparison and single-engine report.
    metrics = compute_metrics(
        trades,
        initial_balance=variant.balance,
        metric_keys=DEFAULT_COMPARISON_METRICS,
    ) if trades else {}

    sharpe = metrics.get("sharpe")
    max_dd = metrics.get("max_drawdown")
    max_dd_pct = max_dd.get("pct") if isinstance(max_dd, dict) else max_dd

    return VariantResult(
        name=variant.name,
        id=variant.id,
        balance=paper.balance,
        pnl=pnl,
        win_rate=win_rate,
        trade_count=len(trades),
        sharpe=sharpe,
        max_drawdown_pct=max_dd_pct,
        params=dict(variant.params),
        created_at=variant.created_at.isoformat() if isinstance(variant.created_at, datetime) else str(variant.created_at),
    )


# ── Persistence helpers (module-level) ────────────────────────────────────────

def list_runs(directory: Optional[str] = None) -> list[dict]:
    """
    List previous comparison snapshots in a directory.

    Returns a list of dicts sorted newest-first (by embedded timestamp).
    Each dict carries: ``timestamp`` (str), ``asset`` (str), ``timeframe``
    (str), ``path`` (str), and ``variants`` (list[str]).
    """
    out_dir = Path(directory) if directory else DEFAULT_VARIANT_DIR
    if not out_dir.is_dir():
        return []

    pattern = re.compile(
        r"^(?P<asset>[A-Z]+)_(?P<timeframe>[0-9a-z]+)_(?P<ts>\d{4}-\d{2}-\d{2}T\d{2}-\d{2}-\d{2})\.json$",
        re.IGNORECASE,
    )
    runs: list[dict] = []
    for path in out_dir.iterdir():
        m = pattern.match(path.name)
        if not m:
            continue
        try:
            with path.open("r", encoding="utf-8") as fh:
                data = json.load(fh)
        except (OSError, json.JSONDecodeError):
            continue
        runs.append({
            "timestamp": m.group("ts"),
            "asset": data.get("asset", m.group("asset")),
            "timeframe": data.get("timeframe", m.group("timeframe")),
            "path": str(path),
            "variants": [r.get("name", "") for r in data.get("results", [])],
        })
    runs.sort(key=lambda r: r["timestamp"], reverse=True)
    return runs


def load_run(timestamp: str, directory: Optional[str] = None) -> ComparisonReport:
    """
    Reload a comparison snapshot by timestamp.

    Parameters
    ----------
    timestamp : str
        ISO timestamp matching the snapshot filename suffix (e.g.
        ``"2026-07-24T15-30-00"``).
    directory : str, optional
        Snapshot directory. Defaults to ``~/.polyalpha/variants``.

    Returns
    -------
    ComparisonReport

    Raises
    ------
    FileNotFoundError
        If no snapshot matches the timestamp.
    ValueError
        If the snapshot file is corrupt.
    """
    out_dir = Path(directory) if directory else DEFAULT_VARIANT_DIR
    if not out_dir.is_dir():
        raise FileNotFoundError(f"Variant directory not found: {out_dir}")
    # Match any asset/timeframe prefix for the given timestamp suffix.
    candidates = list(out_dir.glob(f"*_{timestamp}.json"))
    if not candidates:
        raise FileNotFoundError(
            f"No variant snapshot for timestamp '{timestamp}' in {out_dir}"
        )
    if len(candidates) > 1:
        # Disambiguate by asset/timeframe if multiple files share a timestamp.
        raise ValueError(
            f"Multiple snapshots match timestamp '{timestamp}': "
            f"{[p.name for p in candidates]}"
        )
    try:
        with candidates[0].open("r", encoding="utf-8") as fh:
            data = json.load(fh)
    except json.JSONDecodeError as exc:
        raise ValueError(f"Corrupt snapshot {candidates[0]}: {exc}") from exc
    return ComparisonReport.from_dict(data)


__all__ = [
    "VariantResult",
    "ComparisonReport",
    "build_variant_result",
    "list_runs",
    "load_run",
    "DEFAULT_COMPARISON_METRICS",
]
