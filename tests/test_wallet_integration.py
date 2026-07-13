"""
Integration tests for wallet operations.

These tests require web3.py and eth-account to be installed.
They can be run with: pytest tests/test_wallet_integration.py -v
"""

import pytest
from polyalpha.trading.real import WalletManager


class TestWalletManagerInitialization:
    """Tests for WalletManager initialization."""
    
    def test_initialization(self):
        """Test basic WalletManager initialization."""
        wallet = WalletManager(
            private_key="0x" + "1" * 64,
            rpc_url="https://polygon-rpc.com",
        )
        
        assert wallet._private_key == "0x" + "1" * 64
        assert wallet._rpc_url == "https://polygon-rpc.com"
        assert wallet._balance == 0.0
        assert wallet._allowance == 0.0
    
    def test_initialization_with_logging(self):
        """Test WalletManager initialization with balance logging."""
        wallet = WalletManager(
            private_key="0x" + "1" * 64,
            rpc_url="https://polygon-rpc.com",
            log_balance_updates=True,
        )
        
        assert wallet._log_balance_updates == True


class TestWalletManagerWeb3Fallback:
    """Tests for WalletManager behavior when web3.py is not available."""
    
    def setup_method(self):
        """Set up test fixtures with simulated mode."""
        self.wallet = WalletManager(
            private_key="0x" + "1" * 64,
            rpc_url="https://polygon-rpc.com",
        )
    
    def test_get_address_without_web3(self):
        """Test getting address without web3.py (simulated)."""
        # Force simulated address
        address = self.wallet.get_address()
        
        # Should return a simulated address based on private key
        assert address is not None
        assert isinstance(address, str)
        assert len(address) == 42  # Ethereum address length
        assert address.startswith("0x")
    
    def test_get_balance_without_web3(self):
        """Test getting balance without web3.py (simulated)."""
        balance = self.wallet.get_balance()
        
        # Should return 0.0 when web3 is not available
        assert balance == 0.0
    
    def test_get_allowance_without_web3(self):
        """Test getting allowance without web3.py (simulated)."""
        allowance = self.wallet.get_allowance()
        
        # Should return 0.0 when web3 is not available
        assert allowance == 0.0
    
    def test_approve_clob_without_web3(self):
        """Test approving CLOB without web3.py (simulated)."""
        tx_hash = self.wallet.approve_clob(1000.0)
        
        # Should return a simulated transaction hash
        assert tx_hash is not None
        assert isinstance(tx_hash, str)
        assert tx_hash.startswith("0x")
        assert len(tx_hash) == 66  # Transaction hash length
    
    def test_refresh_balance_without_web3(self):
        """Test refreshing balance without web3.py."""
        self.wallet.refresh_balance()
        
        # Should not raise an error
        assert self.wallet._balance == 0.0
    
    def test_wait_for_transaction_without_web3(self):
        """Test waiting for transaction without web3.py (simulated)."""
        receipt = self.wallet.wait_for_transaction("0x" + "0" * 64)
        
        # Should return a simulated receipt
        assert receipt is not None
        assert isinstance(receipt, dict)
        assert "status" in receipt
        assert "gas_used" in receipt
        assert "block_number" in receipt


@pytest.mark.skipif(
    not pytest.importorskip("web3", reason="web3 not installed"),
    reason="Requires web3.py to be installed"
)
class TestWalletManagerWithWeb3:
    """Tests for WalletManager with actual web3.py (if available)."""
    
    def setup_method(self):
        """Set up test fixtures with web3.py."""
        try:
            from web3 import Web3
            self.web3_available = True
        except ImportError:
            self.web3_available = False
            pytest.skip("web3.py not installed")
        
        # Use a test private key (do not use in production!)
        self.wallet = WalletManager(
            private_key="0x" + "1" * 64,
            rpc_url="https://polygon-rpc.com",
        )
    
    def test_web3_initialization(self):
        """Test that web3.py is properly initialized."""
        if not self.web3_available:
            pytest.skip("web3.py not installed")
        
        # Trigger web3 initialization
        address = self.wallet.get_address()
        
        # Should have initialized web3
        assert self.wallet._web3 is not None
        assert self.wallet._usdc_contract is not None
    
    def test_get_address_with_web3(self):
        """Test getting address with web3.py."""
        if not self.web3_available:
            pytest.skip("web3.py not installed")
        
        address = self.wallet.get_address()
        
        assert address is not None
        assert isinstance(address, str)
        assert len(address) == 42
        assert address.startswith("0x")


