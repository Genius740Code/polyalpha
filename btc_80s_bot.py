"""
BTC 80-second bot with momentum and volatility conditions:

- Last 80 seconds price change must be at least +15 basis points (0.15%)
- ATR below recent average (low volatility)
- Price > VWAP

Usage:
    python btc_80s_bot.py
"""
import logging
import polyalpha
from collections import deque
import time

logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(name)s - %(levelname)s - %(message)s')
log = logging.getLogger(__name__)

bot = polyalpha.Bot("BTC", "5m", balance=100)

# Track price history for 80-second window
price_history = deque(maxlen=80)  # Assuming ~1 tick per second
timestamp_history = deque(maxlen=80)

# Track ATR history for comparison
atr_history = deque(maxlen=20)

# Track tick count for periodic logging
tick_count = 0

# Track if trade already made this session
trade_made_this_session = False

# Track last P&L log time
last_pnl_log_time = 0

@bot.on_tick
def strategy(ctx):
    global tick_count, trade_made_this_session, last_pnl_log_time
    tick_count += 1
    
    # Get current price
    current_price = ctx.price.up
    current_time = time.time()
    
    # Track price and timestamp
    price_history.append(current_price)
    timestamp_history.append(current_time)
    
    # Log price every 50 ticks
    if tick_count % 50 == 0:
        log.info("Current price: %.4f", current_price)
    
    # Log P&L every 5 minutes
    if current_time - last_pnl_log_time > 300:
        log.info("P&L: $%.2f | Balance: $%.2f | Positions: %d", ctx.pnl, ctx.balance, len(ctx.positions))
        last_pnl_log_time = current_time
    
    # Get indicators
    vwap = ctx.indicators.vwap() if ctx.indicators else None
    
    # Calculate 80-second price change
    price_change_80s = 0.0
    if len(price_history) >= 2:
        # Find price from 80 seconds ago
        cutoff_time = current_time - 80
        old_price = None
        for i, ts in enumerate(timestamp_history):
            if ts >= cutoff_time:
                if i > 0:
                    old_price = price_history[i - 1]
                break
        
        if old_price is not None:
            price_change_80s = ((current_price - old_price) / old_price) * 100  # in percentage
    
    # Calculate ATR (simplified using high-low range from price history)
    atr = 0.0
    if len(price_history) >= 14:
        high = max(price_history)
        low = min(price_history)
        atr = (high - low) / current_price * 100  # as percentage
        atr_history.append(atr)
    
    # Calculate recent ATR average
    avg_atr = 0.0
    if len(atr_history) >= 10:
        avg_atr = sum(list(atr_history)[-10:]) / 10
    
    # Check conditions
    conditions_met = True
    
    # Price change >= 15 basis points (0.15%)
    if price_change_80s < 0.15:
        conditions_met = False
        if tick_count % 50 == 0:
            log.info("Price change too low: %.2f%% (need >=0.15%%)", price_change_80s)
    
    # ATR below recent average (low volatility)
    if atr > 0 and avg_atr > 0 and atr >= avg_atr:
        conditions_met = False
        if tick_count % 50 == 0:
            log.info("ATR too high: %.2f%% (avg: %.2f%%)", atr, avg_atr)
    
    # Price > VWAP
    if vwap is None or current_price <= vwap:
        conditions_met = False
        if tick_count % 50 == 0:
            log.info("Price below VWAP: %.4f <= %.4f", current_price, vwap)
    
    # If all conditions met, buy UP (only once per session)
    if conditions_met and not trade_made_this_session:
        log.info("Conditions met: Price=%.4f, Change=%.2f%%, ATR=%.2f%%, AvgATR=%.2f%%, VWAP=%.4f", 
                 current_price, price_change_80s, atr, avg_atr, vwap)
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
