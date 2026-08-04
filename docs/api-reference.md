# API Reference

Concise reference of every symbol exported from `polyalpha.__init__`, grouped by category.

---

**Python:** >=3.9

---

## Entry Point

| Symbol | Source | Description |
|--------|--------|-------------|
| `Client` | `client.py` | Top-level entry point. Wires market discovery, paper/real trading, streaming, order book, and AI. |

---

## Core Types

| Symbol | Source | Description |
|--------|--------|-------------|
| `Market` | `core/market.py` | Dataclass: id, slug, question, end_time, volume, liquidity, up_price, down_price, active, closed, up_token, down_token, etc. |

---

## Environment

| Symbol | Source | Description |
|--------|--------|-------------|
| `load_env_file(env_path=None) -> bool` | `core/env.py` | Load `.env` file via `python-dotenv` |
| `get_env_config() -> dict` | `core/env.py` | Read all `POLYALPHA_*` env vars into a dict |

---

## Streaming

| Symbol | Source | Description |
|--------|--------|-------------|
| `Stream` | `stream.py` | WebSocket price stream for a market. 8 events: `price`, `book`, `trade`, `close`, `error`, `connect`, `price_reset`, `price_anomaly`. |

---

## Markets

| Symbol | Source | Description |
|--------|--------|-------------|
| `MarketClient` | `markets.py` | REST API client for market discovery. Methods: `latest()`, `latest_tweet()`, `get()`, `search()`, `available()` |

---

## Paper Trading

| Symbol | Source | Description |
|--------|--------|-------------|
| `PaperEngine` | `trading/paper_engine.py` | Simulated trading engine. Methods: `buy()`, `sell_position()`, `limit()`, `cancel()`, `resolve()`, `positions()`, `orders()`, `open()`, `summary()`, etc. |
| `PaperConfig` | `trading/paper_config.py` | Configuration dataclass for paper trading: fee mode, slippage, delay, risk limits |

---

## Real Trading

| Symbol | Source | Description |
|--------|--------|-------------|
| `RealTradingEngine` | `trading/real_engine.py` | On-chain Polymarket trading engine |
| `RealTradingConfig` | `trading/real_config.py` | Configuration for real trading: private_key, rpc_url, polymarket_api_key, gas settings |
| `RealOrder` | `trading/real_orders.py` | Real order dataclass |
| `RealPosition` | `trading/real_orders.py` | Real position dataclass |

---

## Wallet (Trading)

| Symbol | Source | Description |
|--------|--------|-------------|
| `WalletManager` | `trading/real_wallet.py` | Real trading wallet management (`polyalpha.trading.WalletManager`, not `polyalpha.wallet.WalletManager`) |
| `PaperWallet` | `trading/wallet.py` | Paper trading wallet with balance tracking |
| `RealWallet` | `trading/wallet.py` | Real on-chain wallet |
| `RealTradingWalletManager` | `trading/wallet.py` | Multi-wallet manager for real trading |
| `WalletSelectionStrategy` | `trading/wallet.py` | Enum: `ROUND_ROBIN`, `BALANCE_BASED`, `RANDOM` |

---

## Auto-Redeem

| Symbol | Source | Description |
|--------|--------|-------------|
| `AutoRedeemConfig` | `trading/auto_redeem.py` | Configuration: trigger types (time/count/value), schedules |
| `AutoRedeemEngine` | `trading/auto_redeem.py` | Automated position redemption engine |

---

## Order Book

| Symbol | Source | Description |
|--------|--------|-------------|
| `ClobBookClient` | `orderbook/clob.py` | REST client for Polymarket CLOB endpoints |
| `TokenPairTracker` | `orderbook/tracker.py` | Live CLOB stream for one UP/DOWN pair: mids, favourite, spread metrics |
| `TokenPairTrackerConfig` | `orderbook/tracker.py` | Configuration for `TokenPairTracker` |
| `OrderBookFeed` | `orderbook/feed.py` | Live order book (REST snapshots + WebSocket) |
| `OrderBookManager` | `orderbook/manager.py` | In-memory book state with subscribers |
| `OrderBookSnapshot` | `orderbook/models.py` | Snapshot dataclass: bids, asks, spread, mid, imbalance |
| `MarketOrderBook` | `orderbook/models.py` | Combined UP/DOWN book for a market |
| `BookLevel` | `orderbook/models.py` | (frozen) price + size at a level |
| `BookSide` | `orderbook/models.py` | Enum: `BUY`, `SELL` |
| `FillEstimate` | `orderbook/models.py` | (frozen) Estimated fill: avg price, slippage, levels used |
| `Trade` | `orderbook/models.py` | Trade dataclass (alias `BookTrade` exported via `polyalpha/__init__.py`) |
| `Strategy` | `orderbook/strategy.py` | Abstract base class for order book strategies |
| `ImbalanceStrategy` | `orderbook/strategy.py` | Trades on order book imbalance |
| `SpreadStrategy` | `orderbook/strategy.py` | Quotes both sides with inventory skew |
| `MomentumStrategy` | `orderbook/strategy.py` | Trades on price momentum |
| `BacktestEngine` | `orderbook/backtest.py` | Replay historical snapshots against a strategy |
| `RiskManager` | `orderbook/risk.py` | Pre-trade risk validation |
| `estimate_fill(book, side, size) -> FillEstimate` | `orderbook/analytics.py` | Walk book to estimate fill |
| `book_summary(book) -> dict` | `orderbook/analytics.py` | Compact book summary |

