"""
Tests for polyalpha.conditions — composable trading conditions.

Run with: pytest tests/unit/core/test_conditions.py -v
"""

import pytest
from typing import Optional

import polyalpha
from polyalpha.conditions import (
    Condition,
    AndCondition,
    OrCondition,
    NotCondition,
    LambdaCondition,
    RSIAbove,
    RSIBelow,
    PriceAbove,
    PriceBelow,
    CrossedAbove,
    CrossedBelow,
    Always,
    Never,
    and_,
    or_,
    not_,
    rsi_above,
    rsi_below,
    price_above,
    price_below,
    crossed_above,
    crossed_below,
    always,
    never,
    when,
)


# ── Helpers ────────────────────────────────────────────────────────────────────


class FakePrice:
    """Stand-in for PriceSnapshot."""
    def __init__(self, up: float = 0.0, down: float = 0.0):
        self.up = up
        self.down = down


class FakeCtx:
    """Minimal TickContext stand-in for condition tests."""
    def __init__(self, rsi: Optional[float] = None, up: float = 0.0, down: float = 0.0):
        self.rsi = rsi
        self.price = FakePrice(up=up, down=down)
        self._cross_state: dict[int, float] = {}


# ── Condition base class ───────────────────────────────────────────────────────


@pytest.mark.unit
class TestCondition:
    def test_call_raises_not_implemented(self):
        c = Condition()
        with pytest.raises(NotImplementedError):
            c(FakeCtx())

    def test_and_operator(self):
        c = Condition() & Condition()
        assert isinstance(c, AndCondition)

    def test_or_operator(self):
        c = Condition() | Condition()
        assert isinstance(c, OrCondition)

    def test_invert_operator(self):
        c = ~Condition()
        assert isinstance(c, NotCondition)

    def test_chained_operators(self):
        a, b, c = Condition(), Condition(), Condition()
        expr = (a & b) | (~c)
        assert isinstance(expr, OrCondition)


# ── Combinators ─────────────────────────────────────────────────────────────────


@pytest.mark.unit
class TestAndCondition:
    def test_all_true(self):
        a = Always()
        b = Always()
        assert AndCondition(a, b)(FakeCtx()) is True

    def test_one_false(self):
        a = Always()
        b = Never()
        assert AndCondition(a, b)(FakeCtx()) is False

    def test_all_false(self):
        a = Never()
        b = Never()
        assert AndCondition(a, b)(FakeCtx()) is False

    def test_short_circuit(self):
        side_effects = []
        class SideEffectCondition(Condition):
            def __call__(self, ctx):
                side_effects.append("called")
                return True
        a = Never()
        b = SideEffectCondition()
        AndCondition(a, b)(FakeCtx())
        assert len(side_effects) == 0

    def test_empty_returns_true(self):
        assert AndCondition()(FakeCtx()) is True


@pytest.mark.unit
class TestOrCondition:
    def test_all_true(self):
        a = Always()
        b = Always()
        assert OrCondition(a, b)(FakeCtx()) is True

    def test_one_true(self):
        a = Never()
        b = Always()
        assert OrCondition(a, b)(FakeCtx()) is True

    def test_all_false(self):
        a = Never()
        b = Never()
        assert OrCondition(a, b)(FakeCtx()) is False

    def test_short_circuit(self):
        side_effects = []
        class SideEffectCondition(Condition):
            def __call__(self, ctx):
                side_effects.append("called")
                return True
        a = Always()
        b = SideEffectCondition()
        OrCondition(a, b)(FakeCtx())
        assert len(side_effects) == 0

    def test_empty_returns_false(self):
        assert OrCondition()(FakeCtx()) is False


@pytest.mark.unit
class TestNotCondition:
    def test_inverts_true_to_false(self):
        c = NotCondition(Always())
        assert c(FakeCtx()) is False

    def test_inverts_false_to_true(self):
        c = NotCondition(Never())
        assert c(FakeCtx()) is True


# ── Lambda wrapper ──────────────────────────────────────────────────────────────


@pytest.mark.unit
class TestLambdaCondition:
    def test_true_lambda(self):
        c = LambdaCondition(lambda ctx: True)
        assert c(FakeCtx()) is True

    def test_false_lambda(self):
        c = LambdaCondition(lambda ctx: False)
        assert c(FakeCtx()) is False

    def test_ctx_passed_through(self):
        def check_rsi(ctx):
            return ctx.rsi is not None
        c = LambdaCondition(check_rsi)
        assert c(FakeCtx(rsi=42.0)) is True
        assert c(FakeCtx(rsi=None)) is False


# ── RSI conditions ──────────────────────────────────────────────────────────────


