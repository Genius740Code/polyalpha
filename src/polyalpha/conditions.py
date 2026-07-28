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


class PriceInRange(Condition):
    """True when the side's current price is in range [min_price, max_price]."""

    def __init__(self, side: str, min_price: float, max_price: float):
        if side.upper() not in ("UP", "DOWN"):
            raise ValueError(f"side must be 'UP' or 'DOWN', got {side!r}")
        if not (0 < min_price < 1):
            raise ValueError(f"min_price must be between 0 and 1, got {min_price}")
        if not (0 < max_price < 1):
            raise ValueError(f"max_price must be between 0 and 1, got {max_price}")
        if min_price >= max_price:
            raise ValueError(f"min_price ({min_price}) must be less than max_price ({max_price})")
        self._side = side.lower()
        self._min_price = min_price
        self._max_price = max_price

    def __call__(self, ctx: TickContext) -> bool:
        price = ctx.price.up if self._side == "up" else ctx.price.down
        return self._min_price <= price <= self._max_price


class PriceNotInRanges(Condition):
    """True when the side's current price is NOT in any of the excluded ranges."""

    def __init__(self, side: str, ranges: list[tuple[float, float]]):
        if side.upper() not in ("UP", "DOWN"):
            raise ValueError(f"side must be 'UP' or 'DOWN', got {side!r}")
        if not ranges:
            raise ValueError("ranges must be a non-empty list")
        for i, (min_price, max_price) in enumerate(ranges):
            if not (0 < min_price < 1):
                raise ValueError(f"ranges[{i}][0] (min) must be between 0 and 1, got {min_price}")
            if not (0 < max_price < 1):
                raise ValueError(f"ranges[{i}][1] (max) must be between 0 and 1, got {max_price}")
            if min_price >= max_price:
                raise ValueError(f"ranges[{i}] min ({min_price}) must be less than max ({max_price})")
        self._side = side.lower()
        self._ranges = ranges

    def __call__(self, ctx: TickContext) -> bool:
        price = ctx.price.up if self._side == "up" else ctx.price.down
        for min_price, max_price in self._ranges:
            if min_price <= price <= max_price:
                return False
        return True


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


# ── Donchian Channel Conditions ────────────────────────────────────────────────

class PriceAboveDCUpper(Condition):
    """True when price is above the upper Donchian Channel."""

    def __init__(self, side: str, length: int = 20):
        if side.upper() not in ("UP", "DOWN"):
            raise ValueError(f"side must be 'UP' or 'DOWN', got {side!r}")
        self._side = side.lower()
        self._length = length

    def __call__(self, ctx: TickContext) -> bool:
        price = ctx.price.up if self._side == "up" else ctx.price.down
        dc = ctx.indicators.donchian(self._length)
        if dc is None:
            return False
        return price > dc.upper


class PriceBelowDCLower(Condition):
    """True when price is below the lower Donchian Channel."""

    def __init__(self, side: str, length: int = 20):
        if side.upper() not in ("UP", "DOWN"):
            raise ValueError(f"side must be 'UP' or 'DOWN', got {side!r}")
        self._side = side.lower()
        self._length = length

    def __call__(self, ctx: TickContext) -> bool:
        price = ctx.price.up if self._side == "up" else ctx.price.down
        dc = ctx.indicators.donchian(self._length)
        if dc is None:
            return False
        return price < dc.lower


# ── PSAR Conditions ────────────────────────────────────────────────────────────

class PSARUptrend(Condition):
    """True when PSAR indicates an uptrend (trend == 1)."""

    def __init__(self, af: float = 0.02, af_max: float = 0.2):
        self._af = af
        self._af_max = af_max

    def __call__(self, ctx: TickContext) -> bool:
        psar = ctx.indicators.psar(self._af, self._af_max)
        trend = psar["trend"].dropna()
        if trend.empty:
            return False
        return trend.iloc[-1] == 1


class PSARDowntrend(Condition):
    """True when PSAR indicates a downtrend (trend == -1)."""

    def __init__(self, af: float = 0.02, af_max: float = 0.2):
        self._af = af
        self._af_max = af_max

    def __call__(self, ctx: TickContext) -> bool:
        psar = ctx.indicators.psar(self._af, self._af_max)
        trend = psar["trend"].dropna()
        if trend.empty:
            return False
        return trend.iloc[-1] == -1


