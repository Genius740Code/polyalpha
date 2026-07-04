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

from .ai import OpenRouterClient
from .core import Market
from .markets import MarketClient
from .stream import Stream
from .trading import PaperEngine
from .trading.paper import PaperConfig


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
    openrouter_api_key : OpenRouter API key for AI features (default None = disabled).

    Attributes
    ----------
    markets : MarketClient  — discover and fetch markets.
    paper   : PaperEngine   — simulate orders and track P&L.
    ai      : OpenRouterClient | None — AI-powered analysis (if API key provided).

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
        openrouter_api_key: str | None = None,
    ):
        # Configure library-specific logger without affecting global logging
        self._log = logging.getLogger("polyalpha")
        self._log.setLevel(getattr(logging, log_level.upper(), logging.WARNING))

        self.markets = MarketClient(timeout=timeout, retries=retries, rate_limit=rate_limit)
        self.paper   = PaperEngine(balance=balance, config=paper_config)
        self.ai      = OpenRouterClient(api_key=openrouter_api_key) if openrouter_api_key else None

        self._timeout = timeout
        self._retries = retries

    def close(self) -> None:
        """Clean up resources (HTTP connections, etc.)."""
        self.markets.close()
        if self.ai:
            self.ai.close()

    def __enter__(self):
        """Context manager entry."""
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        """Context manager exit - ensures resources are cleaned up."""
        self.close()
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
