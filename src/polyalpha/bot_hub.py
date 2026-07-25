"""
BotHub — run multiple strategies from a single data connection.

Each strategy gets its own isolated PaperEngine (independent balance,
positions, and P&L), but they all share ONE market discovery call and
ONE WebSocket stream. This eliminates redundant rate-limited connections
when running many strategies on the same asset / timeframe.

Usage
-----
    hub = polyalpha.BotHub("BTC", "5m", default_balance=500)

    @hub.strategy("momentum")
    def momentum(ctx):
        if ctx.price.up > 0.9 and ctx.rsi > 50:
            ctx.buy("UP", 20)

    @hub.strategy("value", balance=1000)
    def value(ctx):
        if ctx.price.down < 0.10:
            ctx.buy("DOWN", 10)

    hub.run()   # blocking; one stream, N strategies

The BotHub handles the full lifecycle once and fans every price tick
out to all registered strategies:

    discover (once) → stream (once) → tick×N → resolve → rollover → repeat

Each strategy error is isolated — a crash in one strategy is logged and
does not stop the others or the hub.

Variant framework
-----------------
Variants are strategy-like entries that additionally carry free-form
parameter metadata and can be compared side-by-side::

    hub = polyalpha.BotHub("BTC", "5m")

    @hub.variant("rsi_70", params={"rsi_threshold": 70})
    def rsi_70(ctx):
        if ctx.rsi and ctx.rsi > 70:
            ctx.buy("DOWN", 10)

    @hub.variant("rsi_30", params={"rsi_threshold": 30})
    def rsi_30(ctx):
        if ctx.rsi and ctx.rsi < 30:
            ctx.buy("UP", 10)

    hub.run()
    report = hub.compare_variants()   # ComparisonReport sorted by P&L
    report.print()
"""

from __future__ import annotations

import asyncio
import logging
import threading
import time
from collections import deque
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import TYPE_CHECKING, Callable, Optional

if TYPE_CHECKING:
    from .report.comparison import ComparisonReport

try:
    import pandas as pd
except ImportError:
    pd = None  # type: ignore[assignment]

try:
    from .analysis._native_ta import ema as _ema
    from .analysis._native_ta import rsi as _rsi
    from .analysis._native_ta import sma as _sma
except ImportError:
    _rsi = _sma = _ema = None

from .client import Client
from .core import (
    ASSETS,
    FALLBACK_PRICE,
    TIMEFRAME_SECONDS,
    Market,
)
from .core.errors import MarketNotFound
from .trading.paper_config import PaperConfig
from .trading.paper_engine import PaperEngine

log = logging.getLogger(__name__)


# ── Price Snapshot ─────────────────────────────────────────────────────────────

@dataclass
class PriceSnapshot:
    """Current UP/DOWN prices from the shared stream."""
    up: float
    down: float


# ── Strategy Context ───────────────────────────────────────────────────────────