---

## Database

| Symbol | Source | Description |
|--------|--------|-------------|
| `TradeDatabase` | `database/database.py` | SQLite persistence: 85+ methods for CRUD, querying, export, backup, security |

---

## Report

| Symbol | Source | Description |
|--------|--------|-------------|
| `ReportPreset` | `report/presets.py` | Configurable metric/chart preset dataclass |
| `ReportEngine` | `report/engine.py` | Main analytics entry point (accessible as `client.paper.report`) |

*(ReportingEngine, PortfolioAnalytics, metrics, charts, terminal, HTML: use `polyalpha.report.*` directly)*

---

## Logging

| Symbol | Source | Description |
|--------|--------|-------------|
| `log_call` | `utils/logging_utils.py` | Decorator: auto-logs function entry/exit/errors. One-liner for adding logging to any buy/sell/market function. |

See [Logging](./logging.md) for full usage.

---

## Bots

| Symbol | Source | Description |
|--------|--------|-------------|
| `Sniper` | `bots/sniper.py` | Automated time-window trading bot with state machine |
| `Tracker` | `bots/tracker.py` | P&L tracking bot |
| `Bot` | `bot.py` | Declarative bot framework: `@on_tick`, `.when()` + `.buy()` |
| `BotHub` | `bot_hub.py` | Multi-strategy hub: one WebSocket, N isolated paper engines |
| `BinanceAccessor` | `bot_hub.py` | Binance BTC market data for bot strategies — `.close`, `.macd()`, `.price_change()`, etc. |

---

## Strategy Framework

| Symbol | Source | Description |
|--------|--------|-------------|
| `Strategy` | `strategy/base.py` | Declarative strategy ABC — override `signal()` only |
| `ConfigurableStrategy` | `strategy/base.py` | Parameter-only strategy (`from_config()`) |
| `Signal` | `strategy/base.py` | Dataclass: `side` — trigger a trade at configured order size |
| `SignalResult` | `strategy/base.py` | Dataclass: optional `amount_pct` / `limit_price` overrides |
| `StrategySuite` | `strategy/suite.py` | Run N strategies on one shared stream |

See [Strategies](strategies.md).

---

## Conditions

| Symbol | Source | Description |
|--------|--------|-------------|
| `conditions` | `conditions.py` | Module. Condition classes, 3 combinators (`and_`, `or_`, `not_`), 34+ factories (`rsi_above`, `ema_crossed_above`, `supertrend_up`, `ichimoku_bullish_breakout`, `macd_bullish_crossover`, `price_change_above`, etc.), operator overloading (`&`, `\|`, `~`) |

---

## Analysis

| Symbol | Source | Description |
|--------|--------|-------------|
| `DataFeed` | `analysis/data_feed.py` | Market data feed with caching |
| `DataFeedConfig` | `analysis/data_feed.py` | Data feed configuration |
| `IndicatorCalculator` | `analysis/indicators.py` | 19 technical indicators (+ supertrend, psar, ichimoku, donchian) |
| `SignalGenerator` | `analysis/signals.py` | 55+ trading signal methods (+ EMA cross, BB squeeze, supertrend, psar, ichimoku, donchian) |
| `CVDTracker` | `analysis/delta.py` | Binance BTC spot cumulative volume delta (aggTrade stream): `cvd`, `z`, `decelerating`, `velocity`, `acceleration` |
| `CVDTrackerConfig` | `analysis/delta.py` | Configuration for `CVDTracker` |
| `LiquidationTracker` | `analysis/liquidations.py` | Binance futures liquidation clusters (forceOrder stream): `cluster()` |
| `LiquidationTrackerConfig` | `analysis/liquidations.py` | Configuration for `LiquidationTracker` |
| `Globals` | `globals.py` | One instance of every continuously-running feed, shared by all strategies (`defaults`, `start`, `stop`) |
| `MarketCtx` | `globals.py` | Per-market scope: `remaining`, `price()`, `favourite()`, `spread()`, `trade_sweep()` |
| `watch_market` | `globals.py` | Async per-market loop: creates/stops a `TokenPairTracker`, ticks a handler every interval |
| `default_globals` | `globals.py` | Alias for `Globals.defaults(asset, **kwargs)` |

---

## AI

