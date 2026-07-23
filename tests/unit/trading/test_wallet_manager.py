"""
Wallet manager tests — run with: pytest tests/unit/trading/test_wallet_manager.py
"""

import pytest
import time
from unittest.mock import Mock, patch, MagicMock, PropertyMock, call as mock_call

from polyalpha.trading.real_wallet import WalletManager
from polyalpha.core import NetworkError


@pytest.fixture
def wallet():
    return WalletManager(
        private_key="0x" + "1" * 64,
        rpc_url="https://polygon-rpc.com",
    )


@pytest.fixture
def mock_web3():
    """Create a mock Web3 instance that simulates Polygon."""
    with patch("web3.Web3") as mock_w3_class:
        mock_w3 = MagicMock()

        mock_block = {"baseFeePerGas": 50000000000}
        mock_w3.eth.get_block.return_value = mock_block
        mock_w3.eth.get_transaction_count.return_value = 10
        mock_w3.eth.estimate_gas.return_value = 100000
        mock_w3.to_wei.side_effect = lambda val, unit: val * 10**9 if unit == 'gwei' else val * 10**18
        mock_w3.from_wei.side_effect = lambda val, unit: val / 10**18
        mock_w3.is_address.return_value = True

        mock_w3_class.HTTPProvider.return_value = "provider"
        mock_w3_class.return_value = mock_w3

        yield mock_w3


# ── Initialization Tests ─────────────────────────────────────────────────────

@pytest.mark.unit
class TestWalletManagerInit:
    def test_initialization(self):
        wallet = WalletManager(
            private_key="0x" + "1" * 64,
            rpc_url="https://polygon-rpc.com",
        )
        assert wallet._private_key == "0x" + "1" * 64
        assert wallet._rpc_url == "https://polygon-rpc.com"
        assert wallet._address is None
        assert wallet._balance == 0.0
        assert wallet._allowance == 0.0
        assert wallet._web3 is None
        assert wallet._usdc_contract is None

    def test_initialization_with_logging(self):
        wallet = WalletManager(
            private_key="0x" + "1" * 64,
            rpc_url="https://polygon-rpc.com",
            log_balance_updates=True,
        )
        assert wallet._log_balance_updates is True

    def test_initialization_empty_pending(self):
        wallet = WalletManager(
            private_key="0x" + "1" * 64,
            rpc_url="https://polygon-rpc.com",
        )
        assert not hasattr(wallet, '_pending_transactions') or wallet._pending_transactions is None


# ── Address Property Tests ───────────────────────────────────────────────────

@pytest.mark.unit
class TestAddress:
    def test_address_property(self, wallet):
        addr = wallet.address
        assert addr is not None
        assert addr.startswith("0x")
        assert len(addr) == 42

    def test_address_cached(self, wallet):
        first = wallet.address
        second = wallet.address
        assert first == second


# ── Init Web3 Tests ──────────────────────────────────────────────────────────

@pytest.mark.unit
class TestInitWeb3:
    def test_init_web3_sets_address(self, wallet, mock_web3):
        mock_web3.eth.get_transaction_count.return_value = 5
        wallet._init_web3()
        assert wallet._web3 is not None
        assert wallet._address is not None
        assert wallet._nonce == 5

    def test_init_web3_creates_contracts(self, wallet, mock_web3):
        wallet._init_web3()
        assert wallet._usdc_contract is not None
        assert wallet._pending_transactions == {}


# ── Build Transaction Params Tests ──────────────────────────────────────────

@pytest.mark.unit
class TestBuildTransactionParams:
    def test_build_transaction_params(self, wallet, mock_web3):
        wallet._init_web3()
        params = wallet._build_transaction_params(gas_estimate=100000, to_address="0xtest")
        assert params["from"] == wallet._address
        assert params["gas"] == 100000
        assert params["type"] == 2
        assert params["nonce"] == 10
        assert "maxFeePerGas" in params
        assert "maxPriorityFeePerGas" in params


# ── Get Nonce Tests ──────────────────────────────────────────────────────────

@pytest.mark.unit
class TestGetNextNonce:
    def test_get_next_nonce_increments(self, wallet, mock_web3):
        wallet._init_web3()
        nonce1 = wallet._get_next_nonce()
        nonce2 = wallet._get_next_nonce()
        assert nonce2 == nonce1 + 1

    def test_get_next_nonce_uses_network(self, wallet, mock_web3):
        wallet._init_web3()
        mock_web3.eth.get_transaction_count.return_value = 20
        nonce = wallet._get_next_nonce()
        assert nonce == 20


