"""
Multi-signature wallet support for enhanced security.

This module provides multi-signature wallet functionality requiring
multiple signatures for transaction approval.
"""

from __future__ import annotations

import json
import logging
from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum
from typing import Optional, Dict, List, Set, Any
from threading import Lock

try:
    from eth_account import Account
    from eth_account.messages import encode_defunct
    ETH_ACCOUNT_AVAILABLE = True
except ImportError:
    ETH_ACCOUNT_AVAILABLE = False

log = logging.getLogger(__name__)


class MultiSigStatus(Enum):
    """Status of a multi-signature operation."""
    PENDING = "pending"
    APPROVED = "approved"
    REJECTED = "rejected"
    EXECUTED = "executed"
    CANCELLED = "cancelled"


@dataclass
class MultiSigSigner:
    """A signer in a multi-signature wallet."""
    address: str
    weight: int = 1
    is_active: bool = True
    name: Optional[str] = None
    
    def __post_init__(self):
        if self.weight < 1:
            raise ValueError("Signer weight must be at least 1")


@dataclass
class MultiSigTransaction:
    """A transaction requiring multi-signature approval."""
    tx_id: str
    transaction_dict: Dict[str, Any]
    proposer: str
    created_at: datetime
    status: MultiSigStatus = MultiSigStatus.PENDING
    signatures: Dict[str, str] = field(default_factory=dict)
    required_weight: int = 2
    current_weight: int = 0
    executed_at: Optional[datetime] = None
    execution_tx_hash: Optional[str] = None
    metadata: Optional[Dict[str, Any]] = None
    
    def add_signature(self, signer_address: str, signature: str, weight: int = 1) -> None:
        """Add a signature to the transaction."""
        if signer_address in self.signatures:
            log.warning("Signer %s already signed transaction %s", signer_address, self.tx_id)
            return
        
        self.signatures[signer_address] = signature
        self.current_weight += weight
        
        if self.current_weight >= self.required_weight:
            self.status = MultiSigStatus.APPROVED
            log.info("Transaction %s approved with weight %d/%d", self.tx_id, self.current_weight, self.required_weight)
    
    def is_approved(self) -> bool:
        """Check if transaction has enough signatures."""
        return self.current_weight >= self.required_weight
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary for storage."""
        return {
            "tx_id": self.tx_id,
            "transaction_dict": self.transaction_dict,
            "proposer": self.proposer,
            "created_at": self.created_at.isoformat(),
            "status": self.status.value,
            "signatures": self.signatures,
            "required_weight": self.required_weight,
            "current_weight": self.current_weight,
            "executed_at": self.executed_at.isoformat() if self.executed_at else None,
            "execution_tx_hash": self.execution_tx_hash,
            "metadata": self.metadata,
        }
    
    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> 'MultiSigTransaction':
        """Create from dictionary."""
        data['created_at'] = datetime.fromisoformat(data['created_at'])
        data['status'] = MultiSigStatus(data['status'])
        if data.get('executed_at'):
            data['executed_at'] = datetime.fromisoformat(data['executed_at'])
        return cls(**data)


class MultiSigWallet:
    """
    Multi-signature wallet for enhanced security.
    
    Requires multiple signatures from different signers before
    transactions can be executed.
    """
    
    def __init__(
        self,
        wallet_address: str,
        signers: List[MultiSigSigner],
        required_weight: int,
    ):
        """
        Initialize multi-signature wallet.
        
        Parameters
        ----------
        wallet_address : str
            The wallet address (smart contract or EOA).
        signers : list of MultiSigSigner
            List of authorized signers.
        required_weight : int
            Total weight required for approval.
        """
        if not ETH_ACCOUNT_AVAILABLE:
            raise ImportError(
                "eth-account library is required for multi-sig wallets. "
                "Install it with: pip install eth-account"
            )
        
        self.wallet_address = wallet_address
        self._signers: Dict[str, MultiSigSigner] = {s.address: s for s in signers}
        self._required_weight = required_weight
        self._transactions: Dict[str, MultiSigTransaction] = {}
        self._lock = Lock()
        
        # Validate configuration
        total_weight = sum(s.weight for s in signers if s.is_active)
        if required_weight > total_weight:
            raise ValueError(
                f"Required weight ({required_weight}) exceeds total active signer weight ({total_weight})"
            )
        
        log.info(
            "Initialized multi-sig wallet %s with %d signers, required weight: %d",
            wallet_address,
            len(signers),
            required_weight,
        )
    
    def add_signer(self, signer: MultiSigSigner) -> None:
        """
        Add a new signer to the wallet.
        
        Parameters
        ----------
        signer : MultiSigSigner
            Signer to add.
        """
        with self._lock:
            if signer.address in self._signers:
                raise ValueError(f"Signer {signer.address} already exists")
            
            self._signers[signer.address] = signer
            log.info("Added signer %s to multi-sig wallet", signer.address)
    
    def remove_signer(self, signer_address: str) -> None:
        """
        Remove a signer from the wallet.
        
        Parameters
        ----------
        signer_address : str
            Address of signer to remove.
        """
        with self._lock:
            if signer_address not in self._signers:
                raise ValueError(f"Signer {signer_address} not found")
            
            del self._signers[signer_address]
            log.info("Removed signer %s from multi-sig wallet", signer_address)
    
    def get_signers(self) -> List[MultiSigSigner]:
        """Get all signers."""
        with self._lock:
            return list(self._signers.values())
    
    def get_active_signers(self) -> List[MultiSigSigner]:
        """Get active signers."""
        with self._lock:
            return [s for s in self._signers.values() if s.is_active]
    
    def propose_transaction(
        self,
        transaction_dict: Dict[str, Any],
        proposer: str,
        metadata: Optional[Dict[str, Any]] = None,
    ) -> MultiSigTransaction:
        """
        Propose a new transaction for multi-signature approval.
        
        Parameters
        ----------
        transaction_dict : dict
            Transaction to propose (EIP-1559 format).
        proposer : str
            Address of the proposer.
        metadata : dict, optional
            Additional metadata.
        
        Returns
        -------
        MultiSigTransaction
            The proposed transaction.
        """
        with self._lock:
            if proposer not in self._signers:
                raise ValueError(f"Proposer {proposer} is not an authorized signer")
            
            tx_id = f"tx_{datetime.now(timezone.utc).timestamp()}_{proposer[:8]}"
            
            tx = MultiSigTransaction(
                tx_id=tx_id,
                transaction_dict=transaction_dict,
                proposer=proposer,
                created_at=datetime.now(timezone.utc),
                required_weight=self._required_weight,
                metadata=metadata,
            )
            
            self._transactions[tx_id] = tx
            log.info("Proposed transaction %s by %s", tx_id, proposer)
            return tx
    
    def sign_transaction(
        self,
        tx_id: str,
        signer_address: str,
        signature: str,
    ) -> MultiSigTransaction:
        """
        Sign a pending transaction.
        
        Parameters
        ----------
        tx_id : str
            Transaction ID.
        signer_address : str
            Address of the signer.
        signature : str
            Signature of the transaction.
        
        Returns
        -------
        MultiSigTransaction
            Updated transaction.
        """
        with self._lock:
            tx = self._transactions.get(tx_id)
            if not tx:
                raise ValueError(f"Transaction {tx_id} not found")
            
            signer = self._signers.get(signer_address)
            if not signer:
                raise ValueError(f"Signer {signer_address} not authorized")
            
            if not signer.is_active:
                raise ValueError(f"Signer {signer_address} is not active")
            
            # Verify signature
            if not self._verify_signature(tx.transaction_dict, signature, signer_address):
                raise ValueError("Invalid signature")
            
            tx.add_signature(signer_address, signature, signer.weight)
            
            log.info(
                "Transaction %s signed by %s (weight: %d/%d)",
                tx_id,
                signer_address,
                tx.current_weight,
                tx.required_weight,
            )
            
            return tx
    
    def _verify_signature(
        self,
        transaction_dict: Dict[str, Any],
        signature: str,
        signer_address: str,
    ) -> bool:
        """
        Verify a signature for a transaction.
        
        Parameters
        ----------
        transaction_dict : dict
            Transaction that was signed.
        signature : str
            Signature to verify.
        signer_address : str
            Expected signer address.
        
        Returns
        -------
        bool
            True if signature is valid.
        """
        try:
            # Create message hash from transaction
            message = json.dumps(transaction_dict, sort_keys=True)
            message_hash = encode_defunct(text=message)
            
            # Recover address from signature
            recovered_address = Account.recover_message(message_hash, signature)
            
            return recovered_address.lower() == signer_address.lower()
        except Exception as e:
            log.error("Signature verification failed: %s", e)
            return False
    
    def get_transaction(self, tx_id: str) -> Optional[MultiSigTransaction]:
        """Get a transaction by ID."""
        with self._lock:
            return self._transactions.get(tx_id)
    
    def get_pending_transactions(self) -> List[MultiSigTransaction]:
        """Get all pending transactions."""
        with self._lock:
            return [tx for tx in self._transactions.values() if tx.status == MultiSigStatus.PENDING]
    
    def get_approved_transactions(self) -> List[MultiSigTransaction]:
        """Get all approved but not executed transactions."""
        with self._lock:
            return [tx for tx in self._transactions.values() if tx.status == MultiSigStatus.APPROVED]
    
    def execute_transaction(
        self,
        tx_id: str,
        execution_tx_hash: str,
    ) -> MultiSigTransaction:
        """
        Mark a transaction as executed.
        
        Parameters
        ----------
        tx_id : str
            Transaction ID.
        execution_tx_hash : str
            Transaction hash of the execution.
        
        Returns
        -------
        MultiSigTransaction
            Updated transaction.
        """
        with self._lock:
            tx = self._transactions.get(tx_id)
            if not tx:
                raise ValueError(f"Transaction {tx_id} not found")
            
            if not tx.is_approved():
                raise ValueError(f"Transaction {tx_id} is not approved")
            
            tx.status = MultiSigStatus.EXECUTED
            tx.executed_at = datetime.now(timezone.utc)
            tx.execution_tx_hash = execution_tx_hash
            
            log.info("Executed transaction %s with hash %s", tx_id, execution_tx_hash)
            return tx
    
    def cancel_transaction(self, tx_id: str, canceller: str) -> MultiSigTransaction:
        """
        Cancel a pending transaction.
        
        Parameters
        ----------
        tx_id : str
            Transaction ID.
        canceller : str
            Address of the canceller (must be proposer or admin).
        
        Returns
        -------
        MultiSigTransaction
            Updated transaction.
        """
        with self._lock:
            tx = self._transactions.get(tx_id)
            if not tx:
                raise ValueError(f"Transaction {tx_id} not found")
            
            if tx.status != MultiSigStatus.PENDING:
                raise ValueError(f"Transaction {tx_id} is not pending")
            
            if tx.proposer != canceller:
                # In a real implementation, check if canceller is admin
                raise ValueError(f"Only proposer can cancel transaction")
            
            tx.status = MultiSigStatus.CANCELLED
            log.info("Cancelled transaction %s by %s", tx_id, canceller)
            return tx
    
    def reject_transaction(self, tx_id: str, rejecter: str) -> MultiSigTransaction:
        """
        Reject a transaction.
        
        Parameters
        ----------
        tx_id : str
            Transaction ID.
        rejecter : str
            Address of the rejecter.
        
        Returns
        -------
        MultiSigTransaction
            Updated transaction.
        """
        with self._lock:
            tx = self._transactions.get(tx_id)
            if not tx:
                raise ValueError(f"Transaction {tx_id} not found")
            
            if tx.status != MultiSigStatus.PENDING:
                raise ValueError(f"Transaction {tx_id} is not pending")
            
            if rejecter not in self._signers:
                raise ValueError(f"Rejecter {rejecter} is not authorized")
            
            tx.status = MultiSigStatus.REJECTED
            log.info("Rejected transaction %s by %s", tx_id, rejecter)
            return tx
    
    def update_required_weight(self, new_weight: int) -> None:
        """
        Update the required weight for approval.
        
        Parameters
        ----------
        new_weight : int
            New required weight.
        """
        with self._lock:
            total_weight = sum(s.weight for s in self._signers.values() if s.is_active)
            if new_weight > total_weight:
                raise ValueError(
                    f"New weight ({new_weight}) exceeds total active signer weight ({total_weight})"
                )
            
            self._required_weight = new_weight
            log.info("Updated required weight to %d", new_weight)
    
    def get_required_weight(self) -> int:
        """Get the current required weight."""
        return self._required_weight
    
    def get_wallet_address(self) -> str:
        """Get the wallet address."""
        return self.wallet_address


class MultiSigWalletFactory:
    """Factory for creating multi-signature wallets."""
    
    @staticmethod
    def create_2of3(
        wallet_address: str,
        signer_addresses: List[str],
    ) -> MultiSigWallet:
        """
        Create a 2-of-3 multi-signature wallet.
        
        Parameters
        ----------
        wallet_address : str
            Wallet address.
        signer_addresses : list of str
            Three signer addresses.
        
        Returns
        -------
        MultiSigWallet
            Configured 2-of-3 wallet.
        """
        if len(signer_addresses) != 3:
            raise ValueError("Exactly 3 signer addresses required for 2-of-3 wallet")
        
        signers = [
            MultiSigSigner(address=addr, weight=1)
            for addr in signer_addresses
        ]
        
        return MultiSigWallet(
            wallet_address=wallet_address,
            signers=signers,
            required_weight=2,
        )
    
    @staticmethod
    def create_3of5(
        wallet_address: str,
        signer_addresses: List[str],
    ) -> MultiSigWallet:
        """
        Create a 3-of-5 multi-signature wallet.
        
        Parameters
        ----------
        wallet_address : str
            Wallet address.
        signer_addresses : list of str
            Five signer addresses.
        
        Returns
        -------
        MultiSigWallet
            Configured 3-of-5 wallet.
        """
        if len(signer_addresses) != 5:
            raise ValueError("Exactly 5 signer addresses required for 3-of-5 wallet")
        
        signers = [
            MultiSigSigner(address=addr, weight=1)
            for addr in signer_addresses
        ]
        
        return MultiSigWallet(
            wallet_address=wallet_address,
            signers=signers,
            required_weight=3,
        )
    
    @staticmethod
    def create_custom(
        wallet_address: str,
        signers: List[MultiSigSigner],
        required_weight: int,
    ) -> MultiSigWallet:
        """
        Create a custom multi-signature wallet.
        
        Parameters
        ----------
        wallet_address : str
            Wallet address.
        signers : list of MultiSigSigner
            Signers with custom weights.
        required_weight : int
            Required weight for approval.
        
        Returns
        -------
        MultiSigWallet
            Configured custom wallet.
        """
        return MultiSigWallet(
            wallet_address=wallet_address,
            signers=signers,
            required_weight=required_weight,
        )


__all__ = [
    "MultiSigStatus",
    "MultiSigSigner",
    "MultiSigTransaction",
    "MultiSigWallet",
    "MultiSigWalletFactory",
]
