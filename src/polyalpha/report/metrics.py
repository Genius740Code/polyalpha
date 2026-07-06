"""
metrics.py — Pure metric computation from a list[TradeRecord].

All functions are stateless and side-effect-free.  They can be unit-tested
independently without any PaperEngine state.

Mathematical conventions
------------------------
* Annualisation: we use sqrt(N_trades_per_year) where
  N_trades_per_year = len(trades) / (total_calendar_days / 365.25).
  This is appropriate for short-horizon binary markets (5m–24h).
* Returns: pnl / amount_in per trade (gross return on capital deployed).
* Downside deviation: uses MAR = 0 (minimum acceptable return).
* All ratio denominators are guarded against zero — return float('nan') if
  not computable.  Callers should check math.isnan() before displaying.

References
----------
* Sharpe (1966): E[R] / σ(R) × √N
* Sortino (1991): E[R] / σ_d(R) × √N  where σ_d uses only negative returns
* Calmar (1991): CAGR / |max_drawdown_pct|
* Omega (Keating 2002): ∫ max(R-T,0) / ∫ max(T-R,0)  with T=0
* Kelly: p - (1-p)/b  where b = avg_win_pct / avg_loss_pct
* VaR (parametric-free): empirical quantile of return distribution
* CVaR: mean of returns below VaR threshold
* Deflated Sharpe (Bailey & López de Prado 2014): adjusts for multiple testing
"""

from __future__ import annotations

import math
import statistics
from collections import defaultdict
from datetime import datetime, timedelta, timezone
from typing import Any, Optional

from .records import TradeRecord

# ── Type alias ────────────────────────────────────────────────────────────────

MetricsDict = dict[str, Any]

# ── Top-level entry point ─────────────────────────────────────────────────────

