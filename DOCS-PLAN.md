# PolyAlpha Documentation Plan

**Status:** All existing docs are outdated — they were written for a much simpler version of the API and don't cover >80% of the actual codebase. This plan replaces them.

---

## Module Map

The codebase lives entirely in `src/polyalpha/`. Here is every module with its public API surface:

| Module | Files | Public Classes | Public Methods (count) |
|--------|-------|---------------|----------------------|
| `client.py` | 1 | `Client` | 7 attrs + `stream()`, `orderbook()`, `close()` |
| `bot.py` | 1 | `Bot`, `TickContext`, `PriceSnapshot` | `Bot`: 7 methods + `TickContext`: 10 properties + 3 methods |
| `stream.py` | 1 | `Stream` | 6 methods + 6 event types + 4 properties |
| `markets.py` | 1 | `MarketClient`, `RateLimiter` | 6 public methods |
| `core/` | 5 files | `Market`, `MarketSession`, `MarketSessionFilter` | 50+ constants, 22 error classes, `Market`: 7 properties + 4 methods, env helpers |
| `conditions.py` | 1 | 7 condition classes + 9 factory functions | 3 combinators + 11 conditions |
| `trading/` | 12 files | `PaperEngine`, `PaperOrder`, `PaperPosition`, `PaperConfig`, `PaperWallet`, `RealTradingEngine`, `RealTradingConfig`, `RealOrder`, `RealPosition`, `RealWallet`, `RealTradingWalletManager`, `WalletSelectionStrategy`, `AutoRedeemEngine`, `ClobClient`, `AlchemyClient` | PaperEngine: 35+ methods, RealTradingEngine: 14 methods |
| `analysis/` | 6 files | `DataFeed`, `DataFeedConfig`, `IndicatorCalculator`, `SignalGenerator`, `DeltaCalculator` | Indicators: 24 methods, Signals: 30 methods |
| `ai/` | 4 files | `OpenRouterClient`, `ModelConfig`, `MarketAnalysis`, `TradingSignal`, `AIResponse`, `ChatMessage` | OpenRouterClient: 12 methods, 7 AI error types |
| `orderbook/` | 9 files | `ClobBookClient`, `OrderBookFeed`, `OrderBookManager`, `MarketOrderBook`, `BookLevel`, `BookSide`, `FillEstimate`, `BookTrade`, `Order`, `OrderStatus`, `OrderType`, `Portfolio`, `Position`, `SimulatedOrderBookManager`, 3 strategy classes, `RiskManager`, `BacktestEngine` | 8 analytics functions |
| `database/` | 3 files | `TradeDatabase`, `TradeRecord`, `TradeStatistics`, `DatabaseMetrics`, `LogEntry`, `AlertRule`, 4 security classes | TradeDatabase: 30+ methods |
| `report/` | 11 files | `ReportEngine`, `ReportPreset`, `TradeRecord` | 10 metrics functions, 12 chart functions, terminal/HTML rendering |
| `bots/` | 4 files | `Sniper`, `Tracker`, `WeatherConfig` | Sniper: 5 methods + 2 properties + 8 events, Tracker: 4 methods |
| `wallet/` | 6 files | `WalletManager`, `WalletSecurity`, `MultiSigWallet`, `TransactionSigner`, `AuditLogger` | 17 audit event types |
| `utils/` | 1 file | Logging helpers, formatters, filters | 6 functions, 3 classes |

**29 example scripts** in `examples/`.

---

## Proposed Docs

### Phase 1: Core API — covers everything needed to use the SDK day-to-day

