"""
Paper wallet tests — run with: pytest tests/unit/trading/test_paper_wallet.py
"""

import pytest
from polyalpha.trading.wallet import PaperWallet, WalletManager, WalletSelectionStrategy
from polyalpha.trading.paper import PaperOrder, PaperPosition, PaperConfig
from polyalpha.core import OrderNotFound, PositionNotFound


# ── Fixtures ───────────────────────────────────────────────────────────────────

@pytest.fixture
def order():
    return PaperOrder(
        id="ord-001",
        market_id="btc-up-123",
        slug="btc-up-123",
        side="UP",
        price=0.55,
        amount=20.0,
        shares=36.0,
        fee=0.4,
        status="filled",
        is_limit=False,
    )


@pytest.fixture
def position():
    return PaperPosition(
        market_id="btc-up-123",
        slug="btc-up-123",
        question="Will BTC be higher?",
        side="UP",
        shares=36.0,
        avg_price=0.55,
        current_price=0.65,
    )


@pytest.fixture
def wallet():
    return PaperWallet(wallet_id="wal_1", balance=1000.0)


@pytest.fixture
def wallet_with_data(wallet, order, position):
    wallet.add_order(order)
    wallet.add_position(position)
    return wallet


@pytest.fixture
def manager():
    return WalletManager()


@pytest.fixture
def populated_manager(manager, wallet):
    manager.add_wallet(wallet)
    return manager


# ── PaperWallet creation and properties ──────────────────────────────────────

class TestPaperWalletCreation:
    @pytest.mark.unit
    def test_create_default(self):
        w = PaperWallet(wallet_id="w1", balance=500.0)
        assert w.wallet_id == "w1"
        assert w.balance == 500.0
        assert w.orders == {}
        assert w.positions == {}
        assert w.risk_manager is not None
        assert w.created_at is not None

    @pytest.mark.unit
    def test_create_with_config(self):
        config = PaperConfig(fee_mode="zero")
        w = PaperWallet(wallet_id="w2", balance=250.0, config=config)
        assert w.config.fee_mode == "zero"
        assert w.risk_manager.config.fee_mode == "zero"

    @pytest.mark.unit
    def test_orders_property(self, wallet, order):
        wallet.add_order(order)
        assert wallet.orders is wallet._orders
        assert "ord-001" in wallet.orders

    @pytest.mark.unit
    def test_positions_property(self, wallet, position):
        wallet.add_position(position)
        assert wallet.positions is wallet._positions
        assert "btc-up-123:UP" in wallet.positions

    @pytest.mark.unit
    def test_risk_manager_property(self, wallet):
        rm = wallet.risk_manager
        assert rm is wallet._risk_manager
        assert rm.config is wallet.config


# ── set_balance ──────────────────────────────────────────────────────────────

class TestSetBalance:
    @pytest.mark.unit
    def test_set_balance_positive(self, wallet):
        wallet.set_balance(2000.0)
        assert wallet.balance == 2000.0

    @pytest.mark.unit
    def test_set_balance_zero(self, wallet):
        wallet.set_balance(0.0)
        assert wallet.balance == 0.0

    @pytest.mark.unit
    def test_set_balance_negative(self, wallet):
        with pytest.raises(ValueError, match="Balance cannot be negative"):
            wallet.set_balance(-100.0)


# ── Order management ─────────────────────────────────────────────────────────