def compute_metrics(
    trades: list[TradeRecord],
    initial_balance: float,
    metric_keys: list[str],
    risk_free_rate: float = 0.0,
) -> MetricsDict:
    """
    Compute all requested metrics from a list of resolved trades.

    Parameters
    ----------
    trades : list[TradeRecord]
        All resolved trades, sorted chronologically.
    initial_balance : float
        Starting capital.
    metric_keys : list[str]
        Keys from presets.ALL_METRICS to compute.
    risk_free_rate : float
        Annual risk-free rate (default 0.0).

    Returns
    -------
    dict mapping metric_key → value (float | str | None)
    """
    result: MetricsDict = {}

    if not trades:
        return {k: None for k in metric_keys}

    # Pre-compute shared arrays (avoids repeated passes)
    returns      = [t.pnl_pct / 100.0 for t in trades]  # fractional returns
    pnls         = [t.pnl             for t in trades]
    amounts      = [t.amount_in       for t in trades]
    holding_secs = [t.holding_secs    for t in trades]
    wins         = [t for t in trades if t.pnl > 0]
    losses       = [t for t in trades if t.pnl < 0]
    n            = len(trades)

    equity_curve = _build_equity_array(trades, initial_balance)
    ann_factor   = _annualisation_factor(trades)

    # ── Dispatch each key ─────────────────────────────────────────────────────
    for key in metric_keys:
        if key == "net_pnl":
            total = sum(pnls)
            result[key] = {
                "usd": round(total, 4),
                "pct": round((total / initial_balance) * 100, 4) if initial_balance else float("nan"),
            }

        elif key == "win_rate":
            result[key] = round(len(wins) / n, 6) if n else float("nan")

        elif key == "total_trades":
            result[key] = n

        elif key == "sharpe":
            result[key] = _sharpe(returns, ann_factor, risk_free_rate)

        elif key == "sortino":
            result[key] = _sortino(returns, ann_factor, risk_free_rate)

        elif key == "max_drawdown":
            dd_pct, dd_usd = _max_drawdown(equity_curve)
            result[key] = {"pct": dd_pct, "usd": dd_usd}

        elif key == "profit_factor":
            result[key] = _profit_factor(pnls)

        elif key == "avg_win_loss":
            result[key] = {
                "avg_win":  round(statistics.mean(t.pnl for t in wins),   4) if wins   else float("nan"),
                "avg_loss": round(statistics.mean(t.pnl for t in losses), 4) if losses else float("nan"),
            }

        elif key == "expectancy":
            result[key] = _expectancy(returns, wins, losses, n)

        elif key == "median_holding":
            result[key] = round(statistics.median(holding_secs), 2) if holding_secs else float("nan")

        elif key == "best_trade":
            best = max(trades, key=lambda t: t.pnl)
            result[key] = {"pnl": round(best.pnl, 4), "pct": round(best.pnl_pct, 2), "market": best.market_slug}

        elif key == "worst_trade":
            worst = min(trades, key=lambda t: t.pnl)
            result[key] = {"pnl": round(worst.pnl, 4), "pct": round(worst.pnl_pct, 2), "market": worst.market_slug}

        elif key == "mean_holding":
            result[key] = round(statistics.mean(holding_secs), 2) if holding_secs else float("nan")

        elif key == "calmar":
            result[key] = _calmar(trades, initial_balance, equity_curve)

        elif key == "omega":
            result[key] = _omega(returns)

        elif key == "skew":
            result[key] = round(statistics.mean(
                ((r - statistics.mean(returns)) / _std(returns)) ** 3
                for r in returns
            ), 4) if len(returns) >= 3 and _std(returns) > 0 else float("nan")

        elif key == "kurtosis":
            result[key] = _kurtosis(returns)

        elif key == "var_95":
            result[key] = _var(returns, 0.05)

        elif key == "var_99":
            result[key] = _var(returns, 0.01)

        elif key == "cvar_95":
            result[key] = _cvar(returns, 0.05)

        elif key == "cvar_99":
            result[key] = _cvar(returns, 0.01)

        elif key == "max_consec_wins":
            result[key] = _max_consecutive(trades, win=True)

        elif key == "max_consec_losses":
            result[key] = _max_consecutive(trades, win=False)

        elif key == "kelly":
            result[key] = _kelly(wins, losses, n)

        elif key == "rolling_sharpe_30d":
            result[key] = _rolling_sharpe_latest(trades, returns, window_days=30, ann_factor=ann_factor, rfr=risk_free_rate)

        elif key == "rolling_sharpe_90d":
            result[key] = _rolling_sharpe_latest(trades, returns, window_days=90, ann_factor=ann_factor, rfr=risk_free_rate)

        elif key == "fill_rate":
            result[key] = _fill_rate(trades)

        elif key == "avg_slippage":
            result[key] = round(statistics.mean(t.slippage for t in trades), 6) if trades else float("nan")

        elif key == "pnl_concentration":
            result[key] = _pnl_concentration(pnls, n=10)

        elif key == "deflated_sharpe":
            result[key] = _deflated_sharpe(returns, ann_factor)

        elif key == "avg_position_size":
            result[key] = round(statistics.mean(amounts), 4) if amounts else float("nan")

        elif key == "turnover":
            # Turnover = total capital deployed / initial_balance
            result[key] = round(sum(amounts) / initial_balance, 4) if initial_balance else float("nan")

        else:
            result[key] = None

    return result


# ── Rolling metrics (for charts) ──────────────────────────────────────────────

def compute_rolling_sharpe(
    trades: list[TradeRecord],
    window_days: int = 30,
    risk_free_rate: float = 0.0,
) -> tuple[list[datetime], list[float]]:
    """
    Compute rolling Sharpe ratio over a sliding calendar window.

    Returns parallel (timestamps, sharpe_values) lists.
    """
    if len(trades) < 2:
        return [], []

    returns = [t.pnl_pct / 100.0 for t in trades]
    timestamps: list[datetime] = []
    sharpe_values: list[float] = []

    window = timedelta(days=window_days)
    ann_factor = _annualisation_factor(trades)

    for i in range(1, len(trades)):
        ts = trades[i].exit_time
        # Collect trades within the window ending at ts
        window_returns = [
            returns[j]
            for j in range(i + 1)
            if (ts - trades[j].exit_time) <= window
        ]
        if len(window_returns) >= 2:
            s = _sharpe(window_returns, ann_factor, risk_free_rate)
            if not math.isnan(s):
                timestamps.append(ts)
                sharpe_values.append(round(s, 4))

    return timestamps, sharpe_values


