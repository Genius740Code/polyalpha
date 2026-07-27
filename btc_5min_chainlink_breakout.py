"""
BTC 5-Minute Chainlink Breakout — Volatility Expansion UP/DOWN Strategy

╔══════════════════════════════════════════════════════════════════════════╗
║  STRATEGY: Oracle-Confirmed Breakout (Buys UP + DOWN)                  ║
║  TIMEFRAME: 5 minutes                                                  ║
║  DATA: Chainlink oracle (confirmation) + Binance (candles/vol)         ║
║  GOAL: Highest return by riding breakouts in both directions           ║
╚══════════════════════════════════════════════════════════════════════════╝

Core Idea:
──────────
  When BTC compresses into a tight range (low ATR, narrow Bollinger Bands)
  and then EXPLODES out, we ride the breakout.

  Chainlink oracle confirms the move is REAL (not a wick / fake-out)
  by verifying the oracle price is also moving in the breakout direction.

  This is a **trend-following** strategy — it buys strength and sells weakness.

BUY UP (Bullish Breakout):
──────────────────────────
  1. Price breaks above 20-candle high  (resistance breakout)
  2. ATR expanding: current ATR > 1.3× its 20-period average  (volatility surge)
  3. EMA9 > EMA21  (trend aligned)
  4. RSI > 55 but < 85  (momentum without extreme)
  5. Volume > 1.5× average  (conviction)
  6. Chainlink oracle > previous oracle reading  (oracle confirms move up)
  7. Price > VWAP  (institutional flow aligned)

BUY DOWN (Bearish Breakout):
────────────────────────────
  1. Price breaks below 20-candle low  (support breakdown)
  2. ATR expanding: current ATR > 1.3× its 20-period average
  3. EMA9 < EMA21  (trend aligned down)
  4. RSI < 45 but > 15  (selling momentum without extreme)
  5. Volume > 1.5× average
  6. Chainlink oracle < previous oracle reading  (oracle confirms move down)
  7. DOWN price > VWAP-equivalent for down  (selling pressure confirmed)

Usage:
    python btc_5min_chainlink_breakout.py
"""
import logging
import time
from collections import deque

import polyalpha
from polyalpha.analysis import DataFeed, DataFeedConfig

# ── Logging ───────────────────────────────────────────────────────────────────
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s │ %(name)-16s │ %(levelname)-5s │ %(message)s",
)
log = logging.getLogger("chainlink_breakout")


# ── Configuration ─────────────────────────────────────────────────────────────
ASSET = "BTC"
TIMEFRAME = "5m"
BALANCE = 100

# Breakout parameters
LOOKBACK_BARS = 20         # Candles for high/low channel
ATR_EXPANSION = 1.3        # ATR must be 1.3× its average (volatility expanding)
VOLUME_SURGE = 1.5         # Volume must be 1.5× average for breakout conviction

# RSI limits
RSI_UP_MIN = 55            # Minimum RSI for bullish breakout
RSI_UP_MAX = 85            # Cap to avoid blow-off tops
RSI_DOWN_MIN = 15          # Floor to avoid capitulation bottoms
RSI_DOWN_MAX = 45          # Maximum RSI for bearish breakout

# Position sizing
BASE_SIZE = 22
SURGE_SIZE = 30            # When ATR expansion is very strong
MAX_SIZE = 38              # Max per trade


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

# Track previous Chainlink oracle readings for direction confirmation
oracle_history = deque(maxlen=5)


def calc_size(atr_ratio):
    """Size based on ATR expansion strength."""
    if atr_ratio >= 2.0:
        return MAX_SIZE
    elif atr_ratio >= 1.6:
        return SURGE_SIZE
    return BASE_SIZE


# ══════════════════════════════════════════════════════════════════════════════
#  STRATEGY
# ══════════════════════════════════════════════════════════════════════════════