class StrategyContext:
    """
    Per-strategy trading context — same public API as ``Bot.TickContext``.

    Each strategy receives its own ``StrategyContext`` wrapping an isolated
    ``PaperEngine`` (independent balance / positions / P&L) but reading
    prices from the shared stream.

    Properties
    ----------
    price : PriceSnapshot
        Current UP/DOWN mid-prices.
    balance : float
        This strategy's paper balance.
    positions : list
        This strategy's open positions.
    pnl : float
        This strategy's realised P&L.
    market : Market | None
        The current shared market.
    name : str
        This strategy's registered name.
    rsi, sma_20, ema_12 : float | None
        Indicators computed on the shared price history.

    Methods
    -------
    buy(side, amount)
    limit(side, price, amount)
    close_position(side, amount=None)
    """

    def __init__(
        self,
        name: str,
        stream: object,
        paper: PaperEngine,
        market: Optional[Market],
        price_history: deque,
        asset: str = "BTC",
        chainlink_cache: Optional[object] = None,
        get_candle_open=None,
        get_seconds_in=None,
        get_candle_id=None,
        bought_this_candle=None,
    ):
        self.name = name
        self._asset = asset
        self._stream = stream
        self._paper = paper
        self._market = market
        self._price_history = price_history  # shared across strategies
        self._chainlink_cache = chainlink_cache
        self._get_candle_open = get_candle_open or (lambda: None)
        self._get_seconds_in = get_seconds_in or (lambda: 0.0)
        self._get_candle_id: Callable[[], int] = get_candle_id or (lambda: 0)
        self._bought_this_candle: dict[int, dict[str, set[str]]] = bought_this_candle if bought_this_candle is not None else {}
        self._cached_series = None

    # ── Prices ──────────────────────────────────────────────────────────────

    @property
    def price(self) -> PriceSnapshot:
        return PriceSnapshot(
            up=getattr(self._stream, "up", FALLBACK_PRICE),
            down=getattr(self._stream, "down", FALLBACK_PRICE),
        )

    @property
    def spot_price(self) -> Optional[float]:
        """Current Chainlink oracle price for the hub's asset, or *None*."""
        if self._chainlink_cache is not None:
            try:
                return self._chainlink_cache.get_price(self._asset)
            except Exception:
                pass
        return None

    @property
    def candle_open(self) -> Optional[float]:
        """Opening price of the current candle, or *None* if no tick yet."""
        return self._get_candle_open()

    @property
    def seconds_in(self) -> float:
        """Seconds elapsed since the start of the current candle."""
        return self._get_seconds_in()

    # ── Account ─────────────────────────────────────────────────────────────

    @property
    def balance(self) -> float:
        return self._paper.balance

    @property
    def positions(self) -> list:
        return self._paper.positions()

    @property
    def pnl(self) -> float:
        return sum(p.pnl for p in self._paper.all_positions())

    @property
    def market(self) -> Optional[Market]:
        return self._market

    # ── Orders ──────────────────────────────────────────────────────────────

    def buy(self, side: str, amount: float):
        """Place a market buy order against this strategy's paper engine."""
        return self._paper.buy(market=self._market, side=side, amount=amount)

    def limit(self, side: str, price: float, amount: float):
        """Place a limit order against this strategy's paper engine."""
        return self._paper.limit(
            market=self._market, side=side, price=price, amount=amount
        )

    def close_position(self, side: str, amount: Optional[float] = None):
        """Close an open position for this strategy."""
        return self._paper.sell_position(
            market=self._market, side=side, amount=amount
        )

    # ── Candle-aware trading guards ───────────────────────────────────────

    def buy_once_per_candle(self, side: str, amount: float):
        """Buy only if *side* hasn't been bought yet in the current candle.

        Tracks buys per candle via the hub's ``_bought_this_candle`` dict.
        Safe to call multiple times — subsequent calls within the same
        candle for the same side are silently skipped.

        Parameters
        ----------
        side : "UP" | "DOWN"
        amount : USDC to spend
        """
        cid = self._get_candle_id()
        sides = self._bought_this_candle.setdefault(cid, {}).setdefault(self.name, set())
        side = side.upper()
        if side in sides:
            return
        result = self.buy(side, amount)
        sides.add(side)
        return result

    def buy_in_window(self, side: str, amount: float, min_seconds: float, max_seconds: float):
        """Only buy if ``seconds_in`` is within ``[min_seconds, max_seconds]``.

        Useful for buying early in a candle (e.g. first 30 s) or waiting
        for confirmation (e.g. after 60 s of a 5 m candle).

        Parameters
        ----------
        side : "UP" | "DOWN"
        amount : USDC to spend
        min_seconds : float
            Minimum seconds into the candle before buying.
        max_seconds : float
            Maximum seconds into the candle; no buy after this point.
        """
        secs = self.seconds_in
        if min_seconds <= secs <= max_seconds:
            return self.buy(side, amount)

    # ── Indicators (shared price history) ──────────────────────────────────

    def _get_price_series(self):
        if self._cached_series is not None:
            return self._cached_series
        if pd is None:
            raise RuntimeError(
                "Indicators require 'pandas'. Install: pip install pandas"
            )
        if len(self._price_history) < 14:
            return None
        self._cached_series = pd.Series(list(self._price_history))
        return self._cached_series

    def _invalidate_series_cache(self) -> None:
        self._cached_series = None

    @property
    def rsi(self) -> Optional[float]:
        series = self._get_price_series()
        if series is None or _rsi is None:
            return None
        try:
            val = _rsi(series, 14).iloc[-1]
            return None if pd.isna(val) else float(val)
        except Exception:
            return None

    @property
    def sma_20(self) -> Optional[float]:
        series = self._get_price_series()
        if series is None or _sma is None:
            return None
        try:
            val = _sma(series, 20).iloc[-1]
            return None if pd.isna(val) else float(val)
        except Exception:
            return None

    @property
    def ema_12(self) -> Optional[float]:
        series = self._get_price_series()
        if series is None or _ema is None:
            return None
        try:
            val = _ema(series, 12).iloc[-1]
            return None if pd.isna(val) else float(val)
        except Exception:
            return None