class PSARJustTurnedUp(Condition):
    """True when PSAR just flipped from downtrend to uptrend."""

    def __init__(self, af: float = 0.02, af_max: float = 0.2):
        self._af = af
        self._af_max = af_max

    def __call__(self, ctx: TickContext) -> bool:
        psar = ctx.indicators.psar(self._af, self._af_max)
        trend = psar["trend"].dropna()
        if len(trend) < 2:
            return False
        return trend.iloc[-2] == -1 and trend.iloc[-1] == 1


class PSARJustTurnedDown(Condition):
    """True when PSAR just flipped from uptrend to downtrend."""

    def __init__(self, af: float = 0.02, af_max: float = 0.2):
        self._af = af
        self._af_max = af_max

    def __call__(self, ctx: TickContext) -> bool:
        psar = ctx.indicators.psar(self._af, self._af_max)
        trend = psar["trend"].dropna()
        if len(trend) < 2:
            return False
        return trend.iloc[-2] == 1 and trend.iloc[-1] == -1


# ── Ichimoku Conditions ────────────────────────────────────────────────────────

class IchimokuTenkanAboveKijun(Condition):
    """True when Tenkan-sen is above Kijun-sen."""

    def __init__(self, tenkan: int = 9, kijun: int = 26):
        self._tenkan = tenkan
        self._kijun = kijun

    def __call__(self, ctx: TickContext) -> bool:
        ichi = ctx.indicators.ichimoku(self._tenkan, self._kijun)
        tenkan_val = ctx.indicators.get_latest_value(ichi["tenkan"])
        kijun_val = ctx.indicators.get_latest_value(ichi["kijun"])
        if tenkan_val is None or kijun_val is None:
            return False
        return tenkan_val > kijun_val


class IchimokuTenkanBelowKijun(Condition):
    """True when Tenkan-sen is below Kijun-sen."""

    def __init__(self, tenkan: int = 9, kijun: int = 26):
        self._tenkan = tenkan
        self._kijun = kijun

    def __call__(self, ctx: TickContext) -> bool:
        ichi = ctx.indicators.ichimoku(self._tenkan, self._kijun)
        tenkan_val = ctx.indicators.get_latest_value(ichi["tenkan"])
        kijun_val = ctx.indicators.get_latest_value(ichi["kijun"])
        if tenkan_val is None or kijun_val is None:
            return False
        return tenkan_val < kijun_val


class IchimokuPriceAboveCloud(Condition):
    """True when price is above the Ichimoku cloud."""

    def __init__(self, side: str, tenkan: int = 9, kijun: int = 26, senkou: int = 52):
        if side.upper() not in ("UP", "DOWN"):
            raise ValueError(f"side must be 'UP' or 'DOWN', got {side!r}")
        self._side = side.lower()
        self._tenkan = tenkan
        self._kijun = kijun
        self._senkou = senkou

    def __call__(self, ctx: TickContext) -> bool:
        price = ctx.price.up if self._side == "up" else ctx.price.down
        ichi = ctx.indicators.ichimoku(self._tenkan, self._kijun, self._senkou)
        cloud = ichi.get("cloud")
        if cloud is None:
            return False
        top = ctx.indicators.get_latest_value(cloud["top"])
        if top is None:
            return False
        return price > top


class IchimokuPriceBelowCloud(Condition):
    """True when price is below the Ichimoku cloud."""

    def __init__(self, side: str, tenkan: int = 9, kijun: int = 26, senkou: int = 52):
        if side.upper() not in ("UP", "DOWN"):
            raise ValueError(f"side must be 'UP' or 'DOWN', got {side!r}")
        self._side = side.lower()
        self._tenkan = tenkan
        self._kijun = kijun
        self._senkou = senkou

    def __call__(self, ctx: TickContext) -> bool:
        price = ctx.price.up if self._side == "up" else ctx.price.down
        ichi = ctx.indicators.ichimoku(self._tenkan, self._kijun, self._senkou)
        cloud = ichi.get("cloud")
        if cloud is None:
            return False
        bottom = ctx.indicators.get_latest_value(cloud["bottom"])
        if bottom is None:
            return False
        return price < bottom


