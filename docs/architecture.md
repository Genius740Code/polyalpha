# Architecture

Package structure, module dependencies, Client wiring, and data flow.

---

## Package Structure

```
src/polyalpha/
├── __init__.py           # Package root — logging setup, __all__ exports
├── client.py             # Client — top-level entry point, wires all modules
├── stream.py             # Stream — WebSocket price streaming
├── bot.py                # Bot — declarative trading bot framework
├── markets.py            # MarketClient — market discovery REST API
├── conditions.py         # Condition protocol + 11 condition classes + combinators
│
├── core/                 # Foundational types and constants
│   ├── __init__.py       #   Re-exports from all sub-modules
│   ├── constants.py      #   API URLs, timeouts, defaults
│   ├── env.py            #   Environment variable loading
│   ├── errors.py         #   25 exception classes
│   ├── market.py         #   Market dataclass
│   └── market_sessions.py#   MarketSession dataclass + session definitions
│
├── trading/              # Paper and real trading engines
│   ├── __init__.py       #   26 exports
│   ├── paper_engine.py   #   PaperEngine — simulated trading
│   ├── paper_config.py   #   PaperConfig dataclass
│   ├── paper_types.py    #   PaperOrder, PaperPosition dataclasses
│   ├── paper_fees.py     #   Fee calculations
│   ├── paper_risk.py     #   Risk management limits
│   ├── paper_reporting.py#   Terminal position rendering
│   ├── real_engine.py    #   RealTradingEngine — on-chain trading
│   ├── real_config.py    #   RealTradingConfig + presets
│   ├── real_orders.py    #   RealOrder, RealPosition, advanced order dataclasses
│   ├── real_risk.py      #   RiskManager
│   ├── real_wallet.py    #   WalletManager
│   ├── real_position_sizing.py  #   PositionSizer strategies
│   ├── wallet.py         #   PaperWallet, RealWallet, WalletSelectionStrategy
│   ├── clob_client.py    #   Polymarket CLOB API client
│   ├── alchemy_client.py #   Alchemy RPC client
│   ├── auto_redeem.py    #   AutoRedeemEngine — position redemption
│   ├── error_handling.py #   CircuitBreaker, GracefulDegradation, DisasterRecovery
│   └── retry.py          #   Retry decorators with backoff
│
├── orderbook/            # CLOB order book client, feed, strategies, backtest
│   ├── __init__.py       #   All public symbols
│   ├── models.py         #   BookLevel, Order, Trade, FillEstimate, OrderBookSnapshot, etc.
│   ├── clob.py           #   ClobBookClient — REST CLOB API
│   ├── feed.py           #   OrderBookFeed — REST snapshots + WebSocket
│   ├── manager.py        #   OrderBookManager + SimulatedOrderBookManager
│   ├── strategy.py       #   Strategy ABC + ImbalanceStrategy, SpreadStrategy, MomentumStrategy
│   ├── risk.py           #   RiskManager — pre-trade validation
│   ├── backtest.py       #   BacktestEngine — historical replay
│   └── analytics.py      #   7 pure analytics functions
│
├── database/             # SQLite persistence layer
│   ├── __init__.py       #   TradeDatabase + security exports
│   ├── database.py       #   TradeDatabase, TradeRecord, TradeStatistics, etc.
│   └── security.py       #   Encryption, auth, RBAC, data masking
│
├── report/               # Analytics and reporting
│   ├── __init__.py       #   ReportEngine, ReportPreset exports
│   ├── engine.py         #   ReportEngine — main entry point
│   ├── presets.py        #   ReportPreset dataclass + registry
│   ├── metrics.py        #   32 performance metrics
│   ├── charts.py         #   12 Plotly chart builders
│   ├── terminal.py       #   ANSI/rich terminal renderer
│   ├── html_template.py  #   Self-contained HTML dashboard
│   ├── records.py        #   TradeRecord dataclass + extract_trades
│   ├── portfolio_analytics.py  # PortfolioAnalytics engine
│   ├── reporting.py      #   ReportingEngine — comprehensive reports
│   └── real_reports.py   #   Real-trading report functions
│
├── wallet/               # Secure wallet management
│   ├── __init__.py       #   All wallet exports
│   ├── wallet_manager.py #   WalletManager — unified entry point
│   ├── wallet_security.py#   WalletSecurity — encrypted key storage
│   ├── multisig_wallet.py#   MultiSigWallet — weighted multi-sig
│   ├── transaction_signer.py # TransactionSigner — sign + broadcast
│   └── audit_logger.py   #   AuditLogger — 17 event types
│
├── analysis/             # Technical analysis
│   ├── __init__.py       #   DataFeed, IndicatorCalculator, SignalGenerator, DeltaCalculator
│   ├── data_feed.py      #   DataFeed + DataFeedConfig
│   ├── indicators.py     #   24 indicator methods
│   ├── signals.py        #   30 signal methods
│   ├── delta.py          #   DeltaCalculator
│   └── _native_ta.py     #   Pure-python RSI, SMA, EMA implementations
│
├── ai/                   # AI/OpenRouter integration
│   ├── __init__.py       #   OpenRouterClient + error classes
│   ├── client.py         #   OpenRouterClient — 12 methods
│   ├── models.py         #   AIResponse, ChatMessage, MarketAnalysis, ModelConfig, TradingSignal
│   └── errors.py         #   7 AI error classes
│
├── bots/                 # Automated trading bots
│   ├── __init__.py       #   Sniper, Tracker, weather configs
│   ├── sniper.py         #   Sniper — time-window trading bot
│   ├── tracker.py        #   Tracker — P&L tracking
│   └── weather_config.py #   Weather station city presets
│
└── utils/
    └── logging_utils.py  #   SensitiveDataFilter, correlation IDs, masking helpers
```

