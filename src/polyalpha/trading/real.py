"""Real trading — re-exports from specialized sub-modules.

This module has been split into:
    - real_config.py     → RealTradingConfig
    - real_orders.py     → RealOrder, RealPosition, OCOOrder, BracketOrder, etc.
    - real_position_sizing.py → PositionSizer, FixedPositionSizer, etc.
    - real_risk.py       → RiskManager
    - real_wallet.py     → WalletManager
    - real_engine.py     → RealTradingEngine
"""

from .real_config import RealTradingConfig
from .real_orders import (
    RealOrder,
    RealPosition,
    OCOOrder,
    BracketOrder,
    ConditionalOrder,
    IcebergOrder,
    TWAPOrder,
    _validate_side,
    _validate_positive,
    _now,
)
from .real_position_sizing import (
    PositionSizer,
    FixedPositionSizer,
    PercentagePositionSizer,
    KellyPositionSizer,
    HybridPositionSizer,
)
from .real_risk import RiskManager
from .real_wallet import WalletManager
from .real_engine import RealTradingEngine

__all__ = [
    "RealTradingConfig",
    "RealOrder",
    "RealPosition",
    "OCOOrder",
    "BracketOrder",
    "ConditionalOrder",
    "IcebergOrder",
    "TWAPOrder",
    "PositionSizer",
    "FixedPositionSizer",
    "PercentagePositionSizer",
    "KellyPositionSizer",
    "HybridPositionSizer",
    "RiskManager",
    "WalletManager",
    "RealTradingEngine",
]
