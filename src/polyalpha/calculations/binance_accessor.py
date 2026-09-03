"""
Binance accessor - Binance-specific data accessor with price + volume calculations.

Provides Binance BTC (and other asset) market data with full OHLCV + volume
analytics. Supports both time-window (TimeWindow) and DataFeed (DataFrame)
backends. When used inside Bot/BotHub it is backed by a DataFeed DataFrame
and auto-refreshes once per candle; when used standalone it can be backed by
a TimeWindow via ``update(price, volume)``.

Usage
-----
    from polyalpha.calculations import BinanceAccessor
    from polyalpha.windows import TimeWindow

    # TimeWindow mode (seconds-based, like ChainlinkAccessor)
    window = TimeWindow(max_age=120)
    acc = BinanceAccessor(window=window, asset="BTC", timeframe="5m")
    acc.update(67850.0, volume=12.5)
    acc.change_pct(30)          # % change over 30 seconds (via BaseAccessor)
    acc.vol_ratio(10)           # volume ratio over 10 periods

    # DataFeed mode (candle-based, used by Bot/BotHub)
    acc = BinanceAccessor(asset="BTC", timeframe="5m")
    acc.close                   # latest close (triggers refresh)
    acc.quote_volume            # USDT quote volume
    acc.trades                  # trade count
    acc.taker_ratio()           # taker buy / volume
    acc.avg_volume(10)          # avg volume over 10 candles
    acc.volume_momentum(5)      # % change in volume
    acc.relative_volume(0.75,20)# above 75th percentile?
    acc.high(10)                # highest close over 10 candles
    acc.range(10)               # high - low over 10 candles
    acc.rate_of_change(60)      # per-second derivative
"""

from __future__ import annotations

import time
import logging
from typing import Optional, List

try:
    import pandas as pd
except ImportError:  # pragma: no cover
    pd = None  # type: ignore

from .base_accessor import BaseAccessor
from .market_calculations import MarketCalculations, TrendDirection
from .volume_calculations import VolumeCalculations, VolumeTrend

try:
    from ..windows import TimeWindow
except ImportError:
    TimeWindow = None  # type: ignore

log = logging.getLogger(__name__)


