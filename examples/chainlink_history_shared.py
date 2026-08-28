"""
Shared history — one recorder, one WS, one SQLite file → N BotHub strats + Client.

- One ChainlinkRecorder owns the WS + SQLite at ~/.polyalpha/chainlink.db
- All hub strats and notebook clients read the same DB (WAL concurrent)
- User chooses keep counts like {"1m":10, "1h":50, "1s":20}; same file, pruned

Run:
    python examples/chainlink_history_shared.py
"""

import polyalpha
from polyalpha.history import ChainlinkRecorder, ChainlinkHistoryConfig

# One writer for the whole process — owns WS + SQLite
shared = ChainlinkRecorder(
    db_path="~/.polyalpha/chainlink.db",
    timeframes=("1m", "1h", "1s"),
    warmup={"1m": 10, "1h": 2, "1s": 20},  # keep exactly these counts
)
shared.start("BTC", background=True)  # one WS only

hub = polyalpha.BotHub("BTC", "5m", chainlink_history=shared)

@hub.strategy("ema_daily")
def ema_strat(ctx):
    # ctx.chainlink_history is a view over the shared store (same DB)
    if not ctx.chainlink_history.is_ready("1m", 10):
        return
    ema = ctx.chainlink_history.ema("1m", 10)  # or ema("BTC","1m",10)
    close = ctx.chainlink_history.close("1m")
    if ema and close and close > ema:
        ctx.buy("UP", 10)

@hub.strategy("rsi_hourly")
def rsi_strat(ctx):
    # Different TF but same DB, same WS
    rsi = ctx.chainlink_history.rsi("1h", 14)
    if rsi is not None and rsi < 30:
        ctx.buy("DOWN", 10)

@hub.on_warmup
def warmup(status):
    print(f"[hub warming] {status}")

# Standalone read while hub runs — pure SQLite, no WS needed
client = polyalpha.Client(chainlink_history=shared)
print("client status (shared):", client.chainlink_history.status({"1m": 10, "1h": 2, "1s": 20}))
print("hub shares one WS, one DB — unused TFs pruned, file stays ~pages (SQLite WAL)")

# hub.run()  # blocking — one stream fans to both strats
print("Demo done — run hub.run() to trade live with shared history.")
