# polyalpha

Python SDK for [Polymarket](https://polymarket.com) — discover prediction markets, stream live prices, trade paper or real, run bots with composable strategy conditions, analyse with 20+ TA indicators and AI signals, track P&L with full reporting, and manage wallets.

```bash
pip install polyalpha
```

---

## Quick start

```python
import polyalpha

client = polyalpha.Client()
market = client.markets.latest("BTC", "5m")

stream = client.stream(market)
@stream.on("price")
def on_price(up, down):
    print(f"UP={up:.4f}  DOWN={down:.4f}")
stream.start(background=True)

client.paper.buy(market, side="UP", amount=10.0)
client.paper.summary()
```

---

## Market discovery

Find any Up/Down market by asset + timeframe, slug, keyword, or browse all active.

```python
client.markets.latest("BTC", "5m")
client.markets.latest("ETH", "15m")
client.markets.latest("SOL", "1h")
client.markets.get("btc-updown-5m-1751234700")
client.markets.search("ETH 15m")
client.markets.available("5m")      # all active 5m markets
```

**Assets:** BTC, ETH, SOL, XRP, DOGE, HYPE, BNB  
**Timeframes:** 5m, 15m, 1h, 4h, 24h

---

## Price streaming

WebSocket stream with auto-reconnect, PING keepalive, and five event hooks.

```python
stream = client.stream(market)

@stream.on("price")   def on_price(up, down): ...
@stream.on("book")    def on_book(data): ...
@stream.on("trade")   def on_trade(data): ...
@stream.on("close")   def on_close(): ...
@stream.on("error")   def on_error(exc): ...

stream.start()                    # blocking
stream.start(background=True)     # daemon thread
stream.stop()

# Latest prices without a handler
stream.up
stream.down
```

See [`examples/stream.py`](./examples/stream.py) and [`examples/async_stream.py`](./examples/async_stream.py).

---

## Paper trading

Simulate orders with configurable fees, slippage, execution delay, and risk limits. Attach a stream for live P&L.

```python
client = polyalpha.Client(balance=500.0)

client.paper.buy(market, side="UP", amount=10.0)
client.paper.sell(market, side="UP", amount=5.0)
client.paper.limit(market, side="UP", price=0.92, amount=25.0)
client.paper.cancel(order.id)
client.paper.cancel_all()

client.paper.positions()       # open positions
client.paper.all_positions()   # all, incl. resolved
client.paper.balance
client.paper.summary()         # P&L table

# Advanced order types
client.paper.buy(market, side="UP", amount=10.0,
    trailing_stop=0.05,         # 5% trailing stop
    stop_loss=0.10,             # 10% stop-loss
    take_profit=0.50,           # 50% take-profit
    oco_group="group1")         # one-cancels-other

# Attach a stream for auto-fill + live P&L
client.paper.attach_stream(stream, market)

# Resolve after settlement
client.paper.resolve(market, outcome="UP")
```

See [`examples/paper.py`](./examples/paper.py) and [`examples/advanced_orders.py`](./examples/advanced_orders.py).

### Paper config & presets

Tune realism: fee model, slippage, fill probability, execution delay, risk limits.

```python
from polyalpha import PaperConfig

config = PaperConfig.REALISTIC    # 2s delay, polymarket fees, 85% fill prob
config = PaperConfig.AGGRESSIVE   # no delay, high fill prob
config = PaperConfig.CONSERVATIVE # slippage, low fill prob
config = PaperConfig.TEST         # zero fees, instant, 100% fill

client = polyalpha.Client(balance=500.0, paper_config=config)
# or load from .env:
client = polyalpha.Client(paper_config_from_env=True)
```

### Built-in presets

| Preset | Slippage | Delay | Fee | Fill prob |
|---|---|---|---|---|
| `CONSERVATIVE` | 0.1% | 1s | 2% | 85% |
| `BALANCED` | 0.02% | ~1s | 2% | 92% |
| `AGGRESSIVE` | 0% | 0 | 2% | 100% |
| `REALISTIC` | 0.03% | 2s | polymarket | 85% |
| `STRESS` | 0.1% | 5s | polymarket | 70% |
| `TEST` | 0% | 0 | 0% | 100% |

---

## Bots

Bot handles the full lifecycle: discover → stream → tick → resolve → rollover → repeat.

```python
bot = polyalpha.Bot("BTC", "5m", balance=500)

@bot.on_tick
def strategy(ctx):
    if ctx.price.up > 0.9 and ctx.rsi > 50:
        ctx.buy("UP", 20)

bot.run()  # blocking, auto-rollover
```

### TickContext

```python
ctx.price.up / ctx.price.down   # current prices
ctx.balance                     # paper balance
ctx.positions                   # open positions
ctx.pnl                         # realised P&L
ctx.rsi / ctx.sma_20 / ctx.ema_12   # indicators (requires pandas)
ctx.tick_count / ctx.trade_count
ctx.buy("UP", 20)               # market buy
ctx.limit("UP", 0.92, 25)       # limit order
ctx.close_position("UP")        # close position
```

### Composable conditions

Use declarative conditions with `and_`, `or_`, `not_` (or `&`, `|`, `~`).

```python
from polyalpha.conditions import rsi_above, price_above, and_

bot.when(and_(rsi_above(50), price_above("up", 0.9))).buy("UP", 20)
bot.when(rsi_below(30) & price_below("down", 0.15)).buy("DOWN", 20)
bot.run()
```

**Built-in conditions:** `rsi_above`, `rsi_below`, `price_above`, `price_below`, `price_change_pct_above`, `sma_above`, `sma_below`, `trending_up`, `trending_down`, `volatility_above`, `volume_above`, `min_tick_count`, `max_spend`, `stopped`

See [`examples/bot_simple.py`](./examples/bot_simple.py).

---

## Real trading

Trade live on Polymarket via CLOB with EIP-712 signing.

```python
client = polyalpha.Client(
    private_key="0x...",
    rpc_url="https://polygon-rpc.com",
    polymarket_api_key="...",
)

client.real.buy(market, side="UP", amount=10.0)
client.real.cancel(order.id)
client.real.positions()
client.real.order_history()
```

**Real trading presets:** `conservative`, `balanced`, `aggressive`, `scalp`, `dca`, `test`.

See [`examples/real_trading.py`](./examples/real_trading.py) and [`examples/clob_client_example.py`](./examples/clob_client_example.py).

---

## Auto-redeem

Schedule automatic redemption of winning positions.

```python
from polyalpha import AutoRedeemConfig

config = AutoRedeemConfig(time_interval="1d", min_value_usd=100.0)
client.paper.set_auto_redeem_config(config)
client.paper.auto_redeem.start_scheduler()

# Manual
client.paper.auto_redeem.redeem()
client.paper.auto_redeem.get_redeem_history()
```

Triggers: time interval, market count, value threshold. Safety: dry-run, min age, max value caps.

See [`examples/auto_redeem.py`](./examples/auto_redeem.py).

---

## Order book

REST snapshots + optional WebSocket deltas, in-memory O(1) manager, analytics, and backtestable strategies.

```python
# REST
feed = client.orderbook(market)
feed.refresh()
feed.bids[:3]
feed.asks[:3]

# Attach stream for live updates
feed.attach_stream(client.stream(market))

# Analytics
from polyalpha.orderbook import estimate_fill, book_summary, cumulative_depth
estimate_fill(snapshot, side="UP", amount=100.0)

# Strategies + backtesting
from polyalpha.orderbook import MomentumStrategy, SpreadStrategy, BacktestEngine
```

**Strategies:** `MomentumStrategy`, `MeanReversionStrategy`, `SpreadStrategy` (market making), `ImbalanceStrategy`.

See [`examples/orderbook_example.py`](./examples/orderbook_example.py).

---

## Technical analysis

Multi-source data feed and 20+ TA indicators.

```python
from polyalpha.analysis import DataFeed, IndicatorCalculator, SignalGenerator

feed = DataFeed(DataFeedConfig(source="binance", timeframe="5m"))
data = feed.fetch("BTC")

ind = IndicatorCalculator(data)
ind.rsi(14)
ind.bollinger_bands(20, 2.0)
ind.macd(12, 26, 9)
ind.adx(14)
ind.atr(14)
ind.stochastic(14, 3, 3)
ind.obv()

sig = SignalGenerator(ind)
sig.rsi_above(50)
sig.price_above_sma(20)
sig.bollinger_breakout("upper")
sig.macd_crossover()
sig.summary()  # all signals at once
```

**Data sources:** `binance` (default), `chainlink`, `coingecko`, `custom`.

See [`examples/analysis.py`](./examples/analysis.py).

---

## AI-powered signals

Analyse markets and generate trading signals via OpenRouter.

```python
client = polyalpha.Client(openrouter_api_key="sk-or-...")

analysis = client.ai.analyse(market)
analysis.sentiment    # "bullish" | "bearish" | "neutral"
analysis.confidence   # 0.0 – 1.0
analysis.reasoning    # markdown explanation

signal = client.ai.signal(market)
signal.action         # "BUY" | "SELL" | "HOLD"
signal.side           # "UP" | "DOWN" | None
signal.strength       # 0.0 – 1.0
```

See [`examples/ai_trading.py`](./examples/ai_trading.py).

---

## Reporting

Generate terminal summaries, interactive HTML dashboards, and PNG snapshots of paper-trading performance.

```python
client.paper.report.show()                    # terminal (rich tables)
client.paper.report.html(open_browser=True)   # interactive HTML
client.paper.report.save_png("report.png")    # requires kaleido
```

**30+ metrics:** Sharpe, Sortino, Calmar, Omega, Kelly criterion, VaR, CVaR, profit factor, win rate, average win/loss, max drawdown, recovery factor.

**12 charts:** equity curve, underwater drawdown, P&L per trade, win/loss distribution, monthly returns, rolling Sharpe, correlation matrix, P&L hourly heatmap.

See [`examples/report.py`](./examples/report.py) and [`examples/reporting.py`](./examples/reporting.py).

---

## Database

SQLite-backed trade persistence with optional encryption.

```python
client = polyalpha.Client(db_path="./trades.db")

db = client.paper.db
db.get_statistics(start_date="2026-01-01", end_date="2026-07-22")
db.get_trades(market_slug="btc-updown-*")
db.export_json("trades.json")
db.export_csv("trades.csv")
```

See [`examples/database_example.py`](./examples/database_example.py) and [`examples/database_security_example.py`](./examples/database_security_example.py).

---

## Sniper bot

Time-window execution bot with configurable thresholds and auto-rollover.

```python
from polyalpha import Sniper, SniperConfig

Sniper(SniperConfig(
    asset="BTC", timeframe="5m",
    balance=500.0, window_seconds=30,
    side="UP", order_size=25.0,
    auto_rollover=True,
)).run()
```

See [`examples/sniper.py`](./examples/sniper.py) and [`examples/sniper_ta.py`](./examples/sniper_ta.py).

---

## Tracker

Real-time P&L tracking with JSON/CSV export.

```python
from polyalpha import Tracker

tracker = Tracker(client.paper)
tracker.sync()
tracker.summary()
tracker.export_json("trades.json")
tracker.export_csv("trades.csv")
```

See [`examples/tracker.py`](./examples/tracker.py).

---

## Wallet management

Multi-wallet paper trading and secure wallet storage (AES-256, multi-sig, audit logging).

```python
from polyalpha.trading import PaperWallet

client.paper.add_wallet(PaperWallet(balance=1000.0, name="trader-1"))
client.paper.switch_wallet("trader-1")
```

See [`examples/multi_wallet_paper.py`](./examples/multi_wallet_paper.py).

---

## Errors

Typed exceptions for every failure mode:

```python
from polyalpha import (
    PolyalphaError,          # base
    MarketNotFound,          # slug not found
    MarketClosed,            # window closed
    StreamDisconnected,      # WS retry exhausted
    InsufficientBalance,     # balance too low
    OrderNotFound,           # unknown order
    OrderRejected,           # CLOB rejection
    OrderTimeout,            # not filled
    RiskLimitExceeded,       # risk check failed
    NetworkError,            # HTTP/WS failure
)
```

---

## Logging

| Variable | Default | Description |
|---|---|---|
| `POLYALPHA_LOG_LEVEL` | `WARNING` | DEBUG / INFO / WARNING / ERROR |
| `POLYALPHA_LOG_FILE` | — | File path (10 MB rotate) |
| `POLYALPHA_LOG_FORMAT` | `text` | `text` or `json` |

Sensitive data (keys, addresses, tokens) is auto-redacted in both formats.

---

## Configuration

```python
client = polyalpha.Client(
    balance         = 100.0,        # paper USDC balance
    timeout         = 10,           # HTTP timeout (s)
    retries         = 3,            # HTTP retries
    log_level       = "WARNING",
    rate_limit      = None,         # requests/s
    paper_config    = None,         # PaperConfig instance
    paper_config_from_env = False,
    db_path         = None,         # SQLite path
    openrouter_api_key = None,      # AI features
    private_key     = None,         # real trading key
    rpc_url         = None,         # Polygon RPC
    polymarket_api_key = None,      # CLOB API key
    real_config     = None,         # RealTradingConfig
)
```

---

## Examples index

| File | What it shows |
|---|---|
| [`examples/market.py`](./examples/market.py) | Market discovery and slug resolution |
| [`examples/stream.py`](./examples/stream.py) | Price streaming with all event hooks |
| [`examples/paper.py`](./examples/paper.py) | Paper trading — buy, sell, limit, summary |
| [`examples/advanced_orders.py`](./examples/advanced_orders.py) | Trailing stop, OCO, take-profit |
| [`examples/bot_simple.py`](./examples/bot_simple.py) | Bot with on_tick strategy |
| [`examples/sniper.py`](./examples/sniper.py) | Sniper time-window bot |
| [`examples/sniper_ta.py`](./examples/sniper_ta.py) | Sniper + technical analysis |
| [`examples/analysis.py`](./examples/analysis.py) | TA data feed, indicators, signals |
| [`examples/ai_trading.py`](./examples/ai_trading.py) | AI-powered analysis + signals |
| [`examples/orderbook_example.py`](./examples/orderbook_example.py) | Order book REST + WS + analytics |
| [`examples/report.py`](./examples/report.py) | Report engine — show, HTML, PNG |
| [`examples/reporting.py`](./examples/reporting.py) | Full reporting with metrics + charts |
| [`examples/real_trading.py`](./examples/real_trading.py) | Live CLOB trading |
| [`examples/auto_redeem.py`](./examples/auto_redeem.py) | Scheduled auto-redeem |
| [`examples/tracker.py`](./examples/tracker.py) | P&L tracker + export |
| [`examples/multi_wallet_paper.py`](./examples/multi_wallet_paper.py) | Multi-wallet paper trading |
| [`examples/database_example.py`](./examples/database_example.py) | SQLite trade persistence |
| [`examples/database_security_example.py`](./examples/database_security_example.py) | Encrypted database |
| [`examples/async_bots.py`](./examples/async_bots.py) | Async bot strategies |
| [`examples/risk_management.py`](./examples/risk_management.py) | Risk limits and controls |
| [`examples/pairsum_arb.py`](./examples/pairsum_arb.py) | Arbitrage example |
| [`examples/pre_trade_checks.py`](./examples/pre_trade_checks.py) | Pre-trade validation |
| [`examples/fee_rebates.py`](./examples/fee_rebates.py) | Fee rebate tracking |
| [`examples/portfolio_analytics.py`](./examples/portfolio_analytics.py) | Portfolio-level analysis |
| [`examples/weather_config_example.py`](./examples/weather_config_example.py) | Weather market example |

---

## Project layout

```
src/polyalpha/
├── __init__.py          Public API surface
├── client.py            Client — single entry point
├── markets.py           MarketClient — discovery
├── stream.py            Stream — WebSocket price feed
├── bot.py               Bot — lifecycle runner
├── conditions.py        Composable strategy conditions
│
├── core/                Constants, errors, market models, env
├── trading/             PaperEngine, RealTradingEngine, auto-redeem, retry
├── orderbook/           REST + WS book, manager, strategies, backtest
├── analysis/            DataFeed, 20+ indicators, 30+ signals
├── ai/                  OpenRouterClient, MarketAnalysis, TradingSignal
├── report/              ReportEngine, metrics (30+), charts (12), HTML
├── bots/                Sniper, Tracker
├── database/            SQLite, encryption, auth
├── wallet/              WalletSecurity, MultiSig, TransactionSigner, AuditLogger
└── utils/               Sensitive-data logging
```

---

## License

MIT
