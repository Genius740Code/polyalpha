"""
Sniper bot — time-window entry with threshold-based execution.

The Sniper monitors market prices and executes limit orders only during
a specified time window before market resolution. It automatically
transitions to the next market after resolution, enabling continuous
automated trading.

Features:
- Time-window entry (only trades in final N seconds)
- Dual-threshold strategy (entry/exit thresholds)
- Auto-rollover to next market
- Risk management (position limits, consecutive loss protection)
- Performance monitoring (P&L, win rate, statistics)
- Event-driven architecture for custom logic

Usage
-----
    from polyalpha.bots import Sniper

    sniper = Sniper(
        client=client,
        asset="BTC",
        timeframe="5m",
        side="UP",
        entry_price=0.92,
        exit_price=0.88,
        window_seconds=35,
        amount=20.0,
    )

    sniper.run()  # Blocking loop

    # Or with callbacks
    @sniper.on("resolve")
    def on_resolve(outcome, pnl):
        print(f"Resolved {outcome}: ${pnl:.2f}")

    sniper.run()
"""

from __future__ import annotations

import logging
import threading
import time
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from typing import Callable, Optional

from ..core import ASSETS, TIMEFRAME_SECONDS, Market

log = logging.getLogger(__name__)


# ── Configuration ─────────────────────────────────────────────────────────────

@dataclass
class SniperConfig:
    """
    Sniper bot configuration.

    All parameters are validated on initialization. Invalid values
    raise ValueError with descriptive messages.
    """

    # Market parameters
    asset: str = "BTC"
    timeframe: str = "5m"
    side: str = "UP"

    # Trading parameters
    entry_price: float = 0.92
    exit_price: Optional[float] = 0.88
    window_seconds: int = 35
    amount: float = 20.0

    # Risk management
    max_position_size: Optional[float] = None
    max_consecutive_losses: Optional[int] = 3
    max_trades: Optional[int] = None

    # Performance tuning
    pre_window_buffer: int = 5
    post_window_timeout: int = 10

    # Logging
    log_level: str = "INFO"
    log_trades: bool = True
    log_prices: bool = False

    def __post_init__(self):
        """Validate configuration parameters."""
        # Validate asset
        if self.asset.upper() not in ASSETS:
            raise ValueError(
                f"Invalid asset '{self.asset}'. Supported: {ASSETS}"
            )
        self.asset = self.asset.upper()

        # Validate timeframe
        if self.timeframe.lower() not in TIMEFRAME_SECONDS:
            raise ValueError(
                f"Invalid timeframe '{self.timeframe}'. "
                f"Supported: {list(TIMEFRAME_SECONDS)}"
            )
        self.timeframe = self.timeframe.lower()

        # Validate side
        if self.side.upper() not in ("UP", "DOWN"):
            raise ValueError(f"Invalid side '{self.side}'. Must be 'UP' or 'DOWN'")
        self.side = self.side.upper()

        # Validate entry price
        if not (0 < self.entry_price < 1):
            raise ValueError(
                f"entry_price must be between 0 and 1, got {self.entry_price}"
            )

        # Validate exit price if provided
        if self.exit_price is not None:
            if not (0 < self.exit_price < 1):
                raise ValueError(
                    f"exit_price must be between 0 and 1, got {self.exit_price}"
                )
            if self.exit_price >= self.entry_price:
                raise ValueError(
                    f"exit_price ({self.exit_price}) must be less than "
                    f"entry_price ({self.entry_price})"
                )

        # Validate window_seconds
        if self.window_seconds <= 0:
            raise ValueError(
                f"window_seconds must be positive, got {self.window_seconds}"
            )

        # Validate amount
        if self.amount <= 0:
            raise ValueError(f"amount must be positive, got {self.amount}")

        # Validate max_position_size
        if self.max_position_size is not None and self.max_position_size <= 0:
            raise ValueError(
                f"max_position_size must be positive, got {self.max_position_size}"
            )

        # Validate max_consecutive_losses
        if self.max_consecutive_losses is not None and self.max_consecutive_losses <= 0:
            raise ValueError(
                f"max_consecutive_losses must be positive, got {self.max_consecutive_losses}"
            )

        # Validate max_trades
        if self.max_trades is not None and self.max_trades <= 0:
            raise ValueError(f"max_trades must be positive, got {self.max_trades}")

        # Validate buffer/timeout
        if self.pre_window_buffer < 0:
            raise ValueError(
                f"pre_window_buffer must be non-negative, got {self.pre_window_buffer}"
            )
        if self.post_window_timeout <= 0:
            raise ValueError(
                f"post_window_timeout must be positive, got {self.post_window_timeout}"
            )


