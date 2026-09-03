"""
Bot — one-line bot runner for Polymarket.

Usage
-----
    bot = polyalpha.Bot("BTC", "5m", balance=500)

    @bot.on_tick
    def strategy(ctx):
        if ctx.price.up > 0.9 and ctx.rsi > 50:
            ctx.buy("UP", 20)

    bot.run()  # blocking, auto-rollover

The Bot handles the full lifecycle:
discover → stream → tick → resolve → rollover → repeat
"""

from __future__ import annotations

import asyncio
import logging
import threading
import time
from collections import deque
from dataclasses import dataclass
from typing import TYPE_CHECKING, Callable, Optional

from .client import Client
from .core import (
    ASSETS,
    FALLBACK_PRICE,
    TIMEFRAME_SECONDS,
    Market,
)
from .core.errors import MarketNotFound

if TYPE_CHECKING:
    from .conditions import Condition
    from .trading.paper_config import PaperConfig

try:
    from .notifications.telegram import TelegramNotifier
except ImportError:
    TelegramNotifier = None  # type: ignore[assignment]

log = logging.getLogger(__name__)

# Optional indicator deps — imported once at module level, not per property call.
try:
    import pandas as pd
except ImportError:
    pd = None  # type: ignore[assignment]

try:
    from .analysis._native_ta import bbands as _bbands
    from .analysis._native_ta import donchian as _donchian
    from .analysis._native_ta import ema as _ema
    from .analysis._native_ta import ichimoku as _ichimoku
    from .analysis._native_ta import macd as _macd
    from .analysis._native_ta import psar as _psar
    from .analysis._native_ta import rsi as _rsi
    from .analysis._native_ta import sma as _sma
except ImportError:
    _rsi = _sma = _ema = _macd = _bbands = _psar = _ichimoku = _donchian = None

try:
    from .bot_hub import IndicatorAccessor, BinanceAccessor
except ImportError:
    IndicatorAccessor = None  # type: ignore[assignment, misc]
    BinanceAccessor = None

try:
    from .analysis import ChainlinkStreamer
except ImportError:
    ChainlinkStreamer = None

try:
    from .windows import TimeWindow
except ImportError:
    TimeWindow = None  # type: ignore[assignment]


# ── Chainlink history helper ───────────────────────────────────────────────

def _resolve_chainlink_history(
    value, asset: str
):
    """
    Normalize chainlink_history param to (recorder, owned).

    Accepts:
      None / False -> (None, False)
      True        -> default ChainlinkRecorder for asset ("1m": 20)
      dict        -> warmup dict {"1m":10, "1h":50}
      ChainlinkHistoryConfig -> config
      ChainlinkRecorder -> shared recorder (not owned)
    Returns (recorder|None, owned:bool)
    """
    if value is None or value is False:
        return None, False
    try:
        from .history import ChainlinkHistoryConfig, ChainlinkRecorder
    except ImportError:
        return None, False

    if isinstance(value, ChainlinkRecorder):
        return value, False
    if isinstance(value, ChainlinkHistoryConfig):
        rec = ChainlinkRecorder(config=value)
        return rec, True
    if isinstance(value, dict):
        # dict warmup like {"1m":10, "1h":50, "1s":20}
        cfg = ChainlinkHistoryConfig(warmup=dict(value))
        rec = ChainlinkRecorder(config=cfg)
        return rec, True
    if value is True:
        cfg = ChainlinkHistoryConfig(warmup={"1m": 20})
        rec = ChainlinkRecorder(config=cfg)
        return rec, True
    # string path? treat as db_path with default warmup
    if isinstance(value, str):
        cfg = ChainlinkHistoryConfig(warmup={"1m": 20}, db_path=value)
        rec = ChainlinkRecorder(config=cfg)
        return rec, True
    return None, False


# ── Price Snapshot ─────────────────────────────────────────────────────────────

@dataclass
class PriceSnapshot:
    """Current UP/DOWN prices from the stream."""
    up: float
    down: float


# ── Tick Context ───────────────────────────────────────────────────────────────

