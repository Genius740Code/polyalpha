"""
Real trading configuration presets for different trading strategies.

This module provides pre-configured RealTradingConfig settings that can be easily
copied and customized for different real trading strategies.

Note: Authentication parameters (private_key, rpc_url, polymarket_api_key) are NOT
included in presets for security reasons. These must be provided separately when
initializing the Client.

Usage
-----
    from polyalpha.trading.real_config import PRESETS, get_preset, list_presets

    # Use a pre-configured preset
    config_dict = get_preset("REALISTIC")
    client = polyalpha.Client(
        private_key="your-private-key",
        rpc_url="https://polygon-rpc.com",
        polymarket_api_key="your-api-key",
        real_config=polyalpha.RealTradingConfig(**config_dict),
    )

    # List all available presets
    print(list_presets())

    # Print a preset for copy-paste
    from polyalpha.trading.real_config import print_preset
    print_preset("REALISTIC")
"""

from typing import Optional

# Import RealTradingConfig at the end to avoid circular imports


# ── Configuration Presets ───────────────────────────────────────────────────────

PRESETS = {
    "CONSERVATIVE": {
        "require_confirmation": True,
        "max_order_size": 100.0,
        "max_daily_loss": 100.0,
        "max_position_size": 500.0,
        "max_open_positions": 5,
        "position_sizing": "fixed",
        "fixed_amount": 10.0,
        "percentage_of_balance": 0.02,
        "kelly_fraction": 0.15,
        "enable_stop_loss": True,
        "default_stop_loss_pct": 0.15,
        "enable_take_profit": True,
        "default_take_profit_pct": 0.30,
        "max_risk_per_trade": 0.01,
        "enable_position_scaling": False,
        "min_profit_for_scaling": 0.15,
        "max_scale_additions": 2,
        "enable_position_reduction": True,
        "enable_hedging": False,
        "max_hedge_ratio": 0.3,
        "slippage_tolerance": 0.03,
        "order_timeout": 60,
        "retry_attempts": 3,
        "retry_delay": 1.0,
        "fee_mode": "polymarket",
        "log_all_orders": True,
        "log_balance_updates": True,
    },
    "REALISTIC": {
        "require_confirmation": True,
        "max_order_size": 500.0,
        "max_daily_loss": 500.0,
        "max_position_size": 2000.0,
        "max_open_positions": 10,
        "position_sizing": "percentage",
        "fixed_amount": 25.0,
        "percentage_of_balance": 0.05,
        "kelly_fraction": 0.25,
        "enable_stop_loss": True,
        "default_stop_loss_pct": 0.20,
        "enable_take_profit": True,
        "default_take_profit_pct": 0.50,
        "max_risk_per_trade": 0.02,
        "enable_position_scaling": True,
        "min_profit_for_scaling": 0.10,
        "max_scale_additions": 3,
        "enable_position_reduction": True,
        "enable_hedging": True,
        "max_hedge_ratio": 0.5,
        "slippage_tolerance": 0.05,
        "order_timeout": 60,
        "retry_attempts": 3,
        "retry_delay": 1.0,
        "fee_mode": "polymarket",
        "log_all_orders": True,
        "log_balance_updates": True,
    },
    "AGGRESSIVE": {
        "require_confirmation": False,
        "max_order_size": 2000.0,
        "max_daily_loss": 1000.0,
        "max_position_size": 5000.0,
        "max_open_positions": 20,
        "position_sizing": "kelly",
        "fixed_amount": 50.0,
        "percentage_of_balance": 0.10,
        "kelly_fraction": 0.50,
        "enable_stop_loss": True,
        "default_stop_loss_pct": 0.25,
        "enable_take_profit": True,
        "default_take_profit_pct": 0.75,
        "max_risk_per_trade": 0.05,
        "enable_position_scaling": True,
        "min_profit_for_scaling": 0.05,
        "max_scale_additions": 5,
        "enable_position_reduction": True,
        "enable_hedging": True,
        "max_hedge_ratio": 0.7,
        "slippage_tolerance": 0.08,
        "order_timeout": 30,
        "retry_attempts": 5,
        "retry_delay": 0.5,
        "fee_mode": "polymarket",
        "log_all_orders": True,
        "log_balance_updates": True,
    },
    "MINIMAL": {
        "require_confirmation": False,
        "max_order_size": 10000.0,
        "max_daily_loss": 10000.0,
        "max_position_size": 10000.0,
        "max_open_positions": 50,
        "position_sizing": "fixed",
        "fixed_amount": 100.0,
        "percentage_of_balance": 0.20,
        "kelly_fraction": 1.0,
        "enable_stop_loss": False,
        "default_stop_loss_pct": 0.30,
        "enable_take_profit": False,
        "default_take_profit_pct": 1.0,
        "max_risk_per_trade": 0.10,
        "enable_position_scaling": True,
        "min_profit_for_scaling": 0.0,
        "max_scale_additions": 10,
        "enable_position_reduction": True,
        "enable_hedging": True,
        "max_hedge_ratio": 1.0,
        "slippage_tolerance": 0.15,
        "order_timeout": 120,
        "retry_attempts": 1,
        "retry_delay": 2.0,
        "fee_mode": "polymarket",
        "log_all_orders": False,
        "log_balance_updates": False,
    },
    "HIGH_FREQUENCY": {
        "require_confirmation": False,
        "max_order_size": 50.0,
        "max_daily_loss": 300.0,
        "max_position_size": 500.0,
        "max_open_positions": 15,
        "position_sizing": "fixed",
        "fixed_amount": 5.0,
        "percentage_of_balance": 0.01,
        "kelly_fraction": 0.10,
        "enable_stop_loss": True,
        "default_stop_loss_pct": 0.10,
        "enable_take_profit": True,
        "default_take_profit_pct": 0.20,
        "max_risk_per_trade": 0.005,
        "enable_position_scaling": False,
        "min_profit_for_scaling": 0.05,
        "max_scale_additions": 2,
        "enable_position_reduction": True,
        "enable_hedging": False,
        "max_hedge_ratio": 0.3,
        "slippage_tolerance": 0.02,
        "order_timeout": 15,
        "retry_attempts": 2,
        "retry_delay": 0.3,
        "fee_mode": "polymarket",
        "log_all_orders": True,
        "log_balance_updates": True,
    },
    "POSITION_TRADER": {
        "require_confirmation": True,
        "max_order_size": 1000.0,
        "max_daily_loss": 800.0,
        "max_position_size": 5000.0,
        "max_open_positions": 8,
        "position_sizing": "percentage",
        "fixed_amount": 100.0,
        "percentage_of_balance": 0.08,
        "kelly_fraction": 0.30,
        "enable_stop_loss": True,
        "default_stop_loss_pct": 0.25,
        "enable_take_profit": True,
        "default_take_profit_pct": 1.0,
        "max_risk_per_trade": 0.025,
        "enable_position_scaling": True,
        "min_profit_for_scaling": 0.15,
        "max_scale_additions": 4,
        "enable_position_reduction": True,
        "enable_hedging": True,
        "max_hedge_ratio": 0.6,
        "slippage_tolerance": 0.06,
        "order_timeout": 90,
        "retry_attempts": 4,
        "retry_delay": 1.5,
        "fee_mode": "polymarket",
        "log_all_orders": True,
        "log_balance_updates": True,
    },
    "HEDGING_ENABLED": {
        "require_confirmation": True,
        "max_order_size": 800.0,
        "max_daily_loss": 600.0,
        "max_position_size": 3000.0,
        "max_open_positions": 12,
        "position_sizing": "kelly",
        "fixed_amount": 50.0,
        "percentage_of_balance": 0.06,
        "kelly_fraction": 0.35,
        "enable_stop_loss": True,
        "default_stop_loss_pct": 0.20,
        "enable_take_profit": True,
        "default_take_profit_pct": 0.60,
        "max_risk_per_trade": 0.02,
        "enable_position_scaling": True,
        "min_profit_for_scaling": 0.10,
        "max_scale_additions": 3,
        "enable_position_reduction": True,
        "enable_hedging": True,
        "max_hedge_ratio": 0.8,
        "slippage_tolerance": 0.05,
        "order_timeout": 60,
        "retry_attempts": 3,
        "retry_delay": 1.0,
        "fee_mode": "polymarket",
        "log_all_orders": True,
        "log_balance_updates": True,
    },
    "TEST": {
        "require_confirmation": False,
        "max_order_size": 10000.0,
        "max_daily_loss": 10000.0,
        "max_position_size": 10000.0,
        "max_open_positions": 100,
        "position_sizing": "fixed",
        "fixed_amount": 10.0,
        "percentage_of_balance": 0.50,
        "kelly_fraction": 1.0,
        "enable_stop_loss": False,
        "default_stop_loss_pct": 0.50,
        "enable_take_profit": False,
        "default_take_profit_pct": 2.0,
        "max_risk_per_trade": 1.0,
        "enable_position_scaling": True,
        "min_profit_for_scaling": 0.0,
        "max_scale_additions": 10,
        "enable_position_reduction": True,
        "enable_hedging": True,
        "max_hedge_ratio": 1.0,
        "slippage_tolerance": 0.20,
        "order_timeout": 180,
        "retry_attempts": 1,
        "retry_delay": 0.5,
        "fee_mode": "polymarket",
        "log_all_orders": True,
        "log_balance_updates": True,
    },
}


