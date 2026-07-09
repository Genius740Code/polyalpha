"""
Example demonstrating database security features.

This example shows how to use encryption, authentication, authorization,
and data masking with the TradeDatabase class.
"""

from datetime import datetime, timezone
from polyalpha.database import (
    TradeDatabase,
    DatabaseEncryption,
    AuthMethod,
)


def main():
    """Demonstrate security features."""
    # Initialize database
    db = TradeDatabase("trades_security.db")
    
    print("=" * 60)
    print("Database Security Features Example")
    print("=" * 60)
    
    # 1. Encryption
    print("\n1. Encryption")
    print("-" * 60)
    
    # Generate a new encryption key
    key = DatabaseEncryption.generate_key()
    print(f"Generated encryption key: {key[:20]}...")
    
    # Enable encryption with a password
    db.enable_encryption(password="my_secure_password_123")
    print(f"Encryption enabled: {db.is_encryption_enabled()}")
    
    # Disable encryption
    db.disable_encryption()
    print(f"Encryption disabled: {not db.is_encryption_enabled()}")
    
    # 2. Authentication
    print("\n2. Authentication")
    print("-" * 60)
    
    # Set authentication method to API key
    db.set_auth_method("api_key")
    print(f"Auth method: {db.get_auth_method()}")
    
    # Add users
    db.add_user("trader1", "alice", ["trader"])
    db.add_user("analyst1", "bob", ["analyst"])
    db.add_user("admin1", "charlie", ["admin"])
    print("Added users: trader1, analyst1, admin1")
    
    # Authenticate with API key (auto-generated)
    trader_user = db._auth_manager.get_user("trader1")
    print(f"Trader user: {trader_user.username}, roles: {trader_user.roles}")
    
    # 3. Authorization
    print("\n3. Authorization")
    print("-" * 60)
    
    # Check permissions for different roles
    print("Default roles and permissions:")
    print("- Admin: read, write, delete, export, import, backup, restore, manage_users, manage_roles")
    print("- Trader: read, write, export")
    print("- Analyst: read, export")
    print("- Viewer: read")
    
    # Add custom role
    db.add_role("manager", ["read", "write", "export", "backup"], "Manager role")
    print("Added custom role: manager")
    
    # 4. Data Masking
    print("\n4. Data Masking")
    print("-" * 60)
    
    # Add custom masking rule
    db.add_masking_rule("market_id", show_first=4, show_last=4)
    print("Added masking rule for market_id (show first 4, last 4)")
    
    # Test masking
    test_id = "abc123xyz789def456"
    masked = db._data_masker.mask_field("market_id", test_id)
    print(f"Original: {test_id}")
    print(f"Masked:   {masked}")
    
    # Save a trade
    print("\n5. Saving Trade with Security")
    print("-" * 60)
    
    trade_id = db.save_trade(
        market_slug="btc-updown-5m-1751234700",
        market_id="abc123xyz789def456",
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
    print(f"Saved trade with ID: {trade_id}")
    
    # Load and mask the trade
    trades = db.load_all_trades()
    if trades:
        trade = trades[0]
        masked_record = db.mask_trade_record(trade)
        print(f"Original market_id: {trade.market_id}")
        print(f"Masked market_id:   {masked_record['market_id']}")
    
    # 6. Permission-based operations
    print("\n6. Permission-based Operations")
    print("-" * 60)
    
    # Simulate authentication
    db.set_auth_method("api_key")
    api_key = db._auth_manager.generate_api_key()
    db.add_user("test_user", "test", ["trader"], api_key=api_key)
    db.authenticate(api_key)
    print(f"Authenticated as: {db.get_current_user()}")
    print(f"User roles: {db.get_current_roles()}")
    
    # Check permissions
    print(f"Has 'read' permission: {db.check_permission('read')}")
    print(f"Has 'write' permission: {db.check_permission('write')}")
    print(f"Has 'delete' permission: {db.check_permission('delete')}")
    
    # Try to require permission
    try:
        db.require_permission("read")
        print("✓ Read permission granted")
    except PermissionError as e:
        print(f"✗ Read permission denied: {e}")
    
    try:
        db.require_permission("delete")
        print("✓ Delete permission granted")
    except PermissionError as e:
        print(f"✗ Delete permission denied: {e}")
    
    # Clean up
    db.close()
    
    # Clean up database file
    import os
    if os.path.exists("trades_security.db"):
        os.remove("trades_security.db")
    
    print("\n" + "=" * 60)
    print("Example completed successfully!")
    print("=" * 60)


if __name__ == "__main__":
    main()
