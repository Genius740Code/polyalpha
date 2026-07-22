"""
Backward-compatible re-export shim for the paper trading modules.

The monolithic paper.py was split into focused modules:
  - paper_config.py    → PaperConfig
  - paper_types.py     → PaperOrder, PaperPosition, helpers
  - paper_risk.py      → RiskManager
  - paper_fees.py      → PaperFeeManager
  - paper_reporting.py → display/summary functions
  - paper_engine.py    → PaperEngine

This shim re-exports all public names so existing imports continue to work.
"""

from __future__ import annotations

from .paper_config import PaperConfig
from .paper_types import (
    PaperOrder,
    PaperPosition,
    new_id as _new_id,
    now as _now,
    slug_label as _slug_label,
    validate_market as _validate_market,
    validate_side as _validate_side,
    validate_positive as _validate_positive,
    validate_price as _validate_price,
)
from .paper_risk import RiskManager
from .paper_engine import PaperEngine

__all__ = [
    "PaperConfig",
    "PaperOrder",
    "PaperPosition",
    "RiskManager",
    "PaperEngine",
]
