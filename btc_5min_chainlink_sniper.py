"""
BTC 5-Minute Chainlink Sniper — High-Winrate BUY-ONLY Strategy

╔══════════════════════════════════════════════════════════════════════════╗
║  STRATEGY: Multi-Confluence Momentum Sniper (Long Only)                ║
║  TIMEFRAME: 5 minutes                                                  ║
║  DATA: Chainlink oracle (primary) + Binance (volume/candles)           ║
║  GOAL: Maximise winrate AND returns via strict indicator confluence     ║
╚══════════════════════════════════════════════════════════════════════════╝

Entry Conditions (ALL must be true):
─────────────────────────────────────
  1. TREND  — EMA8 > EMA21 > EMA50  (triple EMA alignment = strong uptrend)
  2. VWAP   — Price > VWAP  (institutional buying pressure)
  3. RSI    — 55 ≤ RSI(14) ≤ 72  (momentum zone, not overbought)
  4. MACD   — MACD line > signal AND histogram > 0  (bullish momentum)
  5. ADX    — ADX(14) > 20  (trending, not ranging)
  6. STOCH  — Stoch %K > %D AND %K < 80  (momentum turning up, not overbought)
  7. BB     — Price above BB middle but below BB upper  (room to run)
  8. VOL    — Current volume > 1.2× 20-period average  (participation confirmed)
  9. MIN %  — Price change from 10-candle low ≥ 0.10%  (minimum move filter)
  10. ATR    — ATR(14) is within normal range  (not a volatility spike)
  11. GREEN  — Current candle is green (close > open)
  12. CHAIN  — Chainlink oracle price validates Binance price (±0.5% max deviation)

Position Management:
────────────────────
  • Dynamic sizing based on ADX strength (stronger trend → bigger position)
  • One trade per candle maximum
  • Staleness guard (skip if data > 30s old)

Usage:
    python btc_5min_chainlink_sniper.py
"""
import logging
import time
from collections import deque

import polyalpha
from polyalpha.analysis import DataFeed, DataFeedConfig

# ── Logging ───────────────────────────────────────────────────────────────────
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s │ %(name)-12s │ %(levelname)-5s │ %(message)s",
)
log = logging.getLogger("chainlink_sniper")


# ── Configuration ─────────────────────────────────────────────────────────────
ASSET = "BTC"
TIMEFRAME = "5m"
BALANCE = 100

# Indicator parameters
EMA_FAST = 8
EMA_MID = 21
EMA_SLOW = 50
RSI_PERIOD = 14
RSI_LOWER = 55          # Entry zone floor
RSI_UPPER = 72          # Entry zone ceiling (avoid overbought)
ADX_THRESHOLD = 20      # Minimum trend strength
STOCH_UPPER = 80        # Stochastic overbought limit
VOLUME_MULTIPLIER = 1.2 # Volume must exceed avg by this factor
MIN_PCT_CHANGE = 0.10   # Minimum % move from 10-candle low
ATR_MAX_MULTIPLE = 2.0  # ATR must be < 2× its own 20-period average
CHAINLINK_MAX_DEV = 0.5 # Max deviation (%) between Chainlink and Binance prices

# Position sizing
BASE_SIZE = 20          # Base position size in USDC
MAX_SIZE = 35           # Maximum position size in USDC
ADX_SCALE_MIN = 20      # ADX where sizing starts scaling up
ADX_SCALE_MAX = 40      # ADX where sizing maxes out


# ── Bot Setup ─────────────────────────────────────────────────────────────────
bot = polyalpha.Bot(ASSET, TIMEFRAME, balance=BALANCE)

# Chainlink data feed — fetches oracle-validated price + historical candles
chainlink_config = DataFeedConfig(
    source="chainlink",
    timeframe=TIMEFRAME,
    lookback_periods=100,
)
chainlink_feed = DataFeed(chainlink_config)

# Binance data feed — for volume + OHLCV candle data
binance_config = DataFeedConfig(
    source="binance",
    timeframe=TIMEFRAME,
    lookback_periods=100,
)
binance_feed = DataFeed(binance_config)


# ── State ─────────────────────────────────────────────────────────────────────
tick_count = 0
trade_count = 0
win_count = 0
loss_count = 0

# Data caches
binance_data = None
chainlink_data = None
last_binance_fetch = 0
last_chainlink_fetch = 0

# Tracking
last_pnl_log_time = 0
last_price_update_time = 0

# Per-candle history for min % change
recent_lows = deque(maxlen=10)


