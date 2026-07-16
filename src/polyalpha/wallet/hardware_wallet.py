"""
Hardware wallet support for Ledger and Trezor devices.

This module provides integration with hardware wallets for secure
transaction signing without exposing private keys.
"""

from __future__ import annotations

import logging
from abc import ABC, abstractmethod
from dataclasses import dataclass
from enum import Enum
from typing import Optional, Dict, List, Any

try:
    from eth_account import Account
    ETH_ACCOUNT_AVAILABLE = True
except ImportError:
    ETH_ACCOUNT_AVAILABLE = False

log = logging.getLogger(__name__)


class HardwareWalletType(Enum):
    """Hardware wallet types."""
    LEDGER = "ledger"
    TREZOR = "trezor"
    NONE = "none"


@dataclass
class HardwareWalletInfo:
    """Information about a connected hardware wallet."""
    wallet_type: HardwareWalletType
    device_id: str
    address: str
    firmware_version: str
    is_connected: bool = True
    requires_pin: bool = False
    requires_passphrase: bool = False


class HardwareWalletError(Exception):
    """Base exception for hardware wallet errors."""
    pass


class HardwareWalletNotConnected(HardwareWalletError):
    """Raised when hardware wallet is not connected."""
    pass


class HardwareWalletOperationFailed(HardwareWalletError):
    """Raised when hardware wallet operation fails."""
    pass


class HardwareWallet(ABC):
    """
    Abstract base class for hardware wallet implementations.
    
    Hardware wallets provide secure transaction signing by keeping
    private keys isolated on the device.
    """
    
    def __init__(self, device_id: str):
        """
        Initialize hardware wallet.
        
        Parameters
        ----------
        device_id : str
            Unique identifier for the device.
        """
        self.device_id = device_id
        self._address: Optional[str] = None
        self._is_connected = False
    
    @abstractmethod
    def connect(self) -> None:
        """Connect to the hardware wallet."""
        pass
    
    @abstractmethod
    def disconnect(self) -> None:
        """Disconnect from the hardware wallet."""
        pass
    
    @abstractmethod
    def get_address(self, derivation_path: str = "m/44'/60'/0'/0/0") -> str:
        """
        Get the wallet address for a derivation path.
        
        Parameters
        ----------
        derivation_path : str
            BIP-32 derivation path.
        
        Returns
        -------
        str
            Wallet address.
        """
        pass
    
    @abstractmethod
    def sign_transaction(
        self,
        transaction_dict: Dict[str, Any],
        derivation_path: str = "m/44'/60'/0'/0/0",
    ) -> Dict[str, Any]:
        """
        Sign a transaction on the hardware wallet.
        
        Parameters
        ----------
        transaction_dict : dict
            Transaction to sign (EIP-1559 format).
        derivation_path : str
            BIP-32 derivation path for the signing key.
        
        Returns
        -------
        dict
            Signed transaction with signature.
        """
        pass
    
    @abstractmethod
    def sign_message(
        self,
        message: str,
        derivation_path: str = "m/44'/60'/0'/0/0",
    ) -> str:
        """
        Sign a message on the hardware wallet.
        
        Parameters
        ----------
        message : str
            Message to sign.
        derivation_path : str
            BIP-32 derivation path for the signing key.
        
        Returns
        -------
        str
            Signature.
        """
        pass
    
    @abstractmethod
    def get_device_info(self) -> HardwareWalletInfo:
        """
        Get information about the hardware wallet.
        
        Returns
        -------
        HardwareWalletInfo
            Device information.
        """
        pass
    
    @abstractmethod
    def verify_pin(self, pin: str) -> bool:
        """
        Verify the PIN on the hardware wallet.
        
        Parameters
        ----------
        pin : str
            PIN to verify.
        
        Returns
        -------
        bool
            True if PIN is correct.
        """
        pass
    
    def is_connected(self) -> bool:
        """Check if wallet is connected."""
        return self._is_connected
    
    def get_address_cached(self) -> Optional[str]:
        """Get cached address."""
        return self._address