def compute_underwater_curve(
    trades: list[TradeRecord],
    initial_balance: float,
) -> tuple[list[datetime], list[float]]:
    """
    Compute the drawdown-from-peak percentage at each trade exit.

    Returns parallel (timestamps, drawdown_pct) where drawdown_pct <= 0.
    """
    if not trades:
        return [], []

    equity = _build_equity_array(trades, initial_balance)
    peak = initial_balance
    timestamps: list[datetime] = []
    dd_values: list[float] = []

    # Align with exit times (skip origin which has no matching trade)
    for i, trade in enumerate(trades):
        eq = equity[i + 1]  # equity[0] is the origin, equity[i+1] follows trade i
        peak = max(peak, eq)
        dd_pct = ((eq - peak) / peak * 100) if peak > 0 else 0.0
        timestamps.append(trade.exit_time)
        dd_values.append(round(dd_pct, 4))

    return timestamps, dd_values


def compute_pnl_by_hour(
    trades: list[TradeRecord],
) -> dict[int, float]:
    """Hour-of-day (0-23 UTC) → total PnL."""
    hourly: dict[int, float] = defaultdict(float)
    for t in trades:
        hour = t.entry_time.hour
        hourly[hour] = round(hourly[hour] + t.pnl, 6)
    return dict(hourly)


def compute_pnl_by_weekday(
    trades: list[TradeRecord],
) -> dict[int, float]:
    """Day-of-week (0=Mon, 6=Sun) → total PnL."""
    daily: dict[int, float] = defaultdict(float)
    for t in trades:
        dow = t.entry_time.weekday()
        daily[dow] = round(daily[dow] + t.pnl, 6)
    return dict(daily)


def compute_monthly_returns(
    trades: list[TradeRecord],
    initial_balance: float,
) -> dict[str, float]:
    """
    YYYY-MM → monthly return percentage.

    Builds monthly buckets from the equity curve and computes
    (end_equity - start_equity) / start_equity * 100.
    """
    if not trades:
        return {}

    # Group PnL by (year, month)
    monthly_pnl: dict[tuple[int, int], float] = defaultdict(float)
    monthly_invested: dict[tuple[int, int], float] = defaultdict(float)

    for t in trades:
        key = (t.exit_time.year, t.exit_time.month)
        monthly_pnl[key]      = round(monthly_pnl[key] + t.pnl, 6)
        monthly_invested[key] = round(monthly_invested[key] + t.amount_in, 6)

    result: dict[str, float] = {}
    for (y, m), pnl in sorted(monthly_pnl.items()):
        invested = monthly_invested[(y, m)]
        ret_pct  = round((pnl / invested) * 100, 4) if invested > 0 else 0.0
        result[f"{y:04d}-{m:02d}"] = ret_pct

    return result


def compute_entry_calibration(
    trades: list[TradeRecord],
    n_buckets: int = 10,
) -> dict[float, float]:
    """
    Entry price calibration: bin trades by entry_price → empirical win rate.

    Returns {bucket_midpoint: actual_win_rate}.
    A well-calibrated strategy buying at 0.90 should win ~90% of the time.
    """
    if not trades:
        return {}

    bucket_width = 1.0 / n_buckets
    # key = lower bound of bucket
    wins_in_bucket: dict[float, int] = defaultdict(int)
    count_in_bucket: dict[float, int] = defaultdict(int)

    for t in trades:
        bucket = math.floor(t.entry_price / bucket_width) * bucket_width
        bucket = round(bucket, 6)
        count_in_bucket[bucket] += 1
        if t.pnl > 0:
            wins_in_bucket[bucket] += 1

    result: dict[float, float] = {}
    for bucket, count in sorted(count_in_bucket.items()):
        midpoint = round(bucket + bucket_width / 2, 4)
        win_rate = round(wins_in_bucket[bucket] / count, 4)
        result[midpoint] = win_rate

    return result


# ── Private metric implementations ────────────────────────────────────────────

