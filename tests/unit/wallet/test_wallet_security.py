"""
Tests for wallet security module.
"""

import pytest
from pathlib import Path
from datetime import datetime, timezone
import tempfile
import shutil

from polyalpha.wallet.wallet_security import (
    WalletSecurity,
    WalletStorageType,
    WalletCredentials,
)
from polyalpha.wallet.hardware_wallet import (
    HardwareWalletType,
    HardwareWalletInfo,
    LedgerWallet,
    TrezorWallet,
    detect_hardware_wallets,
    get_hardware_wallet,
)
from polyalpha.wallet.multisig_wallet import (
    MultiSigWallet,
    MultiSigSigner,
    MultiSigStatus,
    MultiSigWalletFactory,
)
from polyalpha.wallet.transaction_signer import (
    TransactionSigner,
    SigningMethod,
    SigningResult,
)
from polyalpha.wallet.wallet_manager import (
    WalletManager,
    WalletType,
    WalletConfig,
)
from polyalpha.wallet.audit_logger import (
    AuditLogger,
    AuditEventType,
    AuditEvent,
)


@pytest.mark.unit
class TestWalletSecurity:
    """Tests for WalletSecurity class."""
    
    @pytest.fixture
    def temp_dir(self):
        """Create a temporary directory for testing."""
        temp_dir = Path(tempfile.mkdtemp())
        yield temp_dir
        shutil.rmtree(temp_dir, ignore_errors=True)
    
    @pytest.fixture
    def wallet_security(self, temp_dir):
        """Create a WalletSecurity instance for testing."""
        return WalletSecurity(
            storage_type=WalletStorageType.FILE,
            storage_path=temp_dir,
        )
    
    def test_add_wallet(self, wallet_security):
        """Test adding a wallet."""
        wallet_address = "0x1234567890123456789012345678901234567890"
        private_key = "0x" + "a" * 64
        password = "test_password"
        
        wallet_security.add_wallet(wallet_address, private_key, password)
        
        assert wallet_address in wallet_security.list_wallets()
    
    def test_get_private_key(self, wallet_security):
        """Test retrieving a private key."""
        wallet_address = "0x1234567890123456789012345678901234567890"
        private_key = "0x" + "a" * 64
        password = "test_password"
        
        wallet_security.add_wallet(wallet_address, private_key, password)
        retrieved_key = wallet_security.get_private_key(wallet_address, password)
        
        assert retrieved_key == private_key
    
    def test_get_private_key_wrong_password(self, wallet_security):
        """Test retrieving with wrong password."""
        wallet_address = "0x1234567890123456789012345678901234567890"
        private_key = "0x" + "a" * 64
        password = "test_password"
        
        wallet_security.add_wallet(wallet_address, private_key, password)
        
        with pytest.raises(ValueError):
            wallet_security.get_private_key(wallet_address, "wrong_password")
    
    def test_remove_wallet(self, wallet_security):
        """Test removing a wallet."""
        wallet_address = "0x1234567890123456789012345678901234567890"
        private_key = "0x" + "a" * 64
        password = "test_password"
        
        wallet_security.add_wallet(wallet_address, private_key, password)
        wallet_security.remove_wallet(wallet_address)
        
        assert wallet_address not in wallet_security.list_wallets()
    
    def test_rotate_key(self, wallet_security):
        """Test key rotation."""
        wallet_address = "0x1234567890123456789012345678901234567890"
        private_key = "0x" + "a" * 64
        old_password = "test_password"
        new_password = "new_password"
        
        wallet_security.add_wallet(wallet_address, private_key, old_password)
        wallet_security.rotate_key(wallet_address, old_password, new_password)
        
        # Should work with new password
        retrieved_key = wallet_security.get_private_key(wallet_address, new_password)
        assert retrieved_key == private_key
        
        # Should fail with old password
        with pytest.raises(ValueError):
            wallet_security.get_private_key(wallet_address, old_password)
    
    def test_export_import_wallet(self, wallet_security, temp_dir):
        """Test wallet export and import."""
        wallet_address = "0x1234567890123456789012345678901234567890"
        private_key = "0x" + "a" * 64
        password = "test_password"
        export_password = "export_password"
        export_path = temp_dir / "wallet_export.json"
        
        wallet_security.add_wallet(wallet_address, private_key, password)
        wallet_security.export_wallet(wallet_address, password, export_path)
        
        # Remove original wallet
        wallet_security.remove_wallet(wallet_address)
        
        # Import from export
        imported_address = wallet_security.import_wallet(export_path, export_password)
        
        assert imported_address == wallet_address
        assert wallet_address in wallet_security.list_wallets()


