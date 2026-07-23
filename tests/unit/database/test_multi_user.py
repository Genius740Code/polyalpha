"""
Multi-user database tests.

Tests that multiple users can each have their own isolated trades,
and that user management (create, read, deactivate, delete) works correctly.
"""

import pytest
from datetime import datetime, timezone
from pathlib import Path
import tempfile
import hashlib

from polyalpha.database import TradeDatabase, DBUser


def _hash_password(password: str) -> str:
    return hashlib.sha256(password.encode()).hexdigest()


def _make_db() -> tuple:
    tmpdir = tempfile.mkdtemp()
    db_path = Path(tmpdir) / "test.db"
    db = TradeDatabase(db_path)
    return tmpdir, db


def _cleanup(tmpdir):
    import shutil
    shutil.rmtree(tmpdir, ignore_errors=True)


_trade_counter = 0


def _save_trade(db, **overrides):
    global _trade_counter
    _trade_counter += 1
    params = dict(
        market_slug=f"btc-updown-5m-{_trade_counter}",
        market_id=f"market_{_trade_counter}",
        side="UP",
        entry_price=0.92,
        exit_price=None,
        amount=10.0,
        shares=10.5,
        fee=0.2,
        outcome="WON",
        pnl=5.3,
        timestamp=datetime.now(timezone.utc),
    )
    params.update(overrides)
    return db.save_trade(**params)


class TestUserCRUD:
    def test_create_user(self):
        tmpdir, db = _make_db()
        try:
            uid = db.create_user("alice", _hash_password("pass"))
            assert uid > 0
            user = db.get_user(uid)
            assert user is not None
            assert user.username == "alice"
            assert user.is_active is True
            assert user.id == uid
            db.close()
        finally:
            _cleanup(tmpdir)

    def test_create_duplicate_user_raises(self):
        tmpdir, db = _make_db()
        try:
            db.create_user("alice", _hash_password("pass"))
            with pytest.raises(ValueError, match="already exists"):
                db.create_user("alice", _hash_password("other"))
            db.close()
        finally:
            _cleanup(tmpdir)

    def test_get_user_nonexistent(self):
        tmpdir, db = _make_db()
        try:
            user = db.get_user(999)
            assert user is None
            db.close()
        finally:
            _cleanup(tmpdir)

    def test_get_user_by_username(self):
        tmpdir, db = _make_db()
        try:
            uid = db.create_user("bob", _hash_password("pass"))
            user = db.get_user_by_username("bob")
            assert user is not None
            assert user.id == uid
            assert user.username == "bob"
            db.close()
        finally:
            _cleanup(tmpdir)

    def test_get_user_by_username_nonexistent(self):
        tmpdir, db = _make_db()
        try:
            user = db.get_user_by_username("nobody")
            assert user is None
            db.close()
        finally:
            _cleanup(tmpdir)

    def test_get_all_users(self):
        tmpdir, db = _make_db()
        try:
            u1 = db.create_user("alice", _hash_password("a"))
            u2 = db.create_user("bob", _hash_password("b"))
            users = db.get_all_users()
            assert len(users) == 2
            usernames = {u.username for u in users}
            assert usernames == {"alice", "bob"}
            db.close()
        finally:
            _cleanup(tmpdir)

    def test_get_all_users_empty(self):
        tmpdir, db = _make_db()
        try:
            users = db.get_all_users()
            assert users == []
            db.close()
        finally:
            _cleanup(tmpdir)

    def test_deactivate_user(self):
        tmpdir, db = _make_db()
        try:
            uid = db.create_user("alice", _hash_password("pass"))
            assert db.get_user(uid).is_active is True
            ok = db.deactivate_user(uid)
            assert ok is True
            assert db.get_user(uid).is_active is False
            db.close()
        finally:
            _cleanup(tmpdir)

    def test_deactivate_user_nonexistent(self):
        tmpdir, db = _make_db()
        try:
            ok = db.deactivate_user(999)
            assert ok is False
            db.close()
        finally:
            _cleanup(tmpdir)

    def test_delete_user_cascades_trades(self):
        tmpdir, db = _make_db()
        try:
            uid = db.create_user("alice", _hash_password("pass"))
            _save_trade(db, user_id=uid)
            _save_trade(db, user_id=uid)
            assert len(db.load_trades_by_user(uid)) == 2
            ok = db.delete_user(uid, reassign_trades=False)
            assert ok is True
            assert db.get_user(uid) is None
            assert len(db.load_all_trades()) == 0
            db.close()
        finally:
            _cleanup(tmpdir)

    def test_delete_user_reassigns_trades(self):
        tmpdir, db = _make_db()
        try:
            uid = db.create_user("alice", _hash_password("pass"))
            _save_trade(db, user_id=uid)
            _save_trade(db, user_id=uid)
            ok = db.delete_user(uid, reassign_trades=True)
            assert ok is True
            assert db.get_user(uid) is None
            trades = db.load_all_trades()
            assert len(trades) == 2
            assert all(t.user_id is None for t in trades)
            db.close()
        finally:
            _cleanup(tmpdir)

    def test_delete_user_nonexistent(self):
        tmpdir, db = _make_db()
        try:
            ok = db.delete_user(999)
            assert ok is False
            db.close()
        finally:
            _cleanup(tmpdir)


