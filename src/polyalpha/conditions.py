"""
Composable trading conditions for Bot strategies.

Usage
-----
    from polyalpha.conditions import rsi_above, price_above, and_

    bot = polyalpha.Bot("BTC", "5m", balance=500)
    bot.when(
        and_(rsi_above(50), price_above("up", 0.9))
    ).buy("UP", 20)
    bot.run()

Each condition is a callable that receives a TickContext and returns bool.
"""

from __future__ import annotations

from typing import Callable

from .bot import TickContext

# ── Protocol ───────────────────────────────────────────────────────────────────

class Condition:
    """
    Base class for trading conditions.

    Subclasses must implement __call__(ctx) -> bool.
    Conditions compose via and_(), or_(), not_().
    """

    def __call__(self, ctx: TickContext) -> bool:
        """Evaluate the condition against the current tick context."""
        raise NotImplementedError

    def __and__(self, other: Condition) -> Condition:
        return and_(self, other)

    def __or__(self, other: Condition) -> Condition:
        return or_(self, other)

    def __invert__(self) -> Condition:
        return not_(self)


# ── Combinators ────────────────────────────────────────────────────────────────

class AndCondition(Condition):
    """True when ALL sub-conditions are true (short-circuits)."""

    def __init__(self, *conditions: Condition):
        self._conditions = conditions

    def __call__(self, ctx: TickContext) -> bool:
        for c in self._conditions:
            if not c(ctx):
                return False
        return True


class OrCondition(Condition):
    """True when ANY sub-condition is true (short-circuits)."""

    def __init__(self, *conditions: Condition):
        self._conditions = conditions

    def __call__(self, ctx: TickContext) -> bool:
        for c in self._conditions:
            if c(ctx):
                return True
        return False


class NotCondition(Condition):
    """Inverts a sub-condition."""

    def __init__(self, condition: Condition):
        self._condition = condition

    def __call__(self, ctx: TickContext) -> bool:
        return not self._condition(ctx)


def and_(*conditions: Condition) -> Condition:
    """Compose conditions — all must be true."""
    return AndCondition(*conditions)


def or_(*conditions: Condition) -> Condition:
    """Compose conditions — any must be true."""
    return OrCondition(*conditions)


def not_(condition: Condition) -> Condition:
    """Invert a condition."""
    return NotCondition(condition)


# ── Lambda wrapper ─────────────────────────────────────────────────────────────

class LambdaCondition(Condition):
    """Wrap an arbitrary function as a Condition."""

    def __init__(self, fn: Callable[[TickContext], bool]):
        self._fn = fn

    def __call__(self, ctx: TickContext) -> bool:
        return self._fn(ctx)


# ── Pre-built conditions ──────────────────────────────────────────────────────

class RSIAbove(Condition):
    """True when RSI(14) is above a threshold."""

    def __init__(self, threshold: float):
        self._threshold = threshold

    def __call__(self, ctx: TickContext) -> bool:
        rsi = ctx.rsi
        if rsi is None:
            return False
        return rsi > self._threshold


class RSIBelow(Condition):
    """True when RSI(14) is below a threshold."""

    def __init__(self, threshold: float):
        self._threshold = threshold

    def __call__(self, ctx: TickContext) -> bool:
        rsi = ctx.rsi
        if rsi is None:
            return False
        return rsi < self._threshold


class PriceAbove(Condition):
    """True when the side's current price is above a threshold."""

    def __init__(self, side: str, threshold: float):
        if side.upper() not in ("UP", "DOWN"):
            raise ValueError(f"side must be 'UP' or 'DOWN', got {side!r}")
        self._side = side.lower()
        self._threshold = threshold

    def __call__(self, ctx: TickContext) -> bool:
        price = ctx.price.up if self._side == "up" else ctx.price.down
        return price > self._threshold


class PriceBelow(Condition):
    """True when the side's current price is below a threshold."""

    def __init__(self, side: str, threshold: float):
        if side.upper() not in ("UP", "DOWN"):
            raise ValueError(f"side must be 'UP' or 'DOWN', got {side!r}")
        self._side = side.lower()
        self._threshold = threshold

    def __call__(self, ctx: TickContext) -> bool:
        price = ctx.price.up if self._side == "up" else ctx.price.down
        return price < self._threshold


class CrossedAbove(Condition):
    """
    True when the side's price crossed *above* the threshold since the
    last tick. Returns False on the first tick (no history to compare).

    State is stored in the TickContext's ``_cross_state`` dict so the
    condition can be safely shared across independent Bot instances.
    """

    def __init__(self, side: str, threshold: float):
        if side.upper() not in ("UP", "DOWN"):
            raise ValueError(f"side must be 'UP' or 'DOWN', got {side!r}")
        self._side = side.lower()
        self._threshold = threshold

    def __call__(self, ctx: TickContext) -> bool:
        price = ctx.price.up if self._side == "up" else ctx.price.down
        key = id(self)
        prev = ctx._cross_state.get(key)
        if prev is None:
            ctx._cross_state[key] = price
            return False
        crossed = prev <= self._threshold < price
        ctx._cross_state[key] = price
        return crossed


