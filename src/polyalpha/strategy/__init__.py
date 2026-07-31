"""
Strategy framework — declarative strategies with minimal boilerplate.

Usage
-----
    from polyalpha.strategy import Strategy, Signal, StrategySuite

    class M41(Strategy):
        name = "M41"
        cl_window_s = 30
        cl_threshold_pct = 0.08
        fav_max = 0.60

        def signal(self, ctx):
            if ctx.cl.change_pct(30) > 0.08 and ctx.price.up < 0.60:
                return Signal("UP")
            if ctx.cl.change_pct(30) < -0.08 and ctx.price.down < 0.60:
                return Signal("DOWN")

    suite = StrategySuite("BTC", "5m", balance=500)
    suite.add(M41())
    suite.run()
"""

from .base import ConfigurableStrategy, Signal, SignalResult, Strategy
from .suite import StrategySuite

__all__ = ["Strategy", "ConfigurableStrategy", "Signal", "SignalResult", "StrategySuite"]