class IchimokuBullishBreakout(Condition):
    """True for combined bullish Ichimoku breakout: price above cloud + TK bullish."""

    def __init__(self, side: str, tenkan: int = 9, kijun: int = 26, senkou: int = 52):
        if side.upper() not in ("UP", "DOWN"):
            raise ValueError(f"side must be 'UP' or 'DOWN', got {side!r}")
        self._side = side.lower()
        self._tenkan = tenkan
        self._kijun = kijun
        self._senkou = senkou

    def __call__(self, ctx: TickContext) -> bool:
        ichi = ctx.indicators.ichimoku(self._tenkan, self._kijun, self._senkou)
        cloud = ichi.get("cloud")
        if cloud is None:
            return False
        tenkan_val = ctx.indicators.get_latest_value(ichi["tenkan"])
        kijun_val = ctx.indicators.get_latest_value(ichi["kijun"])
        top = ctx.indicators.get_latest_value(cloud["top"])
        price = ctx.price.up if self._side == "up" else ctx.price.down
        if tenkan_val is None or kijun_val is None or top is None:
            return False
        return price > top and tenkan_val > kijun_val


class IchimokuBearishBreakout(Condition):
    """True for combined bearish Ichimoku breakout: price below cloud + TK bearish."""

    def __init__(self, side: str, tenkan: int = 9, kijun: int = 26, senkou: int = 52):
        if side.upper() not in ("UP", "DOWN"):
            raise ValueError(f"side must be 'UP' or 'DOWN', got {side!r}")
        self._side = side.lower()
        self._tenkan = tenkan
        self._kijun = kijun
        self._senkou = senkou

    def __call__(self, ctx: TickContext) -> bool:
        ichi = ctx.indicators.ichimoku(self._tenkan, self._kijun, self._senkou)
        cloud = ichi.get("cloud")
        if cloud is None:
            return False
        tenkan_val = ctx.indicators.get_latest_value(ichi["tenkan"])
        kijun_val = ctx.indicators.get_latest_value(ichi["kijun"])
        bottom = ctx.indicators.get_latest_value(cloud["bottom"])
        price = ctx.price.up if self._side == "up" else ctx.price.down
        if tenkan_val is None or kijun_val is None or bottom is None:
            return False
        return price < bottom and tenkan_val < kijun_val


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


def price_in_range(side: str, min_price: float, max_price: float) -> Condition:
    """side ("UP"|"DOWN") current price is in range [min_price, max_price]."""
    return PriceInRange(side, min_price, max_price)


def price_not_in_ranges(side: str, ranges: list[tuple[float, float]]) -> Condition:
    """side ("UP"|"DOWN") current price is NOT in any of the excluded ranges."""
    return PriceNotInRanges(side, ranges)


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


def price_above_dc_upper(side: str, length: int = 20) -> Condition:
    """Price is above upper Donchian Channel."""
    return PriceAboveDCUpper(side, length)


def price_below_dc_lower(side: str, length: int = 20) -> Condition:
    """Price is below lower Donchian Channel."""
    return PriceBelowDCLower(side, length)


def psar_uptrend(af: float = 0.02, af_max: float = 0.2) -> Condition:
    """PSAR indicates an uptrend."""
    return PSARUptrend(af, af_max)


def psar_downtrend(af: float = 0.02, af_max: float = 0.2) -> Condition:
    """PSAR indicates a downtrend."""
    return PSARDowntrend(af, af_max)


def psar_just_turned_up(af: float = 0.02, af_max: float = 0.2) -> Condition:
    """PSAR just flipped from downtrend to uptrend."""
    return PSARJustTurnedUp(af, af_max)


def psar_just_turned_down(af: float = 0.02, af_max: float = 0.2) -> Condition:
    """PSAR just flipped from uptrend to downtrend."""
    return PSARJustTurnedDown(af, af_max)


def ichimoku_tenkan_above_kijun(tenkan: int = 9, kijun: int = 26) -> Condition:
    """Tenkan-sen is above Kijun-sen."""
    return IchimokuTenkanAboveKijun(tenkan, kijun)


def ichimoku_tenkan_below_kijun(tenkan: int = 9, kijun: int = 26) -> Condition:
    """Tenkan-sen is below Kijun-sen."""
    return IchimokuTenkanBelowKijun(tenkan, kijun)