class TestOrderManagement:
    @pytest.mark.unit
    def test_add_order(self, wallet, order):
        wallet.add_order(order)
        assert wallet._orders["ord-001"] is order

    @pytest.mark.unit
    def test_add_multiple_orders(self, wallet, order):
        order2 = PaperOrder(
            id="ord-002", market_id="eth-up-456", slug="eth-up-456",
            side="DOWN", price=0.45, amount=15.0, shares=33.0,
            fee=0.3, status="open", is_limit=True,
        )
        wallet.add_order(order)
        wallet.add_order(order2)
        assert len(wallet._orders) == 2

    @pytest.mark.unit
    def test_get_order(self, wallet_with_data):
        o = wallet_with_data.get_order("ord-001")
        assert o.id == "ord-001"
        assert o.side == "UP"

    @pytest.mark.unit
    def test_get_order_not_found(self, wallet):
        with pytest.raises(OrderNotFound, match="Order missing not found"):
            wallet.get_order("missing")

    @pytest.mark.unit
    def test_remove_order(self, wallet_with_data):
        wallet_with_data.remove_order("ord-001")
        assert "ord-001" not in wallet_with_data._orders

    @pytest.mark.unit
    def test_remove_order_nonexistent(self, wallet):
        wallet.remove_order("nonexistent")
        assert "nonexistent" not in wallet._orders


# ── Position management ──────────────────────────────────────────────────────

class TestPositionManagement:
    @pytest.mark.unit
    def test_add_position(self, wallet, position):
        wallet.add_position(position)
        key = f"{position.market_id}:{position.side}"
        assert wallet._positions[key] is position

    @pytest.mark.unit
    def test_add_position_updates_existing(self, wallet, position):
        wallet.add_position(position)
        updated = PaperPosition(
            market_id="btc-up-123", slug="btc-up-123",
            question="Will BTC be higher?", side="UP",
            shares=72.0, avg_price=0.57, current_price=0.55,
        )
        wallet.add_position(updated)
        key = "btc-up-123:UP"
        assert wallet._positions[key] is updated
        assert wallet._positions[key].shares == 72.0

    @pytest.mark.unit
    def test_get_position(self, wallet_with_data):
        pos = wallet_with_data.get_position("btc-up-123", "UP")
        assert pos.market_id == "btc-up-123"
        assert pos.side == "UP"
        assert pos.shares == 36.0

    @pytest.mark.unit
    def test_get_position_not_found(self, wallet):
        with pytest.raises(PositionNotFound, match="eth-up-456:DOWN not found"):
            wallet.get_position("eth-up-456", "DOWN")

    @pytest.mark.unit
    def test_get_all_positions(self, wallet_with_data):
        positions = wallet_with_data.get_all_positions()
        assert len(positions) == 1
        assert positions[0].market_id == "btc-up-123"

    @pytest.mark.unit
    def test_get_all_positions_empty(self, wallet):
        assert wallet.get_all_positions() == []

    @pytest.mark.unit
    def test_remove_position(self, wallet_with_data):
        wallet_with_data.remove_position("btc-up-123", "UP")
        assert "btc-up-123:UP" not in wallet_with_data._positions

    @pytest.mark.unit
    def test_remove_position_nonexistent(self, wallet):
        wallet.remove_position("nonexistent", "UP")
        assert "nonexistent:UP" not in wallet._positions


# ── get_summary ──────────────────────────────────────────────────────────────

class TestGetSummary:
    @pytest.mark.unit
    def test_summary_empty_wallet(self, wallet):
        summary = wallet.get_summary()
        assert summary["wallet_id"] == "wal_1"
        assert summary["balance"] == 1000.0
        assert summary["total_positions"] == 0
        assert summary["total_orders"] == 0
        assert summary["total_cost_basis"] == 0.0
        assert summary["total_current_value"] == 0.0
        assert summary["total_pnl"] == 0.0
        assert summary["available_balance"] == 1000.0

    @pytest.mark.unit
    def test_summary_with_data(self, wallet_with_data):
        summary = wallet_with_data.get_summary()
        assert summary["wallet_id"] == "wal_1"
        assert summary["total_positions"] == 1
        assert summary["total_orders"] == 1
        assert summary["total_cost_basis"] > 0
        assert summary["total_current_value"] > 0
        assert summary["total_pnl"] > 0


# ── WalletManager creation and wallet management ─────────────────────────────

