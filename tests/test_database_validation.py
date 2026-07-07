"""
Database validation tests — run with: pytest tests/test_database_validation.py
"""

import sys, os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))

import pytest
from datetime import datetime, timezone, timedelta
from pathlib import Path
import tempfile

from polyalpha.database import TradeDatabase


def test_validate_trade_data_valid():
    """Test that valid trade data passes validation."""
    tmpdir = tempfile.mkdtemp()
    try:
        db_path = Path(tmpdir) / "test.db"
        db = TradeDatabase(db_path)
        
        # Valid trade should save without error
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
        
        assert trade_id > 0
        db.close()
    finally:
        import shutil
        shutil.rmtree(tmpdir, ignore_errors=True)


def test_validate_invalid_side():
    """Test that invalid side raises ValueError."""
    tmpdir = tempfile.mkdtemp()
    try:
        db_path = Path(tmpdir) / "test.db"
        db = TradeDatabase(db_path)
        
        with pytest.raises(ValueError, match="side must be 'UP' or 'DOWN'"):
            db.save_trade(
                market_slug="btc-updown-5m-1751234700",
                market_id="abc123",
                side="INVALID",
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
    finally:
        import shutil
        shutil.rmtree(tmpdir, ignore_errors=True)


def test_validate_negative_price():
    """Test that negative entry price raises ValueError."""
    tmpdir = tempfile.mkdtemp()
    try:
        db_path = Path(tmpdir) / "test.db"
        db = TradeDatabase(db_path)
        
        with pytest.raises(ValueError, match="entry_price must be non-negative"):
            db.save_trade(
                market_slug="btc-updown-5m-1751234700",
                market_id="abc123",
                side="UP",
                entry_price=-0.92,
                exit_price=None,
                amount=10.0,
                shares=10.5,
                fee=0.2,
                outcome="WON",
                pnl=5.3,
                timestamp=datetime.now(timezone.utc)
            )
        
        db.close()
    finally:
        import shutil
        shutil.rmtree(tmpdir, ignore_errors=True)


def test_validate_negative_amount():
    """Test that negative amount raises ValueError."""
    tmpdir = tempfile.mkdtemp()
    try:
        db_path = Path(tmpdir) / "test.db"
        db = TradeDatabase(db_path)
        
        with pytest.raises(ValueError, match="amount must be non-negative"):
            db.save_trade(
                market_slug="btc-updown-5m-1751234700",
                market_id="abc123",
                side="UP",
                entry_price=0.92,
                exit_price=None,
                amount=-10.0,
                shares=10.5,
                fee=0.2,
                outcome="WON",
                pnl=5.3,
                timestamp=datetime.now(timezone.utc)
            )
        
        db.close()
    finally:
        import shutil
        shutil.rmtree(tmpdir, ignore_errors=True)


def test_validate_invalid_outcome():
    """Test that invalid outcome raises ValueError."""
    tmpdir = tempfile.mkdtemp()
    try:
        db_path = Path(tmpdir) / "test.db"
        db = TradeDatabase(db_path)
        
        with pytest.raises(ValueError, match="outcome must be one of"):
            db.save_trade(
                market_slug="btc-updown-5m-1751234700",
                market_id="abc123",
                side="UP",
                entry_price=0.92,
                exit_price=None,
                amount=10.0,
                shares=10.5,
                fee=0.2,
                outcome="INVALID",
                pnl=5.3,
                timestamp=datetime.now(timezone.utc)
            )
        
        db.close()
    finally:
        import shutil
        shutil.rmtree(tmpdir, ignore_errors=True)


def test_validate_non_timezone_aware_timestamp():
    """Test that non-timezone-aware timestamp raises ValueError."""
    tmpdir = tempfile.mkdtemp()
    try:
        db_path = Path(tmpdir) / "test.db"
        db = TradeDatabase(db_path)
        
        with pytest.raises(ValueError, match="timestamp must be timezone-aware"):
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
                timestamp=datetime.now()  # No timezone
            )
        
        db.close()
    finally:
        import shutil
        shutil.rmtree(tmpdir, ignore_errors=True)


