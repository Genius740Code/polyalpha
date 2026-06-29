"""
Sniper bot with technical analysis example.

This example demonstrates how to integrate technical analysis
with the Sniper bot for conditional trading logic.

The bot will only enter trades when technical conditions are met,
such as RSI > 40 AND price above SMA20.

Usage
-----
    python examples/sniper_ta.py
    python examples/sniper_ta.py --asset ETH --timeframe 15m
    python examples/sniper_ta.py --entry 0.90 --rsi-threshold 40
"""

import argparse
import sys
import os

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))
import polyalpha

parser = argparse.ArgumentParser(description="polyalpha Sniper with TA")
parser.add_argument("--asset", default="BTC", help="BTC | ETH | SOL | XRP | DOGE")
parser.add_argument("--timeframe", default="5m", help="5m | 15m | 1h | 4h | 24h")
parser.add_argument("--side", default="UP", help="UP | DOWN")
parser.add_argument("--entry", type=float, default=0.92, help="Entry threshold (0-1)")
parser.add_argument("--exit", type=float, default=0.88, help="Exit threshold (0-1)")
parser.add_argument("--window", type=int, default=35, help="Trading window seconds")
parser.add_argument("--amount", type=float, default=20.0, help="USDC per trade")
parser.add_argument("--balance", type=float, default=100.0, help="Starting paper balance")
parser.add_argument("--max-trades", type=int, default=None, help="Stop after N trades")
parser.add_argument("--max-losses", type=int, default=3, help="Pause after N consecutive losses")
parser.add_argument("--data-source", default="binance", help="binance | chainlink")
parser.add_argument("--rsi-threshold", type=float, default=40, help="RSI threshold for entry")
parser.add_argument("--sma-period", type=int, default=20, help="SMA period for entry")
parser.add_argument("--log-level", default="INFO", help="DEBUG | INFO | WARNING")
args = parser.parse_args()

# Initialize client
client = polyalpha.Client(
    balance=args.balance,
    log_level=args.log_level,
)

print(f"Paper balance: ${client.paper.balance:.2f}\n")

# Data source notice
print("="*70)
print("DATA SOURCE NOTICE")
print("="*70)
print("Polymarket uses Chainlink oracles for price feeds.")
print(f"Using {args.data_source} data source for technical analysis.")
print("Price discrepancies may occur between data source and Polymarket.")
print("For best accuracy, use Chainlink data when available.")
print("="*70 + "\n")

# Set up data feed for technical analysis
ta_config = polyalpha.DataFeedConfig(
    source=args.data_source,
    timeframe=args.timeframe,
    lookback_periods=200,
)

print("Fetching technical analysis data...")
try:
    feed = polyalpha.DataFeed(ta_config)
    ta_data = feed.fetch(args.asset)
    print(f"✓ Fetched {len(ta_data)} candles for {args.asset}\n")
except Exception as exc:
    print(f"✗ Error fetching TA data: {exc}")
    print("Continuing without technical analysis...")
    ta_data = None

# Create Sniper configuration
config = polyalpha.bots.sniper.SniperConfig(
    asset=args.asset,
    timeframe=args.timeframe,
    side=args.side,
    entry_price=args.entry,
    exit_price=args.exit,
    window_seconds=args.window,
    amount=args.amount,
    max_trades=args.max_trades,
    max_consecutive_losses=args.max_losses,
    log_level=args.log_level,
    log_trades=True,
    log_prices=False,
)

# Create Sniper bot
sniper = polyalpha.Sniper(client, config)

# Technical analysis check function
def check_ta_conditions():
    """Check if technical conditions are met for entry."""
    if ta_data is None:
        return True  # No TA data, allow entry

    try:
        indicators = polyalpha.IndicatorCalculator(ta_data)
        signals = polyalpha.SignalGenerator(indicators)

        # Check RSI
        rsi_ok = signals.rsi_above(args.rsi_threshold)
        print(f"  TA Check: RSI {args.rsi_threshold} threshold: {'✓' if rsi_ok else '✗'}")

        # Check SMA
        sma_ok = signals.price_above_sma(args.sma_period)
        print(f"  TA Check: Price > SMA({args.sma_period}): {'✓' if sma_ok else '✗'}")

        # Both conditions must be met
        return rsi_ok and sma_ok

    except Exception as exc:
        print(f"  TA Check Error: {exc}")
        return True  # Allow entry on error

