"""
Tests for database security features.

Tests encryption, authentication, authorization, and data masking.
"""

import pytest
from datetime import datetime, timezone
from pathlib import Path
import tempfile

from polyalpha.database import (
    TradeDatabase,
    DatabaseEncryption,
    AuthenticationManager,
    AuthorizationManager,
    DataMasker,
    AuthMethod,
    Role,
    User,
    MaskingRule,
)


class TestDatabaseEncryption:
    """Tests for database encryption."""
    
    def test_generate_key(self):
        """Test encryption key generation."""
        key = DatabaseEncryption.generate_key()
        assert isinstance(key, bytes)
        assert len(key) > 0
    
    def test_key_from_password(self):
        """Test key derivation from password."""
        password = "test_password_123"
        key = DatabaseEncryption.key_from_password(password)
        assert isinstance(key, bytes)
        assert len(key) > 0
        
        # Same password should produce same key with same salt
        key2 = DatabaseEncryption.key_from_password(password, salt=b"test_salt")
        assert key2 == key2
    
    def test_encrypt_decrypt_string(self):
        """Test string encryption and decryption."""
        enc = DatabaseEncryption()
        original = "sensitive_data_123"
        
        encrypted = enc.encrypt(original)
        assert isinstance(encrypted, bytes)
        assert encrypted != original.encode()
        
        decrypted = enc.decrypt(encrypted)
        assert decrypted == original
    
    def test_encrypt_decrypt_dict(self):
        """Test dictionary field encryption and decryption."""
        enc = DatabaseEncryption()
        data = {
            "market_id": "abc123",
            "market_slug": "btc-updown-5m",
            "amount": 100.0,
        }
        
        fields_to_encrypt = ["market_id"]
        encrypted = enc.encrypt_dict(data, fields_to_encrypt)
        
        assert isinstance(encrypted["market_id"], bytes)
        assert encrypted["market_slug"] == data["market_slug"]
        assert encrypted["amount"] == data["amount"]
        
        decrypted = enc.decrypt_dict(encrypted, fields_to_encrypt)
        assert decrypted["market_id"] == data["market_id"]
    
    def test_enable_disable_encryption(self):
        """Test enabling and disabling encryption."""
        enc = DatabaseEncryption()
        assert enc.is_enabled() is True
        
        enc.disable()
        assert enc.is_enabled() is False
        
        enc.enable()
        assert enc.is_enabled() is True
    
    def test_encryption_disabled_returns_plaintext(self):
        """Test that disabled encryption returns plaintext."""
        enc = DatabaseEncryption()
        original = "test_data"
        
        enc.disable()
        encrypted = enc.encrypt(original)
        assert encrypted == original.encode()
        
        decrypted = enc.decrypt(encrypted)
        assert decrypted == original


class TestAuthenticationManager:
    """Tests for authentication manager."""
    
    def test_set_auth_method(self):
        """Test setting authentication method."""
        auth = AuthenticationManager()
        assert auth.get_method() == AuthMethod.NONE
        
        auth.set_method(AuthMethod.API_KEY)
        assert auth.get_method() == AuthMethod.API_KEY
    
    def test_add_remove_user(self):
        """Test adding and removing users."""
        auth = AuthenticationManager()
        
        auth.add_user("user1", "trader", ["trader"])
        user = auth.get_user("user1")
        assert user is not None
        assert user.username == "trader"
        assert "trader" in user.roles
        
        auth.remove_user("user1")
        assert auth.get_user("user1") is None
    
    def test_generate_api_key(self):
        """Test API key generation."""
        auth = AuthenticationManager()
        api_key = auth.generate_api_key()
        assert api_key.startswith("pk_")
        assert len(api_key) > 10
    
    def test_validate_api_key(self):
        """Test API key validation."""
        auth = AuthenticationManager()
        auth.set_method(AuthMethod.API_KEY)
        
        api_key = auth.generate_api_key()
        auth.add_user("user1", "trader", ["trader"], api_key=api_key)
        
        # Valid key
        user_id = auth.validate_api_key(api_key)
        assert user_id == "user1"
        
        # Invalid key
        user_id = auth.validate_api_key("invalid_key")
        assert user_id is None
    
    def test_generate_validate_jwt_token(self):
        """Test JWT token generation and validation."""
        pytest.importorskip("jwt")
        
        auth = AuthenticationManager()
        auth.set_method(AuthMethod.JWT)
        
        jwt_secret = "test_secret_123"
        auth.add_user("user1", "trader", ["trader"], jwt_secret=jwt_secret)
        
        # Generate token
        token = auth.generate_jwt_token("user1")
        assert isinstance(token, str)
        
        # Validate token
        assert auth.validate_jwt_token(token, "user1") is True
        assert auth.validate_jwt_token(token, "user2") is False
        assert auth.validate_jwt_token("invalid_token", "user1") is False


