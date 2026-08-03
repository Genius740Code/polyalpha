"""
Declarative Conditions API — every condition builder and combinator.

Demonstrates:
  - and_, or_, not_ combinators
  - rsi_above, rsi_below, price_above, price_below
  - crossed_above, crossed_below
  - ema_above, ema_below, ema_crossed_above
  - supertrend, PSAR, Donchian, Ichimoku
  - MACD + price-change conditions (from Binance data via ctx.binance)
  - custom when() wrapper
  - Operator shortcuts: &, |, ~

Usage:
    python examples/conditions.py
"""
from collections import namedtuple

import pandas as pd

from polyalpha.conditions import (
    always,
    and_,
    crossed_below,
    ema_above,
    ema_crossed_above,
    ichimoku_bullish_breakout,
    macd_above_zero,
    macd_bullish_crossover,
    never,
    not_,
    or_,
    price_above,
    price_above_dc_upper,
    price_below,
    price_change_below,
    price_down,
    price_in_range,
    price_up,
    psar_uptrend,
    rsi_above,
    rsi_below,
    supertrend_up,
    when,
)

entry_condition = and_(
    rsi_above(50),
    price_above("UP", 0.85),
    or_(macd_bullish_crossover(), supertrend_up(7, 3.0)),
)

exit_condition = or_(
    rsi_below(30),
    price_below("UP", 0.75),
    crossed_below("UP", 0.80),
)

momentum_condition = and_(
    price_up(1),
    ema_above("UP", 20),
)

price_band = and_(
    price_in_range("UP", 0.40, 0.60),
    not_(price_below("DOWN", 0.10)),
)

ichimoku_condition = ichimoku_bullish_breakout("UP", 9, 26, 52)

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
    ("Price band", price_band),
    ("Ichimoku breakout", ichimoku_condition),
    ("Custom when()", custom),
    ("Operator style (&, |, ~)", operator_style),
    ("always()", always()),
    ("never()", never()),
    ("price_up(1)", price_up(1)),
    ("price_down(1)", price_down(1)),
    ("price_change_below(2.0)", price_change_below(2.0)),
    ("ema_above('DOWN', 20)", ema_above("DOWN", 20)),
    ("ema_crossed_above(9, 21)", ema_crossed_above(9, 21)),
    ("macd_bullish_crossover()", macd_bullish_crossover()),
    ("macd_above_zero()", macd_above_zero()),
    ("psar_uptrend()", psar_uptrend()),
    ("price_above_dc_upper('UP', 20)", price_above_dc_upper("UP", 20)),
]


class _FakeIndicators:
    @staticmethod
    def ema(period=20):
        return 0.83

    @staticmethod
    def supertrend(period=7, multiplier=3.0):
        return pd.DataFrame({"direction": [1, 1, 1]})

    @staticmethod
    def psar(af=0.02, af_max=0.2):
        return pd.DataFrame({"trend": [1, 1, 1]})

    @staticmethod
    def donchian(length=20):
        D = namedtuple("DonchianResult", ["upper", "mid", "lower"])
        return D(0.95, 0.85, 0.75)

    @staticmethod
    def ichimoku(tenkan=9, kijun=26, senkou=52):
        return {
            "tenkan": pd.Series([0.88, 0.87, 0.89]),
            "kijun": pd.Series([0.85, 0.84, 0.86]),
            "cloud": {
                "top": pd.Series([0.86, 0.86, 0.87]),
                "bottom": pd.Series([0.80, 0.81, 0.82]),
            },
        }

    @staticmethod
    def get_latest_value(series):
        return float(series.iloc[-1]) if hasattr(series, "iloc") else float(series)


class _FakeBinance:
    M = namedtuple("MACDResult", ["macd", "signal", "histogram"])

    def macd(self, fast=12, slow=26, signal=9):
        return self.M(0.02, 0.015, 0.005)

    def price_above_by(self, min_change, candles_back=1):
        return True

    def price_change(self, candles_back=1):
        return 3.0

    def price_up(self, candles_back=1):
        return True


class _FakePrice:
    up = 0.88
    down = 0.12


class FakeContext:
    balance = 100
    trade_count = 5
    rsi = 55.0
    price = _FakePrice()
    indicators = _FakeIndicators()
    binance = _FakeBinance()
    _cross_state = {}
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
    or_(macd_bullish_crossover(), psar_uptrend()),
)
print(f"  rsi_above(50) & price_above('UP', 0.85) & (macd_bullish_crossover | psar_uptrend) => {chained(ctx)}")
