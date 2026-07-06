"""
Database support for paper trading trades.

This module provides SQLite-based persistence for paper trading data,
allowing trades to be saved and loaded for analysis and backtesting.

Usage
-----
    from polyalpha.database import TradeDatabase
    
    # Initialize database (creates file if not exists)
    db = TradeDatabase("trades.db")
    
    # Save a trade
    db.save_trade(
        market_slug="btc-updown-5m-1751234700",
        market_id="abc123",
        side="UP",
        entry_price=0.92,
        exit_price=None,
        amount=10.0,
        shares=10.5,
        fee=0.2,
        outcome="WON",
        pnl=5.3,
        timestamp=datetime.now(timezone.utc)
    )
    
    # Load all trades
    trades = db.load_all_trades()
    
    # Load trades by market
    btc_trades = db.load_trades_by_market("btc")
    
    # Get statistics
    stats = db.get_statistics()
"""

from .database import TradeDatabase

__all__ = ["TradeDatabase"]
