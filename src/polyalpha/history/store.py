"""
Store — SQLite persistence for candles.

Best format decision:
- SQLite WAL (write-ahead logging) : concurrent reads while writing,
  crash-safe, single file, zero infra. Better than Parquet (needs rewrite
  per flush) or DuckDB (heavier dep) for incremental 1-s tick → candle.
- WITHOUT ROWID on PRIMARY KEY (asset, timeframe, start_ts) : ~2× faster
  lookups for our exact query pattern (range by start_ts), smaller file.
- REAL for OHLC (8 bytes), INTEGER for start_ts/count.
- PRAGMA journal_mode=WAL, synchronous=NORMAL, busy_timeout=5000,
  cache_size=-64MB for bulk writes.

User chooses how much to keep: warmup dict like {"1m":10, "1h":50, "1s":20}
is both the warmup gate AND the retention count. On init and on every
candle close we:
  1) DELETE unused timeframes (not in keep list) → keeps DB minimal
  2) DELETE oldest rows beyond keep_n per (asset, timeframe)
"""

from __future__ import annotations

import logging
import sqlite3
import threading
import time
from pathlib import Path
from typing import Optional

import pandas as pd

from .candle import Candle, normalize_timeframe

log = logging.getLogger(__name__)

_SCHEMA_VERSION = "1"

_CREATE_SQL = """
CREATE TABLE IF NOT EXISTS candles(
  asset TEXT NOT NULL,
  timeframe TEXT NOT NULL,
  start_ts INTEGER NOT NULL,
  open REAL NOT NULL,
  high REAL NOT NULL,
  low REAL NOT NULL,
  close REAL NOT NULL,
  count INTEGER NOT NULL,
  PRIMARY KEY (asset, timeframe, start_ts)
) WITHOUT ROWID;

CREATE TABLE IF NOT EXISTS meta(
  k TEXT PRIMARY KEY,
  v TEXT
) WITHOUT ROWID;
"""

# WAL pragmas applied once per connection
_PRAGMAS = [
    ("journal_mode", "WAL"),
    ("synchronous", "NORMAL"),
    ("busy_timeout", "5000"),
    ("cache_size", "-64000"),
    ("foreign_keys", "ON"),
]