@bot.on_tick
def strategy(ctx):
    global tick_count, binance_data, chainlink_data
    global last_binance_fetch, last_chainlink_fetch
    global last_pnl_log_time

    tick_count += 1
    current_price = ctx.price.up
    current_down = ctx.price.down
    current_time = time.time()

    # ── Periodic logging ──────────────────────────────────────────────────
    if tick_count % 60 == 0:
        log.info(
            "Tick #%d │ UP: %.4f │ DOWN: %.4f │ Bal: $%.2f │ P&L: $%.2f │ "
            "Trades: %d",
            tick_count, current_price, current_down, ctx.balance, ctx.pnl,
            trade_count,
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
            log.info("📡 Binance: %d candles", len(binance_data))
        except Exception as e:
            log.warning("Binance fetch failed: %s", e)

    if chainlink_data is None or (current_time - last_chainlink_fetch) > 300:
        try:
            chainlink_data = chainlink_feed.fetch(ASSET)
            last_chainlink_fetch = current_time
            log.info("🔗 Chainlink: %d rows", len(chainlink_data))

            # Track oracle price history
            if chainlink_data is not None and len(chainlink_data) > 0:
                cl_price = float(chainlink_data.iloc[-1]["close"])
                oracle_history.append(cl_price)
        except Exception as e:
            log.warning("Chainlink fetch failed: %s", e)

    # ── Guards ────────────────────────────────────────────────────────────
    if binance_data is None or len(binance_data) < LOOKBACK_BARS + 10:
        return

    # ── Core indicators ───────────────────────────────────────────────────
    ind = ctx.indicators
    if ind is None:
        return

    ema9 = ind.ema(9)
    ema21 = ind.ema(21)
    rsi = ind.rsi(14)

    # ── Channel, ATR, Volume, VWAP from Binance candles ───────────────────
    high_channel = None
    low_channel = None
    atr_current = None
    atr_avg = None
    atr_ratio = None
    latest_volume = None
    avg_volume = None
    binance_close = None
    vwap = None

    try:
        from polyalpha.analysis import IndicatorCalculator
        calc = IndicatorCalculator(binance_data)
        binance_close = float(binance_data.iloc[-1]["close"])

        # VWAP from Binance (has volume)
        try:
            vwap = float(calc.vwap().iloc[-1])
        except Exception:
            vwap = None

        # 20-candle high/low channel (USD)
        lookback = binance_data.tail(LOOKBACK_BARS)
        high_channel = float(lookback["high"].max())
        low_channel = float(lookback["low"].min())

        # ATR
        atr_series = calc.atr(period=14)
        if atr_series is not None and len(atr_series) > 0:
            atr_current = float(atr_series.iloc[-1])
            if len(atr_series) >= 20:
                atr_avg = float(atr_series.tail(20).mean())
            else:
                atr_avg = float(atr_series.mean())
            if atr_avg > 0:
                atr_ratio = atr_current / atr_avg

        # Volume
        if "volume" in binance_data.columns and len(binance_data) >= 20:
            latest_volume = float(binance_data.iloc[-1]["volume"])
            avg_volume = float(binance_data.tail(20)["volume"].mean())

    except Exception as e:
        log.warning("Indicator error: %s", e)
        return

    # ── Chainlink oracle direction ────────────────────────────────────────
    oracle_rising = False
    oracle_falling = False
    if len(oracle_history) >= 2:
        oracle_rising = oracle_history[-1] > oracle_history[-2]
        oracle_falling = oracle_history[-1] < oracle_history[-2]

    # ══════════════════════════════════════════════════════════════════════
    #  BUY UP — Bullish breakout above channel high
    # ══════════════════════════════════════════════════════════════════════

    up_checks = {}

    # 1. Price above 20-bar high (breakout) — both USD
    up_checks["Price > 20-bar high"] = (
        binance_close is not None and high_channel is not None
        and binance_close > high_channel
    )

    # 2. ATR expanding (volatility surge)
    up_checks[f"ATR > {ATR_EXPANSION}× avg"] = (
        atr_ratio is not None and atr_ratio > ATR_EXPANSION
    )

    # 3. EMA9 > EMA21 (trend aligned)
    up_checks["EMA9 > EMA21"] = (
        ema9 is not None and ema21 is not None and ema9 > ema21
    )

    # 4. RSI in momentum zone
    up_checks[f"RSI {RSI_UP_MIN}–{RSI_UP_MAX}"] = (
        rsi is not None and RSI_UP_MIN < rsi < RSI_UP_MAX
    )

    # 5. Volume surge
    up_checks[f"Vol > {VOLUME_SURGE}× avg"] = (
        latest_volume is not None and avg_volume is not None
        and avg_volume > 0 and latest_volume > avg_volume * VOLUME_SURGE
    )

    # 6. Chainlink oracle rising
    up_checks["Oracle rising"] = oracle_rising

    # 7. Price > VWAP (USD)
    up_checks["Price > VWAP"] = (
        binance_close is not None and vwap is not None and binance_close > vwap
    )

    if all(up_checks.values()):
        size = calc_size(atr_ratio if atr_ratio else 1.0)
        log.info(
            "🚀 BREAKOUT UP │ USD: %.2f │ Channel High: %.2f │ "
            "ATR×: %.2f │ RSI: %.1f │ Vol×: %.1f │ Size: $%.0f",
            binance_close, high_channel,
            atr_ratio if atr_ratio else 0,
            rsi if rsi else 0,
            (latest_volume / avg_volume) if avg_volume else 0,
            size,
        )
        ctx.buy_once_per_candle("UP", size)
    else:
        up_passed = sum(1 for v in up_checks.values() if v)
        if up_passed >= 5 and tick_count % 100 == 0:
            sym = {True: "✅", False: "❌"}
            lines = [f"  {sym[v]} {k}" for k, v in up_checks.items()]
            log.info("UP breakout %d/7:\n%s", up_passed, "\n".join(lines))

    # ══════════════════════════════════════════════════════════════════════
    #  BUY DOWN — Bearish breakout below channel low
    # ══════════════════════════════════════════════════════════════════════

    down_checks = {}

    # 1. Price below 20-bar low (breakdown) — both USD
    down_checks["Price < 20-bar low"] = (
        binance_close is not None and low_channel is not None
        and binance_close < low_channel
    )

    # 2. ATR expanding
    down_checks[f"ATR > {ATR_EXPANSION}× avg"] = (
        atr_ratio is not None and atr_ratio > ATR_EXPANSION
    )

    # 3. EMA9 < EMA21 (bearish alignment)
    down_checks["EMA9 < EMA21"] = (
        ema9 is not None and ema21 is not None and ema9 < ema21
    )

    # 4. RSI in selling zone
    down_checks[f"RSI {RSI_DOWN_MIN}–{RSI_DOWN_MAX}"] = (
        rsi is not None and RSI_DOWN_MIN < rsi < RSI_DOWN_MAX
    )

    # 5. Volume surge
    down_checks[f"Vol > {VOLUME_SURGE}× avg"] = (
        latest_volume is not None and avg_volume is not None
        and avg_volume > 0 and latest_volume > avg_volume * VOLUME_SURGE
    )

    # 6. Chainlink oracle falling
    down_checks["Oracle falling"] = oracle_falling

    # 7. DOWN price showing strength (above 0.5 = market favoring down)
    down_checks["DOWN price > 0.45"] = current_down > 0.45

    if all(down_checks.values()):
        size = calc_size(atr_ratio if atr_ratio else 1.0)
        log.info(
            "💥 BREAKOUT DOWN │ USD: %.2f │ Channel Low: %.2f │ "
            "ATR×: %.2f │ RSI: %.1f │ DOWN: %.4f │ Size: $%.0f",
            binance_close, low_channel,
            atr_ratio if atr_ratio else 0,
            rsi if rsi else 0,
            current_down,
            size,
        )
        ctx.buy_once_per_candle("DOWN", size)
    else:
        down_passed = sum(1 for v in down_checks.values() if v)
        if down_passed >= 5 and tick_count % 100 == 0:
            sym = {True: "✅", False: "❌"}
            lines = [f"  {sym[v]} {k}" for k, v in down_checks.items()]
            log.info("DOWN breakout %d/7:\n%s", down_passed, "\n".join(lines))


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
    log.info("  💥 BTC 5min Chainlink Breakout — VOLATILITY EXPANSION UP/DOWN")
    log.info("=" * 68)
    log.info("  Channel:    %d-bar high/low", LOOKBACK_BARS)
    log.info("  ATR Exp:    ≥ %.1f× average", ATR_EXPANSION)
    log.info("  Volume:     ≥ %.1f× average", VOLUME_SURGE)
    log.info("  RSI UP:     %d – %d", RSI_UP_MIN, RSI_UP_MAX)
    log.info("  RSI DOWN:   %d – %d", RSI_DOWN_MIN, RSI_DOWN_MAX)
    log.info("  Oracle:     Direction confirmation required")
    log.info("  Sizing:     $%d / $%d / $%d (ATR-scaled)", BASE_SIZE, SURGE_SIZE, MAX_SIZE)
    log.info("=" * 68)
    bot.run()