class BinanceAccessor(BaseAccessor):
    """
    Binance market data accessor with price + volume calculations.

    Fetches Binance klines via DataFeed (REST) once per candle when used in
    bot context, and delegates math to MarketCalculations / VolumeCalculations.
    Also supports direct TimeWindow updates for seconds-based analysis.

    Parameters
    ----------
    window : TimeWindow | None
        Existing TimeWindow, or None to create one (max_age=120) and/or
        use DataFeed DataFrame backend.
    max_age : float
        Maximum age for auto-created TimeWindow.
    asset : str
        Asset symbol (e.g. "BTC").
    timeframe : str
        Timeframe for DataFeed fetching (e.g. "5m", "1h", "1d"/"24h").
    """

    def __init__(
        self,
        window: Optional["TimeWindow"] = None,
        max_age: float = 120.0,
        asset: str = "BTC",
        timeframe: str = "5m",
    ):
        super().__init__(window=window, max_age=max_age)
        self._asset = asset.upper()
        self._timeframe = timeframe
        self._data = None  # Optional[pd.DataFrame] — set by _refresh
        self._last_candle_key: Optional[str] = None
        self._feed = None  # Optional[DataFeed]
        self._has_calculations = True
        # Reuse BaseAccessor's calcs but keep explicit refs for candle mode
        self._market_calc = MarketCalculations()
        self._volume_calc = VolumeCalculations()

    # ── Data backend helpers ─────────────────────────────────────────────

    def _lazy_init(self) -> None:
        if self._feed is not None:
            return
        try:
            from ..analysis import DataFeed, DataFeedConfig
            config = DataFeedConfig(source="binance", timeframe=self._timeframe, lookback_periods=100)
            self._feed = DataFeed(config)
        except Exception as exc:  # pragma: no cover
            log.warning("BinanceAccessor: DataFeed init failed for %s: %s", self._asset, exc)
            self._feed = None

    def _refresh(self) -> None:
        """Refresh Binance DataFrame once per candle (no-op if window-only)."""
        if self._feed is None:
            try:
                self._lazy_init()
            except Exception:
                return
            if self._feed is None:
                return
        try:
            from ..core.constants import TIMEFRAME_SECONDS
        except ImportError:
            TIMEFRAME_SECONDS = {"1m": 60, "5m": 300, "15m": 900, "1h": 3600, "4h": 14400, "1d": 86400, "24h": 86400}
        tf_secs = TIMEFRAME_SECONDS.get(self._timeframe, TIMEFRAME_SECONDS.get(self._timeframe.lower(), 300))
        # Handle "24h" alias
        if self._timeframe.lower() == "24h":
            tf_secs = 86400
        now = time.time()
        candle_key = str(int(now // tf_secs))
        if self._last_candle_key == candle_key and self._data is not None:
            return
        try:
            self._data = self._feed.fetch(self._asset)
            self._last_candle_key = candle_key
        except Exception as exc:
            log.warning("BinanceAccessor: refresh failed for %s: %s", self._asset, exc)

    def _has_dataframe(self) -> bool:
        return self._data is not None and pd is not None and not self._data.empty

    def _get_price_data(self) -> List[float]:
        """Price data for BaseAccessor — prefers DataFrame close, falls back to window."""
        if self._has_dataframe():
            try:
                return self._data["close"].tolist()  # type: ignore
            except Exception:
                pass
        if self._window is not None:
            return [p.value for p in self._window._data]
        return []

    def _get_volume_data(self) -> List[float]:
        """Volume data — DataFrame volume or window volume if available."""
        if self._has_dataframe():
            try:
                # Prefer DataFrame volume column
                if "volume" in self._data.columns:  # type: ignore
                    return self._data["volume"].tolist()  # type: ignore
            except Exception:
                pass
        # Fallback: if window has volume tracking (not standard TimeWindow)
        # For now return window-less empty if no DataFrame
        return []

    def _get_quote_volume_data(self) -> List[float]:
        if self._has_dataframe() and "quote_volume" in self._data.columns:  # type: ignore
            try:
                return self._data["quote_volume"].tolist()  # type: ignore
            except Exception:
                pass
        return []

    # ── Override has_volume ──────────────────────────────────────────────

    @property
    def has_volume(self) -> bool:  # type: ignore[override]
        if self._has_dataframe():
            try:
                vol = self._data["volume"].tolist()  # type: ignore
                return len(vol) > 0
            except Exception:
                pass
        return len(self._get_volume_data()) > 0

    # ── TimeWindow update (supports optional volume) ─────────────────────

    def update(self, value: float, volume: Optional[float] = None) -> None:  # type: ignore[override]
        """Update backing TimeWindow with price (and optionally track volume)."""
        if self._window is not None:
            self._window.update(value)
        # Also keep a tiny in-memory volume list if DataFrame not in use
        # For DataFrame mode, volume comes from klines — this is for standalone testing
        if volume is not None and not self._has_dataframe():
            # lazily create a volume list on the instance
            if not hasattr(self, "_vol_list"):
                self._vol_list: List[float] = []
            self._vol_list.append(volume)
            # cap length
            if len(self._vol_list) > 1000:
                self._vol_list.pop(0)

    # ── OHLCV Properties ─────────────────────────────────────────────────

    @property
    def open(self) -> Optional[float]:
        """Latest Binance open price."""
        self._refresh()
        if self._has_dataframe():
            try:
                return float(self._data["open"].iloc[-1])  # type: ignore
            except Exception:
                return None
        # fallback to window last value
        return self.value

    @property
    def close(self) -> Optional[float]:
        """Latest Binance close price."""
        self._refresh()
        if self._has_dataframe():
            try:
                return float(self._data["close"].iloc[-1])  # type: ignore
            except Exception:
                return None
        return self.value

    @property
    def high(self) -> Optional[float]:  # type: ignore[override]
        """Latest Binance high price (property) — latest candle high."""
        self._refresh()
        if self._has_dataframe():
            try:
                return float(self._data["high"].iloc[-1])  # type: ignore
            except Exception:
                return None
        # fallback: high() method with period=1 via BaseAccessor logic
        return self.value

    @property
    def low(self) -> Optional[float]:  # type: ignore[override]
        """Latest Binance low price (property) — latest candle low."""
        self._refresh()
        if self._has_dataframe():
            try:
                return float(self._data["low"].iloc[-1])  # type: ignore
            except Exception:
                return None
        return self.value

    @property
    def volume(self) -> Optional[float]:
        """Latest Binance base asset volume."""
        self._refresh()
        if self._has_dataframe():
            try:
                return float(self._data["volume"].iloc[-1])  # type: ignore
            except Exception:
                return None
        vd = self._get_volume_data()
        return vd[-1] if vd else None

    @property
    def quote_volume(self) -> Optional[float]:
        """Latest Binance quote asset (USDT) volume."""
        self._refresh()
        if self._has_dataframe() and "quote_volume" in self._data.columns:  # type: ignore
            try:
                return float(self._data["quote_volume"].iloc[-1])  # type: ignore
            except Exception:
                return None
        qvd = self._get_quote_volume_data()
        return qvd[-1] if qvd else None

    @property
    def trades(self) -> Optional[int]:
        """Number of trades in latest candle."""
        self._refresh()
        if self._has_dataframe() and "trades" in self._data.columns:  # type: ignore
            try:
                return int(self._data["trades"].iloc[-1])  # type: ignore
            except Exception:
                return None
        return None

    @property
    def taker_buy_base(self) -> Optional[float]:
        """Taker buy base asset volume (latest candle)."""
        self._refresh()
        if self._has_dataframe() and "taker_buy_base" in self._data.columns:  # type: ignore
            try:
                return float(self._data["taker_buy_base"].iloc[-1])  # type: ignore
            except Exception:
                return None
        return None

    @property
    def taker_buy_quote(self) -> Optional[float]:
        """Taker buy quote asset volume (latest candle)."""
        self._refresh()
        if self._has_dataframe() and "taker_buy_quote" in self._data.columns:  # type: ignore
            try:
                return float(self._data["taker_buy_quote"].iloc[-1])  # type: ignore
            except Exception:
                return None
        return None

    # ── Legacy price helpers (candle-based) ──────────────────────────────

    def price_change(self, candles_back: int = 1) -> Optional[float]:
        """Absolute price change over N candles (current - previous)."""
        self._refresh()
        data = self._get_price_data()
        if len(data) <= candles_back:
            return None
        return self._market_calc.change_abs(data, candles_back)

    def price_change_percent(self, candles_back: int = 1) -> Optional[float]:
        """Percentage price change over N candles (as % e.g. 2.5 for 2.5%)."""
        self._refresh()
        data = self._get_price_data()
        if len(data) <= candles_back:
            return None
        pct = self._market_calc.change_pct(data, candles_back)
        return pct * 100.0 if pct is not None else None

    def price_up(self, candles_back: int = 1) -> Optional[bool]:
        """True if close is higher than N candles ago."""
        chg = self.price_change(candles_back)
        if chg is None:
            return None
        return chg > 0

    def price_above_by(self, min_change: float, candles_back: int = 1) -> Optional[bool]:
        """True if price increased by at least min_change USD."""
        chg = self.price_change(candles_back)
        if chg is None:
            return None
        return chg >= min_change

    # ── TA indicators on close series ────────────────────────────────────

    def _series(self):
        if self._has_dataframe():
            return self._data["close"]  # type: ignore
        # fallback: build Series from price data
        data = self._get_price_data()
        if pd is None or not data:
            return None
        return pd.Series(data)

    def macd(self, fast: int = 12, slow: int = 26, signal: int = 9):
        """MACD computed on Binance close prices."""
        _macd = None
        MACDResult = None
        try:
            from polyalpha.analysis._native_ta import macd as _macd  # type: ignore
        except ImportError:
            try:
                import pandas_ta as _pta  # type: ignore
                _macd = _pta.macd  # type: ignore
            except ImportError:
                return None
        try:
            from polyalpha.bot_hub import MACDResult as _MR  # type: ignore
            MACDResult = _MR
        except ImportError:
            pass
        self._refresh()
        series = self._series()
        if series is None or _macd is None:
            return None
        try:
            df = _macd(series, fast, slow, signal)
            # _native_ta returns DataFrame, pandas_ta returns DataFrame
            macd_v = float(df.iloc[-1, 0])
            sig_v = float(df.iloc[-1, 1])
            hist_v = float(df.iloc[-1, 2])
            if pd is not None and (pd.isna(macd_v) or pd.isna(sig_v) or pd.isna(hist_v)):
                return None
            if MACDResult is not None:
                return MACDResult(macd=macd_v, signal=sig_v, histogram=hist_v)
            return (macd_v, sig_v, hist_v)
        except Exception:
            return None

    def rsi(self, period: int = 14) -> Optional[float]:
        """RSI computed on Binance close prices."""
        _rsi = None
        try:
            from polyalpha.analysis._native_ta import rsi as _rsi  # type: ignore
        except ImportError:
            try:
                import pandas_ta as _pta  # type: ignore
                _rsi = _pta.rsi  # type: ignore
            except ImportError:
                return None
        self._refresh()
        series = self._series()
        if series is None or _rsi is None:
            return None
        try:
            val = _rsi(series, period).iloc[-1]
            return None if (pd is not None and pd.isna(val)) else float(val)
        except Exception:
            return None

    def sma(self, period: int = 20) -> Optional[float]:
        _sma = None
        try:
            from polyalpha.analysis._native_ta import sma as _sma  # type: ignore
        except ImportError:
            try:
                import pandas_ta as _pta  # type: ignore
                _sma = _pta.sma  # type: ignore
            except ImportError:
                return None
        self._refresh()
        series = self._series()
        if series is None or _sma is None:
            return None
        try:
            val = _sma(series, period).iloc[-1]
            return None if (pd is not None and pd.isna(val)) else float(val)
        except Exception:
            return None

    def ema(self, period: int = 12) -> Optional[float]:
        _ema = None
        try:
            from polyalpha.analysis._native_ta import ema as _ema  # type: ignore
        except ImportError:
            try:
                import pandas_ta as _pta  # type: ignore
                _ema = _pta.ema  # type: ignore
            except ImportError:
                return None
        self._refresh()
        series = self._series()
        if series is None or _ema is None:
            return None
        try:
            val = _ema(series, period).iloc[-1]
            return None if (pd is not None and pd.isna(val)) else float(val)
        except Exception:
            return None

    # ── Enhanced Calculation Methods (candle-based, backwards compat) ────

    def change_pct(self, candles_back: int = 1) -> Optional[float]:  # type: ignore[override]
        """
        Percentage price change over N candles using calculation library.
        Returns decimal (e.g. 0.12 for 12%). For backwards compat with
        BaseAccessor.change_pct(seconds), if called with float seconds and
        window is populated, it delegates to window logic.
        """
        # If caller passed a time-window style float and we have window data,
        # delegate to BaseAccessor seconds logic for backwards compat.
        # Heuristic: if we have a window with timestamps and candles_back is
        # not an int, treat as seconds.
        if isinstance(candles_back, float) and self._window is not None and len(self._window._data) >= 2:
            return super().change_pct(candles_back)  # type: ignore
        self._refresh()
        data = self._get_price_data()
        if len(data) <= candles_back:
            return None
        return self._market_calc.change_pct(data, candles_back)

    def change_abs(self, candles_back: int = 1) -> Optional[float]:  # type: ignore[override]
        self._refresh()
        data = self._get_price_data()
        if len(data) <= candles_back:
            return None
        return self._market_calc.change_abs(data, candles_back)

    def vol_ratio(self, period: int = 10) -> Optional[float]:  # type: ignore[override]
        self._refresh()
        data = self._get_volume_data()
        if len(data) < 2:
            # try quote volume fallback?
            return self._volume_calc.vol_ratio(data, period) if data else None
        return self._volume_calc.vol_ratio(data, period)

    def volume_trend(self, period: int = 5, threshold: float = 0.1) -> Optional[str]:  # type: ignore[override]
        self._refresh()
        data = self._get_volume_data()
        if not data:
            return VolumeTrend.STABLE.value  # type: ignore
        trend = self._volume_calc.volume_trend(data, period, threshold)
        return trend.value if trend else "stable"

    def volume_surge(self, multiplier: float = 2.0, period: int = 10) -> Optional[bool]:  # type: ignore[override]
        self._refresh()
        data = self._get_volume_data()
        if not data:
            return None
        return self._volume_calc.volume_surge(data, multiplier, period)

    def trend(self, candles_back: int = 1, threshold: float = 0.0) -> Optional[str]:  # type: ignore[override]
        self._refresh()
        data = self._get_price_data()
        if len(data) <= candles_back:
            return TrendDirection.NEUTRAL.value
        trend = self._market_calc.trend(data, candles_back, threshold)
        return trend.value if trend else "neutral"

    def direction(self, candles_back: int = 1) -> Optional[str]:  # type: ignore[override]
        self._refresh()
        data = self._get_price_data()
        if len(data) <= candles_back:
            return None
        # fallback to price_up if needed
        res = self._market_calc.direction(data, candles_back)
        if res is None:
            is_up = self.price_up(candles_back)
            if is_up is None:
                return None
            return "up" if is_up else "down"
        return res

    def volatility(self, period: int = 10) -> Optional[float]:  # type: ignore[override]
        self._refresh()
        data = self._get_price_data()
        if len(data) < 2:
            return None
        return self._market_calc.volatility(data, period)

    # ── New: previously missing proxies ──────────────────────────────────

    def avg_volume(self, period: int = 10) -> Optional[float]:
        """Average volume over period (excluding current candle)."""
        self._refresh()
        data = self._get_volume_data()
        if len(data) < 2:
            return None
        return self._volume_calc.avg_volume(data, period)

    def volume_momentum(self, period: int = 5) -> Optional[float]:
        """Volume momentum — % change in volume over period."""
        self._refresh()
        data = self._get_volume_data()
        if len(data) < 2:
            return None
        return self._volume_calc.volume_momentum(data, period)

    def relative_volume(self, percentile: float = 0.75, period: int = 20) -> Optional[bool]:
        """True if current volume above percentile of last N volumes."""
        self._refresh()
        data = self._get_volume_data()
        if len(data) < 2:
            return None
        return self._volume_calc.relative_volume(data, percentile, period)

    def avg_quote_volume(self, period: int = 10) -> Optional[float]:
        """Average quote (USDT) volume over period."""
        self._refresh()
        data = self._get_quote_volume_data()
        if len(data) < 2:
            return None
        # reuse avg_volume logic on quote data
        if len(data) < period + 1:
            window = data[:-1]
        else:
            window = data[-period-1:-1]
        if not window:
            return None
        return sum(window) / len(window)

    def quote_volume_ratio(self, period: int = 10) -> Optional[float]:
        """Current quote_volume / avg quote_volume."""
        self._refresh()
        data = self._get_quote_volume_data()
        if len(data) < 2:
            return None
        return self._volume_calc.vol_ratio(data, period)

    def taker_ratio(self) -> Optional[float]:
        """Taker buy base / volume ratio for latest candle (0..1)."""
        vol = self.volume
        taker = self.taker_buy_base
        if vol is None or taker is None or vol == 0:
            return None
        return taker / vol

    def high_price(self, period: int = 10) -> Optional[float]:
        """Highest close price over N candles (use high_price to avoid property clash)."""
        self._refresh()
        data = self._get_price_data()
        if not data:
            return None
        return self._market_calc.high(data, period)

    def low_price(self, period: int = 10) -> Optional[float]:
        """Lowest close price over N candles."""
        self._refresh()
        data = self._get_price_data()
        if not data:
            return None
        return self._market_calc.low(data, period)

    def range(self, period: int = 10) -> Optional[float]:  # type: ignore[override]
        """Price range (high - low) over N candles."""
        self._refresh()
        data = self._get_price_data()
        if not data:
            return None
        return self._market_calc.range(data, period)

    def rate_of_change(self, period: int = 1, time_interval: Optional[float] = None) -> Optional[float]:  # type: ignore[override]
        """
        Rate of change per second over N candles.

        If time_interval is None, uses timeframe seconds (e.g. 300 for 5m).
        """
        self._refresh()
        data = self._get_price_data()
        if len(data) <= period:
            return None
        if time_interval is None:
            try:
                from ..core.constants import TIMEFRAME_SECONDS
                time_interval = TIMEFRAME_SECONDS.get(self._timeframe, 300)
                if self._timeframe.lower() == "24h":
                    time_interval = 86400
            except ImportError:
                time_interval = 300
        return self._market_calc.rate_of_change(data, period, time_interval)

    # Compatibility aliases for high/low as methods (period-based)
    # Note: high/low properties return latest candle's high/low; these methods return period high/low
    def high_period(self, period: int = 10) -> Optional[float]:
        return self.high_price(period)

    def low_period(self, period: int = 10) -> Optional[float]:
        return self.low_price(period)

    def __repr__(self) -> str:
        return f"BinanceAccessor(asset={self._asset}, timeframe={self._timeframe}, close={self.close}, volume={self.volume})"
