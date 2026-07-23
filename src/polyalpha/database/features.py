from __future__ import annotations

import logging
import sqlite3
from typing import Optional, List, Dict, Any, Callable, Set
from threading import Lock

from .models import DBUser, TradeRecord
from .security import (
    DatabaseEncryption,
    AuthenticationManager,
    AuthorizationManager,
    DataMasker,
    AuthMethod,
    Role,
    User,
    MaskingRule,
)

log = logging.getLogger(__name__)


class PreparedStatementManager:
    def __init__(self):
        self._prepared_statements: Dict[str, Any] = {}
        self._statement_cache_max_size = 50
        self._statement_lock = Lock()

    def get_prepared_statement(self, query: str, get_conn_fn) -> Any:
        with self._statement_lock:
            if query in self._prepared_statements:
                return self._prepared_statements[query]
            conn = get_conn_fn()
            stmt = conn.execute(query)
            if len(self._prepared_statements) >= self._statement_cache_max_size:
                self._prepared_statements.pop(next(iter(self._prepared_statements)))
            self._prepared_statements[query] = stmt
            return stmt

    def clear(self) -> None:
        with self._statement_lock:
            self._prepared_statements.clear()

    @property
    def size(self) -> int:
        return len(self._prepared_statements)


class UserManager:
    def __init__(self, conn_manager):
        self._conn = conn_manager

    def create_user(self, username: str, password_hash: str) -> int:
        try:
            with self._conn._connection_ctx() as conn:
                cursor = conn.cursor()
                cursor.execute("""
                    INSERT INTO users (username, password_hash)
                    VALUES (?, ?)
                """, (username, password_hash))
                conn.commit()
                user_id = cursor.lastrowid
                log.info("User created: ID=%d, username=%s", user_id, username)
                return user_id
        except sqlite3.IntegrityError:
            raise ValueError(f"Username '{username}' already exists")

    def get_user(self, user_id: int) -> Optional[DBUser]:
        with self._conn._connection_ctx() as conn:
            cursor = conn.cursor()
            cursor.execute("""
                SELECT id, username, password_hash, created_at, is_active
                FROM users WHERE id = ?
            """, (user_id,))
            row = cursor.fetchone()
            if row:
                return DBUser(
                    id=row["id"], username=row["username"],
                    password_hash=row["password_hash"],
                    created_at=row["created_at"],
                    is_active=bool(row["is_active"]),
                )
            return None

    def get_user_by_username(self, username: str) -> Optional[DBUser]:
        with self._conn._connection_ctx() as conn:
            cursor = conn.cursor()
            cursor.execute("""
                SELECT id, username, password_hash, created_at, is_active
                FROM users WHERE username = ?
            """, (username,))
            row = cursor.fetchone()
            if row:
                return DBUser(
                    id=row["id"], username=row["username"],
                    password_hash=row["password_hash"],
                    created_at=row["created_at"],
                    is_active=bool(row["is_active"]),
                )
            return None

    def get_all_users(self) -> List[DBUser]:
        with self._conn._connection_ctx() as conn:
            cursor = conn.cursor()
            cursor.execute("""
                SELECT id, username, password_hash, created_at, is_active
                FROM users ORDER BY id
            """)
            return [
                DBUser(id=row["id"], username=row["username"],
                       password_hash=row["password_hash"],
                       created_at=row["created_at"],
                       is_active=bool(row["is_active"]))
                for row in cursor.fetchall()
            ]

    def deactivate_user(self, user_id: int) -> bool:
        with self._conn._connection_ctx() as conn:
            cursor = conn.cursor()
            cursor.execute("UPDATE users SET is_active = 0 WHERE id = ?", (user_id,))
            conn.commit()
            return cursor.rowcount > 0

    def delete_user(self, user_id: int, reassign_trades: bool = False) -> bool:
        with self._conn._connection_ctx() as conn:
            cursor = conn.cursor()
            if reassign_trades:
                cursor.execute("UPDATE trades SET user_id = NULL WHERE user_id = ?", (user_id,))
            else:
                cursor.execute("DELETE FROM trades WHERE user_id = ?", (user_id,))
            cursor.execute("DELETE FROM users WHERE id = ?", (user_id,))
            conn.commit()
            return cursor.rowcount > 0