class Store:
    """Thread-safe SQLite store for candles."""

    def __init__(
        self,
        db_path: str | Path = "~/.polyalpha/chainlink.db",
        read_only: bool = False,
    ):
        self.db_path = Path(str(db_path)).expanduser()
        self.read_only = read_only
        self._lock = threading.RLock()
        # ensure parent exists for writer
        if not read_only:
            self.db_path.parent.mkdir(parents=True, exist_ok=True)
            if not self.db_path.exists():
                # create empty file so URI mode works
                self.db_path.touch()

        self._conn = self._connect()
        self._ensure_schema()

    def _connect(self) -> sqlite3.Connection:
        path = str(self.db_path)
        if self.read_only:
            # URI read-only mode — no lock issues if writer holds WAL
            uri = f"file:{path}?mode=ro"
            conn = sqlite3.connect(uri, uri=True, check_same_thread=False, timeout=5.0)
            # in read-only mode, don't attempt to change journal_mode etc (would fail)
            try:
                cur = conn.cursor()
                cur.execute("PRAGMA busy_timeout=5000")
                cur.execute("PRAGMA foreign_keys=ON")
            except Exception:
                pass
            return conn
        else:
            conn = sqlite3.connect(path, check_same_thread=False, timeout=5.0)
        # pragmas
        cur = conn.cursor()
        for k, v in _PRAGMAS:
            try:
                cur.execute(f"PRAGMA {k}={v}")
            except Exception:
                pass
        conn.commit()
        return conn

    def _ensure_schema(self) -> None:
        if self.read_only:
            # don't try to write in read-only mode; just ensure tables exist by probing
            # if file is new/empty, caller should have created writable DB first
            return
        with self._lock:
            cur = self._conn.cursor()
            cur.executescript(_CREATE_SQL)
            # meta version
            cur.execute("INSERT OR IGNORE INTO meta(k,v) VALUES('schema_version', ?)", (_SCHEMA_VERSION,))
            self._conn.commit()
            # index for ordering (PRIMARY KEY already indexed, but extra index
            # helps SELECT ORDER BY start_ts DESC LIMIT). Without ROWID the PK
            # is the clustered index, so this is redundant but harmless for
            # older data; skip to keep WITHOUT ROWID benefit.
            # No extra index needed.

    # ── Inserts ───────────────────────────────────────────────────────────────

    def insert(self, candle: Candle) -> None:
        """Insert or replace a single candle (thread-safe)."""
        if self.read_only:
            raise RuntimeError("Store is read-only")
        with self._lock:
            self._conn.execute(
                "INSERT OR REPLACE INTO candles(asset,timeframe,start_ts,open,high,low,close,count) VALUES(?,?,?,?,?,?,?,?)",
                candle.to_tuple(),
            )
            self._conn.commit()

    def insert_many(self, candles: list[Candle]) -> None:
        if not candles:
            return
        if self.read_only:
            raise RuntimeError("Store is read-only")
        with self._lock:
            self._conn.executemany(
                "INSERT OR REPLACE INTO candles(asset,timeframe,start_ts,open,high,low,close,count) VALUES(?,?,?,?,?,?,?,?)",
                [c.to_tuple() for c in candles],
            )
            self._conn.commit()

    # ── Queries ───────────────────────────────────────────────────────────────

    def count(self, asset: str, timeframe: str) -> int:
        asset = asset.upper()
        timeframe = normalize_timeframe(timeframe)
        with self._lock:
            cur = self._conn.execute(
                "SELECT COUNT(*) FROM candles WHERE asset=? AND timeframe=?",
                (asset, timeframe),
            )
            return int(cur.fetchone()[0])

    def get_candles(
        self, asset: str, timeframe: str, limit: int | None = None, ascending: bool = True
    ) -> pd.DataFrame:
        """
        Return candles as DataFrame ordered by start_ts.

        Columns: asset, timeframe, start_ts, open, high, low, close, count, timestamp
        """
        asset = asset.upper()
        timeframe = normalize_timeframe(timeframe)
        with self._lock:
            if limit is not None:
                cur = self._conn.execute(
                    "SELECT asset,timeframe,start_ts,open,high,low,close,count FROM candles "
                    "WHERE asset=? AND timeframe=? ORDER BY start_ts DESC LIMIT ?",
                    (asset, timeframe, limit),
                )
            else:
                cur = self._conn.execute(
                    "SELECT asset,timeframe,start_ts,open,high,low,close,count FROM candles "
                    "WHERE asset=? AND timeframe=? ORDER BY start_ts DESC",
                    (asset, timeframe),
                )
            rows = cur.fetchall()
        if not rows:
            return pd.DataFrame(
                columns=["asset", "timeframe", "start_ts", "open", "high", "low", "close", "count", "timestamp"]
            )
        df = pd.DataFrame(
            rows, columns=["asset", "timeframe", "start_ts", "open", "high", "low", "close", "count"]
        )
        # stored DESC, reverse for ascending (oldest first) which TA expects
        df = df.iloc[::-1].reset_index(drop=True) if ascending else df
        # add timestamp column for IndicatorCalculator compat
        df["timestamp"] = pd.to_datetime(df["start_ts"], unit="s", utc=True)
        # keep consistent dtypes
        return df

    def last_close(self, asset: str, timeframe: str) -> float | None:
        asset = asset.upper()
        timeframe = normalize_timeframe(timeframe)
        with self._lock:
            cur = self._conn.execute(
                "SELECT close FROM candles WHERE asset=? AND timeframe=? ORDER BY start_ts DESC LIMIT 1",
                (asset, timeframe),
            )
            row = cur.fetchone()
            return float(row[0]) if row else None

    def status(self, asset: str, need: dict[str, int] | None = None) -> dict[str, str]:
        """Return progress per timeframe: {"1m": "7/10", ...}. If need is None, counts only."""
        out: dict[str, str] = {}
        if need:
            for tf, n in need.items():
                tf_n = normalize_timeframe(tf)
                c = self.count(asset, tf_n)
                out[tf_n] = f"{c}/{n}" + (" ✅" if c >= n else "")
        else:
            # list all TFs for asset
            with self._lock:
                cur = self._conn.execute(
                    "SELECT timeframe, COUNT(*) FROM candles WHERE asset=? GROUP BY timeframe",
                    (asset.upper(),),
                )
                for tf, cnt in cur.fetchall():
                    out[tf] = str(cnt)
        return out

    # ── Pruning — keep DB minimal per user choice ───────────────────────────

    def prune_unused(self, asset: str, keep_timeframes: list[str] | tuple[str, ...] | set[str]) -> int:
        """
        Delete all candles for *asset* whose timeframe is NOT in keep_timeframes.
        Returns number of rows deleted.
        """
        if not keep_timeframes:
            return 0
        asset = asset.upper()
        keep = {normalize_timeframe(t) for t in keep_timeframes}
        if not keep:
            return 0
        placeholders = ",".join("?" for _ in keep)
        with self._lock:
            cur = self._conn.execute(
                f"DELETE FROM candles WHERE asset=? AND timeframe NOT IN ({placeholders})",
                (asset, *keep),
            )
            deleted = cur.rowcount
            self._conn.commit()
            if deleted:
                log.info("Pruned %d unused timeframe rows for %s (keep %s)", deleted, asset, sorted(keep))
            return deleted

    def prune_keep_last_n(self, asset: str, timeframe: str, keep_n: int) -> int:
        """
        Keep only the latest keep_n candles for (asset, timeframe), delete older.
        Returns rows deleted.
        """
        if keep_n <= 0:
            # delete all for this TF
            asset = asset.upper()
            timeframe = normalize_timeframe(timeframe)
            with self._lock:
                cur = self._conn.execute(
                    "DELETE FROM candles WHERE asset=? AND timeframe=?", (asset, timeframe)
                )
                deleted = cur.rowcount
                self._conn.commit()
                return deleted
        asset = asset.upper()
        timeframe = normalize_timeframe(timeframe)
        with self._lock:
            # delete where start_ts NOT in newest keep_n
            cur = self._conn.execute(
                """
                DELETE FROM candles WHERE asset=? AND timeframe=? AND start_ts NOT IN (
                    SELECT start_ts FROM candles WHERE asset=? AND timeframe=? ORDER BY start_ts DESC LIMIT ?
                )
                """,
                (asset, timeframe, asset, timeframe, keep_n),
            )
            deleted = cur.rowcount
            self._conn.commit()
            if deleted:
                log.debug("Pruned %d excess %s %s candles (keep %d)", deleted, asset, timeframe, keep_n)
            return deleted

    def prune_all(self, asset: str, keep: dict[str, int]) -> int:
        """
        Convenience: for asset, delete unused TFs and trim each keep TF to keep_n.
        Returns total deleted.
        """
        if not keep:
            return 0
        total = 0
        total += self.prune_unused(asset, list(keep.keys()))
        for tf, n in keep.items():
            total += self.prune_keep_last_n(asset, tf, n)
        return total

    def delete_asset(self, asset: str) -> int:
        with self._lock:
            cur = self._conn.execute("DELETE FROM candles WHERE asset=?", (asset.upper(),))
            deleted = cur.rowcount
            self._conn.commit()
            return deleted

    def close(self) -> None:
        with self._lock:
            try:
                self._conn.commit()
                self._conn.close()
            except Exception:
                pass
