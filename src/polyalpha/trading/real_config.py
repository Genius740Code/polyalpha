"""
Real trading configuration for Polymarket CLOB trading.

Provides the RealTradingConfig dataclass with safety checks and pre-configured
presets for different trading strategies.

Note: Authentication parameters (private_key, rpc_url, polymarket_api_key) are NOT
included in presets for security reasons. These must be provided separately when
initializing the Client.

Usage
-----
    from polyalpha.trading.real_config import RealTradingConfig, PRESETS, get_preset

    config = RealTradingConfig(
        private_key="your-private-key",
        rpc_url="https://polygon-rpc.com",
        polymarket_api_key="your-api-key",
    )

    # Or use a preset
    config_dict = get_preset("REALISTIC")
    config = RealTradingConfig(**config_dict)
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Optional


# ── Configuration ────────────────────────────────────────────────────────────────

@dataclass
class RealTradingConfig:
    """Configuration for real trading with safety checks."""

    # Authentication
    private_key: str
    rpc_url: str
    polymarket_api_key: str
    polymarket_api_secret: str = ""
    polymarket_api_passphrase: str = ""

    # Safety settings
    require_confirmation: bool = True
    max_order_size: float = 1000.0
    max_daily_loss: float = 500.0
    max_position_size: float = 2000.0
    max_open_positions: int = 10
    max_positions_per_market: int = 1

    # Position sizing strategy
    position_sizing: str = "fixed"
    fixed_amount: float = 10.0
    percentage_of_balance: float = 0.05
    kelly_fraction: float = 0.25

    # Risk management
    enable_stop_loss: bool = True
    default_stop_loss_pct: float = 0.20
    enable_take_profit: bool = True
    default_take_profit_pct: float = 0.50
    max_risk_per_trade: float = 0.02

    # Position management
    enable_position_scaling: bool = True
    min_profit_for_scaling: float = 0.10
    max_scale_additions: int = 3
    enable_position_reduction: bool = True
    enable_hedging: bool = True
    max_hedge_ratio: float = 0.5

    # Execution settings
    slippage_tolerance: float = 0.05
    order_timeout: int = 60
    retry_attempts: int = 3
    retry_delay: float = 1.0

    # Fee settings
    fee_mode: str = "polymarket"
    market_category: str = "crypto"
    custom_fee_rate: float = 0.02
    maker_fee_rate: float = 0.0

    # Logging
    log_all_orders: bool = True
    log_balance_updates: bool = True

    def __post_init__(self):
        """Validate configuration values."""
        if self.position_sizing not in ("fixed", "percentage", "kelly"):
            raise ValueError(
                f"position_sizing must be 'fixed', 'percentage', or 'kelly', "
                f"got '{self.position_sizing}'"
            )
        if self.fixed_amount < 0:
            raise ValueError(f"fixed_amount must be >= 0, got {self.fixed_amount}")
        if not 0 <= self.percentage_of_balance <= 1:
            raise ValueError(
                f"percentage_of_balance must be between 0 and 1, "
                f"got {self.percentage_of_balance}"
            )
        if not 0 <= self.kelly_fraction <= 1:
            raise ValueError(f"kelly_fraction must be between 0 and 1, got {self.kelly_fraction}")
        if self.max_order_size < 0:
            raise ValueError(f"max_order_size must be >= 0, got {self.max_order_size}")
        if self.max_daily_loss < 0:
            raise ValueError(f"max_daily_loss must be >= 0, got {self.max_daily_loss}")
        if self.max_position_size < 0:
            raise ValueError(f"max_position_size must be >= 0, got {self.max_position_size}")
        if self.max_open_positions < 1:
            raise ValueError(f"max_open_positions must be >= 1, got {self.max_open_positions}")
        if self.max_positions_per_market < 0:
            raise ValueError(f"max_positions_per_market must be >= 0, got {self.max_positions_per_market}")
        if not 0 <= self.default_stop_loss_pct <= 1:
            raise ValueError(
                f"default_stop_loss_pct must be between 0 and 1, "
                f"got {self.default_stop_loss_pct}"
            )
        if not 0 <= self.default_take_profit_pct <= 1:
            raise ValueError(
                f"default_take_profit_pct must be between 0 and 1, "
                f"got {self.default_take_profit_pct}"
            )
        if not 0 <= self.max_risk_per_trade <= 1:
            raise ValueError(
                f"max_risk_per_trade must be between 0 and 1, got {self.max_risk_per_trade}"
            )
        if not 0 <= self.slippage_tolerance <= 1:
            raise ValueError(
                f"slippage_tolerance must be between 0 and 1, got {self.slippage_tolerance}"
            )
        if self.order_timeout < 1:
            raise ValueError(f"order_timeout must be >= 1, got {self.order_timeout}")
        if self.retry_attempts < 1:
            raise ValueError(f"retry_attempts must be >= 1, got {self.retry_attempts}")
        if self.retry_delay < 0:
            raise ValueError(f"retry_delay must be >= 0, got {self.retry_delay}")
        if self.fee_mode not in ("polymarket", "custom", "zero"):
            raise ValueError(
                f"fee_mode must be 'polymarket', 'custom', or 'zero', got '{self.fee_mode}'"
            )
        if self.custom_fee_rate < 0:
            raise ValueError(f"custom_fee_rate must be >= 0, got {self.custom_fee_rate}")
        if self.maker_fee_rate < 0:
            raise ValueError(f"maker_fee_rate must be >= 0, got {self.maker_fee_rate}")

    def __repr__(self) -> str:
        """Safe repr that does not expose the private key."""
        cls = self.__class__.__name__
        fields = []
        for field_name in ("rpc_url", "polymarket_api_key", "max_order_size",
                          "position_sizing", "fixed_amount", "fee_mode"):
            fields.append(f"{field_name}={getattr(self, field_name)!r}")
        return f"{cls}({', '.join(fields)}, private_key='****')"


# ── Configuration Presets ───────────────────────────────────────────────────────

PRESETS = {
    "CONSERVATIVE": {
        "require_confirmation": True,
        "max_order_size": 100.0,
        "max_daily_loss": 100.0,
        "max_position_size": 500.0,
        "max_open_positions": 5,
        "max_positions_per_market": 1,
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
        "max_positions_per_market": 1,
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
        "max_positions_per_market": 1,
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
        "max_positions_per_market": 10,
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
        "max_positions_per_market": 1,
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
        "max_positions_per_market": 1,
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
        "max_positions_per_market": 1,
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
        "max_positions_per_market": 100,
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


def get_real_config_from_preset(name: str, **kwargs):
    """
    Get a RealTradingConfig object from a preset name.

    Parameters
    ----------
    name : str
        The name of the preset to use.
    **kwargs
        Additional key-value pairs to override preset defaults
        or provide required fields like private_key, rpc_url, etc.

    Returns
    -------
    RealTradingConfig
        A RealTradingConfig object initialized with the preset values.

    Raises
    ------
    ValueError
        If the preset name is not found.
    """
    config_dict = get_preset(name)
    config_dict.update(kwargs)
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
