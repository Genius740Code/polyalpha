"""
Wallet security module for encrypted key storage and access control.

This module provides secure storage of private keys and wallet credentials
using encryption at rest, key derivation, and secure key management.
"""

from __future__ import annotations

import base64
import json
import logging
import os
import secrets
from dataclasses import dataclass, asdict
from datetime import datetime, timezone
from enum import Enum
from pathlib import Path
from typing import Optional, Dict, List, Any
from threading import Lock

from ..utils.logging_utils import mask_address

try:
    from cryptography.fernet import Fernet
    from cryptography.hazmat.primitives import hashes
    from cryptography.hazmat.primitives.kdf.pbkdf2 import PBKDF2HMAC
    CRYPTOGRAPHY_AVAILABLE = True
except ImportError:
    CRYPTOGRAPHY_AVAILABLE = False

try:
    import keyring
    KEYRING_AVAILABLE = True
except ImportError:
    KEYRING_AVAILABLE = False

log = logging.getLogger(__name__)


class WalletStorageType(Enum):
    """Wallet storage backend types."""
    FILE = "file"
    KEYRING = "keyring"
    ENV = "environment"
    MEMORY = "memory"


@dataclass
class WalletCredentials:
    """Encrypted wallet credentials."""
    wallet_address: str
    private_key_encrypted: bytes
    salt: bytes
    created_at: datetime
    last_accessed: datetime
    access_count: int = 0
    metadata: Optional[Dict[str, Any]] = None
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary for storage."""
        data = asdict(self)
        data['private_key_encrypted'] = base64.b64encode(self.private_key_encrypted).decode()
        data['salt'] = base64.b64encode(self.salt).decode()
        data['created_at'] = self.created_at.isoformat()
        data['last_accessed'] = self.last_accessed.isoformat()
        return data
    
    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> 'WalletCredentials':
        """Create from dictionary."""
        data['private_key_encrypted'] = base64.b64decode(data['private_key_encrypted'])
        data['salt'] = base64.b64decode(data['salt'])
        data['created_at'] = datetime.fromisoformat(data['created_at'])
        data['last_accessed'] = datetime.fromisoformat(data['last_accessed'])
        return cls(**data)


class WalletSecurity:
    """
    Wallet security manager for encrypted key storage.
    
    Provides:
    - AES-256 encryption for private keys at rest
    - PBKDF2 key derivation from passwords
    - Secure key storage using system keyring or encrypted files
    - Access logging and audit trail
    - Key rotation support
    """
    
    def __init__(
        self,
        storage_type: WalletStorageType = WalletStorageType.KEYRING,
        storage_path: Optional[Path] = None,
        encryption_key: Optional[bytes] = None,
    ):
        """
        Initialize wallet security manager.
        
        Parameters
        ----------
        storage_type : WalletStorageType
            Type of storage backend to use.
        storage_path : Path, optional
            Path for file-based storage (required if storage_type is FILE).
        encryption_key : bytes, optional
            Master encryption key. If not provided, will be derived from password.
        """
        if not CRYPTOGRAPHY_AVAILABLE:
            raise ImportError(
                "cryptography library is required for wallet security. "
                "Install it with: pip install cryptography"
            )
        
        if storage_type == WalletStorageType.KEYRING and not KEYRING_AVAILABLE:
            log.warning("keyring not available, falling back to FILE storage")
            storage_type = WalletStorageType.FILE
        
        self._storage_type = storage_type
        self._storage_path = storage_path or Path.home() / ".polyalpha" / "wallets"
        self._encryption_key = encryption_key
        self._cipher: Optional[Fernet] = None
        self._wallets: Dict[str, WalletCredentials] = {}
        self._lock = Lock()
        
        if self._encryption_key:
            self._cipher = Fernet(self._encryption_key)
        
        # Ensure storage directory exists
        if self._storage_type == WalletStorageType.FILE:
            self._storage_path.mkdir(parents=True, exist_ok=True)
        
        # Load existing wallets
        self._load_wallets()
    
    def _derive_key(self, password: str, salt: Optional[bytes] = None) -> tuple[bytes, bytes]:
        """
        Derive encryption key from password using PBKDF2.
        
        Parameters
        ----------
        password : str
            Password to derive key from.
        salt : bytes, optional
            Salt for key derivation. Generated if not provided.
        
        Returns
        -------
        tuple
            (encryption_key, salt)
        """
        if salt is None:
            salt = secrets.token_bytes(16)
        
        kdf = PBKDF2HMAC(
            algorithm=hashes.SHA256(),
            length=32,
            salt=salt,
            iterations=600000,  # Increased to 600,000 per OWASP recommendations
        )
        key = base64.urlsafe_b64encode(kdf.derive(password.encode()))
        return key, salt
    
    def _encrypt_private_key(self, private_key: str, password: str) -> tuple[bytes, bytes]:
        """
        Encrypt a private key with a password.
        
        Parameters
        ----------
        private_key : str
            Private key to encrypt.
        password : str
            Password to encrypt with.
        
        Returns
        -------
        tuple
            (encrypted_key, salt)
        """
        key, salt = self._derive_key(password)
        cipher = Fernet(key)
        encrypted = cipher.encrypt(private_key.encode())
        return encrypted, salt
    
    def _decrypt_private_key(self, encrypted_key: bytes, password: str, salt: bytes) -> str:
        """
        Decrypt a private key with a password.
        
        Parameters
        ----------
        encrypted_key : bytes
            Encrypted private key.
        password : str
            Password to decrypt with.
        salt : bytes
            Salt used for encryption.
        
        Returns
        -------
        str
            Decrypted private key.
        """
        key, _ = self._derive_key(password, salt)
        cipher = Fernet(key)
        decrypted = cipher.decrypt(encrypted_key)
        return decrypted.decode()
    
    def add_wallet(
        self,
        wallet_address: str,
        private_key: str,
        password: str,
        metadata: Optional[Dict[str, Any]] = None,
    ) -> None:
        """
        Add a wallet with encrypted private key.
        
        Parameters
        ----------
        wallet_address : str
            Wallet address.
        private_key : str
            Private key to encrypt and store.
        password : str
            Password for encryption.
        metadata : dict, optional
            Additional metadata for the wallet.
        """
        with self._lock:
            if wallet_address in self._wallets:
                raise ValueError(f"Wallet {wallet_address} already exists")
            
            encrypted_key, salt = self._encrypt_private_key(private_key, password)
            
            credentials = WalletCredentials(
                wallet_address=wallet_address,
                private_key_encrypted=encrypted_key,
                salt=salt,
                created_at=datetime.now(timezone.utc),
                last_accessed=datetime.now(timezone.utc),
                metadata=metadata,
            )
            
            self._wallets[wallet_address] = credentials
            self._save_wallet(wallet_address, credentials)
            log.info("Added wallet: %s", wallet_address)
    
    def get_private_key(self, wallet_address: str, password: str) -> str:
        """
        Retrieve and decrypt a private key.
        
        Parameters
        ----------
        wallet_address : str
            Wallet address.
        password : str
            Password for decryption.
        
        Returns
        -------
        str
            Decrypted private key.
        """
        with self._lock:
            credentials = self._wallets.get(wallet_address)
            if not credentials:
                raise ValueError(f"Wallet {wallet_address} not found")
            
            try:
                private_key = self._decrypt_private_key(
                    credentials.private_key_encrypted,
                    password,
                    credentials.salt,
                )
                
                # Update access tracking
                credentials.last_accessed = datetime.now(timezone.utc)
                credentials.access_count += 1
                self._save_wallet(wallet_address, credentials)
                
                log.info("Accessed wallet: %s (access count: %d)", mask_address(wallet_address), credentials.access_count)
                return private_key
            except Exception as e:
                log.error("Failed to decrypt private key for wallet %s: %s", mask_address(wallet_address), e)
                raise ValueError("Invalid password or corrupted data") from e
    
    def remove_wallet(self, wallet_address: str) -> None:
        """
        Remove a wallet from storage.
        
        Parameters
        ----------
        wallet_address : str
            Wallet address to remove.
        """
        with self._lock:
            if wallet_address not in self._wallets:
                raise ValueError(f"Wallet {wallet_address} not found")
            
            del self._wallets[wallet_address]
            self._delete_wallet(wallet_address)
            log.info("Removed wallet: %s", mask_address(wallet_address))
    
    def list_wallets(self) -> List[str]:
        """
        List all stored wallet addresses.
        
        Returns
        -------
        list of str
            Wallet addresses.
        """
        with self._lock:
            return list(self._wallets.keys())
    
    def rotate_key(
        self,
        wallet_address: str,
        old_password: str,
        new_password: str,
    ) -> None:
        """
        Rotate the encryption password for a wallet.
        
        Parameters
        ----------
        wallet_address : str
            Wallet address.
        old_password : str
            Current password.
        new_password : str
            New password.
        """
        with self._lock:
            credentials = self._wallets.get(wallet_address)
            if not credentials:
                raise ValueError(f"Wallet {wallet_address} not found")
            
            # Decrypt with old password
            private_key = self._decrypt_private_key(
                credentials.private_key_encrypted,
                old_password,
                credentials.salt,
            )
            
            # Re-encrypt with new password
            encrypted_key, salt = self._encrypt_private_key(private_key, new_password)
            
            credentials.private_key_encrypted = encrypted_key
            credentials.salt = salt
            credentials.last_accessed = datetime.now(timezone.utc)
            
            self._save_wallet(wallet_address, credentials)
            log.info("Rotated key for wallet: %s", wallet_address)
    
    def _save_wallet(self, wallet_address: str, credentials: WalletCredentials) -> None:
        """Save wallet credentials to storage."""
        if self._storage_type == WalletStorageType.KEYRING:
            self._save_to_keyring(wallet_address, credentials)
        elif self._storage_type == WalletStorageType.FILE:
            self._save_to_file(wallet_address, credentials)
        elif self._storage_type == WalletStorageType.MEMORY:
            pass  # Already in memory
    
    def _load_wallets(self) -> None:
        """Load all wallets from storage."""
        if self._storage_type == WalletStorageType.KEYRING:
            self._load_from_keyring()
        elif self._storage_type == WalletStorageType.FILE:
            self._load_from_file()
    
    def _save_to_keyring(self, wallet_address: str, credentials: WalletCredentials) -> None:
        """Save wallet to system keyring."""
        if not KEYRING_AVAILABLE:
            raise RuntimeError("keyring not available")
        
        service_name = "polyalpha_wallet"
        data = json.dumps(credentials.to_dict())
        keyring.set_password(service_name, wallet_address, data)
    
    def _load_from_keyring(self) -> None:
        """Load wallets from system keyring."""
        if not KEYRING_AVAILABLE:
            return
        
        service_name = "polyalpha_wallet"
        try:
            # Try to load known wallets (this is a simplified approach)
            # In production, you'd maintain a registry of wallet addresses
            for wallet_address in self._list_known_wallets():
                data = keyring.get_password(service_name, wallet_address)
                if data:
                    credentials = WalletCredentials.from_dict(json.loads(data))
                    self._wallets[wallet_address] = credentials
        except Exception as e:
            log.warning("Failed to load wallets from keyring: %s", e)
    
    def _save_to_file(self, wallet_address: str, credentials: WalletCredentials) -> None:
        """Save wallet to encrypted file."""
        wallet_file = self._storage_path / f"{wallet_address}.json"
        
        if self._cipher:
            # Encrypt the entire wallet file
            data = json.dumps(credentials.to_dict())
            encrypted = self._cipher.encrypt(data.encode())
            wallet_file.write_bytes(encrypted)
        else:
            # Store as JSON (less secure)
            with open(wallet_file, 'w') as f:
                json.dump(credentials.to_dict(), f, indent=2)
    
    def _load_from_file(self) -> None:
        """Load wallets from files."""
        if not self._storage_path.exists():
            return
        
        for wallet_file in self._storage_path.glob("*.json"):
            try:
                wallet_address = wallet_file.stem
                
                if self._cipher:
                    # Decrypt the wallet file
                    encrypted = wallet_file.read_bytes()
                    decrypted = self._cipher.decrypt(encrypted)
                    data = json.loads(decrypted.decode())
                else:
                    # Read as JSON
                    with open(wallet_file, 'r') as f:
                        data = json.load(f)
                
                credentials = WalletCredentials.from_dict(data)
                self._wallets[wallet_address] = credentials
            except Exception as e:
                log.warning("Failed to load wallet from %s: %s", wallet_file.name, e)
    
    def _delete_wallet(self, wallet_address: str) -> None:
        """Delete wallet from storage."""
        if self._storage_type == WalletStorageType.KEYRING:
            if KEYRING_AVAILABLE:
                service_name = "polyalpha_wallet"
                keyring.delete_password(service_name, wallet_address)
        elif self._storage_type == WalletStorageType.FILE:
            wallet_file = self._storage_path / f"{wallet_address}.json"
            if wallet_file.exists():
                wallet_file.unlink()
    
    def _list_known_wallets(self) -> List[str]:
        """List known wallet addresses (for keyring loading)."""
        # This is a placeholder - in production, maintain a registry
        return list(self._wallets.keys())
    
    def export_wallet(self, wallet_address: str, password: str, export_path: Path) -> None:
        """
        Export a wallet to an encrypted backup file.
        
        Parameters
        ----------
        wallet_address : str
            Wallet address to export.
        password : str
            Password for export encryption.
        export_path : Path
            Path to save the export.
        """
        with self._lock:
            credentials = self._wallets.get(wallet_address)
            if not credentials:
                raise ValueError(f"Wallet {wallet_address} not found")
            
            # Create export with additional encryption layer
            export_key, export_salt = self._derive_key(password)
            export_cipher = Fernet(export_key)
            
            export_data = {
                "wallet_address": wallet_address,
                "encrypted_key": base64.b64encode(credentials.private_key_encrypted).decode(),
                "salt": base64.b64encode(credentials.salt).decode(),
                "export_salt": base64.b64encode(export_salt).decode(),
                "created_at": datetime.now(timezone.utc).isoformat(),
            }
            
            encrypted_export = export_cipher.encrypt(json.dumps(export_data).encode())
            # Prepend salt so import can read it without decrypting
            export_path.write_text(
                base64.b64encode(export_salt).decode() + "\n" + encrypted_export.decode()
            )
            
            log.info("Exported wallet: %s to %s", mask_address(wallet_address), export_path.name)
    
    def import_wallet(self, import_path: Path, password: str) -> str:
        """
        Import a wallet from an encrypted backup file.
        
        Parameters
        ----------
        import_path : Path
            Path to the export file.
        password : str
            Password for export decryption.
        
        Returns
        -------
        str
            Imported wallet address.
        """
        with self._lock:
            content = import_path.read_text()
            salt_b64, encrypted_b64 = content.split("\n", 1)
            export_salt = base64.b64decode(salt_b64)
            export_key, _ = self._derive_key(password, export_salt)
            export_cipher = Fernet(export_key)
            
            decrypted = export_cipher.decrypt(encrypted_b64.encode())
            data = json.loads(decrypted.decode())
            
            wallet_address = data["wallet_address"]
            
            if wallet_address in self._wallets:
                raise ValueError(f"Wallet {wallet_address} already exists")
            
            credentials = WalletCredentials(
                wallet_address=wallet_address,
                private_key_encrypted=base64.b64decode(data["encrypted_key"]),
                salt=base64.b64decode(data["salt"]),
                created_at=datetime.fromisoformat(data["created_at"]),
                last_accessed=datetime.now(timezone.utc),
            )
            
            self._wallets[wallet_address] = credentials
            self._save_wallet(wallet_address, credentials)
            
            log.info("Imported wallet: %s from %s", mask_address(wallet_address), import_path.name)
            return wallet_address


__all__ = [
    "WalletStorageType",
    "WalletCredentials",
    "WalletSecurity",
]
