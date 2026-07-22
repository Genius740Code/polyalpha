"""
Wallet manager for unified wallet security operations.

This module provides a unified interface for wallet operations,
integrating encrypted storage, multi-sig, and transaction signing.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from datetime import datetime, timezone
from enum import Enum
from pathlib import Path
from typing import Optional, Dict, List, Any, Union
from threading import Lock

from ..utils.logging_utils import mask_address
from .wallet_security import WalletSecurity, WalletStorageType, WalletCredentials
from .multisig_wallet import (
    MultiSigWallet,
    MultiSigSigner,
    MultiSigWalletFactory,
)
from .transaction_signer import TransactionSigner, SigningMethod, SigningResult

log = logging.getLogger(__name__)


class WalletType(Enum):
    """Types of wallets managed by WalletManager."""
    SOFTWARE = "software"
    MULTISIG = "multisig"


@dataclass
class WalletConfig:
    """Configuration for a wallet."""
    wallet_type: WalletType
    address: str
    name: Optional[str] = None
    is_default: bool = False
    metadata: Optional[Dict[str, Any]] = None
    
    # Software wallet specific
    password: Optional[str] = None
    
    # Multi-sig specific
    multisig_signers: Optional[List[MultiSigSigner]] = None
    required_weight: Optional[int] = None


class WalletManager:
    """
    Unified wallet manager for secure wallet operations.
    
    Provides:
    - Unified interface for all wallet types
    - Encrypted storage for software wallets
    - Multi-signature wallet management
    - Secure transaction signing
    - Wallet access logging
    """
    
    def __init__(
        self,
        storage_type: WalletStorageType = WalletStorageType.KEYRING,
        storage_path: Optional[Path] = None,
        rpc_url: Optional[str] = None,
    ):
        """
        Initialize wallet manager.
        
        Parameters
        ----------
        storage_type : WalletStorageType
            Storage backend for encrypted keys.
        storage_path : Path, optional
            Path for file-based storage.
        rpc_url : str, optional
            RPC URL for blockchain operations.
        """
        self._storage_type = storage_type
        self._storage_path = storage_path
        self._rpc_url = rpc_url
        
        # Initialize components
        self._wallet_security = WalletSecurity(
            storage_type=storage_type,
            storage_path=storage_path,
        )
        
        self._wallets: Dict[str, WalletConfig] = {}
        self._multisig_wallets: Dict[str, MultiSigWallet] = {}
        self._default_wallet: Optional[str] = None
        self._lock = Lock()
        
        log.info("Initialized wallet manager with storage: %s", storage_type.value)
    
    def add_software_wallet(
        self,
        address: str,
        private_key: str,
        password: str,
        name: Optional[str] = None,
        set_as_default: bool = False,
        metadata: Optional[Dict[str, Any]] = None,
    ) -> None:
        """
        Add a software wallet with encrypted private key.
        
        Parameters
        ----------
        address : str
            Wallet address.
        private_key : str
            Private key to encrypt and store.
        password : str
            Password for encryption.
        name : str, optional
            Wallet name.
        set_as_default : bool
            Whether to set as default wallet.
        metadata : dict, optional
            Additional metadata.
        """
        with self._lock:
            # Add to encrypted storage
            self._wallet_security.add_wallet(address, private_key, password, metadata)
            
            # Add to manager
            config = WalletConfig(
                wallet_type=WalletType.SOFTWARE,
                address=address,
                name=name,
                is_default=set_as_default,
                metadata=metadata,
                password=password,
            )
            
            self._wallets[address] = config
            
            if set_as_default:
                self._default_wallet = address
            
            log.info("Added software wallet: %s", address)
    
    def add_multisig_wallet(
        self,
        address: str,
        signers: List[MultiSigSigner],
        required_weight: int,
        name: Optional[str] = None,
        set_as_default: bool = False,
    ) -> None:
        """
        Add a multi-signature wallet.
        
        Parameters
        ----------
        address : str
            Wallet address.
        signers : list of MultiSigSigner
            Authorized signers.
        required_weight : int
            Required weight for approval.
        name : str, optional
            Wallet name.
        set_as_default : bool
            Whether to set as default wallet.
        """
        with self._lock:
            # Create multi-sig wallet
            multisig = MultiSigWallet(address, signers, required_weight)
            
            # Store
            self._multisig_wallets[address] = multisig
            
            config = WalletConfig(
                wallet_type=WalletType.MULTISIG,
                address=address,
                name=name,
                is_default=set_as_default,
                multisig_signers=signers,
                required_weight=required_weight,
            )
            
            self._wallets[address] = config
            
            if set_as_default:
                self._default_wallet = address
            
            log.info("Added multi-sig wallet: %s (required weight: %d)", mask_address(address), required_weight)
    
    def get_private_key(self, address: str, password: Optional[str] = None) -> str:
        """
        Get private key for a software wallet.
        
        Parameters
        ----------
        address : str
            Wallet address.
        password : str, optional
            Password for decryption (if not stored in config).
        
        Returns
        -------
        str
            Private key.
        """
        config = self._wallets.get(address)
        if not config:
            raise ValueError(f"Wallet {address} not found")
        
        if config.wallet_type != WalletType.SOFTWARE:
            raise ValueError(f"Wallet {address} is not a software wallet")
        
        pwd = password or config.password
        if not pwd:
            raise ValueError("Password required for private key access")
        
        return self._wallet_security.get_private_key(address, pwd)
    
    def create_signer(self, address: Optional[str] = None) -> TransactionSigner:
        """
        Create a transaction signer for a wallet.
        
        Parameters
        ----------
        address : str, optional
            Wallet address. If not provided, uses default wallet.
        
        Returns
        -------
        TransactionSigner
            Transaction signer configured for the wallet.
        """
        addr = address or self._default_wallet
        if not addr:
            raise ValueError("No wallet specified and no default wallet set")
        
        config = self._wallets.get(addr)
        if not config:
            raise ValueError(f"Wallet {addr} not found")
        
        if config.wallet_type == WalletType.SOFTWARE:
            private_key = self.get_private_key(addr, config.password)
            return TransactionSigner(
                signing_method=SigningMethod.PRIVATE_KEY,
                private_key=private_key,
                rpc_url=self._rpc_url,
            )
        
        elif config.wallet_type == WalletType.MULTISIG:
            multisig = self._multisig_wallets.get(addr)
            if not multisig:
                raise ValueError(f"Multi-sig wallet {addr} not found")
            return TransactionSigner(
                signing_method=SigningMethod.MULTISIG,
                multisig_wallet=multisig,
                rpc_url=self._rpc_url,
            )
        
        else:
            raise ValueError(f"Unsupported wallet type: {config.wallet_type}")
    
    def sign_transaction(
        self,
        transaction_dict: Dict[str, Any],
        address: Optional[str] = None,
        password: Optional[str] = None,
    ) -> SigningResult:
        """
        Sign a transaction with a wallet.
        
        Parameters
        ----------
        transaction_dict : dict
            Transaction to sign.
        address : str, optional
            Wallet address. If not provided, uses default wallet.
        password : str, optional
            Password for software wallet decryption.
        
        Returns
        -------
        SigningResult
            Signing result.
        """
        addr = address or self._default_wallet
        if not addr:
            raise ValueError("No wallet specified and no default wallet set")
        
        config = self._wallets.get(addr)
        if not config:
            raise ValueError(f"Wallet {addr} not found")
        
        # For software wallets, update password if provided
        if config.wallet_type == WalletType.SOFTWARE and password:
            config.password = password
        
        signer = self.create_signer(addr)
        return signer.sign_transaction(transaction_dict)
    
    def remove_wallet(self, address: str) -> None:
        """
        Remove a wallet from management.
        
        Parameters
        ----------
        address : str
            Wallet address to remove.
        """
        with self._lock:
            config = self._wallets.get(address)
            if not config:
                raise ValueError(f"Wallet {address} not found")
            
            # Remove from appropriate storage
            if config.wallet_type == WalletType.SOFTWARE:
                self._wallet_security.remove_wallet(address)
            elif config.wallet_type == WalletType.MULTISIG:
                self._multisig_wallets.pop(address, None)
            
            # Remove from manager
            del self._wallets[address]
            
            # Update default if needed
            if self._default_wallet == address:
                self._default_wallet = next(iter(self._wallets.keys()), None)
            
            log.info("Removed wallet: %s", address)
    
    def list_wallets(self) -> List[Dict[str, Any]]:
        """
        List all managed wallets.
        
        Returns
        -------
        list of dict
            Wallet information.
        """
        with self._lock:
            return [
                {
                    "address": addr,
                    "type": config.wallet_type.value,
                    "name": config.name,
                    "is_default": config.is_default,
                }
                for addr, config in self._wallets.items()
            ]
    
    def get_wallet_info(self, address: str) -> Optional[Dict[str, Any]]:
        """
        Get detailed information about a wallet.
        
        Parameters
        ----------
        address : str
            Wallet address.
        
        Returns
        -------
        dict or None
            Wallet information.
        """
        with self._lock:
            config = self._wallets.get(address)
            if not config:
                return None
            
            info = {
                "address": config.address,
                "type": config.wallet_type.value,
                "name": config.name,
                "is_default": config.is_default,
                "metadata": config.metadata,
            }
            
            if config.wallet_type == WalletType.MULTISIG:
                multisig = self._multisig_wallets.get(address)
                if multisig:
                    info["signers"] = [s.address for s in multisig.get_signers()]
                    info["required_weight"] = multisig.get_required_weight()
            
            return info
    
    def set_default_wallet(self, address: str) -> None:
        """
        Set the default wallet.
        
        Parameters
        ----------
        address : str
            Wallet address to set as default.
        """
        with self._lock:
            if address not in self._wallets:
                raise ValueError(f"Wallet {address} not found")
            
            # Update old default
            if self._default_wallet and self._default_wallet in self._wallets:
                self._wallets[self._default_wallet].is_default = False
            
            # Set new default
            self._wallets[address].is_default = True
            self._default_wallet = address
            
            log.info("Set default wallet: %s", address)
    
    def get_default_wallet(self) -> Optional[str]:
        """Get the default wallet address."""
        return self._default_wallet
    
    def export_wallet(
        self,
        address: str,
        export_path: Path,
        password: str,
    ) -> None:
        """
        Export a wallet to an encrypted backup.
        
        Parameters
        ----------
        address : str
            Wallet address to export.
        export_path : Path
            Path to save the export.
        password : str
            Password for export encryption.
        """
        config = self._wallets.get(address)
        if not config:
            raise ValueError(f"Wallet {address} not found")
        
        if config.wallet_type != WalletType.SOFTWARE:
            raise ValueError("Only software wallets can be exported")
        
        self._wallet_security.export_wallet(address, config.password or password, export_path)
    
    def import_wallet(
        self,
        import_path: Path,
        password: str,
        set_as_default: bool = False,
    ) -> str:
        """
        Import a wallet from an encrypted backup.
        
        Parameters
        ----------
        import_path : Path
            Path to the export file.
        password : str
            Password for export decryption.
        set_as_default : bool
            Whether to set as default wallet.
        
        Returns
        -------
        str
            Imported wallet address.
        """
        address = self._wallet_security.import_wallet(import_path, password)
        
        config = WalletConfig(
            wallet_type=WalletType.SOFTWARE,
            address=address,
            is_default=set_as_default,
            password=password,
        )
        
        with self._lock:
            self._wallets[address] = config
            
            if set_as_default:
                self._default_wallet = address
        
        return address
    
    def rotate_password(
        self,
        address: str,
        old_password: str,
        new_password: str,
    ) -> None:
        """
        Rotate the password for a software wallet.
        
        Parameters
        ----------
        address : str
            Wallet address.
        old_password : str
            Current password.
        new_password : str
            New password.
        """
        self._wallet_security.rotate_key(address, old_password, new_password)
        
        # Update config
        if address in self._wallets:
            self._wallets[address].password = new_password
        
        log.info("Rotated credentials for wallet: %s", mask_address(address))
    
    def shutdown(self) -> None:
        """Shutdown wallet manager."""
        with self._lock:
            log.info("Wallet manager shutdown complete")


__all__ = [
    "WalletType",
    "WalletConfig",
    "WalletManager",
]
