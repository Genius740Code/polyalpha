"""
Strategy base class and signal types.

Defines the ``Strategy`` abstract base class that lets you write new
strategies in **< 30 lines** — just the ``signal()`` method, nothing
else.  Everything else (CL window, cooldown, volume filter, price zone,
logging, stats, DB, Telegram) is handled by the framework.

Usage
-----
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
"""

from __future__ import annotations

import time
from abc import ABC, abstractmethod
from dataclasses import dataclass
from typing import Optional

from ..bot_hub import StrategyContext


@dataclass
class Signal:
    """Buy *side* at the configured order size.

    Returned by :meth:`Strategy.signal` to tell the framework to
    execute a trade.  The suite reads ``side`` and fills in the
    amount from the strategy's ``order_size_pct``.
    
    Parameters
    ----------
    side : str
        "UP" or "DOWN" direction.
    metadata : dict, optional
        Additional signal metadata for logging/analysis.
    """

    side: str
    metadata: dict = None

    def __post_init__(self):
        if self.metadata is None:
            self.metadata = {}


@dataclass
class SignalResult:
    """Full signal result with optional override fields.

    Use this when you need to override the default order size or
    set a specific price for a limit order.
    """

    side: str
    amount_pct: Optional[float] = None
    limit_price: Optional[float] = None


class Strategy(ABC):
    """Declarative strategy base class.

    Subclass this and override :meth:`signal` to define your strategy.
    All lifecycle and boilerplate is handled by :class:`StrategySuite`.

    Class-variable parameters (override in subclass):

    ==================  ==========  =======================================
    Field               Default     Description
    ==================  ==========  =======================================
    ``name``            ``""``      Human-readable name
    ``cl_window_s``     ``60``      CL price-change window (seconds)
    ``cl_threshold_pct`` ``0.12``   CL change threshold (%)
    ``fav_min``         ``0.0``     Minimum favourite token price
    ``fav_max``         ``1.0``     Maximum favourite token price
    ``vol_multiplier``  ``0.0``     Min volume ratio (0 = disabled)
    ``order_size_pct``  ``20``      Order size as % of balance
    ``cooldown_s``      ``300``     Min seconds between trades
    ``side``            ``None``    Fixed side (None = auto per signal)
    ==================  ==========  =======================================
    """

    name: str = ""
    cl_window_s: int = 60
    cl_threshold_pct: float = 0.12
    fav_min: float = 0.0
    fav_max: float = 1.0
    vol_multiplier: float = 0.0
    order_size_pct: float = 20
    cooldown_s: int = 300
    side: Optional[str] = None

    _last_trade_time: float = 0.0
    _consecutive_losses: int = 0
    _total_trades: int = 0
    _total_pnl: float = 0.0

    @abstractmethod
    def signal(self, ctx: StrategyContext) -> Optional[Signal]:
        """Evaluate the current tick and return a signal, or *None*

        This is the **only** method you need to override.  The framework
        handles everything else: CL window, cooldown, volume filter,
        price zone, logging, stats, DB, Telegram.

        Parameters
        ----------
        ctx : StrategyContext
            Per-strategy trading context with prices, indicators,
            CL window, Binance data, order book, and paper engine.

        Returns
        -------
        Signal | None
            Return a :class:`Signal` to trigger a trade, or ``None``
            to skip this tick.
        """
        raise NotImplementedError

    def on_start(self) -> None:
        """Called once when the strategy starts running."""

    def on_entry(self, side: str, price: float) -> None:
        """Called after a position is entered."""

    def on_resolve(self, pos) -> None:
        """Called when a position resolves (win or loss).

        ``pos`` has ``side``, ``outcome``, ``pnl``, etc.
        """

    def on_stop(self) -> None:
        """Called when the strategy stops."""

    def check_cooldown(self) -> bool:
        """Return ``True`` if enough time has passed since last trade.

        Override to customise cooldown logic.
        """
        if self.cooldown_s <= 0:
            return True
        return time.time() - self._last_trade_time >= self.cooldown_s

    def check_volume(self, ctx: StrategyContext) -> bool:
        """Return ``True`` if volume is above the configured threshold.

        Override to customise volume filtering.  Default checks
        ``ctx.binance.vol_ratio() >= self.vol_multiplier``.
        """
        if self.vol_multiplier <= 0:
            return True
        ratio = ctx.binance.vol_ratio(10) if ctx.binance else None
        if ratio is None:
            return True
        return ratio >= self.vol_multiplier

    def check_price_zone(self, ctx: StrategyContext, side: str) -> bool:
        """Return ``True`` if the favourite token price is in range.

        Override to customise zone logic.  Default checks
        ``fav_min <= price <= fav_max``.
        """
        price = ctx.price.up if side == "UP" else ctx.price.down
        return self.fav_min <= price <= self.fav_max

    def should_skip(self, ctx: StrategyContext) -> Optional[Signal]:
        """Composite guard: returns ``None`` if all checks pass,
        or a no-trade sentinel.

        Call this at the top of your ``signal()`` if you want all
        standard guards applied automatically::

            def signal(self, ctx):
                if self.should_skip(ctx):
                    return
                # ... your signal logic
        """
        if not self.check_cooldown():
            return None
        return None

    def __repr__(self) -> str:
        return (
            f"{self.__class__.__name__}(name={self.name!r}, side={self.side}, "
            f"order_size={self.order_size_pct}%)"
        )


