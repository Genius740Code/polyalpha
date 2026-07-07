"""
Example: Market Session Filtering for Trading Bot

This example demonstrates how to configure the Sniper bot to only trade
during specific market sessions (London, New York, Asia, Sydney).

The bot will automatically:
1. Detect which market session a trade occurs in
2. Save the market session with each trade record
3. Only execute trades during allowed sessions (if configured)
4. Skip trading outside of allowed sessions

Usage:
    python examples/market_session_filtering.py
"""

from datetime import datetime, timezone
from polyalpha import Client
from polyalpha.bots import Sniper, SniperConfig

# Example 1: Trade only during London session
def example_london_only():
    """
    Configure bot to trade only during London session (07:00-16:00 UTC).
    """
    print("Example 1: London Session Only")
    print("-" * 50)
    
    client = Client()
    
    config = SniperConfig(
        asset="BTC",
        timeframe="5m",
        side="UP",
        entry_price=0.92,
        exit_price=0.88,
        window_seconds=35,
        amount=20.0,
        allowed_market_sessions=["london"],  # Only trade London session
    )
    
    sniper = Sniper(client, config)
    
    # The bot will now only trade during London hours
    # Outside London hours, it will wait and check again every 60 seconds
    print("Bot configured to trade only during London session (07:00-16:00 UTC)")
    print("Current session check:", sniper._check_market_session())
    print()


# Example 2: Trade during London and New York overlap
def example_london_ny_overlap():
    """
    Configure bot to trade during London and New York sessions.
    This captures the high-liquidity overlap period (13:00-16:00 UTC).
    """
    print("Example 2: London + New York Sessions")
    print("-" * 50)
    
    client = Client()
    
    config = SniperConfig(
        asset="ETH",
        timeframe="15m",
        side="UP",
        entry_price=0.90,
        exit_price=0.85,
        window_seconds=60,
        amount=50.0,
        allowed_market_sessions=["london", "new_york"],
    )
    
    sniper = Sniper(client, config)
    
    print("Bot configured to trade during London and New York sessions")
    print("This includes the high-liquidity overlap period (13:00-16:00 UTC)")
    print()


# Example 3: Trade during Asian session
def example_asia_session():
    """
    Configure bot to trade only during Asian session (23:00-08:00 UTC).
    Good for overnight trading strategies.
    """
    print("Example 3: Asian Session Only")
    print("-" * 50)
    
    client = Client()
    
    config = SniperConfig(
        asset="BTC",
        timeframe="1h",
        side="DOWN",
        entry_price=0.15,
        exit_price=0.20,
        window_seconds=300,
        amount=100.0,
        allowed_market_sessions=["asia"],
    )
    
    sniper = Sniper(client, config)
    
    print("Bot configured to trade only during Asian session (23:00-08:00 UTC)")
    print("Ideal for overnight trading strategies")
    print()


# Example 4: No session filtering (trade 24/7)
def example_no_filtering():
    """
    Configure bot without session filtering (default behavior).
    Bot will trade whenever market conditions are met.
    """
    print("Example 4: No Session Filtering (24/7 Trading)")
    print("-" * 50)
    
    client = Client()
    
    config = SniperConfig(
        asset="SOL",
        timeframe="5m",
        side="UP",
        entry_price=0.92,
        exit_price=0.88,
        window_seconds=35,
        amount=20.0,
        allowed_market_sessions=None,  # No filtering (default)
    )
    
    sniper = Sniper(client, config)
    
    print("Bot configured with no session filtering")
    print("Will trade 24/7 based on market conditions")
    print()


# Example 5: Using session aliases
def example_session_aliases():
    """
    Demonstrate using session aliases for configuration.
    """
    print("Example 5: Using Session Aliases")
    print("-" * 50)
    
    from polyalpha.core import validate_session_list
    
    # Aliases are automatically normalized
    sessions = validate_session_list(["ny", "lon", "tokyo"])
    print(f"Normalized sessions: {sessions}")
    
    # Can use in config
    config = SniperConfig(
        asset="BTC",
        timeframe="5m",
        side="UP",
        entry_price=0.92,
        exit_price=0.88,
        window_seconds=35,
        amount=20.0,
        allowed_market_sessions=["ny", "eu"],  # Aliases work too
    )
    
    print("Configured with aliases: ny (New York), eu (London)")
    print()


