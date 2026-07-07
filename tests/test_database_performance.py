"""
Database performance tests — run with: pytest tests/test_database_performance.py
"""

import sys, os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))

import pytest
from datetime import datetime, timezone
from pathlib import Path
import tempfile

from polyalpha.database import TradeDatabase


def test_wal_mode_enabled():
    """Test that WAL mode is enabled by default."""
    tmpdir = tempfile.mkdtemp()
    try:
        db_path = Path(tmpdir) / "test.db"
        db = TradeDatabase(db_path, enable_wal=True)
        
        # Check WAL mode
        conn = db._get_connection()
        cursor = conn.cursor()
        cursor.execute("PRAGMA journal_mode")
        result = cursor.fetchone()
        
        assert result[0] == "wal"
        db.close()
    finally:
        import shutil
        shutil.rmtree(tmpdir, ignore_errors=True)


def test_wal_mode_disabled():
    """Test that WAL mode can be disabled."""
    tmpdir = tempfile.mkdtemp()
    try:
        db_path = Path(tmpdir) / "test.db"
        db = TradeDatabase(db_path, enable_wal=False)
        
        # Check WAL mode is disabled
        conn = db._get_connection()
        cursor = conn.cursor()
        cursor.execute("PRAGMA journal_mode")
        result = cursor.fetchone()
        
        assert result[0] == "delete"
        db.close()
    finally:
        import shutil
        shutil.rmtree(tmpdir, ignore_errors=True)


def test_cache_enabled_by_default():
    """Test that cache is enabled by default."""
    tmpdir = tempfile.mkdtemp()
    try:
        db_path = Path(tmpdir) / "test.db"
        db = TradeDatabase(db_path)
        
        assert db._cache_enabled is True
        db.close()
    finally:
        import shutil
        shutil.rmtree(tmpdir, ignore_errors=True)


def test_cache_can_be_disabled():
    """Test that cache can be disabled."""
    tmpdir = tempfile.mkdtemp()
    try:
        db_path = Path(tmpdir) / "test.db"
        db = TradeDatabase(db_path, enable_cache=False)
        
        assert db._cache_enabled is False
        db.close()
    finally:
        import shutil
        shutil.rmtree(tmpdir, ignore_errors=True)


def test_cache_hit():
    """Test that cache returns cached results."""
    tmpdir = tempfile.mkdtemp()
    try:
        db_path = Path(tmpdir) / "test.db"
        db = TradeDatabase(db_path, enable_cache=True)
        
        # Add a trade
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
            timestamp=datetime.now(timezone.utc),
            check_duplicates=False
        )
        
        # First query - cache miss
        trades1 = db.load_trades(filters={"asset": "BTC"})
        assert len(trades1) == 1
        
        # Second query - cache hit
        trades2 = db.load_trades(filters={"asset": "BTC"})
        assert len(trades2) == 1
        assert trades1[0].id == trades2[0].id
        
        db.close()
    finally:
        import shutil
        shutil.rmtree(tmpdir, ignore_errors=True)


def test_cache_invalidation_on_write():
    """Test that cache is invalidated on write."""
    tmpdir = tempfile.mkdtemp()
    try:
        db_path = Path(tmpdir) / "test.db"
        db = TradeDatabase(db_path, enable_cache=True)
        
        # Add a trade
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
            timestamp=datetime.now(timezone.utc),
            check_duplicates=False
        )
        
        # Query to populate cache
        trades1 = db.load_trades()
        assert len(trades1) == 1
        
        # Add another trade (should invalidate cache)
        db.save_trade(
            market_slug="eth-updown-5m-1751234800",
            market_id="def456",
            side="DOWN",
            entry_price=0.88,
            exit_price=None,
            amount=15.0,
            shares=17.0,
            fee=0.3,
            outcome="LOST",
            pnl=-7.5,
            timestamp=datetime.now(timezone.utc),
            check_duplicates=False
        )
        
        # Query again - should get updated data
        trades2 = db.load_trades()
        assert len(trades2) == 2
        
        db.close()
    finally:
        import shutil
        shutil.rmtree(tmpdir, ignore_errors=True)


