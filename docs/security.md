# Security

Best practices for API key management, private key handling, environment variable hygiene, encryption, and audit logging.

---

## API Key Management

### Never commit secrets

All credential files are in `.gitignore`:
- `.env`, `.env.local`, `.env.*.local`, `secrets.env`
- `*.pem`, `*.key`, `private_key.txt`
- `*.db`, `*.sqlite`, `*.sqlite3`

### Environment variables

All sensitive configuration is read from environment variables with the `POLYALPHA_` prefix:

| Variable | Sensitivity | Description |
|----------|-------------|-------------|
| `POLYALPHA_PRIVATE_KEY` | **CRITICAL** | Wallet private key |
| `POLYALPHA_POLYMARKET_API_KEY` | **HIGH** | CLOB API key |
| `POLYALPHA_POLYMARKET_API_SECRET` | **HIGH** | CLOB API secret |
| `POLYALPHA_POLYMARKET_API_PASSPHRASE` | **HIGH** | CLOB API passphrase |
| `POLYALPHA_OPENROUTER_API_KEY` | **HIGH** | OpenRouter AI API key |
| `POLYALPHA_RPC_URL` | LOW | Polygon RPC endpoint |

```bash
# Recommended: set via export or .env (already in .gitignore)
export POLYALPHA_PRIVATE_KEY="0x..."
export POLYALPHA_POLYMARKET_API_KEY="..."
```

### Loading from `.env`

```python
from polyalpha import load_env_file

load_env_file()  # Loads .env from CWD or parent dirs
```

**Warning:** `load_env_file()` uses `override=True` — if a `.env` file exists, it will override existing shell environment variables. Be careful in shared environments.

---

## Private Key Handling

### Best practices

```python
# BAD: hardcoding keys
client = Client(private_key="0xabc123def...")

# GOOD: environment variables
import os
client = Client(private_key=os.environ["POLYALPHA_PRIVATE_KEY"])

# BEST: encrypted wallet storage
from polyalpha.wallet import WalletManager

wm = WalletManager(storage_type="keyring")  # Uses system keyring
wm.add_software_wallet(address, private_key, password="strong-password")
```

### Encrypted Storage (WalletSecurity)

The `polyalpha.wallet` module provides encrypted key storage:

```python
from polyalpha.wallet import WalletSecurity, WalletStorageType

# FILE storage with encryption (PBKDF2 + Fernet)
ws = WalletSecurity(storage_type="file")
ws.add_wallet("0x...", private_key, password="strong-password")

# KEYRING storage (uses system keychain)
ws = WalletSecurity(storage_type="keyring")
```

Key derivation: PBKDF2-HMAC-SHA256, 600,000 iterations (OWASP 2023 recommendation), with random salt.

Export to an encrypted backup file:

```python
ws.export_wallet("0x...", Path("backup.enc"), password="strong-password")
```

### Password Rotation

```python
# Change wallet encryption password
wm.rotate_password("0x...", old_password="old", new_password="new")
```

---

## Env Var Hygiene

### What `get_env_config()` returns

```python
from polyalpha import get_env_config

config = get_env_config()
# Returns dict with ALL POLYALPHA_* vars, including secrets:
# { "private_key": "0x...", "polymarket_api_key": "...", ... }
```

Treat the result of `get_env_config()` as sensitive. Do not log it, print it, or pass it to untrusted code.

### Client construction

```python
# Explicit parameters (recommended for production)
client = Client(
    private_key=os.environ["POLYALPHA_PRIVATE_KEY"],
    openrouter_api_key=os.environ["POLYALPHA_OPENROUTER_API_KEY"],
)

# All from env (development convenience)
client = Client(
    private_key=os.environ["POLYALPHA_PRIVATE_KEY"],
    rpc_url=os.environ.get("POLYALPHA_RPC_URL"),
    polymarket_api_key=os.environ.get("POLYALPHA_POLYMARKET_API_KEY"),
)
```

---

## Logging Security

The SDK includes automatic redaction of sensitive data in logs via `SensitiveDataFilter`.

### What gets redacted

| Pattern | Example | Redacted |
|---------|---------|----------|
| Ethereum address | `0xabc123...def456` | `0xabc123...def456` (first 6, last 4 visible) |
| Transaction hash | `0x` + 64 hex chars | First 10 + `...` + last 4 |
| Private key | 64+ hex chars | First 8 + `...REDACTED` |
| API keys | `api_key=sk-...` | `api_key=***REDACTED***` |
| Passwords | `password=...` | `password=***REDACTED***` |
| Bearer tokens | `Bearer eyJ...` | `Bearer ***REDACTED***` |
| Secrets | `secret=...` | `secret=***REDACTED***` |

### Log format

