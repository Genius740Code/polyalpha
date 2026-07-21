"""
Environment config tests — run with: pytest tests/unit/core/test_env.py
"""

import pytest
from polyalpha.core.env import load_env_file, get_env_config, get_paper_config_from_env


# ── load_env_file ──────────────────────────────────────────────────────────────

@pytest.mark.unit
def test_load_env_file_dotenv_unavailable(monkeypatch):
    monkeypatch.setattr("polyalpha.core.env.DOTENV_AVAILABLE", False)
    assert load_env_file(".env") is False


@pytest.mark.unit
def test_load_env_file_explicit_path(monkeypatch, tmp_path):
    monkeypatch.setattr("polyalpha.core.env.DOTENV_AVAILABLE", True)
    d = tmp_path / ".env"
    d.write_text("TEST_ENV_VAR=loaded")
    result = load_env_file(str(d))
    assert result is True


@pytest.mark.unit
def test_load_env_file_none_path(monkeypatch):
    monkeypatch.setattr("polyalpha.core.env.DOTENV_AVAILABLE", True)
    # When env_path is None, Path.cwd() is passed to load_dotenv as a directory
    # path rather than a file path, so dotenv does not load any variables.
    result = load_env_file(None)
    assert result is False


# ── get_env_config defaults ────────────────────────────────────────────────────

@pytest.mark.unit
def test_get_env_config_defaults(monkeypatch):
    monkeypatch.delenv("POLYALPHA_BALANCE", raising=False)
    monkeypatch.delenv("POLYALPHA_LOG_LEVEL", raising=False)
    monkeypatch.delenv("POLYALPHA_TIMEOUT", raising=False)
    monkeypatch.delenv("POLYALPHA_RETRIES", raising=False)
    monkeypatch.delenv("POLYALPHA_RPC_URL", raising=False)
    cfg = get_env_config()
    assert cfg["balance"] == 100.0
    assert cfg["log_level"] == "WARNING"
    assert cfg["rate_limit"] is None
    assert cfg["timeout"] == 10
    assert cfg["retries"] == 3
    assert cfg["private_key"] is None
    assert cfg["rpc_url"] == "https://polygon-rpc.com"
    assert cfg["polymarket_api_key"] is None
    assert cfg["openrouter_api_key"] is None
    assert cfg["db_path"] is None


@pytest.mark.unit
def test_get_env_config_with_values(monkeypatch):
    monkeypatch.setenv("POLYALPHA_BALANCE", "500.0")
    monkeypatch.setenv("POLYALPHA_LOG_LEVEL", "DEBUG")
    monkeypatch.setenv("POLYALPHA_TIMEOUT", "30")
    monkeypatch.setenv("POLYALPHA_RETRIES", "5")
    monkeypatch.setenv("POLYALPHA_PRIVATE_KEY", "0xabc123")
    monkeypatch.setenv("POLYALPHA_RPC_URL", "https://custom-rpc.com")

    cfg = get_env_config()
    assert cfg["balance"] == 500.0
    assert cfg["log_level"] == "DEBUG"
    assert cfg["timeout"] == 30
    assert cfg["retries"] == 5
    assert cfg["private_key"] == "0xabc123"
    assert cfg["rpc_url"] == "https://custom-rpc.com"


# ── get_env_config type coercion ───────────────────────────────────────────────

@pytest.mark.unit
def test_get_env_config_float_coercion(monkeypatch):
    monkeypatch.setenv("POLYALPHA_BALANCE", "123.45")
    assert get_env_config()["balance"] == 123.45


@pytest.mark.unit
def test_get_env_config_int_coercion(monkeypatch):
    monkeypatch.setenv("POLYALPHA_TIMEOUT", "42")
    assert get_env_config()["timeout"] == 42


@pytest.mark.unit
def test_get_env_config_str_passthrough(monkeypatch):
    monkeypatch.setenv("POLYALPHA_LOG_LEVEL", "INFO")
    assert get_env_config()["log_level"] == "INFO"


@pytest.mark.unit
def test_get_env_config_rate_limit_none_when_unset():
    assert get_env_config()["rate_limit"] is None


@pytest.mark.unit
def test_get_env_config_rate_limit_int(monkeypatch):
    monkeypatch.setenv("POLYALPHA_RATE_LIMIT", "15")
    assert get_env_config()["rate_limit"] == 15


# ── get_env_config error handling ──────────────────────────────────────────────

@pytest.mark.unit
def test_get_env_config_invalid_float_raises(monkeypatch):
    monkeypatch.setenv("POLYALPHA_BALANCE", "not-a-number")
    with pytest.raises(ValueError):
        get_env_config()


@pytest.mark.unit
def test_get_env_config_invalid_int_raises(monkeypatch):
    monkeypatch.setenv("POLYALPHA_TIMEOUT", "abc")
    with pytest.raises(ValueError):
        get_env_config()


# ── get_paper_config_from_env defaults ─────────────────────────────────────────

