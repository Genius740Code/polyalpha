"""
StrategySuite — run N strategies on one shared WebSocket stream.

Wraps :class:`BotHub` under the hood.  Each :class:`Strategy` gets its
own isolated ``PaperEngine`` (independent balance / positions / P&L),
but all strategies share ONE market discovery call and ONE WebSocket
stream.  Strategy errors are isolated — a crash in one strategy does
not stop the others.

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
            return None

    suite = StrategySuite("BTC", "5m", balance=500)
    suite.add(M41())
    suite.run()

The suite also accepts declarative (parameter-only) strategies::

    suite.add(ConfigurableStrategy.from_config(
        "B1", side="UP", cl_threshold_pct=0.12,
        fav_min=0.50, fav_max=0.75,
    ))
"""

from __future__ import annotations

import logging
from typing import Optional

from ..bot_hub import BotHub, StrategyContext
from .base import Strategy

log = logging.getLogger(__name__)


class StrategySuite:
    """Run N :class:`Strategy` instances on one shared stream.

    Parameters
    ----------
    asset : str
        BTC, ETH, SOL, XRP, DOGE.
    timeframe : str
        5m, 15m, 1h, 4h, 24h.
    balance : float
        Default starting paper balance per strategy (default 100.0).
    mode : str
        Fee/execution template: ``"simple"``, ``"realistic"``, ``"custom"``.
    globals : Globals, optional
        Shared feeds created once in ``main()`` (see
        :mod:`polyalpha.globals`). Every strategy reads the same instances —
        adding a strategy costs 0 extra connections. The caller owns the
        lifecycle (``globals.start()`` / ``globals.stop()``); the suite only
        reads it.
    **kwargs
        Extra keyword arguments forwarded to ``BotHub`` (and ``Client``).
    """

    def __init__(
        self,
        asset: str,
        timeframe: str,
        balance: float = 100.0,
        mode: str = "simple",
        globals: Optional[object] = None,
        **kwargs,
    ):
        self._asset = asset
        self._timeframe = timeframe
        self._balance = balance
        self._globals = globals
        self._hub = BotHub(
            asset=asset, timeframe=timeframe, default_balance=balance, mode=mode,
            globals=globals, **kwargs
        )
        self._strategies = {}
        self._log = logging.getLogger("polyalpha.StrategySuite")

    def add(self, strategy: Strategy, balance: Optional[float] = None) -> Strategy:
        """Register a strategy with the suite.

        Parameters
        ----------
        strategy : Strategy
            A :class:`Strategy` instance (custom subclass or
            :class:`~polyalpha.strategy.ConfigurableStrategy`).
        balance : Optional[float]
            Optional per-strategy starting paper balance.  Defaults to
            the suite-level balance.

        Returns
        -------
        Strategy
            The registered strategy (for chaining / inspection).

        Raises
        ------
        ValueError
            If a strategy with the same name is already registered.
        """
        name = strategy.name or strategy.__class__.__name__
        if name in self._strategies:
            raise ValueError(f"Strategy '{name}' is already registered")
        self._strategies[name] = strategy
        bal = balance if balance is not None else self._balance
        self._hub.add_strategy(
            name=name,
            fn=self._make_tick_handler(strategy),
            balance=bal,
            params=self._extract_params(strategy),
            id=name,
        )
        self._log.info("Registered strategy '%s' (balance=$%.2f)", name, bal)
        return strategy

    def run(self) -> None:
        """Start all strategies (blocking).

        Runs until ``stop()`` is called or an unrecoverable error.
        """
        if not self._strategies:
            raise RuntimeError("No strategies registered.  Use suite.add(strategy) first.")
        for strategy in self._strategies.values():
            try:
                strategy.on_start()
            except Exception as exc:
                self._log.warning("Strategy '%s' on_start error: %s", strategy.name, exc)
        self._hub.run()

    async def run_async(self) -> None:
        """Start all strategies (async)."""
        if not self._strategies:
            raise RuntimeError("No strategies registered.  Use suite.add(strategy) first.")
        for strategy in self._strategies.values():
            try:
                strategy.on_start()
            except Exception as exc:
                self._log.warning("Strategy '%s' on_start error: %s", strategy.name, exc)
        await self._hub.run_async()

    def stop(self) -> None:
        """Signal all strategies to stop gracefully."""
        for strategy in self._strategies.values():
            try:
                strategy.on_stop()
            except Exception as exc:
                self._log.warning("Strategy '%s' on_stop error: %s", strategy.name, exc)
        self._hub.stop()

    @property
    def stats(self) -> dict:
        """Per-strategy running statistics."""
        base = self._hub.stats
        for name, s in self._strategies.items():
            if name in base.get("strategies", {}):
                base["strategies"][name].update(
                    {
                        "total_trades": s._total_trades,
                        "total_pnl": round(s._total_pnl, 2),
                        "consecutive_losses": s._consecutive_losses,
                    }
                )
        return base

    @property
    def strategies(self) -> dict[str, Strategy]:
        """Read-only view of registered strategies."""
        return dict(self._strategies)

    @property
    def globals(self):
        """The shared :class:`~polyalpha.globals.Globals`, or *None*.

        Every strategy reads the same feeds via ``ctx.globals`` — adding a
        strategy costs 0 extra connections.
        """
        return self._globals

    def _make_tick_handler(self, strategy: Strategy):
        """Build a BotHub-compatible tick handler from a Strategy."""

        def tick_handler(ctx: StrategyContext) -> None:
            import time

            if not strategy.check_cooldown():
                return
            if not strategy.check_volume(ctx):
                return
            signal = strategy.signal(ctx)
            if signal is None:
                return
            side = signal.side.upper()
            if side not in ("UP", "DOWN"):
                return
            if not strategy.check_price_zone(ctx, side):
                return
            amount_pct = strategy.order_size_pct
            amount = ctx.balance * amount_pct / 100.0
            if amount <= 0:
                return
            result = ctx.buy(side, amount)
            if result:
                strategy._last_trade_time = time.time()
                strategy._total_trades += 1
                try:
                    strategy.on_entry(side, ctx.price.up if side == "UP" else ctx.price.down)
                except Exception as exc:
                    log.warning("Strategy '%s' on_entry error: %s", strategy.name, exc)
                return

        return tick_handler

    def _extract_params(self, strategy: Strategy) -> dict:
        """Extract a params dict for comparison reports."""
        return {
            "cl_window_s": strategy.cl_window_s,
            "cl_threshold_pct": strategy.cl_threshold_pct,
            "fav_min": strategy.fav_min,
            "fav_max": strategy.fav_max,
            "vol_multiplier": strategy.vol_multiplier,
            "order_size_pct": strategy.order_size_pct,
            "cooldown_s": strategy.cooldown_s,
            "side": strategy.side,
        }