| # | Doc | What it covers | Approx pages |
|---|-----|---------------|-------------|
| 1 | **getting-started.md** | Install from repo (not PyPI), setup venv, `.env` config, `Client` constructor, first script (discover market → stream → trade), basic example walkthrough | 5 |
| 2 | **client.md** | Full `Client` API: all constructor params, every attribute (`markets`, `paper`, `ai`, `real`, `_clob`), methods (`stream()`, `orderbook()`, `close()`), context manager, env loading | 4 |
| 3 | **markets.md** | `MarketClient` full API: `latest()`, `latest_tweet()`, `get()`, `search()`, `available()`. `Market` dataclass: all fields, properties (`up_price`, `down_price`, `url`), methods (`dump()`, `json()`, `refresh()`, `show()`). Slug format. | 4 |
| 4 | **streaming.md** | `Stream` class: constructor, all 6 event types (`price`, `book`, `trade`, `close`, `error`, `connect`), `on()` decorator, `add_handler()`, `start()` blocking/background, `stop()`, properties (`running`, `connection_quality`, `circuit_breaker_state`). Reconnection logic, keepalive protocol, rate limiting, circuit breaker. | 5 |
| 5 | **trading.md** | Paper trading (`PaperEngine`): balance, buy/sell, limit orders, positions, P&L, order history, fees, slippage simulation. Real trading (`RealTradingEngine`): CLOB integration, wallet, orders, positions. `PaperConfig` and `RealTradingConfig` all fields. Auto-redeem engine. | 6 |
| 6 | **configuration.md** | All env vars (40+): core, paper trading, real trading, AI, database. `load_env_file()`, `get_env_config()`, `get_paper_config_from_env()`. Config classes: fields, defaults, presets. | 4 |

### Phase 2: Bot Framework & Strategies

| # | Doc | What it covers | Approx pages |
|---|-----|---------------|-------------|
| 7 | **bot.md** | `Bot` class: constructor, `on_tick` decorator, `when()` + `buy()` declarative API, `run()` lifecycle, `stop()`, `stats`. `TickContext`: all properties (price, balance, positions, pnl, rsi, sma, ema), methods (buy, limit). Cycle: discover → stream → resolve → rollover. | 5 |
| 8 | **conditions.md** | `Condition` protocol, 3 combinators (`and_`, `or_`, `not_`), 11 conditions (`rsi_above`, `rsi_below`, `price_above`, `price_below`, `crossed_above`, `crossed_below`, `always`, `never`, `when`). Operator overloading (`&`, `|`, `~`). Custom conditions. | 3 |
| 9 | **bots.md** | `Sniper` class: 5 methods + 2 properties (`stats`, `state`) + 8 events (`market_found`, `window_enter`, `entry`, `exit`, `resolve`, `rollover`, `error`, `stop`). `Tracker` class. `WeatherConfig` city presets (50+ cities). Configuration fields. | 4 |
| 10 | **examples-guide.md** | Walkthrough of each of the 29 example scripts, grouped by category (bot, trading, analysis, AI, database, report, sniper, etc.) | 5 |

### Phase 3: Analysis & AI

| # | Doc | What it covers | Approx pages |
|---|-----|---------------|-------------|
| 11 | **analysis.md** | `DataFeed` + `DataFeedConfig`: fetching market data, caching. `IndicatorCalculator`: all 24 indicators (RSI, SMA, EMA, MACD, Bollinger, etc.). `SignalGenerator`: all 30 signal methods. `DeltaCalculator`: 8 methods. | 6 |
| 12 | **ai.md** | `OpenRouterClient`: 12 methods, model config, chat, analysis, signals. `MarketAnalysis`, `TradingSignal`. 7 AI error types. Custom prompts. | 4 |

### Phase 4: Infrastructure

