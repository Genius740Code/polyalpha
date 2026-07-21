"""
Tests for transaction signer — run with: pytest tests/unit/wallet/test_transaction_signer.py
"""

import pytest
from unittest.mock import Mock, patch, PropertyMock, MagicMock, call
from datetime import datetime, timezone

from polyalpha.wallet.transaction_signer import (
    TransactionSigner,
    SigningMethod,
    SigningResult,
)


# ── SigningResult Tests ──────────────────────────────────────────────────────

@pytest.mark.unit
class TestSigningResult:
    def test_creation(self):
        result = SigningResult(
            success=True,
            signed_transaction={"hash": "0x123"},
            signature="0xabc",
        )
        assert result.success is True
        assert result.signed_transaction == {"hash": "0x123"}
        assert result.signature == "0xabc"
        assert result.error_message is None
        assert result.signed_at is not None

    def test_default_timestamp(self):
        before = datetime.now(timezone.utc)
        result = SigningResult(success=True, signed_transaction=None, signature=None)
        after = datetime.now(timezone.utc)
        assert before <= result.signed_at <= after

    def test_failed_result(self):
        result = SigningResult(
            success=False,
            signed_transaction=None,
            signature=None,
            error_message="Something went wrong",
        )
        assert result.success is False
        assert result.error_message == "Something went wrong"


# ── TransactionSigner Tests ──────────────────────────────────────────────────

@pytest.fixture
def mock_web3():
    """Mock Web3 instance."""
    with patch("polyalpha.wallet.transaction_signer.Web3") as mock_w3_class:
        mock_w3 = MagicMock()
        mock_w3_class.HTTPProvider = MagicMock(return_value="provider")
        mock_w3_class.return_value = mock_w3
        mock_w3_class.is_address = MagicMock(return_value=True)
        mock_w3.eth.estimate_gas.return_value = 50000
        mock_w3.eth.get_transaction_count.return_value = 5
        mock_w3.eth.send_raw_transaction.return_value = Mock(hex=lambda: "0xhash123")
        mock_receipt = MagicMock()
        mock_receipt.status = 1
        mock_w3.eth.get_transaction_receipt.return_value = mock_receipt
        yield mock_w3


@pytest.fixture
def mock_account():
    """Mock eth_account Account."""
    with patch("polyalpha.wallet.transaction_signer.Account") as mock_account_class:
        mock_acc = MagicMock()
        mock_account_class.from_key.return_value = mock_acc

        mock_signed = MagicMock()
        mock_signed.signature.hex.return_value = "0xsig123"
        mock_signed.rawTransaction = b"raw_tx_data"
        mock_acc.sign_transaction.return_value = mock_signed
        mock_acc.address = "0x1234567890123456789012345678901234567890"

        mock_signed_msg = MagicMock()
        mock_signed_msg.signature.hex.return_value = "0xmsg_sig"
        mock_acc.sign_message.return_value = mock_signed_msg

        yield mock_account_class


@pytest.mark.unit
class TestTransactionSignerInit:
    def test_init_with_private_key(self, mock_web3):
        signer = TransactionSigner(
            signing_method=SigningMethod.PRIVATE_KEY,
            private_key="0x" + "1" * 64,
            rpc_url="https://polygon-rpc.com",
        )
        assert signer._signing_method == SigningMethod.PRIVATE_KEY
        assert signer._private_key == "0x" + "1" * 64

    def test_init_raises_without_private_key(self):
        with pytest.raises(ValueError, match="Private key required"):
            TransactionSigner(
                signing_method=SigningMethod.PRIVATE_KEY,
                rpc_url="https://polygon-rpc.com",
            )

    def test_init_raises_without_multisig(self):
        with pytest.raises(ValueError, match="Multi-sig wallet required"):
            TransactionSigner(
                signing_method=SigningMethod.MULTISIG,
                rpc_url="https://polygon-rpc.com",
            )

    def test_init_with_multisig(self):
        mock_multisig = MagicMock()
        signer = TransactionSigner(
            signing_method=SigningMethod.MULTISIG,
            multisig_wallet=mock_multisig,
            rpc_url="https://polygon-rpc.com",
        )
        assert signer._signing_method == SigningMethod.MULTISIG

    def test_init_without_rpc(self, mock_web3, mock_account):
        signer = TransactionSigner(
            signing_method=SigningMethod.PRIVATE_KEY,
            private_key="0x" + "1" * 64,
        )
        assert signer._w3 is None


