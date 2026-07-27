"""
BTC 5-Minute Paper Trading Sniper

╔══════════════════════════════════════════════════════════════════════════╗
║  PAPER TRADING SNIPER - BUY ONLY                                        ║
║  TIMEFRAME: 5 minutes                                                   ║
║  MARKET: BTC/USD                                                        ║
║  TIME FILTER: 3:40 AM EST only                                         ║
╚══════════════════════════════════════════════════════════════════════════╝

Configuration:
  • Fee: 1% per trade
  • Trade delay: 2 seconds
  • Buy condition: Price at 0.9-0.95 of VWAP
  • Min price change: $30 USD
  • Slippage: 10%
  • Max trades: Once per 5-minute candle
  • Telegram notifications: Enabled if TELEGRAM_BOT_TOKEN and TELEGRAM_CHAT_ID are set
"""
import logging
import time
from datetime import datetime, timezone
import pytz

import polyalpha
from polyalpha.analysis import DataFeed, DataFeedConfig
from polyalpha.trading.paper_config import PaperConfig

# ── Logging ───────────────────────────────────────────────────────────────────
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s │ %(name)-12s │ %(levelname)-5s │ %(message)s",
)
log = logging.getLogger("paper_sniper")

# ── Configuration ─────────────────────────────────────────────────────────────
ASSET = "BTC"
TIMEFRAME = "5m"
BALANCE = 100  # Paper trading balance in USDC

# Time filter: 3:40 AM EST (Eastern Time)
TARGET_HOUR = 3
TARGET_MINUTE = 40

# Buy condition: price as ratio of VWAP
PRICE_RATIO_MIN = 0.90  # 0.9
PRICE_RATIO_MAX = 0.95  # 0.95

# Min price change: $30 USD
MIN_PRICE_CHANGE_USD = 30.0

# Position sizing
POSITION_SIZE_USD = 20  # Fixed position size for paper trading

# ── Paper Trading Config (built-in) ─────────────────────────────────────────
paper_config = PaperConfig(
    fee_mode="custom",
    custom_fee_rate=0.01,  # 1% fee
    execution_delay_ms=2000,  # 2 second delay
    slippage_pct=0.10,  # 10% slippage
    max_positions_per_market=1,  # Once per market
)

# ── Bot Setup ─────────────────────────────────────────────────────────────────
bot = polyalpha.Bot(
    ASSET, 
    TIMEFRAME, 
    balance=BALANCE, 
    mode="custom",
    paper_config=paper_config
)

# Binance data feed
binance_config = DataFeedConfig(
    source="binance",
    timeframe=TIMEFRAME,
    lookback_periods=50,
)
binance_feed = DataFeed(binance_config)

# ── State ─────────────────────────────────────────────────────────────────────
binance_data = None
last_binance_fetch = 0
est_timezone = pytz.timezone("America/New_York")

# ── Helper: Time Filter Check ─────────────────────────────────────────────────
def is_target_time():
    """Check if current time is within the target window (3:40 AM EST)."""
    now_utc = datetime.now(timezone.utc)
    now_est = now_utc.astimezone(est_timezone)
    
    # Check if we're at 3:40 AM EST (within the same minute)
    is_target = (now_est.hour == TARGET_HOUR and 
                 now_est.minute == TARGET_MINUTE)
    
    return is_target, now_est

# ── Helper: Calculate VWAP ────────────────────────────────────────────────────
def calculate_vwap(data):
    """Calculate VWAP from OHLCV data."""
    if data is None or len(data) < 5:
        return None
    
    # VWAP = Σ(Price × Volume) / Σ(Volume)
    # Using typical price: (high + low + close) / 3
    data = data.copy()
    data['typical_price'] = (data['high'] + data['low'] + data['close']) / 3
    data['pv'] = data['typical_price'] * data['volume']
    
    vwap = data['pv'].sum() / data['volume'].sum()
    return vwap

# ── Helper: Check Minimum Price Change ───────────────────────────────────────
def check_min_price_change(current_price, data, min_change_usd):
    """Check if price has changed by at least min_change_usd from recent low/high."""
    if data is None or len(data) < 10:
        return True  # Skip check if not enough data
    
    # Get price range from last 10 candles
    recent_data = data.tail(10)
    min_price = recent_data['low'].min()
    max_price = recent_data['high'].max()
    
    # Check if current price is at least min_change_usd away from recent extremes
    change_from_min = abs(current_price - min_price)
    change_from_max = abs(current_price - max_price)
    
    return max(change_from_min, change_from_max) >= min_change_usd

# ══════════════════════════════════════════════════════════════════════════════
#  STRATEGY TICK HANDLER
# ══════════════════════════════════════════════════════════════════════════════

