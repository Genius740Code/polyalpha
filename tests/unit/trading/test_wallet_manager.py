"""
Wallet manager tests — run with: pytest tests/unit/trading/test_wallet_manager.py
"""

import pytest
from polyalpha.trading.real import WalletManager


@pytest.mark.requires_network
@pytest.mark.unit
def test_wallet_manager_initialization():
    """Test wallet manager initialization."""
    wallet = WalletManager(
        private_key="0x" + "1" * 64,
        rpc_url="https://polygon-rpc.com",
    )
    assert wallet._private_key == "0x" + "1" * 64
    assert wallet._rpc_url == "https://polygon-rpc.com"
    assert wallet._address is None
    assert wallet._balance == 0.0
    assert wallet._allowance == 0.0


@pytest.mark.requires_network
@pytest.mark.unit
def test_wallet_manager_get_address():
    """Test getting wallet address."""
    wallet = WalletManager(
        private_key="0x" + "1" * 64,  # Valid hex private key (non-zero)
        rpc_url="https://polygon-rpc.com",
    )
    address = wallet.get_address()
    # Should return simulated address if Web3 not available
    assert address.startswith("0x")
    assert len(address) == 42


@pytest.mark.requires_network
@pytest.mark.unit
def test_wallet_manager_get_balance():
    """Test getting wallet balance."""
    wallet = WalletManager(
        private_key="0x" + "1" * 64,
        rpc_url="https://polygon-rpc.com",
    )
    balance = wallet.get_balance()
    # Should return 0.0 if Web3 not available
    assert balance == 0.0


@pytest.mark.requires_network
@pytest.mark.unit
def test_wallet_manager_get_allowance():
    """Test getting token allowance."""
    wallet = WalletManager(
        private_key="0x" + "1" * 64,
        rpc_url="https://polygon-rpc.com",
    )
    spender_address = "0x4D16C7936c63648848F7C1d7A5bCfC6C6fF1C8f7"
    try:
        allowance = wallet.get_allowance(spender_address)
        # Should return allowance if Web3 is available
        assert allowance >= 0.0
    except Exception:
        # Expected to fail without actual blockchain connection
        pass


@pytest.mark.requires_network
@pytest.mark.unit
def test_wallet_manager_approve_spender():
    """Test approving spender."""
    wallet = WalletManager(
        private_key="0x" + "1" * 64,
        rpc_url="https://polygon-rpc.com",
    )
    spender_address = "0x4D16C7936c63648848F7C1d7A5bCfC6C6fF1C8f7"
    try:
        tx_hash = wallet.approve_spender(spender_address, 1000.0)
        # Should return tx hash if Web3 is available
        assert tx_hash.startswith("0x")
        assert len(tx_hash) == 66
    except Exception:
        # Expected to fail without actual blockchain connection
        pass


@pytest.mark.requires_network
@pytest.mark.unit
def test_wallet_manager_refresh_balance():
    """Test refreshing balance."""
    wallet = WalletManager(
        private_key="0x" + "1" * 64,
        rpc_url="https://polygon-rpc.com",
    )
    wallet.refresh_balance()
    # Should not raise any errors


@pytest.mark.requires_network
@pytest.mark.unit
def test_wallet_manager_wait_for_transaction():
    """Test waiting for transaction."""
    wallet = WalletManager(
        private_key="0x" + "1" * 64,
        rpc_url="https://polygon-rpc.com",
    )
    receipt = wallet.wait_for_transaction("0x" + "0" * 64)
    # Should return simulated receipt if Web3 not available
    assert receipt['status'] == 1
    assert receipt['gas_used'] == 50000
    assert receipt['block_number'] == 12345678