class TestMultiUserTrades:
    def test_save_trade_with_user_id(self):
        tmpdir, db = _make_db()
        try:
            uid = db.create_user("alice", _hash_password("pass"))
            tid = _save_trade(db, user_id=uid)
            assert tid > 0
            trades = db.load_all_trades()
            assert len(trades) == 1
            assert trades[0].user_id == uid
            db.close()
        finally:
            _cleanup(tmpdir)

    def test_save_trade_without_user_id(self):
        tmpdir, db = _make_db()
        try:
            tid = _save_trade(db)
            assert tid > 0
            trades = db.load_all_trades()
            assert len(trades) == 1
            assert trades[0].user_id is None
            db.close()
        finally:
            _cleanup(tmpdir)

    def test_user_trade_isolation(self):
        tmpdir, db = _make_db()
        try:
            alice = db.create_user("alice", _hash_password("a"))
            bob = db.create_user("bob", _hash_password("b"))

            _save_trade(db, market_slug="alice-trade", user_id=alice)
            _save_trade(db, market_slug="bob-trade", user_id=bob)

            alice_trades = db.load_trades_by_user(alice)
            bob_trades = db.load_trades_by_user(bob)

            assert len(alice_trades) == 1
            assert len(bob_trades) == 1
            assert alice_trades[0].market_slug == "alice-trade"
            assert bob_trades[0].market_slug == "bob-trade"
            assert alice_trades[0].user_id == alice
            assert bob_trades[0].user_id == bob
            db.close()
        finally:
            _cleanup(tmpdir)

    def test_user_trade_isolation_multiple_trades(self):
        tmpdir, db = _make_db()
        try:
            alice = db.create_user("alice", _hash_password("a"))
            bob = db.create_user("bob", _hash_password("b"))

            _save_trade(db, market_slug="a-1", user_id=alice)
            _save_trade(db, market_slug="a-2", user_id=alice)
            _save_trade(db, market_slug="a-3", user_id=alice)
            _save_trade(db, market_slug="b-1", user_id=bob)

            assert len(db.load_trades_by_user(alice)) == 3
            assert len(db.load_trades_by_user(bob)) == 1
            assert len(db.load_all_trades()) == 4
            db.close()
        finally:
            _cleanup(tmpdir)

    def test_load_trades_with_user_id_filter(self):
        tmpdir, db = _make_db()
        try:
            uid = db.create_user("alice", _hash_password("a"))
            _save_trade(db, user_id=uid)
            _save_trade(db, user_id=uid)

            trades = db.load_trades(filters={"user_id": uid})
            assert len(trades) == 2
            db.close()
        finally:
            _cleanup(tmpdir)

    def test_load_trades_with_user_id_none_filter(self):
        tmpdir, db = _make_db()
        try:
            _save_trade(db, market_slug="no-user")
            uid = db.create_user("alice", _hash_password("a"))
            _save_trade(db, user_id=uid)

            null_trades = db.load_trades(filters={"user_id": None})
            assert len(null_trades) == 1
            assert null_trades[0].market_slug == "no-user"
            db.close()
        finally:
            _cleanup(tmpdir)

    def test_get_user_statistics(self):
        tmpdir, db = _make_db()
        try:
            uid = db.create_user("alice", _hash_password("a"))
            _save_trade(db, pnl=10.0, fee=0.5, outcome="WON", user_id=uid)
            _save_trade(db, pnl=-5.0, fee=0.5, outcome="LOST", user_id=uid)

            stats = db.get_user_statistics(uid)
            assert stats.total_trades == 2
            assert stats.wins == 1
            assert stats.losses == 1
            assert stats.win_rate == 50.0
            assert stats.total_pnl == 5.0
            assert stats.total_fees == 1.0
            db.close()
        finally:
            _cleanup(tmpdir)

    def test_get_user_statistics_empty(self):
        tmpdir, db = _make_db()
        try:
            uid = db.create_user("alice", _hash_password("a"))
            stats = db.get_user_statistics(uid)
            assert stats.total_trades == 0
            assert stats.wins == 0
            assert stats.losses == 0
            assert stats.win_rate == 0.0
            assert stats.total_pnl == 0.0
            db.close()
        finally:
            _cleanup(tmpdir)