@bot.on_tick
def strategy(ctx):
    global binance_data, last_binance_fetch
    
    current_price = ctx.price.up
    current_time = time.time()
    
    # ── Periodic logging ──────────────────────────────────────────────────
    if ctx.tick_count % 60 == 0:
        is_target, now_est = is_target_time()
        log.info(
            "Tick #%d │ Price: %.2f │ Balance: $%.2f │ P&L: $%.2f │ "
            "EST Time: %s │ Target Window: %s",
            ctx.tick_count, current_price, ctx.balance, ctx.pnl,
            now_est.strftime("%H:%M:%S"), is_target
        )
    
    # ── Fetch Binance data (every 5 min) ─────────────────────────────────
    if binance_data is None or (current_time - last_binance_fetch) > 300:
        try:
            binance_data = binance_feed.fetch(ASSET)
            last_binance_fetch = current_time
            log.info("📡 Binance: %d candles fetched", len(binance_data))
        except Exception as e:
            log.warning("Binance fetch failed: %s", e)
            binance_data = None
    
    # ── Time Filter Check ───────────────────────────────────────────────
    is_target, now_est = is_target_time()
    
    if not is_target:
        if ctx.tick_count % 300 == 0:  # Log every 5 minutes
            log.info("⏰ Outside target window (3:40 AM EST). Current: %s EST", 
                    now_est.strftime("%H:%M"))
        return
    
    # ── Need data for indicators ─────────────────────────────────────────
    if binance_data is None or len(binance_data) < 20:
        log.info("⏳ Waiting for enough data...")
        return
    
    # ── Calculate VWAP ───────────────────────────────────────────────────
    vwap = calculate_vwap(binance_data)
    
    if vwap is None:
        log.warning("⚠️  Could not calculate VWAP")
        return
    
    # ── Check price ratio condition (0.9 - 0.95 of VWAP) ─────────────────
    price_ratio = current_price / vwap if vwap > 0 else 0
    
    ratio_condition = PRICE_RATIO_MIN <= price_ratio <= PRICE_RATIO_MAX
    
    # ── Check minimum price change ($30 USD) ─────────────────────────────
    min_change_ok = check_min_price_change(current_price, binance_data, MIN_PRICE_CHANGE_USD)
    
    # ── Log conditions ────────────────────────────────────────────────────
    log.info(
        "📊 Price: %.2f │ VWAP: %.2f │ Ratio: %.3f │ "
        "Ratio OK: %s │ Min $30 Change: %s",
        current_price, vwap, price_ratio, ratio_condition, min_change_ok
    )
    
    # ── Execute trade if conditions met ─────────────────────────────────
    if ratio_condition and min_change_ok:
        log.info("🎯 ENTRY SIGNAL at %s EST", now_est.strftime("%H:%M:%S"))
        log.info("   Price: $%.2f │ VWAP: $%.2f │ Ratio: %.3f", 
                current_price, vwap, price_ratio)
        
        # Execute buy (fees, slippage, delay handled by PaperConfig)
        ctx.buy_once_per_candle("UP", POSITION_SIZE_USD)
        log.info("✅ Trade executed (1%% fee, 2s delay, 10%% slippage applied by PaperConfig)")

# ══════════════════════════════════════════════════════════════════════════════
#  ON RESOLVE — Track paper trading outcomes
# ══════════════════════════════════════════════════════════════════════════════

@bot.onresolve
def on_resolve(pos):
    """Track paper trading outcomes."""
    emoji = "🟢" if pos.pnl >= 0 else "🔴"
    
    log.info(
        "%s PAPER TRADE RESOLVED │ Side: %s │ Outcome: %s │ P&L: $%.2f",
        emoji, pos.side, pos.outcome, pos.pnl
    )

# ══════════════════════════════════════════════════════════════════════════════
#  MAIN
# ══════════════════════════════════════════════════════════════════════════════

if __name__ == "__main__":
    log.info("=" * 72)
    log.info("  📄 BTC 5min PAPER TRADING SNIPER")
    log.info("=" * 72)
    log.info("  Asset:     %s", ASSET)
    log.info("  Timeframe: %s", TIMEFRAME)
    log.info("  Balance:   $%s (PAPER TRADING)", BALANCE)
    log.info("  Target:    %d:%d AM EST", TARGET_HOUR, TARGET_MINUTE)
    log.info("  Fee:       1%% (via PaperConfig)")
    log.info("  Delay:     2s (via PaperConfig)")
    log.info("  Slippage:  10%% (via PaperConfig)")
    log.info("  Price Ratio: %.2f - %.2f of VWAP", PRICE_RATIO_MIN, PRICE_RATIO_MAX)
    log.info("  Min Change: $%.2f USD", MIN_PRICE_CHANGE_USD)
    log.info("  Position:  $%.2f", POSITION_SIZE_USD)
    log.info("  Once per market: Yes (via PaperConfig)")
    log.info("=" * 72)
    bot.run()