# ── Configuration Helpers ─────────────────────────────────────────────────────

def list_presets() -> list[str]:
    """Return a list of all available preset names."""
    return list(PRESETS.keys())


def get_preset(name: str) -> dict:
    """
    Get a configuration preset dictionary by name.

    Parameters
    ----------
    name : str
        The name of the preset to retrieve (case-insensitive).

    Returns
    -------
    dict
        The configuration dictionary for the preset.

    Raises
    ------
    ValueError
        If the preset name is not found.
    """
    name_upper = name.upper()
    if name_upper not in PRESETS:
        available = ", ".join(PRESETS.keys())
        raise ValueError(f"Unknown preset '{name}'. Available: {available}")
    
    return PRESETS[name_upper].copy()


def print_preset(name: str) -> None:
    """
    Print a preset configuration in a copy-paste friendly format.

    Parameters
    ----------
    name : str
        The name of the preset to print (key from PRESETS dict).

    Raises
    ------
    ValueError
        If the preset name is not found.
    """
    name_upper = name.upper()
    if name_upper not in PRESETS:
        available = ", ".join(PRESETS.keys())
        raise ValueError(f"Unknown preset '{name}'. Available: {available}")

    config = PRESETS[name_upper]
    
    print(f'"{name_upper}": {{')
    for key, value in config.items():
        if isinstance(value, str):
            print(f'    "{key}": "{value}",')
        elif value is None:
            print(f'    "{key}": None,')
        elif isinstance(value, bool):
            print(f'    "{key}": {str(value).lower()},')
        elif isinstance(value, dict):
            print(f'    "{key}": {{')
            for k, v in value.items():
                print(f'        {k}: {v},')
            print(f'    }},')
        else:
            print(f'    "{key}": {value},')
    print("},")