# ── Sign Transaction Tests ───────────────────────────────────────────────────

@pytest.mark.unit
class TestSignTransaction:
    def test_sign_transaction_success(self, mock_web3, mock_account):
        signer = TransactionSigner(
            signing_method=SigningMethod.PRIVATE_KEY,
            private_key="0x" + "1" * 64,
            rpc_url="https://polygon-rpc.com",
        )

        tx = {
            "to": "0x1234567890123456789012345678901234567890",
            "value": 1000000,
            "chainId": 137,
        }
        result = signer.sign_transaction(tx, validate=True, estimate_gas=False)

        assert result.success is True
        assert result.signature == "0xsig123"

    def test_sign_transaction_with_validation(self, mock_web3, mock_account):
        signer = TransactionSigner(
            signing_method=SigningMethod.PRIVATE_KEY,
            private_key="0x" + "1" * 64,
            rpc_url="https://polygon-rpc.com",
        )

        result = signer.sign_transaction({}, validate=True, estimate_gas=False)
        assert result.success is False
        assert "Missing required field" in result.error_message

    def test_sign_transaction_with_gas_estimate(self, mock_web3, mock_account):
        signer = TransactionSigner(
            signing_method=SigningMethod.PRIVATE_KEY,
            private_key="0x" + "1" * 64,
            rpc_url="https://polygon-rpc.com",
        )

        tx = {
            "to": "0x1234567890123456789012345678901234567890",
            "from": "0x1234567890123456789012345678901234567890",
            "chainId": 137,
        }
        result = signer.sign_transaction(tx, validate=True, estimate_gas=True)

        assert result.success is True

    def test_sign_transaction_with_nonce(self, mock_web3, mock_account):
        signer = TransactionSigner(
            signing_method=SigningMethod.PRIVATE_KEY,
            private_key="0x" + "1" * 64,
            rpc_url="https://polygon-rpc.com",
        )

        tx = {
            "to": "0x1234567890123456789012345678901234567890",
            "from": "0x1234567890123456789012345678901234567890",
            "chainId": 137,
        }
        result = signer.sign_transaction(tx, validate=False, estimate_gas=False)

        assert result.success is True

    def test_sign_transaction_exception(self, mock_web3, mock_account):
        mock_account.from_key.side_effect = Exception("Key error")

        signer = TransactionSigner(
            signing_method=SigningMethod.PRIVATE_KEY,
            private_key="0x" + "1" * 64,
            rpc_url="https://polygon-rpc.com",
        )

        tx = {"to": "0x1234567890123456789012345678901234567890"}
        result = signer.sign_transaction(tx, validate=False, estimate_gas=False)

        assert result.success is False
        assert "Key error" in result.error_message

    def test_sign_multisig(self, mock_web3):
        mock_multisig = MagicMock()
        mock_tx = MagicMock()
        mock_tx.tx_id = "tx-123"
        mock_multisig.propose_transaction.return_value = mock_tx

        signer = TransactionSigner(
            signing_method=SigningMethod.MULTISIG,
            multisig_wallet=mock_multisig,
            rpc_url="https://polygon-rpc.com",
        )

        tx = {
            "to": "0x1234567890123456789012345678901234567890",
            "from": "0xabc",
            "value": 1000,
            "gas": 21000,
        }
        result = signer.sign_transaction(tx, validate=False, estimate_gas=False)

        assert result.success is True
        assert result.signature == "tx-123"

    def test_sign_multisig_not_configured(self, mock_web3):
        mock_multisig = MagicMock()
        signer = TransactionSigner(
            signing_method=SigningMethod.MULTISIG,
            multisig_wallet=mock_multisig,
            rpc_url="https://polygon-rpc.com",
        )
        signer._multisig_wallet = None

        tx = {"to": "0x1234567890123456789012345678901234567890"}
        result = signer._sign_with_multisig(tx)
        assert result.success is False
        assert "not configured" in result.error_message

    def test_unsupported_signing_method(self, mock_web3, mock_account):
        signer = TransactionSigner(
            signing_method=SigningMethod.PRIVATE_KEY,
            private_key="0x" + "1" * 64,
            rpc_url="https://polygon-rpc.com",
        )
        signer._signing_method = "unknown"

        tx = {"to": "0x1234567890123456789012345678901234567890"}
        result = signer.sign_transaction(tx, validate=False, estimate_gas=False)

        assert result.success is False


