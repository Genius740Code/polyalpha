"""
Paper trade 6 Polymarket 5-min bot strategies using BotHub.

All 6 strategies share one WebSocket connection via BotHub, each with
its own isolated PaperEngine (independent balance, positions, P&L).

Usage
-----
    pip install polyalpha[analysis]   # pandas + numpy for RSI indicators
    python examples/paper_6_strategies.py
    python examples/paper_6_strategies.py --balance 5000 --mode realistic
"""

import argparse
import json
import os
import sys
import threading
import time
import urllib.request
from datetime import datetime, timezone

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))
import polyalpha


def log(label: str, msg: str) -> None:
    ts = datetime.now(timezone.utc).strftime("%H:%M:%S")
    print(f"[{ts}][{label:<24s}] {msg}")


# ╔══════════════════════════════════════════════════════════════════════════════╗
# ║  Binance BTC price poller — feeds live BTC prices into a shared list        ║
# ║  Used by Strategy 4 (cross-asset momentum) to detect BTC moves.             ║
# ╚══════════════════════════════════════════════════════════════════════════════╝

BTC_FEED: list[float] = []
BTC_FEED_LOCK = threading.Lock()


def _btc_price_poller(interval: float = 1.0):
    while True:
        try:
            req = urllib.request.urlopen(
                "https://api.binance.com/api/v3/ticker/price?symbol=BTCUSDT",
                timeout=5,
            )
            price = float(json.loads(req.read())["price"])
            with BTC_FEED_LOCK:
                BTC_FEED.append(price)
                if len(BTC_FEED) > 200:
                    BTC_FEED[:] = BTC_FEED[-200:]
        except Exception:
            pass
        time.sleep(interval)


# ╔══════════════════════════════════════════════════════════════════════════════╗
# ║  Strategy 2 — Final-10s Convergence Sniper                                  ║
# ║                                                                             ║
# ║  15-20% of 5m periods resolve in the last 10 seconds. When BTC is deeply    ║
# ║  in one direction with <30s left, the winning token is nearly certain but   ║
# ║  still trades at $0.10-0.25 discount. Buy that discount for an asymmetric   ║
# ║  3:1 to 5:1 payoff.                                                         ║
# ╚══════════════════════════════════════════════════════════════════════════════╝

def strategy_2_convergence_sniper(ctx):
    s = ctx.seconds_in
    if s < 270:
        return
    up, down = ctx.price.up, ctx.price.down
    if up > 0.85 and down < 0.15:
        log("02", f"CONDITION MET: up={up:.3f} > 0.85, down={down:.3f} < 0.15")
        log("02", f"BUY UP @ {up:.3f} (winner near-certain, {300-s:.0f}s left)")
        ctx.buy_once_per_candle("UP", 10)
    elif down > 0.85 and up < 0.15:
        log("02", f"CONDITION MET: down={down:.3f} > 0.85, up={up:.3f} < 0.15")
        log("02", f"BUY DOWN @ {down:.3f} (winner near-certain, {300-s:.0f}s left)")
        ctx.buy_once_per_candle("DOWN", 10)


# ╔══════════════════════════════════════════════════════════════════════════════╗
# ║  Strategy 4 — Cross-Asset Momentum                                          ║
# ║                                                                             ║
# ║  BTC moves first (most liquid). When BTC rips 0.15%+ in a short window,     ║
# ║  ETH/SOL typically follow within 15-30s. We trade the BTC 5m market here    ║
# ║  (since this is a BTC BotHub), gating on BTC spot momentum from Binance.    ║
# ║  Works because the Polymarket Chainlink feed lags Binance by 2-10s.         ║
# ╚══════════════════════════════════════════════════════════════════════════════╝

def strategy_4_cross_asset_momentum(ctx):
    with BTC_FEED_LOCK:
        feed = list(BTC_FEED)
    if len(feed) < 5:
        return
    recent = feed[-5:]
    delta_pct = (recent[-1] - recent[0]) / recent[0] * 100
    up, down = ctx.price.up, ctx.price.down
    if delta_pct > 0.15 and up < 0.65:
        log("04", f"BUY UP @ {up:.3f} (BTC momentum +{delta_pct:.2f}%)")
        ctx.buy_once_per_candle("UP", 15)
    elif delta_pct < -0.15 and down < 0.65:
        log("04", f"BUY DOWN @ {down:.3f} (BTC momentum {delta_pct:.2f}%)")
        ctx.buy_once_per_candle("DOWN", 15)


# ╔══════════════════════════════════════════════════════════════════════════════╗
# ║  Strategy 5 — Flash Crash Recovery                                          ║
# ║                                                                             ║
# ║  When UP drops 30+ cents in <5s (whale market sell or panic), the book      ║
# ║  overreacts. Binary resolution depends on BTC price, not the order book.    ║
# ║  If BTC hasn't moved much, buy the oversold token for mean reversion.       ║
# ╚══════════════════════════════════════════════════════════════════════════════╝

_FLASH_STATE = {"up_prev": None, "up_time": 0.0, "down_prev": None, "down_time": 0.0}

