"""
Security features for database operations.

This module provides encryption, authentication, authorization, and data masking
capabilities for the TradeDatabase class.
"""

from __future__ import annotations

import base64
import hashlib
import hmac
import json
import logging
import secrets
from dataclasses import dataclass
from datetime import datetime, timezone, timedelta
from enum import Enum
from pathlib import Path
from typing import Optional, Dict, List, Set, Any, Callable
from threading import Lock

try:
    from cryptography.fernet import Fernet
    from cryptography.hazmat.primitives import hashes
    from cryptography.hazmat.primitives.kdf.pbkdf2 import PBKDF2HMAC
    CRYPTOGRAPHY_AVAILABLE = True
except ImportError:
    CRYPTOGRAPHY_AVAILABLE = False

try:
    import jwt
    JWT_AVAILABLE = True
except ImportError:
    JWT_AVAILABLE = False

try:
    import bcrypt
    BCRYPT_AVAILABLE = True
except ImportError:
    BCRYPT_AVAILABLE = False

log = logging.getLogger(__name__)


class AuthMethod(Enum):
    """Authentication method types."""
    NONE = "none"
    API_KEY = "api_key"
    JWT = "jwt"
    OAUTH2 = "oauth2"


@dataclass
class Role:
    """Role definition with permissions."""
    name: str
    permissions: Set[str]
    description: Optional[str] = None
    
    def has_permission(self, permission: str) -> bool:
        """Check if role has a specific permission."""
        return permission in self.permissions


