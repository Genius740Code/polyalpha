"""bot_hub.indicators — IndicatorAccessor and TA helpers.

First-class indicator access via ``ctx.indicators.rsi(14)``, etc.
Wraps the shared price history deque and caches computed results
within a single tick.
"""

from __future__ import annotations

import logging
from typing import Optional, Union

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
    from ..analysis._native_ta import roc as _roc
    from ..analysis._native_ta import sma as _sma
    from ..analysis._native_ta import vwap as _vwap

    _NATIVE_TA_AVAILABLE = True
except ImportError:
    _rsi = _sma = _ema = _macd = _bbands = _roc = _vwap = _donchian = None
    _NATIVE_TA_AVAILABLE = False

from .models import BBResult, DonchianResult, MACDResult

log = logging.getLogger(__name__)


def _log_indicators() -> None:
    """Log which TA indicators are available (called once at BotHub init)."""
    if not _NATIVE_TA_AVAILABLE:
        log.info("TA indicators: none available (install pandas-ta or numpy)")
        return
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
    log.info("TA indicators available: %s", ", ".join(names))


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