# ── Transaction Validation Tests ─────────────────────────────────────────────

@pytest.mark.unit
class TestTransactionValidation:
    def test_validate_missing_to(self):
        signer = TransactionSigner(
            signing_method=SigningMethod.PRIVATE_KEY,
            private_key="0x" + "1" * 64,
        )
        result = signer._validate_transaction({})
        assert result.success is False
        assert "Missing required field" in result.error_message

    def test_validate_invalid_to_address(self, mock_web3):
        from polyalpha.wallet.transaction_signer import Web3 as MockedWeb3
        MockedWeb3.is_address.return_value = False

        signer = TransactionSigner(
            signing_method=SigningMethod.PRIVATE_KEY,
            private_key="0x" + "1" * 64,
            rpc_url="https://polygon-rpc.com",
        )
        result = signer._validate_transaction({"to": "invalid"})
        assert result.success is False
        assert "Invalid 'to' address" in result.error_message

    def test_validate_invalid_from_address(self, mock_web3):
        from polyalpha.wallet.transaction_signer import Web3 as MockedWeb3
        MockedWeb3.is_address.side_effect = [True, False]

        signer = TransactionSigner(
            signing_method=SigningMethod.PRIVATE_KEY,
            private_key="0x" + "1" * 64,
            rpc_url="https://polygon-rpc.com",
        )
        result = signer._validate_transaction({"to": "0x1234", "from": "invalid"})
        assert result.success is False
        assert "Invalid 'from' address" in result.error_message

    def test_validate_negative_value(self):
        signer = TransactionSigner(
            signing_method=SigningMethod.PRIVATE_KEY,
            private_key="0x" + "1" * 64,
        )
        result = signer._validate_transaction({"to": "0x" + "1" * 40, "value": -100})
        assert result.success is False
        assert "Value cannot be negative" in result.error_message

    def test_validate_invalid_value_format(self):
        signer = TransactionSigner(
            signing_method=SigningMethod.PRIVATE_KEY,
            private_key="0x" + "1" * 64,
        )
        result = signer._validate_transaction({"to": "0x" + "1" * 40, "value": "not_a_number"})
        assert result.success is False
        assert "Invalid value format" in result.error_message

    def test_validate_zero_gas(self):
        signer = TransactionSigner(
            signing_method=SigningMethod.PRIVATE_KEY,
            private_key="0x" + "1" * 64,
        )
        result = signer._validate_transaction({"to": "0x" + "1" * 40, "gas": 0})
        assert result.success is False
        assert "Gas must be positive" in result.error_message

    def test_validate_invalid_gas_format(self):
        signer = TransactionSigner(
            signing_method=SigningMethod.PRIVATE_KEY,
            private_key="0x" + "1" * 64,
        )
        result = signer._validate_transaction({"to": "0x" + "1" * 40, "gas": "high"})
        assert result.success is False
        assert "Invalid gas format" in result.error_message

    def test_validate_missing_chain_id_warning(self):
        signer = TransactionSigner(
            signing_method=SigningMethod.PRIVATE_KEY,
            private_key="0x" + "1" * 64,
        )
        result = signer._validate_transaction({"to": "0x" + "1" * 40})
        assert result.success is True

    def test_validate_valid_transaction(self, mock_web3):
        signer = TransactionSigner(
            signing_method=SigningMethod.PRIVATE_KEY,
            private_key="0x" + "1" * 64,
            rpc_url="https://polygon-rpc.com",
        )
        result = signer._validate_transaction({
            "to": "0x1234567890123456789012345678901234567890",
            "from": "0x1234567890123456789012345678901234567890",
            "value": 1000,
            "gas": 21000,
            "chainId": 137,
        })
        assert result.success is True

    def test_is_valid_address(self, mock_web3):
        signer = TransactionSigner(
            signing_method=SigningMethod.PRIVATE_KEY,
            private_key="0x" + "1" * 64,
            rpc_url="https://polygon-rpc.com",
        )
        assert signer._is_valid_address("0x1234") is True

    def test_is_valid_address_exception(self, mock_web3):
        from polyalpha.wallet.transaction_signer import Web3 as MockedWeb3
        MockedWeb3.is_address.side_effect = Exception("bad")

        signer = TransactionSigner(
            signing_method=SigningMethod.PRIVATE_KEY,
            private_key="0x" + "1" * 64,
            rpc_url="https://polygon-rpc.com",
        )
        assert signer._is_valid_address("bad") is False