class ConfigurableStrategy(Strategy):
    """Strategy defined entirely by parameters — no custom signal logic.

    Useful for variants where only thresholds differ::

        b1 = ConfigurableStrategy("B1", side="UP", cl_threshold_pct=0.12,
                                  cl_window_s=60, fav_min=0.50, fav_max=0.75)
    """

    def __init__(
        self,
        name: str,
        side: Optional[str] = "UP",
        cl_threshold_pct: float = 0.12,
        cl_window_s: int = 60,
        fav_min: float = 0.0,
        fav_max: float = 1.0,
        vol_multiplier: float = 0.0,
        order_size_pct: float = 20,
        cooldown_s: int = 300,
    ):
        self.name = name
        self.side = side.upper() if side else None
        self.cl_threshold_pct = cl_threshold_pct
        self.cl_window_s = cl_window_s
        self.fav_min = fav_min
        self.fav_max = fav_max
        self.vol_multiplier = vol_multiplier
        self.order_size_pct = order_size_pct
        self.cooldown_s = cooldown_s

    def signal(self, ctx: StrategyContext) -> Optional[Signal]:
        """Auto-generated signal from CL threshold + price zone.

        Logic::

            if CL change > threshold AND fav price in zone -> Signal(side)
            if CL change < -threshold AND fav price in zone -> Signal(opposite)
        """
        change = ctx.cl.change_pct(self.cl_window_s)
        if change is None:
            return None
        if self.side == "UP":
            if change > self.cl_threshold_pct and self.check_price_zone(ctx, "UP"):
                return Signal("UP")
            return None
        if self.side == "DOWN":
            if change < -self.cl_threshold_pct and self.check_price_zone(ctx, "DOWN"):
                return Signal("DOWN")
            return None
        if change > self.cl_threshold_pct and self.check_price_zone(ctx, "UP"):
            return Signal("UP")
        if change < -self.cl_threshold_pct and self.check_price_zone(ctx, "DOWN"):
            return Signal("DOWN")
        return None

    @classmethod
    def from_config(cls, name: str, **kwargs) -> "ConfigurableStrategy":
        """Create a parameter-only strategy from keyword arguments.

        Shorthand for quickly creating variants::

            b1 = ConfigurableStrategy.from_config("B1", side="UP",
                  cl_threshold_pct=0.12, fav_min=0.50, fav_max=0.75)
        """
        return cls(name=name, **kwargs)
