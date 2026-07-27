"""
BTC 5-Minute Paper Trading Sniper (Sniper Bot)

Uses Sniper class with custom conditions: MACD bullish, directional $30 move, UP price band (0.90-0.985).
"""
import polyalpha
from polyalpha.bots import Sniper
from polyalpha.bots.sniper import SniperConfig
from polyalpha.trading.paper_config import PaperConfig
from polyalpha.analysis import DataFeed, DataFeedConfig
from dotenv import load_dotenv
import os
import sqlite3
import requests
from datetime import datetime, timezone

load_dotenv()

# Configuration
ASSET = "BTC"
TIMEFRAME = "5m"
BALANCE = 100
POSITION_SIZE = 20
WINDOW_SECONDS = 80  # 3:40 to 5:00 (80 seconds)
UP_PRICE_MIN = 0.90
UP_PRICE_MAX = 0.985
MIN_PRICE_CHANGE = 30.0  # $30 directional move

# Telegram
TELEGRAM_BOT_TOKEN = os.getenv("BOT_TOKEN")
TELEGRAM_CHAT_ID = os.getenv("CHAT_ID")

# Database
DB_FILE = "trades.db"

# Paper trading config
paper_config = PaperConfig(
    fee_mode="custom",
    custom_fee_rate=0.01,
    execution_delay_ms=2000,
    slippage_pct=0.10,
    max_positions_per_market=1,
)

client = polyalpha.Client(balance=BALANCE, paper_config=paper_config)

# Data feed for TA
spot_feed = DataFeed(DataFeedConfig(
    source="chainlink",
    timeframe=TIMEFRAME,
    lookback_periods=50,
))

# Helpers
def check_macd(data):
    """Check if MACD is bullish."""
    if data is None or len(data) < 35:
        return False
    close = data['close'].values
    def ema(prices, period):
        mult = 2 / (period + 1)
        val = [prices[0]]
        for p in prices[1:]:
            val.append((p - val[-1]) * mult + val[-1])
        return val[-1]
    ema_fast = ema(close, 12)
    ema_slow = ema(close, 26)
    macd_line = ema_fast - ema_slow
    macd_hist = []
    for i in range(26, len(close)):
        fast = ema(close[:i+1], 12)
        slow = ema(close[:i+1], 26)
        macd_hist.append(fast - slow)
    if len(macd_hist) < 9:
        return False
    signal_line = ema(macd_hist, 9)
    return macd_line > signal_line

def check_price_change(data):
    """Check if BTC moved up by $30+ vs previous candle."""
    if data is None or len(data) < 3:
        return False, None, None
    current = data['close'].iloc[-2]
    prev = data['close'].iloc[-3]
    delta = current - prev
    return delta >= MIN_PRICE_CHANGE, current, delta

def check_up_price(up_price):
    """Check if UP price is in band [0.90, 0.985]."""
    return UP_PRICE_MIN <= up_price <= UP_PRICE_MAX

def send_telegram(msg):
    if not TELEGRAM_BOT_TOKEN or not TELEGRAM_CHAT_ID:
        return False
    try:
        requests.post(f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/sendMessage",
                     json={"chat_id": TELEGRAM_CHAT_ID, "text": msg, "parse_mode": "HTML"}, timeout=10)
        return True
    except:
        return False

def init_db():
    conn = sqlite3.connect(DB_FILE)
    conn.execute('''CREATE TABLE IF NOT EXISTS trades (
        id INTEGER PRIMARY KEY AUTOINCREMENT, timestamp TEXT, up_price REAL,
        btc_spot REAL, btc_delta REAL, macd_bullish INTEGER, position_size REAL,
        outcome TEXT, pnl REAL, resolved_at TEXT
    )''')
    conn.commit()
    conn.close()

def save_trade(data):
    conn = sqlite3.connect(DB_FILE)
    conn.execute('''INSERT INTO trades (timestamp, up_price, btc_spot, btc_delta, macd_bullish, position_size)
                 VALUES (?, ?, ?, ?, ?, ?)''',
                 (data["timestamp"], data["up_price"], data["btc_spot"],
                  data["btc_delta"], 1 if data["macd_bullish"] else 0, data["position_size"]))
    conn.commit()
    conn.close()

def update_trade(outcome, pnl):
    conn = sqlite3.connect(DB_FILE)
    conn.execute('''UPDATE trades SET outcome=?, pnl=?, resolved_at=? WHERE id=(SELECT MAX(id) FROM trades)''',
                 (outcome, pnl, datetime.now(timezone.utc).isoformat()))
    conn.commit()
    conn.close()

# Sniper config (no TA - we'll handle it manually)
config = SniperConfig(
    asset=ASSET,
    timeframe=TIMEFRAME,
    side="UP",
    entry_price=UP_PRICE_MIN,
    window_seconds=WINDOW_SECONDS,
    amount=POSITION_SIZE,
    log_trades=True,
)

sniper = Sniper(client=client, config=config)

# Patch price handler to add custom conditions
spot_data = None
original_on_price_update = sniper._on_price_update

def patched_price_handler(up, down):
    global spot_data
    # Fetch spot data
    try:
        spot_data = spot_feed.fetch(ASSET)
    except:
        return
    
    # Check all conditions
    if not check_up_price(up):
        return
    if not check_macd(spot_data):
        return
    price_ok, btc_spot, delta = check_price_change(spot_data)
    if not price_ok:
        return
    
    # All conditions met - call original handler
    original_on_price_update(up, down)

sniper._on_price_update = patched_price_handler

# Event handlers
@sniper.on("entry")
def on_entry(order):
    global spot_data
    price_ok, btc_spot, delta = check_price_change(spot_data)
    macd_ok = check_macd(spot_data)
    print(f"✅ Entry: UP @ {order.price:.4f} | BTC: {btc_spot} (Δ+${delta:.1f}) | MACD: {macd_ok}")
    send_telegram(f"✅ Bought YES\nPrice: {order.price*100:.1f}¢\nBTC Δ: +${delta:.1f}")
    save_trade({
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "up_price": order.price,
        "btc_spot": btc_spot,
        "btc_delta": delta,
        "macd_bullish": macd_ok,
        "position_size": order.amount,
    })

@sniper.on("resolve")
def on_resolve(result):
    emoji = "🟢" if result.pnl >= 0 else "🔴"
    print(f"{emoji} Resolved: {result.outcome} | P&L: ${result.pnl:.2f}")
    send_telegram(f"{emoji} TRADE RESOLVED\n{result.outcome}\nP&L: ${result.pnl:.2f}")
    update_trade(result.outcome, result.pnl)

if __name__ == "__main__":
    init_db()
    print("BTC 5min Sniper: Last 80s | UP 0.90-0.985 | BTC Δ+$30 | MACD bullish | Once/market | DB + TG")
    sniper.run()