def ichimoku_price_above_cloud(side: str, tenkan: int = 9, kijun: int = 26, senkou: int = 52) -> Condition:
    """Price is above the Ichimoku cloud."""
    return IchimokuPriceAboveCloud(side, tenkan, kijun, senkou)


def ichimoku_price_below_cloud(side: str, tenkan: int = 9, kijun: int = 26, senkou: int = 52) -> Condition:
    """Price is below the Ichimoku cloud."""
    return IchimokuPriceBelowCloud(side, tenkan, kijun, senkou)


def ichimoku_bullish_breakout(side: str, tenkan: int = 9, kijun: int = 26, senkou: int = 52) -> Condition:
    """Combined bullish Ichimoku breakout."""
    return IchimokuBullishBreakout(side, tenkan, kijun, senkou)


def ichimoku_bearish_breakout(side: str, tenkan: int = 9, kijun: int = 26, senkou: int = 52) -> Condition:
    """Combined bearish Ichimoku breakout."""
    return IchimokuBearishBreakout(side, tenkan, kijun, senkou)


def when(fn: Callable[[TickContext], bool]) -> Condition:
    """Wrap a lambda as a Condition."""
    return LambdaCondition(fn)


# ── MACD Conditions (from Binance data via ctx.binance) ─────────────────────────

class MACDBullishCrossover(Condition):
    """True when MACD line crossed above signal line on Binance BTC data."""

    def __init__(self, fast: int = 12, slow: int = 26, signal: int = 9):
        if fast >= slow:
            raise ValueError("fast period must be less than slow period")
        self._fast = fast
        self._slow = slow
        self._signal = signal
        self._prev_macd: float | None = None
        self._prev_signal: float | None = None

    def __call__(self, ctx: TickContext) -> bool:
        binance = ctx.binance
        if binance is None:
            return False
        result = binance.macd(self._fast, self._slow, self._signal)
        if result is None:
            return False
        macd_v, sig_v = result.macd, result.signal
        if self._prev_macd is None or self._prev_signal is None:
            self._prev_macd = macd_v
            self._prev_signal = sig_v
            return False
        crossed = self._prev_macd <= self._prev_signal and macd_v > sig_v
        self._prev_macd = macd_v
        self._prev_signal = sig_v
        return crossed


class MACDBearishCrossover(Condition):
    """True when MACD line crossed below signal line on Binance BTC data."""

    def __init__(self, fast: int = 12, slow: int = 26, signal: int = 9):
        if fast >= slow:
            raise ValueError("fast period must be less than slow period")
        self._fast = fast
        self._slow = slow
        self._signal = signal
        self._prev_macd: float | None = None
        self._prev_signal: float | None = None

    def __call__(self, ctx: TickContext) -> bool:
        binance = ctx.binance
        if binance is None:
            return False
        result = binance.macd(self._fast, self._slow, self._signal)
        if result is None:
            return False
        macd_v, sig_v = result.macd, result.signal
        if self._prev_macd is None or self._prev_signal is None:
            self._prev_macd = macd_v
            self._prev_signal = sig_v
            return False
        crossed = self._prev_macd >= self._prev_signal and macd_v < sig_v
        self._prev_macd = macd_v
        self._prev_signal = sig_v
        return crossed


class MACDAboveZero(Condition):
    """True when MACD histogram is positive on Binance BTC data."""

    def __init__(self, fast: int = 12, slow: int = 26, signal: int = 9):
        self._fast = fast
        self._slow = slow
        self._signal = signal

    def __call__(self, ctx: TickContext) -> bool:
        binance = ctx.binance
        if binance is None:
            return False
        result = binance.macd(self._fast, self._slow, self._signal)
        if result is None:
            return False
        return result.histogram > 0


class MACDBelowZero(Condition):
    """True when MACD histogram is negative on Binance BTC data."""

    def __init__(self, fast: int = 12, slow: int = 26, signal: int = 9):
        self._fast = fast
        self._slow = slow
        self._signal = signal

    def __call__(self, ctx: TickContext) -> bool:
        binance = ctx.binance
        if binance is None:
            return False
        result = binance.macd(self._fast, self._slow, self._signal)
        if result is None:
            return False
        return result.histogram < 0


# ── Price Change Conditions (from Binance data via ctx.binance) ─────────────────