# ── Gas Estimation Tests ─────────────────────────────────────────────────────

@pytest.mark.unit
class TestGasEstimation:
    def test_estimate_gas_success(self, mock_web3):
        mock_web3.eth.estimate_gas.return_value = 50000

        signer = TransactionSigner(
            signing_method=SigningMethod.PRIVATE_KEY,
            private_key="0x" + "1" * 64,
            rpc_url="https://polygon-rpc.com",
        )
        gas = signer._estimate_gas({"to": "0x1234"})
        assert gas == 60000  # 50000 * 1.2

    def test_estimate_gas_fallback(self, mock_web3):
        mock_web3.eth.estimate_gas.side_effect = Exception("estimate failed")

        signer = TransactionSigner(
            signing_method=SigningMethod.PRIVATE_KEY,
            private_key="0x" + "1" * 64,
            rpc_url="https://polygon-rpc.com",
        )
        gas = signer._estimate_gas({"to": "0x1234"})
        assert gas == 21000

    def test_estimate_gas_no_web3(self):
        signer = TransactionSigner(
            signing_method=SigningMethod.PRIVATE_KEY,
            private_key="0x" + "1" * 64,
        )
        gas = signer._estimate_gas({"to": "0x1234"})
        assert gas == 21000


# ── Nonce Management Tests ───────────────────────────────────────────────────

@pytest.mark.unit
class TestNonceManagement:
    def test_get_nonce_from_chain(self, mock_web3):
        mock_web3.eth.get_transaction_count.return_value = 42

        signer = TransactionSigner(
            signing_method=SigningMethod.PRIVATE_KEY,
            private_key="0x" + "1" * 64,
            rpc_url="https://polygon-rpc.com",
        )
        nonce = signer._get_nonce("0x1234")
        assert nonce == 42

    def test_get_nonce_cached(self, mock_web3):
        mock_web3.eth.get_transaction_count.return_value = 7

        signer = TransactionSigner(
            signing_method=SigningMethod.PRIVATE_KEY,
            private_key="0x" + "1" * 64,
            rpc_url="https://polygon-rpc.com",
        )

        first = signer._get_nonce("0x1234")
        second = signer._get_nonce("0x1234")
        assert first == second == 7
        assert mock_web3.eth.get_transaction_count.call_count == 1

    def test_get_nonce_fallback(self, mock_web3):
        mock_web3.eth.get_transaction_count.side_effect = Exception("RPC error")

        signer = TransactionSigner(
            signing_method=SigningMethod.PRIVATE_KEY,
            private_key="0x" + "1" * 64,
            rpc_url="https://polygon-rpc.com",
        )
        nonce = signer._get_nonce("0x1234")
        assert nonce == 0

    def test_get_nonce_no_web3(self):
        signer = TransactionSigner(
            signing_method=SigningMethod.PRIVATE_KEY,
            private_key="0x" + "1" * 64,
        )
        nonce = signer._get_nonce("0x1234")
        assert nonce == 0

    def test_clear_nonce_cache_specific(self):
        signer = TransactionSigner(
            signing_method=SigningMethod.PRIVATE_KEY,
            private_key="0x" + "1" * 64,
        )
        signer._nonce_cache = {"0xabc": 5, "0xdef": 10}
        signer.clear_nonce_cache("0xabc")
        assert "0xabc" not in signer._nonce_cache
        assert "0xdef" in signer._nonce_cache

    def test_clear_nonce_cache_all(self):
        signer = TransactionSigner(
            signing_method=SigningMethod.PRIVATE_KEY,
            private_key="0x" + "1" * 64,
        )
        signer._nonce_cache = {"0xabc": 5, "0xdef": 10}
        signer.clear_nonce_cache()
        assert signer._nonce_cache == {}


