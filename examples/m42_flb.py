#!/usr/bin/env python3
"""
M42 — FLB Sweet Spot Scaler
----------------------------
Chainlink-driven Polymarket scalper.

Logic
  1. Track Chainlink BTC/USD price in a rolling 60-second window.
  2. If CL BTC moves > 0.12 % in 60 s, identify the "favourite" (YES on
     up-move, NO on down-move).
  3. If the favourite is priced between 65–79 ¢, buy that side.

Usage
-----
    python examples/m42_flb.py                          # paper, 15m
    python examples/m42_flb.py --timeframe 5m           # paper, 5m
    python examples/m42_flb.py --balance 200             # paper $200
    python examples/m42_flb.py --real                    # real-money
    python examples/m42_flb.py --db-path m42.db          # custom db path

Requires .env with:
    TELEGRAM_BOT_TOKEN=...
    TELEGRAM_CHAT_ID=...
    POLYALPHA_DB_PATH=m42.db        # optional, can use --db-path instead
"""

from __future__ import annotations

import argparse
import logging
import os
import time
from collections import deque

from dotenv import load_dotenv

import polyalpha

logger = logging.getLogger("m42")

# ── Defaults ──────────────────────────────────────────────────────────────────

ASSET = "BTC"
TIMEFRAME = "15m"
BALANCE = 100.0
CL_WINDOW_S = 60
CL_THRESHOLD_PCT = 0.12
SWEET_MIN = 0.65
SWEET_MAX = 0.79
ORDER_SIZE_PCT = 20  # % of balance per trade
COOLDOWN_S = 300  # seconds between entries on the same side
DB_PATH = "m42_trades.db"


def _parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser(description="M42 — FLB Sweet Spot Scaler")
    p.add_argument("--paper", action="store_true", default=True)
    p.add_argument("--real", action="store_true")
    p.add_argument("--asset", default=ASSET, help=f"Asset (default: {ASSET})")
    p.add_argument(
        "--timeframe", default=TIMEFRAME, help=f"Timeframe (default: {TIMEFRAME})"
    )
    p.add_argument(
        "--balance", type=float, default=BALANCE, help=f"Balance (default: {BALANCE})"
    )
    p.add_argument(
        "--db-path",
        default=None,
        help=f"Database path (default: {DB_PATH} or $POLYALPHA_DB_PATH)",
    )
    p.add_argument(
        "--cl-threshold",
        type=float,
        default=CL_THRESHOLD_PCT,
        help=f"CL 60s change threshold %% (default: {CL_THRESHOLD_PCT})",
    )
    p.add_argument("--verbose", "-v", action="store_true")
    args = p.parse_args()
    if args.real:
        args.paper = False
    return args


def _resolve_db_path(args_db_path: str | None) -> str | None:
    if args_db_path:
        return args_db_path
    env_path = os.environ.get("POLYALPHA_DB_PATH")
    if env_path:
        return env_path
    return DB_PATH


def _format_pnl(pnl: float) -> str:
    emoji = "🟢" if pnl >= 0 else "🔴"
    return f"{emoji} ${pnl:+.2f}"


