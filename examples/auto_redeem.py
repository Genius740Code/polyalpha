"""
Auto-Redeem Examples

This example demonstrates how to use the auto-redeem feature to automatically
redeem resolved Polymarket positions based on configurable triggers.
"""

import polyalpha
from polyalpha import AutoRedeemConfig

# ── Simple Daily Auto-Redeem (Paper Trading) ───────────────────────────────────

def simple_daily_redeem_paper():
    """Simple daily auto-redeem for paper trading."""
    
    client = polyalpha.Client(balance=1000.0)
    
    # Enable simple daily auto-redeem
    config = AutoRedeemConfig(
        time_interval="1d",  # Redeem daily
        min_value_usd=100.0,  # Only when value >= $100
        dry_run=False,  # Actually execute redemption
    )
    
    client.paper.set_auto_redeem_config(config)
    
    # Start the scheduler
    client.paper.auto_redeem.start_scheduler()
    
    print("Auto-redeem scheduler started (daily)")
    print("Will redeem positions when value >= $100")
    
    # In a real application, you would keep the main thread alive
    # import time
    # time.sleep(3600)  # Keep running for 1 hour
    
    # Stop the scheduler when done
    client.paper.auto_redeem.stop_scheduler()
    print("Auto-redeem scheduler stopped")


# ── Simple Daily Auto-Redeem (Real Trading) ───────────────────────────────────

def simple_daily_redeem_real():
    """Simple daily auto-redeem for real trading."""
    
    client = polyalpha.Client(
        private_key="your-private-key-here",
        rpc_url="https://polygon-rpc.com",
        polymarket_api_key="your-polymarket-api-key",
        real_config=polyalpha.RealTradingConfig(
            require_confirmation=True,  # Safety: confirm orders
            max_order_size=100.0,
        ),
    )
    
    # Enable simple daily auto-redeem with safety
    config = AutoRedeemConfig(
        time_interval="1d",
        min_value_usd=100.0,
        require_confirmation=True,  # Confirm before redeeming
        dry_run=False,
    )
    
    client.real.set_auto_redeem_config(config)
    client.real.auto_redeem.start_scheduler()
    
    print("Auto-redeem scheduler started (daily)")
    print("Will require confirmation before redeeming")


# ── Multi-Trigger Configuration ───────────────────────────────────────────────

def multi_trigger_redeem():
    """Auto-redeem with multiple trigger types."""
    
    client = polyalpha.Client(balance=1000.0)
    
    config = AutoRedeemConfig(
        # Enable multiple triggers
        trigger_on_time=True,
        trigger_on_count=True,
        trigger_on_value=True,
        
        # Time: redeem every 6 hours
        time_interval="6h",
        
        # Count: redeem after 5 markets, force after 20
        min_markets=5,
        max_markets=20,
        
        # Value: redeem at $50, force at $500
        min_value_usd=50.0,
        max_value_usd=500.0,
        
        # Safety
        require_confirmation=False,
        min_age_hours=2,  # Wait 2 hours after resolution
    )
    
    client.paper.set_auto_redeem_config(config)
    client.paper.auto_redeem.start_scheduler()
    
    print("Multi-trigger auto-redeem started:")
    print("  - Time: every 6 hours")
    print("  - Count: after 5 markets (force at 20)")
    print("  - Value: at $50 (force at $500)")
    print("  - Min age: 2 hours after resolution")


# ── Manual Check and Redeem ───────────────────────────────────────────────────

def manual_check_redeem():
    """Manually check for redeemable positions and redeem."""
    
    client = polyalpha.Client(balance=1000.0)
    
    config = AutoRedeemConfig(
        trigger_on_time=False,  # No auto-scheduling
        trigger_on_count=False,
        min_value_usd=100.0,
    )
    
    client.paper.set_auto_redeem_config(config)
    
    # Manually check for redeemable positions
    positions = client.paper.auto_redeem.check_positions()
    print(f"Found {len(positions)} positions to redeem")
    
    for pos in positions:
        print(f"  - {pos.slug} {pos.side}: ${pos.value_usd:.2f} ({pos.outcome})")
    
    if positions:
        # Manually redeem
        result = client.paper.auto_redeem.redeem(positions)
        print(f"Redeemed {result.redeemed_count} positions")
        print(f"Total value: ${result.total_value_usd:.2f}")
        
        if result.errors:
            print(f"Errors: {result.errors}")


# ── Dry Run Mode ───────────────────────────────────────────────────────────────

def dry_run_mode():
    """Test auto-redeem configuration without executing transactions."""
    
    client = polyalpha.Client(balance=1000.0)
    
    config = AutoRedeemConfig(
        time_interval="1d",
        min_value_usd=100.0,
        dry_run=True,  # Simulate without executing
    )
    
    client.paper.set_auto_redeem_config(config)
    
    # Check positions
    positions = client.paper.auto_redeem.check_positions()
    print(f"Found {len(positions)} positions (dry run)")
    
    # Simulate redemption
    result = client.paper.auto_redeem.redeem(positions)
    print(f"DRY RUN: Would redeem {result.redeemed_count} positions")
    print(f"DRY RUN: Total value: ${result.total_value_usd:.2f}")


# ── Only Winning Positions ────────────────────────────────────────────────────

def only_winning_redeem():
    """Only redeem winning positions, skip losing ones."""
    
    client = polyalpha.Client(balance=1000.0)
    
    config = AutoRedeemConfig(
        time_interval="1d",
        min_markets=5,
        only_winning=True,  # Only redeem winning positions
    )
    
    client.paper.set_auto_redeem_config(config)
    client.paper.auto_redeem.start_scheduler()
    
    print("Auto-redeem started (winning positions only)")


