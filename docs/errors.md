# Errors

Complete reference of all exception classes in the polyalpha SDK, organized by category.

---

## Hierarchy

```
Exception
├── PolyalphaError                          — Base for all SDK errors
│   ├── MarketNotFound                      — Market slug or asset not found
│   ├── MarketClosed                        — Market expired and no longer active
│   ├── StreamDisconnected                  — WebSocket dropped beyond retry budget
│   ├── InsufficientBalance                 — Paper balance too low for order
│   ├── InsufficientAllowance               — CLOB allowance too low
│   ├── OrderNotFound                       — Order ID not found
│   ├── OrderRejected                       — Order rejected by CLOB
│   ├── OrderTimeout                        — Order timed out
│   ├── OrderCancelled                      — Order cancelled by user or system
│   ├── PositionNotFound                    — Position not found
│   ├── OrderBookError                      — Order book fetch/parse failed
│   │   └── OrderBookNotFound               — No book data for token
│   ├── NetworkError                        — Network connectivity failure
│   ├── TransientError                      — Retryable transient failure
│   ├── RiskLimitExceeded                   — Risk management limit exceeded
│   ├── CircuitBreakerOpenError             — Circuit breaker blocking requests
│   ├── ManualInterventionRequiredError     — Requires human recovery
│   ├── TransactionRollbackError            — Rollback failed
│   ├── BackupError                         — Backup/restore operation failed
│   ├── ConfigurationError                  — Invalid configuration
│   ├── AuthenticationError                 — Authentication failed
│   ├── RateLimitExceeded                   — API rate limit hit
│   ├── GasEstimationError                  — Gas estimation failed
│   └── TransactionRebroadcastError         — Transaction rebroadcast failed
│
└── AIError                                 — Base for AI/OpenRouter errors
    ├── AIAuthenticationError               — Invalid or missing API key
    ├── AIModelNotFoundError                — Requested model unavailable
    ├── AIQuotaExceededError                — Rate limit or quota exceeded
    ├── AIResponseError                     — Malformed or invalid response
    ├── AITimeoutError                      — Request timed out
    └── AIConnectionError                   — Connection to OpenRouter failed
```

---

## Core Errors (`polyalpha` / `polyalpha.core.errors`)

All inherit from `PolyalphaError(Exception)`.

### Market Errors

**`MarketNotFound`**
Raised when no market matches the given slug, asset, or timeframe.

```python
from polyalpha import MarketNotFound

try:
    market = client.markets.latest("BTC", "5m")
except MarketNotFound:
    print("No active BTC 5m market right now")
```

**`MarketClosed`**
Raised when a market exists but is no longer active (expired).

### Streaming Errors

**`StreamDisconnected`**
Raised when the WebSocket connection drops and cannot be re-established within the retry budget.

```python
from polyalpha import StreamDisconnected
```

### Trading Errors

**`InsufficientBalance`**
Raised when paper balance is too low to place an order.

**`InsufficientAllowance`**
Raised when the CLOB allowance is insufficient for a trade.

**`OrderNotFound`**
Raised when no order matches the given ID.

**`OrderRejected`**
Raised when the CLOB rejects an order.

**`OrderTimeout`**
Raised when an order times out.

**`OrderCancelled`**
Raised when an order is cancelled (by user or system).

**`PositionNotFound`**
Raised when no position matches the given criteria.

### Order Book Errors

**`OrderBookError`**
Raised when an order book fetch or parse fails.

**`OrderBookNotFound(OrderBookError)`**
Raised when no order book data is available for the requested token.

```python
from polyalpha import OrderBookError, OrderBookNotFound

try:
    book = client.orderbook(market).refresh()
except OrderBookNotFound:
    print("No book data available yet")
except OrderBookError:
    print("Failed to fetch order book")
```

### Network & Transient Errors

**`NetworkError`**
Raised on network connectivity failures.

**`TransientError`**
Raised for retryable transient errors.

**`RateLimitExceeded`**
Raised when API rate limits are exceeded.

### Risk Errors

**`RiskLimitExceeded`**
Raised when a risk management limit is exceeded (position size, daily loss, etc.).

### Circuit Breaker

**`CircuitBreakerOpenError`**
Raised when the circuit breaker is open and blocking requests.

### Transaction Errors

**`TransactionRollbackError`**
Raised when a transaction rollback operation fails.

**`TransactionRebroadcastError`**
Raised when re-broadcasting a transaction fails.

**`GasEstimationError`**
Raised when gas estimation for a transaction fails.

### Backup Errors

**`BackupError`**
Raised when a backup or restore operation fails.

### Configuration Errors

**`ConfigurationError`**
Raised when invalid configuration is provided.

### Authentication Errors

**`AuthenticationError`**
Raised when authentication fails.

### Manual Intervention

**`ManualInterventionRequiredError`**
Raised when human intervention is required to recover from an error.

---

## AI Errors (`polyalpha.ai`)

All inherit from `AIError(Exception)`.

| Error | Description |
|-------|-------------|
| `AIError` | Base for all AI-related errors |
| `AIAuthenticationError` | API key is invalid or missing |
| `AIModelNotFoundError` | Requested model is not available |
| `AIQuotaExceededError` | Rate limit or quota exceeded for OpenRouter |
| `AIResponseError` | Response is malformed or invalid |
| `AITimeoutError` | Request to OpenRouter timed out |
| `AIConnectionError` | Connection to OpenRouter failed |

```python
from polyalpha import AIError, AIQuotaExceededError

try:
    analysis = client.ai.analyze_market(market)
except AIQuotaExceededError:
    print("OpenRouter quota exceeded — try again later")
except AIError as e:
    print(f"AI request failed: {e}")
```

---

## Quick Reference

| Category | Errors |
|----------|--------|
| Market | `MarketNotFound`, `MarketClosed` |
| Stream | `StreamDisconnected` |
| Trading | `InsufficientBalance`, `InsufficientAllowance`, `OrderNotFound`, `OrderRejected`, `OrderTimeout`, `OrderCancelled`, `PositionNotFound` |
| Order Book | `OrderBookError`, `OrderBookNotFound` |
| Network | `NetworkError`, `TransientError`, `RateLimitExceeded` |
| Risk | `RiskLimitExceeded` |
| Circuit Breaker | `CircuitBreakerOpenError` |
| Transaction | `TransactionRollbackError`, `TransactionRebroadcastError`, `GasEstimationError` |
| Backup | `BackupError` |
| Config | `ConfigurationError` |
| Auth | `AuthenticationError` |
| Manual | `ManualInterventionRequiredError` |
| AI | `AIError`, `AIAuthenticationError`, `AIModelNotFoundError`, `AIQuotaExceededError`, `AIResponseError`, `AITimeoutError`, `AIConnectionError` |