# ── Registered strategy ────────────────────────────────────────────────────────

@dataclass
class _RegisteredStrategy:
    name: str
    fn: Callable[[StrategyContext], None]
    balance: float
    paper: Optional[PaperEngine] = None  # lazily built on first cycle
    ctx: Optional[StrategyContext] = None


@dataclass
class Variant:
    """
    A registered strategy variant — same shape as ``_RegisteredStrategy``
    but carries extra metadata for cross-variant comparison.

    Fields
    ------
    name : str
        Unique variant name (decorator argument).
    fn : Callable[[StrategyContext], None]
        The strategy function to invoke on each tick.
    balance : float
        Starting paper balance for this variant.
    params : dict
        Free-form parameter metadata (e.g. rsi_threshold, window size).
        Stored verbatim and surfaced in comparison reports.
    id : str
        Stable identifier used in persistence and comparison snapshots.
        Defaults to ``name``-slugified but can be overridden.
    created_at : datetime
        UTC timestamp the variant was registered.
    run_count : int
        Number of comparison snapshots this variant has appeared in.
    paper : Optional[PaperEngine]
        Lazily built on first cycle.
    ctx : Optional[StrategyContext]
        Built when the market is discovered.
    """

    name: str
    fn: Callable[[StrategyContext], None]
    balance: float
    params: dict = field(default_factory=dict)
    id: str = ""
    created_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
    run_count: int = 0
    paper: Optional[PaperEngine] = None
    ctx: Optional[StrategyContext] = None

    def __post_init__(self) -> None:
        if not self.id:
            self.id = self.name


# ── BotHub ────────────────────────────────────────────────────────────────────