# Example 6: Check current active sessions
def example_check_current_sessions():
    """
    Demonstrate checking which sessions are currently active.
    """
    print("Example 6: Check Current Active Sessions")
    print("-" * 50)
    
    from polyalpha.core import get_session, get_active_sessions
    
    now = datetime.now(timezone.utc)
    current_session = get_session(now)
    all_active = get_active_sessions(now)
    
    print(f"Current time (UTC): {now.strftime('%Y-%m-%d %H:%M:%S')}")
    print(f"Primary session: {current_session}")
    print(f"All active sessions: {all_active}")
    print()


# Example 7: Query trades by market session from database
def example_query_trades_by_session():
    """
    Demonstrate querying trades from database by market session.
    """
    print("Example 7: Query Trades by Market Session")
    print("-" * 50)
    
    from polyalpha.database import TradeDatabase
    
    db = TradeDatabase("trades.db")
    
    # Load all London session trades
    london_trades = db.load_trades_by_market_session("london")
    print(f"Found {len(london_trades)} trades during London session")
    
    # Load all New York session trades
    ny_trades = db.load_trades_by_market_session("new_york")
    print(f"Found {len(ny_trades)} trades during New York session")
    
    # Calculate P&L by session
    london_pnl = sum(t.pnl for t in london_trades)
    ny_pnl = sum(t.pnl for t in ny_trades)
    
    print(f"London session P&L: ${london_pnl:.2f}")
    print(f"New York session P&L: ${ny_pnl:.2f}")
    print()


# Example 8: Full trading session with session tracking
def example_full_session_tracking():
    """
    Complete example showing session tracking in action.
    """
    print("Example 8: Full Session Tracking Example")
    print("-" * 50)
    
    from polyalpha.core import get_session, MARKET_SESSIONS
    
    # Display all session definitions
    print("Available Market Sessions:")
    for name, session in MARKET_SESSIONS.items():
        print(f"  {name}: {session.start_hour:02d}:{session.start_minute:02d} - "
              f"{session.end_hour:02d}:{session.end_minute:02d} UTC")
    print()
    
    # Check current session
    now = datetime.now(timezone.utc)
    current = get_session(now)
    print(f"Current session: {current or 'None (outside trading hours)'}")
    
    # Example configuration
    config = SniperConfig(
        asset="BTC",
        timeframe="5m",
        side="UP",
        entry_price=0.92,
        exit_price=0.88,
        window_seconds=35,
        amount=20.0,
        allowed_market_sessions=["london", "new_york", "asia"],
        log_trades=True,
    )
    
    print("\nBot Configuration:")
    print(f"  Asset: {config.asset}")
    print(f"  Timeframe: {config.timeframe}")
    print(f"  Side: {config.side}")
    print(f"  Allowed sessions: {config.allowed_market_sessions}")
    print(f"  Entry price: {config.entry_price}")
    print(f"  Amount: ${config.amount}")
    print()
    
    print("Note: Bot will automatically:")
    print("  1. Detect market session for each trade")
    print("  2. Save session info with trade record")
    print("  3. Only trade during allowed sessions")
    print("  4. Skip trading outside allowed sessions")
    print()


if __name__ == "__main__":
    print("=" * 50)
    print("Market Session Filtering Examples")
    print("=" * 50)
    print()
    
    # Run examples (comment out actual trading to prevent accidental execution)
    example_london_only()
    example_london_ny_overlap()
    example_asia_session()
    example_no_filtering()
    example_session_aliases()
    example_check_current_sessions()
    
    # Database example (requires existing trades)
    try:
        example_query_trades_by_session()
    except Exception as e:
        print(f"Database example skipped: {e}")
        print()
    
    example_full_session_tracking()
    
    print("=" * 50)
    print("Examples completed")
    print("=" * 50)
    print()
    print("To actually run the bot, uncomment the sniper.run() call")
    print("in the example functions above.")
