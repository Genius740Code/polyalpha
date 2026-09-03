"""
ChainlinkRecorder — ingests 1-s Chainlink ticks, builds OHLC candles,
persists to SQLite, exposes warmup + indicator API.

Thread-safe: ingest() may be called from WS thread; queries from strat thread.
"""

from __future__ import annotations

import logging
import threading
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

import pandas as pd

from .candle import Candle, HISTORY_TIMEFRAME_SECONDS, floor_ts, normalize_timeframe, timeframe_seconds
from .config import ChainlinkHistoryConfig
from .store import Store

log = logging.getLogger(__name__)

try:
    from polyalpha.analysis.indicators import IndicatorCalculator
    from polyalpha.analysis._native_ta import ema as _ema, sma as _sma, rsi as _rsi, macd as _macd, bbands as _bbands
except Exception:  # pragma: no cover
    IndicatorCalculator = None  # type: ignore
    _ema = _sma = _rsi = _macd = _bbands = None  # type: ignore


class ChainlinkRecorder:
    """
    Records Chainlink ticks → candles → SQLite.

    Usage
    -----
    ```python
    rec = ChainlinkRecorder(db_path="~/.polyalpha/chainlink.db",
                            timeframes=("1m","1h"), warmup={"1m":10})
    rec.start("BTC", background=True)
    rec.wait_until_ready({"1m":10}, timeout=600)
    df = rec.candles("BTC","1m",10)
    ema = rec.ema("BTC","1m",10)
    ```
    """

    def __init__(
        self,
        db_path: str | Path = "~/.polyalpha/chainlink.db",
        timeframes: tuple[str, ...] | list[str] | None = None,
        warmup: dict[str, int] | None = None,
        config: ChainlinkHistoryConfig | None = None,
        read_only: bool = False,
        retention: dict[str, int] | None = None,
        keep: dict[str, int] | None = None,
        block: str = "wait",
        block_timeout: float = 600.0,
        prune_unused: bool = True,
        **kwargs,
    ):
        # Build config
        if config is not None:
            self.config = config
        else:
            # warmup may be passed as dict shorthand
            if warmup is None and isinstance(timeframes, dict):
                warmup = timeframes  # allow positional dict
                timeframes = None
            self.config = ChainlinkHistoryConfig(
                timeframes=tuple(timeframes) if timeframes is not None else None,
                warmup=warmup or {},
                keep=keep or retention,
                db_path=str(db_path),
                block=block,  # type: ignore
                block_timeout=block_timeout,
                prune_unused=prune_unused,
            )
        self.db_path = self.config.db_path
        self.read_only = read_only
        self._store = Store(self.db_path, read_only=read_only)
        self._asset: str | None = None
        self._current: dict[tuple[str, str], Candle] = {}
        self._lock = threading.RLock()
        self._streamer = None
        self._started = False
        # keep map for pruning (effective keep = config.keep or warmup)
        self._keep = self.config.effective_keep()

        # initial prune of unused TFs if we have an asset later; but also prune now for all assets?
        # We prune lazily once asset known.

    # ── Lifecycle ────────────────────────────────────────────────────────────

    def start(self, asset: str, background: bool = True) -> None:
        """Start recording for asset (opens WS if writable)."""
        asset = asset.upper()
        if self.read_only:
            self._asset = asset
            return
        with self._lock:
            if self._started and self._asset == asset:
                return
            self._asset = asset
            # prune unused TFs for this asset according to config
            if self.config.prune_unused:
                keep_tfs = list(self._keep.keys()) if self._keep else list(self.config.timeframes or [])
                if keep_tfs:
                    self._store.prune_unused(asset, keep_tfs)
                    for tf, n in (self._keep or {}).items():
                        self._store.prune_keep_last_n(asset, tf, n)

            # attach to Chainlink WS
            try:
                from polyalpha.analysis.streaming import ChainlinkStreamer

                self._streamer = ChainlinkStreamer()
                # hook ingest
                @self._streamer.on("price")
                def _on_price(symbol: str, price: float, ts: datetime):
                    # symbol already upper
                    try:
                        # ts may be datetime with tz
                        epoch = ts.timestamp() if isinstance(ts, datetime) else float(ts)
                    except Exception:
                        epoch = time.time()
                    self.ingest(symbol.upper(), float(price), epoch)

                self._streamer.start(asset, background=background)
                self._started = True
                log.info("ChainlinkRecorder started for %s → %s (tfs=%s keep=%s)", asset, self.db_path, self.config.timeframes, self._keep)
            except Exception as exc:
                log.warning("ChainlinkRecorder: streamer start failed for %s: %s", asset, exc)
                self._started = False

    def stop(self) -> None:
        with self._lock:
            self._flush()
            if self._streamer is not None:
                try:
                    self._streamer.stop()
                except Exception:
                    pass
                self._streamer = None
            self._started = False
            try:
                self._store.close()
            except Exception:
                pass

    def _flush(self) -> None:
        """Flush current forming candles to DB (optional, not counted as closed)."""
        # We don't flush forming candles as closed; only on bucket close do we insert.
        # But ensure any pending finalized candles are already inserted.
        pass

    # ── Ingest — called per tick (~1/s) ─────────────────────────────────────

    def ingest(self, asset: str, price: float, ts: float | None = None) -> None:
        """
        Ingest a Chainlink tick. Thread-safe.
        Buckets price into current candle per timeframe; on bucket boundary,
        finalizes previous candle to SQLite and prunes.
        """
        if self.read_only:
            return
        asset = asset.upper()
        if ts is None:
            ts = time.time()
        # if asset mismatch, ignore (single-asset recorder)
        if self._asset and asset != self._asset:
            # allow multi-asset if configured with multiple assets? v1 single asset
            log.debug("Recorder ingest asset mismatch %s != %s", asset, self._asset)
            return

        timeframes = self.config.timeframes or tuple(self._keep.keys()) or ()
        if not timeframes:
            return

        with self._lock:
            for tf in timeframes:
                tf = normalize_timeframe(tf)
                secs = timeframe_seconds(tf)
                bucket = floor_ts(ts, tf)
                key = (asset, tf)
                cur = self._current.get(key)
                if cur is None:
                    # first tick for this bucket
                    self._current[key] = Candle(asset=asset, timeframe=tf, start_ts=bucket, open=price, high=price, low=price, close=price, count=1)
                elif cur.start_ts == bucket:
                    cur.update(price)
                else:
                    # bucket changed → finalize previous
                    finalized = cur
                    # insert previous
                    try:
                        self._store.insert(finalized)
                        # prune to keep_n
                        keep_n = (self._keep or {}).get(tf)
                        if keep_n is not None:
                            self._store.prune_keep_last_n(asset, tf, keep_n)
                    except Exception as exc:
                        log.warning("Store insert failed for %s %s: %s", asset, tf, exc)
                    # start new candle
                    self._current[key] = Candle(asset=asset, timeframe=tf, start_ts=bucket, open=price, high=price, low=price, close=price, count=1)

    # ── Test helper: inject synthetic ticks without WS ──────────────────────

    def inject_ticks(self, asset: str, ticks: list[tuple[float, float]]) -> None:
        """
        Inject synthetic (ts, price) ticks for testing.
        ticks: list of (epoch_seconds, price)
        """
        for ts, price in ticks:
            self.ingest(asset, price, ts)

    # ── Queries ──────────────────────────────────────────────────────────────

    def count(self, timeframe: str, asset: str | None = None) -> int:
        asset = (asset or self._asset or "BTC").upper()
        return self._store.count(asset, timeframe)

    def is_ready(self, timeframe: str, need: int, asset: str | None = None) -> bool:
        asset = (asset or self._asset or "BTC").upper()
        return self.count(timeframe, asset) >= need

    def is_ready_map(self, need: dict[str, int], asset: str | None = None) -> bool:
        return all(self.is_ready(tf, n, asset) for tf, n in need.items())

    def progress(self, timeframe: str, need: int, asset: str | None = None) -> float:
        if need <= 0:
            return 1.0
        c = self.count(timeframe, asset)
        return min(1.0, c / need)

    def status(self, need: dict[str, int] | None = None, asset: str | None = None) -> dict[str, str]:
        asset = (asset or self._asset or "BTC").upper()
        if need is None:
            need = self._keep or {tf: 0 for tf in (self.config.timeframes or [])}
        return self._store.status(asset, need)

    def candles(
        self, asset: str, timeframe: str, limit: int | None = None
    ) -> pd.DataFrame:
        """
        Return closed candles as DataFrame (oldest first).
        Columns: asset,timeframe,start_ts,open,high,low,close,count,timestamp
        """
        # normalize asset case
        return self._store.get_candles(asset, timeframe, limit=limit, ascending=True)

    def close(self, timeframe: str, asset: str | None = None) -> float | None:
        asset = (asset or self._asset or "BTC").upper()
        return self._store.last_close(asset, timeframe)

    # ── Indicators — delegate to IndicatorCalculator / _native_ta ────────────

    def _df_for_indicator(self, asset: str, timeframe: str, period: int) -> pd.DataFrame | None:
        df = self.candles(asset, timeframe, limit=period)
        # Need at least period rows for indicator (EMA may produce fewer but we check)
        if df.empty or len(df) < period:
            return None
        # IndicatorCalculator expects columns: open, high, low, close, volume
        # Provide volume = count for count-based volume
        if "volume" not in df.columns:
            df = df.copy()
            df["volume"] = df["count"].astype(float)
        # Ensure required columns exist
        for col in ("open", "high", "low", "close", "volume"):
            if col not in df.columns:
                df[col] = df["close"]
        return df

    def ema(self, asset: str, timeframe: str, period: int, price: str = "close") -> float | None:
        df = self._df_for_indicator(asset, timeframe, period)
        if df is None:
            return None
        try:
            if IndicatorCalculator is not None:
                calc = IndicatorCalculator(df)
                series = calc.ema(period, price=price)
                val = series.iloc[-1]
            else:
                series = _ema(df[price], length=period)  # type: ignore
                val = series.iloc[-1]  # type: ignore
            return None if pd.isna(val) else float(val)
        except Exception:
            return None

    def sma(self, asset: str, timeframe: str, period: int, price: str = "close") -> float | None:
        df = self._df_for_indicator(asset, timeframe, period)
        if df is None:
            return None
        try:
            if IndicatorCalculator is not None:
                calc = IndicatorCalculator(df)
                series = calc.sma(period, price=price)
                val = series.iloc[-1]
            else:
                series = _sma(df[price], length=period)  # type: ignore
                val = series.iloc[-1]  # type: ignore
            return None if pd.isna(val) else float(val)
        except Exception:
            return None

    def rsi(self, asset: str, timeframe: str, period: int = 14, price: str = "close") -> float | None:
        df = self._df_for_indicator(asset, timeframe, period)
        if df is None:
            return None
        try:
            if IndicatorCalculator is not None:
                calc = IndicatorCalculator(df)
                series = calc.rsi(period, price=price)
                val = series.iloc[-1]
            else:
                series = _rsi(df[price], length=period)  # type: ignore
                val = series.iloc[-1]  # type: ignore
            return None if pd.isna(val) else float(val)
        except Exception:
            return None

    def macd(self, asset: str, timeframe: str, fast: int = 12, slow: int = 26, signal: int = 9) -> dict | None:
        # need slow+signal rows at least
        need = slow + signal
        df = self._df_for_indicator(asset, timeframe, need)
        if df is None:
            return None
        try:
            if IndicatorCalculator is not None:
                calc = IndicatorCalculator(df)
                out = calc.macd(fast, slow, signal)
                macd_v = out["macd"].iloc[-1]
                sig_v = out["signal"].iloc[-1]
                hist_v = out["histogram"].iloc[-1]
            else:
                out = _macd(df["close"], fast, slow, signal)  # type: ignore
                macd_v = float(out.iloc[-1, 0])
                sig_v = float(out.iloc[-1, 1])
                hist_v = float(out.iloc[-1, 2])
            if pd.isna(macd_v) or pd.isna(sig_v) or pd.isna(hist_v):
                return None
            return {"macd": float(macd_v), "signal": float(sig_v), "histogram": float(hist_v)}
        except Exception:
            return None

    def bollinger_bands(self, asset: str, timeframe: str, period: int = 20, std: float = 2.0) -> dict | None:
        df = self._df_for_indicator(asset, timeframe, period)
        if df is None:
            return None
        try:
            if IndicatorCalculator is not None:
                calc = IndicatorCalculator(df)
                out = calc.bollinger_bands(period, std)
                upper = out["upper"].iloc[-1]
                middle = out["middle"].iloc[-1]
                lower = out["lower"].iloc[-1]
            else:
                out = _bbands(df["close"], length=period, std=std)  # type: ignore
                # native returns BBL, BBM, BBU
                lower = float(out.iloc[-1, 0])
                middle = float(out.iloc[-1, 1])
                upper = float(out.iloc[-1, 2])
            if pd.isna(upper) or pd.isna(middle) or pd.isna(lower):
                return None
            return {"upper": float(upper), "middle": float(middle), "lower": float(lower)}
        except Exception:
            return None

    # ── Warmup helpers ───────────────────────────────────────────────────────

    def wait_until_ready(
        self, need: dict[str, int], timeout: float = 600.0, poll_interval: float = 1.0, asset: str | None = None
    ) -> bool:
        """
        Poll until all need[tf] counts are satisfied or timeout.
        Returns True if ready before timeout.
        """
        asset = (asset or self._asset or "BTC").upper()
        deadline = time.time() + timeout
        while time.time() < deadline:
            if self.is_ready_map(need, asset):
                return True
            time.sleep(poll_interval)
        return self.is_ready_map(need, asset)

    async def wait_until_ready_async(self, need: dict[str, int], timeout: float = 600.0, poll_interval: float = 1.0, asset: str | None = None) -> bool:
        import asyncio

        asset = (asset or self._asset or "BTC").upper()
        deadline = time.time() + timeout
        while time.time() < deadline:
            if self.is_ready_map(need, asset):
                return True
            await asyncio.sleep(poll_interval)
        return self.is_ready_map(need, asset)

    # ── Misc ─────────────────────────────────────────────────────────────────

    def age_s(self, timeframe: str, asset: str | None = None) -> float:
        """Seconds since last closed candle for timeframe."""
        asset = (asset or self._asset or "BTC").upper()
        df = self._store.get_candles(asset, timeframe, limit=1, ascending=False)
        if df.empty:
            return float("inf")
        last_ts = int(df.iloc[0]["start_ts"])
        secs = timeframe_seconds(timeframe)
        # next bucket start = last_ts + secs ; age = now - (last_ts+secs)
        return max(0.0, time.time() - (last_ts + secs))

    def is_fresh(self, timeframe: str, max_age_s: float, asset: str | None = None) -> bool:
        return self.age_s(timeframe, asset) <= max_age_s
