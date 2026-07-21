"""
Tests for wallet/wallet_manager.py — run with: pytest tests/unit/wallet/test_wallet_manager.py
"""

import pytest
from unittest.mock import Mock, patch, MagicMock, PropertyMock
from pathlib import Path

from polyalpha.wallet.wallet_manager import (
    WalletManager,
    WalletType,
    WalletConfig,
)
from polyalpha.wallet.wallet_security import WalletStorageType


@pytest.fixture
def wallet_manager(temp_dir):
    return WalletManager(
        storage_type=WalletStorageType.FILE,
        storage_path=temp_dir,
    )


@pytest.fixture
def sample_address():
    return "0x1234567890123456789012345678901234567890"


@pytest.fixture
def sample_address2():
    return "0x2234567890123456789012345678901234567890"


# ── Initialization Tests ─────────────────────────────────────────────────────

@pytest.mark.unit
class TestWalletManagerInit:
    def test_initialization(self, temp_dir):
        wm = WalletManager(storage_type=WalletStorageType.FILE, storage_path=temp_dir)
        assert wm._storage_type == WalletStorageType.FILE
        assert wm._storage_path == temp_dir
        assert wm._wallets == {}
        assert wm._multisig_wallets == {}
        assert wm._default_wallet is None

    def test_initialization_with_rpc(self, temp_dir):
        wm = WalletManager(
            storage_type=WalletStorageType.FILE,
            storage_path=temp_dir,
            rpc_url="https://polygon-rpc.com",
        )
        assert wm._rpc_url == "https://polygon-rpc.com"


# ── Software Wallet Tests ────────────────────────────────────────────────────

@pytest.mark.unit
class TestSoftwareWallet:
    def test_add_software_wallet(self, wallet_manager, sample_address):
        wallet_manager.add_software_wallet(
            address=sample_address,
            private_key="0x" + "a" * 64,
            password="test_password",
        )
        wallets = wallet_manager.list_wallets()
        assert len(wallets) == 1
        assert wallets[0]["address"] == sample_address
        assert wallets[0]["type"] == "software"

    def test_add_software_wallet_with_name(self, wallet_manager, sample_address):
        wallet_manager.add_software_wallet(
            address=sample_address,
            private_key="0x" + "a" * 64,
            password="test_password",
            name="My Wallet",
        )
        wallets = wallet_manager.list_wallets()
        assert wallets[0]["name"] == "My Wallet"

    def test_add_software_wallet_set_default(self, wallet_manager, sample_address):
        wallet_manager.add_software_wallet(
            address=sample_address,
            private_key="0x" + "a" * 64,
            password="test_password",
            set_as_default=True,
        )
        assert wallet_manager.get_default_wallet() == sample_address

    def test_add_software_wallet_with_metadata(self, wallet_manager, sample_address):
        wallet_manager.add_software_wallet(
            address=sample_address,
            private_key="0x" + "a" * 64,
            password="test_password",
            metadata={"network": "polygon", "label": "primary"},
        )
        info = wallet_manager.get_wallet_info(sample_address)
        assert info["metadata"] == {"network": "polygon", "label": "primary"}

    def test_add_software_wallet_twice(self, wallet_manager, sample_address):
        wallet_manager.add_software_wallet(
            address=sample_address,
            private_key="0x" + "a" * 64,
            password="test_password",
        )
        wallets = wallet_manager.list_wallets()
        assert len(wallets) == 1


# ── Multi-Sig Wallet Tests ───────────────────────────────────────────────────