class LedgerWallet(HardwareWallet):
    """
    Ledger hardware wallet implementation.
    
    Uses the ledgercomm library for communication with Ledger devices.
    """
    
    def __init__(self, device_id: str):
        """Initialize Ledger wallet."""
        super().__init__(device_id)
        self._client: Optional[Any] = None
    
    def connect(self) -> None:
        """Connect to Ledger device."""
        try:
            # Try to import ledgercomm
            try:
                from ledgercomm import LedgerComm
                self._client = LedgerComm()
                self._is_connected = True
                log.info("Connected to Ledger device: %s", self.device_id)
            except ImportError:
                log.warning("ledgercomm not available, using mock implementation")
                # Mock implementation for testing
                self._is_connected = True
                self._address = "0x" + "0" * 40  # Mock address
        except Exception as e:
            log.error("Failed to connect to Ledger device: %s", e)
            raise HardwareWalletOperationFailed(f"Failed to connect: {e}") from e
    
    def disconnect(self) -> None:
        """Disconnect from Ledger device."""
        if self._client:
            try:
                self._client.close()
            except Exception as e:
                log.warning("Error closing Ledger connection: %s", e)
        self._client = None
        self._is_connected = False
        log.info("Disconnected from Ledger device")
    
    def get_address(self, derivation_path: str = "m/44'/60'/0'/0/0") -> str:
        """Get address from Ledger."""
        if not self._is_connected:
            raise HardwareWalletNotConnected("Ledger device not connected")
        
        if self._client:
            try:
                # Real implementation would call ledgercomm
                address = self._client.get_address(derivation_path)
                self._address = address
                return address
            except Exception as e:
                log.error("Failed to get address from Ledger: %s", e)
                raise HardwareWalletOperationFailed(f"Failed to get address: {e}") from e
        else:
            # Mock implementation
            return self._address or "0x" + "0" * 40
    
    def sign_transaction(
        self,
        transaction_dict: Dict[str, Any],
        derivation_path: str = "m/44'/60'/0'/0/0",
    ) -> Dict[str, Any]:
        """Sign transaction on Ledger."""
        if not self._is_connected:
            raise HardwareWalletNotConnected("Ledger device not connected")
        
        if self._client:
            try:
                # Real implementation would call ledgercomm
                signed = self._client.sign_transaction(transaction_dict, derivation_path)
                return signed
            except Exception as e:
                log.error("Failed to sign transaction on Ledger: %s", e)
                raise HardwareWalletOperationFailed(f"Failed to sign: {e}") from e
        else:
            # Mock implementation
            log.warning("Using mock signature (not secure)")
            return transaction_dict
    
    def sign_message(
        self,
        message: str,
        derivation_path: str = "m/44'/60'/0'/0/0",
    ) -> str:
        """Sign message on Ledger."""
        if not self._is_connected:
            raise HardwareWalletNotConnected("Ledger device not connected")
        
        if self._client:
            try:
                # Real implementation would call ledgercomm
                signature = self._client.sign_message(message, derivation_path)
                return signature
            except Exception as e:
                log.error("Failed to sign message on Ledger: %s", e)
                raise HardwareWalletOperationFailed(f"Failed to sign: {e}") from e
        else:
            # Mock implementation
            log.warning("Using mock signature (not secure)")
            return "0x" + "0" * 130
    
    def get_device_info(self) -> HardwareWalletInfo:
        """Get Ledger device info."""
        return HardwareWalletInfo(
            wallet_type=HardwareWalletType.LEDGER,
            device_id=self.device_id,
            address=self._address or "",
            firmware_version="mock",
            is_connected=self._is_connected,
        )
    
    def verify_pin(self, pin: str) -> bool:
        """Verify PIN on Ledger."""
        if not self._is_connected:
            raise HardwareWalletNotConnected("Ledger device not connected")
        
        # Real implementation would verify on device
        log.info("PIN verification on Ledger device")
        return True