@pytest.mark.unit
def test_get_paper_config_defaults():
    cfg = get_paper_config_from_env()
    assert cfg["fee_mode"] == "custom"
    assert cfg["market_category"] == "crypto"
    assert cfg["custom_fee_rate"] == 0.02
    assert cfg["maker_fee_rate"] == 0.0
    assert cfg["enable_rebates"] is True
    assert cfg["maker_rebate_pct"] == 0.25
    assert cfg["execution_delay_ms"] == 0
    assert cfg["delay_randomness"] == 0.0
    assert cfg["slippage_pct"] == 0.0
    assert cfg["slippage_randomness"] == 0.0
    assert cfg["max_slippage_no_fill"] == 0.10
    assert cfg["fill_probability"] == 1.0
    assert cfg["check_mode"] == "continuous"
    assert cfg["enable_risk_management"] is True
    assert cfg["max_daily_loss"] == 500.0
    assert cfg["max_trades_per_day"] == 100
    assert cfg["max_order_size"] == 1000.0
    assert cfg["max_position_size"] == 2000.0
    assert cfg["max_open_positions"] == 10
    assert cfg["max_risk_per_trade"] == 0.02


@pytest.mark.unit
def test_get_paper_config_with_values(monkeypatch):
    monkeypatch.setenv("POLYALPHA_PAPER_FEE_MODE", "zero")
    monkeypatch.setenv("POLYALPHA_PAPER_MAX_DAILY_LOSS", "1000.0")
    monkeypatch.setenv("POLYALPHA_PAPER_MAX_TRADES_PER_DAY", "50")
    monkeypatch.setenv("POLYALPHA_PAPER_CHECK_MODE", "once")

    cfg = get_paper_config_from_env()
    assert cfg["fee_mode"] == "zero"
    assert cfg["max_daily_loss"] == 1000.0
    assert cfg["max_trades_per_day"] == 50
    assert cfg["check_mode"] == "once"


# ── get_paper_config_from_env type coercion ────────────────────────────────────

@pytest.mark.unit
def test_get_paper_config_bool_true_variants(monkeypatch):
    for val in ("true", "1", "yes", "on", "True", "YES", "ON"):
        monkeypatch.setenv("POLYALPHA_PAPER_ENABLE_REBATES", val)
        assert get_paper_config_from_env()["enable_rebates"] is True


@pytest.mark.unit
def test_get_paper_config_bool_false_variants(monkeypatch):
    for val in ("false", "0", "no", "off", "False", "NO", "OFF"):
        monkeypatch.setenv("POLYALPHA_PAPER_ENABLE_REBATES", val)
        assert get_paper_config_from_env()["enable_rebates"] is False


@pytest.mark.unit
def test_get_paper_config_float_coercion(monkeypatch):
    monkeypatch.setenv("POLYALPHA_PAPER_CUSTOM_FEE_RATE", "0.05")
    assert get_paper_config_from_env()["custom_fee_rate"] == 0.05


@pytest.mark.unit
def test_get_paper_config_int_coercion(monkeypatch):
    monkeypatch.setenv("POLYALPHA_PAPER_EXECUTION_DELAY_MS", "500")
    assert get_paper_config_from_env()["execution_delay_ms"] == 500


@pytest.mark.unit
def test_get_paper_config_str_passthrough(monkeypatch):
    monkeypatch.setenv("POLYALPHA_PAPER_FEE_MODE", "polymarket")
    assert get_paper_config_from_env()["fee_mode"] == "polymarket"


# ── get_paper_config_from_env check_mode ───────────────────────────────────────

@pytest.mark.unit
def test_get_paper_config_check_mode_parses_int(monkeypatch):
    monkeypatch.setenv("POLYALPHA_PAPER_CHECK_MODE", "2")
    assert get_paper_config_from_env()["check_mode"] == 2


@pytest.mark.unit
def test_get_paper_config_check_mode_fallback_to_continuous(monkeypatch):
    monkeypatch.setenv("POLYALPHA_PAPER_CHECK_MODE", "invalid")
    assert get_paper_config_from_env()["check_mode"] == "continuous"


# ── get_paper_config_from_env error handling ───────────────────────────────────

@pytest.mark.unit
def test_get_paper_config_invalid_float_raises(monkeypatch):
    monkeypatch.setenv("POLYALPHA_PAPER_CUSTOM_FEE_RATE", "bad-value")
    with pytest.raises(ValueError):
        get_paper_config_from_env()


@pytest.mark.unit
def test_get_paper_config_invalid_int_raises(monkeypatch):
    monkeypatch.setenv("POLYALPHA_PAPER_EXECUTION_DELAY_MS", "not-an-int")
    with pytest.raises(ValueError):
        get_paper_config_from_env()


# ── Isolation ──────────────────────────────────────────────────────────────────

@pytest.mark.unit
def test_get_env_config_does_not_leak_to_paper_config(monkeypatch):
    monkeypatch.setenv("POLYALPHA_BALANCE", "999.0")
    paper = get_paper_config_from_env()
    assert paper["max_daily_loss"] == 500.0  # default still applies
    assert paper["max_trades_per_day"] == 100