class TestWalletManagerCreation:
    @pytest.mark.unit
    def test_create_default(self, manager):
        assert manager.wallets == {}
        assert manager.selection_strategy == WalletSelectionStrategy.ROUND_ROBIN
        assert manager.custom_selector is None
        assert manager._round_robin_index == 0

    @pytest.mark.unit
    def test_create_with_wallets(self):
        w1 = PaperWallet("w1", 100.0)
        w2 = PaperWallet("w2", 200.0)
        wm = WalletManager(wallets={"w1": w1, "w2": w2})
        assert len(wm.wallets) == 2


class TestWalletManagerWallets:
    @pytest.mark.unit
    def test_add_wallet(self, manager, wallet):
        manager.add_wallet(wallet)
        assert "wal_1" in manager.wallets
        assert manager.wallets["wal_1"] is wallet

    @pytest.mark.unit
    def test_add_wallet_duplicate(self, manager, wallet):
        manager.add_wallet(wallet)
        with pytest.raises(ValueError, match="already exists"):
            manager.add_wallet(wallet)

    @pytest.mark.unit
    def test_remove_wallet(self, populated_manager):
        populated_manager.remove_wallet("wal_1")
        assert "wal_1" not in populated_manager.wallets

    @pytest.mark.unit
    def test_remove_wallet_nonexistent(self, manager):
        manager.remove_wallet("nonexistent")
        assert "nonexistent" not in manager.wallets

    @pytest.mark.unit
    def test_get_wallet(self, populated_manager):
        w = populated_manager.get_wallet("wal_1")
        assert w.wallet_id == "wal_1"
        assert w.balance == 1000.0

    @pytest.mark.unit
    def test_get_wallet_not_found(self, manager):
        with pytest.raises(ValueError, match="not found"):
            manager.get_wallet("missing")

    @pytest.mark.unit
    def test_get_all_wallets(self, populated_manager):
        w2 = PaperWallet("wal_2", 500.0)
        populated_manager.add_wallet(w2)
        all_wallets = populated_manager.get_all_wallets()
        assert len(all_wallets) == 2
        ids = {w.wallet_id for w in all_wallets}
        assert ids == {"wal_1", "wal_2"}

    @pytest.mark.unit
    def test_get_all_wallets_empty(self, manager):
        assert manager.get_all_wallets() == []


# ── select_wallet strategies ─────────────────────────────────────────────────