| Symbol | Source | Description |
|--------|--------|-------------|
| `OpenRouterClient` | `ai/client.py` | OpenRouter API client: 6 public methods for chat, analysis, signals |
| `MarketAnalysis` | `ai/models.py` | AI market analysis result dataclass |
| `TradingSignal` | `ai/models.py` | AI trading signal dataclass |

---

## Errors

| Symbol | Source | Description |
|--------|--------|-------------|
| `PolyalphaError` | `core/errors.py` | Base for all SDK errors |
| `MarketNotFound` | `core/errors.py` | No market matched the given criteria |
| `MarketClosed` | `core/errors.py` | Market is no longer active |
| `StreamDisconnected` | `core/errors.py` | WebSocket disconnected beyond retry budget |
| `InsufficientBalance` | `core/errors.py` | Paper balance too low |
| `InsufficientAllowance` | `core/errors.py` | CLOB allowance insufficient |
| `OrderNotFound` | `core/errors.py` | No order matched the given ID |
| `OrderBookError` | `core/errors.py` | Order book fetch/parse failed |
| `OrderBookNotFound` | `core/errors.py` | No book data for token |
| `OrderRejected` | `core/errors.py` | Order rejected by CLOB |
| `OrderTimeout` | `core/errors.py` | Order timed out |
| `NetworkError` | `core/errors.py` | Network connectivity failure |
| `TransientError` | `core/errors.py` | Retryable transient failure |
| `PositionNotFound` | `core/errors.py` | Position not found |
| `RiskLimitExceeded` | `core/errors.py` | Risk management limit exceeded |
| `OrderCancelled` | `core/errors.py` | Order cancelled by user or system |
| `CircuitBreakerOpenError` | `core/errors.py` | Circuit breaker blocking requests |
| `ManualInterventionRequiredError` | `core/errors.py` | Requires human recovery |
| `TransactionRollbackError` | `core/errors.py` | Transaction rollback failed |
| `BackupError` | `core/errors.py` | Backup/restore operation failed |
| `ConfigurationError` | `core/errors.py` | Invalid configuration |
| `AuthenticationError` | `core/errors.py` | Authentication failed |
| `RateLimitExceeded` | `core/errors.py` | API rate limit hit |
| `GasEstimationError` | `core/errors.py` | Gas estimation failed |
| `TransactionRebroadcastError` | `core/errors.py` | Transaction rebroadcast failed |
| `AIError` | `ai/errors.py` | Base for AI-related errors |
| `AIAuthenticationError` | `ai/errors.py` | Invalid/missing API key |
| `AIModelNotFoundError` | `ai/errors.py` | Requested model unavailable |
| `AIQuotaExceededError` | `ai/errors.py` | Rate limit or quota exceeded |
| `AIResponseError` | `ai/errors.py` | Malformed response |
| `AITimeoutError` | `ai/errors.py` | Request timed out |
| `AIConnectionError` | `ai/errors.py` | Connection to OpenRouter failed |

---

## Complete Export List

```
Client, Market, Stream,
load_env_file, get_env_config,
Bot, BotHub, BinanceAccessor, log_call,
PaperEngine, PaperConfig, AutoRedeemConfig,
RealTradingEngine, RealTradingConfig, RealOrder, RealPosition, WalletManager,
ReportPreset, ComparisonReport, VariantResult, TradeDatabase,
ClobBookClient, OrderBookFeed, OrderBookManager, OrderBookSnapshot,
  TokenPairTracker, TokenPairTrackerConfig,
  MarketOrderBook, BookLevel, BookSide, FillEstimate, BookTrade,
  Strategy, ImbalanceStrategy, SpreadStrategy, MomentumStrategy,
  BacktestEngine, RiskManager, estimate_fill, book_summary,
Sniper, Tracker,
DataFeed, DataFeedConfig, IndicatorCalculator, SignalGenerator,
  ChainlinkStreamer, ChainlinkStreamerConfig,
  CVDTracker, CVDTrackerConfig, LiquidationTracker, LiquidationTrackerConfig,
Globals, MarketCtx, watch_market, default_globals,
IndicatorAccessor, MACDResult, BBResult, DonchianResult,
OpenRouterClient, MarketAnalysis, TradingSignal,
conditions,
PolyalphaError, MarketNotFound, MarketClosed, StreamDisconnected,
  InsufficientBalance, InsufficientAllowance, OrderNotFound,
  OrderBookError, OrderBookNotFound, OrderRejected, OrderTimeout,
  NetworkError, TransientError, PositionNotFound, RiskLimitExceeded, OrderCancelled,
  CircuitBreakerOpenError, ManualInterventionRequiredError, TransactionRollbackError,
  BackupError, ConfigurationError, AuthenticationError, RateLimitExceeded,
  GasEstimationError, TransactionRebroadcastError,
AIError, AIAuthenticationError, AIModelNotFoundError, AIQuotaExceededError,
  AIResponseError, AITimeoutError, AIConnectionError
```