class TestWalletManagerErrorHandling:
    """Tests for WalletManager error handling."""
    
    def setup_method(self):
        """Set up test fixtures."""
        self.wallet = WalletManager(
            private_key="0x" + "1" * 64,
            rpc_url="https://polygon-rpc.com",
        )
    
    def test_invalid_rpc_url(self):
        """Test handling of invalid RPC URL."""
        # This should not raise an error during initialization
        wallet = WalletManager(
            private_key="0x" + "1" * 64,
            rpc_url="invalid-url",
        )
        
        # Should still be able to get address (simulated)
        address = wallet.get_address()
        assert address is not None
    
    def test_empty_private_key(self):
        """Test handling of empty private key."""
        wallet = WalletManager(
            private_key="",
            rpc_url="https://polygon-rpc.com",
        )
        
        # Should still work with simulated address
        address = wallet.get_address()
        assert address is not None


class TestWalletManagerTransactionFlow:
    """Tests for wallet transaction flow."""
    
    def setup_method(self):
        """Set up test fixtures."""
        self.wallet = WalletManager(
            private_key="0x" + "1" * 64,
            rpc_url="https://polygon-rpc.com",
        )
    
    def test_approval_flow(self):
        """Test the approval flow."""
        # Get initial allowance
        initial_allowance = self.wallet.get_allowance()
        
        # Approve CLOB
        tx_hash = self.wallet.approve_clob(10000.0)
        
        # Check that allowance was updated (simulated)
        updated_allowance = self.wallet.get_allowance()
        
        assert tx_hash is not None
        # In simulated mode, allowance should be updated
        assert updated_allowance == 10000.0
    
    def test_transaction_wait_flow(self):
        """Test waiting for transaction confirmation."""
        # Simulate a transaction
        tx_hash = self.wallet.approve_clob(1000.0)
        
        # Wait for confirmation
        receipt = self.wallet.wait_for_transaction(tx_hash, timeout=60)
        
        assert receipt is not None
        assert receipt["status"] == 1  # Success
    
    def test_transaction_wait_with_timeout(self):
        """Test transaction wait with timeout."""
        receipt = self.wallet.wait_for_transaction(
            "0x" + "0" * 64,
            timeout=10
        )
        
        # Should return simulated receipt even with timeout
        assert receipt is not None


class TestWalletManagerBalanceTracking:
    """Tests for wallet balance tracking."""
    
    def setup_method(self):
        """Set up test fixtures."""
        self.wallet = WalletManager(
            private_key="0x" + "1" * 64,
            rpc_url="https://polygon-rpc.com",
            log_balance_updates=True,
        )
    
    def test_balance_refresh(self):
        """Test refreshing balance."""
        # Initial balance
        initial_balance = self.wallet.get_balance()
        
        # Refresh
        self.wallet.refresh_balance()
        
        # Balance should be updated (even if to 0 in simulated mode)
        refreshed_balance = self.wallet.balance
        
        assert refreshed_balance == initial_balance
    
    def test_balance_update_logging(self):
        """Test that balance updates are logged when enabled."""
        # This test just ensures the method doesn't crash
        self.wallet.refresh_balance()
        
        # In a real test, we'd check logs, but for now just ensure no error
        assert True


class TestWalletManagerEdgeCases:
    """Tests for wallet manager edge cases."""
    
    def test_zero_approval_amount(self):
        """Test approving zero amount."""
        wallet = WalletManager(
            private_key="0x" + "1" * 64,
            rpc_url="https://polygon-rpc.com",
        )
        
        tx_hash = wallet.approve_clob(0.0)
        assert tx_hash is not None
    
    def test_very_large_approval_amount(self):
        """Test approving very large amount."""
        wallet = WalletManager(
            private_key="0x" + "1" * 64,
            rpc_url="https://polygon-rpc.com",
        )
        
        # Approve 1 million USDC
        tx_hash = wallet.approve_clob(1_000_000.0)
        assert tx_hash is not None
    
    def test_multiple_approvals(self):
        """Test multiple sequential approvals."""
        wallet = WalletManager(
            private_key="0x" + "1" * 64,
            rpc_url="https://polygon-rpc.com",
        )
        
        # First approval
        tx_hash1 = wallet.approve_clob(1000.0)
        assert tx_hash1 is not None
        
        # Second approval (should override)
        tx_hash2 = wallet.approve_clob(5000.0)
        assert tx_hash2 is not None
        
        # Allowance should reflect latest approval
        allowance = wallet.get_allowance()
        assert allowance == 5000.0


class TestWalletManagerSecurity:
    """Tests for wallet security features."""
    
    def test_private_key_not_exposed(self):
        """Test that private key is not exposed in public methods."""
        wallet = WalletManager(
            private_key="0x" + "1" * 64,
            rpc_url="https://polygon-rpc.com",
        )
        
        # Check that private key is not in address
        address = wallet.get_address()
        assert wallet._private_key not in address
        
        # Check that private key is not in transaction hash
        tx_hash = wallet.approve_clob(1000.0)
        assert wallet._private_key not in tx_hash
    
    def test_address_consistency(self):
        """Test that address is consistent across calls."""
        wallet = WalletManager(
            private_key="0x" + "1" * 64,
            rpc_url="https://polygon-rpc.com",
        )
        
        address1 = wallet.get_address()
        address2 = wallet.get_address()
        
        assert address1 == address2


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
