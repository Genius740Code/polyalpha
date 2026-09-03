"""
Database hgroup6 findings — #34 (OAUTH2 gate), #35 (bulk-insert id recovery).

Run with: pytest tests/unit/database/test_hgroup6_bulk_and_oauth.py
"""

import shutil
import tempfile
from datetime import datetime, timezone
from pathlib import Path

import pytest

from polyalpha.database import TradeDatabase


def _make_trade(market_id: str, timestamp: datetime, side: str = "UP") -> dict:
    return {
        "market_slug": "btc-updown-5m-1751234700",
        "market_id": market_id,
        "side": side,
        "entry_price": 0.92,
        "exit_price": None,
        "amount": 10.0,
        "shares": 10.5,
        "fee": 0.2,
        "outcome": "WON",
        "pnl": 5.3,
        "timestamp": timestamp,
        "market_session": "2024-01-01T12:00:00Z",
        "order_id": "order-1",
        "status": "pending",
    }


def test_bulk_insert_returns_ids_of_inserted_rows():
    """hgroup6 #35 — returned ids must match the rows we inserted."""
    tmpdir = tempfile.mkdtemp()
    try:
        db = TradeDatabase(Path(tmpdir) / "test.db")
        base = datetime(2025, 1, 1, 12, 0, tzinfo=timezone.utc)
        trades = [
            _make_trade(f"m{i}", base, side="DOWN" if i % 2 else "UP")
            for i in range(5)
        ]

        ids = db.save_trades_bulk(trades, check_duplicates=False)

        assert len(ids) == 5
        assert ids == sorted(ids)
        assert len(set(ids)) == 5

        for trade_id, trade in zip(ids, trades):
            row = db._repo.get_trade(trade_id)
            assert row is not None
            assert row.market_id == trade["market_id"]
        db.close()
    finally:
        shutil.rmtree(tmpdir, ignore_errors=True)


def test_bulk_insert_ids_correct_with_preexisting_higher_ids():
    """hgroup6 #35 — ids must be the inserted rows even when the table already
    holds higher ids (simulates a concurrent/later writer committing first)."""
    tmpdir = tempfile.mkdtemp()
    try:
        db = TradeDatabase(Path(tmpdir) / "test.db")
        base = datetime(2025, 1, 1, 12, 0, tzinfo=timezone.utc)

        existing = [_make_trade(f"pre{i}", base) for i in range(3)]
        db.save_trades_bulk(existing, check_duplicates=False)

        newer = [_make_trade(f"new{i}", base, side="DOWN") for i in range(2)]
        ids = db.save_trades_bulk(newer, check_duplicates=False)

        assert len(ids) == 2
        for trade_id, market_id in zip(ids, ("new0", "new1")):
            row = db._repo.get_trade(trade_id)
            assert row is not None
            assert row.market_id == market_id
        db.close()
    finally:
        shutil.rmtree(tmpdir, ignore_errors=True)


def test_oauth2_is_gated_at_selection():
    """hgroup6 #34 — selecting OAUTH2 fails fast instead of at authenticate()."""
    tmpdir = tempfile.mkdtemp()
    try:
        db = TradeDatabase(Path(tmpdir) / "test.db")

        with pytest.raises(NotImplementedError, match="OAUTH2"):
            db.set_auth_method("oauth2")

        db.set_auth_method("api_key")
        assert db.get_auth_method() == "api_key"
        db.close()
    finally:
        shutil.rmtree(tmpdir, ignore_errors=True)