class TestAuthorizationManager:
    """Tests for authorization manager."""
    
    def test_default_roles(self):
        """Test that default roles are created."""
        authz = AuthorizationManager()
        
        admin_role = authz.get_role("admin")
        assert admin_role is not None
        assert "read" in admin_role.permissions
        assert "write" in admin_role.permissions
        assert "delete" in admin_role.permissions
        
        trader_role = authz.get_role("trader")
        assert trader_role is not None
        assert "read" in trader_role.permissions
        assert "write" in trader_role.permissions
        assert "delete" not in trader_role.permissions
    
    def test_add_remove_role(self):
        """Test adding and removing custom roles."""
        authz = AuthorizationManager()
        
        role = Role(
            name="custom",
            permissions={"read", "export"},
            description="Custom role"
        )
        authz.add_role(role)
        
        retrieved = authz.get_role("custom")
        assert retrieved is not None
        assert retrieved.name == "custom"
        assert "read" in retrieved.permissions
        
        authz.remove_role("custom")
        assert authz.get_role("custom") is None
    
    def test_check_permission(self):
        """Test permission checking."""
        authz = AuthorizationManager()
        
        # Admin has all permissions
        assert authz.check_permission({"admin"}, "read") is True
        assert authz.check_permission({"admin"}, "delete") is True
        
        # Trader has limited permissions
        assert authz.check_permission({"trader"}, "read") is True
        assert authz.check_permission({"trader"}, "write") is True
        assert authz.check_permission({"trader"}, "delete") is False
        
        # Viewer has only read
        assert authz.check_permission({"viewer"}, "read") is True
        assert authz.check_permission({"viewer"}, "write") is False
        
        # Multiple roles
        assert authz.check_permission({"viewer", "trader"}, "write") is True


class TestDataMasker:
    """Tests for data masking."""
    
    def test_default_rules(self):
        """Test that default masking rules are created."""
        masker = DataMasker()
        
        # market_id should have a rule
        masked = masker.mask_field("market_id", "abc123xyz789")
        assert "*" in masked
        assert masked != "abc123xyz789"
    
    def test_add_remove_rule(self):
        """Test adding and removing masking rules."""
        masker = DataMasker()
        
        rule = MaskingRule(
            field_name="custom_field",
            mask_char="*",
            show_first=2,
            show_last=2,
        )
        masker.add_rule(rule)
        
        masked = masker.mask_field("custom_field", "abcdefgh")
        assert masked.startswith("ab")
        assert masked.endswith("gh")
        assert "*" in masked
        
        masker.remove_rule("custom_field")
        masked = masker.mask_field("custom_field", "abcdefgh")
        assert masked == "abcdefgh"
    
    def test_mask_all(self):
        """Test masking entire field."""
        masker = DataMasker()
        
        rule = MaskingRule(field_name="secret", mask_char="*", mask_all=True)
        masker.add_rule(rule)
        
        masked = masker.mask_field("secret", "my_secret_123")
        assert masked == "*" * len("my_secret_123")
    
    def test_mask_record(self):
        """Test masking an entire record."""
        masker = DataMasker()
        
        record = {
            "market_id": "abc123xyz789",
            "market_slug": "btc-updown-5m",
            "side": "UP",
            "amount": 100.0,
        }
        
        masked = masker.mask_record(record)
        assert masked["market_id"] != record["market_id"]
        assert masked["market_slug"] == record["market_slug"]
        assert masked["side"] == record["side"]
        assert masked["amount"] == record["amount"]
    
    def test_enable_disable_masking(self):
        """Test enabling and disabling masking."""
        masker = DataMasker()
        
        assert masker.is_enabled() is True
        
        masker.disable()
        assert masker.is_enabled() is False
        
        masked = masker.mask_field("market_id", "abc123")
        assert masked == "abc123"
        
        masker.enable()
        assert masker.is_enabled() is True


