"""
BTC 5-Minute Chainlink Reversal — Mean-Reversion UP/DOWN Strategy

╔══════════════════════════════════════════════════════════════════════════╗
║  STRATEGY: Oracle Mean-Reversion (Buys UP + DOWN)                      ║
║  TIMEFRAME: 5 minutes                                                  ║
║  DATA: Chainlink oracle (fair value anchor) + Binance (candles/vol)    ║
║  GOAL: Highest return via snap-back trades at extremes                 ║
╚══════════════════════════════════════════════════════════════════════════╝

Core Idea:
──────────
  Chainlink oracle price = "true" fair value.  When the live price on
  Polymarket deviates too far from the oracle, it tends to snap back.
  We exploit that reversion:

    • Price stretched UP from oracle  + RSI overbought  → buy DOWN
    • Price stretched DOWN from oracle + RSI oversold   → buy UP

  This is a **contrarian** strategy — it fades extremes for profit.

BUY UP Conditions:
───────────────────
  1. Price < Chainlink oracle by ≥ 0.08%  (discount to fair value)
  2. RSI(14) < 35  (oversold)
  3. Price < lower Bollinger Band  (statistically extreme)
  4. MACD histogram turning positive or near zero  (momentum exhaustion)
  5. Volume > average  (capitulation / high participation)
  6. Green candle  (first sign of reversal)

BUY DOWN Conditions:
────────────────────
  1. Price > Chainlink oracle by ≥ 0.08%  (premium to fair value)
  2. RSI(14) > 70  (overbought)
  3. Price > upper Bollinger Band  (statistically extreme)
  4. MACD histogram turning negative or near zero  (momentum fading)
  5. Volume > average  (euphoria / blow-off)
  6. Red candle  (first sign of rejection)

Usage:
    python btc_5min_chainlink_reversal.py
"""
import logging
import time

import polyalpha
from polyalpha.analysis import DataFeed, DataFeedConfig

# ── Logging ───────────────────────────────────────────────────────────────────
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s │ %(name)-16s │ %(levelname)-5s │ %(message)s",
)
log = logging.getLogger("chainlink_reversal")


# ── Configuration ─────────────────────────────────────────────────────────────
ASSET = "BTC"
TIMEFRAME = "5m"
BALANCE = 100

# Oracle deviation thresholds
ORACLE_DEV_MIN = 0.08        # Min % deviation from Chainlink to trigger

# RSI thresholds
RSI_OVERSOLD = 35
RSI_OVERBOUGHT = 70

# MACD histogram exhaustion zone
MACD_HIST_NEAR_ZERO = 0.0005  # Histogram magnitude threshold for "fading"

# Position sizing
BASE_SIZE = 22
STRONG_SIZE = 30              # When deviation + RSI are both extreme
MAX_SIZE = 35


# ── Bot Setup ─────────────────────────────────────────────────────────────────
bot = polyalpha.Bot(ASSET, TIMEFRAME, balance=BALANCE)

chainlink_config = DataFeedConfig(source="chainlink", timeframe=TIMEFRAME, lookback_periods=100)
chainlink_feed = DataFeed(chainlink_config)

binance_config = DataFeedConfig(source="binance", timeframe=TIMEFRAME, lookback_periods=100)
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
last_price_update_time = 0


def size_for_signal(oracle_dev_pct, rsi_value, side):
    """Bigger size when signals are more extreme."""
    size = BASE_SIZE

    if side == "UP":
        if oracle_dev_pct > 0.15 and rsi_value < 28:
            size = MAX_SIZE
        elif oracle_dev_pct > 0.12 or rsi_value < 30:
            size = STRONG_SIZE
    else:  # DOWN
        if oracle_dev_pct > 0.15 and rsi_value > 78:
            size = MAX_SIZE
        elif oracle_dev_pct > 0.12 or rsi_value > 75:
            size = STRONG_SIZE

    return size


# ══════════════════════════════════════════════════════════════════════════════
#  STRATEGY
# ══════════════════════════════════════════════════════════════════════════════

