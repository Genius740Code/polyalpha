"""
polyalpha — Python SDK for Polymarket.

The Client is the single entry point for all SDK features.

    client = polyalpha.Client()

    # Market discovery
    market = client.markets.latest("BTC", "5m")

    # Price streaming
    stream = client.stream(market)

    # Paper trading
    order = client.paper.buy(market, side="UP", amount=10.0)
"""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING, Optional

if TYPE_CHECKING:
    from .database.database import TradeDatabase

from .ai import OpenRouterClient
from .core import Market, TimeSync
from .markets import MarketClient
from .stream import Stream
from .trading import PaperEngine, RealTradingEngine
from .trading.paper_config import PaperConfig
from .trading.real_config import RealTradingConfig
from .trading.auto_redeem import AutoRedeemConfig
from .orderbook import ClobBookClient, OrderBookFeed
from .core.env import get_paper_config_from_env
from .utils.logging_utils import new_correlation_id, track_duration


class Client:
    """
    Main entry point for the polyalpha SDK.

    Parameters
    ----------
    balance            : Starting paper USDC balance (default 100.0).
    timeout            : HTTP request timeout in seconds (default 10).
    retries            : Number of HTTP retries on 5xx errors (default 3).
    log_level          : Python logging level string, e.g. "DEBUG", "INFO", "WARNING".
    rate_limit         : Max API requests per second (default None = unlimited).
    paper_config       : PaperConfig for paper trading realism options (default None).
    paper_config_from_env : Load paper trading config from environment variables (default False).
    db_path            : Path to SQLite database file for trade persistence (default None).
    openrouter_api_key : OpenRouter API key for AI features (default None = disabled).
    private_key        : Private key for real trading wallet (default None = disabled).
    rpc_url            : Polygon RPC URL for real trading (default None = disabled).
    polymarket_api_key : Polymarket API key for CLOB access (default None = disabled).
    real_config        : RealTradingConfig for real trading (default None = disabled).

    Attributes
    ----------
    markets : MarketClient  — discover and fetch markets.
    paper   : PaperEngine   — simulate orders and track P&L.
    ai      : OpenRouterClient | None — AI-powered analysis (if API key provided).
    real    : RealTradingEngine | None — real trading with actual funds (if credentials provided).

    Example
    -------
    >>> import polyalpha
    >>> client = polyalpha.Client(balance=500.0, log_level="INFO", rate_limit=10)
    >>> market = client.markets.latest("BTC", "5m")
    >>> stream = client.stream(market)
    """

    def __init__(
        self,
        balance:   float = 100.0,
        timeout:   int   = 10,
        retries:   int   = 3,
        log_level: str   = "WARNING",
        rate_limit: int | None = None,
        paper_config: PaperConfig | None = None,
        paper_config_from_env: bool = False,
        db_path: str | None = None,
        openrouter_api_key: str | None = None,
        private_key: str | None = None,
        rpc_url: str | None = None,
        polymarket_api_key: str | None = None,
        real_config: RealTradingConfig | None = None,
        chainlink_history=None,
    ):
        # Configure library-specific logger without affecting global logging
        self._log = logging.getLogger("polyalpha")
        self._log.setLevel(getattr(logging, log_level.upper(), logging.WARNING))

        self._cid = new_correlation_id()
        self._log.info("Client initialising (cid=%s)", self._cid[:8])

        # Load paper config from environment if requested
        if paper_config_from_env and paper_config is None:
            env_config = get_paper_config_from_env()
            paper_config = PaperConfig(**env_config)

        self._db: Optional[TradeDatabase] = None
        if db_path:
            from .database.database import TradeDatabase
            self._db = TradeDatabase(db_path)

        self.time_sync = TimeSync()
        self.markets = MarketClient(
            timeout=timeout,
            retries=retries,
            rate_limit=rate_limit,
            time_sync=self.time_sync,
        )
        self.paper   = PaperEngine(balance=balance, config=paper_config, db_path=db_path, db=self._db)
        self.ai      = OpenRouterClient(api_key=openrouter_api_key) if openrouter_api_key else None
        self._clob   = ClobBookClient(timeout=timeout, retries=retries, rate_limit=rate_limit)

        # Real trading (optional - requires all credentials)
        self.real: RealTradingEngine | None = None
        if private_key and rpc_url and polymarket_api_key:
            if real_config is None:
                real_config = RealTradingConfig(
                    private_key=private_key,
                    rpc_url=rpc_url,
                    polymarket_api_key=polymarket_api_key,
                )
            self.real = RealTradingEngine(
                private_key=private_key,
                rpc_url=rpc_url,
                polymarket_api_key=polymarket_api_key,
                config=real_config,
                db_path=db_path,
                db=self._db,
            )
            self._log.info("Real trading enabled")
        else:
            self._log.info("Real trading disabled (set private_key + rpc_url + polymarket_api_key)")

        if self.ai:
            self._log.info("AI analysis enabled via OpenRouter")
        else:
            self._log.info("AI analysis disabled (set openrouter_api_key)")

        if db_path:
            self._log.info("Database path: %s", db_path)

        # ── Chainlink history (read-only or shared) ──────────────────────
        # User chooses e.g. {"1m":10, "1h":50, "1s":20} → read via client.chainlink_history
        self.chainlink_history = None
        self._chainlink_history_owned = False
        if chainlink_history is not None and chainlink_history is not False:
            try:
                from .history import ChainlinkHistoryConfig, ChainlinkRecorder  # type: ignore
                from .history.view import ChainlinkHistoryView  # type: ignore

                if isinstance(chainlink_history, ChainlinkRecorder):
                    self.chainlink_history = chainlink_history
                    self._chainlink_history_owned = False
                elif isinstance(chainlink_history, ChainlinkHistoryConfig):
                    # client is reader by default — read_only
                    # if config says block etc, keep it but don't start WS automatically
                    rec = ChainlinkRecorder(config=chainlink_history, read_only=False)
                    # if user explicitly wants writer, they'd pass background start; we don't auto-start here
                    self.chainlink_history = rec
                    self._chainlink_history_owned = True
                elif isinstance(chainlink_history, dict):
                    cfg = ChainlinkHistoryConfig(warmup=dict(chainlink_history))
                    rec = ChainlinkRecorder(config=cfg, read_only=False)
                    self.chainlink_history = rec
                    self._chainlink_history_owned = True
                elif chainlink_history is True:
                    cfg = ChainlinkHistoryConfig(warmup={"1m": 20})
                    rec = ChainlinkRecorder(config=cfg, read_only=False)
                    self.chainlink_history = rec
                    self._chainlink_history_owned = True
                elif isinstance(chainlink_history, str):
                    # path to db — read_only view
                    from pathlib import Path as _P  # noqa
                    cfg = ChainlinkHistoryConfig(warmup={"1m": 20}, db_path=chainlink_history)
                    rec = ChainlinkRecorder(config=cfg, read_only=True)
                    # wrap in view for uniform API with default asset BTC
                    self.chainlink_history = ChainlinkHistoryView(rec, asset="BTC")
                    self._chainlink_history_owned = True
                # also allow ChainlinkHistoryView directly
                elif hasattr(chainlink_history, "candles"):
                    self.chainlink_history = chainlink_history
            except Exception as exc:
                self._log.warning("Client chainlink_history init failed: %s", exc)

        self._timeout = timeout
        self._retries = retries
        self._log.info(
            "Client ready — balance=%.1f, timeout=%d, retries=%d, rate_limit=%s",
            balance, timeout, retries, rate_limit or "unlimited",
        )

    @property
    def db(self) -> Optional[TradeDatabase]:
        return self._db

    def close(self) -> None:
        """Clean up resources (HTTP connections, etc.)."""
        self._log.info("Client closing — releasing resources")
        self.markets.close()
        self._clob.close()
        if self._db:
            self._db.close()
        if self.ai:
            self.ai.close()
        # chainlink history (only close if owned)
        rec = getattr(self, "chainlink_history", None)
        if rec is not None and getattr(self, "_chainlink_history_owned", False):
            try:
                # if it's a view, close underlying recorder
                inner = getattr(rec, "_rec", None)
                (inner or rec).stop()  # type: ignore
            except Exception:
                pass
        self._log.info("Client closed")

    def __enter__(self):
        """Context manager entry."""
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        """Context manager exit - ensures resources are cleaned up."""
        self.close()
        return False

    def check(self, force_ntp: bool = False) -> dict:
        """Run a pre-market health check and return a report.

        Checks
        ------
        1. **NTP clock sync** — ensures local clock drift is below the
           fail threshold so deterministic slug generation produces the
           correct Polymarket windows.
        2. **Gamma API reachability** — verifies the Polymarket Gamma API
           responds before a market lookup.

        Parameters
        ----------
        force_ntp : Force a fresh NTP query (bypasses cache).

        Returns
        -------
        dict with keys:
            ntp   : NTP sync report (offset, warnings, can_proceed).
            gamma : Gamma API health check.
            all_ok : True when every check passes.

        Example
        -------
        >>> client = polyalpha.Client()
        >>> report = client.check()
        >>> report["all_ok"]
        True
        """
        ntp_report = self.time_sync.sync(force=force_ntp)
        gamma_ok = self._check_gamma()
        all_ok = ntp_report["can_proceed"] and gamma_ok
        return {
            "ntp": ntp_report,
            "gamma": gamma_ok,
            "all_ok": all_ok,
        }

    def _check_gamma(self) -> bool:
        """Quick reachability check against the Gamma API."""
        try:
            from .core.constants import GAMMA_API
            import httpx
            with httpx.Client(timeout=5.0) as c:
                r = c.get(GAMMA_API + "/events", params={"limit": 1})
                r.raise_for_status()
                return True
        except Exception:
            return False

    def stream(self, market: Market, retries: int | None = None) -> Stream:
        """
        Create a real-time WebSocket price stream for *market*.

        Parameters
        ----------
        market  : Market returned by ``client.markets.latest()``.
        retries : Override the default reconnect budget.

        Returns
        -------
        Stream — call ``.start()`` (blocking) or ``.start(background=True)``.

        Example
        -------
        >>> stream = client.stream(market)
        >>>
        >>> @stream.on("price")
        >>> def on_price(up, down):
        ...     print(f"UP={up:.4f}  DOWN={down:.4f}")
        >>>
        >>> stream.start()
        """
        return Stream(
            market  = market,
            retries = retries if retries is not None else self._retries,
        )

    def orderbook(self, market: Market) -> OrderBookFeed:
        """
        Create a live order book feed for *market*.

        Fetches REST snapshots and accepts WebSocket updates via
        ``feed.attach_stream(client.stream(market))``.

        Example
        -------
        >>> feed = client.orderbook(market)
        >>> feed.refresh()
        >>> print(feed.up.mid_price if feed.up else None)
        """
        return OrderBookFeed(market=market, clob=self._clob)