@pytest.mark.unit
class TestRSIAbove:
    def test_above_threshold(self):
        c = RSIAbove(50)
        assert c(FakeCtx(rsi=75.0)) is True

    def test_below_threshold(self):
        c = RSIAbove(50)
        assert c(FakeCtx(rsi=25.0)) is False

    def test_equal_threshold(self):
        c = RSIAbove(50)
        assert c(FakeCtx(rsi=50.0)) is False

    def test_none_rsi_returns_false(self):
        c = RSIAbove(50)
        assert c(FakeCtx(rsi=None)) is False

    def test_boundary_near_zero(self):
        c = RSIAbove(0)
        assert c(FakeCtx(rsi=0.001)) is True
        assert c(FakeCtx(rsi=0.0)) is False

    def test_boundary_near_one_hundred(self):
        c = RSIAbove(99.999)
        assert c(FakeCtx(rsi=100.0)) is True
        assert c(FakeCtx(rsi=99.999)) is False


@pytest.mark.unit
class TestRSIBelow:
    def test_below_threshold(self):
        c = RSIBelow(50)
        assert c(FakeCtx(rsi=25.0)) is True

    def test_above_threshold(self):
        c = RSIBelow(50)
        assert c(FakeCtx(rsi=75.0)) is False

    def test_equal_threshold(self):
        c = RSIBelow(50)
        assert c(FakeCtx(rsi=50.0)) is False

    def test_none_rsi_returns_false(self):
        c = RSIBelow(50)
        assert c(FakeCtx(rsi=None)) is False


# ── Price conditions ────────────────────────────────────────────────────────────


@pytest.mark.unit
class TestPriceAbove:
    def test_up_side_above(self):
        c = PriceAbove("UP", 0.5)
        assert c(FakeCtx(up=0.9)) is True

    def test_up_side_below(self):
        c = PriceAbove("UP", 0.5)
        assert c(FakeCtx(up=0.3)) is False

    def test_up_side_equal(self):
        c = PriceAbove("UP", 0.5)
        assert c(FakeCtx(up=0.5)) is False

    def test_down_side_above(self):
        c = PriceAbove("DOWN", 0.5)
        assert c(FakeCtx(down=0.9)) is True

    def test_down_side_below(self):
        c = PriceAbove("DOWN", 0.5)
        assert c(FakeCtx(down=0.3)) is False

    def test_lowercase_side(self):
        c = PriceAbove("up", 0.5)
        assert c(FakeCtx(up=0.9)) is True

    def test_invalid_side_raises(self):
        with pytest.raises(ValueError, match="side must be 'UP' or 'DOWN'"):
            PriceAbove("LEFT", 0.5)

    def test_invalid_side_empty(self):
        with pytest.raises(ValueError):
            PriceAbove("", 0.5)

    def test_invalid_side_nonsense(self):
        with pytest.raises(ValueError):
            PriceAbove("INVALID", 0.5)

    def test_negative_threshold(self):
        c = PriceAbove("UP", -1.0)
        assert c(FakeCtx(up=-0.5)) is True
        assert c(FakeCtx(up=-2.0)) is False


@pytest.mark.unit
class TestPriceBelow:
    def test_up_side_below(self):
        c = PriceBelow("UP", 0.5)
        assert c(FakeCtx(up=0.3)) is True

    def test_up_side_above(self):
        c = PriceBelow("UP", 0.5)
        assert c(FakeCtx(up=0.9)) is False

    def test_up_side_equal(self):
        c = PriceBelow("UP", 0.5)
        assert c(FakeCtx(up=0.5)) is False

    def test_down_side_below(self):
        c = PriceBelow("DOWN", 0.5)
        assert c(FakeCtx(down=0.3)) is True

    def test_down_side_above(self):
        c = PriceBelow("DOWN", 0.5)
        assert c(FakeCtx(down=0.9)) is False

    def test_invalid_side_raises(self):
        with pytest.raises(ValueError, match="side must be 'UP' or 'DOWN'"):
            PriceBelow("LEFT", 0.5)

    def test_negative_threshold(self):
        c = PriceBelow("DOWN", -1.0)
        assert c(FakeCtx(down=-2.0)) is True
        assert c(FakeCtx(down=-0.5)) is False


# ── Cross conditions (stateful) ─────────────────────────────────────────────────