def add_preset(name: str, config: dict) -> None:
    """
    Add a new configuration preset to the PRESETS dictionary.

    Parameters
    ----------
    name : str
        The name/key for the new preset (will be converted to uppercase).
    config : dict
        The configuration dictionary to add.
    """
    PRESETS[name.upper()] = config


def get_real_config_from_preset(name: str):
    """
    Get a RealTradingConfig object from a preset name.

    Parameters
    ----------
    name : str
        The name of the preset to use.

    Returns
    -------
    RealTradingConfig
        A RealTradingConfig object initialized with the preset values.

    Raises
    ------
    ValueError
        If the preset name is not found.
    """
    from .real import RealTradingConfig
    
    config_dict = get_preset(name)
    return RealTradingConfig(**config_dict)


# ── Example Usage (commented out) ─────────────────────────────────────────────

# Example of how to use these presets:
#
# from polyalpha.trading.real_config import get_preset, get_real_config_from_preset
# from polyalpha.trading.real import RealTradingConfig
# import polyalpha
#
# # Use a pre-configured preset
# config_dict = get_preset("REALISTIC")
# config = RealTradingConfig(**config_dict)
# client = polyalpha.Client(
#     private_key="your-private-key",
#     rpc_url="https://polygon-rpc.com",
#     polymarket_api_key="your-api-key",
#     real_config=config,
# )
#
# # Or get a RealTradingConfig directly
# config = get_real_config_from_preset("AGGRESSIVE")
# client = polyalpha.Client(
#     private_key="your-private-key",
#     rpc_url="https://polygon-rpc.com",
#     polymarket_api_key="your-api-key",
#     real_config=config,
# )
#
# # List available presets
# from polyalpha.trading.real_config import list_presets
# print(list_presets())
