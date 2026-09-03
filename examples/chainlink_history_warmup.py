"""
Chainlink history — user chooses how much candle data to keep.

This example shows:
- User picks 10×1m, 50×1h, 20×1s candles (any mix)
- Unused timeframes are deleted automatically (pruned)
- Storage is SQLite WAL at ~/.polyalpha/chainlink.db — best for
  incremental tick→candle with concurrent reads (single file, ~4KB for
  minutes of data, crash-safe, no server).

Run:
    python examples/chainlink_history_warmup.py
    # with custom keep counts
    python examples/chainlink_history_warmup.py --keep 1m:10,1h:50,1s:20
"""

import time
import argparse
from pathlib import Path

import polyalpha
from polyalpha.history import ChainlinkHistoryConfig

def parse_keep(s: str) -> dict:
    out = {}
    for part in s.split(","):
        if not part.strip():
            continue
        tf, n = part.split(":")
        out[tf.strip()] = int(n.strip())
    return out

if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--keep", default="1m:10,1h:50,1s:20",
                        help="comma list tf:count e.g. 1m:10,1h:50,1s:20")
    parser.add_argument("--db", default="~/.polyalpha/chainlink.db")
    args = parser.parse_args()

    keep = parse_keep(args.keep)
    print(f"User keep choice: {keep}  db={args.db}")

    # Config — warmup == keep (block until enough closed candles)
    cfg = ChainlinkHistoryConfig(warmup=keep, db_path=args.db, block="wait")
    print(f"Timeframes will be {cfg.timeframes}  keep={cfg.keep}")
    print(f"Storage: SQLite WAL {Path(cfg.db_path).expanduser()} (WITHOUT ROWID, ~4KB per page, WAL concurrent)")

    # Bot that uses history — strat only fires when warm (EMA needs history)
    bot = polyalpha.Bot("BTC", "5m", balance=500, chainlink_history=cfg)

    @bot.on_warmup
    def on_warmup(status):
        # status e.g. {"1m":"7/10", "1h":"20/50", "1s":"20/20 ✅"}
        print(f"[warmup] {status}  — collecting Chainlink 1-s ticks → candles")

    @bot.on_tick
    def strat(ctx):
        # ctx.chainlink_history is the pruned, warm view
        # Flexible signatures: ema("1m",10) or ema("BTC","1m",10)
        # Only what user asked to keep exists; others were deleted
        if not ctx.chainlink_history.is_ready("1m", 10):
            return

        close = ctx.chainlink_history.close("1m")
        ema10 = ctx.chainlink_history.ema("1m", 10)
        rsi = ctx.chainlink_history.rsi("1m", 14)

        # Example: trade when price > EMA and RSI < 70
        print(f"[tick] close={close:.1f} ema10={ema10:.1f} rsi={rsi}  counts={ctx.chainlink_history.status(keep)}")

        if close and ema10 and close > ema10 and (rsi is None or rsi < 70):
            ctx.buy("UP", 10)

    print("Config is honest wall-time wait: 10×1m ≈10 min, 20×1s ≈20 s, 50×1h ≈50 h")
    print("Restart is instant: SQLite survives restarts, no re-warming needed.")
    print("Unused TFs are pruned: if you change --keep to '1m:10', 1h/1s rows are deleted.")

    # For demo, we run a short live block if you have network, else just show status
    # bot.run()
    print("\nDemo: querying current store without WS (read-only)...")
    try:
        from polyalpha import Client
        client = Client(chainlink_history=cfg.db_path)  # read-only
        if client.chainlink_history:
            print("client view status:", client.chainlink_history.status(keep))
            print("client candles 1m (latest 3):\n", client.chainlink_history.candles("1m", 3).to_string())
        client.close()
    except Exception as e:
        print(f"client read skipped: {e}")

    # Show pruning demo: switch to smaller keep
    print("\nPruning demo: if you now run with --keep 1m:5, the store will delete 1h/1s rows and trim 1m to 5")