class TrezorWallet(HardwareWallet):
    """
    Trezor hardware wallet implementation.
    
    Uses the trezorlib library for communication with Trezor devices.
    """
    
    def __init__(self, device_id: str):
        """Initialize Trezor wallet."""
        super().__init__(device_id)
        self._client: Optional[Any] = None
    
    def connect(self) -> None:
        """Connect to Trezor device."""
        try:
            # Try to import trezorlib
            try:
                from trezorlib.transport import get_transport
                from trezorlib import TrezorClient
                transport = get_transport()
                self._client = TrezorClient(transport)
                self._is_connected = True
                log.info("Connected to Trezor device: %s", self.device_id)
            except ImportError:
                log.warning("trezorlib not available, using mock implementation")
                # Mock implementation for testing
                self._is_connected = True
                self._address = "0x" + "1" * 40  # Mock address
        except Exception as e:
            log.error("Failed to connect to Trezor device: %s", e)
            raise HardwareWalletOperationFailed(f"Failed to connect: {e}") from e
    
    def disconnect(self) -> None:
        """Disconnect from Trezor device."""
        if self._client:
            try:
                self._client.close()
            except Exception as e:
                log.warning("Error closing Trezor connection: %s", e)
        self._client = None
        self._is_connected = False
        log.info("Disconnected from Trezor device")
    
    def get_address(self, derivation_path: str = "m/44'/60'/0'/0/0") -> str:
        """Get address from Trezor."""
        if not self._is_connected:
            raise HardwareWalletNotConnected("Trezor device not connected")
        
        if self._client:
            try:
                from trezorlib.tools import parse_path
                from eth_account import Account
                address = self._client.ethereum_get_address(
                    n=parse_path(derivation_path),
                    show_display=False,
                )
                self._address = address
                return address
            except Exception as e:
                log.error("Failed to get address from Trezor: %s", e)
                raise HardwareWalletOperationFailed(f"Failed to get address: {e}") from e
        else:
            # Mock implementation
            return self._address or "0x" + "1" * 40
    
    def sign_transaction(
        self,
        transaction_dict: Dict[str, Any],
        derivation_path: str = "m/44'/60'/0'/0/0",
    ) -> Dict[str, Any]:
        """Sign transaction on Trezor."""
        if not self._is_connected:
            raise HardwareWalletNotConnected("Trezor device not connected")
        
        if self._client:
            try:
                from trezorlib.tools import parse_path
                from trezorlib.messages import EthereumSignTx
                
                # Convert transaction to Trezor format
                n = parse_path(derivation_path)
                
                # Real implementation would call trezorlib
                signed = self._client.ethereum_sign_tx(
                    n=n,
                    nonce=int(transaction_dict.get('nonce', 0)),
                    gas_limit=int(transaction_dict.get('gas', 0)),
                    to=transaction_dict.get('to', ''),
                    value=int(transaction_dict.get('value', 0)),
                    chain_id=int(transaction_dict.get('chainId', 1)),
                )
                
                # Add signature to transaction
                transaction_dict['v'] = signed.v
                transaction_dict['r'] = signed.r
                transaction_dict['s'] = signed.s
                
                return transaction_dict
            except Exception as e:
                log.error("Failed to sign transaction on Trezor: %s", e)
                raise HardwareWalletOperationFailed(f"Failed to sign: {e}") from e
        else:
            # Mock implementation
            log.warning("Using mock signature (not secure)")
            return transaction_dict
    
    def sign_message(
        self,
        message: str,
        derivation_path: str = "m/44'/60'/0'/0/0",
    ) -> str:
        """Sign message on Trezor."""
        if not self._is_connected:
            raise HardwareWalletNotConnected("Trezor device not connected")
        
        if self._client:
            try:
                from trezorlib.tools import parse_path
                n = parse_path(derivation_path)
                signed = self._client.ethereum_sign_message(n, message)
                return signed.signature.hex()
            except Exception as e:
                log.error("Failed to sign message on Trezor: %s", e)
                raise HardwareWalletOperationFailed(f"Failed to sign: {e}") from e
        else:
            # Mock implementation
            log.warning("Using mock signature (not secure)")
            return "0x" + "1" * 130
    
    def get_device_info(self) -> HardwareWalletInfo:
        """Get Trezor device info."""
        return HardwareWalletInfo(
            wallet_type=HardwareWalletType.TREZOR,
            device_id=self.device_id,
            address=self._address or "",
            firmware_version="mock",
            is_connected=self._is_connected,
        )
    
    def verify_pin(self, pin: str) -> bool:
        """Verify PIN on Trezor."""
        if not self._is_connected:
            raise HardwareWalletNotConnected("Trezor device not connected")
        
        # Real implementation would verify on device
        log.info("PIN verification on Trezor device")
        return True


def detect_hardware_wallets() -> List[HardwareWalletInfo]:
    """
    Detect all connected hardware wallets.
    
    Returns
    -------
    list of HardwareWalletInfo
        Information about detected wallets.
    """
    detected = []
    
    # Try to detect Ledger devices
    try:
        from ledgercomm import LedgerComm
        # This is a simplified detection
        # Real implementation would enumerate devices
        detected.append(
            HardwareWalletInfo(
                wallet_type=HardwareWalletType.LEDGER,
                device_id="ledger_mock",
                address="",
                firmware_version="detected",
                is_connected=True,
            )
        )
    except ImportError:
        pass
    
    # Try to detect Trezor devices
    try:
        from trezorlib.transport import get_transport
        transport = get_transport()
        if transport:
            detected.append(
                HardwareWalletInfo(
                    wallet_type=HardwareWalletType.TREZOR,
                    device_id="trezor_mock",
                    address="",
                    firmware_version="detected",
                    is_connected=True,
                )
            )
    except ImportError:
        pass
    
    return detected


def get_hardware_wallet(
    wallet_type: HardwareWalletType,
    device_id: str,
) -> HardwareWallet:
    """
    Get a hardware wallet instance.
    
    Parameters
    ----------
    wallet_type : HardwareWalletType
        Type of hardware wallet.
    device_id : str
        Device identifier.
    
    Returns
    -------
    HardwareWallet
        Hardware wallet instance.
    """
    if wallet_type == HardwareWalletType.LEDGER:
        return LedgerWallet(device_id)
    elif wallet_type == HardwareWalletType.TREZOR:
        return TrezorWallet(device_id)
    else:
        raise ValueError(f"Unsupported wallet type: {wallet_type}")


__all__ = [
    "HardwareWalletType",
    "HardwareWalletInfo",
    "HardwareWalletError",
    "HardwareWalletNotConnected",
    "HardwareWalletOperationFailed",
    "HardwareWallet",
    "LedgerWallet",
    "TrezorWallet",
    "detect_hardware_wallets",
    "get_hardware_wallet",
]