# ── Statistics ─────────────────────────────────────────────────────────────────

@dataclass
class TradeRecord:
    """Record of a single trade execution."""
    market_slug: str
    side: str
    entry_price: float
    exit_price: Optional[float]
    amount: float
    shares: float
    outcome: Optional[str]  # "WON" | "LOST" | None
    pnl: float
    timestamp: datetime


@dataclass
class SniperStats:
    """Sniper bot performance statistics."""
    total_trades: int = 0
    wins: int = 0
    losses: int = 0
    total_pnl: float = 0.0
    consecutive_losses: int = 0
    trades: list[TradeRecord] = field(default_factory=list)

    @property
    def win_rate(self) -> float:
        """Win rate as percentage (0-100)."""
        if self.total_trades == 0:
            return 0.0
        return (self.wins / self.total_trades) * 100

    @property
    def avg_entry_price(self) -> float:
        """Average entry price across all trades."""
        if not self.trades:
            return 0.0
        return sum(t.entry_price for t in self.trades) / len(self.trades)

    @property
    def avg_exit_price(self) -> float:
        """Average exit price across trades with exits."""
        exited = [t.exit_price for t in self.trades if t.exit_price is not None]
        if not exited:
            return 0.0
        return sum(exited) / len(exited)

    def add_trade(self, trade: TradeRecord) -> None:
        """Add a trade record and update statistics."""
        self.trades.append(trade)
        self.total_trades += 1
        self.total_pnl += trade.pnl

        if trade.outcome == "WON":
            self.wins += 1
            self.consecutive_losses = 0
        elif trade.outcome == "LOST":
            self.losses += 1
            self.consecutive_losses += 1


# ── Sniper Bot ─────────────────────────────────────────────────────────────────

