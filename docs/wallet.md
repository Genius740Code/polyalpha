# Wallet

The `polyalpha.wallet` module provides secure wallet management, encrypted key storage, multi-signature transaction support, transaction signing, and security audit logging for Polymarket real trading.

---

## Module Overview

| File | Purpose |
|------|---------|
| `wallet_manager.py` | `WalletManager` — unified interface for all wallet types |
| `wallet_security.py` | `WalletSecurity` — encrypted key storage and access control |
| `multisig_wallet.py` | `MultiSigWallet` — multi-signature transaction management |
| `transaction_signer.py` | `TransactionSigner` — sign and broadcast transactions |
| `audit_logger.py` | `AuditLogger` — 17 event types, queryable audit trail |

All public symbols accessible via `polyalpha.wallet`.

---

## WalletManager

Unified entry point for managing software and multi-sig wallets.

```python
from polyalpha.wallet import WalletManager

wm = WalletManager(storage_type="keyring")
```

### Constructor

| Param | Type | Default | Description |
|-------|------|---------|-------------|
| `storage_type` | `WalletStorageType` | `KEYRING` | `FILE`, `KEYRING`, `ENV`, or `MEMORY` |
| `storage_path` | `Path \| None` | `None` | Path for FILE storage (default: `~/.polyalpha/wallets`) |
| `rpc_url` | `str \| None` | `None` | RPC URL for transaction signing |

### Methods

| Method | Description |
|--------|-------------|
| `add_software_wallet(address, private_key, password, name=None, set_as_default=False, metadata=None)` | Add a software wallet (encrypted key storage) |
| `add_multisig_wallet(address, signers, required_weight, name=None, set_as_default=False)` | Add a multi-sig wallet |
| `get_private_key(address, password=None) -> str` | Get decrypted private key |
| `sign_transaction(transaction_dict, address=None, password=None) -> SigningResult` | Convenience: sign a transaction |
| `remove_wallet(address)` | Remove a wallet |
| `list_wallets() -> list[dict]` | List all wallets (address, type, name, default) |
| `get_wallet_info(address) -> dict \| None` | Get detailed wallet info |
| `set_default_wallet(address)` | Set default wallet |
| `get_default_wallet() -> str \| None` | Get default wallet address |
| `export_wallet(address, export_path, password)` | Export encrypted wallet backup |
| `import_wallet(import_path, password, set_as_default=False) -> str` | Import wallet from backup |
| `rotate_password(address, old_password, new_password)` | Change wallet encryption password |
| `shutdown()` | Clean up resources |

---

## WalletSecurity

Encrypted key storage with PBKDF2 key derivation (600,000 iterations, SHA-256) and Fernet symmetric encryption.

```python
from polyalpha.wallet import WalletSecurity

ws = WalletSecurity(storage_type="file", storage_path=Path("~/.polyalpha/wallets"))
```

### Constructor

| Param | Type | Default | Description |
|-------|------|---------|-------------|
| `storage_type` | `WalletStorageType` | `KEYRING` | Storage backend |
| `storage_path` | `Path \| None` | `None` | Path for FILE mode |
| `encryption_key` | `bytes \| None` | `None` | Additional encryption layer |

### Methods

| Method | Description |
|--------|-------------|
| `add_wallet(address, private_key, password, metadata=None)` | Store encrypted wallet |
| `get_private_key(address, password) -> str` | Decrypt and return private key |
| `remove_wallet(address)` | Remove wallet |
| `list_wallets() -> list[str]` | List stored wallet addresses |
| `rotate_key(address, old_password, new_password)` | Re-encrypt with new password |
| `export_wallet(address, password, export_path)` | Export doubly-encrypted backup |
| `import_wallet(import_path, password) -> str` | Import from backup |

### Storage Types

| Type | Backend | Requires |
|------|---------|----------|
| `FILE` | JSON files at `storage_path` | `cryptography` |
| `KEYRING` | System keyring | `cryptography` + `keyring` |
| `ENV` | Environment variables | `cryptography` |
| `MEMORY` | In-memory only | `cryptography` |

---

## MultiSigWallet

Multi-signature transaction management.

```python
from polyalpha.wallet import MultiSigWallet, MultiSigSigner

signers = [
    MultiSigSigner(address="0x...", weight=1),
    MultiSigSigner(address="0x...", weight=1),
    MultiSigSigner(address="0x...", weight=1),
]
wallet = MultiSigWallet(wallet_address="0x...", signers=signers, required_weight=2)
```

Requires: `eth_account`

### Dataclasses

**`MultiSigSigner`**
| Field | Type | Default |
|-------|------|---------|
| `address` | `str` | required |
| `weight` | `int` | `1` |
| `is_active` | `bool` | `True` |
| `name` | `str \| None` | `None` |

**`MultiSigTransaction`**
| Field | Type |
|-------|------|
| `tx_id` | `str` |
| `transaction_dict` | `dict` |
| `proposer` | `str` |
| `created_at` | `datetime` |
| `status` | `MultiSigStatus` |
| `signatures` | `dict[str, str]` |
| `required_weight` | `int` |
| `current_weight` | `int` |
| `executed_at` | `datetime \| None` |
| `execution_tx_hash` | `str \| None` |

### Methods

