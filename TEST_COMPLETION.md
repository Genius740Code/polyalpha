# Test Completion Plan

**1357 tests pass** — 0 failures, 0 errors. 68 network tests skipped (needs API keys).

## Coverage: 60% (7,476 / 12,389 stmts) — report/ module at 91% ✅

### Priority 1 — Zero-coverage modules (write first tests) ✅ DONE

| Module | Lines | Coverage | Effort |
|---|---|---|---|
| `report/portfolio_analytics.py` | 193 | 100% | Medium ✅ |
| `report/real_reports.py` | 73 | 99% | Small ✅ |
| `report/reporting.py` | 293 | 99% | Medium ✅ |

### Priority 2 — Low coverage (<40%)

| Module | Coverage | Lines | Notes |
|---|---|---|---|
| `trading/real.py` | 26% | 1531 | Real trading — needs mocking CLOB API |
| `trading/alchemy_client.py` | 23% | 57 | Small, easy to mock |
| `wallet/transaction_signer.py` | 22% | 216 | On-chain signing — mock web3 |
| `trading/error_handling.py` | 32% | 433 | Error paths, high-value to cover |
| `wallet/hardware_wallet.py` | 38% | 235 | Hardware interaction, mock HID |
| `wallet/wallet_manager.py` | 43% | 197 | |

### Priority 3 — Medium coverage (50-75%)

| Module | Coverage | Lines |
|---|---|---|
| `trading/clob_client.py` | 49% | 156 |
| `wallet/multisig_wallet.py` | 51% | 201 |
| `report/html_template.py` | 56% | 160 |
| `report/engine.py` | 64% | 91 |
| `wallet/audit_logger.py` | 64% | 166 |
| `wallet/wallet_security.py` | 64% | 228 |
| `stream.py` | 72% | 265 |
| `orderbook/strategy.py` | 72% | 117 |
| `utils/logging_utils.py` | 75% | 53 |
| `orderbook/risk.py` | 76% | 33 |
| `trading/paper.py` | 77% | 1156 |
| `trading/auto_redeem.py` | 71% | 228 |

## Goal

- **80%+ coverage** = `report/` + `trading/real.py` + `wallet/*`
- **90%+ coverage** = add error-path tests for all `trading/` and `wallet/` modules