class TickContext:
    """
    Trading context passed to the strategy function on every tick.

    Properties
    ----------
    price : PriceSnapshot
        Current UP and DOWN mid-prices.
    positions : list
        Current open positions from the paper engine.
    balance : float
        Current paper balance.
    pnl : float
        Total realised P&L.
    market : Market
        The current market being traded.
    indicators : IndicatorAccessor | None
        First-class indicator access: ``.indicators.rsi(14)``,
        ``.indicators.macd(12, 26, 9)``,
        ``.indicators.bollinger_bands(20, 2)``, etc.
    chainlink : ChainlinkStreamer | None
        Live BTC spot price from Polymarket Chainlink WebSocket.
        ``ctx.chainlink.last_price`` for the latest BTC/USD price.
    binance : BinanceAccessor | None
        Binance BTC market data: ``ctx.binance.close``, ``ctx.binance.macd()``,
        ``ctx.binance.price_change(30)``, ``ctx.binance.price_up()``.
    cl : TimeWindow | None
        Chainlink price window with change percentage helpers.
        ``ctx.cl.value`` for latest CL price, ``ctx.cl.change_pct(30)`` for
        % change over 30 seconds, ``ctx.cl.age_s`` for seconds since last update.
    rsi : float | None
        RSI indicator (legacy — prefer ``.indicators.rsi(14)``).
    sma : float | None
        SMA for a given period (legacy).
    ema : float | None
        EMA for a given period (legacy).

    Methods
    -------
    buy(side, amount)     — Place a market order.
    limit(side, price, amount) — Place a limit order.
    """

    def __init__(self, bot: Bot):
        self._bot = bot
        self._client = bot._client
        # engine may be missing on test doubles; fallback to paper for backcompat
        self._engine = getattr(bot, "_engine", None) or getattr(bot._client, "paper", None) or getattr(bot, "_client", None)
        # if engine is still a client, try paper
        if self._engine is not None and hasattr(self._engine, "paper") and not hasattr(self._engine, "buy"):
            self._engine = self._engine.paper
        self._market = bot._market
        self._stream = bot._stream
        self._price_history: deque[float] = deque(maxlen=200)
        self._cross_state: dict[int, float] = {}
        self._cached_series = None
        self._indicators: Optional[IndicatorAccessor] = IndicatorAccessor(self._get_price_series) if IndicatorAccessor is not None else None  # type: ignore[arg-type]
        self._cl_window: Optional[TimeWindow] = TimeWindow(max_age=120) if TimeWindow is not None else None

    # ── Prices ──────────────────────────────────────────────────────────────

    @property
    def price(self) -> PriceSnapshot:
        """Latest UP and DOWN mid-prices from the live stream."""
        return PriceSnapshot(
            up=getattr(self._stream, "up", FALLBACK_PRICE),
            down=getattr(self._stream, "down", FALLBACK_PRICE),
        )

    # ── Account ─────────────────────────────────────────────────────────────

    @property
    def balance(self) -> float:
        """Current balance (paper or real depending on Bot engine)."""
        return self._engine.balance

    @property
    def positions(self) -> list:
        """Open (unresolved) positions."""
        return self._engine.positions()

    @property
    def pnl(self) -> float:
        """Realised P&L from all resolved positions."""
        total = 0.0
        for pos in self._engine.all_positions():
            total += pos.pnl
        return total

    @property
    def engine(self):
        """Underlying trading engine (PaperEngine or RealTradingEngine)."""
        return self._engine

    @property
    def market(self) -> Optional[Market]:
        """The currently active market."""
        return self._market

    @property
    def tick_count(self) -> int:
        """Number of price ticks received this session."""
        return self._bot._tick_count

    @property
    def trade_count(self) -> int:
        """Number of trades executed."""
        return self._bot._trade_count

    # ── Orders ──────────────────────────────────────────────────────────────

    def buy(self, side: str, amount: float, **kwargs):
        """
        Place a market buy order.

        Parameters
        ----------
        side : "UP" | "DOWN"
        amount : USDC to spend
        **kwargs : forwarded to engine (e.g. confidence, price, stop_loss, take_profit for real)

        Returns
        -------
        PaperOrder | RealOrder
        """
        if self._bot.buy_once_per_market and self._bot._bought_this_market:
            return None
        order = self._place_buy(side, amount, **kwargs)
        if order:
            self._bot._bought_this_market = True
        return order

    def _place_buy(self, side: str, amount: float, **kwargs):
        """Place the order and fire Telegram notifications (bypasses guards)."""
        # Real engine accepts confirm=False for bot loop (no stdin)
        if getattr(self._engine, "config", None) is not None and getattr(self._engine.config, "require_confirmation", False):
            kwargs.setdefault("confirm", False)
        # Filter kwargs for paper (paper does not accept confidence/confirm)
        if getattr(self._bot, "engine", "paper") != "real":
            allowed = {"stop_loss_pct", "take_profit_pct", "time_window_start", "time_window_end", "stop_loss", "take_profit", "trail_sl", "trail_tp"}
            kwargs = {k: v for k, v in kwargs.items() if k in allowed}
        order = self._engine.buy(market=self._market, side=side, amount=amount, **kwargs)

        # Send Telegram notification if configured
        if self._bot._telegram and order:
            price = getattr(self._bot._stream, side.lower(), None) or (self.price.up if side == "UP" else self.price.down)
            self._bot._telegram.send_buy(
                asset=self._bot.asset,
                side=side,
                amount=amount,
                price=price
            )

        return order

    def limit(self, side: str, price: float, amount: float, **kwargs):
        """
        Place a limit order.

        Parameters
        ----------
        side : "UP" | "DOWN"
        price : trigger price
        amount : USDC to spend

        Returns
        -------
        PaperOrder | RealOrder
        """
        if self._bot.buy_once_per_market and self._bot._bought_this_market:
            return None
        if getattr(self._engine, "config", None) is not None and getattr(self._engine.config, "require_confirmation", False):
            kwargs.setdefault("confirm", False)
        if getattr(self._bot, "engine", "paper") != "real":
            allowed = {"time_window_start", "time_window_end"}
            kwargs = {k: v for k, v in kwargs.items() if k in allowed}
        order = self._engine.limit(
            market=self._market, side=side, price=price, amount=amount, **kwargs
        )
        if order:
            self._bot._bought_this_market = True
        return order

    def close_position(self, side: str, amount: Optional[float] = None, **kwargs):
        """
        Close (sell) an open position.

        Parameters
        ----------
        side : "UP" | "DOWN"
            The side of the position to close.
        amount : float, optional
            USDC amount to sell. Defaults to the full position.

        Returns
        -------
        PaperOrder | RealOrder
        """
        # paper: sell_position, real: sell
        if hasattr(self._engine, "sell_position"):
            order = self._engine.sell_position(
                market=self._market, side=side, amount=amount, **kwargs
            )
        else:
            order = self._engine.sell(
                market=self._market, side=side, amount=amount, **kwargs
            )
        
        # Send Telegram notification if configured
        if self._bot._telegram and order:
            price = getattr(self._bot._stream, side.lower(), None) or (self.price.up if side == "UP" else self.price.down)
            sell_amount = amount if amount else (order.amount if hasattr(order, 'amount') else 0)
            self._bot._telegram.send_sell(
                asset=self._bot.asset,
                side=side,
                amount=sell_amount,
                price=price
            )
        
        return order

    # ── Candle-aware trading guards ───────────────────────────────────────

    @property
    def candle_id(self) -> int:
        """Current candle identifier (increments on each new candle)."""
        return self._bot._candle_id

    @property
    def seconds_in(self) -> float:
        """Seconds elapsed since the start of the current candle."""
        return max(0.0, time.time() - self._bot._candle_start_time)

    def buy_once_per_candle(self, side: str, amount: float):
        """Buy only if *side* hasn't been bought yet in the current candle.

        Tracks buys per candle. Safe to call multiple times — subsequent
        calls within the same candle for the same side are silently skipped.

        Parameters
        ----------
        side : "UP" | "DOWN"
        amount : USDC to spend
        """
        cid = self._bot._candle_id
        sides = self._bot._bought_this_candle.setdefault(cid, set())
        side = side.upper()
        if side in sides:
            return
        result = self._place_buy(side, amount)
        sides.add(side)
        return result

    @property
    def indicators(self):
        """First-class indicator access (RSI, MACD, Bollinger Bands, SMA, EMA).

        Examples
        --------
        >>> ctx.indicators.rsi(14)
        >>> ctx.indicators.macd(12, 26, 9)
        >>> ctx.indicators.bollinger_bands(20, 2)
        >>> ctx.indicators.sma(20)
        >>> ctx.indicators.ema(12)
        """
        return self._indicators

    # ── External data sources ──────────────────────────────────────────────

    @property
    def chainlink(self):
        """Live BTC spot price from Polymarket Chainlink WebSocket.

        Returns ``None`` if the Chainlink streamer is not available.

        Examples
        --------
        >>> ctx.chainlink.last_price
        67850.23
        >>> ctx.chainlink.last_update
        datetime(...)
        """
        return self._bot._chainlink

    @property
    def binance(self):
        """Binance BTC market data for external TA.

        Returns ``None`` if BinanceAccessor is not available.

        Examples
        --------
        >>> ctx.binance.close
        67850.23
        >>> ctx.binance.macd(12, 26, 9)
        MACDResult(macd=..., signal=..., histogram=...)
        >>> ctx.binance.price_change(3)
        150.50
        >>> ctx.binance.price_up(2)
        True
        """
        return self._bot._binance

    @property
    def cl(self):
        """Chainlink price window with change percentage helpers.

        Provides a rolling window of Chainlink BTC prices with convenient
        methods for calculating percentage changes over custom time periods.
        Backed by the Chainlink streamer's own rolling window when available.

        Returns ``None`` if the window is not available.

        Examples
        --------
        >>> ctx.cl.value
        67850.23
        >>> ctx.cl.change_pct(30)
        0.12
        >>> ctx.cl.change_pct(60)
        0.08
        >>> ctx.cl.change_pct(90)
        0.05
        >>> ctx.cl.age_s
        0.5
        """
        chainlink = self._bot._chainlink
        if chainlink is not None:
            window = getattr(chainlink, "window", None)
            if window is not None:
                return window
        return self._cl_window

    @property
    def chainlink_history(self):
        """
        Chainlink candle history with warmup-aware TA.

        Configured via ``Bot(chainlink_history=...)``. Example:

        >>> bot = Bot("BTC","5m", chainlink_history={"1m":10, "1h":50, "1s":20})
        >>> @bot.on_tick
        ... def s(ctx):
        ...     if ctx.chainlink_history.is_ready("1m",10):
        ...         ema = ctx.chainlink_history.ema("1m",10)
        ...         df  = ctx.chainlink_history.candles("1m",10)

        Returns a :class:`~polyalpha.history.ChainlinkHistoryView` (or
        the underlying :class:`~polyalpha.history.ChainlinkRecorder` when
        accessed via ``bot.chainlink_history``) or ``None`` if not configured.
        """
        # per-tick view (so asset is correct)
        rec = getattr(self._bot, "_chainlink_history", None)
        if rec is None:
            return None
        # cache per TickContext
        if hasattr(self, "_chainlink_history_view") and self._chainlink_history_view is not None:
            return self._chainlink_history_view
        try:
            from .history.view import ChainlinkHistoryView
            # asset from bot
            view = ChainlinkHistoryView(rec, asset=self._bot.asset, strat_name="bot")
            self._chainlink_history_view = view
            return view
        except Exception:
            return rec

    # ── Indicators (optional — requires analysis deps) ──────────────────────

    def _get_price_series(self):
        """Lazy-load the price history as a pandas Series."""
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
        if self._indicators is not None:
            self._indicators.invalidate()

    def record_price(self, price: float) -> None:
        """Append a price point for indicator calculations."""
        self._price_history.append(price)

    @property
    def rsi(self) -> Optional[float]:
        """RSI(14) — requires pandas."""
        series = self._get_price_series()
        if series is None or _rsi is None:
            return None
        try:
            val = _rsi(series, 14).iloc[-1]
            return None if pd.isna(val) else float(val)
        except Exception:
            self._log.debug("RSI computation failed", exc_info=True)
            return None

    @property
    def sma_20(self) -> Optional[float]:
        """SMA(20) — requires pandas."""
        series = self._get_price_series()
        if series is None or _sma is None:
            return None
        try:
            val = _sma(series, 20).iloc[-1]
            return None if pd.isna(val) else float(val)
        except Exception:
            self._log.debug("SMA(20) computation failed", exc_info=True)
            return None

    @property
    def ema_12(self) -> Optional[float]:
        """EMA(12) — requires pandas."""
        series = self._get_price_series()
        if series is None or _ema is None:
            return None
        try:
            val = _ema(series, 12).iloc[-1]
            return None if pd.isna(val) else float(val)
        except Exception:
            self._log.debug("EMA(12) computation failed", exc_info=True)
            return None


