"""Helpers extracted from RealTradingEngine for slippage, fees, sizing, validation."""

from __future__ import annotations

import logging
from typing import Optional

from ..core import (
    FEE_ROUNDING,
    MAX_ORDER_PRICE,
    calculate_polymarket_fee,
    fee_rate_for_category,
)

log = logging.getLogger(__name__)


def validate_side(side: str) -> str:
    side = side.upper()
    if side not in ("UP", "DOWN"):
        raise ValueError(f"side must be 'UP' or 'DOWN', got '{side}'")
    return side


def validate_positive(value: float, name: str) -> float:
    if value <= 0:
        raise ValueError(f"{name} must be positive, got {value}")
    return value


def apply_buy_slippage(price: float, config, log_prefix: str = "Real") -> float:
    tolerance = getattr(config, "slippage_tolerance", 0.0)
    if tolerance <= 0 or price <= 0:
        return price
    adjusted = min(price * (1 + tolerance), MAX_ORDER_PRICE)
    if adjusted != price:
        logging.getLogger(__name__).debug(
            "%s: applied %.2f%% buy slippage: %.4f -> %.4f",
            log_prefix, tolerance * 100, price, adjusted,
        )
    return adjusted


def calculate_shares_and_fee(
    amount: float,
    price: float,
    config,
    *,
    is_maker: bool = False,
) -> tuple[float, float]:
    if price <= 0:
        return 0.0, 0.0

    shares_est = amount / price
    fee = _calculate_fee(amount, price, shares_est, config, is_maker=is_maker)

    net_trade = amount - fee
    if net_trade <= 0:
        return 0.0, fee

    shares = net_trade / price

    if getattr(config, "fee_mode", "polymarket") == "polymarket":
        fee = _calculate_fee(amount, price, shares, config, is_maker=is_maker)
        net_trade = amount - fee
        if net_trade <= 0:
            return 0.0, fee
        shares = net_trade / price

    return shares, fee


def _calculate_fee(amount: float, price: float, shares: float, config, *, is_maker: bool = False) -> float:
    fee_mode = getattr(config, "fee_mode", "polymarket")
    if fee_mode == "zero":
        return 0.0
    if fee_mode == "custom":
        fee_rate = getattr(config, "maker_fee_rate", 0.0) if is_maker else getattr(config, "custom_fee_rate", 0.02)
        return round(amount * fee_rate, FEE_ROUNDING)
    if fee_mode == "polymarket":
        return polymarket_fee(amount, price, shares, config, is_maker=is_maker)
    return 0.0


def polymarket_fee(amount: float, price: float, shares: float, config, *, is_maker: bool = False) -> float:
    if str(getattr(config, "market_category", "crypto")).lower() == "geopolitical":
        return 0.0
    fee_rate = fee_rate_for_category(str(getattr(config, "market_category", "crypto")))
    return calculate_polymarket_fee(shares, price, fee_rate)


def create_position_sizer(config):
    from .real_position_sizing import FixedPositionSizer, KellyPositionSizer, PercentagePositionSizer

    strategy = getattr(config, "position_sizing", "fixed")
    if strategy == "fixed":
        return FixedPositionSizer(amount=getattr(config, "fixed_amount", 10.0))
    if strategy == "percentage":
        return PercentagePositionSizer(percentage=getattr(config, "percentage_of_balance", 0.05))
    if strategy == "kelly":
        return KellyPositionSizer(
            kelly_fraction=getattr(config, "kelly_fraction", 0.25),
            min_confidence=0.55,
        )
    return FixedPositionSizer(amount=getattr(config, "fixed_amount", 10.0))
