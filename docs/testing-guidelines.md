# Testing Guidelines

Polyalpha uses a three-tier test structure: **unit**, **integration**, and **e2e**, plus supplementary **performance** and **property-based** tests.

## Test Structure

```
tests/
├── unit/            # Pure unit tests (no external dependencies)
├── integration/     # Tests across multiple components
├── e2e/             # Full workflow tests
├── performance/     # Execution time benchmarks
├── property/        # Hypothesis property-based tests
├── fixtures/        # Shared pytest fixtures
├── conftest.py      # Global pytest configuration
└── __init__.py
```

## Running Tests

```bash
# Run the full suite (skips network-dependent tests)
python -m pytest

# Run with coverage
python -m pytest --cov=src/polyalpha --cov-report=term-missing

# Run by category
python -m pytest -m unit
python -m pytest -m integration
python -m pytest -m e2e
python -m pytest -m performance
python -m pytest -m property

# Run a specific file
python -m pytest tests/unit/trading/test_paper_engine.py

# Run a specific test
python -m pytest tests/unit/trading/test_paper_engine.py::test_paper_market_buy

# Include network tests
python -m pytest -m requires_network

# Run slow tests
python -m pytest -m slow

# Verbose output
python -m pytest -v

# Stop on first failure
python -m pytest -x

# Run tests matching a keyword
python -m pytest -k "buy or sell"
```

## Writing Tests

### Naming Conventions

- **Files**: `test_<module>.py`
- **Classes**: `Test<ClassName>`
- **Functions**: `test_<feature>_<scenario>_<expected>`

```python
def test_order_fill_deducts_balance():
    ...
```

### Test Structure (Arrange-Act-Assert)

```python
def test_withdrawal_reduces_balance():
    """Clear description of the behaviour under test."""
    # Arrange
    engine = PaperEngine(balance=100.0)

    # Act
    engine.buy(market, side="UP", amount=25.0)

    # Assert
    assert engine.balance == pytest.approx(75.0)
```

### Markers

```python
@pytest.mark.unit
@pytest.mark.integration
@pytest.mark.e2e
@pytest.mark.performance
@pytest.mark.slow
@pytest.mark.requires_network
@pytest.mark.requires_database
```

### Fixture Usage

Prefer the shared fixtures in `tests/fixtures/` over defining per-file fixtures. Use `conftest.py` for globally shared fixtures.

**Available fixture modules:**
- `market_fixtures.py` — market instances, sessions, sample data
- `trading_fixtures.py` — engines, orders, positions, configs
- `database_fixtures.py` — temp DB connections, mock queries
- `client_fixtures.py` — API clients, auth, HTTP/WS mocks
- `e2e_fixtures.py` — realistic market data, scenario data, stress data

```python
from tests.fixtures import mock_paper_engine, mock_order

def test_cancel_order(mock_paper_engine, mock_order):
    mock_paper_engine.cancel_order(mock_order.id)
    mock_paper_engine.cancel_order.assert_called_once_with(mock_order.id)
```

### Assertions

- Use `pytest.approx` for float comparisons
- Use `pytest.raises` for expected exceptions
- Prefer `assert` over custom assertion methods

```python
assert result == expected_value
assert result == pytest.approx(0.05)
with pytest.raises(ValueError):
    engine.buy(market, side="UP", amount=-1)
```

### Parametrized Tests

```python
@pytest.mark.parametrize("side,amount,expected_fee", [
    ("UP", 10.0, 0.2),
    ("DOWN", 50.0, 1.0),
    ("UP", 100.0, 2.0),
])
def test_fee_calculation(side, amount, expected_fee):
    ...
```

### Async Tests

Tests in `tests/unit/trading/` use `pytest-asyncio` with `asyncio_mode = "auto"` configured in `pyproject.toml`. Async test functions are automatically detected:

```python
async def test_async_operation():
    result = await some_async_function()
    assert result == expected
```

### Property-Based Tests (Hypothesis)

```python
from hypothesis import given, strategies as st

@given(st.floats(min_value=1, max_value=100))
def test_property_is_preserved(value):
    ...
```

Run with: `python -m pytest tests/property/`

### Mocking

Use `unittest.mock.Mock` and `unittest.mock.patch` from the standard library. Prefer dependency injection over patching when possible.

```python
from unittest.mock import Mock, patch

def test_with_mock():
    mock_client = Mock()
    mock_client.get_price.return_value = 50000.0
    result = my_function(mock_client)
    mock_client.get_price.assert_called_once()
```

## Performance Tests

Located in `tests/performance/`. Measure execution time against thresholds:

```bash
python -m pytest tests/performance/ -m performance
```

Thresholds are defined per-test; update them when optimisations change baseline performance.

## Coverage

```bash
python -m pytest --cov=src/polyalpha --cov-report=html --cov-report=term-missing
open htmlcov/index.html  # view report
python -m pytest --cov=src/polyalpha --cov-fail-under=80  # enforce minimum
```

## Configuration

Test configuration lives in `pyproject.toml` under `[tool.pytest.ini_options]`. Global fixtures and marker registration live in `tests/conftest.py`.

### pyproject.toml settings

```toml
[tool.pytest.ini_options]
testpaths = ["tests"]
python_files = ["test_*.py"]
python_classes = ["Test*"]
python_functions = ["test_*"]
addopts = ["-m", "not requires_network"]
asyncio_mode = "auto"
```

## CI/CD

Tests run automatically on every push and pull request via GitHub Actions. See `.github/workflows/ci.yml` for the pipeline definition.
