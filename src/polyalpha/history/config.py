"""
ChainlinkHistoryConfig — user-facing config for how much history to keep.

User chooses e.g. {"1m":10, "1h":50, "1s":20} (counts per timeframe).
Those counts are BOTH the warmup gate (block until N closed candles)
AND the retention keep count (delete older, delete unused TFs).

Best format: keep dict drives Store.prune_unused + prune_keep_last_n,
so DB stays minimal (only what user asked for). No unbounded growth.
"""

from __future__ import annotations

import os
from dataclasses import dataclass, field
from pathlib import Path
from typing import Literal

from .candle import normalize_timeframe, timeframe_seconds


def _parse_warmup_str(s: str) -> dict[str, int]:
    """
    Parse env string like "1m:10,1d:50,1h:20" → {"1m":10, "1d":50, ...}
    """
    out: dict[str, int] = {}
    for part in s.split(","):
        part = part.strip()
        if not part:
            continue
        if ":" not in part:
            continue
        tf, n = part.split(":", 1)
        tf = normalize_timeframe(tf.strip())
        try:
            out[tf] = int(n.strip())
        except ValueError:
            continue
    return out


@dataclass
class ChainlinkHistoryConfig:
    """
    Configuration for Chainlink candle history.

    Parameters
    ----------
    timeframes : tuple[str, ...] | None
        Explicit timeframes to build. If None, derived from warmup/keep keys.
    warmup : dict[str,int]
        Required candles per timeframe before strategy fires. Also used as
        default retention (keep) if `keep` not set. Example: {"1m":10, "1h":50, "1s":20}
    keep : dict[str,int] | None
        Retention per timeframe (how many latest candles to keep). None → use warmup.
        If user wants to keep more than warmup needs (e.g. warmup 10 but keep 100 for plots), set both.
    db_path : str | Path
        SQLite file. Default "~/.polyalpha/chainlink.db" (WAL, ~KBs for minutes).
    block : "wait" | "skip" | "call_with_flag"
        How to gate strategy until warm: wait (block), skip (strat guards), flag.
    block_timeout : float
        Seconds to wait for warmup when block="wait" before proceeding anyway.
    prune_unused : bool
        If True (default), delete candles for timeframes not in timeframes/keep.
    persist_raw : bool
        If True, also persist 1s ticks (not recommended — bloat). Default False.
    bootstrap : bool
        If True, allow DataFeed backfill for instant warm (off by default = honest wait).
    """

    timeframes: tuple[str, ...] | None = None
    warmup: dict[str, int] = field(default_factory=dict)
    keep: dict[str, int] | None = None
    db_path: str | Path = "~/.polyalpha/chainlink.db"
    block: Literal["wait", "skip", "call_with_flag"] = "wait"
    block_timeout: float = 600.0
    prune_unused: bool = True
    persist_raw: bool = False
    bootstrap: bool = False
    warmup_emit_interval: float = 5.0

    def __post_init__(self) -> None:
        # normalize keys and validate
        if self.warmup:
            norm: dict[str, int] = {}
            for k, v in self.warmup.items():
                tf = normalize_timeframe(k)
                timeframe_seconds(tf)  # validate
                if v < 0:
                    raise ValueError(f"warmup[{tf}] must be >=0, got {v}")
                norm[tf] = int(v)
            self.warmup = norm
        if self.keep is not None:
            normk: dict[str, int] = {}
            for k, v in self.keep.items():
                tf = normalize_timeframe(k)
                timeframe_seconds(tf)
                if v < 0:
                    raise ValueError(f"keep[{tf}] must be >=0, got {v}")
                normk[tf] = int(v)
            self.keep = normk

        # infer timeframes from warmup/keep if not explicit
        if self.timeframes is None:
            keys = set(self.warmup.keys())
            if self.keep:
                keys.update(self.keep.keys())
            if keys:
                self.timeframes = tuple(sorted(keys, key=lambda t: timeframe_seconds(t)))
            else:
                self.timeframes = ()
        else:
            # normalize provided tuple
            self.timeframes = tuple(normalize_timeframe(t) for t in self.timeframes)
            for tf in self.timeframes:
                timeframe_seconds(tf)

        # keep defaults to warmup if not set
        if self.keep is None and self.warmup:
            self.keep = dict(self.warmup)

        # expand db_path
        if isinstance(self.db_path, str):
            self.db_path = str(Path(self.db_path).expanduser())
        else:
            self.db_path = str(Path(self.db_path).expanduser())

        if self.block not in ("wait", "skip", "call_with_flag"):
            raise ValueError(f"block must be wait|skip|call_with_flag, got {self.block!r}")

    @property
    def retention(self) -> dict[str, int] | None:
        """Alias for keep (compat)."""
        return self.keep

    @classmethod
    def from_env(cls) -> "ChainlinkHistoryConfig | None":
        """
        Build from env if POLYALPHA_CHAINLINK_HISTORY=1.
        Env vars:
          POLYALPHA_CHAINLINK_DB=~/.polyalpha/chainlink.db
          POLYALPHA_CHAINLINK_TFS=1m,1h,1d
          POLYALPHA_CHAINLINK_WARMUP=1m:10,1d:50
          POLYALPHA_CHAINLINK_KEEP=1m:100,1d:200  (optional)
        """
        if os.environ.get("POLYALPHA_CHAINLINK_HISTORY", "").strip().lower() not in ("1", "true", "yes"):
            return None
        db = os.environ.get("POLYALPHA_CHAINLINK_DB", "~/.polyalpha/chainlink.db")
        tfs_raw = os.environ.get("POLYALPHA_CHAINLINK_TFS", "")
        warmup_raw = os.environ.get("POLYALPHA_CHAINLINK_WARMUP", "")
        keep_raw = os.environ.get("POLYALPHA_CHAINLINK_KEEP", "")
        tfs = tuple(s.strip() for s in tfs_raw.split(",") if s.strip()) or None
        warmup = _parse_warmup_str(warmup_raw) if warmup_raw else {}
        keep = _parse_warmup_str(keep_raw) if keep_raw else None
        return cls(timeframes=tfs, warmup=warmup, keep=keep, db_path=db)

    def effective_keep(self) -> dict[str, int]:
        """Return dict timeframe -> keep_n (warmup fallback)."""
        if self.keep is not None:
            return dict(self.keep)
        return dict(self.warmup)

    def to_dict(self) -> dict:
        return {
            "timeframes": list(self.timeframes or []),
            "warmup": dict(self.warmup),
            "keep": dict(self.keep) if self.keep else None,
            "db_path": self.db_path,
            "block": self.block,
        }
