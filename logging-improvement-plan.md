# Logging Improvement Plan

## Current State

- 78+ source files with logging
- Python `logging` module with custom `SensitiveDataFormatter` globally applied
- One `StreamHandler` to stdout — no file persistence
- Three subsystems: main logging, database `LogEntry` (in-memory ring buffer), `AuditLogger` (JSON file)
- `print()` still used in 6+ files
- `POLYALPHA_LOG_LEVEL` env var (default: WARNING, overridden to INFO in `__init__.py`)

---

## Phase 1: Plug Sensitive Data Leaks (HIGH)

| # | Issue | File:Line | Fix |
|---|-------|-----------|-----|
| 1 | Full API response body logged on 400 errors | `trading/clob_client.py:418` | Truncate/sanitize body; log only specific error fields |
| 2 | Wallet address unredacted in `remove_wallet` | `wallet/wallet_security.py:302` | Wrap with `mask_address()` |
| 3 | Audit console uses manual `[:8]` truncation instead of `mask_address()` | `wallet/audit_logger.py:177-188` | Replace with `mask_address()` |
| 4 | "Signed transaction with private key" in log message | `wallet/transaction_signer.py:349` | Reword to "Signed transaction (nonce: %s)" |
| 5 | Position keys logged unfiltered | `trading/wallet.py:112,130` | Mask or genericize position keys |
| 6 | f-string logging with position keys | `trading/auto_redeem.py:262,270` | Convert to `%s`-style; mask keys |
| 7 | Database cache keys in plain text | `database/database.py:1736,1874` | Truncate cache keys |
| 8 | S3 bucket/key in plain text | `database/database.py:2398` | Mask key portion |
| 9 | "Rotated password" terminology | `wallet/wallet_manager.py:507` | Reword to "Rotated credentials for wallet" |
| 10 | AI client stores `api_key` with no `__repr__` safety | `ai/client.py:60` | Add `__repr__` that masks key |

---

## Phase 2: Fix Structural Logging Issues (MEDIUM)

| # | Issue | Action |
|---|-------|--------|
| 11 | `print()` used instead of logging in 6+ files | Convert to `logging.info()` / `logging.debug()` |
| 12 | Root logger config overrides third-party loggers | Use named logger `polyalpha` instead of `getLogger()` |
| 13 | No file persistence — logs lost on restart | Add optional `RotatingFileHandler` via `POLYALPHA_LOG_FILE` |
| 14 | No timestamp/module/process in format | Add structured format: `[%(asctime)s] %(levelname)-8s %(name)s %(message)s` |
| 15 | Non-string log args bypass redaction | Extend filter to convert all args to string before matching |
| 16 | All levels go to stdout | Route WARNING+ to stderr, INFO+ to stdout |
| 17 | Verbose log flags inconsistently checked | Audit `log_all_orders`, `log_trades`, `log_prices`, `log_balance_updates` flag usage |

---

## Phase 3: Add Missing Logging Capabilities (MEDIUM)

| # | Capability | How |
|---|-----------|-----|
| 18 | Lifecycle logging | Add log calls to `Client.__init__` / `Client.close` |
| 19 | Correlation ID tracing | Extend existing DB correlation ID to propagate across modules via context |
| 20 | Performance warnings | Log warning on slow ops (>1s), high retries, stale data |
| 21 | Fallback logging | Log when degraded paths activate (e.g., missing key → paper mode) |
| 22 | DB operation timing | Extend existing `LogEntry.duration_ms` pattern to main logging |
| 23 | JSON structured log option | Support `POLYALPHA_LOG_FORMAT=json` for machine-parseable output |

---

## Phase 4: Clean Up Log Hygiene (LOW) — DONE

| # | Issue | Fix |
|---|-------|-----|
| 24 | Inconsistent level usage — debug details at INFO | Audit all modules; downgrade verbose ops to DEBUG |
| 25 | Redundant "success" lines | Remove or demote hot-path logs (price ticks, orderbook snapshots, balance polls) |
| 26 | Wallet module overuses INFO | Keep only non-obvious events at INFO; downgrade routine ops |
| 27 | `re.IGNORECASE` redundant on `[a-fA-F]` patterns | Clean up flags |
| 28 | Private key regex false-positives on long hashes | Add heuristic to distinguish keys from content hashes |

---

## Phase 5: Documentation & Configuration (LOW) — DONE

| # | Item | Action |
|---|------|--------|
| 29 | Logging section in README | Document `POLYALPHA_LOG_LEVEL`, `POLYALPHA_LOG_FILE`, `POLYALPHA_LOG_FORMAT` |
| 30 | Privacy notice | Document what data is captured and what is masked |
| 31 | `logging.config.dictConfig` | Replace manual `__init__.py` handler setup with dict-based config |

---

## Files to Modify

- `src/polyalpha/utils/logging_utils.py` — extend filter, add JSON formatter, fix regex
- `src/polyalpha/__init__.py` — restructure logging bootstrap
- `src/polyalpha/core/env.py` — add `LOG_FILE`, `LOG_FORMAT` env vars
- `.env.example` — document new vars
- `trading/clob_client.py`, `wallet/wallet_security.py`, `wallet/audit_logger.py`, `wallet/transaction_signer.py`, `wallet/wallet_manager.py`, `trading/wallet.py`, `trading/auto_redeem.py`, `database/database.py`, `ai/client.py` — Phase 1 fixes
- `trading/paper.py`, `trading/real.py`, `trading/paper_config.py`, `trading/real_config.py`, `report/reporting.py` — print() cleanup
- Remaining ~60 files — log level audit (Phase 4)

## Things NOT Touched

- Database `LogEntry` / `LogBuffer` structured logging — already correct
- `wallet/audit_logger.py` JSON file audit trail — already correct
