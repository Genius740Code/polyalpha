# Logging

Logging utilities for polyalpha — one-line decorators, auto-redaction, and colored output.

---

## Quick Start

```python
from polyalpha import log_call
from polyalpha.utils.logging_utils import get_logger

log = get_logger()                    # one-liner instead of import+getLogger

@log_call(level=logging.INFO)         # auto-logs entry/exit at INFO (green)
def buy(self, market, side, amount):
    ...
```

---

## `@log_call` Decorator

Logs function **entry**, **exit**, and **exceptions** automatically.

### Default usage

```python
from polyalpha import log_call

@log_call
def get_price(asset: str):
    ...
```

Entry logged at `DEBUG` (dim grey), exceptions at `ERROR` (red):

```
DEBUG  -> get_price(asset='BTC')
ERROR  <- get_price -> MarketNotFound: No market found
```

### Trade-level logging (green)

Pass `level=logging.INFO` for trades — the existing `ColoredFormatter` makes `INFO` green:

```python
@log_call(level=logging.INFO)
def buy(self, market, side, amount):
    ...
```

```
INFO  -> buy(side='UP', amount=42.0)
INFO  <- buy -> Order(id='abc123', status='filled')
```

### Log return values

```python
@log_call(log_result=True)
def sell(self, market, side, amount):
    ...
```

```
DEBUG  -> sell(side='DOWN', amount=10.0)
DEBUG  <- sell -> {'id': 'def456', 'status': 'filled'}
```

### Skip verbose arguments

`self`, `cls`, `market`, and `wallet` are skipped automatically. Override with `skip_args`:

```python
@log_call(skip_args=("self", "cls", "market", "secret"))
def process(secret, value):
    ...
```

### Suppress error logging

```python
@log_call(log_error=False)
def risky():
    ...
```

### Full signature

```python
@log_call(
    level=logging.DEBUG,              # log level for entry/exit
    log_args=True,                    # log function arguments
    log_result=False,                 # log return value
    log_error=True,                   # log exceptions
    skip_args=("self", "cls", "market", "wallet"),
    max_arg_len=100,                  # truncate long args
    max_items=5,                      # truncate long lists/dicts
)
```

---

## `get_logger()` Helper

One line instead of two:

```python
from polyalpha.utils.logging_utils import get_logger

log = get_logger()                     # auto-detects caller module name
log = get_logger("polyalpha.Bot")     # explicit name
```

Equivalent to:

```python
import logging
log = logging.getLogger(__name__)
```

---

## Colorized Output

The `ColoredFormatter` applies ANSI colors by log level automatically when writing to a TTY:

| Level    | Color    |
|----------|----------|
| `DEBUG`  | dim grey |
| `INFO`   | green    |
| `WARNING`| yellow   |
| `ERROR`  | red      |
| `CRITICAL`| white on red |

This means `@log_call(level=logging.INFO)` for trades produces **green** output,
and exceptions produce **red** output — with no extra configuration.

Control with environment variables:

```bash
export POLYALPHA_LOG_COLORS=1      # force colors on
export POLYALPHA_LOG_COLORS=0      # force colors off
export NO_COLOR=1                   # force colors off (widely-adopted)
```

---

## Per-Strategy File Logging

`Bot` and `BotHub` accept a `log_dir` parameter that creates rotating file handlers for each strategy automatically.

### Bot

```python
bot = polyalpha.Bot("BTC", "5m", balance=500, log_dir="./logs")
# Creates ./logs/BTC_5m.log (5 MB max, 3 backups)
```

### BotHub

```python
hub = polyalpha.BotHub("BTC", "5m", log_dir="./logs")
# Creates ./logs/BTC_momentum.log, ./logs/BTC_value.log, etc.
```

Each strategy/variant gets its own `{asset}_{name}.log` file with `DEBUG`-level output.

### `setup_strategy_logger()` Helper

For custom use outside of `Bot`/`BotHub`:

```python
from polyalpha.utils.logging_utils import setup_strategy_logger

log = setup_strategy_logger("my_strategy", "./logs")
# Creates ./logs/my_strategy.log with rotating handler (5 MB, 3 backups)
```

```python
setup_strategy_logger(
    name,          # logger name and log file basename
    log_dir,       # directory for the .log file
    level=logging.DEBUG,
    max_bytes=5 * 1024 * 1024,  # 5 MB
    backup_count=3,
)
```

---

## Environment Variables

| Variable | Default | Description |
|----------|---------|-------------|
| `POLYALPHA_LOG_LEVEL` | `INFO` | Root log level |
| `POLYALPHA_LOG_FORMAT` | `text` | `text` or `json` |
| `POLYALPHA_LOG_FILE` | *(none)* | File path for persistent logs (rotating, 10 MB) |
| `POLYALPHA_LOG_COLORS` | `auto` | `1`, `0`, or `auto` |

---

## Sensitive Data Redaction

The SDK automatically redacts wallet addresses, private keys, API keys, passwords, tokens, transaction hashes, and secrets from all log output.

See [Security](./security.md#logging-security) for details.

---

## Correlation IDs

```python
from polyalpha.utils.logging_utils import (
    set_correlation_id,
    get_correlation_id,
    new_correlation_id,
)

new_correlation_id()                   # generate and set
set_correlation_id("my-session-1")    # explicit
cid = get_correlation_id()            # read current
```

When set, a `[cid=...]` prefix is prepended to every log line.

---

## Performance Tracking

```python
from polyalpha.utils.logging_utils import track_duration

with track_duration("order_fill", log, threshold_ms=500):
    result = place_order(...)
```

Logs a warning if the operation exceeds `threshold_ms`.

---

## JSON Log Format

```bash
export POLYALPHA_LOG_FORMAT=json
```

Produces machine-parseable JSON lines:

```json
{"timestamp": "2026-07-24T10:00:00", "level": "INFO", "logger": "polyalpha.trading",
 "module": "paper_engine", "line": 491, "message": "...", "process": 12345}
```
