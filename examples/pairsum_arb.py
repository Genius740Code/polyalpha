"""
Pair-sum arbitrage — paper trading bot
---------------------------------------
Logic: on a Polymarket UP/DOWN market, UP + DOWN should equal ~1.00
(minus fees) because exactly one side resolves to $1. If UP+DOWN <= THRESHOLD,
buying both legs locks in a risk-free spread at settlement (before fees).

Usage:
    python pairsum_arb.py --asset BTC --timeframe 5m --threshold 0.97 --amount 10 --balance 500
"""

import argparse
import time
from datetime import datetime

import polyalpha


def log(msg: str) -> None:
    print(f"[{datetime.utcnow().strftime('%H:%M:%S')}] {msg}")


def run(asset: str, timeframe: str, threshold: float, amount: float, balance: float) -> None:
    client = polyalpha.Client(balance=balance)

    market = client.markets.latest(asset, timeframe)
    log(f"Market: {market.slug}  (ends {market.end_time})")
    log(f"Watching pair-sum <= {threshold}  |  amount/leg=${amount}  |  balance=${balance}")

    stream = client.stream(market)
    client.paper.attach_stream(stream, market)

    TRADE_COOLDOWN = 2.0  # seconds between trades
    state = {"last_trade_time": 0.0}

    @stream.on("connect")
    def on_connect():
        log("Stream connected.")

    @stream.on("price")
    def on_price(up: float, down: float):
        pair_sum = up + down
        print(f"\rUP={up:.4f}  DOWN={down:.4f}  SUM={pair_sum:.4f}", end="", flush=True)

        now = time.monotonic()
        if now - state["last_trade_time"] < TRADE_COOLDOWN:
            return

        if pair_sum <= threshold:
            print()  # newline after the \r status line
            log(f"ARB TRIGGERED: sum={pair_sum:.4f} <= {threshold}")
            state["last_trade_time"] = now  # set cooldown immediately to avoid double-fire on fast ticks
            try:
                up_order = client.paper.buy(market, side="UP", amount=amount)
                down_order = client.paper.buy(market, side="DOWN", amount=amount)
                log(f"Bought UP   ${amount} @ {up_order.price:.4f}  -> {up_order.shares:.2f} shares (fee ${up_order.fee:.4f})")
                log(f"Bought DOWN ${amount} @ {down_order.price:.4f}  -> {down_order.shares:.2f} shares (fee ${down_order.fee:.4f})")
                total_cost = up_order.amount + down_order.amount + up_order.fee + down_order.fee
                log(f"Total cost: ${total_cost:.4f}  |  Balance remaining: ${client.paper.balance:.2f}")
            except polyalpha.InsufficientBalance as exc:
                log(f"Skipped — insufficient balance: {exc}")

    @stream.on("close")
    def on_close():
        log("Market resolved/closed. Resolving paper positions...")

    @stream.on("error")
    def on_error(exc: Exception):
        log(f"Stream error: {exc}")

    stream.start(background=True)

    try:
        while not market.closed:
            time.sleep(2)
            # refresh market state periodically to detect close
            try:
                market = client.markets.get(market.slug)
            except polyalpha.MarketClosed:
                break
    except KeyboardInterrupt:
        log("Interrupted by user.")
    finally:
        stream.stop()
        print()
        log("Final paper trading summary:")
        client.paper.summary()


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Pair-sum arb paper trading bot")
    parser.add_argument("--asset", default="BTC", help="BTC, ETH, SOL, XRP, DOGE")
    parser.add_argument("--timeframe", default="5m", help="5m, 15m, 1h, 4h, 24h")
    parser.add_argument("--threshold", type=float, default=0.97, help="Fire when UP+DOWN <= this")
    parser.add_argument("--amount", type=float, default=10.0, help="USDC spent per leg")
    parser.add_argument("--balance", type=float, default=500.0, help="Paper trading starting balance")
    args = parser.parse_args()

    run(args.asset, args.timeframe, args.threshold, args.amount, args.balance)