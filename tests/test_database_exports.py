"""
Database export tests — run with: pytest tests/test_database_exports.py
"""

import sys, os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))

import pytest
from datetime import datetime, timezone
from pathlib import Path
import tempfile
import json
import csv

from polyalpha.database import TradeDatabase


def test_export_csv():
    """Test CSV export functionality."""
    tmpdir = tempfile.mkdtemp()
    try:
        db_path = Path(tmpdir) / "test.db"
        csv_path = Path(tmpdir) / "trades.csv"
        
        # Create database and add test data
        db = TradeDatabase(db_path)
        
        # Add sample trades
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
            timestamp=datetime.now(timezone.utc)
        )
        
        # Export to CSV
        db.export_csv(csv_path)
        
        # Close database before cleanup
        db.close()
        
        # Verify file exists
        assert csv_path.exists()
        
        # Verify CSV content (sorted by timestamp DESC, so ETH comes first)
        with csv_path.open("r", encoding="utf-8") as f:
            reader = csv.DictReader(f)
            rows = list(reader)
            assert len(rows) == 2
            # Sort by ID to get consistent order
            rows.sort(key=lambda x: int(x["id"]))
            assert rows[0]["market_slug"] == "btc-updown-5m-1751234700"
            assert rows[0]["side"] == "UP"
            assert rows[1]["market_slug"] == "eth-updown-5m-1751234800"
            assert rows[1]["side"] == "DOWN"
    finally:
        # Cleanup
        import shutil
        shutil.rmtree(tmpdir, ignore_errors=True)


def test_export_csv_with_filters():
    """Test CSV export with filters."""
    tmpdir = tempfile.mkdtemp()
    try:
        db_path = Path(tmpdir) / "test.db"
        csv_path = Path(tmpdir) / "btc_trades.csv"
        
        db = TradeDatabase(db_path)
        
        # Add sample trades
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
            timestamp=datetime.now(timezone.utc)
        )
        
        # Export only BTC trades
        db.export_csv(csv_path, filters={"asset": "BTC"})
        
        db.close()
        
        # Verify only BTC trade is exported
        with csv_path.open("r", encoding="utf-8") as f:
            reader = csv.DictReader(f)
            rows = list(reader)
            assert len(rows) == 1
            assert rows[0]["market_slug"] == "btc-updown-5m-1751234700"
    finally:
        import shutil
        shutil.rmtree(tmpdir, ignore_errors=True)


def test_export_json():
    """Test JSON export functionality."""
    tmpdir = tempfile.mkdtemp()
    try:
        db_path = Path(tmpdir) / "test.db"
        json_path = Path(tmpdir) / "trades.json"
        
        db = TradeDatabase(db_path)
        
        # Add sample trade
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
        
        # Export to JSON
        db.export_json(json_path)
        
        db.close()
        
        # Verify file exists
        assert json_path.exists()
        
        # Verify JSON content
        with json_path.open("r", encoding="utf-8") as f:
            data = json.load(f)
            assert "metadata" in data
            assert "trades" in data
            assert data["metadata"]["total_trades"] == 1
            assert len(data["trades"]) == 1
            assert data["trades"][0]["market_slug"] == "btc-updown-5m-1751234700"
            assert "export_timestamp" in data["metadata"]
    finally:
        import shutil
        shutil.rmtree(tmpdir, ignore_errors=True)


def test_export_json_with_filters():
    """Test JSON export with filters."""
    tmpdir = tempfile.mkdtemp()
    try:
        db_path = Path(tmpdir) / "test.db"
        json_path = Path(tmpdir) / "won_trades.json"
        
        db = TradeDatabase(db_path)
        
        # Add sample trades
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
            timestamp=datetime.now(timezone.utc)
        )
        
        # Export only won trades
        db.export_json(json_path, filters={"outcome": "WON"})
        
        db.close()
        
        # Verify only won trade is exported
        with json_path.open("r", encoding="utf-8") as f:
            data = json.load(f)
            assert data["metadata"]["total_trades"] == 1
            assert len(data["trades"]) == 1
            assert data["trades"][0]["outcome"] == "WON"
    finally:
        import shutil
        shutil.rmtree(tmpdir, ignore_errors=True)


def test_export_parquet_no_dependency():
    """Test that Parquet export raises ImportError without pyarrow."""
    tmpdir = tempfile.mkdtemp()
    try:
        db_path = Path(tmpdir) / "test.db"
        parquet_path = Path(tmpdir) / "trades.parquet"
        
        db = TradeDatabase(db_path)
        
        # Add sample trade
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
        
        # Try to export without pyarrow (should raise ImportError)
        # We'll mock the import to fail
        import sys
        import builtins
        
        # Save original import
        original_import = builtins.__import__
        
        def mock_import(name, *args, **kwargs):
            if name == "pyarrow":
                raise ImportError("pyarrow not installed")
            return original_import(name, *args, **kwargs)
        
        builtins.__import__ = mock_import
        
        try:
            with pytest.raises(ImportError, match="pyarrow is required"):
                db.export_parquet(parquet_path)
        finally:
            # Restore original import
            builtins.__import__ = original_import
            db.close()
    finally:
        import shutil
        shutil.rmtree(tmpdir, ignore_errors=True)


def test_export_excel_no_dependency():
    """Test that Excel export raises ImportError without openpyxl."""
    tmpdir = tempfile.mkdtemp()
    try:
        db_path = Path(tmpdir) / "test.db"
        excel_path = Path(tmpdir) / "trades.xlsx"
        
        db = TradeDatabase(db_path)
        
        # Add sample trade
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
        
        # Try to export without openpyxl (should raise ImportError)
        import sys
        import builtins
        
        # Save original import
        original_import = builtins.__import__
        
        def mock_import(name, *args, **kwargs):
            if name == "openpyxl":
                raise ImportError("openpyxl not installed")
            return original_import(name, *args, **kwargs)
        
        builtins.__import__ = mock_import
        
        try:
            with pytest.raises(ImportError, match="openpyxl is required"):
                db.export_excel(excel_path)
        finally:
            # Restore original import
            builtins.__import__ = original_import
            db.close()
    finally:
        import shutil
        shutil.rmtree(tmpdir, ignore_errors=True)


def test_export_empty_database():
    """Test export when database has no trades."""
    tmpdir = tempfile.mkdtemp()
    try:
        db_path = Path(tmpdir) / "test.db"
        csv_path = Path(tmpdir) / "trades.csv"
        json_path = Path(tmpdir) / "trades.json"
        
        db = TradeDatabase(db_path)
        
        # Export empty database (should not raise error, just log warning)
        db.export_csv(csv_path)
        db.export_json(json_path)
        
        db.close()
        
        # Files should not be created or should be empty
        # The implementation returns early without creating files when no trades exist
    finally:
        import shutil
        shutil.rmtree(tmpdir, ignore_errors=True)


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