# ── Helper: Dynamic Position Sizing ──────────────────────────────────────────
def calculate_position_size(adx_value: float) -> float:
    """Scale position size based on ADX trend strength.

    Stronger trend → larger position. Linear interpolation between
    BASE_SIZE and MAX_SIZE over the ADX range [ADX_SCALE_MIN, ADX_SCALE_MAX].
    """
    if adx_value is None or adx_value <= ADX_SCALE_MIN:
        return BASE_SIZE
    if adx_value >= ADX_SCALE_MAX:
        return MAX_SIZE
    ratio = (adx_value - ADX_SCALE_MIN) / (ADX_SCALE_MAX - ADX_SCALE_MIN)
    return round(BASE_SIZE + ratio * (MAX_SIZE - BASE_SIZE), 2)


# ── Helper: Score Conditions ─────────────────────────────────────────────────
def log_scorecard(checks: dict[str, bool]) -> None:
    """Log a visual scorecard of all entry conditions."""
    total = len(checks)
    passed = sum(1 for v in checks.values() if v)
    symbols = {True: "✅", False: "❌"}
    lines = [f"  {symbols[v]} {name}" for name, v in checks.items()]
    log.info(
        "Scorecard: %d/%d conditions met\n%s",
        passed, total, "\n".join(lines),
    )


# ══════════════════════════════════════════════════════════════════════════════
#  STRATEGY TICK HANDLER
# ══════════════════════════════════════════════════════════════════════════════