def strategy_5_flash_crash(ctx):
    now = time.time()
    up, down = ctx.price.up, ctx.price.down
    if _FLASH_STATE["up_prev"] is not None:
        drop = (_FLASH_STATE["up_prev"] - up) / (_FLASH_STATE["up_prev"] or 1)
        elapsed = now - _FLASH_STATE["up_time"]
        if drop > 0.30 and elapsed < 5.0:
            log("05", f"FLASH CRASH UP @ {up:.3f} (dropped {drop*100:.0f}% in {elapsed:.1f}s)")
            ctx.buy_once_per_candle("UP", 10)
    if _FLASH_STATE["down_prev"] is not None:
        drop = (_FLASH_STATE["down_prev"] - down) / (_FLASH_STATE["down_prev"] or 1)
        elapsed = now - _FLASH_STATE["down_time"]
        if drop > 0.30 and elapsed < 5.0:
            log("05", f"FLASH CRASH DOWN @ {down:.3f} (dropped {drop*100:.0f}% in {elapsed:.1f}s)")
            ctx.buy_once_per_candle("DOWN", 10)
    _FLASH_STATE["up_prev"] = up
    _FLASH_STATE["up_time"] = now
    _FLASH_STATE["down_prev"] = down
    _FLASH_STATE["down_time"] = now


# ╔══════════════════════════════════════════════════════════════════════════════╗
# ║  Strategy 6 — VWAP/RSI Signal Engine                                        ║
# ║                                                                             ║
# ║  Binance BTC 5m candles → RSI(14) + SMA(20) as VWAP proxy.                  ║
# ║  RSI < 30 (oversold) + price below SMA → buy UP (expect mean reversion).    ║
# ║  RSI > 70 (overbought) + price above SMA → buy DOWN.                        ║
# ║  Gate on token price (only enter when underdog is $0.20-0.45 for better     ║
# ║  asymmetric payoff and lower taker fee from the p×(1-p) fee formula).       ║
# ╚══════════════════════════════════════════════════════════════════════════════╝

def strategy_6_vwap_rsi(ctx):
    rsi = ctx.indicators.rsi(14) if ctx.indicators else None
    sma = ctx.indicators.sma(20) if ctx.indicators else None
    if rsi is None or sma is None:
        return
    up, down = ctx.price.up, ctx.price.down
    if rsi < 30 and up < 0.45 and up < sma:
        log("06", f"BUY UP @ {up:.3f} (RSI={rsi:.0f} oversold, SMA={sma:.4f})")
        ctx.buy_once_per_candle("UP", 20)
    elif rsi > 70 and down < 0.45 and down < sma:
        log("06", f"BUY DOWN @ {down:.3f} (RSI={rsi:.0f} overbought, SMA={sma:.4f})")
        ctx.buy_once_per_candle("DOWN", 20)


# ╔══════════════════════════════════════════════════════════════════════════════╗
# ║  Strategy 8 — Order Book Imbalance Detector                                 ║
# ║                                                                             ║
# ║  Track bid:ask volume ratio in real-time. When bids on UP are 3× asks       ║
# ║  (or vice versa), smart money is positioning there. Follow the imbalance.   ║
# ╚══════════════════════════════════════════════════════════════════════════════╝

def strategy_8_orderbook_imbalance(ctx):
    ob = ctx.orderbook
    if ob is None:
        return
    try:
        ob.refresh()
    except Exception:
        return
    up_book = ob.up
    down_book = ob.down
    if up_book is None or down_book is None:
        return
    bids = up_book.bids[:10] if up_book.bids else []
    asks = down_book.asks[:10] if down_book.asks else []
    if not bids or not asks:
        return
    bid_vol = sum(b.size for b in bids)
    ask_vol = sum(a.size for a in asks)
    if bid_vol == 0 or ask_vol == 0:
        return
    ratio = bid_vol / ask_vol
    up, down = ctx.price.up, ctx.price.down
    if ratio > 3.0 and up < 0.50:
        log("08", f"BUY UP @ {up:.3f} (bid:ask={ratio:.1f}x, bids=${bid_vol:.0f} asks=${ask_vol:.0f})")
        ctx.buy_once_per_candle("UP", 10)
    elif ratio < 0.33 and down < 0.50:
        log("08", f"BUY DOWN @ {down:.3f} (bid:ask={ratio:.2f}x, bids=${bid_vol:.0f} asks=${ask_vol:.0f})")
        ctx.buy_once_per_candle("DOWN", 10)


# ╔══════════════════════════════════════════════════════════════════════════════╗
# ║  Strategy 9 — Maker Rebate Optimizer                                        ║
# ║                                                                             ║
# ║  Post GTD limit orders on BOTH sides at mid ± spread. Collect the           ║
# ║  bid-ask spread with zero maker fee (and earn 20% taker-fee rebates).       ║
# ║  Pull all quotes in the final 60s to avoid adverse selection from           ║
# ║  informed traders who know the resolution.                                  ║
# ╚══════════════════════════════════════════════════════════════════════════════╝

