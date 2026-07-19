"""
Real trading configuration tests — run with: pytest tests/unit/trading/test_real_config.py
"""

import pytest
from polyalpha.trading.real import RealTradingConfig


@pytest.mark.unit
def test_real_config_defaults():
    """Test default configuration values."""
    config = RealTradingConfig(
        private_key="0x" + "1" * 64,
        rpc_url="https://polygon-rpc.com",
        polymarket_api_key="test-api-key",
    )
    assert config.require_confirmation == True
    assert config.max_order_size == 1000.0
    assert config.max_daily_loss == 500.0
    assert config.max_position_size == 2000.0
    assert config.max_open_positions == 10
    assert config.position_sizing == "fixed"
    assert config.fixed_amount == 10.0
    assert config.percentage_of_balance == 0.05
    assert config.kelly_fraction == 0.25
    assert config.enable_stop_loss == True
    assert config.default_stop_loss_pct == 0.20
    assert config.enable_take_profit == True
    assert config.default_take_profit_pct == 0.50
    assert config.max_risk_per_trade == 0.02
    assert config.slippage_tolerance == 0.05
    assert config.order_timeout == 60
    assert config.retry_attempts == 3
    assert config.retry_delay == 1.0
    assert config.fee_mode == "polymarket"
    assert config.log_all_orders == True
    assert config.log_balance_updates == True


@pytest.mark.unit
def test_real_config_validation_invalid_position_sizing():
    """Test that invalid position sizing raises ValueError."""
    with pytest.raises(ValueError):
        RealTradingConfig(
            private_key="0x" + "1" * 64,
            rpc_url="https://polygon-rpc.com",
            polymarket_api_key="test-api-key",
            position_sizing="invalid",
        )


@pytest.mark.unit
def test_real_config_validation_negative_fixed_amount():
    """Test that negative fixed amount raises ValueError."""
    with pytest.raises(ValueError):
        RealTradingConfig(
            private_key="0x" + "1" * 64,
            rpc_url="https://polygon-rpc.com",
            polymarket_api_key="test-api-key",
            fixed_amount=-10.0,
        )


@pytest.mark.unit
def test_real_config_validation_invalid_percentage():
    """Test that invalid percentage of balance raises ValueError."""
    with pytest.raises(ValueError):
        RealTradingConfig(
            private_key="0x" + "1" * 64,
            rpc_url="https://polygon-rpc.com",
            polymarket_api_key="test-api-key",
            percentage_of_balance=1.5,
        )


@pytest.mark.unit
def test_real_config_validation_invalid_kelly_fraction():
    """Test that invalid kelly fraction raises ValueError."""
    with pytest.raises(ValueError):
        RealTradingConfig(
            private_key="0x" + "1" * 64,
            rpc_url="https://polygon-rpc.com",
            polymarket_api_key="test-api-key",
            kelly_fraction=1.5,
        )


@pytest.mark.unit
def test_real_config_validation_negative_max_order_size():
    """Test that negative max order size raises ValueError."""
    with pytest.raises(ValueError):
        RealTradingConfig(
            private_key="0x" + "1" * 64,
            rpc_url="https://polygon-rpc.com",
            polymarket_api_key="test-api-key",
            max_order_size=-100.0,
        )


@pytest.mark.unit
def test_real_config_validation_negative_max_daily_loss():
    """Test that negative max daily loss raises ValueError."""
    with pytest.raises(ValueError):
        RealTradingConfig(
            private_key="0x" + "1" * 64,
            rpc_url="https://polygon-rpc.com",
            polymarket_api_key="test-api-key",
            max_daily_loss=-500.0,
        )


@pytest.mark.unit
def test_real_config_validation_invalid_max_open_positions():
    """Test that invalid max open positions raises ValueError."""
    with pytest.raises(ValueError):
        RealTradingConfig(
            private_key="0x" + "1" * 64,
            rpc_url="https://polygon-rpc.com",
            polymarket_api_key="test-api-key",
            max_open_positions=0,
        )


@pytest.mark.unit
def test_real_config_validation_invalid_stop_loss_pct():
    """Test that invalid stop loss percentage raises ValueError."""
    with pytest.raises(ValueError):
        RealTradingConfig(
            private_key="0x" + "1" * 64,
            rpc_url="https://polygon-rpc.com",
            polymarket_api_key="test-api-key",
            default_stop_loss_pct=1.5,
        )


@pytest.mark.unit
def test_real_config_validation_invalid_take_profit_pct():
    """Test that invalid take profit percentage raises ValueError."""
    with pytest.raises(ValueError):
        RealTradingConfig(
            private_key="0x" + "1" * 64,
            rpc_url="https://polygon-rpc.com",
            polymarket_api_key="test-api-key",
            default_take_profit_pct=1.5,
        )


@pytest.mark.unit
def test_real_config_validation_invalid_max_risk():
    """Test that invalid max risk per trade raises ValueError."""
    with pytest.raises(ValueError):
        RealTradingConfig(
            private_key="0x" + "1" * 64,
            rpc_url="https://polygon-rpc.com",
            polymarket_api_key="test-api-key",
            max_risk_per_trade=1.5,
        )


@pytest.mark.unit
def test_real_config_validation_invalid_slippage():
    """Test that invalid slippage tolerance raises ValueError."""
    with pytest.raises(ValueError):
        RealTradingConfig(
            private_key="0x" + "1" * 64,
            rpc_url="https://polygon-rpc.com",
            polymarket_api_key="test-api-key",
            slippage_tolerance=1.5,
        )


@pytest.mark.unit
def test_real_config_validation_invalid_timeout():
    """Test that invalid order timeout raises ValueError."""
    with pytest.raises(ValueError):
        RealTradingConfig(
            private_key="0x" + "1" * 64,
            rpc_url="https://polygon-rpc.com",
            polymarket_api_key="test-api-key",
            order_timeout=0,
        )


@pytest.mark.unit
def test_real_config_validation_invalid_retry_attempts():
    """Test that invalid retry attempts raises ValueError."""
    with pytest.raises(ValueError):
        RealTradingConfig(
            private_key="0x" + "1" * 64,
            rpc_url="https://polygon-rpc.com",
            polymarket_api_key="test-api-key",
            retry_attempts=0,
        )


@pytest.mark.unit
def test_real_config_validation_invalid_retry_delay():
    """Test that invalid retry delay raises ValueError."""
    with pytest.raises(ValueError):
        RealTradingConfig(
            private_key="0x" + "1" * 64,
            rpc_url="https://polygon-rpc.com",
            polymarket_api_key="test-api-key",
            retry_delay=-1.0,
        )


@pytest.mark.unit
def test_real_config_validation_invalid_fee_mode():
    """Test that invalid fee mode raises ValueError."""
    with pytest.raises(ValueError):
        RealTradingConfig(
            private_key="0x" + "1" * 64,
            rpc_url="https://polygon-rpc.com",
            polymarket_api_key="test-api-key",
            fee_mode="invalid",
        )