class BotHub:
    """
    Run multiple strategies from a single data connection.

    One market discovery, one WebSocket stream, N isolated paper engines.
    Eliminates redundant rate-limited connections when running many
    strategies on the same asset / timeframe.

    Parameters
    ----------
    asset : str
        BTC, ETH, SOL, XRP, DOGE, HYPE, BNB (default "BTC").
    timeframe : str
        5m, 15m, 1h, 4h, 24h (default "5m").
    default_balance : float
        Default starting paper balance per strategy (default 100.0).
    mode : str
        Fee/execution template: ``"simple"``, ``"realistic"``, ``"custom"``.
    paper_config : PaperConfig, optional
        Custom paper config when ``mode="custom"``.

    Usage
    -----
        hub = polyalpha.BotHub("BTC", "5m", default_balance=500)

        @hub.strategy("momentum")
        def momentum(ctx):
            if ctx.price.up > 0.9:
                ctx.buy("UP", 20)

        @hub.strategy("value", balance=1000)
        def value(ctx):
            if ctx.price.down < 0.10:
                ctx.buy("DOWN", 10)

        hub.run()
    """

    def __init__(
        self,
        asset: str = "BTC",
        timeframe: str = "5m",
        default_balance: float = 100.0,
        mode: str = "simple",
        paper_config: Optional[PaperConfig] = None,
        chainlink: bool = True,
        **kwargs,
    ):
        asset = asset.upper()
        if asset not in ASSETS:
            raise ValueError(
                f"Unsupported asset '{asset}'. Supported: {list(ASSETS)}"
            )
        if timeframe not in TIMEFRAME_SECONDS:
            raise ValueError(
                f"Unsupported timeframe '{timeframe}'. "
                f"Supported: {list(TIMEFRAME_SECONDS)}"
            )

        self.asset = asset
        self.timeframe = timeframe
        self.default_balance = default_balance
        self.mode = mode

        from .trading.paper_config import get_paper_config_from_preset

        if mode == "realistic":
            self._paper_config = get_paper_config_from_preset("REALISTIC")
        elif mode == "custom":
            self._paper_config = paper_config or PaperConfig()
        else:
            self._paper_config = get_paper_config_from_preset("TEST")

        # One shared client for market discovery + stream creation.
        # Its paper engine is unused — each strategy gets its own.
        self._shared_client = Client(
            balance=default_balance,
            paper_config=self._paper_config,
            **kwargs,
        )

        self._strategies: list[_RegisteredStrategy] = []
        self._variants: list[Variant] = []
        self._market: Optional[Market] = None
        self._stream = None
        self._price_history: deque[float] = deque(maxlen=200)
        self._stop_event = threading.Event()
        self._tick_count = 0
        self._candle_start_time: float = 0.0
        self._candle_open_price: Optional[float] = None
        self._candle_id: int = 0
        self._bought_this_candle: dict[int, dict[str, set[str]]] = {}
        self._chainlink_cache: Optional[object] = None
        if chainlink:
            try:
                from .core.chainlink_cache import ChainlinkPriceCache
                self._chainlink_cache = ChainlinkPriceCache(symbol=self.asset)
            except Exception as exc:
                self._log.warning("Chainlink cache unavailable: %s", exc)
        self._log = logging.getLogger("polyalpha.BotHub")

    # ── Helpers ─────────────────────────────────────────────────────────────

    def _active_tickers(self) -> list[_RegisteredStrategy]:
        """Combined list of strategies and variants that receive each tick.

        Both shapes (``_RegisteredStrategy`` and ``Variant``) expose the
        same runtime protocol — ``name``, ``fn``, ``balance``, ``paper``,
        ``ctx`` — so the fan-out loop treats them uniformly.
        """
        return [*self._strategies, *self._variants]  # type: ignore[list-item]

    # ── Public API ──────────────────────────────────────────────────────────

    def strategy(
        self,
        name: str,
        balance: Optional[float] = None,
    ) -> Callable:
        """
        Decorator — register a strategy function with the hub.

        Parameters
        ----------
        name : str
            Unique strategy name (used in logs and stats).
        balance : float, optional
            Per-strategy starting balance. Defaults to ``default_balance``.

        Example
        -------
        >>> @hub.strategy("momentum", balance=500)
        ... def momentum(ctx):
        ...     if ctx.price.up > 0.9:
        ...         ctx.buy("UP", 20)
        """
        if not name or not isinstance(name, str):
            raise ValueError("strategy name must be a non-empty string")

        def decorator(fn: Callable[[StrategyContext], None]) -> Callable:
            existing = {s.name for s in self._strategies}
            if name in existing:
                raise ValueError(f"strategy '{name}' already registered")
            self._strategies.append(
                _RegisteredStrategy(
                    name=name,
                    fn=fn,
                    balance=balance if balance is not None else self.default_balance,
                )
            )
            self._log.info(
                "Registered strategy '%s' (balance=$%.2f)",
                name, balance or self.default_balance,
            )
            return fn

        return decorator

    def add_strategy(
        self,
        name: str,
        fn: Callable[[StrategyContext], None],
        balance: Optional[float] = None,
    ) -> None:
        """Register a strategy without decorator syntax."""
        self.strategy(name, balance=balance)(fn)

    def variant(
        self,
        name: str,
        balance: Optional[float] = None,
        params: Optional[dict] = None,
        id: str = "",
    ) -> Callable:
        """
        Decorator — register a **variant** strategy with metadata for
        cross-variant comparison.

        Variants behave exactly like strategies at run time (one isolated
        ``PaperEngine`` each, shared stream fan-out) but additionally:

        * Carry a free-form ``params`` dict surfaced in comparison reports.
        * Persist snapshots via ``hub.compare_variants()`` and
          ``hub.list_runs()`` / ``hub.load_run()``.
        * Are returned by ``hub.compare_variants()`` sorted by P&L.

        Parameters
        ----------
        name : str
            Unique variant name (must not collide with another variant
            or strategy name).
        balance : float, optional
            Per-variant starting balance. Defaults to ``default_balance``.
        params : dict, optional
            Free-form parameter metadata, e.g. ``{"rsi_threshold": 70}``.
        id : str, optional
            Stable identifier for persistence snapshots. Defaults to the
            slugified variant ``name``.

        Example
        -------
        >>> @hub.variant("rsi_70", params={"rsi": 70})
        ... def rsi_70(ctx):
        ...     if ctx.rsi and ctx.rsi > 70:
        ...         ctx.buy("DOWN", 10)
        """
        if not name or not isinstance(name, str):
            raise ValueError("variant name must be a non-empty string")

        def decorator(fn: Callable[[StrategyContext], None]) -> Callable:
            existing = {s.name for s in self._strategies}
            existing |= {v.name for v in self._variants}
            if name in existing:
                raise ValueError(f"variant/strategy '{name}' already registered")
            self._variants.append(
                Variant(
                    name=name,
                    fn=fn,
                    balance=balance if balance is not None else self.default_balance,
                    params=dict(params) if params else {},
                    id=id or name,
                )
            )
            self._log.info(
                "Registered variant '%s' (balance=$%.2f, params=%s)",
                name, balance or self.default_balance, params or {},
            )
            return fn

        return decorator

    def add_variant(
        self,
        name: str,
        fn: Callable[[StrategyContext], None],
        balance: Optional[float] = None,
        params: Optional[dict] = None,
        id: str = "",
    ) -> None:
        """Register a variant without decorator syntax."""
        self.variant(name, balance=balance, params=params, id=id)(fn)

    @property
    def tick_count(self) -> int:
        """Total price ticks received this session."""
        return self._tick_count

    @property
    def strategy_count(self) -> int:
        """Number of registered strategies (excludes variants)."""
        return len(self._strategies)

    @property
    def variant_count(self) -> int:
        """Number of registered variants."""
        return len(self._variants)

    @property
    def total_count(self) -> int:
        """Total registered strategies + variants."""
        return len(self._strategies) + len(self._variants)

    @property
    def variants(self) -> list[Variant]:
        """Read-only view of registered variants (copies the list)."""
        return list(self._variants)

    @property
    def stats(self) -> dict:
        """Per-strategy and per-variant running stats."""
        strategies = {
            s.name: {
                "balance": s.paper.balance if s.paper else s.balance,
                "pnl": sum(p.pnl for p in s.paper.all_positions())
                    if s.paper else 0.0,
                "open_positions": len(s.paper.positions()) if s.paper else 0,
            }
            for s in self._strategies
        }
        variants = {
            v.name: {
                "balance": v.paper.balance if v.paper else v.balance,
                "pnl": sum(p.pnl for p in v.paper.all_positions())
                    if v.paper else 0.0,
                "open_positions": len(v.paper.positions()) if v.paper else 0,
                "params": dict(v.params),
            }
            for v in self._variants
        }
        return {
            "ticks": self._tick_count,
            "strategies": strategies,
            "variants": variants,
        }

    def run(self) -> None:
        """Start the hub (blocking). Runs until stop() or fatal error."""
        if not self._strategies and not self._variants:
            raise RuntimeError(
                "No strategies or variants registered. "
                "Use @hub.strategy(...) or @hub.variant(...) first."
            )
        self._log.info(
            "BotHub starting: %s %s | strategies=%d | variants=%d | total_balance=$%.2f",
            self.asset, self.timeframe,
            len(self._strategies), len(self._variants),
            sum(s.balance for s in self._active_tickers()),
        )
        self._stop_event.clear()

        try:
            while not self._stop_event.is_set():
                self._run_cycle()
        except KeyboardInterrupt:
            self._log.info("Interrupted by user")
        except Exception:
            self._log.exception("BotHub fatal error")
            raise
        finally:
            self._cleanup()

    async def run_async(self) -> None:
        """Start the hub using async IO. Runs until stop() or fatal error."""
        if not self._strategies and not self._variants:
            raise RuntimeError(
                "No strategies or variants registered. "
                "Use @hub.strategy(...) or @hub.variant(...) first."
            )
        self._log.info(
            "BotHub starting (async): %s %s | strategies=%d | variants=%d",
            self.asset, self.timeframe,
            len(self._strategies), len(self._variants),
        )
        self._stop_event.clear()

        try:
            while not self._stop_event.is_set():
                await self._run_cycle_async()
        except asyncio.CancelledError:
            self._log.info("BotHub cancelled")
        except Exception:
            self._log.exception("BotHub fatal error")
            raise
        finally:
            self._cleanup()

    def stop(self) -> None:
        """Signal the hub to stop gracefully."""
        self._log.info("BotHub stopping...")
        self._stop_event.set()
        if self._stream:
            try:
                self._stream.stop()
            except Exception:
                pass

    # ── Cycle (mirrors Bot._run_cycle) ──────────────────────────────────────

    def _run_cycle(self) -> None:
        """Single market cycle: discover → stream → tick×N → resolve → rollover."""
        try:
            self._discover()
            self._stream_prices()
        except MarketNotFound:
            self._log.warning("No market found, retrying in 30s...")
            self._sleep(30)
            return

        self._resolve_all()
        self._rollover()

    async def _run_cycle_async(self) -> None:
        """Async single market cycle."""
        try:
            self._discover()
            await self._stream_prices_async()
        except MarketNotFound:
            self._log.warning("No market found, retrying in 30s...")
            await self._asleep(30)
            return

        self._resolve_all()
        await self._rollover_async()

    # ── Lifecycle steps ─────────────────────────────────────────────────────

    def _discover(self) -> None:
        """Discover the latest market ONCE for all strategies and variants."""
        self._market = self._shared_client.markets.latest(self.asset, self.timeframe)
        self._log.info("Market found: %s (shared by %d tickers)",
                       self._market.slug, len(self._active_tickers()))

        # Build / refresh each strategy's and variant's PaperEngine + Context.
        for s in self._active_tickers():
            if s.paper is None:
                from .trading.paper_engine import PaperEngine
                s.paper = PaperEngine(
                    balance=s.balance,
                    config=self._paper_config,
                )
            s.ctx = StrategyContext(
                name=s.name,
                stream=self._stream,  # set later in _stream_prices
                paper=s.paper,
                market=self._market,
                price_history=self._price_history,
                asset=self.asset,
                chainlink_cache=self._chainlink_cache,
                get_candle_open=lambda: self._candle_open_price,
                get_seconds_in=lambda: max(0.0, time.time() - self._candle_start_time),
                get_candle_id=lambda: self._candle_id,
                bought_this_candle=self._bought_this_candle,
            )

    def _stream_prices(self) -> None:
        """Set up ONE stream and fan ticks out to all strategies + variants."""
        self._stream = self._shared_client.stream(self._market)

        # Attach each strategy's and variant's paper engine to the SAME stream
        # so that limit orders auto-fill for every ticker independently.
        for s in self._active_tickers():
            if s.paper is not None:
                s.paper.attach_stream(self._stream, self._market)
            if s.ctx is not None:
                s.ctx._stream = self._stream

        @self._stream.on("price")
        def on_price(up: float, down: float):
            if self._stop_event.is_set():
                return
            self._tick_count += 1
            self._price_history.append(up)
            # ── Candle tracking ──────────────────────────────────────────
            now = time.time()
            tf_seconds = TIMEFRAME_SECONDS[self.timeframe]
            candle_start = (now // tf_seconds) * tf_seconds
            if candle_start != self._candle_start_time:
                self._candle_start_time = candle_start
                self._candle_open_price = up
                self._candle_id += 1
                self._bought_this_candle[self._candle_id] = {}
            # Invalidate each context's cached price series so indicators
            # recompute on the new history.
            for s in self._active_tickers():
                if s.ctx is not None:
                    s.ctx._invalidate_series_cache()

            # ── Fan-out: call each strategy/variant with error isolation ──
            for s in self._active_tickers():
                if s.ctx is None or self._stop_event.is_set():
                    continue
                try:
                    s.fn(s.ctx)
                except Exception as exc:
                    self._log.exception(
                        "Strategy '%s' raised: %s", s.name, exc
                    )

        @self._stream.on("close")
        def on_close():
            self._log.info("Market closed: %s", self._market.slug)

        # Blocking — returns when the stream ends (market resolved).
        self._stream.start(background=False)

    async def _stream_prices_async(self) -> None:
        """Async single-stream fan-out to all strategies + variants."""
        self._stream = self._shared_client.stream(self._market)

        for s in self._active_tickers():
            if s.paper is not None:
                s.paper.attach_stream(self._stream, self._market)
            if s.ctx is not None:
                s.ctx._stream = self._stream

        @self._stream.on("price")
        def on_price(up: float, down: float):
            if self._stop_event.is_set():
                return
            self._tick_count += 1
            self._price_history.append(up)
            # ── Candle tracking ──────────────────────────────────────────
            now = time.time()
            tf_seconds = TIMEFRAME_SECONDS[self.timeframe]
            candle_start = (now // tf_seconds) * tf_seconds
            if candle_start != self._candle_start_time:
                self._candle_start_time = candle_start
                self._candle_open_price = up
                self._candle_id += 1
                self._bought_this_candle[self._candle_id] = {}
            for s in self._active_tickers():
                if s.ctx is not None:
                    s.ctx._invalidate_series_cache()

            for s in self._active_tickers():
                if s.ctx is None or self._stop_event.is_set():
                    continue
                try:
                    s.fn(s.ctx)
                except Exception as exc:
                    self._log.exception(
                        "Strategy '%s' raised: %s", s.name, exc
                    )

        @self._stream.on("close")
        def on_close():
            self._log.info("Market closed: %s", self._market.slug)

        await self._stream.run_async()

    def _resolve_all(self) -> None:
        """Resolve positions for every strategy and variant after the market closes."""
        if not self._market:
            return
        for s in self._active_tickers():
            if s.paper is None:
                continue
            for pos in s.paper.positions():
                if pos.resolved:
                    self._log.info(
                        "[%s] Trade resolved: %s %s | pnl=$%.2f",
                        s.name, pos.side, pos.outcome, pos.pnl,
                    )

    def _rollover(self) -> None:
        """Clean up the stream and prepare for the next cycle."""
        if self._stream:
            try:
                self._stream.stop()
            except Exception:
                pass
            self._stream = None
        self._market = None
        self._candle_id = 0
        self._bought_this_candle = {}
        for s in self._active_tickers():
            s.ctx = None
        self._log.info("Rolling over to next market...")
        self._sleep(2)

    async def _rollover_async(self) -> None:
        if self._stream:
            try:
                self._stream.stop()
            except Exception:
                pass
            self._stream = None
        self._market = None
        self._candle_id = 0
        self._bought_this_candle = {}
        for s in self._active_tickers():
            s.ctx = None
        self._log.info("Rolling over to next market...")
        await self._asleep(2)

    # ── Helpers ─────────────────────────────────────────────────────────────

    def _sleep(self, seconds: float) -> None:
        """Sleep, checking stop_event periodically."""
        for _ in range(int(seconds * 10)):
            if self._stop_event.is_set():
                break
            time.sleep(0.1)

    async def _asleep(self, seconds: float) -> None:
        """Async sleep, checking stop_event periodically."""
        for _ in range(int(seconds * 10)):
            if self._stop_event.is_set():
                break
            await asyncio.sleep(0.1)

    def _cleanup(self) -> None:
        """Clean up shared resources."""
        if self._stream:
            try:
                self._stream.stop()
            except Exception:
                pass
        if self._chainlink_cache is not None:
            try:
                self._chainlink_cache.stop()
            except Exception:
                pass
        self._shared_client.close()
        self._log.info(
            "BotHub stopped — total ticks=%d, strategies=%d, variants=%d",
            self._tick_count, len(self._strategies), len(self._variants),
        )

    # ── Variant comparison & persistence ─────────────────────────────────────

    def compare_variants(self) -> ComparisonReport:
        from .report.comparison import ComparisonReport as CR, build_variant_result
        if not self._variants:
            return CR(results=[], asset=self.asset, timeframe=self.timeframe)
        results = [build_variant_result(v) for v in self._variants]
        for v in self._variants:
            v.run_count += 1
        return CR(
            results=sorted(results, key=lambda r: r.pnl, reverse=True),
            asset=self.asset,
            timeframe=self.timeframe,
        )

    def list_runs(self, directory: Optional[str] = None) -> list[dict]:
        from .report.comparison import list_runs as _list_runs
        return _list_runs(directory=directory)

    def load_run(self, timestamp: str, directory: Optional[str] = None) -> ComparisonReport:
        from .report.comparison import load_run as _load_run
        return _load_run(timestamp=timestamp, directory=directory)