@pytest.mark.unit
class TestHardwareWallet:
    """Tests for hardware wallet support."""
    
    def test_ledger_wallet_creation(self):
        """Test creating a Ledger wallet instance."""
        wallet = LedgerWallet("test_device")
        assert wallet.device_id == "test_device"
        assert not wallet.is_connected()
    
    def test_trezor_wallet_creation(self):
        """Test creating a Trezor wallet instance."""
        wallet = TrezorWallet("test_device")
        assert wallet.device_id == "test_device"
        assert not wallet.is_connected()
    
    def test_get_hardware_wallet(self):
        """Test getting hardware wallet by type."""
        ledger = get_hardware_wallet(HardwareWalletType.LEDGER, "device_1")
        assert isinstance(ledger, LedgerWallet)
        
        trezor = get_hardware_wallet(HardwareWalletType.TREZOR, "device_2")
        assert isinstance(trezor, TrezorWallet)
    
    def test_detect_hardware_wallets(self):
        """Test hardware wallet detection."""
        # This will return empty list if no hardware wallets are connected
        detected = detect_hardware_wallets()
        assert isinstance(detected, list)


@pytest.mark.unit
class TestMultiSigWallet:
    """Tests for multi-signature wallet."""
    
    @pytest.fixture
    def multisig_wallet(self):
        """Create a multi-sig wallet for testing."""
        signers = [
            MultiSigSigner(address="0x" + "1" * 40, weight=1),
            MultiSigSigner(address="0x" + "2" * 40, weight=1),
            MultiSigSigner(address="0x" + "3" * 40, weight=1),
        ]
        return MultiSigWallet(
            wallet_address="0x" + "0" * 40,
            signers=signers,
            required_weight=2,
        )
    
    def test_multisig_creation(self, multisig_wallet):
        """Test multi-sig wallet creation."""
        assert len(multisig_wallet.get_signers()) == 3
        assert multisig_wallet.get_required_weight() == 2
    
    def test_propose_transaction(self, multisig_wallet):
        """Test proposing a transaction."""
        tx_dict = {"to": "0x" + "a" * 40, "value": "1000000000000000000"}
        tx = multisig_wallet.propose_transaction(tx_dict, "0x" + "1" * 40)
        
        assert tx.status == MultiSigStatus.PENDING
        assert tx.proposer == "0x" + "1" * 40
    
    def test_add_signer(self, multisig_wallet):
        """Test adding a signer."""
        new_signer = MultiSigSigner(address="0x" + "4" * 40, weight=1)
        multisig_wallet.add_signer(new_signer)
        
        assert len(multisig_wallet.get_signers()) == 4
    
    def test_remove_signer(self, multisig_wallet):
        """Test removing a signer."""
        multisig_wallet.remove_signer("0x" + "1" * 40)
        
        assert len(multisig_wallet.get_signers()) == 2
        assert "0x" + "1" * 40 not in [s.address for s in multisig_wallet.get_signers()]
    
    def test_multisig_factory_2of3(self):
        """Test factory for 2-of-3 wallet."""
        signers = ["0x" + str(i) * 40 for i in range(1, 4)]
        wallet = MultiSigWalletFactory.create_2of3("0x" + "0" * 40, signers)
        
        assert wallet.get_required_weight() == 2
        assert len(wallet.get_signers()) == 3


@pytest.mark.unit
class TestTransactionSigner:
    """Tests for transaction signer."""
    
    def test_signing_result_creation(self):
        """Test creating a signing result."""
        result = SigningResult(
            success=True,
            signed_transaction={"hash": "0x123"},
            signature="0xabc",
        )
        
        assert result.success is True
        assert result.signed_at is not None
    
    def test_transaction_validation(self):
        """Test transaction validation."""
        # This test would require a real Web3 instance
        # For now, we test the structure
        pass


