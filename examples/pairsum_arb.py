"""
Cross-asset pair-sum scanner — paper trading bot
---------------------------------------------------
IMPORTANT — this is NOT risk-free arbitrage.

The original pair-sum arb works because within ONE market, UP and DOWN are the
two outcomes of the SAME resolution event — exactly one pays $1, the other $0.
Buying both when UP+DOWN <= threshold locks in a spread no matter what happens.

This script instead scans CROSS-asset combos too — e.g. BTC-UP + SOL-DOWN,
ETH-UP + XRP-DOWN, etc. These are two INDEPENDENT markets with unrelated
resolution outcomes. There's no shared event tying them together, so a low
combined price here is NOT a locked-in payout — it's a directional bet on two
unrelated assets that happens to look cheap. Both legs can lose. Treat any
hits from this scanner as speculative pairs ideas to review, not guaranteed
profit.

Usage:
    python cross_pairsum_scan.py --assets BTC ETH SOL XRP DOGE BNB HYPE \
        --timeframe 5m --threshold 0.97 --amount 10 --balance 500
"""

import argparse
import itertools
import threading
import time
from datetime import datetime, timezone

import polyalpha


def log(msg: str) -> None:
    print(f"[{datetime.now(timezone.utc).strftime('%H:%M:%S')}] {msg}")


