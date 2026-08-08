"""
Sniper bot — time-window entry with threshold-based execution.

The Sniper monitors market prices and executes limit orders only during
a specified time window before market resolution. It automatically
transitions to the next market after resolution, enabling continuous
automated trading.

Features:
- Time-window entry (only trades in final N seconds)
- Multiple time windows (disjoint periods, burst patterns, absolute times)
- Conditional windows (indicator-based: BTC price, RSI, SMA, custom)
- Day/hour filtering (trade only on specific days or hours)
- Dual-threshold strategy (entry/exit thresholds)
- Price range filtering (entry_price_min to entry_price_max)
- Excluded price ranges (avoid specific price segments)
- Auto-rollover to next market
- Risk management (position limits, consecutive loss protection)
- Performance monitoring (P&L, win rate, statistics)
- Event-driven architecture for custom logic

Usage
-----
    from polyalpha.bots import Sniper
    from polyalpha.bots.sniper import TimeWindow, ConditionalWindow, TimeFilter

    # Basic usage with single entry price (simple window_seconds)
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

    # Multiple offset windows (e.g., 2 min to 1 min before end, and last 30 seconds)
    sniper = Sniper(
        client=client,
        asset="BTC",
        timeframe="5m",
        side="UP",
        entry_price=0.92,
        exit_price=0.88,
        time_windows=[
            TimeWindow(start_offset=-120, end_offset=-60),
            TimeWindow(start_offset=-30, end_offset=0),
        ],
        amount=20.0,
    )

    # Absolute time windows (e.g., 01:00-02:00 and 02:30-03:00 UTC)
    sniper = Sniper(
        client=client,
        asset="BTC",
        timeframe="5m",
        side="UP",
        entry_price=0.92,
        exit_price=0.88,
        time_windows=[
            TimeWindow(start_time="01:00", end_time="02:00"),
            TimeWindow(start_time="02:30", end_time="03:00"),
        ],
        amount=20.0,
    )

    # Burst pattern (10 seconds on, 20 seconds off, repeating)
    sniper = Sniper(
        client=client,
        asset="BTC",
        timeframe="5m",
        side="UP",
        entry_price=0.92,
        exit_price=0.88,
        time_windows=[
            TimeWindow(burst_on=10, burst_off=20),
        ],
        amount=20.0,
    )

    # Conditional windows (trade only when BTC change < 2%)
    sniper = Sniper(
        client=client,
        asset="BTC",
        timeframe="5m",
        side="UP",
        entry_price=0.92,
        exit_price=0.88,
        time_windows=[
            TimeWindow(start_offset=-60, end_offset=0),
        ],
        conditional_windows=[
            ConditionalWindow(
                indicator="btc_change",
                operator="lt",
                threshold=2.0,
                periods=5
            ),
        ],
        amount=20.0,
    )

    # Day/hour filtering (only trade weekdays 9AM-5PM UTC)
    sniper = Sniper(
        client=client,
        asset="BTC",
        timeframe="5m",
        side="UP",
        entry_price=0.92,
        exit_price=0.88,
        time_windows=[
            TimeWindow(start_offset=-60, end_offset=0),
        ],
        time_filter=TimeFilter(
            days=[0, 1, 2, 3, 4],  # Monday-Friday
            hours=[9, 10, 11, 12, 13, 14, 15, 16, 17]  # 9AM-5PM
        ),
        amount=20.0,
    )

    # Combined: Multiple windows with conditions and time filtering
    sniper = Sniper(
        client=client,
        asset="BTC",
        timeframe="5m",
        side="UP",
        entry_price=0.92,
        exit_price=0.88,
        time_windows=[
            TimeWindow(start_time="01:00", end_time="02:00"),
            TimeWindow(start_time="02:30", end_time="03:00"),
        ],
        conditional_windows=[
            ConditionalWindow(
                indicator="btc_change",
                operator="lt",
                threshold=2.0,
                periods=5
            ),
        ],
        time_filter=TimeFilter(days=[0, 1, 2, 3, 4]),
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

import json as _json
import logging
import re
import threading
import time
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from typing import Any, Callable, Optional, List, Protocol

from ..core import ASSETS, TIMEFRAME_SECONDS, Market
from ..core.market_sessions import validate_session_list, get_session
from ..core.constants import (
    DEFAULT_WINDOW_SECONDS,
    DEFAULT_MAX_CONSECUTIVE_LOSSES,
    DEFAULT_PRE_WINDOW_BUFFER,
    DEFAULT_POST_WINDOW_TIMEOUT,
    DEFAULT_TA_LOOKBACK_PERIODS,
    MARKET_DISCOVERY_BACKOFF,
    POSITION_LIMIT_CHECK_DELAY,
    ROLLOVER_PAUSE,
    STREAM_SETUP_DELAY,
    PRICE_CHECK_INTERVAL,
    RESOLUTION_TIMEOUT,
    RESOLUTION_CHECK_INTERVAL,
)

log = logging.getLogger(__name__)


# ── Helpers ────────────────────────────────────────────────────────────────────

def _jloads(value, default):
    """JSON-decode *value* if it is a string, otherwise return it as-is."""
    if isinstance(value, str):
        try:
            return _json.loads(value)
        except Exception:
            return default
    return value if value is not None else default


# ── Time Window Configuration ──────────────────────────────────────────────────

@dataclass
class TimeWindow:
    """
    Flexible time window specification for trading.
    
    Supports multiple window types:
    - Offset-based: relative to market end (negative) or start (positive)
    - Absolute time: specific HH:MM times within market duration
    - Burst pattern: repeating on/off intervals
    
    Examples
    --------
    # Offset window (30 to 10 seconds before market end)
    TimeWindow(start_offset=-30, end_offset=-10)
    
    # Absolute time window (trade between 01:00 and 02:00 UTC)
    TimeWindow(start_time="01:00", end_time="02:00")
    
    # Burst pattern (10 seconds on, 20 seconds off, repeating)
    TimeWindow(burst_on=10, burst_off=20)
    """
    # Offset-based (relative to market end)
    start_offset: Optional[int] = None  # Seconds before market end (negative) or after start (positive)
    end_offset: Optional[int] = None    # Seconds before market end (negative) or after start (positive)
    
    # Absolute time (HH:MM format in UTC)
    start_time: Optional[str] = None   # HH:MM format
    end_time: Optional[str] = None     # HH:MM format
    
    # Burst pattern (repeating intervals)
    burst_on: Optional[int] = None      # Seconds to stay ON
    burst_off: Optional[int] = None     # Seconds to stay OFF
    
    def __post_init__(self):
        """Validate time window configuration."""
        # Validate offset-based window
        if self.start_offset is not None and self.end_offset is not None:
            if self.start_offset >= self.end_offset:
                raise ValueError(
                    f"start_offset ({self.start_offset}) must be less than end_offset ({self.end_offset})"
                )
        
        # Validate absolute time window
        if self.start_time is not None or self.end_time is not None:
            if self.start_time is None or self.end_time is None:
                raise ValueError(
                    "Both start_time and end_time must be provided for absolute time windows"
                )
            # Validate HH:MM format
            for time_val in [self.start_time, self.end_time]:
                if not re.match(r'^\d{2}:\d{2}$', time_val):
                    raise ValueError(
                        f"Time must be in HH:MM format, got {time_val}"
                    )
        
        # Validate burst pattern
        if self.burst_on is not None or self.burst_off is not None:
            if self.burst_on is None or self.burst_off is None:
                raise ValueError(
                    "Both burst_on and burst_off must be provided for burst patterns"
                )
            if self.burst_on <= 0 or self.burst_off <= 0:
                raise ValueError(
                    f"burst_on and burst_off must be positive, got {self.burst_on}, {self.burst_off}"
                )
        
        # Ensure only one window type is specified
        types_specified = sum([
            self.start_offset is not None,
            self.start_time is not None,
            self.burst_on is not None
        ])
        if types_specified > 1:
            raise ValueError(
                "Only one window type can be specified (offset, absolute time, or burst)"
            )
        if types_specified == 0:
            raise ValueError(
                "At least one window type must be specified"
            )


@dataclass
class ConditionalWindow:
    """
    Conditional time window based on market indicators.
    
    Window opens only when specified conditions are met using indicators
    like BTC price, Chainlink oracles, Binance data, etc.
    
    Examples
    --------
    # Trade only when BTC change < 2%
    ConditionalWindow(
        indicator="btc_change",
        operator="lt",
        threshold=2.0,
        periods=5
    )
    
    # Trade only when RSI < 30
    ConditionalWindow(
        indicator="rsi",
        operator="lt",
        threshold=30.0,
        source="binance"
    )
    """
    indicator: str  # "btc_change", "rsi", "sma", "custom"
    operator: str   # "lt", "lte", "gt", "gte", "eq"
    threshold: float
    source: Optional[str] = None  # "binance", "chainlink", "custom"
    periods: Optional[int] = None  # For multi-period indicators
    custom_check: Optional[Callable] = None  # Custom callable for complex conditions
    
    def __post_init__(self):
        """Validate conditional window configuration."""
        valid_operators = {"lt", "lte", "gt", "gte", "eq"}
        if self.operator not in valid_operators:
            raise ValueError(
                f"Invalid operator '{self.operator}'. Must be one of {valid_operators}"
            )
        
        valid_indicators = {"btc_change", "rsi", "sma", "custom"}
        if self.indicator not in valid_indicators:
            raise ValueError(
                f"Invalid indicator '{self.indicator}'. Must be one of {valid_indicators}"
            )
        
        if self.indicator == "custom" and self.custom_check is None:
            raise ValueError(
                "custom_check must be provided when indicator='custom'"
            )


@dataclass
class TimeFilter:
    """
    Time-based filtering for day of week and hour of day.
    
    Examples
    --------
    # Only trade Monday-Friday
    TimeFilter(days=[0, 1, 2, 3, 4])  # 0=Monday, 6=Sunday
    
    # Only trade 9AM-5PM UTC
    TimeFilter(hours=[9, 10, 11, 12, 13, 14, 15, 16, 17])
    
    # Combined: weekdays during business hours
    TimeFilter(days=[0, 1, 2, 3, 4], hours=[9, 10, 11, 12, 13, 14, 15, 16, 17])
    """
    days: Optional[List[int]] = None  # 0=Monday, 6=Sunday
    hours: Optional[List[int]] = None  # 0-23 UTC
    
    def __post_init__(self):
        """Validate time filter configuration."""
        if self.days is not None:
            if not all(0 <= d <= 6 for d in self.days):
                raise ValueError(
                    f"Days must be 0-6 (Monday-Sunday), got {self.days}"
                )
        
        if self.hours is not None:
            if not all(0 <= h <= 23 for h in self.hours):
                raise ValueError(
                    f"Hours must be 0-23, got {self.hours}"
                )
    
    def is_allowed(self, dt: datetime) -> bool:
        """Check if datetime passes the filter."""
        if self.days is not None and dt.weekday() not in self.days:
            return False
        if self.hours is not None and dt.hour not in self.hours:
            return False
        return True


# ── Configuration ─────────────────────────────────────────────────────────────

@dataclass
class SniperConfig:
    """
    Sniper bot configuration.

    All parameters are validated on initialization. Invalid values
    raise ValueError with descriptive messages.
    """

    # Market parameters
    timeframe: str
    asset: str = "BTC"
    side: str = "UP"

    # Trading parameters
    entry_price: float = 0.92
    entry_price_max: Optional[float] = None  # Maximum entry price for price range
    max_price: float = 1.0  # Max valid price from stream (edge cases can briefly exceed normal 1.0)
    exit_price: Optional[float] = 0.88
    excluded_price_ranges: Optional[List[tuple[float, float]]] = None  # List of (min, max) ranges to exclude
    window_seconds: int = DEFAULT_WINDOW_SECONDS
    amount: float = 20.0
    buy_once_per_market: bool = True

    # Staleness guard: skip entry when the stream's last price update is older
    # than this many seconds (the stream may have dropped / gone quiet).
    stale_data_max_age: float = 5.0

    # Advanced time windows (optional - overrides window_seconds if provided)
    time_windows: Optional[List[TimeWindow]] = None  # Multiple time windows
    conditional_windows: Optional[List[ConditionalWindow]] = None  # Indicator-based windows
    time_filter: Optional[TimeFilter] = None  # Day/hour filtering

    # Risk management
    max_position_size: Optional[float] = None
    max_consecutive_losses: Optional[int] = DEFAULT_MAX_CONSECUTIVE_LOSSES
    max_trades: Optional[int] = None

    # Market session filtering
    allowed_market_sessions: Optional[List[str]] = None  # e.g., ["london", "new_york"]

    # Performance tuning
    pre_window_buffer: int = DEFAULT_PRE_WINDOW_BUFFER
    post_window_timeout: int = DEFAULT_POST_WINDOW_TIMEOUT

    # Logging
    log_level: str = "INFO"
    log_trades: bool = True
    log_prices: bool = False

    # Technical analysis (optional)
    use_ta: bool = False
    ta_data_source: Optional[str] = None  # "binance" | "chainlink" | "custom"
    ta_rsi_threshold: Optional[float] = None
    ta_sma_period: Optional[int] = None
    ta_rules: Optional[list] = None  # Custom TA rules

    # BTC price change filter (optional)
    max_btc_change_pct: Optional[float] = None
    btc_change_periods: int = 5

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

        # Validate entry_price_max if provided
        if self.entry_price_max is not None:
            if not (0 < self.entry_price_max < 1):
                raise ValueError(
                    f"entry_price_max must be between 0 and 1, got {self.entry_price_max}"
                )
            if self.entry_price_max <= self.entry_price:
                raise ValueError(
                    f"entry_price_max ({self.entry_price_max}) must be greater than "
                    f"entry_price ({self.entry_price})"
                )

        # Validate max_price
        if self.max_price <= 0:
            raise ValueError(
                f"max_price must be positive, got {self.max_price}"
            )

        # Validate excluded_price_ranges if provided
        if self.excluded_price_ranges is not None:
            for i, (min_price, max_price) in enumerate(self.excluded_price_ranges):
                if not (0 < min_price < 1):
                    raise ValueError(
                        f"excluded_price_ranges[{i}][0] (min) must be between 0 and 1, got {min_price}"
                    )
                if not (0 < max_price < 1):
                    raise ValueError(
                        f"excluded_price_ranges[{i}][1] (max) must be between 0 and 1, got {max_price}"
                    )
                if min_price >= max_price:
                    raise ValueError(
                        f"excluded_price_ranges[{i}] min ({min_price}) must be less than max ({max_price})"
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

        # Validate staleness guard
        if self.stale_data_max_age <= 0:
            raise ValueError(
                f"stale_data_max_age must be positive, got {self.stale_data_max_age}"
            )

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

        # Validate allowed_market_sessions
        if self.allowed_market_sessions is not None:
            self.allowed_market_sessions = validate_session_list(self.allowed_market_sessions)

        # Validate max_btc_change_pct
        if self.max_btc_change_pct is not None:
            if self.max_btc_change_pct <= 0:
                raise ValueError(
                    f"max_btc_change_pct must be positive, got {self.max_btc_change_pct}"
                )

        # Validate btc_change_periods
        if self.btc_change_periods <= 0:
            raise ValueError(
                f"btc_change_periods must be positive, got {self.btc_change_periods}"
            )

        # Validate advanced time windows
        if self.time_windows is not None:
            if not isinstance(self.time_windows, list):
                raise ValueError(
                    f"time_windows must be a list, got {type(self.time_windows)}"
                )
            for i, window in enumerate(self.time_windows):
                if not isinstance(window, TimeWindow):
                    raise ValueError(
                        f"time_windows[{i}] must be a TimeWindow instance, got {type(window)}"
                    )

        # Validate conditional windows
        if self.conditional_windows is not None:
            if not isinstance(self.conditional_windows, list):
                raise ValueError(
                    f"conditional_windows must be a list, got {type(self.conditional_windows)}"
                )
            for i, window in enumerate(self.conditional_windows):
                if not isinstance(window, ConditionalWindow):
                    raise ValueError(
                        f"conditional_windows[{i}] must be a ConditionalWindow instance, got {type(window)}"
                    )

        # Validate time filter
        if self.time_filter is not None and not isinstance(self.time_filter, TimeFilter):
            raise ValueError(
                f"time_filter must be a TimeFilter instance, got {type(self.time_filter)}"
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
    market_session: Optional[str] = None  # "london" | "new_york" | "asia" | "sydney" | None


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

class StreamLike(Protocol):
    """Minimal surface an external price feed must expose to drive a Sniper.

    Matches what the native stream provides so an injected feed
    (e.g. :class:`polyalpha.bots.hub_feed.HubFeed`) is a drop-in
    replacement for ``client.stream(market)``.
    """

    @property
    def up(self) -> float:
        ...

    @property
    def down(self) -> float:
        ...

    @property
    def running(self) -> bool:
        ...

    def on(self, event: str) -> Callable:
        ...

    def start(self, background: bool = False) -> None:
        ...

    def stop(self) -> None:
        ...

    def price_age_seconds(self) -> float:
        ...


class Sniper:
    """
    Automated trading bot with advanced time-window entry and threshold execution.

    The Sniper monitors a market and executes limit orders only during
    specified time windows before resolution. It automatically transitions
    to the next market after resolution.

    Features
    --------
    - Simple time windows (window_seconds for basic use)
    - Multiple time windows (disjoint periods, burst patterns, absolute times)
    - Conditional windows (indicator-based: BTC price, RSI, SMA, custom)
    - Day/hour filtering (trade only on specific days or hours)
    - Dual-threshold strategy (entry/exit thresholds)
    - Price range filtering (entry_price_min to entry_price_max)
    - Excluded price ranges (avoid specific price segments)
    - Auto-rollover to next market
    - Risk management (position limits, consecutive loss protection)
    - Performance monitoring (P&L, win rate, statistics)
    - Event-driven architecture for custom logic

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

    Examples
    --------
    Basic usage with simple window_seconds:
    >>> sniper = Sniper(client, asset="BTC", timeframe="5m", side="UP",
    ...                 entry_price=0.92, exit_price=0.88, window_seconds=35,
    ...                 amount=20.0)
    >>> sniper.run()

    Advanced usage with multiple time windows:
    >>> from polyalpha.bots.sniper import TimeWindow, ConditionalWindow, TimeFilter
    >>> sniper = Sniper(client, config=SniperConfig(
    ...     asset="BTC", timeframe="5m", side="UP",
    ...     entry_price=0.92, exit_price=0.88,
    ...     time_windows=[
    ...         TimeWindow(start_time="01:00", end_time="02:00"),
    ...         TimeWindow(start_time="02:30", end_time="03:00"),
    ...     ],
    ...     conditional_windows=[
    ...         ConditionalWindow(indicator="btc_change", operator="lt", threshold=2.0),
    ...     ],
    ...     time_filter=TimeFilter(days=[0, 1, 2, 3, 4]),
    ...     amount=20.0
    ... ))
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

    def __init__(self, client, config: Optional[SniperConfig] = None, *, stream: Optional[StreamLike] = None, **kwargs):
        """
        Initialize the Sniper bot.

        Parameters
        ----------
        client : polyalpha.Client
            The polyalpha client instance.
        config : SniperConfig, optional
            Bot configuration. If not provided, uses defaults.
        stream : StreamLike, optional
            Pre-built price feed. When provided, the Sniper is driven off this
            external source (e.g. the shared hub feed) instead of opening its
            own WebSocket via ``client.stream(market)``. It must expose the
            same surface the Sniper expects from a stream: ``up``/``down``,
            ``on(event)``, ``price_age_seconds()``, ``running``, ``start()``
            and ``stop()`` — see :class:`polyalpha.bots.hub_feed.HubFeed`.
        **kwargs
            Additional keyword arguments passed to SniperConfig when config is not provided.
        """
        self.client = client
        if config is None:
            config = SniperConfig(**kwargs)
        self.config = config
        self._injected_stream: Optional[StreamLike] = stream

        # Set up logging
        self._log = logging.getLogger(f"{__name__}.Sniper")
        self._log.setLevel(getattr(logging, self.config.log_level.upper()))

        # State management
        self._state = self.STATE_IDLE
        self._state_lock = threading.Lock()
        self._stop_event = threading.Event()

        # Current market data
        self._market: Optional[Market] = None
        self._stream: Optional[StreamLike] = None
        self._pending_order = None
        self._filled_order = None
        self._final_up: Optional[float] = None
        self._final_down: Optional[float] = None

        # Statistics
        self._stats = SniperStats()

        # Event handlers
        self._handlers: dict[str, list[Callable]] = {}

        # Technical analysis (optional)
        self._ta_data = None
        self._ta_indicators = None
        self._ta_signals = None
        # Cached IndicatorCalculator per data source (for conditional windows)
        self._cond_ta: dict[str, "IndicatorCalculator"] = {}
        if self.config.use_ta:
            self._setup_ta()

        self._log.info("Sniper initialized: %s %s %s @ %s",
                      self.config.asset, self.config.timeframe,
                      self.config.side, self.config.entry_price)

    # ── Technical Analysis Setup ───────────────────────────────────────────────

    def _setup_ta(self) -> None:
        """Set up technical analysis components."""
        try:
            from ..analysis import DataFeed, DataFeedConfig, IndicatorCalculator, SignalGenerator

            source = self.config.ta_data_source or "binance"
            ta_config = DataFeedConfig(
                source=source,
                timeframe=self.config.timeframe,
                lookback_periods=DEFAULT_TA_LOOKBACK_PERIODS,
            )

            feed = DataFeed(ta_config)
            self._ta_data = feed.fetch(self.config.asset)
            self._ta_indicators = IndicatorCalculator(self._ta_data)
            self._ta_signals = SignalGenerator(self._ta_indicators)

            self._log.info("Technical analysis initialized with %s data", source)
        except ImportError:
            self._log.warning("Technical analysis dependencies not available")
            self.config.use_ta = False
        except Exception as exc:
            self._log.warning("Technical analysis setup failed: %s", exc)
            self.config.use_ta = False

    def _check_ta_conditions(self) -> bool:
        """Check if technical analysis conditions are met."""
        if not self.config.use_ta or self._ta_signals is None:
            return True  # No TA or TA failed, allow entry

        try:
            # Use custom rules if provided
            if self.config.ta_rules:
                result = self._ta_signals.evaluate(self.config.ta_rules)
                return result["result"]

            # Use default simple rules
            conditions_met = True

            # Check RSI
            if self.config.ta_rsi_threshold is not None:
                rsi_ok = self._ta_signals.rsi_above(self.config.ta_rsi_threshold)
                self._log.debug("TA: RSI > %.1f: %s", self.config.ta_rsi_threshold, rsi_ok)
                conditions_met = conditions_met and rsi_ok

            # Check SMA
            if self.config.ta_sma_period is not None:
                sma_ok = self._ta_signals.price_above_sma(self.config.ta_sma_period)
                self._log.debug("TA: Price > SMA(%d): %s", self.config.ta_sma_period, sma_ok)
                conditions_met = conditions_met and sma_ok

            return conditions_met

        except Exception as exc:
            self._log.error("Technical analysis check failed: %s", exc)
            return True  # Allow entry on error

    def _check_btc_change(self) -> bool:
        """
        Check if BTC spot price change is within the configured limit.

        Fetches BTC spot price data and calculates the percentage change
        over the configured lookback periods. Returns True if the change
        is within the limit (or filtering is disabled), False if BTC
        volatility is too high.

        Returns
        -------
        bool
            True if trading should proceed, False if BTC change is too high.
        """
        if self.config.max_btc_change_pct is None:
            return True  # No filtering

        try:
            from ..analysis import DataFeed, DataFeedConfig

            # Use Binance as the default source for BTC spot price data
            feed_config = DataFeedConfig(
                source="binance",
                timeframe=self.config.timeframe,
                lookback_periods=self.config.btc_change_periods + 5,
            )
            feed = DataFeed(feed_config)
            data = feed.fetch("BTC")

            if data is None or len(data) < 2:
                self._log.warning("Not enough BTC data for change calculation, allowing entry")
                return True

            # Get the close prices for the lookback period
            latest = data["close"].iloc[-1]
            if len(data) > self.config.btc_change_periods:
                prev = data["close"].iloc[-self.config.btc_change_periods]
            else:
                prev = data["close"].iloc[0]

            change_pct = abs((latest - prev) / prev) * 100
            self._log.debug(
                "BTC change: %.2f%% (limit: %.2f%%, periods: %d)",
                change_pct, self.config.max_btc_change_pct, self.config.btc_change_periods
            )

            if change_pct > self.config.max_btc_change_pct:
                self._log.info(
                    "BTC change %.2f%% exceeds max %.2f%%, skipping entry",
                    change_pct, self.config.max_btc_change_pct
                )
                return False

            return True

        except ImportError:
            self._log.warning("BTC change check dependencies not available, allowing entry")
            return True
        except Exception as exc:
            self._log.warning("BTC change check failed: %s, allowing entry", exc)
            return True

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

    def _check_trade_limits(self) -> bool:
        """Check if trading limits have been reached. Returns True if should stop."""
        if self.config.max_trades and self._stats.total_trades >= self.config.max_trades:
            self._log.info("Max trades (%d) reached", self.config.max_trades)
            self.stop("max_trades")
            return True

        if (self.config.max_consecutive_losses and
            self._stats.consecutive_losses >= self.config.max_consecutive_losses):
            self._log.info("Max consecutive losses (%d) reached",
                          self.config.max_consecutive_losses)
            self.stop("max_losses")
            return True

        return False

    def _check_position_limit(self) -> bool:
        """Check if position size limit has been reached. Returns True if should skip."""
        if not self.config.max_position_size:
            return False

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
            time.sleep(POSITION_LIMIT_CHECK_DELAY)
            return True

        return False

    def _discover_market(self) -> bool:
        """Discover a market. Returns True if successful."""
        self._set_state(self.STATE_DISCOVERING)
        # Reset order tracking for new market cycle
        self._pending_order = None
        self._filled_order = None
        try:
            self._market = self.client.markets.latest(
                self.config.asset,
                self.config.timeframe
            )
            # Fix orientation BEFORE stream creation to ensure correct initial prices
            self._fix_market_orientation(self._market)
            self._log.info("Market found: %s", self._market.slug)
            self._emit("market_found", self._market)
            return True
        except Exception as exc:
            self._log.error("Market discovery failed: %s", exc)
            self._emit("error", exc)
            time.sleep(MARKET_DISCOVERY_BACKOFF)
            return False

    def _fix_market_orientation(self, market: Market) -> None:
        """
        Fix UP/DOWN token and price orientation if API returns them swapped.
        
        Uses the raw Gamma event data to independently verify which token
        corresponds to UP, and swaps tokens/prices if needed.
        """
        if len(market.tokens) < 2 or len(market.prices) < 2:
            return
        
        try:
            raw = market.raw or {}
            sub = (raw.get("markets") or [{}])[0]
            outcomes = _jloads(sub.get("outcomes", "[]"))
            token_ids = _jloads(sub.get("clobTokenIds", "[]"))
            question = str(market.question or "").lower()
            
            q_higher = any(w in question for w in ("higher", "greater", "above"))
            q_lower = any(w in question for w in ("lower", "below"))
            
            def is_up(label: str) -> bool:
                label = str(label).lower()
                if any(w in label for w in ("up", "higher", "greater")):
                    return True
                return ("yes" in label and q_higher) or ("no" in label and q_lower)
            
            idx = next((i for i, lbl in enumerate(outcomes) if is_up(lbl)), None)
            if idx is None or idx >= len(token_ids):
                return
            
            true_up = str(token_ids[idx])
            if true_up and true_up == market.tokens[1]:
                # Swap tokens and prices
                market.tokens[0], market.tokens[1] = market.tokens[1], market.tokens[0]
                market.prices[0], market.prices[1] = market.prices[1], market.prices[0]
                self._log.warning(
                    "UP/DOWN orientation swapped for %s (%r) — corrected",
                    market.slug, market.question
                )
        except Exception as exc:
            self._log.debug("Orientation check failed: %s", exc)

    def _check_market_session(self) -> bool:
        """
        Check if current time is within an allowed market session.
        
        Returns True if trading should proceed (either no filtering or
        current session is allowed), False if should skip.
        """
        if self.config.allowed_market_sessions is None:
            # No session filtering enabled
            return True
        
        now = datetime.now(timezone.utc)
        current_session = get_session(now)
        
        if current_session is None:
            # Not in any session
            self._log.debug("Not in any market session, skipping trade")
            return False
        
        if current_session not in self.config.allowed_market_sessions:
            self._log.debug(
                "Current session '%s' not in allowed sessions %s, skipping trade",
                current_session,
                self.config.allowed_market_sessions
            )
            return False
        
        self._log.debug("Current session '%s' is allowed", current_session)
        return True

    def _run_single_cycle(self) -> None:
        """Execute a single market cycle (discover → trade → resolve)."""
        if self._check_trade_limits():
            return

        if not self._check_market_session():
            time.sleep(60)  # Wait before checking again
            return

        if not self._discover_market():
            return

        if self._check_position_limit():
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
        time.sleep(ROLLOVER_PAUSE)

    # ── Stream Setup ───────────────────────────────────────────────────────────

    def _setup_stream(self) -> None:
        """Set up the price feed for the current market.

        Prefers an externally-provided ``stream`` (hub-driven feed) so the
        Sniper is routed off its own WebSocket. Falls back to opening a
        native ``client.stream(market)`` otherwise.
        """
        assert self._market is not None, "_setup_stream called before market discovery"
        if self._injected_stream is not None:
            self._stream = self._injected_stream
            self._log.info("Using external price feed for %s", self._market.slug)
        else:
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

        # Start stream in background (skip when the external feed already runs)
        if not getattr(self._stream, "running", False):
            self._stream.start(background=True)

        # Wait for connection
        time.sleep(STREAM_SETUP_DELAY)
        self._log.info("Stream attached for %s", self._market.slug)

    def _cleanup_stream(self) -> None:
        """Clean up the price feed.

        Only stops streams the Sniper opened itself — an externally-provided
        feed is owned by the caller (e.g. the hub) and must stay alive across
        market cycles.
        """
        if self._stream:
            if self._stream is not self._injected_stream:
                try:
                    self._stream.stop()
                except Exception:
                    pass
            self._stream = None

    # ── Price Monitoring ───────────────────────────────────────────────────────

    def _price_age_seconds(self) -> float:
        """Age of the stream's last price update, or ``inf`` if unavailable."""
        if not self._stream:
            return float("inf")
        fn = getattr(self._stream, "price_age_seconds", None)
        if callable(fn):
            return float(fn())
        return float("inf")

    def _price_is_stale(self) -> bool:
        """True when the last stream price update predates ``stale_data_max_age``."""
        return self._price_age_seconds() > self.config.stale_data_max_age

    def _on_price_update(self, up: float, down: float) -> None:
        """Handle price updates from the stream."""
        with self._state_lock:
            if self._state != self.STATE_ARMED:
                return

            current_price = up if self.config.side == "UP" else down

            if self.config.log_prices:
                self._log.debug("Price: %s=%.4f", self.config.side, current_price)

            # Check exit threshold (UP exits when price falls, DOWN exits when price rises)
            if (self.config.exit_price is not None and
                self._pending_order and
                ((self.config.side == "UP" and current_price <= self.config.exit_price) or
                 (self.config.side == "DOWN" and current_price >= self.config.exit_price))):
                self._log.info("Exit threshold triggered: %.4f %s %.4f",
                              current_price, "<=" if self.config.side == "UP" else ">=", self.config.exit_price)
                self._cancel_order("exit_threshold")
                return

            # Check entry threshold with price range support
            price_in_range = current_price >= self.config.entry_price
            if self.config.entry_price_max is not None:
                price_in_range = price_in_range and current_price <= self.config.entry_price_max

            # Check if price is in excluded ranges
            price_excluded = False
            if self.config.excluded_price_ranges:
                for min_price, max_price in self.config.excluded_price_ranges:
                    if min_price <= current_price <= max_price:
                        price_excluded = True
                        if self.config.log_prices:
                            self._log.debug("Price %.4f in excluded range [%.4f, %.4f]",
                                          current_price, min_price, max_price)
                        break

            if price_in_range and not price_excluded and not self._pending_order:
                if self._filled_order and self.config.buy_once_per_market:
                    return
                max_str = f"-{self.config.entry_price_max:.4f}" if self.config.entry_price_max else ""
                self._log.info("Entry threshold triggered: %.4f >= %.4f%s",
                              current_price, self.config.entry_price, max_str)

                # Check technical analysis conditions
                if not self._check_ta_conditions():
                    self._log.debug("Technical analysis conditions not met, skipping entry")
                    return

                # Check BTC price change filter
                if not self._check_btc_change():
                    return

                # Staleness guard: reject entry when the stream's last price
                # update is older than the configured threshold.
                if self._price_is_stale():
                    age = self._price_age_seconds()
                    self._log.info("entry skipped: stale price (age=%.1fs) ul=%.4f",
                                  age, current_price)
                    return

                self._place_order()

    # ── Window Management ─────────────────────────────────────────────────────

    def _wait_for_window(self) -> None:
        """Wait until the trading window opens."""
        self._set_state(self.STATE_WAITING)

        # Use advanced time windows if configured, otherwise fall back to simple window_seconds
        if self.config.time_windows:
            self._wait_for_advanced_windows()
        else:
            self._wait_for_simple_window()

    def _wait_for_simple_window(self) -> None:
        """Wait for simple window_seconds-based window (backward compatible)."""
        end_time = self._parse_end_time(self._market.end_time)
        window_start = end_time - timedelta(seconds=self.config.window_seconds + self.config.pre_window_buffer)

        self._log.info("Waiting for window: %s (ends at %s)",
                      self.config.window_seconds, end_time)

        while not self._stop_event.is_set():
            now = datetime.now(timezone.utc)

            if now >= window_start:
                # Check conditional windows (indicator-based) — same gating as
                # the advanced window path, so window_seconds alone works too.
                if self.config.conditional_windows and not self._check_conditional_windows():
                    self._log.debug("Conditional windows not satisfied, waiting...")
                    time.sleep(PRICE_CHECK_INTERVAL)
                    continue

                self._log.info("Entering trading window")
                self._set_state(self.STATE_ARMED)
                self._emit("window_enter", self._market)
                return

            time.sleep(PRICE_CHECK_INTERVAL)

    def _wait_for_advanced_windows(self) -> None:
        """Wait for advanced time windows (multiple windows, burst patterns, etc.)."""
        end_time = self._parse_end_time(self._market.end_time)
        market_start = end_time - timedelta(seconds=TIMEFRAME_SECONDS[self.config.timeframe])

        self._log.info("Waiting for advanced time windows (ends at %s)", end_time)

        while not self._stop_event.is_set():
            now = datetime.now(timezone.utc)

            # Check time filter (day/hour restrictions)
            if self.config.time_filter and not self.config.time_filter.is_allowed(now):
                self._log.debug("Time filter not satisfied, waiting...")
                time.sleep(PRICE_CHECK_INTERVAL)
                continue

            # Check if we're in any of the configured time windows
            in_window = False
            active_window = None

            for window in self.config.time_windows:
                if self._is_in_time_window(window, now, market_start, end_time):
                    in_window = True
                    active_window = window
                    break

            # Check conditional windows (indicator-based)
            if in_window and self.config.conditional_windows:
                if not self._check_conditional_windows():
                    self._log.debug("Conditional windows not satisfied, waiting...")
                    in_window = False

            if in_window:
                window_type = self._get_window_type_string(active_window)
                self._log.info("Entering trading window (%s)", window_type)
                self._set_state(self.STATE_ARMED)
                self._emit("window_enter", self._market)
                return

            time.sleep(PRICE_CHECK_INTERVAL)

    def _is_in_time_window(self, window: TimeWindow, now: datetime, 
                          market_start: datetime, end_time: datetime) -> bool:
        """Check if current time is within the specified time window."""
        # Offset-based window
        if window.start_offset is not None and window.end_offset is not None:
            window_start = end_time + timedelta(seconds=window.start_offset)
            window_end = end_time + timedelta(seconds=window.end_offset)
            return window_start <= now <= window_end

        # Absolute time window
        if window.start_time is not None and window.end_time is not None:
            window_start_time = self._parse_hhmm(window.start_time)
            window_end_time = self._parse_hhmm(window.end_time)
            current_time = now.time()
            
            # Handle overnight windows (e.g., 23:00 to 02:00)
            if window_end_time < window_start_time:
                # Window spans midnight
                return current_time >= window_start_time or current_time <= window_end_time
            else:
                return window_start_time <= current_time <= window_end_time

        # Burst pattern
        if window.burst_on is not None and window.burst_off is not None:
            cycle_duration = window.burst_on + window.burst_off
            seconds_from_start = (now - market_start).total_seconds()
            position_in_cycle = seconds_from_start % cycle_duration
            return position_in_cycle < window.burst_on

        return False

    def _parse_hhmm(self, time_str: str) -> datetime.time:
        """Parse HH:MM string and return as time object."""
        hour, minute = map(int, time_str.split(':'))
        return datetime.time(hour=hour, minute=minute)

    def _get_window_type_string(self, window: TimeWindow) -> str:
        """Get human-readable description of window type."""
        if window.start_offset is not None:
            return f"offset: {window.start_offset}s to {window.end_offset}s"
        elif window.start_time is not None:
            return f"absolute: {window.start_time} to {window.end_time}"
        elif window.burst_on is not None:
            return f"burst: {window.burst_on}s on / {window.burst_off}s off"
        return "unknown"

    def _check_conditional_windows(self) -> bool:
        """Check if all conditional windows are satisfied."""
        if not self.config.conditional_windows:
            return True

        for window in self.config.conditional_windows:
            if not self._check_single_conditional_window(window):
                return False

        return True

    def _check_single_conditional_window(self, window: ConditionalWindow) -> bool:
        """Check if a single conditional window is satisfied."""
        try:
            current_value = self._get_indicator_value(window)
            
            if current_value is None:
                self._log.warning("Could not get value for indicator %s, skipping condition", window.indicator)
                return False

            # Apply operator
            result = self._apply_operator(current_value, window.threshold, window.operator)
            
            self._log.debug("Conditional check: %s %s %s = %s (current: %.2f)",
                          window.indicator, window.operator, window.threshold,
                          result, current_value)
            
            return result

        except Exception as exc:
            self._log.error("Error checking conditional window: %s", exc)
            return False

    def _get_indicator_value(self, window: ConditionalWindow) -> Optional[float]:
        """Get current value for the specified indicator."""
        if window.indicator == "btc_change":
            return self._get_btc_change(window.periods or self.config.btc_change_periods)
        elif window.indicator == "rsi":
            return self._get_rsi_value(window.source)
        elif window.indicator == "sma":
            return self._get_sma_value(window.source, window.periods)
        elif window.indicator == "custom" and window.custom_check:
            return window.custom_check()
        else:
            self._log.warning("Unknown indicator: %s", window.indicator)
            return None

    def _get_btc_change(self, periods: int) -> Optional[float]:
        """Get BTC price change percentage over specified periods."""
        try:
            from ..analysis import DataFeed, DataFeedConfig

            # Use Binance as the default source for BTC spot price data
            feed_config = DataFeedConfig(
                source="binance",
                timeframe=self.config.timeframe,
                lookback_periods=periods + 5,
            )
            feed = DataFeed(feed_config)
            data = feed.fetch("BTC")

            if data is None or len(data) < 2:
                self._log.warning("Not enough BTC data for change calculation")
                return None

            # Get the close prices for the lookback period
            latest = data["close"].iloc[-1]
            if len(data) > periods:
                prev = data["close"].iloc[-periods]
            else:
                prev = data["close"].iloc[0]

            return abs((latest - prev) / prev) * 100
        except Exception as exc:
            self._log.error("Error getting BTC change: %s", exc)
            return None

    def _get_ta_indicators(self, source: Optional[str]) -> Optional[Any]:
        """Fetch and cache an IndicatorCalculator for the given data source."""
        source = source or "binance"
        if source in self._cond_ta:
            return self._cond_ta[source]
        try:
            from ..analysis import DataFeed, DataFeedConfig, IndicatorCalculator

            feed_config = DataFeedConfig(
                source=source,
                timeframe=self.config.timeframe,
                lookback_periods=DEFAULT_TA_LOOKBACK_PERIODS,
            )
            feed = DataFeed(feed_config)
            data = feed.fetch(self.config.asset)
            indicators = IndicatorCalculator(data)
            self._cond_ta[source] = indicators
            return indicators
        except Exception as exc:
            self._log.error("Error building TA indicators from %s: %s", source, exc)
            return None

    def _get_rsi_value(self, source: Optional[str]) -> Optional[float]:
        """Get RSI value from specified source."""
        try:
            indicators = self._get_ta_indicators(source)
            if indicators is None:
                return None
            rsi = indicators.rsi(14)
            return indicators.get_latest_value(rsi)
        except Exception as exc:
            self._log.error("Error getting RSI value: %s", exc)
            return None

    def _get_sma_value(self, source: Optional[str], periods: Optional[int]) -> Optional[float]:
        """Get SMA value from specified source."""
        try:
            indicators = self._get_ta_indicators(source)
            if indicators is None:
                return None
            sma = indicators.sma(periods or 20)
            return indicators.get_latest_value(sma)
        except Exception as exc:
            self._log.error("Error getting SMA value: %s", exc)
            return None

    def _apply_operator(self, value: float, threshold: float, operator: str) -> bool:
        """Apply comparison operator."""
        if operator == "lt":
            return value < threshold
        elif operator == "lte":
            return value <= threshold
        elif operator == "gt":
            return value > threshold
        elif operator == "gte":
            return value >= threshold
        elif operator == "eq":
            return value == threshold
        else:
            raise ValueError(f"Unknown operator: {operator}")

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
        """Place a limit order at the current price (not entry_price)."""
        try:
            # Staleness guard: never read self._stream.{up,down} blindly when
            # the price feed has gone quiet.
            if self._price_is_stale():
                age = self._price_age_seconds()
                ul = getattr(self._stream, self.config.side.lower(), None)
                self._log.info("entry skipped: stale price (age=%.1fs) ul=%s",
                              age, "%.4f" % ul if ul is not None else "n/a")
                return

            # Get current price from stream
            current_price = getattr(self._stream, self.config.side.lower(), None)
            if current_price is None:
                self._log.error("Cannot get current price from stream for order placement")
                return
            
            # Validate price is within allowed range
            if current_price <= 0:
                self._log.warning(
                    "Invalid price %.4f from stream (must be > 0), skipping order",
                    current_price
                )
                return
            if current_price > self.config.max_price:
                self._log.warning(
                    "Price %.4f exceeds max_price %.4f — proceeding anyway (edge case)",
                    current_price, self.config.max_price
                )
            
            # Place limit order at current price (will fill immediately since current >= current)
            order = self.client.paper.limit(
                self._market,
                side=self.config.side,
                price=current_price,
                amount=self.config.amount,
            )
            self._pending_order = order
            self._log.info("Limit order placed: %s @ %.4f ($%.2f)",
                          order.side, order.price, order.amount)

            if self.config.log_trades:
                self._log.debug("Order ID: %s", order.id[:8])

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
                self._emit("entry", self._filled_order)

                if self.config.log_trades:
                    self._log.info("Order filled: %.4f shares @ %.4f",
                                  self._filled_order.shares, self._filled_order.price)

                if self.config.buy_once_per_market:
                    self._set_state(self.STATE_FILLED)
                    return
                # buy_once_per_market=False: stay ARMED and keep buying
                # until the window closes.

            # Check for timeout
            elapsed = time.time() - start
            if elapsed >= timeout_seconds + self.config.post_window_timeout:
                self._log.info("Window closed without fill")
                if self._pending_order:
                    self._cancel_order("window_close")
                return

            time.sleep(PRICE_CHECK_INTERVAL)

    # ── Resolution ────────────────────────────────────────────────────────────

    def _wait_for_resolution(self) -> None:
        """Wait for market resolution and record outcome."""
        if not self._filled_order:
            return

        self._set_state(self.STATE_RESOLVING)

        # Wait for stream close event
        start = time.time()

        while not self._stop_event.is_set():
            if time.time() - start >= RESOLUTION_TIMEOUT:
                self._log.warning("Resolution timeout, forcing manual resolve")
                break

            # Check if stream has closed
            if not self._stream or not self._stream.running:
                break

            time.sleep(RESOLUTION_CHECK_INTERVAL)

        # For paper trading, we need to manually resolve positions
        # Determine outcome based on final price
        final_up = getattr(self, '_final_up', None)
        final_down = getattr(self, '_final_down', None)

        if final_up is not None and final_down is not None:
            # Determine outcome: higher price wins
            outcome = "UP" if final_up > final_down else "DOWN"
            self._log.info("Paper resolution: %s (final prices: UP=%.4f, DOWN=%.4f)",
                          outcome, final_up, final_down)

            # Resolve the position (this saves to database)
            try:
                self.client.paper.resolve(self._market, outcome)
            except Exception as exc:
                self._log.error("Failed to resolve position: %s", exc)

            # Now record the trade
            positions = self.client.paper.positions()
            for pos in positions:
                if pos.market_id == self._market.id and pos.resolved:
                    self._record_trade(pos)
                    return

        self._log.warning("No resolved position found for %s", self._market.slug)

    def _on_market_close(self) -> None:
        """Handle market close event."""
        self._log.info("Market closed: %s", self._market.slug)
        if self._stream:
            self._final_up = self._stream.up
            self._final_down = self._stream.down

    def _record_trade(self, position) -> None:
        """Record a completed trade."""
        timestamp = datetime.now(timezone.utc)
        if self._filled_order and self._filled_order.filled_at:
            timestamp = self._filled_order.filled_at

        # Determine market session
        market_session = get_session(timestamp)

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
            market_session=market_session,
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