**Total: 12 directories, 63 `.py` files.**

---

## Client Wiring Diagram

```
Client
├── self.markets ───────── MarketClient        ─── REST API market discovery
├── self.paper  ────────── PaperEngine          ─── Simulated trading
│   ├── .report ────────── ReportEngine         ─── Analytics (lazy)
│   ├── .database ──────── TradeDatabase         ─── Persistence (optional)
│   └── .portfolio_analytics ── PortfolioAnalytics (lazy)
├── self.real  ─────────── RealTradingEngine   ─── On-chain trading (optional)
│   └── .report ────────── ReportEngine
├── self.ai    ─────────── OpenRouterClient     ─── AI analysis (optional)
├── self._clob ─────────── ClobBookClient       ─── CLOB REST API
├── .stream(market) ────── Stream               ─── WebSocket price feed
└── .orderbook(market) ─── OrderBookFeed        ─── Live order book
    ├── ClobBookClient                         ─── REST snapshots
    └── OrderBookManager                       ─── In-memory state
```

Construction of `Client` wires these modules together. The `Client` itself is a context manager:

```python
with Client(balance=1000.0) as client:
    market = client.markets.latest("BTC", "5m")
    stream = client.stream(market)
    # ...
# client.close() called automatically
```

---

## Data Flow

### Market Discovery
```
Client.markets.latest("BTC", "5m")
  → MarketClient._request("GET", "/markets/latest", ...)
  → Polymarket Gamma API
  ← Market dataclass
```

### Price Streaming
```
Client.stream(market)
  → Stream.__init__
  → Stream.start(background=True)
  → WebSocket connect to ws://clob.polymarket.com/ws
  → _handle_price_change → _publish_prices
  → emit("price", up, down)
```

### Paper Trading
```
Client.paper.buy(market, side="UP", amount=10.0)
  → PaperEngine._validate(market, side, amount)
  → PaperEngine._create_order
  → PaperEngine._charge_fee
  → PaperEngine._watch_for_resolution
  → PaperEngine.resolve(market, outcome)
  → TradeDatabase.save_trade (if db attached)
  → ReportEngine available for analytics
```

### Order Book
```
Client.orderbook(market)
  → OrderBookFeed(market, clob=Client._clob)
  → feed.refresh()                     # REST snapshot
  → feed.attach_stream(stream)         # WebSocket live
  → @feed.on("update") callback
```

### Complete Bot Cycle
```
Bot.run()
  → Bot._discover()              # MarketClient.latest()
  → Bot._stream_prices()         # Stream.start() + TickContext
  → Bot._maybe_build_strategy()  # Conditions → strategy function
  → on_tick callback              # Per-price-tick decision
  → Bot._resolve()               # PaperEngine.resolve()
  → Bot._rollover()              # Clean up, sleep, repeat
```

---

## Key Design Decisions

| Decision | Rationale |
|----------|-----------|
| SQLite via stdlib `sqlite3` | Zero external dependencies for persistence |
| Fernet + PBKDF2 encryption | Industry-standard symmetric encryption for wallet storage |
| Proxy module pattern (`core/`) | Shared constants, errors, and types avoid circular imports |
| Lazy imports in `PaperEngine` | `ReportEngine`, `TradeDatabase`, `AutoRedeemEngine` imported only when used |
| `pytest-asyncio` with `asyncio_mode=auto` | Mix of sync and async code; clean async test support |
| Ruff + mypy in CI | Enforces consistent code style and type safety |
| No CLI entry points | Library-first design; all functionality via Python API |
