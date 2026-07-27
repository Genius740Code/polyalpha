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
    plus_dm[plus_dm <= minus_dm] = 0
    minus_dm[minus_dm <= plus_dm] = 0
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
        f"BBL_{length}_{std}_0": lower,
        f"BBM_{length}_{std}_0": middle,
        f"BBU_{length}_{std}_0": upper,
    })
    return result


def atr(high: pd.Series, low: pd.Series, close: pd.Series, length: int = 14) -> pd.Series:
    tr = pd.concat([high - low, (high - close.shift()).abs(), (low - close.shift()).abs()], axis=1).max(axis=1)
    return tr.rolling(window=length).mean()


def supertrend(high: pd.Series, low: pd.Series, close: pd.Series, length: int = 7, multiplier: float = 3.0) -> pd.DataFrame:
    atr_series = atr(high, low, close, length)
    hl2 = (high + low) / 2
    upper_band = hl2 + multiplier * atr_series
    lower_band = hl2 - multiplier * atr_series

    trend = pd.Series(np.nan, index=close.index)
    direction = pd.Series(1, index=close.index)

    for i in range(1, len(close)):
        if close.iloc[i] > upper_band.iloc[i - 1]:
            direction.iloc[i] = 1
        elif close.iloc[i] < lower_band.iloc[i - 1]:
            direction.iloc[i] = -1
        else:
            direction.iloc[i] = direction.iloc[i - 1]
            if direction.iloc[i] == 1 and lower_band.iloc[i] < lower_band.iloc[i - 1]:
                lower_band.iloc[i] = lower_band.iloc[i - 1]
            if direction.iloc[i] == -1 and upper_band.iloc[i] > upper_band.iloc[i - 1]:
                upper_band.iloc[i] = upper_band.iloc[i - 1]

        trend.iloc[i] = lower_band.iloc[i] if direction.iloc[i] == 1 else upper_band.iloc[i]

    result = pd.DataFrame({
        f"SUPERT_{length}_{multiplier}": trend,
        f"SUPERTd_{length}_{multiplier}": direction,
    })
    return result


def obv(close: pd.Series, volume: pd.Series) -> pd.Series:
    direction = np.sign(close.diff())
    direction[0] = 0
    return (direction * volume).cumsum()


def roc(series: pd.Series, length: int = 12) -> pd.Series:
    return series.pct_change(periods=length) * 100


def vwap(close: pd.Series, volume: pd.Series = None) -> pd.Series:
    """Volume Weighted Average Price.

    Requires volume data. Returns None-filled series when volume is absent.
    """
    if volume is None:
        return pd.Series([None] * len(close), index=close.index)

    tp = close
    cum_volume_price = (tp * volume).cumsum()
    cum_volume = volume.cumsum()
    return cum_volume_price / cum_volume


