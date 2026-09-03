"""bot_hub.binance — BinanceAccessor for external TA.

Fetches Binance klines once per candle (auto-refreshed on each tick).
"""

from __future__ import annotations

import logging
import time
from typing import Optional

try:
    import pandas as pd
except ImportError:
    pd = None  # type: ignore[assignment]

try:
    from ..analysis._native_ta import bbands as _bbands
    from ..analysis._native_ta import donchian as _donchian
    from ..analysis._native_ta import ema as _ema
    from ..analysis._native_ta import macd as _macd
    from ..analysis._native_ta import rsi as _rsi
    from ..analysis._native_ta import sma as _sma
except ImportError:
    _rsi = _sma = _ema = _macd = _bbands = _donchian = None

from .models import MACDResult

log = logging.getLogger(__name__)

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
            from ..calculations import MarketCalculations, VolumeCalculations
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
        from ..analysis import DataFeed, DataFeedConfig
        config = DataFeedConfig(source="binance", timeframe=self._timeframe, lookback_periods=100)
        self._feed = DataFeed(config)

    def _refresh(self) -> None:
        """Refresh Binance data once per candle."""
        if self._feed is None:
            self._lazy_init()
        now = time.time()
        from ..core.constants import TIMEFRAME_SECONDS
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
            from ..core.constants import TIMEFRAME_SECONDS
            time_interval = TIMEFRAME_SECONDS.get(self._timeframe, 300)
            if self._timeframe.lower() == "24h":
                time_interval = 86400
        close_data = self._data["close"].tolist()
        return self._market_calc.rate_of_change(close_data, period, time_interval)


