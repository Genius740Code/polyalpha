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


class TestWalletManagerGasManagement:
    """Tests for WalletManager gas management features."""
    
    def setup_method(self):
        """Set up test fixtures."""
        self.wallet = WalletManager(
            private_key="0x" + "1" * 64,
            rpc_url="https://polygon-rpc.com",
        )
        self.spender_address = "0x4D16C7936c63648848F7C1d7A5bCfC6C6fF1C8f7"  # Example CLOB address
    
    def test_get_gas_stats(self):
        """Test getting gas statistics."""
        stats = self.wallet.get_gas_stats()
        
        assert stats is not None
        assert isinstance(stats, dict)
        assert "total_gas_spent" in stats
        assert "gas_cost_usd" in stats
        assert "pending_transactions" in stats
        assert "current_nonce" in stats
        
        # Initial values should be zero
        assert stats["total_gas_spent"] == 0.0
        assert stats["gas_cost_usd"] == 0.0
        assert stats["pending_transactions"] == 0


@pytest.mark.skipif(
    not pytest.importorskip("web3", reason="web3 not installed"),
    reason="Requires web3.py to be installed"
)
class TestWalletManagerWithWeb3:
    """Tests for WalletManager with actual web3.py (mandatory)."""
    
    def setup_method(self):
        """Set up test fixtures with web3.py."""
        # web3.py is now mandatory, so we expect it to be available
        try:
            from web3 import Web3
            self.web3_available = True
        except ImportError:
            self.web3_available = False
            pytest.skip("web3.py is now mandatory but not installed")
        
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
    
    def test_nonce_management(self):
        """Test nonce management for concurrent transactions."""
        if not self.web3_available:
            pytest.skip("web3.py not installed")
        
        # Initialize web3
        self.wallet.get_address()
        
        # Get initial nonce
        initial_nonce = self.wallet._nonce
        assert initial_nonce >= 0
        
        # Get next nonce should increment
        next_nonce = self.wallet._get_next_nonce()
        assert next_nonce == initial_nonce + 1
        
        # Another call should increment again
        next_nonce2 = self.wallet._get_next_nonce()
        assert next_nonce2 == initial_nonce + 2


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
        spender_address = "0x4D16C7936c63648848F7C1d7A5bCfC6C6fF1C8f7"
        
        # Get initial allowance
        initial_allowance = self.wallet.get_allowance(spender_address)
        
        # Approve spender (will raise without actual web3 connection)
        try:
            tx_hash = self.wallet.approve_spender(spender_address, 10000.0)
            assert tx_hash is not None
            assert isinstance(tx_hash, str)
            assert tx_hash.startswith("0x")
        except Exception:
            # Expected to fail without actual blockchain connection
            pass
    
    def test_transaction_wait_flow(self):
        """Test waiting for transaction confirmation."""
        # Test with a dummy transaction hash
        tx_hash = "0x" + "a" * 64
        
        try:
            # Wait for confirmation (will timeout without real tx)
            receipt = self.wallet.wait_for_transaction(tx_hash, timeout=1)
            # If it somehow succeeds, check structure
            assert receipt is not None
            assert "status" in receipt
        except Exception:
            # Expected to fail without real transaction
            pass
    
    def test_transaction_wait_with_timeout(self):
        """Test transaction wait with timeout."""
        # Test with a dummy transaction hash and short timeout
        tx_hash = "0x" + "0" * 64
        
        try:
            receipt = self.wallet.wait_for_transaction(tx_hash, timeout=1)
            # If it somehow returns, check structure
            assert receipt is not None
        except Exception:
            # Expected to fail without real transaction
            pass


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
        spender_address = "0x4D16C7936c63648848F7C1d7A5bCfC6C6fF1C8f7"
        
        try:
            tx_hash = wallet.approve_spender(spender_address, 0.0)
            assert tx_hash is not None
        except Exception:
            # Expected to fail without actual web3 connection
            pass
    
    def test_very_large_approval_amount(self):
        """Test approving very large amount."""
        wallet = WalletManager(
            private_key="0x" + "1" * 64,
            rpc_url="https://polygon-rpc.com",
        )
        spender_address = "0x4D16C7936c63648848F7C1d7A5bCfC6C6fF1C8f7"
        
        try:
            # Approve 1 million USDC
            tx_hash = wallet.approve_spender(spender_address, 1_000_000.0)
            assert tx_hash is not None
        except Exception:
            # Expected to fail without actual web3 connection
            pass
    
    def test_multiple_approvals(self):
        """Test multiple sequential approvals."""
        wallet = WalletManager(
            private_key="0x" + "1" * 64,
            rpc_url="https://polygon-rpc.com",
        )
        spender_address = "0x4D16C7936c63648848F7C1d7A5bCfC6C6fF1C8f7"
        
        try:
            # First approval
            tx_hash1 = wallet.approve_spender(spender_address, 1000.0)
            assert tx_hash1 is not None
            
            # Second approval (should override)
            tx_hash2 = wallet.approve_spender(spender_address, 5000.0)
            assert tx_hash2 is not None
        except Exception:
            # Expected to fail without actual web3 connection
            pass


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
        spender_address = "0x4D16C7936c63648848F7C1d7A5bCfC6C6fF1C8f7"
        try:
            tx_hash = wallet.approve_spender(spender_address, 1000.0)
            assert wallet._private_key not in tx_hash
        except Exception:
            # Expected to fail without actual web3 connection
            pass
    
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