@pytest.mark.unit
class TestCrossedAbove:
    def test_first_tick_returns_false(self):
        c = CrossedAbove("UP", 0.5)
        ctx = FakeCtx(up=0.9)
        assert c(ctx) is False

    def test_crosses_above_on_second_tick(self):
        c = CrossedAbove("UP", 0.5)
        ctx = FakeCtx(up=0.3)
        c(ctx)  # first tick — records prev
        ctx.price.up = 0.9
        assert c(ctx) is True

    def test_no_cross_stays_below(self):
        c = CrossedAbove("UP", 0.5)
        ctx = FakeCtx(up=0.3)
        c(ctx)
        ctx.price.up = 0.4
        assert c(ctx) is False

    def test_no_cross_stays_above(self):
        c = CrossedAbove("UP", 0.5)
        ctx = FakeCtx(up=0.9)
        c(ctx)
        ctx.price.up = 0.8
        assert c(ctx) is False

    def test_crosses_above_exact_threshold(self):
        c = CrossedAbove("UP", 0.5)
        ctx = FakeCtx(up=0.5)
        c(ctx)  # prev == threshold
        ctx.price.up = 0.6
        assert c(ctx) is True

    def test_multi_cross_detects_each_cross(self):
        c = CrossedAbove("UP", 0.5)
        ctx = FakeCtx(up=0.3)
        c(ctx)
        ctx.price.up = 0.9
        assert c(ctx) is True
        ctx.price.up = 0.4
        c(ctx)
        ctx.price.up = 0.6
        assert c(ctx) is True

    def test_down_side(self):
        c = CrossedAbove("DOWN", 0.5)
        ctx = FakeCtx(down=0.3)
        c(ctx)
        ctx.price.down = 0.9
        assert c(ctx) is True

    def test_invalid_side_raises(self):
        with pytest.raises(ValueError, match="side must be 'UP' or 'DOWN'"):
            CrossedAbove("LEFT", 0.5)

    def test_shared_instance_independent_contexts(self):
        """Same condition used by two bots — each has its own _cross_state."""
        c = CrossedAbove("UP", 0.5)
        ctx_a = FakeCtx(up=0.3)
        ctx_b = FakeCtx(up=0.9)
        assert c(ctx_a) is False  # ctx_a records 0.3
        assert c(ctx_b) is False  # ctx_b records 0.9 (independent!)
        assert c(ctx_a) is False  # ctx_a: 0.3 -> 0.3 no cross
        assert c(ctx_b) is False  # ctx_b: 0.9 -> 0.9 no cross


@pytest.mark.unit
class TestCrossedBelow:
    def test_first_tick_returns_false(self):
        c = CrossedBelow("UP", 0.5)
        ctx = FakeCtx(up=0.3)
        assert c(ctx) is False

    def test_crosses_below_on_second_tick(self):
        c = CrossedBelow("UP", 0.5)
        ctx = FakeCtx(up=0.9)
        c(ctx)
        ctx.price.up = 0.3
        assert c(ctx) is True

    def test_no_cross_stays_above(self):
        c = CrossedBelow("UP", 0.5)
        ctx = FakeCtx(up=0.9)
        c(ctx)
        ctx.price.up = 0.7
        assert c(ctx) is False

    def test_no_cross_stays_below(self):
        c = CrossedBelow("UP", 0.5)
        ctx = FakeCtx(up=0.3)
        c(ctx)
        ctx.price.up = 0.4
        assert c(ctx) is False

    def test_crosses_below_exact_threshold(self):
        c = CrossedBelow("UP", 0.5)
        ctx = FakeCtx(up=0.5)
        c(ctx)
        ctx.price.up = 0.4
        assert c(ctx) is True

    def test_multi_cross_detects_each_cross(self):
        c = CrossedBelow("UP", 0.5)
        ctx = FakeCtx(up=0.9)
        c(ctx)
        ctx.price.up = 0.3
        assert c(ctx) is True
        ctx.price.up = 0.7
        c(ctx)
        ctx.price.up = 0.4
        assert c(ctx) is True

    def test_down_side(self):
        c = CrossedBelow("DOWN", 0.5)
        ctx = FakeCtx(down=0.9)
        c(ctx)
        ctx.price.down = 0.3
        assert c(ctx) is True

    def test_invalid_side_raises(self):
        with pytest.raises(ValueError, match="side must be 'UP' or 'DOWN'"):
            CrossedBelow("LEFT", 0.5)

    def test_shared_instance_independent_contexts(self):
        """Same condition used by two bots — each has its own _cross_state."""
        c = CrossedBelow("UP", 0.5)
        ctx_a = FakeCtx(up=0.9)
        ctx_b = FakeCtx(up=0.3)
        assert c(ctx_a) is False  # ctx_a records 0.9
        assert c(ctx_b) is False  # ctx_b records 0.3 (independent!)
        assert c(ctx_a) is False  # ctx_a: 0.9 -> 0.9 no cross
        assert c(ctx_b) is False  # ctx_b: 0.3 -> 0.3 no cross


# ── Constant conditions ─────────────────────────────────────────────────────────


@pytest.mark.unit
class TestAlways:
    def test_always_true(self):
        c = Always()
        assert c(FakeCtx()) is True
        assert c(FakeCtx(rsi=50, up=0.9, down=0.5)) is True