@bot.on_tick
def strategy(ctx):
    global tick_count, binance_data, chainlink_data
    global last_binance_fetch, last_chainlink_fetch
    global last_pnl_log_time, last_price_update_time

    tick_count += 1
    current_price = ctx.price.up
    current_down = ctx.price.down
    current_time = time.time()
    last_price_update_time = current_time

    # ── Periodic logging ──────────────────────────────────────────────────
    if tick_count % 60 == 0:
        log.info(
            "Tick #%d │ UP: %.4f │ DOWN: %.4f │ Bal: $%.2f │ P&L: $%.2f",
            tick_count, current_price, current_down, ctx.balance, ctx.pnl,
        )

    if current_time - last_pnl_log_time > 300:
        wr = (win_count / max(win_count + loss_count, 1)) * 100
        log.info(
            "📊 Stats │ W: %d │ L: %d │ WR: %.1f%% │ P&L: $%.2f",
            win_count, loss_count, wr, ctx.pnl,
        )
        last_pnl_log_time = current_time

    # ── Fetch data ────────────────────────────────────────────────────────
    if binance_data is None or (current_time - last_binance_fetch) > 300:
        try:
            binance_data = binance_feed.fetch(ASSET)
            last_binance_fetch = current_time
        except Exception as e:
            log.warning("Binance fetch failed: %s", e)

    if chainlink_data is None or (current_time - last_chainlink_fetch) > 300:
        try:
            chainlink_data = chainlink_feed.fetch(ASSET)
            last_chainlink_fetch = current_time
        except Exception as e:
            log.warning("Chainlink fetch failed: %s", e)

    # ── Guards ────────────────────────────────────────────────────────────
    if current_time - last_price_update_time > 30:
        return
    if binance_data is None or len(binance_data) < 30:
        return
    if chainlink_data is None or len(chainlink_data) < 1:
        return

    # ── Chainlink oracle price ────────────────────────────────────────────
    oracle_price = float(chainlink_data.iloc[-1]["close"])
    if oracle_price <= 0:
        return

    oracle_dev_up = ((current_price - oracle_price) / oracle_price) * 100
    oracle_dev_down = ((oracle_price - current_price) / oracle_price) * 100

    # ── Indicators ────────────────────────────────────────────────────────
    ind = ctx.indicators
    if ind is None:
        return

    rsi = ind.rsi(14)

    # MACD + Bollinger from Binance candles
    macd_hist = None
    bb_lower = None
    bb_upper = None
    latest_volume = None
    avg_volume = None

    try:
        from polyalpha.analysis import IndicatorCalculator
        calc = IndicatorCalculator(binance_data)

        # MACD histogram
        macd_result = calc.macd(fast=12, slow=26, signal=9)
        if isinstance(macd_result, dict):
            hist_s = macd_result.get("histogram")
            if hist_s is not None and len(hist_s) > 0:
                macd_hist = float(hist_s.iloc[-1])

        # Bollinger Bands
        bb_result = calc.bollinger_bands(period=20, std_dev=2.0)
        if isinstance(bb_result, dict):
            lower_s = bb_result.get("lower")
            upper_s = bb_result.get("upper")
            if lower_s is not None and len(lower_s) > 0:
                bb_lower = float(lower_s.iloc[-1])
            if upper_s is not None and len(upper_s) > 0:
                bb_upper = float(upper_s.iloc[-1])

        # Volume
        if "volume" in binance_data.columns and len(binance_data) >= 20:
            latest_volume = float(binance_data.iloc[-1]["volume"])
            avg_volume = float(binance_data.tail(20)["volume"].mean())

    except Exception as e:
        log.warning("Indicator error: %s", e)
        return

    # ── Candle color ──────────────────────────────────────────────────────
    candle_open = ctx._bot._candle_open_price
    is_green = candle_open is not None and current_price > candle_open
    is_red = candle_open is not None and current_price < candle_open

    volume_ok = (
        latest_volume is not None and avg_volume is not None
        and avg_volume > 0 and latest_volume >= avg_volume
    )

    # ══════════════════════════════════════════════════════════════════════
    #  BUY UP — Price below oracle, oversold, reversal forming
    # ══════════════════════════════════════════════════════════════════════

    up_checks = {}
    up_checks["Price < Oracle by ≥0.08%"] = oracle_dev_down >= ORACLE_DEV_MIN
    up_checks["RSI < 35 (oversold)"] = rsi is not None and rsi < RSI_OVERSOLD
    up_checks["Price < BB lower"] = bb_lower is not None and current_price < bb_lower
    up_checks["MACD hist fading"] = (
        macd_hist is not None and (macd_hist > -MACD_HIST_NEAR_ZERO or macd_hist > 0)
    )
    up_checks["Volume ≥ avg"] = volume_ok
    up_checks["Green candle"] = is_green

    if all(up_checks.values()):
        size = size_for_signal(oracle_dev_down, rsi, "UP")
        log.info(
            "🟢 BUY UP │ Price: %.4f │ Oracle: %.2f │ Dev: -%.2f%% │ "
            "RSI: %.1f │ Size: $%.0f",
            current_price, oracle_price, oracle_dev_down, rsi, size,
        )
        ctx.buy_once_per_candle("UP", size)
    else:
        up_passed = sum(1 for v in up_checks.values() if v)
        if up_passed >= 4 and tick_count % 120 == 0:
            sym = {True: "✅", False: "❌"}
            lines = [f"  {sym[v]} {k}" for k, v in up_checks.items()]
            log.info("UP scorecard %d/6:\n%s", up_passed, "\n".join(lines))

    # ══════════════════════════════════════════════════════════════════════
    #  BUY DOWN — Price above oracle, overbought, rejection forming
    # ══════════════════════════════════════════════════════════════════════

    down_checks = {}
    down_checks["Price > Oracle by ≥0.08%"] = oracle_dev_up >= ORACLE_DEV_MIN
    down_checks["RSI > 70 (overbought)"] = rsi is not None and rsi > RSI_OVERBOUGHT
    down_checks["Price > BB upper"] = bb_upper is not None and current_price > bb_upper
    down_checks["MACD hist fading"] = (
        macd_hist is not None and (macd_hist < MACD_HIST_NEAR_ZERO or macd_hist < 0)
    )
    down_checks["Volume ≥ avg"] = volume_ok
    down_checks["Red candle"] = is_red

    if all(down_checks.values()):
        size = size_for_signal(oracle_dev_up, rsi, "DOWN")
        log.info(
            "🔴 BUY DOWN │ Price: %.4f │ Oracle: %.2f │ Dev: +%.2f%% │ "
            "RSI: %.1f │ Size: $%.0f",
            current_price, oracle_price, oracle_dev_up, rsi, size,
        )
        ctx.buy_once_per_candle("DOWN", size)
    else:
        down_passed = sum(1 for v in down_checks.values() if v)
        if down_passed >= 4 and tick_count % 120 == 0:
            sym = {True: "✅", False: "❌"}
            lines = [f"  {sym[v]} {k}" for k, v in down_checks.items()]
            log.info("DOWN scorecard %d/6:\n%s", down_passed, "\n".join(lines))


