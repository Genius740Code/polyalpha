from .paper_engine import PaperEngine
from .paper_types import PaperOrder, PaperPosition
from .real_config import RealTradingConfig
from .real_orders import RealOrder, RealPosition
from .real_engine import RealTradingEngine
from .real_wallet import WalletManager as BlockchainWalletManager
from .real_wallet import WalletManager
from .wallet import PaperWallet, RealWallet, RealTradingWalletManager, WalletSelectionStrategy
# New unified helpers (optional imports)
from .engine_protocol import TradingEngineProtocol
from .staleness import get_price_for_side
from .base_risk import BaseRiskManager
from .real_helpers import validate_side, validate_positive, apply_buy_slippage, calculate_shares_and_fee
from .auto_redeem import (
    AutoRedeemEngine,
    AutoRedeemConfig,
    RedeemablePosition,
    RedeemRecord,
    RedeemResult,
)
from .retry import retry_on_error, retry_with_jitter
from .real_config import (
    PRESETS as REAL_PRESETS,
    list_presets as list_real_presets,
    get_preset as get_real_preset,
    print_preset as print_real_preset,
    add_preset as add_real_preset,
    get_real_config_from_preset,
)

__all__ = [
    "PaperEngine",
    "PaperOrder",
    "PaperPosition",
    "RealTradingEngine",
    "RealTradingConfig",
    "RealOrder",
    "RealPosition",
    "WalletManager",
    "BlockchainWalletManager",
    "PaperWallet",
    "RealWallet",
    "RealTradingWalletManager",
    "WalletSelectionStrategy",
    "AutoRedeemEngine",
    "AutoRedeemConfig",
    "RedeemablePosition",
    "RedeemRecord",
    "RedeemResult",
    "retry_on_error",
    "retry_with_jitter",
    "REAL_PRESETS",
    "list_real_presets",
    "get_real_preset",
    "print_real_preset",
    "add_real_preset",
    "get_real_config_from_preset",
    "TradingEngineProtocol",
    "get_price_for_side",
    "BaseRiskManager",
]