def psar(high: pd.Series, low: pd.Series, close: pd.Series, af: float = 0.02, af_max: float = 0.2) -> pd.DataFrame:
    """Parabolic SAR indicator.

    Returns a DataFrame with columns matching pandas_ta naming convention.
    """
    length = len(close)
    psar_vals = pd.Series(np.nan, index=close.index)
    af_vals = pd.Series(0.0, index=close.index)
    trend = pd.Series(1, index=close.index)  # 1 = uptrend, -1 = downtrend
    ep = pd.Series(0.0, index=close.index)  # extreme point

    if length < 2:
        result = pd.DataFrame({
            "PSARl_0.02_0.2": psar_vals,
            "PSARs_0.02_0.2": psar_vals,
        })
        return result

    psar_vals.iloc[0] = low.iloc[0]
    ep.iloc[0] = high.iloc[0]
    af_vals.iloc[0] = af

    for i in range(1, length):
        if trend.iloc[i - 1] == 1:
            psar_vals.iloc[i] = psar_vals.iloc[i - 1] + af_vals.iloc[i - 1] * (ep.iloc[i - 1] - psar_vals.iloc[i - 1])
            psar_vals.iloc[i] = min(psar_vals.iloc[i], low.iloc[i - 1], low.iloc[i - 2] if i >= 2 else low.iloc[i - 1])

            if high.iloc[i] > ep.iloc[i - 1]:
                ep.iloc[i] = high.iloc[i]
                af_vals.iloc[i] = min(af_vals.iloc[i - 1] + af, af_max)
            else:
                ep.iloc[i] = ep.iloc[i - 1]
                af_vals.iloc[i] = af_vals.iloc[i - 1]

            if low.iloc[i] < psar_vals.iloc[i]:
                trend.iloc[i] = -1
                psar_vals.iloc[i] = ep.iloc[i - 1]
                ep.iloc[i] = low.iloc[i]
                af_vals.iloc[i] = af
            else:
                trend.iloc[i] = 1
        else:
            psar_vals.iloc[i] = psar_vals.iloc[i - 1] + af_vals.iloc[i - 1] * (ep.iloc[i - 1] - psar_vals.iloc[i - 1])
            psar_vals.iloc[i] = max(psar_vals.iloc[i], high.iloc[i - 1], high.iloc[i - 2] if i >= 2 else high.iloc[i - 1])

            if low.iloc[i] < ep.iloc[i - 1]:
                ep.iloc[i] = low.iloc[i]
                af_vals.iloc[i] = min(af_vals.iloc[i - 1] + af, af_max)
            else:
                ep.iloc[i] = ep.iloc[i - 1]
                af_vals.iloc[i] = af_vals.iloc[i - 1]

            if high.iloc[i] > psar_vals.iloc[i]:
                trend.iloc[i] = 1
                psar_vals.iloc[i] = ep.iloc[i - 1]
                ep.iloc[i] = high.iloc[i]
                af_vals.iloc[i] = af
            else:
                trend.iloc[i] = -1

    long_col = f"PSARl_{af}_{af_max}"
    short_col = f"PSARs_{af}_{af_max}"
    result = pd.DataFrame({
        long_col: psar_vals.where(trend == 1, np.nan),
        short_col: psar_vals.where(trend == -1, np.nan),
    })
    return result


def ichimoku(high: pd.Series, low: pd.Series, close: pd.Series, tenkan: int = 9, kijun: int = 26, senkou: int = 52) -> tuple[pd.DataFrame, pd.DataFrame]:
    """Ichimoku Kinko Hyo indicator.

    Returns (ichimoku_df, span_df) matching pandas_ta convention.
    """
    # Tenkan-sen (Conversion Line): (highest high + lowest low) / 2 over past 9 periods
    tenkan_sen = (high.rolling(window=tenkan).max() + low.rolling(window=tenkan).min()) / 2

    # Kijun-sen (Base Line): (highest high + lowest low) / 2 over past 26 periods
    kijun_sen = (high.rolling(window=kijun).max() + low.rolling(window=kijun).min()) / 2

    # Senkou Span A (Leading Span A): (tenkan + kijun) / 2, shifted forward 26 periods
    senkou_span_a = ((tenkan_sen + kijun_sen) / 2).shift(kijun)

    # Senkou Span B (Leading Span B): (highest high + lowest low) / 2 over past 52 periods, shifted forward 26
    senkou_span_b = ((high.rolling(window=senkou).max() + low.rolling(window=senkou).min()) / 2).shift(kijun)

    # Chikou Span (Lagging Span): close shifted backward 26 periods
    chikou_span = close.shift(-kijun)

    ichimoku_df = pd.DataFrame({
        f"ITS_{tenkan}": tenkan_sen.rename(f"ITS_{tenkan}"),
        f"IKS_{kijun}": kijun_sen.rename(f"IKS_{kijun}"),
        f"ICS_{kijun}": chikou_span.rename(f"ICS_{kijun}"),
    })

    span_df = pd.DataFrame({
        f"ISA_{kijun}": senkou_span_a.rename(f"ISA_{kijun}"),
        f"ISB_{kijun}": senkou_span_b.rename(f"ISB_{kijun}"),
    })

    return ichimoku_df, span_df


def donchian(high: pd.Series, low: pd.Series, length: int = 20) -> pd.DataFrame:
    """Donchian Channels.

    Returns a DataFrame with upper, middle, lower channel lines.
    """
    upper = high.rolling(window=length).max()
    lower = low.rolling(window=length).min()
    middle = (upper + lower) / 2

    result = pd.DataFrame({
        f"DCL_{length}": lower.rename(f"DCL_{length}"),
        f"DCM_{length}": middle.rename(f"DCM_{length}"),
        f"DCU_{length}": upper.rename(f"DCU_{length}"),
    })
    return result
