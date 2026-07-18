"""
Secure transaction signing module.

This module provides secure transaction signing with validation,
gas estimation, and safety checks.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from datetime import datetime, timezone
from enum import Enum
from typing import Optional, Dict, List, Any, Callable
from threading import Lock

from ..utils.logging_utils import mask_address

try:
    from eth_account import Account
    from eth_account.messages import encode_defunct
    from web3 import Web3
    from web3.exceptions import TransactionNotFound
    WEB3_AVAILABLE = True
except ImportError:
    WEB3_AVAILABLE = False

log = logging.getLogger(__name__)


class SigningMethod(Enum):
    """Transaction signing methods."""
    PRIVATE_KEY = "private_key"
    HARDWARE_WALLET = "hardware_wallet"
    MULTISIG = "multisig"
    KEYRING = "keyring"


@dataclass
class SigningResult:
    """Result of a transaction signing operation."""
    success: bool
    signed_transaction: Optional[Dict[str, Any]]
    signature: Optional[str]
    error_message: Optional[str] = None
    gas_estimate: Optional[int] = None
    gas_price: Optional[int] = None
    signed_at: datetime = None
    
    def __post_init__(self):
        if self.signed_at is None:
            self.signed_at = datetime.now(timezone.utc)


class TransactionSigner:
    """
    Secure transaction signer with validation and safety checks.
    
    Provides:
    - Transaction validation before signing
    - Gas estimation and optimization
    - Replay attack protection (EIP-155)
    - Nonce management
    - Signing method abstraction
    """
    
    def __init__(
        self,
        signing_method: SigningMethod = SigningMethod.PRIVATE_KEY,
        private_key: Optional[str] = None,
        hardware_wallet: Optional[Any] = None,
        multisig_wallet: Optional[Any] = None,
        rpc_url: Optional[str] = None,
    ):
        """
        Initialize transaction signer.
        
        Parameters
        ----------
        signing_method : SigningMethod
            Method to use for signing.
        private_key : str, optional
            Private key (for PRIVATE_KEY method).
        hardware_wallet : HardwareWallet, optional
            Hardware wallet instance (for HARDWARE_WALLET method).
        multisig_wallet : MultiSigWallet, optional
            Multi-sig wallet instance (for MULTISIG method).
        rpc_url : str, optional
            RPC URL for blockchain interaction.
        """
        if not WEB3_AVAILABLE:
            raise ImportError(
                "web3 and eth-account libraries are required for transaction signing. "
                "Install them with: pip install web3 eth-account"
            )
        
        self._signing_method = signing_method
        self._private_key = private_key
        self._hardware_wallet = hardware_wallet
        self._multisig_wallet = multisig_wallet
        self._rpc_url = rpc_url
        self._w3: Optional[Web3] = None
        self._lock = Lock()
        self._nonce_cache: Dict[str, int] = {}
        
        if rpc_url:
            self._w3 = Web3(Web3.HTTPProvider(rpc_url))
        
        # Validate configuration
        if signing_method == SigningMethod.PRIVATE_KEY and not private_key:
            raise ValueError("Private key required for PRIVATE_KEY signing method")
        if signing_method == SigningMethod.HARDWARE_WALLET and not hardware_wallet:
            raise ValueError("Hardware wallet required for HARDWARE_WALLET signing method")
        if signing_method == SigningMethod.MULTISIG and not multisig_wallet:
            raise ValueError("Multi-sig wallet required for MULTISIG signing method")
        
        log.info("Initialized transaction signer with method: %s", signing_method.value)
    
    def sign_transaction(
        self,
        transaction_dict: Dict[str, Any],
        validate: bool = True,
        estimate_gas: bool = True,
    ) -> SigningResult:
        """
        Sign a transaction with safety checks.
        
        Parameters
        ----------
        transaction_dict : dict
            Transaction to sign (EIP-1559 format).
        validate : bool
            Whether to validate the transaction before signing.
        estimate_gas : bool
            Whether to estimate gas before signing.
        
        Returns
        -------
        SigningResult
            Result of the signing operation.
        """
        try:
            with self._lock:
                # Validate transaction
                if validate:
                    validation_result = self._validate_transaction(transaction_dict)
                    if not validation_result.success:
                        return validation_result
                
                # Estimate gas if requested
                if estimate_gas and self._w3:
                    gas_estimate = self._estimate_gas(transaction_dict)
                    transaction_dict['gas'] = gas_estimate
                
                # Ensure nonce is set
                if 'nonce' not in transaction_dict and self._w3:
                    from_address = transaction_dict.get('from')
                    if from_address:
                        transaction_dict['nonce'] = self._get_nonce(from_address)
                
                # Sign based on method
                if self._signing_method == SigningMethod.PRIVATE_KEY:
                    return self._sign_with_private_key(transaction_dict)
                elif self._signing_method == SigningMethod.HARDWARE_WALLET:
                    return self._sign_with_hardware_wallet(transaction_dict)
                elif self._signing_method == SigningMethod.MULTISIG:
                    return self._sign_with_multisig(transaction_dict)
                else:
                    return SigningResult(
                        success=False,
                        signed_transaction=None,
                        signature=None,
                        error_message=f"Unsupported signing method: {self._signing_method}",
                    )
        except Exception as e:
            log.error("Transaction signing failed: %s", e)
            return SigningResult(
                success=False,
                signed_transaction=None,
                signature=None,
                error_message=str(e),
            )
    
    def _validate_transaction(self, transaction_dict: Dict[str, Any]) -> SigningResult:
        """
        Validate a transaction before signing.
        
        Parameters
        ----------
        transaction_dict : dict
            Transaction to validate.
        
        Returns
        -------
        SigningResult
            Validation result.
        """
        # Check required fields
        required_fields = ['to']
        for field in required_fields:
            if field not in transaction_dict:
                return SigningResult(
                    success=False,
                    signed_transaction=None,
                    signature=None,
                    error_message=f"Missing required field: {field}",
                )
        
        # Validate addresses
        if 'to' in transaction_dict and transaction_dict['to']:
            if not self._is_valid_address(transaction_dict['to']):
                return SigningResult(
                    success=False,
                    signed_transaction=None,
                    signature=None,
                    error_message="Invalid 'to' address",
                )
        
        if 'from' in transaction_dict and transaction_dict['from']:
            if not self._is_valid_address(transaction_dict['from']):
                return SigningResult(
                    success=False,
                    signed_transaction=None,
                    signature=None,
                    error_message="Invalid 'from' address",
                )
        
        # Validate value
        if 'value' in transaction_dict:
            try:
                value = int(transaction_dict['value'])
                if value < 0:
                    return SigningResult(
                        success=False,
                        signed_transaction=None,
                        signature=None,
                        error_message="Value cannot be negative",
                    )
            except (ValueError, TypeError):
                return SigningResult(
                    success=False,
                    signed_transaction=None,
                    signature=None,
                    error_message="Invalid value format",
                )
        
        # Validate gas
        if 'gas' in transaction_dict:
            try:
                gas = int(transaction_dict['gas'])
                if gas <= 0:
                    return SigningResult(
                        success=False,
                        signed_transaction=None,
                        signature=None,
                        error_message="Gas must be positive",
                    )
            except (ValueError, TypeError):
                return SigningResult(
                    success=False,
                    signed_transaction=None,
                    signature=None,
                    error_message="Invalid gas format",
                )
        
        # Check for EIP-155 chain ID
        if 'chainId' not in transaction_dict:
            log.warning("Transaction missing chainId, may be vulnerable to replay attacks")
        
        return SigningResult(
            success=True,
            signed_transaction=None,
            signature=None,
        )
    
    def _is_valid_address(self, address: str) -> bool:
        """Check if an address is valid."""
        try:
            return Web3.is_address(address)
        except Exception:
            return False
    
    def _estimate_gas(self, transaction_dict: Dict[str, Any]) -> int:
        """
        Estimate gas for a transaction.
        
        Parameters
        ----------
        transaction_dict : dict
            Transaction to estimate gas for.
        
        Returns
        -------
        int
            Estimated gas.
        """
        if not self._w3:
            return 21000  # Default gas limit
        
        try:
            gas_estimate = self._w3.eth.estimate_gas(transaction_dict)
            # Add 20% buffer
            return int(gas_estimate * 1.2)
        except Exception as e:
            log.warning("Gas estimation failed: %s, using default", e)
            return 21000
    
    def _get_nonce(self, address: str) -> int:
        """
        Get the next nonce for an address.
        
        Parameters
        ----------
        address : str
            Address to get nonce for.
        
        Returns
        -------
        int
            Next nonce.
        """
        if not self._w3:
            return 0
        
        # Check cache
        if address in self._nonce_cache:
            return self._nonce_cache[address]
        
        try:
            nonce = self._w3.eth.get_transaction_count(address)
            self._nonce_cache[address] = nonce
            return nonce
        except Exception as e:
            log.warning("Failed to get nonce for %s: %s", mask_address(address), e)
            return 0
    
    def _sign_with_private_key(self, transaction_dict: Dict[str, Any]) -> SigningResult:
        """
        Sign transaction with private key.
        
        Parameters
        ----------
        transaction_dict : dict
            Transaction to sign.
        
        Returns
        -------
        SigningResult
            Signing result.
        """
        try:
            # Create account from private key
            account = Account.from_key(self._private_key)
            
            # Sign transaction
            signed_txn = account.sign_transaction(transaction_dict)
            
            log.info("Signed transaction with private key, nonce: %d", transaction_dict.get('nonce'))
            
            return SigningResult(
                success=True,
                signed_transaction=signed_txn,
                signature=signed_txn.signature.hex(),
                gas_estimate=transaction_dict.get('gas'),
            )
        except Exception as e:
            log.error("Private key signing failed: %s", e)
            return SigningResult(
                success=False,
                signed_transaction=None,
                signature=None,
                error_message=str(e),
            )
    
    def _sign_with_hardware_wallet(self, transaction_dict: Dict[str, Any]) -> SigningResult:
        """
        Sign transaction with hardware wallet.
        
        Parameters
        ----------
        transaction_dict : dict
            Transaction to sign.
        
        Returns
        -------
        SigningResult
            Signing result.
        """
        try:
            if not self._hardware_wallet:
                return SigningResult(
                    success=False,
                    signed_transaction=None,
                    signature=None,
                    error_message="Hardware wallet not connected",
                )
            
            signed_txn = self._hardware_wallet.sign_transaction(transaction_dict)
            
            log.info("Signed transaction with hardware wallet")
            
            return SigningResult(
                success=True,
                signed_transaction=signed_txn,
                signature=signed_txn.get('signature', ''),
                gas_estimate=transaction_dict.get('gas'),
            )
        except Exception as e:
            log.error("Hardware wallet signing failed: %s", e)
            return SigningResult(
                success=False,
                signed_transaction=None,
                signature=None,
                error_message=str(e),
            )
    
    def _sign_with_multisig(self, transaction_dict: Dict[str, Any]) -> SigningResult:
        """
        Sign transaction with multi-sig wallet.
        
        Parameters
        ----------
        transaction_dict : dict
            Transaction to sign.
        
        Returns
        -------
        SigningResult
            Signing result.
        """
        try:
            if not self._multisig_wallet:
                return SigningResult(
                    success=False,
                    signed_transaction=None,
                    signature=None,
                    error_message="Multi-sig wallet not configured",
                )
            
            # Propose transaction
            proposer = transaction_dict.get('from', '')
            tx = self._multisig_wallet.propose_transaction(transaction_dict, proposer)
            
            log.info("Proposed transaction for multi-sig: %s", tx.tx_id)
            
            return SigningResult(
                success=True,
                signed_transaction=transaction_dict,
                signature=tx.tx_id,  # Return tx_id as signature
                gas_estimate=transaction_dict.get('gas'),
            )
        except Exception as e:
            log.error("Multi-sig signing failed: %s", e)
            return SigningResult(
                success=False,
                signed_transaction=None,
                signature=None,
                error_message=str(e),
            )
    
    def sign_message(self, message: str, address: Optional[str] = None) -> SigningResult:
        """
        Sign a message.
        
        Parameters
        ----------
        message : str
            Message to sign.
        address : str, optional
            Address to sign with (for hardware wallets).
        
        Returns
        -------
        SigningResult
            Signing result.
        """
        try:
            if self._signing_method == SigningMethod.PRIVATE_KEY:
                account = Account.from_key(self._private_key)
                message_hash = encode_defunct(text=message)
                signed_message = account.sign_message(message_hash)
                
                return SigningResult(
                    success=True,
                    signed_transaction=None,
                    signature=signed_message.signature.hex(),
                )
            elif self._signing_method == SigningMethod.HARDWARE_WALLET:
                if not self._hardware_wallet:
                    return SigningResult(
                        success=False,
                        signed_transaction=None,
                        signature=None,
                        error_message="Hardware wallet not connected",
                    )
                
                signature = self._hardware_wallet.sign_message(message)
                
                return SigningResult(
                    success=True,
                    signed_transaction=None,
                    signature=signature,
                )
            else:
                return SigningResult(
                    success=False,
                    signed_transaction=None,
                    signature=None,
                    error_message=f"Message signing not supported for {self._signing_method}",
                )
        except Exception as e:
            log.error("Message signing failed: %s", e)
            return SigningResult(
                success=False,
                signed_transaction=None,
                signature=None,
                error_message=str(e),
            )
    
    def broadcast_transaction(self, signed_transaction: Dict[str, Any]) -> Optional[str]:
        """
        Broadcast a signed transaction to the blockchain.
        
        Parameters
        ----------
        signed_transaction : dict
            Signed transaction to broadcast.
        
        Returns
        -------
        str or None
            Transaction hash if successful, None otherwise.
        """
        if not self._w3:
            log.error("Web3 not configured, cannot broadcast transaction")
            return None
        
        try:
            tx_hash = self._w3.eth.send_raw_transaction(signed_transaction.rawTransaction)
            log.info("Broadcasted transaction: %s", tx_hash.hex())
            return tx_hash.hex()
        except Exception as e:
            log.error("Failed to broadcast transaction: %s", e)
            return None
    
    def wait_for_confirmation(
        self,
        tx_hash: str,
        timeout: int = 120,
        poll_interval: float = 1.0,
    ) -> Optional[Dict[str, Any]]:
        """
        Wait for a transaction to be confirmed.
        
        Parameters
        ----------
        tx_hash : str
            Transaction hash to wait for.
        timeout : int
            Maximum time to wait in seconds.
        poll_interval : float
            Time between polls in seconds.
        
        Returns
        -------
        dict or None
            Transaction receipt if confirmed, None if timeout.
        """
        if not self._w3:
            log.error("Web3 not configured, cannot wait for confirmation")
            return None
        
        import time
        
        start_time = time.time()
        
        while time.time() - start_time < timeout:
            try:
                receipt = self._w3.eth.get_transaction_receipt(tx_hash)
                if receipt:
                    log.info("Transaction confirmed: %s", tx_hash)
                    return receipt
            except TransactionNotFound:
                pass
            except Exception as e:
                log.warning("Error checking transaction status: %s", e)
            
            time.sleep(poll_interval)
        
        log.warning("Transaction confirmation timeout: %s", tx_hash)
        return None
    
    def clear_nonce_cache(self, address: Optional[str] = None) -> None:
        """
        Clear the nonce cache.
        
        Parameters
        ----------
        address : str, optional
            Specific address to clear, or None to clear all.
        """
        with self._lock:
            if address:
                self._nonce_cache.pop(address, None)
            else:
                self._nonce_cache.clear()
            log.info("Cleared nonce cache")


__all__ = [
    "SigningMethod",
    "SigningResult",
    "TransactionSigner",
]