class Sniper:
    """
    Automated trading bot with time-window entry and threshold execution.

    The Sniper monitors a market and executes limit orders only during a
    specified time window before resolution. It automatically transitions
    to the next market after resolution.

    State Machine
    -------------
    IDLE → DISCOVERING → WAITING → ARMED → FILLED → RESOLVING → ROLLOVER → IDLE

    Events
    ------
    - market_found: New market discovered
    - window_enter: Entering the trading window
    - entry: Order filled
    - exit: Order cancelled (reason: 'exit_threshold' | 'window_close')
    - resolve: Market resolved (outcome: 'WON' | 'LOST')
    - rollover: Transitioning to next market
    - error: Unrecoverable error
    - stop: Bot stopped

    Parameters
    ----------
    client : polyalpha.Client
        The polyalpha client instance.
    config : SniperConfig, optional
        Bot configuration. If not provided, uses defaults.

    Example
    -------
    >>> sniper = Sniper(client, asset="BTC", timeframe="5m", side="UP",
    ...                 entry_price=0.92, exit_price=0.88, window_seconds=35,
    ...                 amount=20.0)
    >>> sniper.run()
    """

    # State constants
    STATE_IDLE = "IDLE"
    STATE_DISCOVERING = "DISCOVERING"
    STATE_WAITING = "WAITING"
    STATE_ARMED = "ARMED"
    STATE_FILLED = "FILLED"
    STATE_RESOLVING = "RESOLVING"
    STATE_ROLLOVER = "ROLLOVER"
    STATE_STOP = "STOP"

    def __init__(self, client, config: Optional[SniperConfig] = None):
        """
        Initialize the Sniper bot.

        Parameters
        ----------
        client : polyalpha.Client
            The polyalpha client instance.
        config : SniperConfig, optional
            Bot configuration. If not provided, uses defaults.
        """
        self.client = client
        self.config = config or SniperConfig()

        # Set up logging
        self._log = logging.getLogger(f"{__name__}.Sniper")
        self._log.setLevel(getattr(logging, self.config.log_level.upper()))

        # State management
        self._state = self.STATE_IDLE
        self._state_lock = threading.Lock()
        self._stop_event = threading.Event()

        # Current market data
        self._market: Optional[Market] = None
        self._stream = None
        self._pending_order = None
        self._filled_order = None

        # Statistics
        self._stats = SniperStats()

        # Event handlers
        self._handlers: dict[str, list[Callable]] = {}

        self._log.info("Sniper initialized: %s %s %s @ %s",
                      self.config.asset, self.config.timeframe,
                      self.config.side, self.config.entry_price)

    # ── Public API ─────────────────────────────────────────────────────────────

    def on(self, event: str) -> Callable:
        """
        Decorator to register an event handler.

        Parameters
        ----------
        event : str
            Event name to handle.

        Returns
        -------
        Callable
            Decorator function.

        Example
        -------
        >>> @sniper.on("resolve")
        ... def on_resolve(outcome, pnl):
        ...     print(f"Resolved {outcome}: ${pnl:.2f}")
        """
        def decorator(fn: Callable) -> Callable:
            if event not in self._handlers:
                self._handlers[event] = []
            self._handlers[event].append(fn)
            return fn
        return decorator

    def add_handler(self, event: str, fn: Callable) -> None:
        """
        Register an event handler without decorator syntax.

        Parameters
        ----------
        event : str
            Event name to handle.
        fn : Callable
            Handler function.
        """
        if event not in self._handlers:
            self._handlers[event] = []
        self._handlers[event].append(fn)

    @property
    def stats(self) -> SniperStats:
        """Current bot statistics."""
        return self._stats

    @property
    def state(self) -> str:
        """Current bot state."""
        with self._state_lock:
            return self._state

    def run(self) -> None:
        """
        Start the Sniper bot (blocking).

        This method will block until the bot is stopped via stop() or
        an error occurs. It will continuously cycle through markets
        until stopped.

        Raises
        ------
        Exception
            If an unrecoverable error occurs.
        """
        self._log.info("Starting Sniper bot...")
        self._stop_event.clear()

        try:
            while not self._stop_event.is_set():
                self._run_single_cycle()
        except KeyboardInterrupt:
            self._log.info("Interrupted by user")
            self._emit("stop", "manual")
        except Exception as exc:
            self._log.exception("Fatal error: %s", exc)
            self._emit("error", exc)
            self._emit("stop", "error")
            raise
        finally:
            self._cleanup()

    def stop(self, reason: str = "manual") -> None:
        """
        Stop the Sniper bot.

        Parameters
        ----------
        reason : str, optional
            Reason for stopping (default: "manual").
        """
        self._log.info("Stopping Sniper: %s", reason)
        self._stop_event.set()
        self._set_state(self.STATE_STOP)
        self._emit("stop", reason)

    # ── Single Market Cycle ─────────────────────────────────────────────────────

    def _run_single_cycle(self) -> None:
        """Execute a single market cycle (discover → trade → resolve)."""
        # Check trade limits
        if self.config.max_trades and self._stats.total_trades >= self.config.max_trades:
            self._log.info("Max trades (%d) reached", self.config.max_trades)
            self.stop("max_trades")
            return

        # Check consecutive loss limit
        if (self.config.max_consecutive_losses and
            self._stats.consecutive_losses >= self.config.max_consecutive_losses):
            self._log.info("Max consecutive losses (%d) reached",
                          self.config.max_consecutive_losses)
            self.stop("max_losses")
            return

        # Discover market
        self._set_state(self.STATE_DISCOVERING)
        try:
            self._market = self.client.markets.latest(
                self.config.asset,
                self.config.timeframe
            )
            self._log.info("Market found: %s", self._market.slug)
            self._emit("market_found", self._market)
        except Exception as exc:
            self._log.error("Market discovery failed: %s", exc)
            self._emit("error", exc)
            time.sleep(5)  # Backoff before retry
            return

        # Check position size limit
        if self.config.max_position_size:
            current_positions = self.client.paper.positions()
            current_exposure = sum(
                p.shares * p.current_price
                for p in current_positions
                if not p.resolved
            )
            if current_exposure >= self.config.max_position_size:
                self._log.warning(
                    "Position size limit (%.2f) reached, skipping trade",
                    self.config.max_position_size
                )
                time.sleep(10)
                return

        # Set up stream and trade
        try:
            self._setup_stream()
            self._wait_for_window()
            self._execute_trade()
            self._wait_for_resolution()
        except Exception as exc:
            self._log.exception("Trade cycle error: %s", exc)
            self._emit("error", exc)
        finally:
            self._cleanup_stream()

        # Rollover
        self._set_state(self.STATE_ROLLOVER)
        self._emit("rollover", self._market)
        self._market = None
        time.sleep(1)  # Brief pause before next cycle

    # ── Stream Setup ───────────────────────────────────────────────────────────

    def _setup_stream(self) -> None:
        """Set up WebSocket stream for the current market."""
        self._stream = self.client.stream(self._market)

        # Register price handler
        @self._stream.on("price")
        def _on_price(up: float, down: float):
            self._on_price_update(up, down)

        # Register close handler
        @self._stream.on("close")
        def _on_close():
            self._on_market_close()

        # Register error handler
        @self._stream.on("error")
        def _on_error(exc: Exception):
            self._log.error("Stream error: %s", exc)

        # Attach stream to paper engine for limit order fills
        self.client.paper.attach_stream(self._stream, self._market)

        # Start stream in background
        self._stream.start(background=True)

        # Wait for connection
        time.sleep(1)
        self._log.info("Stream attached for %s", self._market.slug)

    def _cleanup_stream(self) -> None:
        """Clean up WebSocket stream."""
        if self._stream:
            try:
                self._stream.stop()
            except Exception:
                pass
            self._stream = None

    # ── Price Monitoring ───────────────────────────────────────────────────────

    def _on_price_update(self, up: float, down: float) -> None:
        """Handle price updates from the stream."""
        with self._state_lock:
            if self._state != self.STATE_ARMED:
                return

        current_price = up if self.config.side == "UP" else down

        if self.config.log_prices:
            self._log.debug("Price: %s=%.4f", self.config.side, current_price)

        # Check exit threshold
        if (self.config.exit_price is not None and
            self._pending_order and
            current_price <= self.config.exit_price):
            self._log.info("Exit threshold triggered: %.4f <= %.4f",
                          current_price, self.config.exit_price)
            self._cancel_order("exit_threshold")
            return

        # Check entry threshold
        if current_price >= self.config.entry_price and not self._pending_order:
            self._log.info("Entry threshold triggered: %.4f >= %.4f",
                          current_price, self.config.entry_price)
            self._place_order()

    # ── Window Management ─────────────────────────────────────────────────────

    def _wait_for_window(self) -> None:
        """Wait until the trading window opens."""
        self._set_state(self.STATE_WAITING)

        end_time = self._parse_end_time(self._market.end_time)
        window_start = end_time - timedelta(seconds=self.config.window_seconds + self.config.pre_window_buffer)

        self._log.info("Waiting for window: %s (ends at %s)",
                      self.config.window_seconds, end_time)

        while not self._stop_event.is_set():
            now = datetime.now(timezone.utc)

            if now >= window_start:
                self._log.info("Entering trading window")
                self._set_state(self.STATE_ARMED)
                self._emit("window_enter", self._market)
                return

            time.sleep(0.1)

    def _parse_end_time(self, end_time_str: str) -> datetime:
        """Parse market end time string to datetime."""
        # Try ISO format first
        for fmt in ("%Y-%m-%dT%H:%M:%SZ", "%Y-%m-%dT%H:%M:%S.%fZ",
                   "%Y-%m-%d %H:%M:%S", "%Y-%m-%dT%H:%M:%S"):
            try:
                return datetime.strptime(end_time_str, fmt).replace(tzinfo=timezone.utc)
            except ValueError:
                continue
        raise ValueError(f"Cannot parse end time: {end_time_str}")

    # ── Order Execution ───────────────────────────────────────────────────────

    def _place_order(self) -> None:
        """Place a limit order at the entry price."""
        try:
            order = self.client.paper.limit(
                self._market,
                side=self.config.side,
                price=self.config.entry_price,
                amount=self.config.amount,
            )
            self._pending_order = order
            self._log.info("Limit order placed: %s @ %.4f ($%.2f)",
                          order.side, order.price, order.amount)

            if self.config.log_trades:
                self._log.info("Order ID: %s", order.id[:8])

        except Exception as exc:
            self._log.error("Order placement failed: %s", exc)
            self._emit("error", exc)

    def _cancel_order(self, reason: str) -> None:
        """Cancel the pending order."""
        if self._pending_order:
            try:
                self.client.paper.cancel(self._pending_order.id)
                self._log.info("Order cancelled: %s (reason: %s)",
                              self._pending_order.id[:8], reason)
                self._emit("exit", reason)
            except Exception as exc:
                self._log.error("Order cancellation failed: %s", exc)
            finally:
                self._pending_order = None

    def _execute_trade(self) -> None:
        """Wait for order fill or window close."""
        end_time = self._parse_end_time(self._market.end_time)
        timeout_seconds = (end_time - datetime.now(timezone.utc)).total_seconds()

        if timeout_seconds <= 0:
            self._log.warning("Window already closed, skipping trade")
            return

        # Wait for fill or timeout
        start = time.time()

        while not self._stop_event.is_set():
            # Check if order was filled
            if self._pending_order and self._pending_order.status == "filled":
                self._filled_order = self._pending_order
                self._pending_order = None
                self._set_state(self.STATE_FILLED)
                self._emit("entry", self._filled_order)

                if self.config.log_trades:
                    self._log.info("Order filled: %.4f shares @ %.4f",
                                  self._filled_order.shares, self._filled_order.price)
                return

            # Check for timeout
            elapsed = time.time() - start
            if elapsed >= timeout_seconds + self.config.post_window_timeout:
                self._log.info("Window closed without fill")
                if self._pending_order:
                    self._cancel_order("window_close")
                return

            time.sleep(0.1)

    # ── Resolution ────────────────────────────────────────────────────────────

    def _wait_for_resolution(self) -> None:
        """Wait for market resolution and record outcome."""
        if not self._filled_order:
            return

        self._set_state(self.STATE_RESOLVING)

        # Wait for stream close event
        timeout = 120  # Max wait for resolution
        start = time.time()

        while not self._stop_event.is_set():
            if time.time() - start >= timeout:
                self._log.warning("Resolution timeout, forcing manual resolve")
                # In production, this would query the API for outcome
                # For paper, we'll mark as unresolved
                break

            # Check if stream has closed
            if not self._stream or not self._stream.running:
                break

            time.sleep(0.5)

        # Determine outcome from positions
        positions = self.client.paper.positions()
        for pos in positions:
            if pos.market_id == self._market.id and pos.resolved:
                self._record_trade(pos)
                return

        self._log.warning("No resolved position found for %s", self._market.slug)

    def _on_market_close(self) -> None:
        """Handle market close event."""
        self._log.info("Market closed: %s", self._market.slug)

        # For paper trading, we need to manually resolve
        # In production, this would be automatic
        pass

    def _record_trade(self, position) -> None:
        """Record a completed trade."""
        timestamp = datetime.now(timezone.utc)
        if self._filled_order and self._filled_order.filled_at:
            timestamp = self._filled_order.filled_at

        trade = TradeRecord(
            market_slug=self._market.slug,
            side=self.config.side,
            entry_price=self._filled_order.price if self._filled_order else 0,
            exit_price=self.config.exit_price,
            amount=self.config.amount,
            shares=position.shares,
            outcome=position.outcome,
            pnl=position.pnl,
            timestamp=timestamp,
        )

        self._stats.add_trade(trade)

        if self.config.log_trades:
            self._log.info("Trade recorded: %s %s pnl=$%.2f",
                          trade.outcome, trade.market_slug, trade.pnl)

        self._emit("resolve", trade.outcome, trade.pnl)

    # ── State Management ───────────────────────────────────────────────────────

    def _set_state(self, new_state: str) -> None:
        """Thread-safe state transition."""
        with self._state_lock:
            old_state = self._state
            self._state = new_state
            self._log.debug("State: %s → %s", old_state, new_state)

    # ── Event Emission ───────────────────────────────────────────────────────

    def _emit(self, event: str, *args) -> None:
        """Emit an event to all registered handlers."""
        handlers = self._handlers.get(event, [])
        for handler in handlers:
            try:
                handler(*args)
            except Exception as exc:
                self._log.exception("Handler error for event '%s': %s", event, exc)

    # ── Cleanup ─────────────────────────────────────────────────────────────

    def _cleanup(self) -> None:
        """Clean up resources on shutdown."""
        self._cleanup_stream()
        self._log.info("Sniper stopped. Stats: %d trades, %.1f%% win rate, $%.2f P&L",
                      self._stats.total_trades, self._stats.win_rate, self._stats.total_pnl)