def _annualisation_factor(trades: list[TradeRecord]) -> float:
    """
    Estimate sqrt(trades_per_year) for Sharpe/Sortino annualisation.

    Uses calendar time elapsed. Falls back to sqrt(252) if < 2 trades.
    """
    if len(trades) < 2:
        return math.sqrt(252)

    first = trades[0].entry_time
    last  = trades[-1].exit_time
    calendar_days = (last - first).total_seconds() / 86_400.0

    if calendar_days < 1.0:
        # All trades within one day — use a single-day proxy
        trades_per_year = len(trades) * 365.25
    else:
        trades_per_year = len(trades) / calendar_days * 365.25

    return math.sqrt(max(trades_per_year, 1.0))


def _build_equity_array(
    trades: list[TradeRecord],
    initial_balance: float,
) -> list[float]:
    """
    Build a list of equity values with length len(trades)+1.
    equity[0] = initial_balance, equity[i+1] = equity[i] + trades[i].pnl
    """
    equity = [initial_balance]
    running = initial_balance
    for t in trades:
        running = running + t.pnl
        equity.append(running)
    return equity


def _std(values: list[float]) -> float:
    """Sample standard deviation, returns 0 if < 2 values."""
    if len(values) < 2:
        return 0.0
    return statistics.stdev(values)


def _sharpe(
    returns: list[float],
    ann_factor: float,
    risk_free_rate: float = 0.0,
) -> float:
    """Annualised Sharpe ratio."""
    if len(returns) < 2:
        return float("nan")
    mean_r = statistics.mean(returns)
    std_r  = _std(returns)
    if std_r == 0:
        return float("nan")
    # Adjust for per-trade risk-free rate
    per_trade_rfr = risk_free_rate / ann_factor ** 2  # rfr / trades_per_year
    return round((mean_r - per_trade_rfr) / std_r * ann_factor, 4)


def _sortino(
    returns: list[float],
    ann_factor: float,
    risk_free_rate: float = 0.0,
) -> float:
    """Annualised Sortino ratio using downside deviation (MAR=0)."""
    if len(returns) < 2:
        return float("nan")
    mean_r = statistics.mean(returns)
    per_trade_rfr = risk_free_rate / ann_factor ** 2

    negative = [r for r in returns if r < 0.0]
    if len(negative) < 2:
        # No (or one) losing trades — Sortino is infinite (or undefined)
        return float("inf") if mean_r > per_trade_rfr else float("nan")

    # Downside deviation: sqrt(mean of squared negative deviations from MAR=0)
    downside_sq = statistics.mean(r ** 2 for r in negative)
    downside_dev = math.sqrt(downside_sq)

    if downside_dev == 0:
        return float("nan")

    return round((mean_r - per_trade_rfr) / downside_dev * ann_factor, 4)


def _max_drawdown(equity: list[float]) -> tuple[float, float]:
    """
    Compute maximum drawdown.

    Returns
    -------
    (dd_pct, dd_usd)  — both are negative or zero.
    """
    if len(equity) < 2:
        return 0.0, 0.0

    peak = equity[0]
    max_dd_pct = 0.0
    max_dd_usd = 0.0

    for val in equity[1:]:
        if val > peak:
            peak = val
        if peak > 0:
            dd_pct = (val - peak) / peak * 100
            dd_usd = val - peak
            if dd_pct < max_dd_pct:
                max_dd_pct = dd_pct
                max_dd_usd = dd_usd

    return round(max_dd_pct, 4), round(max_dd_usd, 4)


def _profit_factor(pnls: list[float]) -> float:
    """
    Profit factor = gross_profit / |gross_loss|.

    Returns float('inf') if no losing trades, float('nan') if no trades.
    """
    gross_profit = sum(p for p in pnls if p > 0)
    gross_loss   = abs(sum(p for p in pnls if p < 0))

    if gross_loss == 0:
        return float("inf") if gross_profit > 0 else float("nan")

    return round(gross_profit / gross_loss, 4)


