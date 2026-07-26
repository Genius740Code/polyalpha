"""
Multi-wallet paper trading — round-robin and balance-based wallet selection.

Usage:
    python examples/multi_wallet_paper.py
"""
import polyalpha
from polyalpha.trading import PaperWallet, WalletManager

client = polyalpha.Client(balance=600)
market = client.markets.latest("BTC", "5m")

wallets = [
    PaperWallet(balance=100.0),
    PaperWallet(balance=200.0),
    PaperWallet(balance=300.0),
]

manager = WalletManager(wallets, strategy="round_robin")
client.paper.enable_multi_wallet(manager)

for i in range(5):
    side = "UP" if i % 2 == 0 else "DOWN"
    order = client.paper.buy(market, side=side, amount=15.0 + i * 5)
    print(f"Trade {i + 1}: wallet={order.wallet_id} side={order.side} amount={order.amount:.2f}")

client.paper.disable_multi_wallet()

manager.strategy = "balance_weighted"
client.paper.enable_multi_wallet(manager)

for i in range(3):
    order = client.paper.buy(market, side="UP", amount=20.0)
    print(f"Weighted {i + 1}: wallet={order.wallet_id} balance={order.wallet_balance:.2f}")

client.paper.disable_multi_wallet()
client.paper.summary()
