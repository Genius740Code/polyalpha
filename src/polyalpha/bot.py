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

import logging
import threading
import time
from collections import deque
from dataclasses import dataclass
from typing import Callable, Optional

from typing import TYPE_CHECKING

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

log = logging.getLogger(__name__)

# Optional indicator deps — imported once at module level, not per property call.
try:
    import pandas as pd
except ImportError:
    pd = None  # type: ignore[assignment]

try:
    from .analysis._native_ta import rsi as _rsi, sma as _sma, ema as _ema
except ImportError:
    _rsi = _sma = _ema = None


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
    rsi : float | None
        RSI indicator (requires optional analysis deps).
    sma : float | None
        SMA for a given period.
    ema : float | None
        EMA for a given period.

    Methods
    -------
    buy(side, amount)     — Place a market order.
    limit(side, price, amount) — Place a limit order.
    """

    def __init__(self, bot: Bot):
        self._bot = bot
        self._client = bot._client
        self._market = bot._market
        self._stream = bot._stream
        self._price_history: deque[float] = deque(maxlen=200)
        self._cross_state: dict[int, float] = {}

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
        """Current paper-trading balance."""
        return self._client.paper.balance

    @property
    def positions(self) -> list:
        """Open (unresolved) positions."""
        return self._client.paper.positions()

    @property
    def pnl(self) -> float:
        """Realised P&L from all resolved positions."""
        total = 0.0
        for pos in self._client.paper.all_positions():
            total += pos.pnl
        return total

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

    def buy(self, side: str, amount: float):
        """
        Place a market buy order.

        Parameters
        ----------
        side : "UP" | "DOWN"
        amount : USDC to spend

        Returns
        -------
        PaperOrder
        """
        return self._client.paper.buy(market=self._market, side=side, amount=amount)

    def limit(self, side: str, price: float, amount: float):
        """
        Place a limit order.

        Parameters
        ----------
        side : "UP" | "DOWN"
        price : trigger price
        amount : USDC to spend

        Returns
        -------
        PaperOrder
        """
        return self._client.paper.limit(
            market=self._market, side=side, price=price, amount=amount
        )

    # ── Indicators (optional — requires analysis deps) ──────────────────────

    def _get_price_series(self):
        """Lazy-load the price history as a pandas Series."""
        if getattr(self, "_cached_series", None) is not None:
            return self._cached_series
        if pd is None:
            raise RuntimeError(
                "Indicators require 'pandas'. Install: pip install pandas"
            )
        if len(self._price_history) < 14:
            return None
        self._cached_series = pd.Series(list(self._price_history))
        return self._cached_series

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
            return None


# ── Bot ───────────────────────────────────────────────────────────────────────

class Bot:
    """
    One-line bot runner for Polymarket.

    Parameters
    ----------
    asset : str
        BTC, ETH, SOL, XRP, DOGE (default "BTC").
    timeframe : str
        5m, 15m, 1h, 4h, 24h (default "5m").
    balance : float
        Starting paper-trading balance (default 100.0).
    paper : bool
        Paper-trade if True (default), real-trade if False.
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
        asset: str = "BTC",
        timeframe: str = "5m",
        balance: float = 100.0,
        paper: bool = True,
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
        self.paper_mode = paper

        self._client = Client(balance=balance, **kwargs)
        self._market: Optional[Market] = None
        self._stream = None
        self._strategy: Optional[Callable] = None
        self._condition: Optional["Condition"] = None
        self._buy_side: Optional[str] = None
        self._buy_amount: Optional[float] = None
        self._bought_this_cycle: bool = False
        self._stop_event = threading.Event()
        self._tick_count = 0
        self._trade_count = 0
        self._ctx: Optional[TickContext] = None
        self._log = logging.getLogger("polyalpha.Bot")

    # ── Public API ──────────────────────────────────────────────────────────

    def on_tick(self, fn: Callable) -> Callable:
        """
        Decorator — register the strategy function.

        The function receives a TickContext on every price update.
        """
        self._strategy = fn
        return fn

    def when(self, condition: "Condition") -> "Bot":
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

    def buy(self, side: str, amount: float) -> "Bot":
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
            "Bot starting: %s %s | balance=$%.2f | paper=%s",
            self.asset, self.timeframe, self._client.paper.balance, self.paper_mode,
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

    def stop(self) -> None:
        """Signal the bot to stop gracefully."""
        self._log.info("Bot stopping...")
        self._stop_event.set()
        if self._stream:
            try:
                self._stream.stop()
            except Exception:
                pass

    @property
    def stats(self) -> dict:
        """Running bot statistics."""
        return {
            "ticks": self._tick_count,
            "trades": self._trade_count,
            "balance": self._client.paper.balance,
            "pnl": sum(p.pnl for p in self._client.paper.all_positions()),
            "open_positions": len(self._client.paper.positions()),
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

    def _discover(self) -> None:
        """Discover the latest market for the configured asset/timeframe."""
        self._bought_this_cycle = False
        self._market = self._client.markets.latest(self.asset, self.timeframe)
        self._log.info("Market found: %s", self._market.slug)

    def _stream_prices(self) -> None:
        """Set up stream and call strategy on every price tick."""
        self._stream = self._client.stream(self._market)

        # Wire paper engine to stream for limit-order fills
        self._client.paper.attach_stream(self._stream, self._market)

        # Create the context
        self._ctx = TickContext(self)

        # Register handlers
        @self._stream.on("price")
        def on_price(up: float, down: float):
            if self._stop_event.is_set():
                return
            self._tick_count += 1
            if self._ctx:
                self._ctx.record_price(up)
            # Call the strategy
            if self._strategy and self._ctx:
                try:
                    self._strategy(self._ctx)
                except Exception as exc:
                    self._log.exception("Strategy error: %s", exc)

        @self._stream.on("close")
        def on_close():
            self._log.info("Market closed: %s", self._market.slug)

        # Start blocking — returns when stream ends
        self._stream.start(background=False)

    def _resolve(self) -> None:
        """Wait for resolution and record outcome."""
        if not self._market:
            return
        # Check positions
        for pos in self._client.paper.positions():
            if pos.resolved:
                self._trade_count += 1
                self._log.info(
                    "Trade resolved: %s %s | pnl=$%.2f",
                    pos.side, pos.outcome, pos.pnl,
                )

    def _rollover(self) -> None:
        """Clean up and prepare for next cycle."""
        if self._stream:
            try:
                self._stream.stop()
            except Exception:
                pass
            self._stream = None
        self._market = None
        self._ctx = None
        self._log.info("Rolling over to next market...")
        self._sleep(2)

    # ── Helpers ─────────────────────────────────────────────────────────────

    def _sleep(self, seconds: float) -> None:
        """Sleep, checking stop_event periodically."""
        for _ in range(int(seconds * 10)):
            if self._stop_event.is_set():
                break
            time.sleep(0.1)

    def _cleanup(self) -> None:
        """Clean up resources."""
        if self._stream:
            try:
                self._stream.stop()
            except Exception:
                pass
        self._client.close()