@pytest.mark.unit
class TestNever:
    def test_never_false(self):
        c = Never()
        assert c(FakeCtx()) is False
        assert c(FakeCtx(rsi=50, up=0.9, down=0.5)) is False


# ── Factory functions ───────────────────────────────────────────────────────────


@pytest.mark.unit
class TestFactories:
    def test_and_(self):
        c = and_(Always(), Always())
        assert isinstance(c, AndCondition)
        assert c(FakeCtx()) is True

    def test_or_(self):
        c = or_(Never(), Always())
        assert isinstance(c, OrCondition)
        assert c(FakeCtx()) is True

    def test_not_(self):
        c = not_(Always())
        assert isinstance(c, NotCondition)
        assert c(FakeCtx()) is False

    def test_rsi_above(self):
        c = rsi_above(50)
        assert isinstance(c, RSIAbove)
        assert c(FakeCtx(rsi=75)) is True
        assert c(FakeCtx(rsi=25)) is False

    def test_rsi_below(self):
        c = rsi_below(50)
        assert isinstance(c, RSIBelow)
        assert c(FakeCtx(rsi=25)) is True
        assert c(FakeCtx(rsi=75)) is False

    def test_price_above(self):
        c = price_above("UP", 0.5)
        assert isinstance(c, PriceAbove)
        assert c(FakeCtx(up=0.9)) is True

    def test_price_below(self):
        c = price_below("DOWN", 0.5)
        assert isinstance(c, PriceBelow)
        assert c(FakeCtx(down=0.3)) is True

    def test_crossed_above(self):
        c = crossed_above("UP", 0.5)
        assert isinstance(c, CrossedAbove)

    def test_crossed_below(self):
        c = crossed_below("UP", 0.5)
        assert isinstance(c, CrossedBelow)

    def test_always(self):
        c = always()
        assert isinstance(c, Always)
        assert c(FakeCtx()) is True

    def test_never(self):
        c = never()
        assert isinstance(c, Never)
        assert c(FakeCtx()) is False

    def test_when(self):
        c = when(lambda ctx: ctx.rsi is not None)
        assert isinstance(c, LambdaCondition)
        assert c(FakeCtx(rsi=42)) is True
        assert c(FakeCtx(rsi=None)) is False


# ── Composition / integration ───────────────────────────────────────────────────


@pytest.mark.unit
class TestComposition:
    def test_and_or_not_compose(self):
        expr = and_(
            or_(rsi_above(60), rsi_below(40)),
            not_(always()),
        )
        ctx = FakeCtx(rsi=70)
        assert expr(ctx) is False  # not_(always()) is False, and_ short-circuits

    def test_operator_chaining(self):
        expr = rsi_above(50) & price_above("UP", 0.5)
        assert isinstance(expr, Condition)
        ctx = FakeCtx(rsi=70, up=0.9)
        assert expr(ctx) is True
        ctx2 = FakeCtx(rsi=30, up=0.9)
        assert expr(ctx2) is False

    def test_operator_or_chaining(self):
        expr = rsi_above(80) | price_above("UP", 0.9)
        ctx = FakeCtx(rsi=50, up=0.95)
        assert expr(ctx) is True
        ctx2 = FakeCtx(rsi=50, up=0.5)
        assert expr(ctx2) is False

    def test_invert_operator(self):
        expr = ~rsi_above(50)
        assert isinstance(expr, NotCondition)
        ctx = FakeCtx(rsi=70)
        assert expr(ctx) is False
        ctx2 = FakeCtx(rsi=30)
        assert expr(ctx2) is True

    def test_complex_expression(self):
        expr = (rsi_above(50) & price_above("UP", 0.5)) | never()
        ctx = FakeCtx(rsi=70, up=0.9)
        assert expr(ctx) is True

    def test_always_short_circuits_not(self):
        expr = not_(always())
        assert expr(FakeCtx()) is False

    def test_never_short_circuits_not(self):
        expr = not_(never())
        assert expr(FakeCtx()) is True


# ── Module exports ──────────────────────────────────────────────────────────────


@pytest.mark.unit
class TestExports:
    def test_all_matches_expected(self):
        expected = {
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
            "always",
            "never",
            "when",
        }
        assert set(polyalpha.conditions.__all__) == expected

    def test_public_api_via_polyalpha(self):
        assert hasattr(polyalpha, "conditions")
        # Verify key condition types are accessible
        assert hasattr(polyalpha.conditions, "Condition")
        assert hasattr(polyalpha.conditions, "and_")
        assert hasattr(polyalpha.conditions, "or_")
        assert hasattr(polyalpha.conditions, "not_")