| # | Doc | What it covers | Approx pages |
|---|-----|---------------|-------------|
| 13 | **orderbook.md** | `ClobBookClient`: 8 methods. `OrderBookFeed`, `OrderBookManager`. `MarketOrderBook`, `BookLevel`, `BookSide`. 3 strategies: `ImbalanceStrategy`, `SpreadStrategy`, `MomentumStrategy`. `RiskManager`. `BacktestEngine`. 8 analytics functions. | 6 |
| 14 | **database.md** | `TradeDatabase`: 30+ methods for trades, orders, positions, P&L, reports, alerts. `TradeRecord`, `TradeStatistics`, `DatabaseMetrics`, `LogEntry`, `AlertRule`. Security: encryption, key management, audit. | 5 |
| 15 | **reporting.md** | `ReportEngine`: 7 methods. `ReportPreset`. 10 metrics functions. 12 chart/chart types. Terminal rendering. HTML template. Portfolio analytics. | 4 |
| 16 | **wallet.md** | `WalletManager`: 8 methods (balance, approve, transfer, sign, deposit, withdraw). `WalletSecurity`. `MultiSigWallet`. `TransactionSigner`. `AuditLogger` with 17 event types. | 4 |
| 17 | **errors.md** | Complete error reference: all 22+ error classes organized by category (market, trading, AI, network, database, wallet). Exception hierarchy. | 3 |

### Phase 5: Architecture & Reference

| # | Doc | What it covers | Approx pages |
|---|-----|---------------|-------------|
| 18 | **architecture.md** | Package structure, module dependencies, Client wiring diagram, data flow, design decisions | 3 |
| 19 | **api-reference.md** | Concise alphabetical/grouped reference of every exported symbol from `__init__.py` | 5 |
| 20 | **troubleshooting.md** | Common issues: WebSocket disconnects, rate limiting, authentication failures, market not found, insufficient balance | 2 |
| 21 | **testing.md** | Test structure, running tests, mocking patterns, fixtures | 2 |
| 22 | **contributing.md** | Setup dev environment, code style (ruff/mypy config from pyproject.toml), PR process | 2 |
| 23 | **migration-guide.md** | Breaking changes from old API to current, renamed methods (`sell()` → `sell_position()`), removed/added features, upgrade steps per module | 3 |
| 24 | **security.md** | API key management, private key handling, wallet security best practices, env var hygiene, encryption at rest, audit logging | 2 |

---

## Roadmap

```
Phase 1 (Core API)     ─── getting-started, client, markets, streaming, trading, configuration
       ↓
Phase 2 (Bot Strat)    ─── bot, conditions, bots, examples-guide
       ↓
Phase 3 (Analysis)     ─── analysis, ai
       ↓
Phase 4 (Infra)        ─── orderbook, database, reporting, wallet, errors
       ↓
Phase 5 (Reference)    ─── architecture, api-reference, troubleshooting, testing, contributing, migration-guide, security
```

### Existing docs to REVIEW (some may need updates)
Existing 24 docs files in `docs/`:
- `docs/getting-started.md` → verify install/setup text
- `docs/client.md` → verify Client constructor params
- `docs/markets.md` → verify MarketClient API
- `docs/streaming.md` → verify Stream API
- `docs/trading.md` → verify PaperEngine/RealTradingEngine API
- `docs/configuration.md` → verify env vars and config classes
- `docs/ai.md` → verify OpenRouterClient API
- `docs/analysis.md` → verify data feed, indicators, signals
- `docs/orderbook.md` → verify order book, strategies, backtesting
- `docs/database.md` → verify TradeDatabase API
- `docs/database-security.md` → verify security module
- `docs/reporting.md` → verify ReportEngine, metrics, charts
- `docs/wallet.md` → verify wallet security functions
- `docs/errors.md` → verify exception hierarchy
- `docs/bot.md` → verify Bot API
- `docs/bots.md` → verify Sniper, Tracker, WeatherConfig
- `docs/conditions.md` → verify condition protocol
- `docs/examples-guide.md` → verify all 32 example scripts
- `docs/architecture.md` → review package structure diagram
- `docs/api-reference.md` → review exported symbol list
- `docs/troubleshooting.md` → review common issues
- `docs/testing.md` → review test patterns
- `docs/contributing.md` → review dev setup guide
- `docs/migration-guide.md` → review upgrade path
- `docs/security.md` → review security best practices

---

## Verification Process

Every doc will be verified against source code:
1. Each claimed method signature checked against actual source
2. Each claimed config field checked against actual config class
3. Each example code tested to actually run
4. Each CLI/API example cross-referenced with real output
