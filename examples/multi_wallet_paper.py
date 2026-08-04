"""
Multi-wallet paper trading — round-robin and balance-based wallet selection.

Usage:
    python examples/multi_wallet_paper.py
"""
import polyalpha
from polyalpha.trading.paper_config import get_paper_config_from_preset
from polyalpha.trading.wallet import (
    PaperWallet,
    WalletManager,
    WalletSelectionStrategy,
)

# Default PaperConfig allows only one position per market per wallet, which
# would block repeated buys on the same market. Raise the limit for the demo.
config = get_paper_config_from_preset("REALISTIC")
config.max_positions_per_market = 10
config.max_open_positions = 20

client = polyalpha.Client(balance=600)
market = client.markets.latest("BTC", "5m")

wallets = [
    PaperWallet(wallet_id="wallet1", balance=100.0, config=config),
    PaperWallet(wallet_id="wallet2", balance=200.0, config=config),
    PaperWallet(wallet_id="wallet3", balance=300.0, config=config),
]

manager = WalletManager(
    wallets={w.wallet_id: w for w in wallets},
    selection_strategy=WalletSelectionStrategy.ROUND_ROBIN,
)
client.paper.enable_multi_wallet(manager)

for i in range(5):
    side = "UP" if i % 2 == 0 else "DOWN"
    client.paper.buy(market, side=side, amount=15.0 + i * 5)

print("After round-robin (5 trades):")
for wid, summary in manager.get_per_wallet_summary().items():
    print(f"  {wid}: balance=${summary['balance']:.2f} positions={summary['total_positions']}")

client.paper.disable_multi_wallet()

manager.set_selection_strategy(WalletSelectionStrategy.BALANCE_BASED)
client.paper.enable_multi_wallet(manager)

for _ in range(3):
    client.paper.buy(market, side="UP", amount=20.0)

print("\nAfter balance-based (3 trades):")
for wid, summary in manager.get_per_wallet_summary().items():
    print(f"  {wid}: balance=${summary['balance']:.2f} positions={summary['total_positions']}")

client.paper.disable_multi_wallet()
client.paper.summary()