# ── Message Signing Tests ────────────────────────────────────────────────────

@pytest.mark.unit
class TestSignMessage:
    def test_sign_message_private_key(self, mock_web3, mock_account):
        signer = TransactionSigner(
            signing_method=SigningMethod.PRIVATE_KEY,
            private_key="0x" + "1" * 64,
        )

        result = signer.sign_message("Hello World")
        assert result.success is True
        assert result.signature == "0xmsg_sig"

    def test_sign_message_unsupported_method(self):
        signer = TransactionSigner(
            signing_method=SigningMethod.PRIVATE_KEY,
            private_key="0x" + "1" * 64,
        )
        signer._signing_method = SigningMethod.MULTISIG

        result = signer.sign_message("Hello")
        assert result.success is False
        assert "not supported" in result.error_message

    def test_sign_message_exception(self, mock_web3, mock_account):
        mock_account.from_key.side_effect = Exception("signing failed")

        signer = TransactionSigner(
            signing_method=SigningMethod.PRIVATE_KEY,
            private_key="0x" + "1" * 64,
        )

        result = signer.sign_message("Hello")
        assert result.success is False
        assert "signing failed" in result.error_message


# ── Broadcast Tests ──────────────────────────────────────────────────────────

@pytest.mark.unit
class TestBroadcast:
    def test_broadcast_transaction_success(self, mock_web3):
        signer = TransactionSigner(
            signing_method=SigningMethod.PRIVATE_KEY,
            private_key="0x" + "1" * 64,
            rpc_url="https://polygon-rpc.com",
        )

        mock_signed = MagicMock()
        mock_signed.rawTransaction = b"raw_bytes"

        tx_hash = signer.broadcast_transaction(mock_signed)
        assert tx_hash == "0xhash123"

    def test_broadcast_transaction_no_web3(self):
        signer = TransactionSigner(
            signing_method=SigningMethod.PRIVATE_KEY,
            private_key="0x" + "1" * 64,
        )

        tx_hash = signer.broadcast_transaction({"rawTransaction": b"data"})
        assert tx_hash is None

    def test_broadcast_transaction_failure(self, mock_web3):
        mock_web3.eth.send_raw_transaction.side_effect = Exception("broadcast failed")

        signer = TransactionSigner(
            signing_method=SigningMethod.PRIVATE_KEY,
            private_key="0x" + "1" * 64,
            rpc_url="https://polygon-rpc.com",
        )

        mock_signed = MagicMock()
        mock_signed.rawTransaction = b"raw_bytes"

        tx_hash = signer.broadcast_transaction(mock_signed)
        assert tx_hash is None


# ── Wait For Confirmation Tests ──────────────────────────────────────────────

@pytest.mark.unit
class TestWaitForConfirmation:
    def test_wait_for_confirmation_success(self, mock_web3):
        mock_receipt = MagicMock()
        mock_receipt.status = 1
        mock_web3.eth.get_transaction_receipt.return_value = mock_receipt

        signer = TransactionSigner(
            signing_method=SigningMethod.PRIVATE_KEY,
            private_key="0x" + "1" * 64,
            rpc_url="https://polygon-rpc.com",
        )

        receipt = signer.wait_for_confirmation("0xhash", timeout=1, poll_interval=0.1)
        assert receipt is not None
        assert receipt.status == 1

    def test_wait_for_confirmation_no_web3(self):
        signer = TransactionSigner(
            signing_method=SigningMethod.PRIVATE_KEY,
            private_key="0x" + "1" * 64,
        )

        receipt = signer.wait_for_confirmation("0xhash")
        assert receipt is None

    def test_wait_for_confirmation_timeout(self, mock_web3):
        mock_web3.eth.get_transaction_receipt.return_value = None

        signer = TransactionSigner(
            signing_method=SigningMethod.PRIVATE_KEY,
            private_key="0x" + "1" * 64,
            rpc_url="https://polygon-rpc.com",
        )

        receipt = signer.wait_for_confirmation("0xhash", timeout=0.5, poll_interval=0.2)
        assert receipt is None
