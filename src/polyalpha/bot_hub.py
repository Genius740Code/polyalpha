"""
BotHub — run multiple strategies from a single data connection.

Each strategy gets its own isolated PaperEngine (independent balance,
positions, and P&L), but they all share ONE market discovery call and
ONE WebSocket stream. This eliminates redundant rate-limited connections
when running many strategies on the same asset / timeframe.

Usage
-----
    hub = polyalpha.BotHub("BTC", "5m", default_balance=500)

    @hub.strategy("momentum")
    def momentum(ctx):
        if ctx.price.up > 0.9 and ctx.rsi > 50:
            ctx.buy("UP", 20)

    @hub.strategy("value", balance=1000)
    def value(ctx):
        if ctx.price.down < 0.10:
            ctx.buy("DOWN", 10)

    hub.run()   # blocking; one stream, N strategies

The BotHub handles the full lifecycle once and fans every price tick
out to all registered strategies:

    discover (once) → stream (once) → tick×N → resolve → rollover → repeat

Each strategy error is isolated — a crash in one strategy is logged and
does not stop the others or the hub.

Comparison (variants)
---------------------
Any strategy can carry free-form ``params`` metadata. Strategies with
non-empty ``params`` are called "variants" and can be compared
side-by-side via ``compare_variants()``::

    hub = polyalpha.BotHub("BTC", "5m")

    @hub.strategy("rsi_70", params={"rsi_threshold": 70})
    def rsi_70(ctx):
        if ctx.rsi and ctx.rsi > 70:
            ctx.buy("DOWN", 10)

    @hub.strategy("rsi_30", params={"rsi_threshold": 30})
    def rsi_30(ctx):
        if ctx.rsi and ctx.rsi < 30:
            ctx.buy("UP", 10)

    hub.run()
    report = hub.compare_variants()   # ComparisonReport sorted by P&L
    report.print()

You can also use the ``variant()`` alias — it is identical to
``strategy()`` and exists purely for readability::

    @hub.variant("rsi_70", params={"rsi_threshold": 70})  # same as strategy()
"""

from __future__ import annotations

import asyncio
import logging
import threading
import time
from collections import defaultdict, deque, namedtuple
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import TYPE_CHECKING, Callable, Optional, Union

if TYPE_CHECKING:
    from .report.comparison import ComparisonReport

try:
    import pandas as pd
except ImportError:
    pd = None  # type: ignore[assignment]

try:
    from .analysis._native_ta import bbands as _bbands
    from .analysis._native_ta import donchian as _donchian
    from .analysis._native_ta import ema as _ema
    from .analysis._native_ta import macd as _macd
    from .analysis._native_ta import rsi as _rsi
    from .analysis._native_ta import sma as _sma
    from .analysis._native_ta import roc as _roc
    from .analysis._native_ta import vwap as _vwap
    _NATIVE_TA_AVAILABLE = True
except ImportError:
    _rsi = _sma = _ema = _macd = _bbands = _roc = _vwap = _donchian = None
    _NATIVE_TA_AVAILABLE = False

try:
    from .notifications.telegram import TelegramNotifier
except ImportError:
    TelegramNotifier = None  # type: ignore[assignment]

try:
    from .windows import TimeWindow
except ImportError:
    TimeWindow = None  # type: ignore[assignment]

# ── Chainlink history helper (user chooses {"1m":10, "1h":50, "1s":20}) ───

def _resolve_chainlink_history(value, asset: str):
    if value is None or value is False:
        return None, False
    try:
        from .history import ChainlinkHistoryConfig, ChainlinkRecorder
    except ImportError:
        return None, False
    if isinstance(value, ChainlinkRecorder):
        return value, False
    # Import here to avoid circular
    from .history import ChainlinkHistoryConfig as CHC, ChainlinkRecorder as CR  # type: ignore
    if isinstance(value, CHC):
        rec = CR(config=value)
        return rec, True
    if isinstance(value, dict):
        cfg = CHC(warmup=dict(value))
        rec = CR(config=cfg)
        return rec, True
    if value is True:
        cfg = CHC(warmup={"1m": 20})
        rec = CR(config=cfg)
        return rec, True
    if isinstance(value, str):
        cfg = CHC(warmup={"1m": 20}, db_path=value)
        rec = CR(config=cfg)
        return rec, True
    return None, False

MACDResult = namedtuple("MACDResult", ["macd", "signal", "histogram"])
BBResult = namedtuple("BBResult", ["upper", "mid", "lower"])
DonchianResult = namedtuple("DonchianResult", ["upper", "mid", "lower"])

from .client import Client
from .core import (
    ASSETS,
    FALLBACK_PRICE,
    TIMEFRAME_SECONDS,
    Market,
)
from .core.errors import MarketNotFound
from .orderbook import ClobBookClient, OrderBookFeed
from .trading.paper_config import PaperConfig
from .trading.paper_engine import PaperEngine

log = logging.getLogger(__name__)


def _log_indicators() -> None:
    """Log which TA indicators are available (called once at BotHub init)."""
    if not _NATIVE_TA_AVAILABLE:
        log.info("TA indicators: none available (install pandas-ta or numpy)")
        return
    names = []
    if _rsi is not None: names.append("rsi")
    if _sma is not None: names.append("sma")
    if _ema is not None: names.append("ema")
    if _macd is not None: names.append("macd")
    if _bbands is not None: names.append("bollinger_bands")
    if _donchian is not None: names.append("donchian")
    if _roc is not None: names.append("roc")
    if _vwap is not None: names.append("vwap")
    log.info("TA indicators available: %s", ", ".join(names))


# ── Price Snapshot ─────────────────────────────────────────────────────────────

@dataclass
class PriceSnapshot:
    """Current UP/DOWN prices from the shared stream."""
    up: float
    down: float


# ── Indicator Accessor ─────────────────────────────────────────────────────────

class IndicatorAccessor:
    """First-class indicator access via ``ctx.indicators.rsi(14)``, etc.

    Wraps the shared price history deque and caches computed results within
    a single tick. Call ``invalidate()`` to clear the per-tick cache when
    new price data arrives.

    Call ``available()`` to list which indicators are ready to use.
    """

    def __init__(self, get_series_fn):
        self._get_series = get_series_fn
        self._cache: dict[tuple, object] = {}

    def invalidate(self) -> None:
        self._cache.clear()

    def _resolve(self, val):
        if val is None:
            return None
        try:
            return None if pd.isna(val) else float(val)
        except Exception:
            return None

    def _get(self, key, compute_fn):
        if key in self._cache:
            return self._cache[key]
        series = self._get_series()
        if series is None:
            return None
        result = compute_fn(series)
        self._cache[key] = result
        return result

    def available(self) -> list[str]:
        """List of indicator names available on this accessor.

        Returns the subset of supported indicators whose underlying TA
        implementation is loaded (native numpy/pandas or pandas-ta).

        Example
        -------
        >>> ctx.indicators.available()
        ['rsi', 'sma', 'ema', 'macd', 'bollinger_bands', 'roc', 'vwap']
        """
        names = []
        if _rsi is not None:
            names.append("rsi")
        if _sma is not None:
            names.append("sma")
        if _ema is not None:
            names.append("ema")
        if _macd is not None:
            names.append("macd")
        if _bbands is not None:
            names.append("bollinger_bands")
        if _donchian is not None:
            names.append("donchian")
        if _roc is not None:
            names.append("roc")
        if _vwap is not None:
            names.append("vwap")
        return names

    def rsi(self, period: int = 14) -> Optional[float]:
        """Relative Strength Index."""
        if _rsi is None:
            return None
        return self._get(("rsi", period), lambda s: self._resolve(_rsi(s, period).iloc[-1]))

    def sma(self, period: int = 20) -> Optional[float]:
        """Simple Moving Average."""
        if _sma is None:
            return None
        return self._get(("sma", period), lambda s: self._resolve(_sma(s, period).iloc[-1]))

    def ema(self, period: int = 12) -> Optional[float]:
        """Exponential Moving Average."""
        if _ema is None:
            return None
        return self._get(("ema", period), lambda s: self._resolve(_ema(s, period).iloc[-1]))

    def macd(self, fast: int = 12, slow: int = 26, signal: int = 9) -> Optional[MACDResult]:
        """MACD indicator returning ``MACDResult(macd, signal, histogram)``."""
        if _macd is None:
            return None
        def _compute(s):
            df = _macd(s, fast, slow, signal)
            macd_v = float(df.iloc[-1, 0])
            sig_v = float(df.iloc[-1, 1])
            hist_v = float(df.iloc[-1, 2])
            if pd.isna(macd_v) or pd.isna(sig_v) or pd.isna(hist_v):
                return None
            return MACDResult(macd=macd_v, signal=sig_v, histogram=hist_v)
        return self._get(("macd", fast, slow, signal), _compute)

    def bollinger_bands(self, period: int = 20, std: Union[float, int] = 2.0) -> Optional[BBResult]:
        """Bollinger Bands returning ``BBResult(upper, mid, lower)``."""
        if _bbands is None:
            return None
        def _compute(s):
            df = _bbands(s, period, float(std))
            upper_v = float(df.iloc[-1, 2])
            mid_v = float(df.iloc[-1, 1])
            lower_v = float(df.iloc[-1, 0])
            if pd.isna(upper_v) or pd.isna(mid_v) or pd.isna(lower_v):
                return None
            return BBResult(upper=upper_v, mid=mid_v, lower=lower_v)
        return self._get(("bb", period, std), _compute)

    def roc(self, period: int = 12) -> Optional[float]:
        """Rate of Change (percent)."""
        if _roc is None:
            return None
        return self._get(("roc", period), lambda s: self._resolve(_roc(s, period).iloc[-1]))

    def vwap(self) -> Optional[float]:
        """Volume Weighted Average Price."""
        if _vwap is None:
            return None
        return self._get(("vwap",), lambda s: self._resolve(_vwap(s).iloc[-1]))

    def donchian(self, length: int = 20) -> Optional[DonchianResult]:
        """Donchian Channels returning ``DonchianResult(upper, mid, lower)``."""
        if _donchian is None:
            return None
        def _compute(s):
            df = _donchian(s, s, length)
            upper_v = float(df.iloc[-1, 2])
            mid_v = float(df.iloc[-1, 1])
            lower_v = float(df.iloc[-1, 0])
            if pd.isna(upper_v) or pd.isna(mid_v) or pd.isna(lower_v):
                return None
            return DonchianResult(upper=upper_v, mid=mid_v, lower=lower_v)
        return self._get(("donchian", length), _compute)


# ── Binance Accessor ────────────────────────────────────────────────────────────

