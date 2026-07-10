class PolyalphaError(Exception):
    """Base exception for all polyalpha errors."""


class MarketNotFound(PolyalphaError):
    """No market matched the given asset/timeframe or slug."""


class MarketClosed(PolyalphaError):
    """Market exists but is no longer active."""


class StreamDisconnected(PolyalphaError):
    """WebSocket dropped and could not reconnect within the retry budget."""


class InsufficientBalance(PolyalphaError):
    """Paper balance too low to place the order."""


class OrderNotFound(PolyalphaError):
    """No paper order matched the given ID."""


class OrderBookError(PolyalphaError):
    """Order book fetch or parse failed."""


class OrderBookNotFound(OrderBookError):
    """No order book data available for the requested token."""


class InsufficientAllowance(PolyalphaError):
    """Insufficient CLOB allowance for trading."""


class OrderRejected(PolyalphaError):
    """Order rejected by CLOB."""


class OrderTimeout(PolyalphaError):
    """Order timed out."""


class NetworkError(PolyalphaError):
    """Network connectivity error."""


class TransientError(PolyalphaError):
    """Transient error that can be retried."""


class PositionNotFound(PolyalphaError):
    """Position not found."""


class RiskLimitExceeded(PolyalphaError):
    """Risk management limit exceeded."""


class OrderCancelled(PolyalphaError):
    """Order cancelled by user or system."""
