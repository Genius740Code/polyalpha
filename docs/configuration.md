# Configuration

## Environment Variables

PolyAlpha reads configuration from environment variables prefixed with `POLYALPHA_`. Copy `.env.example` to `.env` and customize.

### Core

| Variable | Type | Default | Description |
|----------|------|---------|-------------|
| `POLYALPHA_BALANCE` | `float` | `100.0` | Paper trading starting USDC balance |
| `POLYALPHA_LOG_LEVEL` | `str` | `"WARNING"` | `"DEBUG"`, `"INFO"`, `"WARNING"`, `"ERROR"` |
| `POLYALPHA_LOG_FILE` | `str` | — | Path to log file (10 MB rotated, 3 backups) |
| `POLYALPHA_LOG_FORMAT` | `str` | `"text"` | `"text"` or `"json"` (machine-parseable JSON lines) |
| `POLYALPHA_RATE_LIMIT` | `int` | — | Max API requests per second (unlimited if unset) |
| `POLYALPHA_TIMEOUT` | `int` | `10` | HTTP request timeout in seconds |
| `POLYALPHA_RETRIES` | `int` | `3` | HTTP retries on 5xx errors |

### Paper Trading

All variables use the `POLYALPHA_PAPER_` prefix.

| Variable | Type | Default | Description |
|----------|------|---------|-------------|
| `FEE_MODE` | `str` | `"custom"` | `"polymarket"`, `"custom"`, or `"zero"` |
| `MARKET_CATEGORY` | `str` | `"crypto"` | Market category for polymarket fee mode |
| `CUSTOM_FEE_RATE` | `float` | `0.02` | Custom fee rate (2%) |
| `MAKER_FEE_RATE` | `float` | `0.0` | Maker fee rate |
| `ENABLE_REBATES` | `bool` | `true` | Enable fee rebate tracking |
| `MAKER_REBATE_PCT` | `float` | `0.25` | Maker rebate percentage (25%) |
| `EXECUTION_DELAY_MS` | `int` | `0` | Execution delay in milliseconds |
| `DELAY_RANDOMNESS` | `float` | `0.0` | Delay randomness 0–1 |
| `SLIPPAGE_PCT` | `float` | `0.0` | Slippage percentage |
| `SLIPPAGE_RANDOMNESS` | `float` | `0.0` | Slippage randomness 0–1 |
| `MAX_SLIPPAGE_NO_FILL` | `float` | `0.10` | Max slippage before no-fill 0–1 |
| `FILL_PROBABILITY` | `float` | `1.0` | Fill probability 0–1 |
| `CHECK_MODE` | `str`/`int` | `"continuous"` | `"continuous"`, `"once"`, or integer N |
| `ENABLE_RISK_MANAGEMENT` | `bool` | `true` | Enable risk management checks |
| `MAX_DAILY_LOSS` | `float` | `500.0` | Maximum daily loss in USDC |
| `MAX_TRADES_PER_DAY` | `int` | `100` | Maximum trades per day |
| `MAX_ORDER_SIZE` | `float` | `1000.0` | Maximum USDC per order |
| `MAX_POSITION_SIZE` | `float` | `2000.0` | Maximum position size per market |
| `MAX_OPEN_POSITIONS` | `int` | `10` | Maximum concurrent positions |
| `MAX_RISK_PER_TRADE` | `float` | `0.02` | Max risk per trade as % of balance (2%) |

### Real Trading

| Variable | Type | Default | Description |
|----------|------|---------|-------------|
| `POLYALPHA_PRIVATE_KEY` | `str` | — | Wallet private key **keep secret** |
| `POLYALPHA_RPC_URL` | `str` | `"https://polygon-rpc.com"` | Polygon RPC URL |
| `POLYALPHA_POLYMARKET_API_KEY` | `str` | — | Polymarket API key for CLOB access |
| `POLYALPHA_POLYMARKET_API_SECRET` | `str` | — | Polymarket API secret |
| `POLYALPHA_POLYMARKET_API_PASSPHRASE` | `str` | — | Polymarket API passphrase |

### AI

| Variable | Type | Default | Description |
|----------|------|---------|-------------|
| `POLYALPHA_OPENROUTER_API_KEY` | `str` | — | OpenRouter API key for AI analysis |