@pytest.mark.unit
class TestMultiSigWallet:
    def test_add_multisig_wallet(self, wallet_manager):
        from polyalpha.wallet.multisig_wallet import MultiSigSigner

        signers = [
            MultiSigSigner(address="0x" + "1" * 40, weight=1),
            MultiSigSigner(address="0x" + "2" * 40, weight=1),
        ]
        wallet_manager.add_multisig_wallet(
            address="0x" + "0" * 40,
            signers=signers,
            required_weight=2,
        )
        wallets = wallet_manager.list_wallets()
        assert len(wallets) == 1
        assert wallets[0]["type"] == "multisig"

    def test_add_multisig_wallet_set_default(self, wallet_manager):
        from polyalpha.wallet.multisig_wallet import MultiSigSigner

        signers = [
            MultiSigSigner(address="0x" + "1" * 40, weight=1),
        ]
        wallet_manager.add_multisig_wallet(
            address="0x" + "0" * 40,
            signers=signers,
            required_weight=1,
            set_as_default=True,
        )
        assert wallet_manager.get_default_wallet() == "0x" + "0" * 40

    def test_multisig_info(self, wallet_manager):
        from polyalpha.wallet.multisig_wallet import MultiSigSigner

        signers = [
            MultiSigSigner(address="0x" + "1" * 40, weight=1),
            MultiSigSigner(address="0x" + "2" * 40, weight=1),
        ]
        wallet_manager.add_multisig_wallet(
            address="0x" + "0" * 40,
            signers=signers,
            required_weight=2,
        )
        info = wallet_manager.get_wallet_info("0x" + "0" * 40)
        assert info["type"] == "multisig"
        assert info["required_weight"] == 2
        assert len(info["signers"]) == 2


# ── Get Private Key Tests ────────────────────────────────────────────────────

@pytest.mark.unit
class TestGetPrivateKey:
    def test_get_private_key(self, wallet_manager, sample_address):
        wallet_manager.add_software_wallet(
            address=sample_address,
            private_key="0x" + "a" * 64,
            password="test_password",
        )
        key = wallet_manager.get_private_key(sample_address, "test_password")
        assert key == "0x" + "a" * 64

    def test_get_private_key_from_config(self, wallet_manager, sample_address):
        wallet_manager.add_software_wallet(
            address=sample_address,
            private_key="0x" + "a" * 64,
            password="stored_password",
        )
        key = wallet_manager.get_private_key(sample_address)
        assert key == "0x" + "a" * 64

    def test_get_private_key_not_found(self, wallet_manager):
        with pytest.raises(ValueError, match="not found"):
            wallet_manager.get_private_key("0xunknown")

    def test_get_private_key_wrong_type(self, wallet_manager):
        from polyalpha.wallet.multisig_wallet import MultiSigSigner

        signers = [MultiSigSigner(address="0x" + "1" * 40, weight=1)]
        wallet_manager.add_multisig_wallet(
            address="0x" + "0" * 40, signers=signers, required_weight=1,
        )
        with pytest.raises(ValueError, match="not a software wallet"):
            wallet_manager.get_private_key("0x" + "0" * 40)


# ── Create Signer Tests ──────────────────────────────────────────────────────

@pytest.mark.unit
class TestCreateSigner:
    def test_create_signer_software(self, wallet_manager, sample_address):
        wallet_manager.add_software_wallet(
            address=sample_address,
            private_key="0x" + "a" * 64,
            password="test_password",
            set_as_default=True,
        )
        signer = wallet_manager.create_signer()
        assert signer is not None

    def test_create_signer_no_default(self, wallet_manager):
        with pytest.raises(ValueError, match="No wallet specified"):
            wallet_manager.create_signer()

    def test_create_signer_wallet_not_found(self, wallet_manager):
        wallet_manager._default_wallet = "0xnonexistent"
        with pytest.raises(ValueError, match="not found"):
            wallet_manager.create_signer()

    def test_create_signer_multisig(self, wallet_manager):
        from polyalpha.wallet.multisig_wallet import MultiSigSigner

        signers = [MultiSigSigner(address="0x" + "1" * 40, weight=1)]
        wallet_manager.add_multisig_wallet(
            address="0x" + "0" * 40,
            signers=signers,
            required_weight=1,
            set_as_default=True,
        )
        signer = wallet_manager.create_signer()
        assert signer is not None


# ── Sign Transaction Tests ───────────────────────────────────────────────────