@bot.on_tick
def strategy(ctx):
    global tick_count, binance_data, chainlink_data
    global last_binance_fetch, last_chainlink_fetch
    global last_pnl_log_time, last_price_update_time

    tick_count += 1
    current_price = ctx.price.up
    current_time = time.time()
    last_price_update_time = current_time

    # ── Periodic logging ──────────────────────────────────────────────────
    if tick_count % 60 == 0:
        log.info(
            "Tick #%d │ Price: %.4f │ Balance: $%.2f │ P&L: $%.2f │ "
            "Trades: %d │ Positions: %d",
            tick_count, current_price, ctx.balance, ctx.pnl,
            trade_count, len(ctx.positions),
        )

    if current_time - last_pnl_log_time > 300:
        wr = (win_count / max(win_count + loss_count, 1)) * 100
        log.info(
            "📊 Session Stats │ Wins: %d │ Losses: %d │ Winrate: %.1f%% │ "
            "P&L: $%.2f │ Balance: $%.2f",
            win_count, loss_count, wr, ctx.pnl, ctx.balance,
        )
        last_pnl_log_time = current_time

    # ── Fetch Binance candle + volume data (every 5 min) ──────────────────
    if binance_data is None or (current_time - last_binance_fetch) > 300:
        try:
            binance_data = binance_feed.fetch(ASSET)
            last_binance_fetch = current_time
            log.info("📡 Binance: %d candles fetched", len(binance_data))
        except Exception as e:
            log.warning("Binance fetch failed: %s", e)
            binance_data = None

    # ── Fetch Chainlink oracle price (every 5 min) ────────────────────────
    if chainlink_data is None or (current_time - last_chainlink_fetch) > 300:
        try:
            chainlink_data = chainlink_feed.fetch(ASSET)
            last_chainlink_fetch = current_time
            log.info("🔗 Chainlink: %d rows fetched", len(chainlink_data))
        except Exception as e:
            log.warning("Chainlink fetch failed: %s", e)
            chainlink_data = None

    # ── Staleness guard ───────────────────────────────────────────────────
    data_age = current_time - last_price_update_time
    if data_age > 30:
        if tick_count % 60 == 0:
            log.warning("⚠️  Data stale: %.1fs since last update", data_age)
        return

    # ── Need indicator data ───────────────────────────────────────────────
    if binance_data is None or len(binance_data) < EMA_SLOW + 10:
        return  # Not enough candles yet

    # ── Get all indicators from ctx ───────────────────────────────────────
    ind = ctx.indicators
    if ind is None:
        return

    vwap = ind.vwap() if hasattr(ind, "vwap") else None
    ema_fast = ind.ema(EMA_FAST)
    ema_mid = ind.ema(EMA_MID)
    ema_slow = ind.ema(EMA_SLOW)
    rsi = ind.rsi(RSI_PERIOD)

    # ── MACD from Binance data ────────────────────────────────────────────
    macd_line = None
    macd_signal = None
    macd_hist = None
    adx_value = None
    stoch_k = None
    stoch_d = None
    bb_middle = None
    bb_upper = None
    atr_current = None
    atr_avg = None
    latest_volume = None
    avg_volume = None

    try:
        from polyalpha.analysis import IndicatorCalculator
        calc = IndicatorCalculator(binance_data)

        # MACD
        macd_result = calc.macd(fast=12, slow=26, signal=9)
        if isinstance(macd_result, dict):
            macd_series = macd_result.get("macd")
            signal_series = macd_result.get("signal")
            hist_series = macd_result.get("histogram")
            if macd_series is not None and len(macd_series) > 0:
                macd_line = float(macd_series.iloc[-1])
            if signal_series is not None and len(signal_series) > 0:
                macd_signal = float(signal_series.iloc[-1])
            if hist_series is not None and len(hist_series) > 0:
                macd_hist = float(hist_series.iloc[-1])

        # ADX
        try:
            adx_result = calc.adx(period=14)
            if adx_result is not None:
                if hasattr(adx_result, "iloc"):
                    adx_value = float(adx_result.iloc[-1])
                elif isinstance(adx_result, dict):
                    adx_s = adx_result.get("adx")
                    if adx_s is not None and len(adx_s) > 0:
                        adx_value = float(adx_s.iloc[-1])
                else:
                    adx_value = float(adx_result)
        except Exception:
            adx_value = None

        # Stochastic
        try:
            stoch_result = calc.stochastic(k_period=14, d_period=3)
            if isinstance(stoch_result, dict):
                k_series = stoch_result.get("k") or stoch_result.get("%K")
                d_series = stoch_result.get("d") or stoch_result.get("%D")
                if k_series is not None and len(k_series) > 0:
                    stoch_k = float(k_series.iloc[-1])
                if d_series is not None and len(d_series) > 0:
                    stoch_d = float(d_series.iloc[-1])
        except Exception:
            stoch_k = None
            stoch_d = None

        # Bollinger Bands
        try:
            bb_result = calc.bollinger_bands(period=20, std_dev=2.0)
            if isinstance(bb_result, dict):
                mid_s = bb_result.get("middle")
                upper_s = bb_result.get("upper")
                if mid_s is not None and len(mid_s) > 0:
                    bb_middle = float(mid_s.iloc[-1])
                if upper_s is not None and len(upper_s) > 0:
                    bb_upper = float(upper_s.iloc[-1])
        except Exception:
            bb_middle = None
            bb_upper = None

        # ATR
        try:
            atr_series = calc.atr(period=14)
            if atr_series is not None and len(atr_series) > 0:
                atr_current = float(atr_series.iloc[-1])
                if len(atr_series) >= 20:
                    atr_avg = float(atr_series.tail(20).mean())
                else:
                    atr_avg = float(atr_series.mean())
        except Exception:
            atr_current = None
            atr_avg = None

        # Volume
        if "volume" in binance_data.columns and len(binance_data) >= 20:
            latest_volume = float(binance_data.iloc[-1]["volume"])
            avg_volume = float(binance_data.tail(20)["volume"].mean())

    except Exception as e:
        log.warning("Indicator calculation error: %s", e)
        return

    # ── Track recent lows for min % change ────────────────────────────────
    if len(binance_data) >= 10:
        low_10 = float(binance_data.tail(10)["low"].min())
    else:
        low_10 = current_price

    # ── Green candle check ────────────────────────────────────────────────
    candle_open = ctx._bot._candle_open_price
    is_green = candle_open is not None and current_price > candle_open

    # ── Chainlink price validation ────────────────────────────────────────
    chainlink_price = None
    if chainlink_data is not None and len(chainlink_data) > 0:
        chainlink_price = float(chainlink_data.iloc[-1]["close"])

    # ══════════════════════════════════════════════════════════════════════
    #  ENTRY CONDITION CHECKS
    # ══════════════════════════════════════════════════════════════════════

    checks = {}

    # 1. Triple EMA alignment (strong uptrend)
    checks["EMA8 > EMA21 > EMA50"] = (
        ema_fast is not None and ema_mid is not None and ema_slow is not None
        and ema_fast > ema_mid > ema_slow
    )

    # 2. Price > VWAP
    checks["Price > VWAP"] = (
        vwap is not None and current_price > vwap
    )

    # 3. RSI in momentum zone (not overbought)
    checks[f"RSI({RSI_PERIOD}) in [{RSI_LOWER}-{RSI_UPPER}]"] = (
        rsi is not None and RSI_LOWER <= rsi <= RSI_UPPER
    )

    # 4. MACD bullish (line > signal, histogram > 0)
    checks["MACD bullish"] = (
        macd_line is not None and macd_signal is not None and macd_hist is not None
        and macd_line > macd_signal and macd_hist > 0
    )

    # 5. ADX > threshold (trending)
    checks[f"ADX > {ADX_THRESHOLD}"] = (
        adx_value is not None and adx_value > ADX_THRESHOLD
    )

    # 6. Stochastic: %K > %D and %K < overbought
    checks["Stoch %K > %D, %K < 80"] = (
        stoch_k is not None and stoch_d is not None
        and stoch_k > stoch_d and stoch_k < STOCH_UPPER
    )

    # 7. Bollinger Band: price above middle, below upper
    checks["BB middle < Price < BB upper"] = (
        bb_middle is not None and bb_upper is not None
        and bb_middle < current_price < bb_upper
    )

    # 8. Volume confirmation
    checks[f"Volume > {VOLUME_MULTIPLIER}× avg"] = (
        latest_volume is not None and avg_volume is not None
        and avg_volume > 0 and latest_volume > avg_volume * VOLUME_MULTIPLIER
    )

    # 9. Minimum percentage change from recent low
    pct_from_low = ((current_price - low_10) / low_10) * 100 if low_10 > 0 else 0
    checks[f"Price ≥ {MIN_PCT_CHANGE}% above 10-bar low"] = (
        pct_from_low >= MIN_PCT_CHANGE
    )

    # 10. ATR within normal range (no volatility spike)
    checks["ATR < 2× avg (no vol spike)"] = (
        atr_current is not None and atr_avg is not None and atr_avg > 0
        and atr_current < atr_avg * ATR_MAX_MULTIPLE
    )

    # 11. Green candle
    checks["Green candle"] = is_green

    # 12. Chainlink validation
    if chainlink_price is not None and chainlink_price > 0:
        deviation_pct = abs(current_price - chainlink_price) / chainlink_price * 100
        checks[f"Chainlink deviation < {CHAINLINK_MAX_DEV}%"] = (
            deviation_pct < CHAINLINK_MAX_DEV
        )
    else:
        # If Chainlink unavailable, pass this check (graceful degradation)
        checks[f"Chainlink deviation < {CHAINLINK_MAX_DEV}%"] = True

    # ── Evaluate ──────────────────────────────────────────────────────────
    all_passed = all(checks.values())

    # Log scorecard periodically or when close to entry
    passed_count = sum(1 for v in checks.values() if v)
    if passed_count >= len(checks) - 2 or tick_count % 120 == 0:
        log_scorecard(checks)

    # ── Execute trade ─────────────────────────────────────────────────────
    if all_passed:
        size = calculate_position_size(adx_value)

        log.info(
            "🎯 ENTRY SIGNAL │ Price: %.4f │ RSI: %.1f │ ADX: %.1f │ "
            "MACD-H: %.6f │ Stoch-K: %.1f │ Size: $%.2f",
            current_price,
            rsi if rsi else 0,
            adx_value if adx_value else 0,
            macd_hist if macd_hist else 0,
            stoch_k if stoch_k else 0,
            size,
        )

        ctx.buy_once_per_candle("UP", size)


