"""
Paper trading configuration presets for different trading strategies.

This module provides pre-configured PaperConfig settings that can be easily
copied and customized for different paper trading strategies.

Usage
-----
    from polyalpha.trading.paper_config import PRESETS, get_preset, list_presets

    # Use a pre-configured preset
    config = get_preset("REALISTIC")
    client = polyalpha.Client(balance=1000.0, paper_config=config)

    # List all available presets
    print(list_presets())

    # Print a preset for copy-paste
    from polyalpha.trading.paper_config import print_preset
    print_preset("REALISTIC")
"""

from typing import Optional

# Import PaperConfig at the end to avoid circular imports


# ── Configuration Presets ───────────────────────────────────────────────────────

PRESETS = {
    "CONSERVATIVE": {
        "fee_mode": "polymarket",
        "market_category": "crypto",
        "custom_fee_rate": 0.02,
        "maker_fee_rate": 0.0,
        "enable_rebates": True,
        "rebate_tiers": {
            0: 0.00,
            1000: 0.10,
            5000: 0.15,
            10000: 0.20,
            50000: 0.25,
        },
        "maker_rebate_pct": 0.25,
        "execution_delay_ms": 500,
        "delay_randomness": 0.1,
        "slippage_pct": 0.01,
        "slippage_randomness": 0.05,
        "max_slippage_no_fill": 0.05,
        "fill_probability": 0.95,
        "check_mode": "continuous",
        "enable_risk_management": True,
        "max_daily_loss": 100.0,
        "max_trades_per_day": 20,
        "max_order_size": 200.0,
        "max_position_size": 500.0,
        "max_open_positions": 5,
        "max_positions_per_market": 1,
        "max_risk_per_trade": 0.01,
    },
    "REALISTIC": {
        "fee_mode": "polymarket",
        "market_category": "crypto",
        "custom_fee_rate": 0.02,
        "maker_fee_rate": 0.0,
        "enable_rebates": True,
        "rebate_tiers": {
            0: 0.00,
            1000: 0.10,
            5000: 0.15,
            10000: 0.20,
            50000: 0.25,
        },
        "maker_rebate_pct": 0.25,
        "execution_delay_ms": 2000,
        "delay_randomness": 0.2,
        "slippage_pct": 0.03,
        "slippage_randomness": 0.1,
        "max_slippage_no_fill": 0.10,
        "fill_probability": 0.85,
        "check_mode": "continuous",
        "enable_risk_management": True,
        "max_daily_loss": 500.0,
        "max_trades_per_day": 100,
        "max_order_size": 1000.0,
        "max_position_size": 2000.0,
        "max_open_positions": 10,
        "max_positions_per_market": 1,
        "max_risk_per_trade": 0.02,
    },
    "AGGRESSIVE": {
        "fee_mode": "custom",
        "market_category": "crypto",
        "custom_fee_rate": 0.02,
        "maker_fee_rate": 0.0,
        "enable_rebates": True,
        "rebate_tiers": {
            0: 0.00,
            1000: 0.10,
            5000: 0.15,
            10000: 0.20,
            50000: 0.25,
        },
        "maker_rebate_pct": 0.25,
        "execution_delay_ms": 100,
        "delay_randomness": 0.3,
        "slippage_pct": 0.05,
        "slippage_randomness": 0.2,
        "max_slippage_no_fill": 0.15,
        "fill_probability": 0.70,
        "check_mode": "continuous",
        "enable_risk_management": True,
        "max_daily_loss": 1000.0,
        "max_trades_per_day": 200,
        "max_order_size": 2000.0,
        "max_position_size": 5000.0,
        "max_open_positions": 20,
        "max_positions_per_market": 1,
        "max_risk_per_trade": 0.05,
    },
    "ZERO_FEE": {
        "fee_mode": "zero",
        "market_category": "crypto",
        "custom_fee_rate": 0.0,
        "maker_fee_rate": 0.0,
        "enable_rebates": False,
        "rebate_tiers": {},
        "maker_rebate_pct": 0.0,
        "execution_delay_ms": 0,
        "delay_randomness": 0.0,
        "slippage_pct": 0.0,
        "slippage_randomness": 0.0,
        "max_slippage_no_fill": 0.10,
        "fill_probability": 1.0,
        "check_mode": "continuous",
        "enable_risk_management": True,
        "max_daily_loss": 500.0,
        "max_trades_per_day": 100,
        "max_order_size": 1000.0,
        "max_position_size": 2000.0,
        "max_open_positions": 10,
        "max_positions_per_market": 1,
        "max_risk_per_trade": 0.02,
    },
    "HIGH_LATENCY": {
        "fee_mode": "custom",
        "market_category": "crypto",
        "custom_fee_rate": 0.02,
        "maker_fee_rate": 0.0,
        "enable_rebates": True,
        "rebate_tiers": {
            0: 0.00,
            1000: 0.10,
            5000: 0.15,
            10000: 0.20,
            50000: 0.25,
        },
        "maker_rebate_pct": 0.25,
        "execution_delay_ms": 5000,
        "delay_randomness": 0.5,
        "slippage_pct": 0.08,
        "slippage_randomness": 0.3,
        "max_slippage_no_fill": 0.20,
        "fill_probability": 0.60,
        "check_mode": "continuous",
        "enable_risk_management": True,
        "max_daily_loss": 500.0,
        "max_trades_per_day": 50,
        "max_order_size": 500.0,
        "max_position_size": 1000.0,
        "max_open_positions": 5,
        "max_positions_per_market": 1,
        "max_risk_per_trade": 0.01,
    },
    "LIQUIDITY_PROVIDER": {
        "fee_mode": "custom",
        "market_category": "crypto",
        "custom_fee_rate": 0.01,
        "maker_fee_rate": 0.0,
        "enable_rebates": True,
        "rebate_tiers": {
            0: 0.05,
            1000: 0.15,
            5000: 0.20,
            10000: 0.25,
            50000: 0.30,
        },
        "maker_rebate_pct": 0.35,
        "execution_delay_ms": 1000,
        "delay_randomness": 0.15,
        "slippage_pct": 0.02,
        "slippage_randomness": 0.05,
        "max_slippage_no_fill": 0.05,
        "fill_probability": 0.90,
        "check_mode": "continuous",
        "enable_risk_management": True,
        "max_daily_loss": 300.0,
        "max_trades_per_day": 150,
        "max_order_size": 1500.0,
        "max_position_size": 3000.0,
        "max_open_positions": 15,
        "max_positions_per_market": 1,
        "max_risk_per_trade": 0.015,
    },
    "SCALPER": {
        "fee_mode": "custom",
        "market_category": "crypto",
        "custom_fee_rate": 0.02,
        "maker_fee_rate": 0.0,
        "enable_rebates": True,
        "rebate_tiers": {
            0: 0.00,
            1000: 0.10,
            5000: 0.15,
            10000: 0.20,
            50000: 0.25,
        },
        "maker_rebate_pct": 0.25,
        "execution_delay_ms": 50,
        "delay_randomness": 0.1,
        "slippage_pct": 0.02,
        "slippage_randomness": 0.05,
        "max_slippage_no_fill": 0.03,
        "fill_probability": 0.98,
        "check_mode": "continuous",
        "enable_risk_management": True,
        "max_daily_loss": 200.0,
        "max_trades_per_day": 500,
        "max_order_size": 100.0,
        "max_position_size": 300.0,
        "max_open_positions": 3,
        "max_positions_per_market": 1,
        "max_risk_per_trade": 0.005,
    },
    "TEST": {
        "fee_mode": "zero",
        "market_category": "crypto",
        "custom_fee_rate": 0.0,
        "maker_fee_rate": 0.0,
        "enable_rebates": False,
        "rebate_tiers": {},
        "maker_rebate_pct": 0.0,
        "execution_delay_ms": 0,
        "delay_randomness": 0.0,
        "slippage_pct": 0.0,
        "slippage_randomness": 0.0,
        "max_slippage_no_fill": 0.10,
        "fill_probability": 1.0,
        "check_mode": "continuous",
        "enable_risk_management": False,
        "max_daily_loss": 10000.0,
        "max_trades_per_day": 1000,
        "max_order_size": 10000.0,
        "max_position_size": 10000.0,
        "max_open_positions": 100,
        "max_positions_per_market": 100,
        "max_risk_per_trade": 1.0,
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


def get_paper_config_from_preset(name: str):
    """
    Get a PaperConfig object from a preset name.

    Parameters
    ----------
    name : str
        The name of the preset to use.

    Returns
    -------
    PaperConfig
        A PaperConfig object initialized with the preset values.

    Raises
    ------
    ValueError
        If the preset name is not found.
    """
    from .paper import PaperConfig
    
    config_dict = get_preset(name)
    return PaperConfig(**config_dict)


# ── Example Usage (commented out) ─────────────────────────────────────────────

# Example of how to use these presets:
#
# from polyalpha.trading.paper_config import get_preset, get_paper_config_from_preset
# from polyalpha.trading.paper import PaperConfig
# import polyalpha
#
# # Use a pre-configured preset
# config_dict = get_preset("REALISTIC")
# config = PaperConfig(**config_dict)
# client = polyalpha.Client(balance=1000.0, paper_config=config)
#
# # Or get a PaperConfig directly
# config = get_paper_config_from_preset("AGGRESSIVE")
# client = polyalpha.Client(balance=1000.0, paper_config=config)
#
# # List available presets
# from polyalpha.trading.paper_config import list_presets
# print(list_presets())
