"""
BTC 5-minute bot with technical analysis conditions:

- Price > VWAP
- EMA9 > EMA20  
- Current candle closes green
- Current volume > 20-candle average volume (from Binance)
- RSI between 55 and 70

Usage:
    python examples/btc_5min_ta_bot.py
"""
import logging
import polyalpha
from collections import deque
from polyalpha.analysis import DataFeed, DataFeedConfig

logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(name)s - %(levelname)s - %(message)s')
log = logging.getLogger(__name__)

bot = polyalpha.Bot("BTC", "5m", balance=100)

# Initialize Binance data feed for volume data
binance_config = DataFeedConfig(source="binance", timeframe="5m", lookback_periods=100)
binance_feed = DataFeed(binance_config)

# Track volume history for average calculation
volume_history = deque(maxlen=20)

# Track tick count for periodic logging
tick_count = 0

# Cache for Binance data
binance_data = None
last_binance_fetch = 0

@bot.on_tick
def strategy(ctx):
    global tick_count, binance_data, last_binance_fetch
    import time
    tick_count += 1
    
    # Get current price
    current_price = ctx.price.up
    
    # Log price every 50 ticks
    if tick_count % 50 == 0:
        log.info("Current price: %.4f", current_price)
    
    # Fetch Binance volume data every 5 minutes (300 seconds)
    current_time = time.time()
    if binance_data is None or (current_time - last_binance_fetch) > 300:
        try:
            binance_data = binance_feed.fetch("BTC")
            last_binance_fetch = current_time
            log.info("Fetched %d candles from Binance", len(binance_data))
        except Exception as e:
            log.warning("Failed to fetch Binance data: %s", e)
            binance_data = None
    
    # Get indicators
    vwap = ctx.indicators.vwap() if ctx.indicators else None
    ema9 = ctx.indicators.ema(9) if ctx.indicators else None
    ema20 = ctx.indicators.ema(20) if ctx.indicators else None
    rsi = ctx.indicators.rsi(14) if ctx.indicators else None
    
    # Check if current candle is green (close > open)
    candle_open = ctx._bot._candle_open_price
    is_green = candle_open is not None and current_price > candle_open
    
    # Volume condition using Binance data
    volume_condition = True
    if binance_data is not None and len(binance_data) >= 20:
        # Get the latest candle's volume
        latest_volume = binance_data.iloc[-1]['volume']
        # Calculate 20-candle average volume
        avg_volume = binance_data.tail(20)['volume'].mean()
        # Check if current volume > average
        volume_condition = latest_volume > avg_volume
        volume_history.append(latest_volume)
        
        if tick_count % 50 == 0:
            log.info("Volume: %.2f (avg: %.2f) - %s", latest_volume, avg_volume, 
                     "✓" if volume_condition else "✗")
    else:
        # Skip volume check if no Binance data
        volume_condition = True
    
    # Check all conditions
    conditions_met = True
    
    # Price > VWAP
    if vwap is None or current_price <= vwap:
        conditions_met = False
        
    # EMA9 > EMA20
    if ema9 is None or ema20 is None or ema9 <= ema20:
        conditions_met = False
        
    # Green candle
    if not is_green:
        conditions_met = False
        
    # RSI between 55 and 70
    if rsi is None or not (55 <= rsi <= 70):
        conditions_met = False
        
    # Volume condition
    if not volume_condition:
        conditions_met = False
    
    # If all conditions met, buy UP
    if conditions_met:
        log.info("Conditions met: Price=%.4f, VWAP=%.4f, EMA9=%.4f, EMA20=%.4f, RSI=%.2f", current_price, vwap, ema9, ema20, rsi)
        ctx.buy_once_per_candle("UP", 20)

if __name__ == "__main__":
    bot.run()

"""
BTC 5-minute bot with technical analysis conditions:

- Price > VWAP
- EMA9 > EMA20  
- Current candle closes green
- Current volume > 20-candle average volume (from Binance)
- RSI between 55 and 70

Usage:
    python examples/btc_5min_ta_bot.py
"""
import logging
import polyalpha
from collections import deque
from polyalpha.analysis import DataFeed, DataFeedConfig

logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(name)s - %(levelname)s - %(message)s')
log = logging.getLogger(__name__)

bot = polyalpha.Bot("BTC", "5m", balance=100)

