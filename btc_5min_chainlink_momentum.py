"""
BTC 5-Minute Chainlink Momentum — Higher-Frequency BUY-ONLY Strategy

╔══════════════════════════════════════════════════════════════════════════╗
║  STRATEGY: Relaxed Momentum Sniper (Long Only / Higher Freq)           ║
║  TIMEFRAME: 5 minutes                                                  ║
║  DATA: Chainlink oracle (validation) + Binance (volume/candles)        ║
║  GOAL: More frequent entries while maintaining solid winrate           ║
╚══════════════════════════════════════════════════════════════════════════╝

Compared to the strict 12-condition sniper, this version:
  • Uses 7 conditions instead of 12
  • Wider RSI window (50–75 vs 55–72)
  • Dual EMA instead of triple (EMA9 > EMA21, no EMA50)
  • Volume threshold lowered (1.0× avg instead of 1.2×)
  • No Stochastic / Bollinger Band / ATR requirements
  • Lower min % change (0.05% vs 0.10%)
  • Chainlink deviation widened to 1.0%

Entry Conditions (ALL must be true):
─────────────────────────────────────
  1. TREND  — EMA9 > EMA21  (bullish crossover)
  2. VWAP   — Price > VWAP  (above fair value)
  3. RSI    — 50 ≤ RSI(14) ≤ 75  (wider momentum window)
  4. MACD   — MACD histogram > 0  (bullish momentum)
  5. VOL    — Current volume ≥ 20-period average  (normal participation)
  6. GREEN  — Current candle is green (close > open)
  7. CHAIN  — Chainlink oracle deviation < 1.0%  (price sanity check)

Optional boost (not required, but increases size):
  • ADX > 25 → scale position up
  • Min % change ≥ 0.05% from 10-bar low → extra confidence

Usage:
    python btc_5min_chainlink_momentum.py
"""
import logging
import time

import polyalpha
from polyalpha.analysis import DataFeed, DataFeedConfig

# ── Logging ───────────────────────────────────────────────────────────────────
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s │ %(name)-14s │ %(levelname)-5s │ %(message)s",
)
log = logging.getLogger("chainlink_momentum")


# ── Configuration ─────────────────────────────────────────────────────────────
ASSET = "BTC"
TIMEFRAME = "5m"
BALANCE = 100

# Indicator parameters (relaxed vs sniper)
EMA_FAST = 9
EMA_SLOW = 21
RSI_PERIOD = 14
RSI_LOWER = 50            # Wider entry zone
RSI_UPPER = 75            # More headroom
MIN_PCT_CHANGE = 0.05     # Lower bar to clear
CHAINLINK_MAX_DEV = 1.0   # Wider tolerance

# Position sizing
BASE_SIZE = 20
BOOST_SIZE = 28            # Used when ADX confirms trend
MAX_SIZE = 32


# ── Bot Setup ─────────────────────────────────────────────────────────────────
bot = polyalpha.Bot(ASSET, TIMEFRAME, balance=BALANCE)

# Chainlink data feed
chainlink_config = DataFeedConfig(
    source="chainlink",
    timeframe=TIMEFRAME,
    lookback_periods=100,
)
chainlink_feed = DataFeed(chainlink_config)

# Binance data feed — volume + OHLCV
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

binance_data = None
chainlink_data = None
last_binance_fetch = 0
last_chainlink_fetch = 0

last_pnl_log_time = 0


# ── Helper: Position Sizing with Optional ADX Boost ──────────────────────────
def calculate_size(adx_value, pct_from_low):
    """Base size with optional boosts for strong trend / momentum."""
    size = BASE_SIZE

    # Boost 1: ADX confirms trend
    if adx_value is not None and adx_value > 25:
        size = BOOST_SIZE

    # Boost 2: Strong move from low
    if pct_from_low >= 0.15:
        size = min(size + 4, MAX_SIZE)

    return size


# ══════════════════════════════════════════════════════════════════════════════
#  STRATEGY TICK HANDLER
# ══════════════════════════════════════════════════════════════════════════════