class CrossedBelow(Condition):
    """
    True when the side's price crossed *below* the threshold since the
    last tick. Returns False on the first tick.

    State is stored in the TickContext's ``_cross_state`` dict so the
    condition can be safely shared across independent Bot instances.
    """

    def __init__(self, side: str, threshold: float):
        if side.upper() not in ("UP", "DOWN"):
            raise ValueError(f"side must be 'UP' or 'DOWN', got {side!r}")
        self._side = side.lower()
        self._threshold = threshold

    def __call__(self, ctx: TickContext) -> bool:
        price = ctx.price.up if self._side == "up" else ctx.price.down
        key = id(self)
        prev = ctx._cross_state.get(key)
        if prev is None:
            ctx._cross_state[key] = price
            return False
        crossed = prev >= self._threshold > price
        ctx._cross_state[key] = price
        return crossed


class EMAAbove(Condition):
    """True when the side's current price is above its EMA."""

    def __init__(self, side: str, period: int = 20):
        if side.upper() not in ("UP", "DOWN"):
            raise ValueError(f"side must be 'UP' or 'DOWN', got {side!r}")
        self._side = side.lower()
        self._period = period

    def __call__(self, ctx: TickContext) -> bool:
        price = ctx.price.up if self._side == "up" else ctx.price.down
        ema = ctx.indicators.ema(self._period)
        if ema is None:
            return False
        return price > ema


class EMABelow(Condition):
    """True when the side's current price is below its EMA."""

    def __init__(self, side: str, period: int = 20):
        if side.upper() not in ("UP", "DOWN"):
            raise ValueError(f"side must be 'UP' or 'DOWN', got {side!r}")
        self._side = side.lower()
        self._period = period

    def __call__(self, ctx: TickContext) -> bool:
        price = ctx.price.up if self._side == "up" else ctx.price.down
        ema = ctx.indicators.ema(self._period)
        if ema is None:
            return False
        return price < ema


class EMACrossedAbove(Condition):
    """
    True when the fast EMA crossed *above* the slow EMA since the last tick.

    Stores previous EMA values on the instance to detect the crossing.
    Returns False on the first evaluation (no history).
    """

    def __init__(self, fast: int = 9, slow: int = 21):
        if fast >= slow:
            raise ValueError("fast period must be less than slow period")
        self._fast = fast
        self._slow = slow
        self._prev_fast: float | None = None
        self._prev_slow: float | None = None

    def __call__(self, ctx: TickContext) -> bool:
        fast_val = ctx.indicators.ema(self._fast)
        slow_val = ctx.indicators.ema(self._slow)
        if fast_val is None or slow_val is None:
            return False
        if self._prev_fast is None or self._prev_slow is None:
            self._prev_fast = fast_val
            self._prev_slow = slow_val
            return False
        crossed = self._prev_fast <= self._prev_slow and fast_val > slow_val
        self._prev_fast = fast_val
        self._prev_slow = slow_val
        return crossed


class EMACrossedBelow(Condition):
    """
    True when the fast EMA crossed *below* the slow EMA since the last tick.

    Stores previous EMA values on the instance to detect the crossing.
    Returns False on the first evaluation (no history).
    """

    def __init__(self, fast: int = 9, slow: int = 21):
        if fast >= slow:
            raise ValueError("fast period must be less than slow period")
        self._fast = fast
        self._slow = slow
        self._prev_fast: float | None = None
        self._prev_slow: float | None = None

    def __call__(self, ctx: TickContext) -> bool:
        fast_val = ctx.indicators.ema(self._fast)
        slow_val = ctx.indicators.ema(self._slow)
        if fast_val is None or slow_val is None:
            return False
        if self._prev_fast is None or self._prev_slow is None:
            self._prev_fast = fast_val
            self._prev_slow = slow_val
            return False
        crossed = self._prev_fast >= self._prev_slow and fast_val < slow_val
        self._prev_fast = fast_val
        self._prev_slow = slow_val
        return crossed


class SuperTrendUp(Condition):
    """True when SuperTrend indicates an uptrend (direction == 1)."""

    def __init__(self, period: int = 7, multiplier: float = 3.0):
        self._period = period
        self._multiplier = multiplier

    def __call__(self, ctx: TickContext) -> bool:
        st = ctx.indicators.supertrend(self._period, self._multiplier)
        direction = st["direction"].dropna()
        if direction.empty:
            return False
        return direction.iloc[-1] == 1