# ── Bot ───────────────────────────────────────────────────────────────────────

class Bot:
    """
    One-line bot runner for Polymarket.

    Parameters
    ----------
    asset : str
        BTC, ETH, SOL, XRP, DOGE.
    timeframe : str
        5m, 15m, 1h, 4h, 24h.
    balance : float
        Starting paper-trading balance (default 100.0).
    paper : bool
        Paper-trade if True (default), real-trade if False.
    mode : str
        Fee/execution template: ``"simple"`` (zero fees, instant, 100% fill),
        ``"realistic"`` (polymarket fees, slippage, delay),
        or ``"custom"`` (use ``paper_config``) (default ``"simple"``).
    paper_config : PaperConfig, optional
        PaperConfig instance for ``mode="custom"``. Ignored otherwise.
    log_dir : str, optional
        Directory for a rotating log file.  If set, a ``{asset}_{timeframe}.log``
        file (5 MB max, 3 backups) is created with DEBUG-level output.
    kwargs
        Extra keyword arguments forwarded to polyalpha.Client.

    Usage
    -----
        bot = polyalpha.Bot("BTC", "5m", balance=500)

        @bot.on_tick
        def strategy(ctx):
            if ctx.price.up > 0.9:
                ctx.buy("UP", 20)

        bot.run()
    """

    def __init__(
        self,
        asset: str,
        timeframe: str,
        balance: float = 100.0,
        paper: bool = True,
        mode: str = "simple",
        paper_config: Optional[PaperConfig] = None,
        log_dir: Optional[str] = None,
        buy_once_per_market: bool = True,
        chainlink_history=None,
        engine: str | object | None = None,
        **kwargs,
    ):
        asset = asset.upper()
        if asset not in ASSETS:
            raise ValueError(f"Unsupported asset '{asset}'. Supported: {list(ASSETS)}")
        if timeframe not in TIMEFRAME_SECONDS:
            raise ValueError(
                f"Unsupported timeframe '{timeframe}'. Supported: {list(TIMEFRAME_SECONDS)}"
            )

        self.asset = asset
        self.timeframe = timeframe
        # engine resolution — "paper" | "real" | TradingEngineProtocol instance
        # `paper` bool kept for backcompat: paper=False => real
        if engine is None:
            engine_name = "real" if not paper else "paper"
        elif isinstance(engine, str):
            engine_name = engine.lower()
        else:
            engine_name = "custom"
        self.engine = engine_name
        self.paper_mode = paper if engine is None else (engine_name == "paper")
        if not paper and engine is None:
            import warnings
            warnings.warn("Bot(paper=False) is deprecated, use Bot(engine='real')", DeprecationWarning, stacklevel=2)
        self.buy_once_per_market = buy_once_per_market
        self._bought_this_market = False

        from .trading.paper_config import get_paper_config_from_preset

        if mode == "realistic":
            resolved = get_paper_config_from_preset("REALISTIC")
        elif mode == "custom":
            resolved = paper_config or PaperConfig()
        else:  # "simple"
            resolved = get_paper_config_from_preset("TEST")

        kwargs.pop("paper_config", None)
        # chainlink_history may also be passed via kwargs (e.g. from_tests)
        if chainlink_history is None and "chainlink_history" in kwargs:
            chainlink_history = kwargs.pop("chainlink_history")
        else:
            kwargs.pop("chainlink_history", None)
        self._client = Client(balance=balance, paper_config=resolved, **kwargs)
        # Resolve trading engine after client creation
        if isinstance(engine, object) and not isinstance(engine, str) and engine is not None:
            # custom engine instance
            self._engine = engine
        elif engine_name == "real":
            if self._client.real is None:
                raise ValueError("engine='real' requires private_key + rpc_url + polymarket_api_key (Client.real is None)")
            self._engine = self._client.real
        else:
            self._engine = self._client.paper
        self._market: Optional[Market] = None
        self._stream = None
        self._strategy: Optional[Callable] = None
        self._on_resolve: Optional[Callable] = None
        self._price_anomaly_handler: Optional[Callable] = None
        self._condition: Optional[Condition] = None
        self._buy_side: Optional[str] = None
        self._buy_amount: Optional[float] = None
        self._bought_this_cycle: bool = False
        self._candle_start_time: float = 0.0
        self._candle_open_price: Optional[float] = None
        self._candle_id: int = 0
        self._final_up: Optional[float] = None
        self._final_down: Optional[float] = None
        self._bought_this_candle: dict[int, set[str]] = {}
        self._stop_event = threading.Event()
        self._tick_count = 0
        self._trade_count = 0
        self._ctx: Optional[TickContext] = None
        self._log = logging.getLogger("polyalpha.Bot")
        self._log_dir = log_dir
        if log_dir:
            from .utils.logging_utils import setup_strategy_logger
            self._slog = setup_strategy_logger(
                f"{asset}_{timeframe}", log_dir,
            )
        else:
            self._slog = self._log
        
        # Initialize Telegram notifier (optional)
        self._telegram: Optional[TelegramNotifier] = None
        if TelegramNotifier is not None:
            self._telegram = TelegramNotifier()

        # Initialize Chainlink (live BTC spot price from Polymarket)
        self._chainlink: Optional["ChainlinkStreamer"] = None
        if ChainlinkStreamer is not None:
            try:
                cl = ChainlinkStreamer()
                cl.start(asset, background=True)
                self._chainlink = cl
            except Exception as exc:
                self._log.warning("Chainlink streamer init failed: %s", exc)

        # Initialize BinanceAccessor (TA on Binance data)
        self._binance: Optional["BinanceAccessor"] = None
        if BinanceAccessor is not None:
            try:
                self._binance = BinanceAccessor(asset=asset, timeframe=timeframe)
            except Exception as exc:
                self._log.warning("BinanceAccessor init failed: %s", exc)

        # ── Chainlink history (configurable candle store) ────────────────────
        # User chooses e.g. {"1m":10, "1h":50, "1s":20}; unused TFs are pruned.
        # Storage: SQLite WAL at ~/.polyalpha/chainlink.db (or custom), best for
        # incremental tick→candle with concurrent reads.
        self._chainlink_history = None
        self._chainlink_history_owned = False
        self._on_warmup = None
        try:
            rec, owned = _resolve_chainlink_history(chainlink_history, asset)
            self._chainlink_history = rec
            self._chainlink_history_owned = owned
            if rec is not None:
                # start recorder for this asset (no-op if already started/shared)
                try:
                    rec.start(asset, background=True)
                except Exception as exc:
                    self._log.warning("Chainlink history start failed: %s", exc)
                self._log.info("Chainlink history enabled: %s", getattr(rec.config, "warmup", rec))
        except Exception as exc:
            self._log.debug("Chainlink history init skipped: %s", exc)

    # ── Public API ──────────────────────────────────────────────────────────

    def on_tick(self, fn: Callable) -> Callable:
        """
        Decorator — register the strategy function.

        The function receives a TickContext on every price update.
        """
        self._strategy = fn
        return fn

    def on_warmup(self, fn: Callable) -> Callable:
        """
        Decorator — register a warmup-progress callback.

        Called while ``chainlink_history`` is still warming (when
        ``block="wait"`` the strat is paused, this fires every
        ``warmup_emit_interval`` seconds).

        Example
        -------
        >>> @bot.on_warmup
        ... def warmup(status):
        ...     print(f"warming {status}")  # e.g. {"1m":"7/10", "1h":"50/50 ✅"}
        """
        self._on_warmup = fn
        return fn

    @property
    def chainlink_history(self):
        """The underlying :class:`~polyalpha.history.ChainlinkRecorder` or None."""
        return getattr(self, "_chainlink_history", None)

    def onresolve(self, fn: Callable) -> Callable:
        """
        Decorator — register a resolve callback.

        The function receives a PaperPosition for each resolved position.

        Usage
        -----
            @bot.onresolve
            def on_resolve(pos):
                print(f"{pos.side} {pos.outcome} pnl=${pos.pnl:.2f}")
        """
        self._on_resolve = fn
        return fn

    def on_price_anomaly(self, fn: Callable) -> Callable:
        """
        Decorator — register a price anomaly callback.

        The function receives anomaly details when price validation fails.

        Usage
        -----
            @bot.on_price_anomaly
            def handle_anomaly(anomaly_type: str, *args):
                print(f"Price anomaly: {anomaly_type}")
        """
        self._price_anomaly_handler = fn
        return fn

    def when(self, condition: Condition) -> Bot:
        """
        Set a condition that triggers a trade.

        Combine with .buy() for a declarative strategy:

            bot.when(and_(rsi_above(50), price_above("up", 0.9))).buy("UP", 20)

        Parameters
        ----------
        condition : Condition
            A composable condition from polyalpha.conditions.

        Returns
        -------
        Bot (self) for chaining.
        """
        from .conditions import Condition as _Cond
        if not isinstance(condition, _Cond):
            raise TypeError("condition must be a polyalpha.conditions.Condition")
        self._condition = condition
        return self

    def buy(self, side: str, amount: float) -> Bot:
        """
        Set the default trade action when the condition is met.

        Parameters
        ----------
        side : "UP" | "DOWN"
        amount : USDC to spend per trade

        Returns
        -------
        Bot (self) for chaining.
        """
        side = side.upper()
        if side not in ("UP", "DOWN"):
            raise ValueError(f"side must be 'UP' or 'DOWN', got {side!r}")
        self._buy_side = side
        self._buy_amount = amount
        return self

    def _maybe_build_strategy(self) -> None:
        """Auto-generate a strategy from condition + buy action if no manual strategy set."""
        if self._strategy is not None:
            return
        if self._condition is None or self._buy_side is None:
            return
        condition = self._condition
        side = self._buy_side
        amount = self._buy_amount

        def _auto_strategy(ctx: TickContext) -> None:
            if self._bought_this_cycle:
                return
            if condition(ctx):
                ctx.buy(side, amount)
                self._bought_this_cycle = True

        self._strategy = _auto_strategy

    def run(self) -> None:
        """
        Start the bot (blocking).

        Runs indefinitely until stop() is called or an unrecoverable
        error occurs.
        """
        self._log.info(
            "Bot starting: %s %s | balance=$%.2f | engine=%s",
            self.asset, self.timeframe, self._engine.balance, self.engine,
        )
        self._maybe_build_strategy()
        self._stop_event.clear()

        try:
            while not self._stop_event.is_set():
                self._run_cycle()
        except KeyboardInterrupt:
            self._log.info("Interrupted by user")
        except Exception:
            self._log.exception("Bot fatal error")
            raise
        finally:
            self._cleanup()

    async def run_async(self) -> None:
        """
        Start the bot using async IO.

        Runs multiple bots concurrently in a single event loop:

            async def main():
                await asyncio.gather(
                    bot1.run_async(),
                    bot2.run_async(),
                    bot3.run_async(),
                )

        Runs indefinitely until stop() is called or an unrecoverable
        error occurs.
        """
        self._log.info(
            "Bot starting (async): %s %s | balance=$%.2f | engine=%s",
            self.asset, self.timeframe, self._engine.balance, self.engine,
        )
        self._maybe_build_strategy()
        self._stop_event.clear()

        try:
            while not self._stop_event.is_set():
                await self._run_cycle_async()
        except asyncio.CancelledError:
            self._log.info("Bot cancelled")
        except Exception:
            self._log.exception("Bot fatal error")
            raise
        finally:
            self._cleanup()

    def stop(self) -> None:
        """Signal the bot to stop gracefully."""
        self._log.info("Bot stopping...")
        self._stop_event.set()
        if self._stream:
            try:
                self._stream.stop()
            except Exception as exc:
                self._log.warning("Error stopping stream: %s", exc)
        if self._chainlink:
            try:
                self._chainlink.stop()
            except Exception as exc:
                self._log.warning("Error stopping chainlink: %s", exc)

    @property
    def stats(self) -> dict:
        """Running bot statistics."""
        return {
            "ticks": self._tick_count,
            "trades": self._trade_count,
            "balance": self._engine.balance,
            "pnl": sum(p.pnl for p in self._engine.all_positions()),
            "open_positions": len(self._engine.positions()),
        }

    # ── Cycle ───────────────────────────────────────────────────────────────

    def _run_cycle(self) -> None:
        """Single market cycle: discover → stream → tick → resolve → rollover."""
        try:
            self._discover()
            self._stream_prices()
        except MarketNotFound:
            self._log.warning("No market found, retrying in 30s...")
            self._sleep(30)
            return

        # Stream has ended — resolve and rollover
        self._resolve()
        self._rollover()

    async def _run_cycle_async(self) -> None:
        """Async single market cycle: discover → stream → tick → resolve → rollover."""
        try:
            self._discover()
            await self._stream_prices_async()
        except MarketNotFound:
            self._log.warning("No market found, retrying in 30s...")
            await self._asleep(30)
            return

        self._resolve()
        await self._rollover_async()

    def _discover(self) -> None:
        """Discover the latest market for the configured asset/timeframe."""
        self._bought_this_cycle = False
        self._market = self._client.markets.latest(self.asset, self.timeframe)
        self._log.info("Market found: %s", self._market.slug)

    def _stream_prices(self) -> None:
        """Set up stream and call strategy on every price tick."""
        self._stream = self._client.stream(self._market)

        # Wire engine to stream for limit-order fills / SL-TP
        try:
            self._engine.attach_stream(self._stream, self._market)
        except Exception as exc:
            self._log.debug("attach_stream failed: %s", exc)

        # Create the context
        self._ctx = TickContext(self)

        # Register handlers
        @self._stream.on("price")
        def on_price(up: float, down: float):
            if not self._handle_price_tick(up, down):
                return
            if self._strategy and self._ctx:
                try:
                    self._strategy(self._ctx)
                except Exception as exc:
                    self._slog.exception("Strategy error: %s", exc)

        @self._stream.on("close")
        def on_close():
            self._final_up = getattr(self._stream, "up", None)
            self._final_down = getattr(self._stream, "down", None)
            self._log.info("Market closed: %s", self._market.slug)

        @self._stream.on("price_anomaly")
        def on_price_anomaly(anomaly_type: str, *args):
            if self._stop_event.is_set():
                return
            self._log.warning("Price anomaly detected: type=%s", anomaly_type)
            # Call the price anomaly handler if registered
            if hasattr(self, '_price_anomaly_handler') and self._price_anomaly_handler:
                try:
                    self._price_anomaly_handler(anomaly_type, *args)
                except Exception as exc:
                    self._log.exception("Price anomaly handler error: %s", exc)

        # Start blocking — returns when stream ends
        self._stream.start(background=False)

    async def _stream_prices_async(self) -> None:
        """Set up stream and call strategy on every price tick (async version)."""
        self._stream = self._client.stream(self._market)
        try:
            self._engine.attach_stream(self._stream, self._market)
        except Exception as exc:
            self._log.debug("attach_stream failed (async): %s", exc)
        self._ctx = TickContext(self)

        @self._stream.on("price")
        def on_price(up: float, down: float):
            if not self._handle_price_tick(up, down):
                return
            if self._strategy and self._ctx:
                try:
                    self._strategy(self._ctx)
                except Exception as exc:
                    self._slog.exception("Strategy error: %s", exc)

        @self._stream.on("close")
        def on_close():
            self._final_up = getattr(self._stream, "up", None)
            self._final_down = getattr(self._stream, "down", None)
            self._log.info("Market closed: %s", self._market.slug)

        await self._stream.run_async()

    async def _rollover_async(self) -> None:
        """Clean up and prepare for next cycle (async version)."""
        if self._stream:
            try:
                self._stream.stop()
            except Exception as exc:
                self._log.warning("Error stopping stream during rollover: %s", exc)
            self._stream = None
        self._market = None
        self._ctx = None
        self._candle_id = 0
        self._candle_start_time = 0.0
        self._candle_open_price = None
        self._final_up = None
        self._final_down = None
        self._bought_this_candle = {}
        self._bought_this_market = False
        self._log.info("Rolling over to next market...")
        await self._asleep(2)

    def _handle_price_tick(self, up: float, down: float) -> bool:
        """Shared tick handler for sync and async paths.

        Returns True if strategy should proceed, False if warmup-gated.
        """
        if self._stop_event.is_set():
            return False
        self._tick_count += 1
        if self._ctx:
            self._ctx.record_price(up)
            self._ctx._invalidate_series_cache()
        if self._binance:
            try:
                self._binance._refresh()
            except Exception as exc:
                self._log.warning("Binance refresh failed: %s", exc)
        if self._chainlink_history is not None and getattr(self._chainlink_history, "config", None) is not None:
            cfg = self._chainlink_history.config
            need = getattr(cfg, "warmup", {}) or {}
            if need and cfg.block == "wait" and not self._chainlink_history.is_ready_map(need):
                now_w = time.time()
                last = getattr(self, "_last_warmup_emit", 0)
                interval = getattr(cfg, "warmup_emit_interval", 5.0)
                if now_w - last >= interval:
                    self._last_warmup_emit = now_w
                    try:
                        status = self._chainlink_history.status(need)
                    except Exception:
                        status = {"warming": True}
                    self._log.info("Warming chainlink history %s", status)
                    if self._on_warmup:
                        try:
                            self._on_warmup(status)
                        except Exception:
                            pass
                now2 = time.time()
                tf_seconds = TIMEFRAME_SECONDS.get(self.timeframe, 300)
                candle_start = (now2 // tf_seconds) * tf_seconds
                if candle_start != self._candle_start_time:
                    self._candle_start_time = candle_start
                    self._candle_open_price = up
                    self._candle_id += 1
                    self._bought_this_candle[self._candle_id] = set()
                return False
        now = time.time()
        tf_seconds = TIMEFRAME_SECONDS[self.timeframe]
        candle_start = (now // tf_seconds) * tf_seconds
        if candle_start != self._candle_start_time:
            self._candle_start_time = candle_start
            self._candle_open_price = up
            self._candle_id += 1
            self._bought_this_candle[self._candle_id] = set()
        return True

    def _resolve(self) -> None:
        """Resolve positions for the finished market and record outcomes."""
        if not self._market:
            return
        final_up = self._final_up if self._final_up is not None else getattr(self._stream, "up", None) if self._stream else None
        final_down = self._final_down if self._final_down is not None else getattr(self._stream, "down", None) if self._stream else None
        # Engine-aware resolve: paper uses manual UP>DOWN; real syncs from chain
        if self.engine == "real":
            # For real trading, positions are on-chain; manual resolve is not used.
            # Keep pnl reporting via engine sync; still compute outcome for logging.
            if final_up is not None and final_down is not None and final_up != final_down:
                outcome = "UP" if final_up > final_down else "DOWN"
                self._slog.info("Real engine: market %s closed UP=%.4f DOWN=%.4f outcome=%s (on-chain settle pending)", self._market.slug, final_up, final_down, outcome)
                try:
                    if hasattr(self._engine, "sync_positions_from_chain"):
                        self._engine.sync_positions_from_chain()
                except Exception as exc:
                    self._slog.debug("Real sync after close failed: %s", exc)
            else:
                self._slog.info("No final prices to resolve %s", self._market.slug)
        else:
            if final_up is not None and final_down is not None and final_up != final_down:
                outcome = "UP" if final_up > final_down else "DOWN"
                try:
                    self._engine.resolve(self._market, outcome)  # type: ignore
                except Exception as exc:
                    self._slog.warning("Failed to resolve positions: %s", exc)
            else:
                self._slog.info("No final prices to resolve %s", self._market.slug)

        # Report each resolved position for this market.
        try:
            all_pos = self._engine.all_positions()
        except Exception:
            all_pos = []
        for pos in all_pos:
            if pos.market_id != self._market.id or not pos.resolved:
                continue
            self._trade_count += 1
            self._slog.info(
                "Trade resolved: %s %s | pnl=$%.2f",
                pos.side, pos.outcome, pos.pnl,
            )

            # Send Telegram notification if configured
            if self._telegram:
                self._telegram.send_resolve(
                    asset=self.asset,
                    side=pos.side,
                    outcome=pos.outcome,
                    pnl=pos.pnl
                )

            if self._on_resolve:
                try:
                    self._on_resolve(pos)
                except Exception as exc:
                    self._slog.exception("onresolve handler error: %s", exc)

    def _rollover(self) -> None:
        """Clean up and prepare for next cycle."""
        if self._stream:
            try:
                self._stream.stop()
            except Exception as exc:
                self._log.warning("Error stopping stream during rollover: %s", exc)
            self._stream = None
        self._market = None
        self._ctx = None
        self._candle_id = 0
        self._candle_start_time = 0.0
        self._candle_open_price = None
        self._final_up = None
        self._final_down = None
        self._bought_this_candle = {}
        self._bought_this_market = False
        self._log.info("Rolling over to next market...")
        self._sleep(2)

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
        """Clean up resources."""
        if self._stream:
            try:
                self._stream.stop()
            except Exception as exc:
                self._log.warning("Error stopping stream during cleanup: %s", exc)
        if self._chainlink:
            try:
                self._chainlink.stop()
            except Exception as exc:
                self._log.warning("Error stopping chainlink during cleanup: %s", exc)
        # history recorder — only stop if we own it
        rec = getattr(self, "_chainlink_history", None)
        if rec is not None and getattr(self, "_chainlink_history_owned", False):
            try:
                rec.stop()
            except Exception as exc:
                self._log.warning("Error stopping chainlink history during cleanup: %s", exc)
        self._client.close()
