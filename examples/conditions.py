"""
Declarative Conditions API — every condition builder and combinator.

Demonstrates:
  - and_, or_, not_ combinators
  - rsi_above, price_above, crossed_above
  - sma_above, macd_above, bb_upper
  - volume, ADX, stochastic conditions
  - custom when() wrapper
  - Operator shortcuts: &, |, ~

Usage:
    python examples/conditions.py
"""
from polyalpha.conditions import (
    adx_above,
    always,
    and_,
    bb_lower,
    bb_upper,
    crossed_below,
    ema_above,
    macd_above,
    macd_cross_above,
    macd_cross_below,
    never,
    not_,
    or_,
    price_above,
    price_below,
    price_changed_pct,
    price_down,
    price_up,
    rsi_above,
    rsi_below,
    sma_above,
    sma_below,
    stoch_cross_above,
    stoch_overbought,
    stoch_oversold,
    volume_above,
    volume_below,
    when,
)

entry_condition = and_(
    rsi_above(50),
    price_above("UP", 0.85),
    or_(macd_cross_above("UP"), adx_above(25)),
)

exit_condition = or_(
    rsi_below(30),
    price_below("UP", 0.75),
    crossed_below("UP", 0.80),
)

momentum_condition = and_(
    price_up("UP"),
    volume_above(1000),
    sma_above("UP", 20),
)

bb_squeeze = and_(
    bb_lower("UP"),
    bb_upper("UP"),
    not_(adx_above(25)),
)

stoch_condition = and_(
    stoch_oversold("k"),
    stoch_cross_above(),
)

def custom_balance_check(ctx):
    return ctx.balance > 50 and ctx.trade_count < 10

custom = and_(
    when(custom_balance_check),
    rsi_above(40),
)

operator_style = rsi_above(50) & price_above("UP", 0.85) & ~crossed_below("UP", 0.80)

conditions = [
    ("Entry (function style)", entry_condition),
    ("Exit", exit_condition),
    ("Momentum", momentum_condition),
    ("BB squeeze", bb_squeeze),
    ("Stochastic oversold + cross", stoch_condition),
    ("Custom when()", custom),
    ("Operator style (&, |, ~)", operator_style),
    ("always()", always()),
    ("never()", never()),
    ("price_changed_pct > 2%", price_changed_pct("UP", 2.0)),
    ("ema_above('DOWN', 20)", ema_above("DOWN", 20)),
    ("macd_above('UP')", macd_above("UP")),
    ("macd_cross_below('DOWN')", macd_cross_below("DOWN")),
    ("volume_below(500)", volume_below(500)),
    ("stoch_overbought('d')", stoch_overbought("d")),
    ("sma_below('UP', 50)", sma_below("UP", 50)),
    ("price_down('DOWN')", price_down("DOWN")),
]


class _FakeIndicators:
    @staticmethod
    def rsi(period=14):
        return 55.0

    @staticmethod
    def sma(period=20):
        return 0.82

    @staticmethod
    def ema(period=12):
        return 0.83

    @staticmethod
    def macd(fast=12, slow=26, signal=9):
        from collections import namedtuple
        M = namedtuple("MACDResult", ["macd", "signal", "histogram"])
        return M(0.02, 0.015, 0.005)

    @staticmethod
    def bollinger_bands(period=20, std=2.0):
        from collections import namedtuple
        B = namedtuple("BBResult", ["upper", "mid", "lower"])
        return B(0.95, 0.85, 0.75)

    @staticmethod
    def roc(period=12):
        return 2.0


class _FakePrice:
    up = 0.88
    down = 0.12


class FakeContext:
    balance = 100
    trade_count = 5
    price = _FakePrice()
    indicators = _FakeIndicators()
    seconds_in = 120
    candle_id = 42

    def buy(self, side, amount):
        pass


ctx = FakeContext()

for name, condition in conditions:
    result = condition(ctx)
    status = "PASS" if result else "FAIL"
    print(f"[{status}] {name}")

print("\nChained example:")
chained = and_(
    rsi_above(50),
    price_above("UP", 0.85),
    or_(macd_cross_above("UP"), adx_above(25)),
)
print(f"  rsi_above(50) & price_above('UP', 0.85) & (macd_cross_above | adx_above(25)) => {chained(ctx)}")