@bot.on_tick
def strategy(ctx):
    global tick_count, binance_data, chainlink_data
    global last_binance_fetch, last_chainlink_fetch
    global last_pnl_log_time

    tick_count += 1
    current_price = ctx.price.up
    current_time = time.time()

    # ── Periodic logging ──────────────────────────────────────────────────
    if tick_count % 60 == 0:
        log.info(
            "Tick #%d │ Price: %.4f │ Bal: $%.2f │ P&L: $%.2f │ "
            "Trades: %d │ Open: %d",
            tick_count, current_price, ctx.balance, ctx.pnl,
            trade_count, len(ctx.positions),
        )

    if current_time - last_pnl_log_time > 300:
        wr = (win_count / max(win_count + loss_count, 1)) * 100
        log.info(
            "📊 Stats │ W: %d │ L: %d │ WR: %.1f%% │ P&L: $%.2f",
            win_count, loss_count, wr, ctx.pnl,
        )
        last_pnl_log_time = current_time

    # ── Fetch Binance data (every 5 min) ──────────────────────────────────
    if binance_data is None or (current_time - last_binance_fetch) > 300:
        try:
            binance_data = binance_feed.fetch(ASSET)
            last_binance_fetch = current_time
            log.info("📡 Binance: %d candles", len(binance_data))
        except Exception as e:
            log.warning("Binance fetch failed: %s", e)
            binance_data = None

    # ── Fetch Chainlink oracle price (every 5 min) ────────────────────────
    if chainlink_data is None or (current_time - last_chainlink_fetch) > 300:
        try:
            chainlink_data = chainlink_feed.fetch(ASSET)
            last_chainlink_fetch = current_time
            log.info("🔗 Chainlink: %d rows", len(chainlink_data))
        except Exception as e:
            log.warning("Chainlink fetch failed: %s", e)
            chainlink_data = None

    # ── Need minimum data ─────────────────────────────────────────────────
    if binance_data is None or len(binance_data) < 30:
        return

    # ── Core indicators from ctx (Polymarket sentiment) ───────────────────
    ind = ctx.indicators
    if ind is None:
        return

    ema_fast = ind.ema(EMA_FAST)
    ema_slow = ind.ema(EMA_SLOW)
    rsi = ind.rsi(RSI_PERIOD)

    # ── Binance-based indicators (USD domain) ─────────────────────────────
    binance_close = None
    vwap = None
    macd_hist = None
    adx_value = None

    try:
        from polyalpha.analysis import IndicatorCalculator
        calc = IndicatorCalculator(binance_data)
        binance_close = float(binance_data.iloc[-1]["close"])

        # VWAP from Binance (has volume)
        try:
            vwap = float(calc.vwap().iloc[-1])
        except Exception:
            vwap = None

        # MACD histogram
        macd_result = calc.macd(fast=12, slow=26, signal=9)
        if isinstance(macd_result, dict):
            hist_series = macd_result.get("histogram")
            if hist_series is not None and len(hist_series) > 0:
                macd_hist = float(hist_series.iloc[-1])

        # ADX (optional — used for sizing boost only)
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

    except Exception as e:
        log.warning("Indicator calc error: %s", e)
        return

    # ── Volume ────────────────────────────────────────────────────────────
    latest_volume = None
    avg_volume = None
    if "volume" in binance_data.columns and len(binance_data) >= 20:
        latest_volume = float(binance_data.iloc[-1]["volume"])
        avg_volume = float(binance_data.tail(20)["volume"].mean())

    # ── Min % change from 10-bar low (USD) ────────────────────────────────
    if len(binance_data) >= 10 and binance_close is not None:
        low_10 = float(binance_data.tail(10)["low"].min())
        pct_from_low = ((binance_close - low_10) / low_10) * 100 if low_10 > 0 else 0
    else:
        low_10 = binance_close if binance_close else 0
        pct_from_low = 0

    # ── Green candle ──────────────────────────────────────────────────────
    candle_open = ctx._bot._candle_open_price
    is_green = candle_open is not None and current_price > candle_open

    # ── Chainlink price validation (both USD) ─────────────────────────────
    chainlink_ok = True
    if chainlink_data is not None and len(chainlink_data) > 0 and binance_close is not None:
        cl_price = float(chainlink_data.iloc[-1]["close"])
        if cl_price > 0:
            deviation = abs(binance_close - cl_price) / cl_price * 100
            chainlink_ok = deviation < CHAINLINK_MAX_DEV

    # ══════════════════════════════════════════════════════════════════════
    #  7 ENTRY CONDITIONS
    # ══════════════════════════════════════════════════════════════════════

    checks = {}

    # 1. EMA9 > EMA21 (bullish trend)
    checks["EMA9 > EMA21"] = (
        ema_fast is not None and ema_slow is not None
        and ema_fast > ema_slow
    )

    # 2. Price > VWAP (USD)
    checks["Price > VWAP"] = (
        binance_close is not None and vwap is not None and binance_close > vwap
    )

    # 3. RSI in [50, 75]
    checks["RSI 50–75"] = (
        rsi is not None and RSI_LOWER <= rsi <= RSI_UPPER
    )

    # 4. MACD histogram > 0
    checks["MACD hist > 0"] = (
        macd_hist is not None and macd_hist > 0
    )

    # 5. Volume ≥ average
    checks["Vol ≥ avg"] = (
        latest_volume is not None and avg_volume is not None
        and avg_volume > 0 and latest_volume >= avg_volume
    )

    # 6. Green candle
    checks["Green candle"] = is_green

    # 7. Chainlink OK
    checks["Chainlink OK"] = chainlink_ok

    # ── Evaluate ──────────────────────────────────────────────────────────
    all_passed = all(checks.values())
    passed_count = sum(1 for v in checks.values() if v)

    # Log when close to triggering
    if passed_count >= 5 or tick_count % 120 == 0:
        symbols = {True: "✅", False: "❌"}
        lines = [f"  {symbols[v]} {k}" for k, v in checks.items()]
        log.info(
            "Scorecard %d/7:\n%s", passed_count, "\n".join(lines),
        )

    # ── Execute ───────────────────────────────────────────────────────────
    if all_passed:
        size = calculate_size(adx_value, pct_from_low)

        log.info(
            "🎯 ENTRY │ USD: %.2f │ RSI: %.1f │ MACD-H: %.6f │ "
            "ADX: %s │ Size: $%.0f",
            binance_close,
            rsi if rsi else 0,
            macd_hist if macd_hist else 0,
            f"{adx_value:.1f}" if adx_value else "N/A",
            size,
        )

        ctx.buy_once_per_candle("UP", size)


