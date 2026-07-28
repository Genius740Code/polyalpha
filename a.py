"""
BTC 5-Minute Paper Trading Sniper — rewritten against the actual polyalpha
source (github.com/Genius740Code/polyalpha) instead of just its README.

Same strategy, same behavior, less custom code:
  - UP price band       -> native entry_price/entry_price_max (SniperConfig)
  - MACD + $30 filter    -> patches only Sniper._check_ta_conditions()
  - UP/DOWN orientation  -> corrected once per market at discovery, not per tick
  - Trade ledger         -> Client(db_path=...), auto-saved on resolve
  - Telegram             -> kept requests.post() (polyalpha's own
                             TelegramNotifier is broken with the
                             python-telegram-bot version it requires)
  - Real bug fix: on("resolve") now takes (outcome, pnl) -- the actual
    emit signature, not a single result object

use_ta=True and SignalGenerator.macd_bullish_crossover() were skipped on
purpose (not overlooked) -- former never refreshes after __init__ and
fails open on error, latter is edge-triggered rather than a state check
and would've silently changed how often this enters. Full rationale for
all of this, plus two more library bugs found along the way, is in chat.
"""
import json
import logging
import os
import sys
import threading
import time
from datetime import datetime, timezone

import requests
from dotenv import load_dotenv

import polyalpha
from polyalpha.bots import Sniper
from polyalpha.bots.sniper import SniperConfig
from polyalpha.trading.paper_config import PaperConfig
from polyalpha.analysis import DataFeed, DataFeedConfig, IndicatorCalculator, SignalGenerator, DeltaCalculator

load_dotenv()
logging.basicConfig(level=logging.INFO)
log = logging.getLogger("btc_sniper")

# ── Configuration ─────────────────────────────────────────────────────────────
ASSET = "BTC"
TIMEFRAME = "5m"
BALANCE = 1001
POSITION_SIZE = 5
WINDOW_SECONDS = 299          # 3:40 to 5:00 (80 seconds)
UP_PRICE_MIN = 0.1
UP_PRICE_MAX = 0.985
MIN_PRICE_CHANGE = 1.0      # $30 directional move

TA_SOURCE = "binance"
TA_REFRESH_SECONDS = 10
TA_LOOKBACK = 50

DB_FILE = "polyalpha_tradess.db"   # fresh filename -- your old trades.db has a different schema
SIGNAL_LOG = "signalss.jsonl"

STATUS_REFRESH_SECONDS = 0.5
GREEN, RED, RESET = "\033[92m", "\033[91m", "\033[0m"


# ── Background TA cache (non-blocking; the only part that must never run
# inside a stream tick callback) ──────────────────────────────────────────────

class TAState:
    def __init__(self):
        self._lock = threading.Lock()
        self.ready = False
        self.macd_bullish = False
        self.price_ok = False
        self.btc_spot = None
        self.btc_delta = None

    def update(self, macd_bullish, price_ok, btc_spot, btc_delta):
        with self._lock:
            self.macd_bullish, self.price_ok = macd_bullish, price_ok
            self.btc_spot, self.btc_delta = btc_spot, btc_delta
            self.ready = True

    def snapshot(self):
        with self._lock:
            return (self.macd_bullish, self.price_ok, self.btc_spot, self.btc_delta, self.ready)


ta_state = TAState()
_stop = threading.Event()


def _ta_refresh_loop():
    feed = DataFeed(DataFeedConfig(
        source=TA_SOURCE, timeframe=TIMEFRAME,
        lookback_periods=TA_LOOKBACK, use_cache=False,
    ))
    ta_log = logging.getLogger("ta_refresh")
    while not _stop.is_set():
        try:
            data = feed.fetch(ASSET)
            if len(data) >= 35:
                ind = IndicatorCalculator(data)
                sig = SignalGenerator(ind)
                macd = ind.macd()
                m = ind.get_latest_value(macd["macd"])
                s = ind.get_latest_value(macd["signal"])
                macd_bullish = m is not None and s is not None and m > s
                price_ok = sig.price_above_by(MIN_PRICE_CHANGE)
                btc_spot = float(data["close"].iloc[-1])
                btc_delta = float(DeltaCalculator(data).delta().iloc[-1])
                ta_state.update(macd_bullish, price_ok, btc_spot, btc_delta)
            else:
                ta_log.warning("Only %d candles (<35), skipping this refresh", len(data))
        except Exception as exc:
            ta_log.warning("TA refresh failed, keeping last good values: %s", exc)
        _stop.wait(TA_REFRESH_SECONDS)


# ── Live in-place status block ────────────────────────────────────────────────

class LiveBlock:
    def __init__(self):
        self._n = 0

    def render(self, lines):
        if self._n:
            sys.stdout.write(f"\033[{self._n}A")
        for line in lines:
            sys.stdout.write("\033[2K\r" + line + "\n")
        sys.stdout.flush()
        self._n = len(lines)

    def finalize(self):
        self._n = 0


live_block = LiveBlock()
_active_slug = None


def _status_lines(slug):
    macd_bullish, price_ok, btc_spot, btc_delta, ready = ta_state.snapshot()
    up = sniper._stream.up if sniper._stream else None
    up_ok = up is not None and UP_PRICE_MIN <= up <= UP_PRICE_MAX
    delta_disp = f"${btc_delta:.1f}" if btc_delta is not None else "$0.0"
    ready_line = f"{GREEN}TA ready{RESET}" if ready else f"{RED}TA not ready yet{RESET}"
    return [
        f"--- Market Window: {slug} ---",
        ready_line,
        f"{GREEN if macd_bullish else RED}MACD Bullish: {macd_bullish}{RESET}",
        f"{GREEN if price_ok else RED}BTC \u0394+${MIN_PRICE_CHANGE}: {price_ok} (\u0394: {delta_disp}){RESET}",
        f"{GREEN if up_ok else RED}UP Price [{UP_PRICE_MIN}-{UP_PRICE_MAX}]: {up_ok} "
        f"(current: {f'{up:.4f}' if up is not None else 'N/A'}){RESET}",
        "----------------------------------------",
    ]