@pytest.mark.unit
class TestSignTransaction:
    def test_sign_transaction_no_default(self, wallet_manager):
        with pytest.raises(ValueError, match="No wallet specified"):
            wallet_manager.sign_transaction({"to": "0x1234"})

    def test_sign_transaction_no_address(self, wallet_manager, sample_address):
        wallet_manager.add_software_wallet(
            address=sample_address,
            private_key="0x" + "a" * 64,
            password="test_password",
        )
        with pytest.raises(ValueError, match="No wallet specified"):
            wallet_manager.sign_transaction({"to": "0x1234"})


# ── Remove Wallet Tests ──────────────────────────────────────────────────────

@pytest.mark.unit
class TestRemoveWallet:
    def test_remove_software_wallet(self, wallet_manager, sample_address):
        wallet_manager.add_software_wallet(
            address=sample_address,
            private_key="0x" + "a" * 64,
            password="test_password",
            set_as_default=True,
        )
        wallet_manager.remove_wallet(sample_address)
        assert len(wallet_manager.list_wallets()) == 0
        assert wallet_manager.get_default_wallet() is None

    def test_remove_nonexistent_wallet(self, wallet_manager):
        with pytest.raises(ValueError, match="not found"):
            wallet_manager.remove_wallet("0xunknown")

    def test_remove_updates_default(self, wallet_manager, sample_address, sample_address2):
        wallet_manager.add_software_wallet(
            address=sample_address, private_key="0x" + "a" * 64,
            password="test_password", set_as_default=True,
        )
        wallet_manager.add_software_wallet(
            address=sample_address2, private_key="0x" + "b" * 64,
            password="test_password2",
        )
        wallet_manager.remove_wallet(sample_address)
        assert wallet_manager.get_default_wallet() == sample_address2

    def test_remove_multisig(self, wallet_manager):
        from polyalpha.wallet.multisig_wallet import MultiSigSigner

        signers = [MultiSigSigner(address="0x" + "1" * 40, weight=1)]
        wallet_manager.add_multisig_wallet(
            address="0x" + "0" * 40, signers=signers, required_weight=1,
        )
        wallet_manager.remove_wallet("0x" + "0" * 40)
        assert len(wallet_manager.list_wallets()) == 0


# ── List & Info Tests ────────────────────────────────────────────────────────

@pytest.mark.unit
class TestListAndInfo:
    def test_list_wallets_empty(self, wallet_manager):
        assert wallet_manager.list_wallets() == []

    def test_list_wallets_multiple(self, wallet_manager, sample_address, sample_address2):
        wallet_manager.add_software_wallet(
            address=sample_address, private_key="0x" + "a" * 64,
            password="p1", name="Wallet 1",
        )
        wallet_manager.add_software_wallet(
            address=sample_address2, private_key="0x" + "b" * 64,
            password="p2", name="Wallet 2",
        )
        wallets = wallet_manager.list_wallets()
        assert len(wallets) == 2

    def test_get_wallet_info_exists(self, wallet_manager, sample_address):
        wallet_manager.add_software_wallet(
            address=sample_address, private_key="0x" + "a" * 64,
            password="test_password", name="Test Wallet",
        )
        info = wallet_manager.get_wallet_info(sample_address)
        assert info["address"] == sample_address
        assert info["name"] == "Test Wallet"
        assert info["type"] == "software"

    def test_get_wallet_info_not_found(self, wallet_manager):
        assert wallet_manager.get_wallet_info("0xunknown") is None


# ── Default Wallet Tests ─────────────────────────────────────────────────────

@pytest.mark.unit
class TestDefaultWallet:
    def test_set_default_wallet(self, wallet_manager, sample_address, sample_address2):
        wallet_manager.add_software_wallet(
            address=sample_address, private_key="0x" + "a" * 64,
            password="p1", set_as_default=True,
        )
        wallet_manager.add_software_wallet(
            address=sample_address2, private_key="0x" + "b" * 64,
            password="p2",
        )
        wallet_manager.set_default_wallet(sample_address2)
        assert wallet_manager.get_default_wallet() == sample_address2
        info = wallet_manager.get_wallet_info(sample_address)
        assert info["is_default"] is False

    def test_set_default_wallet_not_found(self, wallet_manager):
        with pytest.raises(ValueError, match="not found"):
            wallet_manager.set_default_wallet("0xunknown")

    def test_get_default_no_default(self, wallet_manager):
        assert wallet_manager.get_default_wallet() is None