# ── View Redemption History ────────────────────────────────────────────────────

def view_history():
    """View redemption history."""
    
    client = polyalpha.Client(balance=1000.0)
    
    # Run some redemptions first
    config = AutoRedeemConfig(
        trigger_on_time=False,
        min_value_usd=50.0,
    )
    client.paper.set_auto_redeem_config(config)
    
    # Check and redeem
    positions = client.paper.auto_redeem.check_positions()
    if positions:
        client.paper.auto_redeem.redeem(positions)
    
    # View history
    history = client.paper.auto_redeem.get_redeem_history()
    print(f"Redemption history: {len(history)} operations")
    
    for record in history:
        print(f"\n{record.timestamp}")
        print(f"  Positions: {record.positions_count}")
        print(f"  Value: ${record.total_value_usd:.2f}")
        print(f"  Trigger: {record.trigger_reason}")
        print(f"  Success: {record.success}")


# ── Advanced Real Trading Configuration ───────────────────────────────────────

def advanced_real_trading():
    """Advanced auto-redeem configuration for real trading."""
    
    config = AutoRedeemConfig(
        # Multiple triggers
        trigger_on_time=True,
        trigger_on_count=True,
        trigger_on_value=True,
        
        # Time: redeem every 12 hours at specific time
        time_interval="12h",
        redeem_at_time="14:00",  # 2 PM UTC
        
        # Count: redeem after 3 markets, force after 10
        min_markets=3,
        max_markets=10,
        
        # Value: redeem at $25, force at $250
        min_value_usd=25.0,
        max_value_usd=250.0,
        
        # Safety settings
        require_confirmation=True,
        max_gas_price=30.0,  # Max 30 Gwei gas
        min_age_hours=1,  # Wait 1 hour after resolution
        
        # Filtering
        only_winning=False,  # Redeem all positions
    )
    
    client = polyalpha.Client(
        private_key="your-private-key-here",
        rpc_url="https://polygon-rpc.com",
        polymarket_api_key="your-polymarket-api-key",
        real_config=polyalpha.RealTradingConfig(
            require_confirmation=True,
            max_order_size=50.0,
        ),
    )
    
    client.real.set_auto_redeem_config(config)
    client.real.auto_redeem.start_scheduler()
    
    print("Advanced auto-redeem started for real trading")
    print("Configuration:")
    print(f"  - Time interval: {config.time_interval}")
    print(f"  - Redeem at: {config.redeem_at_time} UTC")
    print(f"  - Min markets: {config.min_markets}")
    print(f"  - Max markets: {config.max_markets}")
    print(f"  - Min value: ${config.min_value_usd}")
    print(f"  - Max value: ${config.max_value_usd}")
    print(f"  - Require confirmation: {config.require_confirmation}")
    print(f"  - Max gas price: {config.max_gas_price} Gwei")


# ── Hourly Auto-Redeem ────────────────────────────────────────────────────────

def hourly_redeem():
    """Redeem positions every hour."""
    
    client = polyalpha.Client(balance=500.0)
    
    config = AutoRedeemConfig(
        time_interval="1h",  # Every hour
        min_markets=1,  # Redeem after 1 market
    )
    
    client.paper.set_auto_redeem_config(config)
    client.paper.auto_redeem.start_scheduler()
    
    print("Hourly auto-redeem started")


# ── Weekly Auto-Redeem ────────────────────────────────────────────────────────

def weekly_redeem():
    """Redeem positions every week."""
    
    client = polyalpha.Client(balance=2000.0)
    
    config = AutoRedeemConfig(
        time_interval="1w",  # Every week
        min_value_usd=500.0,  # Only when value >= $500
    )
    
    client.paper.set_auto_redeem_config(config)
    client.paper.auto_redeem.start_scheduler()
    
    print("Weekly auto-redeem started")


# ── Check Pending Count ───────────────────────────────────────────────────────

def check_pending():
    """Check how many positions are awaiting redemption."""
    
    client = polyalpha.Client(balance=1000.0)
    
    config = AutoRedeemConfig(
        trigger_on_time=False,
        min_value_usd=100.0,
    )
    
    client.paper.set_auto_redeem_config(config)
    
    # Check positions
    positions = client.paper.auto_redeem.check_positions()
    pending_count = client.paper.auto_redeem.get_pending_count()
    
    print(f"Positions awaiting redemption: {pending_count}")
    print(f"Redeemable positions: {len(positions)}")


# ── Clear History ─────────────────────────────────────────────────────────────

def clear_history():
    """Clear redemption history."""
    
    client = polyalpha.Client(balance=1000.0)
    
    # Clear history
    client.paper.auto_redeem.clear_history()
    print("Redemption history cleared")


# ── Main Example ───────────────────────────────────────────────────────────────

if __name__ == "__main__":
    print("=" * 60)
    print("Auto-Redeem Examples")
    print("=" * 60)
    print()
    print("This example demonstrates various auto-redeem configurations.")
    print("Uncomment the function you want to test.")
    print()
    print("=" * 60)
    print()
    
    # Uncomment one of the examples below to run:
    
    # simple_daily_redeem_paper()
    # simple_daily_redeem_real()
    # multi_trigger_redeem()
    # manual_check_redeem()
    # dry_run_mode()
    # only_winning_redeem()
    # view_history()
    # advanced_real_trading()
    # hourly_redeem()
    # weekly_redeem()
    # check_pending()
    # clear_history()
    
    print("\nTo run an example, uncomment it in the code.")
