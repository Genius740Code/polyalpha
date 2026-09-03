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

Comparison (variants)
---------------------
Any strategy can carry free-form ``params`` metadata. Strategies with
non-empty ``params`` are called "variants" and can be compared
side-by-side via ``compare_variants()``::

    hub = polyalpha.BotHub("BTC", "5m")

    @hub.strategy("rsi_70", params={"rsi_threshold": 70})
    def rsi_70(ctx):
        if ctx.rsi and ctx.rsi > 70:
            ctx.buy("DOWN", 10)

    @hub.strategy("rsi_30", params={"rsi_threshold": 30})
    def rsi_30(ctx):
        if ctx.rsi and ctx.rsi < 30:
            ctx.buy("UP", 10)

    hub.run()
    report = hub.compare_variants()   # ComparisonReport sorted by P&L
    report.print()

You can also use the ``variant()`` alias — it is identical to
``strategy()`` and exists purely for readability::

    @hub.variant("rsi_70", params={"rsi_threshold": 70})  # same as strategy()
"""

from __future__ import annotations

import asyncio
import logging
import threading
import time
from collections import defaultdict, deque
from typing import TYPE_CHECKING, Callable, Optional, Union

if TYPE_CHECKING:
    from ..report.comparison import ComparisonReport

try:
    from ..notifications.telegram import TelegramNotifier
except ImportError:
    TelegramNotifier = None  # type: ignore[assignment]

try:
    from ..windows import TimeWindow
except ImportError:
    TimeWindow = None  # type: ignore[assignment]

from ..client import Client
from ..core import (
    ASSETS,
    FALLBACK_PRICE,
    TIMEFRAME_SECONDS,
    Market,
)
from ..core.errors import MarketNotFound
from ..orderbook import ClobBookClient, OrderBookFeed
from ..trading.paper_config import PaperConfig
from ..trading.paper_engine import PaperEngine

from .binance import BinanceAccessor
from .context import StrategyContext
from .history import _resolve_chainlink_history
from .indicators import _log_indicators
from .models import _RegisteredStrategy

Variant = _RegisteredStrategy  # backward compat alias for hub internals

log = logging.getLogger(__name__)


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
        BTC, ETH, SOL, XRP, DOGE, HYPE, BNB.
    timeframe : str
        5m, 15m, 1h, 4h, 24h.
    default_balance : float
        Default starting paper balance per strategy (default 100.0).
    mode : str
        Fee/execution template: ``"simple"``, ``"realistic"``, ``"custom"``.
    paper_config : PaperConfig, optional
        Custom paper config when ``mode="custom"``.
    log_dir : str, optional
        Directory for per-strategy rotating log files.  If set, each
        strategy and variant gets its own ``{name}.log`` file (5 MB max,
        3 backups) with DEBUG-level output.

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
        asset: str,
        timeframe: str,
        default_balance: float = 100.0,
        mode: str = "simple",
        paper_config: Optional[PaperConfig] = None,
        chainlink: bool = True,
        log_dir: Optional[str] = None,
        globals: Optional[object] = None,
        buy_once_per_market: bool = True,
        chainlink_history=None,
        market_provider=None,
        engine: str | object | None = None,
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
        self.buy_once_per_market = buy_once_per_market
        self._bought_this_market: dict[str, bool] = {}
        self._log_dir = log_dir
        self._globals = globals  # Shared feeds — one connection, many strategies

        from ..trading.paper_config import get_paper_config_from_preset

        if mode == "realistic":
            self._paper_config = get_paper_config_from_preset("REALISTIC")
        elif mode == "custom":
            self._paper_config = paper_config or PaperConfig()
        else:
            self._paper_config = get_paper_config_from_preset("TEST")

        # chainlink_history may be in kwargs (e.g. from tests)
        if chainlink_history is None and "chainlink_history" in kwargs:
            chainlink_history = kwargs.pop("chainlink_history")
        else:
            kwargs.pop("chainlink_history", None)

        # market_provider may be passed positionally or via kwargs
        if market_provider is None and "market_provider" in kwargs:
            market_provider = kwargs.pop("market_provider")
        else:
            kwargs.pop("market_provider", None)
        self._market_provider = market_provider

        # Engine selection — "paper" (default, isolated per-strategy) or "real" (shared client.real)
        if engine is None:
            engine_name = "paper"
            # allow paper= kwarg for backcompat
            if "paper" in kwargs:
                pv = kwargs.pop("paper")
                engine_name = "real" if pv is False else "paper"
        elif isinstance(engine, str):
            engine_name = engine.lower()
        else:
            engine_name = "custom"
        self.engine = engine_name
        self._custom_engine = engine if not isinstance(engine, str) and engine is not None else None

        # One shared client for market discovery + stream creation.
        # Its paper engine is unused when engine=="paper" — each strategy gets its own.
        # For engine=="real", shared client's real engine is the shared engine.
        self._shared_client = Client(
            balance=default_balance,
            paper_config=self._paper_config,
            **kwargs,
        )
        if engine_name == "real" and self._shared_client.real is None:
            raise ValueError("engine='real' requires private_key + rpc_url + polymarket_api_key")
        if engine_name == "custom" and self._custom_engine is None:
            raise ValueError("custom engine instance required")

        self._strategies: list[_RegisteredStrategy] = []
        self._market: Optional[Market] = None
        self._stream = None
        self._price_history: deque[float] = deque(maxlen=200)
        self._down_price_history: deque[float] = deque(maxlen=200)
        self._stop_event = threading.Event()
        self._tick_count = 0
        self._candle_start_time: float = 0.0
        self._candle_open_price: Optional[float] = None
        self._candle_id: int = 0
        self._bought_this_candle: dict[int, dict[str, set[str]]] = {}
        self._final_up: Optional[float] = None
        self._final_down: Optional[float] = None
        # Resolve the shared Chainlink streamer ONCE. When the caller supplies
        # a shared globals.price_feed we reuse it for both the price cache and
        # the context streamer instead of opening a second oracle socket.
        shared_cl = None
        if self._globals is not None:
            try:
                from ..analysis.streaming import ChainlinkStreamer
                _pf = getattr(self._globals, "price_feed", None)
                shared_cl = _pf if isinstance(_pf, ChainlinkStreamer) else None
            except Exception:
                shared_cl = None
        self._chainlink_cache: Optional[object] = None
        if chainlink:
            try:
                from ..core.chainlink_cache import ChainlinkPriceCache
                self._chainlink_cache = ChainlinkPriceCache(symbol=self.asset, streamer=shared_cl)
            except Exception as exc:
                self._log.warning("Chainlink cache unavailable: %s", exc)
        self._log = logging.getLogger("polyalpha.BotHub")
        self._strategy_loggers: dict[str, logging.Logger] = {}
        _log_indicators()

        # ── Event / hook system ──────────────────────────────────────────
        self._handlers: dict[str, list[Callable]] = defaultdict(list)
        self._interval_handlers: list[dict] = []

        # Initialize Telegram notifier (optional)
        self._telegram: Optional[TelegramNotifier] = None
        if TelegramNotifier is not None:
            self._telegram = TelegramNotifier()

        # Initialize Chainlink streamer (live BTC spot from Polymarket).
        # Reuse the shared globals.price_feed when one is provided so we do
        # NOT open a second oracle connection — the caller owns its lifecycle.
        self._chainlink: Optional[object] = None
        self._shared_cl_window: Optional[TimeWindow] = TimeWindow(max_age=120) if TimeWindow is not None else None
        try:
            from ..analysis.streaming import ChainlinkStreamer
            cl = shared_cl
            if cl is None:
                cl = ChainlinkStreamer()
                cl.start(asset, background=True)
            self._chainlink = cl
        except Exception as exc:
            self._log.debug("Chainlink streamer not available: %s", exc)

        # Initialize Binance accessor (TA on Binance data)
        self._binance: Optional[BinanceAccessor] = None
        try:
            self._binance = BinanceAccessor(asset=asset, timeframe=timeframe)
        except Exception as exc:
            self._log.debug("BinanceAccessor not available: %s", exc)

        # ── Chainlink history (shared candle store — user chooses {"1m":10, "1h":50, "1s":20}) ─
        # One recorder per (db_path, asset) via registry; unused TFs pruned automatically.
        self._chainlink_history = None
        self._chainlink_history_owned = False
        self._on_warmup = None
        self._last_warmup_emit = 0.0
        # Prefer globals.chainlink_history if caller supplied it
        _g_hist = getattr(self._globals, "chainlink_history", None) if self._globals is not None else None
        if _g_hist is not None:
            self._chainlink_history = _g_hist
            self._chainlink_history_owned = False
        elif chainlink_history is not None:
            try:
                rec, owned = _resolve_chainlink_history(chainlink_history, asset)
                self._chainlink_history = rec
                self._chainlink_history_owned = owned
                if rec is not None:
                    # reuse registry if shared flag, else direct
                    try:
                        rec.start(asset, background=True)
                    except Exception as exc:
                        self._log.warning("Chainlink history start failed: %s", exc)
                    self._log.info("Chainlink history enabled (hub): %s", getattr(rec.config, "warmup", rec))
            except Exception as exc:
                self._log.debug("Chainlink history init skipped (hub): %s", exc)

    @property
    def chainlink_history(self):
        """Shared :class:`~polyalpha.history.ChainlinkRecorder` or None."""
        return getattr(self, "_chainlink_history", None)

    def on_warmup(self, fn: Callable) -> Callable:
        """Register warmup callback — called with status dict while warming.

        Example: ``@hub.on_warmup(lambda s: print(f"warming {s}"))``
        Works for both ``block="wait"`` (hub blocks all strats) and
        ``block="skip"`` (each strat self-guards).
        """
        self._on_warmup = fn
        return fn

    # ── Helpers ─────────────────────────────────────────────────────────────

    def _active_tickers(self) -> list[_RegisteredStrategy]:
        """All registered strategies (including those with params)."""
        return self._strategies

    # ── Public API ──────────────────────────────────────────────────────────

    def strategy(
        self,
        name: str,
        balance: Optional[float] = None,
        params: Optional[dict] = None,
        id: str = "",
    ) -> Callable:
        """
        Decorator — register a strategy function with the hub.

        Parameters
        ----------
        name : str
            Unique strategy name (used in logs and stats).
        balance : float, optional
            Per-strategy starting balance. Defaults to ``default_balance``.
        params : dict, optional
            Free-form parameter metadata for comparison reports.
            When provided, the strategy is treated as a "variant" and
            included in ``compare_variants()`` output.
        id : str, optional
            Stable identifier for persistence snapshots. Defaults to ``name``.

        Example
        -------
        >>> @hub.strategy("momentum", balance=500)
        ... def momentum(ctx):
        ...     if ctx.price.up > 0.9:
        ...         ctx.buy("UP", 20)

        >>> @hub.strategy("rsi_70", params={"rsi_threshold": 70})
        ... def rsi_70(ctx):
        ...     if ctx.rsi and ctx.rsi > 70:
        ...         ctx.buy("DOWN", 10)
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
                    params=dict(params) if params else {},
                    id=id or name,
                )
            )
            has_params = bool(params)
            label = "variant" if has_params else "strategy"
            log_params = f", params={params}" if has_params else ""
            self._log.info(
                "Registered %s '%s' (balance=$%.2f%s)",
                label, name, balance or self.default_balance, log_params,
            )
            return fn

        return decorator

    def add_strategy(
        self,
        name: str,
        fn: Callable[[StrategyContext], None],
        balance: Optional[float] = None,
        params: Optional[dict] = None,
        id: str = "",
    ) -> None:
        """Register a strategy without decorator syntax."""
        self.strategy(name, balance=balance, params=params, id=id)(fn)

    def variant(
        self,
        name: str,
        balance: Optional[float] = None,
        params: Optional[dict] = None,
        id: str = "",
    ) -> Callable:
        """Alias for ``strategy()`` — registers a variant for comparison.

        ``variant()`` is identical to ``strategy()``. Use it when you want
        to emphasise that this strategy carries parameter metadata for
        cross-variant comparison via ``compare_variants()``.

        See :meth:`strategy` for full parameter documentation.
        """
        return self.strategy(name, balance=balance, params=params, id=id)

    def add_variant(
        self,
        name: str,
        fn: Callable[[StrategyContext], None],
        balance: Optional[float] = None,
        params: Optional[dict] = None,
        id: str = "",
    ) -> None:
        """Register a variant without decorator syntax. Alias for ``add_strategy()``."""
        self.add_strategy(name, fn, balance=balance, params=params, id=id)

    # ── Event / hook system ─────────────────────────────────────────────

    def on(self, event: str, fn: Optional[Callable] = None):
        """Register an event handler (decorator or imperative).

        Supported events
        ----------------
        ``"start"``
            Hub started — handler receives no args.
        ``"stop"``
            Hub stopping gracefully — handler receives no args.
        ``"tick"``
            Every price tick — handler receives ``(up, down)``.
        ``"candle_open"``
            A new candle started — handler receives ``(open_price, candle_id)``.
        ``"candle_close"``
            The current candle closed — handler receives
            ``(candle_id, open_price, close_price)``.
        ``"error"``
            A strategy raised an exception — handler receives
            ``(strategy_name, exception)``.

        Usage
        -----
            @hub.on("tick")
            def on_tick(up, down):
                print(f"price={up:.3f}/{down:.3f}")

            @hub.on("candle_open")
            def on_candle_open(open_price, candle_id):
                print(f"New candle #{candle_id} opened at {open_price}")

            hub.on("stop", my_cleanup_fn)
        """
        if fn is None:
            return lambda f: self._add_handler(event, f)
        self._add_handler(event, fn)
        return fn

    def add_handler(self, event: str, fn: Callable) -> None:
        """Imperative event handler registration.

        See :meth:`on` for supported events and signatures.
        """
        self._add_handler(event, fn)

    def _add_handler(self, event: str, fn: Callable) -> None:
        if not callable(fn):
            raise TypeError(f"handler must be callable, got {type(fn).__name__}")
        self._handlers[event].append(fn)
        self._log.debug("Registered handler for event '%s'", event)

    def every(self, seconds: Union[float, int], fn: Optional[Callable] = None):
        """Register a periodic timer callback (decorator or imperative).

        The handler is called roughly every *seconds* seconds, checked
        on each price tick.  Handlers receive ``(up, down)`` — the
        latest mid-prices from the shared stream.

        Examples
        --------
            @hub.every(30)
            def status_check(up, down):
                print(f"30s ticker — up={up:.3f} down={down:.3f}")

            hub.every(60, my_minute_fn)
        """
        seconds = float(seconds)
        if seconds <= 0:
            raise ValueError("seconds must be positive")

        def _register(f):
            self._interval_handlers.append({
                "interval": seconds,
                "fn": f,
                "last_called": 0.0,
            })
            self._log.debug("Registered interval handler every %.1fs", seconds)
            return f

        if fn is None:
            return _register
        return _register(fn)

    # ── Event dispatch ──────────────────────────────────────────────────

    def _fire(self, event: str, *args, **kwargs) -> None:
        """Dispatch *event* to all registered handlers, isolating errors."""
        for fn in list(self._handlers.get(event, [])):
            try:
                fn(*args, **kwargs)
            except Exception as exc:
                self._log.exception("Handler for '%s' raised: %s", event, exc)

    def _fire_interval_handlers(self, *args, **kwargs) -> None:
        """Check and fire any due interval handlers."""
        now = time.time()
        for h in self._interval_handlers:
            if now - h["last_called"] >= h["interval"]:
                h["last_called"] = now
                try:
                    h["fn"](*args, **kwargs)
                except Exception as exc:
                    self._log.exception("Interval handler raised: %s", exc)

    @property
    def tick_count(self) -> int:
        """Total price ticks received this session."""
        return self._tick_count

    @property
    def strategy_count(self) -> int:
        """Total registered strategies."""
        return len(self._strategies)

    @property
    def variant_count(self) -> int:
        """Total registered strategies (alias for strategy_count)."""
        return len(self._strategies)

    @property
    def total_count(self) -> int:
        """Total registered strategies."""
        return len(self._strategies)

    @property
    def _variants(self) -> list[_RegisteredStrategy]:
        """Backward-compat: all strategies (variant is now an alias for strategy)."""
        return self._strategies

    @property
    def variants(self) -> list[_RegisteredStrategy]:
        """Read-only view of all registered strategies."""
        return list(self._strategies)

    @property
    def strategies(self) -> list[_RegisteredStrategy]:
        """Read-only view of all registered strategies."""
        return list(self._strategies)

    @property
    def stats(self) -> dict:
        """Per-strategy running stats."""
        stats = {}
        for s in self._strategies:
            entry = {
                "balance": s.paper.balance if s.paper else s.balance,
                "pnl": sum(p.pnl for p in s.paper.all_positions())
                    if s.paper else 0.0,
                "open_positions": len(s.paper.positions()) if s.paper else 0,
            }
            if s.params:
                entry["params"] = dict(s.params)
            stats[s.name] = entry
        return {
            "ticks": self._tick_count,
            "strategies": stats,
        }

    def run(self) -> None:
        """Start the hub (blocking). Runs until stop() or fatal error."""
        if not self._strategies:
            raise RuntimeError(
                "No strategies registered. "
                "Use @hub.strategy(...) or @hub.variant(...) first."
            )
        self._log.info(
            "BotHub starting: %s %s | strategies=%d | total_balance=$%.2f",
            self.asset, self.timeframe,
            len(self._strategies),
            sum(s.balance for s in self._active_tickers()),
        )
        self._stop_event.clear()
        self._fire("start")

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
        if not self._strategies:
            raise RuntimeError(
                "No strategies registered. "
                "Use @hub.strategy(...) or @hub.variant(...) first."
            )
        self._log.info(
            "BotHub starting (async): %s %s | strategies=%d",
            self.asset, self.timeframe,
            len(self._strategies),
        )
        self._stop_event.clear()
        self._fire("start")

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

    def _resolve_external_market(self):
        """Try to obtain a :class:`Market` from ``self._market_provider``."""
        provider = getattr(self, "_market_provider", None)
        if provider is None:
            return None
        result = None
        try:
            if callable(provider):
                try:
                    result = provider()
                except TypeError:
                    result = provider(self.asset, self.timeframe)
            elif hasattr(provider, "get_market"):
                result = provider.get_market()
            elif hasattr(provider, "market"):
                result = getattr(provider, "market")
                if result is None and hasattr(provider, "get_market"):
                    try:
                        result = provider.get_market()
                    except Exception:
                        result = None
            elif hasattr(provider, "latest"):
                result = provider.latest(self.asset, self.timeframe)
            else:
                return None
        except Exception as exc:
            self._log.debug("Market provider call failed: %s", exc)
            return None
        if result is None:
            return None
        if isinstance(result, str):
            slug = result.strip()
            if not slug:
                return None
            try:
                return self._shared_client.markets.get(slug)
            except Exception as exc:
                self._log.debug("Market provider slug resolution failed for %s: %s", slug, exc)
                return None
        if hasattr(result, "slug"):
            return result
        return None

    def _discover(self) -> None:
        """Discover the latest market ONCE for all strategies and variants."""
        if getattr(self, "_market_provider", None) is not None:
            try:
                ext_market = self._resolve_external_market()
                if ext_market is not None:
                    self._market = ext_market
                    self._log.info("Market found (via provider): %s (shared by %d tickers)",
                                   self._market.slug, len(self._active_tickers()))
                    # Build / refresh each strategy's and variant's engine + Context
                    for s in self._active_tickers():
                        if s.paper is None:
                            if getattr(self, "engine", "paper") == "real":
                                # real: share single RealTradingEngine across strategies
                                s.paper = self._shared_client.real  # type: ignore
                                s._engine = self._shared_client.real  # type: ignore
                            elif getattr(self, "engine", "paper") == "custom" and getattr(self, "_custom_engine", None) is not None:
                                s.paper = self._custom_engine  # type: ignore
                                s._engine = self._custom_engine  # type: ignore
                            else:
                                from ..trading.paper_engine import PaperEngine
                                s.paper = PaperEngine(
                                    balance=s.balance,
                                    config=self._paper_config,
                                    db=self._shared_client.db,
                                )
                                s._engine = s.paper
                        s.ctx = StrategyContext(
                            name=s.name,
                            stream=self._stream,
                            paper=s.paper,
                            market=self._market,
                            price_history=self._price_history,
                            down_price_history=self._down_price_history,
                            asset=self.asset,
                            clob=self._shared_client._clob,
                            chainlink_cache=self._chainlink_cache,
                            chainlink=self._chainlink,
                            binance=self._binance,
                            cl_window=self._shared_cl_window,
                            globals=self._globals,
                            get_candle_open=lambda: self._candle_open_price,
                            get_seconds_in=lambda: max(0.0, time.time() - self._candle_start_time),
                            get_candle_id=lambda: self._candle_id,
                            bought_this_candle=self._bought_this_candle,
                            hub=self,
                            chainlink_history=self._chainlink_history,
                            engine=getattr(s, "_engine", s.paper),
                        )
                        if self._log_dir and s.name not in self._strategy_loggers:
                            from ..utils.logging_utils import setup_strategy_logger
                            slog = setup_strategy_logger(
                                f"{self.asset}_{s.name}", self._log_dir,
                            )
                            self._strategy_loggers[s.name] = slog
                    return
                self._log.debug("Market provider returned None, falling back to native discovery")
            except Exception as exc:
                self._log.error("Market provider discovery failed: %s, falling back", exc)
        self._market = self._shared_client.markets.latest(self.asset, self.timeframe)
        self._log.info("Market found: %s (shared by %d tickers)",
                       self._market.slug, len(self._active_tickers()))

        # Build / refresh each strategy's and variant's engine + Context.
        for s in self._active_tickers():
            if s.paper is None:
                if getattr(self, "engine", "paper") == "real":
                    s.paper = self._shared_client.real  # type: ignore
                    s._engine = self._shared_client.real  # type: ignore
                elif getattr(self, "engine", "paper") == "custom" and getattr(self, "_custom_engine", None) is not None:
                    s.paper = self._custom_engine  # type: ignore
                    s._engine = self._custom_engine  # type: ignore
                else:
                    from ..trading.paper_engine import PaperEngine
                    s.paper = PaperEngine(
                        balance=s.balance,
                        config=self._paper_config,
                        db=self._shared_client.db,
                    )
                    s._engine = s.paper
            s.ctx = StrategyContext(
                name=s.name,
                stream=self._stream,  # set later in _stream_prices
                paper=s.paper,
                market=self._market,
                price_history=self._price_history,
                down_price_history=self._down_price_history,
                asset=self.asset,
                clob=self._shared_client._clob,
                chainlink_cache=self._chainlink_cache,
                chainlink=self._chainlink,
                binance=self._binance,
                cl_window=self._shared_cl_window,
                globals=self._globals,
                get_candle_open=lambda: self._candle_open_price,
                get_seconds_in=lambda: max(0.0, time.time() - self._candle_start_time),
                get_candle_id=lambda: self._candle_id,
                bought_this_candle=self._bought_this_candle,
                hub=self,
                chainlink_history=self._chainlink_history,
                engine=getattr(s, "_engine", s.paper),
            )
            # Per-strategy rotating file logger
            if self._log_dir and s.name not in self._strategy_loggers:
                from ..utils.logging_utils import setup_strategy_logger
                slog = setup_strategy_logger(
                    f"{self.asset}_{s.name}", self._log_dir,
                )
                self._strategy_loggers[s.name] = slog

    def _stream_prices(self) -> None:
        """Set up ONE stream and fan ticks out to all strategies + variants."""
        self._stream = self._shared_client.stream(self._market)

        # Attach each strategy's and variant's engine to the SAME stream
        for s in self._active_tickers():
            eng = getattr(s, "_engine", None) or getattr(s, "paper", None)
            if eng is not None:
                try:
                    eng.attach_stream(self._stream, self._market)
                except Exception:
                    pass
            if s.ctx is not None:
                s.ctx._stream = self._stream
                # keep ctx engine in sync
                if eng is not None:
                    s.ctx._engine = eng
                    s.ctx._paper = eng

        @self._stream.on("price")
        def on_price(up: float, down: float):
            if self._stop_event.is_set():
                return
            self._tick_count += 1
            self._price_history.append(up)
            self._down_price_history.append(down)
            # Refresh Binance data on each tick (candle-gated internally)
            if self._binance is not None:
                try:
                    self._binance._refresh()
                except Exception:
                    pass
            # ── Chainlink history warmup gate (hub union) ──────────────────
            # User chose e.g. {"1m":10, "1h":50, "1s":20}; hub waits for ALL before any strat runs
            if self._chainlink_history is not None and getattr(self._chainlink_history, "config", None) is not None:
                cfg = self._chainlink_history.config
                need = getattr(cfg, "warmup", {}) or {}
                if need and cfg.block == "wait" and not self._chainlink_history.is_ready_map(need):
                    now_w = time.time()
                    if now_w - getattr(self, "_last_warmup_emit", 0) >= getattr(cfg, "warmup_emit_interval", 5.0):
                        self._last_warmup_emit = now_w
                        try:
                            status = self._chainlink_history.status(need)
                        except Exception:
                            status = {"warming": True}
                        self._log.info("Warming chainlink history (hub) %s", status)
                        self._fire("warmup", status)
                        if getattr(self, "_on_warmup", None):
                            try:
                                self._on_warmup(status)
                            except Exception:
                                pass
                    # still advance candle tracking but skip strat fan-out
                    now2 = time.time()
                    tf_seconds = TIMEFRAME_SECONDS.get(self.timeframe, 300)
                    candle_start = (now2 // tf_seconds) * tf_seconds
                    if candle_start != self._candle_start_time:
                        self._fire("candle_close", self._candle_id, self._candle_open_price, up)
                        self._candle_start_time = candle_start
                        self._candle_open_price = up
                        self._candle_id += 1
                        self._bought_this_candle[self._candle_id] = {}
                        self._fire("candle_open", self._candle_open_price, self._candle_id)
                    return

            # ── Candle tracking ──────────────────────────────────────────
            now = time.time()
            tf_seconds = TIMEFRAME_SECONDS[self.timeframe]
            candle_start = (now // tf_seconds) * tf_seconds
            if candle_start != self._candle_start_time:
                self._fire("candle_close", self._candle_id, self._candle_open_price, up)
                self._candle_start_time = candle_start
                self._candle_open_price = up
                self._candle_id += 1
                self._bought_this_candle[self._candle_id] = {}
                self._fire("candle_open", self._candle_open_price, self._candle_id)
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
                    slog = self._strategy_loggers.get(s.name, self._log)
                    slog.exception(
                        "Strategy '%s' raised: %s", s.name, exc
                    )
                    self._fire("error", s.name, exc)

            # ── Hub-level events ───────────────────────────────────────
            self._fire("tick", up, down)
            self._fire_interval_handlers(up, down)

        @self._stream.on("close")
        def on_close():
            self._final_up = getattr(self._stream, "up", None)
            self._final_down = getattr(self._stream, "down", None)
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
            self._down_price_history.append(down)
            # Refresh Binance data on each tick (candle-gated internally)
            if self._binance is not None:
                try:
                    self._binance._refresh()
                except Exception:
                    pass
            # ── Chainlink history warmup gate (hub union, async) ───────
            if self._chainlink_history is not None and getattr(self._chainlink_history, "config", None) is not None:
                cfg = self._chainlink_history.config
                need = getattr(cfg, "warmup", {}) or {}
                if need and cfg.block == "wait" and not self._chainlink_history.is_ready_map(need):
                    now_w = time.time()
                    if now_w - getattr(self, "_last_warmup_emit", 0) >= getattr(cfg, "warmup_emit_interval", 5.0):
                        self._last_warmup_emit = now_w
                        try:
                            status = self._chainlink_history.status(need)
                        except Exception:
                            status = {"warming": True}
                        self._log.info("Warming chainlink history (hub async) %s", status)
                        self._fire("warmup", status)
                        if getattr(self, "_on_warmup", None):
                            try:
                                self._on_warmup(status)
                            except Exception:
                                pass
                    now2 = time.time()
                    tf_seconds = TIMEFRAME_SECONDS.get(self.timeframe, 300)
                    candle_start = (now2 // tf_seconds) * tf_seconds
                    if candle_start != self._candle_start_time:
                        self._fire("candle_close", self._candle_id, self._candle_open_price, up)
                        self._candle_start_time = candle_start
                        self._candle_open_price = up
                        self._candle_id += 1
                        self._bought_this_candle[self._candle_id] = {}
                        self._fire("candle_open", self._candle_open_price, self._candle_id)
                    return
            # ── Candle tracking ──────────────────────────────────────────
            now = time.time()
            tf_seconds = TIMEFRAME_SECONDS[self.timeframe]
            candle_start = (now // tf_seconds) * tf_seconds
            if candle_start != self._candle_start_time:
                self._fire("candle_close", self._candle_id, self._candle_open_price, up)
                self._candle_start_time = candle_start
                self._candle_open_price = up
                self._candle_id += 1
                self._bought_this_candle[self._candle_id] = {}
                self._fire("candle_open", self._candle_open_price, self._candle_id)
            for s in self._active_tickers():
                if s.ctx is not None:
                    s.ctx._invalidate_series_cache()

            for s in self._active_tickers():
                if s.ctx is None or self._stop_event.is_set():
                    continue
                try:
                    s.fn(s.ctx)
                except Exception as exc:
                    slog = self._strategy_loggers.get(s.name, self._log)
                    slog.exception(
                        "Strategy '%s' raised: %s", s.name, exc
                    )
                    self._fire("error", s.name, exc)

            # ── Hub-level events ───────────────────────────────────────
            self._fire("tick", up, down)
            self._fire_interval_handlers(up, down)

        @self._stream.on("close")
        def on_close():
            self._final_up = getattr(self._stream, "up", None)
            self._final_down = getattr(self._stream, "down", None)
            self._log.info("Market closed: %s", self._market.slug)

        await self._stream.run_async()

    def _resolve_all(self) -> None:
        """Resolve positions for every strategy and variant after the market closes."""
        if not self._market:
            return
        final_up = self._final_up if self._final_up is not None else getattr(self._stream, "up", None) if self._stream else None
        final_down = self._final_down if self._final_down is not None else getattr(self._stream, "down", None) if self._stream else None
        if final_up is None or final_down is None or final_up == final_down:
            self._log.info("No final prices to resolve %s", self._market.slug)
            return
        outcome = "UP" if final_up > final_down else "DOWN"
        # Real engine: on-chain settlement, no manual resolve; just sync
        if getattr(self, "engine", "paper") == "real":
            self._log.info("Real engine: market %s outcome %s (on-chain settle pending)", self._market.slug, outcome)
            try:
                if hasattr(self._shared_client.real, "sync_positions_from_chain"):
                    self._shared_client.real.sync_positions_from_chain()
            except Exception:
                pass
            return
        for s in self._active_tickers():
            eng = getattr(s, "_engine", None) or s.paper
            if eng is None:
                continue
            try:
                eng.resolve(self._market, outcome)
            except Exception as exc:
                self._log.warning("Failed to resolve %s: %s", s.name, exc)
                continue
            for pos in eng.all_positions():
                if pos.market_id != self._market.id or not pos.resolved:
                    continue
                slog = self._strategy_loggers.get(s.name, self._log)
                slog.info(
                    "Trade resolved: %s %s | pnl=$%.2f",
                    pos.side, pos.outcome, pos.pnl,
                )

                # Send Telegram notification if configured
                if self._telegram:
                    self._telegram.send_resolve(
                        asset=self.asset,
                        side=pos.side,
                        outcome=pos.outcome,
                        pnl=pos.pnl,
                        strategy_name=s.name
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
        self._candle_start_time = 0.0
        self._candle_open_price = None
        self._final_up = None
        self._final_down = None
        self._bought_this_candle = {}
        self._bought_this_market = {}
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
        self._candle_start_time = 0.0
        self._candle_open_price = None
        self._final_up = None
        self._final_down = None
        self._bought_this_candle = {}
        self._bought_this_market = {}
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
        self._fire("stop")
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
        rec = getattr(self, "_chainlink_history", None)
        if rec is not None and getattr(self, "_chainlink_history_owned", False):
            try:
                rec.stop()
            except Exception:
                pass
        self._shared_client.close()
        self._log.info(
            "BotHub stopped — total ticks=%d, strategies=%d",
            self._tick_count, len(self._strategies),
        )

    # ── Variant comparison & persistence ─────────────────────────────────────

    def compare_variants(self) -> ComparisonReport:
        """Build a comparison report for all strategies with params.

        Results are sorted by P&L descending and include per-strategy
        metrics (win rate, Sharpe, max drawdown, etc.).
        """
        from ..report.comparison import ComparisonReport as CR
        from ..report.comparison import build_variant_result
        targets = [s for s in self._strategies if s.params] or self._strategies
        if not targets:
            return CR(results=[], asset=self.asset, timeframe=self.timeframe)
        results = [build_variant_result(v) for v in targets]
        for v in targets:
            v.run_count += 1
        return CR(
            results=sorted(results, key=lambda r: r.pnl, reverse=True),
            asset=self.asset,
            timeframe=self.timeframe,
        )

    def list_runs(self, directory: Optional[str] = None) -> list[dict]:
        from ..report.comparison import list_runs as _list_runs
        return _list_runs(directory=directory)

    def load_run(self, timestamp: str, directory: Optional[str] = None) -> ComparisonReport:
        from ..report.comparison import load_run as _load_run
        return _load_run(timestamp=timestamp, directory=directory)
