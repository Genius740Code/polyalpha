# Contributing

Guidelines for setting up a development environment, code style, and submitting changes.

---

## Setup

```bash
# Clone the repository
git clone https://github.com/Genius740Code/polyalpha.git
cd polyalpha

# Create a virtual environment
python -m venv .venv
source .venv/bin/activate  # or .venv\Scripts\activate on Windows

# Install in development mode with all extras
pip install -e ".[all]"

# Copy and edit environment config
cp .env.example .env
```

---

## Code Style

### Ruff (linter)

Configuration in `pyproject.toml`:

```toml
[tool.ruff]
line-length = 100
target-version = "py39"

[tool.ruff.lint]
select = ["E", "F", "I", "N", "W", "UP"]
ignore = ["E501"]
```

Rules: E (pycodestyle errors), F (pyflakes), I (isort), N (naming), W (pycodestyle warnings), UP (pyupgrade).

```bash
# Check for issues
ruff check src/polyalpha tests

# Auto-fix
ruff check src/polyalpha tests --fix
```

### Mypy (type checking)

```toml
[tool.mypy]
python_version = "3.9"
warn_return_any = true
warn_unused_configs = true
disallow_untyped_defs = false
```

```bash
# Type check
mypy src/polyalpha
```

### Pre-commit

```bash
pre-commit install
pre-commit run --all-files
```

---

## Testing

```bash
# Run all tests (skips network tests)
pytest

# Run with coverage
pytest --cov=src/polyalpha

# Run specific category
pytest -m unit
pytest -m integration
```

See [testing.md](testing.md) for detailed testing guide.

---

## Project Structure

```
src/polyalpha/     — Package source
tests/             — Test suite (unit, integration, e2e, performance, property)
examples/          — 32 example scripts
docs/              — Documentation
```

All source code is under `src/polyalpha/`. Tests mirror the source structure under `tests/unit/`.

---

## Pull Request Process

1. Fork the repository and create a feature branch from `main`
2. Make your changes with clear commit messages
3. Run `ruff check src/polyalpha tests` — no new warnings
4. Run `mypy src/polyalpha` — no new type errors
5. Add tests for any new functionality
6. Run `pytest` — all tests pass
7. Submit a pull request to `main`

The CI pipeline (`.github/workflows/ci.yml`) will automatically run:
- Linting (ruff)
- Type checking (mypy)
- Tests across Python 3.9–3.12
- Coverage check (≥70%)

---

## Environment Variables

See `.env.example` for all supported environment variables. Key ones for development:

```
POLYALPHA_LOG_LEVEL=DEBUG
POLYALPHA_LOG_FORMAT=text    # or "json"
POLYALPHA_BALANCE=10000.0
```

---

## Documentation

Docs live in `docs/` as Markdown files. The `DOCS-PLAN.md` tracks the documentation roadmap.

When adding new public API:
- Add the symbol to `__all__` in the appropriate `__init__.py`
- Add to `docs/api-reference.md`
- Add usage examples to the relevant doc
- Add to `docs/` if it introduces a new category

---

## Versioning

The project follows [Semantic Versioning](https://semver.org/). Version is defined in `pyproject.toml` as `version = "0.2.01"` and exported as `polyalpha.__version__`.

Releases are published to PyPI automatically when a `v*` tag is pushed to GitHub (see `.github/workflows/publish.yml`).

---

## License

MIT License — see [License.md](../License.md).