@pytest.mark.unit
class TestWalletManager:
    """Tests for wallet manager."""
    
    @pytest.fixture
    def temp_dir(self):
        """Create a temporary directory for testing."""
        temp_dir = Path(tempfile.mkdtemp())
        yield temp_dir
        shutil.rmtree(temp_dir, ignore_errors=True)
    
    @pytest.fixture
    def wallet_manager(self, temp_dir):
        """Create a WalletManager instance for testing."""
        return WalletManager(
            storage_type=WalletStorageType.FILE,
            storage_path=temp_dir,
        )
    
    def test_add_software_wallet(self, wallet_manager):
        """Test adding a software wallet."""
        address = "0x1234567890123456789012345678901234567890"
        private_key = "0x" + "a" * 64
        password = "test_password"
        
        wallet_manager.add_software_wallet(address, private_key, password)
        
        wallets = wallet_manager.list_wallets()
        assert len(wallets) == 1
        assert wallets[0]["address"] == address
    
    def test_remove_wallet(self, wallet_manager):
        """Test removing a wallet."""
        address = "0x1234567890123456789012345678901234567890"
        private_key = "0x" + "a" * 64
        password = "test_password"
        
        wallet_manager.add_software_wallet(address, private_key, password)
        wallet_manager.remove_wallet(address)
        
        assert len(wallet_manager.list_wallets()) == 0
    
    def test_set_default_wallet(self, wallet_manager):
        """Test setting default wallet."""
        address1 = "0x1234567890123456789012345678901234567890"
        address2 = "0x2234567890123456789012345678901234567890"
        private_key = "0x" + "a" * 64
        password = "test_password"
        
        wallet_manager.add_software_wallet(address1, private_key, password, set_as_default=True)
        wallet_manager.add_software_wallet(address2, private_key, password)
        
        assert wallet_manager.get_default_wallet() == address1
        
        wallet_manager.set_default_wallet(address2)
        assert wallet_manager.get_default_wallet() == address2


@pytest.mark.unit
class TestAuditLogger:
    """Tests for audit logger."""
    
    @pytest.fixture
    def temp_dir(self):
        """Create a temporary directory for testing."""
        temp_dir = Path(tempfile.mkdtemp())
        yield temp_dir
        shutil.rmtree(temp_dir, ignore_errors=True)
    
    @pytest.fixture
    def audit_logger(self, temp_dir):
        """Create an AuditLogger instance for testing."""
        log_path = temp_dir / "audit.log"
        return AuditLogger(log_path=log_path, enable_console_logging=False)
    
    def test_log_event(self, audit_logger):
        """Test logging an event."""
        audit_logger.log_event(
            event_type=AuditEventType.WALLET_CREATED,
            wallet_address="0x1234567890123456789012345678901234567890",
            actor="test_user",
            success=True,
        )
        
        events = audit_logger.query_events(limit=10)
        assert len(events) == 1
        assert events[0].event_type == AuditEventType.WALLET_CREATED
    
    def test_query_events(self, audit_logger):
        """Test querying events."""
        audit_logger.log_event(
            event_type=AuditEventType.WALLET_CREATED,
            wallet_address="0x1234567890123456789012345678901234567890",
            actor="test_user",
            success=True,
        )
        
        audit_logger.log_event(
            event_type=AuditEventType.WALLET_ACCESSED,
            wallet_address="0x1234567890123456789012345678901234567890",
            actor="test_user",
            success=True,
        )
        
        wallet_events = audit_logger.query_events(
            event_type=AuditEventType.WALLET_CREATED,
            limit=10,
        )
        assert len(wallet_events) == 1
    
    def test_get_wallet_history(self, audit_logger):
        """Test getting wallet history."""
        wallet_address = "0x1234567890123456789012345678901234567890"
        
        audit_logger.log_event(
            event_type=AuditEventType.WALLET_CREATED,
            wallet_address=wallet_address,
            actor="test_user",
            success=True,
        )
        
        history = audit_logger.get_wallet_history(wallet_address)
        assert len(history) == 1
        assert history[0].wallet_address == wallet_address
    
    def test_get_failed_events(self, audit_logger):
        """Test getting failed events."""
        audit_logger.log_event(
            event_type=AuditEventType.WALLET_ACCESSED,
            wallet_address="0x1234567890123456789012345678901234567890",
            actor="test_user",
            success=False,
            error_message="Invalid password",
        )
        
        failed = audit_logger.get_failed_events()
        assert len(failed) == 1
        assert not failed[0].success
    
    def test_get_statistics(self, audit_logger):
        """Test getting statistics."""
        audit_logger.log_event(
            event_type=AuditEventType.WALLET_CREATED,
            wallet_address="0x1234567890123456789012345678901234567890",
            actor="test_user",
            success=True,
        )
        
        audit_logger.log_event(
            event_type=AuditEventType.WALLET_ACCESSED,
            wallet_address="0x1234567890123456789012345678901234567890",
            actor="test_user",
            success=False,
            error_message="Invalid password",
        )
        
        stats = audit_logger.get_statistics()
        assert stats["total_events"] == 2
        assert stats["successful_events"] == 1
        assert stats["failed_events"] == 1


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
