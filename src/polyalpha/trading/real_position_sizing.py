"""Position sizing strategies for real trading."""

from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Optional


class PositionSizer(ABC):
    """Abstract base class for position sizing strategies."""

    @abstractmethod
    def calculate_size(
        self,
        balance: float,
        market,
        side: str,
        confidence: float = 0.5,
        price: Optional[float] = None,
    ) -> float:
        """Calculate position size in USDC."""
        pass


class FixedPositionSizer(PositionSizer):
    """Fixed amount position sizing."""

    def __init__(self, amount: float):
        self.amount = amount

    def calculate_size(
        self,
        balance: float,
        market,
        side: str,
        confidence: float = 0.5,
        price: Optional[float] = None,
    ) -> float:
        return min(self.amount, balance)


class PercentagePositionSizer(PositionSizer):
    """Percentage of balance position sizing."""

    def __init__(self, percentage: float):
        self.percentage = percentage

    def calculate_size(
        self,
        balance: float,
        market,
        side: str,
        confidence: float = 0.5,
        price: Optional[float] = None,
    ) -> float:
        return balance * self.percentage


class KellyPositionSizer(PositionSizer):
    """
    Kelly criterion position sizing.

    Formula: f* = (bp - q) / b
    Where:
    - f* = fraction of bankroll to wager
    - b = odds received on the wager (decimal odds)
    - p = probability of winning
    - q = probability of losing (1 - p)

    For binary markets: f* = p - q/b = 2p - 1 (when odds are 1:1)
    """

    def __init__(self, kelly_fraction: float = 0.25, min_confidence: float = 0.55):
        self.kelly_fraction = kelly_fraction
        self.min_confidence = min_confidence

    def calculate_size(
        self,
        balance: float,
        market,
        side: str,
        confidence: float = 0.5,
        price: Optional[float] = None,
    ) -> float:
        if confidence < self.min_confidence:
            return 0.0

        implied_prob = price if price else (market.up_price if side == "UP" else market.down_price)

        if confidence <= implied_prob:
            return 0.0

        kelly_fraction = (confidence - implied_prob) / (1 - implied_prob)
        kelly_fraction *= self.kelly_fraction
        kelly_fraction = min(kelly_fraction, 0.5)

        return balance * kelly_fraction


class HybridPositionSizer(PositionSizer):
    """
    Hybrid position sizing combining multiple strategies.

    Strategies:
    - Base size from fixed or percentage
    - Adjust based on Kelly confidence
    - Apply risk limits
    """

    def __init__(
        self,
        base_strategy: str = "percentage",
        base_amount: float = 0.05,
        enable_kelly_adjustment: bool = True,
        kelly_fraction: float = 0.25,
        max_size: float = 1000.0,
        min_size: float = 1.0,
    ):
        self.base_strategy = base_strategy
        self.base_amount = base_amount
        self.enable_kelly_adjustment = enable_kelly_adjustment
        self.kelly_fraction = kelly_fraction
        self.max_size = max_size
        self.min_size = min_size

    def calculate_size(
        self,
        balance: float,
        market,
        side: str,
        confidence: float = 0.5,
        price: Optional[float] = None,
    ) -> float:
        if self.base_strategy == "fixed":
            size = min(self.base_amount, balance)
        else:
            size = balance * self.base_amount

        if self.enable_kelly_adjustment and confidence > 0.5:
            implied_prob = price if price else (market.up_price if side == "UP" else market.down_price)
            if confidence > implied_prob:
                kelly_adj = (confidence - implied_prob) / (1 - implied_prob) * self.kelly_fraction
                size *= (1 + kelly_adj)

        size = max(self.min_size, min(size, self.max_size))
        size = min(size, balance)

        return size