class SecurityManager:
    def __init__(self):
        self._encryption: Optional[DatabaseEncryption] = None
        self._auth_manager = AuthenticationManager()
        self._authz_manager = AuthorizationManager()
        self._data_masker = DataMasker()
        self._current_user_id: Optional[str] = None
        self._current_roles: Set[str] = set()
        self._encryption_fields: List[str] = []

    @property
    def encryption(self) -> Optional[DatabaseEncryption]:
        return self._encryption

    @property
    def encryption_fields(self) -> List[str]:
        return self._encryption_fields

    @property
    def auth_manager(self):
        return self._auth_manager

    @property
    def authz_manager(self):
        return self._authz_manager

    @property
    def data_masker(self):
        return self._data_masker

    @property
    def current_user_id(self) -> Optional[str]:
        return self._current_user_id

    @current_user_id.setter
    def current_user_id(self, value: Optional[str]) -> None:
        self._current_user_id = value

    @property
    def current_roles(self) -> Set[str]:
        return self._current_roles

    @current_roles.setter
    def current_roles(self, value: Set[str]) -> None:
        self._current_roles = value

    def enable_encryption(self, key=None, password=None, fields=None):
        self._encryption = DatabaseEncryption(key=key, password=password)
        self._encryption_fields = fields or ["market_id"]
        log.info("Encryption enabled for fields: %s", self._encryption_fields)

    def disable_encryption(self):
        if self._encryption:
            self._encryption.disable()
        log.info("Encryption disabled")

    def is_encryption_enabled(self) -> bool:
        return self._encryption is not None and self._encryption.is_enabled()

    def set_auth_method(self, method: str) -> None:
        auth_method = AuthMethod(method.lower())
        self._auth_manager.set_method(auth_method)
        log.info("Authentication method set to: %s", method)

    def get_auth_method(self) -> str:
        return self._auth_manager.get_method().value

    def add_user(self, user_id: str, username: str, roles: List[str],
                 api_key=None, jwt_secret=None) -> None:
        if api_key is None and self._auth_manager.get_method() == AuthMethod.API_KEY:
            api_key = self._auth_manager.generate_api_key()
        self._auth_manager.add_user(user_id, username, roles, api_key, jwt_secret)

    def remove_user(self, user_id: str) -> None:
        self._auth_manager.remove_user(user_id)

    def authenticate(self, credential: str, user_id: Optional[str] = None) -> bool:
        method = self._auth_manager.get_method()
        if method == AuthMethod.API_KEY:
            authenticated_user_id = self._auth_manager.validate_api_key(credential)
            if authenticated_user_id:
                self._current_user_id = authenticated_user_id
                user = self._auth_manager.get_user(authenticated_user_id)
                if user:
                    self._current_roles = user.roles
                return True
            return False
        elif method == AuthMethod.JWT:
            if user_id is None:
                raise ValueError("user_id is required for JWT authentication")
            if self._auth_manager.validate_jwt_token(credential, user_id):
                self._current_user_id = user_id
                user = self._auth_manager.get_user(user_id)
                if user:
                    self._current_roles = user.roles
                return True
            return False
        elif method == AuthMethod.NONE:
            return True
        return False

    def get_current_user(self) -> Optional[str]:
        return self._current_user_id

    def get_current_roles(self) -> Set[str]:
        return self._current_roles.copy()

    def add_role(self, name: str, permissions: List[str], description: Optional[str] = None) -> None:
        role = Role(name=name, permissions=set(permissions), description=description)
        self._authz_manager.add_role(role)

    def remove_role(self, role_name: str) -> None:
        self._authz_manager.remove_role(role_name)

    def check_permission(self, permission: str) -> bool:
        if not self._auth_manager.is_enabled():
            return True
        return self._authz_manager.check_permission(self._current_roles, permission)

    def require_permission(self, permission: str) -> None:
        if not self.check_permission(permission):
            raise PermissionError(
                f"User '{self._current_user_id}' with roles {self._current_roles} "
                f"does not have permission '{permission}'"
            )

    def add_masking_rule(self, field_name: str, mask_char: str = "*",
                         show_first: int = 0, show_last: int = 0, mask_all: bool = False) -> None:
        rule = MaskingRule(
            field_name=field_name, mask_char=mask_char,
            show_first=show_first, show_last=show_last, mask_all=mask_all,
        )
        self._data_masker.add_rule(rule)

    def remove_masking_rule(self, field_name: str) -> None:
        self._data_masker.remove_rule(field_name)

    def enable_masking(self) -> None:
        self._data_masker.enable()

    def disable_masking(self) -> None:
        self._data_masker.disable()

    def is_masking_enabled(self) -> bool:
        return self._data_masker.is_enabled()

    def mask_trade_record(self, trade: TradeRecord) -> Dict[str, Any]:
        record_dict = trade.to_dict()
        return self._data_masker.mask_record(record_dict)


