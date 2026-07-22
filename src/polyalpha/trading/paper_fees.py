"""Fee calculation, rebates, slippage, and execution delay for paper trading."""

from __future__ import annotations

import logging
import random
import time
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from .paper_config import PaperConfig

from ..core import (
    TAKER_FEE_RATE,
    FEE_RATE_SPORTS,
    FEE_RATE_CRYPTO,
    FEE_RATE_ECONOMICS,
    MINIMUM_FEE,
    POLYMARKET_FEE_ROUNDING,
    FEE_ROUNDING,
)

log = logging.getLogger(__name__)


class PaperFeeManager:
    """Fee and rebate tracking for paper trading.

    Holds all fee/rebate/volume state and provides calculation methods.
    Composed into PaperEngine.
    """

    def __init__(self, config: PaperConfig):
        self.config = config
        self.total_fees_paid: float = 0.0
        self.total_rebates_earned: float = 0.0
        self.total_volume: float = 0.0
        self.taker_fees: float = 0.0
        self.maker_fees: float = 0.0
        self.taker_rebates: float = 0.0
        self.maker_rebates: float = 0.0

    def calculate_fee(
        self, amount: float, price: float, shares: float, is_maker: bool = False
    ) -> tuple[float, float, float, str]:
        if self.config.fee_mode == "zero":
            return 0.0, 0.0, 0.0, "taker"
        elif self.config.fee_mode == "custom":
            fee_rate = self.config.maker_fee_rate if is_maker else self.config.custom_fee_rate
            fee = round(amount * fee_rate, FEE_ROUNDING)
            fee_type = "maker" if is_maker else "taker"
            rebate_amount, rebate_rate = self._calculate_rebate(fee, fee_type)
            return fee, rebate_amount, rebate_rate, fee_type
        elif self.config.fee_mode == "polymarket":
            return self._polymarket_fee(amount, price, shares, is_maker)
        else:
            fee = round(amount * TAKER_FEE_RATE, FEE_ROUNDING)
            rebate_amount, rebate_rate = self._calculate_rebate(fee, "taker")
            return fee, rebate_amount, rebate_rate, "taker"

    def _polymarket_fee(
        self, amount: float, price: float, shares: float, is_maker: bool = False
    ) -> tuple[float, float, float, str]:
        if self.config.market_category.lower() == "geopolitical":
            return 0.0, 0.0, 0.0, "taker"

        category = self.config.market_category.lower()
        if category == "sports":
            fee_rate = FEE_RATE_SPORTS
        elif category in ("crypto", "finance", "politics", "tech"):
            fee_rate = FEE_RATE_CRYPTO
        elif category in ("economics", "culture", "weather", "other"):
            fee_rate = FEE_RATE_ECONOMICS
        else:
            fee_rate = FEE_RATE_CRYPTO

        exponent = 1
        fee = shares * price * fee_rate * (price * (1 - price)) ** exponent
        fee = round(fee, POLYMARKET_FEE_ROUNDING)
        if fee < MINIMUM_FEE:
            fee = 0.0

        fee_type = "maker" if is_maker else "taker"
        rebate_amount, rebate_rate = self._calculate_rebate(fee, fee_type)
        return fee, rebate_amount, rebate_rate, fee_type

    def _calculate_rebate(self, fee: float, fee_type: str) -> tuple[float, float]:
        if not self.config.enable_rebates or fee == 0:
            return 0.0, 0.0

        rebate_rate = self._get_volume_rebate_rate()
        if fee_type == "maker":
            rebate_rate += self.config.maker_rebate_pct

        rebate_rate = min(rebate_rate, 1.0)
        rebate_amount = round(fee * rebate_rate, FEE_ROUNDING)
        return rebate_amount, rebate_rate

    def _get_volume_rebate_rate(self) -> float:
        if not self.config.rebate_tiers:
            return 0.0

        thresholds = sorted(self.config.rebate_tiers.keys(), reverse=True)
        for threshold in thresholds:
            if self.total_volume >= threshold:
                return self.config.rebate_tiers[threshold]
        return 0.0

    def track_fee_and_rebate(self, fee: float, rebate: float, fee_type: str, amount: float) -> None:
        self.total_fees_paid += fee
        self.total_rebates_earned += rebate
        self.total_volume += amount

        if fee_type == "taker":
            self.taker_fees += fee
            self.taker_rebates += rebate
        else:
            self.maker_fees += fee
            self.maker_rebates += rebate

        log.debug(
            "Paper: fee tracked - total_fees=$%.4f, total_rebates=$%.4f, total_volume=$%.2f",
            self.total_fees_paid, self.total_rebates_earned, self.total_volume,
        )

    def apply_slippage(self, target_price: float, side: str) -> tuple[float, bool]:
        if self.config.slippage_pct == 0:
            return target_price, True

        slippage = target_price * self.config.slippage_pct
        if self.config.slippage_randomness > 0:
            random_factor = random.uniform(
                1 - self.config.slippage_randomness,
                1 + self.config.slippage_randomness,
            )
            slippage = slippage * random_factor

        if side == "UP":
            actual_price = target_price + slippage
        else:
            actual_price = target_price - slippage

        price_change_pct = abs(actual_price - target_price) / target_price
        if price_change_pct > self.config.max_slippage_no_fill:
            log.debug(
                "Paper: slippage %.2f%% exceeds max %.2f%% - order not filled",
                price_change_pct * 100, self.config.max_slippage_no_fill * 100,
            )
            return target_price, False

        return actual_price, True

    def apply_execution_delay(self) -> None:
        if self.config.execution_delay_ms == 0:
            return

        delay_ms = self.config.execution_delay_ms
        if self.config.delay_randomness > 0:
            random_factor = random.uniform(
                1 - self.config.delay_randomness,
                1 + self.config.delay_randomness,
            )
            delay_ms = int(delay_ms * random_factor)

        delay_seconds = delay_ms / 1000.0
        log.debug("Paper: applying execution delay of %.0fms", delay_ms)
        time.sleep(delay_seconds)

    def check_fill_probability(self) -> bool:
        if self.config.fill_probability >= 1.0:
            return True
        return random.random() < self.config.fill_probability