_MAKER_STATE: dict[str, dict] = {}

def strategy_9_maker_rebate(ctx):
    s = ctx.seconds_in
    name = ctx.name
    state = _MAKER_STATE.setdefault(name, {"up_id": None, "down_id": None})
    if s > 240:
        if state["up_id"] is not None:
            try:
                ctx._paper.cancel(state["up_id"])
            except Exception:
                pass
            state["up_id"] = None
        if state["down_id"] is not None:
            try:
                ctx._paper.cancel(state["down_id"])
            except Exception:
                pass
            state["down_id"] = None
        return
    mid = (ctx.price.up + ctx.price.down) / 2
    if mid < 0.30 or mid > 0.70:
        return
    up, down = ctx.price.up, ctx.price.down
    if state["up_id"] is None and up < 0.50:
        buy_price = round(up + 0.005, 3)
        order = ctx.limit("UP", buy_price, 5)
        if order:
            state["up_id"] = order.id
            log("09", f"LIMIT BUY UP @ {buy_price:.3f} (spot={up:.3f})")
    if state["down_id"] is None and down < 0.50:
        buy_price = round(down + 0.005, 3)
        order = ctx.limit("DOWN", buy_price, 5)
        if order:
            state["down_id"] = order.id
            log("09", f"LIMIT BUY DOWN @ {buy_price:.3f} (spot={down:.3f})")


# ╔══════════════════════════════════════════════════════════════════════════════╗
# ║  Main                                                                       ║
# ╚══════════════════════════════════════════════════════════════════════════════╝

def main():
    parser = argparse.ArgumentParser(description="Paper trade 6 Polymarket 5-min strategies")
    parser.add_argument("--balance", type=float, default=1000.0)
    parser.add_argument("--mode", default="simple", choices=["simple", "realistic"])
    args = parser.parse_args()

    threading.Thread(target=_btc_price_poller, args=(1.0,), daemon=True).start()

    if args.mode == "realistic":
        from polyalpha.trading.paper_config import get_paper_config_from_preset
        hpc = get_paper_config_from_preset("REALISTIC")
        hub = polyalpha.BotHub("BTC", "5m", default_balance=args.balance,
                               mode="custom", paper_config=hpc)
    else:
        hub = polyalpha.BotHub("BTC", "5m", default_balance=args.balance)

    # ── Register 6 strategies ──────────────────────────────────────────────

    @hub.strategy("02_convergence_sniper", balance=args.balance)
    def s2(ctx):
        strategy_2_convergence_sniper(ctx)

    @hub.strategy("04_cross_asset_momentum", balance=args.balance)
    def s4(ctx):
        strategy_4_cross_asset_momentum(ctx)

    @hub.strategy("05_flash_crash", balance=args.balance)
    def s5(ctx):
        strategy_5_flash_crash(ctx)

    @hub.strategy("06_vwap_rsi", balance=args.balance)
    def s6(ctx):
        strategy_6_vwap_rsi(ctx)

    @hub.strategy("08_orderbook_imbalance", balance=args.balance)
    def s8(ctx):
        if ctx.orderbook is not None:
            strategy_8_orderbook_imbalance(ctx)

    @hub.strategy("09_maker_rebate", balance=args.balance)
    def s9(ctx):
        strategy_9_maker_rebate(ctx)

    # ── Log startup ────────────────────────────────────────────────────────

    log("HUB", f"Starting 6 strategies on BTC 5m | balance=${args.balance:.0f} | mode={args.mode}")
    print()
    log("02", "Convergence Sniper  — buy near-certain winner at $0.10-0.25 in final 10s")
    log("04", "Cross-Asset Momen   — BTC momentum → directional entry before oracle reprices")
    log("05", "Flash Crash         — buy 30%+ drops in <5s when BTC hasn't moved")
    log("06", "VWAP/RSI            — RSI<30/70 + SMA crossover → mean reversion")
    log("08", "Orderbook Imbalance — bid:ask ratio >3:1 → follow the smart money")
    log("09", "Maker Rebate        — GTD limit orders both sides at mid±3¢, zero taker fee")
    print()
    log("HUB", "Press Ctrl+C to stop and print comparison report")
    print()

    # ── Periodic status ticker (every 30s) ─────────────────────────────
    @hub.every(30)
    def status_ticker(up, down):
        s_in = time.time() % 300
        with BTC_FEED_LOCK:
            btc_snap = list(BTC_FEED)
        btc_delta = ""
        if len(btc_snap) >= 5:
            dp = (btc_snap[-1] - btc_snap[-5]) / btc_snap[-5] * 100
            btc_delta = f" BTC_d={dp:+.2f}%"
        log("STATUS", f"UP={up:.3f} DOWN={down:.3f} | {s_in:.0f}s / 300s{btc_delta}")

    try:
        hub.run()
    except KeyboardInterrupt:
        hub.stop()
        print()
        log("HUB", "Generating P&L comparison across all 6 strategies...")
        report = hub.compare_variants()
        report.print()


if __name__ == "__main__":
    main()