def main() -> None:
    load_dotenv()
    args = _parse_args()

    level = logging.DEBUG if args.verbose else logging.INFO
    logging.basicConfig(
        level=level,
        format="%(asctime)s [%(levelname)-7s] %(name)s: %(message)s",
        datefmt="%H:%M:%S",
    )

    db_path = _resolve_db_path(args.db_path)

    bot = polyalpha.Bot(
        args.asset,
        args.timeframe,
        balance=args.balance,
        paper=args.paper,
        db_path=db_path,
    )

    cl_prices: deque[tuple[float, float]] = deque(maxlen=500)
    last_entry: dict[str, float] = {}
    stats = {"entries": 0, "total_pnl": 0.0, "wins": 0, "losses": 0}

    # ── Telegram helper ─────────────────────────────────────────────────────
    def _tg(msg: str) -> None:
        tg = getattr(bot, "_telegram", None)
        if tg:
            try:
                tg.send_custom(msg)
            except Exception as e:
                logger.debug("Telegram send failed: %s", e)

    mode = "REAL" if args.real else "PAPER"
    _tg(
        f"🤖 <b>M42 FLB Sweet Spot Scaler</b>\n"
        f"Mode: {mode}\n"
        f"Asset: {args.asset} | TF: {args.timeframe}\n"
        f"Balance: ${args.balance:.0f}\n"
        f"CL threshold: {args.cl_threshold}%\n"
        f"Sweet spot: {SWEET_MIN}–{SWEET_MAX}¢\n"
        f"DB: {db_path}"
    )

    @bot.on_tick
    def m42(ctx: polyalpha.TickContext) -> None:
        now = time.time()

        # ── 1. Track Chainlink price ────────────────────────────────────────
        if ctx.chainlink and ctx.chainlink.last_price:
            cl_prices.append((now, ctx.chainlink.last_price))

        while cl_prices and now - cl_prices[0][0] > 90:
            cl_prices.popleft()

        if len(cl_prices) < 5:
            return

        # ── 2. Compute 60 s CL change ───────────────────────────────────────
        target_ts = now - CL_WINDOW_S
        price_60s = cl_prices[0][1]
        for ts, p in cl_prices:
            if ts >= target_ts:
                price_60s = p
                break
            price_60s = p

        current_price = cl_prices[-1][1]
        if not current_price or not price_60s:
            return

        change_pct = ((current_price - price_60s) / price_60s) * 100

        # ── 3. Threshold check ──────────────────────────────────────────────
        if abs(change_pct) < args.cl_threshold:
            return

        # ── 4. Favourite side + sweet-spot check ────────────────────────────
        side = "UP" if change_pct > 0 else "DOWN"
        fav_price = ctx.price.up if side == "UP" else ctx.price.down

        if not (SWEET_MIN <= fav_price <= SWEET_MAX):
            return

        # ── 5. Per-side cooldown ────────────────────────────────────────────
        if side in last_entry and now - last_entry[side] < COOLDOWN_S:
            return

        # ── 6. Enter ────────────────────────────────────────────────────────
        stats["entries"] += 1
        amount = args.balance * ORDER_SIZE_PCT / 100
        ctx.buy(side, amount)
        last_entry[side] = now

        msg = (
            f"M42 ENTER {side:>4} @ {fav_price:.2f}¢ "
            f"| CL Δ: {change_pct:+.2f}% "
            f"| CL ${current_price:,.0f}"
        )
        logger.info(msg)
        print(msg)

        _tg(
            f"⚡ <b>M42 ENTER {side}</b>\n"
            f"Price: {fav_price:.2f}¢\n"
            f"Amount: ${amount:.0f}\n"
            f"CL Δ: {change_pct:+.2f}% (${current_price:,.0f})"
        )

    @bot.onresolve
    def on_resolve(pos) -> None:
        pnl = pos.pnl or 0.0
        stats["total_pnl"] += pnl
        if pnl >= 0:
            stats["wins"] += 1
        else:
            stats["losses"] += 1

        msg = (
            f"M42 RESOLVE {pos.side:>4} → {pos.outcome:>4} "
            f"| PnL: {_format_pnl(pnl)} "
            f"| Entry: ${pos.entry_price:.2f}¢"
        )
        logger.info(msg)
        print(msg)

    # ── Run ──────────────────────────────────────────────────────────────────
    try:
        bot.run()
    except KeyboardInterrupt:
        logger.info("M42 stopped by user")
        final = stats
        summary = (
            f"📊 <b>M42 Session Summary</b>\n"
            f"Entries: {final['entries']}\n"
            f"Wins: {final['wins']} | Losses: {final['losses']}\n"
            f"Total PnL: {_format_pnl(final['total_pnl'])}\n"
            f"DB: {db_path}"
        )
        print(summary.replace("<b>", "").replace("</b>", ""))
        _tg(summary)
    except Exception as exc:
        logger.exception("M42 fatal: %s", exc)
        _tg(f"💥 <b>M42 Fatal Error</b>\n{exc}")
        raise


if __name__ == "__main__":
    main()