def _expectancy(
    returns: list[float],
    wins: list[TradeRecord],
    losses: list[TradeRecord],
    n: int,
) -> float:
    """
    Expectancy per trade in return-space.

    E = P_win × avg_win_return + P_loss × avg_loss_return
    """
    if n == 0:
        return float("nan")

    p_win  = len(wins)  / n
    p_loss = len(losses) / n

    avg_win_r  = statistics.mean(t.pnl_pct / 100 for t in wins)   if wins   else 0.0
    avg_loss_r = statistics.mean(t.pnl_pct / 100 for t in losses) if losses else 0.0

    return round(p_win * avg_win_r + p_loss * avg_loss_r, 6)


def _calmar(
    trades: list[TradeRecord],
    initial_balance: float,
    equity: list[float],
) -> float:
    """
    Calmar ratio = CAGR / |max_drawdown_pct|.
    """
    if len(trades) < 2:
        return float("nan")

    first = trades[0].entry_time
    last  = trades[-1].exit_time
    years = (last - first).total_seconds() / (365.25 * 86_400)

    if years <= 0 or initial_balance <= 0:
        return float("nan")

    final = equity[-1]
    cagr  = (final / initial_balance) ** (1 / years) - 1

    _, dd_pct = _max_drawdown(equity)
    dd_pct = abs(dd_pct)

    if dd_pct == 0:
        return float("inf") if cagr > 0 else float("nan")

    return round(cagr / (dd_pct / 100), 4)


def _omega(returns: list[float], threshold: float = 0.0) -> float:
    """
    Omega ratio = ∑max(r-T,0) / ∑max(T-r,0).

    threshold (T) defaults to 0.
    """
    gain = sum(max(r - threshold, 0) for r in returns)
    loss = sum(max(threshold - r, 0) for r in returns)

    if loss == 0:
        return float("inf") if gain > 0 else float("nan")

    return round(gain / loss, 4)


def _kurtosis(returns: list[float]) -> float:
    """
    Excess kurtosis (Fisher definition, kurtosis - 3).

    Uses the sample formula with bias correction (n*(n+1) / ((n-1)*(n-2)*(n-3))).
    """
    n = len(returns)
    if n < 4:
        return float("nan")

    mean_r = statistics.mean(returns)
    std_r  = _std(returns)
    if std_r == 0:
        return float("nan")

    m4 = sum((r - mean_r) ** 4 for r in returns) / n
    # Population excess kurtosis
    kurt = m4 / std_r ** 4 - 3.0
    # Sample bias correction (Fisher's kurtosis)
    correction = ((n - 1) / ((n - 2) * (n - 3))) * ((n + 1) * kurt + 6)
    return round(correction, 4)


def _var(returns: list[float], alpha: float) -> float:
    """
    Historical VaR at confidence level (1-alpha).

    alpha=0.05 → 95% VaR (the 5th percentile of the return distribution).
    Returns as a positive loss figure (absolute value of the percentile).
    """
    if not returns:
        return float("nan")
    sorted_r = sorted(returns)
    idx = max(0, int(math.ceil(alpha * len(sorted_r))) - 1)
    return round(abs(sorted_r[idx]), 6)


def _cvar(returns: list[float], alpha: float) -> float:
    """
    Historical CVaR (Expected Shortfall) at confidence level (1-alpha).

    Mean of returns that are at or below the VaR threshold.
    Returned as a positive loss figure.
    """
    if not returns:
        return float("nan")
    sorted_r = sorted(returns)
    cutoff_idx = max(1, int(math.ceil(alpha * len(sorted_r))))
    tail = sorted_r[:cutoff_idx]
    if not tail:
        return float("nan")
    return round(abs(statistics.mean(tail)), 6)


def _max_consecutive(trades: list[TradeRecord], win: bool) -> int:
    """Max consecutive wins (win=True) or losses (win=False)."""
    max_streak = 0
    streak = 0
    for t in trades:
        is_match = t.pnl > 0 if win else t.pnl < 0
        if is_match:
            streak += 1
            max_streak = max(max_streak, streak)
        else:
            streak = 0
    return max_streak