### Database

| Variable | Type | Default | Description |
|----------|------|---------|-------------|
| `POLYALPHA_DB_PATH` | `str` | — | Path to SQLite database file |

## Loading Functions

### `load_env_file(env_path=None) -> bool`

Load environment variables from a `.env` file. Returns `True` if loaded, `False` if `python-dotenv` is not installed.

```python
import polyalpha
polyalpha.load_env_file()                        # search cwd and parents
polyalpha.load_env_file("/path/to/.env")         # explicit path
```

### `get_env_config() -> dict`

Return all PolyAlpha configuration values currently set in the environment.

```python
config = polyalpha.get_env_config()
print(config["balance"])       # 100.0
print(config["log_level"])     # "WARNING"
print(config["rate_limit"])    # None
```

Returns keys: `balance`, `log_level`, `log_file`, `log_format`, `rate_limit`, `timeout`, `retries`, `private_key`, `rpc_url`, `polymarket_api_key`, `polymarket_api_secret`, `polymarket_api_passphrase`, `openrouter_api_key`, `db_path`.

### `get_paper_config_from_env() -> dict`

Return paper trading configuration from `POLYALPHA_PAPER_*` environment variables.

```python
from polyalpha.core.env import get_paper_config_from_env
paper_config = polyalpha.PaperConfig(**get_paper_config_from_env())
```

## Config Classes

### PaperConfig

Directly construct for full control:

```python
from polyalpha import PaperConfig

config = PaperConfig(
    fee_mode="polymarket",
    slippage_pct=0.03,
    execution_delay_ms=2000,
    fill_probability=0.85,
    max_daily_loss=500.0,
    max_open_positions=10,
)
```

Pass to Client:

```python
client = polyalpha.Client(balance=100.0, paper_config=config)
```

Or load from env:

```python
client = polyalpha.Client(balance=100.0, paper_config_from_env=True)
```

### PaperConfig Presets

Built-in presets for common scenarios:

```python
from polyalpha.trading.paper_config import get_paper_config_from_preset, list_presets

print(list_presets())
# ['CONSERVATIVE', 'REALISTIC', 'AGGRESSIVE', 'ZERO_FEE',
#  'HIGH_LATENCY', 'LIQUIDITY_PROVIDER', 'SCALPER', 'TEST']

config = get_paper_config_from_preset("REALISTIC")
client = polyalpha.Client(paper_config=config)
```

Preset characteristics:

| Preset | Fill Prob | Slippage | Delay | Risk |
|--------|-----------|----------|-------|------|
| CONSERVATIVE | 95% | 1% | 500ms | Low |
| REALISTIC | 85% | 3% | 2000ms | Medium |
| AGGRESSIVE | 70% | 5% | 100ms | High |
| ZERO_FEE | 100% | 0% | 0ms | Medium |
| HIGH_LATENCY | 60% | 8% | 5000ms | Medium |
| SCALPER | 98% | 2% | 50ms | Low |
| TEST | 100% | 0% | 0ms | None |

### RealTradingConfig

```python
from polyalpha import RealTradingConfig

config = RealTradingConfig(
    private_key="0x...",
    rpc_url="https://polygon-rpc.com",
    polymarket_api_key="...",
    position_sizing="kelly",
    kelly_fraction=0.25,
    max_order_size=100.0,
    require_confirmation=True,
)
```

### AutoRedeemConfig

```python
from polyalpha.trading.auto_redeem import AutoRedeemConfig

config = AutoRedeemConfig(
    enabled=True,
    trigger_on_time=True,
    time_interval="1d",
    min_markets=10,
    dry_run=False,
    only_winning=True,
)
```

## Logging Configuration

PolyAlpha configures its own logger (`polyalpha`) on import. Settings:

- INFO to stdout (filtered below WARNING)
- WARNING+ to stderr
- Optional file handler (10 MB rotating, 3 backups, DEBUG level)
- Format: `"text"` (default with sensitive data redaction) or `"json"` (machine-parseable)

Set via env:

```
POLYALPHA_LOG_LEVEL=INFO
POLYALPHA_LOG_FORMAT=json
POLYALPHA_LOG_FILE=./polyalpha.log
```

Or pass to Client:

```python
client = polyalpha.Client(log_level="DEBUG")
```
