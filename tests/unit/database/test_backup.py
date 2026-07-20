"""
Database backup and restore tests.
"""

import pytest
from datetime import datetime, timezone
from pathlib import Path
import tempfile
import shutil

from polyalpha.database import TradeDatabase


def test_backup_creates_file():
    """Test that backup creates a copy of the database file."""
    tmpdir = tempfile.mkdtemp()
    try:
        db_path = Path(tmpdir) / "test.db"
        backup_path = Path(tmpdir) / "backups" / "test_backup.db"
        
        db = TradeDatabase(db_path)
        
        # Add some test data
        trade_id = db.save_trade(
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
        
        # Create backup
        db.backup(backup_path)
        
        # Verify backup file exists
        assert backup_path.exists()
        
        # Verify backup has data
        backup_db = TradeDatabase(backup_path)
        backup_trades = backup_db.load_all_trades()
        assert len(backup_trades) == 1
        assert backup_trades[0].market_slug == "btc-updown-5m-1751234700"
        backup_db.close()
        
        db.close()
    finally:
        shutil.rmtree(tmpdir, ignore_errors=True)


def test_backup_creates_parent_directory():
    """Test that backup creates parent directories if they don't exist."""
    tmpdir = tempfile.mkdtemp()
    try:
        db_path = Path(tmpdir) / "test.db"
        backup_path = Path(tmpdir) / "backups" / "nested" / "test_backup.db"
        
        db = TradeDatabase(db_path)
        
        # Add test data
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
        
        # Create backup with nested directory
        db.backup(backup_path)
        
        # Verify backup file exists and parent directory was created
        assert backup_path.exists()
        assert backup_path.parent.exists()
        
        db.close()
    finally:
        shutil.rmtree(tmpdir, ignore_errors=True)


def test_backup_nonexistent_database():
    """Test that backup raises error for nonexistent database."""
    tmpdir = tempfile.mkdtemp()
    try:
        db_path = Path(tmpdir) / "nonexistent.db"
        backup_path = Path(tmpdir) / "backup.db"
        
        # Don't create the database file
        # Just initialize the TradeDatabase object without creating the file
        db = TradeDatabase.__new__(TradeDatabase)
        db.db_path = db_path
        db._conn = None
        
        with pytest.raises(FileNotFoundError, match="Source database not found"):
            db.backup(backup_path)
    finally:
        shutil.rmtree(tmpdir, ignore_errors=True)


def test_restore_from_backup():
    """Test that restore loads data from backup file."""
    tmpdir = tempfile.mkdtemp()
    try:
        db_path = Path(tmpdir) / "test.db"
        backup_path = Path(tmpdir) / "backup.db"
        
        # Create database with initial data
        db = TradeDatabase(db_path)
        trade_id = db.save_trade(
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
        db.close()
        
        # Create backup
        shutil.copy2(db_path, backup_path)
        
        # Modify original database
        db = TradeDatabase(db_path)
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
        db.close()
        
        # Restore from backup
        db = TradeDatabase(db_path)
        db.restore(backup_path, overwrite=True)
        
        # Verify only original data exists
        trades = db.load_all_trades()
        assert len(trades) == 1
        assert trades[0].market_slug == "btc-updown-5m-1751234700"
        
        db.close()
    finally:
        shutil.rmtree(tmpdir, ignore_errors=True)


def test_restore_without_overwrite():
    """Test that restore raises error when overwrite=False and database exists."""
    tmpdir = tempfile.mkdtemp()
    try:
        db_path = Path(tmpdir) / "test.db"
        backup_path = Path(tmpdir) / "backup.db"
        
        # Create database
        db = TradeDatabase(db_path)
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
        db.close()
        
        # Create backup
        shutil.copy2(db_path, backup_path)
        
        # Try to restore without overwrite
        db = TradeDatabase(db_path)
        with pytest.raises(FileExistsError, match="Database file already exists"):
            db.restore(backup_path, overwrite=False)
        
        db.close()
    finally:
        shutil.rmtree(tmpdir, ignore_errors=True)


def test_restore_nonexistent_backup():
    """Test that restore raises error for nonexistent backup file."""
    tmpdir = tempfile.mkdtemp()
    try:
        db_path = Path(tmpdir) / "test.db"
        backup_path = Path(tmpdir) / "nonexistent_backup.db"
        
        db = TradeDatabase(db_path)
        
        with pytest.raises(FileNotFoundError, match="Backup file not found"):
            db.restore(backup_path)
        
        db.close()
    finally:
        shutil.rmtree(tmpdir, ignore_errors=True)


def test_backup_preserves_all_data():
    """Test that backup preserves all trades and indexes."""
    tmpdir = tempfile.mkdtemp()
    try:
        db_path = Path(tmpdir) / "test.db"
        backup_path = Path(tmpdir) / "backup.db"
        
        db = TradeDatabase(db_path)
        
        # Add multiple trades
        for i in range(5):
            db.save_trade(
                market_slug=f"btc-updown-5m-175123470{i}",
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
        
        # Create backup
        db.backup(backup_path)
        
        # Verify backup has all data
        backup_db = TradeDatabase(backup_path)
        backup_trades = backup_db.load_all_trades()
        assert len(backup_trades) == 5
        
        # Verify statistics match
        original_stats = db.get_statistics()
        backup_stats = backup_db.get_statistics()
        assert original_stats.total_trades == backup_stats.total_trades
        assert original_stats.total_pnl == backup_stats.total_pnl
        
        backup_db.close()
        db.close()
    finally:
        shutil.rmtree(tmpdir, ignore_errors=True)


def test_backup_with_open_connection():
    """Test that backup works correctly with an open connection."""
    tmpdir = tempfile.mkdtemp()
    try:
        db_path = Path(tmpdir) / "test.db"
        backup_path = Path(tmpdir) / "backup.db"
        
        db = TradeDatabase(db_path)
        
        # Add data with connection open
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
        
        # Backup with connection open (should close and reopen)
        db.backup(backup_path)
        
        # Verify connection is still usable
        trades = db.load_all_trades()
        assert len(trades) == 1
        
        # Verify backup exists
        assert backup_path.exists()
        
        db.close()
    finally:
        shutil.rmtree(tmpdir, ignore_errors=True)


def test_restore_with_open_connection():
    """Test that restore works correctly with an open connection."""
    tmpdir = tempfile.mkdtemp()
    try:
        db_path = Path(tmpdir) / "test.db"
        backup_path = Path(tmpdir) / "backup.db"
        
        # Create initial database
        db = TradeDatabase(db_path)
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
        db.close()
        
        # Create backup
        shutil.copy2(db_path, backup_path)
        
        # Add more data to original
        db = TradeDatabase(db_path)
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
        
        # Restore with connection open (should close and reopen)
        db.restore(backup_path, overwrite=True)
        
        # Verify connection is still usable and data is restored
        trades = db.load_all_trades()
        assert len(trades) == 1
        assert trades[0].market_slug == "btc-updown-5m-1751234700"
        
        db.close()
    finally:
        shutil.rmtree(tmpdir, ignore_errors=True)


def test_backup_to_s3_invalid_uri():
    """Test that backup_to_s3 raises ValueError for invalid URI without bucket."""
    tmpdir = tempfile.mkdtemp()
    try:
        db_path = Path(tmpdir) / "test.db"
        
        db = TradeDatabase(db_path)
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
        
        # Test with invalid URI (no bucket name)
        # This should raise ValueError before trying to import boto3
        with pytest.raises(ValueError, match="Bucket name must be provided"):
            db.backup_to_s3("invalid_uri", bucket_name=None)
        
        db.close()
    finally:
        shutil.rmtree(tmpdir, ignore_errors=True)


def test_backup_to_gcs_invalid_uri():
    """Test that backup_to_gcs raises ValueError for invalid URI without bucket."""
    tmpdir = tempfile.mkdtemp()
    try:
        db_path = Path(tmpdir) / "test.db"
        
        db = TradeDatabase(db_path)
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
        
        # Test with invalid URI (no bucket name)
        # This should raise ValueError before trying to import google-cloud-storage
        with pytest.raises(ValueError, match="Bucket name must be provided"):
            db.backup_to_gcs("invalid_uri", bucket_name=None)
        
        db.close()
    finally:
        shutil.rmtree(tmpdir, ignore_errors=True)


def test_restore_invalidates_cache():
    """Test that restore invalidates the query cache."""
    tmpdir = tempfile.mkdtemp()
    try:
        db_path = Path(tmpdir) / "test.db"
        backup_path = Path(tmpdir) / "backup.db"
        
        # Create database with data
        db = TradeDatabase(db_path, enable_cache=True)
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
        db.close()
        
        # Create backup
        shutil.copy2(db_path, backup_path)
        
        # Add more data
        db = TradeDatabase(db_path, enable_cache=True)
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
        
        # Populate cache
        trades_before = db.load_all_trades()
        assert len(trades_before) == 2
        
        # Restore from backup
        db.restore(backup_path, overwrite=True)
        
        # Verify cache was invalidated (should have 1 trade, not 2)
        trades_after = db.load_all_trades()
        assert len(trades_after) == 1
        
        db.close()
    finally:
        shutil.rmtree(tmpdir, ignore_errors=True)
