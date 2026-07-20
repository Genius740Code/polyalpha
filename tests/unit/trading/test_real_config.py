"""
Real trading configuration tests — run with: pytest tests/unit/trading/test_real_config.py
"""

import pytest
from polyalpha.trading.real import RealTradingConfig
from polyalpha.trading.real_config import (
    PRESETS,
    list_presets,
    get_preset,
    print_preset,
    add_preset,
    get_real_config_from_preset,
)


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


# ── Preset Management Tests ───────────────────────────────────────────────────

@pytest.mark.unit
def test_list_presets():
    """Test listing all available presets."""
    presets = list_presets()
    assert isinstance(presets, list)
    assert len(presets) > 0
    assert "CONSERVATIVE" in presets
    assert "REALISTIC" in presets
    assert "AGGRESSIVE" in presets


@pytest.mark.unit
def test_get_preset_conservative():
    """Test getting CONSERVATIVE preset."""
    config = get_preset("CONSERVATIVE")
    assert isinstance(config, dict)
    assert config["require_confirmation"] is True
    assert config["max_order_size"] == 100.0
    assert config["max_daily_loss"] == 100.0
    assert config["position_sizing"] == "fixed"


@pytest.mark.unit
def test_get_preset_realistic():
    """Test getting REALISTIC preset."""
    config = get_preset("REALISTIC")
    assert isinstance(config, dict)
    assert config["require_confirmation"] is True
    assert config["max_order_size"] == 500.0
    assert config["position_sizing"] == "percentage"


@pytest.mark.unit
def test_get_preset_aggressive():
    """Test getting AGGRESSIVE preset."""
    config = get_preset("AGGRESSIVE")
    assert isinstance(config, dict)
    assert config["require_confirmation"] is False
    assert config["max_order_size"] == 2000.0
    assert config["position_sizing"] == "kelly"


@pytest.mark.unit
def test_get_preset_case_insensitive():
    """Test that preset names are case-insensitive."""
    config_lower = get_preset("conservative")
    config_upper = get_preset("CONSERVATIVE")
    config_mixed = get_preset("Conservative")
    
    assert config_lower == config_upper
    assert config_upper == config_mixed


@pytest.mark.unit
def test_get_preset_returns_copy():
    """Test that get_preset returns a copy, not the original."""
    config1 = get_preset("CONSERVATIVE")
    config2 = get_preset("CONSERVATIVE")
    
    # Modify one config
    config1["max_order_size"] = 999.0
    
    # The other should be unchanged
    assert config2["max_order_size"] == 100.0


@pytest.mark.unit
def test_get_preset_unknown():
    """Test that unknown preset raises ValueError."""
    with pytest.raises(ValueError, match="Unknown preset"):
        get_preset("UNKNOWN_PRESET")


@pytest.mark.unit
def test_print_preset(capsys):
    """Test printing a preset."""
    print_preset("CONSERVATIVE")
    captured = capsys.readouterr()
    
    assert "CONSERVATIVE" in captured.out
    assert "require_confirmation" in captured.out
    assert "max_order_size" in captured.out


@pytest.mark.unit
def test_print_preset_unknown():
    """Test printing unknown preset raises ValueError."""
    with pytest.raises(ValueError, match="Unknown preset"):
        print_preset("UNKNOWN_PRESET")


@pytest.mark.unit
def test_add_preset():
    """Test adding a new preset."""
    custom_config = {
        "require_confirmation": True,
        "max_order_size": 250.0,
        "max_daily_loss": 250.0,
        "max_position_size": 1000.0,
        "max_open_positions": 7,
        "max_positions_per_market": 1,
        "position_sizing": "percentage",
        "fixed_amount": 20.0,
        "percentage_of_balance": 0.03,
        "kelly_fraction": 0.20,
        "enable_stop_loss": True,
        "default_stop_loss_pct": 0.18,
        "enable_take_profit": True,
        "default_take_profit_pct": 0.40,
        "max_risk_per_trade": 0.015,
        "enable_position_scaling": True,
        "min_profit_for_scaling": 0.12,
        "max_scale_additions": 2,
        "enable_position_reduction": True,
        "enable_hedging": False,
        "max_hedge_ratio": 0.4,
        "slippage_tolerance": 0.04,
        "order_timeout": 45,
        "retry_attempts": 3,
        "retry_delay": 1.0,
        "fee_mode": "polymarket",
        "log_all_orders": True,
        "log_balance_updates": True,
    }
    
    add_preset("CUSTOM", custom_config)
    
    # Verify it was added
    assert "CUSTOM" in list_presets()
    
    # Verify we can retrieve it
    retrieved = get_preset("CUSTOM")
    assert retrieved["max_order_size"] == 250.0
    
    # Clean up to avoid polluting other tests
    from polyalpha.trading.real_config import PRESETS
    PRESETS.pop("CUSTOM", None)


