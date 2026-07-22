# Testing

Test structure, running tests, mocking patterns, and fixtures.

---

## Framework

- **pytest** with `pytest-asyncio` (asyncio_mode = auto)
- **hypothesis** for property-based tests
- **pytest-cov** for coverage reporting

---

## Test Structure

```
tests/
├── conftest.py              # Global fixtures (temp_dir, mock_env_vars, sample data)
├── fixtures/
│   ├── __init__.py           # Re-exports all fixture modules
│   ├── client_fixtures.py    # Mock clients, API responses, WebSocket
│   ├── database_fixtures.py  # SQLite temp DB, mock connections
│   ├── e2e_fixtures.py       # Realistic market data, backtest data
│   ├── market_fixtures.py    # Mock markets, sessions, multi-market data
│   └── trading_fixtures.py  # Mock engines, orders, positions, configs
│
├── unit/                     # Fast tests, no external deps
│   ├── ai/
│   ├── analysis/
│   ├── bots/
│   ├── core/
│   ├── database/
│   ├── markets/
│   ├── orderbook/
│   ├── report/
│   ├── stream/
│   ├── trading/
│   └── wallet/
│
├── integration/              # Multi-component tests
├── e2e/                      # Full workflow tests
├── performance/              # Timing benchmarks
└── property/                 # Hypothesis property-based tests
```

**81 test source files** across 5 categories + 6 fixture modules.

---

## Running Tests

```bash
# Install dev dependencies
pip install -e ".[dev]"

# Run all tests (skips requires_network by default)
pytest

# Run with coverage
pytest --cov=src/polyalpha

# Run specific categories
pytest -m unit
pytest -m integration
pytest -m e2e
pytest -m slow
pytest -m performance
pytest -m property

# Run network tests (explicit opt-in)
pytest -m requires_network

# Run a specific test file
pytest tests/unit/trading/test_paper_engine.py

# Run a specific test
pytest tests/unit/trading/test_paper_engine.py::test_paper_market_buy
```

---

## Test Markers

| Marker | Purpose |
|--------|---------|
| `unit` | No external dependencies, fast |
| `integration` | Multiple components |
| `e2e` | Full workflow tests |
| `performance` | Timing benchmarks |
| `slow` | Longer-running tests |
| `property` | Hypothesis property-based |
| `requires_network` | Needs live network access |
| `requires_database` | Needs database access |

Tests marked `requires_network` are **skipped by default**. Use `-m requires_network` to include them.

---

## Mocking Patterns

### 1. `unittest.mock.Mock` for fake objects

```python
from unittest.mock import Mock

def test_with_mock_client():
    client = Mock()
    client.markets = Mock()
    client.markets.latest.return_value = Mock(slug="btc-updown-5m-123")
    # ...
```

### 2. `unittest.mock.patch` for HTTP/WebSocket

```python
from unittest.mock import patch, Mock

def test_market_discovery():
    with patch('httpx.Client.get') as mock_get:
        mock_response = Mock()
        mock_response.status_code = 200
        mock_response.json.return_value = MOCK_MARKET_RESPONSE
        mock_get.return_value = mock_response

        market = client.markets.get("btc-updown-5m-123")
        assert market.slug == "btc-updown-5m-123"
```

### 3. `monkeypatch` for env vars and module attributes

```python
def test_env_config_defaults(monkeypatch):
    monkeypatch.delenv("POLYALPHA_BALANCE", raising=False)
    monkeypatch.setattr("polyalpha.core.env.DOTENV_AVAILABLE", False)
    cfg = get_env_config()
    assert cfg["balance"] == 100.0
```

---

## Fixtures

### Global (`conftest.py`)

| Fixture | Scope | Returns |
|---------|-------|---------|
| `project_root` | session | `Path` to repo root |
| `src_dir` | session | `Path` to `src/` |
| `tests_dir` | session | `Path` to `tests/` |
| `temp_dir` | function | Temporary directory (`tmp_path`) |
| `mock_env_vars` | function | Sets `POLYALPHA_ENV=test` and `POLYALPHA_LOG_LEVEL=DEBUG` |
| `sample_market_data` | function | Dict with symbol, price, bid, ask, volume, timestamp |
| `sample_order_data` | function | Dict with symbol, side, quantity, price, order_type |
| `sample_portfolio_data` | function | Dict with cash, positions |

### Fixture Modules (`tests/fixtures/`)

| Module | Provides |
|--------|----------|
| `client_fixtures.py` | Mock clients, API responses, WebSocket connections |
| `database_fixtures.py` | SQLite temp databases, mock DB connections, sample trade data |
| `market_fixtures.py` | Mock `Market` objects, market sessions, multi-market datasets |
| `trading_fixtures.py` | Mock `PaperEngine`, orders, positions, config objects |
| `e2e_fixtures.py` | Realistic market data, backtest datasets, stress test data, performance benchmarks |

All fixture modules are re-exported via `fixtures/__init__.py` for project-wide availability.

---

## Writing Tests

### Unit Test (pure logic)

```python
@pytest.mark.unit
def test_paper_market_buy(engine, make_market):
    market = make_market()
    order = engine.buy(market, side="UP", amount=10.0)
    assert order.status == "filled"
    assert order.side == "UP"
    assert engine.balance == pytest.approx(90.0, abs=1e-6)
```

### Async Test (auto-detected)

```python
@pytest.mark.unit
async def test_apply_snapshot(manager):
    snapshot = OrderBookSnapshot.from_clob_response(MOCK_DATA)
    await manager.apply_snapshot(snapshot)
    assert manager.sequence == 1
```

### Property-Based Test (hypothesis)

```python
from hypothesis import given, strategies as st

@pytest.mark.property
@given(st.lists(st.floats(min_value=1.0, max_value=1000.0), min_size=50, max_size=1000))
def test_rsi_always_between_0_and_100(prices):
    indicators = IndicatorCalculator(make_data(prices))
    rsi = indicators.rsi(14)
    for val in rsi.dropna():
        assert 0 <= val <= 100
```

### Performance Test

```python
@pytest.mark.performance
def test_metric_computation_speed(large_trade_set):
    start = time.time()
    metrics = compute_metrics(large_trade_set, 1000.0, ALL_METRICS)
    elapsed = time.time() - start
    assert elapsed < 2.0
```

---

## Coverage

```bash
# Run with coverage report
pytest --cov=src/polyalpha --cov-report=term-missing

# Generate HTML report
pytest --cov=src/polyalpha --cov-report=html

# Enforce minimum coverage
pytest --cov=src/polyalpha --cov-fail-under=70
```

The CI pipeline runs coverage after tests and uploads results.

---

## CI Pipeline

The `.github/workflows/ci.yml` pipeline runs:

1. **lint** — `ruff check src/polyalpha tests`
2. **typecheck** — `mypy src/polyalpha`
3. **test** — Matrix across Python 3.9, 3.10, 3.11, 3.12 with `pytest --cov`
4. **coverage** — HTML report with `--cov-fail-under=70`
5. **performance** — `pytest tests/performance/ -m performance`