```python
import os

# Text format (default)
os.environ["POLYALPHA_LOG_FORMAT"] = "text"

# JSON format for machine parsing
os.environ["POLYALPHA_LOG_FORMAT"] = "json"

# Enable file logging with rotation (10 MB max, 3 backups)
os.environ["POLYALPHA_LOG_FILE"] = "polyalpha.log"
```

### Manual masking

```python
from polyalpha.utils.logging_utils import (
    mask_address,
    mask_transaction_hash,
    mask_private_key,
)

print(mask_address("0xabc123..."))        # 0xabc123...
print(mask_transaction_hash("0xabc..."))  # 0xabc7890...5678
print(mask_private_key(key))               # abcdef12...REDACTED
```

**Note:** Redaction only applies to logs sent through `logging.getLogger()`. Direct `print()` or `repr()` of objects containing secrets will bypass redaction.

---

## Database Security

### Encryption at rest

```python
from polyalpha.database import TradeDatabase

db = TradeDatabase("trades.db")

# Enable field-level encryption
db.enable_encryption(password="strong-password")

# Or use a derived key
import os
key = os.urandom(32)
db.enable_encryption(key=key, fields=["market_id", "pnl"])
```

### Authentication

```python
from polyalpha.database.security import AuthMethod

# API key authentication
db.set_auth_method("api_key")
db.add_user(
    user_id="user1",
    username="trader1",
    roles=["trader"],
)

# JWT authentication
db.set_auth_method("jwt")
token = db.authenticate("api_key_value")
```

### Authorization (RBAC)

Default roles:

| Role | Permissions |
|------|-------------|
| `admin` | read, write, delete, export, import, backup, restore, manage_users, manage_roles |
| `trader` | read, write, export |
| `analyst` | read, export |
| `viewer` | read |

```python
from polyalpha.database import Role

# Check permissions before operations
db.require_permission("export")
trades = db.export_csv("backup.csv")

# Custom roles
db.add_role("compliance_officer", permissions=["read", "audit"])
```

### Data masking

```python
from polyalpha.database import DataMasker

masker = DataMasker()
masked = masker.mask_record({
    "api_key": "sk-abc123",
    "market_id": "0xdeadbeef",
})
# {"api_key": "***", "market_id": "0xde...beef"}
```

---

## Wallet Security

### Audit logging

All wallet operations are logged with 17 event types:

```python
from polyalpha.wallet import AuditLogger, AuditEventType

logger = AuditLogger()

logger.log_event(
    event_type=AuditEventType.TRANSACTION_SIGNED,
    wallet_address="0x...",
    details={"tx_type": "buy", "amount": 100.0},
)

# Query wallet history
events = logger.get_wallet_history("0x...")

# Get security events
security_events = logger.get_security_events()
```

### Transaction signing

```python
from polyalpha.wallet import TransactionSigner

signer = TransactionSigner(
    signing_method="private_key",
    private_key=os.environ["POLYALPHA_PRIVATE_KEY"],
    rpc_url="https://polygon-rpc.com",
)

# Validates address, value, gas before signing
# Warns on missing chainId (replay attack protection)
result = signer.sign_transaction(tx_dict)
```

### Multi-sig wallets

```python
from polyalpha.wallet import MultiSigWallet, MultiSigSigner, MultiSigWalletFactory

# 2-of-3 multi-sig
wallet = MultiSigWalletFactory.create_2of3(
    wallet_address="0x...",
    signer_addresses=["0xA", "0xB", "0xC"],
)

# Propose and approve transactions
tx = wallet.propose_transaction(tx_dict, proposer="0xA")
wallet.sign_transaction(tx.tx_id, "0xB", signature)
wallet.sign_transaction(tx.tx_id, "0xC", signature)
# Auto-approved when threshold met
```

---

## Additional Protections

### Circuit breakers

The SDK includes circuit breakers that prevent cascading failures:

- **CLOB API circuit breaker**: Opens after consecutive failures, blocks requests, auto-recovers after timeout
- **Wallet RPC circuit breaker**: Prevents repeated transactions to a failing RPC endpoint

### Prompt injection detection

The AI client (`OpenRouterClient`) detects and blocks common prompt injection patterns before sending to OpenRouter.

### Correlation IDs

Every `Client` instance generates a correlation ID (`cid`) that is attached to all log entries, enabling tracing of operations across components:

```python
from polyalpha.utils.logging_utils import new_correlation_id

cid = new_correlation_id()
# All subsequent logs in this context include [cid=...]
```

### Secure defaults

- HTTP requests time out after 10 seconds (configurable)
- 3 retries on 5xx errors (configurable)
- Logging defaults to WARNING level (verbose only when debugging)
- Rate limiting available for API requests
- Private keys never appear in logs (redacted by `SensitiveDataFilter`)
- Safe `__repr__` on all classes holding credentials