def test_validate_empty_market_slug():
    """Test that empty market_slug raises ValueError."""
    tmpdir = tempfile.mkdtemp()
    try:
        db_path = Path(tmpdir) / "test.db"
        db = TradeDatabase(db_path)
        
        with pytest.raises(ValueError, match="market_slug must be a non-empty string"):
            db.save_trade(
                market_slug="",
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
    finally:
        import shutil
        shutil.rmtree(tmpdir, ignore_errors=True)


def test_duplicate_detection_exact_match():
    """Test duplicate detection with exact timestamp match."""
    tmpdir = tempfile.mkdtemp()
    try:
        db_path = Path(tmpdir) / "test.db"
        db = TradeDatabase(db_path)
        
        timestamp = datetime.now(timezone.utc)
        
        # Save first trade
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
            timestamp=timestamp
        )
        
        # Try to save duplicate (should raise ValueError)
        with pytest.raises(ValueError, match="Duplicate trade detected"):
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
                timestamp=timestamp
            )
        
        db.close()
    finally:
        import shutil
        shutil.rmtree(tmpdir, ignore_errors=True)


def test_duplicate_detection_within_tolerance():
    """Test duplicate detection with timestamp within tolerance."""
    tmpdir = tempfile.mkdtemp()
    try:
        db_path = Path(tmpdir) / "test.db"
        db = TradeDatabase(db_path)
        
        timestamp = datetime.now(timezone.utc)
        
        # Save first trade
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
            timestamp=timestamp
        )
        
        # Try to save with timestamp 0.5 seconds later (within tolerance)
        timestamp2 = timestamp + timedelta(seconds=0.5)
        with pytest.raises(ValueError, match="Duplicate trade detected"):
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
                timestamp=timestamp2
            )
        
        db.close()
    finally:
        import shutil
        shutil.rmtree(tmpdir, ignore_errors=True)


def test_duplicate_detection_different_side():
    """Test that different side is not considered duplicate."""
    tmpdir = tempfile.mkdtemp()
    try:
        db_path = Path(tmpdir) / "test.db"
        db = TradeDatabase(db_path)
        
        timestamp = datetime.now(timezone.utc)
        
        # Save UP trade
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
            timestamp=timestamp
        )
        
        # Save DOWN trade with same market_id and timestamp (should succeed)
        trade_id = db.save_trade(
            market_slug="btc-updown-5m-1751234700",
            market_id="abc123",
            side="DOWN",
            entry_price=0.88,
            exit_price=None,
            amount=10.0,
            shares=11.4,
            fee=0.2,
            outcome="LOST",
            pnl=-5.3,
            timestamp=timestamp
        )
        
        assert trade_id > 0
        db.close()
    finally:
        import shutil
        shutil.rmtree(tmpdir, ignore_errors=True)


def test_duplicate_detection_disabled():
    """Test that duplicate checking can be disabled."""
    tmpdir = tempfile.mkdtemp()
    try:
        db_path = Path(tmpdir) / "test.db"
        db = TradeDatabase(db_path)
        
        timestamp = datetime.now(timezone.utc)
        
        # Save first trade
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
            timestamp=timestamp
        )
        
        # Save duplicate with check_duplicates=False (should succeed)
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
            timestamp=timestamp,
            check_duplicates=False
        )
        
        assert trade_id > 0
        db.close()
    finally:
        import shutil
        shutil.rmtree(tmpdir, ignore_errors=True)


def test_schema_version():
    """Test schema version tracking."""
    tmpdir = tempfile.mkdtemp()
    try:
        db_path = Path(tmpdir) / "test.db"
        db = TradeDatabase(db_path)
        
        # New database should have version 1
        version = db.get_schema_version()
        assert version == 1
        
        db.close()
    finally:
        import shutil
        shutil.rmtree(tmpdir, ignore_errors=True)


def test_run_migrations_no_pending():
    """Test that run_migrations works when no migrations are pending."""
    tmpdir = tempfile.mkdtemp()
    try:
        db_path = Path(tmpdir) / "test.db"
        db = TradeDatabase(db_path)
        
        # Should not raise any errors
        db.run_migrations()
        
        # Version should still be 1
        version = db.get_schema_version()
        assert version == 1
        
        db.close()
    finally:
        import shutil
        shutil.rmtree(tmpdir, ignore_errors=True)


def test_is_duplicate_trade_method():
    """Test the is_duplicate_trade method directly."""
    tmpdir = tempfile.mkdtemp()
    try:
        db_path = Path(tmpdir) / "test.db"
        db = TradeDatabase(db_path)
        
        timestamp = datetime.now(timezone.utc)
        
        # Initially no duplicate
        assert not db.is_duplicate_trade("abc123", "UP", timestamp)
        
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
            timestamp=timestamp,
            check_duplicates=False  # Disable to avoid circular check
        )
        
        # Now should detect duplicate
        assert db.is_duplicate_trade("abc123", "UP", timestamp)
        
        # Different market_id should not be duplicate
        assert not db.is_duplicate_trade("def456", "UP", timestamp)
        
        db.close()
    finally:
        import shutil
        shutil.rmtree(tmpdir, ignore_errors=True)


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
