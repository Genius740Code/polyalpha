"""
Multi-wallet paper trading example.

This example demonstrates how to use multiple paper trading wallets
with different selection strategies.

Usage
-----
    python examples/multi_wallet_paper.py
    python examples/multi_wallet_paper.py --strategy round_robin
    python examples/multi_wallet_paper.py --strategy balance_based
"""

import argparse
import sys
import os

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))
import polyalpha
from polyalpha.trading.wallet import WalletManager, PaperWallet, WalletSelectionStrategy

parser = argparse.ArgumentParser(description="polyalpha multi-wallet paper trading")
parser.add_argument("--asset", default="BTC", help="BTC | ETH | SOL | XRP | DOGE")
parser.add_argument("--timeframe", default="5m", help="5m | 15m | 1h | 4h | 24h")
parser.add_argument("--side", default="UP", help="UP | DOWN")
parser.add_argument("--amount", default=10.0, type=float, help="USDC per trade")
parser.add_argument("--trades", default=5, type=int, help="Number of trades to execute")
parser.add_argument("--strategy", default="round_robin", 
                   choices=["round_robin", "balance_based", "random"],
                   help="Wallet selection strategy")
args = parser.parse_args()

print("="*70)
print("MULTI-WALLET PAPER TRADING EXAMPLE")
print("="*70)
print(f"Asset: {args.asset} {args.timeframe}")
print(f"Side: {args.side}")
print(f"Amount per trade: ${args.amount:.2f}")
print(f"Number of trades: {args.trades}")
print(f"Selection strategy: {args.strategy}")
print("="*70)
print()

# ── 1. Create multiple paper wallets ─────────────────────────────────────────────

print("Creating paper wallets...")
wallet_manager = WalletManager()

# Create wallets with different balances and strategies
wallet_configs = [
    ("conservative", 50.0),
    ("balanced", 100.0),
    ("aggressive", 200.0),
]

for wallet_id, balance in wallet_configs:
    wallet = PaperWallet(wallet_id=wallet_id, balance=balance)
    wallet_manager.add_wallet(wallet)
    print(f"  Created wallet '{wallet_id}' with ${balance:.2f}")

print()

# ── 2. Set wallet selection strategy ─────────────────────────────────────────────

strategy_map = {
    "round_robin": WalletSelectionStrategy.ROUND_ROBIN,
    "balance_based": WalletSelectionStrategy.BALANCE_BASED,
    "random": WalletSelectionStrategy.RANDOM,
}

wallet_manager.set_selection_strategy(strategy_map[args.strategy])
print(f"Wallet selection strategy: {args.strategy}")
print()

# ── 3. Initialize client with multi-wallet support ────────────────────────────────

client = polyalpha.Client(log_level="INFO")
client.paper.enable_multi_wallet(wallet_manager)

print("Multi-wallet mode enabled")
print()

# ── 4. Display initial wallet summary ─────────────────────────────────────────────

print("Initial wallet summary:")
summary = client.paper.wallets.get_per_wallet_summary()
for wallet_id, stats in summary.items():
    print(f"  {wallet_id}: ${stats['balance']:.2f}")
print()

# ── 5. Discover market ─────────────────────────────────────────────────────────

print(f"Finding {args.asset} {args.timeframe} market…")
market = client.markets.latest(args.asset, args.timeframe)
print(f"  {market.question}")
print(f"  UP={market.up_price:.3f}  DOWN={market.down_price:.3f}")
print()

# ── 6. Execute trades across wallets ─────────────────────────────────────────────

print(f"Executing {args.trades} trades using {args.strategy} strategy...")
print()

for i in range(args.trades):
    # Get the wallet that will be used for this trade
    wallet = client.paper.wallets.select_wallet()
    
    print(f"Trade {i+1}/{args.trades}: Using wallet '{wallet.wallet_id}' (${wallet.balance:.2f})")
    
    # Place the order
    try:
        order = client.paper.buy(market, side=args.side, amount=args.amount)
        print(f"  ✅ Filled: {order.shares:.4f} shares @ {order.price:.4f} (fee: ${order.fee:.4f})")
    except Exception as e:
        print(f"  ❌ Error: {e}")
    
    print()

# ── 7. Display final wallet summary ───────────────────────────────────────────────

print("="*70)
print("FINAL WALLET SUMMARY")
print("="*70)

print("\nPer-wallet summary:")
summary = client.paper.wallets.get_per_wallet_summary()
for wallet_id, stats in summary.items():
    print(f"  {wallet_id}:")
    print(f"    Balance: ${stats['balance']:.2f}")
    print(f"    Positions: {stats['total_positions']}")
    print(f"    Orders: {stats['total_orders']}")
    print(f"    P&L: ${stats['total_pnl']:.2f}")
    print()

print("Aggregated summary:")
agg_summary = client.paper.wallets.get_aggregated_summary()
print(f"  Total wallets: {agg_summary['total_wallets']}")
print(f"  Total balance: ${agg_summary['total_balance']:.2f}")
print(f"  Total positions: {agg_summary['total_positions']}")
print(f"  Total orders: {agg_summary['total_orders']}")
print(f"  Total P&L: ${agg_summary['total_pnl']:.2f}")
print()

# ── 8. Display positions ─────────────────────────────────────────────────────────

print("Current positions:")
positions = client.paper.positions()
if positions:
    for pos in positions:
        print(f"  {pos.slug} {pos.side}: {pos.shares:.4f} shares @ {pos.avg_price:.4f} (P&L: ${pos.pnl:.2f})")
else:
    print("  No open positions")
print()

print("="*70)
print("Example complete")
print("="*70)