@dataclass
class User:
    """User definition with roles."""
    user_id: str
    username: str
    roles: Set[str]
    api_key_hash: Optional[str] = None
    jwt_secret: Optional[str] = None
    enabled: bool = True
    created_at: datetime = None
    
    def __post_init__(self):
        if self.created_at is None:
            self.created_at = datetime.now(timezone.utc)
    
    def has_role(self, role_name: str) -> bool:
        """Check if user has a specific role."""
        return role_name in self.roles
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary (excluding sensitive data)."""
        return {
            "user_id": self.user_id,
            "username": self.username,
            "roles": list(self.roles),
            "enabled": self.enabled,
            "created_at": self.created_at.isoformat(),
        }


@dataclass
class MaskingRule:
    """Data masking rule for sensitive fields."""
    field_name: str
    mask_char: str = "*"
    show_first: int = 0
    show_last: int = 0
    mask_all: bool = False
    
    def mask(self, value: Optional[str]) -> Optional[str]:
        """Apply masking to a value."""
        if value is None:
            return None
        
        if self.mask_all:
            return self.mask_char * len(value)
        
        if self.show_first == 0 and self.show_last == 0:
            return self.mask_char * len(value)
        
        if len(value) <= self.show_first + self.show_last:
            # Value too short to mask properly
            return value
        
        first_part = value[:self.show_first]
        last_part = value[-self.show_last:]
        middle_length = len(value) - self.show_first - self.show_last
        middle = self.mask_char * middle_length
        
        return first_part + middle + last_part


class DatabaseEncryption:
    """
    Database encryption manager using Fernet symmetric encryption.
    
    Provides at-rest encryption for sensitive database fields and files.
    """
    
    def __init__(self, key: Optional[bytes] = None, password: Optional[str] = None):
        """
        Initialize encryption manager.
        
        Parameters
        ----------
        key : bytes, optional
            32-byte URL-safe base64-encoded encryption key.
            If not provided, a new key will be generated.
        password : str, optional
            Password to derive encryption key from using PBKDF2.
            If provided, key parameter is ignored.
        """
        if not CRYPTOGRAPHY_AVAILABLE:
            raise ImportError(
                "cryptography library is required for encryption. "
                "Install it with: pip install cryptography"
            )
        
        if password:
            self._key = self._derive_key_from_password(password)
        elif key:
            self._key = key
        else:
            self._key = Fernet.generate_key()
        
        self._cipher = Fernet(self._key)
        self._enabled = True
    
    def _derive_key_from_password(self, password: str, salt: Optional[bytes] = None) -> bytes:
        """
        Derive encryption key from password using PBKDF2.
        
        Parameters
        ----------
        password : str
            Password to derive key from.
        salt : bytes, optional
            Salt for key derivation. If not provided, a random salt is generated.
        
        Returns
        -------
        bytes
            32-byte encryption key.
        """
        if salt is None:
            salt = secrets.token_bytes(16)
        
        kdf = PBKDF2HMAC(
            algorithm=hashes.SHA256(),
            length=32,
            salt=salt,
            iterations=100000,
        )
        key = base64.urlsafe_b64encode(kdf.derive(password.encode()))
        return key
    
    @staticmethod
    def generate_key() -> bytes:
        """Generate a new random encryption key."""
        if not CRYPTOGRAPHY_AVAILABLE:
            raise ImportError(
                "cryptography library is required for encryption. "
                "Install it with: pip install cryptography"
            )
        return Fernet.generate_key()
    
    @staticmethod
    def key_from_password(password: str, salt: Optional[bytes] = None) -> bytes:
        """Derive encryption key from password."""
        if not CRYPTOGRAPHY_AVAILABLE:
            raise ImportError(
                "cryptography library is required for encryption. "
                "Install it with: pip install cryptography"
            )
        enc = DatabaseEncryption(password=password)
        return enc._key
    
    def encrypt(self, data: str) -> bytes:
        """
        Encrypt string data.
        
        Parameters
        ----------
        data : str
            Data to encrypt.
        
        Returns
        -------
        bytes
            Encrypted data.
        """
        if not self._enabled:
            return data.encode()
        
        return self._cipher.encrypt(data.encode())
    
    def decrypt(self, encrypted_data: bytes) -> str:
        """
        Decrypt encrypted data.
        
        Parameters
        ----------
        encrypted_data : bytes
            Data to decrypt.
        
        Returns
        -------
        str
            Decrypted string.
        """
        if not self._enabled:
            return encrypted_data.decode()
        
        return self._cipher.decrypt(encrypted_data).decode()
    
    def encrypt_dict(self, data: Dict[str, Any], fields: List[str]) -> Dict[str, Any]:
        """
        Encrypt specific fields in a dictionary.
        
        Parameters
        ----------
        data : dict
            Dictionary containing data to encrypt.
        fields : list of str
            Field names to encrypt.
        
        Returns
        -------
        dict
            Dictionary with specified fields encrypted.
        """
        result = data.copy()
        for field in fields:
            if field in result and result[field] is not None:
                if isinstance(result[field], str):
                    result[field] = self.encrypt(result[field])
                elif isinstance(result[field], (int, float)):
                    result[field] = self.encrypt(str(result[field]))
        return result
    
    def decrypt_dict(self, data: Dict[str, Any], fields: List[str]) -> Dict[str, Any]:
        """
        Decrypt specific fields in a dictionary.
        
        Parameters
        ----------
        data : dict
            Dictionary containing encrypted data.
        fields : list of str
            Field names to decrypt.
        
        Returns
        -------
        dict
            Dictionary with specified fields decrypted.
        """
        result = data.copy()
        for field in fields:
            if field in result and result[field] is not None:
                if isinstance(result[field], bytes):
                    result[field] = self.decrypt(result[field])
        return result
    
    def enable(self) -> None:
        """Enable encryption."""
        self._enabled = True
    
    def disable(self) -> None:
        """Disable encryption (data will be stored in plaintext)."""
        self._enabled = False
    
    def is_enabled(self) -> bool:
        """Check if encryption is enabled."""
        return self._enabled
    
    def get_key(self) -> bytes:
        """Get the encryption key."""
        return self._key


class AuthenticationManager:
    """
    Authentication manager for database access.
    
    Supports API key and JWT-based authentication.
    """
    
    def __init__(self, method: AuthMethod = AuthMethod.NONE):
        """
        Initialize authentication manager.
        
        Parameters
        ----------
        method : AuthMethod
            Authentication method to use.
        """
        self._method = method
        self._users: Dict[str, User] = {}
        self._api_keys: Dict[str, str] = {}  # api_key -> user_id mapping
        self._lock = Lock()
        self._jwt_algorithm = "HS256"
        self._jwt_expiry_hours = 24
    
    def set_method(self, method: AuthMethod) -> None:
        """
        Set authentication method.
        
        Parameters
        ----------
        method : AuthMethod
            Authentication method to use.
        """
        if method == AuthMethod.JWT and not JWT_AVAILABLE:
            raise ImportError(
                "PyJWT library is required for JWT authentication. "
                "Install it with: pip install pyjwt"
            )
        self._method = method
    
    def get_method(self) -> AuthMethod:
        """Get current authentication method."""
        return self._method
    
    def add_user(
        self,
        user_id: str,
        username: str,
        roles: List[str],
        api_key: Optional[str] = None,
        jwt_secret: Optional[str] = None,
    ) -> None:
        """
        Add a user to the authentication system.
        
        Parameters
        ----------
        user_id : str
            Unique user identifier.
        username : str
            Username.
        roles : list of str
            List of role names for the user.
        api_key : str, optional
            API key for the user (required if method is API_KEY).
        jwt_secret : str, optional
            JWT secret for the user (required if method is JWT).
        """
        with self._lock:
            api_key_hash = None
            if api_key:
                api_key_hash = self._hash_api_key(api_key)
                self._api_keys[api_key_hash] = user_id
            
            user = User(
                user_id=user_id,
                username=username,
                roles=set(roles),
                api_key_hash=api_key_hash,
                jwt_secret=jwt_secret,
            )
            self._users[user_id] = user
            log.info("Added user: %s with roles: %s", username, roles)
    
    def remove_user(self, user_id: str) -> None:
        """
        Remove a user from the authentication system.
        
        Parameters
        ----------
        user_id : str
            User identifier to remove.
        """
        with self._lock:
            if user_id in self._users:
                user = self._users[user_id]
                if user.api_key_hash:
                    self._api_keys.pop(user.api_key_hash, None)
                del self._users[user_id]
                log.info("Removed user: %s", user_id)
    
    def get_user(self, user_id: str) -> Optional[User]:
        """
        Get a user by ID.
        
        Parameters
        ----------
        user_id : str
            User identifier.
        
        Returns
        -------
        User or None
            User object if found, None otherwise.
        """
        return self._users.get(user_id)
    
    def _hash_api_key(self, api_key: str) -> str:
        """Hash an API key for storage using bcrypt."""
        if not BCRYPT_AVAILABLE:
            raise ImportError(
                "bcrypt library is required for secure password hashing. "
                "Install it with: pip install bcrypt"
            )
        salt = bcrypt.gensalt(rounds=12)
        hashed = bcrypt.hashpw(api_key.encode(), salt)
        return hashed.decode('utf-8')
    
    def generate_api_key(self) -> str:
        """Generate a random API key."""
        return f"pk_{secrets.token_urlsafe(32)}"
    
    def validate_api_key(self, api_key: str) -> Optional[str]:
        """
        Validate an API key and return the associated user ID.
        
        Parameters
        ----------
        api_key : str
            API key to validate.
        
        Returns
        -------
        str or None
            User ID if valid, None otherwise.
        """
        if self._method != AuthMethod.API_KEY:
            return None
        
        if not BCRYPT_AVAILABLE:
            raise ImportError(
                "bcrypt library is required for secure password hashing. "
                "Install it with: pip install bcrypt"
            )
        
        # Check against all stored hashes
        for stored_hash, user_id in self._api_keys.items():
            if bcrypt.checkpw(api_key.encode(), stored_hash.encode('utf-8')):
                return user_id
        
        return None
    
    def generate_jwt_token(self, user_id: str, payload: Optional[Dict[str, Any]] = None) -> str:
        """
        Generate a JWT token for a user.
        
        Parameters
        ----------
        user_id : str
            User identifier.
        payload : dict, optional
            Additional payload data.
        
        Returns
        -------
        str
            JWT token.
        """
        if not JWT_AVAILABLE:
            raise ImportError(
                "PyJWT library is required for JWT authentication. "
                "Install it with: pip install pyjwt"
            )
        
        user = self.get_user(user_id)
        if not user or not user.jwt_secret:
            raise ValueError(f"User {user_id} not found or has no JWT secret")
        
        now = datetime.now(timezone.utc)
        expiry = now + timedelta(hours=self._jwt_expiry_hours)
        
        token_payload = {
            "user_id": user_id,
            "username": user.username,
            "roles": list(user.roles),
            "iat": now.timestamp(),
            "exp": expiry.timestamp(),
        }
        
        if payload:
            token_payload.update(payload)
        
        token = jwt.encode(token_payload, user.jwt_secret, algorithm=self._jwt_algorithm)
        return token
    
    def validate_jwt_token(self, token: str, user_id: str) -> bool:
        """
        Validate a JWT token for a user.
        
        Parameters
        ----------
        token : str
            JWT token to validate.
        user_id : str
            Expected user ID.
        
        Returns
        -------
        bool
            True if valid, False otherwise.
        """
        if not JWT_AVAILABLE:
            return False
        
        user = self.get_user(user_id)
        if not user or not user.jwt_secret:
            return False
        
        try:
            payload = jwt.decode(
                token,
                user.jwt_secret,
                algorithms=[self._jwt_algorithm],
            )
            return payload.get("user_id") == user_id
        except jwt.InvalidTokenError:
            return False
    
    def is_enabled(self) -> bool:
        """Check if authentication is enabled."""
        return self._method != AuthMethod.NONE


class AuthorizationManager:
    """
    Authorization manager for role-based access control.
    
    Manages roles and permissions for database operations.
    """
    
    def __init__(self):
        """Initialize authorization manager."""
        self._roles: Dict[str, Role] = {}
        self._lock = Lock()
        self._initialize_default_roles()
    
    def _initialize_default_roles(self) -> None:
        """Initialize default roles."""
        # Admin role - full access
        self.add_role(
            Role(
                name="admin",
                permissions={
                    "read", "write", "delete", "export", "import",
                    "backup", "restore", "manage_users", "manage_roles",
                },
                description="Full administrative access",
            )
        )
        
        # Trader role - read and write trades
        self.add_role(
            Role(
                name="trader",
                permissions={"read", "write", "export"},
                description="Can read and write trades",
            )
        )
        
        # Analyst role - read-only access
        self.add_role(
            Role(
                name="analyst",
                permissions={"read", "export"},
                description="Read-only access for analysis",
            )
        )
        
        # Viewer role - limited read access
        self.add_role(
            Role(
                name="viewer",
                permissions={"read"},
                description="Limited read-only access",
            )
        )
    
    def add_role(self, role: Role) -> None:
        """
        Add a role.
        
        Parameters
        ----------
        role : Role
            Role to add.
        """
        with self._lock:
            self._roles[role.name] = role
            log.info("Added role: %s with permissions: %s", role.name, role.permissions)
    
    def remove_role(self, role_name: str) -> None:
        """
        Remove a role.
        
        Parameters
        ----------
        role_name : str
            Role name to remove.
        """
        with self._lock:
            if role_name in self._roles:
                del self._roles[role_name]
                log.info("Removed role: %s", role_name)
    
    def get_role(self, role_name: str) -> Optional[Role]:
        """
        Get a role by name.
        
        Parameters
        ----------
        role_name : str
            Role name.
        
        Returns
        -------
        Role or None
            Role object if found, None otherwise.
        """
        return self._roles.get(role_name)
    
    def check_permission(self, roles: Set[str], permission: str) -> bool:
        """
        Check if any of the given roles has a specific permission.
        
        Parameters
        ----------
        roles : set of str
            Set of role names to check.
        permission : str
            Permission to check for.
        
        Returns
        -------
        bool
            True if any role has the permission, False otherwise.
        """
        for role_name in roles:
            role = self.get_role(role_name)
            if role and role.has_permission(permission):
                return True
        return False
    
    def get_all_roles(self) -> Dict[str, Role]:
        """Get all roles."""
        return self._roles.copy()


class DataMasker:
    """
    Data masking manager for sensitive fields.
    
    Provides field-level masking for sensitive data like market IDs, API keys, etc.
    """
    
    def __init__(self):
        """Initialize data masker."""
        self._rules: Dict[str, MaskingRule] = {}
        self._enabled = True
        self._initialize_default_rules()
    
    def _initialize_default_rules(self) -> None:
        """Initialize default masking rules."""
        # Mask market_id (show first 4, last 4)
        self.add_rule(
            MaskingRule(
                field_name="market_id",
                mask_char="*",
                show_first=4,
                show_last=4,
            )
        )
        
        # Mask API keys (show first 3, last 4)
        self.add_rule(
            MaskingRule(
                field_name="api_key",
                mask_char="*",
                show_first=3,
                show_last=4,
            )
        )
        
        # Mask secrets completely
        self.add_rule(
            MaskingRule(
                field_name="secret",
                mask_char="*",
                mask_all=True,
            )
        )
        
        # Mask passwords completely
        self.add_rule(
            MaskingRule(
                field_name="password",
                mask_char="*",
                mask_all=True,
            )
        )
    
    def add_rule(self, rule: MaskingRule) -> None:
        """
        Add a masking rule.
        
        Parameters
        ----------
        rule : MaskingRule
            Masking rule to add.
        """
        self._rules[rule.field_name] = rule
        log.debug("Added masking rule for field: %s", rule.field_name)
    
    def remove_rule(self, field_name: str) -> None:
        """
        Remove a masking rule.
        
        Parameters
        ----------
        field_name : str
            Field name to remove rule for.
        """
        if field_name in self._rules:
            del self._rules[field_name]
            log.debug("Removed masking rule for field: %s", field_name)
    
    def mask_field(self, field_name: str, value: Optional[str]) -> Optional[str]:
        """
        Mask a field value if a rule exists.
        
        Parameters
        ----------
        field_name : str
            Field name.
        value : str or None
            Value to mask.
        
        Returns
        -------
        str or None
            Masked value if rule exists, original value otherwise.
        """
        if not self._enabled:
            return value
        
        rule = self._rules.get(field_name)
        if rule:
            return rule.mask(value)
        return value
    
    def mask_record(self, record: Dict[str, Any]) -> Dict[str, Any]:
        """
        Apply masking to all fields in a record.
        
        Parameters
        ----------
        record : dict
            Record dictionary.
        
        Returns
        -------
        dict
            Record with sensitive fields masked.
        """
        result = record.copy()
        for field_name, value in record.items():
            if isinstance(value, str):
                result[field_name] = self.mask_field(field_name, value)
        return result
    
    def enable(self) -> None:
        """Enable data masking."""
        self._enabled = True
    
    def disable(self) -> None:
        """Disable data masking."""
        self._enabled = False
    
    def is_enabled(self) -> bool:
        """Check if masking is enabled."""
        return self._enabled


__all__ = [
    "AuthMethod",
    "Role",
    "User",
    "MaskingRule",
    "DatabaseEncryption",
    "AuthenticationManager",
    "AuthorizationManager",
    "DataMasker",
]