def run(assets, timeframe: str, threshold: float, amount: float, balance: float) -> None:
    client = polyalpha.Client(balance=balance)

    markets = {}
    streams = {}
    prices = {}  # asset -> {"up": float, "down": float}
    lock = threading.Lock()

    for asset in assets:
        try:
            market = client.markets.latest(asset, timeframe)
        except polyalpha.MarketNotFound as exc:
            log(f"Skipping {asset}: {exc}")
            continue
        markets[asset] = market
        prices[asset] = {"up": market.up_price, "down": market.down_price}
        log(f"Loaded {asset}: {market.slug}")

    if len(markets) < 2:
        log("Need at least 2 valid assets to scan cross-asset combos. Exiting.")
        return

    # All (asset, side) legs, e.g. (BTC, up), (BTC, down), (SOL, up)...
    legs = [(a, side) for a in markets for side in ("up", "down")]
    # All cross-asset leg pairs (skip same-asset — that's the same-market arb, not this scanner)
    combos = [
        (a1, s1, a2, s2)
        for (a1, s1), (a2, s2) in itertools.combinations(legs, 2)
        if a1 != a2
    ]
    log(f"Scanning {len(combos)} cross-asset combos across {len(markets)} assets "
        f"for combined price <= {threshold}")

    EXECUTION_DELAY = 2.0  # seconds between trigger and actual buy — re-checks live price at fill time
    SCAN_COOLDOWN = 0.5    # min gap between opportunity scans (just a rate limiter, not execution delay)
    fired_pairs = set()      # combos already traded or already attempted — one shot per combo per run
    locked_assets = set()    # assets currently committed to an open (or in-flight) position
    last_scan = {"t": 0.0}
    market_closed = {"any": False}

    def execute_after_delay(a1, s1, a2, s2, trigger_p1, trigger_p2):
        log(f"Waiting {EXECUTION_DELAY:.0f}s before filling {a1}-{s1.upper()} + {a2}-{s2.upper()}...")
        time.sleep(EXECUTION_DELAY)

        with lock:
            snapshot = {a: dict(p) for a, p in prices.items()}
        p1_now = snapshot.get(a1, {}).get(s1)
        p2_now = snapshot.get(a2, {}).get(s2)
        moved = ""
        if p1_now is not None and p2_now is not None:
            moved = (f"  (was {trigger_p1:.4f}+{trigger_p2:.4f}={trigger_p1+trigger_p2:.4f} "
                     f"at trigger, now {p1_now:.4f}+{p2_now:.4f}={p1_now+p2_now:.4f})")
        log(f"Filling now{moved}")

        try:
            o1 = client.paper.buy(markets[a1], side=s1.upper(), amount=amount)
            o2 = client.paper.buy(markets[a2], side=s2.upper(), amount=amount)
            log(f"Bought {a1}-{s1.upper()} ${amount} @ {o1.price:.4f} -> {o1.shares:.2f} shares")
            log(f"Bought {a2}-{s2.upper()} ${amount} @ {o2.price:.4f} -> {o2.shares:.2f} shares")
            log(f"Balance remaining: ${client.paper.balance:.2f}")
            # success — keep both assets locked, position stays open
        except polyalpha.InsufficientBalance as exc:
            log(f"Skipped {a1}/{a2} combo — insufficient balance: {exc}")
            with lock:
                locked_assets.discard(a1)
                locked_assets.discard(a2)
        except Exception as exc:
            log(f"Trade attempt failed for {a1}/{a2}: {exc}")
            with lock:
                locked_assets.discard(a1)
                locked_assets.discard(a2)

    def check_combos():
        now = time.monotonic()
        if now - last_scan["t"] < SCAN_COOLDOWN:
            return
        last_scan["t"] = now

        with lock:
            snapshot = {a: dict(p) for a, p in prices.items()}

            for (a1, s1, a2, s2) in combos:
                key = (a1, s1, a2, s2)
                if key in fired_pairs:
                    continue
                # one open position per market: skip if either asset is already committed
                # elsewhere (e.g. XRP already locked into a BTC combo can't also join a SOL combo)
                if a1 in locked_assets or a2 in locked_assets:
                    continue
                p1 = snapshot.get(a1, {}).get(s1)
                p2 = snapshot.get(a2, {}).get(s2)
                if p1 is None or p2 is None:
                    continue
                pair_sum = p1 + p2
                if pair_sum <= threshold:
                    log(f"CROSS-ASSET HIT: {a1}-{s1.upper()} ({p1:.4f}) + "
                        f"{a2}-{s2.upper()} ({p2:.4f}) = {pair_sum:.4f} <= {threshold}")
                    fired_pairs.add(key)
                    locked_assets.add(a1)
                    locked_assets.add(a2)
                    threading.Thread(
                        target=execute_after_delay,
                        args=(a1, s1, a2, s2, p1, p2),
                        daemon=True,
                    ).start()
                    return  # one trigger per scan keeps things simple/readable

    def make_price_handler(asset):
        def on_price(up: float, down: float):
            with lock:
                prices[asset] = {"up": up, "down": down}
            check_combos()
        return on_price

    def make_close_handler(asset):
        def on_close():
            log(f"{asset} market closed.")
            market_closed["any"] = True
        return on_close

    for asset, market in markets.items():
        stream = client.stream(market)
        client.paper.attach_stream(stream, market)
        stream.on("price")(make_price_handler(asset))
        stream.on("close")(make_close_handler(asset))
        stream.on("connect")(lambda a=asset: log(f"{a} stream connected."))
        stream.on("error")(lambda exc, a=asset: log(f"{a} stream error: {exc}"))
        streams[asset] = stream

    for stream in streams.values():
        stream.start(background=True)

    try:
        while not market_closed["any"]:
            time.sleep(2)
    except KeyboardInterrupt:
        log("Interrupted by user.")
    finally:
        for stream in streams.values():
            stream.stop()
        print()
        log("Final paper trading summary:")
        client.paper.summary()


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Cross-asset pair-sum scanner (speculative, not risk-free arb)")
    parser.add_argument("--assets", nargs="+", default=["BTC", "ETH", "SOL", "XRP", "DOGE", "BNB", "HYPE"])
    parser.add_argument("--timeframe", default="5m")
    parser.add_argument("--threshold", type=float, default=0.97)
    parser.add_argument("--amount", type=float, default=10.0)
    parser.add_argument("--balance", type=float, default=500.0)
    args = parser.parse_args()

    run(args.assets, args.timeframe, args.threshold, args.amount, args.balance)