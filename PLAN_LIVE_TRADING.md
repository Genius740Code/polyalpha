# Live Trading Completion Plan

## Status Overview

Paper trading is **complete** (fees, slippage, rebates, risk, advanced orders, multi-wallet, auto-redeem).  
Live trading via `RealTradingEngine` has **all safety/sizing/risk/config code in place** but the actual on-chain execution layer is **not functional**.

## Priority Work (Critical Path)

### P0 — Core Execution

- [ ] **Complete `ClobClient`** (`src/polyalpha/trading/clob_client.py`)
  - Replace `_simulate_response()` fallback with real Polymarket CLOB API calls
  - Switch from `requests` to `httpx` (rest of SDK uses httpx)
  - Implement proper CLOB request signing (EIP-712 typed data)
  - Wire up real endpoints: `/orders/place`, `/orders/{id}/cancel`, `/orders/{id}/status`, `/account/balance`
- [ ] **Validate credentials & env vars** (`src/polyalpha/core/env.py`, `.env.example`)
  - Ensure `POLYMARKET_API_KEY`, `POLYMARKET_PRIVATE_KEY`, `RPC_URL` are correctly loaded and validated
- [ ] **End-to-end smoke test** — place a tiny real buy order, confirm on-chain settlement

### P1 — Advanced Order Placeholders

- [ ] **`cancel()`** (`real.py:2046`) — replace `# Cancel on CLOB (placeholder)` with real CLOB cancel call
- [ ] **`_execute_iceberg_slice()`** (`real.py:4266`) — uncomment/replace placeholder `self.limit()` call
- [ ] **`_execute_twap_slice()`** (`real.py:4438`) — uncomment/replace placeholder `self.buy()`/`self.limit()` calls
- [ ] **`activate_bracket_orders()`** (`real.py:4001`) — uncomment stop-loss/take-profit placement
- [ ] **`check_conditional_triggers()`** (`real.py:4146`) — uncomment child order placement
- [ ] **`transfer_position()`** (`real.py:2982`) — implement real on-chain token transfer
- [ ] **`execute_trailing_stop_exit()`** (`real.py:2678`) — replace simplified stub with actual order execution

### P2 — Post-Trade & Recovery

- [ ] **Auto-redeem for real trading** (`auto_redeem.py:416`) — replace placeholder with on-chain redemption via CLOB
- [ ] **`restore_from_backup()`** (`real.py:1697`) — implement position/order reconstruction from emergency snapshot
- [ ] **`sync_positions_from_chain()`** (`real.py:2334`) — improve fill-price derivation from placeholder

### P3 — Hardening

- [ ] **Multi-wallet support for real trading** (TOD item) — extend `wallet.py` paper multi-wallet to real engine
- [ ] **Wallet tracker** (TOD item) — track wallet balances across real accounts
- [ ] **CI test coverage** — write real integration tests against testnet; remove mock-only coverage
- [ ] **CLOB_WS** (`constants.py:7`) — wire real-time order status updates via CLOB WebSocket

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
