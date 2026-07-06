"""
Example demonstrating database persistence for paper trading.

This example shows how to:
1. Enable database persistence
2. Execute trades that are automatically saved
3. Load and analyze trades from the database
"""

from datetime import datetime, timezone
import polyalpha
from polyalpha.database import TradeDatabase

def main():
    print("=" * 60)
    print("POLYALPHA DATABASE PERSISTENCE EXAMPLE")
    print("=" * 60)
    
    # Example 1: Using database through the client
    print("\n1. Creating client with database persistence...")
    client = polyalpha.Client(balance=1000.0, db_path="example_trades.db")
    
    print(f"   Database enabled: {client.paper.database is not None}")
    print(f"   Database path: example_trades.db")
    
    # Example 2: Direct database access
    print("\n2. Direct database access...")
    db = TradeDatabase("example_trades.db")
    
    # Save a sample trade manually
    print("   Saving sample trade...")
    trade_id = db.save_trade(
        market_slug="btc-updown-5m-1751234700",
        market_id="sample-market-id-123",
        side="UP",
        entry_price=0.92,
        exit_price=None,
        amount=50.0,
        shares=52.5,
        fee=1.0,
        outcome="WON",
        pnl=5.0,
        timestamp=datetime.now(timezone.utc),
    )
    print(f"   Trade saved with ID: {trade_id}")
    
    # Save another trade
    print("   Saving another trade...")
    db.save_trade(
        market_slug="eth-updown-15m-1751234800",
        market_id="sample-market-id-456",
        side="DOWN",
        entry_price=0.88,
        exit_price=None,
        amount=30.0,
        shares=33.0,
        fee=0.6,
        outcome="LOST",
        pnl=-3.0,
        timestamp=datetime.now(timezone.utc),
    )
    
    # Example 3: Load trades
    print("\n3. Loading trades from database...")
    all_trades = db.load_all_trades()
    print(f"   Total trades in database: {len(all_trades)}")
    
    for trade in all_trades:
        print(f"   - {trade.market_slug} {trade.side} {trade.outcome} P&L=${trade.pnl:.2f}")
    
    # Example 4: Filter trades
    print("\n4. Filtering trades...")
    btc_trades = db.load_trades_by_asset("BTC")
    print(f"   BTC trades: {len(btc_trades)}")
    
    up_trades = db.load_trades_by_side("UP")
    print(f"   UP side trades: {len(up_trades)}")
    
    won_trades = db.load_trades_by_outcome("WON")
    print(f"   Winning trades: {len(won_trades)}")
    
    # Example 5: Get statistics
    print("\n5. Database statistics...")
    stats = db.get_statistics()
    print(f"   Total trades: {stats.total_trades}")
    print(f"   Wins: {stats.wins}")
    print(f"   Losses: {stats.losses}")
    print(f"   Win rate: {stats.win_rate:.1f}%")
    print(f"   Total P&L: ${stats.total_pnl:.2f}")
    print(f"   Total fees: ${stats.total_fees:.2f}")
    print(f"   Avg entry price: {stats.avg_entry_price:.4f}")
    print(f"   Avg P&L per trade: ${stats.avg_pnl_per_trade:.2f}")
    
    # Example 6: Enable/disable database on paper engine
    print("\n6. Enable/disable database on paper engine...")
    client2 = polyalpha.Client(balance=500.0)
    print(f"   Database enabled (initial): {client2.paper.database is not None}")
    
    client2.paper.enable_database("trades2.db")
    print(f"   Database enabled (after enable): {client2.paper.database is not None}")
    
    client2.paper.disable_database()
    print(f"   Database enabled (after disable): {client2.paper.database is not None}")
    
    # Clean up
    print("\n7. Cleanup...")
    db.close()
    print("   Database connection closed")
    
    print("\n" + "=" * 60)
    print("EXAMPLE COMPLETED SUCCESSFULLY")
    print("=" * 60)
    print("\nDatabase files created:")
    print("  - example_trades.db")
    print("  - trades2.db")
    print("\nYou can open these files with any SQLite viewer to inspect the data.")

if __name__ == "__main__":
    main()