# ── Export / Import Tests ────────────────────────────────────────────────────

@pytest.mark.unit
class TestExportImport:
    def test_export_wallet(self, wallet_manager, sample_address, temp_dir):
        wallet_manager.add_software_wallet(
            address=sample_address, private_key="0x" + "a" * 64,
            password="test_password",
        )
        export_path = temp_dir / "export.json"
        wallet_manager.export_wallet(sample_address, export_path, "test_password")
        assert export_path.exists()

    def test_export_wallet_not_found(self, wallet_manager, temp_dir):
        with pytest.raises(ValueError, match="not found"):
            wallet_manager.export_wallet("0xunknown", temp_dir / "out.json", "pass")

    def test_export_multisig_not_allowed(self, wallet_manager, temp_dir):
        from polyalpha.wallet.multisig_wallet import MultiSigSigner

        signers = [MultiSigSigner(address="0x" + "1" * 40, weight=1)]
        wallet_manager.add_multisig_wallet(
            address="0x" + "0" * 40, signers=signers, required_weight=1,
        )
        with pytest.raises(ValueError, match="Only software wallets"):
            wallet_manager.export_wallet("0x" + "0" * 40, temp_dir / "out.json", "pass")

    def test_import_wallet(self, wallet_manager, sample_address, temp_dir):
        wallet_manager.add_software_wallet(
            address=sample_address, private_key="0x" + "a" * 64,
            password="test_password",
        )
        export_path = temp_dir / "export.json"
        wallet_manager.export_wallet(sample_address, export_path, "test_password")

        import_dir = temp_dir / "import"
        import_dir.mkdir()
        wm2 = WalletManager(
            storage_type=WalletStorageType.FILE,
            storage_path=import_dir,
        )
        imported = wm2.import_wallet(export_path, "test_password")
        assert imported == sample_address

    def test_import_wallet_set_default(self, wallet_manager, sample_address, temp_dir):
        wallet_manager.add_software_wallet(
            address=sample_address, private_key="0x" + "a" * 64,
            password="test_password",
        )
        export_path = temp_dir / "export.json"
        wallet_manager.export_wallet(sample_address, export_path, "test_password")

        import_dir = temp_dir / "import"
        import_dir.mkdir()
        wm2 = WalletManager(
            storage_type=WalletStorageType.FILE,
            storage_path=import_dir,
        )
        imported = wm2.import_wallet(export_path, "test_password", set_as_default=True)
        assert wm2.get_default_wallet() == imported


# ── Password Rotation Tests ──────────────────────────────────────────────────

@pytest.mark.unit
class TestPasswordRotation:
    def test_rotate_password(self, wallet_manager, sample_address):
        wallet_manager.add_software_wallet(
            address=sample_address, private_key="0x" + "a" * 64,
            password="old_password",
        )
        wallet_manager.rotate_password(sample_address, "old_password", "new_password")
        key = wallet_manager.get_private_key(sample_address, "new_password")
        assert key == "0x" + "a" * 64

    def test_rotate_password_updates_config(self, wallet_manager, sample_address):
        wallet_manager.add_software_wallet(
            address=sample_address, private_key="0x" + "a" * 64,
            password="old_password",
        )
        wallet_manager.rotate_password(sample_address, "old_password", "new_password")
        assert wallet_manager._wallets[sample_address].password == "new_password"


# ── Shutdown Tests ───────────────────────────────────────────────────────────

@pytest.mark.unit
class TestShutdown:
    def test_shutdown(self, wallet_manager):
        wallet_manager.shutdown()