def _kelly(
    wins: list[TradeRecord],
    losses: list[TradeRecord],
    n: int,
) -> float:
    """
    Realized Kelly fraction.

    f* = p - (1-p)/b
    where p  = win rate
          b  = avg_win_pct / avg_loss_pct  (both expressed as positive fractions)

    Clamps to [-1, 1].
    """
    if n == 0 or not wins or not losses:
        return float("nan")

    p = len(wins) / n
    avg_win_r  = abs(statistics.mean(t.pnl_pct / 100 for t in wins))
    avg_loss_r = abs(statistics.mean(t.pnl_pct / 100 for t in losses))

    if avg_loss_r == 0:
        return float("nan")

    b = avg_win_r / avg_loss_r
    if b == 0:
        return float("nan")

    kelly = p - (1 - p) / b
    return round(max(-1.0, min(1.0, kelly)), 4)


def _rolling_sharpe_latest(
    trades: list[TradeRecord],
    returns: list[float],
    window_days: int,
    ann_factor: float,
    rfr: float,
) -> float:
    """
    Most recent rolling Sharpe over the last `window_days` calendar days.
    """
    if not trades:
        return float("nan")

    cutoff = trades[-1].exit_time - timedelta(days=window_days)
    window_returns = [
        returns[i] for i, t in enumerate(trades) if t.exit_time >= cutoff
    ]
    if len(window_returns) < 2:
        return float("nan")

    return _sharpe(window_returns, ann_factor, rfr)


def _fill_rate(trades: list[TradeRecord]) -> float:
    """
    Fraction of trades that used limit orders (vs market orders).
    """
    if not trades:
        return float("nan")
    limits = sum(1 for t in trades if t.fill_type in ("limit", "mixed"))
    return round(limits / len(trades), 4)


def _pnl_concentration(pnls: list[float], n: int = 10) -> float:
    """
    Fraction of total gross profit that comes from the top-N winning trades.
    """
    gross_profit = sum(p for p in pnls if p > 0)
    if gross_profit == 0:
        return float("nan")

    top_n = sorted((p for p in pnls if p > 0), reverse=True)[:n]
    return round(sum(top_n) / gross_profit, 4)


def _deflated_sharpe(returns: list[float], ann_factor: float) -> float:
    """
    Deflated Sharpe Ratio (Bailey & López de Prado, 2014).

    Adjusts Sharpe for the number of independent strategy trials by computing
    the probability that a positive Sharpe is due to chance.

    DSR = Φ( (SR̂ - SR*) × √(N-1) / √(1 - γ₃·SR̂ + ((γ₄-1)/4)·SR̂²) )

    where:
      SR̂  = estimated Sharpe (non-annualised, per-observation)
      SR*  = maximum expected Sharpe under H₀ (≈ 0 for single strategy)
      γ₃   = skewness
      γ₄   = kurtosis
      N    = number of observations
      Φ    = CDF of standard normal

    We return the probability (0–1). Values > 0.95 suggest a statistically
    significant Sharpe after accounting for multiple-comparison bias.
    """
    n = len(returns)
    if n < 5:
        return float("nan")

    mean_r = statistics.mean(returns)
    std_r  = _std(returns)
    if std_r == 0:
        return float("nan")

    # Non-annualised Sharpe per observation
    sr_hat = mean_r / std_r

    # Skewness and kurtosis
    skew = sum((r - mean_r) ** 3 for r in returns) / (n * std_r ** 3) if std_r > 0 else 0.0
    kurt = sum((r - mean_r) ** 4 for r in returns) / (n * std_r ** 4) if std_r > 0 else 3.0

    # Standard error of Sharpe (Mertens 2002)
    var_sr = (1 - skew * sr_hat + ((kurt - 1) / 4) * sr_hat ** 2) / (n - 1)
    if var_sr <= 0:
        return float("nan")

    se_sr = math.sqrt(var_sr)

    # Under H₀, SR* = 0 (single strategy, no benchmark selection)
    sr_star = 0.0
    z = (sr_hat - sr_star) / se_sr

    # CDF of standard normal (erf-based)
    prob = 0.5 * (1 + math.erf(z / math.sqrt(2)))
    return round(prob, 4)