# Initialize Binance data feed for volume data
binance_config = DataFeedConfig(source="binance", timeframe="5m", lookback_periods=100)
binance_feed = DataFeed(binance_config)

# Track volume history for average calculation
volume_history = deque(maxlen=20)

# Track tick count for periodic logging
tick_count = 0

# Cache for Binance data
binance_data = None
last_binance_fetch = 0

# Track if trade already made this session
trade_made_this_session = False

# Track last P&L log time
last_pnl_log_time = 0

# Track last price update time for staleness detection
last_price_update_time = 0

@bot.on_tick
def strategy(ctx):
    global tick_count, binance_data, last_binance_fetch, trade_made_this_session, last_pnl_log_time, last_price_update_time
    import time
    tick_count += 1
    
    # Get current price
    current_price = ctx.price.up
    current_time = time.time()
    
    # Update last price update time (data is fresh when we receive a tick)
    last_price_update_time = current_time
    
    # Log price every 50 ticks
    if tick_count % 50 == 0:
        log.info("Current price: %.4f", current_price)
    
    # Log P&L every 5 minutes
    if current_time - last_pnl_log_time > 300:
        log.info("P&L: $%.2f | Balance: $%.2f | Positions: %d", ctx.pnl, ctx.balance, len(ctx.positions))
        last_pnl_log_time = current_time
    
    # Fetch Binance volume data every 5 minutes (300 seconds)
    if binance_data is None or (current_time - last_binance_fetch) > 300:
        try:
            binance_data = binance_feed.fetch("BTC")
            last_binance_fetch = current_time
            log.info("Fetched %d candles from Binance", len(binance_data))
        except Exception as e:
            log.warning("Failed to fetch Binance data: %s", e)
            binance_data = None
    
    # Get indicators
    vwap = ctx.indicators.vwap() if ctx.indicators else None
    ema9 = ctx.indicators.ema(9) if ctx.indicators else None
    ema20 = ctx.indicators.ema(20) if ctx.indicators else None
    rsi = ctx.indicators.rsi(14) if ctx.indicators else None
    
    # Check if current candle is green (close > open)
    candle_open = ctx._bot._candle_open_price
    is_green = candle_open is not None and current_price > candle_open
    
    # Volume condition using Binance data
    volume_condition = True
    if binance_data is not None and len(binance_data) >= 20:
        # Get the latest candle's volume
        latest_volume = binance_data.iloc[-1]['volume']
        # Calculate 20-candle average volume
        avg_volume = binance_data.tail(20)['volume'].mean()
        # Check if current volume > average
        volume_condition = latest_volume > avg_volume
        volume_history.append(latest_volume)
        
        if tick_count % 50 == 0:
            log.info("Volume: %.2f (avg: %.2f) - %s", latest_volume, avg_volume, 
                     "✓" if volume_condition else "✗")
    else:
        # Skip volume check if no Binance data
        volume_condition = True
    
    # Check all conditions
    conditions_met = True
    
    # Data staleness check (skip if no price update for 30+ seconds)
    data_age = current_time - last_price_update_time
    if data_age > 30:
        conditions_met = False
        if tick_count % 50 == 0:
            log.warning("Data stale: %.1fs since last update (max 30s)", data_age)
    
    # Price > VWAP
    if vwap is None or current_price <= vwap:
        conditions_met = False
        
    # EMA9 > EMA20
    if ema9 is None or ema20 is None or ema9 <= ema20:
        conditions_met = False
        
    # Green candle
    if not is_green:
        conditions_met = False
        
    # RSI between 55 and 70
    if rsi is None or not (55 <= rsi <= 70):
        conditions_met = False
        
    # Volume condition
    if not volume_condition:
        conditions_met = False
    
    # If all conditions met, buy UP (only once per session)
    if conditions_met and not trade_made_this_session:
        log.info("Conditions met: Price=%.4f, VWAP=%.4f, EMA9=%.4f, EMA20=%.4f, RSI=%.2f", current_price, vwap, ema9, ema20, rsi)
        ctx.buy("UP", 20)
        trade_made_this_session = True
        log.info("Trade executed for this session")

@bot.onresolve
def on_resolve(pos):
    """Reset trade flag when position resolves."""
    global trade_made_this_session
    trade_made_this_session = False
    log.info("Position resolved: %s %s | P&L: $%.2f", pos.side, pos.outcome, pos.pnl)

if __name__ == "__main__":
    bot.run()