# ══════════════════════════════════════════════════════════════════════════════
#  ON RESOLVE
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
        "%s %s │ P&L: $%.2f │ WR: %.1f%% (%d/%d)",
        emoji, pos.outcome, pos.pnl, wr, win_count, total,
    )


# ══════════════════════════════════════════════════════════════════════════════
#  MAIN
# ══════════════════════════════════════════════════════════════════════════════

if __name__ == "__main__":
    log.info("=" * 68)
    log.info("  ⚡ BTC 5min Chainlink Momentum — HIGHER FREQ BUY-ONLY")
    log.info("=" * 68)
    log.info("  Asset:     %s", ASSET)
    log.info("  Timeframe: %s", TIMEFRAME)
    log.info("  Balance:   $%s", BALANCE)
    log.info("  EMAs:      %d / %d", EMA_FAST, EMA_SLOW)
    log.info("  RSI Zone:  %d – %d", RSI_LOWER, RSI_UPPER)
    log.info("  Min %%Δ:    %.2f%% (boost only)", MIN_PCT_CHANGE)
    log.info("  Chainlink: ≤ %.1f%% deviation", CHAINLINK_MAX_DEV)
    log.info("  Sizing:    $%d / $%d / $%d", BASE_SIZE, BOOST_SIZE, MAX_SIZE)
    log.info("  Conditions: 7 (vs 12 in sniper)")
    log.info("=" * 68)
    bot.run()