# Register event callbacks
@sniper.on("market_found")
def on_market_found(market):
    print(f"\n🎯 Market found: {market.question}")
    print(f"   Slug: {market.slug}")
    print(f"   UP={market.up_price:.4f}  DOWN={market.down_price:.4f}")

@sniper.on("window_enter")
def on_window_enter(market):
    print(f"\n⏱️  Entering trading window ({args.window}s before close)")
    print(f"   Entry threshold: {args.entry:.4f}")
    print(f"   Exit threshold: {args.exit:.4f}")

    # Check technical conditions
    print("\n📊 Technical Analysis Check:")
    ta_ok = check_ta_conditions()
    if ta_ok:
        print("   ✓ Technical conditions met - ready to enter")
    else:
        print("   ✗ Technical conditions NOT met - will skip entry")

@sniper.on("entry")
def on_entry(order):
    print(f"\n✅ Order filled: {order.side} @ {order.price:.4f}")
    print(f"   Shares: {order.shares:.4f}")
    print(f"   Fee: ${order.fee:.4f}")

@sniper.on("exit")
def on_exit(reason):
    print(f"\n❌ Order cancelled: {reason}")

@sniper.on("resolve")
def on_resolve(outcome, pnl):
    if outcome == "WON":
        print(f"\n🏆 WON: +${pnl:.2f}")
    else:
        print(f"\n💔 LOST: ${pnl:.2f}")

    # Print running stats
    stats = sniper.stats
    print(f"   Stats: {stats.total_trades} trades, {stats.win_rate:.1f}% win rate, ${stats.total_pnl:.2f} P&L")

@sniper.on("rollover")
def on_rollover(next_market):
    print(f"\n🔄 Rolling over to next market...")

@sniper.on("error")
def on_error(exc):
    print(f"\n⚠️  Error: {exc}")

@sniper.on("stop")
def on_stop(reason):
    print(f"\n🛑 Sniper stopped: {reason}")

    # Print final statistics
    stats = sniper.stats
    print("\n" + "="*60)
    print("FINAL STATISTICS")
    print("="*60)
    print(f"Total trades: {stats.total_trades}")
    print(f"Wins: {stats.wins}")
    print(f"Losses: {stats.losses}")
    print(f"Win rate: {stats.win_rate:.1f}%")
    print(f"Total P&L: ${stats.total_pnl:.2f}")
    print(f"Avg entry price: {stats.avg_entry_price:.4f}")
    if stats.avg_exit_price > 0:
        print(f"Avg exit price: {stats.avg_exit_price:.4f}")
    print("="*60)

# Start the bot
print("="*60)
print("SNIPER BOT WITH TECHNICAL ANALYSIS STARTING")
print("="*60)
print(f"Asset: {args.asset} {args.timeframe}")
print(f"Side: {args.side}")
print(f"Entry threshold: {args.entry:.4f}")
print(f"Exit threshold: {args.exit:.4f}")
print(f"Window: {args.window}s")
print(f"Amount: ${args.amount:.2f}")
print(f"Max trades: {args.max_trades or 'unlimited'}")
print(f"Max consecutive losses: {args.max_losses or 'unlimited'}")
print(f"\nTechnical Analysis:")
print(f"  Data source: {args.data_source}")
print(f"  RSI threshold: {args.rsi_threshold}")
print(f"  SMA period: {args.sma_period}")
print("="*60)
print("\nPress Ctrl+C to stop\n")

try:
    sniper.run()
except KeyboardInterrupt:
    sniper.stop("manual")
except Exception as exc:
    print(f"\nFatal error: {exc}")
    sniper.stop("error")
    raise
