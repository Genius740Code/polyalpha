"""bot_hub.context — StrategyContext per-strategy trading context."""

from __future__ import annotations

import logging
from collections import deque
from typing import TYPE_CHECKING, Callable, Optional

try:
    import pandas as pd
except ImportError:
    pd = None  # type: ignore[assignment]

try:
    from ..analysis._native_ta import bbands as _bbands
    from ..analysis._native_ta import donchian as _donchian
    from ..analysis._native_ta import ema as _ema
    from ..analysis._native_ta import macd as _macd
    from ..analysis._native_ta import rsi as _rsi
    from ..analysis._native_ta import sma as _sma
except ImportError:
    _rsi = _sma = _ema = _macd = _bbands = _donchian = None

try:
    from ..windows import TimeWindow
except ImportError:
    TimeWindow = None  # type: ignore[assignment]

from ..core import FALLBACK_PRICE
from ..core import Market
from ..orderbook import ClobBookClient
from ..trading.paper_engine import PaperEngine

from .binance import BinanceAccessor
from .indicators import IndicatorAccessor
from .models import PriceSnapshot
from .orderbook import OrderBookAccessor

log = logging.getLogger(__name__)

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
    indicators : IndicatorAccessor
        First-class indicator access: ``.indicators.rsi(14)``,
        ``.indicators.macd(12, 26, 9)``,
        ``.indicators.bollinger_bands(20, 2)``, etc.
    cl : TimeWindow | None
        Chainlink price window with change percentage helpers.
        ``ctx.cl.value`` for latest CL price, ``ctx.cl.change_pct(30)`` for
        % change over 30 seconds, ``ctx.cl.age_s`` for seconds since last update.
    rsi, sma_20, ema_12 : float | None
        Legacy indicators (prefer ``ctx.indicators.rsi(14)``, etc.).

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
        down_price_history: Optional[deque] = None,
        asset: str = "BTC",
        clob: Optional[ClobBookClient] = None,
        chainlink_cache: Optional[object] = None,
        chainlink: Optional[object] = None,
        binance: Optional[BinanceAccessor] = None,
        cl_window: Optional[TimeWindow] = None,
        globals: Optional[object] = None,
        get_candle_open=None,
        get_seconds_in=None,
        get_candle_id=None,
        bought_this_candle=None,
        hub=None,
        chainlink_history=None,
        engine: object | None = None,
    ):
        self.name = name
        self._asset = asset
        self._stream = stream
        self._paper = paper
        # engine alias — for real trading paper is actually RealTradingEngine
        self._engine = engine if engine is not None else paper
        self._market = market
        self._price_history = price_history  # shared across strategies
        self._down_price_history: deque = down_price_history if down_price_history is not None else deque(maxlen=200)
        self._clob = clob
        self._chainlink_cache = chainlink_cache
        self._chainlink = chainlink
        self._binance = binance
        self._hub = hub  # Reference to BotHub for Telegram notifications
        self._globals = globals  # Shared feeds (Globals) — one connection, many strategies
        self._chainlink_history = chainlink_history
        self._chainlink_history_view = None
        self._get_candle_open = get_candle_open or (lambda: None)
        self._get_seconds_in = get_seconds_in or (lambda: 0.0)
        self._get_candle_id: Callable[[], int] = get_candle_id or (lambda: 0)
        self._bought_this_candle: dict[int, dict[str, set[str]]] = bought_this_candle if bought_this_candle is not None else {}
        self._cached_series = None
        self._down_cached_series = None
        self._indicators: IndicatorAccessor = IndicatorAccessor(self._get_price_series)
        self._down_indicators: IndicatorAccessor = IndicatorAccessor(self._get_down_price_series)
        self._orderbook: Optional[OrderBookAccessor] = None
        self._cl_window: Optional[TimeWindow] = cl_window if cl_window is not None else (TimeWindow(max_age=120) if TimeWindow is not None else None)

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
    def chainlink(self):
        """Live BTC spot price from Polymarket Chainlink WebSocket.

        ``ctx.chainlink.last_price`` for the latest BTC/USD price.
        Returns ``None`` if not available in this context.
        """
        return self._chainlink

    @property
    def binance(self):
        """Binance BTC market data for external TA.

        ``ctx.binance.close``, ``ctx.binance.macd()``, ``ctx.binance.price_change(30)``.
        Returns ``None`` if not available in this context.
        """
        return self._binance

    @property
    def globals(self):
        """The shared :class:`~polyalpha.globals.Globals` instance, if any.

        Every strategy reads the same feeds (``ctx.globals.cvd``,
        ``ctx.globals.price_feed``, …) so adding a strategy costs 0 extra
        connections. Returns ``None`` when the hub was not given one.
        """
        return self._globals

    @property
    def cl(self):
        """Chainlink price window with change percentage helpers.

        Provides a rolling window of Chainlink BTC prices with convenient
        methods for calculating percentage changes over custom time periods.
        Backed by the shared Chainlink streamer's own rolling window when
        available.

        Returns ``None`` if the window is not available.

        Examples
        --------
        >>> ctx.cl.value
        67850.23
        >>> ctx.cl.change_pct(30)
        0.12
        >>> ctx.cl.change_pct(60)
        0.08
        >>> ctx.cl.age_s
        0.5
        """
        if self._chainlink is not None:
            window = getattr(self._chainlink, "window", None)
            if window is not None:
                return window
        return self._cl_window

    @property
    def chainlink_history(self):
        """
        Chainlink candle history (shared, pruned to user keep counts).

        Example: ``ctx.chainlink_history.ema("1m",10)``
        or ``ctx.chainlink_history.candles("1m",10)``.
        Supports both ``ema("1m",10)`` and ``ema("BTC","1m",10)`` forms.
        Returns ``None`` if not configured on the hub.
        """
        rec = self._chainlink_history
        # fallback to hub's recorder or globals
        if rec is None and self._hub is not None:
            rec = getattr(self._hub, "_chainlink_history", None)
        if rec is None and self._globals is not None:
            rec = getattr(self._globals, "chainlink_history", None)
        if rec is None:
            return None
        if self._chainlink_history_view is not None:
            return self._chainlink_history_view
        try:
            from ..history.view import ChainlinkHistoryView
            # ChainlinkHistoryView expects recorder; if rec is already a view, return it
            if isinstance(rec, ChainlinkHistoryView):
                self._chainlink_history_view = rec
                return rec
            view = ChainlinkHistoryView(rec, asset=self._asset, strat_name=self.name)
            self._chainlink_history_view = view
            return view
        except Exception:
            return rec

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
        return self._engine.balance

    @property
    def positions(self) -> list:
        return self._engine.positions()

    @property
    def pnl(self) -> float:
        return sum(p.pnl for p in self._engine.all_positions())

    @property
    def engine(self):
        return self._engine

    @property
    def paper(self):
        return self._engine

    @property
    def market(self) -> Optional[Market]:
        return self._market

    # ── Order book ──────────────────────────────────────────────────────────

    @property
    def orderbook(self) -> Optional[OrderBookAccessor]:
        """Live order book for the current market (auto-attached).

        Returns ``None`` if the market is not yet known (should not happen
        during normal operation).

        Usage
        -----
            >>> ctx.orderbook.up.bids       # top-of-book UP bids
            >>> ctx.orderbook.down.asks     # top-of-book DOWN asks
            >>> ctx.orderbook.up.spread     # UP bid-ask spread
            >>> ctx.orderbook.refresh()     # force REST refresh
        """
        if self._market is None or self._clob is None:
            return None
        if self._orderbook is None:
            self._orderbook = OrderBookAccessor(
                ctx=self,
                market=self._market,
                clob=self._clob,
            )
        return self._orderbook

    # ── Orders ──────────────────────────────────────────────────────────────

    def buy(self, side: str, amount: float, **kwargs):
        """Place a market buy order against this strategy's engine (paper or real)."""
        if self._hub is not None and self._hub.buy_once_per_market and self._hub._bought_this_market.get(self.name, False):
            return None
        order = self._place_buy(side, amount, **kwargs)
        if self._hub is not None and order:
            self._hub._bought_this_market[self.name] = True
        return order

    def _place_buy(self, side: str, amount: float, **kwargs):
        """Place the order and fire Telegram notifications (bypasses guards)."""
        if getattr(self._engine, "config", None) is not None and getattr(self._engine.config, "require_confirmation", False):
            kwargs.setdefault("confirm", False)
        # paper engine cannot accept real-specific kwargs
        hub_engine = getattr(self._hub, "engine", "paper") if self._hub else "paper"
        if hub_engine != "real":
            allowed = {"stop_loss_pct", "take_profit_pct", "time_window_start", "time_window_end", "stop_loss", "take_profit", "trail_sl", "trail_tp"}
            kwargs = {k: v for k, v in kwargs.items() if k in allowed}
        order = self._engine.buy(market=self._market, side=side, amount=amount, **kwargs)

        # Send Telegram notification if configured
        if self._hub is not None and self._hub._telegram and order:
            price = getattr(self._stream, side.lower(), None) or self.price.up if side == "UP" else self.price.down
            self._hub._telegram.send_buy(
                asset=self._asset,
                side=side,
                amount=amount,
                price=price,
                strategy_name=self.name
            )

        return order

    def limit(self, side: str, price: float, amount: float, **kwargs):
        """Place a limit order against this strategy's engine.

        Respects the same ``buy_once_per_market`` guard as :meth:`buy`, so
        a limit order cannot be used to circumvent the once-per-market cap.
        """
        if self._hub is not None and self._hub.buy_once_per_market and self._hub._bought_this_market.get(self.name, False):
            return None
        if getattr(self._engine, "config", None) is not None and getattr(self._engine.config, "require_confirmation", False):
            kwargs.setdefault("confirm", False)
        hub_engine = getattr(self._hub, "engine", "paper") if self._hub else "paper"
        if hub_engine != "real":
            allowed = {"time_window_start", "time_window_end"}
            kwargs = {k: v for k, v in kwargs.items() if k in allowed}
        order = self._engine.limit(
            market=self._market, side=side, price=price, amount=amount, **kwargs
        )
        if self._hub is not None and order:
            self._hub._bought_this_market[self.name] = True
        return order

    def close_position(self, side: str, amount: Optional[float] = None, **kwargs):
        """Close an open position for this strategy."""
        if hasattr(self._engine, "sell_position"):
            order = self._engine.sell_position(
                market=self._market, side=side, amount=amount, **kwargs
            )
        else:
            order = self._engine.sell(
                market=self._market, side=side, amount=amount, **kwargs
            )
        
        # Send Telegram notification if configured
        if self._hub is not None and self._hub._telegram and order:
            price = getattr(self._stream, side.lower(), None) or self.price.up if side == "UP" else self.price.down
            sell_amount = amount if amount else (order.amount if hasattr(order, 'amount') else 0)
            self._hub._telegram.send_sell(
                asset=self._asset,
                side=side,
                amount=sell_amount,
                price=price,
                strategy_name=self.name
            )
        
        return order

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
        result = self._place_buy(side, amount)
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
            return self._place_buy(side, amount)

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

    def _get_down_price_series(self):
        if self._down_cached_series is not None:
            return self._down_cached_series
        if pd is None:
            raise RuntimeError(
                "Indicators require 'pandas'. Install: pip install pandas"
            )
        if len(self._down_price_history) < 14:
            return None
        self._down_cached_series = pd.Series(list(self._down_price_history))
        return self._down_cached_series

    @property
    def indicators(self) -> IndicatorAccessor:
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

    def _invalidate_series_cache(self) -> None:
        self._cached_series = None
        self._down_cached_series = None
        self._indicators.invalidate()
        self._down_indicators.invalidate()

    @property
    def down_indicators(self) -> IndicatorAccessor:
        """Indicators computed on the DOWN leg price history.

        Mirrors ``ctx.indicators`` but is fed from ``down`` ticks instead
        of ``up`` ticks, so DOWN-based signals use DOWN data.
        """
        return self._down_indicators

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

    # ── Strategy Helper Methods ────────────────────────────────────────────────

    def bollinger_pctile(self, period: int = 20, std_dev: float = 2.0, avg_period: int = 50) -> tuple[Optional[float], Optional[dict]]:
        """Calculate Bollinger band width percentile and current band values.

        Returns the percentile of current band width relative to historical average,
        along with the current upper, lower, and close values.

        Parameters
        ----------
        period : int
            BB period (default: 20).
        std_dev : float
            Standard deviation multiplier (default: 2.0).
        avg_period : int
            Rolling average period for width comparison (default: 50).

        Returns
        -------
        tuple (pctile, bb_dict)
            pctile : float or None
                Width percentile (0-100) based on historical average.
            bb_dict : dict or None
                Dictionary with 'upper', 'lower', 'close' values.
        """
        series = self._get_price_series()
        if series is None or _bbands is None:
            return None, None

        try:
            bb_df = _bbands(series, period, float(std_dev))
            upper = float(bb_df.iloc[-1, 2])
            lower = float(bb_df.iloc[-1, 0])
            close = float(series.iloc[-1])

            if pd.isna(upper) or pd.isna(lower) or pd.isna(close):
                return None, None

            # Calculate width and historical average
            width = upper - lower
            if len(series) < avg_period:
                return None, None

            # Calculate historical widths
            historical_widths = []
            for i in range(avg_period, len(series)):
                if i >= period:
                    slice_series = series.iloc[i-period:i]
                    slice_bb = _bbands(slice_series, period, float(std_dev))
                    if not pd.isna(slice_bb.iloc[-1, 2]) and not pd.isna(slice_bb.iloc[-1, 0]):
                        hist_width = float(slice_bb.iloc[-1, 2]) - float(slice_bb.iloc[-1, 0])
                        historical_widths.append(hist_width)

            if not historical_widths:
                return None, None

            avg_width = sum(historical_widths) / len(historical_widths)
            if avg_width == 0:
                return None, None

            # Calculate percentile (where current width falls in distribution)
            pctile = (width / avg_width) * 100

            bb_dict = {
                "upper": upper,
                "lower": lower,
                "close": close
            }

            return pctile, bb_dict

        except Exception:
            return None, None

    def vol_ratio(self, period: int = 10) -> Optional[float]:
        """Get volume ratio from Binance data.

        Parameters
        ----------
        period : int
            Period for volume ratio calculation (default: 10).

        Returns
        -------
        float or None
            Volume ratio value.
        """
        if self._binance is None:
            return None
        return self._binance.vol_ratio(period)

    def side_price(self, direction: str) -> Optional[float]:
        """Get the current price for a specific direction.

        Parameters
        ----------
        direction : str
            "UP" or "DOWN".

        Returns
        -------
        float or None
            Current price for the specified direction.
        """
        direction = direction.upper()
        if direction == "UP":
            return self.price.up
        elif direction == "DOWN":
            return self.price.down
        return None