| Method | Description |
|--------|-------------|
| `add_signer(signer)` / `remove_signer(address)` | Manage signers |
| `get_signers() -> list[MultiSigSigner]` | List all signers |
| `get_active_signers() -> list[MultiSigSigner]` | List active signers |
| `propose_transaction(tx_dict, proposer, metadata=None) -> MultiSigTransaction` | Propose new transaction |
| `sign_transaction(tx_id, signer_address, signature) -> MultiSigTransaction` | Sign a transaction |
| `get_transaction(tx_id) -> MultiSigTransaction \| None` | Get by ID |
| `get_pending_transactions() -> list[MultiSigTransaction]` | Pending transactions |
| `get_approved_transactions() -> list[MultiSigTransaction]` | Approved transactions |
| `execute_transaction(tx_id, execution_tx_hash) -> MultiSigTransaction` | Mark as executed |
| `cancel_transaction(tx_id, canceller) -> MultiSigTransaction` | Cancel (proposer only) |
| `reject_transaction(tx_id, rejecter) -> MultiSigTransaction` | Reject transaction |
| `update_required_weight(new_weight)` | Change required weight |

### Statuses

`PENDING` → `APPROVED` (auto when weight ≥ threshold) → `EXECUTED`
`PENDING` → `REJECTED` / `CANCELLED`

### Factory Methods

`MultiSigWalletFactory.create_2of3(address, signer_addresses)` — 3 signers, requires 2
`MultiSigWalletFactory.create_3of5(address, signer_addresses)` — 5 signers, requires 3
`MultiSigWalletFactory.create_custom(address, signers, required_weight)` — custom config

---

## TransactionSigner

Sign and broadcast Ethereum transactions.

```python
from polyalpha.wallet import TransactionSigner

signer = TransactionSigner(
    signing_method="private_key",
    private_key="0x...",
    rpc_url="https://polygon-rpc.com"
)
```

### Constructor

| Param | Type | Default | Description |
|-------|------|---------|-------------|
| `signing_method` | `SigningMethod` | `PRIVATE_KEY` | `PRIVATE_KEY`, `MULTISIG`, or `KEYRING` |
| `private_key` | `str \| None` | `None` | Required for PRIVATE_KEY method |
| `multisig_wallet` | `MultiSigWallet \| None` | `None` | Required for MULTISIG method |
| `rpc_url` | `str \| None` | `None` | RPC URL for gas/nonce/broadcast |

### Methods

| Method | Description |
|--------|-------------|
| `sign_transaction(transaction_dict, validate=True, estimate_gas=True) -> SigningResult` | Sign a transaction |
| `sign_message(message, address=None) -> SigningResult` | Sign arbitrary message |
| `broadcast_transaction(signed_transaction) -> str \| None` | Send raw transaction, return tx hash |
| `wait_for_confirmation(tx_hash, timeout=120, poll_interval=1.0) -> dict \| None` | Wait for receipt |
| `clear_nonce_cache(address=None)` | Clear nonce cache |

### `SigningResult`

| Field | Type |
|-------|------|
| `success` | `bool` |
| `signed_transaction` | `dict \| None` |
| `signature` | `str \| None` |
| `error_message` | `str \| None` |
| `gas_estimate` | `int \| None` |
| `gas_price` | `int \| None` |
| `signed_at` | `datetime` |

Requires: `web3`, `eth_account`

---

## AuditLogger

Security event logging with queryable event store.

```python
from polyalpha.wallet import AuditLogger

logger = AuditLogger(log_path=Path("~/.polyalpha/audit.log"), max_events=10000)
```

### Event Types (17)

| Event | Description |
|-------|-------------|
| `WALLET_CREATED` | Wallet creation |
| `WALLET_ACCESSED` | Wallet access attempt |
| `WALLET_REMOVED` | Wallet deletion |
| `WALLET_EXPORTED` | Wallet export |
| `WALLET_IMPORTED` | Wallet import |
| `KEY_ROTATED` | Encryption key rotation |
| `TRANSACTION_SIGNED` | Transaction signed |
| `TRANSACTION_BROADCAST` | Transaction broadcast |
| `HARDWARE_CONNECTED` | Hardware wallet connected |
| `HARDWARE_DISCONNECTED` | Hardware wallet disconnected |
| `MULTISIG_PROPOSED` | Multi-sig transaction proposed |
| `MULTISIG_SIGNED` | Multi-sig transaction signed |
| `MULTISIG_EXECUTED` | Multi-sig transaction executed |
| `PERMISSION_GRANTED` | Permission granted |
| `PERMISSION_REVOKED` | Permission revoked |
| `CONFIG_CHANGED` | Configuration changed |
| `SECURITY_EVENT` | Generic security event |

### Methods

| Method | Description |
|--------|-------------|
| `log_event(event_type, wallet_address=None, actor=None, ip_address=None, details=None, success=True, error_message=None)` | Log an event |
| `query_events(event_type=None, wallet_address=None, actor=None, start_time=None, end_time=None, success=None, limit=100) -> list[AuditEvent]` | Query by up to 6 criteria |
| `get_wallet_history(address, limit=100) -> list[AuditEvent]` | Shorthand for wallet history |
| `get_failed_events(limit=100) -> list[AuditEvent]` | Failed events only |
| `get_security_events(limit=100) -> list[AuditEvent]` | Security events only |
| `export_events(export_path, start_time=None, end_time=None)` | Export as JSON |
| `clear_old_events(days_to_keep=90) -> int` | Purge old events |
| `get_statistics() -> dict` | Event stats (counts, success rate, unique wallets) |

### Global Singleton

```python
from polyalpha.wallet import get_audit_logger

logger = get_audit_logger()  # Lazy-init singleton
```

---

## Quick Reference

```
polyalpha.wallet
├── WalletManager — add/get/list/remove/sign wallets
├── WalletSecurity — PBKDF2 + Fernet encrypted storage
├── MultiSigWallet — 2-of-3, 3-of-5, custom multi-sig
├── TransactionSigner — sign, broadcast, confirm
├── AuditLogger — 17 event types, queryable, exportable
│   └── get_audit_logger() — global singleton
├── WalletStorageType — FILE / KEYRING / ENV / MEMORY
└── SigningMethod — PRIVATE_KEY / MULTISIG / KEYRING
```
