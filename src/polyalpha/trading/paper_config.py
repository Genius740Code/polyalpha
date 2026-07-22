"""
Paper trading configuration and presets.

This module provides PaperConfig dataclass and pre-configured presets
for different paper trading strategies.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Optional


# ── Configuration ────────────────────────────────────────────────────────────────


@dataclass
class PaperConfig:
    """Configuration for paper trading realism options."""
    # Fee configuration
    fee_mode: str = "custom"  # "polymarket", "custom", or "zero"
    custom_fee_rate: float = 0.02  # Used when fee_mode="custom"
    market_category: str = "crypto"  # For polymarket mode: "crypto", "sports", "geopolitical", etc.
    maker_fee_rate: float = 0.0  # Separate maker fee (optional)

    # Fee rebate configuration
    enable_rebates: bool = True  # Enable fee rebate tracking
    rebate_tiers: dict = field(default_factory=lambda: {
        0: 0.00,    # $0 - $1000: 0% rebate
        1000: 0.10,  # $1000 - $5000: 10% rebate
        5000: 0.15,  # $5000 - $10000: 15% rebate
        10000: 0.20, # $10000 - $50000: 20% rebate
        50000: 0.25, # $50000+: 25% rebate
    })  # Volume-based rebate tiers (volume_threshold: rebate_rate)
    maker_rebate_pct: float = 0.25  # Additional rebate for maker orders (on top of tier)

    # Execution delay
    execution_delay_ms: int = 0  # Delay in milliseconds (0 = no delay)
    delay_randomness: float = 0.0  # Random variation as percentage (0-1)

    # Slippage
    slippage_pct: float = 0.0  # Slippage percentage (e.g., 0.05 for 5%)
    slippage_randomness: float = 0.0  # Random variation as percentage (0-1)
    max_slippage_no_fill: float = 0.10  # If price moves beyond this, order doesn't fill

    # Fill probability
    fill_probability: float = 1.0  # Default 100% fill

    # Condition check mode for limit orders
    check_mode: str | int = "continuous"  # "continuous", "once", or int for N times

    # Risk management settings
    enable_risk_management: bool = True  # Enable risk management checks
    max_daily_loss: float = 500.0  # Stop trading if daily loss exceeds this (USDC)
    max_trades_per_day: int = 100  # Maximum number of trades per day
    max_order_size: float = 1000.0  # Maximum USDC per order
    max_position_size: float = 2000.0  # Maximum position size per market (USDC)
    max_open_positions: int = 10  # Maximum concurrent positions (global)
    max_positions_per_market: int = 1  # Maximum concurrent positions per individual market (None = no limit)
    max_risk_per_trade: float = 0.02  # Maximum risk per trade as percentage of balance (2%)

    def __post_init__(self):
        """Validate configuration values."""
        if self.fee_mode not in ("polymarket", "custom", "zero"):
            raise ValueError(f"fee_mode must be 'polymarket', 'custom', or 'zero', got '{self.fee_mode}'")
        if self.custom_fee_rate < 0:
            raise ValueError(f"custom_fee_rate must be >= 0, got {self.custom_fee_rate}")
        if self.maker_fee_rate < 0:
            raise ValueError(f"maker_fee_rate must be >= 0, got {self.maker_fee_rate}")
        if self.execution_delay_ms < 0:
            raise ValueError(f"execution_delay_ms must be >= 0, got {self.execution_delay_ms}")
        if not 0 <= self.delay_randomness <= 1:
            raise ValueError(f"delay_randomness must be between 0 and 1, got {self.delay_randomness}")
        if self.slippage_pct < 0:
            raise ValueError(f"slippage_pct must be >= 0, got {self.slippage_pct}")
        if not 0 <= self.slippage_randomness <= 1:
            raise ValueError(f"slippage_randomness must be between 0 and 1, got {self.slippage_randomness}")
        if not 0 <= self.max_slippage_no_fill <= 1:
            raise ValueError(f"max_slippage_no_fill must be between 0 and 1, got {self.max_slippage_no_fill}")
        if not 0 <= self.fill_probability <= 1:
            raise ValueError(f"fill_probability must be between 0 and 1, got {self.fill_probability}")
        if isinstance(self.check_mode, str) and self.check_mode not in ("continuous", "once"):
            raise ValueError(f"check_mode must be 'continuous', 'once', or a positive integer, got '{self.check_mode}'")
        if isinstance(self.check_mode, int) and self.check_mode < 1:
            raise ValueError(f"check_mode as integer must be >= 1, got {self.check_mode}")
        if not 0 <= self.maker_rebate_pct <= 1:
            raise ValueError(f"maker_rebate_pct must be between 0 and 1, got {self.maker_rebate_pct}")
        if self.rebate_tiers:
            thresholds = sorted(self.rebate_tiers.keys())
            rates = [self.rebate_tiers[t] for t in thresholds]
            if any(not 0 <= r <= 1 for r in rates):
                raise ValueError(f"Rebate rates must be between 0 and 1")
        if self.max_daily_loss < 0:
            raise ValueError(f"max_daily_loss must be >= 0, got {self.max_daily_loss}")
        if self.max_trades_per_day < 0:
            raise ValueError(f"max_trades_per_day must be >= 0, got {self.max_trades_per_day}")
        if self.max_order_size < 0:
            raise ValueError(f"max_order_size must be >= 0, got {self.max_order_size}")
        if self.max_position_size < 0:
            raise ValueError(f"max_position_size must be >= 0, got {self.max_position_size}")
        if self.max_open_positions < 0:
            raise ValueError(f"max_open_positions must be >= 0, got {self.max_open_positions}")
        if self.max_positions_per_market < 0:
            raise ValueError(f"max_positions_per_market must be >= 0, got {self.max_positions_per_market}")
        if not 0 <= self.max_risk_per_trade <= 1:
            raise ValueError(f"max_risk_per_trade must be between 0 and 1, got {self.max_risk_per_trade}")


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


def get_paper_config_from_preset(name: str) -> PaperConfig:
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
    config_dict = get_preset(name)
    return PaperConfig(**config_dict)
