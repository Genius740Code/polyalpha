"""Native pandas/numpy implementations of technical indicators.

Provides drop-in replacements for pandas-ta functions using only
pandas and numpy. Used when pandas-ta is not installed.
"""

import numpy as np
import pandas as pd


def sma(series: pd.Series, length: int = 20) -> pd.Series:
    return series.rolling(window=length).mean()


def ema(series: pd.Series, length: int = 20) -> pd.Series:
    return series.ewm(span=length, adjust=False).mean()


def rsi(series: pd.Series, length: int = 14) -> pd.Series:
    delta = series.diff()
    gain = delta.clip(lower=0)
    loss = -delta.clip(upper=0)
    avg_gain = gain.ewm(alpha=1.0 / length, min_periods=length).mean()
    avg_loss = loss.ewm(alpha=1.0 / length, min_periods=length).mean()
    rs = avg_gain / avg_loss.replace(0, np.nan)
    rsi_series = 100 - (100 / (1 + rs))
    return rsi_series


def macd(series: pd.Series, fast: int = 12, slow: int = 26, signal: int = 9) -> pd.DataFrame:
    ema_fast = ema(series, fast)
    ema_slow = ema(series, slow)
    macd_line = ema_fast - ema_slow
    signal_line = ema(macd_line, signal)
    histogram = macd_line - signal_line
    result = pd.DataFrame({
        f"MACD_{fast}_{slow}_{signal}": macd_line,
        f"MACDs_{fast}_{slow}_{signal}": signal_line,
        f"MACDh_{fast}_{slow}_{signal}": histogram,
    })
    return result


def adx(high: pd.Series, low: pd.Series, close: pd.Series, length: int = 14) -> pd.DataFrame:
    plus_dm = high.diff().clip(lower=0)
    minus_dm = -low.diff().clip(upper=0)
    plus_dm[plus_dm < minus_dm] = 0
    minus_dm[minus_dm < plus_dm] = 0
    tr = pd.concat([high - low, (high - close.shift()).abs(), (low - close.shift()).abs()], axis=1).max(axis=1)
    atr_series = tr.rolling(window=length).mean()
    plus_di = 100 * plus_dm.rolling(window=length).mean() / atr_series.replace(0, np.nan)
    minus_di = 100 * minus_dm.rolling(window=length).mean() / atr_series.replace(0, np.nan)
    dx = 100 * (plus_di - minus_di).abs() / (plus_di + minus_di).replace(0, np.nan)
    adx_series = dx.rolling(window=length).mean()
    result = pd.DataFrame({
        f"ADX_{length}": adx_series,
        f"DMP_{length}": plus_di,
        f"DMN_{length}": minus_di,
    })
    return result


def stoch(high: pd.Series, low: pd.Series, close: pd.Series, k: int = 14, d: int = 3, smooth_k: int = 3) -> pd.DataFrame:
    low_min = low.rolling(window=k).min()
    high_max = high.rolling(window=k).max()
    k_raw = 100 * (close - low_min) / (high_max - low_min).replace(0, np.nan)
    k_smooth = k_raw.rolling(window=smooth_k).mean()
    d_series = k_smooth.rolling(window=d).mean()
    result = pd.DataFrame({
        f"STOCHk_{k}_{d}_{smooth_k}": k_smooth,
        f"STOCHd_{k}_{d}_{smooth_k}": d_series,
    })
    return result


def willr(high: pd.Series, low: pd.Series, close: pd.Series, length: int = 14) -> pd.Series:
    highest_high = high.rolling(window=length).max()
    lowest_low = low.rolling(window=length).min()
    result = -100 * (highest_high - close) / (highest_high - lowest_low).replace(0, np.nan)
    return result


def cci(high: pd.Series, low: pd.Series, close: pd.Series, length: int = 20) -> pd.Series:
    tp = (high + low + close) / 3
    sma_tp = tp.rolling(window=length).mean()
    mad = tp.rolling(window=length).apply(lambda x: np.abs(x - x.mean()).mean(), raw=True)
    result = (tp - sma_tp) / (0.015 * mad.replace(0, np.nan))
    return result


def bbands(series: pd.Series, length: int = 20, std: float = 2.0) -> pd.DataFrame:
    middle = series.rolling(window=length).mean()
    std_dev = series.rolling(window=length).std()
    upper = middle + std * std_dev
    lower = middle - std * std_dev
    result = pd.DataFrame({
        f"BBL_{length}_{std}_{std}": lower,
        f"BBM_{length}_{std}_{std}": middle,
        f"BBU_{length}_{std}_{std}": upper,
    })
    return result


def atr(high: pd.Series, low: pd.Series, close: pd.Series, length: int = 14) -> pd.Series:
    tr = pd.concat([high - low, (high - close.shift()).abs(), (low - close.shift()).abs()], axis=1).max(axis=1)
    return tr.rolling(window=length).mean()


def obv(close: pd.Series, volume: pd.Series) -> pd.Series:
    direction = np.sign(close.diff())
    direction[0] = 0
    return (direction * volume).cumsum()


def roc(series: pd.Series, length: int = 12) -> pd.Series:
    return series.pct_change(periods=length) * 100