@pytest.mark.unit
def test_add_preset_uppercase():
    """Test that preset names are converted to uppercase."""
    custom_config = {"require_confirmation": True, "max_order_size": 100.0}
    
    add_preset("lowercase_name", custom_config)
    
    # Should be stored as uppercase
    assert "LOWERCASE_NAME" in list_presets()
    
    # Clean up to avoid polluting other tests
    from polyalpha.trading.real_config import PRESETS
    PRESETS.pop("LOWERCASE_NAME", None)


@pytest.mark.unit
def test_get_real_config_from_preset():
    """Test getting RealTradingConfig from preset."""
    config = get_real_config_from_preset(
        "CONSERVATIVE",
        private_key="0x" + "1" * 64,
        rpc_url="https://polygon-rpc.com",
        polymarket_api_key="test-api-key",
    )
    
    assert isinstance(config, RealTradingConfig)
    assert config.require_confirmation is True
    assert config.max_order_size == 100.0
    assert config.position_sizing == "fixed"


@pytest.mark.unit
def test_get_real_config_from_preset_unknown():
    """Test getting RealTradingConfig from unknown preset."""
    with pytest.raises(ValueError, match="Unknown preset"):
        get_real_config_from_preset("UNKNOWN_PRESET")


@pytest.mark.unit
def test_presets_dict_structure():
    """Test that all presets have required keys."""
    required_keys = [
        "require_confirmation", "max_order_size", "max_daily_loss",
        "max_position_size", "max_open_positions", "max_positions_per_market",
        "position_sizing", "fixed_amount", "percentage_of_balance",
        "kelly_fraction", "enable_stop_loss", "default_stop_loss_pct",
        "enable_take_profit", "default_take_profit_pct", "max_risk_per_trade",
        "enable_position_scaling", "min_profit_for_scaling", "max_scale_additions",
        "enable_position_reduction", "enable_hedging", "max_hedge_ratio",
        "slippage_tolerance", "order_timeout", "retry_attempts",
        "retry_delay", "fee_mode", "log_all_orders", "log_balance_updates",
    ]
    
    for preset_name in list_presets():
        config = get_preset(preset_name)
        for key in required_keys:
            assert key in config, f"Preset {preset_name} missing key {key}"


@pytest.mark.unit
def test_preset_minimal():
    """Test MINIMAL preset values."""
    config = get_preset("MINIMAL")
    assert config["require_confirmation"] is False
    assert config["enable_stop_loss"] is False
    assert config["enable_take_profit"] is False
    assert config["log_all_orders"] is False
    assert config["log_balance_updates"] is False


@pytest.mark.unit
def test_preset_high_frequency():
    """Test HIGH_FREQUENCY preset values."""
    config = get_preset("HIGH_FREQUENCY")
    assert config["max_order_size"] == 50.0
    assert config["order_timeout"] == 15
    assert config["retry_delay"] == 0.3
    assert config["position_sizing"] == "fixed"


@pytest.mark.unit
def test_preset_position_trader():
    """Test POSITION_TRADER preset values."""
    config = get_preset("POSITION_TRADER")
    assert config["default_take_profit_pct"] == 1.0
    assert config["order_timeout"] == 90
    assert config["max_scale_additions"] == 4


@pytest.mark.unit
def test_preset_hedging_enabled():
    """Test HEDGING_ENABLED preset values."""
    config = get_preset("HEDGING_ENABLED")
    assert config["enable_hedging"] is True
    assert config["max_hedge_ratio"] == 0.8
    assert config["position_sizing"] == "kelly"


@pytest.mark.unit
def test_preset_test():
    """Test TEST preset values."""
    config = get_preset("TEST")
    assert config["max_order_size"] == 10000.0
    assert config["max_open_positions"] == 100
    assert config["max_positions_per_market"] == 100
    assert config["max_risk_per_trade"] == 1.0