class SuperTrendDown(Condition):
    """True when SuperTrend indicates a downtrend (direction == -1)."""

    def __init__(self, period: int = 7, multiplier: float = 3.0):
        self._period = period
        self._multiplier = multiplier

    def __call__(self, ctx: TickContext) -> bool:
        st = ctx.indicators.supertrend(self._period, self._multiplier)
        direction = st["direction"].dropna()
        if direction.empty:
            return False
        return direction.iloc[-1] == -1


class SuperTrendJustTurnedUp(Condition):
    """True when SuperTrend just flipped from downtrend to uptrend."""

    def __init__(self, period: int = 7, multiplier: float = 3.0):
        self._period = period
        self._multiplier = multiplier

    def __call__(self, ctx: TickContext) -> bool:
        st = ctx.indicators.supertrend(self._period, self._multiplier)
        direction = st["direction"].dropna()
        if len(direction) < 2:
            return False
        return direction.iloc[-2] == -1 and direction.iloc[-1] == 1


class SuperTrendJustTurnedDown(Condition):
    """True when SuperTrend just flipped from uptrend to downtrend."""

    def __init__(self, period: int = 7, multiplier: float = 3.0):
        self._period = period
        self._multiplier = multiplier

    def __call__(self, ctx: TickContext) -> bool:
        st = ctx.indicators.supertrend(self._period, self._multiplier)
        direction = st["direction"].dropna()
        if len(direction) < 2:
            return False
        return direction.iloc[-2] == 1 and direction.iloc[-1] == -1


class Always(Condition):
    """Always true — useful as a default / fallthrough."""

    def __call__(self, ctx: TickContext) -> bool:
        return True


class Never(Condition):
    """Always false."""

    def __call__(self, ctx: TickContext) -> bool:
        return False


# ── Factory functions ──────────────────────────────────────────────────────────

def rsi_above(threshold: float) -> Condition:
    """RSI(14) > threshold."""
    return RSIAbove(threshold)


def rsi_below(threshold: float) -> Condition:
    """RSI(14) < threshold."""
    return RSIBelow(threshold)


def price_above(side: str, threshold: float) -> Condition:
    """side ("UP"|"DOWN") current price > threshold."""
    return PriceAbove(side, threshold)


def price_below(side: str, threshold: float) -> Condition:
    """side ("UP"|"DOWN") current price < threshold."""
    return PriceBelow(side, threshold)


def crossed_above(side: str, threshold: float) -> Condition:
    """side price crossed above threshold since last tick."""
    return CrossedAbove(side, threshold)


def crossed_below(side: str, threshold: float) -> Condition:
    """side price crossed below threshold since last tick."""
    return CrossedBelow(side, threshold)


def ema_above(side: str, period: int = 20) -> Condition:
    """side ("UP"|"DOWN") current price > EMA(period)."""
    return EMAAbove(side, period)


def ema_below(side: str, period: int = 20) -> Condition:
    """side ("UP"|"DOWN") current price < EMA(period)."""
    return EMABelow(side, period)


def ema_crossed_above(fast: int = 9, slow: int = 21) -> Condition:
    """fast EMA crossed above slow EMA since last tick."""
    return EMACrossedAbove(fast, slow)


def ema_crossed_below(fast: int = 9, slow: int = 21) -> Condition:
    """fast EMA crossed below slow EMA since last tick."""
    return EMACrossedBelow(fast, slow)


def always() -> Condition:
    """Condition that is always true."""
    return Always()


def never() -> Condition:
    """Condition that is always false."""
    return Never()


def supertrend_up(period: int = 7, multiplier: float = 3.0) -> Condition:
    """SuperTrend indicates an uptrend."""
    return SuperTrendUp(period, multiplier)


def supertrend_down(period: int = 7, multiplier: float = 3.0) -> Condition:
    """SuperTrend indicates a downtrend."""
    return SuperTrendDown(period, multiplier)


def supertrend_just_turned_up(period: int = 7, multiplier: float = 3.0) -> Condition:
    """SuperTrend just flipped from downtrend to uptrend."""
    return SuperTrendJustTurnedUp(period, multiplier)


def supertrend_just_turned_down(period: int = 7, multiplier: float = 3.0) -> Condition:
    """SuperTrend just flipped from uptrend to downtrend."""
    return SuperTrendJustTurnedDown(period, multiplier)


def when(fn: Callable[[TickContext], bool]) -> Condition:
    """Wrap a lambda as a Condition."""
    return LambdaCondition(fn)


__all__ = [
    "Condition",
    "and_",
    "or_",
    "not_",
    "rsi_above",
    "rsi_below",
    "price_above",
    "price_below",
    "crossed_above",
    "crossed_below",
    "ema_above",
    "ema_below",
    "ema_crossed_above",
    "ema_crossed_below",
    "supertrend_up",
    "supertrend_down",
    "supertrend_just_turned_up",
    "supertrend_just_turned_down",
    "always",
    "never",
    "when",
]
