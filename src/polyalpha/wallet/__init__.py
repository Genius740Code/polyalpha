"""
Wallet security module for real trading.

This module provides comprehensive wallet security features including:
- Encrypted key storage
- Multi-signature wallet support
- Secure transaction signing
- Wallet recovery mechanisms
- Access controls and permissions
"""

from __future__ import annotations

from .wallet_manager import WalletManager
from .wallet_security import WalletSecurity
from .multisig_wallet import MultiSigWallet
from .transaction_signer import TransactionSigner
from .audit_logger import AuditLogger, AuditEventType, get_audit_logger

__all__ = [
    "WalletManager",
    "WalletSecurity",
    "MultiSigWallet",
    "TransactionSigner",
    "AuditLogger",
    "AuditEventType",
    "get_audit_logger",
]