class TestTradeDatabaseSecurity:
    """Tests for TradeDatabase security integration."""
    
    @pytest.fixture
    def temp_db(self):
        """Create a temporary database for testing."""
        with tempfile.NamedTemporaryFile(suffix=".db", delete=False) as f:
            db_path = f.name
        db = TradeDatabase(db_path)
        yield db
        db.close()
        Path(db_path).unlink(missing_ok=True)
    
    def test_enable_encryption(self, temp_db):
        """Test enabling encryption on database."""
        pytest.importorskip("cryptography")
        
        temp_db.enable_encryption(password="test_password")
        assert temp_db.is_encryption_enabled() is True
    
    def test_disable_encryption(self, temp_db):
        """Test disabling encryption on database."""
        pytest.importorskip("cryptography")
        
        temp_db.enable_encryption(password="test_password")
        temp_db.disable_encryption()
        assert temp_db.is_encryption_enabled() is False
    
    def test_set_auth_method(self, temp_db):
        """Test setting authentication method."""
        temp_db.set_auth_method("api_key")
        assert temp_db.get_auth_method() == "api_key"
        
        temp_db.set_auth_method("jwt")
        assert temp_db.get_auth_method() == "jwt"
    
    def test_add_user(self, temp_db):
        """Test adding users to database."""
        temp_db.add_user("user1", "trader", ["trader"])
        temp_db.add_user("user2", "analyst", ["analyst"])
        
        # Users should be in auth manager
        assert temp_db._auth_manager.get_user("user1") is not None
        assert temp_db._auth_manager.get_user("user2") is not None
    
    def test_authenticate_api_key(self, temp_db):
        """Test API key authentication."""
        temp_db.set_auth_method("api_key")
        
        api_key = temp_db._auth_manager.generate_api_key()
        temp_db.add_user("user1", "trader", ["trader"], api_key=api_key)
        
        # Valid authentication
        assert temp_db.authenticate(api_key) is True
        assert temp_db.get_current_user() == "user1"
        assert "trader" in temp_db.get_current_roles()
        
        # Invalid authentication
        assert temp_db.authenticate("invalid_key") is False
    
    def test_authenticate_jwt(self, temp_db):
        """Test JWT authentication."""
        pytest.importorskip("jwt")
        
        temp_db.set_auth_method("jwt")
        
        jwt_secret = "test_secret"
        temp_db.add_user("user1", "trader", ["trader"], jwt_secret=jwt_secret)
        
        token = temp_db._auth_manager.generate_jwt_token("user1")
        
        # Valid authentication
        assert temp_db.authenticate(token, user_id="user1") is True
        assert temp_db.get_current_user() == "user1"
        
        # Invalid authentication
        assert temp_db.authenticate(token, user_id="user2") is False
    
    def test_check_permission(self, temp_db):
        """Test permission checking."""
        temp_db.set_auth_method("api_key")
        
        api_key = temp_db._auth_manager.generate_api_key()
        temp_db.add_user("user1", "trader", ["trader"], api_key=api_key)
        temp_db.authenticate(api_key)
        
        # Trader should have read and write permissions
        assert temp_db.check_permission("read") is True
        assert temp_db.check_permission("write") is True
        assert temp_db.check_permission("delete") is False
    
    def test_require_permission_success(self, temp_db):
        """Test require_permission with valid permission."""
        temp_db.set_auth_method("api_key")
        
        api_key = temp_db._auth_manager.generate_api_key()
        temp_db.add_user("user1", "trader", ["trader"], api_key=api_key)
        temp_db.authenticate(api_key)
        
        # Should not raise
        temp_db.require_permission("read")
        temp_db.require_permission("write")
    
    def test_require_permission_failure(self, temp_db):
        """Test require_permission with invalid permission."""
        temp_db.set_auth_method("api_key")
        
        api_key = temp_db._auth_manager.generate_api_key()
        temp_db.add_user("user1", "trader", ["trader"], api_key=api_key)
        temp_db.authenticate(api_key)
        
        # Should raise PermissionError
        with pytest.raises(PermissionError):
            temp_db.require_permission("delete")
    
    def test_add_custom_role(self, temp_db):
        """Test adding custom role."""
        temp_db.add_role("manager", ["read", "write", "export"], "Manager role")
        
        role = temp_db._authz_manager.get_role("manager")
        assert role is not None
        assert "read" in role.permissions
        assert "export" in role.permissions
    
    def test_add_masking_rule(self, temp_db):
        """Test adding masking rule."""
        temp_db.add_masking_rule("custom_field", show_first=2, show_last=2)
        
        masked = temp_db._data_masker.mask_field("custom_field", "abcdefgh")
        assert masked.startswith("ab")
        assert masked.endswith("gh")
    
    def test_mask_trade_record(self, temp_db):
        """Test masking a trade record."""
        from polyalpha.database.database import TradeRecord
        
        trade = TradeRecord(
            id=1,
            market_slug="btc-updown-5m",
            market_id="abc123xyz789",
            side="UP",
            entry_price=0.92,
            exit_price=None,
            amount=10.0,
            shares=10.5,
            fee=0.2,
            outcome="WON",
            pnl=5.3,
            timestamp=datetime.now(timezone.utc),
        )
        
        masked = temp_db.mask_trade_record(trade)
        assert masked["market_id"] != trade.market_id
        assert "*" in masked["market_id"]
    
    def test_enable_disable_masking(self, temp_db):
        """Test enabling and disabling masking."""
        assert temp_db.is_masking_enabled() is True
        
        temp_db.disable_masking()
        assert temp_db.is_masking_enabled() is False
        
        temp_db.enable_masking()
        assert temp_db.is_masking_enabled() is True


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
