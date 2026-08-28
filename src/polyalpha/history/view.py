"""
ChainlinkHistoryView — read-only facade per strat.

Delegates to shared Store/Recorder but captures asset + strat name for
logging / warmup isolation. Same surface as Recorder for queries.
"""

from __future__ import annotations

import pandas as pd

from .recorder import ChainlinkRecorder


class ChainlinkHistoryView:
    """
    Thin view over a shared ChainlinkRecorder.

    Each StrategyContext / TickContext gets its own View so logs can
    include strat name, but all views share the same SQLite file.
    """

    def __init__(self, recorder: ChainlinkRecorder, asset: str, strat_name: str = ""):
        self._rec = recorder
        self.asset = asset.upper()
        self.strat_name = strat_name

    # ── Passthroughs ───────────────────────────────────────────────────────

    def count(self, timeframe: str, asset: str | None = None) -> int:
        return self._rec.count(timeframe, asset or self.asset)

    def is_ready(self, timeframe: str, need: int, asset: str | None = None) -> bool:
        return self._rec.is_ready(timeframe, need, asset or self.asset)

    def is_ready_map(self, need: dict[str, int], asset: str | None = None) -> bool:
        return self._rec.is_ready_map(need, asset or self.asset)

    def progress(self, timeframe: str, need: int, asset: str | None = None) -> float:
        return self._rec.progress(timeframe, need, asset or self.asset)

    def status(self, need: dict[str, int] | None = None, asset: str | None = None) -> dict[str, str]:
        return self._rec.status(need, asset or self.asset)

    def candles(self, timeframe: str, limit: int | None = None, asset: str | None = None) -> pd.DataFrame:
        # recorder.candles expects (asset, timeframe, limit)
        return self._rec.candles(asset or self.asset, timeframe, limit)

    def close(self, timeframe: str, asset: str | None = None) -> float | None:
        return self._rec.close(timeframe, asset or self.asset)

    # ── Indicator helpers — support both signatures
    # plan uses 3-arg: ema("BTC","1m",10)  ; shorthand: ema("1m",10)
    def _resolve(self, *args, asset_kw=None, default_period=None):
        """
        Resolve (asset, timeframe, period) from flexible args.
        - ema("BTC","1m",10) -> asset=BTC tf=1m period=10
        - ema("1m",10)       -> asset=self.asset tf=1m period=10
        - ema(timeframe="1m", period=10, asset="BTC") -> same
        """
        if asset_kw is not None:
            asset = asset_kw
            if len(args) == 2:
                tf, period = args
                return asset, tf, period
            if len(args) == 1:
                # ambiguous; assume tf
                return asset, args[0], default_period
        if len(args) == 3:
            return args[0], args[1], args[2]
        if len(args) == 2:
            # could be (tf, period)  or (asset, tf) with period in kwargs (not used)
            # heuristic: if first arg is known asset, treat as asset
            if isinstance(args[0], str) and args[0].upper() in ("BTC", "ETH", "SOL", "XRP", "DOGE", "HYPE", "BNB"):
                # but then missing period -> unlikely; treat as asset+tf where period is default?
                # For 2-arg asset case we assume not used; just treat as tf+period with default asset
                pass
            return self.asset, args[0], args[1]
        if len(args) == 1:
            return self.asset, args[0], default_period
        raise TypeError(f"expected (timeframe, period) or (asset, timeframe, period), got {args}")

    def ema(self, *args, **kwargs) -> float | None:
        asset_kw = kwargs.pop("asset", None)
        period_kw = kwargs.pop("period", None)
        tf_kw = kwargs.pop("timeframe", None)
        if tf_kw is not None:
            # called with kwargs
            asset = kwargs.pop("asset", asset_kw) or asset_kw or self.asset
            # allow ema(asset="BTC", timeframe="1m", period=10)
            if args:
                # prefer args
                pass
            period = period_kw if period_kw is not None else (args[0] if args else None)
            tf = tf_kw
            # if args has asset
            if len(args) == 2 and asset_kw is None:
                # ema("BTC","1m",10) with tf_kw given shouldn't happen
                pass
            return self._rec.ema(asset or self.asset, tf, period)  # type: ignore
        # positional
        asset, tf, period = self._resolve(*args, asset_kw=asset_kw)
        return self._rec.ema(asset, tf, period)  # type: ignore

    def sma(self, *args, **kwargs) -> float | None:
        asset_kw = kwargs.pop("asset", None)
        tf_kw = kwargs.pop("timeframe", None)
        period_kw = kwargs.pop("period", None)
        if tf_kw is not None:
            asset = asset_kw or self.asset
            period = period_kw if period_kw is not None else (args[0] if args else None)
            return self._rec.sma(asset, tf_kw, period)  # type: ignore
        asset, tf, period = self._resolve(*args, asset_kw=asset_kw)
        return self._rec.sma(asset, tf, period)  # type: ignore

    def rsi(self, *args, **kwargs) -> float | None:
        asset_kw = kwargs.pop("asset", None)
        tf_kw = kwargs.pop("timeframe", None)
        period_kw = kwargs.pop("period", None)
        if tf_kw is not None:
            asset = asset_kw or self.asset
            period = period_kw if period_kw is not None else (args[0] if args else 14)
            return self._rec.rsi(asset, tf_kw, period)  # type: ignore
        # rsi can be called as rsi("1m",14) or rsi("BTC","1m",14) or rsi("1m")
        if len(args) == 1:
            return self._rec.rsi(self.asset, args[0], 14)
        asset, tf, period = self._resolve(*args, asset_kw=asset_kw, default_period=14)
        if period is None:
            period = 14
        return self._rec.rsi(asset, tf, period)  # type: ignore

    def macd(self, *args, **kwargs) -> dict | None:
        # macd signatures: macd("BTC","1d",12,26,9) or macd("1d") or macd("1d",12,26,9)
        asset_kw = kwargs.pop("asset", None)
        if "timeframe" in kwargs:
            tf = kwargs.pop("timeframe")
            asset = asset_kw or self.asset
            fast = kwargs.pop("fast", 12)
            slow = kwargs.pop("slow", 26)
            signal = kwargs.pop("signal", 9)
            return self._rec.macd(asset, tf, fast, slow, signal)
        if len(args) >= 1 and isinstance(args[0], str) and args[0].upper() in ("BTC", "ETH", "SOL", "XRP", "DOGE", "HYPE", "BNB"):
            # first arg asset
            asset = args[0]
            tf = args[1] if len(args) > 1 else "1d"
            fast = args[2] if len(args) > 2 else kwargs.get("fast", 12)
            slow = args[3] if len(args) > 3 else kwargs.get("slow", 26)
            signal = args[4] if len(args) > 4 else kwargs.get("signal", 9)
            return self._rec.macd(asset, tf, fast, slow, signal)
        else:
            tf = args[0] if args else "1d"
            fast = args[1] if len(args) > 1 else kwargs.get("fast", 12)
            slow = args[2] if len(args) > 2 else kwargs.get("slow", 26)
            signal = args[3] if len(args) > 3 else kwargs.get("signal", 9)
            return self._rec.macd(self.asset, tf, fast, slow, signal)

    def bollinger_bands(self, *args, **kwargs) -> dict | None:
        asset_kw = kwargs.pop("asset", None)
        if "timeframe" in kwargs:
            tf = kwargs.pop("timeframe")
            asset = asset_kw or self.asset
            period = kwargs.pop("period", 20)
            std = kwargs.pop("std", 2.0)
            return self._rec.bollinger_bands(asset, tf, period, std)
        if len(args) >= 1 and isinstance(args[0], str) and args[0].upper() in ("BTC", "ETH", "SOL", "XRP", "DOGE", "HYPE", "BNB"):
            asset = args[0]
            tf = args[1] if len(args) > 1 else "1d"
            period = args[2] if len(args) > 2 else kwargs.get("period", 20)
            std = args[3] if len(args) > 3 else kwargs.get("std", 2.0)
            return self._rec.bollinger_bands(asset, tf, period, std)
        else:
            tf = args[0] if args else "1d"
            period = args[1] if len(args) > 1 else kwargs.get("period", 20)
            std = args[2] if len(args) > 2 else kwargs.get("std", 2.0)
            return self._rec.bollinger_bands(self.asset, tf, period, std)

    def age_s(self, timeframe: str, asset: str | None = None) -> float:
        return self._rec.age_s(timeframe, asset or self.asset)

    def is_fresh(self, timeframe: str, max_age_s: float, asset: str | None = None) -> bool:
        return self._rec.is_fresh(timeframe, max_age_s, asset or self.asset)

    # Compat: allow recorder-style signature ema(asset, timeframe, period)
    # by detecting 3 args: if user does view.ema("BTC","1m",10) they actually call
    # view.ema("BTC", "1m", 10) — our method would see timeframe="BTC", period="1m" type error.
    # So we provide __getattr__ fallback that tries recorder directly?
    # Instead add explicit helpers that match plan's 3-arg form:
    def _compat_ema(self, *args, **kwargs):
        if len(args) == 3:
            asset, tf, period = args
            return self._rec.ema(asset, tf, period)
        if len(args) == 2:
            tf, period = args
            asset = kwargs.get("asset", self.asset)
            return self._rec.ema(asset, tf, period)
        return self._rec.ema(*args, **kwargs)

    # Provide plan-compatible 3-arg ema via dynamic wrapper: override ema to support both
    # We do this by checking types at call time in ema()/sma() etc above? Simpler to
    # just expose recorder-style methods as well:
    def ema3(self, asset: str, timeframe: str, period: int) -> float | None:
        return self._rec.ema(asset, timeframe, period)

    # For ergonomic use: allow ctx.chainlink_history.ema("BTC","1m",10) by
    # implementing __call__? Instead we will make ema handle both signatures.

    def __repr__(self) -> str:
        return f"<ChainlinkHistoryView asset={self.asset} strat={self.strat_name!r} db={self._rec.db_path}>"