def test_cache_clear():
    """Test that cache can be manually cleared."""
    tmpdir = tempfile.mkdtemp()
    try:
        db_path = Path(tmpdir) / "test.db"
        db = TradeDatabase(db_path, enable_cache=True)
        
        # Add a trade
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
            timestamp=datetime.now(timezone.utc),
            check_duplicates=False
        )
        
        # Query to populate cache
        db.load_trades()
        assert len(db._query_cache) > 0
        
        # Clear cache
        db.clear_cache()
        assert len(db._query_cache) == 0
        
        db.close()
    finally:
        import shutil
        shutil.rmtree(tmpdir, ignore_errors=True)


def test_cache_enable_disable():
    """Test enabling and disabling cache."""
    tmpdir = tempfile.mkdtemp()
    try:
        db_path = Path(tmpdir) / "test.db"
        db = TradeDatabase(db_path, enable_cache=True)
        
        # Add a trade
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
            timestamp=datetime.now(timezone.utc),
            check_duplicates=False
        )
        
        # Query with cache enabled
        db.load_trades()
        assert len(db._query_cache) > 0
        
        # Disable cache
        db.disable_cache()
        assert db._cache_enabled is False
        assert len(db._query_cache) == 0
        
        # Re-enable cache
        db.enable_cache()
        assert db._cache_enabled is True
        
        db.close()
    finally:
        import shutil
        shutil.rmtree(tmpdir, ignore_errors=True)


def test_bulk_insert():
    """Test bulk insert functionality."""
    tmpdir = tempfile.mkdtemp()
    try:
        db_path = Path(tmpdir) / "test.db"
        db = TradeDatabase(db_path)
        
        # Prepare bulk data
        trades = []
        for i in range(10):
            trades.append({
                "market_slug": f"btc-updown-5m-{1751234700 + i}",
                "market_id": f"market_{i}",
                "side": "UP" if i % 2 == 0 else "DOWN",
                "entry_price": 0.9 + (i * 0.01),
                "exit_price": None,
                "amount": 10.0 + i,
                "shares": 10.5 + i,
                "fee": 0.2 + (i * 0.01),
                "outcome": "WON" if i % 3 == 0 else None,
                "pnl": 5.3 + i,
                "timestamp": datetime.now(timezone.utc),
            })
        
        # Bulk insert
        trade_ids = db.save_trades_bulk(trades, check_duplicates=False)
        
        # Verify all trades were saved
        all_trades = db.load_all_trades()
        assert len(all_trades) == 10
        
        # Verify all expected market_ids are present (order may vary due to timestamp)
        saved_market_ids = set(t.market_id for t in all_trades)
        expected_market_ids = {f"market_{i}" for i in range(10)}
        assert saved_market_ids == expected_market_ids
        
        db.close()
    finally:
        import shutil
        shutil.rmtree(tmpdir, ignore_errors=True)


def test_bulk_insert_empty():
    """Test bulk insert with empty list."""
    tmpdir = tempfile.mkdtemp()
    try:
        db_path = Path(tmpdir) / "test.db"
        db = TradeDatabase(db_path)
        
        trade_ids = db.save_trades_bulk([])
        assert trade_ids == []
        
        db.close()
    finally:
        import shutil
        shutil.rmtree(tmpdir, ignore_errors=True)


def test_bulk_insert_with_validation_error():
    """Test that bulk insert fails on validation error."""
    tmpdir = tempfile.mkdtemp()
    try:
        db_path = Path(tmpdir) / "test.db"
        db = TradeDatabase(db_path)
        
        # Prepare bulk data with invalid trade
        trades = [
            {
                "market_slug": "btc-updown-5m-1751234700",
                "market_id": "abc123",
                "side": "UP",
                "entry_price": 0.92,
                "exit_price": None,
                "amount": 10.0,
                "shares": 10.5,
                "fee": 0.2,
                "outcome": "WON",
                "pnl": 5.3,
                "timestamp": datetime.now(timezone.utc),
            },
            {
                "market_slug": "eth-updown-5m-1751234800",
                "market_id": "def456",
                "side": "INVALID",  # Invalid side
                "entry_price": 0.88,
                "exit_price": None,
                "amount": 15.0,
                "shares": 17.0,
                "fee": 0.3,
                "outcome": "LOST",
                "pnl": -7.5,
                "timestamp": datetime.now(timezone.utc),
            },
        ]
        
        # Should raise ValueError
        with pytest.raises(ValueError, match="side must be 'UP' or 'DOWN'"):
            db.save_trades_bulk(trades)
        
        # Verify no trades were saved (transaction rollback)
        all_trades = db.load_all_trades()
        assert len(all_trades) == 0
        
        db.close()
    finally:
        import shutil
        shutil.rmtree(tmpdir, ignore_errors=True)


