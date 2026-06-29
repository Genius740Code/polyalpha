"""
P&L Tracker example — performance monitoring and reporting.

This example demonstrates the Tracker utility, which provides
comprehensive P&L tracking, statistics, and reporting for
trading activities.

Features demonstrated:
- Syncing with paper engine state
- Generating summary reports
- Exporting to JSON and CSV
- Trade history analysis

Usage
-----
    python examples/tracker.py
    python examples/tracker.py --export-json trades.json
    python examples/tracker.py --export-csv trades.csv
"""

import argparse
import sys
import os

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))
import polyalpha

parser = argparse.ArgumentParser(description="polyalpha P&L Tracker")
parser.add_argument("--balance", type=float, default=100.0, help="Starting paper balance")
parser.add_argument("--export-json", type=str, default=None, help="Export to JSON file")
parser.add_argument("--export-csv", type=str, default=None, help="Export to CSV file")
parser.add_argument("--log-level", default="INFO", help="DEBUG | INFO | WARNING")
args = parser.parse_args()

# Initialize client
client = polyalpha.Client(balance=args.balance, log_level=args.log_level)

print(f"Paper balance: ${client.paper.balance:.2f}\n")

# Create tracker
tracker = polyalpha.Tracker(client)

# Sync with current state
print("Syncing with paper engine...")
tracker.sync()

# Print summary
tracker.summary()

# Export if requested
if args.export_json:
    tracker.export_json(args.export_json)
    print(f"\n✅ Exported to JSON: {args.export_json}")

if args.export_csv:
    tracker.export_csv(args.export_csv)
    print(f"\n✅ Exported to CSV: {args.export_csv}")

# Show individual trades
trades = tracker.trades()
if trades:
    print(f"\n📊 Trade History ({len(trades)} trades)")
    print("="*70)
    for i, trade in enumerate(trades, 1):
        print(f"{i}. {trade.market_slug} | {trade.side} | "
              f"{trade.entry_price:.4f} → ${trade.pnl:+.2f} ({trade.outcome})")
    print("="*70)
