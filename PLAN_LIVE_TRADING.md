# Live Trading Completion Plan

## Status Overview

Paper trading is **complete**.  
Live trading via `RealTradingEngine` now has a functional CLOB execution layer.

## Completed Work (as of Jul 2026)

### P0 — Core Execution ✅

- [x] **Complete `ClobClient`** (`src/polyalpha/trading/clob_client.py`)
  - Switched from `requests` to `httpx.Client` with base URL, timeout, retry
  - Replaced `_simulate_response()` with real CLOB API calls (simulate mode preserved for tests)
  - Implemented EIP-712 typed data signing for order payloads (Order struct: salt, maker, signer, taker, tokenId, maker/takerAmount, side, signatureType)
  - Implemented **L2 HMAC-SHA256** authentication (official Polymarket spec):
    - `POLY_ADDRESS` — wallet address derived from private key
    - `POLY_SIGNATURE` — `HMAC-SHA256(timestamp + method + path + body)` signed with `api_secret`
    - `POLY_TIMESTAMP` — current UNIX timestamp
    - `POLY_API_KEY` — API key from settings
    - `POLY_PASSPHRASE` — API passphrase from settings
  - Added `derive_api_credentials()` — L1 EIP-712 wallet auth → `POST /auth/derive-api-key` to obtain L2 creds
  - Real endpoints:
    - `POST /order` — place EIP-712 signed order
    - `DELETE /order/{id}` — cancel order
    - `GET /order/{id}` — get order status
    - `GET /orderbook?token_id=` — get orderbook
    - `GET /balance/allowance` — get balance & CLOB allowance
  - Retry with exponential backoff (3 attempts), error mapping (`NetworkError`, `OrderRejected`, `RateLimitExceeded`, `OrderTimeout`)
  - Added `api_secret`/`api_passphrase` optional params to constructor
- [x] **Validate credentials & env vars** (`src/polyalpha/core/env.py`, `.env.example`)
  - `_validate_credentials()` checks for placeholder patterns, minimum length, valid URL format
  - Added `POLYALPHA_POLYMARKET_API_SECRET` and `POLYALPHA_POLYMARKET_API_PASSPHRASE` env vars
  - All vars documented in `.env.example`
- [x] **Wired `RealTradingEngine`** (`src/polyalpha/trading/real.py`)
  - `sell()` method — inverts side, delegates to `buy()`
  - `token_id` added to `IcebergOrder`, `TWAPOrder`, `BracketOrder`, `ConditionalOrder` dataclasses
  - L2 credentials passed through constructor → `ClobClient`
  - `RealTradingConfig` includes `polymarket_api_secret`, `polymarket_api_passphrase`

### P1 — Advanced Order Execution ✅

- [x] **`_execute_iceberg_slice()`** — calls `clob_client.place_order()` with token_id/price/size, tracks child order IDs
- [x] **`_execute_twap_slice()`** — calls `clob_client.place_order()` with limit or market order per slice
- [x] **`activate_bracket_orders()`** — places stop-loss and take-profit orders via `clob_client.place_order()`
- [x] **`check_conditional_triggers()`** — places child order via `clob_client.place_order()` when price condition triggers
- [x] **`execute_trailing_stop_exit()`** — places market sell order via `clob_client.place_order()`, tracks result
- [x] **`cancel()`** — delegates to `clob_client.cancel_order()` (was already wired via `cancel_order`)

### P2 — Post-Trade & Recovery ✅

- [x] **Auto-redeem for real trading** (`auto_redeem.py`)
  - Added `redeem_position(market_id, side)` to `RealTradingEngine` — calls CTF `redeem()` via `WalletManager._ctf_contract`
  - Wire-up complete: `auto_redeem.py` calls `trading.redeem_position()` with real on-chain tx
  - Returns `{success, tx_hash, error}` dict; updates local position balance on success
- [x] **`restore_from_backup()`** — position/order reconstruction from emergency snapshot
  - Added `RealPosition.dump()` / `RealOrder.dump()` with `market_id`, `entry_time`, `scale_count`, `hedge_amount`
  - Added `RealPosition.from_dump()` / `RealOrder.from_dump()` factory methods
  - `restore_from_backup()` reads JSON, reconstructs all objects, rebuilds cross-references, refreshes balance
- [x] **`sync_positions_from_chain()`** — improved fill-price derivation
  - Multi-strategy price resolution: (1) match existing order records, (2) Gamma metadata price, (3) CLOB orderbook mid-price, (4) existing position avg_price, (5) `FALLBACK_PRICE`
  - Real entry_time from Alchemy `blockTimestamp` instead of `datetime.now()`
- [x] **`transfer_position()`** — real on-chain ERC1155 transfer
  - Calls `CTF.safeTransferFrom(from, to, tokenId, amount, data)` via `WalletManager._ctf_contract`
  - Updates local position shares; removes position if fully transferred

### P3 — Hardening

- [ ] **Multi-wallet support for real trading** — extend wallet.py paper multi-wallet to real engine
- [ ] **Wallet tracker** — track wallet balances across real accounts
- [ ] **CI test coverage** — write real integration tests against testnet; remove mock-only coverage
- [ ] **CLOB_WS** (`constants.py:7`) — wire real-time order status updates via CLOB WebSocket
- [ ] **End-to-end smoke test** — place a tiny real buy order, confirm on-chain settlement

## File Index

| Area | File |
|---|---|
| CLOB API client | `src/polyalpha/trading/clob_client.py` |
| Real trading engine | `src/polyalpha/trading/real.py` |
| Real trading config | `src/polyalpha/trading/real_config.py` |
| Alchemy on-chain client | `src/polyalpha/trading/alchemy_client.py` |
| Error handling / circuit breakers | `src/polyalpha/trading/error_handling.py` |
| Auto-redeem engine | `src/polyalpha/trading/auto_redeem.py` |
| Multi-wallet | `src/polyalpha/trading/wallet.py` |
| Constants / endpoints | `src/polyalpha/core/constants.py` |
| Environment config | `src/polyalpha/core/env.py` |
| Client entry point | `src/polyalpha/client.py` |
| Example | `examples/real_trading.py` |
| Unit tests | `tests/unit/trading/test_real_engine.py` |
| E2E tests | `tests/e2e/test_real_trading_workflow.py` |