class TestSelectWallet:
    @pytest.fixture
    def multi_wallet_manager(self):
        wm = WalletManager()
        wm.add_wallet(PaperWallet("w_a", 100.0))
        wm.add_wallet(PaperWallet("w_b", 500.0))
        wm.add_wallet(PaperWallet("w_c", 300.0))
        return wm

    @pytest.mark.unit
    def test_select_empty_raises(self, manager):
        with pytest.raises(ValueError, match="No wallets available"):
            manager.select_wallet()

    @pytest.mark.unit
    def test_select_single_wallet(self, populated_manager):
        w = populated_manager.select_wallet()
        assert w.wallet_id == "wal_1"

    @pytest.mark.unit
    def test_select_round_robin_cycles(self, multi_wallet_manager):
        wm = multi_wallet_manager
        ids = [wm.select_wallet(WalletSelectionStrategy.ROUND_ROBIN).wallet_id for _ in range(3)]
        assert len(set(ids)) == 3

    @pytest.mark.unit
    def test_select_round_robin_wraps_around(self, multi_wallet_manager):
        wm = multi_wallet_manager
        first = wm.select_wallet(WalletSelectionStrategy.ROUND_ROBIN).wallet_id
        wm.select_wallet(WalletSelectionStrategy.ROUND_ROBIN)
        wm.select_wallet(WalletSelectionStrategy.ROUND_ROBIN)
        fourth = wm.select_wallet(WalletSelectionStrategy.ROUND_ROBIN).wallet_id
        assert first == fourth

    @pytest.mark.unit
    def test_select_balance_based(self, multi_wallet_manager):
        w = multi_wallet_manager.select_wallet(WalletSelectionStrategy.BALANCE_BASED)
        assert w.wallet_id == "w_b"
        assert w.balance == 500.0

    @pytest.mark.unit
    def test_select_balance_based_tie(self):
        wm = WalletManager()
        wm.add_wallet(PaperWallet("w_x", 300.0))
        wm.add_wallet(PaperWallet("w_y", 300.0))
        w = wm.select_wallet(WalletSelectionStrategy.BALANCE_BASED)
        assert w.balance == 300.0

    @pytest.mark.unit
    def test_select_random(self, multi_wallet_manager):
        w = multi_wallet_manager.select_wallet(WalletSelectionStrategy.RANDOM)
        assert w.wallet_id in {"w_a", "w_b", "w_c"}

    @pytest.mark.unit
    def test_select_custom_without_selector(self, multi_wallet_manager):
        with pytest.raises(ValueError, match="Custom selector not provided"):
            multi_wallet_manager.select_wallet(WalletSelectionStrategy.CUSTOM)

    @pytest.mark.unit
    def test_select_custom_selector(self, multi_wallet_manager):
        multi_wallet_manager.set_custom_selector(lambda wallets: wallets[-1])
        w = multi_wallet_manager.select_wallet()
        assert w.wallet_id == "w_c"

    @pytest.mark.unit
    def test_select_uses_default_strategy(self, multi_wallet_manager):
        ids = [multi_wallet_manager.select_wallet().wallet_id for _ in range(3)]
        assert len(set(ids)) == 3


# ── set_selection_strategy / set_custom_selector ─────────────────────────────

class TestSelectionStrategy:
    @pytest.mark.unit
    def test_set_selection_strategy(self, manager):
        manager.set_selection_strategy(WalletSelectionStrategy.BALANCE_BASED)
        assert manager.selection_strategy == WalletSelectionStrategy.BALANCE_BASED

    @pytest.mark.unit
    def test_set_selection_strategy_resets_index(self):
        wm = WalletManager()
        wm.add_wallet(PaperWallet("w_a", 100.0))
        wm.add_wallet(PaperWallet("w_b", 200.0))
        wm.select_wallet()
        assert wm._round_robin_index == 1
        wm.set_selection_strategy(WalletSelectionStrategy.ROUND_ROBIN)
        assert wm._round_robin_index == 0

    @pytest.mark.unit
    def test_set_custom_selector(self, manager):
        manager.set_custom_selector(lambda wallets: wallets[0])
        assert manager.custom_selector is not None
        assert manager.selection_strategy == WalletSelectionStrategy.CUSTOM

    @pytest.mark.unit
    def test_custom_selector_used_by_select(self, multi_wallet_manager):
        multi_wallet_manager.set_custom_selector(lambda wallets: [w for w in wallets if w.balance > 200][0])
        w = multi_wallet_manager.select_wallet()
        assert w.balance > 200

    @pytest.fixture
    def multi_wallet_manager(self):
        wm = WalletManager()
        wm.add_wallet(PaperWallet("w_a", 100.0))
        wm.add_wallet(PaperWallet("w_b", 500.0))
        wm.add_wallet(PaperWallet("w_c", 300.0))
        return wm


# ── Aggregated and per-wallet summaries ──────────────────────────────────────

