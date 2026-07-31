"""
Strategy framework — declarative strategies in < 30 lines.

Shows three ways to use :class:`polyalpha.strategy.Strategy`:

1. A custom subclass (M41) with its own ``signal()`` logic.
2. A parameter-only strategy via ``ConfigurableStrategy.from_config``.
3. Running several strategies side-by-side on one shared stream.

Usage:
    python examples/strategy_framework.py
"""
from polyalpha.strategy import (
    ConfigurableStrategy,
    Signal,
    Strategy,
    StrategySuite,
)


class M41(Strategy):
    """Buy UP when CL pumped > 0.08% in 30s while BTC < $0.60."""

    name = "M41"
    cl_window_s = 30
    cl_threshold_pct = 0.08
    fav_max = 0.60

    def signal(self, ctx):
        change = ctx.cl.change_pct(self.cl_window_s)
        if change is not None:
            if change > self.cl_threshold_pct and ctx.price.up < self.fav_max:
                return Signal("UP")
            if change < -self.cl_threshold_pct and ctx.price.down < self.fav_max:
                return Signal("DOWN")
        return None


if __name__ == "__main__":
    suite = StrategySuite("BTC", "5m", balance=500)

    # 1) custom strategy
    suite.add(M41())

    # 2) parameter-only strategies (same signal logic, different thresholds)
    suite.add(ConfigurableStrategy.from_config(
        "B1", side="UP", cl_threshold_pct=0.12, fav_min=0.50, fav_max=0.75,
    ))
    suite.add(ConfigurableStrategy.from_config(
        "B2", side="DOWN", cl_threshold_pct=0.15, fav_min=0.40, fav_max=0.80,
    ))

    # 3) auto-side variant with a per-strategy balance
    suite.add(ConfigurableStrategy.from_config(
        "AUTO", side=None, cl_threshold_pct=0.10, fav_min=0.45, fav_max=0.85,
    ), balance=1000)

    print("Registered strategies:", list(suite.strategies))
    suite.run()