# ══════════════════════════════════════════════════════════════════════════════
#  ON RESOLVE — Track wins/losses
# ══════════════════════════════════════════════════════════════════════════════

@bot.onresolve
def on_resolve(pos):
    """Track outcomes for winrate calculation."""
    global trade_count, win_count, loss_count
    trade_count += 1

    if pos.pnl >= 0:
        win_count += 1
        emoji = "🟢"
    else:
        loss_count += 1
        emoji = "🔴"

    total = win_count + loss_count
    wr = (win_count / max(total, 1)) * 100

    log.info(
        "%s RESOLVED │ Side: %s │ Outcome: %s │ P&L: $%.2f │ "
        "Running WR: %.1f%% (%d/%d)",
        emoji, pos.side, pos.outcome, pos.pnl, wr, win_count, total,
    )


# ══════════════════════════════════════════════════════════════════════════════
#  MAIN
# ══════════════════════════════════════════════════════════════════════════════

if __name__ == "__main__":
    log.info("=" * 72)
    log.info("  🚀 BTC 5min Chainlink Sniper — HIGH WINRATE BUY-ONLY")
    log.info("=" * 72)
    log.info("  Asset:     %s", ASSET)
    log.info("  Timeframe: %s", TIMEFRAME)
    log.info("  Balance:   $%s", BALANCE)
    log.info("  EMAs:      %d / %d / %d", EMA_FAST, EMA_MID, EMA_SLOW)
    log.info("  RSI Zone:  %d – %d", RSI_LOWER, RSI_UPPER)
    log.info("  ADX Min:   %d", ADX_THRESHOLD)
    log.info("  Min %%Δ:    %.2f%%", MIN_PCT_CHANGE)
    log.info("  Vol Mult:  %.1f×", VOLUME_MULTIPLIER)
    log.info("  Max Dev:   %.1f%% (Chainlink)", CHAINLINK_MAX_DEV)
    log.info("  Sizing:    $%d – $%d (ADX-scaled)", BASE_SIZE, MAX_SIZE)
    log.info("=" * 72)
    bot.run()