class TestSummaries:
    @pytest.mark.unit
    def test_get_aggregated_summary_empty(self, manager):
        summary = manager.get_aggregated_summary()
        assert summary["total_wallets"] == 0
        assert summary["total_balance"] == 0.0
        assert summary["total_positions"] == 0
        assert summary["total_orders"] == 0
        assert summary["total_pnl"] == 0.0

    @pytest.mark.unit
    def test_get_aggregated_summary(self, populated_manager):
        w2 = PaperWallet("wal_2", 500.0)
        populated_manager.add_wallet(w2)
        summary = populated_manager.get_aggregated_summary()
        assert summary["total_wallets"] == 2
        assert summary["total_balance"] == 1500.0
        assert summary["total_positions"] == 0
        assert summary["total_orders"] == 0

    @pytest.mark.unit
    def test_get_aggregated_summary_with_data(self, populated_manager, order, position):
        populated_manager.get_wallet("wal_1").add_order(order)
        populated_manager.get_wallet("wal_1").add_position(position)
        summary = populated_manager.get_aggregated_summary()
        assert summary["total_orders"] == 1
        assert summary["total_positions"] == 1
        assert summary["total_cost_basis"] > 0

    @pytest.mark.unit
    def test_get_per_wallet_summary_empty(self, manager):
        assert manager.get_per_wallet_summary() == {}

    @pytest.mark.unit
    def test_get_per_wallet_summary(self, populated_manager):
        w2 = PaperWallet("wal_2", 500.0)
        populated_manager.add_wallet(w2)
        per_wallet = populated_manager.get_per_wallet_summary()
        assert set(per_wallet.keys()) == {"wal_1", "wal_2"}
        assert per_wallet["wal_1"]["balance"] == 1000.0
        assert per_wallet["wal_2"]["balance"] == 500.0

    @pytest.mark.unit
    def test_get_per_wallet_summary_isolated(self, populated_manager, order):
        populated_manager.get_wallet("wal_1").add_order(order)
        per_wallet = populated_manager.get_per_wallet_summary()
        assert per_wallet["wal_1"]["total_orders"] == 1


# ── Edge cases ───────────────────────────────────────────────────────────────

class TestEdgeCases:
    @pytest.mark.unit
    def test_wallet_zero_balance(self):
        w = PaperWallet("w_zero", 0.0)
        summary = w.get_summary()
        assert summary["available_balance"] == 0.0

    @pytest.mark.unit
    def test_remove_all_wallets(self, populated_manager):
        populated_manager.remove_wallet("wal_1")
        assert populated_manager.get_all_wallets() == []
        with pytest.raises(ValueError, match="No wallets available"):
            populated_manager.select_wallet()

    @pytest.mark.unit
    def test_manager_remove_nonexistent_no_error(self, manager):
        manager.remove_wallet("does_not_exist")
        assert "does_not_exist" not in manager.wallets

    @pytest.mark.unit
    def test_aggregated_summary_after_removal(self, populated_manager):
        w2 = PaperWallet("wal_2", 500.0)
        populated_manager.add_wallet(w2)
        populated_manager.remove_wallet("wal_1")
        summary = populated_manager.get_aggregated_summary()
        assert summary["total_wallets"] == 1
        assert summary["total_balance"] == 500.0

    @pytest.mark.unit
    def test_order_added_after_creation(self, wallet):
        o = PaperOrder(
            id="ord-late", market_id="test", slug="test",
            side="DOWN", price=0.3, amount=10.0, shares=33.0,
            fee=0.2, status="open", is_limit=True,
        )
        wallet.add_order(o)
        assert wallet.get_order("ord-late").status == "open"

    @pytest.mark.unit
    def test_position_added_after_creation(self, wallet):
        pos = PaperPosition(
            market_id="new-mkt", slug="new-mkt",
            question="New market?", side="DOWN",
            shares=10.0, avg_price=0.40, current_price=0.50,
        )
        wallet.add_position(pos)
        assert wallet.get_position("new-mkt", "DOWN").shares == 10.0

    @pytest.mark.unit
    def test_unknown_strategy(self, manager):
        manager.add_wallet(PaperWallet("w1", 100.0))
        manager.add_wallet(PaperWallet("w2", 200.0))
        with pytest.raises(ValueError, match="Unknown strategy"):
            manager.select_wallet("unknown_strategy")  # type: ignore[arg-type]


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