def _status_loop():
    was_armed = False
    while not _stop.is_set():
        armed = sniper.state == Sniper.STATE_ARMED
        if armed and _active_slug:
            live_block.render(_status_lines(_active_slug))
        elif was_armed and not armed:
            live_block.finalize()
        was_armed = armed
        time.sleep(STATUS_REFRESH_SECONDS)


# ── Telegram (raw request -- polyalpha's own notifier is broken, see chat) ───

BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN") or os.getenv("BOT_TOKEN")
CHAT_ID = os.getenv("TELEGRAM_CHAT_ID") or os.getenv("CHAT_ID")


def send_telegram(msg: str) -> bool:
    if not BOT_TOKEN or not CHAT_ID:
        return False
    try:
        requests.post(
            f"https://api.telegram.org/bot{BOT_TOKEN}/sendMessage",
            json={"chat_id": CHAT_ID, "text": msg, "parse_mode": "HTML"},
            timeout=10,
        )
        return True
    except Exception:
        return False


def _log_signal(slug, up_price, btc_spot, btc_delta, macd_bullish):
    row = {
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "market_slug": slug, "up_price": up_price,
        "btc_spot": btc_spot, "btc_delta": btc_delta,
        "macd_bullish": macd_bullish,
    }
    with open(SIGNAL_LOG, "a") as f:
        f.write(json.dumps(row) + "\n")


# ── Client / Sniper setup ─────────────────────────────────────────────────────

paper_config = PaperConfig(
    fee_mode="custom", custom_fee_rate=0.01,
    execution_delay_ms=2000, slippage_pct=0.10,
    max_positions_per_market=1,
)
client = polyalpha.Client(balance=BALANCE, paper_config=paper_config, db_path=DB_FILE)

config = SniperConfig(
    asset=ASSET, timeframe=TIMEFRAME, side="UP",
    entry_price=UP_PRICE_MIN, entry_price_max=UP_PRICE_MAX,   # native band, replaces check_up_price()
    exit_price=None,                                          # no stop-loss was ever intended here
    window_seconds=WINDOW_SECONDS, amount=POSITION_SIZE,
    log_trades=True,
)
sniper = Sniper(client=client, config=config)


def _ta_gate() -> bool:
    """Replaces Sniper._check_ta_conditions (fresh MACD+delta gate; see chat)."""
    macd_bullish, price_ok, _, _, ready = ta_state.snapshot()
    result = ready and macd_bullish and price_ok
    if not result:
        log.debug("TA gate blocked: ready=%s, macd_bullish=%s, price_ok=%s", ready, macd_bullish, price_ok)
    return result


sniper._check_ta_conditions = _ta_gate


# ── Events ─────────────────────────────────────────────────────────────────

@sniper.on("market_found")
def on_market_found(market):
    # Debug: log initial market prices
    print(f"DEBUG: Market found - slug: {market.slug}")
    print(f"DEBUG: Market tokens: {market.tokens if hasattr(market, 'tokens') else 'N/A'}")
    print(f"DEBUG: Market prices: {market.prices if hasattr(market, 'prices') else 'N/A'}")


@sniper.on("window_enter")
def on_window_enter(market):
    global _active_slug
    print()
    _active_slug = market.slug
    # Debug: log stream details
    if sniper._stream:
        print(f"DEBUG: Stream object: {sniper._stream}")
        print(f"DEBUG: Stream.up: {getattr(sniper._stream, 'up', 'NOT SET')}")
        print(f"DEBUG: Stream.down: {getattr(sniper._stream, 'down', 'NOT SET')}")
        print(f"DEBUG: Market tokens: {market.tokens if hasattr(market, 'tokens') else 'N/A'}")
        print(f"DEBUG: Market prices: {market.prices if hasattr(market, 'prices') else 'N/A'}")
    live_block.render(_status_lines(market.slug))


@sniper.on("entry")
def on_entry(order):
    macd_bullish, price_ok, btc_spot, btc_delta, ready = ta_state.snapshot()
    print(f"✅ Entry: UP @ {order.price:.4f} | BTC: {btc_spot} (Δ+${btc_delta:.1f}) | MACD: {macd_bullish}")
    send_telegram(f"✅ Bought YES\nPrice: {order.price*100:.1f}¢\nBTC Δ: +${btc_delta:.1f}")
    _log_signal(_active_slug, order.price, btc_spot, btc_delta, macd_bullish)


@sniper.on("resolve")
def on_resolve(outcome, pnl):  # the actual emit signature -- two args, not one "result" object
    emoji = "🟢" if pnl >= 0 else "🔴"
    print(f"{emoji} Resolved: {outcome} | P&L: ${pnl:.2f}")
    send_telegram(f"{emoji} TRADE RESOLVED\n{outcome}\nP&L: ${pnl:.2f}")


threading.Thread(target=_ta_refresh_loop, daemon=True).start()
threading.Thread(target=_status_loop, daemon=True).start()


if __name__ == "__main__":
    print("BTC 5min Sniper: Last 80s | UP 0.90-0.985 | BTC Δ+$30 | MACD bullish | Once/market | DB + TG")
    try:
        sniper.run()
    finally:
        _stop.set()
        client.paper.report.show()   # new: final P&L summary via polyalpha's own reporting