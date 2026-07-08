"""
Paper trading example.

Usage
-----
    python examples/paper.py
    python examples/paper.py --side DOWN --amount 25
    python examples/paper.py --limit 0.92 --amount 20
    python examples/paper.py --rate-limit 10
    python examples/paper.py --fee-mode polymarket --category crypto
    python examples/paper.py --delay 2000 --slippage 0.05
"""

import argparse
import sys
import os

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))
import polyalpha

parser = argparse.ArgumentParser(description="polyalpha paper trading")
parser.add_argument("--asset",     default="BTC",   help="BTC | ETH | SOL | XRP | DOGE")
parser.add_argument("--timeframe", default="5m",    help="5m | 15m | 1h | 4h | 24h")
parser.add_argument("--side",      default="UP",    help="UP | DOWN")
parser.add_argument("--amount",    default=10.0,    type=float, help="USDC to spend")
parser.add_argument("--limit",     default=None,    type=float, help="Limit trigger price")
parser.add_argument("--balance",   default=100.0,   type=float, help="Starting paper balance")
parser.add_argument("--rate-limit", type=int, default=None, help="Max API requests per second (default: unlimited)")
parser.add_argument("--fee-mode", default="custom", choices=["polymarket", "custom", "zero"], help="Fee mode")
parser.add_argument("--category", default="crypto", help="Market category for polymarket fee mode")
parser.add_argument("--custom-fee", type=float, default=0.02, help="Custom fee rate (default: 0.02)")
parser.add_argument("--delay", type=int, default=0, help="Execution delay in milliseconds (default: 0)")
parser.add_argument("--slippage", type=float, default=0.0, help="Slippage percentage (default: 0.0)")
parser.add_argument("--fill-prob", type=float, default=1.0, help="Fill probability for limit orders (default: 1.0)")
parser.add_argument("--check-mode", default="continuous", help="Condition check mode: continuous, once, or integer N (default: continuous)")
parser.add_argument("--enable-rebates", action="store_true", help="Enable fee rebate tracking (default: enabled)")
parser.add_argument("--disable-rebates", action="store_true", help="Disable fee rebate tracking")
parser.add_argument("--custom-rebate-tiers", type=str, help="Custom rebate tiers as JSON string (e.g., '{\"0\":0.0,\"1000\":0.15,\"5000\":0.20}')")
args = parser.parse_args()

# Create paper trading configuration
from polyalpha.trading.paper import PaperConfig

# Parse check_mode - could be string or integer
check_mode = args.check_mode
if check_mode not in ("continuous", "once"):
    try:
        check_mode = int(check_mode)
    except ValueError:
        check_mode = "continuous"

# Parse custom rebate tiers if provided
rebate_tiers = None
if args.custom_rebate_tiers:
    import json
    try:
        rebate_tiers = json.loads(args.custom_rebate_tiers)
    except json.JSONDecodeError:
        print(f"Invalid JSON for custom-rebate-tiers: {args.custom_rebate_tiers}")
        print("Using default rebate tiers")
        rebate_tiers = None

# Determine if rebates are enabled
enable_rebates = not args.disable_rebates

config = PaperConfig(
    fee_mode=args.fee_mode,
    market_category=args.category,
    custom_fee_rate=args.custom_fee,
    execution_delay_ms=args.delay,
    slippage_pct=args.slippage,
    fill_probability=args.fill_prob,
    check_mode=check_mode,
    enable_rebates=enable_rebates,
    rebate_tiers=rebate_tiers,
)

client = polyalpha.Client(balance=args.balance, log_level="INFO", rate_limit=args.rate_limit, paper_config=config)

print(f"Paper balance: ${client.paper.balance:.2f}")
print(f"Fee mode: {config.fee_mode}")
if config.fee_mode == "polymarket":
    print(f"Market category: {config.market_category}")
elif config.fee_mode == "custom":
    print(f"Custom fee rate: {config.custom_fee_rate:.2%}")
if config.execution_delay_ms > 0:
    print(f"Execution delay: {config.execution_delay_ms}ms")
if config.slippage_pct > 0:
    print(f"Slippage: {config.slippage_pct:.2%}")
if config.fill_probability < 1.0:
    print(f"Fill probability: {config.fill_probability:.0%}")
if config.check_mode != "continuous":
    print(f"Check mode: {config.check_mode}")
if config.enable_rebates:
    print(f"Fee rebates: enabled")
    print(f"Maker rebate bonus: {config.maker_rebate_pct:.1%}")
else:
    print(f"Fee rebates: disabled")
print()

# ── 1. Discover market ─────────────────────────────────────────────────────────
print(f"Finding {args.asset} {args.timeframe} market…")
market = client.markets.latest(args.asset, args.timeframe)
print(f"  {market.question}")
print(f"  UP={market.up_price:.3f}  DOWN={market.down_price:.3f}\n")

# ── 2. Place order ─────────────────────────────────────────────────────────────
if args.limit:
    print(f"Placing limit {args.side} @ {args.limit} for ${args.amount:.2f}…")
    order = client.paper.limit(market, side=args.side, price=args.limit, amount=args.amount)
    print(f"  Order {order.id[:8]}  status={order.status}\n")
else:
    print(f"Placing market {args.side} for ${args.amount:.2f}…")
    order = client.paper.buy(market, side=args.side, amount=args.amount)
    print(f"  Filled {order.shares:.4f} shares @ {order.price:.3f}")
    print(f"  Fee: ${order.fee:.4f}  status={order.status}\n")

# ── 3. Stream prices + auto-fill limits ────────────────────────────────────────
stream = client.stream(market)
client.paper.attach_stream(stream, market)

@stream.on("connect")
def on_connect():
    print(f"Streaming {market.slug} — watching prices and pending limits.\n")

@stream.on("price")
def on_price(up: float, down: float):
    positions = client.paper.positions()
    for pos in positions:
        print(
            f"  {pos.side:<4}  price={pos.current_price:.4f}"
            f"  shares={pos.shares:.4f}  pnl=${pos.pnl:>+.4f}"
        )

@stream.on("close")
def on_close():
    print("\nMarket resolved.")
    outcome = input("Enter outcome (UP/DOWN): ").strip().upper()
    if outcome in ("UP", "DOWN"):
        client.paper.resolve(market, outcome)
    print()
    client.paper.summary()
    if config.enable_rebates:
        print()
        client.paper.fee_summary()
    sys.exit(0)

@stream.on("error")
def on_error(exc: Exception):
    print(f"Stream error: {exc}")

print("Streaming live (Ctrl+C to stop and print summary)\n")
try:
    stream.start()
except KeyboardInterrupt:
    print()
    client.paper.summary()
    if config.enable_rebates:
        print()
        client.paper.fee_summary()