# ══════════════════════════════════════════════════════════════════════════════
#  ON RESOLVE
# ══════════════════════════════════════════════════════════════════════════════

@bot.onresolve
def on_resolve(pos):
    global trade_count, win_count, loss_count
    trade_count += 1
    if pos.pnl >= 0:
        win_count += 1
        e = "🟢"
    else:
        loss_count += 1
        e = "🔴"
    wr = (win_count / max(win_count + loss_count, 1)) * 100
    log.info(
        "%s %s %s │ P&L: $%.2f │ WR: %.1f%% (%d/%d)",
        e, pos.side, pos.outcome, pos.pnl, wr, win_count, win_count + loss_count,
    )


# ══════════════════════════════════════════════════════════════════════════════
#  MAIN
# ══════════════════════════════════════════════════════════════════════════════

if __name__ == "__main__":
    log.info("=" * 68)
    log.info("  🔄 BTC 5min Chainlink Reversal — MEAN REVERSION UP/DOWN")
    log.info("=" * 68)
    log.info("  Oracle Dev:  ≥ %.2f%%", ORACLE_DEV_MIN)
    log.info("  RSI Zones:   < %d (UP) │ > %d (DOWN)", RSI_OVERSOLD, RSI_OVERBOUGHT)
    log.info("  Bollinger:   Outside bands = entry zone")
    log.info("  Sizing:      $%d / $%d / $%d", BASE_SIZE, STRONG_SIZE, MAX_SIZE)
    log.info("=" * 68)
    bot.run()