class PriceChangeAbove(Condition):
    """True when BTC spot price changed by at least min_change USD."""

    def __init__(self, min_change: float, candles_back: int = 1):
        if min_change <= 0:
            raise ValueError("min_change must be positive")
        self._min_change = min_change
        self._candles_back = candles_back

    def __call__(self, ctx: TickContext) -> bool:
        binance = ctx.binance
        if binance is None:
            return False
        result = binance.price_above_by(self._min_change, self._candles_back)
        return bool(result)


class PriceChangeBelow(Condition):
    """True when BTC spot price dropped by at least min_change USD."""

    def __init__(self, min_change: float, candles_back: int = 1):
        if min_change <= 0:
            raise ValueError("min_change must be positive")
        self._min_change = min_change
        self._candles_back = candles_back

    def __call__(self, ctx: TickContext) -> bool:
        binance = ctx.binance
        if binance is None:
            return False
        chg = binance.price_change(self._candles_back)
        if chg is None:
            return False
        return chg <= -self._min_change


class PriceUp(Condition):
    """True when BTC close price is higher than N candles ago."""

    def __init__(self, candles_back: int = 1):
        self._candles_back = candles_back

    def __call__(self, ctx: TickContext) -> bool:
        binance = ctx.binance
        if binance is None:
            return False
        result = binance.price_up(self._candles_back)
        return bool(result)


class PriceDown(Condition):
    """True when BTC close price is lower than N candles ago."""

    def __init__(self, candles_back: int = 1):
        self._candles_back = candles_back

    def __call__(self, ctx: TickContext) -> bool:
        binance = ctx.binance
        if binance is None:
            return False
        up = binance.price_up(self._candles_back)
        if up is None:
            return False
        return not up


# ── Factory functions ───────────────────────────────────────────────────────────

def macd_bullish_crossover(fast: int = 12, slow: int = 26, signal: int = 9) -> Condition:
    """MACD line crossed above signal line (from Binance BTC data)."""
    return MACDBullishCrossover(fast, slow, signal)


def macd_bearish_crossover(fast: int = 12, slow: int = 26, signal: int = 9) -> Condition:
    """MACD line crossed below signal line (from Binance BTC data)."""
    return MACDBearishCrossover(fast, slow, signal)


def macd_above_zero(fast: int = 12, slow: int = 26, signal: int = 9) -> Condition:
    """MACD histogram is positive (from Binance BTC data)."""
    return MACDAboveZero(fast, slow, signal)


def macd_below_zero(fast: int = 12, slow: int = 26, signal: int = 9) -> Condition:
    """MACD histogram is negative (from Binance BTC data)."""
    return MACDBelowZero(fast, slow, signal)


def price_change_above(min_change: float, candles_back: int = 1) -> Condition:
    """BTC spot price changed by at least min_change USD (from Binance BTC data)."""
    return PriceChangeAbove(min_change, candles_back)


def price_change_below(min_change: float, candles_back: int = 1) -> Condition:
    """BTC spot price dropped by at least min_change USD (from Binance BTC data)."""
    return PriceChangeBelow(min_change, candles_back)


def price_up(candles_back: int = 1) -> Condition:
    """BTC close price is higher than N candles ago (from Binance BTC data)."""
    return PriceUp(candles_back)


def price_down(candles_back: int = 1) -> Condition:
    """BTC close price is lower than N candles ago (from Binance BTC data)."""
    return PriceDown(candles_back)


__all__ = [
    "Condition",
    "and_",
    "or_",
    "not_",
    "rsi_above",
    "rsi_below",
    "price_above",
    "price_below",
    "price_in_range",
    "price_not_in_ranges",
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
    "psar_uptrend",
    "psar_downtrend",
    "psar_just_turned_up",
    "psar_just_turned_down",
    "price_above_dc_upper",
    "price_below_dc_lower",
    "ichimoku_tenkan_above_kijun",
    "ichimoku_tenkan_below_kijun",
    "ichimoku_price_above_cloud",
    "ichimoku_price_below_cloud",
    "ichimoku_bullish_breakout",
    "ichimoku_bearish_breakout",
    "always",
    "never",
    "when",
    # MACD conditions (from Binance)
    "macd_bullish_crossover",
    "macd_bearish_crossover",
    "macd_above_zero",
    "macd_below_zero",
    # Price change conditions (from Binance)
    "price_change_above",
    "price_change_below",
    "price_up",
    "price_down",
]