class BinanceAccessor:
    """
    Binance BTC market data for use inside bot strategies.

    Fetches Binance klines once per candle (auto-refreshed on each tick).
    Provides indicators computed on Binance spot price data (not Polymarket).
    Now integrated with calculation library for enhanced price and volume analysis.

    Usage
    -----
        >>> ctx.binance.close               # latest Binance close price
        >>> ctx.binance.macd(12, 26, 9)     # MACD on Binance BTC data
        >>> ctx.binance.price_change(3)     # BTC spot change over N candles
        >>> ctx.binance.price_up(2)         # BTC spot went up over N candles
        >>> ctx.binance.change_pct(30)      # % change over 30 seconds (new)
        >>> ctx.binance.vol_ratio(10)       # volume ratio (new)
    """

    def __init__(self, asset: str = "BTC", timeframe: str = "5m"):
        self._asset = asset.upper()
        self._timeframe = timeframe
        self._data: Optional[pd.DataFrame] = None
        self._last_candle_key: Optional[str] = None
        self._feed: Optional[object] = None
        
        # Try to load calculation library for enhanced methods
        try:
            from .calculations import MarketCalculations, VolumeCalculations
            self._market_calc = MarketCalculations()
            self._volume_calc = VolumeCalculations()
            self._has_calculations = True
        except ImportError:
            self._market_calc = None
            self._volume_calc = None
            self._has_calculations = False

    def _lazy_init(self) -> None:
        if self._feed is not None:
            return
        from .analysis import DataFeed, DataFeedConfig
        config = DataFeedConfig(source="binance", timeframe=self._timeframe, lookback_periods=100)
        self._feed = DataFeed(config)

    def _refresh(self) -> None:
        """Refresh Binance data once per candle."""
        if self._feed is None:
            self._lazy_init()
        now = time.time()
        from polyalpha.core.constants import TIMEFRAME_SECONDS
        tf_secs = TIMEFRAME_SECONDS.get(self._timeframe, 300)
        candle_key = str(int(now // tf_secs))
        if self._last_candle_key == candle_key and self._data is not None:
            return
        try:
            self._data = self._feed.fetch(self._asset)
            self._last_candle_key = candle_key
        except Exception as exc:
            log.warning("BinanceAccessor: refresh failed for %s: %s", self._asset, exc)

    @property
    def close(self) -> Optional[float]:
        """Latest Binance close price."""
        self._refresh()
        if self._data is None or self._data.empty:
            return None
        return float(self._data["close"].iloc[-1])

    @property
    def high(self) -> Optional[float]:
        self._refresh()
        if self._data is None or self._data.empty:
            return None
        return float(self._data["high"].iloc[-1])

    @property
    def low(self) -> Optional[float]:
        self._refresh()
        if self._data is None or self._data.empty:
            return None
        return float(self._data["low"].iloc[-1])

    @property
    def volume(self) -> Optional[float]:
        self._refresh()
        if self._data is None or self._data.empty:
            return None
        return float(self._data["volume"].iloc[-1])

    def price_change(self, candles_back: int = 1) -> Optional[float]:
        """Absolute BTC price change over N candles (current - previous)."""
        self._refresh()
        if self._data is None or len(self._data) <= candles_back:
            return None
        curr = float(self._data["close"].iloc[-1])
        prev = float(self._data["close"].iloc[-candles_back - 1])
        return curr - prev

    def price_change_percent(self, candles_back: int = 1) -> Optional[float]:
        """Percentage BTC price change over N candles."""
        self._refresh()
        if self._data is None or len(self._data) <= candles_back:
            return None
        curr = float(self._data["close"].iloc[-1])
        prev = float(self._data["close"].iloc[-candles_back - 1])
        if prev == 0:
            return None
        return ((curr - prev) / prev) * 100.0

    def price_up(self, candles_back: int = 1) -> Optional[bool]:
        """True if BTC close price is higher than N candles ago."""
        chg = self.price_change(candles_back)
        if chg is None:
            return None
        return chg > 0

    def price_above_by(self, min_change: float, candles_back: int = 1) -> Optional[bool]:
        """True if BTC price increased by at least min_change USD."""
        chg = self.price_change(candles_back)
        if chg is None:
            return None
        return chg >= min_change

    def macd(self, fast: int = 12, slow: int = 26, signal: int = 9) -> Optional[MACDResult]:
        """MACD computed on Binance BTC close prices."""
        self._refresh()
        if self._data is None or _macd is None:
            return None
        try:
            series = self._data["close"]
            df = _macd(series, fast, slow, signal)
            macd_v = float(df.iloc[-1, 0])
            sig_v = float(df.iloc[-1, 1])
            hist_v = float(df.iloc[-1, 2])
            if pd is not None and (pd.isna(macd_v) or pd.isna(sig_v) or pd.isna(hist_v)):
                return None
            return MACDResult(macd=macd_v, signal=sig_v, histogram=hist_v)
        except Exception:
            return None

    def rsi(self, period: int = 14) -> Optional[float]:
        """RSI computed on Binance BTC close prices."""
        self._refresh()
        if self._data is None or _rsi is None:
            return None
        try:
            series = self._data["close"]
            val = _rsi(series, period).iloc[-1]
            return None if (pd is not None and pd.isna(val)) else float(val)
        except Exception:
            return None

    def sma(self, period: int = 20) -> Optional[float]:
        self._refresh()
        if self._data is None or _sma is None:
            return None
        try:
            series = self._data["close"]
            val = _sma(series, period).iloc[-1]
            return None if (pd is not None and pd.isna(val)) else float(val)
        except Exception:
            return None

    def ema(self, period: int = 12) -> Optional[float]:
        self._refresh()
        if self._data is None or _ema is None:
            return None
        try:
            series = self._data["close"]
            val = _ema(series, period).iloc[-1]
            return None if (pd is not None and pd.isna(val)) else float(val)
        except Exception:
            return None
    
    # ── Enhanced Calculation Methods (using calculation library) ───────────────
    
    def change_pct(self, candles_back: int = 1) -> Optional[float]:
        """
        Percentage price change over N candles using calculation library.
        
        Parameters
        ----------
        candles_back : int
            Number of candles back to compare (default: 1).
        
        Returns
        -------
        float | None
            Percentage change as decimal, or None if insufficient data.
        """
        if not self._has_calculations:
            # Fallback to existing method
            change = self.price_change_percent(candles_back)
            return change / 100.0 if change is not None else None
        
        self._refresh()
        if self._data is None or len(self._data) <= candles_back:
            return None
        
        close_data = self._data["close"].tolist()
        return self._market_calc.change_pct(close_data, candles_back)
    
    def change_abs(self, candles_back: int = 1) -> Optional[float]:
        """
        Absolute price change over N candles using calculation library.
        
        Parameters
        ----------
        candles_back : int
            Number of candles back to compare (default: 1).
        
        Returns
        -------
        float | None
            Absolute price change, or None if insufficient data.
        """
        if not self._has_calculations:
            # Fallback to existing method
            return self.price_change(candles_back)
        
        self._refresh()
        if self._data is None or len(self._data) <= candles_back:
            return None
        
        close_data = self._data["close"].tolist()
        return self._market_calc.change_abs(close_data, candles_back)
    
    def vol_ratio(self, period: int = 10) -> Optional[float]:
        """
        Current volume as ratio to average volume over N candles.
        
        Parameters
        ----------
        period : int
            Number of candles to calculate average (default: 10).
        
        Returns
        -------
        float | None
            Volume ratio, or None if insufficient data or calculations unavailable.
        """
        if not self._has_calculations:
            return None
        
        self._refresh()
        if self._data is None or len(self._data) <= period:
            return None
        
        volume_data = self._data["volume"].tolist()
        return self._volume_calc.vol_ratio(volume_data, period)
    
    def volume_trend(self, period: int = 5, threshold: float = 0.1) -> Optional[str]:
        """
        Determine volume trend direction over N candles.
        
        Parameters
        ----------
        period : int
            Number of candles to analyze (default: 5).
        threshold : float
            Minimum relative change to consider a trend (default: 0.1).
        
        Returns
        -------
        str | None
            "increasing", "decreasing", or "stable". None if insufficient data.
        """
        if not self._has_calculations:
            return None
        
        self._refresh()
        if self._data is None or len(self._data) <= period:
            return None
        
        volume_data = self._data["volume"].tolist()
        trend = self._volume_calc.volume_trend(volume_data, period, threshold)
        return trend.value if trend else "stable"
    
    def volume_surge(self, multiplier: float = 2.0, period: int = 10) -> Optional[bool]:
        """
        Detect sudden volume surge compared to recent average.
        
        Parameters
        ----------
        multiplier : float
            Multiple of average volume to consider a surge (default: 2.0).
        period : int
            Number of candles to calculate average (default: 10).
        
        Returns
        -------
        bool | None
            True if volume surge detected, None if insufficient data.
        """
        if not self._has_calculations:
            return None
        
        self._refresh()
        if self._data is None or len(self._data) <= period:
            return None
        
        volume_data = self._data["volume"].tolist()
        return self._volume_calc.volume_surge(volume_data, multiplier, period)
    
    def trend(self, candles_back: int = 1, threshold: float = 0.0) -> Optional[str]:
        """
        Determine overall price trend direction over N candles.
        
        Parameters
        ----------
        candles_back : int
            Number of candles back to analyze (default: 1).
        threshold : float
            Minimum absolute change to consider a trend (default: 0.0).
        
        Returns
        -------
        str | None
            "up", "down", or "neutral". None if insufficient data.
        """
        if not self._has_calculations:
            return None
        
        self._refresh()
        if self._data is None or len(self._data) <= candles_back:
            return None
        
        close_data = self._data["close"].tolist()
        trend = self._market_calc.trend(close_data, candles_back, threshold)
        return trend.value if trend else "neutral"
    
    def direction(self, candles_back: int = 1) -> Optional[str]:
        """
        Get simple direction of price change (up/down/flat).
        
        Parameters
        ----------
        candles_back : int
            Number of candles back to compare (default: 1).
        
        Returns
        -------
        str | None
            "up", "down", or "flat". None if insufficient data.
        """
        if not self._has_calculations:
            # Fallback to existing method
            is_up = self.price_up(candles_back)
            if is_up is None:
                return None
            return "up" if is_up else "down"
        
        self._refresh()
        if self._data is None or len(self._data) <= candles_back:
            return None
        
        close_data = self._data["close"].tolist()
        return self._market_calc.direction(close_data, candles_back)
    
    def volatility(self, period: int = 10) -> Optional[float]:
        """
        Calculate price volatility (standard deviation) over N candles.
        
        Parameters
        ----------
        period : int
            Number of candles to analyze (default: 10).
        
        Returns
        -------
        float | None
            Standard deviation of prices, or None if insufficient data.
        """
        if not self._has_calculations:
            return None
        
        self._refresh()
        if self._data is None or len(self._data) < 2:
            return None
        
        close_data = self._data["close"].tolist()
        return self._market_calc.volatility(close_data, period)

    # ── Missing OHLCV Fields ───────────────────────────────────────────────

    @property
    def open(self) -> Optional[float]:
        """Latest Binance open price."""
        self._refresh()
        if self._data is None or self._data.empty:
            return None
        if "open" in self._data.columns:
            return float(self._data["open"].iloc[-1])
        return None

    @property
    def quote_volume(self) -> Optional[float]:
        """Latest Binance quote asset (USDT) volume."""
        self._refresh()
        if self._data is None or self._data.empty:
            return None
        if "quote_volume" in self._data.columns:
            return float(self._data["quote_volume"].iloc[-1])
        return None

    @property
    def trades(self) -> Optional[int]:
        """Number of trades in latest Binance candle."""
        self._refresh()
        if self._data is None or self._data.empty:
            return None
        if "trades" in self._data.columns:
            return int(self._data["trades"].iloc[-1])
        return None

    @property
    def taker_buy_base(self) -> Optional[float]:
        """Taker buy base asset volume (latest candle)."""
        self._refresh()
        if self._data is None or self._data.empty:
            return None
        if "taker_buy_base" in self._data.columns:
            return float(self._data["taker_buy_base"].iloc[-1])
        return None

    @property
    def taker_buy_quote(self) -> Optional[float]:
        """Taker buy quote asset volume (latest candle)."""
        self._refresh()
        if self._data is None or self._data.empty:
            return None
        if "taker_buy_quote" in self._data.columns:
            return float(self._data["taker_buy_quote"].iloc[-1])
        return None

    def taker_ratio(self) -> Optional[float]:
        """Taker buy base / volume ratio for latest candle (0..1)."""
        vol = self.volume
        taker = self.taker_buy_base
        if vol is None or taker is None or vol == 0:
            return None
        return taker / vol

    # ── Missing Calculation Proxies ────────────────────────────────────────

    def avg_volume(self, period: int = 10) -> Optional[float]:
        """Average volume over period (excluding current candle)."""
        if not self._has_calculations:
            return None
        self._refresh()
        if self._data is None or len(self._data) < 2:
            return None
        volume_data = self._data["volume"].tolist()
        return self._volume_calc.avg_volume(volume_data, period)

    def volume_momentum(self, period: int = 5) -> Optional[float]:
        """Volume momentum — % change in volume over period."""
        if not self._has_calculations:
            return None
        self._refresh()
        if self._data is None or len(self._data) < 2:
            return None
        volume_data = self._data["volume"].tolist()
        return self._volume_calc.volume_momentum(volume_data, period)

    def relative_volume(self, percentile: float = 0.75, period: int = 20) -> Optional[bool]:
        """True if current volume above percentile of last N volumes."""
        if not self._has_calculations:
            return None
        self._refresh()
        if self._data is None or len(self._data) < 2:
            return None
        volume_data = self._data["volume"].tolist()
        return self._volume_calc.relative_volume(volume_data, percentile, period)

    def avg_quote_volume(self, period: int = 10) -> Optional[float]:
        """Average quote (USDT) volume over period (excluding current)."""
        if not self._has_calculations:
            return None
        self._refresh()
        if self._data is None or len(self._data) < 2 or "quote_volume" not in self._data.columns:
            return None
        qv = self._data["quote_volume"].tolist()
        if len(qv) < 2:
            return None
        # reuse avg_volume logic on quote data
        window = qv[-period-1:-1] if len(qv) >= period + 1 else qv[:-1]
        if not window:
            return None
        return sum(window) / len(window)

    def quote_volume_ratio(self, period: int = 10) -> Optional[float]:
        """Current quote_volume / avg quote_volume over period."""
        if not self._has_calculations:
            return None
        self._refresh()
        if self._data is None or len(self._data) < 2 or "quote_volume" not in self._data.columns:
            return None
        qv = self._data["quote_volume"].tolist()
        return self._volume_calc.vol_ratio(qv, period)

    def high_price(self, period: int = 10) -> Optional[float]:
        """Highest close price over N candles."""
        if not self._has_calculations:
            return None
        self._refresh()
        if self._data is None or len(self._data) < 1:
            return None
        close_data = self._data["close"].tolist()
        return self._market_calc.high(close_data, period)

    def low_price(self, period: int = 10) -> Optional[float]:
        """Lowest close price over N candles."""
        if not self._has_calculations:
            return None
        self._refresh()
        if self._data is None or len(self._data) < 1:
            return None
        close_data = self._data["close"].tolist()
        return self._market_calc.low(close_data, period)

    def range(self, period: int = 10) -> Optional[float]:  # type: ignore[override]
        """Price range (high - low) over N candles."""
        if not self._has_calculations:
            return None
        self._refresh()
        if self._data is None or len(self._data) < 1:
            return None
        close_data = self._data["close"].tolist()
        return self._market_calc.range(close_data, period)

    def rate_of_change(self, period: int = 1, time_interval: Optional[float] = None) -> Optional[float]:
        """Rate of change per second over N candles. Uses timeframe seconds if None."""
        if not self._has_calculations:
            return None
        self._refresh()
        if self._data is None or len(self._data) <= period:
            return None
        if time_interval is None:
            from polyalpha.core.constants import TIMEFRAME_SECONDS
            time_interval = TIMEFRAME_SECONDS.get(self._timeframe, 300)
            if self._timeframe.lower() == "24h":
                time_interval = 86400
        close_data = self._data["close"].tolist()
        return self._market_calc.rate_of_change(close_data, period, time_interval)


# ── Order Book Accessor ────────────────────────────────────────────────────────

class OrderBookAccessor:
    """
    Live order book for the strategy's current market.

    Lazily creates and auto-attaches an ``OrderBookFeed`` to the shared
    WebSocket stream on first property access.  Fetches an initial REST
    snapshot so data is available immediately even before the stream
    connects.

    Usage
    -----
        >>> ctx.orderbook.up.bids            # tuple[BookLevel] — UP bids
        >>> ctx.orderbook.down.asks          # tuple[BookLevel] — DOWN asks
        >>> ctx.orderbook.up.spread          # float — UP bid-ask spread
        >>> ctx.orderbook.up.mid_price       # float — UP mid price
        >>> ctx.orderbook.down.best_bid      # float — best DOWN bid
        >>> ctx.orderbook.refresh()          # force REST refresh

    Properties
    ----------
    up : OrderBookSnapshot | None
        UP token order book (bids, asks, spread, mid_price, …).
    down : OrderBookSnapshot | None
        DOWN token order book (bids, asks, spread, mid_price, …).
    book : MarketOrderBook
        Combined UP + DOWN market book.
    """

    def __init__(
        self,
        ctx: StrategyContext,
        market: Market,
        clob: ClobBookClient,
    ):
        self._ctx = ctx
        self._feed = OrderBookFeed(market=market, clob=clob)
        self._stream_attached = False

    def _ensure(self) -> None:
        if self._stream_attached:
            return
        self._feed.refresh()
        stream = self._ctx._stream
        if stream is not None:
            self._feed.attach_stream(stream)
        self._stream_attached = True

    @property
    def up(self) -> OrderBookSnapshot | None:
        """UP token order book snapshot."""
        self._ensure()
        return self._feed.up

    @property
    def down(self) -> OrderBookSnapshot | None:
        """DOWN token order book snapshot."""
        self._ensure()
        return self._feed.down

    @property
    def book(self) -> MarketOrderBook:
        """Combined UP + DOWN market order book."""
        self._ensure()
        return self._feed.book

    def refresh(self) -> MarketOrderBook:
        """Fetch fresh REST snapshots for UP and DOWN tokens."""
        self._ensure()
        return self._feed.refresh()


# ── Strategy Context ───────────────────────────────────────────────────────────

class StrategyContext:
    """
    Per-strategy trading context — same public API as ``Bot.TickContext``.

    Each strategy receives its own ``StrategyContext`` wrapping an isolated
    ``PaperEngine`` (independent balance / positions / P&L) but reading
    prices from the shared stream.

    Properties
    ----------
    price : PriceSnapshot
        Current UP/DOWN mid-prices.
    balance : float
        This strategy's paper balance.
    positions : list
        This strategy's open positions.
    pnl : float
        This strategy's realised P&L.
    market : Market | None
        The current shared market.
    name : str
        This strategy's registered name.
    indicators : IndicatorAccessor
        First-class indicator access: ``.indicators.rsi(14)``,
        ``.indicators.macd(12, 26, 9)``,
        ``.indicators.bollinger_bands(20, 2)``, etc.
    cl : TimeWindow | None
        Chainlink price window with change percentage helpers.
        ``ctx.cl.value`` for latest CL price, ``ctx.cl.change_pct(30)`` for
        % change over 30 seconds, ``ctx.cl.age_s`` for seconds since last update.
    rsi, sma_20, ema_12 : float | None
        Legacy indicators (prefer ``ctx.indicators.rsi(14)``, etc.).

    Methods
    -------
    buy(side, amount)
    limit(side, price, amount)
    close_position(side, amount=None)
    """

    def __init__(
        self,
        name: str,
        stream: object,
        paper: PaperEngine,
        market: Optional[Market],
        price_history: deque,
        down_price_history: Optional[deque] = None,
        asset: str = "BTC",
        clob: Optional[ClobBookClient] = None,
        chainlink_cache: Optional[object] = None,
        chainlink: Optional[object] = None,
        binance: Optional[BinanceAccessor] = None,
        cl_window: Optional[TimeWindow] = None,
        globals: Optional[object] = None,
        get_candle_open=None,
        get_seconds_in=None,
        get_candle_id=None,
        bought_this_candle=None,
        hub=None,
        chainlink_history=None,
        engine: object | None = None,
    ):
        self.name = name
        self._asset = asset
        self._stream = stream
        self._paper = paper
        # engine alias — for real trading paper is actually RealTradingEngine
        self._engine = engine if engine is not None else paper
        self._market = market
        self._price_history = price_history  # shared across strategies
        self._down_price_history: deque = down_price_history if down_price_history is not None else deque(maxlen=200)
        self._clob = clob
        self._chainlink_cache = chainlink_cache
        self._chainlink = chainlink
        self._binance = binance
        self._hub = hub  # Reference to BotHub for Telegram notifications
        self._globals = globals  # Shared feeds (Globals) — one connection, many strategies
        self._chainlink_history = chainlink_history
        self._chainlink_history_view = None
        self._get_candle_open = get_candle_open or (lambda: None)
        self._get_seconds_in = get_seconds_in or (lambda: 0.0)
        self._get_candle_id: Callable[[], int] = get_candle_id or (lambda: 0)
        self._bought_this_candle: dict[int, dict[str, set[str]]] = bought_this_candle if bought_this_candle is not None else {}
        self._cached_series = None
        self._down_cached_series = None
        self._indicators: IndicatorAccessor = IndicatorAccessor(self._get_price_series)
        self._down_indicators: IndicatorAccessor = IndicatorAccessor(self._get_down_price_series)
        self._orderbook: Optional[OrderBookAccessor] = None
        self._cl_window: Optional[TimeWindow] = cl_window if cl_window is not None else (TimeWindow(max_age=120) if TimeWindow is not None else None)

    # ── Prices ──────────────────────────────────────────────────────────────

    @property
    def price(self) -> PriceSnapshot:
        return PriceSnapshot(
            up=getattr(self._stream, "up", FALLBACK_PRICE),
            down=getattr(self._stream, "down", FALLBACK_PRICE),
        )

    @property
    def spot_price(self) -> Optional[float]:
        """Current Chainlink oracle price for the hub's asset, or *None*."""
        if self._chainlink_cache is not None:
            try:
                return self._chainlink_cache.get_price(self._asset)
            except Exception:
                pass
        return None

    @property
    def chainlink(self):
        """Live BTC spot price from Polymarket Chainlink WebSocket.

        ``ctx.chainlink.last_price`` for the latest BTC/USD price.
        Returns ``None`` if not available in this context.
        """
        return self._chainlink

    @property
    def binance(self):
        """Binance BTC market data for external TA.

        ``ctx.binance.close``, ``ctx.binance.macd()``, ``ctx.binance.price_change(30)``.
        Returns ``None`` if not available in this context.
        """
        return self._binance

    @property
    def globals(self):
        """The shared :class:`~polyalpha.globals.Globals` instance, if any.

        Every strategy reads the same feeds (``ctx.globals.cvd``,
        ``ctx.globals.price_feed``, …) so adding a strategy costs 0 extra
        connections. Returns ``None`` when the hub was not given one.
        """
        return self._globals

    @property
    def cl(self):
        """Chainlink price window with change percentage helpers.

        Provides a rolling window of Chainlink BTC prices with convenient
        methods for calculating percentage changes over custom time periods.
        Backed by the shared Chainlink streamer's own rolling window when
        available.

        Returns ``None`` if the window is not available.

        Examples
        --------
        >>> ctx.cl.value
        67850.23
        >>> ctx.cl.change_pct(30)
        0.12
        >>> ctx.cl.change_pct(60)
        0.08
        >>> ctx.cl.age_s
        0.5
        """
        if self._chainlink is not None:
            window = getattr(self._chainlink, "window", None)
            if window is not None:
                return window
        return self._cl_window

    @property
    def chainlink_history(self):
        """
        Chainlink candle history (shared, pruned to user keep counts).

        Example: ``ctx.chainlink_history.ema("1m",10)``
        or ``ctx.chainlink_history.candles("1m",10)``.
        Supports both ``ema("1m",10)`` and ``ema("BTC","1m",10)`` forms.
        Returns ``None`` if not configured on the hub.
        """
        rec = self._chainlink_history
        # fallback to hub's recorder or globals
        if rec is None and self._hub is not None:
            rec = getattr(self._hub, "_chainlink_history", None)
        if rec is None and self._globals is not None:
            rec = getattr(self._globals, "chainlink_history", None)
        if rec is None:
            return None
        if self._chainlink_history_view is not None:
            return self._chainlink_history_view
        try:
            from .history.view import ChainlinkHistoryView
            # ChainlinkHistoryView expects recorder; if rec is already a view, return it
            if isinstance(rec, ChainlinkHistoryView):
                self._chainlink_history_view = rec
                return rec
            view = ChainlinkHistoryView(rec, asset=self._asset, strat_name=self.name)
            self._chainlink_history_view = view
            return view
        except Exception:
            return rec

    @property
    def candle_open(self) -> Optional[float]:
        """Opening price of the current candle, or *None* if no tick yet."""
        return self._get_candle_open()

    @property
    def seconds_in(self) -> float:
        """Seconds elapsed since the start of the current candle."""
        return self._get_seconds_in()

    # ── Account ─────────────────────────────────────────────────────────────

    @property
    def balance(self) -> float:
        return self._engine.balance

    @property
    def positions(self) -> list:
        return self._engine.positions()

    @property
    def pnl(self) -> float:
        return sum(p.pnl for p in self._engine.all_positions())

    @property
    def engine(self):
        return self._engine

    @property
    def paper(self):
        return self._engine

    @property
    def market(self) -> Optional[Market]:
        return self._market

    # ── Order book ──────────────────────────────────────────────────────────

    @property
    def orderbook(self) -> Optional[OrderBookAccessor]:
        """Live order book for the current market (auto-attached).

        Returns ``None`` if the market is not yet known (should not happen
        during normal operation).

        Usage
        -----
            >>> ctx.orderbook.up.bids       # top-of-book UP bids
            >>> ctx.orderbook.down.asks     # top-of-book DOWN asks
            >>> ctx.orderbook.up.spread     # UP bid-ask spread
            >>> ctx.orderbook.refresh()     # force REST refresh
        """
        if self._market is None or self._clob is None:
            return None
        if self._orderbook is None:
            self._orderbook = OrderBookAccessor(
                ctx=self,
                market=self._market,
                clob=self._clob,
            )
        return self._orderbook

    # ── Orders ──────────────────────────────────────────────────────────────

    def buy(self, side: str, amount: float, **kwargs):
        """Place a market buy order against this strategy's engine (paper or real)."""
        if self._hub is not None and self._hub.buy_once_per_market and self._hub._bought_this_market.get(self.name, False):
            return None
        order = self._place_buy(side, amount, **kwargs)
        if self._hub is not None and order:
            self._hub._bought_this_market[self.name] = True
        return order

    def _place_buy(self, side: str, amount: float, **kwargs):
        """Place the order and fire Telegram notifications (bypasses guards)."""
        if getattr(self._engine, "config", None) is not None and getattr(self._engine.config, "require_confirmation", False):
            kwargs.setdefault("confirm", False)
        # paper engine cannot accept real-specific kwargs
        hub_engine = getattr(self._hub, "engine", "paper") if self._hub else "paper"
        if hub_engine != "real":
            allowed = {"stop_loss_pct", "take_profit_pct", "time_window_start", "time_window_end", "stop_loss", "take_profit", "trail_sl", "trail_tp"}
            kwargs = {k: v for k, v in kwargs.items() if k in allowed}
        order = self._engine.buy(market=self._market, side=side, amount=amount, **kwargs)

        # Send Telegram notification if configured
        if self._hub is not None and self._hub._telegram and order:
            price = getattr(self._stream, side.lower(), None) or self.price.up if side == "UP" else self.price.down
            self._hub._telegram.send_buy(
                asset=self._asset,
                side=side,
                amount=amount,
                price=price,
                strategy_name=self.name
            )

        return order

    def limit(self, side: str, price: float, amount: float, **kwargs):
        """Place a limit order against this strategy's engine.

        Respects the same ``buy_once_per_market`` guard as :meth:`buy`, so
        a limit order cannot be used to circumvent the once-per-market cap.
        """
        if self._hub is not None and self._hub.buy_once_per_market and self._hub._bought_this_market.get(self.name, False):
            return None
        if getattr(self._engine, "config", None) is not None and getattr(self._engine.config, "require_confirmation", False):
            kwargs.setdefault("confirm", False)
        hub_engine = getattr(self._hub, "engine", "paper") if self._hub else "paper"
        if hub_engine != "real":
            allowed = {"time_window_start", "time_window_end"}
            kwargs = {k: v for k, v in kwargs.items() if k in allowed}
        order = self._engine.limit(
            market=self._market, side=side, price=price, amount=amount, **kwargs
        )
        if self._hub is not None and order:
            self._hub._bought_this_market[self.name] = True
        return order

    def close_position(self, side: str, amount: Optional[float] = None, **kwargs):
        """Close an open position for this strategy."""
        if hasattr(self._engine, "sell_position"):
            order = self._engine.sell_position(
                market=self._market, side=side, amount=amount, **kwargs
            )
        else:
            order = self._engine.sell(
                market=self._market, side=side, amount=amount, **kwargs
            )
        
        # Send Telegram notification if configured
        if self._hub is not None and self._hub._telegram and order:
            price = getattr(self._stream, side.lower(), None) or self.price.up if side == "UP" else self.price.down
            sell_amount = amount if amount else (order.amount if hasattr(order, 'amount') else 0)
            self._hub._telegram.send_sell(
                asset=self._asset,
                side=side,
                amount=sell_amount,
                price=price,
                strategy_name=self.name
            )
        
        return order

    # ── Candle-aware trading guards ───────────────────────────────────────

    def buy_once_per_candle(self, side: str, amount: float):
        """Buy only if *side* hasn't been bought yet in the current candle.

        Tracks buys per candle via the hub's ``_bought_this_candle`` dict.
        Safe to call multiple times — subsequent calls within the same
        candle for the same side are silently skipped.

        Parameters
        ----------
        side : "UP" | "DOWN"
        amount : USDC to spend
        """
        cid = self._get_candle_id()
        sides = self._bought_this_candle.setdefault(cid, {}).setdefault(self.name, set())
        side = side.upper()
        if side in sides:
            return
        result = self._place_buy(side, amount)
        sides.add(side)
        return result

    def buy_in_window(self, side: str, amount: float, min_seconds: float, max_seconds: float):
        """Only buy if ``seconds_in`` is within ``[min_seconds, max_seconds]``.

        Useful for buying early in a candle (e.g. first 30 s) or waiting
        for confirmation (e.g. after 60 s of a 5 m candle).

        Parameters
        ----------
        side : "UP" | "DOWN"
        amount : USDC to spend
        min_seconds : float
            Minimum seconds into the candle before buying.
        max_seconds : float
            Maximum seconds into the candle; no buy after this point.
        """
        secs = self.seconds_in
        if min_seconds <= secs <= max_seconds:
            return self._place_buy(side, amount)

    # ── Indicators (shared price history) ──────────────────────────────────

    def _get_price_series(self):
        if self._cached_series is not None:
            return self._cached_series
        if pd is None:
            raise RuntimeError(
                "Indicators require 'pandas'. Install: pip install pandas"
            )
        if len(self._price_history) < 14:
            return None
        self._cached_series = pd.Series(list(self._price_history))
        return self._cached_series

    def _get_down_price_series(self):
        if self._down_cached_series is not None:
            return self._down_cached_series
        if pd is None:
            raise RuntimeError(
                "Indicators require 'pandas'. Install: pip install pandas"
            )
        if len(self._down_price_history) < 14:
            return None
        self._down_cached_series = pd.Series(list(self._down_price_history))
        return self._down_cached_series

    @property
    def indicators(self) -> IndicatorAccessor:
        """First-class indicator access (RSI, MACD, Bollinger Bands, SMA, EMA).

        Examples
        --------
        >>> ctx.indicators.rsi(14)
        >>> ctx.indicators.macd(12, 26, 9)
        >>> ctx.indicators.bollinger_bands(20, 2)
        >>> ctx.indicators.sma(20)
        >>> ctx.indicators.ema(12)
        """
        return self._indicators

    def _invalidate_series_cache(self) -> None:
        self._cached_series = None
        self._down_cached_series = None
        self._indicators.invalidate()
        self._down_indicators.invalidate()

    @property
    def down_indicators(self) -> IndicatorAccessor:
        """Indicators computed on the DOWN leg price history.

        Mirrors ``ctx.indicators`` but is fed from ``down`` ticks instead
        of ``up`` ticks, so DOWN-based signals use DOWN data.
        """
        return self._down_indicators

    @property
    def rsi(self) -> Optional[float]:
        series = self._get_price_series()
        if series is None or _rsi is None:
            return None
        try:
            val = _rsi(series, 14).iloc[-1]
            return None if pd.isna(val) else float(val)
        except Exception:
            return None

    @property
    def sma_20(self) -> Optional[float]:
        series = self._get_price_series()
        if series is None or _sma is None:
            return None
        try:
            val = _sma(series, 20).iloc[-1]
            return None if pd.isna(val) else float(val)
        except Exception:
            return None

    @property
    def ema_12(self) -> Optional[float]:
        series = self._get_price_series()
        if series is None or _ema is None:
            return None
        try:
            val = _ema(series, 12).iloc[-1]
            return None if pd.isna(val) else float(val)
        except Exception:
            return None

    # ── Strategy Helper Methods ────────────────────────────────────────────────

    def bollinger_pctile(self, period: int = 20, std_dev: float = 2.0, avg_period: int = 50) -> tuple[Optional[float], Optional[dict]]:
        """Calculate Bollinger band width percentile and current band values.

        Returns the percentile of current band width relative to historical average,
        along with the current upper, lower, and close values.

        Parameters
        ----------
        period : int
            BB period (default: 20).
        std_dev : float
            Standard deviation multiplier (default: 2.0).
        avg_period : int
            Rolling average period for width comparison (default: 50).

        Returns
        -------
        tuple (pctile, bb_dict)
            pctile : float or None
                Width percentile (0-100) based on historical average.
            bb_dict : dict or None
                Dictionary with 'upper', 'lower', 'close' values.
        """
        series = self._get_price_series()
        if series is None or _bbands is None:
            return None, None

        try:
            bb_df = _bbands(series, period, float(std_dev))
            upper = float(bb_df.iloc[-1, 2])
            lower = float(bb_df.iloc[-1, 0])
            close = float(series.iloc[-1])

            if pd.isna(upper) or pd.isna(lower) or pd.isna(close):
                return None, None

            # Calculate width and historical average
            width = upper - lower
            if len(series) < avg_period:
                return None, None

            # Calculate historical widths
            historical_widths = []
            for i in range(avg_period, len(series)):
                if i >= period:
                    slice_series = series.iloc[i-period:i]
                    slice_bb = _bbands(slice_series, period, float(std_dev))
                    if not pd.isna(slice_bb.iloc[-1, 2]) and not pd.isna(slice_bb.iloc[-1, 0]):
                        hist_width = float(slice_bb.iloc[-1, 2]) - float(slice_bb.iloc[-1, 0])
                        historical_widths.append(hist_width)

            if not historical_widths:
                return None, None

            avg_width = sum(historical_widths) / len(historical_widths)
            if avg_width == 0:
                return None, None

            # Calculate percentile (where current width falls in distribution)
            pctile = (width / avg_width) * 100

            bb_dict = {
                "upper": upper,
                "lower": lower,
                "close": close
            }

            return pctile, bb_dict

        except Exception:
            return None, None

    def vol_ratio(self, period: int = 10) -> Optional[float]:
        """Get volume ratio from Binance data.

        Parameters
        ----------
        period : int
            Period for volume ratio calculation (default: 10).

        Returns
        -------
        float or None
            Volume ratio value.
        """
        if self._binance is None:
            return None
        return self._binance.vol_ratio(period)

    def side_price(self, direction: str) -> Optional[float]:
        """Get the current price for a specific direction.

        Parameters
        ----------
        direction : str
            "UP" or "DOWN".

        Returns
        -------
        float or None
            Current price for the specified direction.
        """
        direction = direction.upper()
        if direction == "UP":
            return self.price.up
        elif direction == "DOWN":
            return self.price.down
        return None


# ── Registered strategy ────────────────────────────────────────────────────────

@dataclass
class _RegisteredStrategy:
    """A registered strategy with optional comparison metadata.

    Every strategy (whether registered via ``strategy()`` or ``variant()``)
    is stored as this type.  Strategies with non-empty ``params`` are
    considered "variants" for comparison purposes.
    """

    name: str
    fn: Callable[[StrategyContext], None]
    balance: float
    params: dict = field(default_factory=dict)
    id: str = ""
    created_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
    run_count: int = 0
    paper: Optional[PaperEngine] = None  # lazily built on first cycle (or RealTradingEngine when engine=real)
    _engine: Optional[object] = None  # unified engine ref (paper or real)
    ctx: Optional[StrategyContext] = None

    def __post_init__(self) -> None:
        if not self.id:
            self.id = self.name


Variant = _RegisteredStrategy  # backward compat alias


# ── BotHub ────────────────────────────────────────────────────────────────────

class BotHub:
    """
    Run multiple strategies from a single data connection.

    One market discovery, one WebSocket stream, N isolated paper engines.
    Eliminates redundant rate-limited connections when running many
    strategies on the same asset / timeframe.

    Parameters
    ----------
    asset : str
        BTC, ETH, SOL, XRP, DOGE, HYPE, BNB.
    timeframe : str
        5m, 15m, 1h, 4h, 24h.
    default_balance : float
        Default starting paper balance per strategy (default 100.0).
    mode : str
        Fee/execution template: ``"simple"``, ``"realistic"``, ``"custom"``.
    paper_config : PaperConfig, optional
        Custom paper config when ``mode="custom"``.
    log_dir : str, optional
        Directory for per-strategy rotating log files.  If set, each
        strategy and variant gets its own ``{name}.log`` file (5 MB max,
        3 backups) with DEBUG-level output.

    Usage
    -----
        hub = polyalpha.BotHub("BTC", "5m", default_balance=500)

        @hub.strategy("momentum")
        def momentum(ctx):
            if ctx.price.up > 0.9:
                ctx.buy("UP", 20)

        @hub.strategy("value", balance=1000)
        def value(ctx):
            if ctx.price.down < 0.10:
                ctx.buy("DOWN", 10)

        hub.run()
    """

    def __init__(
        self,
        asset: str,
        timeframe: str,
        default_balance: float = 100.0,
        mode: str = "simple",
        paper_config: Optional[PaperConfig] = None,
        chainlink: bool = True,
        log_dir: Optional[str] = None,
        globals: Optional[object] = None,
        buy_once_per_market: bool = True,
        chainlink_history=None,
        market_provider=None,
        engine: str | object | None = None,
        **kwargs,
    ):
        asset = asset.upper()
        if asset not in ASSETS:
            raise ValueError(
                f"Unsupported asset '{asset}'. Supported: {list(ASSETS)}"
            )
        if timeframe not in TIMEFRAME_SECONDS:
            raise ValueError(
                f"Unsupported timeframe '{timeframe}'. "
                f"Supported: {list(TIMEFRAME_SECONDS)}"
            )

        self.asset = asset
        self.timeframe = timeframe
        self.default_balance = default_balance
        self.mode = mode
        self.buy_once_per_market = buy_once_per_market
        self._bought_this_market: dict[str, bool] = {}
        self._log_dir = log_dir
        self._globals = globals  # Shared feeds — one connection, many strategies

        from .trading.paper_config import get_paper_config_from_preset

        if mode == "realistic":
            self._paper_config = get_paper_config_from_preset("REALISTIC")
        elif mode == "custom":
            self._paper_config = paper_config or PaperConfig()
        else:
            self._paper_config = get_paper_config_from_preset("TEST")

        # chainlink_history may be in kwargs (e.g. from tests)
        if chainlink_history is None and "chainlink_history" in kwargs:
            chainlink_history = kwargs.pop("chainlink_history")
        else:
            kwargs.pop("chainlink_history", None)

        # market_provider may be passed positionally or via kwargs
        if market_provider is None and "market_provider" in kwargs:
            market_provider = kwargs.pop("market_provider")
        else:
            kwargs.pop("market_provider", None)
        self._market_provider = market_provider

        # Engine selection — "paper" (default, isolated per-strategy) or "real" (shared client.real)
        if engine is None:
            engine_name = "paper"
            # allow paper= kwarg for backcompat
            if "paper" in kwargs:
                pv = kwargs.pop("paper")
                engine_name = "real" if pv is False else "paper"
        elif isinstance(engine, str):
            engine_name = engine.lower()
        else:
            engine_name = "custom"
        self.engine = engine_name
        self._custom_engine = engine if not isinstance(engine, str) and engine is not None else None

        # One shared client for market discovery + stream creation.
        # Its paper engine is unused when engine=="paper" — each strategy gets its own.
        # For engine=="real", shared client's real engine is the shared engine.
        self._shared_client = Client(
            balance=default_balance,
            paper_config=self._paper_config,
            **kwargs,
        )
        if engine_name == "real" and self._shared_client.real is None:
            raise ValueError("engine='real' requires private_key + rpc_url + polymarket_api_key")
        if engine_name == "custom" and self._custom_engine is None:
            raise ValueError("custom engine instance required")

        self._strategies: list[_RegisteredStrategy] = []
        self._market: Optional[Market] = None
        self._stream = None
        self._price_history: deque[float] = deque(maxlen=200)
        self._down_price_history: deque[float] = deque(maxlen=200)
        self._stop_event = threading.Event()
        self._tick_count = 0
        self._candle_start_time: float = 0.0
        self._candle_open_price: Optional[float] = None
        self._candle_id: int = 0
        self._bought_this_candle: dict[int, dict[str, set[str]]] = {}
        self._final_up: Optional[float] = None
        self._final_down: Optional[float] = None
        # Resolve the shared Chainlink streamer ONCE. When the caller supplies
        # a shared globals.price_feed we reuse it for both the price cache and
        # the context streamer instead of opening a second oracle socket.
        shared_cl = None
        if self._globals is not None:
            try:
                from .analysis.streaming import ChainlinkStreamer
                _pf = getattr(self._globals, "price_feed", None)
                shared_cl = _pf if isinstance(_pf, ChainlinkStreamer) else None
            except Exception:
                shared_cl = None
        self._chainlink_cache: Optional[object] = None
        if chainlink:
            try:
                from .core.chainlink_cache import ChainlinkPriceCache
                self._chainlink_cache = ChainlinkPriceCache(symbol=self.asset, streamer=shared_cl)
            except Exception as exc:
                self._log.warning("Chainlink cache unavailable: %s", exc)
        self._log = logging.getLogger("polyalpha.BotHub")
        self._strategy_loggers: dict[str, logging.Logger] = {}
        _log_indicators()

        # ── Event / hook system ──────────────────────────────────────────
        self._handlers: dict[str, list[Callable]] = defaultdict(list)
        self._interval_handlers: list[dict] = []

        # Initialize Telegram notifier (optional)
        self._telegram: Optional[TelegramNotifier] = None
        if TelegramNotifier is not None:
            self._telegram = TelegramNotifier()

        # Initialize Chainlink streamer (live BTC spot from Polymarket).
        # Reuse the shared globals.price_feed when one is provided so we do
        # NOT open a second oracle connection — the caller owns its lifecycle.
        self._chainlink: Optional[object] = None
        self._shared_cl_window: Optional[TimeWindow] = TimeWindow(max_age=120) if TimeWindow is not None else None
        try:
            from .analysis.streaming import ChainlinkStreamer
            cl = shared_cl
            if cl is None:
                cl = ChainlinkStreamer()
                cl.start(asset, background=True)
            self._chainlink = cl
        except Exception as exc:
            self._log.debug("Chainlink streamer not available: %s", exc)

        # Initialize Binance accessor (TA on Binance data)
        self._binance: Optional[BinanceAccessor] = None
        try:
            self._binance = BinanceAccessor(asset=asset, timeframe=timeframe)
        except Exception as exc:
            self._log.debug("BinanceAccessor not available: %s", exc)

        # ── Chainlink history (shared candle store — user chooses {"1m":10, "1h":50, "1s":20}) ─
        # One recorder per (db_path, asset) via registry; unused TFs pruned automatically.
        self._chainlink_history = None
        self._chainlink_history_owned = False
        self._on_warmup = None
        self._last_warmup_emit = 0.0
        # Prefer globals.chainlink_history if caller supplied it
        _g_hist = getattr(self._globals, "chainlink_history", None) if self._globals is not None else None
        if _g_hist is not None:
            self._chainlink_history = _g_hist
            self._chainlink_history_owned = False
        elif chainlink_history is not None:
            try:
                rec, owned = _resolve_chainlink_history(chainlink_history, asset)
                self._chainlink_history = rec
                self._chainlink_history_owned = owned
                if rec is not None:
                    # reuse registry if shared flag, else direct
                    try:
                        rec.start(asset, background=True)
                    except Exception as exc:
                        self._log.warning("Chainlink history start failed: %s", exc)
                    self._log.info("Chainlink history enabled (hub): %s", getattr(rec.config, "warmup", rec))
            except Exception as exc:
                self._log.debug("Chainlink history init skipped (hub): %s", exc)

    @property
    def chainlink_history(self):
        """Shared :class:`~polyalpha.history.ChainlinkRecorder` or None."""
        return getattr(self, "_chainlink_history", None)

    def on_warmup(self, fn: Callable) -> Callable:
        """Register warmup callback — called with status dict while warming.

        Example: ``@hub.on_warmup(lambda s: print(f"warming {s}"))``
        Works for both ``block="wait"`` (hub blocks all strats) and
        ``block="skip"`` (each strat self-guards).
        """
        self._on_warmup = fn
        return fn

    # ── Helpers ─────────────────────────────────────────────────────────────

    def _active_tickers(self) -> list[_RegisteredStrategy]:
        """All registered strategies (including those with params)."""
        return self._strategies

    # ── Public API ──────────────────────────────────────────────────────────

    def strategy(
        self,
        name: str,
        balance: Optional[float] = None,
        params: Optional[dict] = None,
        id: str = "",
    ) -> Callable:
        """
        Decorator — register a strategy function with the hub.

        Parameters
        ----------
        name : str
            Unique strategy name (used in logs and stats).
        balance : float, optional
            Per-strategy starting balance. Defaults to ``default_balance``.
        params : dict, optional
            Free-form parameter metadata for comparison reports.
            When provided, the strategy is treated as a "variant" and
            included in ``compare_variants()`` output.
        id : str, optional
            Stable identifier for persistence snapshots. Defaults to ``name``.

        Example
        -------
        >>> @hub.strategy("momentum", balance=500)
        ... def momentum(ctx):
        ...     if ctx.price.up > 0.9:
        ...         ctx.buy("UP", 20)

        >>> @hub.strategy("rsi_70", params={"rsi_threshold": 70})
        ... def rsi_70(ctx):
        ...     if ctx.rsi and ctx.rsi > 70:
        ...         ctx.buy("DOWN", 10)
        """
        if not name or not isinstance(name, str):
            raise ValueError("strategy name must be a non-empty string")

        def decorator(fn: Callable[[StrategyContext], None]) -> Callable:
            existing = {s.name for s in self._strategies}
            if name in existing:
                raise ValueError(f"strategy '{name}' already registered")
            self._strategies.append(
                _RegisteredStrategy(
                    name=name,
                    fn=fn,
                    balance=balance if balance is not None else self.default_balance,
                    params=dict(params) if params else {},
                    id=id or name,
                )
            )
            has_params = bool(params)
            label = "variant" if has_params else "strategy"
            log_params = f", params={params}" if has_params else ""
            self._log.info(
                "Registered %s '%s' (balance=$%.2f%s)",
                label, name, balance or self.default_balance, log_params,
            )
            return fn

        return decorator

    def add_strategy(
        self,
        name: str,
        fn: Callable[[StrategyContext], None],
        balance: Optional[float] = None,
        params: Optional[dict] = None,
        id: str = "",
    ) -> None:
        """Register a strategy without decorator syntax."""
        self.strategy(name, balance=balance, params=params, id=id)(fn)

    def variant(
        self,
        name: str,
        balance: Optional[float] = None,
        params: Optional[dict] = None,
        id: str = "",
    ) -> Callable:
        """Alias for ``strategy()`` — registers a variant for comparison.

        ``variant()`` is identical to ``strategy()``. Use it when you want
        to emphasise that this strategy carries parameter metadata for
        cross-variant comparison via ``compare_variants()``.

        See :meth:`strategy` for full parameter documentation.
        """
        return self.strategy(name, balance=balance, params=params, id=id)

    def add_variant(
        self,
        name: str,
        fn: Callable[[StrategyContext], None],
        balance: Optional[float] = None,
        params: Optional[dict] = None,
        id: str = "",
    ) -> None:
        """Register a variant without decorator syntax. Alias for ``add_strategy()``."""
        self.add_strategy(name, fn, balance=balance, params=params, id=id)

    # ── Event / hook system ─────────────────────────────────────────────

    def on(self, event: str, fn: Optional[Callable] = None):
        """Register an event handler (decorator or imperative).

        Supported events
        ----------------
        ``"start"``
            Hub started — handler receives no args.
        ``"stop"``
            Hub stopping gracefully — handler receives no args.
        ``"tick"``
            Every price tick — handler receives ``(up, down)``.
        ``"candle_open"``
            A new candle started — handler receives ``(open_price, candle_id)``.
        ``"candle_close"``
            The current candle closed — handler receives
            ``(candle_id, open_price, close_price)``.
        ``"error"``
            A strategy raised an exception — handler receives
            ``(strategy_name, exception)``.

        Usage
        -----
            @hub.on("tick")
            def on_tick(up, down):
                print(f"price={up:.3f}/{down:.3f}")

            @hub.on("candle_open")
            def on_candle_open(open_price, candle_id):
                print(f"New candle #{candle_id} opened at {open_price}")

            hub.on("stop", my_cleanup_fn)
        """
        if fn is None:
            return lambda f: self._add_handler(event, f)
        self._add_handler(event, fn)
        return fn

    def add_handler(self, event: str, fn: Callable) -> None:
        """Imperative event handler registration.

        See :meth:`on` for supported events and signatures.
        """
        self._add_handler(event, fn)

    def _add_handler(self, event: str, fn: Callable) -> None:
        if not callable(fn):
            raise TypeError(f"handler must be callable, got {type(fn).__name__}")
        self._handlers[event].append(fn)
        self._log.debug("Registered handler for event '%s'", event)

    def every(self, seconds: Union[float, int], fn: Optional[Callable] = None):
        """Register a periodic timer callback (decorator or imperative).

        The handler is called roughly every *seconds* seconds, checked
        on each price tick.  Handlers receive ``(up, down)`` — the
        latest mid-prices from the shared stream.

        Examples
        --------
            @hub.every(30)
            def status_check(up, down):
                print(f"30s ticker — up={up:.3f} down={down:.3f}")

            hub.every(60, my_minute_fn)
        """
        seconds = float(seconds)
        if seconds <= 0:
            raise ValueError("seconds must be positive")

        def _register(f):
            self._interval_handlers.append({
                "interval": seconds,
                "fn": f,
                "last_called": 0.0,
            })
            self._log.debug("Registered interval handler every %.1fs", seconds)
            return f

        if fn is None:
            return _register
        return _register(fn)

    # ── Event dispatch ──────────────────────────────────────────────────

    def _fire(self, event: str, *args, **kwargs) -> None:
        """Dispatch *event* to all registered handlers, isolating errors."""
        for fn in list(self._handlers.get(event, [])):
            try:
                fn(*args, **kwargs)
            except Exception as exc:
                self._log.exception("Handler for '%s' raised: %s", event, exc)

    def _fire_interval_handlers(self, *args, **kwargs) -> None:
        """Check and fire any due interval handlers."""
        now = time.time()
        for h in self._interval_handlers:
            if now - h["last_called"] >= h["interval"]:
                h["last_called"] = now
                try:
                    h["fn"](*args, **kwargs)
                except Exception as exc:
                    self._log.exception("Interval handler raised: %s", exc)

    @property
    def tick_count(self) -> int:
        """Total price ticks received this session."""
        return self._tick_count

    @property
    def strategy_count(self) -> int:
        """Total registered strategies."""
        return len(self._strategies)

    @property
    def variant_count(self) -> int:
        """Total registered strategies (alias for strategy_count)."""
        return len(self._strategies)

    @property
    def total_count(self) -> int:
        """Total registered strategies."""
        return len(self._strategies)

    @property
    def _variants(self) -> list[_RegisteredStrategy]:
        """Backward-compat: all strategies (variant is now an alias for strategy)."""
        return self._strategies

    @property
    def variants(self) -> list[_RegisteredStrategy]:
        """Read-only view of all registered strategies."""
        return list(self._strategies)

    @property
    def strategies(self) -> list[_RegisteredStrategy]:
        """Read-only view of all registered strategies."""
        return list(self._strategies)

    @property
    def stats(self) -> dict:
        """Per-strategy running stats."""
        stats = {}
        for s in self._strategies:
            entry = {
                "balance": s.paper.balance if s.paper else s.balance,
                "pnl": sum(p.pnl for p in s.paper.all_positions())
                    if s.paper else 0.0,
                "open_positions": len(s.paper.positions()) if s.paper else 0,
            }
            if s.params:
                entry["params"] = dict(s.params)
            stats[s.name] = entry
        return {
            "ticks": self._tick_count,
            "strategies": stats,
        }

    def run(self) -> None:
        """Start the hub (blocking). Runs until stop() or fatal error."""
        if not self._strategies:
            raise RuntimeError(
                "No strategies registered. "
                "Use @hub.strategy(...) or @hub.variant(...) first."
            )
        self._log.info(
            "BotHub starting: %s %s | strategies=%d | total_balance=$%.2f",
            self.asset, self.timeframe,
            len(self._strategies),
            sum(s.balance for s in self._active_tickers()),
        )
        self._stop_event.clear()
        self._fire("start")

        try:
            while not self._stop_event.is_set():
                self._run_cycle()
        except KeyboardInterrupt:
            self._log.info("Interrupted by user")
        except Exception:
            self._log.exception("BotHub fatal error")
            raise
        finally:
            self._cleanup()

    async def run_async(self) -> None:
        """Start the hub using async IO. Runs until stop() or fatal error."""
        if not self._strategies:
            raise RuntimeError(
                "No strategies registered. "
                "Use @hub.strategy(...) or @hub.variant(...) first."
            )
        self._log.info(
            "BotHub starting (async): %s %s | strategies=%d",
            self.asset, self.timeframe,
            len(self._strategies),
        )
        self._stop_event.clear()
        self._fire("start")

        try:
            while not self._stop_event.is_set():
                await self._run_cycle_async()
        except asyncio.CancelledError:
            self._log.info("BotHub cancelled")
        except Exception:
            self._log.exception("BotHub fatal error")
            raise
        finally:
            self._cleanup()

    def stop(self) -> None:
        """Signal the hub to stop gracefully."""
        self._log.info("BotHub stopping...")
        self._stop_event.set()
        if self._stream:
            try:
                self._stream.stop()
            except Exception:
                pass

    # ── Cycle (mirrors Bot._run_cycle) ──────────────────────────────────────

    def _run_cycle(self) -> None:
        """Single market cycle: discover → stream → tick×N → resolve → rollover."""
        try:
            self._discover()
            self._stream_prices()
        except MarketNotFound:
            self._log.warning("No market found, retrying in 30s...")
            self._sleep(30)
            return

        self._resolve_all()
        self._rollover()

    async def _run_cycle_async(self) -> None:
        """Async single market cycle."""
        try:
            self._discover()
            await self._stream_prices_async()
        except MarketNotFound:
            self._log.warning("No market found, retrying in 30s...")
            await self._asleep(30)
            return

        self._resolve_all()
        await self._rollover_async()

    # ── Lifecycle steps ─────────────────────────────────────────────────────

    def _resolve_external_market(self):
        """Try to obtain a :class:`Market` from ``self._market_provider``."""
        provider = getattr(self, "_market_provider", None)
        if provider is None:
            return None
        result = None
        try:
            if callable(provider):
                try:
                    result = provider()
                except TypeError:
                    result = provider(self.asset, self.timeframe)
            elif hasattr(provider, "get_market"):
                result = provider.get_market()
            elif hasattr(provider, "market"):
                result = getattr(provider, "market")
                if result is None and hasattr(provider, "get_market"):
                    try:
                        result = provider.get_market()
                    except Exception:
                        result = None
            elif hasattr(provider, "latest"):
                result = provider.latest(self.asset, self.timeframe)
            else:
                return None
        except Exception as exc:
            self._log.debug("Market provider call failed: %s", exc)
            return None
        if result is None:
            return None
        if isinstance(result, str):
            slug = result.strip()
            if not slug:
                return None
            try:
                return self._shared_client.markets.get(slug)
            except Exception as exc:
                self._log.debug("Market provider slug resolution failed for %s: %s", slug, exc)
                return None
        if hasattr(result, "slug"):
            return result
        return None

    def _discover(self) -> None:
        """Discover the latest market ONCE for all strategies and variants."""
        if getattr(self, "_market_provider", None) is not None:
            try:
                ext_market = self._resolve_external_market()
                if ext_market is not None:
                    self._market = ext_market
                    self._log.info("Market found (via provider): %s (shared by %d tickers)",
                                   self._market.slug, len(self._active_tickers()))
                    # Build / refresh each strategy's and variant's engine + Context
                    for s in self._active_tickers():
                        if s.paper is None:
                            if getattr(self, "engine", "paper") == "real":
                                # real: share single RealTradingEngine across strategies
                                s.paper = self._shared_client.real  # type: ignore
                                s._engine = self._shared_client.real  # type: ignore
                            elif getattr(self, "engine", "paper") == "custom" and getattr(self, "_custom_engine", None) is not None:
                                s.paper = self._custom_engine  # type: ignore
                                s._engine = self._custom_engine  # type: ignore
                            else:
                                from .trading.paper_engine import PaperEngine
                                s.paper = PaperEngine(
                                    balance=s.balance,
                                    config=self._paper_config,
                                    db=self._shared_client.db,
                                )
                                s._engine = s.paper
                        s.ctx = StrategyContext(
                            name=s.name,
                            stream=self._stream,
                            paper=s.paper,
                            market=self._market,
                            price_history=self._price_history,
                            down_price_history=self._down_price_history,
                            asset=self.asset,
                            clob=self._shared_client._clob,
                            chainlink_cache=self._chainlink_cache,
                            chainlink=self._chainlink,
                            binance=self._binance,
                            cl_window=self._shared_cl_window,
                            globals=self._globals,
                            get_candle_open=lambda: self._candle_open_price,
                            get_seconds_in=lambda: max(0.0, time.time() - self._candle_start_time),
                            get_candle_id=lambda: self._candle_id,
                            bought_this_candle=self._bought_this_candle,
                            hub=self,
                            chainlink_history=self._chainlink_history,
                            engine=getattr(s, "_engine", s.paper),
                        )
                        if self._log_dir and s.name not in self._strategy_loggers:
                            from .utils.logging_utils import setup_strategy_logger
                            slog = setup_strategy_logger(
                                f"{self.asset}_{s.name}", self._log_dir,
                            )
                            self._strategy_loggers[s.name] = slog
                    return
                self._log.debug("Market provider returned None, falling back to native discovery")
            except Exception as exc:
                self._log.error("Market provider discovery failed: %s, falling back", exc)
        self._market = self._shared_client.markets.latest(self.asset, self.timeframe)
        self._log.info("Market found: %s (shared by %d tickers)",
                       self._market.slug, len(self._active_tickers()))

        # Build / refresh each strategy's and variant's engine + Context.
        for s in self._active_tickers():
            if s.paper is None:
                if getattr(self, "engine", "paper") == "real":
                    s.paper = self._shared_client.real  # type: ignore
                    s._engine = self._shared_client.real  # type: ignore
                elif getattr(self, "engine", "paper") == "custom" and getattr(self, "_custom_engine", None) is not None:
                    s.paper = self._custom_engine  # type: ignore
                    s._engine = self._custom_engine  # type: ignore
                else:
                    from .trading.paper_engine import PaperEngine
                    s.paper = PaperEngine(
                        balance=s.balance,
                        config=self._paper_config,
                        db=self._shared_client.db,
                    )
                    s._engine = s.paper
            s.ctx = StrategyContext(
                name=s.name,
                stream=self._stream,  # set later in _stream_prices
                paper=s.paper,
                market=self._market,
                price_history=self._price_history,
                down_price_history=self._down_price_history,
                asset=self.asset,
                clob=self._shared_client._clob,
                chainlink_cache=self._chainlink_cache,
                chainlink=self._chainlink,
                binance=self._binance,
                cl_window=self._shared_cl_window,
                globals=self._globals,
                get_candle_open=lambda: self._candle_open_price,
                get_seconds_in=lambda: max(0.0, time.time() - self._candle_start_time),
                get_candle_id=lambda: self._candle_id,
                bought_this_candle=self._bought_this_candle,
                hub=self,
                chainlink_history=self._chainlink_history,
                engine=getattr(s, "_engine", s.paper),
            )
            # Per-strategy rotating file logger
            if self._log_dir and s.name not in self._strategy_loggers:
                from .utils.logging_utils import setup_strategy_logger
                slog = setup_strategy_logger(
                    f"{self.asset}_{s.name}", self._log_dir,
                )
                self._strategy_loggers[s.name] = slog

    def _stream_prices(self) -> None:
        """Set up ONE stream and fan ticks out to all strategies + variants."""
        self._stream = self._shared_client.stream(self._market)

        # Attach each strategy's and variant's engine to the SAME stream
        for s in self._active_tickers():
            eng = getattr(s, "_engine", None) or getattr(s, "paper", None)
            if eng is not None:
                try:
                    eng.attach_stream(self._stream, self._market)
                except Exception:
                    pass
            if s.ctx is not None:
                s.ctx._stream = self._stream
                # keep ctx engine in sync
                if eng is not None:
                    s.ctx._engine = eng
                    s.ctx._paper = eng

        @self._stream.on("price")
        def on_price(up: float, down: float):
            if self._stop_event.is_set():
                return
            self._tick_count += 1
            self._price_history.append(up)
            self._down_price_history.append(down)
            # Refresh Binance data on each tick (candle-gated internally)
            if self._binance is not None:
                try:
                    self._binance._refresh()
                except Exception:
                    pass
            # ── Chainlink history warmup gate (hub union) ──────────────────
            # User chose e.g. {"1m":10, "1h":50, "1s":20}; hub waits for ALL before any strat runs
            if self._chainlink_history is not None and getattr(self._chainlink_history, "config", None) is not None:
                cfg = self._chainlink_history.config
                need = getattr(cfg, "warmup", {}) or {}
                if need and cfg.block == "wait" and not self._chainlink_history.is_ready_map(need):
                    now_w = time.time()
                    if now_w - getattr(self, "_last_warmup_emit", 0) >= getattr(cfg, "warmup_emit_interval", 5.0):
                        self._last_warmup_emit = now_w
                        try:
                            status = self._chainlink_history.status(need)
                        except Exception:
                            status = {"warming": True}
                        self._log.info("Warming chainlink history (hub) %s", status)
                        self._fire("warmup", status)
                        if getattr(self, "_on_warmup", None):
                            try:
                                self._on_warmup(status)
                            except Exception:
                                pass
                    # still advance candle tracking but skip strat fan-out
                    now2 = time.time()
                    tf_seconds = TIMEFRAME_SECONDS.get(self.timeframe, 300)
                    candle_start = (now2 // tf_seconds) * tf_seconds
                    if candle_start != self._candle_start_time:
                        self._fire("candle_close", self._candle_id, self._candle_open_price, up)
                        self._candle_start_time = candle_start
                        self._candle_open_price = up
                        self._candle_id += 1
                        self._bought_this_candle[self._candle_id] = {}
                        self._fire("candle_open", self._candle_open_price, self._candle_id)
                    return

            # ── Candle tracking ──────────────────────────────────────────
            now = time.time()
            tf_seconds = TIMEFRAME_SECONDS[self.timeframe]
            candle_start = (now // tf_seconds) * tf_seconds
            if candle_start != self._candle_start_time:
                self._fire("candle_close", self._candle_id, self._candle_open_price, up)
                self._candle_start_time = candle_start
                self._candle_open_price = up
                self._candle_id += 1
                self._bought_this_candle[self._candle_id] = {}
                self._fire("candle_open", self._candle_open_price, self._candle_id)
            # Invalidate each context's cached price series so indicators
            # recompute on the new history.
            for s in self._active_tickers():
                if s.ctx is not None:
                    s.ctx._invalidate_series_cache()

            # ── Fan-out: call each strategy/variant with error isolation ──
            for s in self._active_tickers():
                if s.ctx is None or self._stop_event.is_set():
                    continue
                try:
                    s.fn(s.ctx)
                except Exception as exc:
                    slog = self._strategy_loggers.get(s.name, self._log)
                    slog.exception(
                        "Strategy '%s' raised: %s", s.name, exc
                    )
                    self._fire("error", s.name, exc)

            # ── Hub-level events ───────────────────────────────────────
            self._fire("tick", up, down)
            self._fire_interval_handlers(up, down)

        @self._stream.on("close")
        def on_close():
            self._final_up = getattr(self._stream, "up", None)
            self._final_down = getattr(self._stream, "down", None)
            self._log.info("Market closed: %s", self._market.slug)

        # Blocking — returns when the stream ends (market resolved).
        self._stream.start(background=False)

    async def _stream_prices_async(self) -> None:
        """Async single-stream fan-out to all strategies + variants."""
        self._stream = self._shared_client.stream(self._market)

        for s in self._active_tickers():
            if s.paper is not None:
                s.paper.attach_stream(self._stream, self._market)
            if s.ctx is not None:
                s.ctx._stream = self._stream

        @self._stream.on("price")
        def on_price(up: float, down: float):
            if self._stop_event.is_set():
                return
            self._tick_count += 1
            self._price_history.append(up)
            self._down_price_history.append(down)
            # Refresh Binance data on each tick (candle-gated internally)
            if self._binance is not None:
                try:
                    self._binance._refresh()
                except Exception:
                    pass
            # ── Chainlink history warmup gate (hub union, async) ───────
            if self._chainlink_history is not None and getattr(self._chainlink_history, "config", None) is not None:
                cfg = self._chainlink_history.config
                need = getattr(cfg, "warmup", {}) or {}
                if need and cfg.block == "wait" and not self._chainlink_history.is_ready_map(need):
                    now_w = time.time()
                    if now_w - getattr(self, "_last_warmup_emit", 0) >= getattr(cfg, "warmup_emit_interval", 5.0):
                        self._last_warmup_emit = now_w
                        try:
                            status = self._chainlink_history.status(need)
                        except Exception:
                            status = {"warming": True}
                        self._log.info("Warming chainlink history (hub async) %s", status)
                        self._fire("warmup", status)
                        if getattr(self, "_on_warmup", None):
                            try:
                                self._on_warmup(status)
                            except Exception:
                                pass
                    now2 = time.time()
                    tf_seconds = TIMEFRAME_SECONDS.get(self.timeframe, 300)
                    candle_start = (now2 // tf_seconds) * tf_seconds
                    if candle_start != self._candle_start_time:
                        self._fire("candle_close", self._candle_id, self._candle_open_price, up)
                        self._candle_start_time = candle_start
                        self._candle_open_price = up
                        self._candle_id += 1
                        self._bought_this_candle[self._candle_id] = {}
                        self._fire("candle_open", self._candle_open_price, self._candle_id)
                    return
            # ── Candle tracking ──────────────────────────────────────────
            now = time.time()
            tf_seconds = TIMEFRAME_SECONDS[self.timeframe]
            candle_start = (now // tf_seconds) * tf_seconds
            if candle_start != self._candle_start_time:
                self._fire("candle_close", self._candle_id, self._candle_open_price, up)
                self._candle_start_time = candle_start
                self._candle_open_price = up
                self._candle_id += 1
                self._bought_this_candle[self._candle_id] = {}
                self._fire("candle_open", self._candle_open_price, self._candle_id)
            for s in self._active_tickers():
                if s.ctx is not None:
                    s.ctx._invalidate_series_cache()

            for s in self._active_tickers():
                if s.ctx is None or self._stop_event.is_set():
                    continue
                try:
                    s.fn(s.ctx)
                except Exception as exc:
                    slog = self._strategy_loggers.get(s.name, self._log)
                    slog.exception(
                        "Strategy '%s' raised: %s", s.name, exc
                    )
                    self._fire("error", s.name, exc)

            # ── Hub-level events ───────────────────────────────────────
            self._fire("tick", up, down)
            self._fire_interval_handlers(up, down)

        @self._stream.on("close")
        def on_close():
            self._final_up = getattr(self._stream, "up", None)
            self._final_down = getattr(self._stream, "down", None)
            self._log.info("Market closed: %s", self._market.slug)

        await self._stream.run_async()

    def _resolve_all(self) -> None:
        """Resolve positions for every strategy and variant after the market closes."""
        if not self._market:
            return
        final_up = self._final_up if self._final_up is not None else getattr(self._stream, "up", None) if self._stream else None
        final_down = self._final_down if self._final_down is not None else getattr(self._stream, "down", None) if self._stream else None
        if final_up is None or final_down is None or final_up == final_down:
            self._log.info("No final prices to resolve %s", self._market.slug)
            return
        outcome = "UP" if final_up > final_down else "DOWN"
        # Real engine: on-chain settlement, no manual resolve; just sync
        if getattr(self, "engine", "paper") == "real":
            self._log.info("Real engine: market %s outcome %s (on-chain settle pending)", self._market.slug, outcome)
            try:
                if hasattr(self._shared_client.real, "sync_positions_from_chain"):
                    self._shared_client.real.sync_positions_from_chain()
            except Exception:
                pass
            return
        for s in self._active_tickers():
            eng = getattr(s, "_engine", None) or s.paper
            if eng is None:
                continue
            try:
                eng.resolve(self._market, outcome)
            except Exception as exc:
                self._log.warning("Failed to resolve %s: %s", s.name, exc)
                continue
            for pos in eng.all_positions():
                if pos.market_id != self._market.id or not pos.resolved:
                    continue
                slog = self._strategy_loggers.get(s.name, self._log)
                slog.info(
                    "Trade resolved: %s %s | pnl=$%.2f",
                    pos.side, pos.outcome, pos.pnl,
                )

                # Send Telegram notification if configured
                if self._telegram:
                    self._telegram.send_resolve(
                        asset=self.asset,
                        side=pos.side,
                        outcome=pos.outcome,
                        pnl=pos.pnl,
                        strategy_name=s.name
                    )

    def _rollover(self) -> None:
        """Clean up the stream and prepare for the next cycle."""
        if self._stream:
            try:
                self._stream.stop()
            except Exception:
                pass
            self._stream = None
        self._market = None
        self._candle_id = 0
        self._candle_start_time = 0.0
        self._candle_open_price = None
        self._final_up = None
        self._final_down = None
        self._bought_this_candle = {}
        self._bought_this_market = {}
        for s in self._active_tickers():
            s.ctx = None
        self._log.info("Rolling over to next market...")
        self._sleep(2)

    async def _rollover_async(self) -> None:
        if self._stream:
            try:
                self._stream.stop()
            except Exception:
                pass
            self._stream = None
        self._market = None
        self._candle_id = 0
        self._candle_start_time = 0.0
        self._candle_open_price = None
        self._final_up = None
        self._final_down = None
        self._bought_this_candle = {}
        self._bought_this_market = {}
        for s in self._active_tickers():
            s.ctx = None
        self._log.info("Rolling over to next market...")
        await self._asleep(2)

    # ── Helpers ─────────────────────────────────────────────────────────────

    def _sleep(self, seconds: float) -> None:
        """Sleep, checking stop_event periodically."""
        for _ in range(int(seconds * 10)):
            if self._stop_event.is_set():
                break
            time.sleep(0.1)

    async def _asleep(self, seconds: float) -> None:
        """Async sleep, checking stop_event periodically."""
        for _ in range(int(seconds * 10)):
            if self._stop_event.is_set():
                break
            await asyncio.sleep(0.1)

    def _cleanup(self) -> None:
        """Clean up shared resources."""
        self._fire("stop")
        if self._stream:
            try:
                self._stream.stop()
            except Exception:
                pass
        if self._chainlink_cache is not None:
            try:
                self._chainlink_cache.stop()
            except Exception:
                pass
        rec = getattr(self, "_chainlink_history", None)
        if rec is not None and getattr(self, "_chainlink_history_owned", False):
            try:
                rec.stop()
            except Exception:
                pass
        self._shared_client.close()
        self._log.info(
            "BotHub stopped — total ticks=%d, strategies=%d",
            self._tick_count, len(self._strategies),
        )

    # ── Variant comparison & persistence ─────────────────────────────────────

    def compare_variants(self) -> ComparisonReport:
        """Build a comparison report for all strategies with params.

        Results are sorted by P&L descending and include per-strategy
        metrics (win rate, Sharpe, max drawdown, etc.).
        """
        from .report.comparison import ComparisonReport as CR
        from .report.comparison import build_variant_result
        targets = [s for s in self._strategies if s.params] or self._strategies
        if not targets:
            return CR(results=[], asset=self.asset, timeframe=self.timeframe)
        results = [build_variant_result(v) for v in targets]
        for v in targets:
            v.run_count += 1
        return CR(
            results=sorted(results, key=lambda r: r.pnl, reverse=True),
            asset=self.asset,
            timeframe=self.timeframe,
        )

    def list_runs(self, directory: Optional[str] = None) -> list[dict]:
        from .report.comparison import list_runs as _list_runs
        return _list_runs(directory=directory)

    def load_run(self, timestamp: str, directory: Optional[str] = None) -> ComparisonReport:
        from .report.comparison import load_run as _load_run
        return _load_run(timestamp=timestamp, directory=directory)