class IndexManager:
    def __init__(self, conn_manager):
        self._conn = conn_manager

    def analyze_indexes(self) -> None:
        with self._conn._connection_ctx() as conn:
            cursor = conn.cursor()
            cursor.execute("ANALYZE")
            conn.commit()
            log.info("Database indexes analyzed")

    def optimize_database(self) -> None:
        with self._conn._connection_ctx() as conn:
            cursor = conn.cursor()
            cursor.execute("PRAGMA optimize")
            conn.commit()
            log.info("Database optimized")

    def get_index_info(self) -> Dict[str, Dict[str, Any]]:
        with self._conn._connection_ctx() as conn:
            cursor = conn.cursor()
            cursor.execute("""
                SELECT name, tbl_name, sql
                FROM sqlite_master
                WHERE type='index' AND name NOT LIKE 'sqlite_%'
            """)
            indexes = {}
            for row in cursor.fetchall():
                indexes[row["name"]] = {"table": row["tbl_name"], "sql": row["sql"]}
            return indexes

    def rebuild_index(self, index_name: str) -> None:
        with self._conn._connection_ctx() as conn:
            cursor = conn.cursor()
            valid_indexes = {
                "idx_market_slug": "CREATE INDEX idx_market_slug ON trades(market_slug)",
                "idx_market_id": "CREATE INDEX idx_market_id ON trades(market_id)",
                "idx_side": "CREATE INDEX idx_side ON trades(side)",
                "idx_outcome": "CREATE INDEX idx_outcome ON trades(outcome)",
                "idx_timestamp": "CREATE INDEX idx_timestamp ON trades(timestamp)",
                "idx_duplicate_check": "CREATE INDEX idx_duplicate_check ON trades(market_id, side, timestamp)",
                "idx_market_session": "CREATE INDEX idx_market_session ON trades(market_session)",
                "idx_user_id": "CREATE INDEX idx_user_id ON trades(user_id)",
            }
            if index_name not in valid_indexes:
                raise ValueError(
                    f"Invalid index name '{index_name}'. Valid options: {sorted(valid_indexes.keys())}"
                )
            cursor.execute("SELECT name FROM sqlite_master WHERE type='index' AND name=?", (index_name,))
            if not cursor.fetchone():
                raise ValueError(f"Index '{index_name}' does not exist")
            cursor.execute(f"DROP INDEX IF EXISTS {index_name}")
            cursor.execute(valid_indexes[index_name])
            conn.commit()
            log.info("Index '%s' rebuilt", index_name)