def test_analyze_indexes():
    """Test index analysis."""
    tmpdir = tempfile.mkdtemp()
    try:
        db_path = Path(tmpdir) / "test.db"
        db = TradeDatabase(db_path)
        
        # Should not raise any errors
        db.analyze_indexes()
        
        db.close()
    finally:
        import shutil
        shutil.rmtree(tmpdir, ignore_errors=True)


def test_optimize_database():
    """Test database optimization."""
    tmpdir = tempfile.mkdtemp()
    try:
        db_path = Path(tmpdir) / "test.db"
        db = TradeDatabase(db_path)
        
        # Should not raise any errors
        db.optimize_database()
        
        db.close()
    finally:
        import shutil
        shutil.rmtree(tmpdir, ignore_errors=True)


def test_get_index_info():
    """Test getting index information."""
    tmpdir = tempfile.mkdtemp()
    try:
        db_path = Path(tmpdir) / "test.db"
        db = TradeDatabase(db_path)
        
        indexes = db.get_index_info()
        
        # Check that expected indexes exist
        assert "idx_market_slug" in indexes
        assert "idx_market_id" in indexes
        assert "idx_side" in indexes
        assert "idx_outcome" in indexes
        assert "idx_timestamp" in indexes
        assert "idx_duplicate_check" in indexes
        
        # Check index structure
        assert indexes["idx_market_slug"]["table"] == "trades"
        assert indexes["idx_market_slug"]["sql"] is not None
        
        db.close()
    finally:
        import shutil
        shutil.rmtree(tmpdir, ignore_errors=True)


def test_rebuild_index():
    """Test rebuilding an index."""
    tmpdir = tempfile.mkdtemp()
    try:
        db_path = Path(tmpdir) / "test.db"
        db = TradeDatabase(db_path)
        
        # Rebuild an existing index
        db.rebuild_index("idx_market_slug")
        
        # Verify index still exists
        indexes = db.get_index_info()
        assert "idx_market_slug" in indexes
        
        db.close()
    finally:
        import shutil
        shutil.rmtree(tmpdir, ignore_errors=True)


def test_rebuild_nonexistent_index():
    """Test that rebuilding nonexistent index raises error."""
    tmpdir = tempfile.mkdtemp()
    try:
        db_path = Path(tmpdir) / "test.db"
        db = TradeDatabase(db_path)
        
        with pytest.raises(ValueError, match="Index 'nonexistent' does not exist"):
            db.rebuild_index("nonexistent")
        
        db.close()
    finally:
        import shutil
        shutil.rmtree(tmpdir, ignore_errors=True)


def test_cache_lru_eviction():
    """Test that cache evicts oldest entries when full."""
    tmpdir = tempfile.mkdtemp()
    try:
        db_path = Path(tmpdir) / "test.db"
        db = TradeDatabase(db_path, enable_cache=True)
        
        # Set a small cache size for testing
        db._cache_max_size = 3
        
        # Add a trade
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
            timestamp=datetime.now(timezone.utc),
            check_duplicates=False
        )
        
        # Fill cache with different queries
        db.load_trades(filters={"side": "UP"})
        db.load_trades(filters={"side": "DOWN"})
        db.load_trades(filters={"outcome": "WON"})
        
        assert len(db._query_cache) == 3
        
        # Add one more query - should evict oldest
        db.load_trades(filters={"outcome": "LOST"})
        
        # Cache size should still be 3 (LRU eviction)
        assert len(db._query_cache) == 3
        
        db.close()
    finally:
        import shutil
        shutil.rmtree(tmpdir, ignore_errors=True)


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