# ── Track Pending Transaction Tests ──────────────────────────────────────────

@pytest.mark.unit
class TestTrackPendingTransaction:
    def test_track_pending(self, wallet, mock_web3):
        wallet._init_web3()
        wallet._track_pending_transaction("0xhash", 5)
        assert "0xhash" in wallet._pending_transactions
        assert wallet._pending_transactions["0xhash"]["nonce"] == 5
        assert wallet._pending_transactions["0xhash"]["retry_count"] == 0


# ── Gas Stats Tests ──────────────────────────────────────────────────────────

@pytest.mark.unit
class TestGasStats:
    def test_get_gas_stats_default(self, wallet, mock_web3):
        wallet._init_web3()
        stats = wallet.get_gas_stats()
        assert stats["total_gas_spent"] == 0.0
        assert stats["gas_cost_usd"] == 0.0
        assert stats["pending_transactions"] == 0

    def test_get_gas_stats_after_tracking(self, wallet, mock_web3):
        wallet._init_web3()
        wallet._total_gas_spent = 50000.0
        wallet._gas_cost_usd = 0.05
        wallet._track_pending_transaction("0xhash", 1)
        stats = wallet.get_gas_stats()
        assert stats["total_gas_spent"] == 50000.0
        assert stats["gas_cost_usd"] == 0.05
        assert stats["pending_transactions"] == 1


# ── Get Address Tests ────────────────────────────────────────────────────────

@pytest.mark.unit
class TestGetAddress:
    def test_get_address(self, wallet, mock_web3):
        addr = wallet.get_address()
        assert addr is not None
        assert addr.startswith("0x")

    def test_get_address_cached(self, wallet, mock_web3):
        wallet.get_address()
        wallet.get_address()
        assert wallet._address is not None


# ── Get Balance Tests ────────────────────────────────────────────────────────

@pytest.mark.unit
class TestGetBalance:
    def test_get_balance_success(self, wallet, mock_web3):
        mock_balance_func = MagicMock()
        mock_balance_func.call.return_value = 5000000000  # 5000 USDC (6 decimals)
        mock_web3.eth.contract.return_value.functions.balanceOf.return_value = mock_balance_func

        wallet._init_web3()
        balance = wallet.get_balance()
        assert balance == 5000.0

    def test_get_balance_raises_on_error(self, wallet, mock_web3):
        mock_balance_func = MagicMock()
        mock_balance_func.call.side_effect = Exception("RPC error")
        mock_web3.eth.contract.return_value.functions.balanceOf.return_value = mock_balance_func

        wallet._init_web3()
        with pytest.raises(NetworkError):
            wallet.get_balance()


# ── Get Allowance Tests ──────────────────────────────────────────────────────

@pytest.mark.unit
class TestGetAllowance:
    def test_get_allowance_success(self, wallet, mock_web3):
        mock_allowance_func = MagicMock()
        mock_allowance_func.call.return_value = 1000000000  # 1000 USDC
        mock_web3.eth.contract.return_value.functions.allowance.return_value = mock_allowance_func

        wallet._init_web3()
        allowance = wallet.get_allowance("0xspender")
        assert allowance == 1000.0

    def test_get_allowance_raises_on_error(self, wallet, mock_web3):
        mock_allowance_func = MagicMock()
        mock_allowance_func.call.side_effect = Exception("RPC error")
        mock_web3.eth.contract.return_value.functions.allowance.return_value = mock_allowance_func

        wallet._init_web3()
        with pytest.raises(NetworkError):
            wallet.get_allowance("0xspender")


# ── Approve Spender Tests ────────────────────────────────────────────────────