class TestSaveTradesBulkWithUser:
    def test_bulk_save_with_user_id(self):
        tmpdir, db = _make_db()
        try:
            uid = db.create_user("alice", _hash_password("a"))
            ts = datetime.now(timezone.utc)
            trades = [
                dict(market_slug="a-1", market_id="m1", side="UP",
                     entry_price=0.9, exit_price=None, amount=10.0,
                     shares=10.0, fee=0.2, outcome="WON", pnl=5.0, timestamp=ts),
                dict(market_slug="a-2", market_id="m2", side="DOWN",
                     entry_price=0.8, exit_price=None, amount=10.0,
                     shares=12.0, fee=0.2, outcome="LOST", pnl=-3.0, timestamp=ts),
            ]
            ids = db.save_trades_bulk(trades, check_duplicates=False, user_id=uid)
            assert len(ids) == 2

            user_trades = db.load_trades_by_user(uid)
            assert len(user_trades) == 2
            assert all(t.user_id == uid for t in user_trades)
            db.close()
        finally:
            _cleanup(tmpdir)

    def test_bulk_save_mixed_users(self):
        tmpdir, db = _make_db()
        try:
            alice = db.create_user("alice", _hash_password("a"))
            bob = db.create_user("bob", _hash_password("b"))
            ts = datetime.now(timezone.utc)

            alice_trades = [
                dict(market_slug="a-1", market_id="m1", side="UP",
                     entry_price=0.9, exit_price=None, amount=10.0,
                     shares=10.0, fee=0.2, outcome="WON", pnl=5.0, timestamp=ts),
            ]
            bob_trades = [
                dict(market_slug="b-1", market_id="m2", side="DOWN",
                     entry_price=0.8, exit_price=None, amount=10.0,
                     shares=12.0, fee=0.2, outcome="LOST", pnl=-3.0, timestamp=ts),
            ]

            db.save_trades_bulk(alice_trades, check_duplicates=False, user_id=alice)
            db.save_trades_bulk(bob_trades, check_duplicates=False, user_id=bob)

            assert len(db.load_trades_by_user(alice)) == 1
            assert len(db.load_trades_by_user(bob)) == 1
            assert len(db.load_all_trades()) == 2
            db.close()
        finally:
            _cleanup(tmpdir)


class TestUserTradeRecord:
    def test_trade_record_to_dict_includes_user_id(self):
        tmpdir, db = _make_db()
        try:
            uid = db.create_user("alice", _hash_password("a"))
            tid = _save_trade(db, user_id=uid)
            trades = db.load_all_trades()
            d = trades[0].to_dict()
            assert "user_id" in d
            assert d["user_id"] == uid
            db.close()
        finally:
            _cleanup(tmpdir)

    def test_trade_record_to_dict_user_id_none(self):
        tmpdir, db = _make_db()
        try:
            _save_trade(db)
            trades = db.load_all_trades()
            d = trades[0].to_dict()
            assert "user_id" in d
            assert d["user_id"] is None
            db.close()
        finally:
            _cleanup(tmpdir)


class TestUserMigration:
    def test_run_migrations_creates_users_table(self):
        tmpdir, db = _make_db()
        try:
            db.run_migrations()
            uid = db.create_user("migrated_user", _hash_password("x"))
            assert uid > 0
            db.close()
        finally:
            _cleanup(tmpdir)

    def test_get_schema_version_after_init(self):
        tmpdir, db = _make_db()
        try:
            version = db.get_schema_version()
            assert version >= 1
            db.close()
        finally:
            _cleanup(tmpdir)

    def test_new_table_has_user_id_column(self):
        tmpdir, db = _make_db()
        try:
            uid = db.create_user("alice", _hash_password("a"))
            _save_trade(db, user_id=uid)
            trade = db.load_all_trades()[0]
            assert hasattr(trade, "user_id")
            assert trade.user_id == uid
            db.close()
        finally:
            _cleanup(tmpdir)


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
