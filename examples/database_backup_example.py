"""
Database Backup and Restore Examples

This example demonstrates how to use the backup and restore functionality
of the TradeDatabase class for local file backups and cloud storage backups.

Run with: python examples/database_backup_example.py
"""

import sys
import os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))

from datetime import datetime, timezone
from pathlib import Path
from polyalpha.database import TradeDatabase


def example_local_backup():
    """Example: Create and restore local database backups."""
    print("=" * 60)
    print("Local Backup and Restore Example")
    print("=" * 60)
    
    # Initialize database
    db = TradeDatabase("trades.db")
    
    # Add some sample trades
    print("\nAdding sample trades...")
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
    
    db.save_trade(
        market_slug="eth-updown-5m-1751234700",
        market_id="def456",
        side="DOWN",
        entry_price=0.88,
        exit_price=None,
        amount=20.0,
        shares=22.0,
        fee=0.4,
        outcome="LOST",
        pnl=-2.0,
        timestamp=datetime.now(timezone.utc)
    )
    
    print(f"Total trades in database: {len(db.load_all_trades())}")
    
    # Create a backup
    backup_path = "backups/trades_backup.db"
    print(f"\nCreating backup to: {backup_path}")
    db.backup(backup_path)
    print("Backup created successfully!")
    
    # Add more trades
    print("\nAdding more trades...")
    db.save_trade(
        market_slug="sol-updown-5m-1751234700",
        market_id="ghi789",
        side="UP",
        entry_price=0.95,
        exit_price=None,
        amount=15.0,
        shares=15.5,
        fee=0.3,
        outcome="WON",
        pnl=7.5,
        timestamp=datetime.now(timezone.utc)
    )
    
    print(f"Total trades after adding more: {len(db.load_all_trades())}")
    
    # Restore from backup
    print(f"\nRestoring from backup: {backup_path}")
    db.restore(backup_path, overwrite=True)
    print("Restore completed successfully!")
    
    print(f"Total trades after restore: {len(db.load_all_trades())}")
    
    db.close()
    print("\nLocal backup example completed!\n")


def example_scheduled_backup():
    """Example: Create scheduled backups with timestamps."""
    print("=" * 60)
    print("Scheduled Backup Example")
    print("=" * 60)
    
    # Initialize database
    db = TradeDatabase("trades.db")
    
    # Add sample data
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
    
    # Create backup with timestamp in filename
    timestamp = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")
    backup_path = f"backups/trades_backup_{timestamp}.db"
    
    print(f"\nCreating timestamped backup: {backup_path}")
    db.backup(backup_path)
    print("Backup created successfully!")
    
    db.close()
    print("\nScheduled backup example completed!\n")


def example_s3_backup():
    """Example: Backup to Amazon S3 (requires boto3)."""
    print("=" * 60)
    print("Amazon S3 Backup Example")
    print("=" * 60)
    
    # Initialize database
    db = TradeDatabase("trades.db")
    
    # Add sample data
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
    
    print("\nNote: This example requires boto3 to be installed.")
    print("Install with: pip install boto3")
    print("\nExample S3 backup code (commented out):")
    print("""
    # Backup using S3 URI
    db.backup_to_s3("s3://my-bucket/backups/trades.db")
    
    # Backup with explicit credentials
    db.backup_to_s3(
        "s3://my-bucket/backups/trades.db",
        aws_access_key_id="YOUR_ACCESS_KEY",
        aws_secret_access_key="YOUR_SECRET_KEY",
        region_name="us-east-1"
    )
    
    # Backup with custom key name
    db.backup_to_s3(
        "s3://my-bucket/backups/trades_2024_01_01.db",
        region_name="us-east-1"
    )
    """)
    
    db.close()
    print("\nS3 backup example completed!\n")


def example_gcs_backup():
    """Example: Backup to Google Cloud Storage (requires google-cloud-storage)."""
    print("=" * 60)
    print("Google Cloud Storage Backup Example")
    print("=" * 60)
    
    # Initialize database
    db = TradeDatabase("trades.db")
    
    # Add sample data
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
    
    print("\nNote: This example requires google-cloud-storage to be installed.")
    print("Install with: pip install google-cloud-storage")
    print("\nExample GCS backup code (commented out):")
    print("""
    # Backup using GCS URI with Application Default Credentials
    db.backup_to_gcs("gs://my-bucket/backups/trades.db")
    
    # Backup with service account credentials
    db.backup_to_gcs(
        "gs://my-bucket/backups/trades.db",
        credentials_path="service_account.json",
        project_id="my-project-id"
    )
    
    # Backup with custom blob name
    db.backup_to_gcs(
        "gs://my-bucket/backups/trades_2024_01_01.db",
        credentials_path="service_account.json",
        project_id="my-project-id"
    )
    """)
    
    db.close()
    print("\nGCS backup example completed!\n")


def example_backup_before_migration():
    """Example: Create backup before schema migration."""
    print("=" * 60)
    print("Backup Before Migration Example")
    print("=" * 60)
    
    # Initialize database
    db = TradeDatabase("trades.db")
    
    # Add sample data
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
    
    print("\nCreating backup before migration...")
    backup_path = "backups/pre_migration_backup.db"
    db.backup(backup_path)
    print("Backup created successfully!")
    
    print("\nNow you can safely perform schema migrations...")
    print("If anything goes wrong, you can restore with:")
    print(f"  db.restore('{backup_path}', overwrite=True)")
    
    db.close()
    print("\nBackup before migration example completed!\n")


def example_backup_with_filters():
    """Example: Create backup and export with filters."""
    print("=" * 60)
    print("Backup with Export Filters Example")
    print("=" * 60)
    
    # Initialize database
    db = TradeDatabase("trades.db")
    
    # Add sample trades for different assets
    assets = ["btc", "eth", "sol"]
    for i, asset in enumerate(assets):
        db.save_trade(
            market_slug=f"{asset}-updown-5m-175123470{i}",
            market_id=f"abc{i}",
            side="UP" if i % 2 == 0 else "DOWN",
            entry_price=0.92 + (i * 0.01),
            exit_price=None,
            amount=10.0 + i,
            shares=10.5 + i,
            fee=0.2 + (i * 0.1),
            outcome="WON" if i % 2 == 0 else "LOST",
            pnl=5.3 + i,
            timestamp=datetime.now(timezone.utc)
        )
    
    print(f"\nTotal trades: {len(db.load_all_trades())}")
    
    # Create full backup
    print("\nCreating full backup...")
    db.backup("backups/full_backup.db")
    
    # Export BTC trades to CSV
    print("Exporting BTC trades to CSV...")
    db.export_csv("backups/btc_trades.csv", filters={"asset": "BTC"})
    
    # Export winning trades to JSON
    print("Exporting winning trades to JSON...")
    db.export_json("backups/winning_trades.json", filters={"outcome": "WON"})
    
    print("Backup and exports completed successfully!")
    
    db.close()
    print("\nBackup with filters example completed!\n")


if __name__ == "__main__":
    # Run all examples
    example_local_backup()
    example_scheduled_backup()
    example_s3_backup()
    example_gcs_backup()
    example_backup_before_migration()
    example_backup_with_filters()
    
    print("=" * 60)
    print("All backup examples completed!")
    print("=" * 60)