@pytest.mark.unit
class TestApproveSpender:
    def test_approve_spender_success(self, wallet, mock_web3):
        mock_approve_func = MagicMock()
        mock_estimate = MagicMock()
        mock_estimate.estimate_gas.return_value = 100000
        mock_approve_func.estimate_gas.return_value = mock_estimate

        mock_approve_build = MagicMock()
        mock_approve_func.build_transaction.return_value = {
            "to": "0xspender", "value": 0, "data": "0x",
            "gas": 100000, "gasPrice": 50000000000, "nonce": 10,
        }

        mock_web3.eth.contract.return_value.functions.approve.return_value = mock_approve_func

        mock_tx_hash = MagicMock()
        mock_tx_hash.hex.return_value = "0xabc123"
        mock_web3.eth.send_raw_transaction.return_value = mock_tx_hash

        with patch("eth_account.Account") as mock_account_cls:
            mock_acc = MagicMock()
            mock_acc.address = "0x19E7E6bEC3D6F165425D92F427d2c26FC0B6ff2A"
            mock_account_cls.from_key.return_value = mock_acc
            mock_signed = MagicMock()
            mock_signed.raw_transaction = b"raw_signed_tx"
            mock_acc.sign_transaction.return_value = mock_signed

            wallet._init_web3()
            tx_hash = wallet.approve_spender("0xspender", 1000.0)
            assert tx_hash == "0xabc123"

    def test_approve_spender_raises_on_error(self, wallet, mock_web3):
        mock_approve_func = MagicMock()
        mock_estimate = MagicMock()
        mock_estimate.estimate_gas.side_effect = Exception("Gas estimation failed")
        mock_approve_func.estimate_gas.return_value = mock_estimate

        mock_web3.eth.contract.return_value.functions.approve.return_value = mock_approve_func

        wallet._init_web3()
        with pytest.raises(Exception):
            wallet.approve_spender("0xspender", 1000.0)


# ── Refresh Balance Tests ────────────────────────────────────────────────────

@pytest.mark.unit
class TestRefreshBalance:
    def test_refresh_balance(self, wallet, mock_web3):
        mock_balance_func = MagicMock()
        mock_balance_func.call.return_value = 5000000000
        mock_web3.eth.contract.return_value.functions.balanceOf.return_value = mock_balance_func

        wallet._init_web3()
        wallet.refresh_balance()
        assert wallet._balance == 5000.0


# ── Wait For Transaction Tests ───────────────────────────────────────────────

@pytest.mark.unit
class TestWaitForTransaction:
    def test_wait_for_transaction_success(self, wallet, mock_web3):
        mock_receipt = {
            "status": 1,
            "gasUsed": 50000,
            "blockNumber": 12345678,
            "effectiveGasPrice": 50000000000,
        }
        mock_web3.eth.get_transaction_receipt.return_value = mock_receipt

        wallet._init_web3()
        receipt = wallet.wait_for_transaction("0xhash", timeout=1, poll_interval=0.1)

        assert receipt["status"] == 1
        assert receipt["gas_used"] == 50000
        assert receipt["block_number"] == 12345678

    def test_wait_for_transaction_removes_pending(self, wallet, mock_web3):
        mock_receipt = {
            "status": 1,
            "gasUsed": 50000,
            "blockNumber": 100,
            "effectiveGasPrice": 50000000000,
        }
        mock_web3.eth.get_transaction_receipt.return_value = mock_receipt

        wallet._init_web3()
        wallet._track_pending_transaction("0xhash", 1)
        wallet.wait_for_transaction("0xhash", timeout=1, poll_interval=0.1)

        assert "0xhash" not in wallet._pending_transactions

    def test_wait_for_transaction_tracks_gas(self, wallet, mock_web3):
        mock_receipt = {
            "status": 1,
            "gasUsed": 50000,
            "blockNumber": 100,
            "effectiveGasPrice": 50000000000,
        }
        mock_web3.eth.get_transaction_receipt.return_value = mock_receipt

        wallet._init_web3()
        wallet.wait_for_transaction("0xhash", timeout=1, poll_interval=0.1)

        assert wallet._total_gas_spent > 0
        assert wallet._gas_cost_usd > 0


# ── Re-broadcast Transaction Tests ──────────────────────────────────────────

@pytest.mark.unit
class TestRebroadcastTransaction:
    def test_rebroadcast_not_tracked(self, wallet, mock_web3):
        wallet._init_web3()
        result = wallet._rebroadcast_transaction("0xunknown")
        assert result["status"] == 0
        assert "not tracked" in result["error"]

    def test_rebroadcast_max_retries(self, wallet, mock_web3):
        wallet._init_web3()
        wallet._track_pending_transaction("0xhash", 1)
        wallet._pending_transactions["0xhash"]["retry_count"] = 3

        result = wallet._rebroadcast_transaction("0xhash")
        assert result["status"] == 0
        assert "Max retries" in result["error"]
